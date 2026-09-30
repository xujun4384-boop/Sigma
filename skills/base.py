"""
Skill 基类：BaseTool, ToolParameter, ToolResult
参考 llamda 架构，声明式工具定义
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolParameter:
    name: str
    type: str  # "string" | "integer" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    enum: list[str] | None = None
    default: Any = None


@dataclass
class ToolResult:
    """工具执行结果。

    重要约定（务必遵守）：
    - `content` 是「回喂给 LLM 的文本」，LLM 只能看到这个字段。
      任何 LLM 后续需要的信息（路径、时长、时间戳、关键数据、错误详情、
      进度阶段等）都必须写进 content，否则 LLM 拿不到。
    - `details` 是「给代码/前端用的结构化元数据」，tool_loop / server 不会把它
      传给 LLM。只放非关键、可丢弃的辅助字段，不要放 LLM 需要的数据。
    """
    success: bool
    content: str
    truncated: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, content: str, **details) -> "ToolResult":
        return cls(success=True, content=content, details=details)

    @classmethod
    def fail(cls, error: str, **details) -> "ToolResult":
        return cls(success=False, content=error, details=details)


class BaseTool(ABC):
    """声明式工具基类，子类只需定义类属性 + 实现 execute()"""

    name: str = ""
    description: str = ""
    parameters: list[ToolParameter] = []

    def __init__(self, cwd: str = "."):
        self.cwd = cwd
        self._progress_callback: Callable[[dict], None] | None = None

    def set_progress_callback(self, callback: Callable[[dict], None] | None) -> None:
        """设置进度回调，用于实时推送工具执行进度到前端"""
        self._progress_callback = callback

    def _emit_progress(self, content: str, **extra) -> None:
        """上报进度，子类在关键节点调用"""
        if self._progress_callback:
            try:
                event = {"type": "tool_progress", "tool_name": self.name, "content": content}
                event.update(extra)
                self._progress_callback(event)
            except Exception:
                pass  # 进度上报失败不影响主流程

    def _resolve_path(self, path: str):
        """Resolve relative path against cwd and return a Path object."""
        from pathlib import Path

        p = Path(path).expanduser()
        if p.is_absolute():
            return p
        return (Path(self.cwd) / p) if self.cwd else p

    def validate_input(self, **kwargs) -> tuple[bool, str]:
        """校验输入参数"""
        for param in self.parameters:
            value = kwargs.get(param.name)
            if param.required and (value is None or value == ""):
                # 列出所有必填参数帮助 LLM 修正
                required_params = ", ".join(
                    f"{p.name} ({p.type})" for p in self.parameters if p.required
                )
                return False, (
                    f"缺少必填参数: {param.name}。"
                    f"该工具必填参数: {required_params}"
                )
            if value is not None and param.enum and value not in param.enum:
                return False, f"参数 {param.name} 取值不在允许范围: {param.enum}"
        return True, ""

    def check_permission(self, **kwargs) -> tuple[bool, str]:
        """权限检查，默认允许，子类可覆盖"""
        return True, ""

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具，子类必须实现"""
        ...

    def to_anthropic_tool(self) -> dict:
        """导出为 Anthropic tool use 格式"""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_openai_tool(self) -> dict:
        """导出为 OpenAI function calling 格式"""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
