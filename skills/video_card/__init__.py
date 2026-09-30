"""
video_card skill - 竖版卡片短视频统一入口

合并原 video_auto / video_custom / video_overlay 三个入口，按两个维度区分差异：
  - asset_source : auto（AI 自动配图 / 自动提炼脚本） | user（LLM 手动提供素材）
  - material_type: image（中部为静态图片） | video（中部为视频，可保留音轨）

本入口是薄路由层，不重写渲染逻辑，按参数委托给已存在的内部工具执行：
  - material_type=video          -> dispatch("video_overlay")  复用 overlay_render (moviepy 原生叠加)
  - material_type=image,user     -> dispatch("video_custom")   复用 video_short (PIL 逐帧)
  - asset_source=auto            -> dispatch("video_auto")     复用新闻解析+AI 配图 + video_short

asset_source / material_type 是数据驱动的参数分支，非关键词匹配打分。
"""
from skills.base import BaseTool, ToolParameter, ToolResult

from skills.video_auto import DEFAULT_IMAGE_STYLE


class VideoCardTool(BaseTool):
    name = "video_card"
    description = (
        "竖版卡片短视频（9:16 无声）统一入口。顶部标题/副标题 + 中部素材卡片 + 底部打字机字幕。"
        "素材来源 asset_source：auto=AI自动配图（给 news_content 自动提炼脚本）；user=你手动提供素材路径。"
        "中部素材类型 material_type：image=静态图片；video=视频素材（可 keep_audio 保留音轨）。"
        "这是做新闻/资讯/产品/教程等竖版卡片视频的统一入口。"
        "区别于 video_produce（完整流水线带旁白）与 video_cinematic（电影级AI生视频）。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 MP4 文件路径（绝对路径）"),
        ToolParameter("asset_source", "string",
            "素材来源。auto=AI自动配图并自动提炼脚本（配合 news_content）；user=你手动提供素材路径（配合 scenes）",
            required=False, default="user", enum=["auto", "user"]),
        ToolParameter("material_type", "string",
            "中部素材类型。image=静态图片（走 PIL 逐帧合成）；video=视频素材（moviepy 原生叠加，可保留音轨）",
            required=False, default="image", enum=["image", "video"]),
        ToolParameter("news_content", "string",
            "原文/内容。仅 asset_source=auto 时必填，自动提炼标题+分镜并 AI 配图", required=False),
        ToolParameter("title", "string", "大标题。auto 时可由 news_content 自动提炼", required=False),
        ToolParameter("subtitle", "string", "副标题", required=False, default=""),
        ToolParameter("scenes", "array",
            "场景列表。material_type=image 时每项含 image(图片路径,必填)；"
            "material_type=video 时每项含 media(视频/图片路径,必填)。"
            "每项: {text(字幕文案), duration(时长秒,默认4), transition(fade|slide_left|slide_right|slide_up|zoom_in,默认none)}",
            required=False),
        ToolParameter("keep_audio", "boolean", "仅 material_type=video 生效：素材视频是否保留音轨，默认 true",
            required=False, default=True),
        ToolParameter("image_style", "string", "仅 asset_source=auto 生效：AI 生成图片风格前缀",
            required=False, default=DEFAULT_IMAGE_STYLE),
        ToolParameter("width", "integer", "视频宽度，默认 1080", required=False, default=1080),
        ToolParameter("height", "integer", "视频高度，默认 1920（竖版 9:16）", required=False, default=1920),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
        ToolParameter("title_height", "integer", "标题区域高度（px），默认 560", required=False, default=560),
        ToolParameter("image_height", "integer", "图片卡片高度（px，material_type=image），默认 640", required=False, default=640),
        ToolParameter("media_height", "integer", "素材卡片高度（px，material_type=video），默认 640", required=False, default=640),
        ToolParameter("style", "object",
            "视觉样式覆盖（可选）。可覆盖键: bg_gradient_top, bg_gradient_bottom, title_color, subtitle_color, "
            "subtitle_text_color, subtitle_bg_color, accent_color, card_radius, card_bg, "
            "title_font_size, subtitle_font_size, subtitle_font_size_bottom。颜色用 #RRGGBB 或 rgba(...)",
            required=False, default=None),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None, **kwargs):
        super().__init__(cwd)
        self.skill_manager = skill_manager

    def execute(
        self,
        output_path: str,
        asset_source: str = "user",
        material_type: str = "image",
        news_content: str = None,
        title: str = None,
        subtitle: str = "",
        scenes: list = None,
        keep_audio: bool = True,
        image_style: str = DEFAULT_IMAGE_STYLE,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        title_height: int = 560,
        image_height: int = 640,
        media_height: int = 640,
        style: dict = None,
        **kwargs,
    ) -> ToolResult:
        if not self.skill_manager:
            return ToolResult.fail("video_card 需要 skill_manager 上下文")

        # ── 分支 1: 视频素材 ──
        if material_type == "video":
            return self._route_overlay(
                output_path=output_path, title=title, subtitle=subtitle,
                scenes=scenes, keep_audio=keep_audio, width=width, height=height,
                fps=fps, title_height=title_height, media_height=media_height,
                style=style,
            )

        # ── 分支 2: 图片素材 + user ──
        if asset_source == "user":
            return self._route_custom(
                output_path=output_path, title=title, subtitle=subtitle,
                scenes=scenes, width=width, height=height, fps=fps,
                title_height=title_height, image_height=image_height, style=style,
            )

        # ── 分支 3: auto（自动配图/自动提炼） ──
        return self._route_auto(
            output_path=output_path, news_content=news_content, title=title,
            subtitle=subtitle, scenes=scenes, image_style=image_style,
            width=width, height=height, fps=fps,
            title_height=title_height, image_height=image_height,
        )

    # ── material_type=video → video_overlay (overlay_render / moviepy 原生叠加) ──
    def _route_overlay(self, output_path, title, subtitle, scenes, keep_audio,
                       width, height, fps, title_height, media_height, style):
        normalized = self._normalize_scenes(scenes, target="media")
        if not title:
            return ToolResult.fail("video_card(material_type=video) 需要 title")
        if not normalized:
            return ToolResult.fail(
                "video_card(material_type=video) 缺少 scenes，且每项需含素材路径（media，视频或图片）。"
            )
        result = self.skill_manager.dispatch(
            "video_overlay",
            output_path=output_path,
            title=title,
            subtitle=subtitle or "",
            scenes=normalized,
            keep_audio=keep_audio,
            width=width, height=height, fps=fps,
            title_height=title_height,
            media_height=media_height,
            style=style,
        )
        return result

    # ── material_type=image + user → video_custom (video_short / PIL 逐帧) ──
    def _route_custom(self, output_path, title, subtitle, scenes,
                      width, height, fps, title_height, image_height, style):
        normalized = self._normalize_scenes(scenes, target="image")
        if not title:
            return ToolResult.fail("video_card(asset_source=user) 需要 title")
        if not normalized:
            return ToolResult.fail(
                "video_card(asset_source=user) 缺少 scenes，且每项需含图片路径（image）。"
            )
        result = self.skill_manager.dispatch(
            "video_custom",
            output_path=output_path,
            title=title,
            subtitle=subtitle or "",
            scenes=normalized,
            width=width, height=height, fps=fps,
            title_height=title_height,
            image_height=image_height,
            style=style,
        )
        return result

    # ── asset_source=auto → video_auto (新闻解析 + AI 配图 + video_short) ──
    def _route_auto(self, output_path, news_content, title, subtitle, scenes,
                    image_style, width, height, fps, title_height, image_height):
        kwargs = {
            "output_path": output_path,
            "image_style": image_style,
            "width": width, "height": height, "fps": fps,
            "title_height": title_height,
            "image_height": image_height,
        }
        if news_content and news_content.strip():
            # 走自动提炼 + AI 配图
            return self.skill_manager.dispatch("video_auto", news_content=news_content, **kwargs)
        # 无 news_content：手动给 title/subtitle/scenes，但用 auto 的配图管线做 AI 配图（即原 video_auto 手动分支）
        if not title:
            return ToolResult.fail(
                "video_card(asset_source=auto) 需要 news_content 自动提炼，或提供 title+scenes 指定内容。"
            )
        kwargs["title"] = title
        kwargs["subtitle"] = subtitle or ""
        normalized = self._normalize_scenes(scenes, target="image")
        if normalized:
            kwargs["scenes"] = normalized
        result = self.skill_manager.dispatch("video_auto", **kwargs)
        return result

    @staticmethod
    def _normalize_scenes(scenes, target: str) -> list:
        """把统一 schema 的 scenes 归一化到内层工具期望的字段 (image 或 media)。

        material_type=image -> target='image'；material_type=video -> target='media'。
        兼容三种来源键：image / media / video。
        """
        if not scenes or not isinstance(scenes, list):
            return []
        out = []
        for s in scenes:
            if not isinstance(s, dict):
                continue
            src = s.get("media") or s.get("image") or s.get("video") or ""
            item = {
                "text": str(s.get("text", "")),
                target: src,
                "duration": float(s.get("duration", 4)),
                "transition": s.get("transition", "none"),
            }
            out.append(item)
        return out


__all__ = ["VideoCardTool"]