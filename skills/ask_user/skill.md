# ask_user skill
# 摘要
向用户提问，暂停任务等待用户回答后继续执行。LLM 在遇到歧义、需要确认方向、选择方案、补充信息时主动使用。工具调用计数器会在用户回答后归零，避免长任务被硬截断。
## 使用场景
- 任务执行中遇到歧义，需要用户澄清需求
- 多个可选方案，需要用户做出选择
- 需要用户补充关键信息才能继续
- 工具调用次数即将用尽，向用户汇报进度并请求继续
- 子任务拆分前需要用户确认优先级
# 触发条件
当 LLM 判断需要用户输入才能继续推进任务时调用此工具。不应频繁使用，只在关键决策点使用。
# 注意
- 调用后任务暂停，用户提交后自动继续
- 工具调用次数会重新计数
- 每题一个 sheet，用户逐题回答，最后一题提交
- 支持单选题(single_choice)、多选题(multi_choice)、开放问答(open)

═══ 参数详情 ═══

── ask_user ──

title: string, 必填
  问卷标题，简要说明需要用户回答什么。

questions: array, 必填
  问题列表。每个元素包含：
  - id: string, 唯一标识
  - text: string, 问题文本
  - type: string, 题型: "single_choice" | "multi_choice" | "open"
  - options: string[], 选择题选项列表（single_choice/multi_choice 必填）
  - required: boolean, 是否必填，默认 true
