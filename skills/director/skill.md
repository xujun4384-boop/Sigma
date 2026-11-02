# director - 导演组（计划驱动，不写死流程）

> ★ **视频制作的统一入口**：任何「做视频 / 生成动画短片 / 出成片」的需求都应走这里。

**总导演**：先产出制作蓝图交用户确认，确认后按蓝图调度各部门完成成片。它不是固定流水线——**做什么由蓝图决定**，导演只负责编排、门禁与收尾审查。蓝图可定义 BGM（`music`）与音效（`sfx`，由音效组按配方程序合成）。

## 两阶段用法
1. **设计**：`director(brief="用户需求", cinematic_count=1)` → 内部导演 LLM 产出蓝图 → 返回 `need_confirm`。
   主 LLM 用 `ask_user` 把蓝图给用户确认（不同意就改/重来），并顺便确认 cinematic 段数（默认 1，可 0/2/3）。
2. **执行**：`director(plan="<确认后的蓝图JSON>", output_path="final.mp4", project="xxx", cinematic_count=1)` → 按蓝图制作成片。

> `cinematic_count` 是整片影视级段数：**默认 1 段**；用户明确要求 0（不用）/ 2 / 3 段时才改。
> 设计阶段是硬约束（蓝图里 cinematic 数量必须相等）；执行阶段超出预算的段会自动降级为 HTML 动画。
>
> 另一种开场/任意段模式 `footage`（用户自备视频）：**只有用户主动提供素材并点名用途时**才写进蓝图。
> 素材由用户放在项目文件夹，`video` 写路径，可用 `overlay` 加标题；用户没提就绝不自动使用。
>
> 真实地图用 `amap`（高德）：真实中国/世界行政区、真实驾车/步行/骑行路线、地点标注、行程演示。
> 它和 `styled` 的 `visualStyle="map"`（风格化纸地图/插画）不是一回事；真实地理与行程必须用 `amap`。

## 蓝图结构
```json
{
  "title": "标题",
  "style": "整体视觉风格",
  "canvas": {"width": 1920, "height": 1080, "fps": 30},
  "panels": [
    {"engine": "opendesign|manim|cinematic|styled|remotion|footage|amap",
     "hook": {"type": "result|question|wrongway|contrast|ui|object|countdown|map|sound|handwritten|footage",
              "text": "屏幕上出现的钩子文案（可空）", "why": "为什么能抓人（可选）"},
     "narration": "本段旁白(可空)",
     "visual": "本段画面需求", "prompt": "仅cinematic英文提示词", "seconds": 10,
     "video": "仅footage必填：用户提供的视频（相对项目目录/绝对路径；非 mp4 自动转 mp4）",
     "fit": "仅footage可选：contain（默认，补边）| cover（裁切铺满）",
     "clip_seconds": "仅footage可选：只取素材前 N 秒（默认整段）",
     "keep_audio": "仅footage可选：保留素材原声（默认true；有旁白时旁白优先）",
     "map": {"kind": "route|region|world|flight", "title": "地图标题", "subtitle": "副标题", "city": "北京",
             "theme": "dark|light", "markers": [{"name": "北京", "coord": [116.4074, 39.9042]}],
             "route": {"origin": "三里屯", "destination": "国贸", "mode": "driving"},
             "flight": {"from": "上海", "to": "大连", "arc": 0.16},
             "region": {"soc": "CHN", "name": "北京市", "adcode": "110000", "depth": 1,
                        "bounds": [[73.5,3.8],[135.1,53.6]], "highlight": ["北京市", "上海市"]},
             "world": {"highlight": ["CHN", "USA"], "center": [0, 20]}},
     "visualStyle": "仅styled必填：14种风格id之一", "shots": "仅styled linear可选：2~5",
     "layout": "仅styled可选：linear（默认）| grid（大画布分格跳格）",
     "grid": {"cols": 2, "rows": 2, "order": [0, 1, 2, 3], "weights": [1, 1, 1, 1],
              "moves": {"1": {"zoom": 1.14}}},
     "overlay": {"title": "标题", "subtitle": "副标题(可空)", "accent": "#e03131", "position": "upper"},
     "sfx": [{"at": 0.4, "recipe": "cartoon.pop", "level": 55}]}
  ],
  "subtitles": true,
  "review": true,
  "sfx_density": "normal",
  "sfx_snap": "visual",
  "transition": "dissolve",
  "transition_seconds": 0.6
}
```
> `overlay` / `transition` / `music` / `sfx` 是**可选**字段（不填即不启用）。`music` / `sfx` **默认不写**，见下文。

