"""
video_overlay 渲染脚本 - 竖版卡片模板，中部支持视频叠加

布局（默认 1080×1920）:
  - 顶部标题区: title_height px（大标题 + 副标题，渐变背景）
  - 中部素材区: media_height px（圆角卡片，可放图片或视频）
  - 底部字幕区: 剩余高度（打字机逐字动画）

与 video_short 的区别:
  - video_short 中部只支持静态图片（PIL 逐帧合成）
  - video_overlay 中部支持视频（moviepy 原生 VideoFileClip 叠加，可保留音轨）
"""
import os
import io
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from skills.video_auto.scripts.video_short import (
    _find_font,
    _wrap_text,
    _wrap_text_by_chars,
    _deep_merge,
    _hex_to_rgb,
    DEFAULT_STYLE,
    TRANSITION_FUNCTIONS,
)


# ═══════════════════════════════════════════════════
# 单帧背景渲染（不含中部素材，素材由 moviepy 叠加）
# ═══════════════════════════════════════════════════

def _render_background_frame(
    width: int, height: int,
    title: str, subtitle: str,
    typewriter_progress: float,
    all_body_lines: list[str],
    title_height: int,
    media_height: int,
    style: dict,
    font_title, font_subtitle, font_body,
) -> np.ndarray:
    """
    渲染背景帧：渐变背景 + 标题/副标题 + 卡片底色 + 打字机字幕。
    中部素材区域留空（由 moviepy 叠加视频/图片）。
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 背景渐变 ──
    tc = _hex_to_rgb(style["bg_gradient_top"])
    bc = _hex_to_rgb(style["bg_gradient_bottom"])
    for y in range(height):
        ratio = y / height
        r = int(tc[0] + (bc[0] - tc[0]) * ratio)
        g = int(tc[1] + (bc[1] - tc[1]) * ratio)
        b = int(tc[2] + (bc[2] - tc[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # ── 顶部标题区（文字靠下，避开状态栏）──
    title_area_bottom = title_height
    title_max_width = int(width * style.get("title_max_width_ratio", 0.85))

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

    # ── 中部素材卡片底色（素材由 moviepy 叠加在此区域之上）──
    card_radius = style["card_radius"]
    card_margin_h = 40
    card_margin_v = 20
    card_x = card_margin_h
    card_y = title_height + card_margin_v
    card_w = width - card_margin_h * 2
    card_h = media_height - card_margin_v * 2
    inner_margin = 8

    card_bg_color = _hex_to_rgb(style["card_bg"])
    card_bg = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_bg)
    card_draw.rounded_rectangle(
        [(0, 0), (card_w, card_h)],
        radius=card_radius, fill=(*card_bg_color, 255),
    )
    img.paste(card_bg, (card_x, card_y), card_bg)

    # ── 底部字幕区（打字机动画）──
    bottom_y = title_height + media_height
    bottom_h = height - bottom_y

    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [(0, bottom_y), (width, height)],
        fill=style["subtitle_bg_color"],
    )

    if all_body_lines and typewriter_progress > 0:
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

        # 闪烁光标
        if cursor_line_idx >= 0:
            cursor_prefix = all_body_lines[cursor_line_idx][:cursor_char_idx]
            cursor_bbox = draw.textbbox((0, 0), cursor_prefix, font=font_body)
            cursor_x = (width - cursor_bbox[2] + cursor_bbox[0]) // 2 + (cursor_bbox[2] - cursor_bbox[0])
            cursor_y = start_y + cursor_line_idx * line_height
            cursor_h = cursor_bbox[3] - cursor_bbox[1]
            draw.rectangle(
                [(cursor_x + 2, cursor_y + 2), (cursor_x + 6, cursor_y + cursor_h - 2)],
                fill=style["accent_color"],
            )

    rgb_img = Image.new("RGB", (width, height), (0, 0, 0))
    rgb_img.paste(img, (0, 0), img)
    return np.array(rgb_img)


# ═══════════════════════════════════════════════════
# 圆角 mask 生成（供 moviepy 使用）
# ═══════════════════════════════════════════════════

def _make_rounded_mask(width: int, height: int, radius: int):
    """生成圆角矩形 mask（moviepy ImageClip）。"""
    from moviepy import ImageClip
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (width, height)], radius=radius, fill=255)
    mask_array = np.array(mask) / 255.0
    return ImageClip(mask_array, is_mask=True)


# ═══════════════════════════════════════════════════
# 素材类型判断（不硬编码关键词，按文件魔数/扩展名白名单）
# ═══════════════════════════════════════════════════

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff"}


def _is_video_file(path: str) -> bool:
    """按扩展名判断是否为视频文件（非关键词匹配，是文件类型白名单）。"""
    ext = Path(path).suffix.lower()
    if ext in _VIDEO_EXTENSIONS:
        return True
    if ext in _IMAGE_EXTENSIONS:
        return False
    # 未知扩展名：尝试按图片打开，失败则认为是视频
    try:
        Image.open(path)
        return False
    except Exception:
        return True


# ═══════════════════════════════════════════════════
# 主渲染函数
# ═══════════════════════════════════════════════════

def render_overlay_video(
    output_path: str,
    title: str,
    subtitle: str,
    scenes: list,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    title_height: int = 560,
    media_height: int = 640,
    transition_duration: float = 0.6,
    keep_audio: bool = True,
    style_overrides: dict | None = None,
) -> str:
    """
    渲染竖版卡片视频，中部支持视频/图片叠加。

    参数:
        output_path: 输出 MP4 路径
        title: 大标题
        subtitle: 副标题
        scenes: 场景列表 [
            {
                "text": "字幕文案",
                "media": "/path/video.mp4 或 /path/img.jpg",
                "duration": 5.0,
                "transition": "fade|slide_left|slide_right|slide_up|zoom_in|none",
            },
            ...
        ]
        width/height: 视频尺寸
        fps: 帧率
        title_height: 标题区域高度
        media_height: 中部素材卡片高度
        transition_duration: 场景切换动效时长（秒）
        keep_audio: 素材视频是否保留音轨（默认 True）
        style_overrides: 样式覆盖字典

    返回:
        output_path
    """
    from moviepy import (
        VideoClip, VideoFileClip, ImageClip, ColorClip,
        CompositeVideoClip, concatenate_videoclips,
        concatenate_audioclips, CompositeAudioClip,
    )

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
            media_path = s.get("media") or s.get("image") or s.get("video") or ""
            parsed_scenes.append({
                "text": s.get("text", ""),
                "media": media_path,
                "duration": float(s.get("duration", 4)),
                "transition": s.get("transition", "none"),
            })
        elif isinstance(s, str):
            parsed_scenes.append({"text": s, "media": "", "duration": 4, "transition": "none"})

    if not parsed_scenes:
        raise ValueError("scenes 不能为空")

    # 中部素材卡片几何参数（与 _render_background_frame 一致）
    card_margin_h = 40
    card_margin_v = 20
    card_x = card_margin_h
    card_y = title_height + card_margin_v
    card_w = width - card_margin_h * 2
    card_h = media_height - card_margin_v * 2
    inner_margin = 8
    inner_w = card_w - inner_margin * 2
    inner_h = card_h - inner_margin * 2
    inner_x = card_x + inner_margin
    inner_y = card_y + inner_margin

    # 圆角 mask（素材叠加用）
    corner_radius = max(4, style["card_radius"] - inner_margin // 2)
    media_mask = _make_rounded_mask(inner_w, inner_h, corner_radius)

    scene_clips = []

    for scene_idx, scene in enumerate(parsed_scenes):
        duration = scene["duration"]
        text = scene["text"]
        media_path = scene["media"]
        transition_type = scene.get("transition", "none")

        body_lines = _wrap_text_by_chars(text, 18)
        if not body_lines:
            body_lines = [text]

        # 打字机动画时序
        typewriter_delay_ratio = 0.15
        typewriter_end_ratio = 0.60

        # 预渲染打字机关键帧（避免逐帧 PIL 开销，但保留打字机动画）
        total_frames = int(duration * fps)
        frame_data = []
        for frame_idx in range(total_frames):
            frame_t = frame_idx / total_frames
            if frame_t < typewriter_delay_ratio:
                typewriter_progress = 0.0
            elif frame_t < typewriter_end_ratio:
                raw = (frame_t - typewriter_delay_ratio) / (typewriter_end_ratio - typewriter_delay_ratio)
                from skills.video_auto.scripts.video_short import _ease_in_out_cubic
                typewriter_progress = _ease_in_out_cubic(raw)
            else:
                typewriter_progress = 1.0

            frame_data.append(
                _render_background_frame(
                    width, height, title, subtitle,
                    typewriter_progress, body_lines,
                    title_height, media_height, style,
                    font_title, font_subtitle, font_body,
                )
            )

        def make_bg_frame(t, fd=frame_data, f=fps):
            idx = min(int(t * f), len(fd) - 1)
            return fd[idx]

        bg_clip = VideoClip(make_bg_frame, duration=duration).with_fps(fps)

        # ── 中部素材叠加 ──
        media_clip = None
        if media_path and os.path.exists(media_path):
            if _is_video_file(media_path):
                # 视频素材：moviepy 原生播放
                src = VideoFileClip(media_path)
                # 时长策略：源视频短则循环，长则截断
                if src.duration < duration:
                    loops = int(duration / src.duration) + 1
                    from moviepy import concatenate_videoclips as concat_videos
                    src = concat_videos([src] * loops)
                if src.duration > duration:
                    src = src.subclipped(0, duration)

                # 缩放并居中裁切到 inner_w x inner_h
                src_ratio = src.w / src.h
                target_ratio = inner_w / inner_h
                if src_ratio > target_ratio:
                    new_h = inner_h
                    new_w = int(new_h * src_ratio)
                else:
                    new_w = inner_w
                    new_h = int(new_w / src_ratio)
                src = src.resized((new_w, new_h))
                x1 = (new_w - inner_w) // 2
                y1 = (new_h - inner_h) // 2
                src = src.cropped(x1=x1, y1=y1, width=inner_w, height=inner_h)

                # 保留音轨（可选）
                if keep_audio and src.audio is not None:
                    src = src.with_audio(src.audio)
                else:
                    src = src.without_audio()

                media_clip = src
            else:
                # 图片素材：静态 ImageClip
                img_clip = ImageClip(media_path, duration=duration)
                img_ratio = img_clip.w / img_clip.h
                target_ratio = inner_w / inner_h
                if img_ratio > target_ratio:
                    new_h = inner_h
                    new_w = int(new_h * img_ratio)
                else:
                    new_w = inner_w
                    new_h = int(new_w / img_ratio)
                img_clip = img_clip.resized((new_w, new_h))
                x1 = (new_w - inner_w) // 2
                y1 = (new_h - inner_h) // 2
                img_clip = img_clip.cropped(x1=x1, y1=y1, width=inner_w, height=inner_h)
                media_clip = img_clip

        if media_clip is not None:
            # 应用圆角 mask
            media_clip = media_clip.with_mask(media_mask)

            # 转场动效（仅作用于素材叠加层）
            if scene_idx > 0 and transition_type != "none":
                trans_fn = TRANSITION_FUNCTIONS.get(transition_type)
                if trans_fn:
                    trans_frames = int(transition_duration * fps)

                    def media_transform(get_frame, t, trans_fn=trans_fn, trans_frames=trans_frames):
                        """在转场期间对素材帧做 alpha/offset/scale 变换。"""
                        frame_idx = int(t * fps)
                        if frame_idx >= trans_frames:
                            return get_frame(t)
                        progress = frame_idx / trans_frames
                        params = trans_fn(progress)
                        alpha = params["image_alpha"]
                        offset_x = int(params["image_offset_x"])
                        offset_y = int(params["image_offset_y"])
                        scale = params["image_scale"]

                        frame = get_frame(t)
                        if scale != 1.0:
                            sw = max(1, int(inner_w * scale))
                            sh = max(1, int(inner_h * scale))
                            pil_img = Image.fromarray(frame).resize((sw, sh), Image.Resampling.LANCZOS)
                            canvas = Image.new("RGB", (inner_w, inner_h), (0, 0, 0))
                            px = (inner_w - sw) // 2 + offset_x
                            py = (inner_h - sh) // 2 + offset_y
                            canvas.paste(pil_img, (px, py))
                            frame = np.array(canvas)
                        elif offset_x != 0 or offset_y != 0:
                            pil_img = Image.fromarray(frame)
                            canvas = Image.new("RGB", (inner_w, inner_h), (0, 0, 0))
                            canvas.paste(pil_img, (offset_x, offset_y))
                            frame = np.array(canvas)

                        if alpha < 1.0:
                            frame = (frame * alpha).astype(np.uint8)
                        return frame

                    media_clip = media_clip.transform(media_transform)

            media_clip = media_clip.with_position((inner_x, inner_y))
            scene_clip = CompositeVideoClip([bg_clip, media_clip], size=(width, height))
        else:
            scene_clip = bg_clip

        scene_clips.append(scene_clip)

    # ── 拼接所有场景 ──
    if len(scene_clips) == 1:
        final_video = scene_clips[0]
    else:
        final_video = concatenate_videoclips(scene_clips, method="compose")

    # ── 收集音轨 ──
    audio_clips = []
    current_start = 0.0
    for idx, clip in enumerate(scene_clips):
        if isinstance(clip, CompositeVideoClip):
            for sub in clip.clips:
                if hasattr(sub, "audio") and sub.audio is not None:
                    audio_clips.append(sub.audio.with_start(current_start))
        elif hasattr(clip, "audio") and clip.audio is not None:
            audio_clips.append(clip.audio.with_start(current_start))
        current_start += parsed_scenes[idx]["duration"]

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
        final_video = final_video.with_audio(final_audio)
    else:
        final_video = final_video.without_audio()

    # ── 输出 ──
    final_video.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac" if audio_clips else None,
        preset="medium",
        logger=None,
    )

    for c in scene_clips:
        c.close()
    final_video.close()

    return output_path
