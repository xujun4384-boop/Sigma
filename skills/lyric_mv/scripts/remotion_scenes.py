# -*- coding: utf-8 -*-
"""lyric_mv 的 Remotion 画面生成器（替代 canvas 版 scenes.js）。

职责边界：
  - 只负责「要画面 → 写 TSX → 同步注册表 → 过闸门 → 有界修复」；
  - 时间轴、歌词层、章节、进度条、颗粒全部由 remotion_runtime 的引擎负责，画面代码碰不到；
  - 画面代码里没有任何题材实体，内容全部来自 plan / story / 视觉圣经。

产物布局：
  <out_dir>/parts/shots-bN.tsx 或 parts/line-bN.tsx   模型写出的源文件（可复用）
  <out_dir>/parts/registry.json                        场景 id → 文件/导出名/时间
  runtime/src/scenes/generated/*.tsx                   实际参与编译的副本
  runtime/src/scenes/registry.ts                       引擎读的注册表
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tsx_exports import has_named_export

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parents[1] / "remotion_runtime"
GENERATED = RUNTIME / "src/scenes/generated"
REGISTRY = RUNTIME / "src/scenes/registry.ts"
RENDER = RUNTIME / "scripts/render_mv.py"

# 镜头批大小（一个批次一次模型调用）
SHOTS_PER_CALL = int(os.environ.get("LYRIC_MV_TSX_SHOTS_PER_CALL", "3"))
LINES_PER_CALL = int(os.environ.get("LYRIC_MV_TSX_LINES_PER_CALL", "4"))

BANNED = [
    (r"\bMath\.random\b", "Math.random（会让逐帧不可复现）"),
    (r"\bDate\.now\b", "Date.now（会让逐帧不可复现）"),
    (r"\bperformance\.now\b", "performance.now"),
    (r"\bwindow\b", "window（画面代码里不允许碰浏览器对象）"),
    (r"\bdocument\b", "document"),
    (r"\bfetch\s*\(", "fetch（离线渲染，不能联网）"),
    (r"\bsetTimeout\b", "setTimeout"),
    (r"\bsetInterval\b", "setInterval"),
    (r"\brequestAnimationFrame\b", "requestAnimationFrame"),
    (r"\beval\s*\(", "eval"),
    (r"\bnew\s+Function\b", "new Function"),
    (r"\brequire\s*\(", "require"),
    (r"@keyframes|animation\s*:", "CSS 动画（必须用帧驱动）"),
]

# XML/SVG 命名空间是标识符，不是网络请求：<svg xmlns="http://www.w3.org/2000/svg"> 完全合法。
# 先把它剔掉再查外部 URL，否则会把整批正常镜头误判成"用了外网"。
NS_URL = re.compile(r"https?://(?:www\.)?w3\.org/[\w./#-]*")
EXTERNAL_URL = re.compile(r"https?://")

ALLOWED_IMPORTS = (
    "react", "remotion",
    "./char-hero", "./char-cast",
    "../../types", "../../ui", "../../ui/Actor", "../../ui/Chibi",
    "../../engine/context", "../../engine/math", "../../engine/measure", "../../engine/theme",
    "@remotion/effects", "@remotion/paths", "@remotion/shapes", "@remotion/motion-blur",
)

SPEC = """# 你在写 Remotion 画面组件

一个镜头 = 一个 React 组件。**只输出一个 TSX 文件，不要解释、不要 Markdown 代码块之外的文字。**

## 文件结构（必须严格遵守）

```tsx
import React from 'react';
import {AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {useE} from '../../engine/context';

export const META = {7: {bg: '#0e1424'}};   // 键=镜头编号，bg=这个镜头的整体底色

export const Shot7: React.FC = () => {
  const e = useE();
  return (
    <AbsoluteFill style={{backgroundColor: '#0e1424'}}>
      <svg viewBox={`0 0 ${e.W} ${e.H}`} width={e.W} height={e.H}>…</svg>
    </AbsoluteFill>
  );
};
```