## 开场钩子（第一段必填）

没有 cinematic 时，开场不能靠空镜/慢推。第一段是钩子，不是封面/logo/空镜。第一段必须写 `hook`，从下面选一个：

| hook.type | 钩子 | 适合内容 | 优先引擎 |
|---|---|---|---|
| `result` | 结果前置/数字冲击：先给最终结果或反差数字，再倒回讲过程 | 效率、成长、测评、案例 | remotion / opendesign |
| `question` | 反常识提问：一句话逐字打出，停半拍再给答案 | 观点、科普、职场 | remotion / opendesign |
| `wrongway` | 错误示范/痛点现场：先演常见错误，再给解法 | 教程、工具、避坑 | remotion / opendesign |
| `contrast` | 前后对比：左右/上下分屏「你以为 vs 实际」 | 产品、改造、对比测评 | remotion / opendesign |
| `ui` | 熟悉 UI/POV：假手机屏、聊天、搜索框、后台仪表盘 | 互联网、AI、产品、生活痛点 | remotion / opendesign |
| `object` | 物件特写：车票、账单、钥匙、信封等近景 + 慢推/音效 | 个人故事、情绪、回忆 | styled |
| `countdown` | 倒计时/进度：天数、deadline、进度条 | 挑战、计划、复盘 | remotion / opendesign |
| `map` | 地图路线：真实路线/地点开场，配时间/距离数字 | 旅行、通勤、地理、迁徙 | amap（真实路线）/ styled（风格化纸图） |
| `sound` | 声音先导：黑屏先响一声闹钟/提示音/盖章，再出画面 | 生活、职场、悬念 | remotion / opendesign + sfx |
| `handwritten` | 手写便签：便签/清单/日记逐字出现，划掉关键项 | 日常、亲情、成长 | styled / opendesign |
| `footage` | 用户素材开场：用户自备视频直接作开场（**仅用户主动提供素材时**） | 已有成片、实拍素材、外部生成的开场 | footage |

规则：
- **第一段画面至少 10 秒**，只传达 1 个信息点；不要压成三五秒敷衍。
  例外：`cinematic`（固定 6/10 秒）、`footage`（素材原长）。
  **旁白可以短于 10 秒**；旁白结束后剩余画面留白（不加旁白、不加新内容），
  第二段从第一段画面结束后开始，**第二段的旁白与字幕时间轴不得被挤动**。
- 非 cinematic/footage 的第一段，蓝图 `seconds` 写 ≥10（写小了执行层也会抬到 10 秒）。
- 第一句旁白直接给结果/问题/冲突；禁止“大家好 / 今天我们来聊聊 / 本期视频”。
- 优先 `remotion`（title / kinetic / ui 模板）或 opendesign / styled；只有 `cinematic_count > 0` 且确实需要实拍感时，才用 cinematic。
- **真实地点/行程/路线开场（如“从 A 到 B”“某城市/国家地图”）→ `amap`。**
- **只有用户主动提供素材、并说明用它开场/做某一段时，才用 `footage`；用户没提就不要用。**
- **`remotion` 只用于第一段**；其他段不要用。
- **`cinematic_count=0` 时，第一段禁止 cinematic，也禁止空镜/慢推/纯氛围画面。**
- 钩子必须和正片内容真实相关，不要标题党。

## 选引擎（用对、用好）
按"这一段要让观众看到什么"选，别惯性全用一个：
- **`manim`（Manim 讲解）**——**科普讲解首选**。数学/几何图形、公式推导、坐标与函数、原理分步演示。
  - 用 manim 时，`visual` 要写清"**讲什么、分几步、出现哪些图形/公式、节奏**"；工具内部会写好动画并精确对齐时长。
  - 边界：擅长精确的数学几何表达；**不擅长写实实体建模**（无遮挡剔除）→ 产品/人物/场景写实画面请用 cinematic。
