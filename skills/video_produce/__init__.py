"""
video_produce skill - 视频制作流水线

把「脚本设计 → 确认 → 制作」整条流程收拢进一个工具，由 design LLM 内部完成：
  Stage 0 脚本设计 → (ask_user 确认) → Stage 1-5 自动执行

流程顺序由代码写死（有 1 才有 2），每个 stage 失败重试 6 次，超过熔断。
主 LLM 只负责传需求 + ask_user 确认，脚本/分镜/时长/图片全部由 skill 内部（design LLM）决定。
"""
import json
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from skills.doubao_tts.voices import resolve_voice
from cancellation import ToolCancelledError

MAX_RETRY = 6


class VideoProduceTool(BaseTool):
    name = "video_produce"
    description = (
        "视频制作流水线。接收用户需求描述，内部由 design LLM 设计脚本（分镜+旁白+风格），"
        "脚本设计完成后返回给主 LLM 供用户确认，确认后再次调用即可自动跑完："
        "旁白 → 画面规划 → 配图 → 画面生成 → 合成，产出带旁白+字幕的最终 mp4。"
        "流程顺序固定、每步失败自动重试 6 次。"
    )
    parameters = [
        ToolParameter("brief", "string", "用户需求描述（原始需求，脚本由 design LLM 在流水线内设计）"),
        ToolParameter("output_path", "string", "最终输出 mp4 路径"),
        ToolParameter("script", "string", "确认后的脚本 JSON（二次调用时传入，跳过脚本设计直接制作）", required=False),
        ToolParameter("project", "string", "项目名，用于组织输出目录", required=False),
        ToolParameter("speaker", "string", "旁白音色ID。留空则使用用户在 Settings 中配置的音色。", required=False),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None,
                 llm_config: dict = None, default_speaker: str = "", **kwargs):
        super().__init__(cwd)
        self.skill_manager = skill_manager
        self.llm_config = llm_config or {}
        # Settings 中配置的旁白音色；留空则回落内置默认
        self.default_speaker = (default_speaker or "").strip()

    def execute(
        self,
        brief: str,
        output_path: str,
        script: str = None,
        project: str = None,
        speaker: str = None,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        **kwargs,
    ) -> ToolResult:
        from .scripts.pipeline import PipelineAbortError, run_pipeline

        if not brief:
            return ToolResult.fail("brief 不能为空（需要用户需求描述）")

        if not self.skill_manager:
            return ToolResult.fail("video_produce 需要 skill_manager 上下文")

        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 音色优先级：调用方显式传入 > Settings 配置 > 内置默认
        speaker = resolve_voice(speaker, self.default_speaker)

        def progress(msg: str):
            self._emit_progress(msg)

        try:
            result = run_pipeline(
                brief=brief,
                script=script,
                output_path=str(out),
                project=project or "",
                speaker=speaker,
                skill_manager=self.skill_manager,
                llm_config=self.llm_config,
                fps=fps, width=width, height=height,
                progress=progress,
            )
        except ToolCancelledError:
            return ToolResult.fail("已取消：视频制作流水线被用户停止。")
        except PipelineAbortError as e:
            return ToolResult.fail(
                f"视频制作流水线在「{e.stage}」阶段重试 {MAX_RETRY} 次仍失败，已熔断停止。\n"
                f"错误：{e.error}\n\n"
                f"已完成阶段产物保留在项目目录，可修正后从断点继续。"
            )
        except Exception as e:
            return ToolResult.fail(f"视频制作流水线失败: {e}")

        # 脚本设计完成，等用户确认
        if result.get("need_confirm"):
            script_json = json.dumps(result["script"], ensure_ascii=False, indent=2)
            return ToolResult.ok(
                f"脚本已设计完成，请向用户确认（可修改）后再调用本工具继续制作。\n\n"
                f"脚本：\n{script_json}",
                need_confirm=True,
                script=result["script"],
            )

        artifacts = result.get("artifacts", {})
        final_video = artifacts.get("final_video") or str(out)
        subtitle_file = artifacts.get("subtitle_file", "")
        parts_root = artifacts.get("parts_root", "")

        msg = [
            f"视频制作完成: {final_video}",
            f"总时长: {result['duration']} 秒",
        ]
        if parts_root and Path(parts_root).exists():
            seg_dirs = sorted(
                (p for p in Path(parts_root).glob("seg_*") if p.is_dir()),
                key=lambda p: int(p.name.split("_")[-1]),
            )
            if seg_dirs:
                msg.append("分段产物（每段独立文件夹，可单段替换/检查）:")
                for d in seg_dirs:
                    files = " / ".join(f.name for f in sorted(d.iterdir()) if f.is_file())
                    msg.append(f"  {d.name}: {files}")
            else:
                msg.append(f"中间产物目录: {parts_root}")
        if subtitle_file and Path(subtitle_file).exists():
            msg.append(f"字幕文件(SRT): {subtitle_file}")

        out_p = Path(final_video)
        size_mb = out_p.stat().st_size / 1024 / 1024 if out_p.exists() else 0
        return ToolResult.ok(
            "\n".join(msg),
            output_path=final_video,
            subtitle_file=subtitle_file if Path(subtitle_file).exists() else "",
            parts_root=parts_root,
            duration=result.get("duration", 0),
            size_mb=round(size_mb, 1),
        )


__all__ = ["VideoProduceTool"]
