"""computer_use skill —— 混合式桌面操作工具（供 LLM 调用）。

策略（混合式）：
1. 优先 uia_tree 读取控件树 → click_element / set_element_value 按「元素」操作，无坐标误差；
2. 控件树覆盖不到（自绘控件 / 游戏 / 跨进程浮层）时，降级到 screenshot + 坐标点击；
3. 坐标一律以「截图像素」给出，引擎自动换算回真实屏幕坐标。

保留 Computer Use 独有动作：drag（拖拽）、long_press（长按）、type_text/key/hotkey（键盘）。

人机协同：执行每一步前会检查会话状态——被暂停/接管时阻塞等待；被停止时中止；
用户提交的纠正（correction）会在动作边界回传给 LLM，促使它即时调整计划。
"""
from __future__ import annotations

import json
import time

from skills.base import BaseTool, ToolParameter, ToolResult
from computer_use.engine import DesktopController
from computer_use.manager import computer_use_manager as CM
from computer_use.vision import describe_image


_COORD_ACTIONS = {"move", "click", "right_click", "double_click", "long_press", "drag"}
_UIA_ACTIONS = {
    "click_element": "click",
    "double_click_element": "double_click",
    "invoke_element": "invoke",
    "focus_element": "focus",
    "set_element_value": "set_value",
    "type_element": "set_value",
}

# 屏幕理解的默认提示：只描述确凿所见，禁止臆测，服务于「确认状态」这一目的
_SCREEN_PROMPT = (
    "这是 Windows 桌面当前截图。请客观描述：前台是哪个窗口/程序、"
    "可见的关键控件（按钮、菜单、图标、输入框、列表项）及大致位置、"
    "以及当前界面处于什么状态（例如某个窗口是否已打开、是否停在某个页面）。"
    "用简体中文，只描述你确实看到的内容，不要臆测或补充常识。"
)


