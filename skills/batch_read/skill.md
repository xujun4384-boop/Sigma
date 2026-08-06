# batch_read skill
# ---------------------------------------------------------------------------
# 摘要
# 批量读取文件的唯一入口。替代 read/read_docx/read_pdf/read_xlsx。
# 通过子 Agent 并行读取分析，返回智能摘要，token 消耗可控。
#
## ⚠️ 重要提示
# - 阅读 >=2 个文件时必须使用 batch_read，不要逐文件调用 read
# - 读 1 个文件时也优先使用 batch_read（设置 purpose 可获得更精准的摘要）
# - 需要查看文件原文时，设置 include_content=true，子 Agent 会同时返回摘要+原文
# - 需要深入了解文件细节时，在 purpose 中明确描述即可
# - 禁止直接调用 read/read_docx/read_pdf/read_xlsx 读取文件
#
## 使用场景
# - 了解项目结构：batch_read 多个入口文件
# - 代码审查：批量读取变更文件并获得分析摘要
# - 文档分析：批量读取文档并提取关键信息
# - 需要原文：设置 include_content=true 获取摘要+原文
# - 任何需要读取文件的操作
#
# 包含 1 种工具:
#   batch_read - 批量文件读取
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── batch_read ──
# 批量读取文件并返回统一摘要。每个文件由独立子 Agent 并行分析。
#
# 参数:
#   file_paths (array, 必填) 文件路径列表
#   purpose (string, 必填) 读取目的，帮助精准提取关键信息
#   include_content (boolean, 可选) 是否包含文件原文，默认 false
#
# 输出:
#   include_content=false: 各子 Agent 的摘要结果汇总
#   include_content=true:  各子 Agent 的摘要+原文结果汇总
# ---------------------------------------------------------------------------
