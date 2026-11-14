# director - 导演组（计划驱动，不写死流程）

> ★ **视频制作的统一入口**：任何「做视频 / 生成动画短片 / 出成片」的需求都应走这里。

**总导演**：先产出制作蓝图交用户确认，确认后按蓝图调度各部门完成成片。它不是固定流水线——**做什么由蓝图决定**，导演只负责编排、门禁与收尾审查。蓝图可定义 BGM（`music`）与音效（`sfx`，由音效组按配方程序合成）。

## 两阶段用法
1. **设计**：`director(brief="用户需求", cinematic_count=1)` → 内部导演 LLM 产出蓝图 → 返回 `need_confirm`。
   主 LLM 用 `ask_user` 把蓝图给用户确认（不同意就改/重来），并顺便确认 cinematic 段数（默认 1，可 0/2/3）。
2. **执行**：`director(plan="<确认后的蓝图JSON>", output_path="final.mp4", project="xxx", cinematic_count=1)` → 按蓝图制作成片。
3. **定妆**（蓝图里有人物时才做，且必须在执行前）：`character_sheet(spec=..., project="<同名>")`
   → 应用画布出五格定妆图，用户在画布上点确认 → 再把
   `character="video_work/<project>/character.json"` 传给 `director`。
   角色是跨段的共同资产：没定妆就开拍，等于每段各画一个人。

> `cinematic_count` 是整片影视级段数：**默认 1 段**；用户明确要求 0（不用）/ 2 / 3 段时才改。
> 设计阶段是硬约束（蓝图里 cinematic 数量必须相等）；执行阶段超出预算的 cinematic 段会先改用 3D 渲染
> （`blender` 作为 cinematic 的 backup），3D 也失败才退到 HTML 动画。
>
> 另一种开场/任意段模式 `footage`（用户自备视频）：**只有用户主动提供素材并点名用途时**才写进蓝图。
> 素材由用户放在项目文件夹，`video` 写路径，可用 `overlay` 加标题；用户没提就绝不自动使用。
>
> 真实地图用 `amap`（高德）：真实中国/世界行政区、真实驾车/步行/骑行路线、地点标注、行程演示。
> 它和 `styled` 里写的「风格化纸地图」不是一回事；真实地理与行程必须用 `amap`。

## 蓝图结构
```json
{
  "title": "标题",
  "style": "整体视觉风格",
  "canvas": {"width": 1920, "height": 1080, "fps": 30},
  "panels": [
    {"engine": "opendesign|manim|cinematic|styled|footage|amap|webpage|blender",
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
     "styleNote": "仅styled段可选：本段局部风格要求",
     "intro": {"title": "从一条路线\n看懂一座城市", "accent": "一座城市", "sub": "副标（可空）",
               "tag": "SIGMA 科普视频", "side": "right", "seconds": 4},
     "embeds": [{"type": "blender|manim|amap", "brief": "特效画面描述",
                 "rect": [760, 250, 900, 506], "start": 1.2, "duration": 4.0,
                 "mask": "圆角 24px", "map": {"kind": "route", "…": "仅 amap"}}],
     "overlay": {"title": "标题", "subtitle": "副标题(可空)", "accent": "#e03131", "position": "upper"},
     "sfx": [{"at": 0.4, "recipe": "cartoon.pop", "level": 55}]}
  ],
  "styleGuide": "有 styled 段时写：全片风格档案（配色/线条/质感/光/构图/运动/文字/禁止项），各 styled 段共用",
  "subtitles": true,
  "review": true,
  "sfx_density": "normal",
  "sfx_snap": "visual",
  "transition": "dissolve",
  "transition_seconds": 0.6
}
```
> `overlay` / `transition` / `music` / `sfx` 是**可选**字段（不填即不启用）。`music` / `sfx` **默认不写**，见下文。

## 开场钩子 + 标题入场（前 1~2 段）

没有 cinematic 时，开场不能靠空镜/慢推。第一段是钩子，不是封面/logo/空镜。第一段必须写 `hook`，从下面选一个；如果钩子需要两个节拍，第 2 段也可以继续写 `hook`（第 3 段起禁止）：