- 导出名必须是 `Shot<镜头编号>`（叙事）或 `Line<句序号>`（逐句），编号用我给你的一基/零基编号，一字不差。
- `META` 必须给出每个组件对应编号的 `bg`（深色或浅色，引擎据此决定歌词用浅字还是深字）。
- 组件里只能有 **一个** `useE()` 调用点；不要用 `useCurrentFrame` 另算时间（e.t 已经是秒）。

## 环境对象 e（等价于 canvas 版的 e）

| 字段 | 含义 |
|---|---|
| `e.t` `e.dt` | 秒 / 1fps |
| `e.line` `e.i` `e.n` | 当前歌词句（text/start/end/chars）。**空档时也返回一个空对象**，字段可直接读；判断有没有歌调用 `e.hasLine` |
| `e.kind` | scene / intro / interlude / outro / gap |
| `e.u` `e.cardT` | 本卡 0~1 进度 / 卡内已过秒 |
| `e.shotU` `e.shotT` `e.shotDur` | 镜头内 0~1 进度 / 已过秒 / 总长（优先用这三个） |
| `e.beat` `e.beatIdx` `e.bar` `e.phase` | 连续拍位 / 第几拍 / 第几小节 / 拍内相位 |
| `e.strong` `e.pulse(k)` `e.hit(n)` | 强拍包络 / 每拍衰减 / 是否踩拍 |
| `e.sung` → 用 `e.line.chars` 自己算 | 逐字时间在 `e.line.chars[i][1]` |
| `e.W` `e.H` | 画布尺寸（1920×1080） |
| `e.P` `e.hexA(c,a)` `e.isDark(c)` | 调色板 / 加透明度 / 判深浅 |
| `e.rnd(s)` `e.hash(s)` | 确定性伪随机（seed 可以是数字或字符串；禁止 Math.random） |
| `e.lerp(a, b, t)` | 从 a 到 b 插值，**第三个参数才是进度**（不要把 t 放第一位） |
| `e.clamp(v, a, b)` `e.clamp01(v)` `e.seg(a, b, v)` | 限幅 / 0~1 限幅 / a→b 区间进度 |
| `e.easeOut(x)` `e.easeIn(x)` `e.easeIO(x)` `e.back(x)` `e.elastic(x)` `e.wave(x)` | **都只接一个 0~1 参数**，返回 0~1；不要传起止值 |
| `e.lyricBox` | 歌词占用矩形 `[x0,y0,x1,y1]`（**1280×720 坐标系，乘 1.5 就是 1920×1080**） |

## 硬性规则

1. **确定性**：同样的 `e.t` 必须画出同样的像素。禁止随机、时间戳、外部状态。
2. **不要画歌词**：字幕由引擎画。画面主体、人脸、关键道具都避开 `e.lyricBox`；短标题/标签可以写，但不要重复歌词原文。
3. **禁止整帧亮度脉动**：卡点只做位移/形变/缩放；整屏明暗往复会被出片验收拦下。
4. **必须有一个一眼可辨的主体**：不要只有渐变和色块。人物、道具、场景至少一个清楚的对象。
5. **构图**：主体重心放在画面中下部，左右留 ≥120px 安全边；不要把主体堆在四个角。
6. **一致性**：同一角色/场景跨镜头用同一套造型参数（写成模块级常量，复制到每个组件里）。
7. 只用 SVG / React / CSS transform；不要图片外链、不要字体网络加载（中文用系统字体栈）。
8. 允许 import：react / remotion / @remotion/effects/* / @remotion/paths / @remotion/shapes /
   @remotion/motion-blur / ../../engine/context / ../../engine/math / ../../engine/measure /
   ../../engine/theme。除此之外一律不要。

## 质感基线（达不到就是没画完）

- 背景：主色渐变 + 一处光晕 + 一处暗角，不要纯色铺满。
- 主体：至少 3 层（暗部/本体/高光），轮廓要干净；人物有脸、有手、有脚。
- 前景：一层虚化/颗粒/暗角压边，让画面有纵深。
- 运动：入场用缓入缓出（`e.easeIO`/`e.back`），不要匀速直线；静止时留 1~2px 呼吸。
"""

SPEC_TAIL = """
## 输出前自检
- 组件名与编号一致；`META` 覆盖所有编号；`bg` 与画面主色一致。
- 每个组件都能在 `e.t` 任意取值下渲染，不依赖 React 状态。
- 没有 `Math.random` / `window` / `document` / 定时器 / 外链。
"""


def _log(msg: str) -> None:
    print(f"[tsx] {msg}", flush=True)


def _run(cmd: str, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), shell=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def clean_code(txt: str) -> str:
    t = (txt or "").strip()
    m = re.search(r"```(?:tsx|ts|jsx|js)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    return t


def _code_only(code: str) -> str:
    """只保留真正会执行的代码。

    静态闸门拦的是「代码做了什么」，不是「画面上写了什么」：注释、字符串字面量、
    JSX 文本节点里的同一串字（例如构图板上的标签 window）都不该被判违规。
    """
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c == "/" and i + 1 < n and code[i + 1] == "/":
            j = code.find("\n", i)
            i = n if j == -1 else j
        elif c == "/" and i + 1 < n and code[i + 1] == "*":
            j = code.find("*/", i + 2)
            out.append("\n" * code.count("\n", i, j + 2 if j != -1 else n))
            i = n if j == -1 else j + 2
        elif c in ("'", '"', "`"):
            q, j = c, i + 1
            while j < n:
                if code[j] == "\\":
                    j += 2
                    continue
                if code[j] == q:
                    break
                j += 1
            out.append(q + q)
            i = j + 1
        else:
            out.append(c)
            i += 1
    text = "".join(out)
    # JSX 文本节点：>标签文字<（同一行、不含花括号，避免误伤普通运算符表达式）
    return re.sub(r">([^<>{};\n]*)<", "><", text)


