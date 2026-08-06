# network_bridge skill
# 操控用户真实浏览器，完成需要页面交互的任务——填表、搜索、发帖、登录、点击按钮、读取页面内容等。
## 使用场景
# - 需要在网页上填写表单、搜索、点击按钮、提交内容
# - 需要从网页读取信息（文本、标题、HTML）
# - 需要导航到特定 URL、管理浏览器标签页
# - 需要截图查看页面状态
# - 需要查询浏览器收藏夹找到目标网站
# 强制规则：
# 1. 当用户要求去某个网站/查某种信息时，必须优先调用 get_bookmarks 搜索浏览器收藏夹；
#    若收藏夹中有匹配站点（如风鸟企业查询、kimi code），则必须优先 navigate 到收藏夹 URL。
# 2. 只有收藏夹中找不到合适站点时，才允许使用 navigate 打开通用搜索引擎或默认网站。
# 3. 不要根据网站名称的相似度猜测 URL，优先相信收藏夹里的真实 URL。
# 4. 操作模式：使用 actions 数组逐步骤操作浏览器，3-5 步一批为宜。每批操作后自动 snapshot。
# 包含工具: network_bridge
# ---------------------------------------------------------------------------

# ═══ 核心设计 ═══

network_bridge 必须使用 actions 手动模式：

## actions 使用方式

通过 `actions` 数组逐步骤操作浏览器：

```json
{
  "actions": [
    {"action": "navigate", "url": "https://www.baidu.com", "newTab": true},
    {"action": "snapshot"},
    {"action": "fill", "ref": "@e1", "value": "Python教程"},
    {"action": "click", "ref": "@e2"},
    {"action": "wait", "duration": 2000},
    {"action": "snapshot"}
  ]
}
```

# ═══ 操作参数 ═══

── navigate ──
打开指定 URL。可选 newTab (true/false) 控制是否在新标签页打开。
参数: url (必填), newTab (可选)

── snapshot ──
获取当前页面 DOM 结构化快照，返回页面文本、可交互元素树、@eN 引用。
返回的核心字段: url, title, text (页面文本摘要), tree, elements (含 ref/selector/rect/text 等)
参数: 无

snapshot.elements 中每个元素还包含以下状态字段，供你判断元素是否可交互：
- clickable (bool): 元素是否真正可点击（综合 tag/role/cursor/pointer-events/disabled 判断）
- covered (bool): 元素中心是否被其他元素遮挡
- coveredBy (object | undefined): 遮挡元素的 tag/text/selector（仅 covered=true 时存在）
- inViewport (bool): 元素是否在当前可视区域内
- shadowHost (bool): 元素本身是否是 Shadow Host（内部可能还有可交互元素）
- insideShadowDom (bool): 元素是否位于 Shadow DOM 内部
- insideIframe (bool): 元素是否位于 iframe 内部
- disabled (bool): 元素是否被禁用

── ax_snapshot ──
获取 CDP 无障碍树。当 DOM snapshot 看不到内容时使用（邮件正文、富文本、Shadow DOM 等）。
返回 @axN 引用。
参数: limit (可选, 默认 120)

── click ──
点击元素。运行时内部自动尝试多策略兜底。
参数: ref (推荐, @eN 引用) 或 selector (CSS 选择器)

── force_click ──
强制点击，多策略兜底（el.click → dispatch events → main world injection）。
参数: ref 或 selector

── fill ──
填写输入框/文本域/下拉框。
参数: ref 或 selector, value (输入内容)

── cdp_type ──
通过 CDP 发送真实文本输入，适用于 React 等前端框架拦截的场景。
参数: ref/selector (可选, 不传则输入到当前焦点), text (输入内容)

── cdp_click ──
通过 CDP 发送真实鼠标点击事件。
参数: ref (来自 ax_snapshot 的 @axN), 或 selector, 或 x/y

── cdp_keypress ──
通过 CDP 发送真实按键。常用键: Enter, Tab, Escape, Backspace, Delete, ArrowUp/Down/Left/Right
参数: key (必填), ref/selector (可选)

── targeted_click ──
按语义描述寻找最匹配的点击目标并点击。
参数: query (按钮文字或语义描述), limit (可选, 候选数, 默认 20)

── click_xy ──
按可视区域坐标点击。
参数: x, y (CSS 像素)

── scroll_to ──
滚动页面。支持 ref/selector 或 x/y 坐标。
参数: ref 或 selector (滚动到元素), 或 x/y (滚动到坐标)

── hover ──
悬停元素，触发 mouseenter/mouseover。
参数: ref 或 selector

── keypress ──
在元素上模拟按键。支持 ctrl/alt/shift/meta 修饰键。
参数: key (必填), ref/selector (可选), ctrl/alt/shift/meta (可选)

── select ──
选择下拉框选项。三选一：value / index / text。
参数: ref 或 selector, value 或 index 或 text

── evaluate ──
在 content script 隔离环境执行 JavaScript。
参数: script (代码字符串, 支持 await)

