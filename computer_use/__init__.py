"""Computer Use —— 混合式桌面自动化。

设计要点：
- 混合控制：优先 UI Automation 控件树（元素级、免坐标）；控件树覆盖不到时，
  降级到「截图 + 坐标」。
- 坐标一致性：截图与鼠标键盘统一走同一套屏幕坐标系，并对下采样做换算，
  规避「截图被压缩导致点击偏移」这一最常见失败。
- 统一保留 Computer Use 独有能力：拖拽 / 长按 / 键盘（输入 / 按键 / 组合键）。
- 可选依赖缺失时优雅降级，通过 capabilities() 暴露真实能力，不做硬编码假设。
"""
from computer_use.engine import DesktopController
from computer_use.manager import ComputerUseManager, computer_use_manager
from computer_use.tool import ComputerUseTool

__all__ = [
    "DesktopController",
    "ComputerUseManager",
    "computer_use_manager",
    "ComputerUseTool",
]