def static_check(code: str) -> list[str]:
    errs = []
    body = _code_only(code)
    for pat, why in BANNED:
        if re.search(pat, body):
            errs.append(f"用了 {why}")
    if EXTERNAL_URL.search(NS_URL.sub("", body)):
        errs.append("用了 外部 URL（渲染机无外网）")
    # 只认行首的 import 语句：代码字符串里的 "from '...'" 不是真的导入
    for m in re.finditer(r"""^[ \t]*import\s+(?:[^'"]*\s+from\s+)?['"]([^'"]+)['"]""",
                         code, re.M):
        mod = m.group(1)
        if not any(mod == a or mod.startswith(a + "/") for a in ALLOWED_IMPORTS):
            errs.append(f"import 了不允许的模块 {mod}")
    return errs


def _ask_tsx(label: str, system: str, ctx: str, llm, cfg: dict, dump_fn, w: Path,
             need: list[str], tries: int = 3) -> str | None:
    """要模型写一小段 TSX：语法/禁用项先自查，错就带着具体原因重试。"""
    last = ""
    for k in range(1, tries + 1):
        try:
            raw = llm(system, ctx, cfg, meta_label=f"tsx-{label}-{k}")
        except Exception as e:
            last = f"调用失败：{e}"
            _log(f"  {label} 第 {k} 次{last}")
            continue
        code = clean_code(raw)
        dump_fn(f"tsx-{label}-{k}", code)
        missing = [n for n in need if not has_named_export(code, n)]
        if "export const META" not in code:
            missing.append("META")
        errs = static_check(code)
        if missing:
            errs.append("缺少导出：" + "、".join(missing))
        if not errs:
            return code
        last = "；".join(errs)
        _log(f"  {label} 第 {k} 次不合规：{last[:160]}")
        ctx += f"\n\n【上一次输出被拦下的原因，必须修正】\n{last}\n只输出修正后的完整文件。"
    _log(f"  {label} 放弃：{last[:200]}")
    return None


