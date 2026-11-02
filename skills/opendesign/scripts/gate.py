# -*- coding: utf-8 -*-
"""opendesign 渲染前闸门 + 自愈修补

契约来源：`prompts/hyperframes_composer.md`（HyperFrames 视频合成契约）。

闸1 静态结构   DOM 契约断言（根元素/片段属性/轨道唯一/时间覆盖）+ 内联脚本语法 + 违禁 API 扫描
闸2 运行时     无头浏览器加载 index.html，自模拟 clip 显隐，采集页面异常 / 时间轴越界 / overflow
闸3 确定性     同一时刻渲染两次（两次都从 0 顺序走到该时刻，与真实渲染路径一致）画面必须一致
闸5 视觉复审   抽帧交视觉模型，查画面是否有实质内容、文字可读性与底部字幕安全区（在本模块，由调用方触发）

**不含「运动/信息量」检查**——那是 styled_video 的诉求，opendesign 不适用。

本模块既作为子进程脚本（默认入口）被 `OpendesignVideoTool.execute` 调用，也导出自愈修补函数。
输出约定：错误行以 "- " 开头（与 styled/manim 的闸门一致）；最后一行为 `GATE-KIND: <类别>`。
"""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

# 与 lyric_mv 一致的浏览器参数：允许 file:// 读本地脚本、关滚动条、禁 LCD 抗锯齿（保证像素稳定）。
# --enable-unsafe-swiftshader：新版 Chromium 默认禁用软件 WebGL，加上它 three.js 场景才能在无 GPU 的
# 渲染机上跑起来（与 hyperframes 的 `--browser-gpu auto` 回退 SwiftShader 同一个目的）。
PLAY_ARGS = ["--allow-file-access-from-files", "--hide-scrollbars", "--disable-lcd-text",
             "--enable-unsafe-swiftshader"]

_EXTERNAL_RE = re.compile(r'^\s*(?:https?:)?//', re.IGNORECASE)
_REPEAT_FOREVER_RE = re.compile(r'repeat\s*:\s*-\s*1')
# 墙钟驱动的 CSS 动画：渲染器只 seek GSAP 时间轴，CSS 动画的相位由页面加载时刻决定，
# 同一时刻两次渲染像素必然不同 —— 属确定性问题，静态阶段就要拦下（省得白跑一遍运行时）。
_CSS_CLOCK_ANIM_RE = re.compile(r'@keyframes|\banimation(?:-[\w-]+)?\s*:', re.IGNORECASE)
_EDITS_MAX = 8
_MAX_RUNTIME_SAMPLES = 16
_MAX_DET_SAMPLES = 6

# 契约明令禁止的调用：它们直接破坏确定性或离线可渲染性
_BANNED_API = [
    ("Math.random(", "数学随机数"),
    ("Date.now(", "当前时间"),
    ("performance.now(", "当前时间"),
    ("fetch(", "网络请求"),
    ("XMLHttpRequest(", "网络请求"),
    ("setInterval(", "定时器（会累积外部状态）"),
]

# 视觉复审用的抽帧提示：问清"有没有实质内容 + 文字可不可读 + 底部字幕安全区有没有被占"
_REVIEW_PROMPT = (
    "你在审查一帧 16:9 视频画面。只输出 JSON，不要解释、不要 markdown：\n"
    '{"has_content": <画面是否有实质内容（文字/图形/图像/排版），而不是纯色背景或近乎空屏>, '
    '"has_text": <画面里是否有文字>, '
    '"legible": <若有文字，是否清晰可读：与背景对比足够、无重叠遮挡>, '
    '"bottom_clean": <画面底部约 8~12%（下缘往上约 1/10 高度）是否没有文字/按钮/logo/装饰>, '
    '"issue": "<不通过时用一句话说明最该修的地方；通过则空字符串>"}'
)


