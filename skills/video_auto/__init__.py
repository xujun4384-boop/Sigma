"""
video_auto skill - 新闻解说短视频一键生成

提供 video_auto 工具，接收新闻原文后自动完成:
  1. 脚本提炼（LLM 提取标题/副标题/分镜）
  2. 场景配图（AI 生成）
  3. 竖版视频合成（打字机字幕 + 场景切换动效）

断点续传：
  - 在 work_dir 下保存 state.json，记录各阶段进度
  - 重试时自动从断点继续，不重复解析脚本、不重复生成已有图片
"""
import json
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE_STYLE = "现代科技新闻插画风格，高清，适合竖屏视频背景"

# 阶段常量
STAGE_INIT = "init"            # 未开始
STAGE_PARSED = "parsed"        # 脚本已提炼
STAGE_IMAGES_READY = "images_ready"  # 配图已完成
STAGE_RENDERED = "rendered"    # 视频已生成


def _get_work_dir(output_path: str) -> Path:
    """根据 output_path 计算项目工作目录。"""
    out = Path(output_path)
    safe_name = "".join(
        c if c.isalnum() or c in "._-" else "_" for c in out.stem
    )[:50] or "video"
    return out.parent / "video_work" / safe_name


def _load_state(work_dir: Path) -> dict | None:
    """加载断点状态。"""
    state_file = work_dir / "state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def _save_state(work_dir: Path, state: dict):
    """保存断点状态。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    state_file = work_dir / "state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")





class VideoAutoTool(BaseTool):
    name = "video_auto"
    description = (
        "新闻类竖版（9:16）无声短视频一键生成。接收新闻原文后自动提炼标题和分镜文案，"
        "自动配图（AI生成），合成带标题卡片+图片+打字机字幕+场景动效的无声MP4（纯视觉，无旁白无BGM）。"
        "支持断点续传：超时后再次调用相同 output_path 可自动从失败阶段继续，不会重复解析或生成图片。"
        "这是做新闻/资讯竖版卡片视频的最简路径，无需手写HTML Canvas动画。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 MP4 文件路径（绝对路径或相对路径）"),
        ToolParameter("news_content", "string", "新闻原文或内容，提供后自动提炼标题和分镜", required=False),
        ToolParameter("title", "string", "大标题（若提供 news_content 可留空自动提炼）", required=False),
        ToolParameter("subtitle", "string", "副标题", required=False),
        ToolParameter("scenes", "array", "场景列表 [{\"text\":\"文案\",\"duration\":5}]，提供 news_content 时自动生成", required=False),
        ToolParameter("image_source", "string", "图片来源策略（保留参数，当前统一使用 AI 生成）", required=False, default="auto"),
        ToolParameter("image_style", "string", "AI生成图片风格前缀", required=False, default=DEFAULT_IMAGE_STYLE),
        ToolParameter("width", "integer", "视频宽度，默认 1080", required=False, default=1080),
        ToolParameter("height", "integer", "视频高度，默认 1920（竖版 9:16）", required=False, default=1920),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
        ToolParameter("title_height", "integer", "标题区域高度（px），默认 560", required=False, default=560),
        ToolParameter("image_height", "integer", "图片卡片高度（px），默认 640", required=False, default=640),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 skill_manager = None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.skill_manager = skill_manager

    def execute(
        self,
        output_path: str,
        news_content: str = None,
        title: str = None,
        subtitle: str = None,
        scenes: list = None,
        image_source: str = "auto",
        image_style: str = DEFAULT_IMAGE_STYLE,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        title_height: int = 560,
        image_height: int = 640,
        **kwargs,
    ) -> ToolResult:

        # ── 0. 解析路径 & 加载断点状态 ──
        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        work_dir = _get_work_dir(str(out))
        state = _load_state(work_dir)
        resumed_from = None
        stage = STAGE_INIT
        image_paths = []

        self._emit_progress(f"开始生成视频: {out.name}")

        # 如果目标文件已存在，直接返回
        if out.exists() and out.stat().st_size > 1024:
            size_mb = out.stat().st_size / 1024 / 1024
            return ToolResult.ok(
                f"视频已存在，无需重新生成: {out.name}\n"
                f"文件大小: {round(size_mb, 1)} MB",
                output_path=str(out.resolve()),
                stage=STAGE_RENDERED,
                resumed_from=STAGE_RENDERED,
                size_mb=round(size_mb, 1),
            )

        # ── 1. 脚本获取（优先断点恢复 → LLM 解析 → 手动参数）──
        if state and state.get("stage") in (STAGE_PARSED, STAGE_IMAGES_READY):
            # 断点恢复：直接使用已保存的脚本
            title = state.get("title", title or "")
            subtitle = state.get("subtitle", subtitle or "")
            state_scenes = state.get("scenes", [])
            if state_scenes:
                scenes = state_scenes
            image_paths = state.get("image_paths", [])
            stage = state.get("stage", STAGE_PARSED)
            resumed_from = stage
        elif news_content and news_content.strip():
            # 新闻内容 → LLM 解析
            self._emit_progress("正在提炼新闻脚本...")
            try:
                from .scripts.news_parser import call_llm_parse_news

                llm_base_url = self.llm_config.get("base_url", "")
                llm_api_key = self.llm_config.get("api_key", "")
                llm_model = self.llm_config.get("model", "")

                if not llm_base_url or not llm_api_key or not llm_model:
                    return ToolResult.fail(
                        "LLM 配置不完整，无法进行脚本提炼。"
                        "请确保已配置 LLM API (base_url, api_key, model)。"
                        "或手动提供 title、subtitle、scenes 参数。"
                    )

                script = call_llm_parse_news(
                    news_content=news_content.strip(),
                    base_url=llm_base_url,
                    api_key=llm_api_key,
                    model=llm_model,
                )

                title = script.get("title", title or "")
                subtitle = script.get("subtitle", subtitle or "")
                scenes = script.get("scenes", scenes or [])
                stage = STAGE_PARSED

            except Exception as e:
                return ToolResult.fail(f"脚本提炼失败: {e}")

        # ── 2. 参数校验 ──
        if not title:
            return ToolResult.fail("缺少标题 (title)。请提供 news_content 自动提炼 或 手动指定 title。")
        if not scenes:
            return ToolResult.fail("缺少场景列表 (scenes)。请提供 news_content 自动生成 或 手动指定 scenes。")

        # 标准化 scenes
        parsed_scenes = []
        for s in (scenes or []):
            if isinstance(s, dict):
                parsed_scenes.append({
                    "text": str(s.get("text", "")),
                    "duration": float(s.get("duration", 5)),
                    "transition": s.get("transition", "none"),
                    "image": s.get("image", ""),
                })
            elif isinstance(s, str):
                parsed_scenes.append({"text": s, "duration": 4, "transition": "none", "image": ""})
        scenes = parsed_scenes

        if not scenes:
            return ToolResult.fail("scenes 解析后为空，请检查输入格式")

        # 保存脚本阶段状态
        if stage == STAGE_PARSED and resumed_from is None:
            _save_state(work_dir, {
                "stage": STAGE_PARSED,
                "title": title,
                "subtitle": subtitle,
                "scenes": [{"text": s["text"], "duration": s["duration"], "transition": s["transition"]} for s in scenes],
                "image_paths": [],
                "output_path": str(out),
            })

        # ── 3. 场景配图（断点恢复 > 池匹配 > 搜索/生成）──
        if resumed_from == STAGE_IMAGES_READY and image_paths:
            # 断点恢复：验证已有路径是否仍有效
            valid_count = sum(1 for p in image_paths if p and Path(p).exists())
            if valid_count >= len(scenes):
                for i, scene in enumerate(scenes):
                    if i < len(image_paths) and image_paths[i]:
                        scene["image"] = image_paths[i]
                stage = STAGE_IMAGES_READY
            else:
                image_paths = []  # 部分丢失，走完整配图流程
        elif all(s.get("image") for s in scenes if Path(s.get("image", "")).exists()):
            # scene 自带有效 image 路径
            image_paths = [s.get("image", "") for s in scenes]
            stage = STAGE_IMAGES_READY

        if stage != STAGE_IMAGES_READY:
            # 调用 image_provider（内部自动做池匹配 → 搜索 → 生成）
            self._emit_progress(f"正在为 {len(scenes)} 个场景配图...")
            from .scripts.image_provider import provide_images_for_scenes

            try:
                image_paths = provide_images_for_scenes(
                    scenes=scenes,
                    image_source=image_source,
                    image_style=image_style,
                    work_dir=str(out.parent),
                    project=out.stem,
                    skill_manager=self.skill_manager,
                )
            except Exception as e:
                # 配图失败但脚本已保存，提示可重试
                _save_state(work_dir, {
                    "stage": STAGE_PARSED,
                    "title": title,
                    "subtitle": subtitle,
                    "scenes": [{"text": s["text"], "duration": s["duration"], "transition": s["transition"]} for s in scenes],
                    "image_paths": [],
                    "output_path": str(out),
                })
                return ToolResult.fail(
                    f"场景配图失败: {e}\n"
                    f"脚本已保存，重试时将跳过解析直接继续配图。"
                )

            # 将图片路径注入 scenes
            for i, scene in enumerate(scenes):
                if i < len(image_paths) and image_paths[i]:
                    scene["image"] = image_paths[i]
                elif not scene.get("image"):
                    scene["image"] = ""

            stage = STAGE_IMAGES_READY
            # 保存配图阶段状态
            _save_state(work_dir, {
                "stage": STAGE_IMAGES_READY,
                "title": title,
                "subtitle": subtitle,
                "scenes": [{"text": s["text"], "duration": s["duration"], "transition": s["transition"]} for s in scenes],
                "image_paths": image_paths,
                "output_path": str(out),
            })

        # ── 4. 视频渲染 ──
        self._emit_progress("正在渲染视频...")
        from .scripts.video_short import render_news_video

        try:
            result_path = render_news_video(
                output_path=str(out),
                title=title or "",
                subtitle=subtitle or "",
                scenes=scenes,
                width=width,
                height=height,
                fps=fps,
                title_height=title_height,
                image_height=image_height,
            )
            stage = STAGE_RENDERED
            _save_state(work_dir, {
                "stage": STAGE_RENDERED,
                "title": title,
                "subtitle": subtitle,
                "scenes": [{"text": s["text"], "duration": s["duration"], "transition": s["transition"]} for s in scenes],
                "image_paths": image_paths,
                "output_path": str(out),
            })
        except ImportError as e:
            return ToolResult.fail(
                f"缺少 Python 依赖，请在终端执行:\n"
                f"  pip install moviepy pillow httpx numpy\n"
                f"错误详情: {e}"
            )
        except Exception as e:
            # 渲染失败但图片已就绪，重试时跳过配图
            return ToolResult.fail(
                f"视频渲染失败: {e}\n"
                f"配图已完成（{len(image_paths)} 张），重试时将跳过解析和配图直接渲染。"
            )

        # ── 5. 返回结果 ──
        size_mb = Path(result_path).stat().st_size / 1024 / 1024 if Path(result_path).exists() else 0
        image_count = sum(1 for p in image_paths if p)

        summary_lines = [f"视频生成完成: {Path(result_path).name}"]
        if resumed_from:
            summary_lines.append(f"(从 {resumed_from} 阶段恢复，跳过已完成的步骤)")
        summary_lines += [
            f"标题: {title}",
            f"场景数: {len(scenes)}",
            f"配图: {image_count} 张",
            f"分辨率: {width}x{height}",
            f"文件大小: {round(size_mb, 1)} MB",
        ]

        return ToolResult.ok(
            "\n".join(summary_lines),
            output_path=str(Path(result_path).resolve()),
            title=title,
            subtitle=subtitle,
            scene_count=len(scenes),
            image_count=image_count,
            resolution=f"{width}x{height}",
            size_mb=round(size_mb, 1),
            stage=stage,
            resumed_from=resumed_from,
            scenes=scenes,
        )


__all__ = ["VideoAutoTool"]