def sync_registry(w: Path, namespace: str = "") -> None:
    manifest_p = w / "parts" / "registry.json"
    # 外部工具（编辑器 / PowerShell Out-File）可能写成带 BOM 的 UTF-8，utf-8-sig 都能读
    manifest = json.loads(manifest_p.read_text(encoding="utf-8-sig")) if manifest_p.exists() else {}
    GENERATED.mkdir(parents=True, exist_ok=True)
    keep = {ent["file"] for ent in manifest.values()}
    # 定妆角色（char-*.tsx）不属于任何镜头文件，必须保留
    keep |= {p.name for p in GENERATED.glob("char-*.tsx")}
    for old in GENERATED.glob("*.tsx"):
        if old.name in keep:
            continue
        # namespace 隔离：只清理自己前缀的产物。lyric_mv 与 styled 共用同一运行时，
        # 不加隔离会互相删掉对方已经渲好的镜头文件。
        if namespace and not old.name.startswith(namespace + "-"):
            continue
        old.unlink()
    # 源文件统一拷进 runtime，保证 import 路径是相对的、可编译的
    for src in sorted((w / "parts").glob("*.tsx")):
        if src.name not in keep:
            continue
        dst = GENERATED / src.name
        if not dst.exists() or dst.read_text(encoding="utf-8") != src.read_text(encoding="utf-8"):
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    imports, entries = [], []
    imports.append("import {DefaultFiller} from './DefaultFiller';")
    entries.append("  'default.filler': {comp: DefaultFiller, bg: '#0b0d16'},")
    by_file: dict[str, list[dict]] = {}
    for key, ent in manifest.items():
        by_file.setdefault(ent["file"], []).append(ent)
    for i, (fname, items) in enumerate(sorted(by_file.items())):
        alias = f"M{i}"
        names = ", ".join(sorted({it["export"] for it in items}))
        imports.append(f"import {{{names}, META as {alias}}} from './generated/{fname.replace('.tsx', '')}';")
        for it in items:
            entries.append(f"  '{it['key']}': {{comp: {it['export']}, bg: {alias}[{it['index']}]?.bg}},")
    body = "\n".join(imports) + "\n\nexport type SceneEntry = {comp: React.FC; bg?: string};\n\n"
    body += "export const REGISTRY: Record<string, SceneEntry> = {\n" + "\n".join(entries) + "\n};\n"
    REGISTRY.write_text("import React from 'react';\n" + body, encoding="utf-8")


def _plan_for_gate(w: Path, plan: dict, manifest: dict) -> None:
    """闸门渲染前先写 render-plan：否则渲染器不知道时间→组件的映射，会渲出空画面。"""
    rp = dict(plan)
    shots = [v for v in manifest.values() if v["key"].startswith("shot-")]
    lines = [v for v in manifest.values() if v["key"].startswith("line-")]
    if shots:
        rp["shots"] = [{"start": v.get("start", 0), "end": v.get("end", 0), "scene": v["key"]}
                       for v in sorted(shots, key=lambda x: x["index"])]
    if lines:
        rp["scenes"] = [v["key"] for v in sorted(lines, key=lambda x: x["index"])]
        rp.setdefault("filler", "default.filler")
    rp.setdefault("lyricStyle", "band")
    (w / "render-plan.json").write_text(json.dumps(rp, ensure_ascii=False, indent=2), encoding="utf-8")


