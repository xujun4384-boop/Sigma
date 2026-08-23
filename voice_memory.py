"""
语音对话记忆模块（独立于主 LLM 链路）。

仅保留长期记忆：会话结束后，把 QA 交给主 LLM 摘录事实句，向量化后存本地 JSON，
供后续跨会话检索使用。会话内的短期上下文由全双工语音模型自身维护（对话上下文 +
dialog_id 接续），不再需要本模块维护 short_term。

存储位置：项目目录 `.sigma/voice/` 下。
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from datetime import datetime, date
from pathlib import Path
from typing import List

from voice_logger import vlog as logger

MEMORY_DIR = Path(__file__).parent / ".sigma" / "voice"
LONG_TERM_FILE = MEMORY_DIR / "long_term.json"


def _ensure_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("[voice.memory] read %s failed: %s", path.name, e)
    return default


def _write_json(path: Path, data) -> None:
    _ensure_dir()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ════════════════════════════════════════════════════════════
#  长期记忆（向量）
# ════════════════════════════════════════════════════════════

def _relative_time(ts_ms: int) -> str:
    """把存储时间戳换算成相对描述（今天/昨天/N天前/N周前/N个月前/N年前）。"""
    stored = datetime.fromtimestamp(ts_ms / 1000).date()
    today = date.today()
    days = (today - stored).days
    if days <= 0:
        return "今天"
    if days == 1:
        return "昨天"
    if days == 2:
        return "前天"
    if days < 7:
        return f"{days}天前"
    if days < 30:
        return f"{days // 7}周前"
    if days < 365:
        return f"{days // 30}个月前"
    return f"{days // 365}年前"


def _embed(texts: List[str], base_url: str, api_key: str, model: str) -> List[List[float]]:
    """调用 OpenAI 兼容 embedding 接口。"""
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/embeddings",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [item["embedding"] for item in data.get("data", [])]


def save_long_term_facts(facts: List[str], base_url: str, api_key: str, model: str) -> int:
    """把主 LLM 摘录的事实句向量化并存入长期记忆。返回新增条数。"""
    facts = [f.strip() for f in facts if f and f.strip()]
    if not facts:
        return 0
    try:
        vectors = _embed(facts, base_url, api_key, model)
    except Exception as e:
        logger.warning("[voice.memory] embed failed: %s", e)
        return 0

    store = _read_json(LONG_TERM_FILE, [])
    now = int(time.time() * 1000)
    for fact, vec in zip(facts, vectors):
        store.append({"fact": fact, "embedding": vec, "ts": now})
    _write_json(LONG_TERM_FILE, store)
    return len(facts)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_long_term(query: str, base_url: str, api_key: str, model: str,
                     top_k: int = 5, min_score: float = 0.3) -> List[str]:
    """检索相关长期记忆，返回带相对时间描述的事实句。"""
    store = _read_json(LONG_TERM_FILE, [])
    if not store:
        return []
    try:
        qvec = _embed([query], base_url, api_key, model)[0]
    except Exception as e:
        logger.warning("[voice.memory] query embed failed: %s", e)
        return []

    scored = [(item, _cosine(qvec, item.get("embedding", []))) for item in store]
    scored = [s for s in scored if s[1] >= min_score]
    scored.sort(key=lambda s: s[1], reverse=True)

    results = []
    for item, _score in scored[:top_k]:
        rel = _relative_time(item.get("ts", 0))
        results.append(f"[{rel}] {item.get('fact', '')}")
    return results


def long_term_count() -> int:
    return len(_read_json(LONG_TERM_FILE, []))