── inject_evaluate ──
在页面主世界执行 JavaScript。
参数: script (代码字符串, 支持 await)

── screenshot ──
截取当前标签页可见区域，返回 base64 图片。
参数:
  - format (可选, "png" 或 "jpeg", 默认 "jpeg")
  - quality (可选, 20-90, 默认 65)
  - analyze (可选, bool, 默认 false): 截图后是否自动调用 vision 模型分析图片内容
  - prompt (可选, string): 自定义 vision 分析提示词（仅 analyze=true 时有效）
  - source="visible"（内部标记）

── cdp_screenshot ──
通过 CDP 截取完整页面渲染结果（包括视口外内容）。
参数: 同 screenshot，但 source="full"

── analyze_screenshot ──
截图并调用主程序配置的 vision key 进行视觉分析，返回图片内容文字描述。
这是最推荐的“看不懂页面/弹窗/下拉菜单时”的查看方式。
参数:
  - source (可选, "visible" 或 "full", 默认 "visible"): 截取可见区域还是完整页面
  - format / quality: 同 screenshot
  - prompt (可选, string): 自定义分析提示词
返回字段: screenshot (base64), mimeType, analysis (vision 分析文字)

注意：analyze_screenshot 和 screenshot analyze=true 都会消耗 vision model 的 token；
选择哪个 LLM 不影响视觉分析，只要主程序 Settings 中配置了 visionApiKey/visionModel/visionBaseUrl。

── get_page_text / get_page_html / get_page_title ──
读取页面文本/HTML/标题。无需参数。

── query_selector ──
CSS 选择器查询单个元素。返回元素信息含 @eN 引用。
参数: selector

── wait ──
等待指定毫秒数。
参数: duration (毫秒, 最大 60000)

── highlight / clear_highlight ──
高亮/清除高亮元素。
参数: ref 或 selector, color (可选, 默认黄色)

── list_tabs ──
列出所有打开的标签页。无需参数。

── new_tab ──
新建标签页。
参数: url (可选), active (可选, 默认 true)

── activate_tab ──
切换到指定标签页。
参数: tabId

── close_tab ──
关闭指定标签页。
参数: tabId

── get_bookmarks ──
搜索浏览器收藏夹。
参数: keyword (搜索关键词), limit (可选, 默认 20)

重要：当用户表达任务意图时（如查企业、查天气、查地图、查快递），应优先调用 get_bookmarks 搜索收藏夹中是否有更合适的站点，而不是直接打开通用搜索引擎或默认网站。

── site_memory_get ──
读取当前域名的站点记忆（历史操作经验）。
参数: 无

── site_memory_put ──
保存站点记忆。
参数: entries (记忆条目列表)

── inspect_all_elements ──
扫描页面所有可交互元素，在页面上显示黄色编号选框。
参数: maxElements (可选, 默认 200)

── clear_inspect ──
清除元素选框。无需参数。

── start_recording / stop_recording ──
录制/停止录制用户操作序列。无需参数。

# ═══ 重要规则 ═══

1. 优先使用 snapshot 返回的 @eN 引用，不要手写 CSS selector。
2. snapshot 返回的 tree 字段提供快速概览，elements 数组提供详细信息。
⚠️ **黄金法则**：每次 click / force_click / targeted_click / navigate / new_tab 之后，页面很可能已变化。如果返回结果带 navigationDetected: true 或 hint，必须立刻 snapshot（或 read_page）获取新 @eN 后再继续操作。沿用旧 @eN 会触发 element_moved / element_detached 错误。
⚠️ **ref 漂移检测**：如果 click / force_click / fill 报元素位置已漂移或元素已脱离文档，说明页面在 snapshot 后发生了重排或局部刷新，必须重新 snapshot 再操作。
⚠️ **多标签页**：navigate 和 new_tab 会锁定当前操作的目标标签页，后续 click / fill / snapshot 默认都在该标签页执行。如需切换，先 list_tabs 再 switch_tab。

3. 页面跳转、刷新后 @eN 引用可能失效，需要重新 snapshot。
4. 如果 click 后无反应，可尝试 force_click；如果仍无效，尝试 targeted_click 按语义定位。
5. 填写富文本编辑器/contenteditable 时，fill 会自动检测并使用 contenteditable 策略。
6. 当 DOM snapshot 看不到内容时，使用 ax_snapshot + cdp_click/cdp_type 组合。
7. **收藏夹优先**：用户表达任何带有“去某网站查/做某事”意图时，先调用 get_bookmarks 搜索收藏夹。如果收藏夹中有匹配的站点（如风鸟企业查询、百度地图、快递 100 等），必须优先 navigate 到收藏夹中的 URL，而不是默认打开通用搜索引擎或自己猜测的站点。只有在收藏夹找不到合适站点时，才使用 search 或默认网站。

# ═══ 点击失败 / 元素可见但点不上时的处理策略 ═══

