"""Computer Use 会话管理器。

职责：
- 维护会话状态机：idle / running / paused / taken_over / stopped
- 保存最新一帧画面（供悬浮窗实时观看）
- 记录动作日志（供悬浮窗与用户审阅）
- 承接用户的人机协同指令：暂停 / 继续 / 接管 / 交还 / 停止 / 纠正
- 为执行引擎提供 wait_until_operable()：在暂停或用户接管时阻塞，实现「可暂停、可中途接管」

线程模型：工具在 ThreadPoolExecutor 工作线程中执行（见 tool_loop），因此这里的阻塞
不会卡住事件循环；HTTP 端点仍在事件循环里，随时可读写状态。
"""
from __future__ import annotations

import threading
import time
from collections import deque

STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_TAKEN_OVER = "taken_over"
STATE_STOPPED = "stopped"

_OPERABLE = (STATE_IDLE, STATE_RUNNING)
_BLOCKING = (STATE_PAUSED, STATE_TAKEN_OVER)


class ComputerUseManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = STATE_IDLE
        self._frame: dict | None = None
        self._log: deque = deque(maxlen=200)
        self._corrections: deque = deque()
        self._task = ""
        self._message = ""
        self._llm_config: dict | None = None

    # ── LLM 配置 ──
    def set_llm_config(self, cfg: dict | None):
        with self._lock:
            self._llm_config = dict(cfg) if cfg else None

    def get_llm_config(self) -> dict | None:
        with self._lock:
            return dict(self._llm_config) if self._llm_config else None

    # ── 会话生命周期 ──
    def start(self, task: str = ""):
        with self._lock:
            self._state = STATE_RUNNING
            self._task = task or ""
            self._message = ""
            self._log.clear()
            self._corrections.clear()

    def stop(self, message: str = ""):
        with self._lock:
            self._state = STATE_STOPPED
            if message:
                self._message = message

    def state(self) -> str:
        with self._lock:
            return self._state

    def set_state(self, state: str, message: str = ""):
        with self._lock:
            self._state = state
            if message:
                self._message = message

    # ── 画面与日志 ──
    def push_frame(self, cap: dict):
        with self._lock:
            self._frame = {
                "image": cap.get("image"),
                "mime": cap.get("mime", "image/jpeg"),
                "width": cap.get("image_width"),
                "height": cap.get("image_height"),
                "ts": cap.get("ts", time.time()),
            }

    def log_action(self, action: str, detail: str, ok: bool = True):
        with self._lock:
            self._log.append({
                "ts": time.time(),
                "action": action,
                "detail": str(detail)[:300],
                "ok": bool(ok),
            })

    # ── 用户纠正 ──
    def post_correction(self, text: str):
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._corrections.append(text)

    def consume_corrections(self) -> list[str]:
        with self._lock:
            items = list(self._corrections)
            self._corrections.clear()
            return items

    # ── 供悬浮窗轮询的快照 ──
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "task": self._task,
                "message": self._message,
                "frame": dict(self._frame) if self._frame else None,
                "log": list(self._log)[-20:],
                "pending_corrections": len(self._corrections),
            }

    # ── 执行前的可操作性闸门 ──
    def wait_until_operable(self, poll: float = 0.25) -> bool:
        """每次执行动作前调用。

        - idle / running：放行
        - paused / taken_over：阻塞等待用户恢复（这就是「暂停 / 中途接管」的实现）
        - stopped：返回 False，要求调用方中止
        """
        while True:
            s = self.state()
            if s in _OPERABLE:
                return True
            if s == STATE_STOPPED:
                return False
            time.sleep(poll)


# 全局单例
computer_use_manager = ComputerUseManager()
