"""styled_video —— 导演组的单段风格动画引擎（Remotion 版）。

一段 = 一个 Remotion 场景，时长由导演给；画面由 LLM 直接写 TSX，
与 lyric_mv 的镜头作者走同一条路线（同一运行时、同一套闸门）。

风格不再来自固定枚举：导演按用户需求写一份 styleGuide，原样注入生成提示词。
无歌词层（plain 模式），旁白/字幕/合成仍由导演组后续处理。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parents[1]
RUNTIME = SKILLS_ROOT / "remotion_runtime"
GENERATED = RUNTIME / "src" / "scenes" / "generated"
RENDER = RUNTIME / "scripts" / "render_mv.py"

sys.path.insert(0, str(SKILLS_ROOT / "lyric_mv" / "scripts"))
import remotion_scenes as rs  # noqa: E402

NAMESPACE = "styled"
MAX_TRIES = max(1, int(os.environ.get("STYLED_REMOTION_TRIES", "2")))


def _log(msg: str) -> None:
    print(f"[styled] {msg}", flush=True)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


SYSTEM = """你是动画美术导演，用 Remotion 写一段 10~30 秒的风格动画。

## 这一段的任务
按导演给的「本段内容」和「风格档案」设计画面：要有一个明确的主体，
前→后有叙事推进，全程都在动。风格档案里的配色、线条、质感、光、构图、运动与禁止项
必须严格执行——那就是这一段的画风，不要另起一套。

## 交付契约
1. 导出 `export const Shot1: React.FC`、`export const BG = '#rrggbb';`
   和 `export const META = {1: {bg: '#rrggbb'}};`（META 的键必须是 1）。
2. **整个画面就是一个 `<svg viewBox="0 0 1920 1080">`**，所有图元放在它里面。
   **禁止** `<div>` / `<span>` / `AbsoluteFill` / `<Sequence>`：Remotion 的 `Sequence`
   和 `AbsoluteFill` 都会渲染成 `<div>`，嵌在 SVG 里整棵子树都不显示，画面会静默变全空。
   需要滤镜就用 `<filter>` + `<g filter="url(#id)">`（滤镜区域给足，别裁掉内容）。
3. 时间只从 `const e = useE();` 读（`e.t` 秒、`e.shotU` 本镜 0~1 进度、
   `e.shotT` 本镜已过秒数），不用外部时钟。
4. 这一段没有歌词层，不要画歌词/字幕原文，也不要使用 e.lyricBox。
   **底部 12% 是导演组的字幕安全区**，主体和文字都不要放进去。
5. 确定性：同帧同像素；禁止随机数、时间戳、定时器、网络与外链图片。

## 分镜
时长以「本段时长」为准。超过 12 秒时，要在同一块 `<svg>` 里切成 2~4 个镜头：
按 `e.t`（或 `e.shotT`）划时间段，用 `e.seg(a, b, e.t)` / `e.clamp01` 算出每个镜头的权重，
权重为 0 的镜头把 `opacity` 归零即可——**不要用 `<Sequence>`**（它渲染成 `<div>`，整段会全空）。
镜头之间可以是推进关系，也可以是情绪对比。
每个镜头都要有看得见的运动（主体位移/缩放/形变/粒子/光影漂移），
不能是一张静态图；0.5 秒内至少满足一条：主体移动 ≥ 画面宽 1.5%、缩放变化 ≥ 8%、
透明度变化 ≥ 15%，或一组元素整体位移 ≥ 20px。

## 环境
画布 1920×1080，30fps。`useE()` 来自 `'../../engine/context'`，字段：
`t, dt, W, H, i, n, kind, u, shotU, shotT, shotDur, beat, beatIdx, bar, phase, strong,
 pulse(k), hit(n), P, hexA(c,a), isDark(c), rnd(seed), hash(seed), lerp(a,b,t),
 clamp(v,a,b), clamp01(v), seg(a,b,v), easeOut(x), easeIn(x), easeIO(x), back(x), elastic(x), wave(x)`

