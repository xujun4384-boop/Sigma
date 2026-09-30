# opendesign / HyperFrames 版式风格处方

> 本文件是一份**跨场景的风格叠加层**（style overlay），不是场景 profile。
> `guideline/design/profiles/*.md` 是**场景驱动**（由业务/受众场景选中）；本处方是**风格/tone 驱动**（由视觉倾向选中）。两者**正交**：在已选场景 profile 之上，再按本处方的 tone 叠出版式与视觉语调，产出"现代简洁、留白充足、配色克制"的 PPT。

> 出处：本处方的 tone 语义与默认风格，对齐 opendesign（HyperFrames 视频合成）设计语言（`skills/opendesign/`）。**此处只复用其版式与视觉，产出的是静态、可编辑的 .pptd/.page，不含视频、不带动效、不配音。**

---

## 1. 何时引用本处方

当用户在该次演示的视觉需求里**点明一种可识别的视觉风格来源**（如某设计体系、参考作品、某版式倾向），且该来源的气质与"现代简洁、克制、留白"相符时，可在视觉设计阶段叠加本处方。判断基于"风格来源是否点名 + 可选 tone"，**不做关键词匹配**。

引用优先级：用户显式要求 > 本风格处方 > 通用 style_prompt。

---

## 2. tone → 版式特征映射表

tone 是通用驱动轴（academic / product / editorial / technical），用于定下版式与视觉语调。未指定时默认 `product`（对齐 opendesign 默认）。

| tone | 版式主特征 | 配色倾向 | 中文字体推荐（`format/fonts.md`） |
|---|---|---|---|
| academic | 克制内敛、信息密度高、少装饰；章标题配细 rule 线 | 低饱和、近单色 | siyuanSongti / Noto Sans SC |
| product | 现代简洁、突出卖点、品牌质感；hero 标题+副标题+横向展开线、metric 指标芯片 | 克制的主色 + 留白 | MiSans / alimamashuheiti |
| editorial | 强字号层级、留白优雅、宽边距；衬线标题 + 规则线分隔 | 中性底 + 单强调色 | siyuanSongti / xiawuxinzhisong |
| technical | 数据/图表清晰、冷静理性；图表 + metric 芯片 + 细网格线 | 低饱和 + 点状强调 | MiSans / QuattrocentoSans |

共同默认（opendesign 风格基调）：
- 配色克制，主色 1~2 个、强调色保守；**避免 AI 常见廉价色**（亮紫、白紫渐变、俗蓝）。
- 留白充足，字体/元素的层级对比>依赖边框卡片。
- 标题与正文字号差要拉开（title 42~48，body 18~22）。

---

## 3. 版式母题 → PPTD 配方

opendesign 动态版面在 PPT 里落地为**静态母题**，逐条映射到 .pptd/.page 元素（text / shape / image / background）。

### 母题 1：Hero（封面 / 章节首屏）
- `background`：`gradient`（中性底→主色糅合）或整幅 `image`。
- `text`：主标题，大字号 44~52，主色或近黑。
- `text`：副标题，次要色。
- `shape`(line)：标题下方的横向展开细规则线（elementType=shape, shapeName=line, 主色），呼应 hero-rule。

### 母题 2：Metric 指标芯片（数据 / 卖点）
- `shape`(rect 或 roundRect)：芯片容器，浅底。
- `text`：数字 / KPI，大字号（fontSize 40+），主色。
- `text`：指标说明，小字号次要色。
- 可加细 `shape`(line) 分隔排布。

### 母题 3：卡片分组（多要点）
- `shape`(rect)：卡片容器，留足圆角/边距，宁可少边框多留白。
- 卡片内 `text` + 可选 `shape`(icon 化小方条)。
- 多卡片网格对齐，左右/上下留白均等。

### 母题 4：章节转场条带 bar + rule（章节页）
- PPT 无 GSAP，"扫过"转场译成**静态条带贯穿版式**：
- `shape`(rect)：章节页顶部一条主色横条（bar）。
- `shape`(line)：其下一条细色线（rule）贯穿。
- 章节号／章节名大字号置于条带区，呼应"章节转场"的节奏感。

### 母题 5：封面全屏背景 + 渐变蒙版
- `background(image)` 或 `background(gradient)` 铺满；
- 叠加半透明 `shape`(rect) 蒙版保证文字可读；
- 标题字色用蒙版之上可读的浅色（如白 / 近白）。

---

## 4. 与场景 profiles 的关系

- **不新增 profiles 文件**。现有 `profiles/*.md`（business_insight / academic / promotion / education / work_report / strategic / general）按**场景**选中，保留不变。
- 本处方作为**风格叠加层**挂在 `design/` 下，叠加于任一已选 profile 之上：先按场景 profile 定内容密度与版式基调，再按本处方 tone 定视觉语调与母题。

---

## 5. 禁忌（双向）

### 从 opendesign 视频语言中**必须剔除**的（PPT 不需要）
- 固定 1920×1080 画布、`data-*`/`clip`/`track-index`/`data-start`/`data-duration` 字段 —— 全删。
- GSAP / 动效时间轴 / 转场动画 —— PPT 无动效，改成静态条带/静态 line 布局。
- 底部 8~12% **字幕安全区** —— PPT 无字幕；不得误译成整页底部大留白。
- 中文字体用 `system-ui, sans-serif` 的 fallback —— PPT 中**必须显式指定中文字体**（见上表，遵循 `format/fonts.md`）。

### PPTD 生成中**不得触发**的
- 不得写 video 专属字段（layout/type/title/subtitle/author/decoration 等旧字段）。
- 卡片容器不得过度依赖边框而挤掉留白；用字号/留白做层级。
- 标题与正文字号差不拉开、body 小于 18px —— 违反可读性底线。
- 章节页只剩"章节号+名称"的裸版式（无条带/背景/留白设计）—— 过于单薄。