# --------------------------------------------------------------------------- #
# 闸1 静态结构
# --------------------------------------------------------------------------- #
class _Dom(HTMLParser):
    """极简 DOM 收集器：只留标签名与属性，够做契约断言即可（不引第三方解析库）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements: list[dict] = []
        self.scripts: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        d = {}
        for k, v in attrs:
            d[k.lower()] = v if v is not None else ""
        self.elements.append({"tag": tag, "attrs": d})
        if tag == "script" and "src" not in d:
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._buf is not None:
            self.scripts.append("".join(self._buf))
            self._buf = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)


def _fnum(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _inum(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _elems_with_class(doc: _Dom, cls: str):
    out = []
    for e in doc.elements:
        if cls in (e["attrs"].get("class") or "").split():
            out.append(e)
    return out


def _static_check(html: str, width: int, height: int, duration_hint):
    """静态结构闸。返回 (errors, notes, meta)；meta 含 total 与 clips。"""
    doc = _Dom()
    doc.feed(html)
    errs: list[str] = []
    notes: list[str] = []

    def attr(e, k):
        return (e["attrs"].get(k) or "").strip()

    def label(e):
        return f"{e['tag']}#{attr(e, 'id')}" if attr(e, "id") else f"<{e['tag']}>"

    # —— 根元素
    root = next((e for e in doc.elements if "data-composition-id" in e["attrs"]), None)
    total = float(duration_hint) if duration_hint else 0.0
    if root is None:
        errs.append("缺少根合成元素（没有带 data-composition-id 的元素）")
    else:
        for k in ("data-duration", "data-width", "data-height"):
            if not attr(root, k):
                errs.append(f"根元素缺少 {k}")
        for k, want in (("data-width", width), ("data-height", height)):
            got = _inum(attr(root, k))
            if got is not None and want and got != int(want):
                errs.append(f"根元素 {k}={got} 与请求的 {int(want)} 不一致")
        if not total:
            total = _fnum(attr(root, "data-duration")) or 0.0

    # —— 时间元素：runtime 的显隐开关是 `data-start`（**不是** class="clip"，那只是全屏盒子的样式钩子）。
    #     `data-track-index` 官方标注为可选、仅供 Studio 时间轴显示，渲染既不读它也不靠它分层 —— 故不作校验。
    #     根元素自身时间范围等于总时长，不参与"片段覆盖"判断。
    clips: list[tuple] = []
    for e in doc.elements:
        if e is root:
            continue
        cls = (attr(e, "class") or "").split()
        if "data-start" not in e["attrs"]:
            if "clip" in cls:
                notes.append(f"{label(e)} 有 class=\"clip\" 却没有 data-start，永远不会被 runtime 隐去")
            continue
        s, d = _fnum(attr(e, "data-start")), _fnum(attr(e, "data-duration"))
        if s is None:
            errs.append(f"{label(e)} 的 data-start 不是数字：{attr(e, 'data-start')!r}")
            continue
        if d is None:
            errs.append(f"{label(e)} 有 data-start 但缺少合法的 data-duration")
            continue
        clips.append((s, d))
        if d <= 0:
            errs.append(f"时间元素 {label(e)} 的 data-duration={d:g} 非正数")
        if "clip" not in cls:
            notes.append(f"{label(e)} 未写 class=\"clip\"，拿不到全屏盒子（显隐不受影响）")
    if root is not None and not clips:
        errs.append("没有任何带 data-start/data-duration 的时间元素（runtime 靠它控制显隐，缺了整片是空的）")

    # —— 时间覆盖：片段应铺满 [0, 总时长]
    if clips and total > 0:
        max_end = max(s + d for s, d in clips)
        min_start = min(s for s, _ in clips)
        if abs(max_end - total) > 2.0:
            errs.append(f"片段最晚结束于 {max_end:.2f}s，与总时长 {total:.2f}s 相差 {abs(max_end - total):.2f}s（应 ≤2s）")
        if min_start > 0.6:
            errs.append(f"最早的片段从 {min_start:.2f}s 才开始，开头 {min_start:.2f}s 是空画面")

    # —— 内联脚本：违禁 API + 语法
    script_text = "\n".join(doc.scripts)
    for token, why in _BANNED_API:
        if token in script_text:
            errs.append(f"内联脚本出现 {token}（{why}）—— 契约要求确定性逻辑")
    if _REPEAT_FOREVER_RE.search(html):
        errs.append("出现 repeat: -1（无限循环动画会击穿截帧引擎）")
    if _CSS_CLOCK_ANIM_RE.search(html):
        errs.append("出现 CSS @keyframes / animation（相位由页面加载时刻决定，与逐帧 seek 对不上，"
                    "同一时刻两次渲染必然不同）—— 改用 GSAP 时间轴驱动")
    if doc.scripts:
        node = shutil.which("node")
        if not node:
            notes.append("未找到 node，跳过内联脚本语法检查")
        else:
            for js in doc.scripts:
                if not js.strip():
                    continue
                tmp = None
                try:
                    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fb:
                        fb.write(js)
                        tmp = fb.name
                    r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
                    if r.returncode != 0:
                        tail = [ln for ln in (r.stderr or r.stdout).splitlines() if ln.strip()][-3:]
                        errs.append("内联脚本语法错误：" + " ｜ ".join(tail)[:300])
                finally:
                    if tmp:
                        try:
                            os.unlink(tmp)
                        except OSError:
                            pass

    # —— 外链：脚本外链会直接导致离线渲染失败；其他资源只提示
    extern_notes = set()
    for e in doc.elements:
        for k in ("src", "href"):
            v = attr(e, k)
            if not v or not _EXTERNAL_RE.match(v):
                continue
            if e["tag"] == "script" and k == "src":
                errs.append(f"脚本仍引用外链 {v}（离线渲染加载不到，回退成本地相对路径）")
            else:
                extern_notes.add(f"{e['tag']} 引用外链 {v}（建议改成本地 assets/ 资源）")
    notes.extend(sorted(extern_notes))

    return errs, notes, {"total": total, "clips": clips}


# --------------------------------------------------------------------------- #
# 闸2/闸3 运行时 + 确定性（无头浏览器）
# --------------------------------------------------------------------------- #
_READY_JS = """() => {
  const r = document.querySelector('[data-composition-id]');
  if (!r) return false;
  const id = r.getAttribute('data-composition-id');
  const tls = window.__timelines || {};
  return !!(tls[id] && typeof tls[id].time === 'function');
}"""

# 自模拟 HyperFrames runtime 的显隐：官方契约里显隐开关是 `data-start` 本身（不是 class="clip"，
# 那只是全屏盒子的样式钩子），所以这里对所有带 data-start 的元素按区间开关 display，
# 再把 paused 时间轴 seek 到 t。（闸门阶段没有 hyperframes CLI 注入的 runtime，必须自己来。）
_SEEK_JS = """(t) => {
  const r = document.querySelector('[data-composition-id]');
  const id = r ? r.getAttribute('data-composition-id') : 'root';
  document.querySelectorAll('[data-start]').forEach(function (el) {
    const s = parseFloat(el.getAttribute('data-start'));
    const d = parseFloat(el.getAttribute('data-duration'));
    const on = (isFinite(s) && isFinite(d)) ? (t >= s && t < s + d) : true;
    el.style.display = on ? '' : 'none';
  });
  const tl = (window.__timelines || {})[id];
  if (tl && typeof tl.time === 'function') { tl.pause(); tl.time(t); }
  return true;
}"""

# seek 只改了 DOM/CSS 值，浏览器还没把新内容合成出来；此刻立刻截帧会拍到上一帧的合成结果，
# 同一 t 两次截帧就会出现亚像素级差异（假阳性）。等两帧 rAF 确保新内容已提交再截。
_COMMIT_JS = """() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"""


async def _seek(page, t) -> None:
    """把页面 seek 到 t 并等浏览器提交该帧，之后截帧才是这一时刻的画面。"""
    await page.evaluate(_SEEK_JS, t)
    await page.evaluate(_COMMIT_JS)


_WEBGL_JS = """() => {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl') || c.getContext('experimental-webgl'));
  } catch (e) { return false; }
}"""

_OVERFLOW_JS = """() => {
  const r = document.querySelector('[data-composition-id]');
  const els = [];
  if (r) els.push(r);
  document.querySelectorAll('.stage').forEach(el => els.push(el));
  return els.map(el => getComputedStyle(el).overflow);
}"""

_BOUNDS_JS = """() => {
  const r = document.querySelector('[data-composition-id]');
  const id = r ? r.getAttribute('data-composition-id') : 'root';
  const tl = (window.__timelines || {})[id];
  if (!tl || typeof tl.getChildren !== 'function') return null;
  return tl.getChildren(true, true, true).map(c => ({
    s: (c.startTime ? c.startTime() : 0),
    d: (c.duration ? c.duration() : 0)
  }));
}"""


def _img_range(shot: bytes) -> float:
    """单帧灰度极差（排查用；闸门本身不再据此判空帧）。"""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(shot)).convert("L")
        lo, hi = im.getextrema()
        return float(hi - lo)
    except Exception:
        return 255.0


# 同一时刻两次截帧的比对口径。
# 不能要求字节完全一致：浏览器对带 filter / blur / mix-blend-mode / will-change 的合成图层
# 有"复用缓存"和"重新光栅化"两条路径，内容完全相同的两帧也会因此出现稳定但不可见的抗锯齿差异
# （实测：整幅最大灰度差 13/255、仅 522 个像素超过 8，全部落在同一段文字图层的字缘上；换软光栅也一样）。
# 这类光栅噪声比"页面依赖随机数/当前时间"造成的语义差异小两三个数量级（实测后者平均差 6.34、
# 3.5 万个降采样点差 >8），所以比对前先做 k×k 均值降采样抹平噪声，再按容差判等 —— 真实的不确定性
# 依然会被判为不一致，而不可见的光栅噪声不会再把好页面拦下来。
_FRAME_DOWNSCALE = 4
_FRAME_MAX_DIFF = 12      # 降采样后单点允许的最大灰度差（blur 边缘实测可到 12）
_FRAME_MEAN_DIFF = 0.5    # 降采样后允许的平均灰度差


def _same_frame(a: bytes, b: bytes) -> bool:
    """两帧是否为"同一画面"（容许不可见的光栅化噪声）。"""
    if a == b:
        return True
    try:
        from PIL import Image, ImageChops
    except Exception:
        return False          # 没有 PIL 就退回严格字节比对，宁可严一点
    try:
        ia = Image.open(io.BytesIO(a)).convert("L")
        ib = Image.open(io.BytesIO(b)).convert("L")
    except Exception:
        return False
    k = _FRAME_DOWNSCALE
    w, h = ia.width // k, ib.height // k
    if ia.size != ib.size or w < 1 or h < 1:
        return False
    ia = ia.resize((w, h), Image.BOX)
    ib = ib.resize((w, h), Image.BOX)
    px = list(ImageChops.difference(ia, ib).getdata())
    return max(px) <= _FRAME_MAX_DIFF and sum(px) / len(px) <= _FRAME_MEAN_DIFF


def _sample_times(total: float, clips, n: int = _MAX_RUNTIME_SAMPLES) -> list[float]:
    """抽查时刻：片段入点、中点、结尾，加上均匀分布的点。"""
    if total <= 0:
        return [0.0]
    cand: list[float] = [0.2, round(total / 2, 3), round(max(0.3, total - 0.25), 3)]
    for s, d in clips:
        cand.append(round(s + 0.15, 3))
        cand.append(round(s + d / 2, 3))
        if d > 1.6:
            cand.append(round(s + d - 0.2, 3))
    if total > 2:
        cand += [round(total * k / 12, 3) for k in range(1, 12)]

    out, seen = [], set()
    for t in cand:
        t = round(t, 2)
        if t < 0 or t >= total or t in seen:
            continue
        seen.add(t)
        out.append(t)
    out.sort()
    if len(out) > n:
        step = len(out) / n
        out = [out[int(i * step)] for i in range(n)]
    return out


def _review_times(total: float, clips, k: int = 10):
    """视觉复审抽帧时刻：每个段落至少一个中点，首段补入场点、末段补退场点。

    之前只取每段中点、上限 4 帧，段落多时前面的段落会被抽样跳过，
    前段空镜或漏内容就查不出来；现在保证每段都被检查，并且首尾都有覆盖。
    """
    spans = [(s, d) for s, d in clips if d >= 1.0 and s < total and s + d > 0]
    if not spans:
        return [round(total * (i + 0.5) / k, 3) for i in range(k)] if total > 0 else [0.5]
    if len(spans) > k:
        step = len(spans) / k
        spans = [spans[int(i * step)] for i in range(k)]
    times: list[float] = []
    for idx, (s, d) in enumerate(spans):
        # 入场/退场采样避开转场与入场动画：至少留 1 秒，否则容易把"动画还没出现"误判成空画面
        pad = min(1.0, d * 0.25)
        times.append(round(s + d / 2, 3))
        if idx == 0:
            times.append(round(s + pad, 3))
        if idx == len(spans) - 1:
            times.append(round(s + d - pad, 3))
    return sorted({t for t in times if 0 < t < total})


async def _runtime(html_path: Path, w: int, h: int, total: float, clips,
                   frames_out: Path, review_times):
    """返回 (errors, notes, kind)。kind 为 None 表示运行时与确定性全过。"""
    from playwright.async_api import async_playwright

    errs: list[str] = []
    notes: list[str] = []
    page_errors: list[str] = []
    console_errors: list[str] = []
    samples = _sample_times(total, clips)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=PLAY_ARGS)
        page = await browser.new_page(viewport={"width": w, "height": h})
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        try:
            await page.goto(Path(html_path).resolve().as_uri(), wait_until="load")

            # 就绪：时间轴注册且可 seek（gsap 未加载 / 脚本报错都会让这一步超时）
            try:
                await page.wait_for_function(_READY_JS, timeout=20000)
            except Exception:
                detail = page_errors[0][:200] if page_errors else "无页面异常，疑似 gsap 未加载或脚本未执行"
                errs.append("页面加载后时间轴未注册（window.__timelines 里找不到根合成）：" + detail)
                return errs, notes, "runtime"

            # overflow：根元素与所有舞台必须 hidden，否则内容会溢出画布
            for ov in await page.evaluate(_OVERFLOW_JS):
                if ov and "hidden" not in ov:
                    errs.append(f"根元素/舞台的 overflow 是 {ov}，应为 hidden")
                    break

            # WebGL 可用性：用到 three.js 而本机又没有 WebGL 时提前说明，避免渲染阶段才发现走了降级分支
            try:
                uses_three = "THREE" in html_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                uses_three = False
            if uses_three and await page.evaluate(_WEBGL_JS) is False:
                notes.append("本机无可用 WebGL，three.js 场景会走降级分支（渲染机软渲染时同此）")

            # 时间轴越界：所有补间必须落在 [0, 总时长] 内
            children = await page.evaluate(_BOUNDS_JS)
            if children is None:
                notes.append("时间轴不是 gsap.timeline，跳过越界检查")
            else:
                over = [c for c in children if c["s"] < -0.01 or (c["s"] + c["d"]) > total + 0.05]
                if over:
                    c0 = over[0]
                    errs.append(f"{len(over)} 段动画超出 [0, {total:.2f}]s 区间（例 start={c0['s']:.2f} "
                                f"dur={c0['d']:.2f}）—— 绝对时间必须落在总时长内")

            # 逐时刻：seek → 采集运行时报错
            ran_err = []
            print(f"  · 闸门·运行时：抽查 {len(samples)} 个时刻", flush=True)
            for t in samples:
                try:
                    await _seek(page, t)
                except Exception as e:
                    ran_err.append((t, str(e)[:200]))
                    continue
                if page_errors:
                    break

            if page_errors:
                errs.append(f"页面脚本抛错：{page_errors[0][:200]}")
            elif ran_err:
                errs.append(f"{len(ran_err)}/{len(samples)} 个时刻 seek 时抛错（例 t={ran_err[0][0]} "
                            f"{ran_err[0][1]}）")
            if console_errors:
                notes.append(f"控制台报错 {len(console_errors)} 条（例：{console_errors[0][:120]}）")
            if errs:
                return errs, notes, "runtime"

            # 确定性：同一 t 渲染两次，画面必须一致（容许不可见的光栅噪声）。
            # 两次都从 0 顺序走到 t —— 与真实渲染路径一致（渲染器只会向前逐帧 seek）。
            # 之前用"跳去很远的时刻再跳回来"会误伤 GSAP fromTo + filter 的页面：
            # 跳回后某些图层的合成状态不会恢复，整帧看起来是另一层底，但那在正向播放里
            # 根本不会发生（实测某段 t=0.15 跳回后整幅差 84/255，正向两次完全相同）。
            print("  · 闸门·确定性：同一时刻两次渲染比对", flush=True)
            det_times = samples[:: max(1, len(samples) // _MAX_DET_SAMPLES)][:_MAX_DET_SAMPLES]
            det_bad = []
            for t in det_times:
                await _seek(page, 0.0)
                a = await _shot_at(page, t)
                await _seek(page, 0.0)
                c = await _shot_at(page, t)
                if not _same_frame(a, c):
                    det_bad.append((t, hashlib.md5(a).hexdigest()[:8], hashlib.md5(c).hexdigest()[:8]))
            if det_bad:
                errs.append(f"确定性失败：{len(det_bad)} 个时刻两次渲染像素不一致（例 t={det_bad[0][0]} "
                            f"{det_bad[0][1]}≠{det_bad[0][2]}）—— 画面代码里不能用随机数/当前时间/累积外部状态")
                return errs, notes, "determinism"

            # 全过：抽帧留给闸5 视觉复审
            if frames_out and review_times:
                shutil.rmtree(frames_out, ignore_errors=True)
                frames_out.mkdir(parents=True, exist_ok=True)
                for i, t in enumerate(review_times):
                    await _seek(page, t)
                    await page.screenshot(path=str(frames_out / f"f_{i:02d}.png"))
                notes.append(f"已抽 {len(review_times)} 帧待视觉复审")
        finally:
            await browser.close()
    return errs, notes, None


async def _shot_at(page, t: float) -> bytes:
    await _seek(page, t)
    return await page.screenshot(type="png")


# --------------------------------------------------------------------------- #
# 闸5 视觉复审（在主进程内调用，复用主 LLM 的多模态能力）
# --------------------------------------------------------------------------- #
def _frame_b64(p: Path, max_side: int = 1280):
    """压成 JPEG 再送视觉接口：整幅 PNG 一张 1~2MB，直接 base64 容易超限。"""
    try:
        from PIL import Image
        im = Image.open(p)
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return base64.b64encode(Path(p).read_bytes()).decode("ascii"), "image/png"


def _json_of(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                pass
    return {}


def review_frames(project_dir, llm_config: dict):
    """闸5：对 gate_frames/ 里的抽帧做视觉复审。返回问题列表；视觉接口不可用时返回 None。"""
    frames = sorted((Path(project_dir) / "gate_frames").glob("f_*.png"))
    if not frames:
        return None
    try:
        from skills.image_reader import describe_image_b64
    except Exception:
        return None
    issues = []
    for f in frames:
        b64, mime = _frame_b64(f)
        try:
            txt = describe_image_b64(b64, mime, _REVIEW_PROMPT, llm_config, timeout=90)
        except Exception:
            return None
        doc = _json_of(txt)
        if not doc:
            continue  # 视觉接口返回无法解析，不做判定
        # 没有文字不等于没问题：先看这一帧到底有没有实质内容，避免前段空镜被直接放行
        if doc.get("has_content") is False:
            issues.append(f"{f.name}：画面几乎没有内容（疑似空白或只有背景）")
            continue
        if doc.get("has_text") is not False and doc.get("legible") is False:
            issues.append(f"{f.name}：" + str(doc.get("issue") or "文字与背景对比不足"))
        if doc.get("bottom_clean") is False:
            issues.append(f"{f.name}：底部字幕安全区被文字/按钮/logo 占用")
    return issues


# --------------------------------------------------------------------------- #
# 自愈：让 LLM 只回传最小 find/replace 清单，原地修补 index.html
# --------------------------------------------------------------------------- #
_KIND_RULE = {
    "static": "这是静态结构错误：只修报错涉及的标签/属性（根元素属性、时间元素的 data-start/data-duration、"
              "内联脚本语法、违禁 API 或 CSS 墙钟动画），不要重排版面。",
    "runtime": "这是运行时报错：只修报错处相关的场景/元素及其脚本，别动其他场景。",
    "determinism": "这是确定性错误：只把非确定逻辑（Math.random / Date.now / 累积状态）换成确定写法，"
                   "不要改版式。",
    "visual": "这是视觉复审错误：只改文字颜色/描边/底板以提升对比，并把底部 8~12% 的元素上移或删除。",
    "image": "这是配图生成失败：只改报错那张 <img> 的 data-gen 描述（更短、更具体、去掉人名/品牌/敏感内容），"
             "或者删掉该 <img> 改用 CSS 图形替代；不要动其他版式与动画。",
}


def _repair_system(kind: str, duration, width, height) -> str:
    rule = _KIND_RULE.get(kind, "只修与本次错误直接相关的部分。")
    return f"""你是 HyperFrames 视频合成（index.html）的代码修复器。下面给你当前完整的 index.html 与具体错误。
