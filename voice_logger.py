"""
语音通话独立日志 —— 与 sigma 主日志分离。

- 当前日志: logs/voice.log
- 历史归档: logs/voice_YYYY-MM-DD.log（每日一份）
- 只写文件 + 控制台 INFO，不复用 sigma 的 logger，避免日志混在一起。
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

_SIGMA_USER_DATA = os.environ.get("SIGMA_USER_DATA", "")
_LOG_BASE = Path(_SIGMA_USER_DATA) if _SIGMA_USER_DATA else Path(__file__).parent
LOG_DIR = _LOG_BASE / "logs"


def setup_voice_logger() -> logging.Logger:
    """配置并返回语音专用 logger，写入 voice.log，每日自动归档。"""
    logger = logging.getLogger("sigma.voice")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # 不向 root/sigma 传播，彻底隔离

    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOG_DIR / "voice.log"
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 每日归档
    if log_file.exists():
        try:
            old_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            old_date = old_mtime.strftime("%Y-%m-%d")
            if old_date != today_str:
                archive = LOG_DIR / f"voice_{old_date}.log"
                log_file.rename(archive)
        except OSError:
            pass

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        fh = logging.FileHandler(str(log_file), encoding="utf-8", mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.info("[VoiceLogger] 语音日志文件: %s", log_file)
    except Exception as e:
        print(f"[VoiceLogger] 无法创建日志文件 {log_file}: {e}", file=sys.stderr)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# 模块级实例，供 voice_chat / voice_memory 直接 import 使用
vlog = setup_voice_logger()