只输出一个 TSX 文件（可带围栏），不要解释。
"""

CHARACTER_BLOCK = """
## 人物（这一段有人物时才用）
人物只能来自已定妆的角色组件，不要自己拼人体：`import {IMPORTS} from './char-hero';`

| 参数 | 取值 | 用途 |
|---|---|---|
| `view` | `front` / `side` / `back` | 角度 |
| `pose` | `stand` / `sit` | 站 / 坐 |
| `armL` / `armR` | 度数（0=下垂，正值向外）或 `[手x, 手y]` | 伸手、扶额、打字 |
| `headTurn` | 度数 | 转头 |
| `tilt` | 度数 | 身体倾斜 |
| `mood` | `calm` / `tired` / `surprised` / `dizzy` / `happy` / `worried` | 表情 |

```tsx
<g transform="translate(960 980) scale(1.2)"><Character view="front" pose="sit" armR={[52,-150]} /></g>
```

局部坐标：脚底 (0,0)，总高约 430。不要用 rect/path 另画手臂或头。
这一段不需要人就别画，人物高度不超过画面的 1/2。
"""


def _timeline(duration: float, fps: int) -> dict:
    return {"duration": round(float(duration), 3), "fps": fps, "beat_seconds": 0.5, "lines": []}


def _plan(duration: float, fps: int) -> dict:
    return {
        "plain": True,
        "lyricStyle": "band",
        "chrome": {"section": "hide", "progress": "hide"},
        "shots": [{"start": 0, "end": round(float(duration), 3)}],
        "canvas": {"width": 0, "height": 0, "fps": fps},
    }


def _context(brief: str, duration: float, style_guide: str, style_note: str,
             has_character: bool, prev: str = "", error: str = "", issues=None) -> str:
    lines = [
        f"本段时长：{duration:.1f}s",
        f"本段内容：\n{brief or '按风格档案自由发挥，但必须有明确主体和推进。'}",
        "",
        "风格档案（必须严格执行）：",
        style_guide or "导演没有写风格档案：按内容自己定一套统一的画风，并在画面里保持一致。",
    ]
    if style_note.strip():
        lines += ["", f"本段局部要求：{style_note.strip()}"]
    if not has_character:
        lines += ["", "这一段没有已定妆人物：不要画具象人体；需要人的话用剪影/背影/局部，或干脆不用人。"]
    if prev:
        lines += ["", "上一版代码（在此基础上修，不要推翻重来，除非结构有硬伤）：", "```tsx", prev, "```"]
    if error:
        lines += ["", "渲染/编译错误：", error]
    if issues:
        lines += ["", "上一版被检查出的问题："] + [f"- {x}" for x in issues]
    lines += ["", "只输出 TSX 文件内容。"]
    return "\n".join(lines)


def _llm(system: str, context: str, cfg: dict) -> str:
    from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
    try:
        from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
    except Exception:
        LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS = 128_000, (96_000, 64_000, 32_000)
    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            system_prompt=system, context=context,
            base_url=cfg.get("base_url", ""), api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""), protocol=cfg.get("protocol", "anthropic"),
            max_tokens=budget, timeout=240, attempts=2,
            provider=cfg.get("provider"), thinking=cfg.get("thinking"),
        ),
        max_tokens=LONG_OUTPUT_MAX_TOKENS, fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    return _strip_fences(raw)


def _strip_fences(code: str) -> str:
    m = re.search(r"```(?:tsx|ts|jsx)?\s*(.*?)```", code or "", re.S)
    return (m.group(1) if m else (code or "")).strip()


def _contract_errors(code: str) -> list[str]:
    errs = rs.static_check(code)
    for need in ("Shot1", "BG", "META"):
        if need == "META":
            if "export const META" not in code:
                errs.append("必须导出 META = {1: {bg: '#rrggbb'}}")
        elif not rs.has_named_export(code, need):
            errs.append(f"必须导出 {need}")
    if "<svg" not in code:
        errs.append('画面必须包在 <svg viewBox="0 0 1920 1080"> 里')
    if re.search(r"<div\b|<span\b|AbsoluteFill", code):
        errs.append("不要用 <div>/<span>/AbsoluteFill：嵌在 SVG 里不会渲染")
    # Sequence 同样渲染成 <div>（AbsoluteFill）：整棵子树在 SVG 里不显示，整段会变全空。
    if re.search(r"<Sequence\b", code):
        errs.append("不要用 <Sequence>：它渲染成 <div>，嵌在 SVG 里整段不显示；"
                    "分镜改成按 e.t / e.seg 算权重并调 opacity")
    return errs


def _register(work: Path, code: str, duration: float) -> None:
    """写镜头源码与注册清单；一次渲染只注册这一条。"""
    parts = work / "parts"
    fname = f"{NAMESPACE}-shot-1.tsx"
    _atomic_text(parts / fname, code)
    manifest = {
        "shot-1": {
            "key": "shot-1", "file": fname, "export": "Shot1", "index": 1,
            "start": 0, "end": round(float(duration), 3),
            "t": round(float(duration) / 2, 3),
        }
    }
    _atomic_text(parts / "registry.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def _prepare(work: Path, duration: float, fps: int, width: int, height: int) -> dict:
    plan = _plan(duration, fps)
    plan["canvas"] = {"width": width, "height": height, "fps": fps}
    _atomic_text(work / "timeline.json", json.dumps(_timeline(duration, fps), ensure_ascii=False, indent=2))
    _atomic_text(work / "plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
    return plan


def _still(work: Path, t: float, dst: Path) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(RENDER), str(work), "--still", f"{t:.3f}", "--strict"],
        cwd=str(RUNTIME), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=900,
    )
    produced = work / f"still-{t:.2f}.png"
    if r.returncode != 0 or not produced.exists():
        return False, "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-14:])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(produced.read_bytes())
    return True, ""


def _render_video(work: Path, dst: Path, fps: int, width: int, height: int) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, str(RENDER), str(work), "--fps", str(fps),
         "--width", str(width), "--height", str(height), "--no-audio"],
        cwd=str(RUNTIME), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800,
    )
    final = work / "mv.mp4"
    if r.returncode != 0 or not final.exists():
        return False, "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-16:])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(final.read_bytes())
    return True, ""


# ───────────────────── 静帧内容校验（渲染整段之前的闸门） ─────────────────────
# 之前只确认"静帧文件生成了"就放行：图元如果被包进 <Sequence>/<div>（SVG 里不渲染）
# 或者整段 opacity/坐标写坏，静帧是全空画面，整段黑屏也会被直接送进渲染。
# 现在采 3 个时刻，先做像素级空白检测（不依赖视觉模型），再交视觉模型复审。
_STILL_FRACTIONS = (0.2, 0.5, 0.8)
# 最频繁的 16 级色桶占比 ≥ 该值 → 整帧几乎同一种颜色（空白/纯色/黑屏）
_BLANK_FLAT = 0.99

_REVIEW_PROMPT = """这是一段风格动画的 3 帧拼图（按时间顺序：前/中/后，画面里没有文字叠层）。
请只做视觉审查，直接给结论，不要客套。输出 JSON：
{"has_content": <三帧是否都有可见的画面内容，而不是黑屏/纯色/近乎空白>,
 "issues": ["最多 3 条具体问题"], "summary": "一句话结论"}

