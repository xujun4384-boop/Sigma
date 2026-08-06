"""
video_short 渲染引擎 - 纯视觉竖版新闻短视频渲染

使用 moviepy + Pillow 生成带标题、圆角图片卡片、打字机动画字幕的无声竖版 MP4。
支持多套场景切换动效（fade / slide / zoom 等）。

布局（默认 1080×1920）:
  - 顶部标题区: title_height px（大标题 + 副标题，渐变背景，文字靠下）
  - 中部图片区: image_height px（圆角卡片，图片居中裁切）
  - 底部字幕区: 剩余高度（打字机逐字动画）
"""
import os
import io
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


# ─── 字体查找 ───

def _find_font() -> str:
    """查找可用的中文字体，按优先级尝试。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simkai.ttf",
        "C:/Windows/Fonts/STKAITI.TTF",
        "C:/Windows/Fonts/Deng.ttf",
        "C:/Windows/Fonts/Dengb.ttf",
    ]
    candidates += [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return ""


# ─── 文字换行 ───

def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """将文本按 max_width 换行，返回行列表。"""
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            lines.append("")
            continue
        current_line = ""
        for char in paragraph:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
    return lines


def _wrap_text_by_chars(text: str, max_chars_per_line: int) -> list[str]:
    """按字符数折行，用于底部字幕区域。"""
    lines = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for i in range(0, len(paragraph), max_chars_per_line):
            lines.append(paragraph[i:i + max_chars_per_line])
    return lines


# ─── 辅助: 字典深合并 ───

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并 override 到 base，返回新字典。"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


# ─── 默认样式 ───

DEFAULT_STYLE = {
    "bg_gradient_top": "#1a1a2e",
    "bg_gradient_bottom": "#16213e",
    "title_color": "#ffffff",
    "subtitle_color": "#e0e0e0",
    "subtitle_text_color": "#ffffff",
    "subtitle_bg_color": (0, 0, 0, 180),
    "accent_color": "#e94560",
    "card_radius": 20,
    "card_bg": "#0f3460",
    "title_font_size": 64,
    "subtitle_font_size": 36,
    "subtitle_font_size_bottom": 32,
    "title_max_width_ratio": 0.85,
}


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# ═══════════════════════════════════════════════════
# 帧渲染（含打字机动画）
# ═══════════════════════════════════════════════════

def _render_frame(
    width: int, height: int,
    title: str, subtitle: str,
    image_path: str,
    typewriter_progress: float,
    all_body_lines: list[str],
    title_height: int,
    image_height: int,
    style: dict,
    font_title, font_subtitle, font_body,
    image_alpha: float = 1.0,
    image_offset_x: float = 0.0,
    image_offset_y: float = 0.0,
    image_scale: float = 1.0,
) -> bytes:
    """
    渲染单帧为 JPEG 字节。

    typewriter_progress: 0.0 ~ 1.0，控制打字机动画进度
    image_alpha/image_offset/image_scale: 图片切换动效参数
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 1. 背景渐变 ──
    tc = _hex_to_rgb(style["bg_gradient_top"])
    bc = _hex_to_rgb(style["bg_gradient_bottom"])
    for y in range(height):
        ratio = y / height
        r = int(tc[0] + (bc[0] - tc[0]) * ratio)
        g = int(tc[1] + (bc[1] - tc[1]) * ratio)
        b = int(tc[2] + (bc[2] - tc[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # ── 2. 顶部标题区（文字放在区域底部，上方留空避开状态栏/灵动岛）──
    title_area_bottom = title_height
    title_max_width = int(width * style["title_max_width_ratio"])

    title_lines = _wrap_text(title, font_title, title_max_width, draw)
    total_title_h = 0
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        total_title_h += (bbox[3] - bbox[1]) + 10
    if subtitle:
        total_title_h += 20
        sub_lines = _wrap_text(subtitle, font_subtitle, title_max_width, draw)
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=font_subtitle)
            total_title_h += (bbox[3] - bbox[1]) + 8

    title_y = max(60, title_area_bottom - total_title_h - 30)

    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        draw.text(
            ((width - line_w) // 2, title_y),
            line, font=font_title, fill=style["title_color"],
        )
        title_y += line_h + 10

    if subtitle:
        title_y += 20
        sub_lines = _wrap_text(subtitle, font_subtitle, title_max_width, draw)
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=font_subtitle)
            line_w = bbox[2] - bbox[0]
            line_h = bbox[3] - bbox[1]
            draw.text(
                ((width - line_w) // 2, title_y),
                line, font=font_subtitle, fill=style["subtitle_color"],
            )
            title_y += line_h + 8

    accent_y = title_area_bottom - 4
    draw.line(
        [(width // 4, accent_y), (width * 3 // 4, accent_y)],
        fill=style["accent_color"], width=3,
    )

    # ── 3. 中部图片卡片 ──
    card_radius = style["card_radius"]
    card_margin_h = 40
    card_margin_v = 20
    card_x = card_margin_h
    card_y = title_height + card_margin_v
    card_w = width - card_margin_h * 2
    card_h = image_height - card_margin_v * 2
    inner_margin = 8
    inner_w = card_w - inner_margin * 2
    inner_h = card_h - inner_margin * 2

    if image_alpha > 0.01:
        img_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        card_bg_color = _hex_to_rgb(style["card_bg"])
        card_bg = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card_bg)
        card_draw.rounded_rectangle(
            [(0, 0), (card_w, card_h)],
            radius=card_radius, fill=(*card_bg_color, 255),
        )
        img_layer.paste(card_bg, (card_x, card_y), card_bg)

        if image_path and os.path.exists(image_path):
            try:
                photo = Image.open(image_path).convert("RGBA")

                # ── 第一步：裁切适配到卡片内部尺寸 ──
                photo_ratio = photo.width / photo.height
                target_ratio = inner_w / inner_h
                if photo_ratio > target_ratio:
                    new_h = inner_h
                    new_w = int(new_h * photo_ratio)
                else:
                    new_w = inner_w
                    new_h = int(new_w / photo_ratio)
                photo = photo.resize((new_w, new_h), Image.Resampling.LANCZOS)
                # 居中裁切到 exact inner_w x inner_h
                crop_left = (new_w - inner_w) // 2
                crop_top = (new_h - inner_h) // 2
                photo = photo.crop((crop_left, crop_top, crop_left + inner_w, crop_top + inner_h))
                # 此时 photo 大小严格为 (inner_w, inner_h)

                # ── 第二步：应用动效变换（缩放、位移、透明度）──
                if image_scale != 1.0 or image_offset_x != 0 or image_offset_y != 0:
                    sw = max(1, int(inner_w * image_scale))
                    sh = max(1, int(inner_h * image_scale))
                    photo = photo.resize((sw, sh), Image.Resampling.LANCZOS)
                    # 在 inner_w x inner_h 画布上居中 + 偏移后放置
                    canvas = Image.new("RGBA", (inner_w, inner_h), (0, 0, 0, 0))
                    px = (inner_w - sw) // 2 + int(image_offset_x)
                    py = (inner_h - sh) // 2 + int(image_offset_y)
                    canvas.paste(photo, (px, py))
                    photo = canvas

                # 应用透明度
                if image_alpha < 1.0:
                    r, g, b, a = photo.split()
                    a = a.point(lambda p: int(p * image_alpha))
                    photo = Image.merge("RGBA", (r, g, b, a))

                # ── 第三步：圆角 mask 后贴入卡片区域 ──
                mask = Image.new("L", (inner_w, inner_h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle(
                    [(0, 0), (inner_w, inner_h)],
                    radius=max(4, card_radius - inner_margin // 2),
                    fill=255,
                )
                img_layer.paste(photo, (card_x + inner_margin, card_y + inner_margin), mask)
            except Exception:
                pass

        img = Image.alpha_composite(img, img_layer)

    # ── 4. 底部字幕区（打字机动画）──
    bottom_y = title_height + image_height
    bottom_h = height - bottom_y

    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [(0, bottom_y), (width, height)],
        fill=style["subtitle_bg_color"],
    )

    if all_body_lines and typewriter_progress > 0:
        # 计算总字符数，按进度决定显示多少字符
        total_chars = sum(len(line) for line in all_body_lines)
        visible_chars = max(1, int(total_chars * typewriter_progress))

        line_height = 48
        bottom_pad_top = 60
        start_y = bottom_y + bottom_pad_top
        max_lines = (bottom_h - bottom_pad_top - 40) // line_height

        chars_remaining = visible_chars
        cursor_line_idx = -1
        cursor_char_idx = -1

        for i, line in enumerate(all_body_lines):
            if i >= max_lines:
                break
            line_len = len(line)
            if chars_remaining >= line_len:
                display_text = line
                chars_remaining -= line_len
                if chars_remaining == 0:
                    cursor_line_idx = i
                    cursor_char_idx = line_len
            elif chars_remaining > 0:
                display_text = line[:chars_remaining]
                cursor_line_idx = i
                cursor_char_idx = chars_remaining
                chars_remaining = 0
            else:
                break

            bbox = draw.textbbox((0, 0), display_text, font=font_body)
            line_w = bbox[2] - bbox[0]
            line_x = (width - line_w) // 2
            draw.text(
                (line_x, start_y + i * line_height),
                display_text, font=font_body,
                fill=style["subtitle_text_color"],
            )

        # 绘制闪烁光标
        if cursor_line_idx >= 0:
            cursor_char = all_body_lines[cursor_line_idx][cursor_char_idx - 1] if cursor_char_idx > 0 else ""
            cursor_prefix = all_body_lines[cursor_line_idx][:cursor_char_idx]
            cursor_bbox = draw.textbbox((0, 0), cursor_prefix, font=font_body)
            cursor_x = (width - cursor_bbox[2] + cursor_bbox[0]) // 2 + (cursor_bbox[2] - cursor_bbox[0])
            cursor_y = start_y + cursor_line_idx * line_height
            cursor_h = cursor_bbox[3] - cursor_bbox[1]
            draw.rectangle(
                [(cursor_x + 2, cursor_y + 2), (cursor_x + 6, cursor_y + cursor_h - 2)],
                fill=style["accent_color"],
            )

    # 转换为 RGB
    rgb_img = Image.new("RGB", (width, height), (0, 0, 0))
    rgb_img.paste(img, (0, 0), img)
    buf = io.BytesIO()
    rgb_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ═══════════════════════════════════════════════════
# 场景切换动画模板
# ═══════════════════════════════════════════════════

def _ease_in_out_cubic(t: float) -> float:
    """缓动函数：cubic ease-in-out"""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def _ease_out_back(t: float) -> float:
    """缓动函数：overshoot ease-out"""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# 每套动效返回 (image_alpha, image_offset_x, image_offset_y, image_scale) 随 progress (0~1) 的变化

def _transition_fade(progress: float) -> dict:
    """柔和淡入"""
    return {
        "image_alpha": _ease_in_out_cubic(progress),
        "image_offset_x": 0,
        "image_offset_y": 0,
        "image_scale": 1.0,
    }


def _transition_slide_left(progress: float) -> dict:
    """从右往左滑入"""
    t = _ease_in_out_cubic(progress)
    return {
        "image_alpha": min(1.0, progress * 2),
        "image_offset_x": int((1 - t) * 300),
        "image_offset_y": 0,
        "image_scale": 1.0,
    }


def _transition_slide_right(progress: float) -> dict:
    """从左往右滑入"""
    t = _ease_in_out_cubic(progress)
    return {
        "image_alpha": min(1.0, progress * 2),
        "image_offset_x": int((t - 1) * 300),
        "image_offset_y": 0,
        "image_scale": 1.0,
    }


def _transition_slide_up(progress: float) -> dict:
    """从下往上滑入"""
    t = _ease_in_out_cubic(progress)
    return {
        "image_alpha": min(1.0, progress * 2),
        "image_offset_x": 0,
        "image_offset_y": int((1 - t) * 300),
        "image_scale": 1.0,
    }


def _transition_zoom_in(progress: float) -> dict:
    """从中心放大进入"""
    t = _ease_out_back(progress)
    return {
        "image_alpha": min(1.0, progress * 3),
        "image_offset_x": 0,
        "image_offset_y": 0,
        "image_scale": 0.3 + 0.7 * t,
    }


# 动效注册表
TRANSITION_FUNCTIONS = {
    "fade": _transition_fade,
    "slide_left": _transition_slide_left,
    "slide_right": _transition_slide_right,
    "slide_up": _transition_slide_up,
    "zoom_in": _transition_zoom_in,
}


# ═══════════════════════════════════════════════════
# 主渲染函数
# ═══════════════════════════════════════════════════

def render_news_video(
    output_path: str,
    title: str,
    subtitle: str,
    scenes: list,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    title_height: int = 560,
    image_height: int = 640,
    transition_duration: float = 0.6,
    style_overrides: dict | None = None,
) -> str:
    """
    渲染无声竖版新闻短视频（纯视觉，无旁白/无BGM）。

    参数:
        output_path: 输出 MP4 路径
        title: 大标题
        subtitle: 副标题
        scenes: 场景列表 [
            {"text": "字幕文案", "image": "/path/img.jpg", "duration": 5.0, "transition": "slide_left"},
            ...
        ]
        width/height: 视频尺寸
        fps: 帧率
        title_height: 标题区域高度
        image_height: 图片卡片高度
        transition_duration: 场景切换动画时长（秒）
        style_overrides: 样式覆盖字典

    返回:
        output_path
    """
    from moviepy import VideoClip, concatenate_videoclips, CompositeVideoClip

    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    style = _deep_merge(DEFAULT_STYLE, style_overrides or {})

    # 加载字体
    font_path = _find_font()
    try:
        font_title = ImageFont.truetype(font_path, style["title_font_size"])
        font_subtitle = ImageFont.truetype(font_path, style["subtitle_font_size"])
        font_body = ImageFont.truetype(font_path, style["subtitle_font_size_bottom"])
    except Exception:
        font_title = ImageFont.load_default()
        font_subtitle = ImageFont.load_default()
        font_body = ImageFont.load_default()

    # 解析场景
    parsed_scenes = []
    for s in scenes:
        if isinstance(s, dict):
            parsed_scenes.append({
                "text": s.get("text", ""),
                "image": s.get("image", ""),
                "duration": float(s.get("duration", 4)),
                "transition": s.get("transition", "none"),
            })
        elif isinstance(s, str):
            parsed_scenes.append({"text": s, "image": "", "duration": 4, "transition": "none"})

    if not parsed_scenes:
        raise ValueError("scenes 不能为空")

    # ── 为每个场景生成视频片段 ──
    scene_clips = []

    for scene_idx, scene in enumerate(parsed_scenes):
        duration = scene["duration"]
        text = scene["text"]
        image_path = scene["image"]
        transition_type = scene.get("transition", "none")

        # 拆分字幕行
        body_lines = _wrap_text_by_chars(text, 18)
        if not body_lines:
            body_lines = [text]

        total_frames = int(duration * fps)

        # 打字机动画时序:
        # 0.0 ~ 0.15 * duration: 静止（给观众看标题和图片）
        # 0.15 ~ 0.6 * duration: 打字动画
        # 0.6 ~ 1.0 * duration: 完整文字停留
        typewriter_delay_ratio = 0.15
        typewriter_end_ratio = 0.60

        frame_data = []
        for frame_idx in range(total_frames):
            frame_t = frame_idx / total_frames

            # 打字机进度
            if frame_t < typewriter_delay_ratio:
                typewriter_progress = 0.0
            elif frame_t < typewriter_end_ratio:
                raw = (frame_t - typewriter_delay_ratio) / (typewriter_end_ratio - typewriter_delay_ratio)
                typewriter_progress = _ease_in_out_cubic(raw)
            else:
                typewriter_progress = 1.0

            # 图片动效（仅 scene_idx > 0 时应用进入动效，持续 transition_duration 秒）
            ia, iox, ioy, iscale = 1.0, 0.0, 0.0, 1.0
            if scene_idx > 0 and transition_type != "none":
                trans_fn = TRANSITION_FUNCTIONS.get(transition_type, _transition_fade)
                trans_frames = int(transition_duration * fps)
                if frame_idx < trans_frames:
                    trans_progress = frame_idx / trans_frames
                    params = trans_fn(trans_progress)
                    ia = params["image_alpha"]
                    iox = params["image_offset_x"]
                    ioy = params["image_offset_y"]
                    iscale = params["image_scale"]

            jpg_bytes = _render_frame(
                width, height,
                title, subtitle,
                image_path,
                typewriter_progress,
                body_lines,
                title_height, image_height,
                style,
                font_title, font_subtitle, font_body,
                image_alpha=ia,
                image_offset_x=iox,
                image_offset_y=ioy,
                image_scale=iscale,
            )
            frame_data.append(jpg_bytes)

        def make_frame(t, fd=frame_data, f=fps):
            idx = min(int(t * f), len(fd) - 1)
            buf = io.BytesIO(fd[idx])
            try:
                return np.array(Image.open(buf))
            except Exception:
                return np.zeros((height, width, 3), dtype=np.uint8)

        clip = VideoClip(make_frame, duration=duration).with_fps(fps)
        scene_clips.append(clip)

    # ── 拼接所有场景（简单串联，动效已在各场景开头内部渲染）──
    if len(scene_clips) == 1:
        final_video = scene_clips[0]
    else:
        final_video = concatenate_videoclips(scene_clips, method="compose")

    # ── 输出（无声）──
    final_video.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio=False,
        preset="medium",
        logger=None,
    )

    for c in scene_clips:
        c.close()
    final_video.close()

    return output_path