- **`opendesign`（HTML 动画）**——**信息/排版主力**。文字标题、要点罗列、图表数据、流程/对比、UI 演示。
- **`cinematic`（影视级）**——**实拍感/氛围**。真实场景空镜、情绪镜头、开场钩子；单段 6/10s；
  **整片段数由 `cinematic_count` 决定，默认 1 段**（0=不用；用户可在确认时明确要求 2/3 段，最多 3 段）。
  ⚠️ 画面是**固定长度**，该段旁白**必须 ≤ 画面时长（宁短勿长）**；旁白长于画面会让成片结尾**卡在最后一帧**（像视频卡住）。
  opendesign/manim 由旁白定时长、定格一帧无妨；cinematic 不行，所以这类段的旁白要写得短。
- **`styled`（风格动画）**——**叙事/插画主力**。讲故事、情绪、隐喻、人物关系、需要一个完整统一画风的段落。
  - 选了 `styled` **必须**写 `visualStyle`（14 种之一），其他引擎不要写。
  - 它用代码逐帧画（无歌词），时长跟随旁白；可选 `shots`（2~5）控制 linear 镜头数。
  - **可选版式**：不写 `layout` = 现有 `linear`（2~5 切镜，行为完全不变）。
    只有这一段是 **2~6 个互不相关的画面/信息点**（像分镜故事板）时，才写 `"layout": "grid"`：
    一张大画布分格，camera 到点瞬间跳格，每格独立播放；格内可推拉。
    - `grid` 可选：`cols`/`rows`（默认 2×2）、`order`（播放顺序）、`weights`（每格时长权重）、
      `moves`（格内推拉，如 `{"1":{"zoom":1.14}}`）。不写 = 2×2 等权重、无推拉。
    - `shots` 只对 linear 生效；grid 是一段一个 scene，格数由 `grid` 决定。
    - 连续动作/情绪推进仍用 linear；grid 是“多个独立画面”的工具，不要滥用。
  - 可以画短标题、关键词、标签、数字、单字（≤12 字，按风格的「文字」规则）；
    **不能画旁白/字幕原文**，底部 12% 留给导演组字幕。
  - 风格库（14 选 1）：`crayon` 绘本 / `shadow` 皮影 / `flat` 扁平 MG / `ink` 水墨 /
    `pixel` 像素 / `comic` 漫画 / `whiteboard` 白板 / `hanzi` 汉字 / `timeline` 时间线 /
    `isometric` 等距 / `scale` 比例尺 / `infographic` 信息图 / `map` 风格化地图 / `exploded` 3D 拆解。
  - **`map` 是“风格化纸地图”**（米色纸/等高线/图钉/虚线），适合虚构、隐喻、绘本式地图，不保证真实地理；
    真实地点/行程/中国或世界地图必须用 `amap`，不要用 styled 的 map 代替真实路线。
  - **风格由导演组决定，不要向用户询问风格，也不要把风格选择推给用户。**
    按每一段的内容、时代与叙事来选：现代都市→flat/comic，古装/宿命→shadow/ink，讲解→whiteboard/isometric，
    数据→infographic/scale，旅程→map，游戏怀旧→pixel，温柔日常→crayon。
- **`remotion`（开场钩子）**——**只用于第一段**，画面至少 10 秒（时长由导演给定，动画铺满整段）。
  默认让 LLM 自由写 TSX，渲染后做视觉闸门；不过回灌重写，最多 3 次，再回退模板。
  - 导演只写 `hook` 与 `visual`，不直接写 TSX。
  - `hook.type` 用于提示词与模板兜底：`result`/`countdown` → kinetic；`question`/`sound`/`object`/`handwritten` → title；
    `ui`/`wrongway`/`contrast`/`map` → ui。
  - 首次运行可能需要 `npm install`；自由发挥和模板都失败时自动降级 opendesign。
- **`footage`（用户自备素材）**——把用户自己放在项目文件夹里的视频（如 10 秒 mp4）**直接**用作一段。
  - **只能由用户主动提出**：用户说明"我自己提供了一段视频 / 素材放在项目里 / 用我这段视频开场或做第几段"时才用；
    用户没提就不要选它（目录里有视频也不代表要用——可能是历史成片）。
  - 必填 `video`（素材路径，相对项目目录或绝对路径；mp4/mov/mkv/webm 等均可），一般还要写 `overlay` 加标题/副标题。
  - **非 mp4 素材自动转成 mp4**；画面统一到项目画布（默认 **1920×1080**）。
  - 段长 = 素材原长（`clip_seconds` 可只取前 N 秒）；不做补帧拉伸，旁白必须 ≤ 素材长度。
  - 画布适配 `fit`：`contain`（默认，完整保留并补黑边）/ `cover`（等比裁切铺满）。
  - 原声默认保留（`keep_audio`，默认 true）；该段**有旁白时旁白优先**，没有旁白才用素材原声。
  - 素材找不到 / 不是视频：**如实失败，不降级成别的画面**（用户指定的素材不能被替换）。
