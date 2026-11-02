"""title_overlay skill - 标题/蒙版包装（内部能力，由导演按需调度）

在"底片"（如影视级空镜、开场段）上叠加「渐显蒙版 + 封面式大标题入场」，让画面更饱满、更有设计感：
  - **前半段保留原画**（默认前 50% 不做任何叠加），后半段蒙版渐显、标题以左对齐大字入场。
  - 不改变底片内容，只在上层叠加；产物仍是普通 mp4（compose 照旧归一化拼接）。
  - 纯确定性渲染（无随机/无外部请求）。
  - **不写死**：本工具只是"可选能力"，是否使用由导演按蓝图的可选字段 `overlay` 决定。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class TitleOverlayTool(BaseTool):
    name = "title_overlay"
    description = (
        "标题/蒙版包装：底片前半段保留原画，后半段渐显蒙版并叠加封面式大标题入场动画，输出同规格 mp4。"
        "供导演在需要时给某段（尤其影视级空镜 / 开场引导）增加设计感；不改底片内容。"
    )
    parameters = [
        ToolParameter("input_video", "string", "底片视频路径"),
        ToolParameter("output_path", "string", "输出 mp4 路径"),
        ToolParameter("title", "string", "标题文字"),
        ToolParameter("subtitle", "string", "副标题（可空）", required=False),
        ToolParameter("accent", "string", "强调色（十六进制，如 #e03131）；缺省白色", required=False, default="#ffffff"),
        ToolParameter("position", "string", "标题纵向位置: upper / top / center / bottom（默认 upper，即左上偏中）", required=False, default="upper"),
        ToolParameter("reveal_ratio", "number", "蒙版与标题开始出现的时间点，占总时长比例（默认 0.5，即前 50% 保留原画）", required=False),
        ToolParameter("align", "string", "文字对齐: left / center（默认 left）", required=False),
        ToolParameter("fps", "integer", "帧率；留空用底片帧率", required=False),
    ]

    def __init__(self, cwd: str = ".", **kwargs):
        super().__init__(cwd)

    def execute(self, input_video: str, output_path: str, title: str,
                subtitle: str = "", accent: str = "#ffffff",
                position: str = "upper", fps: int = 0,
                reveal_ratio=None, align: str | None = None, **kwargs) -> ToolResult:
        src = self._resolve_path(input_video)
        if not Path(src).exists():
            return ToolResult.fail(f"底片不存在: {input_video}")
        out = Path(output_path)
        if not out.is_absolute():
            out = Path(self.cwd) / out
        try:
            from .scripts.render import render_title_overlay
        except Exception as e:
            return ToolResult.fail(f"缺少依赖（moviepy / pillow）: {e}")

        reveal = None
        if reveal_ratio not in (None, ""):
            try:
                reveal = float(reveal_ratio)
            except (TypeError, ValueError):
                return ToolResult.fail(f"reveal_ratio 需为 0~1 的小数，收到: {reveal_ratio}")

        self._emit_progress(f"叠加 渐显蒙版+标题 包装（{position or 'upper'}/{align or 'left'}）...")
        try:
            res = render_title_overlay(
                str(src), str(out), title=title, subtitle=subtitle or "",
                accent=accent or "#ffffff", position=position or "upper", fps=int(fps or 0),
                reveal_ratio=reveal, align=align,
            )
        except Exception as e:
            return ToolResult.fail(f"标题包装渲染失败: {e}")

        return ToolResult.ok(
            f"标题包装完成: {res['output_path']}（{res['duration']}s, {res['resolution']}）",
            output_path=res["output_path"],
            duration=res["duration"],
            resolution=res["resolution"],
            reveal_ratio=res["reveal_ratio"],
        )


__all__ = ["TitleOverlayTool"]

