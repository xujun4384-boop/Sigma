# Debug Session: canvas-stale-content

Status: [OPEN]

## Symptom
LLM 调用 canvas 成功，但 Excalidraw 画布没有按预期更新，仍显示之前的“上海品天投资”等内容。新建画布并选择不保存后，刷新或重启仍会重新出现旧内容。

## Hypotheses
1. `canvas_patch` 事件只被 ChatPanel 的流式读取分支消费，未进入统一 `handleSSEEvent` 分发。
2. 补丁到达前端，但 Excalidraw API 尚未就绪或画布名称切换，导致补丁被跳过。
3. 旧内容来自持久化的 `.excalidraw` 数据或当前画布名称恢复逻辑。
4. 新建画布“不保存”只改变前端状态，没有清除或隔离旧画布数据。

## Evidence Plan
- 记录后端 canvas_update 执行和 SSE 事件。
- 记录 ChatPanel 收到的 canvas_patch 及统一分发情况。
- 记录 CanvasPanel 当前画布名、补丁目标、API 是否就绪、加载结果和应用结果。
- 记录新建画布、画布加载和保存路径/名称。

## State
- [OPEN]
- No business logic fix applied before runtime evidence.
