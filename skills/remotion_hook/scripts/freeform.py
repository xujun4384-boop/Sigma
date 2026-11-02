# -*- coding: utf-8 -*-
"""Remotion 自由发挥 + 视觉闸门。

流程：
  LLM 写 HookImpl.tsx -> 静态检查 -> Remotion 渲染 -> 抽 3 帧做视觉审查
  -> 不通过则把问题/错误回灌给 LLM 重写 -> 最多 3 次 -> 仍失败由上层回退模板。

只允许受限的 import 与 API；所有运动必须逐帧确定性。
"""
import base64
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from skills.image_reader import describe_image_b64
from skills.opendesign.scripts.renderer import (
    call_llm_text, _call_with_token_fallback,
    LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
)

from .render_hook import PROJECT, render_freeform

HOOK_IMPL = PROJECT / "src" / "freeform" / "HookImpl.tsx"
MAX_CODE = 30000
MAX_ATTEMPTS = 3

PLACEHOLDER = """import React from 'react';
import {AbsoluteFill} from 'remotion';
import {FreeformProps} from './types';

// 占位实现：自由发挥失败时保持工程可编译；每次生成会覆盖本文件。
export const GeneratedHook: React.FC<FreeformProps> = ({text}) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#04060c',
        color: '#f5f8ff',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 64,
        fontFamily: '"Microsoft YaHei", sans-serif',
      }}
    >
      {text}
    </AbsoluteFill>
  );
};
"""

_CODE_SYS = """你是 Remotion 动效导演。为视频第一段写一个开场钩子组件。
时长以调用方给出的 duration 为准（开场钩子通常 10 秒或更长，不要按 3~5 秒的短片来写）。
只输出一个完整的 HookImpl.tsx 文件内容，不要 markdown 围栏，不要解释。

必须满足：
1. 从 './types' 导入 FreeformProps；
2. 导出 `export const GeneratedHook: React.FC<FreeformProps> = ({text, kicker, sub, accent}) => { ... }`；
3. 所有画面放在 <AbsoluteFill> 里；尺寸/时长从 useVideoConfig() 读取；
4. 所有运动由 useCurrentFrame() + interpolate()/spring() 驱动，逐帧确定性；
5. 字体只用系统字体；不要联网、不要外部图片/字体/音频；
6. 屏幕文字必须来自 props 的 text/kicker/sub，不要写死与内容无关的文案；
7. 四周留 6% 安全区，底部 12% 不放重要内容（导演组会叠字幕）；
8. 在给定时长内完成「引入 → 强调 → 保持 → 收尾」，只传达一个信息点；
   主信息在前段完成，剩余时间用持续的镜头运动/光效/细节动效保持画面活性，不要提前静止或长时间定格；
9. 画面要有主次：主文案大、辅助信息小，避免满屏同字号。

允许的 import（只能这些）：
- react
- remotion（AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring, Easing, Sequence, Solid）
- @remotion/effects/light-leak
- @remotion/effects/noise
- @remotion/effects/scanlines
- @remotion/effects/chromatic-aberration
- @remotion/effects/light-trail
- @remotion/motion-blur（Trail）
- @remotion/shapes
- @remotion/paths
- ./types

禁止：fetch / XMLHttpRequest / require / 动态 import / eval / new Function / process / fs /
child_process / Date.now / Math.random / setTimeout / setInterval / requestAnimationFrame /
window / document / 外部 URL / CSS animation / transition。

只输出 TSX，不要 markdown，不要解释。"""

_REVIEW_PROMPT = """这是一支视频开场钩子的 3 帧拼图（按时间顺序：前/中/后）。
请只做视觉审查，直接给结论，不要客套。输出 JSON：
{"pass": true/false, "score": 0-10, "issues": ["..."], "summary": "..."}

注意：
- 第 1 帧可能处于动画引入阶段，允许文字尚未完全出现；不要把“正在入场”误判为空帧。
  如果第 1 帧空白但第 2/3 帧有完整内容，不算空帧。
- 底部 12% 指画面最下方一条窄带；画面中部的文字不算占用底部安全区。
- 可读性以第 2/3 帧为主。

检查：
1) 是否三帧都空/纯色/黑屏/只有噪点；
2) 主文字是否可读，是否被裁切、出框、重叠或糊；
3) 底部窄带是否被重要内容占用（导演组会叠字幕）；
4) 主体是否明确，是否一眼能看懂一个信息点；
5) 是否像"开场钩子"，而不是普通标题页或静态封面。
分数 6 分及以上且没有硬伤才算通过。"""