- **`amap`（高德真实地图）**——真实中国/世界行政区、真实驾车/步行/骑行路线、地点标注、行程演示。
  - **涉及真实地点、行程、路线、中国地图、世界地图时优先用它**；不要用 styled 的 map 画假地图。
  - 必填 `map` 对象；标题/副标题写在 `map` 里，不要用 `overlay`。
  - `map.kind`：
    - `route`：`origin`/`destination`（中文地名或 `[经度,纬度]`）+ **`city`（如“北京”）**；`mode` 可选 driving/walking/riding；
       自动算距离/时间（`subtitle` 留空时自动填）。
     - `flight`：`from`/`to`（城市名或 `[经度,纬度]`）+ 可选 `arc`（默认 0.16）；真实城市位置 + 弧线 + 飞机图标 +
       已飞轨迹 + 直线距离；这是“航线示意”，不是真实航班轨迹，适合飞机/跨城/旅行段。
     - `region`：`soc`（默认 CHN）+ `depth=1`（省级）+ `highlight`（行政区名或 adcode）+ `markers`；
       单省可写 `name`（如“北京市”）或 `bounds`（省级视图）。城市街道级/具体行程用 `route`，不要用 region。
     - `world`：`highlight` 写国家 `SOC`（CHN/USA/JPN…）或中文国名 + `markers`；
       默认 0° 经线居中、zoom 3（适合 1920×1080），境外城市标记最好直接写 `coord`。
  - `markers`：城市点；写 `name` 或 `coord`，地名会地理编码（有 `city` 更准）。
  - **不要编造坐标**；不确定就写地名 + `city`。只写真实存在的地点。
  - 地图需要联网和高德 Key；未配置时设计阶段会明确提示不要用 amap。
  - 境外只有国界/洲名级别，没有境外街道细节；境外城市街区请换别的方案。

判断准则：**有公式/几何/原理/函数 → manim**；纯信息与文字排版 → opendesign；要实拍感/氛围 → cinematic；
**讲故事/要画风 → styled**；**真实地点/行程/路线/中国或世界地图 → amap**；**用户主动提供了视频素材 → footage**。
一段若"既讲原理又给信息"，按该段**主要意图**择一。
**不要每段都用 manim——只在真正"讲道理"的段落用**，其余交给 opendesign / styled 承担节奏。

## 执行顺序（依赖驱动，非写死阶段）
1. **旁白先行**（若任一面板有旁白）→ 实测时长 = 骨架；各面板时长随之确定。
2. **画面派工**：逐面板按 `engine` 派给对应部门，**可多引擎混排**。
   - `opendesign` → `opendesign_video`；`manim` → `manim_video`；`cinematic` → `video_cinematic_generate`；
     `styled` → `styled_video`（内部引擎，14 选 1）；`remotion` → `remotion_hook_generate`（只用于第一段）；
     `footage` → `footage_video`（用户自备素材，仅在用户点名时）；`amap` → `map_video`（高德真实地图）。
   - **影视级预算**：不再查询 API 额度。默认每支片只用 **1 段** cinematic；用户可在 ask_user 明确要求 **0（不用）/ 2 / 3 段**，通过 `cinematic_count` 传入。设计蓝图时该段数是硬约束（panels 里 cinematic 数量必须相等）；执行时超出预算的段自动降级为 HTML 动画。
   - **降级链**：`styled → opendesign`、`manim → opendesign`、`cinematic → opendesign`、`remotion → opendesign`、`amap → opendesign`；`footage` **不降级**（素材缺失/损坏如实报错，不拿别的画面冒充），任一段失败不整片崩。
   - 画面引擎只有这七个；蓝图里的 `engine` 必须取其中之一，其余取值一律按 `opendesign` 处理。
     `remotion` 仅限第一段；其他段出现会被校验打回。`footage` 可用在任意一段（含开场）；`amap` 也可用在任意段。
   - `footage` 段在**旁白之前**先做素材存在性检查，缺文件直接报错，不会白花旁白/合成时间。
