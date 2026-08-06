"""
NetworkBridge 文件日志系统
写入 skills/network_bridge/logs/ 目录，按日期切分
同时保留 print() 到 stdout 用于控制台调试
"""

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).parent / "logs"
_LOCK = threading.Lock()
_FILE_DATE = None
_FILE_HANDLE = None


def _get_log_path() -> Path:
    """获取今日日志文件路径"""
    today = datetime.now().strftime("%Y-%m-%d")
    return _LOG_DIR / f"network_bridge_{today}.log"


def _ensure_file():
    """确保日志文件已打开，跨天自动切换"""
    global _FILE_DATE, _FILE_HANDLE
    today = datetime.now().strftime("%Y-%m-%d")
    if _FILE_DATE == today and _FILE_HANDLE is not None:
        return
    with _LOCK:
        if _FILE_DATE == today and _FILE_HANDLE is not None:
            return
        if _FILE_HANDLE:
            try:
                _FILE_HANDLE.close()
            except Exception:
                pass
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        _FILE_HANDLE = open(str(_get_log_path()), "a", encoding="utf-8", buffering=1)
        _FILE_DATE = today


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def log(level: str, msg: str):
    """写入日志文件 + stdout"""
    ts = _ts()
    line = f"[{ts}] [{level}] {msg}"
    try:
        _ensure_file()
        if _FILE_HANDLE:
            _FILE_HANDLE.write(line + "\n")
            _FILE_HANDLE.flush()
    except Exception:
        pass
    print(line, file=sys.stderr if level == "ERROR" else sys.stdout, flush=True)


def info(msg: str):
    log("INFO", msg)


def warn(msg: str):
    log("WARN", msg)


def error(msg: str):
    log("ERROR", msg)


def debug(msg: str):
    log("DEBUG", msg)


def action_start(action: str, params: dict = None):
    """记录操作开始"""
    params_str = ""
    if params:
        important = {k: v for k, v in params.items()
                     if k in ("selector", "ref", "url", "value", "x", "y", "query", "snapshotId")}
        if important:
            params_str = " " + str(important)
    info(f"▶ action={action}{params_str}")


def action_result(action: str, success: bool, detail: str = ""):
    """记录操作结果"""
    status = "✅" if success else "❌"
    extra = f" | {detail}" if detail else ""
    info(f"{status} action={action} success={success}{extra}")


def click_detail(action: str, selector: str, stability: dict = None,
                 navigation_detected: bool = None, url_before: str = "",
                 url_after: str = ""):
    """记录点击操作的详细信息"""
    parts = [f"action={action}", f"selector={selector}"]
    if stability:
        parts.append(f"stability={stability}")
    if navigation_detected is not None:
        parts.append(f"navDetected={navigation_detected}")
    if url_before and url_after and url_before != url_after:
        parts.append(f"urlChanged: {url_before[:80]} → {url_after[:80]}")
    info(f"🖱 CLICK | {' | '.join(parts)}")


def content_logs(entries: list):
    """批量写入 content.js 的日志到文件（每条一行，带 [CONTENT] 标记）"""
    for entry in entries:
        ts = datetime.fromtimestamp(entry.get("ts", 0) / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = entry.get("level", "INFO")
        msg = entry.get("msg", "")
        extra = entry.get("extra")
        line = f"[{ts}] [CONTENT] [{level}] {msg}"
        if extra and isinstance(extra, dict):
            line += " | " + str(extra)
        try:
            _ensure_file()
            if _FILE_HANDLE:
                _FILE_HANDLE.write(line + "\n")
                _FILE_HANDLE.flush()
        except Exception:
            pass
    if entries:
        print(f"[logger] 已同步 {len(entries)} 条 content 日志到文件", flush=True)