| hook.type | 钩子 | 适合内容 | 建议引擎（按需，非硬约束） |
|---|---|---|---|
| `result` | 结果前置/数字冲击：先给最终结果或反差数字，再倒回讲过程 | 效率、成长、测评、案例 | styled / opendesign |
| `question` | 反常识提问：一句话逐字打出，停半拍再给答案 | 观点、科普、职场 | styled / opendesign |
| `wrongway` | 错误示范/痛点现场：先演常见错误，再给解法 | 教程、工具、避坑 | styled / opendesign |
| `contrast` | 前后对比：左右/上下分屏「你以为 vs 实际」 | 产品、改造、对比测评 | styled / opendesign |
| `ui` | 熟悉 UI/POV：假手机屏、聊天、搜索框、后台仪表盘 | 互联网、AI、产品、生活痛点 | opendesign / styled |
| `object` | 物件特写：车票、账单、钥匙、信封等近景 + 慢推/音效 | 个人故事、情绪、回忆 | styled / cinematic（有预算时） |
| `object3d` | 3D 设备/物件开场：真 3D 设备或关键物件绕机、推近、翻转 | 硬件、数码、产品发布、设备展示 | blender（真 3D）/ opendesign（three.js） |
| `countdown` | 倒计时/进度：天数、deadline、进度条 | 挑战、计划、复盘 | opendesign / styled |
| `map` | 地图路线：真实路线/地点开场，配时间/距离数字 | 旅行、通勤、地理、迁徙 | amap（真实路线）/ styled（风格化纸图） |
| `sound` | 声音先导：黑屏先响一声闹钟/提示音/盖章，再出画面 | 生活、职场、悬念 | styled / opendesign + sfx |
| `handwritten` | 手写便签：便签/清单/日记逐字出现，划掉关键项 | 日常、亲情、成长 | styled / opendesign |
| `footage` | 用户素材开场：用户自备视频直接作开场（**仅用户主动提供素材时**） | 已有成片、实拍素材、外部生成的开场 | footage |

### 标题入场 intro（钩子之后、正片之前）

在**最后一段钩子**上写 `intro`，把钩子的全屏画面连续缩小到一侧，另一侧出现本次视频的大标题、副标和 Sigma 标签：

```json
"intro": {"title": "从一条路线\n看懂一座城市", "accent": "一座城市",
          "sub": "距离、时间与路径，都是理解城市的一手证据。",
          "tag": "SIGMA 科普视频", "side": "right", "seconds": 4}
```

- 这是**固定品牌转场**，不是普通分镜；执行层用模板渲染，不交给 LLM 写 HTML。
- `title` 必填，1~2 行，每行尽量 ≤8 字（最多 10 字）；字号会按最长一行自动定，最大 104px。
- `accent` 可选：标题里要强调的词，会变成品牌绿。
- `sub` 可选；`tag` 默认 `SIGMA 科普视频`。
- `side` 是**钩子画面缩到哪一侧**（left/right）；标题放另一侧，默认 right。
- `seconds` 2.5~5.5，默认 4；**没有旁白**，是静音转场。
- **钩子结尾不要淡出到黑/白**：intro 会接住钩子的最后一帧来缩小，最后一帧必须是可读画面。
- 全片最多一个 intro，必须写在最后一段钩子上；**写了 intro 的钩子段不要写 `overlay`**（两者都会上大标题）。
- 不写 intro 也可以；但如果用了 2 段钩子，建议写，让观众知道正片开始。

规则：
- **第一段画面至少 10 秒**，只传达 1 个信息点；不要压成三五秒敷衍。
  如果拆成 2 段钩子：两段合计 ≥10 秒、单段 ≥4 秒；拆段不是把钩子变短。
  例外：`cinematic`（固定 6/10 秒）、`footage`（素材原长）。
  **旁白可以短于 10 秒**；旁白结束后剩余画面留白（不加旁白、不加新内容），
  第二段从第一段画面结束后开始，**第二段的旁白与字幕时间轴不得被挤动**。