_FORBIDDEN = [
    (r"\bfetch\s*\(", "fetch()"),
    (r"\bXMLHttpRequest\b", "XMLHttpRequest"),
    (r"\brequire\s*\(", "require()"),
    (r"\bimport\s*\(", "动态 import()"),
    (r"\beval\s*\(", "eval()"),
    (r"\bnew\s+Function\b", "new Function"),
    (r"\bprocess\.", "process"),
    (r"\bchild_process\b", "child_process"),
    (r"\bfs\.", "fs"),
    (r"\bDate\.now\b", "Date.now"),
    (r"\bMath\.random\b", "Math.random"),
    (r"\bsetTimeout\b", "setTimeout"),
    (r"\bsetInterval\b", "setInterval"),
    (r"\brequestAnimationFrame\b", "requestAnimationFrame"),
    (r"\bwindow\.", "window"),
    (r"\bdocument\.", "document"),
    (r"<iframe\b", "iframe"),
    (r"<script\b", "script"),
    (r"https?://", "外部 URL"),
]
_ALLOWED = {
    "react", "remotion", "./types",
    "@remotion/motion-blur", "@remotion/shapes", "@remotion/paths",
}


def _allowed_import(mod: str) -> bool:
    m = (mod or "").strip()
    if m in _ALLOWED:
        return True
    return m.startswith("@remotion/effects/")


def _strip_fences(code: str) -> str:
    code = (code or "").strip()
    m = re.search(r"```(?:tsx|ts|jsx|js)?\s*(.*?)```", code, re.S)
    if m:
        code = m.group(1).strip()
    return code


def validate_code(code: str) -> list:
    errs = []
    if not code.strip():
        return ["代码为空"]
    if len(code) > MAX_CODE:
        errs.append(f"代码过长（{len(code)} 字符，上限 {MAX_CODE}）")
    if "GeneratedHook" not in code:
        errs.append("必须导出 GeneratedHook")
    if "useCurrentFrame" not in code:
        errs.append("必须使用 useCurrentFrame 驱动逐帧动画")
    for m in re.finditer(r"^\s*import\s+[^;\n]+?\s+from\s+['\"]([^'\"]+)['\"]", code, re.M):
        mod = m.group(1)
        if not _allowed_import(mod):
            errs.append(f"不允许的 import：{mod}")
    for pattern, label in _FORBIDDEN:
        if re.search(pattern, code):
            errs.append(f"禁止使用：{label}")
    return errs[:8]


def _code_context(spec: dict, previous: str, error: str, issues: list) -> str:
    lines = [
        f"钩子类型：{spec.get('hook_type') or 'title'}",
        f"主文案：{spec.get('text') or ''}",
        f"顶部标签：{spec.get('kicker') or ''}",
        f"副文案：{spec.get('sub') or ''}",
        f"强调色：{spec.get('accent') or '由你决定'}",
        f"时长：{spec.get('duration')}s｜画布：{spec.get('width')}x{spec.get('height')}@{spec.get('fps')}fps",
        f"整体风格：{spec.get('style') or '简洁、电影感'}",
    ]
    if previous:
        lines += ["", "上一版代码（在此基础上修，不要推翻重来，除非结构有硬伤）：", "```tsx", previous, "```"]
    if error:
        lines += ["", "渲染/编译错误：", error]
    if issues:
        lines += ["", "视觉审查问题："] + [f"- {x}" for x in issues]
    lines += ["", "只输出 TSX 文件内容。"]
    return "\n".join(lines)


def _generate_code(spec: dict, cfg: dict, previous: str = "", error: str = "",
                   issues: list | None = None) -> str:
    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            system_prompt=_CODE_SYS,
            context=_code_context(spec, previous, error, issues or []),
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
            protocol=cfg.get("protocol", "anthropic"),
            max_tokens=budget,
            timeout=180,
            attempts=2,
            provider=cfg.get("provider"),
            thinking=cfg.get("thinking"),
        ),
        max_tokens=LONG_OUTPUT_MAX_TOKENS,
        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    return _strip_fences(raw)


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _extract_frames(video: Path, duration: float, outdir: Path) -> list:
    times = [max(0.05, duration * 0.12), max(0.05, duration * 0.5), max(0.05, duration * 0.88)]
    frames = []
    for i, t in enumerate(times):
        fp = outdir / f"frame_{i}.png"
        r = subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
             "-frames:v", "1", str(fp)],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0 and fp.exists():
            frames.append(fp)
    return frames


