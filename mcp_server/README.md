# Sigma MCP bridge

This is a standalone stdio MCP server that delegates to Sigma's local FastAPI backend. If Sigma is not already running, MCP starts the current source project with `npm run electron:dev`; that script starts Vite and Electron, and Electron starts the Python backend. MCP waits for Electron readiness, then before each task asks the Electron main process to show/focus its window and switch the visible workspace to the exact shared path. It avoids deliberately launching a second copy when the loopback control endpoint is already available. Set `SIGMA_PROJECT_DIR` if this file is not under the Sigma project directory. The Electron build must include the MCP control listener (restart Sigma after updating its main process).

## Run

```powershell
$env:SIGMA_BACKEND_URL = 'http://127.0.0.1:8765'
python .\mcp_server\server.py
```

Register it in your MCP client as a stdio server with command `python` and args `C:\path\to\sigma\mcp_server\server.py`. Set `SIGMA_BACKEND_URL` in the MCP server environment if Sigma uses a different backend port.

## Tools

- `sigma_list_models`: returns registered IDs and non-secret model selection metadata.
- `sigma_run_task`: takes a task, a registered model ID, and the exact absolute shared workspace path. Optionally specify a stable `session_id` to continue the same Sigma ToolLoop session. Returns immediately with a `task_id`; the task runs in a background thread.
- `sigma_task_status`: reports one task's status, elapsed seconds, recent tool events, and last event kind without waiting.
- `sigma_task_result`: returns the final text once the task finishes; `wait_seconds` (0-120) blocks briefly before reporting progress again.

Long tasks therefore never occupy a single MCP call: start with `sigma_run_task`, then poll `sigma_task_result` (the tool descriptions tell the model to do this).

When MCP starts Sigma, the Electron window is displayed on the desktop. You can set `SIGMA_PROJECT_DIR` to the Sigma source directory; if the MCP server lives inside that project, its parent directory is used by default. If Vite/Electron dependencies are unavailable or the launcher exits, the MCP task reports the startup failure. The MCP process intentionally does not kill Sigma on shutdown.

Interactive Sigma questionnaire and tool-timeout events currently fail clearly rather than hanging the MCP call; handle such prompts in the Sigma UI and retry. Cancellation from the MCP client is not yet wired to Sigma's `/api/stop-task` endpoint.