- 非 cinematic/footage 的第一段，蓝图 `seconds` 写 ≥10（写小了执行层也会抬到 10 秒）。
- 第一句旁白直接给结果/问题/冲突；禁止“大家好 / 今天我们来聊聊 / 本期视频”。
- **钩子引擎按内容选，不要默认 remotion——它已停用**（只会做标题/动态字，撑不起开场钩子）：
  实拍感/人物/真实场景 → cinematic（预算允许时）；3D 设备/物件/结构 → blender + `hook.type=object3d`（轻量 3D 可用 opendesign 的 three.js）；
  版式/数字/对比/假 UI/动态字 → styled 或 opendesign；公式/推导/原理 → manim；
  真实地点/行程/路线 → amap；真实网页/数据 → webpage；用户自备素材 → footage。
  以上都是**按内容按需选择，不是硬约束**；唯一硬规则：**任何分镜都不能写 `remotion`**。
- **真实地点/行程/路线开场（如“从 A 到 B”“某城市/国家地图”）→ `amap`。**
- **只有用户主动提供素材、并说明用它开场/做某一段时，才用 `footage`；用户没提就不要用。**
- **hook 只允许前 1~2 段**：第 1 段必填，第 2 段可选，第 3 段起禁止；intro 只能有一个且只能写在最后一段钩子上。
- **`cinematic_count=0` 时，第一段禁止 cinematic，也禁止空镜/慢推/纯氛围画面。**
- 钩子必须和正片内容真实相关，不要标题党。

## 选引擎（用对、用好）
按"这一段要让观众看到什么"选，别惯性全用一个：
- **`manim`（Manim 讲解）**——**科普讲解首选**。数学/几何图形、公式推导、坐标与函数、原理分步演示。
  - 用 manim 时，`visual` 要写清"**讲什么、分几步、出现哪些图形/公式、节奏**"；工具内部会写好动画并精确对齐时长。
  - 边界：擅长精确的数学几何表达；**不擅长写实实体建模**（无遮挡剔除）→ 产品/人物/场景写实画面请用 cinematic。
- **`blender`（原理解释型 3D / 3D+文字）**——**"看不见的结构"讲不清时用它**。
  - 什么时候用：原理的关键在于**空间关系**——谁在谁里面、谁绕着谁转、力/场怎么走、剖开是什么、
    零件怎么装配。这些用平面图解怎么画都别扭，3D 一眼就懂。
  - 什么时候不用：纯公式推导 → `manim`；纯概念对比/流程/数据 → `opendesign`；
    真实场景氛围 → `cinematic`。
  - **方案是「3D 机理 + 画面内短标注」**：3D 负责让人看懂结构，文字只标部件名/关键量（≤6 字）。
    **3D 里绝不照抄旁白原句**——字幕由导演组统一加在底部，重复会打架。
  - 节奏：单段 5~10 秒、2~3 个镜头；**开头 0.5 秒先给全貌**建立空间感，再推进到关键部位。
  - 次要用途：产品外观、设备屏幕内容展示（这时面板写 `screen_html`，工具会用无头 Chromium
    把真实界面截成贴图贴到屏幕上——**不要在 3D 里手画界面**）。
  - **真 3D 开场钩子**：设备/物件/产品外观本身是卖点时，第一段可以直接用 blender，
    配 `hook.type=object3d`（首段仍会抬到 ≥10 秒）。
  - 代价：比 HTML 慢（GPU 约 0.7~1 秒/帧，10 秒 3D 约几分钟起）；全片通常只用 1 段。
  - 失败自动降级 `opendesign`。
- **`opendesign`（HTML 动画）**——**信息/排版主力**。文字标题、要点罗列、图表数据、流程/对比、UI 演示。
  - 可选写 `embeds`，把 **blender / manim / amap** 作为**版面里的一个图层**嵌进来：
    外部片段会先被渲染成帧雪碧图，再由 opendesign 的 canvas + GSAP 逐帧绘制，
    因此可以和文字、卡片、遮罩、阴影共用同一张版，而不是整屏硬切。
  - **有协同价值就优先用**：Manim 需要步骤标签/进度/结论，3D 需要参数/部件清单，地图需要地点/行程说明时，
    优先 `opendesign + embeds`，不要惯性使用裸特效段。
  - **内嵌不等于小窗**：特效可占 60%~80% 主视觉区，opendesign 负责标题、侧栏、进度与批注，统一全片风格。
  - 多个连续理论/公式演示，可合并为一个 opendesign 段 + 一个覆盖全程的 Manim embed，避免连续裸 Manim 段。
  - **不是替代**：特效是唯一叙事主体、完全不需要持续文字协同时，仍可用单独的 `engine=blender/manim/amap` 段。
  - **不强制**每段都嵌：纯标题、纯文字、纯静态图表保持干净。建议全片 1~3 段带 embeds，每段最多 2 个。
  - `rect` 用画布像素 `[x,y,w,h]`；`start` 相对本段开始；`duration ≥1.5s` 且不超出本段时长。
  - 蓝图里这段会显示成「HTML动画 + 3D渲染 / Manim讲解 / 高德地图」，用户能直接看懂。