执行 click 或 force_click 失败后，请根据 snapshot 中元素的状态字段和错误信息，按以下优先级排查：

1. **被遮挡 (covered=true)**：元素中心被其他元素盖住。
   - 先查看 coveredBy 中的遮挡元素，判断是否是弹窗、抽屉、遮罩层。
   - 如果是误触的遮罩，尝试关闭它（如按 Escape、点击遮罩外区域）。
   - 否则使用 cdp_click 直接命中元素几何中心，绕过上层拦截。

2. **不在可视区域 (inViewport=false)**：元素在页面滚动范围外。
   - 先用 scroll_to 把元素滚到视口中央，再点击。

3. **位于 Shadow DOM (insideShadowDom=true)**：普通 DOM 路径无法直接操作。
   - 优先使用 cdp_click（传入 ref 或 selector）。
   - 如果 ref 失效，使用 evaluate / inject_evaluate 在页面内执行自定义 JS。

4. **位于 iframe (insideIframe=true)**：
   - 同域 iframe：snapshot 已能扫描到内部元素，直接用 ref 操作。
   - 跨域 iframe：普通 content script 无法访问，必须使用 cdp_click / cdp_type / cdp_keypress。

5. **clickable=false 但视觉上是按钮**：说明元素没有标准交互属性（如自定义 div 按钮）。
   - 使用 targeted_click 按文字/语义定位并点击。
   - 或使用 click_xy 按坐标点击。

6. **disabled=true**：元素被禁用，点击无效。检查前置条件是否满足（如表单未填写、未勾选协议）。

7. **多次失败仍无效**：使用 `analyze_screenshot` 截图并调用 vision 模型分析当前页面实际状态，根据分析结果决定下一步。

# ═══ 弹窗 / 下拉菜单 / 浮动层处理策略 ═══

弹出界面（modal、dialog、dropdown、toast、popover 等）通常是动态生成并很快消失，静态 snapshot 可能抓不到。请按以下策略处理：

1. **先触发，再 snapshot**：
   - 点击按钮弹出菜单/弹窗后，立即 `wait 500-1500ms`，然后重新 `snapshot`。
   - 下拉菜单通常是 hover 触发，先 `hover` 目标，再 `snapshot`。

2. **弹窗出现后优先关闭遮罩层**：
   - 如果 snapshot 显示有一个全屏或半屏遮罩层（mask/overlay/backdrop）盖住了目标，先尝试关闭它：
     - 按 `Escape` 键（keypress/cdp_keypress）。
     - 点击遮罩层边缘或关闭按钮（通常是右上角 ×）。
   - 关闭后再操作目标元素。

3. **截图并视觉分析确认**：
   - 弹窗或下拉菜单出现后，使用 `analyze_screenshot` 直接截图并让 vision 模型描述内容、位置、遮挡关系。
   - 如果弹窗很快自动消失，使用 `analyze_screenshot source="full"` 或 `cdp_screenshot analyze=true`。
   - 普通 `screenshot` 只返回图片，只有配置了 vision key 且调用 analyze_screenshot / screenshot analyze=true 才能“看懂”图片。

4. **对浮动层内元素使用 cdp_click / cdp_type**：
   - 浮动层中的元素可能通过 React Portal / Vue Teleport 渲染到 body 下，普通 ref 可能不稳定。
   - 如果 click/fill 失败，改用 `cdp_click` / `cdp_type` 命中几何中心。

5. **处理自动消失的提示**：
   - toast、notification 等通常 2-5 秒后消失，无法交互。如果需要获取其文本，在出现后立刻 `get_page_text` 或 `screenshot`。

6. **明确告诉用户限制**：
   - 如果弹窗是跨域 iframe、浏览器原生控件（如文件选择器、日期选择器）或需要真实鼠标悬停才能维持的下拉菜单，当前能力有限，应向用户说明。

# ═══ 标签页切换策略（点击打开新页面时） ═══

部分网站点击按钮/链接会新开标签页。你需要主动管理标签页焦点：

1. **点击后检查是否有新标签页打开**：
   - 执行 click 后 wait 1-2 秒，然后调用 `list_tabs` 列出所有标签页。
   - 对比 click 前后的标签列表，找到新打开的标签页（通常是最后一个或 url 与当前不同的）。

2. **切换到新标签页**：
   - 使用 `activate_tab` 切换到新标签页的 tabId。
   - 切换后 wait 1-2 秒等待页面加载，再 `snapshot` 继续操作。

3. **典型流程**（银行/政务网站点击"查询"新开标签页）：
   ```json
   [
     {"action": "click", "ref": "@e5"},
     {"action": "wait", "duration": 2000},
     {"action": "list_tabs"},
     {"action": "activate_tab", "tabId": 123},
     {"action": "wait", "duration": 1500},
     {"action": "snapshot"}
   ]
   ```

4. **操作完成后建议回到原标签页或关闭新标签页**，
   避免标签页堆积。如果新页面操作完后还要继续在原页面操作，
   使用 `activate_tab` 切回去。
