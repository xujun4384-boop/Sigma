# edit_xlsx skill
# ---------------------------------------------------------------------------
# 摘要
# 编辑现有 Excel 文件：修改单元格、增删行列、公式、工作表管理。
# 修改值时自动保持原有格式。
#
## 使用场景
# - 修改 Excel 单元格数据
# - 批量更新、数据清洗
# - 添加公式、格式化
# - 工作表增删改
#
# 包含 1 种工具:
#   edit_xlsx - 编辑 .xlsx 文件
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── edit_xlsx ──
# 编辑现有 Excel 文件，支持批量修改操作。
#
# 参数:
#   file_path (string, 必填) Excel 文件路径
#   sheet_name (string, 必填) 目标工作表
#   modifications (array, 必填) 修改操作列表, 每项 {action, ...}
#   save_as (string, 可选) 另存为路径
#
# 支持的 action:
#   set_cell    - {action: "set_cell", cell: "A1", value: "新值"}
#   set_row     - {action: "set_row", row: 2, value: ["a","b"]}
#   set_col     - {action: "set_col", col: "B", value: ["x","y"]}
#   add_formula - {action: "add_formula", cell: "C1", value: "=SUM(...)"}
#   delete_row  - {action: "delete_row", row: 3}
#   delete_col  - {action: "delete_col", col: "C"}
#   insert_row  - {action: "insert_row", row: 2}
#   insert_col  - {action: "insert_col", col: "B"}
#   clear_cell  - {action: "clear_cell", cell: "A1"}
#   add_sheet   - {action: "add_sheet", name: "新表"}
#   delete_sheet- {action: "delete_sheet", target_sheet: "Sheet2"}
#   rename_sheet- {action: "rename_sheet", new_name: "重命名"}
#   auto_fit    - {action: "auto_fit"}
#
# 格式保持: 修改单元格值时默认保持原格式，无需额外操作。
# ---------------------------------------------------------------------------
