"""桌面控制引擎：截图 / UI Automation 控件树 / 鼠标键盘。

坐标系约定（关键）：
- 截图与鼠标键盘统一走 pyautogui 的屏幕坐标系，避免「截图来自 A 库、点击来自 B 库」
  造成的 DPI / 缩放错位。
- 截图会按视觉模型的处理上限做下采样，并记录缩放比；坐标类操作传入的是「截图像素
  坐标」，由 to_screen() 换算回真实屏幕坐标。
- UI Automation 路径按控件对象直接操作（Click / SetValue），不依赖坐标。
"""
from __future__ import annotations

import base64
import io
import threading
import time
from typing import Any

# ── 可选依赖探测：缺失时降级而非崩溃 ──
try:
    import pyautogui as _pag

    try:
        _pag.FAILSAFE = False  # 关闭角落急停，避免自动化时误触发
        _pag.PAUSE = 0.03
    except Exception:
        pass
except Exception:  # pragma: no cover - 环境相关
    _pag = None

try:
    from PIL import Image  # noqa: F401
except Exception:  # pragma: no cover
    Image = None

try:
    import pyperclip as _clip
except Exception:  # pragma: no cover
    _clip = None

try:
    import uiautomation as _uia

    try:
        _uia.SetGlobalSearchTimeout(2)
    except Exception:
        pass
except Exception:  # pragma: no cover - 仅 Windows 且有该库时可用
    _uia = None


# 与主流视觉模型的长边处理上限对齐：超过会被服务端下采样，导致坐标漂移
MAX_LONG_EDGE = 1568

# UIA 控件类型白名单（按控件"类型"筛选，不是按名称关键词匹配）：
# 只保留可交互控件 + 少量结构性锚点，避免 200 节点配额被 Pane/Group/Custom 容器占满。
_INTERACTIVE_UIA_TYPES = {
    "ButtonControl", "CheckBoxControl", "RadioButtonControl", "ComboBoxControl",
    "EditControl", "HyperlinkControl", "ListItemControl", "MenuItemControl",
    "SplitButtonControl", "TabItemControl", "TreeItemControl", "DataItemControl",
    "SliderControl", "SpinnerControl", "HeaderItemControl", "ThumbControl",
}
_LANDMARK_UIA_TYPES = {
    "WindowControl", "MenuControl", "MenuBarControl", "ToolBarControl",
    "TabControl", "ListControl", "TreeControl", "DataGridControl", "DocumentControl",
}
_USEFUL_UIA_TYPES = _INTERACTIVE_UIA_TYPES | _LANDMARK_UIA_TYPES

# uiautomation 依赖 COM，且要求在每个使用它的线程里初始化（工具跑在线程池工作线程里）
_thread_local = threading.local()


def _ensure_uia_thread() -> None:
    """在当前线程初始化 UIAutomation（COM）。线程池worker线程首次使用前必须调用。"""
    if _uia is None:
        return
    if getattr(_thread_local, "uia_ready", False):
        return
    try:
        _uia.InitializeUIAutomationInCurrentThread()
    except Exception:
        # 退路：直接初始化 COM 单元
        try:
            import comtypes  # type: ignore
            comtypes.CoInitialize()
        except Exception:
            pass
    _thread_local.uia_ready = True


