"""定妆预览的暂存与「等用户确认」。

角色参数由工具推给前端画布，用户在画布上点「确认这版」才算定稿。
工具跑在工作线程里（ThreadPoolExecutor），所以这里用 threading.Event 阻塞，
不能用 asyncio —— 工具线程里没有事件循环。

只有一块画布、一个待确认角色，因此用全局单槽位而不是按会话分桶。
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

_lock = threading.Lock()
_pending: dict[str, dict[str, Any]] = {}
_events: dict[str, threading.Event] = {}
_latest: dict[str, Any] | None = None

VERDICT_CONFIRM = "confirm"
VERDICT_REVISE = "revise"


def publish(
    spec: dict[str, Any],
    title: str = "角色定妆",
    note: str = "",
    style: dict[str, Any] | None = None,
    project: str = "",
    characters: list[dict[str, Any]] | None = None,
) -> str:
    """把一版角色参数发布到画布，返回这次预览的凭据 token。

    characters 是整组角色（主角 + 配角），一次推上画布一起确认；
    不传时按只有主角处理，保持旧调用方兼容。
    """
    global _latest
    token = uuid.uuid4().hex[:12]
    payload = {
        "token": token,
        "spec": spec,
        "characters": list(characters or [{"role": "hero", "spec": spec}]),
        "title": title,
        "note": note,
        "style": dict(style or {}),
        "project": project,
        "created_at": time.time(),
    }
    with _lock:
        _pending[token] = payload
        _events[token] = threading.Event()
        _latest = payload
    return token


def wait_for_verdict(token: str, timeout: float = 900.0) -> dict[str, Any] | None:
    """等用户在这版预览上做决定。超时返回 None（调用方按「未确认」处理）。"""
    with _lock:
        event = _events.get(token)
    if event is None:
        return None
    if not event.wait(timeout):
        return None
    with _lock:
        payload = _pending.get(token) or {}
        return payload.get("answer")


def resolve(token: str, verdict: str, note: str = "") -> bool:
    """前端提交决定：确认 / 要求调整。"""
    if verdict not in (VERDICT_CONFIRM, VERDICT_REVISE):
        return False
    with _lock:
        payload = _pending.get(token)
        event = _events.get(token)
        if payload is None or event is None:
            return False
        payload["answer"] = {"verdict": verdict, "note": (note or "").strip()}
    event.set()
    return True


def dismiss(token: str) -> None:
    """工具结束时清掉这次预览，避免前端拿旧 token 反复提交。"""
    with _lock:
        _pending.pop(token, None)
        _events.pop(token, None)


def current() -> dict[str, Any] | None:
    """最近一次发布过的角色参数（续跑、画面部门取角色时用）。"""
    with _lock:
        return dict(_latest) if _latest else None


def latest_spec() -> dict[str, Any] | None:
    latest = current()
    return dict(latest["spec"]) if latest else None
