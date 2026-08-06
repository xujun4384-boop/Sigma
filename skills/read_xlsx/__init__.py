"""
read_xlsx skill - 读取 Excel 文件

读取 .xlsx 文件内容，列出工作表，提取数据。
支持指定工作表、读取表头、返回行列数。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ReadXlsxTool(BaseTool):
    name = "read_xlsx"
    description = (
        "读取 Excel (.xlsx) 文件内容。列出所有工作表名称，返回指定工作表的数据和结构信息。"
        "data_only=True 可读取公式计算后的值。"
    )
    parameters = [
        ToolParameter("file_path", "string", "Excel 文件路径（绝对路径或相对于项目根目录的路径）"),
        ToolParameter("sheet_name", "string", "指定读取的工作表名称（可选，不指定则读取全部工作表）", required=False),
        ToolParameter("data_only", "boolean", "是否只读取公式计算后的值（默认 True）", required=False, default=True),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, sheet_name: str = None,
                data_only: bool = True, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not os.path.exists(full_path):
            return ToolResult.fail(f"文件不存在: {file_path}")

        if not full_path.suffix.lower() in (".xlsx", ".xlsm"):
            return ToolResult.fail("仅支持 .xlsx / .xlsm 格式")

        try:
            from openpyxl import load_workbook

            wb = load_workbook(str(full_path), data_only=data_only, read_only=True)
        except ImportError:
            return ToolResult.fail("缺少 openpyxl 库，请执行: pip install openpyxl")
        except Exception as e:
            return ToolResult.fail(f"打开文件失败: {e}")

        try:
            sheet_names = list(wb.sheetnames)
            sheets_to_read = [sheet_name] if sheet_name else sheet_names
            missing = [s for s in sheets_to_read if s not in sheet_names]
            if missing:
                wb.close()
                return ToolResult.fail(f"工作表不存在: {missing}。可用: {sheet_names}")
            sheets_data = {}

            for sname in sheets_to_read:
                ws = wb[sname]
                rows = []
                for row in ws.iter_rows(values_only=True):
                    rows.append([str(c) if c is not None else "" for c in row])

                sheets_data[sname] = {
                    "row_count": len(rows),
                    "column_count": len(rows[0]) if rows else 0,
                    "data": rows,
                }

            wb.close()

            # 格式化所有工作表数据到 content
            lines = [f"读取完成：{len(sheets_data)} 个工作表\n"]
            for sname, sdata in sheets_data.items():
                lines.append(f"── 工作表: {sname} ({sdata['row_count']} 行 x {sdata['column_count']} 列) ──")
                for i, row in enumerate(sdata["data"]):
                    lines.append(" | ".join(row))
                    if i >= 500:  # 每表最多 500 行
                        lines.append(f"... 还有 {sdata['row_count'] - 501} 行未显示")
                        break
                lines.append("")

            return ToolResult.ok(
                "\n".join(lines),
                file_path=str(full_path),
                sheet_names=list(sheets_data.keys()),
                total_sheets=len(sheet_names),
                sheets=sheets_data,
            )

        except Exception as e:
            return ToolResult.fail(f"读取失败: {e}")
