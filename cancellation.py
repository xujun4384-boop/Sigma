"""
会话级取消与子进程管理。

目标：用户在前端按下「停止」时，
  1. 当前会话的 asyncio 循环尽快跳出（由调用方在循环里检查 cancel 状态）；
  2. 当前会话由工具（bash / sandbox / 各 skill）派生出的所有子进程被终止。

设计：
  - `CancellationToken`：每个会话一个。内部持有一个线程安全的取消标志，
    并登记该会话执行期间产生的所有 `subprocess.Popen`，取消时按平台杀掉整棵进程树。
    对外暴露 `is_set()` / `set()`，与原先的 `asyncio.Event` 接口兼容（二者原本只用这两个方法）。
  - `install_process_guard()`：对 `subprocess.Popen.__init__` 做一次全局包装。
    凡是「取消令牌可见」的线程里起的进程都会自动登记（`subprocess.run` 底层也走 Popen）。
    这样无需逐个 skill 改造即可覆盖 bash / sandbox / 渲染脚本等全部派生进程。
  - `current_cancel_token`：ContextVar，用于把令牌从调度线程传递到工具执行线程。
  - `cancelled()`：任何工具线程都可直接调用，判断当前会话是否已取消。
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from contextvars import ContextVar

# 保存原始 Popen 类：终止进程时用它派发 taskkill，避免被守卫再次登记
_real_popen = subprocess.Popen


class ToolCancelledError(Exception):
    """工具执行过程中检测到用户取消时抛出，供长循环提前退出。"""


class CancellationToken:
    """会话级取消令牌：线程安全的取消标志 + 子进程登记表。"""

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._procs: "set[subprocess.Popen]" = set()

    # ── asyncio.Event 兼容接口（现有代码只用 is_set()/set()）──
    def is_set(self) -> bool:
        return self._event.is_set()

    def set(self) -> None:
        """触发取消：置位标志并终止已登记的子进程。"""
        self.cancel()

    # ── 取消 ──
    def cancel(self) -> None:
        self._event.set()
        self.kill_processes()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    # ── 进程登记 ──
    def register_proc(self, proc: subprocess.Popen) -> None:
        """登记子进程；若已取消，则立即杀掉它。"""
        with self._lock:
            if self._event.is_set():
                kill = True
            else:
                self._procs.add(proc)
                kill = False
        if kill:
            self._kill_proc(proc)

    def unregister_proc(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)

    # ── 进程终止 ──
    def kill_processes(self) -> None:
        with self._lock:
            procs = list(self._procs)
            self._procs.clear()
        for p in procs:
            self._kill_proc(p)

    @staticmethod
    def _kill_proc(proc: subprocess.Popen) -> None:
        try:
            if proc.poll() is not None:  # 已结束
                return
        except Exception:
            return
        pid = proc.pid
        # 终止 tree 时派发的 taskkill 必须屏蔽登记，避免自我登记后被立刻杀掉
        suppress_registration.set(True)
        try:
            if os.name == "nt":
                _real_popen(
                    f"taskkill /F /T /PID {pid}",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # POSIX：先尽力终止，再兜底强杀
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            suppress_registration.set(False)


# ── ContextVar：把当前会话令牌传到工具执行线程 ──

current_cancel_token: ContextVar["CancellationToken | None"] = ContextVar(
    "current_cancel_token", default=None
)
# 终止进程期间屏蔽登记，防止 taskkill 自身被登记
suppress_registration: ContextVar[bool] = ContextVar("suppress_registration", default=False)


def cancelled() -> bool:
    """当前执行上下文（通常为工具线程）是否已被取消。"""
    tok = current_cancel_token.get()
    return bool(tok is not None and tok.is_set())


def raise_if_cancelled() -> None:
    if cancelled():
        raise ToolCancelledError("用户已取消任务")


# ── 会话令牌注册表 ──

_tokens: "dict[str, CancellationToken]" = {}
_tokens_lock = threading.Lock()


def get_token(session_id: str) -> CancellationToken:
    """取会话令牌；若不存在或已被使用过（已取消），则新建。"""
    with _tokens_lock:
        tok = _tokens.get(session_id)
        if tok is None or tok.is_set():
            tok = CancellationToken(session_id)
            _tokens[session_id] = tok
        return tok


def release_token(session_id: str) -> None:
    with _tokens_lock:
        _tokens.pop(session_id, None)


def cancel_session(session_id: str) -> bool:
    """取消指定会话：置位标志并终止其全部子进程。"""
    with _tokens_lock:
        tok = _tokens.get(session_id)
    if tok is None:
        return False
    tok.cancel()
    return True


# ── 子进程全局守卫 ──

_guard_installed = False
_guard_lock = threading.Lock()


def install_process_guard() -> None:
    """幂等地给 subprocess.Popen 安装登记守卫。

    仅登记「当前线程可见取消令牌」的进程；令牌不可见的进程（如 Sigma 自身启动的
    服务、系统命令）一律不登记，因此不会被误杀。
    """
    global _guard_installed
    with _guard_lock:
        if _guard_installed:
            return
        _guard_installed = True

        orig_init = subprocess.Popen.__init__

        def _patched_init(self, *args, **kwargs):
            orig_init(self, *args, **kwargs)
            if suppress_registration.get():
                return
            tok = current_cancel_token.get()
            if tok is None:
                return
            tok.register_proc(self)
            # 进程结束后自动注销，避免登记表膨胀
            threading.Thread(
                target=_reaper, args=(tok, self), daemon=True
            ).start()

        subprocess.Popen.__init__ = _patched_init


def _reaper(tok: "CancellationToken", proc: subprocess.Popen) -> None:
    try:
        proc.wait()
    except Exception:
        pass
    finally:
        tok.unregister_proc(proc)
