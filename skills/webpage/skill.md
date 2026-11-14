# webpage - 真实网页取景讲解（内部引擎）

> 由 `director` 导演组调度，不直接暴露给用户。

## 用途

讲一个知识点时，画面不重绘，而是在**模拟浏览器窗口里滚动真实网页**，同时在网页原文上做高亮，
旁边浮现**批注卡片**（原文摘录 + 一句解释）：

```
浏览器窗口内滚动定位 → 高亮关键原文 → 批注逐段浮现（序号 → 原文 → 解释）→ 切下一条
```

适合：需要真实依据的科普（定义、数据、原文、官方说明）。
不适合：抽象概念、纯情绪表达、没有任何公开来源的内容。

## 两阶段

### 1. 设计阶段（`scripts/prepare.py`）

```
web.query / web.url
  → web_search 找候选（无 url 时）
  → 轻量读取候选页，LLM 选定来源
  → 完整抓取：文本块 + 矩形
  → 聚类：把高亮收敛到同一屏幕范围内的区块
  → LLM 选段 → LLM 摘句（原文逐字）
  → Range 精确定位（逐行矩形）
  → 冻结截图：覆盖标注区域的"页面带"（1:1，不做缩略）
  → 写回蓝图：source / marks / 坐标 / capture_dir
```

设计阶段结束后，蓝图里能看到**具体来源、要高亮的原文、坐标**。执行阶段不再抓页。

### 2. 执行阶段（`WebpageVideoTool`）

```
读取冻结缓存 → 页面带写入 assets
  → 整理场景（page / viewport / notes / pacing / min_read）
  → LLM 按契约写「浏览器 + 标注 + 批注」的 HTML+GSAP
  → 结构/运行时/确定性闸门 → 标注几何实测 → 视觉复审
  → npx hyperframes render
```

## 数据约定

面板字段：

```json
{"engine": "webpage",
 "web": {"url": "可选", "query": "无 url 时必填", "focus": "这一段讲什么", "max_marks": 3},
 "narration": "本段旁白",
 "visual": "画面需求"}
```

设计阶段把 `web` 补全为：

```json
{"source": {"url": "...", "title": "...", "domain": "...", "reason": "..."},
 "capture_id": "...",
 "capture_dir": "video_work/<project>/web/<id>",
 "page": {"width": 1920, "height": 44061, "hash": "..."},
 "overview": {"file": "overview.png", "width": 1920, "height": 15000, "y": 2116},
 "marks": [{"id": "m1", "quote": "原文逐字", "reason": "为什么值得看",
            "rect": [x, y, w, h], "lines": [[x, y, w, h], ...]}]}
```

`rect` / `lines` 是**页面坐标**（页面坐标减 `overview.y`），单位 CSS 像素。
`overview.png` 是覆盖标注区域的页面带，不是整页缩略图。

执行阶段由 `scripts/scene.py` 转成合成场景：

| 字段 | 含义 |
|---|---|
| `page` | 页面带图片与尺寸 |
| `viewport` | 建议的浏览器视口尺寸 + chrome 高度（版式可调） |
| `notes[]` | 每条批注：`index` / `quote` / `explain` / `mark.rect` / `anchor_y` / `scroll_y` / `at` / `until` / `min_read` |
| `pacing` | 节奏建议：`scroll 0.7s` / `enter 0.9s` / `exit_lead 0.35s` |
| `intro` | 开场滚动位置与片头结束时间 |

## 硬约束

- **版式自由**：浏览器窗口在左或右、批注并排或浮层都可以，但**不允许上下堆叠**；位置由 LLM 决定，代码不写死。
- **页面 1:1**：只对 `#page-stage` 做 `translateY` 滚动，**禁止 scale**（缩放会让文字发糊、标注坐标失准）。
- **标注落在页面图层内**：`data-mark` 必须是 `#page-stage` 的直接子元素、绝对定位，
  几何与 `mark.rect` 逐像素一致（闸门实测，误差 >2px 打回）。这样标注会随网页一起滚动。
- **批注正文**：序号 + 原文摘录 + 解释；`quote` 过长的只展示最关键一段，**不得改写原文**。
- **节奏宁慢勿快**：滚动到位再入场；入场 ≥ `pacing.enter`；落位后 `min_read` 秒内画面完全静止。
- 渲染期完全离线：只用 `assets/` 下的本地截图与本地 `gsap.min.js`。
- 抓取失败：用户明确给了网址 → 如实报错；自动搜索来的来源 → 该段降级为 `opendesign` 并在蓝图注明。
