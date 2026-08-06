# search_document skill
# ---------------------------------------------------------------------------
# 摘要
# 跨格式文档全文搜索。在多种文档格式（DOCX/PDF/XLSX/PPTX/TXT/MD/JSON 等）中
# 搜索关键词，支持单文件、整个目录、正则、近义词扩展搜索。返回上下文和位置。
#
## ⚠️ 与 search_docx 的区别:
#   search_docx     → 仅搜索 DOCX 文件内部内容（段落/表格等具体语义元素）
#   search_document → 搜索所有格式（DOCX/PDF/XLSX/PPTX/TXT/MD 等），
#                     支持目录递归、近义词扩展，但只返回关键词匹配的行
#
## 使用场景
# - 在项目目录中查找包含特定关键词的文档
# - 在 PDF/PPT 中搜索内容
# - 近义词扩展搜索（如搜"预算"同时找到"费用、成本、开支"）
# - 正则搜索（如找所有邮箱地址、日期格式）
#
# 包含 1 种工具:
#   search_document - 跨格式文档全文搜索
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── search_document ──
# 在文档中搜索关键词，支持单文件或目录。
#
# 参数:
#   file_path (string, 必填) 文档路径或目录路径
#   keyword (string, 必填) 搜索关键词
#   context_chars (integer, 可选) 上下文前后字符数（默认 50）
#   case_sensitive (boolean, 可选) 区分大小写（默认 false）
#   whole_word (boolean, 可选) 全词匹配（默认 false）
#   use_regex (boolean, 可选) 正则模式（默认 false）
#   extended_keywords (array, 可选) 近义词扩展列表
#        如 ["预算", "费用", "成本", "开支", "资金"]
#        LLM 可根据用户意图生成相关词，提高召回率
#
# 支持格式: .docx .pdf .xlsx .pptx .txt .md .py .json .csv .xml .html .js .css .yaml .log
#
# 依赖: python-docx PyMuPDF openpyxl python-pptx
# ---------------------------------------------------------------------------