- **`webpage`（真实网页取景）**——在**模拟浏览器窗口**里滚动真实网页，高亮原文并在旁边浮现批注（原文摘录 + 解释）。
  - **什么时候用**：核心论据是真实统计/榜单/表格数值、官方定义与原文、报告结论、政策条款；
    或讲人群/规模/分布/排名变化；或用户直接给了网址。
    它给的是"凭什么这么说"——观众能亲眼看到原始数字与原句。
  - **什么时候不用**：纯抽象概念与公式推演（manim）、纯排版总结（opendesign）、需要虚构画面（styled/cinematic）、
    登录墙/付费墙页面、关键信息隔着好几屏。
  - **怎么用**：有网址写 `web.url`，没有写 `web.query`（知识点原话，**禁止编造 URL**）；必须写 `web.focus`
    （要让观众看到哪类证据）；`web.max_marks` 默认 3（最多 4），尽量落在同一屏/同一张表。
  - 设计阶段系统会抓取真实来源、选出可逐字标注的原文并算出坐标，回填 `web.source` / `web.marks`；
    蓝图确认时就能看到来源、高亮原文与坐标。
  - **密度**：一支片子 1~2 段最合适；全片都用会单调，opendesign 负责它前后的总结与对比。
  - 和 opendesign 的区别：画面是真实网页（1:1 滚动，不是缩略图），不是重绘。
- **`cinematic`（影视级）**——**实拍感/氛围**。真实场景空镜、情绪镜头、开场钩子；单段 6/10s；
  **整片段数由 `cinematic_count` 决定，默认 1 段**（0=不用；用户可在确认时明确要求 2/3 段，最多 3 段）。
  ⚠️ 画面是**固定长度**，该段旁白**必须 ≤ 画面时长（宁短勿长）**；旁白长于画面会让成片结尾**卡在最后一帧**（像视频卡住）。
  opendesign/manim 由旁白定时长、定格一帧无妨；cinematic 不行，所以这类段的旁白要写得短。
- **`styled`（风格动画）**——**叙事/插画主力**。讲故事、情绪、隐喻、人物关系、需要一个完整统一画风的段落。
  - 它没有固定风格可选：用 **Remotion 现场作画**（无歌词，**仅 2D**），画风来自蓝图顶层的 `styleGuide`。
  - 蓝图里只要有 styled 段，就必须在**顶层**写一份 `styleGuide`（配色/线条/质感/光/构图/运动/文字/禁止项），
    全片所有 styled 段共用；各段可再用 `styleNote` 做局部微调。
  - 用户点名了画风就照原话写进 `styleGuide`；没提就按内容与时代自己定，**不要向用户询问风格**。
  - 可以画短标题、关键词、标签、数字、单字（≤12 字）；**不能画旁白/字幕原文**，底部 12% 留给导演组字幕。
  - 片中有固定人物且需要跨段一致时，先 `character_sheet` 定妆并让用户确认，再执行；
    需要给关键物品也定妆时同样走这一轮。其余情况不必每次都定妆。
  - 风格化的"地图插画"写进 `styleGuide` 即可；真实地点/行程必须用 `amap`，不要用 styled 冒充。
- **`remotion`（已停用）**——旧版开场钩子引擎，只会做标题/动态字，撑不起钩子，**新蓝图任何分镜都不要写**。
  执行层仍保留它的代码（历史蓝图复跑时可用），但设计校验会直接打回。开场钩子请按内容改用
  `cinematic` / `blender` / `styled` / `manim` / `amap` / `opendesign` / `webpage`（按需，不是硬约束）。
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

