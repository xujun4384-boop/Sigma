"""
火山引擎「端到端实时语音大模型-全双工版本」(Seeduplex) 中转服务。

前端通过 /ws/voice WebSocket 连接本服务，本服务桥接到火山
wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue，
负责 JSON 事件收发、音频 Base64 编解码，并在前后端之间转发音频流。

职责划分（全双工 FC 架构）：
- 语音模型只承担「听 + 说 + 闲聊 + 判断任务是否完成」。
- 需要执行任务时，语音模型通过 Function Calling 调用 run_task，
  本服务转交主 Sigma /api/chat 执行，把结果通过
  conversation.item.create(role=tool) 回传进语音模型上下文。
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
import websockets
from fastapi import WebSocket, WebSocketDisconnect

import voice_memory
import voice_bridge
from voice_task_coordinator import VoiceTask, VoiceTaskCoordinator
from voice_logger import vlog as logger

# ────────────────────────────────────────────────────────────
# 协议常量
# ────────────────────────────────────────────────────────────
VOLC_BASE_URL = "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
VOLC_MODEL = "1.2.6.1"

# 语音模型暴露给 Function Calling 的工具：只有一个 run_task，把实际执行交给主 Sigma
RUN_TASK_TOOL = {
    "type": "function",
    "name": "run_task",
    "description": (
        "把用户要执行的任务交给 Sigma 主智能体处理并返回最终结果。"
        "当用户提出查询、搜索、读写文件、写代码、生成内容等一切需要实际执行的任务时，"
        "都必须调用此工具；只有闲聊、问候、无需执行的简单问答才直接回答。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "完整、清晰的任务描述，供主智能体理解和执行",
            },
        },
        "required": ["description"],
    },
}

SYSTEM_PROMPT = (
    "你是 SIGMA，徐总的专属智能助手，徐总是你的唯一主人。\n"
    "你的职责：自然、专业地陪徐总聊天；当徐总提出需要实际操作的任务时，"
    "调用 run_task 工具把任务交给系统执行，拿到结果后再用自然语言向徐总汇报。\n"
    "对于闲聊、问候、简单问答，直接回答即可，不要调用工具。"
)


class VolcRealtimeClient:
    """火山全双工实时语音客户端（JSON 协议）。"""

    def __init__(self, api_key: str, speaker: str = "zh_male_yunzhou_jupiter_bigtts",
                 input_format: str = "pcm", output_format: str = "pcm_s16le"):
        self.api_key = api_key
        self.speaker = speaker
        self.input_format = input_format
        self.output_format = output_format
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.session_id = str(uuid.uuid4())
        self.dialog_id: Optional[str] = None
        self._event_id = 0

    def new_event_id(self) -> str:
        self._event_id += 1
        return f"event_{self._event_id}"

    def _headers(self) -> Dict[str, str]:
        return {"X-Api-Key": self.api_key}

    async def connect(self) -> None:
        self.ws = await websockets.connect(
            VOLC_BASE_URL,
            additional_headers=self._headers(),
            ping_interval=None,
        )

    async def send(self, event: Dict[str, Any]) -> None:
        assert self.ws is not None
        await self.ws.send(json.dumps(event, ensure_ascii=False))

    async def recv(self) -> Dict[str, Any]:
        assert self.ws is not None
        raw = await self.ws.recv()
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def session_create_event(self) -> Dict[str, Any]:
        session: Dict[str, Any] = {
            "id": self.session_id,
            "model": VOLC_MODEL,
            "instructions": SYSTEM_PROMPT,
            "audio": {
                "input": {
                    "format": {"type": self.input_format, "rate": 16000},
                },
                "output": {
                    "format": {"type": self.output_format, "rate": 24000},
                    "voice": self.speaker,
                },
            },
            "tools": [RUN_TASK_TOOL],
        }
        extension = {
            "asr": {"extra": {}},
            "tts": {"extra": {}},
            "dialog": {
                "extra": {
                    "audit_response": "抱歉，这个问题我无法回答，你可以换个其他话题，我会尽力为你提供帮助。",
                    "enable_loudness_norm": True,
                    "enable_music": False,
                },
            },
        }
        return {
            "type": "session.create",
            "event_id": self.new_event_id(),
            "session": session,
            "extension": extension,
        }

    async def send_audio(self, audio: bytes) -> None:
        b64 = base64.b64encode(audio).decode("ascii")
        await self.send({"type": "input_audio_buffer.append", "audio": b64})

    async def return_tool_result(self, call_id: str, text: str) -> None:
        await self.send({
            "type": "conversation.item.create",
            "event_id": self.new_event_id(),
            "items": [
                {
                    "type": "message",
                    "role": "tool",
                    "call_id": call_id,
                    "content": [{"type": "input_text", "text": text}],
                },
            ],
        })

    async def speech_text_replacement(self, text: str) -> None:
        """干预模型回复：直接指定文本合成音频，不依赖 FC call_id（用于结果插播）。"""
        speech_id = str(uuid.uuid4())
        await self.send({
            "type": "speech_text_buffer.replacement.append",
            "event_id": self.new_event_id(),
            "speech_id": speech_id,
            "text": text,
        })
        await self.send({
            "type": "speech_text_buffer.replacement.commit",
            "event_id": self.new_event_id(),
            "speech_id": speech_id,
            "text": text,
        })

    async def session_close(self) -> None:
        await self.send({"type": "session.close", "event_id": self.new_event_id()})

    async def close(self) -> None:
        if self.ws is None:
            return
        try:
            await self.ws.close()
        except Exception:
            pass
        self.ws = None


async def _get_backend_url() -> str:
    """主 Sigma 后端地址（供 run_task 调用 /api/chat）。"""
    port = os.environ.get("SIGMA_BACKEND_PORT", "8765")
    return f"http://127.0.0.1:{port}"


def _voice_cfg() -> Dict[str, str]:
    """读取语音记忆配置（embedding + 摘录 LLM）。"""
    cfg_path = voice_memory.MEMORY_DIR / "config.json"
    file_cfg: Dict[str, Any] = {}
    try:
        if cfg_path.exists():
            file_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        file_cfg = {}

    def pick(env_key: str, file_key: str, default: str = "") -> str:
        return os.environ.get(env_key) or file_cfg.get(file_key, default) or default

    return {
        "embed_base_url": pick("EMBED_BASE_URL", "embedBaseUrl"),
        "embed_api_key": pick("EMBED_API_KEY", "embedApiKey"),
        "embed_model": pick("EMBED_MODEL", "embedModel", "text-embedding-3-small"),
        "llm_base_url": pick("VOICE_LLM_BASE_URL", "voiceLlmBaseUrl"),
        "llm_api_key": pick("VOICE_LLM_API_KEY", "voiceLlmApiKey"),
        "llm_model": pick("VOICE_LLM_MODEL", "voiceLlmModel"),
    }


EXTRACT_PROMPT = (
    "你是一个记忆摘录助手。下面是一段用户（徐总）和语音助手 SIGMA 的对话记录。\n"
    "请只提取值得长期记住的信息，包括：身份/称呼、偏好/习惯、明确要求 SIGMA 记住的事实、有后续性的计划或约定。\n"
    "忽略普通问答、闲聊、一次性指令、无信息量的应答。\n"
    "若有值得记的内容，逐条输出简短事实句，每条一行；若没有，只输出「无」。\n\n"
    "对话记录：\n{conversation}"
)


async def _extract_and_store_facts(session_qas: List[Dict[str, str]], cfg: Dict[str, str]) -> None:
    """会话结束：把 QA 发给主 LLM 摘录事实，向量化后写入长期记忆。"""
    if not session_qas:
        return
    if not (cfg["llm_base_url"] and cfg["llm_api_key"] and cfg["llm_model"]):
        logger.info("[voice] 未配置摘录 LLM，跳过长期记忆摘录")
        return
    if not (cfg["embed_base_url"] and cfg["embed_api_key"]):
        logger.info("[voice] 未配置 embedding，跳过长期记忆写入")
        return

    convo = "\n".join(
        f"徐总：{qa.get('user','')}\nSIGMA：{qa.get('assistant','')}" for qa in session_qas
    ).strip()
    if not convo:
        return

    body = {
        "model": cfg["llm_model"],
        "messages": [{"role": "user", "content": EXTRACT_PROMPT.format(conversation=convo)}],
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as http:
            resp = await http.post(
                f"{cfg['llm_base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['llm_api_key']}", "Content-Type": "application/json"},
                json=body,
            )
            data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
    except Exception as e:
        logger.warning("[voice] 摘录 LLM 调用失败: %s", e)
        return

    text = text.strip()
    if not text or text == "无":
        logger.info("[voice] 本次会话无值得长期记住的内容")
        return
    facts = [ln.strip("-•* ").strip() for ln in text.splitlines() if ln.strip() and ln.strip() != "无"]
    added = voice_memory.save_long_term_facts(
        facts, cfg["embed_base_url"], cfg["embed_api_key"], cfg["embed_model"]
    )
    logger.info("[voice] 长期记忆新增 %d 条", added)


async def voice_ws_handler(websocket: WebSocket) -> None:
    """FastAPI WebSocket 端点：前端 <-> 火山全双工实时语音中转。"""
    await websocket.accept()

    client: Optional[VolcRealtimeClient] = None
    upstream_task: Optional[asyncio.Task] = None
    downstream_task: Optional[asyncio.Task] = None
    session_qas: List[Dict[str, str]] = []
    # 本次语音通话复用的主 Sigma 会话 id，让多次 run_task 共享同一份工作上下文
    sigma_session_id = f"voice-{uuid.uuid4().hex[:8]}"

    try:
        # 等待前端首条 JSON 控制消息（含 API Key）
        first = await websocket.receive_text()
        cfg = json.loads(first)
        api_key = cfg.get("apiKey", "")
        speaker = cfg.get("speaker", "zh_male_yunzhou_jupiter_bigtts")
        output_format = cfg.get("outputFormat", "pcm_s16le")

        if not api_key:
            await websocket.send_text(json.dumps({"type": "error", "message": "缺少火山 API Key"}))
            return

        client = VolcRealtimeClient(api_key, speaker=speaker, output_format=output_format)
        await client.connect()
        await client.send(client.session_create_event())

        # 等待 session.created 拿到 dialog id
        while True:
            data = await client.recv()
            if data.get("type") == "session.created":
                sess = data.get("session") or {}
                client.dialog_id = sess.get("id") or data.get("session_id") or data.get("id")
                logger.info("[voice] 语音会话建立 speaker=%s dialog=%s", speaker, client.dialog_id)
                await websocket.send_text(json.dumps({"type": "ready"}))
                break
            if data.get("type") == "error":
                await websocket.send_text(json.dumps({"type": "error", "message": str(data)}))
                return

        cur_user = ""
        cur_assistant = ""

        async def deliver_task_result(task: VoiceTask) -> bool:
            """在语音空闲时交付任务摘要。

            - call_id 仍有效：走 conversation.item.create 回传，让模型理解并自然回复。
            - call_id 已因用户打断失效：走 speech_text_buffer.replacement 主动插播。
            """
            try:
                if task.call_valid:
                    for cid in [task.call_id] + task.extra_call_ids:
                        await client.return_tool_result(cid, task.summary)
                    logger.info("[voice] 任务摘要已回传 call_ids=%s", [task.call_id] + task.extra_call_ids)
                else:
                    await client.speech_text_replacement(task.summary)
                    logger.info("[voice] 任务摘要已插播（call_id 失效）task=%s", task.id)
                return True
            except Exception as e:
                logger.warning("[voice] 任务摘要交付失败 task=%s: %s", task.id, e)
                return False

        coordinator = VoiceTaskCoordinator(deliver_task_result)

        def _flush_qa():
            nonlocal cur_user, cur_assistant
            if cur_user or cur_assistant:
                session_qas.append({"user": cur_user, "assistant": cur_assistant})
                logger.info("[voice] QA 配对 | 徐总: %s | SIGMA: %s", cur_user[:40], cur_assistant[:40])
                cur_user, cur_assistant = "", ""

        async def upstream():
            """前端 -> 火山：把 16k PCM 原始字节转 Base64 后发 input_audio_buffer.append。"""
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    await client.send_audio(msg["bytes"])
                elif msg.get("text") is not None:
                    try:
                        cmd = json.loads(msg["text"])
                    except Exception:
                        continue
                    if cmd.get("type") == "stop":
                        break

        async def downstream():
            """火山 -> 前端：解析 JSON 事件，转发音频，处理 FC，捕获转录用于记忆。"""
            nonlocal cur_user, cur_assistant
            while True:
                data = await client.recv()
                event_type = data.get("type", "")

                # 模型开始播报：等待播报结束后才能交付下一项结果
                if event_type == "response.output_audio.started":
                    await coordinator.set_assistant_speaking(True)
                    continue

                # 模型一轮音频合成结束：标记空闲，触发下一条待播结果交付
                if event_type == "response.output_audio.done":
                    await coordinator.set_assistant_speaking(False)
                    continue

                # 一轮交互结束（比 output_audio.done 更可靠）：同样标记模型播报结束
                if event_type == "response.done":
                    await coordinator.set_assistant_speaking(False)
                    continue

                # 音频：Base64 解码成 PCM 原始字节转发前端
                if event_type == "response.output_audio.delta":
                    b64 = data.get("audio") or data.get("delta") or ""
                    if b64:
                        try:
                            audio = base64.b64decode(b64)
                            await websocket.send_bytes(audio)
                        except Exception:
                            pass
                    continue

                # 用户开口首字：通知前端打断当前播报，并标记进行中的 FC call_id 失效
                if event_type == "conversation.item.input_audio_transcription.started":
                    await coordinator.set_user_speaking(True)
                    coordinator.mark_active_calls_invalid()
                    try:
                        await websocket.send_text(json.dumps({"type": "interrupt"}))
                    except Exception:
                        pass
                    continue

                # 用户说话最终文本
                if event_type == "conversation.item.input_audio_transcription.completed":
                    await coordinator.set_user_speaking(False)
                    text = (data.get("transcript") or data.get("text") or data.get("content") or "").strip()
                    if text:
                        if cur_assistant:
                            _flush_qa()
                        cur_user = text
                        logger.info("[voice] ASR 定稿: %s", cur_user[:60])
                    continue

                # 模型回复文本（增量/结束）
                if event_type == "response.output_text.done":
                    text = (data.get("text") or data.get("content") or "").strip()
                    if text:
                        cur_assistant = text
                        _flush_qa()
                        logger.info("[voice] Chat 定稿: %s", cur_assistant[:60])
                    continue

                # Function Calling：模型请求执行 run_task（后台执行，不阻塞接收循环）
                if event_type == "response.function_call_arguments.done":
                    asyncio.create_task(_handle_function_call(data, client))
                    continue

                if event_type == "error":
                    logger.warning("[voice] server error: %s", data)
                    await websocket.send_text(json.dumps({"type": "error", "message": str(data)}))
                    continue

                # 未识别事件：打 debug，便于定位 output_audio.done / response.done 等是否到达
                logger.debug("[voice] 未处理事件 type=%s data=%s", event_type, str(data)[:200])

        async def _handle_function_call(data: Dict[str, Any], client: VolcRealtimeClient) -> None:
            """处理模型发来的 FC：解析 run_task 参数 -> 调主 Sigma -> 回传结果。"""
            items = data.get("items") or []
            if not items:
                # 兼容顶层 call_id 结构
                items = [data]

            for item in items:
                call_id = item.get("call_id", "")
                name = item.get("name", "")
                arguments = item.get("arguments", "{}")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except Exception:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}

                if name != "run_task":
                    logger.warning("[voice] 收到未注册的工具调用: %s", name)
                    await client.return_tool_result(call_id, f"未注册的工具：{name}")
                    continue

                description = (arguments.get("description") or "").strip()
                if not description:
                    await client.return_tool_result(call_id, "任务描述为空")
                    continue

                logger.info("[voice] FC 调用 run_task: %s", description[:50])

                # 去重：用户插话后语音模型可能对同一任务重复发起 FC，复用已有任务，避免并行重复执行
                existing = coordinator.find_running(description)
                if existing is not None:
                    coordinator.attach_call_id(existing.id, call_id)
                    logger.info("[voice] FC 重复，复用任务 %s", existing.id)
                    continue

                task = coordinator.register(description, call_id)

                async def on_event(event: Dict[str, Any]) -> None:
                    """把主 Sigma 的过程事件实时转发给前端语音弹窗。"""
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "task_event",
                            "task_id": task.id,
                            "event": event,
                        }))
                    except Exception:
                        pass

                backend_url = await _get_backend_url()
                result = await voice_bridge.run_task(
                    description, backend_url, on_event=on_event, session_id=sigma_session_id
                )
                # 完整结果只存主 Sigma 会话；语音模型收到的是主 LLM 生成的简明摘要。
                summary = await voice_bridge.summarize_for_voice(result)
                await coordinator.complete(task.id, result, summary)

        async def flush_loop():
            """兜底轮询：每 0.5s 尝试交付待播结果，避免事件驱动遗漏导致结果卡在队列。"""
            while True:
                await asyncio.sleep(0.5)
                await coordinator.flush_if_idle()

        upstream_task = asyncio.create_task(upstream())
        downstream_task = asyncio.create_task(downstream())
        flush_task = asyncio.create_task(flush_loop())

        done, pending = await asyncio.wait(
            {upstream_task, downstream_task, flush_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("[voice] handler error: %s", e)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        for task in (upstream_task, downstream_task, flush_task):
            if task and not task.done():
                task.cancel()
        if client is not None:
            try:
                await client.session_close()
            except Exception:
                pass
            await client.close()
        logger.info("[voice] 语音会话结束，本轮共 %d 个 QA", len(session_qas))
        try:
            await _extract_and_store_facts(session_qas, _voice_cfg())
        except Exception as e:
            logger.warning("[voice] 摘录长期记忆失败: %s", e)


def register(app) -> None:
    """在 FastAPI app 上注册语音 WebSocket 路由。"""
    @app.websocket("/ws/voice")
    async def _voice_ws(websocket: WebSocket):
        await voice_ws_handler(websocket)
