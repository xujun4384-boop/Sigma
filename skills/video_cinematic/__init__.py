"""
video_cinematic skill - 电影级 AI 视频生成

提供两个工具:
  video_cinematic_storyboard - 分镜脚本设计（LLM 拆解用户意图为电影分镜）
  video_cinematic_generate   - 电影级视频生成（按 Settings 选择的服务商提交文生视频任务）

服务商（由用户在 Settings → Skill Keys → 影视级视频生成 中选择）:
  - minimax：MiniMax-Hailuo-2.3（默认）
  - ark：火山方舟 / 豆包 Seedance 系列

核心特性:
  - 纯提示词驱动，生成后不可修改
  - 每次生成消耗一次视频额度（按套餐用量扣减，具体以控制台为准）
  - 支持 [运镜指令] 语法实现精确镜头控制
"""
import json
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent


def _get_work_dir(output_path: str) -> Path:
    """根据 output_path 计算项目工作目录。"""
    out = Path(output_path)
    safe_name = "".join(
        c if c.isalnum() or c in "._-" else "_" for c in out.stem
    )[:50] or "cinematic"
    return out.parent / "video_work" / "cinematic" / safe_name


# ═══════════════════════════════════════════════════
# video_cinematic_storyboard - 分镜脚本设计
# ═══════════════════════════════════════════════════

