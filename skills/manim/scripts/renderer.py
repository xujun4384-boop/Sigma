# -*- coding: utf-8 -*-
"""Manim 部门渲染器（部门内部实现，自包含）。

职责：把"自然语言 brief"变成一段 Manim 场景代码并渲染成 mp4。
  1. call_llm_scene() —— 画面生成 LLM 依 skill.md 写 Python 场景代码（入口类名固定 Main）
  2. render_code()    —— python -m manim render 渲染（PATH 前置 TinyTeX，保证 MathTex 可用）
  3. 渲染失败 → 由调用方把报错回喂 LLM 重写（自愈，见 __init__.py）
  4. fit_to_duration()—— 成片裁剪/补帧到目标时长，保证与导演时间轴严格一致

设计原则：本模块不认识"数学/几何"等任何具体题材，只负责"代码→影片"的通用管线；
          题材与画面完全由 LLM 依据 skill.md 自由生成。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCENE_CLASS = "Main"   # 入口类名（固定契约，与内容无关）


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe") or "ffprobe"


def probe_duration(path) -> float:
    try:
        r = subprocess.run(
            [_ffprobe(), "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0


def _tex_bin_candidates() -> list:
    """TinyTeX 可能的 bin 目录（本机系统 PATH 里的 MiKTeX 可能损坏，故显式前置 TinyTeX）。"""
    cands = []
    for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramData")):
        if base:
            cands.append(Path(base) / "TinyTeX" / "bin" / "windows")
            cands.append(Path(base) / "TinyTeX" / "bin")
    return cands


def build_env() -> dict:
    """渲染子进程环境：把 TinyTeX 的 bin 前置到 PATH（覆盖可能损坏的 MiKTeX），并统一 UTF-8。"""
    env = os.environ.copy()
    for d in _tex_bin_candidates():
        try:
            if (d / "latex.exe").exists() or (d / "latex").exists():
                env["PATH"] = str(d) + os.pathsep + env.get("PATH", "")
                break
        except OSError:
            continue
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _tail(text: str, n: int = 2500) -> str:
    t = (text or "").strip()
    return t[-n:] if len(t) > n else t


def _newest_mp4(media_dir: Path):
    files = list(Path(media_dir).rglob("*.mp4"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def syntax_ok(code: str):
    """快速语法检查：返回 None 表示通过，否则返回错误文本（避免把语法错也丢给 manim 慢慢跑）。"""
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"Python 语法错误：{e.msg}（第 {e.lineno} 行）"
    return None


def _frame_size(W: int, H: int) -> tuple:
    """把 Manim 的可视高度固定为 8 单位，宽度按目标画布比例推导。

    这样 1920×1080 仍是 14.22×8（Manim 默认），而 1080×1920 会变成 4.5×8：
    文字/图形在竖屏里保持与横屏一致的**相对高度**，不会因为画布变高而显得很小。
    """
    frame_h = 8.0
    frame_w = frame_h * max(1e-6, float(W) / float(H))
    return frame_w, frame_h


def render_code(code_path: Path, media_dir: Path, W: int, H: int, fps: int,
                output_name: str = "manim_scene", timeout=None):
    """调用 manim 渲染场景代码，返回产出的 mp4 路径（失败抛 RuntimeError，含报错尾部）。"""
    media_dir = Path(media_dir)
    shutil.rmtree(media_dir, ignore_errors=True)   # 清掉上次产物，避免误取旧文件
    media_dir.mkdir(parents=True, exist_ok=True)

    # Manim 的 -r 只设像素尺寸，不会自动把 frame_width/frame_height 改成目标比例；
    # 不显式设置时，竖屏会沿用 16:9 的横向视野、纵向被拉长，文字看起来非常小。
    frame_w, frame_h = _frame_size(W, H)
    cfg_path = media_dir / "sigma_manim.cfg"
    cfg_path.write_text(
        "[CLI]\n"
        f"frame_width = {frame_w:.6f}\n"
        f"frame_height = {frame_h:.6f}\n",
        encoding="utf-8",
    )

    cmd = [
        sys.executable, "-m", "manim", "render",
        "--config_file", str(cfg_path),
        "--disable_caching",
        "--media_dir", str(media_dir),
        "-r", f"{int(W)},{int(H)}",
        "--fps", str(int(fps)),
        "--format", "mp4",
        "-o", output_name,
        "-v", "warning",
        str(code_path),
        SCENE_CLASS,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                           env=build_env(), timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"manim 渲染超时: {e}")

    mp4 = _newest_mp4(media_dir)
    if r.returncode != 0 or mp4 is None:
        detail = _tail((r.stdout or "") + "\n" + (r.stderr or ""))
        raise RuntimeError(detail or "manim 渲染失败（无输出文件）")
    return mp4


def fit_to_duration(src, dst, target: float, W: int, H: int, fps: int) -> str:
    """把渲染结果对齐到目标时长：短了补末帧、长了裁剪；并统一画布/fps/像素格式。"""
    src, dst = str(src), str(dst)
    d = probe_duration(src)
    if abs(d - target) <= 0.08:
        shutil.copy2(src, dst)
        return dst
    if d > target:
        extra = 0.0
    else:
        extra = max(0.0, target - d)
    vf = []
    if extra > 0:
        vf.append(f"tpad=stop_mode=clone:stop_duration={extra:.3f}")
    vf.append(
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={fps},format=yuv420p"
    )
    cmd = [_ffmpeg(), "-y", "-i", src, "-vf", ",".join(vf), "-an",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-t", f"{max(0.05, target):.3f}", dst]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
    if r.returncode != 0 or not Path(dst).exists():
        raise RuntimeError(f"时长对齐失败: {(r.stderr or '')[-500:]}")
    return dst


def check_manim() -> str:
    """探测 manim 是否可用；可用返回版本号，否则返回空串。"""
    try:
        r = subprocess.run([sys.executable, "-m", "manim", "--version"],
                           capture_output=True, text=True, timeout=60, env=build_env())
        ver = (r.stdout or "").strip().splitlines()
        return ver[0] if r.returncode == 0 and ver else ""
    except Exception:
        return ""