def gate(w: Path, tl: dict, plan: dict, times: list[float], manifest: dict,
         namespace: str = "") -> tuple[bool, str, str]:
    """静态 → 编译 → 运行时（strict） → 确定性。
    返回 (ok, 致命错误, 类型告警)。
    语法错/运行时错/不确定 → 致命；类型错（TS2xxx/TS7xxx）只作为告警：
    模型仍在学 API，一次类型告警值得回灌修一次，但不该把整片拦死。"""
    sync_registry(w, namespace=namespace)
    out_lines: list[str] = []
    warnings: list[str] = []

    # 1 静态：禁用项 + import 白名单（逐文件，映射回镜头时刻）
    for src in sorted((w / "parts").glob("*.tsx")):
        errs = static_check(src.read_text(encoding="utf-8"))
        if errs:
            ent = next((v for v in manifest.values() if v["file"] == src.name), None)
            t = ent.get("t") if ent else None
            out_lines.append(f"- t={t:.3f} {src.name}：" + "；".join(errs) if t is not None
                             else f"- {src.name}：" + "；".join(errs))

    # 2 编译：tsc 报错带文件/行号；语法错致命，类型错只告警
    r = _run("npx tsc --noEmit", RUNTIME, timeout=600)
    if r.returncode != 0:
        for line in (r.stdout or r.stderr or "").splitlines():
            m = re.match(r"src/scenes/generated/([^()]+)\((\d+),\d+\):\s*error\s+(TS\d+):\s*(.*)", line.strip())
            if not m:
                continue
            fname, ln, code, msg = m.group(1), m.group(2), m.group(3), m.group(4)
            ent = next((v for v in manifest.values() if v["file"] == fname), None)
            t = ent.get("t") if ent else None
            text = f"{fname}:{ln} {msg}"
            if code.startswith("TS1"):
                out_lines.append(f"- t={t:.3f} {text}" if t is not None else f"- {text}")
            else:
                warnings.append(f"- t={t:.3f} {text}" if t is not None else f"- {text}")
        if r.returncode != 0 and not out_lines and not warnings:
            out_lines.append("- 编译失败（错误不在画面文件里）："
                             + " ".join((r.stdout or r.stderr or "").splitlines()[:3]))

    # 3 运行时 + 4 确定性：交给 render_mv --gate（strict 模式，崩溃直接失败）
    if not out_lines:
        _plan_for_gate(w, plan, manifest)
        cmd = (f'"{sys.executable}" "{RENDER}" "{w}" --gate '
               f'--times={",".join(f"{t:.3f}" for t in times)} --fps=30')
        rr = _run(cmd, RUNTIME, timeout=1800)
        text = (rr.stdout or "") + (rr.stderr or "")
        bad = [l for l in text.splitlines() if l.strip().startswith("- t=")]
        out_lines.extend(bad)
        if rr.returncode != 0 and not bad:
            out_lines.append("- 闸门渲染失败：" + " ".join(text.splitlines()[-3:]))

    return (len(out_lines) == 0), "\n".join(out_lines), "\n".join(warnings)


def _bad_batches(text: str, manifest: dict) -> set[int]:
    """把闸门报错行里的 t= 映射回批次号（文件名里的 -bN）。"""
    bad: set[int] = set()
    for line in (text or "").splitlines():
        m = re.search(r"t=([0-9]+(?:\.[0-9]+)?)", line)
        if not m:
            continue
        t = float(m.group(1))
        ent = min(manifest.values(), key=lambda v: abs(float(v.get("t") or 0) - t))
        mm = re.search(r"-b(\d+)\.tsx", ent["file"])
        if mm:
            bad.add(int(mm.group(1)))
    return bad


def _pick_times(entries: list[dict], cap: int = 8) -> list[float]:
    ts = [e["t"] for e in entries if e.get("t") is not None]
    if len(ts) <= cap:
        return ts
    step = len(ts) / cap
    return [ts[min(len(ts) - 1, int(i * step))] for i in range(cap)]


# ───────────────────────────── 叙事型：按镜头写 ─────────────────────────────

