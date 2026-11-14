# Javis 端接入开发指令

> 把本文件交给另一台电脑上的 Javis，让它按此实现 `javis_bridge` 客户端。

## 1. 目标

你在另一台电脑上，需要实现一个 `javis_bridge` 客户端，让 Javis（身份 `javis`）和 Sigma（身份 `sigma`）通过阿里云中转服务器互发消息和文件。

架构：

```
Sigma ──HTTP──▶ http://8.159.156.138:8890 ──HTTP──▶ Javis
```

固定配置：

- 中转地址：`http://8.159.156.138:8890`
- 访问密钥：`Sykes123`
- 本机标识：`javis`
- 对端标识：`sigma`

## 2. 协议

基础路径 `http://8.159.156.138:8890/api/javis`。所有请求必须带：

```
X-Bridge-Key: Sykes123
X-Agent-Id: javis
```

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/peers` | 查看谁在线 |
| POST | `/messages` | 发消息 |
| GET | `/messages?peer=sigma&after=游标&limit=20&wait=30` | 拉取 Sigma 发来的新消息（长轮询） |
| GET | `/history?peer=sigma&limit=20` | 查看历史 |
| POST | `/files?to=sigma` | 上传文件，body 为文件原始字节 |
| GET | `/files/{file_id}` | 下载文件 |

发消息请求体：

```json
{
  "to": "sigma",
  "from": "javis",
  "content": "文本内容",
  "kind": "text",
  "attachments": [{"file_id": "xxx", "name": "a.pdf", "size": 123}],
  "client_msg_id": "随机字符串",
  "created_at": 1700000000
}
```

拉取消息返回：

```json
{"cursor": 43, "messages": [{"id": 43, "from": "sigma", "to": "javis", "kind": "mixed", "content": "…", "attachments": [], "created_at": 1700000000}]}
```

上传文件必须带这些头：

```
X-File-Name: 文件名（UTF-8 后 URL 编码）
Content-Type: 文件 MIME
Content-Length: 字节数
```

## 3. 客户端必须做到

1. 持久化游标：把最后消费的消息 id 存到本地文件；重启后从游标继续，不能重复处理旧消息。
2. 长轮询：监听时用 `wait=30`，没有消息就隔 1 秒再拉；失败按 1/2/5/10/30 秒退避重试。
3. 只拉取 `peer=sigma` 的消息；自己发出的消息不会被自己消费。
4. 收到附件立即下载到本地暂存目录 `./javis_inbox/<消息id>/<文件名>`，文件名做安全清洗。
5. 文件只保存在本地暂存；后续灵动岛接入时再进入它的暂存区，现在至少返回保存路径和大小。
6. 不记录、不打印密钥；不在回复里泄露密钥。
7. 不伪造 Sigma 的消息或回复；所有内容以接口返回为准。
8. 自动回复要克制：收到消息先交给 LLM/用户处理，只有需要回执或用户要求回复时才发消息，避免双方自动互回形成死循环。

## 4. LLM 行为规则

- 每次开始处理与 Sigma 相关的任务前，先 `GET /peers` 确认服务器可达、Sigma 是否在线。
- 用户让你“看看 Sigma 说了什么”：调用 `/messages` 拉取，有附件就下载并说明保存路径。
- 用户让你“回复 Sigma / 把结果发回去”：调用 `POST /messages`，默认不等回复；用户明确要当场等答案才用 `wait=10` 再拉一次。
- 用户让你发文件：先 `POST /files` 上传拿 `file_id`，再随消息发 `attachments`。
- 用户要你处理 Sigma 发来的文件：从 `javis_inbox` 里读取，处理完如需回传再上传并回复。
- 如果连接失败或密钥错误，如实告知用户，不要编造成功或编造对方回复。

## 5. 参考实现（Python 标准库，可直接运行）

保存为 `javis_bridge_client.py`，按需修改 `CONFIG`：

```python
import json, mimetypes, re, sys, time, uuid, urllib.error, urllib.parse, urllib.request
from pathlib import Path

CONFIG = {
    "url": "http://8.159.156.138:8890",
    "key": "Sykes123",
    "agent_id": "javis",
    "peer": "sigma",
    "state_file": "./javis_bridge_state.json",
    "inbox_dir": "./javis_inbox",
    "poll_wait": 30,
    "limit": 20,
}

API_BASE = CONFIG["url"].rstrip("/") + "/api/javis"
STATE_FILE = Path(CONFIG["state_file"])
INBOX_DIR = Path(CONFIG["inbox_dir"])