3. **字幕**（蓝图 `subtitles=true`）：`subtitle` 依旁白字级时间戳出单行/底部 `.ass`。
4. **配乐**（仅当蓝图写了 `music`）：`music_generate`（音乐组）按描述生成纯音乐 BGM，铺满全片
   （音乐偏短则交叉淡化无缝循环），由合成组与旁白混音（旁白优先，音量取 `level`，首尾淡入淡出，**与画面同时结束**）。
4b. **音效**（仅当面板/顶层写了 `sfx`）：`sfx`（音效组）按配方程序合成短音效，
   按面板内相对时间换算到成片时间轴，与旁白/BGM 混音；单个失败只跳过该音效，不阻断成片。
5. **合成**：`compose_video` 归一化 + 拼接（可按蓝图做**段间转场**）+ 旁白 + 背景音乐 + 音效 + 烧字幕。
6. **审查**（蓝图 `review=true`）：`video_review` 随机截帧 + 字幕位置校验。

## 配乐（默认关闭，成片满意后追加）
配乐是**可追加的后期工序**，不进默认流程：
- **默认不配乐**：设计蓝图时**不写 `music`**；只有用户在需求里明确要求配乐/BGM/主题曲时才写。
- **为什么默认关**：音乐生成单次要 2~3.5 分钟，是整条流程里最慢的一步；且多数需求先看画面。
- **成片后追加（只重做配乐与合成）**：
  ```
  director(project="<同名>", patch='{"music": {"prompt": "轻快科技感电子配乐，无人声", "level": 22}}')
  ```
  画面/旁白/字幕全部按签名复用，**不会重做**；只有配乐是新生成的，合成因 BGM 变化而重烧一次。
- **移除配乐**：`patch='{"music": null}'` → 只重烧合成。
- **音量**：`level` 是百分比(0~100，默认 22)；旁白优先，配乐只做铺底。
- **时长对齐**：音乐固定裁到成片时长并首尾淡入淡出，**视频结束处音乐同时结束**；
  音乐比片长短时用 **acrossfade 交叉淡化无缝循环**铺满（不是硬循环，长片也不会有"咔"的接缝）。
- 缺 Key 或生成失败时**自动跳过配乐**，不阻断成片。

## 音效（默认关闭，按画面动作点添加）

音效与 BGM 是两条独立轨道：**BGM 是铺满全片的音乐床，音效是带时间点的一次性事件**（哔、duang、whoosh、盖章、金币、重击等）。

- **默认不加**：只有画面里有明确动作点/强调点/转场点时，才在该面板写 `sfx`。
- **密度由时长控制**（不再用固定 3~8 个）：顶层 `sfx_density` 取 `light` / `normal`（默认）/ `rich` / `none`，
  执行层按成片实测时长换算目标区间：

  | 档位 | 每分钟事件数 | 2 分钟视频约 |
  |---|---|---|
  | `light` | 1~2 | 2~4 个 |
  | `normal` | 3~6 | 6~12 个 |
  | `rich` | 6~10 | 12~20 个 |
  | `none` | 0 | 关闭 |

- **三条硬约束**（执行层自动执行，不靠 LLM 自觉）：
  1. 单段上限 = `min(3, ceil(段长/10s))`：短段最多 1 个，长段最多 3 个；
  2. 全片两个音效之间至少 **2 秒**；
  3. 超出密度上限时按 `priority`（0~100，默认 50）保留，其余裁掉；全片硬上限 40 个。
- **重要事件写高优先级**：`priority` 70~90 给关键动作/转场，40~60 给点缀。
- **`at` 是“预计的画面动作时刻”，不是旁白断句时间**：执行层会对成片做视觉节拍检测
  （元素入场 / 镜头切换 / 动画起点），在 `sfx_snap_window`（默认 ±1.5 秒）内把音效吸附到最近节拍。
  所以 `at` 要写在你预期的画面上，不要跟着旁白走。
- **`sfx_snap`**：`visual`（默认，吸附画面节拍）/ `none`（保留原时间）；
  单条音效要严格卡点时写 `"snap": false`。
- **画面节拍检测不截图、不调用视觉模型、不消耗 token**：只把 12fps / 48×48 的 RGB 原始帧
  通过管道读进内存（单段 30s 约 2.5MB 临时数据），结果按“视频路径 + mtime”缓存。
  成本远低于一次视觉调用。
