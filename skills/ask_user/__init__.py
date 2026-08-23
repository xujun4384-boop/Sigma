"""
ask_user skill - 向用户提问，中断循环等待答案后继续执行

LLM 在任务执行中遇到需要用户确认/选择/补充信息时调用此工具。
调用后任务会暂停，用户回答后自动继续，且工具调用次数计数器归零。
"""
from skills.base import BaseTool, ToolParameter, ToolResult


class AskUserTool(BaseTool):
    name = "ask_user"
    description = (
        "向用户提出问题，暂停任务等待用户回答后继续执行。"
        "适用于：需要用户确认方向、选择方案、补充信息、澄清歧义等场景。"
        "也适用于工具调用次数即将用尽时向用户汇报进度并请求继续。"
        "调用后任务暂停，用户提交后自动继续，且工具调用次数会重新计数。"
        "严格要求：questions 必须是对象数组；每题的 id、text、type 为字符串；"
        "single_choice 与 multi_choice 的 options 必须直接是字符串数组，例如 [\"方案 A\", \"方案 B\"]，"
        "不要将选项包装为 {label: ...}、{text: ...}、{item: [...]} 或其他对象。"
    )
    parameters = [
        ToolParameter(
            "title", "string",
            "问卷标题，简要说明需要用户回答什么，例如：'任务执行方向确认'",
        ),
        ToolParameter(
            "questions", "array",
            "问题列表，每个问题包含以下字段："
            "id (string, 唯一标识), "
            "text (string, 问题文本), "
            "type (string, 题型: single_choice|multi_choice|open), "
            "options (string[], 选择题的直接字符串数组；正确示例 [\"选项 A\", \"选项 B\"]；禁止对象包装), "
            "required (boolean, 是否必填, 默认true)",
        ),
    ]

    def execute(self, title: str = "", questions: list = None, **kwargs) -> ToolResult:
        """此方法不会实际执行，tool_loop 会在主循环中拦截 ask_user 调用"""
        return ToolResult.ok("ask_user 由 tool_loop 特殊处理")
