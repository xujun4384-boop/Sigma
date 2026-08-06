# longread skill
# ---------------------------------------------------------------------------
# 摘要
# 大文档并行阅读。将超大文档按 token 数切分为多个 chunk（10% 重叠），
# LLM 通过 sub_agent 并行阅读每个 chunk 后汇总。支持 PDF/DOCX/PPTX/TXT/MD。
#
## 使用场景
# - 文档 > 10000 字符或单次 read_pdf 输出被截断时
# - 合同、报告、学术论文等长文档需要全文阅读
# - "总结这个 50 页的 PDF"
#
# 三个自动策略:
#   longread → 切分后返回 chunk 列表 + sub_agent 调用示例
#   LLM → sub_agent 并行读 → 汇总
#
# 与 sub_agent 配合:
#   1. longread(file_path) → 返回 N 个 chunk 文件路径
#   2. sub_agent(tasks=[每个 chunk 一个子 Agent])
#   3. 汇总所有子 Agent 返回的内容
#
# 包含 1 种工具:
#   longread - 切分大文档
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── longread ──
# 切分大文档为多个 chunk 文件。
#
# 参数:
#   file_path (string, 必填) 文档路径
#   chunk_size (integer, 可选) 每个 chunk 的 token 数上限（默认 32000）
#
# 输出: 切分信息 + sub_agent 调用示例代码
# 依赖: tiktoken (精准分块) / pypdf (PDF 备选)
# ---------------------------------------------------------------------------
