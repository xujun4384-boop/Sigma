"""读图专用视觉模型的进程级配置。

Settings → Skill Keys → 图片读取 里选择一个已保存的 LLM 作为读图模型后，
server 会把它解析成标准 llm_config 注入这里；所有走 describe_image_b64 的
看图链路（read_image、computer_use 截图理解、抽帧复审等）都会优先使用它。
未配置时，各调用方回落到自己的主 LLM 配置。

同时把配置写入环境变量 SIGMA_VISION_LLM，供通过子进程运行的技能
（如 lyric_mv 的 pipeline.py）继承——子进程里的 get_vision_llm_config
读不到进程内存，但能读到继承的环境变量。
"""
from __future__ import annotations

import json
import os
import threading

_LOCK = threading.Lock()
_CONFIG: dict | None = None
_ENV_KEY = "SIGMA_VISION_LLM"


def set_vision_llm_config(config: dict | None) -> None:
    """注入/清除读图专用 LLM 配置（传 None 表示回落主 LLM）。"""
    global _CONFIG
    with _LOCK:
        _CONFIG = dict(config) if config else None
        if _CONFIG:
            os.environ[_ENV_KEY] = json.dumps(_CONFIG, ensure_ascii=False)
        else:
            os.environ.pop(_ENV_KEY, None)


def get_vision_llm_config() -> dict | None:
    """取当前读图专用 LLM 配置的副本；未配置返回 None。

    优先用进程内注入值；子进程场景回落到继承的环境变量。
    """
    with _LOCK:
        if _CONFIG:
            return dict(_CONFIG)
    raw = os.environ.get(_ENV_KEY)
    if raw:
        try:
            cfg = json.loads(raw)
            if isinstance(cfg, dict) and cfg.get("api_key") and cfg.get("base_url") and cfg.get("model"):
                return cfg
        except Exception:
            return None
    return None
