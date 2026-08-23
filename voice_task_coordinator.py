"""语音任务协调器：隔离完整任务结果，并在语音空闲时串行交付摘要。"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

from voice_logger import vlog as logger


@dataclass
class VoiceTask:
    """一次 run_task 的后端任务记录。完整结果只保存在这里，不直接注入语音 LLM。"""

    id: str
    description: str
    call_id: str
    status: str = "running"
    result: str = ""
    summary: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    delivered_at: Optional[float] = None
    # call_id 是否仍然有效。用户在工具执行期间开口打断后，火山模型会放弃该 FC 等待，
    # 此时再用原 call_id 回传结果无效，需要改用 speech_text_buffer.replacement 主动插播。
    call_valid: bool = True
    # 重复 FC 带来的额外 call_id：用户插话后语音模型可能对同一任务再次发起 FC，
    # 这些 call_id 一并关联到本任务，结果交付时全部回传，避免同任务重复执行。
    extra_call_ids: List[str] = field(default_factory=list)


class VoiceTaskCoordinator:
    """管理同一通话内的任务、结果摘要和等待交付队列。

    - task registry 保存主 Sigma 的完整工作结果；
    - pending queue 只按 FIFO 保存等待交付的任务 id；
    - 用户说话或语音模型正在回复时，完成结果留在队列；
    - 空闲时，通过 deliver 回调一次交付一个摘要给语音模型。
    """

    def __init__(self, deliver: Callable[[VoiceTask], Awaitable[bool]], max_summary_chars: int = 200):
        self._deliver = deliver
        self._max_summary_chars = max_summary_chars
        self.tasks: Dict[str, VoiceTask] = {}
        self.pending_result_ids: List[str] = []
        self.user_speaking = False
        self.assistant_speaking = False
        self._lock = asyncio.Lock()
        self._flushing = False

    def register(self, description: str, call_id: str) -> VoiceTask:
        task = VoiceTask(id=f"voice-task-{uuid.uuid4().hex[:8]}", description=description, call_id=call_id)
        self.tasks[task.id] = task
        return task

    def find_running(self, description: str) -> Optional[VoiceTask]:
        """查找描述完全一致、仍在执行的任务，用于对重复 FC 去重。"""
        for task in self.tasks.values():
            if task.status == "running" and task.description == description:
                return task
        return None

    def attach_call_id(self, task_id: str, call_id: str) -> None:
        """把重复 FC 的 call_id 关联到已有任务，交付时一并回传。"""
        task = self.tasks.get(task_id)
        if task and call_id and call_id != task.call_id and call_id not in task.extra_call_ids:
            task.extra_call_ids.append(call_id)

    @staticmethod
    def summarize(result: str, max_chars: int = 700) -> str:
        """生成不依赖 LLM 的保守摘要，避免把数千字主任务结果塞进语音上下文。"""
        text = " ".join((result or "").split())
        if not text:
            return "任务已完成，但没有返回可播报的文本结果。"
        if len(text) <= max_chars:
            return text

        # 优先在句末、换行或列表边界截断；找不到则硬截断。
        cut = max(text.rfind(mark, 0, max_chars) for mark in ("。", "！", "？", "；", "\n"))
        if cut < max_chars // 2:
            cut = max_chars
        return f"{text[:cut + 1].rstrip()}。结果内容较长，完整结果已保留，您可以继续问我具体部分。"

    async def complete(self, task_id: str, result: str, summary: str = "") -> None:
        """保存完整结果、生成/接收摘要并把任务推入待交付队列。"""
        async with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                return
            task.status = "completed"
            task.result = result
            task.summary = summary or self.summarize(result, self._max_summary_chars)
            task.completed_at = time.time()
            self.pending_result_ids.append(task_id)

        # 任务完成时若语音空闲，立即尝试交付；否则等语音状态变化事件触发。
        await self.flush_if_idle()

    async def fail(self, task_id: str, message: str) -> None:
        await self.complete(task_id, f"任务执行失败：{message}")
        task = self.tasks.get(task_id)
        if task:
            task.status = "failed"

    async def set_user_speaking(self, speaking: bool) -> None:
        self.user_speaking = speaking
        if not speaking:
            await self.flush_if_idle()

    def mark_active_calls_invalid(self) -> None:
        """用户开口打断时调用：所有尚未交付的任务，其 call_id 已失效。"""
        for task in self.tasks.values():
            if task.status != "delivered":
                task.call_valid = False

    async def set_assistant_speaking(self, speaking: bool) -> None:
        self.assistant_speaking = speaking
        if not speaking:
            await self.flush_if_idle()

    async def flush_if_idle(self) -> None:
        """语音空闲时按 FIFO 交付一个待播结果，避免并发写入语音模型。"""
        async with self._lock:
            if not self.pending_result_ids:
                return  # 无待交付，静默返回
            if self._flushing or self.user_speaking or self.assistant_speaking:
                logger.debug(
                    "[voice.coord] flush 跳过 flushing=%s user=%s assistant=%s pending=%d",
                    self._flushing, self.user_speaking, self.assistant_speaking, len(self.pending_result_ids),
                )
                return
            task_id = self.pending_result_ids.pop(0)
            task = self.tasks.get(task_id)
            if task is None:
                return
            self._flushing = True
            task.status = "delivering"

        logger.info("[voice.coord] 开始交付 task=%s call_valid=%s", task.id, task.call_valid)
        delivered = False
        try:
            delivered = await self._deliver(task)
        finally:
            async with self._lock:
                self._flushing = False
                if delivered:
                    task.status = "delivered"
                    task.delivered_at = time.time()
                    # tool 结果一旦交给语音模型，下一条必须等本轮 response.done 再发。
                    self.assistant_speaking = True
                else:
                    task.status = "completed"
                    self.pending_result_ids.insert(0, task.id)

        # 一次只交付一个。下一条等待模型本轮 response.done 后再投递。

    def get_task(self, task_id: str) -> Optional[VoiceTask]:
        return self.tasks.get(task_id)
