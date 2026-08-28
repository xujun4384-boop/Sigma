"""
Sigma 后端服务
接收前端请求，通过 ToolLoop 处理 LLM 对话 + Skill 调用
支持按会话隔离的 TodoList + SessionState 持久化
支持上下文用量追踪与压缩
"""
import json
import os
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from skills.manager import SkillManager, ALL_SKILLS
from skills.todo_manager import TodoManager
from skills.project_memory import (
    ProjectScanTool, MemoryReadTool, MemoryRecordTool,
    _get_overview_path, _get_history_path, _ensure_memory_dir,
)

# Sigma 本体记忆路径（用于 network bridge 等非项目场景）
SIGMA_APP_DIR = Path(__file__).parent
SIGMA_MEMORY_DIR = SIGMA_APP_DIR / ".sigma" / "memory"

def _get_sigma_overview_path() -> Path:
    return SIGMA_MEMORY_DIR / "network_bridge_overview.md"

def _get_sigma_history_path() -> Path:
    return SIGMA_MEMORY_DIR / "network_bridge_history.md"

def _ensure_sigma_memory_dir():
    SIGMA_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
from context_manager import SessionState, ContextTracker, apply_model_specific_params
from tool_loop import ToolLoop, resolve_questionnaire, resolve_tool_timeout
from file_watcher import get_watcher
from network_bridge_manager import bridge_manager
from custom_agent_manager import custom_agent_manager


def _ensure_network_bridge_memory():
    """确保 network bridge 记忆文件存在，不存在则创建空模板。"""
    _ensure_sigma_memory_dir()
    overview_path = _get_sigma_overview_path()
    if not overview_path.exists():
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        overview_path.write_text(
            "# Network Bridge 概览\n"
            f"> 初始化时间: {now}\n\n"
            "此文件记录浏览器自动化任务的跨站点经验和模式。\n"
            "LLM 可通过 memory_read 读取，memory_update/memory_record 更新。\n\n"
            "## 常访问站点\n\n"
            "## 跨站点经验\n\n",
            encoding="utf-8",
        )
    history_path = _get_sigma_history_path()
    if not history_path.exists():
        history_path.write_text(
            "# Network Bridge 任务记录\n\n",
            encoding="utf-8",
        )
from sigma_logger import log

app = FastAPI(title="Sigma Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 按会话隔离的管理器（纯内存，重启即清空）
_todo_managers: dict[str, TodoManager] = {}
_session_states: dict[str, SessionState] = {}
_session_messages: dict[str, list] = {}
_cancel_events: dict[str, asyncio.Event] = {}


def _get_todo_manager(session_id: str) -> TodoManager:
    """获取或创建会话对应的 TodoManager"""
    if session_id not in _todo_managers:
        _todo_managers[session_id] = TodoManager(session_id)
    return _todo_managers[session_id]


def _get_session_state(session_id: str) -> SessionState:
    """获取或创建会话对应的 SessionState"""
    if session_id not in _session_states:
        _session_states[session_id] = SessionState()
    return _session_states[session_id]


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "sigma"}


@app.post("/api/custom-agents/sync")
async def sync_custom_agents(request: Request):
    """
    前端同步自定义 Agent 配置到后端内存。
    当用户在设置中增删改 Agent 时调用，全量同步。
    """
    body = await request.json()
    agents = body.get("agents", [])
    count = custom_agent_manager.sync(agents)
    return {"success": True, "count": count}


@app.get("/api/custom-agents")
async def list_custom_agents():
    """列出所有已同步的自定义 Agent（摘要信息）"""
    return {"agents": custom_agent_manager.list_all()}


@app.get("/api/available-skills")
async def get_available_skills():
    """返回所有可供自定义 Agent 选择的 Skill 列表（动态从 ALL_SKILLS 获取）。"""
    skills = []
    for name, info in ALL_SKILLS.items():
        skills.append({
            "name": name,
            "label": info.get("label", name),
            "tool_count": len(info.get("tool_names", [])),
            "tool_names": info.get("tool_names", []),
        })
    return {"skills": skills}