class ComputerUseTool(BaseTool):
    name = "computer_use"
    description = (
        "混合式桌面自动化：操作当前电脑的任意 GUI（Windows 桌面、原生软件、浏览器窗口等）。\n"
        "使用 actions 数组逐步操作，一步失败即停止。\n\n"
        "【首选】结构化路径：uia_tree 读取控件树 → click_element/set_element_value 按元素操作。\n"
        "【兜底】像素路径：screenshot 拿到画面（返回文字识别 description）→ 用截图像素坐标 click/drag/long_press（系统自动换算坐标）。\n\n"
        "保留能力：drag 拖拽、long_press 长按、type_text 输入、key 按键、hotkey 组合键。\n"
        "术语：screenshot 返回的坐标即「截图像素坐标」，直接用于 click/drag 即可。"
    )
    parameters = [
        ToolParameter(
            "actions",
            "array",
            "桌面操作序列，每步含 action 及参数。\n"
            "示例: [{\"action\":\"uia_tree\"},{\"action\":\"click_element\",\"ref\":\"@u3\"},"
            "{\"action\":\"type_text\",\"text\":\"hello\"},{\"action\":\"hotkey\",\"keys\":\"ctrl+s\"}]",
            required=True,
        ),
        ToolParameter("task", "string", "当前任务目标（可选，用于日志）", required=False, default=""),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)
        self._engine = DesktopController()
        self._last_refresh = 0.0

    # ── 入口 ──

    def execute(self, actions: list, task: str = "", **kwargs) -> ToolResult:
        if not actions:
            return ToolResult.fail("请提供 actions 参数")

        caps = self._engine.capabilities()

        # 用户纠正优先：若在动作前已有纠正，直接回传，让 LLM 重新规划
        pending = CM.consume_corrections()
        if pending:
            return ToolResult.ok(json.dumps({
                "user_correction": pending,
                "note": "用户在你上一次决策后提交了纠正，请据此调整计划后再执行。",
                "capabilities": caps,
            }, ensure_ascii=False, indent=2))

        results: list[dict] = []
        stopped_early = False
        corr_after: list[str] = []

        for i, step in enumerate(actions):
            if not isinstance(step, dict) or "action" not in step:
                results.append({"index": i, "success": False, "error": f"步骤 {i} 缺少 'action'"})
                stopped_early = True
                break

            # 可操作性闸门：暂停 / 接管时在此阻塞
            if not CM.wait_until_operable():
                results.append({"index": i, "action": step.get("action"), "success": False,
                                "error": "会话已被停止"})
                stopped_early = True
                break

            action = str(step["action"])
            params = {k: v for k, v in step.items() if k != "action"}
            try:
                out = self._run(action, params)
            except Exception as e:
                out = {"success": False, "error": f"{type(e).__name__}: {e}"}
            out["index"] = i
            results.append(out)
            CM.log_action(action, out.get("summary") or out.get("error", ""), out.get("success", False))

            if not out.get("success"):
                stopped_early = True
                break

            # 动作边界检查纠正：中途纠正 → 中止剩余步骤，交回 LLM
            corr = CM.consume_corrections()
            if corr:
                corr_after = corr
                stopped_early = True
                break

        # 组装回喂内容：结果即文本（含 screenshot 的视觉描述）
        payload = {
            "total": len(actions),
            "completed": len([r for r in results if r.get("success")]),
            "stopped_early": stopped_early,
            "capabilities": caps,
            "results": results,
        }
        if corr_after:
            payload["user_correction"] = corr_after
            payload["note"] = "用户提交了纠正，剩余步骤已取消，请据此调整计划。"

        content = json.dumps(payload, ensure_ascii=False, indent=2)
        all_ok = not stopped_early
        return ToolResult.ok(content) if all_ok else ToolResult.fail(content)

    # ── 单步分派 ──

    def _run(self, action: str, p: dict) -> dict:
        a = (action or "").strip().lower()

        if a == "screenshot":
            cap = self._engine.capture(quality=int(p.get("quality", 50)))
            CM.push_frame(cap)
            out = {
                "success": True,
                "summary": f"截图 图像{cap['image_width']}x{cap['image_height']} / 屏幕{cap['screen_width']}x{cap['screen_height']}",
                "image_width": cap["image_width"],
                "image_height": cap["image_height"],
                "note": "以下 description 来自对当前截图的识别（主 LLM）。坐标按截图像素给出，系统自动换算回真实屏幕坐标。",
            }
            try:
                out["description"] = describe_image(cap["image"], cap["mime"], p.get("prompt") or _SCREEN_PROMPT)
            except Exception as e:
                out["vision_error"] = str(e)
                out["note"] = "本次截图视觉识别失败，界面无法确认；请改用 uia_tree 获取控件树来判断当前状态。"
            return out

        if a == "describe_screen":
            cap = self._engine.capture(quality=int(p.get("quality", 55)))
            CM.push_frame(cap)
            text = describe_image(cap["image"], cap["mime"], p.get("prompt") or _SCREEN_PROMPT)
            return {"success": True, "summary": "视觉描述完成", "description": text}

        if a in ("uia_tree", "tree", "ax_tree"):
            interactive_only = p.get("interactive_only", True)
            if isinstance(interactive_only, str):
                interactive_only = interactive_only.strip().lower() not in ("false", "0", "no")
            nodes = self._engine.uia_tree(
                max_depth=int(p.get("max_depth", 12)),
                max_nodes=int(p.get("max_nodes", 200)),
                interactive_only=bool(interactive_only),
            )
            return {
                "success": True,
                "summary": f"控件树 {len(nodes)} 个节点",
                "nodes": nodes,
                "hint": "click_element / set_element_value / focus_element 的 ref 必须直接使用 nodes[].ref（形如 @u3），不要自行拼接或改写路径。",
            }

        if a in _UIA_ACTIONS:
            # 兼容模型把元素引用放在 ref / element / element_ref 等字段
            ref = p.get("ref") or p.get("element") or p.get("element_ref")
            if isinstance(ref, str):
                ref = ref.strip()
                # 引用形如 @u3；容错补全漏写的 @
                if ref and not ref.startswith("@") and ref[:1].lower() == "u" and ref[1:].isdigit():
                    ref = "@" + ref
            if not ref:
                return {"success": False, "error": f"{a} 需要 ref 参数（来自 uia_tree 的 @uN）"}
            act = _UIA_ACTIONS[a]
            # 兼容模型用 clicks/button 表达双击
            clicks = p.get("clicks")
            if isinstance(clicks, str) and clicks.isdigit():
                clicks = int(clicks)
            btn = str(p.get("button", "")).lower()
            if act == "click" and ((isinstance(clicks, int) and clicks >= 2) or btn in ("double", "doubleclick", "double_click", "left_double")):
                act = "double_click"
            out = self._engine.uia_action(ref, act, text=p.get("text") or p.get("value"))
            self._refresh()
            name = out.get("name") if isinstance(out, dict) else ""
            return {"success": True, "summary": f"{act} {ref} {name}", **(out or {})}

        if a in _COORD_ACTIONS:
            return self._coord_action(a, p)

        if a in ("type_text", "type", "input_text"):
            self._engine.type_text(p.get("text", p.get("value", "")), interval=float(p.get("interval", 0.02)))
            self._refresh()
            return {"success": True, "summary": "已输入文本"}

        if a in ("key", "press"):
            key_name = p.get("key") or p.get("value")
            if not key_name:
                return {"success": False, "error": "key 需要 key 参数"}
            self._engine.key(key_name)
            self._refresh()
            return {"success": True, "summary": f"按键 {key_name}"}

        if a in ("hotkey", "shortcut"):
            keys = p.get("keys") or p.get("key")
            if not keys:
                return {"success": False, "error": "hotkey 需要 keys 参数"}
            self._engine.hotkey(keys)
            self._refresh()
            return {"success": True, "summary": f"组合键 {keys}"}

        if a == "wait":
            time.sleep(min(float(p.get("duration", 500)) / 1000.0, 60.0))
            return {"success": True, "summary": "等待完成"}

        return {"success": False, "error": f"未知操作: {action}"}

    def _coord_action(self, a: str, p: dict) -> dict:
        e = self._engine

        def screen(x, y):
            return e.to_screen(x, y)

        if a == "move":
            sx, sy = screen(p["x"], p["y"])
            e.move(sx, sy, duration=float(p.get("duration", 0.2)))
            self._refresh()
            return {"success": True, "summary": f"移动到 ({sx},{sy})"}

        if a == "click":
            sx, sy = screen(p["x"], p["y"])
            e.click(sx, sy, button=p.get("button", "left"), clicks=int(p.get("clicks", 1)))
            self._refresh()
            return {"success": True, "summary": f"点击 ({sx},{sy})"}

        if a == "right_click":
            sx, sy = screen(p["x"], p["y"])
            e.click(sx, sy, button="right")
            self._refresh()
            return {"success": True, "summary": f"右键 ({sx},{sy})"}

        if a == "double_click":
            sx, sy = screen(p["x"], p["y"])
            e.click(sx, sy, clicks=2)
            self._refresh()
            return {"success": True, "summary": f"双击 ({sx},{sy})"}

        if a == "long_press":
            sx, sy = screen(p["x"], p["y"])
            e.long_press(sx, sy, duration=float(p.get("duration", 1.0)), button=p.get("button", "left"))
            self._refresh()
            return {"success": True, "summary": f"长按 ({sx},{sy}) {p.get('duration', 1.0)}s"}

        if a == "drag":
            x1, y1 = screen(p["x1"], p["y1"])
            x2, y2 = screen(p["x2"], p["y2"])
            e.drag(x1, y1, x2, y2, duration=float(p.get("duration", 0.5)), button=p.get("button", "left"))
            self._refresh()
            return {"success": True, "summary": f"拖拽 ({x1},{y1}) → ({x2},{y2})"}

        return {"success": False, "error": f"未知坐标操作: {a}"}

    def _refresh(self):
        """动作后抓一帧预览推给悬浮窗（不改变坐标基准，不返回给 LLM）。"""
        now = time.time()
        if now - self._last_refresh < 0.15:
            return
        self._last_refresh = now
        try:
            CM.push_frame(self._engine.capture_preview())
        except Exception:
            pass


skill = ComputerUseTool()
