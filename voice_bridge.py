"""
语音 → 主 Sigma 桥接（全双工 Function Calling 版）。

语音模型（Seeduplex）通过 Function Calling 调用 run_task 时，本模块负责把
任务转交给主 Sigma /api/chat 执行，并返回最终文本结果。结果由 voice_chat 通过
conversation.item.create(role=tool) 回传进语音模型上下文，语音模型再据此回复。

与旧版相比：不再有 [交接任务] 标记解析、后台任务队列、待播队列这些中间态，
任务执行完成后结果直接回到语音模型的对话上下文里。
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict

import httpx

from network_bridge_manager import bridge_manager
from voice_logger import vlog as logger


def _load_working_dir() -> str:
    """从 sigma.config.json 读取当前工作目录，让主 Sigma 在项目上下文中工作。"""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "sigma.config.json")
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("workingDirectory", "") or ""
    except Exception:
        return ""


async def run_task(description: str, backend_url: str, on_event=None, session_id: str = None) -> str:
    """把任务交给主 Sigma /api/chat 执行，返回最终文本结果。

    on_event: 可选异步回调，用于把主 Sigma 的过程事件（思考/工具/回复）实时转发出去。
    session_id: 主 Sigma 会话 id；同一语音通话应复用同一个 id，使主 LLM 跨多次 run_task 累积工作上下文。
    """
    llm_cfg = bridge_manager.get_active_llm_config()
    if not llm_cfg:
        logger.warning("[voice.bridge] 无主 LLM 配置，无法执行 run_task")
        return "主 LLM 未配置，暂时无法执行任务。"

    config: Dict[str, Any] = {
        "baseUrl": llm_cfg.get("baseUrl", ""),
        "apiKey": llm_cfg.get("apiKey", ""),
        "model": llm_cfg.get("model", ""),
        "protocol": llm_cfg.get("protocol", "anthropic"),
        "skillKeys": bridge_manager.get_skill_keys(),
    }
    body = {
        "message": description,
        "config": config,
        "sessionId": session_id or f"voice-task-{uuid.uuid4().hex[:8]}",
        "working_dir": _load_working_dir(),
    }

    text_parts: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream(
                "POST", f"{backend_url}/api/chat", json=body
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        chunk = json.loads(line[5:].strip())
                    except Exception:
                        continue
                    if on_event is not None:
                        try:
                            await on_event(chunk)
                        except Exception:
                            pass
                    ctype = chunk.get("type")
                    if ctype in ("text", "content", "delta"):
                        # 跳过主 LLM 的思考过程，只保留最终响应文本
                        if chunk.get("contentType") == "thinking":
                            continue
                        piece = chunk.get("text") or chunk.get("content") or ""
                        if piece:
                            text_parts.append(piece)
                    elif ctype == "chat_complete":
                        break
                    elif ctype == "error":
                        return f"任务执行出错：{chunk.get('message', '未知错误')}"
    except Exception as e:
        logger.warning("[voice.bridge] run_task 失败: %s", e)
        return f"任务执行失败：{e}"

    result = "".join(text_parts).strip()
    logger.info("[voice.bridge] run_task 完成，返回 %d 字", len(result))
    return result or "任务已完成，但未返回文本结果。"


def _fallback_summary(text: str, max_chars: int = 200) -> str:
    """无 LLM 时的兜底摘要：规则截断，避免把数千字结果直接塞给语音模型。"""
    flat = " ".join((text or "").split())
    if not flat:
        return "任务已完成，但没有返回可播报的文本结果。"
    if len(flat) <= max_chars:
        return flat
    cut = max(flat.rfind(mark, 0, max_chars) for mark in ("。", "！", "？", "；", "\n"))
    if cut < max_chars // 2:
        cut = max_chars
    return f"{flat[:cut + 1].rstrip()}。完整结果已保留，您可以继续问我具体部分。"


async def summarize_for_voice(text: str, max_chars: int = 200) -> str:
    """用主 LLM 把任务结果压成适合语音播报的简明总结。

    语音场景下，主 LLM 与文字输入的展开式回答分离：这里只回传一句话关键结论，
    完整结果仍保存在主 Sigma 会话中，供用户追问细节时继续复用。
    """
    if not text:
        return "任务已完成，但没有返回可播报的文本结果。"
    if len(text) <= max_chars:
        return text

    llm_cfg = bridge_manager.get_active_llm_config()
    if not llm_cfg:
        return _fallback_summary(text, max_chars)

    base_url = (llm_cfg.get("baseUrl") or "").rstrip("/")
    api_key = llm_cfg.get("apiKey") or ""
    model = llm_cfg.get("model") or ""
    protocol = llm_cfg.get("protocol", "anthropic")
    if not (base_url and api_key and model):
        return _fallback_summary(text, max_chars)

    prompt = (
        "请把下面的任务结果压缩成适合语音播报的一段话：简明扼要、只保留关键结论，"
        f"不超过 {max_chars} 字，去掉过程与冗余细节。\n\n任务结果：\n{text}"
    )
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            if protocol == "openai":
                url = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
                resp = await http.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
                )
                data = resp.json()
                summary = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            else:
                url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
                resp = await http.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={"model": model, "max_tokens": 512, "messages": [{"role": "user", "content": prompt}]},
                )
                data = resp.json()
                summary = "".join(
                    b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
                )
        summary = summary.strip()
        if summary:
            logger.info("[voice.bridge] 已生成语音摘要 %d 字", len(summary))
            return summary
    except Exception as e:
        logger.warning("[voice.bridge] 语音摘要生成失败: %s", e)
    return _fallback_summary(text, max_chars)
