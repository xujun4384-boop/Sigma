"""
video_shot skill - 产一段视频片段（自由组合长视频的积木）

给主 LLM 一个"片段级"能力：按 engine 指定内容引擎，产出一段独立 mp4
（可选带旁白），主 LLM 想用几段就调几次，最后统一交 compose_video 合成。

engine 是 enum → 内部引擎工具的映射（数据驱动，非关键词打分），天然可扩展：
  - opendesign  : 文字/排版/图表画面（opendesign_video, HTML 渲染）
  - card        : 竖版卡片短视频（video_card, PIL 逐帧）
  - cinematic   : 影视级 AI 视频（video_cinematic_generate, MiniMax 纯 prompt）
  - pdoom       : 水彩动画（pdoom_render, 需提供 html_path=?core=章节脚本）

旁白（narration 可选）走内部 doubao_tts，返回 mp3 路径 + 字级时间戳，
供组合时按时间轴对字幕。
"""
from skills.base import BaseTool, ToolParameter, ToolResult

DEFAULT_SPEAKER = "zh_male_guanggaojieshuo_uranus_bigtts"


class VideoShotTool(BaseTool):
    name = "video_shot"
    description = (
        "产出一段视频片段（积木）。指定内容引擎 engine(opendesign|card|cinematic|pdoom) 渲染一段独立 mp4，"
        "可选 narration 生成旁白(mp3+字级时间戳)。做「组合长视频」时，主 LLM 逐段视听内容决定引擎，"
        "多段产物统一交给 compose_video 合成。区别于 video_produce(整套流水线) / video_card(单卡)。"
    )
    parameters = [
        ToolParameter("output_path", "string", "本段输出 MP4 文件路径（绝对路径）"),
        ToolParameter("engine", "string", "内容引擎: opendesign(文字图表/HTML) / card(竖版卡片) / cinematic(影视级AI) / pdoom(水彩动画,需html_path)",
                      enum=["opendesign", "card", "cinematic", "pdoom"]),
        ToolParameter("narration", "string", "本段旁白文本（可选）。提供后走内部 TTS 生成 mp3，返回字级时间戳", required=False),
        ToolParameter("speaker", "string", "旁白音色ID", required=False, default=DEFAULT_SPEAKER),
        ToolParameter("project", "string", "工程名，用于组织产物目录", required=False),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        # ── opendesign ──
        ToolParameter("brief", "string", "engine=opendesign：本段画面需求描述", required=False),
        ToolParameter("n_scenes", "integer", "engine=opendesign：本段场景数", required=False),
        ToolParameter("style_prompt", "string", "engine=opendesign：视觉风格描述", required=False),
        ToolParameter("assets_dir", "string", "engine=opendesign：配图目录", required=False),
        # ── card ──
        ToolParameter("material_type", "string", "engine=card：中部素材类型 image|video", required=False, enum=["image", "video"]),
        ToolParameter("asset_source", "string", "engine=card：素材来源 auto|user", required=False, enum=["auto", "user"]),
        ToolParameter("title", "string", "engine=card：标题", required=False),
        ToolParameter("subtitle", "string", "engine=card：副标题", required=False),
        ToolParameter("scenes", "array", "engine=card：场景列表", required=False),
        ToolParameter("image_style", "string", "engine=card(asset_source=auto)：AI配图风格", required=False),
        ToolParameter("style", "object", "engine=card：视觉样式覆盖", required=False),
        ToolParameter("keep_audio", "boolean", "engine=card(material_type=video)：保留音轨", required=False, default=False),
        ToolParameter("title_height", "integer", "engine=card：标题区高度(px)", required=False),
        ToolParameter("image_height", "integer", "engine=card：图片卡片高度(px)", required=False),
        ToolParameter("media_height", "integer", "engine=card(material_type=video)：中部素材高度(px)", required=False),
        # ── cinematic ──
        ToolParameter("prompt", "string", "engine=cinematic：影视画面提示词", required=False),
        ToolParameter("duration", "integer", "engine=cinematic/pdoom：本段时长（秒）；旁白给定则按旁白时长", required=False),
        ToolParameter("resolution", "string", "engine=cinematic：分辨率，默认 768P", required=False),
        # ── pdoom ──
        ToolParameter("html_path", "string", "engine=pdoom：水彩章节 HTML 路径（含 ?core=章节脚本）", required=False),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None, **kwargs):
        super().__init__(cwd)
        self.skill_manager = skill_manager

    def execute(
        self,
        output_path: str,
        engine: str,
        narration: str = None,
        speaker: str = DEFAULT_SPEAKER,
        project: str = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        brief: str = None,
        n_scenes: int = None,
        style_prompt: str = None,
        assets_dir: str = None,
        material_type: str = "image",
        asset_source: str = "user",
        title: str = None,
        subtitle: str = "",
        scenes: list = None,
        image_style: str = None,
        style: dict = None,
        keep_audio: bool = False,
        prompt: str = None,
        duration: int = None,
        resolution: str = "768P",
        html_path: str = None,
        title_height: int = None,
        image_height: int = None,
        media_height: int = None,
        **kwargs,
    ) -> ToolResult:
        if not self.skill_manager:
            return ToolResult.fail("video_shot 需要 skill_manager 上下文")

        engine = (engine or "").lower()
        audio_path = None
        words = []
        audio_duration = None

        # ── 0. 旁白（可选） ──
        if narration and narration.strip():
            self._emit_progress("正在生成旁白...")
            mp3 = self._alias_path(output_path, ".mp3")
            res = self.skill_manager.dispatch(
                "doubao_tts", text=narration.strip(),
                output_path=mp3, project=project or "", speaker=speaker,
            )
            if not res.success:
                return res
            audio_path = res.details.get("output_path", mp3)
            words = res.details.get("words", [])
            audio_duration = res.details.get("duration")

        # ── 1. 按 engine 路由到内部引擎 ──
        if engine == "opendesign":
            if not brief:
                return ToolResult.fail("engine=opendesign 需要 brief")
            seg_dur = duration or (int(round(audio_duration)) if audio_duration else 8)
            result = self.skill_manager.dispatch(
                "opendesign_video", brief=brief, output_path=output_path,
                project=project or "", duration_s=seg_dur,
                n_scenes=n_scenes, style_prompt=style_prompt,
                assets_dir=assets_dir, fps=fps, width=width, height=height,
            )
        elif engine == "card":
            if not title:
                return ToolResult.fail("engine=card 需要 title（或 news_content 由 auto 提炼）")
            result = self.skill_manager.dispatch(
                "video_card", output_path=output_path,
                asset_source=asset_source, material_type=material_type,
                title=title, subtitle=subtitle, scenes=scenes,
                keep_audio=keep_audio, image_style=image_style, style=style,
                width=width, height=height, fps=fps,
                title_height=title_height, image_height=image_height,
                media_height=media_height,
            )
        elif engine == "cinematic":
            if not prompt:
                return ToolResult.fail("engine=cinematic 需要 prompt")
            snap = duration or (int(round(audio_duration)) if audio_duration else 10)
            result = self.skill_manager.dispatch(
                "video_cinematic_generate", prompt=prompt,
                output_path=output_path, duration=snap, resolution=resolution,
            )
        elif engine == "pdoom":
            if not html_path:
                return ToolResult.fail(
                    "engine=pdoom（水彩）需要 html_path（含 ?core=环节脚本）。"
                    "请先通过动画环节流程准备环节脚本再指定其路径。"
                )
            pdoom_dur = duration or (int(round(audio_duration)) if audio_duration else 8)
            result = self.skill_manager.dispatch(
                "pdoom_render", output_path=output_path, html_path=html_path,
                duration=pdoom_dur, fps=fps, width=width, height=height, mode="full",
            )
        else:
            return ToolResult.fail(f"未知 engine: {engine}（可选 opendesign|card|cinematic|pdoom）")

        if not result.success:
            return result

        video = result.details.get("output_path", output_path)
        info = [f"本段视频生成完成: {video}", f"引擎: {engine}"]

        return ToolResult.ok(
            "\n".join(info),
            engine=engine,
            video=video,
            audio=audio_path or "",
            words=words,
            narration_duration=audio_duration,
            scene_count=result.details.get("scene_count", result.details.get("n_scenes")),
            resolution=result.details.get("resolution"),
        )

    def _alias_path(self, video_path: str, suffix: str) -> str:
        """把 video 输出路径换成同目录同名的另一后缀文件（用于旁白 mp3）。"""
        from pathlib import Path
        p = Path(self._resolve_path(video_path))
        return str(p.with_suffix(suffix))


__all__ = ["VideoShotTool"]