"""绘画画布的画面快照存储。

后端工具看不到浏览器里的画布，所以由前端在画完后把合成图回传到这里，
`canvas_review` 再取出来交给读图模型审查。

整个应用只有一块绘画画布，因此用一个全局槽位而不是按会话分桶。
"""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_snapshot: dict[str, Any] = {}
_review_count = 0
_generation = 0
_last_draw_at = 0.0


def set_snapshot(
    image_b64: str,
    stroke_count: int = 0,
    layers: list[str] | None = None,
    stroke_audit: list[dict[str, Any]] | None = None,
    width: int = 1600,
    height: int = 1000,
) -> int:
    """保存最新画面。返回本次快照的代数，供调用方判断是否是新画面。

    stroke_audit 是前端按真实采样点算出的笔迹几何事实（包围盒、长度、是否闭合），
    后端据此做可核对的审计，不依赖视觉模型的主观判断。
    """
    global _snapshot, _generation
    with _lock:
        _generation += 1
        _snapshot = {
            "image": image_b64,
            "strokes": int(stroke_count or 0),
            "layers": list(layers or []),
            "stroke_audit": list(stroke_audit or []),
            "width": int(width or 1600),
            "height": int(height or 1000),
            "generation": _generation,
            "updated_at": time.time(),
        }
        return _generation


def get_snapshot() -> dict[str, Any] | None:
    with _lock:
        return dict(_snapshot) if _snapshot else None


def clear_snapshot() -> None:
    global _snapshot
    with _lock:
        _snapshot = {}


def note_draw() -> None:
    """记下"刚刚下发过绘图指令"的时间点，用于判断快照是否为这次绘制之后的画面。"""
    global _last_draw_at
    with _lock:
        _last_draw_at = time.time()


def last_draw_at() -> float:
    with _lock:
        return _last_draw_at


def is_snapshot_fresh() -> bool:
    """当前快照是否产生于最近一次绘制指令之后。"""
    with _lock:
        if not _snapshot:
            return False
        return _snapshot.get("updated_at", 0) >= _last_draw_at


def wait_for_fresh_snapshot(timeout: float = 8.0, interval: float = 0.2) -> bool:
    """等前端把本次绘制后的画面回传过来。

    前端收到指令后会导出一张"完整画面"上传（与播放进度无关），
    通常在几百毫秒内完成；这里留出余量覆盖慢机器与多批指令的情况。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_snapshot_fresh():
            return True
        time.sleep(interval)
    return is_snapshot_fresh()


def next_review_index() -> int:
    """消耗一次审查配额，返回本次是第几次审查（从 1 开始）。"""
    global _review_count
    with _lock:
        _review_count += 1
        return _review_count


def reviews_used() -> int:
    with _lock:
        return _review_count


def reset_reviews() -> None:
    """新的一轮任务开始时重置配额，避免上一轮的审查次数挤占本轮。"""
    global _review_count
    with _lock:
        _review_count = 0