def _contact_sheet(frames: list, outdir: Path) -> Optional[Path]:
    if not frames:
        return None
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return frames[0]
    imgs = []
    width = 960
    for fp in frames:
        im = Image.open(fp).convert("RGB")
        h = max(1, int(width * im.height / im.width))
        imgs.append(im.resize((width, h), Image.Resampling.LANCZOS))
    gap = 8
    total_h = sum(im.height for im in imgs) + gap * (len(imgs) - 1)
    sheet = Image.new("RGB", (width, total_h), (10, 12, 18))
    draw = ImageDraw.Draw(sheet)
    y = 0
    for i, im in enumerate(imgs):
        sheet.paste(im, (0, y))
        draw.rectangle([8, y + 8, 54, y + 34], fill=(0, 0, 0))
        draw.text((18, y + 12), f"{i + 1}/{len(imgs)}", fill=(255, 255, 255))
        y += im.height + gap
    p = outdir / "contact.jpg"
    sheet.save(p, format="JPEG", quality=82, optimize=True)
    return p


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _blank_check(frames: list) -> dict:
    """视觉模型不可用时的兜底：只检查是否接近纯色/黑屏。"""
    try:
        from PIL import Image, ImageStat
    except Exception:
        return {"pass": True, "score": 6, "issues": [], "summary": "无视觉模型，跳过抽查",
                "source": "skip"}
    stats = []
    for fp in frames:
        im = Image.open(fp).convert("L")
        st = ImageStat.Stat(im)
        stats.append((sum(st.mean) / len(st.mean), sum(st.stddev) / len(st.stddev)))
    flat = all(mean < 6 or std < 2 for mean, std in stats)
    if flat:
        return {"pass": False, "score": 2, "issues": ["画面接近纯色/黑屏，没有可见内容"],
                "summary": "空白检测未通过", "source": "blank-check"}
    return {"pass": True, "score": 6, "issues": [], "summary": "视觉模型不可用，仅通过空白检测",
            "source": "blank-check"}


def review_video(video: Path, duration: float, cfg: dict) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="hook_review_"))
    try:
        frames = _extract_frames(video, duration, tmp)
        if not frames:
            return {"pass": False, "score": 0, "issues": ["无法抽取审查帧"], "summary": "", "source": "no-frames"}
        sheet = _contact_sheet(frames, tmp)
        if not sheet:
            return _blank_check(frames)
        try:
            b64 = base64.b64encode(sheet.read_bytes()).decode("ascii")
            text = describe_image_b64(
                b64, "image/jpeg",
                _REVIEW_PROMPT + f"\n视频时长 {duration:.1f}s，分辨率见拼图。",
                cfg, timeout=90,
            )
            data = _parse_json(text)
            if data:
                score = float(data.get("score", 0) or 0)
                passed = bool(data.get("pass")) and score >= 6
                issues = [str(x) for x in (data.get("issues") or [])][:6]
                return {
                    "pass": passed,
                    "score": score,
                    "issues": issues,
                    "summary": str(data.get("summary") or ""),
                    "source": "vision",
                }
            return _blank_check(frames)
        except Exception as e:
            fallback = _blank_check(frames)
            fallback["summary"] = (fallback.get("summary") or "") + f"（视觉审查失败：{e}）"
            return fallback
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_freeform(spec: dict, cfg: dict, out: Path,
                 on_progress: Optional[Callable[[str], None]] = None,
                 attempts: int = MAX_ATTEMPTS) -> dict:
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        raise RuntimeError("未配置主 LLM，无法自由发挥")

    def emit(msg: str):
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    original = HOOK_IMPL.read_text(encoding="utf-8") if HOOK_IMPL.exists() else PLACEHOLDER
    previous, last_error, last_issues = "", "", []
    try:
        for attempt in range(1, max(1, attempts) + 1):
            emit(f"Remotion 自由发挥 第 {attempt}/{attempts} 次：生成代码...")
            try:
                code = _generate_code(spec, cfg, previous, last_error, last_issues)
            except Exception as e:
                last_error, last_issues = f"LLM 生成失败：{e}", []
                continue
            problems = validate_code(code)
            if problems:
                previous = code
                last_error, last_issues = "代码检查未通过：\n" + "\n".join(problems), problems
                emit("代码检查未通过，回灌重写")
                continue

            HOOK_IMPL.write_text(code, encoding="utf-8")
            emit(f"渲染中（第 {attempt} 次）...")
            try:
                info = render_freeform(spec, out)
            except Exception as e:
                previous = code
                last_error, last_issues = str(e), []
                emit("渲染失败，回灌重写")
                continue

            emit("视觉闸门审查中...")
            gate = review_video(out, float(spec.get("duration") or 4), cfg)
            if gate.get("pass"):
                code_path = out.with_suffix(".hook.tsx")
                try:
                    code_path.write_text(code, encoding="utf-8")
                except OSError:
                    code_path = None
                return {
                    "output_path": str(out),
                    "size_bytes": out.stat().st_size,
                    "attempt": attempt,
                    "review": gate,
                    "freeform": True,
                    "code_path": str(code_path) if code_path else "",
                }
            previous = code
            last_error, last_issues = "", gate.get("issues") or [gate.get("summary") or "视觉审查未通过"]
            emit("视觉闸门未通过，回灌重写")
    finally:
        try:
            HOOK_IMPL.write_text(original, encoding="utf-8")
        except Exception:
            pass

    detail = last_error or "；".join(str(x) for x in last_issues)
    raise RuntimeError(f"自由发挥 {attempts} 次未通过视觉闸门：{detail}")
