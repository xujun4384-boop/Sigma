"""
video_overlay skill - 竖版卡片视频生成（中部支持视频叠加）

与 video_custom 的区别:
  - video_custom 中部只支持静态图片（PIL 逐帧合成）
  - video_overlay 中部支持视频/图片，视频用 moviepy 原生叠加播放，可保留音轨

布局固定 9:16 竖版:
  - 顶部标题区 (title_height px)
  - 中部素材卡片 (media_height px, 圆角, 支持视频/图片)
  - 底部字幕区 (剩余高度, 打字机动画)
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

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
}


class VideoOverlayTool(BaseTool):
    name = "video_overlay"
    description = (
        "竖版（9:16）卡片视频生成，中部素材区域支持视频和图片。"
        "顶部固定标题/副标题，中部圆角卡片叠加视频或图片，底部打字机动画字幕。"
        "视频素材用 moviepy 原生叠加播放，支持保留音轨。"
        "适用于：新闻解说、产品演示、教程讲解等需要在中部嵌入视频片段的场景。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 MP4 文件路径（绝对路径或相对路径）"),
        ToolParameter("title", "string", "视频大标题"),
        ToolParameter("scenes", "array",
            "场景列表。每项: {text(字幕文案), media(素材绝对路径,支持视频/图片), "
            "duration(时长秒数,默认4), transition(动效:fade|slide_left|slide_right|slide_up|zoom_in,默认none)}"),
        ToolParameter("subtitle", "string", "副标题", required=False, default=""),
        ToolParameter("width", "integer", "视频宽度，默认 1080", required=False, default=1080),
        ToolParameter("height", "integer", "视频高度，默认 1920（竖版 9:16）", required=False, default=1920),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
        ToolParameter("title_height", "integer", "标题区域高度（px），默认 560", required=False, default=560),
        ToolParameter("media_height", "integer", "素材卡片高度（px），默认 640", required=False, default=640),
        ToolParameter("keep_audio", "boolean", "素材视频是否保留音轨，默认 true", required=False, default=True),
        ToolParameter("style", "object",
            "视觉样式覆盖（可选）。可覆盖的键: bg_gradient_top, bg_gradient_bottom, "
            "title_color, subtitle_color, subtitle_text_color, subtitle_bg_color, "
            "accent_color, card_radius, card_bg, title_font_size, subtitle_font_size, "
            "subtitle_font_size_bottom。颜色用 #RRGGBB 或 rgba(...) 格式。",
            required=False, default=None),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(
        self,
        output_path: str,
        title: str,
        scenes: list,
        subtitle: str = "",
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        title_height: int = 560,
        media_height: int = 640,
        keep_audio: bool = True,
        style: dict = None,
        **kwargs,
    ) -> ToolResult:
        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 目标已存在
        if out.exists() and out.stat().st_size > 1024:
            size_mb = out.stat().st_size / 1024 / 1024
            return ToolResult.ok(
                f"视频已存在: {out.name} ({round(size_mb, 1)} MB)",
                output_path=str(out.resolve()),
                size_mb=round(size_mb, 1),
            )

        # 校验参数
        if not title or not title.strip():
            return ToolResult.fail("title 不能为空")
        if not scenes or not isinstance(scenes, list):
            return ToolResult.fail("scenes 必须是非空列表")

        # 标准化 scenes
        parsed_scenes = []
        missing_media = []
        for i, s in enumerate(scenes):
            if not isinstance(s, dict):
                return ToolResult.fail(f"scenes[{i}] 必须是字典格式")
            media = s.get("media") or s.get("image") or s.get("video") or ""
            if not media:
                missing_media.append(str(i))
            parsed_scenes.append({
                "text": str(s.get("text", "")),
                "media": media,
                "duration": float(s.get("duration", 4)),
                "transition": s.get("transition", "none"),
            })

        if missing_media:
            return ToolResult.fail(
                f"以下场景缺少素材路径: [{', '.join(missing_media)}]。"
                f"请提供 media 字段（视频或图片路径）。"
            )

        # 校验素材文件存在
        self._emit_progress(f"正在校验 {len(parsed_scenes)} 个场景素材...")
        for i, s in enumerate(parsed_scenes):
            media_path = Path(s["media"])
            if not media_path.is_absolute():
                media_path = self._resolve_path(s["media"])
                parsed_scenes[i]["media"] = str(media_path)
            if not media_path.exists():
                return ToolResult.fail(
                    f"scenes[{i}] 素材不存在: {s['media']}"
                )

        # 处理样式：合并默认样式 + 用户覆盖
        style_overrides = dict(DEFAULT_STYLE)
        if style and isinstance(style, dict):
            for k, v in style.items():
                if k in style_overrides:
                    style_overrides[k] = v

        # 调用渲染引擎
        self._emit_progress(f"正在渲染视频 ({len(parsed_scenes)} 个场景, {width}x{height})...")
        from .scripts.overlay_render import render_overlay_video

        try:
            result_path = render_overlay_video(
                output_path=str(out),
                title=title.strip(),
                subtitle=subtitle.strip() if subtitle else "",
                scenes=parsed_scenes,
                width=width,
                height=height,
                fps=fps,
                title_height=title_height,
                media_height=media_height,
                keep_audio=keep_audio,
                style_overrides=style_overrides,
            )
        except ImportError as e:
            return ToolResult.fail(
                f"缺少 Python 依赖，请执行: pip install moviepy pillow numpy\n错误: {e}"
            )
        except Exception as e:
            return ToolResult.fail(f"视频渲染失败: {e}")

        size_mb = Path(result_path).stat().st_size / 1024 / 1024 if Path(result_path).exists() else 0
        return ToolResult.ok(
            f"视频生成完成: {Path(result_path).name}\n"
            f"标题: {title}\n"
            f"场景数: {len(parsed_scenes)}\n"
            f"分辨率: {width}x{height}\n"
            f"音轨: {'保留' if keep_audio else '静音'}\n"
            f"文件大小: {round(size_mb, 1)} MB",
            output_path=str(Path(result_path).resolve()),
            title=title,
            scene_count=len(parsed_scenes),
            resolution=f"{width}x{height}",
            size_mb=round(size_mb, 1),
        )


__all__ = ["VideoOverlayTool"]
