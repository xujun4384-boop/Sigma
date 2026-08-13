"""Canvas skill - Excalidraw 画布增量更新工具。"""
from __future__ import annotations

from typing import Any, Callable

from skills.base import BaseTool, ToolParameter, ToolResult


class CanvasUpdateTool(BaseTool):
    """将 Excalidraw 元素骨架以增量补丁推送到前端画布。"""

    name = "canvas_update"
    description = (
        "创建或更新 Canvas 画布。elements 使用 Excalidraw 元素对象，支持丰富的视觉属性。"
        "带文字的形状必须用容器-文本绑定：容器加 id 和 boundElements:[{type:'text',id:'txt-1'}]，"
        "文本元素加 containerId:'容器id'、textAlign:'center'、verticalAlign:'middle'，"
        "文字会自动居中在容器内，禁止用独立的 rectangle + text 叠加。"
        "基础骨架: {type:'rectangle',x:100,y:100,width:220,height:80}; "
        "{type:'text',x:130,y:125,text:'步骤 1'}; "
        "{type:'arrow',x:320,y:140,width:100,height:0,points:[[0,0],[100,0]]}。"
        "可选视觉属性: strokeColor(描边色), backgroundColor(填充色), strokeWidth(线宽), "
        "fillStyle(solid/hachure/cross-hatch), roughness(0光滑/1手绘/2粗糙), "
        "roundness(圆角), fontSize(字号), fontFamily(1手写/2正常/3代码), textAlign。"
        "默认 add 只追加元素，不覆盖已有内容；replace 重建整张画布。"
        "⚠️ 同一批 elements 中 id 必须唯一；重复 id 会被自动去重，保留最后一个。"
    )
    parameters = [
        ToolParameter("elements", "array", "要新增或替换的 Excalidraw 元素骨架数组", required=True),
        ToolParameter("operation", "string", "add 为追加元素；replace 为明确重建整张画布", required=False, enum=["add", "replace"], default="add"),
        ToolParameter("canvas_name", "string", "目标画布名称，始终使用 default（默认画布），不要随意起名", required=False, default="default"),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)
        self._progress_callback: Callable[[dict[str, Any]], None] | None = None

    def set_progress_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._progress_callback = callback

    def _deduplicate_elements(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按 id 去重，保留最后一个出现的元素（假设后面的更正确）。
        
        流式生成时，模型可能因自我修正而重复发送同一元素。
        按 id 去重确保画布上每个 id 只出现一次。
        """
        if not elements:
            return elements
        seen: dict[str, int] = {}  # id -> index
        for i, el in enumerate(elements):
            el_id = el.get("id")
            if el_id:
                seen[el_id] = i
        # 保留每个 id 最后出现的索引
        keep_indices = set(seen.values())
        # 无 id 的元素始终保留（无法去重）
        result = []
        for i, el in enumerate(elements):
            if not el.get("id") or i in keep_indices:
                result.append(el)
        return result

    def execute(self, elements: list[dict[str, Any]], operation: str = "add", canvas_name: str = "default", **_: Any) -> ToolResult:
        if not isinstance(elements, list) or not elements:
            return ToolResult.fail("elements 必须是非空数组")
        if operation not in ("add", "replace"):
            return ToolResult.fail("operation 仅支持 add 或 replace")

        # 按 id 去重，解决流式生成中重复元素的问题
        deduped = self._deduplicate_elements(elements)
        dup_count = len(elements) - len(deduped)

        safe_name = str(canvas_name or "default").replace("/", "_").replace("\\", "_")
        event = {
            "type": "canvas_patch",
            "canvas_name": safe_name,
            "operation": operation,
            "elements": deduped,
        }
        if self._progress_callback:
            self._progress_callback(event)
        action = "追加" if operation == "add" else "重建"
        msg = f"已向画布“{safe_name}”{action} {len(deduped)} 个元素"
        if dup_count > 0:
            msg += f"（自动去除 {dup_count} 个重复元素）"
        return ToolResult.ok(msg)
