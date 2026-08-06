"""
write_xlsx skill - 创建 Excel 文件

从零创建 .xlsx 文件，支持多工作表、数据写入、格式化、图表、公式。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class WriteXlsxTool(BaseTool):
    name = "write_xlsx"
    description = (
        "从零创建 Excel (.xlsx) 文件。支持多工作表、表头格式化、数据写入。"
        "可指定工作表名称和数据。"
    )
    parameters = [
        ToolParameter("file_path", "string", "输出文件路径（绝对路径或相对于项目根目录）"),
        ToolParameter(
            "sheets",
            "array",
            "工作表列表。每项: {name (名称), headers (表头列表, 可选), "
            "data (二维数组, 可选), merge_cells (合并区域列表, 可选, 如 'A1:C1')}",
        ),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, sheets: list, **kwargs) -> ToolResult:
        if isinstance(sheets, dict):
            sheets = [sheets]
        elif sheets and isinstance(sheets, list) and all(not isinstance(item, dict) for item in sheets):
            sheets = [{"name": "Sheet1", "data": sheets}]
        if not sheets or not isinstance(sheets, list):
            return ToolResult.fail("sheets 必须是非空列表")

        full_path = self._resolve_path(file_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            return ToolResult.fail("缺少 openpyxl 库，请执行: pip install openpyxl")

        wb = Workbook()
        results = []

        for si, sheet_info in enumerate(sheets):
            name = sheet_info.get("name", f"Sheet{si + 1}")
            if si == 0:
                ws = wb.active
                ws.title = name
            else:
                ws = wb.create_sheet(title=name)

            headers = sheet_info.get("headers", [])
            data = sheet_info.get("data", [])
            merge_list = sheet_info.get("merge_cells", [])

            # 合并单元格
            for mc in merge_list:
                try:
                    ws.merge_cells(mc)
                except Exception:
                    pass

            start_row = 1

            # 写表头
            if headers:
                for ci, h in enumerate(headers, 1):
                    cell = ws.cell(row=start_row, column=ci, value=h)
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill(start_color="4472C4", fill_type="solid")
                    cell.alignment = Alignment(horizontal="center")
                start_row += 1

            # 写数据
            for ri, row_data in enumerate(data):
                for ci, val in enumerate(row_data, 1):
                    ws.cell(row=start_row + ri, column=ci, value=val)

            # 自动调整列宽
            if headers or data:
                max_cols = len(headers) if headers else (len(data[0]) if data else 0)
                for ci in range(1, max_cols + 1):
                    max_len = 0
                    col_letter = ws.cell(row=1, column=ci).column_letter
                    for row_cells in ws.iter_rows(min_col=ci, max_col=ci, values_only=True):
                        for cell_val in row_cells:
                            if cell_val:
                                char_len = 0
                                for ch in str(cell_val):
                                    char_len += 2 if ord(ch) > 127 else 1
                                max_len = max(max_len, char_len)
                    ws.column_dimensions[col_letter].width = min(max_len + 4, 60)

            results.append({"name": name, "rows": len(data) + (1 if headers else 0)})

        try:
            wb.save(str(full_path))
        except Exception as e:
            return ToolResult.fail(f"保存失败: {e}")

        detail = "; ".join(f"{r['name']}({r['rows']}行)" for r in results)
        return ToolResult.ok(
            f"Excel 文件已创建: {detail}",
            file_path=str(full_path),
            sheets=results,
        )
