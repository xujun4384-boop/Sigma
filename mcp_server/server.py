"""Minimal stdio MCP bridge to a running Sigma backend.

Configure SIGMA_BACKEND_URL when Sigma uses a non-default backend port.
Long tasks run in a background thread; the model starts one, then polls
sigma_task_status / sigma_task_result instead of blocking a single call.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BACKEND = os.environ.get("SIGMA_BACKEND_URL", "http://127.0.0.1:8765").rstrip("/")
CONTROL = os.environ.get("SIGMA_CONTROL_URL", "http://127.0.0.1:8766").rstrip("/")
PROJECT_DIR = Path(os.environ.get("SIGMA_PROJECT_DIR", Path(__file__).resolve().parent.parent)).resolve()
PROTOCOL_VERSION = "2024-11-05"
_sigma_process: subprocess.Popen | None = None

# MCP stdio is UTF-8; Windows Python 3.14 still defaults to the locale codec.
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8")

_TASKS: dict[str, dict[str, Any]] = {}
_TASKS_LOCK = threading.Lock()
_MAX_KEPT_TASKS = 20

# Hosts cancel an MCP tool call after their own per-call budget (DSH defaults to
# 60s), and a cancelled call looks like a Sigma failure even though the task
# keeps running. Read the caller's budget and never advertise or block past it.
def _call_budget_seconds() -> float:
    raw = os.environ.get("SIGMA_MCP_TOOL_TIMEOUT_MS", "60000")
    try:
        milliseconds = float(raw)
    except ValueError:
        milliseconds = 60000.0
    return max(5.0, milliseconds / 1000.0)


CALL_BUDGET_SECONDS = _call_budget_seconds()
# Reserve headroom for transport and the host's own bookkeeping.
MAX_WAIT_SECONDS = max(1.0, CALL_BUDGET_SECONDS - 5.0)


def _snapshot(task_id: str) -> dict[str, Any]:
    with _TASKS_LOCK:
        entry = _TASKS.get(task_id)
        if entry is None:
            raise ValueError(f"Unknown task_id: {task_id}")
        return dict(entry)


def _update(task_id: str, **fields: Any) -> None:
    with _TASKS_LOCK:
        entry = _TASKS.get(task_id)
        if entry is not None:
            entry.update(fields)


def _prune_tasks() -> None:
    """Keep finished tasks bounded; running ones are never dropped."""
    finished = sorted(
        (task_id for task_id, entry in _TASKS.items() if entry["status"] != "running"),
        key=lambda task_id: _TASKS[task_id]["started"],
    )
    for task_id in finished[: max(0, len(_TASKS) - _MAX_KEPT_TASKS)]:
        _TASKS.pop(task_id, None)


def http_json(path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BACKEND + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Sigma returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach Sigma at {BACKEND}: {exc.reason}") from exc


def control_request(method: str, route: str, body: dict | None = None, timeout: float = 3) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        CONTROL + route,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _project_ports() -> tuple[int, int]:
    """Read Sigma's configured ports; the launcher itself uses the same file."""
    try:
        data = json.loads((PROJECT_DIR / "sigma.config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return int(data.get("frontendPort") or 5173), int(data.get("backendPort") or 8765)


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _dist_ready() -> bool:
    return (PROJECT_DIR / "dist" / "index.html").is_file()


def _build_frontend() -> None:
    """Packaged mode loads dist/; build it once when it is missing.

    stdout is the MCP protocol channel, so build output must be redirected to
    stderr as well.
    """
    print("[sigma-mcp] Sigma dist/ is missing, building frontend...", file=sys.stderr, flush=True)
    node = "node.exe" if os.name == "nt" else "node"
    result = subprocess.run(
        [node, "scripts/vite-build.cjs"],
        cwd=PROJECT_DIR,
        stdout=sys.stderr,
        stderr=sys.stderr,
        timeout=600,
    )
    if result.returncode != 0 or not _dist_ready():
        raise RuntimeError("Could not build Sigma's frontend; run `npm run build` inside Sigma and retry.")


def _electron_executable() -> str | None:
    """Locate an Electron distribution without relying on the project-pinned one."""
    if os.name == "nt":
        names = [Path("electron.exe")]
    elif sys.platform == "darwin":
        names = [Path("Electron.app") / "Contents" / "MacOS" / "Electron"]
    else:
        names = [Path("electron")]
    roots = []
    override = os.environ.get("SIGMA_ELECTRON_DIST")
    if override:
        roots.append(Path(override))
    roots.append(PROJECT_DIR / "node_modules" / "electron" / "dist")
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return str(candidate)
    return None


def _launch_command() -> list[str]:
    """Launch Sigma in packaged mode.

    Packaged mode serves dist/index.html over file://, the exact origin that
    holds the user's saved model configuration. Dev mode loads
    http://localhost, a different origin with empty storage, which drops the app
    on its initial configuration screen and gives the MCP bridge no models.
    """
    executable = _electron_executable()
    if executable:
        return [executable, "."]
    # Fallback: the project's own packaged-mode script (builds, then launches).
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return [npm, "run", "electron:win"]


def ensure_sigma_started() -> None:
    global _sigma_process
    try:
        status = control_request("GET", "/mcp/status")
        if status.get("success") and status.get("ready"):
            return
        if status.get("success"):
            # Electron already owns the control port and is starting; wait for
            # its main window instead of spawning a second instance.
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    status = control_request("GET", "/mcp/status", timeout=2)
                    if status.get("success") and status.get("ready"):
                        return
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                    pass
                time.sleep(0.5)
            raise RuntimeError(f"Sigma Electron control endpoint is alive but its window did not become ready at {CONTROL}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass

    package_json = PROJECT_DIR / "package.json"
    electron_main = PROJECT_DIR / "electron" / "main.cjs"
    if not package_json.is_file() or not electron_main.is_file():
        raise RuntimeError(f"Sigma source project not found at {PROJECT_DIR}; set SIGMA_PROJECT_DIR to its directory")

    _frontend_port, backend_port = _project_ports()
    if _port_in_use(backend_port):
        raise RuntimeError(
            f"Port {backend_port} is already in use while Sigma's control endpoint stays silent. "
            "A leftover Sigma backend is probably still running; stop that process and retry."
        )

    if not _dist_ready():
        _build_frontend()

    if _sigma_process is None or _sigma_process.poll() is not None:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        environment = dict(os.environ)
        # main.cjs serves dist/ only when NODE_ENV is not "development"; the DSH
        # kernel may inherit a dev NODE_ENV, which would flip Sigma onto the
        # empty http://localhost origin again.
        environment["NODE_ENV"] = "production"
        # A project-pinned Electron may be unusable on this machine; a working
        # distribution can be supplied explicitly and the launcher picks it up.
        electron_dist = environment.get("SIGMA_ELECTRON_DIST")
        if electron_dist and os.path.isdir(electron_dist):
            environment["ELECTRON_OVERRIDE_DIST_PATH"] = electron_dist
        try:
            _sigma_process = subprocess.Popen(
                _launch_command(),
                cwd=PROJECT_DIR,
                stdin=subprocess.DEVNULL,
                stdout=sys.stderr,
                stderr=sys.stderr,
                env=environment,
                creationflags=creationflags,
                start_new_session=(os.name != "nt"),
            )
        except OSError as exc:
            raise RuntimeError(f"Could not start Sigma from {PROJECT_DIR}: {exc}") from exc

    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if _sigma_process.poll() is not None:
            raise RuntimeError(f"Sigma launcher exited with code {_sigma_process.returncode}; check the Sigma terminal output")
        try:
            status = control_request("GET", "/mcp/status", timeout=2)
            if status.get("success") and status.get("ready"):
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for Sigma Electron at {CONTROL}; last error: {last_error}")


def activate_sigma(workspace: str) -> None:
    ensure_sigma_started()
    try:
        result = control_request("POST", "/mcp/activate", {"workspace_path": workspace}, timeout=15)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Cannot activate Sigma Electron (HTTP {exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Sigma Electron activation failed: {exc}") from exc
    if not result.get("success"):
        raise RuntimeError("Cannot activate Sigma Electron: " + str(result.get("error", "unknown error")))


def validate_task_args(args: dict[str, Any]) -> dict[str, Any]:
    task = args.get("task")
    model_id = args.get("model_id")
    workspace = args.get("workspace_path")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    if model_id is not None and (not isinstance(model_id, str) or not model_id):
        raise ValueError("model_id must be a registered Sigma model ID when supplied")
    if not isinstance(workspace, str) or not os.path.isabs(workspace):
        raise ValueError("workspace_path must be the absolute path of the shared workspace")
    if not os.path.isdir(workspace):
        raise ValueError("workspace_path must identify an existing directory")
    session_id = args.get("session_id")
    return {
        "task": task,
        "model_id": model_id or None,
        "workspace_path": workspace,
        "session_id": session_id if isinstance(session_id, str) and session_id else None,
    }


def wait_for_models(timeout: float = 25.0) -> list:
    """Sigma's frontend syncs its model registry after mount; poll until it arrives."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            models = http_json("/api/mcp/models").get("models", [])
            if models:
                return models
        except RuntimeError:
            pass
        time.sleep(1)
    return []


def resolve_model_id(explicit: str | None) -> str:
    """Sigma's model registry lives in its running frontend, so resolve late."""
    if explicit:
        return explicit
    models = wait_for_models()
    if not models:
        raise RuntimeError(
            "Sigma reports no registered models yet. Its window is starting: open Settings once, "
            "make sure at least one model is configured, then retry."
        )
    first = models[0]
    return str(first.get("id") if isinstance(first, dict) else first)


def run_task(task_id: str, spec: dict[str, Any]) -> str:
    """Stream one Sigma task to completion, publishing progress into the registry."""
    workspace = spec["workspace_path"]
    activate_sigma(workspace)
    model_id = resolve_model_id(spec["model_id"])
    _update(task_id, model_id=model_id, last_event="submitting")
    request = urllib.request.Request(
        BACKEND + "/api/mcp/tasks",
        data=json.dumps({
            "task": spec["task"],
            "model_id": model_id,
            "workspace_path": workspace,
            "session_id": spec["session_id"],
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    texts: list[str] = []
    events: list[str] = []
    try:
        response = urllib.request.urlopen(request, timeout=60 * 60)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Sigma task request failed (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Sigma task connection failed: {exc.reason}") from exc

    completed = False
    with response:
        content_type = response.headers.get("Content-Type", "")
        if "text/event-stream" not in content_type:
            payload = json.loads(response.read().decode("utf-8"))
            raise RuntimeError(str(payload.get("error") or payload.get("message") or payload))
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            kind = event.get("type")
            if kind == "text" and event.get("contentType", "text") == "text":
                texts.append(str(event.get("content", "")))
            elif kind == "tool_start":
                events.append(f"tool_start: {event.get('tool_name', 'unknown')}")
            elif kind == "tool_result":
                events.append(f"tool_result: {event.get('tool_name', 'unknown')} ({'ok' if event.get('success') else 'failed'})")
            elif kind in ("questionnaire", "tool_timeout"):
                raise RuntimeError(
                    "Sigma paused for user interaction ("
                    + str(kind)
                    + "). This MCP bridge cannot answer interactive prompts; handle it in Sigma UI and retry."
                )
            elif kind == "error":
                raise RuntimeError(str(event.get("message", "Sigma task failed")))
            elif kind == "chat_complete":
                completed = True
                _update(task_id, events=events[-60:], last_event="chat_complete",
                        text_length=sum(len(part) for part in texts))
                break
            _update(task_id, events=events[-60:], last_event=f"{kind}: {events[-1] if events else ''}".strip())

    if not completed:
        raise RuntimeError("Sigma task stream ended before chat_complete")
    result = "".join(texts).strip()
    if not result:
        result = "Sigma completed without a text response."
    if events:
        result += "\n\nExecution summary:\n" + "\n".join(events[-60:])
    return result


def start_task(args: dict[str, Any]) -> str:
    spec = validate_task_args(args)

    def worker() -> None:
        try:
            text = run_task(task_id, spec)
            _update(task_id, status="completed", text=text, finished=time.time(), last_event="completed")
        except Exception as exc:  # noqa: BLE001 - surfaced to the model as task failure
            _update(task_id, status="failed", error=str(exc), finished=time.time(), last_event="failed")

    task_id = uuid.uuid4().hex[:12]
    with _TASKS_LOCK:
        _TASKS[task_id] = {
            "id": task_id,
            "status": "running",
            "started": time.time(),
            "finished": None,
            "last_event": "queued",
            "events": [],
            "text": "",
            "error": None,
            "text_length": 0,
            "model_id": spec["model_id"],
            "workspace_path": spec["workspace_path"],
            "session_id": spec["session_id"],
        }
        _prune_tasks()
    threading.Thread(target=worker, name=f"sigma-task-{task_id}", daemon=True).start()
    return json.dumps({
        "task_id": task_id,
        "status": "running",
        "hint": "Poll sigma_task_result with this task_id; pass wait_seconds to block briefly.",
    }, ensure_ascii=False)


def task_status(args: dict[str, Any]) -> str:
    task_id = args.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id must be a non-empty string")
    entry = _snapshot(task_id)
    elapsed = round((entry["finished"] or time.time()) - entry["started"], 1)
    return json.dumps({
        "task_id": task_id,
        "status": entry["status"],
        "elapsed_seconds": elapsed,
        "last_event": entry["last_event"],
        "recent_events": entry["events"][-15:],
        "text_length": entry["text_length"],
        "error": entry["error"],
    }, ensure_ascii=False)


def task_result(args: dict[str, Any]) -> str:
    task_id = args.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id must be a non-empty string")
    wait_seconds = args.get("wait_seconds", 0)
    if not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool):
        raise ValueError("wait_seconds must be a number")
    requested = min(max(float(wait_seconds), 0.0), MAX_WAIT_SECONDS)
    deadline = time.monotonic() + requested

    entry = _snapshot(task_id)
    while entry["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.5)
        entry = _snapshot(task_id)

    if entry["status"] == "running":
        elapsed = round(time.time() - entry["started"], 1)
        return json.dumps({
            "task_id": task_id,
            "status": "running",
            "elapsed_seconds": elapsed,
            "waited_seconds": round(requested, 1),
            "wait_limit_seconds": round(MAX_WAIT_SECONDS, 1),
            "last_event": entry["last_event"],
            "recent_events": entry["events"][-15:],
            "hint": "Still running. Call sigma_task_result again to keep waiting; each call waits at most wait_limit_seconds.",
        }, ensure_ascii=False)
    if entry["status"] == "failed":
        raise RuntimeError(str(entry["error"]))
    return entry["text"]


TOOLS = [
    {
        "name": "sigma_list_models",
        "description": "List models currently registered by the Sigma frontend. Starts Sigma when it is not running (its window opens for visualization), then returns only non-secret model metadata and IDs.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "sigma_run_task",
        "description": "Start a task in Sigma's ToolLoop and return immediately with a task_id. Pass the same absolute workspace path used by the caller. model_id is optional: omit it to use Sigma's first registered model. Sigma can read its project memory and use its skills. Follow up with sigma_task_result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The concrete task Sigma should execute."},
                "workspace_path": {"type": "string", "description": "Absolute path to the exact shared project workspace."},
                "model_id": {"type": "string", "description": "Optional registered Sigma model ID; omit to use the first registered model."},
                "session_id": {"type": "string", "description": "Optional stable session ID to continue a Sigma task context."},
            },
            "required": ["task", "workspace_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "sigma_task_status",
        "description": "Check one Sigma task without waiting: status, elapsed time, recent tool events, and the last event kind.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "Task ID returned by sigma_run_task."}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "sigma_task_result",
        "description": (
            "Return the final text of a Sigma task. If it is still running, optionally wait before "
            f"reporting progress (wait_seconds, at most {MAX_WAIT_SECONDS:.0f} per call). Long work such as "
            "image generation needs several calls; each one returns promptly with the current status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID returned by sigma_run_task."},
                "wait_seconds": {
                    "type": "number",
                    "description": f"Optional wait before reporting progress, 0-{MAX_WAIT_SECONDS:.0f} seconds.",
                },
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
]


def reply(message_id: Any, result: dict | None = None, error: dict | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id}
    payload["error" if error is not None else "result"] = error if error is not None else result
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(message: dict) -> None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    if method == "notifications/initialized" or method == "notifications/cancelled":
        return
    if method == "initialize":
        reply(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "sigma-mcp", "version": "0.2.0"},
        })
        return
    if method == "ping":
        reply(request_id, {})
        return
    if method == "tools/list":
        reply(request_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "sigma_list_models":
                ensure_sigma_started()
                models = wait_for_models()
                if not models:
                    raise RuntimeError(
                        "Sigma is running but has not synced any model yet. Open Settings once, "
                        "make sure at least one model is configured, then retry."
                    )
                text = json.dumps(models, ensure_ascii=False, indent=2)
            elif name == "sigma_run_task":
                text = start_task(args)
            elif name == "sigma_task_status":
                text = task_status(args)
            elif name == "sigma_task_result":
                text = task_result(args)
            else:
                raise ValueError(f"Unknown tool: {name}")
            reply(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as exc:
            reply(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return
    if request_id is not None:
        reply(request_id, error={"code": -32601, "message": f"Method not found: {method}"})


def main() -> None:
    # MCP stdio is line-delimited JSON-RPC; stdout must contain protocol only.
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if isinstance(message, dict):
                handle(message)
        except Exception as exc:
            print(f"sigma-mcp: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