只输出 JSON 修改清单，不要解释、不要 markdown、不要输出整份文件。

### 输出格式（严格）
{{"edits":[{{"find":"原文中逐字复制的一段唯一代码","replace":"修正后的代码"}}]}}

### HyperFrames 契约（修复不得违反）
- 根元素：<div id="root" data-composition-id="root" data-start="0" data-duration="{duration}"
  data-width="{width}" data-height="{height}">，且 overflow:hidden。
- 上屏元素：class="clip stage" + data-start + data-duration；显隐开关是 data-start，
  data-track-index 可选且不影响渲染层级（要压盖用 CSS z-index）。
- 时间轴：window.__timelines["root"] = gsap.timeline({{paused:true}})，所有动画的绝对秒数都在
  [0, {duration}] 内；用 from()/fromTo() 做入场，不要给 .clip/.stage 设 opacity 或 CSS transform 初始态。
- 确定性：禁止 Math.random() / Date.now() / performance.now() / fetch() / 网络请求 / repeat:-1 /
  CSS @keyframes 与 animation（墙钟相位无法被 seek 复现）。
- 脚本用本地相对路径（本地库清单里列出的文件名），不留 CDN 外链。
- 底部 8~12% 留白（字幕安全区），不放文字/按钮/logo。
- 中文字体用 system-ui, sans-serif，不写具体中文字体名。

