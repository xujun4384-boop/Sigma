# Debug Session: llm-internal-server-error

Status: [OPEN]

## Symptom
All configured primary LLMs return `Error: Internal Server Error`.

## Hypotheses
1. A recent SkillManager constructor/configuration change breaks server initialization for all LLM requests.
2. `server.py` contains duplicate or invalid image configuration injection that raises during request handling.
3. The LLM request succeeds, but response streaming/tool registration fails uniformly afterward.
4. The running backend/frontend is stale or partially updated relative to the workspace files.

## Evidence
- Backend is listening on `127.0.0.1:8765`.
- `server.py` passes `image_gen_provider` into `SkillManager(...)`.
- `SkillManager.__init__` previously used `image_gen_provider` but did not declare it, causing request-time `TypeError` and HTTP 500 for all LLM requests.

## Root Cause
Missing `image_gen_provider` constructor parameter in `skills/manager.py`.

## Fix
Added `image_gen_provider: str = "ark"` to `SkillManager.__init__`.

## Verification
- `SkillManager(image_gen_provider="ark")` initializes successfully.
- Python compilation passes for `server.py`, `skills/manager.py`, and `skills/image_generate/__init__.py`.
- Existing backend process must be restarted to load the fix.

Status: [FIXED_PENDING_RESTART]
