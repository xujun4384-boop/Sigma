# -*- coding: utf-8 -*-
"""styled_video —— 导演组内部引擎：单段「14 选 1」风格动画。

不是给用户直接选的入口：导演组在蓝图里给某个 panel 指定 engine="styled"
和 visualStyle（crayon/shadow/ink/...），再由本工具渲成一段无声 mp4。
旁白、字幕、合成仍由导演组后续处理。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from skills import style_lib

from .scripts.pipeline import run


class StyledVideoTool(BaseTool):
    name = "styled_video"
    description = (
        "风格动画单段渲染（内部工具，由 director 调度）：从 14 种视觉风格里选一种，"
        "确定性渲染成无声 mp4。默认 linear（2~5 个镜头硬切）；"
        "可选 grid（一张大画布分格，camera 到点跳格，每格独立播放，格内可推拉）。"
        "不负责旁白/字幕/合成；不要直接暴露给用户选风格。"
    )
    parameters = [
        ToolParameter("brief", "string", "这一段要讲什么/画面需求"),
        ToolParameter("visual_style", "string",
                      "14 种风格 id：crayon / shadow / flat / ink / pixel / comic / "
                      "whiteboard / hanzi / timeline / isometric / scale / infographic / map / exploded",
                      enum=style_lib.ids()),
        ToolParameter("duration", "number", "时长（秒）"),
        ToolParameter("output_path", "string", "输出 mp4 路径"),
        ToolParameter("project", "string", "项目名（中间产物放 video_work/<project>/styled/）",
                      required=False),
        ToolParameter("width", "integer", "画布宽", required=False, default=1920),
        ToolParameter("height", "integer", "画布高", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("shots", "integer", "linear 模式的镜头数 2~5（grid 模式忽略）",
                      required=False, default=3),
        ToolParameter("layout", "string",
                      "linear（默认，现有 2~5 切镜）| grid（大画布分格：camera 跳格，每格独立播放）",
                      required=False, default="linear", enum=["linear", "grid"]),
        ToolParameter("grid", "object",
                      "仅 layout=grid：{cols,rows,order,weights,moves}；"
                      "cols/rows 默认 2×2，order 是播放顺序，weights 是每格时长权重，"
                      "moves 是格内推拉（键为格号，如 {\"1\":{\"zoom\":1.14}}）",
                      required=False),
        ToolParameter("with_images", "boolean",
                      "是否允许引擎按需生图（默认关；导演组按面板的 images 字段显式开启）",
                      required=False, default=False),
        ToolParameter("max_images", "integer", "本段最多生成几张图（默认 3）",
                      required=False, default=3),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 skill_manager=None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.skill_manager = skill_manager

    def execute(self, brief: str, visual_style: str, duration: float, output_path: str,
                project: str = "", width: int = 1920, height: int = 1080,
                fps: int = 30, shots: int = 3, layout: str = "linear",
                grid: dict = None, with_images: bool = False, max_images: int = 3,
                **kw) -> ToolResult:
        if not self.llm_config:
            return ToolResult.fail("styled_video 需要主 LLM 配置（由导演组注入）")
        out = self._resolve_path(output_path)
        proj = project or "styled_panel"
        work = Path(self.cwd) / "video_work" / proj / "styled"
        ok, note, path = run(
            brief=brief, style_id=visual_style, duration=duration,
            output_path=str(out), work_dir=str(work),
            width=width, height=height, fps=fps, shots=shots,
            layout=layout, grid=grid,
            with_images=with_images, max_images=max_images,
            skill_manager=self.skill_manager,
            llm_cfg=self.llm_config, progress=self._emit_progress)
        if not ok:
            return ToolResult.fail(f"styled_video 失败：{note}")
        mode = "grid" if str(layout or "").lower() == "grid" else "linear"
        if mode == "grid":
            g = grid if isinstance(grid, dict) else {}
            cols = int(g.get("cols") or 2)
            rows = int(g.get("rows") or 2)
            cells = len(g.get("order") or []) or cols * rows
            label = f"{cols}×{rows} 分格（{cells} 格）"
        else:
            label = f"{shots} 镜头"
        return ToolResult.ok(
            f"风格动画完成：{path}\n风格 {visual_style}｜{label}｜{float(duration):.1f}s",
            output_path=path, style=visual_style, duration=duration,
            layout=mode, grid=grid)


__all__ = ["StyledVideoTool"]