### 修复规则
1. 最小修改：{rule}
2. find 必须从当前文件里**逐字复制**，且在全文**只出现一次**；太短容易重复，请带上足够上下文。
3. replace 保留原逻辑，只改必要部分；若要删除，replace 用空字符串。
4. 最多 {_EDITS_MAX} 处编辑；不要输出整份文件，不要输出解释。
5. 工程参数：{duration}s / {width}×{height}。"""


def _apply_edits(html: str, edits) -> tuple:
    """按 find/replace 原地修改；find 必须唯一。返回 (new_html, applied, failed)。"""
    if not isinstance(edits, list):
        return html, 0, ["edits 不是数组"]
    applied, failed = 0, []
    for ed in edits[:_EDITS_MAX]:
        if not isinstance(ed, dict):
            continue
        find = ed.get("find")
        if not isinstance(find, str) or not find:
            continue
        repl = ed.get("replace")
        repl = "" if repl is None else str(repl)
        n = html.count(find)
        if n != 1:
            failed.append(f"find 出现 {n} 次：{find[:60]!r}")
            continue
        html = html.replace(find, repl, 1)
        applied += 1
    return html, applied, failed


def repair_html(current_html: str, errs: list, kind: str, cfg: dict,
                duration, width: int, height: int) -> tuple:
    """让 LLM 只返回最小修改清单并应用到当前 HTML。返回 (new_html, applied, failed)。"""
    from .renderer import (
        _library_text, call_llm_text,
        _call_with_token_fallback, LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
    )

    ctx = (
        "【当前 index.html】\n```html\n" + current_html + "\n```\n\n"
        "【本次错误】\n" + "\n".join(f"- {e}" for e in (errs or [])[:5]) + "\n\n"
        "只输出 JSON 修改清单。"
    )
    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            # 附上本地库清单：修脚本引用时才能改成本地已落盘的文件名，而不是凭记忆写别的 CDN 地址
            system_prompt=_repair_system(kind, duration, width, height) + "\n\n" + _library_text(),
            context=ctx,
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
            protocol=cfg.get("protocol", "anthropic"),
            provider=cfg.get("provider"),
            thinking="disabled",
            max_tokens=budget,
            timeout=240,
            attempts=1,
        ),
        max_tokens=LONG_OUTPUT_MAX_TOKENS,
        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    doc = _json_of(raw)
    edits = doc if isinstance(doc, list) else (doc.get("edits") if isinstance(doc, dict) else None)
    new_html, applied, failed = _apply_edits(current_html, edits)
    return new_html, applied, failed


# --------------------------------------------------------------------------- #
# 子进程入口：给 OpendesignVideoTool.execute 调用
# --------------------------------------------------------------------------- #
def run_gates(project_dir, duration_s, width: int, height: int) -> tuple:
    """跑闸门，返回 (ok, out, errs, kind)。errs 为以 "- " 开头的错误行（已去掉前缀）。"""
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--project", str(project_dir),
        "--duration", str(float(duration_s)),
        "--width", str(int(width)),
        "--height", str(int(height)),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    errs = [ln.strip(" -\t") for ln in out.splitlines() if ln.lstrip().startswith("-")]
    kind = "runtime"
    for ln in out.splitlines():
        if ln.startswith("GATE-KIND:"):
            kind = ln.split(":", 1)[1].strip() or kind
    if r.returncode != 0 and not errs:
        errs = [(out.strip().splitlines() or ["闸门进程异常退出"])[-1][:300]]
    return r.returncode == 0, out, errs, kind


def main() -> int:
    ap = argparse.ArgumentParser(description="opendesign 渲染前闸门")
    ap.add_argument("--project", required=True, help="HyperFrames 项目目录（内含 index.html）")
    ap.add_argument("--duration", type=float, default=None, help="视频总时长（秒）；不给则读根元素 data-duration")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--frames-out", default=None, help="闸5 抽帧输出目录，默认 <project>/gate_frames")
    args = ap.parse_args()

    proj = Path(args.project)
    html_path = proj / "index.html"
    if not html_path.is_file():
        print(f"- 找不到 {html_path}", flush=True)
        print("GATE-KIND: static", flush=True)
        return 1

    html = html_path.read_text(encoding="utf-8")
    errs, notes, meta = _static_check(html, args.width, args.height, args.duration)
    for n in notes:
        print(f"  · {n}", flush=True)
    if errs:
        for e in errs:
            print(f"- {e}", flush=True)
        print("GATE-KIND: static", flush=True)
        return 1
    print("  · 闸门·静态结构：通过", flush=True)

    total = meta["total"]
    clips = meta["clips"]
    if total <= 0:
        print("- 无法确定视频总时长（根元素 data-duration 缺失或非法）", flush=True)
        print("GATE-KIND: static", flush=True)
        return 1

    frames_out = Path(args.frames_out) if args.frames_out else (proj / "gate_frames")
    review_times = _review_times(total, clips)
    try:
        r_errs, r_notes, kind = asyncio.run(
            _runtime(html_path, args.width, args.height, total, clips, frames_out, review_times)
        )
    except ImportError as e:
        print(f"  · 未安装 playwright，跳过运行时/确定性闸门（{e}）", flush=True)
        print("GATE-KIND: static", flush=True)
        return 0
    except Exception as e:
        print(f"- 运行时闸门执行失败：{e}", flush=True)
        print("GATE-KIND: runtime", flush=True)
        return 1

    for n in r_notes:
        print(f"  · {n}", flush=True)
    if r_errs:
        for e in r_errs:
            print(f"- {e}", flush=True)
        print(f"GATE-KIND: {kind or 'runtime'}", flush=True)
        return 1
    print("  · 闸门·运行时 / 确定性：通过", flush=True)
    print("GATE-KIND: ok", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