判定口径：
- 主体、背景层次、图元都算内容；留白多但看得到东西，算有内容。
- 允许某一段是刻意的转场留白或淡入淡出；只有三帧里 ≥2 帧整幅空白/纯色，才算没有内容。
- 不要因为"画风朴素""元素少"就判空。"""


def _frame_stats(path: Path) -> dict | None:
    """量化到 16 级 RGB 色桶，返回最频繁色桶占比与平均亮度（无 PIL 时返回 None）。"""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        return None
    small = im.resize((160, max(1, int(160 * im.height / im.width))), Image.BOX)
    counts: dict[tuple, int] = {}
    lum = 0
    px = list(small.getdata())
    for r, g, b in px:
        key = (r >> 4, g >> 4, b >> 4)
        counts[key] = counts.get(key, 0) + 1
        lum += (r * 299 + g * 587 + b * 114) // 1000
    n = max(1, len(px))
    return {"flat": max(counts.values()) / n, "mean": lum / n, "colors": len(counts)}


def _contact_sheet(paths: list[Path], dst: Path) -> Path | None:
    """三帧竖排拼图：一次视觉调用就能看到整段，比逐帧调用省时。"""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        imgs = []
        width = 960
        for p in paths:
            im = Image.open(p).convert("RGB")
            imgs.append(im.resize((width, max(1, int(width * im.height / im.width)))))
        gap = 6
        sheet = Image.new("RGB", (width, sum(i.height for i in imgs) + gap * (len(imgs) - 1)),
                          (0, 0, 0))
        y = 0
        for im in imgs:
            sheet.paste(im, (0, y))
            y += im.height + gap
        dst.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(dst, format="JPEG", quality=84, optimize=True)
        return dst
    except Exception:
        return None


def _json_obj(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        doc = json.loads(m.group(0))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _verify_stills(work: Path, duration: float, attempt: int, cfg: dict,
                   emit=None) -> tuple[bool, str]:
    """真渲 3 帧并校验内容。返回 (ok, 错误说明)；错误说明直接回灌给模型重写。"""
    emit = emit or _log
    times = sorted({round(duration * f, 3) for f in _STILL_FRACTIONS})
    times = [t for t in times if 0 < t < duration] or [round(duration / 2, 3)]
    shots: list[tuple[float, Path]] = []
    for i, t in enumerate(times):
        dst = work / "art" / f"still-r{attempt}-{i}.png"
        ok, err = _still(work, t, dst)
        if not ok:
            return False, f"渲染崩了（t={t:.2f}s）：\n{err}"
        shots.append((t, dst))
    # 留一份代表帧（最接近段中点）方便人工查看
    try:
        mid = min(shots, key=lambda x: abs(x[0] - duration / 2))
        (work / "art" / f"still-r{attempt}.png").write_bytes(mid[1].read_bytes())
    except OSError:
        pass

    blank = [(t, st) for t, p in shots
             for st in [_frame_stats(p)] if st and st["flat"] >= _BLANK_FLAT]
    if len(blank) == len(shots):
        t, st = blank[0]
        return False, (
            f"整段几乎没有画面：{len(shots)} 个采样帧（t={', '.join(f'{x:.1f}s' for x, _ in blank)}）"
            f"里 {st['flat'] * 100:.1f}% 的像素是同一种颜色，平均亮度 {st['mean']:.0f}/255，"
            "看不到任何图元。常见原因：图元被包进 <Sequence>/<div>/<AbsoluteFill>"
            "（嵌在 <svg> 里不渲染）、整段 opacity 为 0、坐标/scale 把内容移出画面，"
            "或 fill 与背景同色。"
        )
    if blank:
        emit(f"  ⚠ {len(blank)}/{len(shots)} 个采样帧接近空白（t="
             f"{', '.join(f'{x:.1f}s' for x, _ in blank)}），请确认是刻意的留白")

    sheet = _contact_sheet([p for _, p in shots], work / "art" / f"still-r{attempt}-sheet.jpg")
    if sheet is None:
        return True, ""
    try:
        import base64
        from skills.image_reader import describe_image_b64
        b64 = base64.b64encode(sheet.read_bytes()).decode("ascii")
        doc = _json_obj(describe_image_b64(b64, "image/jpeg", _REVIEW_PROMPT, cfg, timeout=90))
    except Exception as e:
        emit(f"  · 视觉复审跳过（{type(e).__name__}）")
        return True, ""
    if not doc:
        return True, ""
    if doc.get("has_content") is False:
        issues = [str(x) for x in (doc.get("issues") or []) if str(x).strip()][:3]
        return False, "视觉复审判定整段没有画面内容：" + (
            "；".join(issues) or str(doc.get("summary") or "三帧都接近空白"))
    issues = [str(x) for x in (doc.get("issues") or []) if str(x).strip()][:3]
    if issues:
        emit("  · 视觉复审提示（不阻塞）：" + "；".join(issues[:2]))
    return True, ""


def run(brief: str, duration: float, output_path: str, work_dir: str,
        width: int = 1920, height: int = 1080, fps: int = 30,
        style_guide: str = "", style_note: str = "", character: str = "",
        skill_manager=None, llm_cfg: dict | None = None, progress=None) -> tuple[bool, str, str]:
    """渲一段风格动画。character 是已确认的角色参数路径（可空）。"""
    emit = progress or _log
    cfg = llm_cfg or {}
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        return False, "未配置主 LLM，styled 需要现场写画面", ""

    duration = max(1.0, float(duration or 8))
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    dst = Path(output_path)
    _prepare(work, duration, fps, width, height)

    has_character = False
    char_poses: list[str] = []
    if str(character or "").strip():
        char_file = Path(character)
        if char_file.exists():
            try:
                spec = json.loads(char_file.read_text(encoding="utf-8-sig"))
                from skills.remotion_runtime.character_module import install_character, sync_char_registry
                install_character(RUNTIME / "src", spec, "scenes/generated/char-hero.tsx")
                char_poses = sync_char_registry(RUNTIME / "src") or []
                has_character = bool(char_poses)
                if has_character:
                    emit(f"已载入定妆角色：{', '.join(char_poses)}")
            except Exception as e:
                emit(f"定妆角色载入失败（本段不用人物）：{e}")

    system = SYSTEM
    if has_character:
        system += CHARACTER_BLOCK.replace("{IMPORTS}", "{" + ", ".join(char_poses) + "}")

    previous, last_error, last_issues = "", "", []
    for attempt in range(1, MAX_TRIES + 1):
        emit(f"styled 第 {attempt}/{MAX_TRIES} 次生成画面...")
        try:
            code = _llm(system, _context(brief, duration, style_guide, style_note,
                                         has_character, previous, last_error, last_issues), cfg)
        except Exception as e:
            previous, last_error, last_issues = "", f"LLM 生成失败：{e}", []
            continue
        errs = _contract_errors(code)
        if errs:
            previous, last_error, last_issues = code, "交付契约不满足", errs
            emit("契约检查未通过，回灌重写")
            continue

        _register(work, code, duration)
        rs.sync_registry(work, namespace=NAMESPACE)
        rs._plan_for_gate(work, json.loads((work / "plan.json").read_text(encoding="utf-8")),
                          json.loads((work / "parts" / "registry.json").read_text(encoding="utf-8")))
        _atomic_text(work / "art" / f"styled-r{attempt}.tsx", code)

        emit("真渲静帧校验（内容 / 空白 / 视觉复审）...")
        ok, err = _verify_stills(work, duration, attempt, cfg, emit)
        if not ok:
            previous, last_error, last_issues = code, "", [err]
            emit("静帧校验未通过，回灌重写")
            continue

        emit(f"渲染整段（{duration:g}s）...")
        ok, err = _render_video(work, dst, fps, width, height)
        if not ok:
            previous, last_error, last_issues = code, "", [f"整段渲染失败：\n{err}"]
            continue
        return True, f"{dst}（{duration:.1f}s）", str(dst)

    detail = last_error or "；".join(str(x) for x in last_issues) or "未知错误"
    return False, f"styled 生成失败（{MAX_TRIES} 次）：{detail[:600]}", ""
