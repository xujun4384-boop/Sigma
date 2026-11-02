"""title_overlay 渲染：在底片上叠加「渐显蒙版 + 封面式大标题入场」，输出同规格 mp4。

排版意图（替代旧版「中部横幅」）：
- 前半段（默认 50%）**完全保留原画**，不做任何叠加；
- 后半段**渐变蒙版渐显**，随后标题以左对齐（可居中）的大字入场：
  标题逐行淡入上移 → 强调色分割线自左扫出 → 副标题错峰淡入。
- 字号比例克制（默认标题约画面高的 6%），只做「封面式标题排版」，不铺满、不横幅。

其他约束：
- 纯确定性：逐帧为 t 的纯函数，无随机、无跨帧状态、无外部请求。
- 文字用 PIL 绘制（不依赖 ImageMagick）；中文优先用系统雅黑/黑体字体。
"""
from pathlib import Path

_FONT_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
]
_FONT_REGULAR_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]

# 版式默认值（可通过参数/样式覆盖，不写死单一外观）
DEFAULTS = {
    "reveal_ratio": 0.5,        # 蒙版/标题开始出现的时间点（占总时长比例）
    "align": "left",            # 文字对齐: left / center
    "position": "upper",        # 文字纵向落点: upper / top / center / bottom
    "scrim_style": "uniform",   # 蒙版形态: uniform(全屏均匀) / bottom / top / center
    "scrim_alpha": 0.78,        # 蒙版最深处的透明度（uniform 时即整屏透明度）
    "title_size_ratio": 0.080,  # 标题字号 / 画面高
    "subtitle_size_ratio": 0.032,
    "side_margin_ratio": 0.07,  # 文字距画面左/右边缘
    "text_width_ratio": 0.66,   # 文字最大宽度 / 画面宽
    "title_max_lines": 2,
    "fade_out_seconds": 0.45,   # 片尾淡出（避免硬切）
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _ease_out(p: float) -> float:
    p = _clamp01(p)
    return 1 - (1 - p) ** 3


def _smoothstep(p: float) -> float:
    p = _clamp01(p)
    return p * p * (3 - 2 * p)


def _hex_rgb(s: str):
    s = (s or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    try:
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except Exception:
        return (255, 255, 255)


def _find_font(candidates) -> str | None:
    import os
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _load_font(font_file, size):
    from PIL import ImageFont
    if font_file:
        return ImageFont.truetype(font_file, size)
    return ImageFont.load_default()


def _wrap_chars(text: str, font, max_w: float, draw) -> list[str]:
    """按字符宽度折行（含手动换行），中英混排均可。"""
    lines: list[str] = []
    for para in (text or "").split("\n"):
        para = para.strip()
        if not para:
            continue
        cur = ""
        for ch in para:
            trial = cur + ch
            if cur and draw.textlength(trial, font=font) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur = trial
        if cur:
            lines.append(cur)
    return lines


def _fit_text(text: str, font_file, base_size: int, max_w: float,
              max_lines: int, draw):
    """逐级缩小字号，使其在 max_w 内折行不超过 max_lines 行。"""
    size = int(base_size)
    while size > 14:
        font = _load_font(font_file, size)
        lines = _wrap_chars(text, font, max_w, draw)
        if lines and len(lines) <= max_lines:
            return font, size, lines
        size -= 2
    font = _load_font(font_file, 14)
    return font, 14, _wrap_chars(text, font, max_w, draw) or [" "]


def _draw_gradient_line(draw, x: float, y: float, length: float, thickness: int,
                        c1, c2, alpha: int, segments: int = 96):
    """画一条水平渐变短线（强调色 → 变亮），用于标题下方分割线。"""
    if length <= 1:
        return
    seg_w = length / segments
    for i in range(segments):
        p = i / max(1, segments - 1)
        r = int(c1[0] + (c2[0] - c1[0]) * p)
        g = int(c1[1] + (c2[1] - c1[1]) * p)
        b = int(c1[2] + (c2[2] - c1[2]) * p)
        x0 = x + i * seg_w
        draw.rectangle([x0, y, x0 + seg_w + 1, y + thickness],
                       fill=(r, g, b, alpha))


def _scrim_profile(height: int, width: int, style: str, depth: float):
    """返回 (H, W) 的 Mask 强度分布。
    style=uniform 时整屏均匀；bottom/top/center 时该侧深、对侧透明（渐变形态）。"""
    import numpy as np
    ys = np.arange(height, dtype=np.float32)
    if style == "uniform":
        p = np.ones(height, dtype=np.float32)
    elif style == "top":
        # 顶部深 → 向下渐隐
        p = np.clip((depth - ys) / max(1e-6, depth), 0.0, 1.0)
    elif style == "center":
        # 中部深 → 向上下各渐隐
        p = np.clip(1.0 - np.abs(ys - height * 0.5) / max(1e-6, depth), 0.0, 1.0)
    else:
        # 底部深 → 向上渐隐
        p = np.clip((ys - (height - depth)) / max(1e-6, depth), 0.0, 1.0)
    p = p * p * (3 - 2 * p)  # smoothstep
    return np.repeat(p[:, None], width, axis=1)


def render_title_overlay(input_video: str, output_path: str, title: str,
                         subtitle: str = "", accent: str = "#ffffff",
                         position: str = "upper", fps: int = 0,
                         reveal_ratio: float | None = None,
                         align: str | None = None,
                         style_overrides: dict | None = None) -> dict:
    """
    在底片后半段叠加渐变蒙版与封面式标题动画。

    参数:
        input_video: 底片路径（原画不被改写）
        output_path: 输出 mp4 路径
        title/subtitle: 标题与副标题
        accent: 强调色（分割线 / 多行标题的末行）
        position: 文字纵向落点 upper / top / center / bottom（默认 upper，即左上偏中）
        fps: 0 表示沿用底片帧率
        reveal_ratio: 蒙版与标题出现的时间点（占总时长比例，默认 0.5）
        align: 文字对齐 left / center（默认 left）
        style_overrides: 其它版式覆盖（见 DEFAULTS 的键，含 scrim_style / scrim_alpha）

    返回:
        {output_path, duration, resolution, fps, size_mb, reveal_ratio}
    """
    from PIL import Image, ImageDraw
    from moviepy import VideoFileClip, VideoClip, CompositeVideoClip

    cfg = dict(DEFAULTS)
    cfg.update(style_overrides or {})
    if reveal_ratio is not None:
        cfg["reveal_ratio"] = reveal_ratio
    if align:
        cfg["align"] = align
    if position:
        cfg["position"] = position

    title = (title or "").strip() or " "
    subtitle = (subtitle or "").strip()
    align = str(cfg["align"]).lower()
    pos = str(cfg["position"]).lower()
    scrim_style = str(cfg.get("scrim_style") or "uniform").lower()
    if align not in ("left", "center"):
        align = "left"
    if pos not in ("upper", "top", "center", "bottom"):
        pos = "upper"
    if scrim_style not in ("uniform", "top", "center", "bottom"):
        scrim_style = "uniform"

    base = VideoFileClip(input_video)
    W, H = base.size
    FPS = int(fps or base.fps or 30)
    DUR = float(base.duration or 0)
    if DUR <= 0:
        base.close()
        raise RuntimeError("底片时长无效")

    import numpy as np

    accent_rgb = _hex_rgb(accent)
    accent_light = tuple(int(c + (255 - c) * 0.55) for c in accent_rgb)

    font_bold_file = _find_font(_FONT_BOLD_CANDIDATES)
    font_reg_file = _find_font(_FONT_REGULAR_CANDIDATES)

    probe = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    side_margin = W * float(cfg["side_margin_ratio"])
    max_text_w = W * float(cfg["text_width_ratio"])

    title_font, title_size, title_lines = _fit_text(
        title, font_bold_file, H * float(cfg["title_size_ratio"]),
        max_text_w, int(cfg["title_max_lines"]), probe,
    )
    sub_font, sub_size, sub_lines = (
        _fit_text(subtitle, font_reg_file, H * float(cfg["subtitle_size_ratio"]),
                  max_text_w, 1, probe)
        if subtitle else (None, 0, [])
    )

    # ── 版式几何（一次性计算，帧内只做绘制）──
    line_step = title_size * 1.20
    gap_title_div = title_size * 0.36
    div_h = max(3, int(H * 0.0042))
    gap_div_sub = sub_size * 0.85 if subtitle else 0.0
    sub_h = sub_size * 1.2 if subtitle else 0.0

    title_w_max = max(probe.textlength(l, font=title_font) for l in title_lines)
    sub_w = probe.textlength(sub_lines[0], font=sub_font) if sub_lines else 0.0
    div_w = min(max(title_w_max, sub_w, W * 0.22), max_text_w)

    block_h = len(title_lines) * line_step + gap_title_div + div_h + gap_div_sub + sub_h
    if pos == "top":
        block_top = H * 0.10
    elif pos == "upper":
        # 左上偏中：既落在画面上部，又不贴顶、纵向尽量靠中间
        block_top = H * 0.32
    elif pos == "center":
        block_top = (H - block_h) / 2
    else:
        block_top = H * 0.90 - block_h

    # ── 动画时间轴 ──
    t_reveal = DUR * _clamp01(float(cfg["reveal_ratio"]))
    remain = max(0.1, DUR - t_reveal)
    scrim_dur = min(0.9, max(0.35, remain * 0.30))
    title_delay = 0.12
    title_stagger = 0.13
    elem_dur = 0.50
    last_title_start = t_reveal + title_delay + title_stagger * max(0, len(title_lines) - 1)
    div_start = last_title_start + elem_dur * 0.55
    div_dur = 0.45
    sub_start = div_start + div_dur * 0.45
    sub_dur = 0.50
    t_out = min(float(cfg["fade_out_seconds"]), remain * 0.35)

    scrim_profile = _scrim_profile(H, W, scrim_style, depth=H * 0.55)
    scrim_rgb = (7, 9, 13)
    white = (255, 255, 255)
    sub_color = (230, 235, 242)

    def _alpha(p: float) -> int:
        return int(round(_clamp01(p) * 255))

    def make(t):
        rgba = np.empty((H, W, 4), dtype=np.uint8)
        rgba[..., 0] = scrim_rgb[0]
        rgba[..., 1] = scrim_rgb[1]
        rgba[..., 2] = scrim_rgb[2]
        rgba[..., 3] = 0

        # 前半段：不加任何叠加，原画直出
        if t < t_reveal:
            return rgba

        # 片尾淡出
        out_p = 1.0
        if t > DUR - t_out:
            out_p = 1.0 - _ease_out((t - (DUR - t_out)) / max(1e-6, t_out))

        # 渐变蒙版渐显
        scrim_p = _ease_out((t - t_reveal) / scrim_dur) * out_p
        if scrim_p > 0.002:
            alpha = scrim_profile * (float(cfg["scrim_alpha"]) * 255.0 * scrim_p)
            rgba[..., 3] = np.clip(alpha, 0, 255).astype(np.uint8)

        img = Image.fromarray(rgba, "RGBA")
        d = ImageDraw.Draw(img)

        def anchor_x(line_w: float, lw: float = 0.0) -> float:
            """左对齐时忽略宽度；居中时按宽度算左边缘。"""
            return side_margin if align == "left" else (W - lw) / 2

        # 标题逐行淡入 + 上移
        for i, line in enumerate(title_lines):
            p = _ease_out((t - (t_reveal + title_delay + i * title_stagger)) / elem_dur)
            if p <= 0.002:
                continue
            a = int(255 * p * out_p)
            lw = probe.textlength(line, font=title_font)
            rise = (1 - p) * H * 0.032
            cy = block_top + line_step * (i + 0.5) + rise
            # 多行标题的末行用强调色，形成层递感
            fill = accent_rgb if (i == len(title_lines) - 1 and len(title_lines) > 1) else white
            d.text((anchor_x(lw, lw), cy), line, font=title_font, anchor="lm",
                   fill=(fill[0], fill[1], fill[2], a))

        # 强调色分割线：自左扫出
        div_p = _ease_out((t - div_start) / div_dur)
        if div_p > 0.002:
            dy = block_top + len(title_lines) * line_step + gap_title_div
            x0 = anchor_x(0, div_w)
            _draw_gradient_line(d, x0, dy, div_w * div_p, div_h,
                                accent_rgb, accent_light, int(255 * div_p * out_p))

        # 副标题错峰淡入
        if sub_lines:
            p = _ease_out((t - sub_start) / sub_dur)
            if p > 0.002:
                a = int(235 * p * out_p)
                sw = probe.textlength(sub_lines[0], font=sub_font)
                rise = (1 - p) * H * 0.018
                sy = block_top + len(title_lines) * line_step + gap_title_div + div_h + gap_div_sub \
                    + sub_size * 0.6 + rise
                d.text((anchor_x(sw, sw), sy), sub_lines[0], font=sub_font, anchor="lm",
                       fill=(sub_color[0], sub_color[1], sub_color[2], a))

        return np.array(img)

    overlay = VideoClip(make, duration=DUR)
    final = CompositeVideoClip([base, overlay], size=(W, H))
    if base.audio is not None:
        final = final.with_audio(base.audio)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        final.write_videofile(output_path, fps=FPS, codec="libx264",
                              audio_codec="aac", logger=None)
    finally:
        for c in (overlay, final, base):
            try:
                c.close()
            except Exception:
                pass

    return {
        "output_path": output_path,
        "duration": round(DUR, 3),
        "resolution": f"{W}x{H}",
        "fps": FPS,
        "size_mb": round(Path(output_path).stat().st_size / 1048576, 2),
        "reveal_ratio": round(_clamp01(float(cfg["reveal_ratio"])), 3),
    }