class VideoCinematicStoryboardTool(BaseTool):
    name = "video_cinematic_storyboard"
    description = (
        "电影分镜脚本设计。将用户的视频意图拆解为专业电影分镜，"
        "包含每镜的详细提示词（英文）、镜头运动、光影氛围、时长等。"
        "这是 video_cinematic_generate 的前置步骤，用于确保生成质量。"
    )
    parameters = [
        ToolParameter("user_intent", "string", "用户想要视频的文字描述"),
        ToolParameter("total_duration", "integer", "目标总时长（秒），默认 30（3 个 10s 分镜，按实际需要调整）", required=False, default=30),
        ToolParameter("style", "string", "视觉风格参考，默认 cinematic", required=False, default="cinematic"),
        ToolParameter("scene_count", "integer", "分镜数量，不提供则自动计算", required=False),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    def execute(
        self,
        user_intent: str,
        total_duration: int = 30,
        style: str = "cinematic",
        scene_count: int = None,
        **kwargs,
    ) -> ToolResult:
        from .scripts.storyboard_designer import call_llm_design_storyboard

        llm_base_url = self.llm_config.get("base_url", "")
        llm_api_key = self.llm_config.get("api_key", "")
        llm_model = self.llm_config.get("model", "")
        llm_protocol = self.llm_config.get("protocol", "anthropic")

        if not llm_base_url or not llm_api_key or not llm_model:
            return ToolResult.fail(
                "LLM 配置不完整，无法进行分镜设计。"
                "请确保已配置 LLM API (base_url, api_key, model)。"
            )

        self._emit_progress(f"正在设计电影分镜: {user_intent[:50]}...")

        try:
            storyboard = call_llm_design_storyboard(
                user_intent=user_intent,
                total_duration=total_duration,
                style=style,
                scene_count=scene_count,
                base_url=llm_base_url,
                api_key=llm_api_key,
                model=llm_model,
                protocol=llm_protocol,
            )
        except Exception as e:
            return ToolResult.fail(f"分镜设计失败: {e}")

        # 构建用户友好的摘要
        scenes = storyboard.get("scenes", [])
        summary_lines = [
            f"分镜设计完成: {storyboard.get('title', '未命名')}",
            f"剧情概括: {storyboard.get('logline', '无')}",
            f"总时长: {storyboard.get('total_duration', 0)} 秒",
            f"分镜数: {len(scenes)} 个",
            f"风格说明: {storyboard.get('style_notes', '无')}",
            "",
            "分镜详情:",
        ]
        for s in scenes:
            summary_lines.append(
                f"  [{s['scene_id']}] {s['duration']}s | {s['camera']} | {s['mood']}"
            )
            summary_lines.append(f"      {s['prompt_zh']}")

        return ToolResult.ok(
            "\n".join(summary_lines),
            storyboard=storyboard,
            title=storyboard.get("title", ""),
            logline=storyboard.get("logline", ""),
            scene_count=len(scenes),
            total_duration=storyboard.get("total_duration", 0),
            scenes=scenes,
            style_notes=storyboard.get("style_notes", ""),
        )


# ═══════════════════════════════════════════════════
# video_cinematic_generate - 电影级视频生成
# ═══════════════════════════════════════════════════

class VideoCinematicGenerateTool(BaseTool):
    name = "video_cinematic_generate"
    description = (
        "电影级 AI 视频生成。按 Settings 中选择的服务商（MiniMax-Hailuo-2.3 或 火山方舟 Seedance）"
        "通过纯文本提示词生成具有电影感画面的高质量视频。\n"
        "⚠️ 重要：生成后不可修改，任务一旦提交即消耗配额。\n"
        "建议先使用 video_cinematic_storyboard 设计分镜，再逐镜调用本工具。"
    )
    parameters = [
        ToolParameter("prompt", "string", "视频生成提示词（建议英文，支持 [运镜指令] 语法）"),
        ToolParameter("output_path", "string", "输出 MP4 文件路径"),
        ToolParameter("duration", "integer", "视频时长（秒），6 或 10，默认 10（推荐用满赠送额度）", required=False, default=10),
        ToolParameter("resolution", "string", "分辨率：768P / 1080P，默认 768P（768P 支持 10s；1080P 仅 6s）", required=False, default="768P"),
        ToolParameter("prompt_optimizer", "boolean", "是否自动优化 prompt，默认 true", required=False, default=True),
        ToolParameter("fast_pretreatment", "boolean", "是否缩短 prompt 优化耗时，默认 false", required=False, default=False),
        ToolParameter("poll_interval", "integer", "轮询间隔（秒），默认 10", required=False, default=10),
        ToolParameter("max_wait", "integer", "最大等待时间（秒），默认 1800", required=False, default=1800),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 minimax_video_api_key: str = "",
                 video_provider: str = "minimax",
                 ark_video_api_key: str = "",
                 ark_video_base_url: str = "",
                 ark_video_model: str = "",
                 **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.minimax_video_api_key = minimax_video_api_key
        # 服务商由 Settings 决定（minimax | ark），默认沿用历史上的 MiniMax
        self.video_provider = (video_provider or "minimax").strip().lower()
        self.ark_video_api_key = ark_video_api_key
        self.ark_video_base_url = ark_video_base_url
        self.ark_video_model = ark_video_model

    def execute(
        self,
        prompt: str,
        output_path: str,
        duration: int = 10,
        resolution: str = "768P",
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        poll_interval: int = 10,
        max_wait: int = 1800,
        **kwargs,
    ) -> ToolResult:
        import os

        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 检查是否已存在
        if out.exists() and out.stat().st_size > 1024:
            size_mb = out.stat().st_size / 1024 / 1024
            return ToolResult.ok(
                f"视频已存在，无需重新生成: {out.name}\n"
                f"文件大小: {round(size_mb, 1)} MB",
                output_path=str(out.resolve()),
                status="exists",
                size_mb=round(size_mb, 1),
            )

        self._emit_progress(
            f"正在提交视频生成任务 ({self.video_provider}, {duration}s, {resolution})...")

        def _progress(status, elapsed):
            self._emit_progress(f"任务状态: {status} (已等待 {elapsed}s)")

        try:
            if self.video_provider == "ark":
                ark_key = self.ark_video_api_key or os.environ.get("ARK_API_KEY", "")
                if not ark_key:
                    return ToolResult.fail(
                        "火山方舟 API Key 未配置。\n"
                        "请在 Settings → Skill Keys → 影视级视频生成 中选择「火山方舟 Seedance」并填写 ARK API Key。")
                from .scripts.ark_video_client import generate_cinematic_video as gen_ark
                result = gen_ark(
                    prompt=prompt,
                    output_path=str(out),
                    api_key=ark_key,
                    duration=duration,
                    resolution=resolution,
                    base_url=self.ark_video_base_url,
                    model=self.ark_video_model,
                    poll_interval=poll_interval,
                    max_wait=max_wait,
                    progress_callback=_progress,
                )
            else:
                # 获取 MiniMax API Key（优先级：构造参数 > 环境变量 > llm_config）
                minimax_api_key = self.minimax_video_api_key
                if not minimax_api_key:
                    minimax_api_key = os.environ.get("MINIMAX_API_KEY", "")
                if not minimax_api_key:
                    minimax_api_key = self.llm_config.get("minimax_api_key", "")
                if not minimax_api_key:
                    return ToolResult.fail(
                        "MiniMax API Key 未配置。\n"
                        "请在 Settings → Skill Keys → 影视级视频生成 中填写，或设置环境变量 MINIMAX_API_KEY。\n"
                        "Token Plan 订阅 Key 和按量计费 API Key 均可用于 Hailuo-2.3。")
                from .scripts.hailuo_client import generate_cinematic_video as gen_hailuo
                result = gen_hailuo(
                    prompt=prompt,
                    output_path=str(out),
                    api_key=minimax_api_key,
                    duration=duration,
                    resolution=resolution,
                    prompt_optimizer=prompt_optimizer,
                    fast_pretreatment=fast_pretreatment,
                    poll_interval=poll_interval,
                    max_wait=max_wait,
                    progress_callback=_progress,
                )
        except Exception as e:
            return ToolResult.fail(f"视频生成失败: {e}")

        # 计算文件大小
        size_mb = 0
        if Path(result["output_path"]).exists():
            size_mb = Path(result["output_path"]).stat().st_size / 1024 / 1024

        return ToolResult.ok(
            f"电影级视频生成完成（{self.video_provider}）: {Path(result['output_path']).name}\n"
            f"任务 ID: {result['task_id']}\n"
            f"时长: {result['duration']} 秒\n"
            f"分辨率: {result['resolution']} ({result.get('video_width', 0)}x{result.get('video_height', 0)})\n"
            f"文件大小: {round(size_mb, 1)} MB",
            output_path=result["output_path"],
            task_id=result["task_id"],
            status=result["status"],
            video_url=result.get("video_url", ""),
            duration=result["duration"],
            resolution=result["resolution"],
            video_width=result.get("video_width", 0),
            video_height=result.get("video_height", 0),
            size_mb=round(size_mb, 1),
        )


__all__ = ["VideoCinematicStoryboardTool", "VideoCinematicGenerateTool"]