def _request(method, path, body=None, extra_headers=None, timeout=60):
    headers = {
        "X-Bridge-Key": CONFIG["key"],
        "X-Agent-Id": CONFIG["agent_id"],
        "Accept": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if body is not None:
        if isinstance(body, dict):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data = body
    request = urllib.request.Request(API_BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _json_request(method, path, body=None, timeout=60):
    _, _, raw = _request(method, path, body=body, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


def _identity():
    return f"{API_BASE}|{CONFIG['agent_id']}"


def load_cursor():
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if state.get("identity") == _identity():
            return int(state.get("cursor", 0))
    except (OSError, ValueError):
        pass
    return 0


def save_cursor(cursor):
    STATE_FILE.write_text(
        json.dumps({"identity": _identity(), "cursor": int(cursor)}, ensure_ascii=False),
        encoding="utf-8",
    )


def status():
    health = _json_request("GET", "/health", timeout=10)
    peers = _json_request("GET", "/peers", timeout=10).get("peers", [])
    return {"health": health, "peers": peers, "cursor": load_cursor()}


def poll(wait=None, limit=None, mark_read=True):
    after = load_cursor()
    query = urllib.parse.urlencode({
        "peer": CONFIG["peer"],
        "after": after,
        "limit": limit or CONFIG["limit"],
        "wait": wait if wait is not None else CONFIG["poll_wait"],
    })
    data = _json_request("GET", f"/messages?{query}", timeout=60 + (wait or 0))
    messages = data.get("messages") or []
    if mark_read and messages:
        save_cursor(int(data.get("cursor") or messages[-1]["id"]))
    return messages


def upload(path, peer=None):
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(str(file_path))
    size = file_path.stat().st_size
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = file_path.read_bytes()
    headers = {
        "X-File-Name": urllib.parse.quote(file_path.name),
        "Content-Type": mime,
        "Content-Length": str(size),
    }
    target = peer or CONFIG["peer"]
    data = _json_request("POST", f"/files?to={urllib.parse.quote(target)}", body=body,
                         timeout=300)
    return {"file_id": data["file_id"], "name": data.get("name", file_path.name),
            "size": data.get("size", size)}


def send(content="", attachments=None, peer=None):
    files = [upload(path, peer) for path in (attachments or [])]
    if not content and not files:
        raise ValueError("content 和 attachments 至少提供一项")
    target = peer or CONFIG["peer"]
    payload = {
        "to": target,
        "from": CONFIG["agent_id"],
        "content": content or "",
        "kind": "mixed" if content and files else ("file" if files else "text"),
        "attachments": files,
        "client_msg_id": uuid.uuid4().hex,
        "created_at": int(time.time()),
    }
    return _json_request("POST", "/messages", body=payload)


def _safe_name(name, fallback):
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name or "").strip().strip(".")[:180]
    return name or fallback


def download(file_id, name_hint=None, message_id=None):
    _, headers, raw = _request("GET", f"/files/{file_id}", timeout=300)
    disposition = headers.get("Content-Disposition", "")
    match = re.search(r"filename\*=UTF-8''([^;]+)", disposition)
    remote_name = urllib.parse.unquote(match.group(1)) if match else (name_hint or "")
    filename = _safe_name(remote_name, f"javis_{file_id}")
    target_dir = INBOX_DIR / (str(message_id) if message_id else "files")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    index = 1
    while target.exists():
        target = target_dir / f"{Path(filename).stem}_{index}{Path(filename).suffix}"
        index += 1
    target.write_bytes(raw)
    return str(target)


def handle_message(message):
    """收到 Sigma 消息时的处理入口，按你的 LLM/业务逻辑实现。"""
    saved = []
    for attachment in message.get("attachments") or []:
        saved.append(download(attachment["file_id"], attachment.get("name"), message.get("id")))
    print(f"[Sigma -> Javis] {message.get('content', '')}")
    for path in saved:
        print(f"[附件已暂存] {path}")
    return saved


def listen():
    backoff = 1
    while True:
        try:
            messages = poll()
            for message in messages:
                handle_message(message)
            backoff = 1
            if not messages:
                time.sleep(1)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"[JavisBridge] 拉取失败: {exc}", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    print(json.dumps(status(), ensure_ascii=False, indent=2))
    listen()
```

> 说明：参考实现为便于阅读，上传时会把整个文件读进内存。实际传输超过 50MB 的文件时，建议改用 `http.client` 或 `requests` 流式上传；单文件服务端上限为 200MB。

## 6. 联调验证顺序

1. 在 Javis 电脑确认能访问 `http://8.159.156.138:8890/health`。
2. 运行 `python javis_bridge_client.py`，应打印 `status` 并进入监听。
3. 在 Sigma 侧发送一条测试消息，Javis 控制台应打印 `[Sigma -> Javis] ...`。
4. 在 Javis 侧回复一条，Sigma 用 `poll` 能收到。
5. 双向发一个文件，确认对方能下载。
