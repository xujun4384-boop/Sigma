"""
Javis Bridge 中转服务 (Relay Server)

部署在阿里云服务器上，为 Sigma 与另一台电脑上的 Javis 转发消息和文件。
只依赖 Python 标准库，无需安装第三方包。

启动方式:
  python relay_server.py --port 8890 --key YOUR_SHARED_SECRET_KEY

可选参数:
  --host 0.0.0.0          监听地址
  --port 8890             监听端口（不要与现有微信中转的 8888 冲突）
  --key  YOUR_KEY         预共享密钥（Sigma 与 Javis 都配置同一个）
  --db   ./javis_bridge.db      消息/文件元数据存储位置
  --storage ./javis_bridge_files  上传文件暂存目录
  --online-window 90      秒内有请求的对端视为在线

客户端协议见 skills/javis_bridge/skill.md「通信协议」一节。
鉴权: 所有 /api/javis/* 请求都需要请求头 X-Bridge-Key；
身份: 请求头 X-Agent-Id（Sigma 为 sigma，Javis 为 javis）。
"""
from __future__ import annotations

import argparse
import hmac
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

SERVICE_VERSION = "1.0"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DB_WRITE_LOCK = threading.Lock()


# ── 数据库 ───────────────────────────────────────────────────────

def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'text',
                content TEXT NOT NULL DEFAULT '',
                attachments TEXT NOT NULL DEFAULT '[]',
                client_msg_id TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_inbox
                ON messages (recipient, sender, id);
            CREATE INDEX IF NOT EXISTS idx_messages_created
                ON messages (created_at);

            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                last_seen INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                file_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                size INTEGER NOT NULL,
                path TEXT NOT NULL,
                uploader TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(BridgeHandler.db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ── HTTP 处理 ────────────────────────────────────────────────────

def _safe_agent_id(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^0-9A-Za-z_.-]+", "_", value)
    return value[:64] or "unknown"


def _message_row_to_dict(row: sqlite3.Row) -> dict:
    try:
        attachments = json.loads(row["attachments"])
    except (TypeError, ValueError):
        attachments = []
    return {
        "id": row["id"],
        "from": row["sender"],
        "to": row["recipient"],
        "kind": row["kind"],
        "content": row["content"],
        "attachments": attachments,
        "created_at": row["created_at"],
    }


class BridgeHandler(BaseHTTPRequestHandler):
    shared_key: str = ""
    db_path: Path = Path("./javis_bridge.db")
    storage_dir: Path = Path("./javis_bridge_files")
    online_window: int = 90
    request_timeout = 120

    def log_message(self, format, *args):
        print(f"[JavisBridge] {args[0]}", flush=True)

    def setup(self):
        super().setup()
        self.connection.settimeout(self.request_timeout)

    # ── 通用响应 ──

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _authorized(self) -> bool:
        if not self.shared_key:
            return True
        provided = self.headers.get("X-Bridge-Key", "")
        if hmac.compare_digest(provided, self.shared_key):
            return True
        self._error(401, "unauthorized")
        return False

    def _agent_id(self) -> str:
        return _safe_agent_id(self.headers.get("X-Agent-Id", ""))

    def _mark_seen(self, agent_id: str) -> None:
        now = int(time.time())
        with DB_WRITE_LOCK:
            conn = db_connect()
            try:
                conn.execute(
                    "INSERT INTO agents (agent_id, last_seen) VALUES (?, ?) "
                    "ON CONFLICT(agent_id) DO UPDATE SET last_seen = excluded.last_seen",
                    (agent_id, now),
                )
                conn.commit()
            finally:
                conn.close()

    def _is_online(self, agent_id: str) -> bool:
        conn = db_connect()
        try:
            row = conn.execute(
                "SELECT last_seen FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        finally:
            conn.close()
        return bool(row) and int(time.time()) - int(row["last_seen"]) <= self.online_window

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._error(400, "invalid Content-Length")
            return None
        if length <= 0:
            self._error(400, "empty body")
            return None
        if length > MAX_JSON_BYTES:
            self._error(413, "json body too large")
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._error(400, "invalid json")
            return None
        if not isinstance(data, dict):
            self._error(400, "json body must be an object")
            return None
        return data

    def _query(self, path: str) -> dict:
        return {k: v[-1] for k, v in parse_qs(urlparse(path).query).items()}

    # ── 路由 ──

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(
                200,
                {"ok": True, "service": "javis-bridge", "version": SERVICE_VERSION,
                 "time": int(time.time())},
            )
            return
        if not path.startswith("/api/javis/"):
            self._error(404, "not found")
            return
        if not self._authorized():
            return

        agent_id = self._agent_id()
        self._mark_seen(agent_id)

        if path == "/api/javis/health":
            self._send_json(
                200,
                {"ok": True, "service": "javis-bridge", "version": SERVICE_VERSION,
                 "time": int(time.time())},
            )
            return
        if path == "/api/javis/peers":
            return self._handle_peers()
        if path == "/api/javis/messages":
            return self._handle_poll(agent_id)
        if path == "/api/javis/history":
            return self._handle_history(agent_id)
        if path.startswith("/api/javis/files/"):
            return self._handle_download(path.rsplit("/", 1)[-1])
        self._error(404, "not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/javis/"):
            self._error(404, "not found")
            return
        if not self._authorized():
            return

        agent_id = self._agent_id()
        self._mark_seen(agent_id)

        if path == "/api/javis/messages":
            return self._handle_send(agent_id)
        if path == "/api/javis/files":
            return self._handle_upload(agent_id)
        self._error(404, "not found")

    # ── 具体接口 ──

    def _handle_peers(self) -> None:
        conn = db_connect()
        try:
            rows = conn.execute("SELECT agent_id, last_seen FROM agents").fetchall()
        finally:
            conn.close()
        now = int(time.time())
        peers = [
            {
                "id": row["agent_id"],
                "online": now - int(row["last_seen"]) <= self.online_window,
                "last_seen": int(row["last_seen"]),
            }
            for row in rows
        ]
        self._send_json(200, {"peers": peers})

    def _handle_send(self, agent_id: str) -> None:
        data = self._read_json_body()
        if data is None:
            return
        to = _safe_agent_id(str(data.get("to") or ""))
        content = str(data.get("content") or "")
        kind = str(data.get("kind") or ("text" if content else "file"))
        attachments = data.get("attachments") or []
        if to == "unknown":
            self._error(400, "missing to")
            return
        if not content and not attachments:
            self._error(400, "content and attachments are both empty")
            return
        if not isinstance(attachments, list):
            self._error(400, "attachments must be an array")
            return
        now = int(time.time())
        with DB_WRITE_LOCK:
            conn = db_connect()
            try:
                cur = conn.execute(
                    "INSERT INTO messages "
                    "(sender, recipient, kind, content, attachments, client_msg_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        agent_id,
                        to,
                        kind,
                        content,
                        json.dumps(attachments, ensure_ascii=False),
                        str(data.get("client_msg_id") or "")[:128],
                        now,
                    ),
                )
                message_id = cur.lastrowid
                conn.commit()
            finally:
                conn.close()
        self._send_json(
            200,
            {
                "id": message_id,
                "delivered": self._is_online(to),
                "created_at": now,
            },
        )

    def _handle_poll(self, agent_id: str) -> None:
        query = self._query(self.path)
        peer = _safe_agent_id(query.get("peer", ""))
        if peer == "unknown":
            self._error(400, "missing peer")
            return
        try:
            after = int(query.get("after", 0))
        except ValueError:
            after = 0
        try:
            limit = max(1, min(int(query.get("limit", 20)), 100))
        except ValueError:
            limit = 20
        try:
            wait = max(0, min(int(query.get("wait", 0)), 120))
        except ValueError:
            wait = 0

        deadline = time.time() + wait
        while True:
            conn = db_connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE recipient = ? AND sender = ? AND id > ? "
                    "ORDER BY id ASC LIMIT ?",
                    (agent_id, peer, after, limit),
                ).fetchall()
            finally:
                conn.close()
            if rows or time.time() >= deadline:
                break
            time.sleep(0.4)

        messages = [_message_row_to_dict(row) for row in rows]
        cursor = messages[-1]["id"] if messages else after
        self._send_json(200, {"cursor": cursor, "messages": messages})

    def _handle_history(self, agent_id: str) -> None:
        query = self._query(self.path)
        peer = _safe_agent_id(query.get("peer", ""))
        if peer == "unknown":
            self._error(400, "missing peer")
            return
        try:
            limit = max(1, min(int(query.get("limit", 20)), 100))
        except ValueError:
            limit = 20
        conn = db_connect()
        try:
            rows = conn.execute(
                "SELECT * FROM messages WHERE "
                "(sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?) "
                "ORDER BY id DESC LIMIT ?",
                (agent_id, peer, peer, agent_id, limit),
            ).fetchall()
        finally:
            conn.close()
        messages = [_message_row_to_dict(row) for row in reversed(rows)]
        self._send_json(200, {"messages": messages})

    def _handle_upload(self, agent_id: str) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._error(400, "invalid Content-Length")
            return
        if length <= 0:
            self._error(400, "empty file")
            return
        if length > MAX_UPLOAD_BYTES:
            self._error(413, "file too large")
            return

        raw_name = unquote(self.headers.get("X-File-Name", "")) or "upload.bin"
        name = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", Path(raw_name).name).strip()[:180]
        name = name or "upload.bin"
        file_id = uuid.uuid4().hex
        target = self.storage_dir / file_id
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        remaining = length
        try:
            with target.open("wb") as handle:
                while remaining > 0:
                    chunk = self.rfile.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    handle.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            target.unlink(missing_ok=True)
            return
        if remaining > 0:
            target.unlink(missing_ok=True)
            self._error(400, "incomplete upload")
            return

        size = target.stat().st_size
        now = int(time.time())
        with DB_WRITE_LOCK:
            conn = db_connect()
            try:
                conn.execute(
                    "INSERT INTO files (file_id, name, size, path, uploader, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (file_id, name, size, str(target), agent_id, now),
                )
                conn.commit()
            finally:
                conn.close()
        self._send_json(200, {"file_id": file_id, "name": name, "size": size})

    def _handle_download(self, file_id: str) -> None:
        conn = db_connect()
        try:
            row = conn.execute("SELECT * FROM files WHERE file_id = ?", (file_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            self._error(404, "file not found")
            return
        target = Path(row["path"])
        if not target.is_file():
            self._error(410, "file expired")
            return
        size = target.stat().st_size
        content_type = mimetypes.guess_type(row["name"])[0] or "application/octet-stream"
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(row['name'])}",
            )
            self.end_headers()
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Javis Bridge 中转服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, default=8890, help="监听端口，默认 8890")
    parser.add_argument("--key", required=True, help="预共享密钥（Sigma/Javis 共用）")
    parser.add_argument("--db", default="./javis_bridge.db", help="SQLite 数据库路径")
    parser.add_argument(
        "--storage", default="./javis_bridge_files", help="上传文件暂存目录"
    )
    parser.add_argument(
        "--online-window", type=int, default=90, help="在线判定窗口（秒），默认 90"
    )
    args = parser.parse_args()

    if len(args.key) < 8:
        print("错误: 密钥至少 8 个字符")
        sys.exit(1)

    BridgeHandler.shared_key = args.key
    BridgeHandler.db_path = Path(args.db).resolve()
    BridgeHandler.storage_dir = Path(args.storage).resolve()
    BridgeHandler.online_window = max(10, args.online_window)
    init_db(BridgeHandler.db_path)

    restart_count = 0
    while True:
        try:
            server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
            server.daemon_threads = True
            print(f"[JavisBridge] 服务已启动 (重启次数: {restart_count})")
            print(f"[JavisBridge] 监听: {args.host}:{args.port}")
            print(f"[JavisBridge] 数据库: {BridgeHandler.db_path}")
            print(f"[JavisBridge] 文件暂存: {BridgeHandler.storage_dir}")
            print(f"[JavisBridge] 健康检查: http://{args.host}:{args.port}/health")
            print()
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[JavisBridge] 服务已停止")
            try:
                server.server_close()
            except Exception:
                pass
            break
        except Exception as exc:
            restart_count += 1
            print(f"[JavisBridge] 崩溃 ({type(exc).__name__}: {exc})，3 秒后重启...", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
