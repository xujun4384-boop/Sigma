"""
edit_xlsx skill - 编辑 Excel 文件

修改现有 Excel 文件的单元格内容、行列、工作表。
核心原则：修改单元格值时保持原有格式不变。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class EditXlsxTool(BaseTool):
    name = "edit_xlsx"
    description = (
        "编辑现有 Excel (.xlsx) 文件：修改单元格值、添加/删除行列、添加公式、数据清洗。"
        "修改值时自动保持原有单元格格式。支持指定保存路径（另存为）。"
    )
    parameters = [
        ToolParameter("file_path", "string", "Excel 文件路径"),
        ToolParameter("sheet_name", "string", "目标工作表名称（必填）"),
        ToolParameter(
            "modifications",
            "array",
            "修改操作列表。每项: {action, cell/row/col, value, ...}。"
            "action 可选: set_cell / set_row / set_col / delete_row / delete_col / "
            "insert_row / insert_col / add_formula / add_sheet / rename_sheet / "
            "delete_sheet / auto_fit / clear_cell",
        ),
        ToolParameter("save_as", "string", "另存为路径（可选，不指定则覆盖原文件）", required=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, sheet_name: str = None, modifications: list = None,
                save_as: str = None, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not os.path.exists(full_path):
            return ToolResult.fail(f"文件不存在: {file_path}")

        if not isinstance(modifications, list) or not modifications:
            return ToolResult.fail("modifications 必须是非空列表")

        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(full_path))
        except ImportError:
            return ToolResult.fail("缺少 openpyxl 库，请执行: pip install openpyxl")
        except Exception as e:
            return ToolResult.fail(f"打开文件失败: {e}")

        sheet_name = sheet_name or (wb.sheetnames[0] if wb.sheetnames else "Sheet")
        sheet_independent_actions = {"add_sheet", "delete_sheet", "rename_sheet"}
        needs_existing_sheet = any(
            (mod.get("action", "") not in sheet_independent_actions)
            for mod in modifications
        )
        if needs_existing_sheet and sheet_name not in wb.sheetnames:
            return ToolResult.fail(f"工作表 '{sheet_name}' 不存在。可用: {wb.sheetnames}")

        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.active
        results = []
        errors = []

        for i, mod in enumerate(modifications):
            action = mod.get("action", "")
            try:
                msg = self._apply(ws, wb, action, mod, i)
                results.append(msg)
            except Exception as e:
                errors.append(f"#{i} {action}: {e}")

        save_path = self._resolve_path(save_as) if save_as else full_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            wb.save(str(save_path))
        except Exception as e:
            return ToolResult.fail(f"保存失败: {e}")

        summary = f"完成 {len(results)}/{len(modifications)} 项修改"
        if errors:
            summary += f"，{len(errors)} 项失败"
        return ToolResult.ok(
            summary,
            modified=len(results),
            errors=len(errors),
            details={"results": results, "errors": errors},
            save_path=str(save_path),
        )

    def _apply(self, ws, wb, action: str, mod: dict, idx: int) -> str:
        val = mod.get("value")

        if action == "set_cell":
            cell_ref = mod.get("cell", "")
            cell = ws[cell_ref]
            cell.value = val
            return f"#{idx} {cell_ref} = {val}"

        elif action == "set_row":
            row_num = mod.get("row", 1)
            for ci, v in enumerate(val, 1):
                ws.cell(row=row_num, column=ci, value=v)
            return f"#{idx} 行 {row_num} 已设置 {len(val)} 列"

        elif action == "set_col":
            col_letter = mod.get("col", "A")
            for ri, v in enumerate(val, 1):
                ws.cell(row=ri, column=ws[f"{col_letter}1"].column, value=v)
            return f"#{idx} 列 {col_letter} 已设置 {len(val)} 行"

        elif action == "add_formula":
            cell_ref = mod.get("cell", "")
            ws[cell_ref] = val
            return f"#{idx} {cell_ref} 公式已设置"

        elif action == "delete_row":
            row_num = mod.get("row", 1)
            ws.delete_rows(row_num)
            return f"#{idx} 删除行 {row_num}"

        elif action == "delete_col":
            col_letter = mod.get("col", "A")
            col_idx = ws[f"{col_letter}1"].column
            ws.delete_cols(col_idx)
            return f"#{idx} 删除列 {col_letter}"

        elif action == "insert_row":
            row_num = mod.get("row", 1)
            ws.insert_rows(row_num)
            return f"#{idx} 插入行 {row_num}"

        elif action == "insert_col":
            col_letter = mod.get("col", "A")
            col_idx = ws[f"{col_letter}1"].column
            ws.insert_cols(col_idx)
            return f"#{idx} 插入列 {col_letter}"

        elif action == "clear_cell":
            cell_ref = mod.get("cell", "")
            ws[cell_ref] = None
            return f"#{idx} 清除 {cell_ref}"

        elif action == "add_sheet":
            name = mod.get("name", f"Sheet{wb.sheetnames.__len__() + 1}")
            wb.create_sheet(title=name)
            return f"#{idx} 新建工作表: {name}"

        elif action == "rename_sheet":
            new_name = mod.get("new_name", "")
            if mod.get("target_sheet"):
                wb[mod["target_sheet"]].title = new_name
            else:
                ws.title = new_name
            return f"#{idx} 重命名为: {new_name}"

        elif action == "delete_sheet":
            target = mod.get("target_sheet", "")
            if target in wb.sheetnames:
                del wb[target]
                return f"#{idx} 删除工作表: {target}"
            return f"#{idx} 工作表不存在: {target}"

        elif action == "auto_fit":
            cols = mod.get("columns") or list(ws.columns)
            widths = {}
            for col_cells in cols:
                max_len = 0
                col_letter = None
                for cell in col_cells:
                    if col_letter is None:
                        col_letter = cell.coordinate.rstrip("0123456789")
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                if col_letter and max_len > 0:
                    ws.column_dimensions[col_letter].width = min(max_len + 4, 60)
            return f"#{idx} 自动调整列宽完成"

        else:
            return f"#{idx} 未知操作: {action}"
