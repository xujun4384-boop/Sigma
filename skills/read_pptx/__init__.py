"""
read_pptx skill - PPTX 文件内容读取

内部工具，仅供子 Agent 使用，不对外暴露给 LLM。
基于 python-pptx 提取幻灯片文本内容。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ReadPptxTool(BaseTool):
    name = "read_pptx"
    description = "读取 .pptx 文件的文本内容（内部工具）"
    parameters = [
        ToolParameter("file_path", "string", "文件路径", required=True),
        ToolParameter("offset", "integer", "起始幻灯片索引（0-based）", required=False, default=0),
        ToolParameter("limit", "integer", "最大幻灯片数量", required=False, default=0),
    ]

    def execute(self, file_path: str, offset: int = 0, limit: int = 0, **kwargs) -> ToolResult:
        resolved = self._resolve_path(file_path)
        if not resolved.exists():
            return ToolResult.fail(f"文件不存在: {file_path}")
        if resolved.suffix.lower() not in (".pptx", ".ppt"):
            return ToolResult.fail(f"不支持的文件类型: {resolved.suffix}")

        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
        except ImportError:
            return ToolResult.fail("缺少 python-pptx 库，请运行 pip install python-pptx")

        try:
            prs = Presentation(str(resolved))
            total_slides = len(prs.slides)

            if total_slides == 0:
                return ToolResult.ok("(文档无幻灯片)")

            if limit <= 0:
                limit = total_slides - offset
            end = min(offset + limit, total_slides)
            slides_to_read = list(prs.slides)[offset:end]

            lines = [f"[文件] {resolved.name}  (幻灯片 {offset + 1}-{end} / 共 {total_slides} 张)\n"]

            for i, slide in enumerate(slides_to_read):
                slide_num = offset + i + 1
                lines.append(f"--- Slide {slide_num} ---")

                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text = para.text.strip()
                            if text:
                                lines.append(text)
                    if shape.has_table:
                        table = shape.table
                        for row in table.rows:
                            cells = [cell.text.strip() for cell in row.cells]
                            lines.append(" | ".join(cells))

                lines.append("")

            result = "\n".join(lines)

            if end < total_slides:
                result += f"\n[TRUNCATED] 仅显示第 {offset + 1}-{end} 张，共 {total_slides} 张。如需继续，请用 offset={end}。"

            return ToolResult.ok(result)
        except Exception as e:
            return ToolResult.fail(f"读取 PPTX 失败: {e}")
