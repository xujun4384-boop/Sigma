# -*- coding: utf-8 -*-
"""Blender 部门渲染器（部门内部实现，自包含）。

职责：把"自然语言 brief"变成一段 bpy 场景脚本并渲染成 mp4：
  1. find_blender()  —— 定位 blender.exe（PATH 或便携版目录）
  2. render()        —— 用固定 harness.py 渲染场景脚本为 PNG 序列（Cycles CPU）
  3. encode()        —— ffmpeg 把 PNG 序列合成 mp4
  4. 渲染失败由调用方把报错回喂 LLM 重写（自愈，见 __init__.py）

设计原则：本模块不认识任何具体题材，只负责"脚本→影片"的通用管线；
          题材与画面完全由 LLM 依据 skill.md 自由生成。
"""
import os
import shutil
import subprocess
from pathlib import Path

HARNESS = Path(__file__).resolve().parent / "harness.py"


def _tail(text: str, n: int = 2500) -> str:
    t = (text or "").strip()
    return t[-n:] if len(t) > n else t


def find_blender() -> str:
    """定位 blender.exe：优先 PATH，其次便携版常见目录（含版本子目录）。"""
    p = shutil.which("blender") or shutil.which("blender.exe")
    if p:
        return p
    bases = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramData"),
        os.environ.get("APPDATA"),
    ]
    names = ("BlenderPortable", "Blender Foundation", "Programs/Blender Foundation")
    for b in bases:
        if not b:
            continue
        for name in names:
            d = Path(b) / name
            if not d.is_dir():
                continue
            found = sorted(d.rglob("blender.exe"))
            if found:
                return str(found[-1])
    return ""


def build_env(extra: dict = None) -> dict:
    """渲染子进程环境：把 Blender 用户目录挪到临时目录（沙箱里 AppData 写受限），并统一 UTF-8。"""
    env = os.environ.copy()
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or "."
    user = os.path.join(tmp, "sigma_blender_user")
    try:
        os.makedirs(user, exist_ok=True)
    except OSError:
        pass
    env["BLENDER_USER_RESOURCES"] = user
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    # 不生成 __pycache__：scene.py 会随产物留在项目目录，别在旁边留编译缓存
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        for k, v in extra.items():
            if v is not None:
                env[str(k)] = str(v)
    return env


def find_chromium() -> str:
    """定位 Chromium 内核浏览器（Chrome / Edge），用于把 HTML 截成贴图。"""
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        p = shutil.which(name)
        if p:
            return p
    bases = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
             os.environ.get("LOCALAPPDATA")]
    rels = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"Google\Chrome Beta\Application\chrome.exe",
    ]
    for b in bases:
        if not b:
            continue
        for rel in rels:
            p = Path(b) / rel
            if p.is_file():
                return str(p)
    return ""


def find_cjk_font() -> str:
    """定位系统里的中文字体，供 3D 场景做部件标注（Text 对象默认字体不含中文）。"""
    cands = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for c in cands:
        if Path(c).is_file():
            return c
    return ""


def check_blender() -> str:
    """探测 blender 是否可用；可用返回版本行，否则返回空串。"""
    exe = find_blender()
    if not exe:
        return ""
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=120, env=build_env())
        lines = (r.stdout or "").strip().splitlines()
        return lines[0] if r.returncode == 0 and lines else ""
    except Exception:
        return ""


def syntax_ok(code: str):
    """快速语法检查 + 契约检查：返回 None 表示通过，否则返回错误文本。"""
    import ast
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"Python 语法错误：{e.msg}（第 {e.lineno} 行）"
    if "def build" not in code:
        return "scene.py 必须定义 `def build():`（这是固定契约）"
    return None


def render(scene_path, outdir, W: int, H: int, fps: int, frames: int, samples: int,
           blender: str = None, timeout=None, extra_env: dict = None) -> int:
    """渲染场景脚本为 PNG 序列，返回帧数（失败抛 RuntimeError，含报错尾部）。

    extra_env：透传给 Blender 子进程（如 SCREEN_TEX 贴图路径、SIGMA_BLENDER_DEVICE 设备）。
    """
    exe = blender or find_blender()
    if not exe:
        raise RuntimeError("未找到 blender.exe（请安装 Blender 或在 PATH 中提供 blender）")

    outdir = Path(outdir)
    shutil.rmtree(outdir, ignore_errors=True)
    outdir.mkdir(parents=True, exist_ok=True)

    cmd = [
        exe, "-b", "--factory-startup", "-noaudio",
        "--python", str(HARNESS), "--",
        str(scene_path), str(outdir),
        str(int(W)), str(int(H)), str(int(fps)), str(int(frames)), str(int(samples)),
    ]
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                       env=build_env(extra_env), timeout=timeout)
    n = len(list(outdir.glob("f_*.png")))
    if r.returncode != 0 or n == 0:
        detail = _tail((r.stdout or "") + "\n" + (r.stderr or ""))
        raise RuntimeError(detail or "blender 渲染失败（无输出帧）")
    return n


def shoot_html(html_path, out_png, width: int, height: int, timeout=None) -> str:
    """用无头 Chromium 把 HTML 截成 PNG（设备屏幕内容贴图）。

    HTML 按 CSS 像素排版；需要更高分辨率就在 HTML 里用 zoom 放大，或直接按目标像素设计。
    """
    exe = find_chromium()
    if not exe:
        raise RuntimeError("未找到 Chromium 内核浏览器（Chrome/Edge），无法把 HTML 截成贴图")

    html_path = Path(html_path).resolve()
    if not html_path.is_file():
        raise RuntimeError(f"HTML 不存在: {html_path}")
    out_png = Path(out_png).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if out_png.exists():
        out_png.unlink()

    uri = "file:///" + html_path.as_posix()
    cmd = [
        exe, "--headless=new", "--hide-scrollbars", "--no-sandbox",
        f"--window-size={int(width)},{int(height)}",
        "--virtual-time-budget=5000",
        f"--screenshot={out_png}", uri,
    ]
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    if not out_png.exists() or out_png.stat().st_size == 0:
        raise RuntimeError(f"HTML 截图失败: {_tail((r.stdout or '') + (r.stderr or ''), 800)}")
    return str(out_png)


def encode(frames_dir, out_mp4, fps: int) -> str:
    """把 PNG 序列合成 mp4。"""
    ff = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"
    out_mp4 = str(out_mp4)
    cmd = [
        ff, "-y", "-loglevel", "error",
        "-framerate", str(int(fps)), "-start_number", "1",
        "-i", str(Path(frames_dir) / "f_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-movflags", "+faststart", out_mp4,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=None)
    if r.returncode != 0 or not Path(out_mp4).exists():
        raise RuntimeError(f"帧合成失败: {(r.stderr or '')[-500:]}")
    return out_mp4


def probe_duration(path) -> float:
    fp = shutil.which("ffprobe") or shutil.which("ffprobe.exe") or "ffprobe"
    try:
        r = subprocess.run([fp, "-v", "quiet", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float((r.stdout or "").strip())
    except Exception:
        return 0.0