class DesktopController:
    """一个桌面控制会话的底层能力封装（无状态持久化，坐标基准随截图更新）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._uia_refs: dict[str, Any] = {}
        self._uia_seq = 0
        # 记录「最近一次返回给上层/LLM 的截图」的换算基准。
        # 预览帧（仅供悬浮窗看）不会覆盖它，保证坐标基准稳定。
        self._last_capture: dict[str, Any] = {}

    # ── 能力探测 ──

    def capabilities(self) -> dict:
        return {
            "input": _pag is not None,      # 鼠标键盘
            "capture": _pag is not None,    # 截图（依赖 pyautogui）
            "pillow": Image is not None,    # 缩放/编码
            "uia": _uia is not None,        # UI Automation 控件树
            "clipboard": _clip is not None,  # 非 ASCII 文本粘贴
        }

    def _require_input(self):
        if _pag is None:
            raise RuntimeError(
                "pyautogui 不可用，无法进行鼠标/键盘/截图操作。请安装依赖: pip install pyautogui"
            )

    # ── 截图 ──

    def capture(self, max_long_edge: int = MAX_LONG_EDGE, quality: int = 55) -> dict:
        """抓取主屏并编码为 JPEG；作为返回给上层的基准截图，会更新坐标基准。"""
        return self._grab(max_long_edge, quality, remember=True)

    def capture_preview(self, max_long_edge: int = 1280, quality: int = 45) -> dict:
        """抓取预览帧（供悬浮窗轮询显示），不改变坐标基准。"""
        return self._grab(max_long_edge, quality, remember=False)

    def _grab(self, max_long_edge: int, quality: int, remember: bool) -> dict:
        self._require_input()
        img = _pag.screenshot()
        if Image is not None:
            img = img.convert("RGB")
        width, height = img.size

        if Image is not None and max(width, height) > int(max_long_edge):
            ratio = max(width, height) / float(max_long_edge)
            img = img.resize((max(1, int(width / ratio)), max(1, int(height / ratio))), Image.LANCZOS)

        img_w, img_h = img.size
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=int(quality))
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        meta = {
            "image": b64,
            "mime": "image/jpeg",
            "image_width": img_w,
            "image_height": img_h,
            "screen_width": width,
            "screen_height": height,
            # 截图像素 → 屏幕像素 的缩放比
            "scale": (width / float(img_w)) if img_w else 1.0,
            "ts": time.time(),
        }
        if remember:
            with self._lock:
                self._last_capture = meta
        return meta

    def to_screen(self, image_x: float, image_y: float) -> tuple[int, int]:
        """把「截图像素坐标」换算回真实屏幕坐标（缩放校正）。"""
        with self._lock:
            cap = dict(self._last_capture)
        if not cap.get("image_width"):
            raise RuntimeError("尚未截图，无法换算坐标。请先执行 screenshot 获取一帧画面。")
        scale = cap["screen_width"] / float(cap["image_width"])
        return int(round(float(image_x) * scale)), int(round(float(image_y) * scale))

    # ── 鼠标（含拖拽 / 长按） ──

    def move(self, x: int, y: int, duration: float = 0.2) -> None:
        self._require_input()
        _pag.moveTo(int(x), int(y), duration=float(duration))

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        self._require_input()
        btn = {"left": "left", "right": "right", "middle": "middle"}.get(str(button).lower(), "left")
        _pag.click(int(x), int(y), clicks=int(clicks), button=btn)

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5, button: str = "left") -> None:
        self._require_input()
        _pag.moveTo(int(x1), int(y1))
        time.sleep(0.05)
        _pag.dragTo(int(x2), int(y2), duration=float(duration), button=str(button))

    def long_press(self, x: int, y: int, duration: float = 1.0, button: str = "left") -> None:
        """在坐标处按住不放指定时长（长按 / 按住拖动 / 右键菜单场景）。"""
        self._require_input()
        _pag.moveTo(int(x), int(y))
        _pag.mouseDown(button=str(button))
        time.sleep(max(0.05, float(duration)))
        _pag.mouseUp(button=str(button))

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        self._require_input()
        if x is not None and y is not None:
            _pag.moveTo(int(x), int(y))
        _pag.scroll(int(amount))

    # ── 键盘 ──

    def type_text(self, text: str, interval: float = 0.02) -> None:
        """输入文本。非 ASCII（中文等）无法逐键输入，改用剪贴板粘贴。"""
        self._require_input()
        text = str(text)
        if text.isascii():
            _pag.typewrite(text, interval=float(interval))
        elif _clip is not None:
            _clip.copy(text)
            time.sleep(0.05)
            _pag.hotkey("ctrl", "v")
        else:
            _pag.write(text, interval=float(interval))

    def key(self, key_name: str) -> None:
        self._require_input()
        _pag.press(str(key_name))

    def hotkey(self, keys) -> None:
        self._require_input()
        if isinstance(keys, str):
            keys = [k for k in keys.replace("+", " ").split() if k]
        _pag.hotkey(*[str(k) for k in keys])

    # ── UI Automation 控件树 ──

    def uia_tree(self, max_depth: int = 12, max_nodes: int = 200,
                 interactive_only: bool = True, max_visited: int = 4000) -> list[dict]:
        if _uia is None:
            raise RuntimeError("uiautomation 不可用（仅支持 Windows）。请安装: pip install uiautomation")
        _ensure_uia_thread()
        with self._lock:
            self._uia_refs = {}
            self._uia_seq = 0
        root = _uia.GetRootControl()

        def collect(filter_types):
            nodes: list[dict] = []
            visited = [0]

            def walk(ctrl, depth: int):
                if depth > max_depth or len(nodes) >= max_nodes or visited[0] >= max_visited:
                    return
                try:
                    children = list(ctrl.GetChildren())
                except Exception:
                    return
                for child in children:
                    if len(nodes) >= max_nodes or visited[0] >= max_visited:
                        return
                    visited[0] += 1
                    info = self._describe_control(child, depth)
                    if info is None:
                        continue
                    if filter_types is None or info["type"] in filter_types:
                        self._register_control(child, info)
                        nodes.append(info)
                    walk(child, depth + 1)

            walk(root, 0)
            return nodes

        nodes = collect(_USEFUL_UIA_TYPES) if interactive_only else collect(None)
        # 兜底：全是自绘控件（无标准类型）时，退回完整原始树
        if interactive_only and not nodes:
            nodes = collect(None)
        return nodes

    def _describe_control(self, ctrl, depth: int) -> dict | None:
        try:
            rect = ctrl.BoundingRectangle
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return None
            return {
                "name": (ctrl.Name or "").strip()[:120],
                "type": ctrl.ControlTypeName or "",
                "automation_id": (ctrl.AutomationId or "")[:80],
                "class": (ctrl.ClassName or "")[:80],
                "enabled": bool(ctrl.IsEnabled),
                "depth": depth,
                "rect": {"left": rect.left, "top": rect.top, "width": width, "height": height},
            }
        except Exception:
            return None

    def _register_control(self, ctrl, info: dict) -> None:
        with self._lock:
            self._uia_seq += 1
            ref = f"@u{self._uia_seq}"
            self._uia_refs[ref] = ctrl
        info["ref"] = ref

    def uia_action(self, ref: str, action: str = "click", text: str | None = None) -> dict:
        _ensure_uia_thread()
        with self._lock:
            ctrl = self._uia_refs.get(ref)
        if ctrl is None:
            raise RuntimeError(f"未知或已失效的控件引用: {ref}，请重新执行 uia_tree")
        action = (action or "click").lower()
        meta = {"ref": ref, "name": (ctrl.Name or "")[:80], "type": ctrl.ControlTypeName or ""}

        if action in ("click", "invoke", "double_click"):
            attempts = []
            if action == "double_click":
                try:
                    ctrl.DoubleClick(simulateMove=False)
                    return {**meta, "strategy": "DoubleClick"}
                except Exception as e:
                    attempts.append(f"DoubleClick:{e}")
            for strategy in ("Click", "Invoke", "keyboard"):
                try:
                    if strategy == "Click":
                        ctrl.Click(simulateMove=False)
                    elif strategy == "Invoke":
                        ctrl.GetInvokePattern().Invoke()
                    else:
                        ctrl.SetFocus()
                        _pag.press("enter")
                    return {**meta, "strategy": strategy}
                except Exception as e:  # 逐级兜底
                    attempts.append(f"{strategy}:{e}")
            # 坐标兜底：在控件中心用真实鼠标操作
            try:
                rect = ctrl.BoundingRectangle
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
                if action == "double_click":
                    _pag.doubleClick(cx, cy)
                else:
                    _pag.click(cx, cy)
                return {**meta, "strategy": "coord_fallback", "x": cx, "y": cy}
            except Exception as e:
                attempts.append(f"coord:{e}")
            raise RuntimeError(f"控件操作失败: {'; '.join(attempts)}")

        if action == "focus":
            ctrl.SetFocus()
            return {**meta, "action": "focus"}

        if action in ("set_value", "type"):
            ctrl.SetFocus()
            value = "" if text is None else str(text)
            try:
                ctrl.GetValuePattern().SetValue(value)
                return {**meta, "action": "set_value", "strategy": "ValuePattern"}
            except Exception:
                # 回退：全选替换
                _pag.hotkey("ctrl", "a")
                self.type_text(value)
                return {**meta, "action": "set_value", "strategy": "keyboard"}

        if action in ("get_value", "read"):
            value = ""
            try:
                value = ctrl.GetValuePattern().Value
            except Exception:
                value = ctrl.Name or ""
            return {**meta, "action": "get_value", "value": value}

        raise RuntimeError(f"不支持的控件操作: {action}")
