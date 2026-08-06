# task_management skill
# ---------------------------------------------------------------------------
# 摘要
# 多步骤任务的规划、跟踪和管理。当任务需要 3 个以上步骤或涉及多个 skill 组合时，
# 无论是代码修改、办公文件处理还是其他类型任务，都必须使用此 skill 创建任务列表。
#
## 触发条件
# 满足以下任一条件时必须启用:
#   1. 任务需要 3 个以上独立步骤
#   2. 任务涉及多个 skill 组合（如 file_operations + web_search）
#   3. 任务需要清晰的执行计划来追踪进度
#   4. 任务步骤之间有依赖关系（后续步骤依赖前一步结果）
#
# 典型触发场景:
#   - "给这个项目添加用户认证功能"（分析→设计→实现→测试→校验）
#   - "重构 utils 模块，拆分成独立文件"（扫描→拆分→调整引用→验证→清理）
#   - "分析这个文件夹内所有 PDF，生成摘要报告"（查找→读取→分析→生成报告）
#   - "把这份 Word 文档中的表格数据提取到 Excel"（读取→解析→提取→写入→校验）
#   - "搜索最新行业报告，整理成 PPT"（搜索→筛选→提取→排版→生成）
#   - "批量压缩图片，生成 Word 报告"（扫描→筛选→压缩→写报告）
#   - "合并多份 Excel 报表，生成汇总图表"（读取→汇总→分析→绘图→输出）
#
# 不需要触发的场景:
#   - "读取这个文件的内容"（单步骤）
#   - "这个文件有多少行"（简单查询）
#   - "把这段文字翻译成英文"（单步骤）
#
# 能力 (CAPABILITIES)
#   创建任务列表、追踪进度、动态调整、逐步执行、清晰展示进度
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── todo_write ──
# 创建和管理结构化的任务列表，用于将复杂任务拆解为多个步骤并追踪进度。
# 这是 task_management skill 的唯一工具。
#
# 参数:
#   todos (array, 必填) 任务列表，每项包含以下字段:
#     id       (string)  唯一标识（如 "1", "2", "3"）
#     content  (string)  任务描述，应清晰说明该步骤具体要做什么
#     status   (string)  pending | in_progress | completed
#     priority (string)  high | medium | low
#
#     示例:
#       {"id": "1", "content": "读取所有 PDF 文件内容", "status": "pending", "priority": "high"}
#       {"id": "2", "content": "提取每个 PDF 的关键信息", "status": "pending", "priority": "medium"}
#       {"id": "3", "content": "生成 Markdown 摘要报告", "status": "pending", "priority": "medium"}
#
#   merge (boolean, 可选, 默认 false) 是否合并更新。
#          false = 全量替换整个任务列表（首次创建时使用）
#          true  = 按 id 合并更新已有任务（逐步更新状态时使用）
#
# 使用规则:
#   1. 同一时间只能有一个任务处于 in_progress 状态
#   2. 开始执行前先将任务标记为 in_progress，完成后立即标记为 completed
#   3. 首次创建使用 merge=false 全量设置所有步骤
#   4. 后续更新状态使用 merge=true，只传状态变化的任务项
#   5. 任务完成后不要删除，标记为 completed 即可
#   6. 保持任务列表简洁，通常 3-7 个步骤为宜
#   7. 任务粒度适中：每步应是一个有意义的操作单元，不要太细（如"导入库"）也不要太粗
#
# 输出: 格式化的任务列表，显示完成进度 (N/M) 和每个任务的状态与优先级。
#
#
# ── 典型使用流程 ──
#
# 步骤 1: 首次创建（merge=false）
#   将完整任务计划一次性提交:
#   {
#     "todos": [
#       {"id": "1", "content": "查找工作目录下所有 Excel 文件", "status": "in_progress", "priority": "high"},
#       {"id": "2", "content": "逐份读取并汇总数据", "status": "pending", "priority": "high"},
#       {"id": "3", "content": "生成汇总图表并写入新 Excel", "status": "pending", "priority": "medium"},
#       {"id": "4", "content": "校验输出文件数据正确性", "status": "pending", "priority": "low"}
#     ],
#     "merge": false
#   }
#
# 步骤 2: 完成第一个任务，开始第二个（merge=true）
#   只传状态有变化的任务项:
#   {
#     "todos": [
#       {"id": "1", "content": "查找工作目录下所有 Excel 文件", "status": "completed", "priority": "high"},
#       {"id": "2", "content": "逐份读取并汇总数据", "status": "in_progress", "priority": "high"}
#     ],
#     "merge": true
#   }
#
# 步骤 3-N: 继续逐步更新，直至全部完成