- **偏少不强行补**：实际数量低于目标下限时只提示“偏少，可用 patch 追加”，不会无依据地硬塞。
- 每段最多 3 个，不要每段都加，也不要在旁白连续说话时堆。
- **配方库**：`skills/sfx/skill.md` 里有 30 个配方，分 6 个风格家族：
  `mg` / `cartoon` / `paper` / `pixel` / `tech` / `cinematic`。按该段画面风格选（如 crayon→cartoon、pixel→pixel、whiteboard→paper、flat→mg）。
- **写法（面板内相对时间）**：
  ```json
  {"engine": "styled", "visualStyle": "crayon",
   "sfx": [{"at": 0.4, "recipe": "cartoon.pop", "level": 55, "priority": 50},
           {"at": 2.1, "recipe": "cartoon.duang", "level": 65, "priority": 80,
            "params": {"pitch": -2}}]}
  ```
  `at` 相对本段开头，导演会换算到成片时间轴；旁白重配、转场变化后仍然对齐。
- **顶层写法（适合 patch 追加到已有项目）**：
  ```json
  {"sfx": [{"panel": 3, "at": 1.2, "recipe": "mg.whoosh", "level": 50}]}
  ```
  `panel` 从 **1** 开始。
- **音量**：`level` 是百分比 0~100，默认 60；旁白优先，音效只做点缀。
- **参数**：`params` 可选 `pitch`（半音 -12~12）、`brightness`（-1~1）、`seed`（轻微变化）。
- **追加/修改/移除（patch）**：
  ```json
  {"panels": {"3": {"sfx": [{"at": 1.2, "recipe": "cartoon.boing", "level": 60}]}}}
  ```
  写空数组 `[]` 即移除该段音效；`{"sfx": null}` 清空顶层音效。
- **调整全片密度 / 画面吸附（patch）**：
  ```json
  {"sfx_density": "light", "sfx_snap": "visual"}
  ```
  可选 `light` / `normal` / `rich` / `none`；`sfx_snap` 可选 `visual` / `none`。
  改完只需要重算音效与合成，画面/旁白/字幕复用。
- **容错**：配方不存在 / 合成失败只跳过该音效并提示，不影响成片。
- **边界**：程序合成擅长 MG/UI/卡通/氛围；写实类（雨声、脚步、关门）暂不覆盖。

## 成片技巧建议（可选，导演按题材定夺）
- **标题/蒙版包装（overlay）**：底片**前半段保留原画**，后半段渐显全屏蒙版并叠加「封面式大标题入场」，
  让画面更饱满、更有设计感。**仅 `cinematic` / `footage` 可用**（opendesign/manim 自带排版，不叠蒙版）。
  - 通过内部能力 `title_overlay` 实现（把包装**烘焙进该段**，产物仍是普通 mp4，合成无需改动）。
  - **最适用**：① **开场钩子**——`cinematic` 空镜或用户素材 + overlay 大标题做"引导过渡"，再进正片；
    ② 空镜/素材偏单调时；③ 章节/主题切换处。
  - 用法：在对应面板写 `overlay:{title, subtitle?, accent?, position?, align?, reveal_ratio?}` 即启用；**不写 = 不用**。
    `reveal_ratio` 默认 0.5（前 50% 不下蒙版），`align` 默认 left（左对齐），`position` 默认 upper（左上偏中，避开底部字幕）。
  - 原则：**克制**，别每段都加；是否采用由导演判断，工具不强制。
- **段间转场（transition）**：段与段之间用溶解/打散/径向等切换，替代单调的硬切。
  - 用法：蓝图顶层写 `transition`（如 `"dissolve"`）+ `transition_seconds`（默认 0.6），应用到**所有接缝**；
    也可在**单个面板**写 `transition` / `transition_seconds` **只覆盖某一处接缝**（指"进入该段"的那处）；
    写 `"none"` 即该处硬切。
  - 可用名（ffmpeg xfade）：`fade/dissolve/pixelize/radial/hblur/distance/circleopen/circleclose/circlecrop/rectcrop`、
    `wipeleft…wipebr`、`slideleft…slidedown`、`smoothleft…smoothdown`、`coverleft…coverdown`、`revealleft…revealdown`、
    `diagtl/diagtr/diagbl/diagbr`、`hlslice/hrslice/vuslice/vdslice`、`squeezeh/squeezev/zoomin`、
    `fadeblack/fadewhite/fadegrays/fadefast/fadeslow`、`vertopen/vertclose/horzopen/horzclose`、`hlwind/hrwind/vuwind/vdwind`。
  - **建议用法**：主题/章节切换用 `dissolve`/`circleopen`；科技/数据感用 `pixelize`/`hlslice`；情绪推进用 `fadeblack`。
    别每处都用同一个，也别过度使用（**转场会"吃掉"时长**，全片加太多会显得拖沓）。
  - ⚠️ 转场会让相邻两段重叠、成片时长变短；导演/合成已按同一重叠量对齐**字幕与旁白时间轴**，无需手动补偿。
