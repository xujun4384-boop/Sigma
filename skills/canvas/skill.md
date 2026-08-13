# canvas skill
# ---------------------------------------------------------------------------
# 摘要
# 通过增量补丁创建和编辑 Sigma 的 Excalidraw 画布。
# 默认只追加新元素，不覆盖用户已经手动调整的内容。
#
## 使用场景
# - 根据用户描述绘制流程图、架构图、思维导图或关系图
# - 在当前画布中追加节点、文字和连线
# - 用户明确要求重建整张画布时替换现有元素
# - 将复杂任务的结构化结果实时呈现在画布中
#
# 包含 1 种工具:
#   canvas_update - 以增量补丁更新 Excalidraw 画布
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── canvas_update ──
# 创建或更新 Canvas 画布。默认 add 只追加元素，不覆盖用户已有编辑。
#
# 参数:
#   elements (array, 必填) Excalidraw 元素对象数组。
#     rectangle: {type, x, y, width, height, ...视觉属性}
#     ellipse: {type, x, y, width, height, ...视觉属性}
#     diamond: {type, x, y, width, height, ...视觉属性}
#     text: {type, x, y, text, ...视觉属性} — 仅用于无容器的独立标注
#     arrow: {type, x, y, width, height, points, ...视觉属性}
#     line: {type, x, y, width, height, points, ...视觉属性}
#   operation (string, 可选) add 或 replace，默认 add。
#     add: 增量追加元素，保留现有画布内容。
#     replace: 明确重建整张画布时使用。
#   canvas_name (string, 可选) 目标画布名称，始终使用 default（默认画布）。
#     除非用户明确要求创建新画布，否则不要填写任何其他名字。
#
# 输出:
#   content: 更新结果摘要
#   事件: canvas_patch，由前端实时应用到目标画布

# ═══ 元素 id 规则（必须遵守）═══
#
# 每个元素必须有唯一 id，用于去重和绑定引用。
# id 命名规范: "{类型缩写}-{语义}-{序号}"
#   示例: rect-start-1, txt-title-1, arrow-flow-1, ellipse-end-1
#
# ⚠️ 流式生成时，同一批 elements 中 id 绝不能重复。
# ⚠️ 如果后续批次需要修正之前的元素，必须使用相同 id 发送完整元素。
#    前端会自动用新元素替换同 id 的旧元素。

# ═══ 文本绑定模式（必须遵守）═══
#
# ⚠️ 这是最重要的规则。带文字的形状必须使用容器-文本绑定。
#
# 每个带文字的形状 = 2 个元素，一一配对：
#
# 第 1 个元素（容器）:
#   {
#     "type": "rectangle",
#     "id": "rect-process-1",
#     "x": 100, "y": 100, "width": 200, "height": 80,
#     "strokeColor": "#1971c2",
#     "backgroundColor": "#e7f5ff",
#     "boundElements": [{"type": "text", "id": "txt-process-1"}]
#   }
#
# 第 2 个元素（文本，绑定到容器）:
#   {
#     "type": "text",
#     "id": "txt-process-1",
#     "x": 110, "y": 120,
#     "text": "节点内容",
#     "fontSize": 16,
#     "strokeColor": "#1971c2",
#     "containerId": "rect-process-1",
#     "textAlign": "center",
#     "verticalAlign": "middle"
#   }
#
# 绑定规则（必须同时满足）:
#   ✅ 容器必须有唯一 "id" 字段
#   ✅ 容器必须有 "boundElements": [{"type":"text","id":"txt-N"}]
#   ✅ 文本必须有 "containerId": "rect-N"（与容器 id 对应）
#   ✅ 文本的 id 必须与容器 boundElements 中引用的 id 一致
#   ✅ 文本的 x/y 只需大致在容器范围内，Excalidraw 会自动居中
#   ❌ 不要只写 containerId 而容器没有 boundElements
#   ❌ 不要只写 boundElements 而文本没有 containerId
#   ❌ 不要 rectangle + text 两个独立元素但没有绑定关系
#
# 独立文本（无容器，仅用于标签、注释）:
#   {
#     "type": "text",
#     "id": "txt-label-1",
#     "x": 100, "y": 200,
#     "text": "独立标签",
#     "fontSize": 14,
#     "strokeColor": "#495057"
#   }
#   注意：独立文本不会自动居中，需要手动计算位置。

# ═══ 尺寸估算规则（防止文字溢出）═══
#
# 文本尺寸估算:
#   每行高度 = fontSize × 1.25
#   每字符宽度 ≈ fontSize × 0.6（中文字符 ≈ fontSize × 1.0）
#
# 容器尺寸建议:
#   单行文本容器: width = 文本宽度 + 40px padding, height = fontSize + 40px
#   多行文本容器: height = 行数 × fontSize × 1.25 + 40px
#
# 常用尺寸速查:
#   fontSize 16: 单行文本约 100-160px 宽 → 容器 180-220px 宽, 60px 高
#   fontSize 20: 单行文本约 120-200px 宽 → 容器 220-260px 宽, 70px 高
#   fontSize 14: 注释文本约 80-120px 宽 → 容器 140-180px 宽, 50px 高

