# computer_use skill
# ---------------------------------------------------------------------------
# 摘要
# 混合式桌面自动化：在真实电脑上操作任意 GUI——读取控件树按元素点击、输入、拖拽、
# 长按、键盘组合键，必要时降级到「截图 + 坐标」。用于需要操作原生软件、系统窗口、
# 或浏览器之外界面的任务。
#
## 使用场景
# - 操作 Windows 原生软件 / 系统设置 / 文件管理器
# - 任何 GUI 上的点击、输入、拖拽、长按、快捷键
# - 浏览器之外的跨软件流程编排
#
# 包含 1 种子操作:
#   computer_use - 执行桌面操作序列
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── computer_use ──
# 执行桌面操作序列。一步失败即停止剩余步骤；被用户暂停/接管时会阻塞等待；被停止时中止。
#
# 参数:
#   actions (array, 必填) 操作序列，每项为对象，含 action 及参数：
#     {"action": "<动作名>", ...对应参数}
#   task (string, 可选) 任务目标（用于日志）
#
# ── 结构化路径（首选，无坐标误差）──
#   uia_tree           读取 UI Automation 控件树。参数: max_depth(默认12), max_nodes(默认200),
#                      interactive_only(默认 true)
#                      默认只返回可交互控件 + 结构性锚点（按控件类型过滤），命中率更高；
#                      若目标缺失可传 interactive_only=false 获取完整原始树。
#                      返回 nodes[].ref（@uN 引用）与 name/type/automation_id/rect
#   click_element      按元素点击。参数: ref（必须直接使用 uia_tree 返回的 @uN，不要自行拼接）
#   invoke_element     按元素触发默认动作。参数: ref
#   focus_element      聚焦元素。参数: ref
#   set_element_value  设置元素值（输入框等）。参数: ref, text
#
# ── 像素路径（兜底，控件树覆盖不到时）──
#   screenshot         截取主屏，返回「截图像素」尺寸 + 对当前画面的文字识别（description）。
#                      你看到的是识别文本，不是图片本身。参数: quality(默认50), prompt(可选)
#   describe_screen    同 screenshot（可用 prompt 指定观察重点），返回文字描述
#   click              坐标点击。参数: x, y, button(默认left), clicks(默认1)
#   right_click        坐标右键。参数: x, y
#   double_click       坐标双击。参数: x, y
#   move               移动鼠标。参数: x, y, duration(默认0.2)
#   drag               拖拽。参数: x1, y1, x2, y2, duration(默认0.5), button
#   long_press         长按。参数: x, y, duration(默认1.0), button
#
# ── 键盘 ──
#   type_text          输入文本（非 ASCII 自动走剪贴板粘贴）。参数: text, interval
#   key                按单个键。参数: key（如 enter/tab/esc/f1）
#   hotkey             组合键。参数: keys（如 "ctrl+s"、"ctrl+shift+esc"）
#
# ── 其他 ──
#   wait               等待。参数: duration(毫秒, 最大60000)
#
# 坐标说明:
#   所有坐标 (x, y) 均按 screenshot 返回图片的像素坐标给出，系统自动换算回真实屏幕坐标，
#   无需自己处理分辨率缩放。
#
# ═══ 重要规则 ═══
# 1. 优先结构化：先 uia_tree，能定位到控件就用 click_element/set_element_value；
#    控件树拿不到目标（自绘控件、游戏、跨进程浮层）才用 screenshot + 坐标。
# 2. 【严禁幻觉】你只能依据本工具真实返回的 description / nodes / results 下结论，看不到图片本身。
#    任何「已完成/已打开/已成功」都必须有对应的 description 或 uia_tree 佐证，并在答复中说明依据。
#    禁止把未完成说成已完成。
# 3. 【禁止编造数据】磁盘容量、文件名、金额、数量等具体数值必须来自 uia_tree / screenshot 的实际返回，
#    不得凭常识或印象估算；拿不到就如实说明拿不到。
# 4. 【达成即止】用户要的是「打开/查看某物」，不是穷尽界面。目标一旦达成并确认（例如此电脑窗口已打开），
#    立即汇报所见内容并结束，不得为收集额外信息继续在已达成目标的窗口里点击探索。
# 5. 每步关键操作后用 screenshot 或 uia_tree 确认结果，再决定下一步。
# 6. 打开桌面图标/文件用双击：double_click_element，或 click_element 加 clicks:2 / button:"double"。
# 7. 若工具返回 user_correction，说明用户中途纠正，必须立即按纠正调整计划。
# 8. 涉及删除/支付/发送等高风险操作前，先明确目标，避免误操作。
