# Debug Session: ask-user-chatbar

Status: [OPEN]

## Symptom
LLM triggers Ask User, after which Chatbar frontend rendering crashes. Retrying refreshes the page and loses state; task completion state is unknown.

## Falsifiable hypotheses
1. The Ask User event payload has a shape the Chatbar renderer does not handle, causing a JavaScript render exception.
2. The retry handler uses a full-page navigation/reload rather than restoring the failed message in client state.
3. Ask User leaves the active request or task state unresolved, so a subsequent retry conflicts with an in-flight request.
4. Persisted chat/task state serialization fails when it contains the Ask User event or callback metadata.
5. A backend stream/event error after Ask User is not handled by the frontend and causes the render state to become inconsistent.

## Evidence to collect
- Current backend and frontend runtime logs around the failing Ask User event.
- Browser console error and network request sequence.
- Chatbar Ask User event rendering and retry state-management paths.