# ═══ 布局模式模板 ═══
#
# ── 模板: 垂直流程图（3 节点）──
#   节点1: x=200, y=80,  w=180, h=60
#   节点2: x=200, y=200, w=180, h=60
#   节点3: x=200, y=320, w=180, h=60
#   箭头: 从上一节点 bottom 到下一节点 top, 长度 60px
#   垂直间距: 80px（节点高60 + 间距20）
#
# ── 模板: 水平流程图（3 节点）──
#   节点1: x=80,  y=150, w=160, h=70
#   节点2: x=300, y=150, w=160, h=70
#   节点3: x=520, y=150, w=160, h=70
#   箭头: 从上一节点 right 到下一节点 left, 长度 60px
#   水平间距: 220px（节点宽160 + 间距60）
#
# ── 模板: 三层架构图 ──
#   层1（表示层）: x=100, y=80,  w=600, h=100, 3个子节点水平排列
#   层2（业务层）: x=100, y=220, w=600, h=100, 3个子节点水平排列
#   层3（数据层）: x=100, y=360, w=600, h=100, 3个子节点水平排列
#   层间距: 140px（层高100 + 间距40）
#   层内节点: 宽160, 间距40, 起始x=120
#
# ── 模板: 思维导图（中心辐射）──
#   中心节点: x=350, y=250, w=200, h=80, fontSize=20
#   分支节点: 距中心 200px, 8方向均匀分布
#     上:    x=370, y=100, w=160, h=60
#     右上:  x=580, y=150, w=160, h=60
#     右:    x=620, y=270, w=160, h=60
#     右下:  x=580, y=390, w=160, h=60
#     下:    x=370, y=450, w=160, h=60
#     左下:  x=160, y=390, w=160, h=60
#     左:    x=120, y=270, w=160, h=60
#     左上:  x=160, y=150, w=160, h=60
#   连线: 从中心到各分支, 无箭头

# ═══ 颜色语义化 ═══
#
# 语义色板（优先使用，保持视觉一致性）:
#   "primary"   → stroke "#1971c2", bg "#e7f5ff"  —— 主要流程、核心节点
#   "success"   → stroke "#2f9e44", bg "#ebfbee"  —— 成功状态、完成节点
#   "warning"   → stroke "#e8590c", bg "#fff4e6"  —— 警告、需要注意
#   "error"     → stroke "#e03131", bg "#fff5f5"  —— 错误、失败、终止
#   "info"      → stroke "#9c36b5", bg "#f8f0fc"  —— 信息、说明、备注
#   "neutral"   → stroke "#495057", bg "#f1f3f5"  —— 中性、次要、禁用
#
# 对比度安全规则:
#   浅背景（#e7f5ff, #ebfbee 等）→ 深文字（#1971c2, #2f9e44, #1e1e1e）
#   深背景（#1971c2, #2f9e44 等）→ 白文字 #ffffff
#   不确定时，宁可文字颜色深一点，不要浅一点

# ═══ 元素视觉属性 ═══
#
# 通用属性（rectangle/ellipse/diamond/arrow/line）:
#   strokeColor: 描边颜色，使用语义色板或自定义 hex
#   backgroundColor: 填充色 "transparent" 或语义色板 bg
#   fillStyle: "hachure" | "cross-hatch" | "solid"
#   strokeWidth: 1 | 2 | 4
#   strokeStyle: "solid" | "dashed" | "dotted"
#   roughness: 0（光滑）| 1（适中）| 2（粗糙），正式图表建议 0
#   opacity: 0-100
#   roundness: {type: 3} 或 null（直角）
#
# 文本专属属性:
#   fontSize: 正文 16-20，标题 24-32，注释 12-14
#   fontFamily: 1（手写）| 2（正常）| 3（代码），正式图表建议 2
#   textAlign: "left" | "center" | "right"
#   verticalAlign: "top" | "middle" | "bottom"

# ═══ 自检清单（输出 elements 前必须逐项检查）═══
#
# 1. id 唯一性: 同一批 elements 中，所有 id 是否唯一？
# 2. 绑定完整性: 每个 text 元素是否有 containerId？每个 containerId 是否有对应容器？
# 3. 绑定双向性: 每个容器的 boundElements 是否引用了正确的 text id？
# 4. 尺寸匹配: 容器尺寸是否能容纳文本？（参考尺寸估算规则）
# 5. 坐标合理: 元素是否超出画布常见范围（x: 0-1200, y: 0-800）？
# 6. 颜色对比: 文字颜色与背景色是否有足够对比度？
#
# 如果任何一条不满足，修正后再输出。

# ═══ Troubleshooting ═══
#
# | 问题现象 | 可能原因 | 解决方案 |
# |---------|---------|---------|
# | 文字在容器外面 | containerId 与容器 id 不匹配 | 检查绑定双向性，确保 id 一致 |
# | 同一元素出现多次 | 流式批次中重复发送相同元素 | 确保同一批中 id 唯一；修正时使用相同 id |
# | 文字溢出容器 | 容器尺寸太小 | 按尺寸估算规则增加容器宽高 |
# | 元素挤在一起 | 间距不足 | 参考布局模板的间距建议 |
# | 箭头不显示 | points 数组为空或格式错误 | 确保 points 是 [[x1,y1],[x2,y2]] 格式 |
# | 颜色太浅看不清 | 对比度不足 | 遵循对比度安全规则，深背景用白字 |
# | 画布出现旧元素 | operation 误用 add 而非 replace | 明确重建画布时使用 replace |
# | 绑定关系被破坏 | 流式批次中容器和文本分属不同批次 | 确保同一绑定对在同一批次中发送 |

# ═══ 禁忌（违反以下任何一条都会导致视觉效果严重问题）═══
#   ❌ 禁止 rectangle + 独立 text 元素叠加（文字必然偏移）
#   ❌ 禁止同一批 elements 中出现重复 id
#   ❌ 禁止文字颜色与背景色对比度不足
#   ❌ 禁止所有元素都用默认黑色 + transparent
#   ❌ 禁止 roughness=2 用于正式图表
#   ❌ 禁止元素挤在一起
#   ❌ 禁止把容器和绑定文本拆到不同流式批次
