"""
Sigma TodoManager - 任务拆解与进度追踪

TodoList 由 LLM 通过 todo_write 工具管理，驱动多步骤任务执行。
参照 LLaMDA 设计：TodoWriteTool 通过 ContextVar 获取 TodoManager 实例，
ToolLoop 负责注入未完成任务上下文和推送 SSE 事件。
纯内存存储，重启即清空。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# 当前会话的 TodoManager（通过 ContextVar 在线程间传递）
current_todo_manager: ContextVar[Optional["TodoManager"]] = ContextVar("todo_manager", default=None)


class TodoItem:
    """单个 Todo 项"""
    __slots__ = ('id', 'content', 'status', 'priority')

    def __init__(self, id: str, content: str, status: str = 'pending', priority: str = 'medium'):
        self.id = id
        self.content = content
        self.status = status       # pending | in_progress | completed
        self.priority = priority   # high | medium | low

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'content': self.content,
            'status': self.status,
            'priority': self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TodoItem:
        return cls(
            id=data['id'],
            content=data['content'],
            status=data.get('status', 'pending'),
            priority=data.get('priority', 'medium'),
        )


class TodoManager:
    """Todo 列表管理器，绑定到会话。纯内存，重启即清空。"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._items: list[TodoItem] = []

    # ── 属性 ──

    @property
    def items(self) -> list[TodoItem]:
        return list(self._items)

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def completed_count(self) -> int:
        return sum(1 for t in self._items if t.status == 'completed')

    @property
    def in_progress_count(self) -> int:
        return sum(1 for t in self._items if t.status == 'in_progress')

    @property
    def is_completed(self) -> bool:
        return len(self._items) > 0 and all(t.status == 'completed' for t in self._items)

    def get_progress(self) -> dict:
        return {
            'total': self.count,
            'completed': self.completed_count,
            'in_progress': self.in_progress_count,
            'pending': self.count - self.completed_count - self.in_progress_count,
            'is_completed': self.is_completed,
        }

    def get_current_task(self) -> Optional[TodoItem]:
        """获取当前正在执行的任务（第一个 in_progress）"""
        for item in self._items:
            if item.status == 'in_progress':
                return item
        return None

    def get_next_pending(self) -> Optional[TodoItem]:
        """获取下一个待执行任务"""
        for item in self._items:
            if item.status == 'pending':
                return item
        return None

    # ── 操作 ──

    def replace_all(self, todos: list[dict]) -> list[TodoItem]:
        """全量替换 todo 列表"""
        self._items = [TodoItem.from_dict(t) for t in todos]
        return list(self._items)

    def merge(self, todos: list[dict]) -> list[TodoItem]:
        """合并更新：以 id 匹配，新 id 追加，已有 id 更新 status/content/priority"""
        id_map = {t.id: t for t in self._items}

        for item_data in todos:
            tid = item_data['id']
            if tid in id_map:
                existing = id_map[tid]
                if 'status' in item_data:
                    existing.status = item_data['status']
                if 'content' in item_data:
                    existing.content = item_data['content']
                if 'priority' in item_data:
                    existing.priority = item_data['priority']
            else:
                self._items.append(TodoItem.from_dict(item_data))

        return list(self._items)

    def to_dict(self) -> dict:
        return {
            'todos': [t.to_dict() for t in self._items],
            'progress': self.get_progress(),
        }
