from skills.base import BaseTool, ToolParameter, ToolResult
from skills.todo_manager import TodoManager, current_todo_manager

__all__ = ["BaseTool", "ToolParameter", "ToolResult", "SkillManager", "ALL_TOOL_CLASSES", "TodoManager", "current_todo_manager"]


def __getattr__(name):
    # 延迟导入 skills.manager，避免 skills.manager ↔ computer_use.tool 之间的循环导入
    if name in ("SkillManager", "ALL_TOOL_CLASSES"):
        from skills.manager import SkillManager, ALL_TOOL_CLASSES
        return {"SkillManager": SkillManager, "ALL_TOOL_CLASSES": ALL_TOOL_CLASSES}[name]
    raise AttributeError(f"module 'skills' has no attribute '{name}'")
