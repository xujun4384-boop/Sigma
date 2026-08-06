"""
Sigma 日志系统 —— 固定写入 sigma.log，跨天自动归档

- 当前日志: logs/sigma.log
- 历史归档: logs/sigma_YYYY-MM-DD.log（每日一份）
- 控制台实时输出所有 INFO+ 级别日志
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

_SIGMA_USER_DATA = os.environ.get("SIGMA_USER_DATA", "")
_LOG_BASE = Path(_SIGMA_USER_DATA) if _SIGMA_USER_DATA else Path(__file__).parent
LOG_DIR = _LOG_BASE / "logs"


def setup_logger() -> logging.Logger:
    """配置并返回 sigma 专用 logger。写入 sigma.log，每日自动归档旧文件。"""
    logger = logging.getLogger("sigma")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOG_DIR / "sigma.log"
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 每日归档：如果 sigma.log 是昨天的，重命名为 sigma_YYYY-MM-DD.log
    if log_file.exists():
        try:
            old_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            old_date = old_mtime.strftime("%Y-%m-%d")
            if old_date != today_str:
                archive = LOG_DIR / f"sigma_{old_date}.log"
                log_file.rename(archive)
        except OSError:
            pass

    # 文件 handler：DEBUG 级别全量写入
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        fh = logging.FileHandler(str(log_file), encoding="utf-8", mode="a")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        logger.info(f"[Logger] 日志文件: {log_file}")
    except Exception as e:
        print(f"[Logger] 无法创建日志文件 {log_file}: {e}", file=sys.stderr)

    # 控制台 handler：INFO 级别，开发方便
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


# 模块级 logger 实例
log = setup_logger()
