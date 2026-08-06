# docx_editor skill
# ---------------------------------------------------------------------------
# 摘要
# Word 文档编辑技能。采用"读取-分析-修改-验证"四步工作流精确修改 .docx 文档。
# 支持段落/表格/标题的替换、插入、删除和样式修改。
#
## 使用场景
# - 需要修改 Word 文档中的特定内容
# - 需要替换表格中的单元格数据
# - 需要调整文档段落样式
# - 需要批量替换文档内容
# - 编辑前想预览修改效果（dry_run 模式）
#
# 包含 1 种子操作:
#   edit_docx - 编辑 Word 文档
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── edit_docx ──
# 精确编辑 Word (.docx) 文档，支持四步工作流。
#
# 参数:
#   file_path        (string, 必填) 要编辑的文档路径。
#   edit_instructions (array, 必填) 修改指令列表，每项包含:
#     target       (string) paragraph | table | heading
#     match_type   (string) index | content | regex | style | level
#     match_value  (string) 匹配值
#     action       (string) replace | insert | delete | modify_style
#     new_content  (string, 可选) 新内容
#     old_content  (string, 可选) 用于验证的原内容
#     style_changes (object, 可选) {font_name, font_size, bold, color}
#     cell_location (object, 可选) {row, col} 表格目标时使用
#
#     示例:
#       [{"target": "paragraph", "match_type": "content", "match_value": "旧文本",
#         "action": "replace", "new_content": "新文本"}]
#       [{"target": "table", "match_type": "content", "match_value": "1000",
#         "action": "replace", "new_content": "2000", "cell_location": {"row": 1, "col": 2}}]
#
#   output_path (string, 可选) 输出路径，不指定则覆盖原文件。
#   backup      (boolean, 可选, 默认 true) 是否创建 .backup 备份。
#   dry_run     (boolean, 可选, 默认 false) 预览模式，只分析不实际修改。
#
# 输出: 修改统计（成功/失败数）、验证检查结果、输出路径。
