# -*- coding: utf-8 -*-
"""Sigma 片尾：按视频类型生成不同节奏的「Sigma 制作」动画，并追加到成片尾部。

设计约束：
  - 片尾是**确定性**动画：同一 t 永远画同一帧，不依赖随机状态，方便缓存与重跑。
  - 视觉配方是**显式注册表**（recipe），按引擎/风格 id 查表，不做文本关键词匹配。
  - 追加是**幂等**的：成片旁边留一份「未加片尾」的底片与 manifest，
    重跑时只要底片没变就直接复用，避免把片尾叠两次。
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TEXT = "Sigma 制作"
DEFAULT_DURATION = 3.0

RECIPES = ("clean", "editorial", "kinetic", "neon", "ink", "pixel", "data")

# styled 视觉风格（skills/style_lib.py 的 14 种）→ 片尾配方
_VISUAL_STYLE_TO_RECIPE = {
    "ink": "ink",
    "hanzi": "ink",
    "crayon": "ink",
    "whiteboard": "clean",
    "flat": "clean",
    "shadow": "clean",
    "isometric": "clean",
    "pixel": "pixel",
    "comic": "kinetic",
    "timeline": "data",
    "infographic": "data",
    "scale": "data",
    "exploded": "data",
    "map": "data",
}

# director 引擎（显式枚举）→ 片尾配方
_ENGINE_TO_RECIPE = {
    "opendesign": "clean",
    "remotion": "kinetic",
    "cinematic": "kinetic",
    "manim": "editorial",
    "amap": "data",
    "footage": "clean",
    "styled": "clean",
}

# lyric_mv 字效风格（skills/lyric_mv/type_styles.py 的 6 种）→ 片尾配方
_TYPE_STYLE_TO_RECIPE = {
    "brutalist": "kinetic",
    "editorial": "editorial",
    "neon": "neon",
    "handwritten": "ink",
    "pixel": "pixel",
    "kinetic": "kinetic",
}

_PALETTE = {
    "clean": {"bg": (7, 9, 13), "accent": (90, 169, 255), "text": (234, 242, 255)},
    "editorial": {"bg": (16, 16, 16), "accent": (201, 166, 107), "text": (242, 237, 227)},
    "kinetic": {"bg": (8, 8, 10), "accent": (255, 210, 63), "text": (255, 255, 255)},
    "neon": {"bg": (5, 6, 12), "accent": (0, 229, 255), "text": (234, 251, 255)},
    "ink": {"bg": (11, 16, 20), "accent": (92, 138, 160), "text": (237, 231, 218)},
    "pixel": {"bg": (6, 9, 10), "accent": (70, 240, 138), "text": (216, 255, 232)},
    "data": {"bg": (5, 9, 13), "accent": (47, 224, 200), "text": (223, 249, 243)},
}


def resolve_recipe(style_id, fallback="clean"):
    """按显式 id 解析配方；不认识就回落，不做模糊匹配。"""
    sid = str(style_id or "").strip()
    if sid in RECIPES:
        return sid
    for table in (_VISUAL_STYLE_TO_RECIPE, _TYPE_STYLE_TO_RECIPE, _ENGINE_TO_RECIPE):
        if sid in table:
            return table[sid]
    return fallback


def recipe_for_director(plan, panels):
    """director 的片尾配方：蓝图显式指定 > styled 视觉风格 > 引擎类型。"""
    raw = str((plan or {}).get("outro_style") or (plan or {}).get("outroStyle") or "").strip()
    if raw:
        return resolve_recipe(raw)
    styles = [str((p or {}).get("visualStyle") or "").strip() for p in (panels or [])]
    styles = [s for s in styles if s]
    if styles:
        return resolve_recipe(styles[0])
    engines = [str((p or {}).get("engine") or "").strip().lower() for p in (panels or [])]
    engines = [e for e in engines if e]
    if engines:
        counts = {}
        for e in engines:
            counts[e] = counts.get(e, 0) + 1
        top = max(counts, key=lambda k: counts[k])
        return resolve_recipe(top)
    return "clean"


def recipe_for_lyric(type_style):
    return resolve_recipe(type_style)


# ---------- 基础绘制 ----------

def _font(size: int, serif: bool = False):
    names = (["simsun.ttc", "msyh.ttc"] if serif else ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"])
    for name in names:
        p = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size, index=0)
            except Exception:
                continue
    return ImageFont.load_default()


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _span(t: float, a: float, b: float) -> float:
    if b <= a:
        return 1.0 if t >= b else 0.0
    return max(0.0, min(1.0, (t - a) / (b - a)))


_bg_cache = {}


def _background(w: int, h: int, recipe: str) -> Image.Image:
    key = (w, h, recipe)
    if key in _bg_cache:
        return _bg_cache[key]
    pal = _PALETTE[recipe]
    base = pal["bg"]
    img = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(img)
    # 纵向微渐变（上略亮、下略暗），一次性算好
    for y in range(h):
        k = y / max(1, h - 1)
        c = tuple(int(v * (1.0 - 0.22 * k)) for v in base)
        draw.line([(0, y), (w, y)], fill=c)
    # 柔光：低分辨率径向图放大，避免逐像素计算
    gw, gh = max(8, w // 48), max(8, h // 48)
    glow = Image.new("L", (gw, gh), 0)
    gd = ImageDraw.Draw(glow)
    cx, cy = gw * 0.5, gh * 0.46
    rad = int(max(gw, gh) * 0.55)
    for i in range(rad, 0, -1):
        a = int(58 * (i / rad) ** 2)
        gd.ellipse([cx - i, cy - i, cx + i, cy + i], fill=a)
    glow = glow.resize((w, h), Image.BICUBIC)
    tint = Image.new("RGB", (w, h), pal["accent"])
    img = Image.composite(tint, img, glow.point(lambda v: int(v * 0.35)))
    _bg_cache[key] = img
    return img


def _text_layer(text: str, font, fill, tracking: int = 0) -> Image.Image:
    widths = [int(font.getlength(ch)) for ch in text]
    total = sum(widths) + tracking * max(0, len(text) - 1)
    layer = Image.new("RGBA", (max(1, total + 8), int(font.size * 1.8) + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = 4
    y = 4
    for ch, cw in zip(text, widths):
        d.text((x, y), ch, font=font, fill=fill)
        x += cw + tracking
    # 裁到字形实际边界：这样"居中"是文字居中，而不是带上下留白的图层居中
    bbox = layer.getbbox()
    return layer.crop(bbox) if bbox else layer


def _pad(layer: Image.Image, pad: int) -> Image.Image:
    out = Image.new("RGBA", (layer.width + pad * 2, layer.height + pad * 2), (0, 0, 0, 0))
    out.paste(layer, (pad, pad), layer)
    return out


def _paste_center(canvas: Image.Image, layer: Image.Image, dy: int = 0):
    x = (canvas.width - layer.width) // 2
    y = (canvas.height - layer.height) // 2 + dy
    canvas.paste(layer, (x, y), layer)


def _fade_to_black(img: Image.Image, t: float) -> Image.Image:
    k = max(0.0, min(1.0, (t - 0.90) / 0.10))
    if k <= 0:
        return img
    black = Image.new("RGB", img.size, (0, 0, 0))
    return Image.blend(img, black, k)


# ---------- 各配方单帧 ----------

def _frame_clean(w, h, t, font, text):
    img = _background(w, h, "clean").copy()
    pal = _PALETTE["clean"]
    d = ImageDraw.Draw(img)
    ease = _ease_out_cubic(_span(t, 0.08, 0.48))
    # 细线由中心向两侧展开
    half = int(w * 0.10 * ease)
    y = int(h * 0.60)
    if half > 1:
        d.line([(w // 2 - half, y), (w // 2 + half, y)], fill=pal["accent"], width=max(1, h // 540))
    layer = _text_layer(text, font, pal["text"] + (int(255 * _ease_out_cubic(_span(t, 0.14, 0.52))),))
    _paste_center(img, layer, int(h * 0.035 * (1 - ease)))
    return _fade_to_black(img, t)


def _frame_editorial(w, h, t, font, text):
    img = _background(w, h, "editorial").copy()
    pal = _PALETTE["editorial"]
    d = ImageDraw.Draw(img)
    ease = _ease_out_cubic(_span(t, 0.06, 0.6))
    line_w = int(w * (0.12 + 0.18 * ease))
    lw = max(1, h // 720)
    d.line([(w // 2 - line_w, int(h * 0.38)), (w // 2 + line_w, int(h * 0.38))], fill=pal["accent"], width=lw)
    d.line([(w // 2 - line_w, int(h * 0.64)), (w // 2 + line_w, int(h * 0.64))], fill=pal["accent"], width=lw)
    layer = _text_layer(text, font, pal["text"] + (255,), tracking=max(2, int(font.size * 0.12)))
    # 从左到右遮罩揭示
    reveal = _ease_out_cubic(_span(t, 0.12, 0.58))
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, int(layer.width * reveal), layer.height], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), mask, mask))
    _paste_center(img, layer, 0)
    return _fade_to_black(img, t)


def _frame_kinetic(w, h, t, font, text):
    img = _background(w, h, "kinetic").copy()
    pal = _PALETTE["kinetic"]
    d = ImageDraw.Draw(img)
    # 背景速度线
    speed = _span(t, 0.0, 0.55)
    for i in range(7):
        y = int(h * (0.12 + 0.76 * i / 6))
        x0 = int(w * ((0.0 - 0.35 * speed) % 1.0)) - w // 4
        d.line([(x0, y), (x0 + int(w * 0.22), y)],
               fill=tuple(int(v) for v in (28 * (1 - speed),) * 3), width=1)
    # 逐字弹入
    widths = [int(font.getlength(ch)) for ch in text]
    gap = max(2, int(font.size * 0.05))
    total = sum(widths) + gap * (len(text) - 1)
    x = (w - total) // 2
    for i, (ch, cw) in enumerate(zip(text, widths)):
        a, b = 0.06 + i * 0.042, 0.28 + i * 0.042
        k = _ease_out_back(_span(t, a, b))
        ox = int((1 - k) * (w * 0.12 * (1 if i % 2 == 0 else -1)))
        oy = int((1 - k) * h * 0.06)
        glyph = Image.new("RGBA", (cw + 12, int(font.size * 1.6) + 12), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph)
        gd.text((6, 6), ch, font=font, fill=pal["text"] + (int(255 * _span(t, a, b + 0.08)),))
        bb = glyph.getbbox()
        if bb:
            glyph = glyph.crop(bb)
        gy = (h - glyph.height) // 2
        img.paste(glyph, (x + ox, gy + oy), glyph)
        x += cw + gap
    return _fade_to_black(img, t)


def _frame_neon(w, h, t, font, text):
    img = _background(w, h, "neon").copy()
    pal = _PALETTE["neon"]
    layer = _pad(_text_layer(text, font, pal["text"] + (255,)), max(4, font.size // 4))
    glow = layer.filter(ImageFilter.GaussianBlur(max(2, font.size // 12)))
    tint = Image.new("RGBA", layer.size, pal["accent"] + (190,))
    glow = Image.composite(tint, Image.new("RGBA", layer.size, (0, 0, 0, 0)), glow.getchannel("A"))
    # 前段 RGB 分离，后段收拢
    sep = int(font.size * 0.10 * (1 - _span(t, 0.12, 0.5)))
    alpha = int(255 * _span(t, 0.04, 0.3))
    for dx, color in ((-sep, (255, 60, 120)), (sep, (60, 220, 255))):
        ch = Image.new("RGBA", layer.size, color + (0,))
        ch.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha / 255)))
        cx = (w - layer.width) // 2
        cy = (h - layer.height) // 2
        img.paste(ch, (cx + dx, cy), ch)
    _paste_center(img, glow)
    _paste_center(img, layer)
    return _fade_to_black(img, t)


def _frame_ink(w, h, t, font, text):
    img = _background(w, h, "ink").copy()
    pal = _PALETTE["ink"]
    # 三团缓慢漂移的水彩
    wash = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wash)
    blobs = [((0.28, 0.38), (86, 116, 136), 0.20), ((0.74, 0.58), (110, 92, 120), 0.16),
             ((0.54, 0.76), (126, 110, 86), 0.14)]
    for (bx, by), color, rad in blobs:
        cx = int(w * (bx + 0.012 * _span(t, 0, 1)))
        cy = int(h * (by - 0.010 * _span(t, 0, 1)))
        r = int(min(w, h) * rad)
        wd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (42,))
    wash = wash.filter(ImageFilter.GaussianBlur(max(6, min(w, h) // 28)))
    img = Image.alpha_composite(img.convert("RGBA"), wash).convert("RGB")
    # 文字像墨迹一样由湿到干
    k = _ease_out_cubic(_span(t, 0.14, 0.58))
    layer = _pad(_text_layer(text, font, pal["text"] + (255,)), max(4, font.size // 5))
    if k < 0.98:
        layer = layer.filter(ImageFilter.GaussianBlur(max(0, int(font.size * 0.10 * (1 - k)))))
    a = layer.getchannel("A").point(lambda v: int(v * k))
    layer.putalpha(a)
    _paste_center(img, layer)
    return _fade_to_black(img, t)


def _frame_pixel(w, h, t, font, text):
    img = _background(w, h, "pixel").copy()
    pal = _PALETTE["pixel"]
    d = ImageDraw.Draw(img)
    # 扫描线
    for y in range(0, h, max(3, h // 240)):
        d.line([(0, y), (w, y)], fill=(20, 26, 24))
    layer = _text_layer(text, font, pal["text"] + (255,))
    # 前段低分辨率马赛克，后段恢复清晰
    blur_k = _span(t, 0.08, 0.5)
    if blur_k < 0.95:
        small = layer.resize((max(1, layer.width // 10), max(1, layer.height // 10)), Image.NEAREST)
        layer = small.resize(layer.size, Image.NEAREST)
    _paste_center(img, layer)
    # 扫描光标
    sx = int((w * 0.12) + (w * 0.76) * _span(t, 0.0, 0.8))
    d.line([(sx, int(h * 0.40)), (sx, int(h * 0.62))], fill=pal["accent"], width=max(1, w // 640))
    return _fade_to_black(img, t)


def _frame_data(w, h, t, font, text):
    img = _background(w, h, "data").copy()
    pal = _PALETTE["data"]
    d = ImageDraw.Draw(img)
    cols = 12
    for i in range(cols):
        x = int(w * (i + 1) / (cols + 1))
        for j in range(9):
            ph = (t * 1.6 + i * 0.13 + j * 0.21) % 1.0
            y = int(h * ph)
            a = int(34 * (1 - abs(ph - 0.5) * 2))
            d.line([(x, y), (x, y + max(2, h // 120))],
                   fill=tuple(int(v * a / 255) for v in pal["accent"]), width=1)
    # 扫描线：压暗到 45%，避免整条高亮横带像画面故障
    sy = int(h * ((-0.2 + 1.4 * t) % 1.0))
    dim = tuple(int(v * 0.45) for v in pal["accent"])
    d.rectangle([0, sy, w, sy + max(1, h // 360)], fill=dim)
    layer = _text_layer(text, font, pal["text"] + (255,))
    n = int(len(text) * _ease_out_cubic(_span(t, 0.14, 0.58)))
    mask = Image.new("L", layer.size, 0)
    ImageDraw.Draw(mask).rectangle([0, 0, int(layer.width * n / max(1, len(text))), layer.height], fill=255)
    layer.putalpha(Image.composite(layer.getchannel("A"), mask, mask))
    _paste_center(img, layer)
    d.line([(w // 2 - int(w * 0.12 * _span(t, 0.3, 0.9)), int(h * 0.61)),
            (w // 2 + int(w * 0.12 * _span(t, 0.3, 0.9)), int(h * 0.61))],
           fill=pal["accent"], width=max(1, h // 720))
    return _fade_to_black(img, t)


_FRAME_FN = {
    "clean": _frame_clean,
    "editorial": _frame_editorial,
    "kinetic": _frame_kinetic,
    "neon": _frame_neon,
    "ink": _frame_ink,
    "pixel": _frame_pixel,
    "data": _frame_data,
}


def render_frame(w: int, h: int, t: float, recipe: str, text: str = TEXT) -> Image.Image:
    rec = resolve_recipe(recipe)
    font_size = max(28, int(min(w, h) * 0.125))
    font = _font(font_size, serif=(rec == "editorial"))
    img = _FRAME_FN[rec](w, h, t, font, text or TEXT)
    if t < 0.12:
        # 从黑场淡入，避免硬切到亮色卡片造成一次亮度跳变
        img = Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, t / 0.12)
    return img


# ---------- 视频文件 ----------

def _probe(path: str) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 失败：{out.stderr[-300:]}")
    data = json.loads(out.stdout or "{}")
    info = {"width": 0, "height": 0, "fps": 30.0, "has_audio": False,
            "sample_rate": 48000, "channels": 2, "duration": 0.0, "time_base": "", "tbn": 0}
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video" and not info["width"]:
            info["width"] = int(s.get("width") or 0)
            info["height"] = int(s.get("height") or 0)
            rate = str(s.get("r_frame_rate") or "30/1")
            try:
                num, den = rate.split("/")
                info["fps"] = float(num) / float(den or 1)
            except Exception:
                info["fps"] = 30.0
            info["time_base"] = str(s.get("time_base") or "")
            try:
                info["tbn"] = int(info["time_base"].split("/")[1])
            except Exception:
                info["tbn"] = 0
        elif s.get("codec_type") == "audio" and not info["has_audio"]:
            info["has_audio"] = True
            info["sample_rate"] = int(s.get("sample_rate") or 48000)
            info["channels"] = int(s.get("channels") or 2)
    info["duration"] = float((data.get("format") or {}).get("duration") or 0)
    info["tags"] = dict(((data.get("format") or {}).get("tags") or {}))
    return info


def _clip_path(work_dir: Path, w: int, h: int, fps: float, recipe: str,
               duration: float, audio: dict, tbn: int = 0) -> Path:
    a = f"a{audio.get('sample_rate', 48000)}x{audio.get('channels', 2)}" if audio else "noaudio"
    name = f"sigma_outro_{recipe}_{w}x{h}_{int(round(fps))}_{duration:.2f}_{a}_tb{tbn}.mp4"
    return work_dir / name


def build_clip(dst: Path, width: int, height: int, fps: float, recipe: str,
               duration: float, text: str = TEXT, audio: dict = None, tbn: int = 0) -> Path:
    """渲染独立片尾片段（确定性逐帧，直接送 ffmpeg 编码）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    total = max(1, int(round(duration * fps)))
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ffmpeg, "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
           "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-f", "lavfi", "-i",
                f"anullsrc=channel_layout={'stereo' if audio.get('channels', 2) >= 2 else 'mono'}"
                f":sample_rate={audio.get('sample_rate', 48000)}",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(fps)]
    if tbn:
        # 与成片保持同一时间基，copy 拼接时不会把时长按比例放大
        cmd += ["-video_track_timescale", str(tbn)]
    cmd += ["-movflags", "+faststart", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        for i in range(total):
            t = i / max(1, total - 1)
            frame = render_frame(width, height, t, recipe, text)
            proc.stdin.write(frame.tobytes())
            proc.stdin.flush()
    except BrokenPipeError:
        err = (proc.stderr.read() or b"").decode("utf-8", "ignore")
        raise RuntimeError(f"片尾编码中断：{err[-400:]}")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
    err = (proc.stderr.read() or b"").decode("utf-8", "ignore")
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"片尾编码失败：{err[-400:]}")
    return dst


