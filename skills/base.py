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
    # 条件必填：仅当 required=False 时生效。形如 {"engine": ["opendesign", "manim"]}，
    # 表示"当 engine 取值为 opendesign 或 manim 时，本参数变为必填"。
    # 用于一个工具按判别参数分派多种子能力、各子能力必填项不同的场景。
    required_when: dict[str, list[Any]] | None = None

    def condition_label(self) -> str:
        """把 required_when 渲染成人类可读条件串，供 schema 描述与报错信息复用。"""
        if not self.required_when:
            return ""
        return " 且 ".join(
            f"{key} 为 {'/'.join(str(v) for v in vals)}"
            for key, vals in self.required_when.items()
        )

    def is_required(self, kwargs: dict) -> bool:
        """按当前入参判断本参数此刻是否必填（无条件参数恒用 required）。"""
        if self.required:
            return True
        if not self.required_when:
            return False
        for key, allowed in self.required_when.items():
            current = kwargs.get(key)
            if not any(str(current) == str(v) for v in allowed):
                return False
        return True


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

    def is_cancelled(self) -> bool:
        """当前会话是否已被用户取消。长循环应在每次迭代开始处检查并提前退出。"""
        from cancellation import cancelled

        return cancelled()

    def raise_if_cancelled(self) -> None:
        """取消时抛 ToolCancelledError，供循环内快速短路。"""
        from cancellation import raise_if_cancelled

        raise_if_cancelled()

    def validate_input(self, **kwargs) -> tuple[bool, str]:
        """校验输入参数（含按 required_when 触发的条件必填）"""
        for param in self.parameters:
            value = kwargs.get(param.name)
            if param.is_required(kwargs) and (value is None or value == ""):
                cond = param.condition_label()
                hint = f"（条件: {cond}）" if cond else ""
                # 列出「当前条件下」的必填参数，帮助 LLM 一次性补齐
                required_params = ", ".join(
                    f"{p.name}{('[' + p.condition_label() + ']') if p.condition_label() else ''}"
                    for p in self.parameters if p.is_required(kwargs)
                )
                return False, (
                    f"缺少必填参数: {param.name}{hint}。"
                    f"当前条件下所需参数: {required_params}"
                )
            if value is not None and param.enum and value not in param.enum:
                return False, f"参数 {param.name} 取值不在允许范围: {param.enum}"
        return True, ""

    @staticmethod
    def _param_property(p: "ToolParameter") -> dict:
        """把参数导出为 JSON Schema 属性；条件必填写进 description，
        保持标准 schema（不用 oneOf/anyOf，避免部分 provider 严格校验报错）。"""
        desc = p.description
        cond = p.condition_label()
        if cond:
            desc = f"{desc}（当 {cond} 时必填）"
        prop: dict[str, Any] = {"type": p.type, "description": desc}
        if p.enum:
            prop["enum"] = p.enum
        if p.default is not None:
            prop["default"] = p.default
        return prop

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
            properties[p.name] = self._param_property(p)
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
            properties[p.name] = self._param_property(p)
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