def generate_story(w: Path, tl: dict, plan: dict, story: dict, cfg: dict, llm, dump_fn,
                   force: bool = False, only_batches=None, review_notes=None):
    shots = story.get("shots") or []
    if not shots:
        return False, "故事蓝图没有镜头表", None
    parts = w / "parts"
    parts.mkdir(exist_ok=True)
    manifest_p = parts / "registry.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8")) if manifest_p.exists() else {}

    batches = [list(range(i, min(i + SHOTS_PER_CALL, len(shots))))
               for i in range(0, len(shots), SHOTS_PER_CALL)]
    only = set(only_batches or ())

    bible = ""
    bpath = w / "visual-bible.json"
    if bpath.exists():
        bible = bpath.read_text(encoding="utf-8")
    plan_txt = json.dumps(plan, ensure_ascii=False)

    def ctx_of(bi, idxs, err=""):
        base = ("【本批要画的镜头】\n" + "\n".join(
            f"镜头 {i + 1}（id={shots[i].get('id')}）：{float(shots[i].get('start', 0)):.2f}~"
            f"{float(shots[i].get('end', 0)):.2f}s，景别 {shots[i].get('size') or '中景'}；"
            f"内容：{shots[i].get('action') or shots[i].get('desc') or ''}"
            for i in idxs)
            + f"\n\n本批导出：{', '.join(f'Shot{i + 1}' for i in idxs)}，"
            + f"META 覆盖编号 {', '.join(str(i + 1) for i in idxs)}。"
            + "\n\n【编导方案】\n" + plan_txt
            + ("\n\n【视觉圣经 · 全片统一，优先级仅次于用户要求】\n" + bible if bible else "")
            + f"\n\n本批镜头在整片中的位置：第 {idxs[0] + 1}~{idxs[-1] + 1} 个，共 {len(shots)} 个。"
            + ("\n承接上一批的情绪与画面状态，但不要重复它的构图。" if bi > 1 else "")
            + ("\n\n【上一版这几帧被指出问题，针对性修正（不要改 start/end）】\n"
               + "\n".join(review_notes.get(bi, [])) if review_notes and bi in review_notes else ""))
        if err:
            base += ("\n\n【闸门/编译报出的问题 · 只改本批，导出名和编号不要动】\n"
                     + err + "\n逐条修掉，不要解释，只输出完整文件。")
        return base

    def gen(bi, idxs, err="", tries=3):
        need = [f"Shot{i + 1}" for i in idxs]
        _log(f"  镜头批 {bi}/{len(batches)} {'修复' if err else '生成'}中...")
        code = _ask_tsx(f"shots-b{bi}", SPEC + SPEC_TAIL, ctx_of(bi, idxs, err),
                        llm, cfg, dump_fn, w, need, tries=tries)
        if code is None:
            return False
        (parts / f"shots-b{bi}.tsx").write_text(code, encoding="utf-8")
        for i in idxs:
            manifest[f"shot-{i + 1}"] = {
                "key": f"shot-{i + 1}", "file": f"shots-b{bi}.tsx",
                "export": f"Shot{i + 1}", "index": i + 1,
                "start": shots[i].get("start", 0), "end": shots[i].get("end", 0),
                "t": round((float(shots[i].get("start", 0)) + float(shots[i].get("end", 0))) / 2, 3),
            }
        manifest_p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    for bi, idxs in enumerate(batches, 1):
        if only and bi not in only:
            continue
        if (parts / f"shots-b{bi}.tsx").exists() and not force and not only:
            _log(f"  镜头批 {bi}/{len(batches)} 复用")
            continue
        if not gen(bi, idxs):
            return False, f"镜头批 {bi} 未通过", None

    entries = [v for v in manifest.values() if v["key"].startswith("shot-")]
    times = _pick_times(entries)
    fixed: set[int] = set()
    ok, out, warn = True, "", ""
    for attempt in range(3):
        ok, out, warn = gate(w, tl, plan, times, manifest)
        if ok and not warn:
            break
        bad = _bad_batches(out if not ok else warn, manifest) - fixed
        if not bad:
            break
        if attempt == 2:
            break
        for bi in sorted(bad):
            fixed.add(bi)
            if not gen(bi, batches[bi - 1], err=(out if not ok else warn)):
                return False, f"镜头批 {bi} 修复失败", None
    if not ok:
        return False, "闸门未通过：" + out[-300:], None
    scenes = w / "scenes.tsx"
    scenes.write_text(json.dumps(sorted(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return True, f"{len(batches)}批 / {len(shots)}镜", scenes


# ───────────────────────────── 表演型/文字类：按句写 ─────────────────────────────

def generate_lines(w: Path, tl: dict, plan: dict, brief: str, cfg: dict, llm, dump_fn,
                   mode: str = "performance", force: bool = False,
                   only_batches=None, review_notes=None):
    parts = w / "parts"
    parts.mkdir(exist_ok=True)
    lines = tl.get("lines") or []
    if not lines:
        return False, "没有歌词行", None
    manifest_p = parts / "registry.json"
    manifest = json.loads(manifest_p.read_text(encoding="utf-8")) if manifest_p.exists() else {}
    batches = [list(range(i, min(i + LINES_PER_CALL, len(lines))))
               for i in range(0, len(lines), LINES_PER_CALL)]
    only = set(only_batches or ())

    bible = ""
    bpath = w / "visual-bible.json"
    if bpath.exists():
        bible = bpath.read_text(encoding="utf-8")
    type_block = ""
    tp = w / "type-plan.json"
    if tp.exists():
        type_block = "\n\n【字效方案】\n" + tp.read_text(encoding="utf-8")
    # Remotion 引擎不注入任何预设画风：画法由画面作者自己判断
    style_block = ""
    plan_txt = json.dumps(plan, ensure_ascii=False)

    def ctx_of(bi, idxs, err=""):
        base = ("【本批要画的内容】\n" + "\n".join(
            f"第 {i} 句（{lines[i]['start']:.2f}~{lines[i]['end']:.2f}s，{lines[i].get('section', '')}）："
            f"「{lines[i]['text']}」" for i in idxs)
            + f"\n\n本批导出：{', '.join(f'Line{i}' for i in idxs)}，"
            + f"META 覆盖编号 {', '.join(str(i) for i in idxs)}。"
            + "\n逐字时间在 e.line.chars（[字, 开始秒]），做逐字动画用 e.line.chars[i][1]。"
            + "\n\n【编导方案】\n" + plan_txt
            + ("\n\n【视觉圣经 · 全片统一】\n" + bible if bible else "")
            + ("\n\n【美术方向（只影响画法，不限制内容）】\n" + style_block if style_block else "")
            + type_block
            + (f"\n\n【用户要求】\n{brief}" if brief else "")
            + ("\n承接上一批的视觉语言，不要重复构图。" if bi > 1 else "")
            + ("\n\n【上一版这些问题必须修】\n" + "\n".join(review_notes.get(bi, []))
               if review_notes and bi in review_notes else ""))
        if err:
            base += ("\n\n【闸门/编译报出的问题 · 只改本批，导出名和编号不要动】\n"
                     + err + "\n逐条修掉，不要解释，只输出完整文件。")
        return base

    def gen(bi, idxs, err="", tries=3):
        need = [f"Line{i}" for i in idxs]
        _log(f"  句子批 {bi}/{len(batches)} {'修复' if err else '生成'}中...")
        code = _ask_tsx(f"line-b{bi}", SPEC + SPEC_TAIL, ctx_of(bi, idxs, err),
                        llm, cfg, dump_fn, w, need, tries=tries)
        if code is None:
            return False
        (parts / f"line-b{bi}.tsx").write_text(code, encoding="utf-8")
        for i in idxs:
            manifest[f"line-{i}"] = {
                "key": f"line-{i}", "file": f"line-b{bi}.tsx",
                "export": f"Line{i}", "index": i,
                "start": lines[i]["start"], "end": lines[i]["end"],
                "t": round((lines[i]["start"] + lines[i]["end"]) / 2, 3),
            }
        manifest_p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    for bi, idxs in enumerate(batches, 1):
        if only and bi not in only:
            continue
        if (parts / f"line-b{bi}.tsx").exists() and not force and not only:
            _log(f"  句子批 {bi}/{len(batches)} 复用")
            continue
        if not gen(bi, idxs):
            return False, f"句子批 {bi} 未通过", None

    # 闸门：致命错误（语法/运行时/不确定）必改；类型告警先回灌修一轮，仍不过就带告警放行
    entries = [v for v in manifest.values() if v["key"].startswith("line-")]
    times = _pick_times(entries)
    fixed: set[int] = set()
    out, warn = "", ""
    for attempt in range(3):
        ok, out, warn = gate(w, tl, plan, times, manifest)
        if ok and not warn:
            break
        bad = _bad_batches(out if not ok else warn, manifest) - fixed
        if not bad:
            if ok:
                break
            return False, "闸门未通过：" + out[-300:], None
        if attempt == 2:
            break
        for bi in sorted(bad):
            fixed.add(bi)
            if not gen(bi, batches[bi - 1], err=(out if not ok else warn)):
                return False, f"句子批 {bi} 修复失败", None

    if not ok:
        return False, "闸门未通过：" + (out or warn)[-300:], None
    if warn:
        _log(f"  ⚠ 仍有 {len(warn.splitlines())} 条类型告警（已放行，逐条见 llm/tsx-*）")
    scenes = w / "scenes.tsx"
    scenes.write_text(json.dumps(sorted(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return True, f"{len(batches)}批 / {len(lines)}句", scenes