def _concat_copy(base: Path, outro: Path, dst: Path, sig: str = "") -> bool:
    lst = dst.with_suffix(".concat.txt")
    lst.write_text(
        "file '" + str(base.resolve()).replace("'", "'\\''") + "'\n"
        + "file '" + str(outro.resolve()).replace("'", "'\\''") + "'\n",
        encoding="utf-8")
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c", "copy"]
    if sig:
        cmd += ["-metadata", f"comment=sigma_outro:{sig}"]
    cmd += ["-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lst.unlink(missing_ok=True)
    return r.returncode == 0 and dst.exists()


def _concat_reencode(base: Path, outro: Path, dst: Path, has_audio: bool, sig: str = "") -> bool:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    cmd = [ffmpeg, "-y", "-v", "error", "-i", str(base), "-i", str(outro)]
    if has_audio:
        fc = "[0:v][1:v]concat=n=2:v=1:a=0[v];[0:a][1:a]concat=n=2:v=0:a=1[a]"
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    if sig:
        cmd += ["-metadata", f"comment=sigma_outro:{sig}"]
    cmd += ["-movflags", "+faststart", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and dst.exists()


def _sha(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:16]


def append_outro(video_path: str, recipe: str = "clean", duration: float = DEFAULT_DURATION,
                 text: str = TEXT, work_dir: str = None) -> str:
    """把片尾追加到成片尾部。

    幂等策略：
      - 成片旁的 <stem>.base.mp4 是「未加片尾」的底片；
      - <stem>.sigma_outro.json 记录底片与成片的指纹；
      - 底片有效时永远从底片重建，避免重复叠加；
      - 成片被重新合成（指纹变化）时刷新底片。
    """
    src = Path(video_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"成片不存在：{src}")
    info = _probe(str(src))
    if not info["width"] or not info["height"]:
        raise RuntimeError("无法读取成片分辨率")
    work = Path(work_dir).resolve() if work_dir else src.parent / ".sigma_outro"
    work.mkdir(parents=True, exist_ok=True)
    base = work / f"{src.stem}.base{src.suffix}"
    manifest = work / f"{src.stem}.sigma_outro.json"

    sig = _sha(recipe, duration, text, info["width"], info["height"], int(round(info["fps"])))
    old = {}
    if manifest.exists():
        try:
            old = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            old = {}

    cur_fp = _sha(src.stat().st_size, int(src.stat().st_mtime))
    # 容器里带了片尾标记：即使 .sigma_outro 目录被清掉也能识别，避免叠第二层
    tag = str(info.get("tags", {}).get("comment") or "")
    if tag == f"sigma_outro:{sig}":
        return str(src)
    if tag.startswith("sigma_outro:") and not base.exists():
        return str(src)
    # 已经就是「加了片尾」的版本 → 直接复用
    if old.get("out_fp") == cur_fp and old.get("sig") == sig:
        return str(src)

    # 底片只在「当前成片就是我们上一次加的片尾版本」时才可复用；
    # 如果成片被重新合成（指纹变了），必须刷新底片，否则会拿旧内容拼新片尾。
    base_ok = bool(old.get("out_fp") == cur_fp and base.exists()
                   and old.get("base_fp") == _sha(base.stat().st_size, int(base.stat().st_mtime)))
    if not base_ok:
        if old.get("out_fp") == cur_fp and base.exists():
            # 成片未变但底片丢了/被改过：保留现状，宁可不重拼也不叠两层
            return str(src)
        tmp = base.with_suffix(".copy.tmp" + base.suffix)
        shutil.copy2(src, tmp)
        os.replace(tmp, base)

    audio = None
    if info["has_audio"]:
        audio = {"sample_rate": info["sample_rate"], "channels": info["channels"]}

    outro = _clip_path(work, info["width"], info["height"], info["fps"], recipe, duration, audio,
                       info.get("tbn") or 0)
    if not outro.exists():
        build_clip(outro, info["width"], info["height"], info["fps"], recipe, duration, text,
                   audio, info.get("tbn") or 0)

    dst = work / f"{src.stem}.with_outro{src.suffix}"
    base_dur = _probe(str(base)).get("duration") or 0.0
    expected = base_dur + duration
    ok = _concat_copy(base, outro, dst, sig)
    if ok:
        # copy 拼接最怕时间基不一致：时长/帧率对不上就改用重编码，宁可慢也不出错片
        got = _probe(str(dst))
        if abs((got.get("duration") or 0) - expected) > 0.5 or abs((got.get("fps") or 0) - info["fps"]) > 0.05:
            dst.unlink(missing_ok=True)
            ok = False
    if not ok and base_dur <= 900:
        # 兜底重编码只用于短成片：长片重编码代价过大，宁可不加片尾也不拖住整条流水线
        ok = _concat_reencode(base, outro, dst, info["has_audio"], sig)
    if not ok:
        dst.unlink(missing_ok=True)
        raise RuntimeError("片尾拼接失败（copy 与重编码均失败）")

    final_mtime = int(dst.stat().st_mtime)
    os.replace(dst, src)
    manifest.write_text(json.dumps({
        "sig": sig,
        "recipe": recipe,
        "duration": duration,
        "base_fp": _sha(base.stat().st_size, int(base.stat().st_mtime)),
        "out_fp": _sha(src.stat().st_size, final_mtime),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(src)
