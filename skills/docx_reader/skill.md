# docx_reader skill
# ---------------------------------------------------------------------------
# 摘要
# Word 文档读取技能。使用 python-docx 读取 .docx 文件内容，支持提取文本段落、
# 表格、图片信息和文档元数据。大文档支持分段读取。
#
## 使用场景
# - 需要查看 Word 文档的文本内容
# - 需要提取文档中的表格数据
# - 需要获取文档的元数据（标题、作者、日期等）
# - 文档较大需要分段逐块读取
# - 编辑前需要先了解文档结构和内容
#
# 包含 1 种子操作:
#   read_docx - 读取 Word 文档
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── read_docx ──
# 读取 Word (.docx) 文档的内容。
#
# 参数:
#   file_path        (string, 必填) Word 文档路径。
#                    示例: "report.docx", "C:/docs/contract.docx"
#   extract_tables   (boolean, 可选, 默认 false) 是否提取表格内容。
#   extract_images   (boolean, 可选, 默认 false) 是否提取图片引用信息。
#   include_metadata (boolean, 可选, 默认 false) 是否包含文档元数据。
#   chunk_size       (integer, 可选) 分段大小（段落数），用于大文档分块读取。
#   chunk_index      (integer, 可选, 默认 0) 分段索引，配合 chunk_size 使用。
#
# 输出: 文档正文内容，可选含元数据、表格统计、图片统计。
