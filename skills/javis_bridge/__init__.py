"""
Javis Bridge Skill — Sigma 与另一台电脑上的 Javis 智能体跨机沟通。

双方不直接互联，而是通过阿里云中转服务器收发消息与文件：
  Sigma  ──HTTP──▶  中转服务器  ◀──HTTP──  Javis
消息按单调递增的消息 id 做游标消费；附件先上传拿到 file_id，再随消息发送。

配置（任一来源，优先级：Settings → .env）：
  javisBridgeUrl / JAVIS_BRIDGE_URL    中转服务器根地址，如 http://1.2.3.4:8888
  javisBridgeKey / JAVIS_BRIDGE_KEY    双方共享的访问密钥
  javisAgentId   / JAVIS_AGENT_ID      本机身份，默认 Sigma（大小写敏感）
  javisPeerId    / JAVIS_PEER_ID       对端身份，默认 javis
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from sigma_logger import log
from skills.base import BaseTool, ToolParameter, ToolResult

SIGMA_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = SIGMA_ROOT / ".sigma" / "javis_bridge_state.json"
DEFAULT_AGENT = "Sigma"
DEFAULT_PEER = "javis"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 30
POLL_TIMEOUT_MAX = 120

# 跨机咨询会话协议
END_MARKER = "[[END]]"
SOFT_ROUND_LIMIT = 6    # 第 6 轮起提示收尾
HARD_ROUND_LIMIT = 12   # 第 12 轮强制追加 [[END]]
CONSULT_POLL_WAIT = 10  # 咨询时单次长轮询秒数（短一点以便及时响应取消）
CONSULT_DEFAULT_IDLE = 180
CONSULT_MAX_SECONDS = 30 * 60
LLM_TIMEOUT = 120


class JavisBridgeError(RuntimeError):
    pass


class JavisBridgeTool(BaseTool):
    name = "javis_bridge"
    description = (
        "与另一台电脑上的 Javis 智能体跨机沟通（经阿里云中转服务器）：发送消息、等待/拉取回复、"
        "查看沟通记录、上传或下载文件。所有收发内容都以中转服务器为准，不得凭空编造 Javis 的回复。"
        "action 取值：consult（带着任务上下文向 Javis 发起一次完整咨询，内部自动多轮对话）/ "
        "status（连接与在线状态）/ send（发送消息）/ poll（拉取新消息）/ "
        "history（查看历史）/ upload（上传文件）/ download（下载附件）/ end（发送 [[END]] 中止对话）。"
    )
    parameters = [
        ToolParameter(
            "action",
            "string",
            "要执行的动作",
            required=True,
            enum=["consult", "status", "send", "poll", "history", "upload", "download", "end"],
        ),
        ToolParameter(
            "content",
            "string",
            "consult 必填：要向 Javis 发起的初始问题；send 时则是要发送的文本（与 attachments 至少一项）。",
            required=False,
            required_when={"action": ["consult"]},
        ),
        ToolParameter(
            "context",
            "string",
            "consult 时的当前任务上下文（用户目标、已完成步骤、关键数据等）。"
            "内部模型据此代替 Sigma 回答 Javis 的追问，请尽量写清楚。",
            required=False,
        ),
        ToolParameter(
            "idle_timeout",
            "integer",
            "consult 时连续多久收不到 Javis 新消息就自动收线，默认 180 秒，范围 30-600。",
            required=False,
            default=CONSULT_DEFAULT_IDLE,
        ),
        ToolParameter(
            "peer",
            "string",
            "对端身份标识，默认取配置中的 peer（通常为 javis）。Chat 时一般无需填写。",
            required=False,
            default=DEFAULT_PEER,
        ),
        ToolParameter(
            "attachments",
            "array",
            "send 时可选的本地文件路径列表，会先上传再把附件随消息一起发给 Javis。",
            required=False,
        ),
        ToolParameter(
            "file_paths",
            "array",
            "upload 必填：要上传到中转服务器的本地文件路径列表。",
            required=False,
            required_when={"action": ["upload"]},
        ),
        ToolParameter(
            "file_id",
            "string",
            "download 必填：要下载的附件 file_id（由 poll/history 返回的 attachments 中获取）。",
            required=False,
            required_when={"action": ["download"]},
        ),
        ToolParameter(
            "limit",
            "integer",
            "poll/history 单次返回的最大消息条数，默认 20，最大 100。",
            required=False,
            default=20,
        ),
        ToolParameter(
            "wait",
            "integer",
            "等待秒数（0-120）。默认 0，立即返回；只有用户明确要求当场等回复时才建议传 5-10。"
            "对端离线时会自动跳过等待。",
            required=False,
            default=0,
        ),
        ToolParameter(
            "mark_read",
            "boolean",
            "poll 后是否把本地游标推进到最新（默认 true）。传 false 可用于预览而不消费。",
            required=False,
            default=True,
        ),
        ToolParameter(
            "save_dir",
            "string",
            "download 保存目录，默认 .sigma2.0/javis_inbox（相对当前工作目录）。",
            required=False,
        ),
    ]

    def __init__(
        self,
        cwd: str = ".",
        bridge_url: str = "",
        bridge_key: str = "",
        agent_id: str = "",
        peer_id: str = "",
        llm_config: dict | None = None,
    ):
        super().__init__(cwd)
        self._bridge_url = bridge_url.strip().rstrip("/")
        self._bridge_key = bridge_key.strip()
        self._agent_id = agent_id.strip() or DEFAULT_AGENT
        self._peer_id = peer_id.strip() or DEFAULT_PEER
        self.llm_config = llm_config or {}
        self._config_ready = False
        # 上岛推送：只推给本机正在运行的灵动岛，失败即丢弃，不排队。
        self._island_url = ""
        self._island_session_id = "manual"
        self._island_round = 0

    # ── 配置与 HTTP ───────────────────────────────────────────────

    def _load_config(self) -> None:
        if self._config_ready:
            return
        self._config_ready = True
        env_file = self._resolve_path(".env")
        if env_file.is_file():
            load_dotenv(env_file)
        self._bridge_url = (self._bridge_url or os.getenv("JAVIS_BRIDGE_URL", "")).rstrip("/")
        self._bridge_key = self._bridge_key or os.getenv("JAVIS_BRIDGE_KEY", "")
        self._agent_id = self._agent_id or os.getenv("JAVIS_AGENT_ID", "") or DEFAULT_AGENT
        self._peer_id = self._peer_id or os.getenv("JAVIS_PEER_ID", "") or DEFAULT_PEER
        self._island_url = (
            os.getenv("JAVIS_ISLAND_URL", "http://127.0.0.1:8891").strip().rstrip("/")
        )

    def _api_base(self) -> str:
        self._load_config()
        if not self._bridge_url:
            raise JavisBridgeError(
                "未配置 Javis 中转地址。请在「设置 → 技能 API 配置」填写 Javis 中转地址与访问密钥"
                "（或在本项目 .env 中设置 JAVIS_BRIDGE_URL / JAVIS_BRIDGE_KEY）。"
            )
        base = self._bridge_url
        return base if base.endswith("/api/javis") else f"{base}/api/javis"

    def _headers(self) -> dict:
        self._load_config()
        if not self._bridge_key:
            raise JavisBridgeError(
                "未配置 Javis 中转访问密钥。请在「设置 → 技能 API 配置」填写，"
                "或在本项目 .env 中设置 JAVIS_BRIDGE_KEY。"
            )
        return {
            "X-Bridge-Key": self._bridge_key,
            "X-Agent-Id": self._agent_id,
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        read_timeout: int = READ_TIMEOUT,
        extra_headers: dict | None = None,
        **kwargs,
    ):
        url = f"{self._api_base()}{path}"
        headers = self._headers()
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = requests.request(
                method,
                url,
                headers=headers,
                timeout=(CONNECT_TIMEOUT, read_timeout),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise JavisBridgeError(f"无法连接 Javis 中转服务器（{url}）：{exc}") from exc
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = body.get("error") or body.get("message") or json.dumps(body, ensure_ascii=False)
            except ValueError:
                detail = resp.text[:300]
            raise JavisBridgeError(f"中转服务器返回 HTTP {resp.status_code}：{detail}")
        return resp

    def _json(self, method: str, path: str, read_timeout: int = READ_TIMEOUT, **kwargs) -> dict:
        resp = self._request(method, path, read_timeout=read_timeout, **kwargs)
        try:
            data = resp.json()
        except ValueError as exc:
            raise JavisBridgeError(f"中转服务器返回了非 JSON 响应：{resp.text[:200]}") from exc
        if not isinstance(data, dict):
            raise JavisBridgeError("中转服务器返回的数据格式不正确（期望 JSON 对象）")
        return data

    # ── 本地游标 ─────────────────────────────────────────────────

    def _state_identity(self) -> str:
        self._load_config()
        return f"{self._bridge_url}|{self._agent_id}"

    def _load_state(self) -> dict:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("identity") != self._state_identity():
            return {}
        return data

    def _save_state(self, state: dict) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            log.warning(f"[JavisBridge] 写入游标失败: {exc}")

    def _get_cursor(self, peer: str) -> int:
        state = self._load_state()
        try:
            return int(state.get("cursors", {}).get(peer, 0))
        except (TypeError, ValueError):
            return 0

    def _set_cursor(self, peer: str, cursor: int) -> None:
        if cursor <= 0:
            return
        state = self._load_state()
        state["identity"] = self._state_identity()
        cursors = state.setdefault("cursors", {})
        cursors[peer] = int(cursor)
        self._save_state(state)

    # ── 文件 ────────────────────────────────────────────────────

    def _mime_type(self, path: Path) -> str:
        import mimetypes

        return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    def _upload_one(self, raw_path: str, peer: str) -> dict:
        path = self._resolve_path(raw_path)
        if not path.is_file():
            raise JavisBridgeError(f"文件不存在或不是普通文件：{raw_path}")
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise JavisBridgeError(
                f"文件过大：{path.name}（{size} 字节），单文件上限 {MAX_UPLOAD_BYTES} 字节"
            )
        # 以原始字节流上传，避免中转服务端解析 multipart；文件名按 RFC 3986 编码放进请求头。
        # 显式带 Content-Length，服务端才能边读边写盘，不会把大文件读进内存。
        extra_headers = {
            "X-File-Name": quote(path.name),
            "Content-Type": self._mime_type(path),
            "Content-Length": str(size),
        }
        with path.open("rb") as handle:
            resp = self._request(
                "POST",
                f"/files?to={quote(peer)}",
                read_timeout=300,
                data=handle,
                extra_headers=extra_headers,
            )
        data = resp.json()
        file_id = data.get("file_id") or data.get("id")
        if not file_id:
            raise JavisBridgeError(f"上传 {path.name} 后未获得 file_id")
        return {
            "file_id": str(file_id),
            "name": data.get("name") or path.name,
            "size": data.get("size", size),
        }

    def _safe_filename(self, name: str, fallback: str) -> str:
        name = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", name).strip().strip(".")
        return name[:180] or fallback

    def _download_one(self, file_id: str, save_dir: str | None) -> str:
        resp = self._request("GET", f"/files/{file_id}", read_timeout=600, stream=True)
        disposition = resp.headers.get("Content-Disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)', disposition)
        remote_name = match.group(1) if match else ""
        filename = self._safe_filename(remote_name, f"javis_{file_id}")
        if save_dir:
            target_dir = self._resolve_path(save_dir)
        else:
            target_dir = self._resolve_path(".sigma2.0/javis_inbox")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        stem, suffix = target.stem, target.suffix
        index = 1
        while target.exists():
            target = target_dir / f"{stem}_{index}{suffix}"
            index += 1
        with target.open("wb") as handle:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    handle.write(chunk)
        return str(target)

    # ── 跨机咨询协议 ─────────────────────────────────────────────

    @staticmethod
    def _strip_end(text: str) -> tuple[str, bool]:
        """剥离任意位置的 [[END]]，返回（干净正文, 是否出现中止标记）。"""
        raw = text or ""
        has_end = END_MARKER in raw
        if has_end:
            raw = raw.replace(END_MARKER, "")
        return raw.strip(), has_end

    def _post_message(self, content: str, attachments: list, peer: str) -> dict:
        payload = {
            "to": peer,
            "from": self._agent_id,
            "content": content or "",
            "kind": "mixed" if content and attachments else ("file" if attachments else "text"),
            "attachments": attachments,
            "client_msg_id": uuid.uuid4().hex,
            "created_at": int(time.time()),
        }
        data = self._json("POST", "/messages", json=payload)
        display, has_end = self._strip_end(content or "")
        if display or attachments:
            self._notify_island({
                "type": "message",
                "session_id": self._island_session_id,
                "role": self._agent_id,
                "content": display,
                "round": self._island_round or None,
                "created_at": int(time.time()),
                "attachments": [
                    {"name": att.get("name"), "size": att.get("size")}
                    for att in attachments
                ],
                "end": has_end,
            })
        return data

    def _notify_island(self, payload: dict) -> None:
        """把对话事件推给本机灵动岛；岛没开时连接失败，直接丢弃，不排队。"""
        url = self._island_url or "http://127.0.0.1:8891"
        try:
            requests.post(f"{url}/javis/event", json=payload, timeout=(0.1, 0.35))
        except requests.RequestException:
            pass

    def _format_transcript(self, transcript: list, limit: int = 16) -> str:
        lines = []
        for item in transcript[-limit:]:
            who = "Sigma" if item.get("from") == self._agent_id else "Javis"
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"[{who}] {content[:1500]}")
            for att in item.get("attachments") or []:
                lines.append(f"  [附件] {att.get('name') or att.get('file_id')}")
            for path in item.get("saved_files") or []:
                lines.append(f"  [已暂存] {path}")
        return "\n".join(lines) or "（暂无记录）"

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """用 Sigma 当前主模型生成一条给 Javis 的回复（同步调用，运行在工具线程）。"""
        cfg = self.llm_config or {}
        base_url = str(cfg.get("base_url") or cfg.get("baseUrl") or "").rstrip("/")
        api_key = str(cfg.get("api_key") or cfg.get("apiKey") or "")
        model = str(cfg.get("model") or "")
        protocol = str(cfg.get("protocol") or "anthropic").lower()
        if not base_url or not api_key or not model:
            raise JavisBridgeError("缺少 Sigma 主模型配置（base_url / api_key / model），无法生成咨询回复")

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        if protocol == "openai":
            url = (
                f"{base_url}/v1/chat/completions"
                if "/v1" not in base_url
                else f"{base_url}/chat/completions"
            )
            body = {
                "model": model,
                "max_tokens": 2048,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        else:
            url = (
                f"{base_url}/v1/messages"
                if "/v1" not in base_url
                else f"{base_url}/messages"
            )
            headers["anthropic-version"] = "2023-06-01"
            body = {
                "model": model,
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": user_prompt}],
            }
            if system_prompt:
                body["system"] = system_prompt

        # 复用项目里的模型预设（思考模式 / 采样参数），失败不影响基础调用
        try:
            from context_manager import apply_model_specific_params

            apply_model_specific_params(
                body,
                model,
                "openai" if protocol == "openai" else "anthropic",
                {
                    "provider": cfg.get("provider") or "generic",
                    "thinking": cfg.get("thinking") or "default",
                },
            )
        except Exception as exc:
            log.warning(f"[JavisBridge] 应用模型预设失败（忽略）: {exc}")

        try:
            resp = requests.post(
                url, headers=headers, json=body, timeout=(CONNECT_TIMEOUT, LLM_TIMEOUT)
            )
        except requests.RequestException as exc:
            raise JavisBridgeError(f"调用 Sigma 模型失败：{exc}") from exc
        if resp.status_code >= 400:
            raise JavisBridgeError(
                f"Sigma 模型返回 HTTP {resp.status_code}：{resp.text[:300]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise JavisBridgeError(f"Sigma 模型返回非 JSON 响应：{resp.text[:200]}") from exc

        if protocol == "openai":
            choices = data.get("choices") or []
            content = choices[0].get("message", {}).get("content", "") if choices else ""
        else:
            blocks = data.get("content") or []
            content = "".join(
                str(block.get("text", ""))
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", "")) if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content or "").strip()

    def _generate_reply(
        self, context: str, transcript: list, round_no: int, closing: bool = False,
    ) -> str | None:
        """根据任务上下文 + 对话记录，生成下一条发给 Javis 的回复。"""
        self._llm_error = ""
        system_prompt = (
            "你是 Sigma，正在通过中转通道向另一台电脑上的 Javis 咨询，以获取完成当前任务所需的信息。"
            "你输出的内容会被直接发送给 Javis：只输出回复正文，不要输出分析过程、角色标签或多余引号。"
            "不要编造 Javis 没有说过的事实；如果信息已经足够，请在回复末尾单独一行输出 [[END]] 结束对话。"
            f"\n\n当前任务上下文：\n{context or '（未提供）'}"
        )
        latest = ""
        for item in reversed(transcript):
            if item.get("from") != self._agent_id:
                latest = str(item.get("content") or "")
                break
        user_prompt = (
            f"以下是双方已有对话：\n{self._format_transcript(transcript)}\n\n"
            f"Javis 的最新消息：{latest}\n\n"
            f"这是第 {round_no} 轮。请生成下一条发给 Javis 的回复。"
        )
        if closing:
            user_prompt += "\n已经进入收尾阶段：尽量一次问清/答完，信息足够时在回复末尾输出 [[END]]。"
        if round_no >= HARD_ROUND_LIMIT:
            user_prompt += "\n这是最后一轮，必须收尾，不要再展开新话题。"
        try:
            return self._call_llm(system_prompt, user_prompt)
        except JavisBridgeError as exc:
            self._llm_error = str(exc)
            log.warning(f"[JavisBridge] consult 生成回复失败: {exc}")
            return None

    def _send_end_best_effort(self, peer: str, reason: str) -> None:
        text = f"本轮先到这里。\n{END_MARKER}"
        try:
            self._post_message(text, [], peer)
            log.info(f"[JavisBridge] 已发送中止信号（{reason}）")
        except JavisBridgeError as exc:
            log.warning(f"[JavisBridge] 发送中止信号失败（{reason}）: {exc}")

    def _consult(
        self, content: str, context: str, peer: str, idle_timeout: int
    ) -> ToolResult:
        """带上下文向 Javis 发起一次完整咨询，内部多轮对话直到 END / 12 轮 / 超时。"""
        question = (content or "").strip()
        if not question:
            return ToolResult.fail("consult 需要提供要问 Javis 的 content")

        cfg = self.llm_config or {}
        if not (cfg.get("api_key") or cfg.get("apiKey")):
            return ToolResult.fail("缺少 Sigma 主模型配置，无法进行 Javis 咨询")

        # 对端明确离线时快速失败，避免白等 180 秒
        try:
            peers = self._json("GET", "/peers").get("peers") or []
            for item in peers:
                if (item.get("id") or item.get("agent_id")) == peer:
                    if not item.get("online"):
                        return ToolResult.fail(
                            f"Javis（{peer}）当前不在线，咨询未发起。请确认对端已启动监听。"
                        )
                    break
        except JavisBridgeError:
            # 老版本中转服务可能没有 /peers，继续尝试发送
            pass

        session_id = f"javis-{int(time.time())}-{uuid.uuid4().hex[:6]}"
        self._island_session_id = session_id
        self._island_round = 0
        self._notify_island({"type": "session_start", "session_id": session_id, "round": 0})
        try:
            sent = self._post_message(question, [], peer)
        except JavisBridgeError as exc:
            self._notify_island({
                "type": "session_end",
                "session_id": session_id,
                "status": "send_error",
                "rounds": 0,
            })
            self._island_session_id = "manual"
            self._island_round = 0
            return ToolResult.fail(f"向 Javis 发起咨询失败：{exc}")
        # 以初始问题落库后的消息 id 为基线：更早的历史消息只消费、不回复，
        # 避免把上一次会话遗留的未读消息当成本轮咨询的第 1 轮。
        try:
            baseline_id = int(sent.get("id") or sent.get("message_id") or 0)
        except (TypeError, ValueError):
            baseline_id = 0

        transcript: list[dict] = [{
            "from": self._agent_id,
            "to": peer,
            "content": question,
            "attachments": [],
            "created_at": int(time.time()),
        }]
        self._emit_progress(
            f"已向 Javis 发起咨询：{question[:80]}", stage="consult_sent", round=0
        )

        rounds = 0
        ended_by = ""
        final_answer = ""
        errors: list[str] = []
        self._llm_error = ""
        started = time.time()
        pending_since = time.time()
        done = False

        while not done:
            now = time.time()
            if self.is_cancelled():
                ended_by = "cancelled"
                self._send_end_best_effort(peer, "用户中止")
                break
            if now - started > CONSULT_MAX_SECONDS:
                ended_by = "total_timeout"
                self._send_end_best_effort(peer, "总时长超过上限")
                break
            idle_remaining = idle_timeout - (now - pending_since)
            if idle_remaining <= 0:
                ended_by = "idle_timeout"
                self._send_end_best_effort(peer, "等待 Javis 回复超时")
                break

            try:
                messages = self._poll_messages(
                    peer,
                    limit=20,
                    wait=min(CONSULT_POLL_WAIT, max(1, int(idle_remaining))),
                    mark_read=True,
                )
            except JavisBridgeError as exc:
                errors.append(str(exc))
                log.warning(f"[JavisBridge] consult 拉取失败: {exc}")
                time.sleep(1)
                continue
            if not messages:
                continue

            for message in messages:
                try:
                    message_id = int(message.get("id") or 0)
                except (TypeError, ValueError):
                    message_id = 0
                if baseline_id and message_id <= baseline_id:
                    # 咨询开始前的历史消息：游标已消费，但不计入轮次、不生成回复。
                    continue
                text = str(message.get("content") or "")
                clean, has_end = self._strip_end(text)
                rounds += 1
                self._island_round = rounds

                attachments = message.get("attachments") or []
                saved: list[str] = []
                for att in attachments:
                    file_id = str(att.get("file_id") or "")
                    if not file_id:
                        continue
                    try:
                        saved.append(self._download_one(file_id, None))
                    except JavisBridgeError as exc:
                        errors.append(f"附件下载失败 {file_id}: {exc}")

                transcript.append({
                    "from": message.get("from") or peer,
                    "to": message.get("to") or self._agent_id,
                    "content": clean,
                    "attachments": attachments,
                    "saved_files": saved,
                    "created_at": message.get("created_at") or int(time.time()),
                })
                self._emit_progress(
                    f"第 {rounds} 轮：收到 Javis 回复" + ("（对方已结束）" if has_end else ""),
                    stage="received",
                    round=rounds,
                    detail=clean[:300],
                )
                self._notify_island({
                    "type": "message",
                    "session_id": self._island_session_id,
                    "role": message.get("from") or peer,
                    "content": clean,
                    "round": rounds,
                    "created_at": message.get("created_at") or int(time.time()),
                    "attachments": [
                        {"name": att.get("name"), "size": att.get("size")}
                        for att in attachments
                    ],
                    "end": has_end,
                })

                if has_end:
                    ended_by = "javis"
                    final_answer = clean or final_answer
                    done = True
                    break

                closing = rounds >= SOFT_ROUND_LIMIT
                raw_reply = self._generate_reply(context, transcript, rounds, closing=closing)
                if raw_reply is None:
                    errors.append(self._llm_error)
                    self._send_end_best_effort(peer, "Sigma 模型生成失败")
                    ended_by = "llm_error"
                    done = True
                    break

                reply_text, reply_has_end = self._strip_end(raw_reply)
                if not reply_text:
                    reply_text = "收到。"
                send_content = raw_reply.strip()
                if rounds >= HARD_ROUND_LIMIT:
                    # 硬上限：无论模型输出什么，都强制带 [[END]]
                    if not reply_has_end:
                        send_content = f"{reply_text}\n{END_MARKER}"
                    reply_has_end = True
                elif not reply_has_end:
                    send_content = reply_text

                try:
                    self._post_message(send_content, [], peer)
                except JavisBridgeError as exc:
                    errors.append(f"发送回复失败: {exc}")
                    self._send_end_best_effort(peer, "回复发送失败")
                    ended_by = "send_error"
                    done = True
                    break

                transcript.append({
                    "from": self._agent_id,
                    "to": peer,
                    "content": reply_text,
                    "attachments": [],
                    "created_at": int(time.time()),
                })
                self._emit_progress(
                    f"第 {rounds} 轮：已回复 Javis", stage="sent", round=rounds,
                    detail=reply_text[:300],
                )

                if reply_has_end:
                    ended_by = "sigma" if rounds < HARD_ROUND_LIMIT else "round_limit"
                    final_answer = clean or final_answer
                    done = True
                    break

                if rounds >= HARD_ROUND_LIMIT:
                    ended_by = "round_limit"
                    final_answer = clean or final_answer
                    done = True
                    break

                pending_since = time.time()

        status = ended_by or "unknown"
        self._notify_island({
            "type": "session_end",
            "session_id": self._island_session_id,
            "status": status,
            "rounds": rounds,
        })
        self._island_session_id = "manual"
        self._island_round = 0
        trimmed = [
            {
                "from": item.get("from"),
                "to": item.get("to"),
                "content": str(item.get("content") or "")[:2000],
                "attachments": item.get("attachments") or [],
                "saved_files": item.get("saved_files") or [],
                "created_at": item.get("created_at"),
            }
            for item in transcript[-24:]
        ]
        result = {
            "status": status,
            "rounds": rounds,
            "peer": peer,
            "final_answer": final_answer,
            "transcript": trimmed,
            "errors": errors[-5:],
            "llm_error": self._llm_error,
            "hint": (
                "以上是本次与 Javis 咨询的真实结果。请把它合并进当前任务上下文，"
                "继续完成原任务；不要重复发起同样的咨询。"
            ),
        }
        return ToolResult.ok(json.dumps(result, ensure_ascii=False, indent=2))

    def _end(self, content: str, peer: str) -> ToolResult:
        text = f"{(content or '').strip()}\n{END_MARKER}".strip() if (content or "").strip() else END_MARKER
        try:
            data = self._post_message(text, [], peer)
        except JavisBridgeError as exc:
            return ToolResult.fail(f"发送中止信号失败：{exc}")
        self._notify_island({
            "type": "session_end",
            "session_id": self._island_session_id,
            "status": "sigma",
            "rounds": self._island_round,
        })
        self._island_session_id = "manual"
        self._island_round = 0
        return ToolResult.ok(
            json.dumps(
                {"ended": True, "message_id": data.get("id") or data.get("message_id"), "to": peer},
                ensure_ascii=False,
                indent=2,
            )
        )

    # ── 动作 ─────────────────────────────────────────────────────

    def _status(self, peer: str) -> ToolResult:
        health = self._json("GET", "/health", read_timeout=CONNECT_TIMEOUT)
        peers: list = []
        try:
            peers = list(self._json("GET", "/peers").get("peers", []))
        except JavisBridgeError:
            # 老版本中转服务可能没有 /peers，不影响基础通信
            pass
        online = None
        for item in peers:
            ident = item.get("id") or item.get("agent_id")
            if ident == peer:
                online = bool(item.get("online"))
                break
        result = {
            "agent": self._agent_id,
            "peer": peer,
            "server": health,
            "peer_online": online,
            "peers": peers,
            "local_cursor": self._get_cursor(peer),
        }
        return ToolResult.ok(json.dumps(result, ensure_ascii=False, indent=2))

    def _send(
        self, content: str, peer: str, attachments: list, wait: int
    ) -> ToolResult:
        files = [self._upload_one(path, peer) for path in attachments]
        if not content and not files:
            return ToolResult.fail("send 需要 content 或 attachments 至少一项")
        data = self._post_message(content or "", files, peer)
        result = {
            "sent": True,
            "message_id": data.get("id") or data.get("message_id"),
            "delivered": data.get("delivered"),
            "attachments": files,
            "to": peer,
        }
        if wait > 0:
            # 对端离线时等待毫无意义，直接返回，避免用户以为发送卡死。
            if data.get("delivered") is False:
                result["replies"] = []
                result["hint"] = "对端当前不在线，消息已发出。之后用 poll 取回复即可。"
            else:
                result["replies"] = self._poll_messages(
                    peer, limit=20, wait=wait, mark_read=True
                )
                result["local_cursor"] = self._get_cursor(peer)
        return ToolResult.ok(json.dumps(result, ensure_ascii=False, indent=2))

    def _poll_messages(self, peer: str, limit: int, wait: int, mark_read: bool) -> list:
        after = self._get_cursor(peer)
        params = {"peer": peer, "after": after, "limit": limit}
        if wait > 0:
            params["wait"] = min(wait, POLL_TIMEOUT_MAX)
        data = self._json("GET", "/messages", read_timeout=READ_TIMEOUT + wait, params=params)
        messages = data.get("messages") or []
        cursor = data.get("cursor")
        try:
            cursor = int(cursor) if cursor is not None else 0
        except (TypeError, ValueError):
            cursor = 0
        if mark_read and cursor > 0:
            self._set_cursor(peer, cursor)
        return messages

    def _poll(self, peer: str, limit: int, wait: int, mark_read: bool) -> ToolResult:
        messages = self._poll_messages(peer, limit, wait, mark_read)
        for message in messages:
            clean, has_end = self._strip_end(str(message.get("content") or ""))
            if clean or message.get("attachments"):
                self._notify_island({
                    "type": "message",
                    "session_id": self._island_session_id,
                    "role": message.get("from") or peer,
                    "content": clean,
                    "round": None,
                    "created_at": message.get("created_at") or int(time.time()),
                    "attachments": [
                        {"name": att.get("name"), "size": att.get("size")}
                        for att in message.get("attachments") or []
                    ],
                    "end": has_end,
                })
        result = {
            "peer": peer,
            "count": len(messages),
            "messages": messages,
            "local_cursor": self._get_cursor(peer),
        }
        if not messages:
            result["hint"] = "暂无新消息。可以稍后再 poll，或增大 wait 秒数等待对方回复。"
        return ToolResult.ok(json.dumps(result, ensure_ascii=False, indent=2))

    def _history(self, peer: str, limit: int) -> ToolResult:
        data = self._json("GET", "/history", params={"peer": peer, "limit": limit})
        messages = data.get("messages") or []
        return ToolResult.ok(
            json.dumps(
                {"peer": peer, "count": len(messages), "messages": messages},
                ensure_ascii=False,
                indent=2,
            )
        )

    def _upload(self, peer: str, file_paths: list) -> ToolResult:
        if not file_paths:
            return ToolResult.fail("upload 需要提供 file_paths")
        uploaded = [self._upload_one(path, peer) for path in file_paths]
        return ToolResult.ok(
            json.dumps(
                {"uploaded": uploaded, "to": peer, "hint": "把 file_id 放进 send 的 attachments 即可发出"},
                ensure_ascii=False,
                indent=2,
            )
        )

    def _download(self, file_id: str, save_dir: str | None) -> ToolResult:
        path = self._download_one(file_id, save_dir)
        return ToolResult.ok(
            json.dumps(
                {"file_id": file_id, "saved_to": path, "hint": "可直接用 read/bash 等工具处理该文件"},
                ensure_ascii=False,
                indent=2,
            )
        )

    # ── 入口 ────────────────────────────────────────────────────

    def execute(self, **kwargs) -> ToolResult:
        self._load_config()
        action = str(kwargs.get("action") or "").strip().lower()
        peer = str(kwargs.get("peer") or "").strip() or self._peer_id
        try:
            limit = int(kwargs.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(limit, 100))
        try:
            wait = int(kwargs.get("wait") or 0)
        except (TypeError, ValueError):
            wait = 0
        wait = max(0, min(wait, POLL_TIMEOUT_MAX))
        try:
            idle_timeout = int(kwargs.get("idle_timeout") or CONSULT_DEFAULT_IDLE)
        except (TypeError, ValueError):
            idle_timeout = CONSULT_DEFAULT_IDLE
        idle_timeout = max(30, min(idle_timeout, 600))
        mark_read = kwargs.get("mark_read")
        if mark_read is None:
            mark_read = True
        else:
            mark_read = bool(mark_read)

        try:
            if action == "consult":
                return self._consult(
                    str(kwargs.get("content") or ""),
                    str(kwargs.get("context") or ""),
                    peer,
                    idle_timeout,
                )
            if action == "end":
                return self._end(str(kwargs.get("content") or ""), peer)
            if action == "status":
                return self._status(peer)
            if action == "send":
                attachments = kwargs.get("attachments") or []
                if not isinstance(attachments, list):
                    attachments = [attachments]
                return self._send(str(kwargs.get("content") or ""), peer, attachments, wait)
            if action == "poll":
                return self._poll(peer, limit, wait, mark_read)
            if action == "history":
                return self._history(peer, limit)
            if action == "upload":
                file_paths = kwargs.get("file_paths") or []
                if not isinstance(file_paths, list):
                    file_paths = [file_paths]
                return self._upload(peer, file_paths)
            if action == "download":
                file_id = str(kwargs.get("file_id") or "").strip()
                if not file_id:
                    return ToolResult.fail("download 需要提供 file_id")
                return self._download(file_id, kwargs.get("save_dir"))
            return ToolResult.fail(
                f"未知 action：{action or '(空)'}，可用：consult / status / send / poll / "
                f"history / upload / download / end"
            )
        except JavisBridgeError as exc:
            return ToolResult.fail(str(exc))
        except Exception as exc:  # 兜底，避免把堆栈直接喂给 LLM
            log.error(f"[JavisBridge] {action} 执行异常: {exc}")
            return ToolResult.fail(f"Javis 通信失败：{exc}")


skill = JavisBridgeTool()
