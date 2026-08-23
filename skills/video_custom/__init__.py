"""
video_custom skill - 自定义竖版视频生成

与 video_auto 的区别:
  - video_auto: 新闻全自动（生图/解析脚本），LLM 只需给原文
  - video_custom: 完全自定义（LLM 自己准备图片和场景），不做任何自动配图

复用 video_auto/scripts/video_short.py 的渲染引擎，固定竖版 9:16 布局:
  - 顶部标题区 (title_height px)
  - 中部图片卡片 (image_height px, 圆角)
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


class VideoCustomTool(BaseTool):
    name = "video_custom"
    description = (
        "自定义竖版（9:16）视频生成。LLM 自行准备场景图片（本地文件路径），"
        "指定标题、副标题、每个场景的文案/时长/图片/转场动效，以及整体视觉样式。"
        "不做任何自动配图，完全由 LLM 控制素材和内容。"
        "适用于：产品展示、品牌宣传、活动回顾、教程演示等非新闻类竖版短视频。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 MP4 文件路径（绝对路径或相对路径）"),
        ToolParameter("title", "string", "视频大标题"),
        ToolParameter("scenes", "array",
            "场景列表。每项: {text(字幕文案), image(图片绝对路径,必填), "
            "duration(时长秒数,默认4), transition(动效:fade|slide_left|slide_right|slide_up|zoom_in,默认none)}"),
        ToolParameter("subtitle", "string", "副标题", required=False, default=""),
        ToolParameter("width", "integer", "视频宽度，默认 1080", required=False, default=1080),
        ToolParameter("height", "integer", "视频高度，默认 1920（竖版 9:16）", required=False, default=1920),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
        ToolParameter("title_height", "integer", "标题区域高度（px），默认 560", required=False, default=560),
        ToolParameter("image_height", "integer", "图片卡片高度（px），默认 640", required=False, default=640),
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
        image_height: int = 640,
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
        missing_images = []
        for i, s in enumerate(scenes):
            if not isinstance(s, dict):
                return ToolResult.fail(f"scenes[{i}] 必须是字典格式")
            img = s.get("image", "")
            if not img:
                missing_images.append(str(i))
            parsed_scenes.append({
                "text": str(s.get("text", "")),
                "image": img,
                "duration": float(s.get("duration", 4)),
                "transition": s.get("transition", "none"),
            })

        if missing_images:
            return ToolResult.fail(
                f"以下场景缺少图片路径: [{', '.join(missing_images)}]。"
                f"请先准备图片（生图/本地文件），再调用 video_custom。"
            )

        # 校验图片文件存在
        self._emit_progress(f"正在校验 {len(parsed_scenes)} 个场景素材...")
        for i, s in enumerate(parsed_scenes):
            img_path = Path(s["image"])
            if not img_path.is_absolute():
                img_path = self._resolve_path(s["image"])
                parsed_scenes[i]["image"] = str(img_path)
            if not img_path.exists():
                return ToolResult.fail(
                    f"scenes[{i}] 图片不存在: {s['image']}"
                )

        # 处理样式：合并默认样式 + 用户覆盖
        style_overrides = dict(DEFAULT_STYLE)
        if style and isinstance(style, dict):
            for k, v in style.items():
                if k in style_overrides:
                    style_overrides[k] = v

        # 调用渲染引擎
        self._emit_progress(f"正在渲染视频 ({len(parsed_scenes)} 个场景, {width}x{height})...")
        from skills.video_auto.scripts.video_short import render_news_video

        try:
            result_path = render_news_video(
                output_path=str(out),
                title=title.strip(),
                subtitle=subtitle.strip() if subtitle else "",
                scenes=parsed_scenes,
                width=width,
                height=height,
                fps=fps,
                title_height=title_height,
                image_height=image_height,
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
            f"文件大小: {round(size_mb, 1)} MB",
            output_path=str(Path(result_path).resolve()),
            title=title,
            scene_count=len(parsed_scenes),
            resolution=f"{width}x{height}",
            size_mb=round(size_mb, 1),
        )
