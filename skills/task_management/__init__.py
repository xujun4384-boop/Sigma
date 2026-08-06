"""
任务管理工具：todo_write
让 LLM 可以将复杂任务拆解为多个步骤并追踪进度

TodoWriteTool 本身不持有状态，通过 ContextVar 获取当前会话的 TodoManager。
"""
from skills.base import BaseTool, ToolParameter, ToolResult
from skills.todo_manager import current_todo_manager


class TodoWriteTool(BaseTool):
    name = "todo_write"
    description = (
        "创建和管理结构化的任务列表，用于将复杂任务拆解为多个步骤并追踪进度。\n"
        "规则：\n"
        "- 同一时间只能有一个任务处于 in_progress 状态\n"
        "- 开始执行前先标记为 in_progress，完成后立即标记为 completed\n"
        "- merge=false 时全量替换，merge=true 时按 id 合并更新\n"
        "- 任务完成后不要删除，标记为 completed 即可"
    )
    parameters = [
        ToolParameter("todos", "array", "任务列表，每项包含 id/content/status/priority。status: pending|in_progress|completed, priority: high|medium|low"),
        ToolParameter("merge", "boolean", "是否合并更新（true=按id更新已有项，false=全量替换）", required=False, default=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, todos: list, merge: bool = False, **kwargs) -> ToolResult:
        todo_manager = current_todo_manager.get()
        if not todo_manager:
            return ToolResult.fail("TodoManager 未初始化，无法操作任务列表")

        try:
            if merge:
                result = todo_manager.merge(todos)
            else:
                result = todo_manager.replace_all(todos)

            progress = todo_manager.get_progress()
            lines = [f"任务列表已更新 ({progress['completed']}/{progress['total']} 完成):"]
            for item in result:
                icon = {'pending': '-', 'in_progress': '>', 'completed': 'x'}.get(item.status, '?')
                lines.append(f"  [{icon}] [{item.priority}] {item.content}")

            return ToolResult.ok(
                "\n".join(lines),
                total=progress['total'],
                completed=progress['completed'],
                in_progress=progress['in_progress'],
            )
        except Exception as e:
            return ToolResult.fail(f"更新任务列表失败: {e}")
