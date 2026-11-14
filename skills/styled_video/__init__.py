# -*- coding: utf-8 -*-
"""styled_video —— 导演组内部引擎：单段风格动画（Remotion 版）。

不是给用户直接选的入口：导演组在蓝图里给某个 panel 指定 engine="styled"，
并写一份按用户需求生成的 styleGuide，再由本工具渲成一段无声 mp4。
旁白、字幕、合成仍由导演组后续处理。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

from .scripts.pipeline import run


class StyledVideoTool(BaseTool):
    name = "styled_video"
    description = (
        "风格动画单段渲染（内部工具，由 director 调度）：按导演写的 styleGuide 现场作画，"
        "确定性渲染成无声 mp4。风格不来自固定枚举，由这一段的内容与用户要求决定。"
        "不负责旁白/字幕/合成；不要让用户直接选风格。"
    )
    parameters = [
        ToolParameter("brief", "string", "这一段要讲什么/画面需求"),
        ToolParameter("style_guide", "string",
                      "风格档案：配色/线条/质感/光/构图/运动/禁止项，以及人物怎么用。"
                      "由导演按用户需求写，同片各 styled 段共用同一份。", required=False, default=""),
        ToolParameter("style_note", "string",
                      "本段局部风格要求（例如「这一段更冷、更暗」），可空", required=False, default=""),
        ToolParameter("duration", "number", "时长（秒）"),
        ToolParameter("output_path", "string", "输出 mp4 路径"),
        ToolParameter("project", "string", "项目名（中间产物放 video_work/<project>/styled/）",
                      required=False),
        ToolParameter("width", "integer", "画布宽", required=False, default=1920),
        ToolParameter("height", "integer", "画布高", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("character", "string",
                      "已确认的定妆参数路径（video_work/<project>/character.json）；"
                      "这一段有人物时传入，画面里的人物必须来自它。", required=False, default=""),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 skill_manager=None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.skill_manager = skill_manager

    def execute(self, brief: str, duration: float, output_path: str,
                style_guide: str = "", style_note: str = "", character: str = "",
                project: str = "", width: int = 1920, height: int = 1080,
                fps: int = 30, **kw) -> ToolResult:
        if not self.llm_config:
            return ToolResult.fail("styled_video 需要主 LLM 配置（由导演组注入）")
        out = self._resolve_path(output_path)
        proj = project or "styled_panel"
        work = Path(self.cwd) / "video_work" / proj / "styled"
        char = ""
        if str(character or "").strip():
            p = self._resolve_path(character)
            char = str(p) if p.exists() else ""
        ok, note, path = run(
            brief=brief, duration=duration, output_path=str(out), work_dir=str(work),
            width=width, height=height, fps=fps,
            style_guide=style_guide, style_note=style_note, character=char,
            skill_manager=self.skill_manager,
            llm_cfg=self.llm_config, progress=self._emit_progress)
        if not ok:
            return ToolResult.fail(f"styled_video 失败：{note}")
        return ToolResult.ok(
            f"风格动画完成：{path}｜{float(duration):.1f}s"
            + (f"｜人物来自定妆" if char else ""),
            output_path=path, duration=duration)


__all__ = ["StyledVideoTool"]