判断准则：**有公式/几何/原理/函数 → manim**；纯信息与文字排版 → opendesign；
**"看不见的结构"讲不清（遮挡/装配/机构运动/场/剖切）→ blender**；要实拍感/氛围 → cinematic；
**讲故事/要画风 → styled**；**3D 设备/物件/产品外观开场 → blender（hook.type=object3d）**；
**真实地点/行程/路线/中国或世界地图 → amap**；**用户主动提供了视频素材 → footage**；
**要出示真实证据（数据、榜单、官方原文、报告结论）→ webpage**。
**别用 opendesign 把有说服力的真实数字重画一遍**——那种地方优先端出真实页面，opendesign 负责它前后的总结与对比。
一段若"既讲原理又给信息"，按该段**主要意图**择一。
**不要每段都用 manim——只在真正"讲道理"的段落用**，其余交给 opendesign / styled 承担节奏。

## 执行顺序（依赖驱动，非写死阶段）
0. **定妆**（仅当蓝图里有人物）：先 `character_sheet` 出角色、用户在画布确认，再带着 `character` 执行。
   角色参数落到 `video_work/<project>/character.json`，续跑/微调会自动复用。
1. **旁白先行**（若任一面板有旁白）→ 实测时长 = 骨架；各面板时长随之确定。
2. **画面派工**：逐面板按 `engine` 派给对应部门，**可多引擎混排**。
   - `opendesign` → `opendesign_video`；`manim` → `manim_video`；`cinematic` → `video_cinematic_generate`；
     `styled` → `styled_video`（内部引擎，Remotion 现场作画）；
     `footage` → `footage_video`（用户自备素材，仅在用户点名时）；`amap` → `map_video`（高德真实地图）；
     `webpage` → `webpage_video`（真实网页截图 + 高亮标注）；`blender` → `blender_video`（真 3D 渲染）。
   - **影视级预算**：不再查询 API 额度。默认每支片只用 **1 段** cinematic；用户可在 ask_user 明确要求 **0（不用）/ 2 / 3 段**，通过 `cinematic_count` 传入。设计蓝图时该段数是硬约束（panels 里 cinematic 数量必须相等）；执行时超出预算的 cinematic 段先改用 **3D 渲染**（`blender` 作为 cinematic 的 backup），3D 也失败才降级为 HTML 动画。
   - **降级链**：`styled → opendesign`、`manim → opendesign`、`cinematic → blender → opendesign`、`remotion → opendesign`、`amap → opendesign`、`blender → opendesign`；`footage` 与 `webpage` **不降级**（用户指定的素材/真实网页不能被别的画面冒充），任一段失败不整片崩。
   - 画面引擎只有这八个；蓝图里的 `engine` 必须取其中之一，其余取值一律按 `opendesign` 处理。
     `remotion` 已停用：新蓝图写出它会被校验打回（历史蓝图仍可复跑）。`footage` / `amap` / `webpage` 可用在任意段。
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
  director(project="<同名>", patch='{"music": {"prompt": "轻快科技感电子配乐，无人声", "level": 30}}')
  ```
  画面/旁白/字幕全部按签名复用，**不会重做**；只有配乐是新生成的，合成因 BGM 变化而重烧一次。
- **移除配乐**：`patch='{"music": null}'` → 只重烧合成。
- **音量**：`level` 是百分比(0~100，默认 30)；旁白优先，配乐只做铺底。
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
    `styled` 段额外看 `styleGuide`（全片档案）与 `styleNote`——换画风只重做受影响的段。
  - 每次执行结束会汇报"画面 重做 N / 复用 M 段；旁白 重配 X / 复用 Y 句"，便于判断是不是真·微调。
- `force=true` → 无视签名，整片重来。

## 边界
- 导演**不改流程、不重写渲染**，一切交给部门。
- `styled_video` 是导演组内部引擎，**不直接暴露给用户，也不让用户选风格**（画风由 `styleGuide` 决定）。
- 能力缺口（如实拍）应在设计阶段就告知用户。
- 产物目录：`video_work/<project>/{voice,panels,music,sfx,subtitles,review}/` + 成片 + `director_state.json`。