- 其余部门保持单一职责，导演按需组合，不写死流程。

## 进度（不盲盒）
导演在每步 emit 进度，并把子部门进度转发到导演名下（`[narration] …` / `[music_generate] …` / `[sfx] …` / `[opendesign_video] …`），
前端实时显示："③ 画面 第 4/10 段（水彩）生成中…"、"④b 配乐生成…"、"④c 音效：9 个（标准密度目标 6~12，3 个吸附到画面节拍）…"、"⑤ 合成…" 等。

## 断点续做 / 微调（逐项签名，只重做改动处）
- 状态存于 `video_work/<project>/director_state.json`：蓝图、**逐句旁白缓存**、**每个分镜的签名与产物**、**配乐**、**音效资产**、**画面节拍缓存**、字幕、成片。
- 每步都用**内容签名**判断是否需要重做：
  - 旁白按"文案+音色+语速"逐句缓存 → 只重配改动的那句，偏移自动重算；
  - 画面按"引擎+画面描述+时长+画布+风格+该段旁白"逐段签名 → **只重渲染改动的那段**；
    `styled` 段的签名额外包含 `visualStyle`、风格规格指纹，以及显式选择时的 `layout/grid`；
    换风格或 linear↔grid 只重做这一段；
    `footage` 段的签名额外包含素材路径 + 文件 mtime/大小 + `fit` / `clip_seconds` / `keep_audio`，
    换素材（含同名覆盖）只重做这一段；
  - 配乐按"描述"签名 → 描述没改就复用已有 BGM，不重复生成；
  - 音效按"配方 + 参数 + 种子"签名 → 相同音效复用 wav，不重复合成；
  - 画面节拍按"视频路径 + mtime"缓存 → 画面没变就不重复分析；画面重渲后自动重算；
  - 字幕按"所用旁白"签名；合成按"各段内容签名 + 字幕 + 配乐 + 音效 + 画布"签名 → 上游有任何变化才重合成。
- **中途崩溃 / 程序被关**：用**相同 `project`** 再调一次即可续做（`director(project="<同名>")`）。
- **微调（patch）**：不改整份蓝图，只描述"改哪几处"，做**最小 diff → 手术式重做 + 重合成**：
  ```json
  {"panels": {"3": {"engine": "cinematic", "visual": "新画面描述"}, "5": {"narration": "新旁白"}}, "style": "…"}
  ```
  `panels` 的键是"第几段"（从 **1** 开始）。调用：`director(project="<同名>", patch="<上面的JSON>")`。
  - ⚠️ **微调必须用 `patch`，不要重发整份 plan**：重发整份 plan 时，模型常把措辞/`seconds` 改得略有不同，会引发不必要的大面积重渲（形同重做）。
  - ⚠️ **不要用 `force=true`**：force 会抛弃所有签名、整片重来。`patch` 模式内部会**忽略** force=true，只重做受影响段；即使误传也不会整片重渲。
  - 逐段签名只看"引擎/画面/提示词/标题包装/旁白/实测时长/画布"；**全局 `style` 与兜底 `seconds` 不参与**，所以风格措辞微调不会触发重渲。
    `styled` 段额外看 `visualStyle`、风格规格指纹、`shots`，以及显式选择时的 `layout/grid`。
  - 每次执行结束会汇报"画面 重做 N / 复用 M 段；旁白 重配 X / 复用 Y 句"，便于判断是不是真·微调。
- `force=true` → 无视签名，整片重来。

## 边界
- 导演**不改流程、不重写渲染**，一切交给部门。
- `styled_video` 是导演组内部引擎，**不直接暴露给用户，也不让用户选风格**。
- 能力缺口（如实拍）应在设计阶段就告知用户。
- 产物目录：`video_work/<project>/{voice,panels,music,sfx,subtitles,review}/` + 成片 + `director_state.json`。