@app.post("/api/agent-ai-generate")
async def agent_ai_generate(request: Request):
    """
    AI 辅助生成/润色 Agent 的描述和提示词。
    复用当前主 LLM 配置，发送简单的非工具对话请求。
    """
    import httpx
    body = await request.json()
    base_url = (body.get("baseUrl") or "").rstrip("/")
    api_key = body.get("apiKey") or ""
    model = body.get("model") or ""
    protocol = body.get("protocol") or "anthropic"
    system_prompt = body.get("systemPrompt") or ""
    user_prompt = body.get("userPrompt") or ""

    if not base_url or not api_key or not model:
        return {"success": False, "error": "Missing LLM configuration"}
    if not user_prompt:
        return {"success": False, "error": "Missing userPrompt"}

    messages = []
    if system_prompt:
        messages.append({"role": "system" if protocol == "openai" else "user", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if protocol == "anthropic":
                # Anthropic 协议: system 作为顶层参数
                payload = {
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [m for m in messages if m.get("content")],
                }
                if system_prompt:
                    payload["system"] = system_prompt
                apply_model_specific_params(payload, model, "anthropic")
                resp = await client.post(
                    f"{base_url}/v1/messages",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            else:
                payload = {
                    "model": model,
                    "max_tokens": 1024,
                    "messages": [m for m in messages if m.get("content")],
                }
                apply_model_specific_params(payload, model, "openai")
                resp = await client.post(
                    f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "content-type": "application/json",
                    },
                    json=payload,
                )

            if resp.status_code != 200:
                error_text = (await resp.aread()).decode()[:300]
                return {"success": False, "error": f"LLM API error {resp.status_code}: {error_text}"}

            data = resp.json()
            if protocol == "anthropic":
                content = data.get("content", [])
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            else:
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""

            return {"success": True, "text": text.strip()}

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/init-project-memory")
async def init_project_memory(request: Request):
    """
    前端启动/切换目录时调用，生成项目文件地图。
    仅做目录遍历，不使用 LLM 标注（基于文件名的猜测不可靠）。
    """
    body = await request.json()
    working_dir = body.get("working_dir", "")

    if not working_dir or not os.path.isdir(working_dir):
        return {"scanned": False, "annotated": False, "error": "Invalid working_dir"}

    overview_path = _get_overview_path(working_dir)
    if overview_path.exists():
        return {"scanned": False, "annotated": False}

    from skills.project_memory import _walk_directory, _ensure_memory_dir as _ensure_mem

    wd = Path(working_dir)
    _ensure_mem(working_dir)
    listing, file_count = _walk_directory(wd)

    if not listing.strip():
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = f"# 项目概览\n> 自动扫描: {now}\n> 文件/目录总数: 0\n\n> 未发现可扫描的文件/目录\n"
        overview_path.write_text(content, encoding="utf-8")
        return {"scanned": True, "annotated": False, "file_count": 0}

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"# 项目概览\n> 自动扫描: {now}\n> 文件/目录总数: {file_count}\n\n{listing}\n"
    overview_path.write_text(content, encoding="utf-8")
    log.info(f"[Project Memory] 扫描完成: {overview_path} ({file_count} 条目)")

    return {"scanned": True, "annotated": False, "file_count": file_count}


@app.get("/api/watch-files")
async def watch_files(request: Request, dir: str = ""):
    """SSE 端点：监听工作目录中文件的外部变更并推送 diff 事件"""
    if not dir or not os.path.isdir(dir):
        return StreamingResponse(
            _empty_stream("Missing or invalid dir parameter"),
            media_type="text/event-stream",
        )

    watcher = get_watcher(dir)
    queue: asyncio.Queue = asyncio.Queue()
    unsubscribe = watcher.subscribe(queue)
    cancel_event = asyncio.Event()

    async def consumer():
        try:
            yield f"data: {json.dumps({'type': 'watcher_ready', 'dir': dir}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=10.0)
                except asyncio.TimeoutError:
                    if await request.is_disconnected():
                        cancel_event.set()
                        log.info("[FileWatcher] 客户端断开")
                        break
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            cancel_event.set()
            log.info("[FileWatcher] SSE 流关闭")
        finally:
            unsubscribe()

    return StreamingResponse(consumer(), media_type="text/event-stream")


async def _empty_stream(msg: str):
    yield f"data: {json.dumps({'type': 'error', 'message': msg}, ensure_ascii=False)}\n\n"


@app.post("/api/test-llm")
async def test_llm(request: Request):
    """测试 LLM 连接是否正常, 发送简单对话验证返回"""
    import httpx
    body = await request.json()
    base_url = (body.get("baseUrl") or "").rstrip("/")
    api_key = body.get("apiKey") or ""
    model = body.get("model") or ""
    protocol = body.get("protocol") or "anthropic"

    if not base_url or not api_key or not model:
        return {"success": False, "error": "Missing baseUrl, apiKey, or model"}

    log.info(f"[TestLLM] 测试连接: model={model}, base_url={base_url[:60]}, protocol={protocol}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if protocol == "anthropic":
                payload = {
                    "model": model,
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
                apply_model_specific_params(payload, model, protocol)
                request_url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
                log.info(
                    f"[TestLLM Debug] protocol={protocol} | request_url={request_url} | "
                    f"payload={json.dumps(payload, ensure_ascii=False)} | "
                    f"headers={{'Authorization': 'Bearer {api_key[:4]}...{api_key[-4:]} (len={len(api_key)})', "
                    f"'anthropic-version': '2023-06-01', 'content-type': 'application/json'}}"
                )
                resp = await client.post(
                    request_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
            else:
                # OpenAI 兼容协议
                payload = {
                    "model": model,
                    "max_tokens": 50,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
                apply_model_specific_params(payload, model, protocol)
                request_url = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
                log.info(
                    f"[TestLLM Debug] protocol={protocol} | request_url={request_url} | "
                    f"payload={json.dumps(payload, ensure_ascii=False)} | "
                    f"headers={{'Authorization': 'Bearer {api_key[:4]}...{api_key[-4:]} (len={len(api_key)})', "
                    f"'content-type': 'application/json'}}"
                )
                resp = await client.post(
                    request_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "content-type": "application/json",
                    },
                    json=payload,
                )

            if resp.status_code != 200:
                error_text = await resp.aread()
                error_msg = f"HTTP {resp.status_code}: {error_text.decode()[:200]}"
                log.warning(f"[TestLLM] 失败: {error_msg}")
                return {"success": False, "error": error_msg}

            data = resp.json()
            # 检查是否有文本回复
            if protocol == "anthropic":
                content = data.get("content", [])
                text = "".join(
                    b.get("text", b.get("thinking", ""))
                    for b in content if b.get("type") in ("text", "thinking")
                )
            else:
                choices = data.get("choices", [])
                msg = choices[0].get("message", {}) if choices else {}
                text = msg.get("content", "") or ""
                # DeepSeek 等推理模型可能把最终内容放在 reasoning_content
                if not text.strip():
                    text = msg.get("reasoning_content", "") or ""

            if text.strip():
                return {"success": True, "text": text.strip()}
            # 诊断日志：打印完整 message 结构帮助排查
            log.warning(
                f"[TestLLM] 空响应: model={model}, protocol={protocol}, "
                f"base_url={base_url}, "
                f"msg_keys={list(msg.keys()) if choices else 'no choices'}, "
                f"content_sample={repr(msg.get('content'))}, "
                f"reasoning_sample={repr(msg.get('reasoning_content', 'N/A'))[:100]}"
            )
            return {"success": False, "error": "LLM returned empty response"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/llm-balance")
async def llm_balance(request: Request):
    """查询 LLM 供应商账户实时余额或用量。支持 DeepSeek、Kimi Code、MiniMax。
    余额接口从用户配置的 baseUrl 推导，不硬编码官方域名。"""
    import httpx
    from urllib.parse import urljoin

    body = await request.json()
    provider = body.get("provider") or "generic"
    api_key = body.get("apiKey") or ""
    base_url = (body.get("baseUrl") or "").rstrip("/")

    if provider not in ("deepseek", "kimi-code", "minimax", "ark"):
        return {"success": False, "error": f"Provider '{provider}' does not support balance query"}
    if not api_key:
        return {"success": False, "error": "Missing API Key"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if provider == "deepseek":
                # sigma 中 DeepSeek 的 baseUrl 可能带 /anthropic 等 chat 路径后缀，
                # 余额接口固定为官方地址，因此使用硬编码 URL。
                url = "https://api.deepseek.com/user/balance"
            elif provider == "kimi-code":
                if not base_url:
                    return {"success": False, "error": "Missing base URL for Kimi Code"}
                url = urljoin(base_url + "/", "v1/usages")
            elif provider == "ark":
                # 火山引擎账单 QueryBalanceAcct 使用 HMAC-SHA256 签名，不走 Bearer Token
                # apiKey 字段传入格式为 "AK:SK"
                if ":" not in api_key:
                    return {"success": False, "error": "火山引擎余额查询需要 AK:SK 格式，例如 'AKLTxxx:WkRZxxx'"}
                ak, sk = api_key.split(":", 1)
                return await _query_volc_balance(client, ak, sk)
            else:
                # MiniMax 用量接口独立于 chat 域名，按官方文档固定为 www.minimaxi.com。
                # baseUrl 仅用于参考，应用真实接口走官方地址。
                url = "https://www.minimaxi.com/v1/token_plan/remains"

            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
            data = resp.json()
            if resp.status_code != 200:
                if provider == "deepseek":
                    error_msg = data.get("error", {}).get("message", "Unknown error")
                else:
                    error_msg = data.get("error", {}).get("message", "Unknown error") if isinstance(data, dict) and "error" in data else str(data)
                return {"success": False, "error": f"{provider} API error: {error_msg}"}
            # MiniMax 返回 { base_resp, model_remains: [...] }；如有 base_resp 则校验 status_code。
            if provider == "minimax" and isinstance(data, dict):
                base_resp = data.get("base_resp") or {}
                if base_resp.get("status_code") not in (0, None):
                    return {"success": False, "error": base_resp.get("status_msg") or f"minimax API error: {base_resp}"}
            return {"success": True, "balance": data}
    except httpx.TimeoutException:
        return {"success": False, "error": "Request timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _query_volc_balance(client: httpx.AsyncClient, ak: str, sk: str):
    """火山引擎 QueryBalanceAcct 余额查询（HMAC-SHA256 签名）"""
    import hashlib
    import hmac
    from datetime import datetime, timezone

    host = "billing.volcengineapi.com"
    region = "cn-beijing"
    service = "billing"
    action = "QueryBalanceAcct"
    version = "2022-01-01"

    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    # 步骤二：创建规范请求
    canonical_uri = "/"
    canonical_querystring = f"Action={action}&Version={version}"
    canonical_headers = f"host:{host}\nx-date:{x_date}\n"
    signed_headers = "host;x-date"
    payload_hash = hashlib.sha256(b"").hexdigest()  # GET 请求 body 为空

    canonical_request = (
        f"GET\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    # 步骤三：创建待签名字符串
    algorithm = "HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/request"
    string_to_sign = (
        f"{algorithm}\n{x_date}\n{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )

    # 步骤四：派生签名密钥
    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_secret = sk.encode()
    k_date = sign(k_secret, date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, service)
    k_signing = sign(k_service, "request")

    # 步骤五：计算签名
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    # 步骤六：构建 Authorization
    authorization = (
        f"{algorithm} Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    url = f"https://{host}/?Action={action}&Version={version}"
    resp = await client.get(
        url,
        headers={
            "Host": host,
            "X-Date": x_date,
            "Authorization": authorization,
        },
    )
    data = resp.json()

    if resp.status_code != 200:
        error = data.get("ResponseMetadata", {}).get("Error", {})
        return {"success": False, "error": f"火山引擎 API 错误: {error.get('Code', '')} {error.get('Message', str(data))}"}

    result = data.get("Result", {})
    return {
        "success": True,
        "balance": {
            "account_id": result.get("AccountID"),
            "available_balance": result.get("AvailableBalance"),
            "cash_balance": result.get("CashBalance"),
            "arrears_balance": result.get("ArrearsBalance"),
            "freeze_amount": result.get("FreezeAmount"),
            "credit_limit": result.get("CreditLimit"),
        }
    }


@app.post("/api/test-music")
async def test_music(request: Request):
    """测试 MiniMax 音乐模型是否可调用，不保存生成音频。"""
    import httpx

    body = await request.json()
    api_key = body.get("apiKey") or ""
    base_url = (body.get("baseUrl") or "https://api.minimaxi.com/v1").rstrip("/")
    model = body.get("model") or "music-3.0"
    if not api_key:
        return {"success": False, "error": "Missing MiniMax music API key"}

    payload = {
        "model": model,
        "prompt": "短小的钢琴纯音乐测试片段，明亮、舒缓",
        "is_instrumental": True,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/music_generation",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
        data = response.json()
        base_resp = data.get("base_resp") or {} if isinstance(data, dict) else {}
        if response.status_code >= 400 or base_resp.get("status_code") not in (0, None):
            message = base_resp.get("status_msg") or data.get("message") or str(data)
            return {"success": False, "error": f"{model}: {message}", "model": model, "status": response.status_code}
        return {"success": True, "model": model, "message": f"{model} 可调用", "response": data}
    except httpx.TimeoutException:
        return {"success": False, "error": f"{model}: request timeout"}
    except Exception as error:
        return {"success": False, "error": f"{model}: {error}"}


@app.post("/api/test-vision")
async def test_vision(request: Request):
    """测试 Vision API 连接，发送简单请求验证 Key 是否有效"""
    import httpx
    body = await request.json()
    api_key = body.get("apiKey") or ""
    model = body.get("model") or "kimi-for-coding"
    base_url = (body.get("baseUrl") or "https://api.moonshot.cn/anthropic").rstrip("/")

    # debug: 打印实际请求参数
    full_url = f"{base_url}/v1/messages"
    print(f"[test-vision] URL: {full_url}")
    print(f"[test-vision] Model: {model}")
    print(f"[test-vision] Key prefix: {api_key[:12]}...")

    if not api_key:
        return {"success": False, "error": "Missing API Key"}
    if not base_url:
        return {"success": False, "error": "Missing Base URL"}
    if not model:
        return {"success": False, "error": "Missing Model"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "model": model,
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            apply_model_specific_params(payload, model, "anthropic")
            resp = await client.post(
                full_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
            )
            print(f"[test-vision] Status: {resp.status_code}")
            if resp.status_code != 200:
                error_text = await resp.aread()
                print(f"[test-vision] Error body: {error_text.decode()[:300]}")
                return {"success": False, "error": f"HTTP {resp.status_code}: {error_text.decode()[:200]}"}
            data = resp.json()
            content = data.get("content", [])
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            print(f"[test-vision] Response: {text[:100]}")
            return {"success": True} if text.strip() else {"success": False, "error": "Vision API returned empty response"}
    except Exception as e:
        print(f"[test-vision] Exception: {e}")
        return {"success": False, "error": str(e)}


def _check_mail163_smtp(address: str, auth_code: str, host: str, port: int):
    """同步测试 SMTP 登录，返回 (ok, error)。"""
    import smtplib
    try:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(address, auth_code)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)


def _check_mail163_imap(address: str, auth_code: str, host: str, port: int):
    """同步测试 IMAP 登录并读取收件箱，返回 (ok, error)。"""
    import imaplib
    import traceback
    try:
        print(f"[test-mail163] IMAP connecting to {host}:{port}...")
        imap = imaplib.IMAP4_SSL(host, port)
        print(f"[test-mail163] IMAP login as {address}...")
        imap.login(address, auth_code)
        print(f"[test-mail163] IMAP login OK, sending ID command...")
        # 163 要求登录后发送 IMAP ID 命令 (RFC 2971)，否则 select 会被拦截为 "Unsafe Login"
        # 直接通过底层 socket 发送原始命令，绕过 imaplib 的参数引号转义
        tag = imap._new_tag()
        if isinstance(tag, bytes):
            tag = tag.decode()
        imap.send(f'{tag} ID ("name" "Sigma" "version" "1.0.0")\r\n'.encode("ascii"))
        tag_bytes = tag.encode("ascii")
        while True:
            line = imap.readline()
            if line.startswith(tag_bytes):
                break
        print(f"[test-mail163] IMAP ID OK, selecting INBOX...")
        typ, data = imap.select("INBOX", readonly=True)
        if typ != "OK":
            imap.logout()
            err_text = data[0].decode(errors="replace") if data and data[0] else str(data)
            if "Unsafe Login" in err_text:
                return False, (
                    "163 安全拦截：请先在网页端授权。"
                    "登录 163 网页邮箱 → 设置 → POP3/SMTP/IMAP → 检查「客户端授权」或「第三方客户端登录」开关，"
                    "或重新生成授权码后重试。原始错误: " + err_text
                )
            return False, f"登录成功但打开收件箱失败: {err_text}"
        imap.logout()
        return True, None
    except Exception as e:
        traceback.print_exc()
        return False, str(e)


@app.post("/api/test-mail163")
async def test_mail163(request: Request):
    """测试 163 邮箱连接，验证授权码及 SMTP/IMAP 服务是否可用"""
    body = await request.json()
    address = body.get("address") or ""
    auth_code = body.get("authCode") or ""
    smtp_host = body.get("smtpHost") or "smtp.163.com"
    imap_host = body.get("imapHost") or "imap.163.com"

    def _to_port(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    smtp_port = _to_port(body.get("smtpPort"), 465)
    imap_port = _to_port(body.get("imapPort"), 993)

    if not address or not auth_code:
        return {"success": False, "error": "缺少邮箱地址或授权码"}

    smtp_ok, smtp_err = await asyncio.to_thread(_check_mail163_smtp, address, auth_code, smtp_host, smtp_port)
    imap_ok, imap_err = await asyncio.to_thread(_check_mail163_imap, address, auth_code, imap_host, imap_port)

    print(f"[test-mail163] SMTP ok={smtp_ok} err={smtp_err}")
    print(f"[test-mail163] IMAP ok={imap_ok} err={imap_err}")

    if smtp_ok and imap_ok:
        return {"success": True, "detail": "SMTP 与 IMAP 均连接成功，授权码有效"}
    if smtp_ok:
        return {"success": True, "detail": f"SMTP 连接成功，但 IMAP 失败: {imap_err}"}
    if imap_ok:
        return {"success": True, "detail": f"IMAP 连接成功，但 SMTP 失败: {smtp_err}"}
    return {"success": False, "error": f"SMTP 与 IMAP 均连接失败。SMTP: {smtp_err}。IMAP: {imap_err}"}


def _check_wecom_email_smtp(address: str, auth_code: str, host: str, port: int):
    """同步测试企业微信邮箱 SMTP 登录，返回 (ok, error)。"""
    import smtplib
    try:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(address, auth_code)
        server.quit()
        return True, None
    except Exception as e:
        return False, str(e)


def _check_wecom_email_imap(address: str, auth_code: str, host: str, port: int):
    """同步测试企业微信邮箱 IMAP 登录并读取收件箱，返回 (ok, error)。"""
    import imaplib
    import traceback
    try:
        print(f"[test-wecom-email] IMAP connecting to {host}:{port}...")
        imap = imaplib.IMAP4_SSL(host, port)
        print(f"[test-wecom-email] IMAP login as {address}...")
        imap.login(address, auth_code)
        typ, data = imap.select("INBOX", readonly=True)
        if typ != "OK":
            imap.logout()
            err_text = data[0].decode(errors="replace") if data and data[0] else str(data)
            return False, f"登录成功但打开收件箱失败: {err_text}"
        imap.logout()
        return True, None
    except Exception as e:
        traceback.print_exc()
        return False, str(e)


@app.post("/api/test-wecom-email")
async def test_wecom_email(request: Request):
    """测试企业微信邮箱连接，验证授权码及 SMTP/IMAP 服务是否可用"""
    body = await request.json()
    address = body.get("address") or ""
    auth_code = body.get("authCode") or ""
    smtp_host = body.get("smtpHost") or "smtp.exmail.qq.com"
    imap_host = body.get("imapHost") or "imap.exmail.qq.com"

    def _to_port(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    smtp_port = _to_port(body.get("smtpPort"), 465)
    imap_port = _to_port(body.get("imapPort"), 993)

    if not address or not auth_code:
        return {"success": False, "error": "缺少邮箱地址或授权码"}

    smtp_ok, smtp_err = await asyncio.to_thread(_check_wecom_email_smtp, address, auth_code, smtp_host, smtp_port)
    imap_ok, imap_err = await asyncio.to_thread(_check_wecom_email_imap, address, auth_code, imap_host, imap_port)

    print(f"[test-wecom-email] SMTP ok={smtp_ok} err={smtp_err}")
    print(f"[test-wecom-email] IMAP ok={imap_ok} err={imap_err}")

    if smtp_ok and imap_ok:
        return {"success": True, "detail": "SMTP 与 IMAP 均连接成功，凭据有效"}
    if smtp_ok:
        return {"success": True, "detail": f"SMTP 连接成功，但 IMAP 失败: {imap_err}"}
    if imap_ok:
        return {"success": True, "detail": f"IMAP 连接成功，但 SMTP 失败: {smtp_err}"}
    return {"success": False, "error": f"SMTP 与 IMAP 均连接失败。SMTP: {smtp_err}。IMAP: {imap_err}"}


# ─── 项目记忆 ───

def _load_project_memory(working_dir: str) -> str:
    """加载项目记忆（overview + history），不存在时返回空字符串。"""
    parts = []
    overview_path = _get_overview_path(working_dir)
    if overview_path.exists():
        parts.append(overview_path.read_text(encoding="utf-8"))
    history_path = _get_history_path(working_dir)
    if history_path.exists():
        parts.append(history_path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


async def _record_task_memory(
    working_dir: str,
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    messages: list,
    protocol: str = "anthropic",
) -> None:
    """
    对话结束后，调用 LLM 判断是否有实质性任务进展，
    有则调用 memory_record 追加记录。
    """
    import httpx

    memory_dir = _get_overview_path(working_dir).parent
    if not memory_dir.exists():
        return  # 项目记忆未初始化，跳过

    # 提取关键信息给 LLM 判断
    summary_msgs = []
    for m in messages[-8:]:  # 只取最后 8 轮
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        text_parts.append(f"[调用 {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        c = block.get("content", "")
                        text_parts.append(f"[结果] {str(c)[:200]}")
                    elif block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            content = " ".join(text_parts)
        summary_msgs.append(f"{role}: {str(content)[:300]}")

    summary_text = "\n".join(summary_msgs)

    prompt = (
        "你是一个任务记录助手。判断以下对话中是否有实质性的任务进展（如：修改代码、创建文件、修复bug、"
        "分析文档等）。如果只是闲聊、问候或无实质操作，请回复 \"NO_TASK\"。\n\n"
        "如果有实质性进展，请用一句话总结做了什么（30字以内），并提供涉及的关键文件（如有），"
        "格式：TASK|summary|files\n\n"
        f"用户原始消息: {user_message[:200]}\n\n"
        f"对话摘要:\n{summary_text}"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if protocol == "openai":
                opened_url = f"{base_url.rstrip('/')}/v1/chat/completions" if "/v1" not in base_url else f"{base_url.rstrip('/')}/chat/completions"
                resp = await client.post(
                    opened_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 200,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": "你是一个简洁的任务摘要助手。"},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                text = text.strip()
            else:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/v1/messages",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 200,
                        "temperature": 0.3,
                        "system": "你是一个简洁的任务摘要助手。",
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                content = data.get("content", [])
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                text = text.strip()

            if not text or text == "NO_TASK":
                log.info("[Project Memory] 无实质性任务，跳过记录")
                return

            # 解析 TASK|summary|files
            if text.startswith("TASK|"):
                parts = text[5:].split("|", 1)
                summary = parts[0].strip()
                files = parts[1].strip() if len(parts) > 1 else ""
            else:
                summary = text[:50]
                files = ""

            # 调用 memory_record 写入
            record_tool = MemoryRecordTool(cwd=working_dir)
            result = record_tool.execute(
                working_dir=working_dir,
                summary=summary,
                files=files,
            )
            if result.success:
                log.info(f"[Project Memory] 任务已记录: {summary}")
            else:
                log.warning(f"[Project Memory] 记录失败: {result.content}")
    except Exception as e:
        log.warning(f"[Project Memory] 记录异常: {e}")


async def _record_network_bridge_memory(
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    messages: list,
    protocol: str = "anthropic",
) -> None:
    """Network bridge 任务完成后，记录到 Sigma 本体记忆 (.sigma/memory/)。"""
    import httpx

    _ensure_sigma_memory_dir()

    summary_msgs = []
    for m in messages[-8:]:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        text_parts.append(f"[调用 {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        c = block.get("content", "")
                        text_parts.append(f"[结果] {str(c)[:200]}")
                    elif block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
            content = " ".join(text_parts)
        summary_msgs.append(f"{role}: {str(content)[:300]}")

    summary_text = "\n".join(summary_msgs)

    prompt = (
        "你是一个浏览器自动化任务记录助手。判断以下对话中是否有实质性的浏览器任务进展"
        "（如：搜索信息、访问网站、填写表单、提取数据等）。"
        "如果只是闲聊或无实质操作，请回复 \"NO_TASK\"。\n\n"
        "如果有实质性进展，请用一句话总结（30字以内），"
        "格式：TASK|summary\n\n"
        f"用户原始消息: {user_message[:200]}\n\n"
        f"对话摘要:\n{summary_text}"
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if protocol == "openai":
                opened_url = f"{base_url.rstrip('/')}/v1/chat/completions" if "/v1" not in base_url else f"{base_url.rstrip('/')}/chat/completions"
                resp = await client.post(
                    opened_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 200,
                        "temperature": 0.3,
                        "messages": [
                            {"role": "system", "content": "你是一个简洁的任务摘要助手。"},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                text = text.strip()
            else:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/v1/messages",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 200,
                        "temperature": 0.3,
                        "system": "你是一个简洁的任务摘要助手。",
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                if resp.status_code != 200:
                    return
                data = resp.json()
                content = data.get("content", [])
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                text = text.strip()

            if not text or text == "NO_TASK":
                log.info("[NB Memory] 无实质性任务，跳过记录")
                return

            # 解析
            if text.startswith("TASK|"):
                summary = text[5:].split("|")[0].strip()
            else:
                summary = text[:50]

            # 写入 Sigma 本体 task_history
            history_path = _get_sigma_history_path()
            now = datetime.now().strftime("%H:%M")
            today = datetime.now().strftime("%Y-%m-%d")

            existing = history_path.read_text(encoding="utf-8") if history_path.exists() else ""

            record = f"- [{now}] {summary}"
            if not existing.strip():
                content = f"# Network Bridge 任务记录\n\n## {today}\n{record}\n"
            elif f"## {today}" in existing:
                lines = existing.split("\n")
                new_lines = []
                inserted = False
                in_today = False
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if line.strip() == f"## {today}":
                        in_today = True
                    elif in_today:
                        if line.strip().startswith("## ") and line.strip() != f"## {today}":
                            new_lines.insert(i, record)
                            inserted = True
                            in_today = False
                        elif i == len(lines) - 1:
                            new_lines.append(record)
                            inserted = True
                if not inserted and in_today:
                    new_lines.append(record)
                content = "\n".join(new_lines)
            else:
                parts = existing.split("\n", 2)
                content = f"{parts[0]}\n{parts[1]}\n\n## {today}\n{record}\n{parts[2] if len(parts) > 2 else ''}"

            history_path.write_text(content, encoding="utf-8")
            log.info(f"[NB Memory] 任务已记录: {summary}")
    except Exception as e:
        log.warning(f"[NB Memory] 记录异常: {e}")


async def _execute_custom_agent_chat(
    user_message: str,
    custom_agent: dict,
    config: dict,
    session_id: str,
    working_dir: str = "",
    backup_enabled: bool = True,
    max_turns: int = 8,
    request: Request | None = None,
):
    """
    @ 触发模式：使用自定义 Agent 执行任务（共享上下文）。
    
    Agent 能看到完整的对话历史，执行结果回注到会话中。
    """
    import httpx

    agent_name = custom_agent.get("name", "unknown")
    agent_system_prompt = custom_agent.get("system_prompt", "")
    agent_tools = custom_agent.get("tools", [])
    agent_model = custom_agent.get("model", "")

    # 优先使用 Agent 自己的 LLM 配置，回退到主配置
    base_url = (custom_agent.get("base_url") or config.get("baseUrl") or "https://api.kimi.com/coding").rstrip("/")
    api_key = custom_agent.get("api_key") or config.get("apiKey") or ""
    protocol = custom_agent.get("protocol") or config.get("protocol", "anthropic")
    main_model = config.get("model") or "kimi-for-coding"

    # Agent 使用自己的模型（如果有），否则用主模型
    model = agent_model or main_model

    if not api_key:
        return {"error": "API Key is required"}

    todo_manager = _get_todo_manager(session_id)
    session_state = _get_session_state(session_id)
    existing_messages = _session_messages.get(session_id, [])

    skill_keys = config.get("skillKeys", {}) or {}
    # 调试日志：确认前端是否传入了微信密钥（@ 触发模式）
    wechat_appid_val = skill_keys.get("wechatAppId", "")
    wechat_appsecret_val = skill_keys.get("wechatAppSecret", "")
    log.info(
        f"[SkillKeys] received (@agent) | wechatAppId={'***' if wechat_appid_val else '(空)'} "
        f"wechatAppSecret={'***' if wechat_appsecret_val else '(空)'} "
        f"skillKeys keys={list(skill_keys.keys())}"
    )
    skill_mgr_cwd = working_dir if working_dir and os.path.isdir(working_dir) else "."

    # 创建 SkillManager，仅暴露 Agent 允许的工具（加上只读工具和任务管理工具用于内部）
    all_tool_names = set(agent_tools) | {"read", "read_docx", "read_pdf", "read_xlsx", "read_pptx", "todo_write"}
    # 对 LLM 暴露的有效工具集：Agent 选择的工具 + 基础工具（todo_write）
    _BASE_TOOLS = {"todo_write"}
    effective_tools = set(agent_tools) | _BASE_TOOLS
    skill_manager = SkillManager(
        cwd=skill_mgr_cwd,
        web_search_provider=skill_keys.get("webSearchProvider", "kimi"),
        web_search_api_key=skill_keys.get("webSearchApiKey", ""),
        web_search_base_url=skill_keys.get("webSearchBaseUrl", ""),
        tavily_api_key=skill_keys.get("tavilyApiKey", ""),
        image_gen_provider=skill_keys.get("imageGenProvider", "ark"),
        image_gen_api_key=skill_keys.get(
            "imageMinimaxApiKey" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkApiKey",
            skill_keys.get("imageGenApiKey", ""),
        ),
        image_gen_base_url=skill_keys.get(
            "imageMinimaxBaseUrl" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkBaseUrl",
            skill_keys.get("imageGenBaseUrl", "https://ark.cn-beijing.volces.com/api/v3"),
        ),
        image_gen_model=skill_keys.get(
            "imageMinimaxModel" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkModel",
            skill_keys.get("imageGenModel", ""),
        ),
        music_gen_api_key=skill_keys.get("musicGenApiKey", ""),
        music_gen_base_url=skill_keys.get("musicGenBaseUrl", "https://api.minimaxi.com/v1"),
        music_gen_model=skill_keys.get("musicGenModel", "music-3.0"),
        minimax_video_api_key=skill_keys.get("minimaxVideoApiKey", ""),
        vision_api_key=skill_keys.get("visionApiKey", ""),
        vision_model=skill_keys.get("visionModel", "kimi-for-coding"),
        vision_base_url=skill_keys.get("visionBaseUrl", "https://api.moonshot.cn/anthropic"),
        wechat_appid=skill_keys.get("wechatAppId", ""),
        wechat_appsecret=skill_keys.get("wechatAppSecret", ""),
        wechat_relay_url=skill_keys.get("wechatRelayUrl", ""),
        wechat_relay_key=skill_keys.get("wechatRelayKey", ""),
        fengniao_api_key=skill_keys.get("fengniaoApiKey", ""),
        flyai_api_key=skill_keys.get("flyaiApiKey", ""),
        baidu_map_auth_token=skill_keys.get("baiduMapAuthToken", ""),
        mail163_address=skill_keys.get("mail163Address", ""),
        mail163_auth_code=skill_keys.get("mail163AuthCode", ""),
        mail163_smtp_host=skill_keys.get("mail163SmtpHost", ""),
        mail163_smtp_port=skill_keys.get("mail163SmtpPort", ""),
        mail163_imap_host=skill_keys.get("mail163ImapHost", ""),
        mail163_imap_port=skill_keys.get("mail163ImapPort", ""),
        wecom_email_address=skill_keys.get("wecomEmailAddress", ""),
        wecom_email_auth_code=skill_keys.get("wecomEmailAuthCode", ""),
        wecom_email_smtp_host=skill_keys.get("wecomEmailSmtpHost", ""),
        wecom_email_smtp_port=skill_keys.get("wecomEmailSmtpPort", ""),
        wecom_email_imap_host=skill_keys.get("wecomEmailImapHost", ""),
        wecom_email_imap_port=skill_keys.get("wecomEmailImapPort", ""),
        llm_config={
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "protocol": protocol,
        },
        todo_manager=todo_manager,
        backup_enabled=backup_enabled,
    )

    log.info(
        f"[CustomAgent Chat] name={agent_name} | model={model} | base_url={base_url[:60]}... "
        f"| tools={agent_tools} | history={len(existing_messages)} msgs"
    )

    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    _cancel_events[session_id] = cancel_event

    async def producer():
        client = None
        try:
            client = httpx.AsyncClient(timeout=120)

            # 构建共享上下文消息：system = agent的prompt，历史 = 对话历史 + 当前用户消息
            messages = []
            # 添加 Agent 的 system prompt（末尾追加当前工作目录，与主 LLM 一致）
            if agent_system_prompt:
                prompt = agent_system_prompt
                if working_dir and os.path.isdir(working_dir):
                    prompt += f"\n\n[当前工作目录: {working_dir}]"
                messages.append({"role": "system", "content": prompt})

            # 添加历史对话（共享上下文）
            for msg in existing_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                text_parts.append(f"[调用工具: {block.get('name', '')}]")
                    content = " ".join(text_parts)
                if content:
                    messages.append({"role": role, "content": str(content)})

            # 添加当前用户消息
            messages.append({"role": "user", "content": user_message})

            # Agent 执行循环
            turn_count = 0
            final_content = ""

            await queue.put({
                "type": "agent_start",
                "agent_name": agent_name,
                "tools": agent_tools,
                "model": model,
            })

            while turn_count < max_turns:
                turn_count += 1

                await queue.put({
                    "type": "agent_turn",
                    "agent_name": agent_name,
                    "turn": turn_count,
                    "status": "thinking",
                })

                # 构建工具 schema（包含 todo_write 等基础工具）
                tools_schema = []
                for tool_name in effective_tools:
                    try:
                        inst = skill_manager._get_instance(tool_name)
                        tools_schema.append(inst.to_anthropic_tool())
                    except Exception:
                        pass

                # 调用 LLM
                log.info(f"[CustomAgent Chat] Turn {turn_count}: calling LLM (msgs={len(messages)}, tools={len(tools_schema)})")
                if protocol == "anthropic":
                    body = {
                        "model": model,
                        "max_tokens": 16384,
                        "messages": _convert_agent_messages_anthropic(messages),
                    }
                    if tools_schema:
                        body["tools"] = tools_schema
                    resp = await client.post(
                        f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "anthropic-version": "2023-06-01",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code != 200:
                        log.warning(f"[CustomAgent Chat] HTTP {resp.status_code}: {resp.text[:300]}")
                        await queue.put({"type": "error", "message": f"LLM 请求失败 (HTTP {resp.status_code})"})
                        return
                    data = resp.json()
                    content_blocks = data.get("content", [])
                    text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
                    tool_calls = []
                    for block in content_blocks:
                        if block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "input": block.get("input", {}),
                            })
                else:
                    body = {
                        "model": model,
                        "max_tokens": 16384,
                        "messages": _convert_agent_messages_openai(messages),
                    }
                    if tools_schema:
                        body["tools"] = tools_schema
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                    if resp.status_code != 200:
                        log.warning(f"[CustomAgent Chat] HTTP {resp.status_code}")
                        await queue.put({"type": "error", "message": f"LLM 请求失败 (HTTP {resp.status_code})"})
                        return
                    data = resp.json()
                    choice = (data.get("choices") or [{}])[0]
                    message = choice.get("message", {})
                    text = message.get("content", "")
                    raw_tool_calls = message.get("tool_calls", [])
                    tool_calls = [
                        {"id": tc.get("id", ""), "name": tc.get("function", {}).get("name", ""),
                         "input": json.loads(tc.get("function", {}).get("arguments", "{}"))}
                        for tc in raw_tool_calls
                    ]

                if text:
                    await queue.put({
                        "type": "text",
                        "content": text,
                        "contentType": "response_text",
                    })

                if not tool_calls:
                    final_content = text
                    break

                # 添加 assistant 消息
                assistant_entry = {"role": "assistant", "content": text or ""}
                if tool_calls:
                    anthropic_tool_calls = []
                    for tc in tool_calls:
                        anthropic_tool_calls.append({
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["input"])},
                        })
                    assistant_entry["tool_calls"] = anthropic_tool_calls
                messages.append(assistant_entry)

                # 执行工具
                for tc in tool_calls:
                    tool_name = tc["name"]
                    await queue.put({
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "tool_input": tc["input"],
                    })

                    if tool_name not in effective_tools:
                        result_text = f"无权使用工具: {tool_name}"
                        success = False
                    else:
                        try:
                            result = await asyncio.to_thread(skill_manager.dispatch, tool_name, **tc["input"])
                            result_text = result.content[:8000]
                            success = result.success
                        except Exception as e:
                            result_text = f"工具执行失败: {e}"
                            success = False

                    await queue.put({
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "content": result_text,
                        "success": success,
                    })

                    # 工具结果消息
                    messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": tc["id"],
                            "content": result_text,
                        }],
                    })

            # 达到最大轮次但未产出最终文本 → 追加一次无工具调用，强制生成总结
            if turn_count >= max_turns and not final_content:
                log.info(f"[CustomAgent Chat] Max turns reached ({max_turns}), forcing final summary without tools")
                try:
                    # 添加提示让 LLM 生成总结
                    messages.append({
                        "role": "user",
                        "content": "你已达到最大执行轮次。请根据以上所有工具执行结果，总结最终答案给用户。"
                    })
                    if protocol == "anthropic":
                        summary_body = {
                            "model": model,
                            "max_tokens": 4096,
                            "messages": _convert_agent_messages_anthropic(messages),
                        }
                        summary_resp = await client.post(
                            f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "anthropic-version": "2023-06-01",
                                "Content-Type": "application/json",
                            },
                            json=summary_body,
                        )
                        if summary_resp.status_code == 200:
                            summary_data = summary_resp.json()
                            final_content = "".join(
                                b.get("text", "") for b in summary_data.get("content", []) if b.get("type") == "text"
                            )
                    else:
                        summary_body = {
                            "model": model,
                            "max_tokens": 4096,
                            "messages": _convert_agent_messages_openai(messages),
                        }
                        summary_resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json=summary_body,
                        )
                        if summary_resp.status_code == 200:
                            summary_data = summary_resp.json()
                            choice = (summary_data.get("choices") or [{}])[0]
                            final_content = choice.get("message", {}).get("content", "")
                    if final_content:
                        await queue.put({
                            "type": "text",
                            "content": final_content,
                            "contentType": "response_text",
                        })
                except Exception as e:
                    log.warning(f"[CustomAgent Chat] Summary call failed: {e}")

            # Agent 完成
            await queue.put({
                "type": "agent_complete",
                "agent_name": agent_name,
                "turns": turn_count,
            })

            # 将 Agent 结果存入会话消息
            agent_assistant_msg = {
                "role": "assistant",
                "content": f"[@{agent_name}] {final_content or '(executed tool calls)'}",
            }
            _session_messages[session_id] = existing_messages + [
                {"role": "user", "content": user_message},
                agent_assistant_msg,
            ]

        except Exception as e:
            import traceback
            log.error(f"[CustomAgent Chat Error] {type(e).__name__}: {e}\n{traceback.format_exc()}")

            # 优雅降级：保留已生成的内容，注入错误提示
            if not final_content:
                final_content = f"（Agent 执行异常: {e}）"
            else:
                final_content += f"\n\n（Agent 中途异常: {e}）"

            await queue.put({
                "type": "text",
                "content": final_content,
                "contentType": "response_text",
            })
            await queue.put({
                "type": "agent_complete",
                "agent_name": agent_name,
                "turns": turn_count,
            })

            # 将 Agent 部分结果存入会话消息
            agent_assistant_msg = {
                "role": "assistant",
                "content": f"[@{agent_name}] {final_content}",
            }
            _session_messages[session_id] = existing_messages + [
                {"role": "user", "content": user_message},
                agent_assistant_msg,
            ]
        finally:
            await queue.put({"type": "chat_complete"})
            _cancel_events.pop(session_id, None)
            if client:
                await client.aclose()

    producer_task = asyncio.create_task(producer())

    async def consumer():
        try:
            yield f"data: {json.dumps({'type': 'started'}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if request and await request.is_disconnected():
                        cancel_event.set()
                        break
                    continue
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                if chunk["type"] in ("chat_complete", "error"):
                    break
        except GeneratorExit:
            cancel_event.set()
        finally:
            if not producer_task.done():
                producer_task.cancel()

    return StreamingResponse(consumer(), media_type="text/event-stream")


def _convert_agent_messages_anthropic(messages: list) -> list:
    """将内部消息格式转换为 Anthropic API 格式"""
    result = []
    for m in messages:
        role = m["role"]
        if role == "system":
            result.append({"role": "system", "content": m["content"]})
        elif role == "assistant":
            entry = {"role": "assistant", "content": []}
            if m.get("content"):
                entry["content"].append({"type": "text", "text": m["content"]})
            if m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    func = tc.get("function", {})
                    entry["content"].append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")),
                    })
            result.append(entry)
        elif role == "user" and isinstance(m.get("content"), list):
            entry = {"role": "user", "content": []}
            for item in m["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    entry["content"].append({
                        "type": "tool_result",
                        "tool_use_id": item["tool_use_id"],
                        "content": item["content"],
                    })
            result.append(entry)
        else:
            result.append({"role": "user", "content": str(m.get("content", ""))})
    return result


def _convert_agent_messages_openai(messages: list) -> list:
    """将内部消息格式转换为 OpenAI API 格式"""
    result = []
    for m in messages:
        role = m["role"]
        if role == "assistant":
            entry = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("tool_calls"):
                entry["tool_calls"] = m["tool_calls"]
            result.append(entry)
        elif role == "user" and isinstance(m.get("content"), list):
            for item in m["content"]:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    result.append({"role": "tool", "content": item["content"]})
        else:
            result.append({"role": role, "content": str(m.get("content", ""))})
    return result


async def _execute_chat(
    user_message: str,
    config: dict,
    session_id: str,
    max_iterations: int = 10,
    sub_agent_max_turns: int = 8,
    working_dir: str = "",
    workspace_dirs: list | None = None,
    backup_enabled: bool = True,
    extra_context: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    language: str = "zh",
    request: Request | None = None,
):
    """核心 chat 执行逻辑，供 /api/chat 和 /api/panel-chat 共用。"""
    # 注入额外上下文（如浏览器标签页信息、工作目录等）
    ctx_parts = []
    if working_dir:
        ctx_parts.append(f"[主工作目录: {working_dir}]")
    if workspace_dirs and len(workspace_dirs) > 1:
        ctx_parts.append(f"[附加工件区目录: {', '.join(d for d in workspace_dirs if d != working_dir)}]")
    if extra_context:
        ctx_parts.extend(extra_context)
    if ctx_parts:
        user_message = f"{chr(10).join(ctx_parts)}\n\n{user_message}"

    base_url = (config.get("baseUrl") or "https://api.kimi.com/coding").rstrip("/")
    api_key = config.get("apiKey") or ""
    model = config.get("model") or "kimi-for-coding"
    provider = config.get("provider") or "generic"
    llm_params = {
        "provider": provider,
        "thinking": config.get("thinking") or ("enabled" if provider == "minimax" else None),
        "context_size": config.get("contextSize") or (1_000_000 if provider == "minimax" else None),
        "max_tokens": config.get("maxTokens") or (32768 if provider == "minimax" else None),
        "temperature": config.get("temperature") if config.get("temperature") is not None else (1.0 if provider == "minimax" else None),
        "top_p": config.get("topP") if config.get("topP") is not None else (0.95 if provider == "minimax" else None),
    }

    if not api_key:
        return {"error": "API Key is required"}

    # 缓存 LLM 配置，供浏览器扩展面板使用
    protocol = config.get("protocol", "anthropic")
    config_name = config.get("name") or model
    bridge_manager.register_llm_config(
        name=config_name,
        base_url=base_url,
        api_key=api_key,
        model=model,
        protocol=protocol,
        active=True,
    )
    # 推送最新配置到已连接的浏览器扩展
    asyncio.create_task(bridge_manager._push_llm_configs())

    # 同步 skillKeys，供浏览器扩展复用主程序完整配置
    skill_keys = config.get("skillKeys", {}) or {}
    bridge_manager.register_skill_keys(skill_keys)

    # ── 同步 vision 配置，供 network_bridge analyze_screenshot 使用 ──
    vision_api_key = skill_keys.get("visionApiKey", "")
    vision_model = skill_keys.get("visionModel", "")
    vision_base_url = skill_keys.get("visionBaseUrl", "")
    if vision_api_key:
        bridge_manager.register_vision_config(
            api_key=vision_api_key,
            model=vision_model or "kimi-for-coding",
            base_url=vision_base_url or "https://api.moonshot.cn/anthropic",
        )
        log.info(f"[Vision] 已同步 vision 配置到 Bridge: model={vision_model or 'kimi-for-coding'}")

    # ── 同步自定义 Agent：从每次请求的 config 中读取并同步到内存 ──
    custom_agents_raw = config.get("customAgents", [])
    llm_configs_raw = config.get("llms", [])
    if custom_agents_raw:
        agents_for_sync = []
        for a in custom_agents_raw:
            # 解析 Agent 的 LLM 配置
            llm_config = None
            llm_config_id = a.get("llmConfigId", "")
            if llm_config_id:
                for llm in llm_configs_raw:
                    if llm.get("id") == llm_config_id:
                        llm_config = {
                            "base_url": llm.get("baseUrl", ""),
                            "api_key": llm.get("apiKey", ""),
                            "model": llm.get("model", ""),
                            "protocol": llm.get("protocol", "anthropic"),
                        }
                        break
            agents_for_sync.append({
                "name": a.get("name", ""),
                "description": a.get("description", ""),
                "system_prompt": a.get("systemPrompt", ""),
                "tools": a.get("tools", []),
                "model": llm_config.get("model") if llm_config else a.get("model", ""),
                "capabilities": a.get("capabilities", []),
                "llm_config": llm_config,
            })
        custom_agent_manager.sync(agents_for_sync)

    todo_manager = _get_todo_manager(session_id)
    session_state = _get_session_state(session_id)
    context_tracker = ContextTracker(model, llm_params["context_size"])
    existing_messages = _session_messages.get(session_id, [])

    skill_keys = config.get("skillKeys", {}) or {}
    # 调试日志：确认前端是否传入了微信密钥
    wechat_appid_val = skill_keys.get("wechatAppId", "")
    wechat_appsecret_val = skill_keys.get("wechatAppSecret", "")
    log.info(
        f"[SkillKeys] received | wechatAppId={'***' if wechat_appid_val else '(空)'} "
        f"wechatAppSecret={'***' if wechat_appsecret_val else '(空)'} "
        f"wechatRelayUrl={'***' if skill_keys.get('wechatRelayUrl', '') else '(空)'} "
        f"skillKeys keys={list(skill_keys.keys())}"
    )
    skill_mgr_cwd = working_dir if working_dir and os.path.isdir(working_dir) else "."
    skill_manager = SkillManager(
        cwd=skill_mgr_cwd,
        web_search_provider=skill_keys.get("webSearchProvider", "kimi"),
        web_search_api_key=skill_keys.get("webSearchApiKey", ""),
        web_search_base_url=skill_keys.get("webSearchBaseUrl", ""),
        tavily_api_key=skill_keys.get("tavilyApiKey", ""),
        image_gen_provider=skill_keys.get("imageGenProvider", "ark"),
        image_gen_api_key=skill_keys.get(
            "imageMinimaxApiKey" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkApiKey",
            skill_keys.get("imageGenApiKey", ""),
        ),
        image_gen_base_url=skill_keys.get(
            "imageMinimaxBaseUrl" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkBaseUrl",
            skill_keys.get("imageGenBaseUrl", "https://ark.cn-beijing.volces.com/api/v3"),
        ),
        image_gen_model=skill_keys.get(
            "imageMinimaxModel" if skill_keys.get("imageGenProvider") == "minimax" else "imageArkModel",
            skill_keys.get("imageGenModel", ""),
        ),
        music_gen_api_key=skill_keys.get("musicGenApiKey", ""),
        music_gen_base_url=skill_keys.get("musicGenBaseUrl", "https://api.minimaxi.com/v1"),
        music_gen_model=skill_keys.get("musicGenModel", "music-3.0"),
        minimax_video_api_key=skill_keys.get("minimaxVideoApiKey", ""),
        vision_api_key=skill_keys.get("visionApiKey", ""),
        vision_model=skill_keys.get("visionModel", "kimi-for-coding"),
        vision_base_url=skill_keys.get("visionBaseUrl", "https://api.moonshot.cn/anthropic"),
        wechat_appid=skill_keys.get("wechatAppId", ""),
        wechat_appsecret=skill_keys.get("wechatAppSecret", ""),
        wechat_relay_url=skill_keys.get("wechatRelayUrl", ""),
        wechat_relay_key=skill_keys.get("wechatRelayKey", ""),
        fengniao_api_key=skill_keys.get("fengniaoApiKey", ""),
        flyai_api_key=skill_keys.get("flyaiApiKey", ""),
        baidu_map_auth_token=skill_keys.get("baiduMapAuthToken", ""),
        mail163_address=skill_keys.get("mail163Address", ""),
        mail163_auth_code=skill_keys.get("mail163AuthCode", ""),
        mail163_smtp_host=skill_keys.get("mail163SmtpHost", ""),
        mail163_smtp_port=skill_keys.get("mail163SmtpPort", ""),
        mail163_imap_host=skill_keys.get("mail163ImapHost", ""),
        mail163_imap_port=skill_keys.get("mail163ImapPort", ""),
        wecom_email_address=skill_keys.get("wecomEmailAddress", ""),
        wecom_email_auth_code=skill_keys.get("wecomEmailAuthCode", ""),
        wecom_email_smtp_host=skill_keys.get("wecomEmailSmtpHost", ""),
        wecom_email_smtp_port=skill_keys.get("wecomEmailSmtpPort", ""),
        wecom_email_imap_host=skill_keys.get("wecomEmailImapHost", ""),
        wecom_email_imap_port=skill_keys.get("wecomEmailImapPort", ""),
        llm_config={
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "protocol": config.get("protocol", "anthropic"),
        },
        todo_manager=todo_manager,
        backup_enabled=backup_enabled,
        enabled_skills=enabled_skills,
    )
    skill_manager.sub_agent_max_turns = sub_agent_max_turns

    tool_loop = ToolLoop(
        base_url=base_url,
        api_key=api_key,
        model=model,
        skill_manager=skill_manager,
        max_iterations=max_iterations,
        todo_manager=todo_manager,
        session_state=session_state,
        context_tracker=context_tracker,
        session_id=session_id,
        tool_timeout=int(config.get("toolTimeout", 300)),
        protocol=config.get("protocol", "anthropic"),
        language=language,
        llm_params=llm_params,
    )

    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    _cancel_events[session_id] = cancel_event

    async def producer():
        log.info(f"[Chat Request] session={session_id}, model={model}, history={len(existing_messages)} msgs")
        is_network_bridge = not working_dir and enabled_skills and "network_bridge" in enabled_skills
        try:
            # ── 项目记忆：兜底检查（启动时已通过 /api/init-project-memory 扫描） ──
            if working_dir and os.path.isdir(working_dir):
                overview_path = _get_overview_path(working_dir)
                if not overview_path.exists():
                    # 极端情况：启动时未扫描（如 working_dir 在启动后才变更），补扫
                    log.info(f"[Project Memory] 兜底扫描: {working_dir}")
                    from skills.project_memory import _walk_directory, _ensure_memory_dir as _ensure_mem
                    wd = Path(working_dir)
                    _ensure_mem(working_dir)
                    listing, file_count = _walk_directory(wd)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    if listing.strip():
                        content = f"# 项目概览\n> 自动扫描: {now}\n> 文件/目录总数: {file_count}\n\n{listing}\n"
                    else:
                        content = f"# 项目概览\n> 自动扫描: {now}\n> 文件/目录总数: 0\n\n> 未发现可扫描的文件/目录\n"
                    overview_path.write_text(content, encoding="utf-8")
                    log.info(f"[Project Memory] 兜底扫描完成: {overview_path} ({file_count} 条目)")

            # ── Network Bridge 记忆：首次使用时初始化 ──
            if is_network_bridge:
                _ensure_network_bridge_memory()

            await tool_loop.run(user_message, queue, existing_messages, cancel_event)
            _session_messages[session_id] = tool_loop.messages

            # ── 对话结束后记录任务 ──
            if is_network_bridge:
                await _record_network_bridge_memory(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    user_message=user_message,
                    messages=tool_loop.messages,
                    protocol=protocol,
                )
            elif working_dir and os.path.isdir(working_dir):
                await _record_task_memory(
                    working_dir=working_dir,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    user_message=user_message,
                    messages=tool_loop.messages,
                    protocol=protocol,
                )
        except Exception as e:
            log.error(f"[Chat Error] {e}")
        finally:
            await queue.put({"type": "chat_complete"})
            log.info("[Chat Complete]")
            _cancel_events.pop(session_id, None)

    producer_task = asyncio.create_task(producer())

    async def consumer():
        try:
            yield f"data: {json.dumps({'type': 'started'}, ensure_ascii=False)}\n\n"
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if request and await request.is_disconnected():
                        cancel_event.set()
                        log.info("[Chat Cancelled] Client disconnected")
                        break
                    continue
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                if chunk["type"] == "questionnaire":
                    log.info(f"[SSE] 问卷已发送到前端: {chunk.get('title', '')[:50]}")
                if chunk["type"] in ("chat_complete", "error"):
                    break
        except GeneratorExit:
            cancel_event.set()
            log.info("[Chat Cancelled] SSE stream closed")
        finally:
            # 确保 producer_task 被取消，避免断开后任务继续跑
            if not producer_task.done():
                producer_task.cancel()
                try:
                    await producer_task
                except asyncio.CancelledError:
                    pass
            _cancel_events.pop(session_id, None)

    return StreamingResponse(consumer(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    user_message = body.get("message", "")
    if not user_message:
        return {"error": "Message cannot be empty"}

    # @ 触发模式：直接使用自定义 Agent 执行
    custom_agent_config = body.get("custom_agent")
    if custom_agent_config and isinstance(custom_agent_config, dict):
        return await _execute_custom_agent_chat(
            user_message=user_message,
            custom_agent=custom_agent_config,
            config=body.get("config", {}),
            session_id=body.get("sessionId", "default"),
            working_dir=body.get("working_dir", ""),
            backup_enabled=body.get("backupEnabled", True),
            max_turns=int(body.get("subAgentMaxTurns", 8)),
            request=request,
        )

    return await _execute_chat(
        user_message=user_message,
        config=body.get("config", {}),
        session_id=body.get("sessionId", "default"),
        max_iterations=int(body.get("maxIterations", 10)),
        sub_agent_max_turns=int(body.get("subAgentMaxTurns", 8)),
        working_dir=body.get("working_dir", ""),
        workspace_dirs=body.get("workspace_dirs", []),
        backup_enabled=body.get("backupEnabled", True),
        language=body.get("language", "zh"),
        request=request,
    )


@app.post("/api/panel-chat")
async def panel_chat(request: Request):
    """浏览器扩展面板专用：通过 configName 查找缓存的完整配置。"""
    body = await request.json()
    user_message = body.get("message", "")
    if not user_message:
        return {"error": "Message cannot be empty"}

    config_name = body.get("configName", "")
    cfg = bridge_manager.get_llm_config(config_name)
    if not cfg:
        return {"error": f"未找到 LLM 配置: {config_name}，请先在主程序发送一条消息"}

    config = {
        "baseUrl": cfg["baseUrl"],
        "apiKey": cfg["apiKey"],
        "model": cfg["model"],
        "protocol": cfg.get("protocol", "anthropic"),
    }

    # 注入浏览器标签页上下文 + 插件专用强制规则
    extra_context = [
        "[系统规则: 浏览器扩展面板只能使用 network_bridge skill。当用户要求访问网站或查询信息时，你必须先调用 get_bookmarks 搜索浏览器收藏夹；只有收藏夹中找不到匹配站点时，才允许 navigate 到通用搜索引擎或默认网站。优先使用收藏夹里的真实 URL，不要根据名称猜测 URL。]"
    ]
    tab_title = body.get("tabTitle", "")
    tab_url = body.get("tabUrl", "")
    if tab_title:
        extra_context.append(f"[当前标签页标题: {tab_title}]")
    if tab_url:
        extra_context.append(f"[当前标签页URL: {tab_url}]")

    return await _execute_chat(
        user_message=user_message,
        config=config,
        session_id=body.get("session_id", "sigma-panel"),
        max_iterations=bridge_manager.get_max_iterations(),
        extra_context=extra_context if extra_context else None,
        enabled_skills=["network_bridge"],
        request=request,
    )


@app.post("/api/user-answer")
async def user_answer(request: Request):
    """接收前端提交的 ask_user 问卷答案，解析阻塞中的 tool_loop"""
    body = await request.json()
    request_id = body.get("request_id", "")
    answers = body.get("answers", [])

    if not request_id:
        return {"success": False, "error": "Missing request_id"}

    resolved = resolve_questionnaire(request_id, answers)
    if resolved:
        log.info(f"[UserAnswer] request_id={request_id}, {len(answers)} answers")
        return {"success": True}
    else:
        return {"success": False, "error": "No pending questionnaire found or already answered"}


@app.post("/api/tool-timeout-answer")
async def tool_timeout_answer(request: Request):
    """接收前端提交的工具超时选择（继续等待/后台运行/取消）。"""
    body = await request.json()
    request_id = body.get("request_id", "")
    choice = body.get("choice", "")

    if not request_id:
        return {"success": False, "error": "Missing request_id"}
    if choice not in ("wait", "background", "cancel"):
        return {"success": False, "error": "Invalid choice, must be wait/background/cancel"}

    resolved = resolve_tool_timeout(request_id, choice)
    if resolved:
        log.info(f"[ToolTimeout] request_id={request_id}, choice={choice}")
        return {"success": True}
    else:
        return {"success": False, "error": "No pending tool timeout found or already answered"}


@app.post("/api/stop-task")
async def stop_task(request: Request):
    """取消指定会话正在运行的任务。"""
    body = await request.json()
    session_id = body.get("session_id", "default")
    cancel_event = _cancel_events.get(session_id)
    if cancel_event:
        cancel_event.set()
        log.info(f"[Stop Task] session={session_id}")
        return {"success": True}
    return {"success": False, "error": "No active task for this session"}


# ─── Network Bridge：浏览器扩展通信 ───


@app.websocket("/ws/browser")
async def ws_browser(websocket: WebSocket):
    """浏览器扩展 WebSocket 连接端点。"""
    await bridge_manager.handle_connection(websocket)


@app.get("/api/network-bridge/status")
async def network_bridge_status():
    """查询浏览器扩展连接状态。"""
    return {
        "running": True,
        "extension_connected": bridge_manager.is_connected,
    }


@app.post("/api/network-bridge/command")
async def network_bridge_command(request: Request):
    """接收来自 skill 的浏览器操作命令，转发给扩展并返回结果。

    请求体: {"action": str, "args": dict, "session": str (optional)}
    响应: 扩展返回的完整 JSON
    """
    body = await request.json()
    action = body.get("action", "")
    args = body.get("args", {})

    if not action:
        return {"success": False, "error": "缺少 action 参数"}

    try:
        result = await bridge_manager.send_command(action, args)
        return result
    except ConnectionError as e:
        return {"success": False, "error": str(e)}
    except TimeoutError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"桥接异常: {str(e)}"}

@app.get("/api/network-bridge/llm-configs")
async def network_bridge_llm_configs():
    """返回缓存的 LLM 配置列表（apiKey 已脱敏）。"""
    return {
        "configs": bridge_manager.get_llm_config_list(),
    }


@app.post("/api/network-bridge/sync-configs")
async def network_bridge_sync_configs(request: Request):
    """接收主程序前端同步的 LLM 配置列表和 Vision 配置。"""
    body = await request.json()
    llms = body.get("llms", [])
    if not llms:
        return {"success": False, "error": "llms 不能为空"}

    count = 0
    for entry in llms:
        name = entry.get("name", entry.get("model", ""))
        base_url = entry.get("baseUrl", "")
        api_key = entry.get("apiKey", "")
        model = entry.get("model", "")
        protocol = entry.get("protocol", "anthropic")
        if name and api_key and base_url:
            bridge_manager.register_llm_config(
                name=name,
                base_url=base_url,
                api_key=api_key,
                model=model,
                protocol=protocol,
            )
            count += 1

    # 同步 skillKeys 配置
    skill_keys = body.get("skillKeys") or {}
    bridge_manager.register_skill_keys(skill_keys)

    # 同步 vision 配置
    vision = body.get("vision") or {}
    bridge_manager.register_vision_config(
        api_key=vision.get("apiKey", ""),
        model=vision.get("model", ""),
        base_url=vision.get("baseUrl", ""),
    )

    # 同步最大工具调用轮次
    max_iterations = body.get("maxIterations", 0)
    if max_iterations > 0:
        bridge_manager.set_max_iterations(max_iterations)

    # 推送更新到浏览器扩展
    await bridge_manager._push_llm_configs()

    return {"success": True, "synced": count}


@app.get("/api/network-bridge/vision-config")
async def network_bridge_vision_config():
    """返回当前缓存的 Vision 配置（供 skill 本地调用）。"""
    config = bridge_manager.get_vision_config()
    if not config:
        return {"success": False, "error": "Vision 配置未同步，请在主程序 Settings 中配置 vision key"}
    return {"success": True, "config": config}


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "sigma.config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"backendPort": 8765, "frontendPort": 5173}

if __name__ == "__main__":
    import uvicorn
    config = load_config()
    port = config.get("backendPort", 8765)
    log.info(f"[Server Start] Sigma starting on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
