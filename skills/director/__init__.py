"""
director skill - 导演组（计划驱动的执行器）

不是写死流程的流水线：流程由"制作蓝图(plan)"决定，本工具只按蓝图**通用地**调度各部门。
  - 首次调用（给 brief）：内部「导演 LLM」产出蓝图（分镜 + 每镜引擎 + 全局风格 + 用不用字幕/审查）
    → 返回 need_confirm，由主 LLM 用 ask_user 与用户确认（不同意就重排重来）。
  - 二次调用（给 plan）：按蓝图执行——先旁白(骨架)，再逐面板派工(单/双/多引擎混排)，字幕，合成，审查。

各步骤通过各部门技能完成（narration / opendesign_video / manim_video /
video_cinematic_generate / footage_video / styled_video / subtitle / compose_video / video_review），
导演不改流程、不重写渲染。
注：水彩技能已下线，其引擎并入 lyric_mv（仅作过场/氛围，不承担主画面）。
    导演当前阵容为 opendesign + manim + cinematic + styled（Remotion 现场作画，
    画风由全片 styleGuide 决定，不设固定风格库）+ blender（3D 机理）+ webpage
    + footage（用户自备 mp4，仅在用户主动提供素材时使用）
    + amap（高德真实地图：真实路线/中国/世界地图；与 styled 的风格化纸图区分）。

进度：本工具在每步 emit 进度（含 第 i/N 段、合成阶段等），并把子部门进度转发到导演名下，
前端即可实时看到"1/10"这类步进，而非盲盒。
"""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

_DESIGN_PROMPT = """你是一位视频总导演。根据用户需求，产出一个「制作蓝图」，只输出 JSON，不要解释或 markdown。

蓝图结构：
{
  "title": "视频标题",
  "style": "整体视觉风格（配色/字体/动效基调）",
  "canvas": {"width": 1920, "height": 1080, "fps": 30},
  "panels": [
    {"engine": "opendesign|manim|cinematic|styled|footage|amap|webpage|blender",
     "narration": "本段旁白文案（可空，空=无声段）",
     "visual": "本段画面需求（自然语言）",
     "hook": {"type": "result|question|wrongway|contrast|ui|object|countdown|map|sound|handwritten|footage",
              "text": "钩子文案（可空）", "why": "为什么能抓人（可选）"},
     "intro": {"title": "从一条路线\\n看懂一座城市", "accent": "一座城市", "sub": "副标（可空）",
               "tag": "SIGMA 科普视频", "side": "right", "seconds": 4},
     "styleGuide": "仅 styled 段可选：覆盖全片风格档案的段落级补充",
     "styleNote": "仅 styled 段可选：本段局部风格要求（更冷/更暗等）",
     "screen_html": "仅 blender 可选：设备屏幕界面的 HTML 文件路径（工具先截图再贴到屏幕）",
     "screen_size": "仅 blender 可选：屏幕贴图像素尺寸，如 2048x1536",
     "prompt": "仅 cinematic 用：英文提示词（可空，缺省用 visual）",
     "video": "仅 footage 必填：用户提供的视频（相对项目目录的路径或绝对路径；mp4/mov/mkv/webm 等，非 mp4 自动转 mp4）",
     "fit": "仅 footage 可选：contain（默认，完整保留并补黑边）| cover（等比裁切铺满）",
     "clip_seconds": "仅 footage 可选：只取素材前 N 秒（默认整段）",
     "keep_audio": "仅 footage 可选：保留素材原声（默认 true；该段有旁白时旁白优先）",
     "map": "仅 amap 必填：真实地图 spec（kind=route|region|world；见下方地图引擎说明）",
     "web": {"url": "用户明确给出的网址（可选）",
             "query": "没有网址时必填：用来搜索真实来源的知识点/主题",
             "focus": "这一段要讲清什么、要标哪类信息（必填）",
             "max_marks": 3},
     "images": "仅 opendesign/styled 可选：这一段是否需要 AI 生成配图，默认 false",
     "embeds": "仅 opendesign 可选：把 blender/manim/amap 作为版面图层嵌入（最多 2 个，非必填；见下方说明）",
     "overlay": {"title": "标题文字", "subtitle": "副标题(可空)", "accent": "#e03131",
                 "position": "upper", "align": "left", "reveal_ratio": 0.5},
     "sfx": [{"at": 0.4, "recipe": "cartoon.pop", "level": 55}],
     "seconds": 10}
  ],
  "subtitles": true,
  "review": true,
  "sfx_density": "normal",
  "sfx_snap": "visual"
}

选引擎（按"这一段到底要让观众看到什么"来定，别惯性全用同一个）：
- manim = **讲解型**：数学/几何图形、公式推导、坐标与函数、原理分步演示（科普讲解的**首选**）。
  用 manim 时，visual 要写清"讲什么、分几步、出现哪些图形/公式、节奏"。工具内部会自动写好动画。
  边界：manim 擅长精确的数学几何表达，**不擅长写实实体建模**（无遮挡剔除）→ 别用它做产品/人物/场景写实画面。
- opendesign = **信息/排版型**：文字标题、要点罗列、图表数据、流程/对比、UI 演示（**通用主力**）。
  可选写 `embeds` 把 blender/manim/amap 当成版面里的一个图层嵌进来（见下方「opendesign 内嵌特效」）。
  **当演示需要与步骤标签、侧栏批注、参数、进度或结论同框时，优先用组合段，不要只给裸特效段。**
- blender = **原理解释型 3D（3D + 文字）**：当一个原理"讲不清是因为看不见结构"时用它——
  空间遮挡、装配关系、机构运动、场的分布与走向、体积与层次、剖切透视。
  输出是「3D 机理画面 + 画面内短标注」：3D 负责让人看懂结构，文字只标部件名/关键量（≤6 字）。
  ✅ 该用：口头或平面图解说不清"谁在谁里面、谁绕着谁转、力/场怎么走、切开来是什么"。
  ❌ 不该用：纯公式推导（manim）、纯概念对比/流程/数据（opendesign）、真实场景氛围（cinematic）。
  段落建议 5~10 秒、2~3 个镜头：开头 0.5 秒先给全貌建立空间感，再推进到关键部位。
  文字规则：3D 里只放部件名/参数，**绝不照抄旁白原句**（字幕由导演组统一加在底部）。
  次要用途：产品外观/设备屏幕内容展示（这时可写 screen_html 让工具把真实界面截成贴图），
  以及**真 3D 开场钩子**（设备/物件/产品外观，配 `"hook": {"type": "object3d", ...}`）。
  渲染比 2D 慢（10 秒要几分钟起），只在「3D 本身就是卖点」时用，全片通常 1 段。
  失败自动降级 opendesign。
- webpage = **真实网页取景型**：在模拟浏览器窗口里 1:1 滚动真实网页，高亮原文，旁边浮现批注（原文摘录 + 解释）。
  它解决的是"**凭什么这么说**"：观众能亲眼看到真实页面上的原始数字或原句，而不是听你转述。

  **一定要用**（满足任意一条，就该认真给它安排一段）：
  - 核心论据是**真实统计/榜单/表格数值**：用户数与增长率、市场份额、排名、价格、时间线、财报数字；
  - 要引用**官方原文**：定义、标准条款、政策原文、公告、报告结论（转述不如直接给观众看）；
  - 内容的可信度来自**权威一手来源**：官网/官方博客、标准文档、百科、论文、机构报告；
  - 用户直接给了网址，或说"看这个网页 / 官网 / 这份报告 / 这组数据"；
  - 讲"谁在用/多少人/分布如何/排名变化"这类**人群、规模、分布**话题。

  **不要用**：
  - 纯抽象概念、纯逻辑推演、公式推导（交给 manim）；纯排版总结、对比清单（交给 opendesign）；
  - 需要虚构/示意画面的段落（交给 styled / cinematic）；
  - 目标页面需要登录、有付费墙、几乎全是视频或图片；
  - 关键信息分散在页面首尾、隔着好几屏（一个视口里讲不连贯）。

  **怎么用**：
  - 有网址 → 写 `web.url`；没有 → 写 `web.query`（用知识点原话去搜，**绝对不要编造 URL**）。
  - `web.focus` 必须写清"要让观众看到哪类证据"（关键数字 / 定义原句 / 结论句）——系统靠它挑原文。
  - `web.max_marks` 默认 3、最多 4：只标最能支撑论点的 2~3 处，**尽量落在同一屏或同一张表里**。
  - 一段一个页面；讲多个页面就拆多段。
  - `web.source` / `web.marks`（来源、原文、坐标）由系统抓取后自动回填，**你不要自己写坐标或臆造原文**。
  - 和其它引擎分工：webpage 给证据，manim 讲原理，opendesign 做总结与对比。

  **密度**：一支片子里通常 1~2 段 webpage 最合适（证据段）。全片都用会显得单调，
  所以只在"这段真的需要出示证据"时才选它。
- cinematic = **实拍感/氛围型**：真实场景空镜、情绪镜头、开场钩子的视觉冲击（纯英文提示词生成）；
  单段只能 6 或 10 秒；**整片 cinematic 段数必须严格等于下方「制作预算」给出的段数**（默认 1，0=完全不用）。
  ⚠️ 画面是**固定长度**（6/10 秒），所以该段旁白**必须不超过画面时长（宁短勿长，约 ≤ 10 秒 / 45 字）**；
  旁白一旦长于画面，成片结尾会**卡在最后一帧**（看起来像视频卡住）——opendesign/manim 定格一帧无妨，cinematic 不行。
- styled = **叙事/插画型**：讲故事、情绪、隐喻、人物关系、需要一个完整统一画风的段落。
  它没有固定风格可选：你按用户需求写一份**全片风格档案** `styleGuide`（见下），
  这一段按档案现场作画（Remotion，无歌词，**仅 2D**）。适合"这一段要让观众看到一段有画风的戏"。
- ~~remotion~~ = **已停用，不要选**：它只会做标题/动态字，撑不起开场钩子。
  开场钩子改用 cinematic / blender / styled / manim / amap / opendesign（按内容选，见下方钩子规则）。
- footage = **用户自备素材型**：把用户自己放在项目文件夹里的视频（如 10 秒 mp4）直接用成一段。
  **只有在用户明确说自己提供了素材、并指定了用途（开场或某一段）时才可用**；
  必须把真实文件名写进 `video`，不得臆造路径。素材原长就是该段长度（可用 `clip_seconds` 截取），
  需要标题就写 `overlay`。用户没提素材时**绝对不要选 footage**。
- amap = **真实地图型**：真实中国/世界行政区、真实驾车/步行/骑行路线、地点标注、行程演示。
  用户需求涉及**真实地点、行程、路线、中国地图、世界地图**时优先用它；必须写 `map` 对象（见下）。
  它和 styled 的"风格化纸地图"不同：那种只是像地图的插画，不保证真实地理；
  真实行程/地点用 amap，只有要“像地图的图形/纸图质感”时才用 styled 的 map 风格。
选择准则：有公式/几何/原理推导/函数图像 → manim；纯信息与文字排版 → opendesign；
**"看不见的结构"讲不清（遮挡/装配/机构运动/场/剖切）→ blender**；要实拍感/氛围 → cinematic；
**讲故事/要画风 → styled；开场钩子按内容选 cinematic / blender / styled / manim / amap / opendesign**；
**3D 设备/物件/产品外观开场 → blender（或 opendesign 的 three.js）**；
**真实地点/行程/路线/中国或世界地图 → amap**；**用户主动提供了视频素材 → footage（只用于用户点名的那一段/开场）**；
**要出示真实证据（数据、榜单、官方原文、报告结论）→ webpage**。
一段若"既讲原理又给信息"，按该段主要意图择一；**不要把每段都写成 manim，只在真正"讲道理"的段落用它**。
**也不要整片都用 opendesign 把数据重画一遍**：凡是"数字/原文本身就有说服力"的地方，
优先用 webpage 把真实页面端出来，opendesign 负责它前后的总结与对比。

### opendesign 内嵌特效（有协同价值就优先用，不是必填）

opendesign 段可以写 `embeds`，把 blender / manim / amap 特效作为**版面里的一个图层**嵌进去，
而不是另起一段整屏硬切。它不是"额外装饰"，而是让**演示画面与解释文字同框**的常用构图手段。

例如（Manim 理论演示 + 审讯档案式批注）：
```json
{"engine": "opendesign",
 "visual": "左侧约 70% 是理论演示，右侧固定档案栏显示理论编号、短标签与结论；三项理论切换时右侧同步更新",
 "embeds": [{"type": "manim", "brief": "依次演示广播网络、二阶表征与整合网络，图形保持清晰",
             "rect": [70, 180, 1230, 690], "start": 0.0, "duration": 24.0}]}
```

使用规则：
- **有下面任一协同价值，就优先组合成 `opendesign + embeds`，不要惯性拆成纯特效独立段**：
  - Manim 演示需要持续的章节标签、步骤进度、对比文字、结论或批注；
  - 3D 设备/结构旁边需要参数、部件清单、操作提示或产品文案；
  - 地图路线需要行程信息、地点卡片、时间/距离或阶段说明。
- **内嵌不等于缩成小窗**：特效可以占 60%~80% 的主视觉区，opendesign 只负责边缘标题、侧栏、进度与批注；统一风格由版面保证。
- 纯标题、纯文字、纯静态图表、明确不需要解释层的段落仍可保持干净；不强制每段都有 embeds。
- 全片通常 1~3 段带 embeds，每段最多 2 个；**多个连续理论/公式/流程演示，优先考虑合并为一个 opendesign 段 + 一个覆盖全程的 Manim embed**，而不是连续多个裸 Manim 段。
- 特效本身就是唯一叙事主体、完全不需要持续文字协同，才保留单独 `engine: blender / manim / amap` 段；内嵌不是替代整屏特效。
- `rect` 用画布像素 `[x, y, w, h]`；`start` 相对本段开始；`duration` ≥1.5s，且 `start+duration ≤ 本段 seconds`。
- `brief/visual` 只描述特效画面，不要写文字排版；amap 用 `map` 对象。
- 系统会把这段显示成「HTML动画 + 3D渲染 / Manim讲解 / 高德地图」，用户能直接看懂它嵌了什么。

### 地图引擎 amap 的 `map` 对象

```json
{
  "kind": "route | region | world | flight",
  "title": "地图上的标题", "subtitle": "副标题（route/flight 可留空，自动填距离）",
  "kicker": "顶部小标签（可空）",
  "theme": "dark | light",
  "city": "北京",
  "list": true,
  "markers": [{"name": "北京", "sub": "BEIJING", "coord": [116.4074, 39.9042], "side": "left-up"}],
  "route": {"origin": "三里屯", "destination": "国贸", "mode": "driving",
            "origin_name": "起点显示名", "destination_name": "终点显示名"},
  "flight": {"from": "上海", "to": "大连", "arc": 0.16},
  "region": {"soc": "CHN", "name": "北京市", "adcode": "110000", "depth": 1,
             "bounds": [[73.5,3.8],[135.1,53.6]], "highlight": ["北京市", "上海市"]},
  "world": {"highlight": ["CHN", "USA", "JPN"], "center": [0, 20]}
}
```

- `route`：两地点真实路线；`origin`/`destination` 可以是中文地名或 `[经度,纬度]`。
  **必须写 `city`（如 "北京"）**，否则同名地点（三里屯/国贸）会解析到别的城市。
- `flight`：两地飞行航线示意；`from`/`to` 写城市名或坐标，`arc` 可选（默认 0.16，弧线弯曲程度）。
  画面是真实城市位置 + 弧线 + 飞机图标 + 已飞轨迹 + 直线距离；
  这是“航线示意”，不是真实航班轨迹，副标题会自动带“航线示意”。
- `region`：中国/省级行政区；`soc` 默认 `CHN`，`depth=1` 省级；
  `highlight` 写行政区名或 adcode。中国默认完整版图；单省可写 `name`（如“北京市”）或 `bounds`（省级视图）。
  城市街道级/具体行程不要用 region，改用 `route`。
- `world`：世界国家；`highlight` 写 `SOC`（CHN/USA/JPN…）或中文国名；
  默认以 0° 经线居中、zoom 3（适合 1920×1080），不要自己改 center 除非确有必要。
- `markers`：要标注的城市点；没有坐标时写 `name`，引擎会地理编码（有 `city` 更准）；
  世界地图的境外城市最好直接写 `coord`，避免中文地名解析不到。
- 只写真实存在的地点，**不要编造坐标**；不确定坐标就写地名 + `city`。
- 地图标题/副标题写在 `map` 里，不要用 `overlay`。

### 网页取景段 webpage 的 `web` 对象

```json
{
  "url": "用户明确给出的网址（可选；没给就不要写）",
  "query": "没有网址时必填：用知识点/主题原话去搜真实来源",
  "focus": "这一段要讲清什么，重点标哪类信息（关键数据 / 定义 / 结论句）",
  "max_marks": 3
}
```

- **url 与 query 至少一个**：用户给了网址就写 `url`；没给就写 `query`，**绝对不要自己编造 URL**。
- `focus` 必填，写清"讲什么"和"标哪类信息"；这是系统挑原文的依据。
- `max_marks` 默认 3，最多 4；知识点密度要克制，优先关键数字与结论，不要满屏标。
- 系统会在设计阶段自动：找真实来源 → 抓取页面 → 选出可逐字标注的原文 → 算出坐标，
  并把 `web.source`（来源标题/网址/理由）与 `web.marks`（原文 + 坐标）回填进蓝图。
  你**不要**自己写 `source` / `marks` / 坐标，也不要臆造页面原文。
- 设计完成时，每个 webpage 段都必须带 `web.source` 与至少 1 条 `web.marks`；为空就代表取景失败，
  不能把它当成"已完成"，必须改 query/focus 或改用别的引擎。
- 一个网址/页面一段；要讲多个页面就拆成多段。

### styled 段的风格档案（styleGuide）

styled 没有固定风格可选。凡是蓝图里有 styled 段，就在**顶层**写一份 `styleGuide`，
它决定全片所有 styled 段的画风；各段还可以用 `styleNote` 做局部微调。

`styleGuide` 写成一段可直接照做的规格（字符串），至少覆盖：
配色（主色/辅色/明度关系）｜线条（有无描边、粗细、抖动）｜质感（颗粒/纸纹/平涂/渐变）｜
光（光源方向、明暗层次）｜构图（主体占比、留白、景深）｜运动（镜头怎么动、节奏）｜
文字（能不能出现字、字体气质、对比度）｜禁止项（明确不要出现什么）。

**风格由你按用户需求与这一段的内容/时代来定，不要向用户询问，也不要把风格选择推给用户。**
- 用户点名了画风（如"水墨""像素""蜡笔绘本"）→ 就照用户的原话写进 `styleGuide`，不要改写成别的。
- 用户没提 → 按内容与时代自己定，并在 `styleGuide` 里写清楚，保证各段一致。
- 片中有固定人物/物品且需要跨段一致时，先用 `character_sheet` 定妆并让用户确认；
  需要给物品也做定妆时同样走这一轮。其余情况不必每次都定妆。

### 开场钩子 + 标题入场（前 1~2 段）

开场不是封面/logo/空镜。**前 1~2 段是钩子**：第 1 段必须写 hook；如果钩子需要两个节拍，
第 2 段也可以写 hook（继续同一个钩子，不要在第 2 段就进入正片）。第 3 段起不能再写 hook。
`"hook": {"type": "result", "text": "屏幕上出现的钩子文案（可空）", "why": "为什么能抓人（可选）"}`
hook.type 从下面选一个：
{HOOK_MENU}

**钩子之后、正片之前，最后一段钩子上要写 `intro`（标题入场）**：
`"intro": {"title": "从一条路线\\n看懂一座城市", "accent": "一座城市", "sub": "距离、时间与路径，都是理解城市的一手证据。", "tag": "SIGMA 科普视频", "side": "right", "seconds": 4}`

- 作用：把钩子的全屏画面**连续缩小**到 `side` 指定的一侧（left/right），另一侧出现本次视频的大标题、副标和 Sigma 标签；这是从「钩子」进入「正片」的固定品牌转场。
- `title` 必填，1~2 行，每行尽量 ≤8 字；执行层按最长一行自动定字号（最大 104px），**不要写长句**。
- `accent` 可选：标题里要强调的词（会变成品牌绿）；不写就整行白色。
- `sub` 可选，一句话；`tag` 默认 `SIGMA 科普视频`。
- `side` 是**钩子画面缩到哪一侧**；标题放在另一侧。默认 `right`（画面在右、标题在左）。
- `seconds` 2.5~5.5，默认 4；这段**没有旁白**，是纯画面转场。
- **钩子不要在结尾淡出到黑/白**：intro 会接住钩子的最后一帧来缩小，结尾必须是可读画面。
- 全片只能有一个 intro，且必须写在**最后一段钩子**上；intro 之后才是正片第 1 段。
- **写了 intro 的钩子段不要再写 `overlay`**：两者都会上大标题，会打架。
- 不写 intro 也可以：钩子结束后直接进正片（老流程）。但如果你用了 2 段钩子，建议写 intro，让观众知道正片开始。

钩子规则：
1. 第一段画面**至少 10 秒**，只传达 1 个信息点；不要压成三五秒敷衍。
   例外：cinematic（固定 6/10 秒）、footage（素材原长）。
   旁白可以**短于 10 秒**（建议仍简短有力，不要为凑满 10 秒硬写）；旁白结束后剩余画面留白
   （不加旁白、不加新内容），intro/第二段从画面结束后开始，**旁白与字幕时间轴不得被挤动**。
   非 cinematic/footage 的第一段，蓝图 `seconds` 要写 ≥10（写小了执行层也会抬到 10 秒）。
   **如果拆成 2 段钩子**：两段合计 ≥10 秒、单段 ≥4 秒；执行层不会再把第一段单独抬到 10 秒。
2. 第一句旁白直接给结果/问题/冲突；禁止“大家好 / 今天我们来聊聊 / 本期视频”。
3. **钩子引擎按内容选，不要默认 remotion——它已停用**（只会做标题/动态字，撑不起开场钩子）：
   实拍感/人物/真实场景 → cinematic（预算允许时）；
   **3D 设备/物件/产品外观/结构 → blender + hook.type=object3d**（轻量 3D 可用 opendesign 的 three.js）；
   版式/数字/对比/假 UI/动态字 → styled 或 opendesign；公式/推导/原理 → manim；
   真实地点/行程/路线 → amap；真实网页/数据 → webpage；用户自备素材 → footage。
   以上都是**按内容按需选择，不是硬约束**；唯一硬规则：**任何分镜都不能写 remotion**。
4. 钩子必须和正片内容真实相关，不要标题党。
5. **钩子段的旁白只覆盖钩子画面**：intro 是静音转场，不要把旁白写到 intro 上。

硬性规则：
- 旁白是骨架：各面板时长由旁白实际读速决定，**不要预先定死总时长**。
- 面板 3~10 个；旁白口语化、前 3 秒有钩子；风格统一。
- **cinematic 段数**：panels 里 engine="cinematic" 的数量必须**恰好等于**「制作预算」给出的段数；
  默认 1 段，0 表示完全不用 cinematic。不要多也不要少。
- **hook 只允许前 1~2 段**：第 1 段必须写，第 2 段可选（继续钩子），第 3 段起禁止；
  hook.type 必须是上方类型之一，没有第 1 段 hook 的蓝图会被打回。
- **intro 只能有一个，且必须写在最后一段钩子上**：它是静音的品牌转场（画面缩小 + 大标题 + Sigma 标签），
  不要把旁白或正片内容写进 intro；intro 之后的第 1 段才是正片开始。
- **任何分镜都不要写 remotion**（该引擎已停用）：开场钩子按内容选
  cinematic / blender / styled / manim / amap / opendesign / webpage。
- 所有画面底部预留字幕安全区（字幕由字幕组后期叠加）。
- **画幅默认横版**：`canvas` 写 `{"width": 1920, "height": 1080, "fps": 30}`，不要因为题材
  （科普、新闻、健康）就自己改成竖屏。只有用户在需求里**明确**说竖屏 / 抖音 / 小红书 / 9:16 时，
  才写 `{"width": 1080, "height": 1920}`；brief 里没提画幅就一律横版。
- **配图默认不开（只有 opendesign / styled 段可选）**：默认**不配图**，画面全用图形/排版/动画完成。
  只有这一段确实需要"照片感、氛围底图、具体物件或人物的插画"时，才在这个面板里写 `"images": true`。
  - 适合开：品牌氛围、情绪空镜、需要真实质感的场景、画面主体是具体物件或人物。
  - 不要开：战术/流程/结构/数据/文字排版的示意画面 —— 这类用矢量图形画更准，配图反而干扰。
  - 开了以后图片必须参与动效（引擎会强制要求），所以只在"图本身就是画面主体"的段落开。
- **人物按风格定分寸（影响成片质感）**：styled 段的人物是代码逐帧画的，面部与手部精细度有限。
  风格库里每条都写了「人物」这一项 —— 剪影类（皮影 / 水墨 / 比例尺）可以用人物当叙事主体；
  扁平 MG、漫画、白板这类有五官的，尽量少用、只做小比例配角；图表类（信息图 / 地图 / 拆解）基本不用。
  写 `visual` 时**按你选的这条风格的分寸来安排**：优先物件、场景、光影、构图与动作暗示；
  需要人时写中远景、侧身/背影/剪影，不要安排正面特写和多人同框。
  注意：**不是一律不用人物** —— 该有人的段落硬删会丢掉叙事和情绪，只是别让镜头怼到脸上。

可选的「背景音乐」（music，由音乐组生成，会循环铺满全片并与旁白混音，旁白优先）：
- **默认不配乐**：蓝图**不要写 music 字段**。成片交付后用户若想要配乐，可再单独追加一条 `music` 补丁重烧，
  那时只重做配乐与合成，**已生成的画面/旁白/字幕全部复用**，不会重做。
- **仅当用户在需求里明确要求配乐/BGM/背景音乐/主题曲时**才写，字段：`{"prompt": "风格/情绪/乐器描述", "level": 30}`
  （`level` 是音量百分比 0~100，默认 30）。
- 若「配乐能力」事实为"未配置"，**任何情况下都不要写 music 字段**。
- prompt 只写**风格 + 情绪 + 具体乐器 + 节奏**，例如
  「科技感与推进力，合成器铺底，弦乐主旋律，鼓组打四四拍，90BPM」。
  - **不要写「无人声 / 纯音乐 / 不抢人声」**：音乐模型对否定句不敏感，这类词重复出现反而会被当成素材线索。
    纯器乐由工具统一加器乐外壳（正面声明 + 具体编曲 + 排除项）来保证，不靠这里写。
  - **不要写歌词**，也不要写「主题曲 / 歌曲 / 演唱 / 合唱」这类词——会把模型往歌曲形态带。
  - 宁可把乐器写具体，也不要写空泛的「史诗感 / 大气」。

可选的「音效」（sfx，由音效组程序合成，**不需要 Key**）：
- **默认不写**；只有画面里有明确的动作点、强调点或转场点时，才在该面板写 sfx。
  但成片较长时不要过于保守：按下面的密度目标分配到各段，**不要整片只有 1 个**。
- 全片密度由顶层 `sfx_density` 控制：`light`（1~2 个/分钟）/ `normal`（3~6，默认）/
  `rich`（6~10）/ `none`。2 分钟视频 normal 约 6~12 个；每段最多 3 个，不要每段都加。
- 执行层会按密度上限、单段上限（短段 1 个、长段最多 3 个）和 2 秒最小间隔自动裁剪；
  重要事件写 `priority` 70~90，点缀写 40~60，超限时优先保留高优先级。
- **`at` 是“预计的画面动作时刻”，不是旁白断句时间**：执行层会对成片做视觉节拍检测，
  在 `sfx_snap_window`（默认 ±1.5 秒）内把音效吸附到最近的一次明显画面变化
  （元素入场 / 镜头切换 / 动画起点）。请把 `at` 写在你预期的画面上，不要跟着旁白走。
- `sfx_snap`：`visual`（默认，吸附画面节拍）/ `none`（保留原时间）。
  单条音效如果想严格卡点，可写 `"snap": false`。
- 每个事件：`{"at": 秒(相对本段开头), "recipe": "目录里的 id", "level": 60, "priority": 60, "params": {...可选}}`
  - `at` 是面板内相对时间，不是全片绝对时间；导演会换算到成片时间轴，并吸附到画面节拍。
  - `level` 是音量百分比 0~100，默认 60；旁白优先，音效不要盖住人声。
  - `params` 可选：`{"pitch": -2, "brightness": 0.2, "seed": 7}`。
- **选 recipe 按该段的画面风格家族**：mg / cartoon / paper / pixel / tech / cinematic，
  与这一段 `styleGuide` 里写的画风对齐（如绘本/蜡笔→cartoon、像素→pixel、纸质→paper、扁平 MG→mg）。
- 不要在旁白连续说话时堆音效；优先放在段首、转场、关键词落点。
- 音效目录（**只能从这里选 id**）：
{SFX_MENU}

可选的「标题/蒙版包装」（overlay，**仅 cinematic / footage 可用**，由你按题材判断是否采用，不强加）：
- 作用：底片**前半段保留原画**，后半段（默认 50% 起）**渐显全屏蒙版 + 封面式大标题入场**（标题逐行淡入上移、
  强调色分割线扫出、副标题错峰淡入），让空镜/素材更饱满、更有设计感。
- **只对 cinematic / footage 生效**：opendesign / manim 本身就要承载标题与图文排版，再叠蒙版会遮挡正文——所以这些引擎**不要写 overlay**（写了也会被忽略）。
- **最适用**：① 开场钩子——cinematic 空镜 / 用户素材 + overlay 大标题做"引导过渡"，再进正片；
  ② cinematic 空镜或 footage 素材偏单调时；③ 章节/主题切换处。
- overlay 的 title 要短（1~2 行）、subtitle 可选（一行）；`reveal_ratio` 控制标题出现的时间点（默认 0.5）、
  `align` 控制左对齐/居中（默认 left）、`position` 控制纵向落点（默认 upper，即左上偏中，避开底部字幕）；
  不需要就**整段不写 overlay**（不要每段都加，避免喧宾夺主）。
"""

_ENGINE_TOOL = {
    "opendesign": "opendesign_video",
    "webpage": "webpage_video",
    "cinematic": "video_cinematic_generate",
    "manim": "manim_video",
    "styled": "styled_video",
    "remotion": "remotion_hook_generate",
    "footage": "footage_video",
    "amap": "map_video",
    "blender": "blender_video",
}
_ENGINE_LABEL = {"opendesign": "HTML动画", "webpage": "网页取景", "cinematic": "影视级",
                 "manim": "Manim讲解", "styled": "风格动画", "remotion": "Remotion钩子",
                 "footage": "用户素材", "amap": "高德地图", "blender": "3D渲染"}

# opendesign 可以内嵌的特效引擎：把外部片段转成帧雪碧图，作为版面里的一个图层。
# 不强制每个 opendesign 都写 embeds：纯文字/数据段保持干净；只在"特效必须和版面同框"时用。
_EMBED_TYPES = {"blender", "manim", "amap"}
_EMBED_MAX_PER_PANEL = 2
_EMBED_MAX_PANELS = 3
_EMBED_SHEET_REV = 1   # 雪碧图转换算法有实质变更时递增，旧 embed 缓存自动失效


def _panel_embeds(p) -> list[dict]:
    raw = p.get("embeds") if isinstance(p, dict) else None
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def _panel_engine_label(p, engine: str) -> str:
    """蓝图/进度里显示的引擎名：opendesign 内嵌特效时显示成「HTML动画 + 3D渲染」。"""
    base = _ENGINE_LABEL.get(engine, engine)
    if str(engine).lower() != "opendesign":
        return base
    labels = [_ENGINE_LABEL.get(str(e.get("type") or "").lower(), str(e.get("type") or ""))
              for e in _panel_embeds(p)]
    labels = [x for x in labels if x]
    return base + (" + " + " + ".join(labels) if labels else "")

# 「蒙版+标题」包装(overlay) 只用于**不自带排版**的引擎（如实拍感的 cinematic、用户自备素材）；
# opendesign / manim 自身就是排版/讲解型，叠加蒙版会挡住正文，故不适用。
_OVERLAY_ENGINES = {"cinematic", "footage"}

# 影视级预算：每支片默认只用 1 段 cinematic；用户可在 ask_user 明确改为 0 / 2 / 3。
_CINEMATIC_DEFAULT = 1
_CINEMATIC_MAX = 3

# 开场钩子类型：第一段必须选一个，避免没有 cinematic 时用空镜/慢推开场。
# engine 只是"按内容推荐"，不是硬约束；唯一硬规则是 remotion 已停用、不能出现在任何分镜。
_HOOK_TYPES = {
    "result": {"label": "结果前置/数字冲击", "desc": "先给最终结果或反差数字，再倒回讲过程", "engine": "styled / opendesign"},
    "question": {"label": "反常识提问", "desc": "用一句反常识问题开场，停半拍再给答案", "engine": "styled / opendesign"},
    "wrongway": {"label": "错误示范/痛点现场", "desc": "先演常见错误或痛点，再给解法", "engine": "styled / opendesign"},
    "contrast": {"label": "前后对比", "desc": "左右/上下分屏对比 before/after 或你以为/实际", "engine": "styled / opendesign"},
    "ui": {"label": "熟悉 UI/POV", "desc": "假手机屏、聊天、搜索框、后台等熟悉界面", "engine": "opendesign / styled"},
    "object": {"label": "物件特写", "desc": "关键物件近景 + 慢推/音效，替代 cinematic 近景", "engine": "styled / cinematic（有预算时）"},
    "object3d": {"label": "3D 设备/物件开场", "desc": "真 3D 设备或关键物件开场：绕机、推近、翻转，直接建立空间与质感",
                 "engine": "blender（真 3D）/ opendesign（three.js）"},
    "countdown": {"label": "倒计时/进度", "desc": "倒计时、进度条、天数，先给紧迫感", "engine": "opendesign / styled"},
    "map": {"label": "地图路线", "desc": "真实路线/地点开场，配时间/距离数字", "engine": "amap（真实路线）/ styled（风格化纸图）"},
    "sound": {"label": "声音先导", "desc": "黑屏先响一声提示音/闹钟/盖章，再出画面", "engine": "styled / opendesign + sfx"},
    "handwritten": {"label": "手写便签", "desc": "便签/清单/日记逐字出现，划掉关键项", "engine": "styled / opendesign"},
    "footage": {"label": "用户素材开场", "desc": "用户自备的视频直接用开场（仅在用户主动提供素材时）", "engine": "footage"},
}

# Remotion 模板只覆盖 title / kinetic / ui 三种；按 hook.type 选模板，不按文案内容做关键词匹配。
# 注：remotion 已从蓝图停用（仍在执行层保留，供历史蓝图复跑），新蓝图不要再产生这类段。
_REMOTION_TEMPLATE_BY_HOOK = {
    "result": "kinetic",
    "countdown": "kinetic",
    "question": "title",
    "sound": "title",
    "object": "title",
    "handwritten": "title",
    "ui": "ui",
    "wrongway": "ui",
    "contrast": "ui",
    "map": "ui",
}


def _hook_menu() -> str:
    return "\n".join(
        f"- {k}（{v['label']}）：{v['desc']}；建议 {v['engine']}"
        for k, v in _HOOK_TYPES.items()
    )

# 合成逻辑修订号：compose_video 的合成实现有实质变更时递增——使旧成片缓存失效，
# 只重烧合成（画面/旁白/字幕照常命中缓存复用，不重做）。
_COMPOSE_REV = 5

# 引擎渲染逻辑修订号：引擎的渲染实现有实质变更时递增，使旧分镜缓存失效、只重渲该引擎的段。
# manim：竖屏 frame 修复后，旧的 1080×1920 分镜必须重渲，否则会复用大字比例错误的成片。
# amap：地图就绪竞态与地理编码修复后，旧的“地图段降级产物”必须重渲，否则会继续复用 HTML 片段。
_ENGINE_REV = {"manim": 1, "amap": 1, "webpage": 2}

# 音效密度：每分钟事件数区间（light / normal / rich）；none=关闭。
# 目标区间在旁白实测时长确定后计算，执行层按区间做上限裁剪与最小间隔过滤。
_SFX_DENSITY = {
    "none": (0.0, 0.0),
    "light": (1.0, 2.0),
    "normal": (3.0, 6.0),
    "rich": (6.0, 10.0),
}
_SFX_DENSITY_LABEL = {"none": "关闭", "light": "轻", "normal": "标准", "rich": "丰富"}
_SFX_GLOBAL_CAP = 40      # 全片硬上限，防止长片无限堆
_SFX_MIN_GAP = 2.0        # 两个音效的最小间隔（秒）
_SFX_PER_PANEL_CAP = 3    # 单段硬上限（执行层会再按段长收紧）
_SFX_SNAP_WINDOW = 1.5    # 音效吸附到画面节拍的最大窗口（秒）

# 用户自备素材的候选扩展名：只用于向蓝图设计如实列出"项目目录里有哪些视频"，
# 不参与任何自动挑选（用不用素材由用户明确提出、由设计 LLM 写进蓝图）。
# 非 mp4 容器由 footage_video 统一转成 mp4，所以这里要覆盖常见视频格式。
_SOURCE_VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".wmv",
    ".mpg", ".mpeg", ".ts", ".mts", ".m2ts", ".3gp", ".rmvb", ".ogv", ".vob",
}

# 开场钩子的最低画面时长：除 cinematic（固定 6/10 秒）与 footage（素材原长）外，
# 第一段画面必须至少 10 秒——旁白可以更短，剩余画面留白（不配音、不加字幕），
# 但绝不允许把开场压成三五秒敷衍过去，也不影响第二段的旁白/字幕时间轴。
_HOOK_MIN_SECONDS = 10.0


def _probe_dur(path) -> float:
    """探测媒体实际时长（秒）；失败返回 0。"""
    try:
        from skills.compose_video.scripts.renderer import probe_duration
        return float(probe_duration(str(path)) or 0.0)
    except Exception:
        return 0.0


def _apply_hook_min_duration(plan: dict) -> None:
    """把首段（非 cinematic/footage）的 `seconds` 抬到至少 10 秒。

    只改蓝图的展示/兜底时长，不替引擎决定实际时长；旁白更短时由执行层留白。
    """
    panels = (plan or {}).get("panels") or []
    if not panels or not isinstance(panels[0], dict):
        return
    if str(panels[0].get("engine", "")).lower() in ("cinematic", "footage"):
        return
    # 两段钩子按"合计 ≥10 秒"控制，不把第一段单独抬到 10 秒，否则第二段就白拆了
    if len(panels) > 1 and isinstance(panels[1].get("hook"), dict):
        return
    try:
        cur = float(panels[0].get("seconds") or 0)
    except (TypeError, ValueError):
        cur = 0
    if cur < _HOOK_MIN_SECONDS:
        panels[0]["seconds"] = _HOOK_MIN_SECONDS


def _style_guide(plan: dict) -> str:
    """全片风格档案：所有 styled 段共用，解决逐段各自成风的问题。"""
    raw = (plan or {}).get("styleGuide")
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False, indent=2)
    return str(raw or "").strip()


def _style_note(p: dict) -> str:
    return str((p or {}).get("styleNote") or "").strip()


class DirectorTool(BaseTool):
    name = "director"
    description = (
        "导演组：先产出制作蓝图（分镜+每镜引擎+风格）交用户确认，确认后按蓝图调度各部门完成成片。"
        "流程由蓝图决定（不写死）：旁白先定骨架，画面可单/双/多引擎混排，再字幕、配乐、音效、合成、审查。"
        "蓝图支持 music（BGM）与 sfx（音效组配方事件，按面板内相对时间）。"
        "首次调用返回 need_confirm 的蓝图；确认后带 plan 再调一次执行。"
        "cinematic 默认每支片只用 1 段；用户明确要求 0/2/3 段时才改 cinematic_count。"
        "第一段必须先定开场钩子（hook），引擎按内容选 cinematic / blender / styled / manim / amap / opendesign / webpage；"
        "remotion 已停用（只会做标题，撑不起钩子），任何分镜都不要写它。"
        "第一段画面至少 10 秒（cinematic / footage 除外），旁白可以更短、剩余画面留白，"
        "第二段旁白与字幕仍从第一段画面结束后开始。"
        "用户主动提供本地视频素材（如 10 秒 mp4）时，可用 footage 引擎把它直接用于开场或指定段，"
        "并可用 overlay 加标题；素材缺失会如实失败，不会用别的画面冒充。"
        "真实地点/行程/路线/中国或世界地图用 amap 引擎（高德真实地图，需要在面板写 map 对象），"
        "它和 styled 的「风格化纸图」是两回事：真实地理必须用 amap。"
    )
    parameters = [
        ToolParameter("brief", "string", "用户需求（首次设计蓝图时用）", required=False),
        ToolParameter("plan", "string", "已确认的制作蓝图 JSON（二次执行时传入；传入即开始制作）", required=False),
        ToolParameter("output_path", "string", "最终输出 mp4 路径（执行时需要）", required=False),
        ToolParameter("project", "string", "项目名，产物放 video_work/<project>/", required=False),
        ToolParameter("character", "string",
                      "已确认的定妆参数路径（video_work/<project>/character.json）。"
                      "蓝图里有人物时，先用 character_sheet 让用户在画布上确认，再把路径传进来。",
                      required=False),
        ToolParameter("speaker", "string", "旁白音色ID；留空用 Settings 配置", required=False),
        ToolParameter("speech_rate", "integer", "旁白语速 -50~100", required=False, default=0),
        ToolParameter("cinematic_count", "integer",
                      "整片 cinematic 段数：默认 1；0=完全不用；用户明确要求时才传 2 或 3（最多 3）。"
                      "首次设计前若用户没说，先用 ask_user 问清再传本参数。",
                      required=False, default=1),
        ToolParameter("force", "boolean",
                      "是否抛弃断点重头制作，默认 false。**微调 / 只重做某段请用 patch，不要用 force=true**——"
                      "force 会让整片重来。", required=False, default=False),
        ToolParameter("patch", "string", "微调（手术式重做）：对已有蓝图做最小修改后重跑，只重做受影响部分。"
                      "**微调请用本参数，不要重发整份 plan**（重发整份 plan 会因措辞/时长微差导致全片重渲）。"
                      "微调/续做会沿用项目已确定的音色与语速（漏传 speaker/speech_rate 不会导致旁白重配）。"
                      "JSON，如 {\"panels\":{\"3\":{\"engine\":\"cinematic\",\"visual\":\"...\"},\"5\":{\"narration\":\"...\"}},\"style\":\"...\"}"
                      "（panels 的键是第几段，从 1 开始）。"
                      "**patch 模式下会自动忽略 force=true，只重做受影响段**，不要同时传 force。"
                      "**追加/改配乐**（成片满意后单独补一条 BGM，画面/旁白/字幕全部复用、只重做配乐与合成）："
                      "{\"music\":{\"prompt\":\"轻快科技感电子配乐，无人声\",\"level\":30}}；移除配乐：{\"music\":null}", required=False),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None, llm_config: dict = None,
                 default_speaker: str = "",
                 minimax_video_api_key: str = "", **kwargs):
        super().__init__(cwd)
        self.skill_manager = skill_manager
        self.llm_config = llm_config or {}
        self.default_speaker = (default_speaker or "").strip()
        # 视频 Key 由 video_cinematic skill 使用；导演侧不再查询额度。

    # ─── 影视级预算（本地规则，不查 API） ───
    @staticmethod
    def _cine_count(value=None, default: int = _CINEMATIC_DEFAULT) -> int:
        """把 cinematic_count 归一化到 0~3；缺省用 default。"""
        try:
            n = int(value) if value is not None else int(default)
        except (TypeError, ValueError):
            n = _CINEMATIC_DEFAULT
        return max(0, min(_CINEMATIC_MAX, n))

    @staticmethod
    def _count_cinematic(plan: dict) -> int:
        return sum(1 for p in (plan.get("panels") or [])
                   if isinstance(p, dict) and str(p.get("engine", "")).lower() == "cinematic")

    @staticmethod
    def _cine_budget_text(n: int) -> str:
        if n <= 0:
            return "影视级 cinematic：0 段（本片不使用 cinematic）"
        return (f"影视级 cinematic：{n} 段（每段 6 或 10 秒；硬预算，"
                f"panels 里 cinematic 数量必须等于 {n}）")

    # ─── 入口 ───
    def execute(self, brief: str = None, plan=None, output_path: str = None,
                project: str = None, speaker: str = None, speech_rate: int = 0,
                cinematic_count: int = None, character: str = None,
                force: bool = False, patch=None, **kwargs) -> ToolResult:
        if not self.skill_manager:
            return ToolResult.fail("director 需要 skill_manager 上下文")
        proj = project or "director"
        base = Path(self.cwd) / "video_work" / proj
        state_path = base / "director_state.json"

        # 微调：对已有蓝图打补丁 → 逐项签名决定只重做哪几处
        if patch:
            patch = self._parse_patch(patch)
            if not patch:
                return ToolResult.fail("patch 解析失败（需为 JSON 对象）")
            state = self._load_state(state_path)
            base_plan = state.get("plan")
            if not base_plan:
                return ToolResult.fail("没有可微调的蓝图：请先用 brief 设计或 plan 执行过一次。")
            new_plan = self._apply_patch(base_plan, patch)
            # 补丁改了网页取景的来源/讲法：清掉旧坐标并重新取景，避免沿用过期截图
            changed_web: list[dict] = []
            old_panels = base_plan.get("panels") or []
            for j, np in enumerate(new_plan.get("panels") or []):
                if str(np.get("engine", "")).lower() != "webpage":
                    continue
                bw = (old_panels[j].get("web") if j < len(old_panels) else {}) or {}
                nw = np.get("web") or {}
                if any(bw.get(k) != nw.get(k) for k in ("url", "query", "focus", "max_marks")):
                    for key in ("capture_id", "capture_dir", "source", "page", "overview", "marks"):
                        nw.pop(key, None)
                    np["web"] = nw
                    changed_web.append(nw)
            if changed_web:
                fail = self._prepare_web_panels(
                    new_plan, project=proj, brief="",
                    user_urls={str(w.get("url") or "").strip()
                               for w in changed_web if w.get("url")})
                if fail:
                    return ToolResult.fail(fail)
            out = output_path or state.get("output_path") or str(base / f"{proj}.mp4")
            if force:
                self._emit_progress("patch 模式下忽略 force=true：只重做受影响段，不整片重来")
            self._emit_progress(f"微调：应用到已有蓝图，仅重做受影响部分（补丁键：{list(patch.keys())}）")
            cine_n = (self._cine_count(cinematic_count) if cinematic_count is not None
                      else self._count_cinematic(new_plan))
            # patch = 手术式重做，永远不整片重来（即使用户/主 LLM 误传 force=true）
            return self._execute_plan(new_plan, out, proj, speaker, speech_rate, False,
                                      state_path, cinematic_count=cine_n, character=character)

        if plan:
            parsed = self._parse_plan(plan)
            if not parsed:
                return ToolResult.fail("plan 解析失败（需为蓝图 JSON）")
            have = self._count_cinematic(parsed)
            cine_n = have if cinematic_count is None else self._cine_count(cinematic_count)
            if cine_n != have:
                return ToolResult.fail(
                    f"蓝图里有 {have} 段 cinematic，与 cinematic_count={cine_n} 不一致。"
                    f"请用 brief + cinematic_count={cine_n} 重新设计蓝图，再执行。")
            out = output_path or str(base / f"{proj}.mp4")
            # 网页取景必须在设计阶段抓过真实页面；手写 plan 直接执行会没有来源与坐标
            missing = [
                i + 1 for i, p in enumerate(parsed.get("panels") or [])
                if isinstance(p, dict) and str(p.get("engine", "")).lower() == "webpage"
                and not ((p.get("web") or {}).get("capture_dir"))
            ]
            if missing:
                return ToolResult.fail(
                    f"第 {'、'.join(str(i) for i in missing)} 段是 webpage，但还没有真实来源与坐标。"
                    "请先用 brief 重新设计蓝图（设计阶段会自动抓取页面并回填 web.marks），再执行。")
            return self._execute_plan(parsed, out, proj, speaker, speech_rate, force,
                                      state_path, cinematic_count=cine_n, character=character)

        if brief:
            cine_n = self._cine_count(cinematic_count)
            self._emit_progress("① 导演正在设计制作蓝图...")
            blueprint = self._design(brief, cinematic_count=cine_n, project=proj)
            if isinstance(blueprint, ToolResult):
                return blueprint
            panels = blueprint.get("panels", [])
            engines = "、".join(sorted({_ENGINE_LABEL.get(p.get("engine"), p.get("engine")) for p in panels}))
            budget_text = self._cine_budget_text(cine_n)
            md = self._write_blueprint_md(blueprint, project, budget_text=budget_text)
            head = (f"已把制作蓝图写成 md 放在工作目录：{md}\n（Sigma 会自动弹出该 md，用户可直接阅读确认）\n\n"
                    ) if md else ""
            return ToolResult.ok(
                head
                + "制作蓝图已生成，请用 ask_user 与用户确认（可修改）；确认后带 plan 再调用本工具开始制作。\n"
                + "风格（engine / styleGuide）已由导演组按每段内容与用户要求定好，**不要再单独问用户用哪个风格**；"
                  "用户只需确认整份蓝图，或指出哪一段要改。\n"
                + "cinematic 默认只用 1 段；请在 ask_user 里顺便确认：「这支片的 cinematic 用几条？默认 1，"
                  "可明确要求 0（不用）/ 2 / 3」。\n"
                + f"若用户改了段数，带 brief + cinematic_count=<0/1/2/3> + 同一个 project 重新设计蓝图，"
                  "不要直接执行旧 plan。\n\n"
                f"标题：{blueprint.get('title', '')}\n分镜数：{len(panels)}\n进棚部门：{engines}\n"
                f"{budget_text}\n\n"
                f"蓝图：\n{json.dumps(blueprint, ensure_ascii=False, indent=2)}",
                need_confirm=True,
                plan=blueprint,
                blueprint_md=md,
                cinematic_count=cine_n,
                cinematic_budget=cine_n,
            )

        # 无 brief/plan：尝试断点续做（项目里存有蓝图与进度）
        state = self._load_state(state_path)
        if state and state.get("plan"):
            self._emit_progress("检测到未完成的制作，尝试断点续做...")
            out = output_path or state.get("output_path") or str(base / f"{proj}.mp4")
            cine_n = (self._cine_count(cinematic_count) if cinematic_count is not None
                      else self._count_cinematic(state["plan"]))
            return self._execute_plan(state["plan"], out, proj, speaker, speech_rate, force,
                                      state_path, cinematic_count=cine_n)
        return ToolResult.fail(
            "需要 brief（设计蓝图）或 plan（执行蓝图）；"
            "若上次中断，请带上相同的 project 再次调用以断点续做。"
        )

    # ─── 设计蓝图（内部导演 LLM） ───
    def _design(self, brief: str, cinematic_count: int = _CINEMATIC_DEFAULT,
                project: str = None):
        cfg = self.llm_config or {}
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            return ToolResult.fail("导演需要 LLM 设计蓝图，但未配置主 LLM。")
        # 影视级预算：本地规则（默认 1 段，用户可改 0/2/3），不再查询 API 额度。
        cine_n = self._cine_count(cinematic_count)
        budget = self._cine_budget_text(cine_n)
        hook_note = (
            "本片 cinematic_count=0：第一段禁止使用 cinematic，也禁止空镜/慢推/纯氛围画面；"
            "钩子按内容用 styled / opendesign / manim 的信息或演示型画面、blender 的 3D 结构、"
            "amap 的真实地图、webpage 的真实数据（若用户主动提供了开场素材，则改用 footage）；"
            "不能用 remotion。"
            if cine_n == 0 else
            f"本片 cinematic_count={cine_n}：第一段可以用 cinematic（实拍感/人物/真实场景），"
            "也可按内容用 blender（3D 设备/结构）、styled / opendesign（版式/数字/假 UI）、"
            "manim（公式推导）、amap（真实地点/路线）、webpage（真实数据）；"
            "这些是按需选择、不是硬约束，但 remotion 不能用。"
        )
        bgm_note = (
            "配乐能力：已配置音乐生成 API Key，可为成片配 BGM（蓝图 music 字段）。"
            if self._music_available() else
            "配乐能力：未配置音乐生成 API Key，**不要在蓝图里写 music 字段**。"
        )
        map_note = (
            "地图能力：已配置高德 Key，可用 amap 引擎（真实中国/世界地图、真实驾车/步行/骑行路线、地点标注）。"
            "用户需求涉及真实地点/行程/路线/中国或世界地图时，优先用 amap；"
            "只有要风格化/虚构地图时，才在 styled 的 styleGuide 里写「地图插画」画风。"
            if self._map_available() else
            "地图能力：未配置高德 Key，**不要在蓝图里用 amap**；"
            "需要地图画面时，用 styled 并在 styleGuide 里写「风格化纸地图」画风。"
        )
        web_note = (
            "网页取景能力：可用（已配置联网搜索，用户没给网址时也能用 web.query 自动找真实来源）。\n"
            "凡是需求里有『可核验的真实证据』——统计数字、榜单/表格、官方定义、报告结论、政策原文、"
            "或人群/规模/分布这类话题——**优先给它安排一段 webpage**，不要用 opendesign 把数字重画一遍。\n"
            "webpage 段必须写 web.focus（要让观众看到哪类证据），来源/原文/坐标由系统抓取后自动回填；"
            "一支片子通常 1~2 段 webpage 最合适。"
            if self._web_search_available() else
            "网页取景能力：不可用（未配置联网搜索）。**只有用户明确给了网址时**才能用 webpage（写 web.url）；"
            "否则不要用 webpage，需要展示数据时用 opendesign 图表。"
        )
        try:
            from skills.sfx.scripts.synth import catalog_menu
            sfx_menu = catalog_menu()
        except Exception as e:
            sfx_menu = f"（音效组不可用：{e}）"
        sources = self._source_videos()
        if sources:
            src_lines = "\n".join(f"- {s['name']}（{s['duration']:g}s）" for s in sources)
            footage_note = (
                "项目目录下的视频文件：\n" + src_lines + "\n"
                "只有当用户明确说自己提供了素材、并指定用在哪一段（开场 / 第几段）时，才可用 "
                "engine=\"footage\" 并把上面对应的文件名写进 video；用户没提素材时不要用 footage"
                "（目录里的视频也可能是历史成片）。"
            )
        else:
            footage_note = "项目目录下未发现视频文件：**本片不要使用 footage 引擎**。"
        context = (
            f"用户需求：\n{brief}\n\n"
            f"—— 制作预算（硬约束）——\n{budget}\n"
            f"panels 里 engine=\"cinematic\" 的数量必须恰好等于 {cine_n}；0 表示完全不用。\n"
            f"—— 开场钩子（硬约束）——\n{hook_note}\n"
            "第 1 段必须写 hook 字段，hook.type 从系统提示的钩子类型里选一个。\n\n"
            f"—— 用户自备视频素材（事实）——\n{footage_note}\n\n"
            f"—— 地图能力（事实）——\n{map_note}\n\n"
            f"—— 网页取景能力（事实）——\n{web_note}\n\n"
            f"—— 配乐能力（事实）——\n{bgm_note}\n\n"
            f"—— 音效能力（事实）——\n"
            "音效组已内置 30 个程序合成配方，不需要 API Key；"
            "按系统提示末尾的目录选 recipe，并在面板 sfx 字段里写事件。"
        )
        try:
            from skills.opendesign.scripts.renderer import call_llm_text
        except Exception as e:
            return ToolResult.fail(f"蓝图设计失败: {e}")
        errs = []
        sys_prompt = (_DESIGN_PROMPT.replace("{SFX_MENU}", sfx_menu)
                      .replace("{HOOK_MENU}", _hook_menu()))
        for k in (1, 2, 3):
            ctx = context + ("\n\n上次蓝图有问题，只修这些：\n" + "\n".join(errs) if errs else "")
            try:
                from skills.opendesign.scripts.renderer import (
                    _call_with_token_fallback, LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
                )
                raw = _call_with_token_fallback(
                    lambda token_budget: call_llm_text(
                        system_prompt=sys_prompt, context=ctx,
                        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
                        protocol=cfg.get("protocol", "anthropic"), max_tokens=token_budget,
                        provider=cfg.get("provider"), thinking=cfg.get("thinking"),
                        # 停滞超时给足：长思考模型（关不掉思考的，如 K3.1）思考期可能长时间无正文
                        timeout=600,
                    ),
                    max_tokens=LONG_OUTPUT_MAX_TOKENS,
                    fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                )
            except Exception as e:
                errs = [f"调用失败：{e}"]
                self._emit_progress("① 蓝图调用失败，重试一次：" + str(e)[:120])
                continue
            parsed = self._parse_plan(raw)
            if not parsed:
                errs = ["输出不是有效蓝图 JSON（需要 title/style/canvas/panels）"]
                continue
            errs = self._validate_blueprint(parsed, cinematic_count=cine_n)
            if not errs:
                # 让蓝图展示与执行一致：首段画面时长（非 cinematic/footage）不低于 10 秒。
                _apply_hook_min_duration(parsed)
                # 网页取景：设计阶段就把真实来源、高亮原文与坐标抓出来写进蓝图
                fail = self._prepare_web_panels(parsed, project=project, brief=brief)
                if fail:
                    return ToolResult.fail(fail)
                return parsed
            self._emit_progress("① 蓝图有小问题，重排一次：" + "；".join(errs[:3]))
        return ToolResult.fail("蓝图设计失败：" + "；".join(errs[:3]))

    @staticmethod
    def _parse_plan(plan) -> dict:
        data = plan
        if isinstance(plan, str):
            try:
                data = json.loads(plan)
            except json.JSONDecodeError:
                import re
                m = re.search(r"\{.*\}", plan, re.DOTALL)
                if not m:
                    return {}
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    return {}
        if not isinstance(data, dict) or not isinstance(data.get("panels"), list) or not data["panels"]:
            return {}
        return data

    @staticmethod
    def _validate_blueprint(plan: dict, cinematic_count: int | None = None) -> list:
        """蓝图的结构校验：引擎 / styled 风格 / 音效事件 / cinematic 段数。"""
        errs = []
        panels = [p for p in (plan.get("panels") or []) if isinstance(p, dict)]
        try:
            from skills.sfx.scripts.synth import is_recipe
        except Exception:
            is_recipe = lambda _rid: False  # noqa: E731

        def check_sfx(events, label: str, panel_count: int | None = None):
            if events is None:
                return
            if not isinstance(events, list):
                errs.append(f"{label} 的 sfx 必须是数组")
                return
            if len(events) > 6:
                errs.append(f"{label} 的 sfx 事件过多（{len(events)}），建议每段 ≤3 个、硬上限 6 个")
            for j, ev in enumerate(events):
                if not isinstance(ev, dict):
                    errs.append(f"{label} sfx 第 {j + 1} 个必须是对象")
                    continue
                rid = str(ev.get("recipe") or "").strip()
                if not is_recipe(rid):
                    errs.append(f"{label} sfx 第 {j + 1} 个 recipe={rid!r} 不在音效目录")
                try:
                    at = float(ev.get("at"))
                    if at < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    errs.append(f"{label} sfx 第 {j + 1} 个 at 必须是 >=0 的秒数")
                lvl = ev.get("level")
                if lvl is not None:
                    try:
                        lv = float(lvl)
                        if not 0 <= lv <= 100:
                            raise ValueError
                    except (TypeError, ValueError):
                        errs.append(f"{label} sfx 第 {j + 1} 个 level 必须是 0~100")
                if panel_count is not None:
                    try:
                        pid = int(ev.get("panel"))
                    except (TypeError, ValueError):
                        pid = None
                    if pid is None or not 1 <= pid <= panel_count:
                        errs.append(f"{label} sfx 第 {j + 1} 个 panel 必须是 1~{panel_count}")
                snap = ev.get("snap")
                if snap is not None and not isinstance(snap, bool):
                    errs.append(f"{label} sfx 第 {j + 1} 个 snap 必须是 true / false")

        canvas = plan.get("canvas") if isinstance(plan.get("canvas"), dict) else {}
        try:
            cw = int(canvas.get("width") or 1920)
            ch = int(canvas.get("height") or 1080)
        except (TypeError, ValueError):
            cw, ch = 1920, 1080
        embed_panels = 0
        hook_idxs = [i for i, p in enumerate(panels) if isinstance(p.get("hook"), dict)]
        last_hook = hook_idxs[-1] if hook_idxs else -1
        intro_panels = 0

        def check_hook(p, i):
            hk = p.get("hook")
            if hk is None:
                if i == 0:
                    errs.append("第 1 段必须写 hook 对象（type/text/why）作为开场钩子")
                return
            if not isinstance(hk, dict):
                errs.append(f"第 {i + 1} 段 hook 必须是对象（type/text/why）")
                return
            if i > 1:
                errs.append(f"第 {i + 1} 段不能再写 hook：开场钩子只允许前 1~2 段")
            ht = str(hk.get("type") or "").strip().lower()
            if ht not in _HOOK_TYPES:
                errs.append(f"第 {i + 1} 段 hook.type={ht!r} 不认识，只能是 "
                            f"{' / '.join(_HOOK_TYPES)}")
            eng_i = str(p.get("engine", "")).lower()
            if ht == "footage" and eng_i != "footage":
                errs.append(f"第 {i + 1} 段 hook.type=footage 时，engine 必须是 footage"
                            "（用户素材开场）")
            if ht == "object3d" and eng_i not in ("blender", "opendesign"):
                errs.append(f"第 {i + 1} 段 hook.type=object3d 时，engine 必须是 blender（真 3D）"
                            "或 opendesign（three.js）")
            if "text" in hk and not isinstance(hk.get("text"), str):
                errs.append(f"第 {i + 1} 段 hook.text 必须是字符串")

        def check_intro(p, i):
            nonlocal intro_panels
            intro = p.get("intro")
            if intro is None:
                return
            if not isinstance(intro, dict):
                errs.append(f"第 {i + 1} 段 intro 必须是对象")
                return
            intro_panels += 1
            if intro_panels > 1:
                errs.append("全片只能有一个 intro（标题入场）")
            if not isinstance(p.get("hook"), dict):
                errs.append(f"第 {i + 1} 段写了 intro，但它不是钩子段："
                            "intro 只能写在开场钩子的最后一段上")
            if i != last_hook:
                errs.append(f"第 {i + 1} 段写了 intro，但它不是最后一段钩子"
                            f"（当前最后钩子是第 {last_hook + 1} 段）："
                            "intro 要接住前一段钩子的画面")
            ovp = p.get("overlay")
            if isinstance(ovp, dict) and str(ovp.get("title") or "").strip():
                errs.append(f"第 {i + 1} 段同时写了 intro 和 overlay："
                            "两者都会上大标题，二选一")
            title = str(intro.get("title") or "").strip()
            if not title:
                errs.append(f"第 {i + 1} 段 intro 缺 title（另一侧的大标题）")
            else:
                lines = [x.strip() for x in title.splitlines() if x.strip()]
                if len(lines) > 2:
                    errs.append(f"第 {i + 1} 段 intro.title 最多 2 行（现在 {len(lines)} 行）")
                if any(len(x) > 10 for x in lines):
                    errs.append(f"第 {i + 1} 段 intro.title 每行建议 ≤8 字、最多 10 字，"
                                "否则大标题会掉字号或压到版式")
            accent = intro.get("accent")
            if accent not in (None, "") and not isinstance(accent, str):
                errs.append(f"第 {i + 1} 段 intro.accent 必须是字符串（要强调的词）")
            side = str(intro.get("side") or "").strip().lower()
            if side and side not in ("left", "right"):
                errs.append(f"第 {i + 1} 段 intro.side={side!r} 不认识，只能是 left / right")
            secs = intro.get("seconds")
            if secs not in (None, ""):
                try:
                    s = float(secs)
                    if not 2.5 <= s <= 5.5:
                        raise ValueError
                except (TypeError, ValueError):
                    errs.append(f"第 {i + 1} 段 intro.seconds 必须是 2.5~5.5 秒")
            tag = intro.get("tag")
            if tag not in (None, "") and not isinstance(tag, str):
                errs.append(f"第 {i + 1} 段 intro.tag 必须是字符串")

        for i, p in enumerate(panels):
            eng = str(p.get("engine", "")).lower()
            if eng not in _ENGINE_TOOL:
                errs.append(f"第 {i + 1} 段 engine={eng!r} 不认识，只能是 "
                            f"{' / '.join(_ENGINE_TOOL)}")
            check_hook(p, i)
            check_intro(p, i)
            embeds = p.get("embeds")
            if embeds is not None:
                # opendesign 内嵌特效：可选，不强制；只做结构/边界校验，不做"每段必须有一个"。
                if eng != "opendesign":
                    errs.append(f"第 {i + 1} 段写了 embeds，但 engine={eng!r}："
                                "只有 opendesign 支持内嵌 blender/manim/amap 图层")
                if not isinstance(embeds, list) or not embeds:
                    errs.append(f"第 {i + 1} 段 embeds 必须是非空数组（不需要就整个字段不写）")
                else:
                    embed_panels += 1
                    if len(embeds) > _EMBED_MAX_PER_PANEL:
                        errs.append(f"第 {i + 1} 段有 {len(embeds)} 个 embed，"
                                    f"最多 {_EMBED_MAX_PER_PANEL} 个")
                    for j, e in enumerate(embeds):
                        label = f"第 {i + 1} 段 embed 第 {j + 1} 个"
                        if not isinstance(e, dict):
                            errs.append(f"{label} 必须是对象")
                            continue
                        et = str(e.get("type") or "").strip().lower()
                        if et not in _EMBED_TYPES:
                            errs.append(f"{label} type={et!r} 不认识，只能是 "
                                        f"{' / '.join(sorted(_EMBED_TYPES))}")
                        rect = e.get("rect")
                        if not (isinstance(rect, (list, tuple)) and len(rect) == 4):
                            errs.append(f"{label} 缺 rect：[x, y, w, h]（画布像素）")
                        else:
                            try:
                                x, y, rw, rh = (float(v) for v in rect)
                                if rw < 160 or rh < 90:
                                    errs.append(f"{label} rect 太小（{rw:.0f}×{rh:.0f}，"
                                                "最小 160×90）")
                                if x < 0 or y < 0 or x + rw > cw + 1 or y + rh > ch + 1:
                                    errs.append(f"{label} rect 超出画布 {cw}×{ch}："
                                                f"({x:.0f}, {y:.0f}) {rw:.0f}×{rh:.0f}")
                            except (TypeError, ValueError):
                                errs.append(f"{label} rect 四个值必须都是数字")
                        try:
                            start = float(e.get("start") or 0)
                            edur = float(e.get("duration") or 0)
                        except (TypeError, ValueError):
                            start, edur = -1.0, 0.0
                        if start < 0:
                            errs.append(f"{label} start 必须是 >=0 的秒数")
                        if edur < 1.0:
                            errs.append(f"{label} duration 必须 >=1 秒")
                        secs = p.get("seconds")
                        if secs not in (None, ""):
                            try:
                                psec = float(secs)
                                # 首段执行时会被抬到 ≥10s，校验也按抬高后的时长算
                                if i == 0 and eng not in ("cinematic", "footage"):
                                    psec = max(psec, _HOOK_MIN_SECONDS)
                                if psec > 0 and start + edur > psec + 0.25:
                                    errs.append(
                                        f"{label} start+duration={start + edur:.1f}s "
                                        f"超过了本段 seconds={psec:.1f}s")
                            except (TypeError, ValueError):
                                pass
                        if et == "amap":
                            mp = e.get("map")
                            if not isinstance(mp, dict):
                                errs.append(f"{label} 是 amap，但缺少 map 对象")
                            else:
                                mk = str(mp.get("kind") or "").strip().lower()
                                if mk not in ("route", "region", "world", "flight"):
                                    errs.append(f"{label} map.kind={mk!r} 不认识，"
                                                "只能是 route / region / world / flight")
                                if mk == "route":
                                    rt = mp.get("route")
                                    if not isinstance(rt, dict) or not rt.get("origin") \
                                            or not rt.get("destination"):
                                        errs.append(f"{label} route 需要 origin 与 destination")
                        elif et in ("blender", "manim"):
                            if not str(e.get("brief") or e.get("visual") or "").strip():
                                errs.append(f"{label} 缺 brief/visual：要描述这个特效画面")
            if eng == "remotion":
                errs.append(f"第 {i + 1} 段不能用 remotion：该引擎只做标题/动态字，已停用；"
                            "开场钩子按内容改用 cinematic / blender / styled / manim / amap / opendesign")
            if eng == "footage":
                if not str(p.get("video") or "").strip():
                    errs.append(f"第 {i + 1} 段是 footage，但缺少 video（用户提供的视频文件路径）")
                fit = str(p.get("fit") or "").strip().lower()
                if fit and fit not in ("contain", "cover"):
                    errs.append(f"第 {i + 1} 段 fit={fit!r} 不认识，只能是 contain / cover")
                cs = p.get("clip_seconds")
                if cs not in (None, ""):
                    try:
                        if float(cs) <= 0:
                            raise ValueError
                    except (TypeError, ValueError):
                        errs.append(f"第 {i + 1} 段 clip_seconds 必须是 >0 的秒数（整段请不要写）")
            if eng == "amap":
                mp = p.get("map")
                if not isinstance(mp, dict):
                    errs.append(f"第 {i + 1} 段是 amap，但缺少 map 对象（kind/title/route/region/world）")
                else:
                    mk = str(mp.get("kind") or "").strip().lower()
                    if mk not in ("route", "region", "world", "flight"):
                        errs.append(f"第 {i + 1} 段 map.kind={mk!r} 不认识，"
                                    "只能是 route / region / world / flight")
                    theme = str(mp.get("theme") or "").strip().lower()
                    if theme and theme not in ("dark", "light"):
                        errs.append(f"第 {i + 1} 段 map.theme={theme!r} 不认识，只能是 dark / light")
                    if mk == "route":
                        rt = mp.get("route")
                        if not isinstance(rt, dict) or not rt.get("origin") or not rt.get("destination"):
                            errs.append(f"第 {i + 1} 段 route 需要 origin 与 destination（地名或 [经度,纬度]）")
                        else:
                            def _coord(v):
                                return isinstance(v, (list, tuple)) and len(v) >= 2
                            if not mp.get("city") and not (_coord(rt.get("origin")) and _coord(rt.get("destination"))):
                                errs.append(f"第 {i + 1} 段 route 请写 city（如 \"北京\"）："
                                            "中文地名不加城市限定会解析到别的城市")
                    if mk == "flight":
                        ft = mp.get("flight")
                        if not isinstance(ft, dict) or not ft.get("from") or not ft.get("to"):
                            if not mp.get("from") or not mp.get("to"):
                                errs.append(f"第 {i + 1} 段 flight 需要 from 与 to（城市名或 [经度,纬度]）")
                    if mk == "region" and mp.get("region") is not None and not isinstance(mp.get("region"), dict):
                        errs.append(f"第 {i + 1} 段 map.region 必须是对象")
                    if mk == "world" and mp.get("world") is not None and not isinstance(mp.get("world"), dict):
                        errs.append(f"第 {i + 1} 段 map.world 必须是对象")
                    if mp.get("markers") is not None and not isinstance(mp.get("markers"), list):
                        errs.append(f"第 {i + 1} 段 map.markers 必须是数组")
            if eng == "webpage":
                w = p.get("web")
                if not isinstance(w, dict) or not w:
                    errs.append(f"第 {i + 1} 段是 webpage，但缺少 web 对象"
                                "（url 或 query + focus）")
                else:
                    u = str(w.get("url") or "").strip()
                    q = str(w.get("query") or "").strip()
                    f = str(w.get("focus") or "").strip()
                    if not u and not q:
                        errs.append(f"第 {i + 1} 段 webpage 需要 web.url 或 web.query 至少一个")
                    if u and not u.lower().startswith(("http://", "https://")):
                        errs.append(f"第 {i + 1} 段 web.url 必须是 http(s) 地址")
                    if not f:
                        errs.append(f"第 {i + 1} 段 webpage 必须写 web.focus"
                                    "（这段讲什么、重点标哪类信息）")
                    mm = w.get("max_marks")
                    if mm is not None:
                        try:
                            if not 1 <= int(mm) <= 4:
                                raise ValueError
                        except (TypeError, ValueError):
                            errs.append(f"第 {i + 1} 段 web.max_marks 必须是 1~4")
                    if w.get("marks") or w.get("source"):
                        errs.append(f"第 {i + 1} 段 webpage 不要自己写 web.source/web.marks"
                                    "（系统抓取真实页面后回填）")
            if eng == "styled":
                # styled 不再挑固定风格 id：全片风格档案写在顶层 styleGuide，段内可写 styleNote。
                sg = p.get("styleGuide")
                if sg is not None and not isinstance(sg, (str, dict)):
                    errs.append(f"第 {i + 1} 段 styleGuide 必须是字符串或对象")
                sn = p.get("styleNote")
                if sn is not None and not isinstance(sn, str):
                    errs.append(f"第 {i + 1} 段 styleNote 必须是字符串")
            check_sfx(p.get("sfx"), f"第 {i + 1} 段")

        if len(hook_idxs) == 2:
            hs = []
            for k in hook_idxs:
                try:
                    hs.append(float(panels[k].get("seconds") or 0))
                except (TypeError, ValueError):
                    hs.append(0.0)
            if all(v > 0 for v in hs):
                if min(hs) < 4:
                    errs.append("两段钩子单段至少 4 秒：太短会把钩子拆碎")
                if sum(hs) < 9.5:
                    errs.append(f"两段钩子合计至少 10 秒（当前 {sum(hs):.1f}s）："
                                "拆成两段不是把钩子变短")
        if embed_panels > _EMBED_MAX_PANELS:
            errs.append(f"全片有 {embed_panels} 段 opendesign 内嵌了特效，最多 "
                        f"{_EMBED_MAX_PANELS} 段：每段都要预渲染+雪碧图，太多会变慢、画面也会堆砌")
        check_sfx(plan.get("sfx"), "顶层 sfx", len(panels))
        dens = plan.get("sfx_density")
        if dens is not None and str(dens).strip().lower() not in _SFX_DENSITY:
            errs.append(f"sfx_density={dens!r} 不认识，只能是 {' / '.join(_SFX_DENSITY)}")
        snap = plan.get("sfx_snap")
        if snap is not None and str(snap).strip().lower() not in ("visual", "none"):
            errs.append(f"sfx_snap={snap!r} 不认识，只能是 visual / none")
        win = plan.get("sfx_snap_window")
        if win is not None:
            try:
                w = float(win)
                if not 0.3 <= w <= 3.0:
                    raise ValueError
            except (TypeError, ValueError):
                errs.append("sfx_snap_window 必须是 0.3~3.0 的秒数")
        if cinematic_count is not None:
            got = sum(1 for p in panels
                      if str(p.get("engine", "")).lower() == "cinematic")
            if got != cinematic_count:
                errs.append(f"cinematic 段数必须是 {cinematic_count}，当前 {got}")
            if (cinematic_count == 0 and panels
                    and str(panels[0].get("engine", "")).lower() == "cinematic"):
                errs.append("cinematic_count=0 时第 1 段不能是 cinematic"
                            "（开场钩子按内容用 styled / opendesign / blender / manim / amap / webpage，"
                            "或用户素材 footage；不能用 remotion）")
        return errs

    # ─── 断点续做：状态 ───
    @staticmethod
    def _load_state(path: Path) -> dict:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    @staticmethod
    def _save_state(path: Path, state: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _ok_file(p) -> bool:
        try:
            return bool(p) and Path(str(p)).exists() and Path(str(p)).stat().st_size > 0
        except Exception:
            return False

    @staticmethod
    def _as_bool(v, default: bool = True) -> bool:
        """布尔边界归一：蓝图里可能写成字符串（"false"/"no"/"0"）。"""
        if v is None:
            return default
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "none", "")
        return bool(v)

    # ─── 蓝图 md（供用户在 Sigma 中直接确认：md 会自动弹出） ───
    @staticmethod
    def _slug(text: str, fallback: str = "video") -> str:
        import re
        s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(text or "").strip())
        s = re.sub(r"\s+", " ", s).strip(" ._")
        return s[:40] or fallback

    def _write_blueprint_md(self, plan: dict, project: str = None, budget_text: str = "") -> str:
        """把蓝图写成 md 放到工作目录（Sigma 会自动弹出 md 供用户确认），返回文件路径。"""
        panels = [p for p in (plan.get("panels") or []) if isinstance(p, dict)]
        canvas = plan.get("canvas") or {}
        mspec = self._music_spec(plan)
        sfx_events = []
        for p in panels:
            evs = p.get("sfx")
            if isinstance(evs, list):
                sfx_events.extend(evs)
        top_sfx = plan.get("sfx")
        if isinstance(top_sfx, list):
            sfx_events.extend(top_sfx)
        sfx_density = self._sfx_density(plan)
        sfx_density_label = _SFX_DENSITY_LABEL.get(sfx_density, sfx_density)
        sfx_lo, sfx_hi = _SFX_DENSITY[sfx_density]
        sfx_snap = str(plan.get("sfx_snap") or "visual").strip().lower()
        sfx_snap_label = "关闭" if sfx_snap == "none" else "开"
        try:
            from skills.sfx.scripts.synth import get_recipe as get_sfx_recipe
        except Exception:
            get_sfx_recipe = lambda _rid: None  # noqa: E731

        def _sfx_cell(p):
            evs = p.get("sfx") or []
            if not isinstance(evs, list) or not evs:
                return "—"
            parts = []
            for ev in evs[:6]:
                if not isinstance(ev, dict):
                    continue
                rid = str(ev.get("recipe") or "").strip()
                rec = get_sfx_recipe(rid)
                title = rec["title"] if rec else rid
                parts.append(f"{ev.get('at', 0)}s {title}")
            return " / ".join(parts) or "—"

        rows = [
            f"# {plan.get('title') or '视频制作蓝图'}",
            "",
            f"> 制作蓝图 · 分镜 {len(panels)} 段 · 画布 {canvas.get('width', 1920)}×{canvas.get('height', 1080)} "
            f"@{canvas.get('fps', 30)}fps · 字幕{'开' if plan.get('subtitles', True) else '关'} · "
            f"配乐{'开' if mspec else '关'} · 音效{len(sfx_events)}个（{sfx_density_label}） · "
            f"审查{'开' if plan.get('review', True) else '关'}",
            "",
        ]
        if budget_text:
            rows += [f"> {budget_text}", ""]
        hook = (panels[0].get("hook") if panels else None)
        if isinstance(hook, dict) and hook.get("type"):
            ht = str(hook.get("type")).strip().lower()
            hlabel = _HOOK_TYPES.get(ht, {}).get("label", ht)
            line = f"**开场钩子**：{hlabel}（{ht}）｜文案：{hook.get('text') or '—'}"
            if hook.get("why"):
                line += f"｜{hook.get('why')}"
            rows += [line, ""]
        intro = next((p.get("intro") for p in panels
                      if isinstance(p.get("intro"), dict)), None)
        if intro:
            ititle = " / ".join(x.strip() for x in str(intro.get("title") or "").splitlines()
                                if x.strip())
            rows += [f"**标题入场**：{ititle or '—'}｜画面缩到 "
                     f"{str(intro.get('side') or 'right')}｜"
                     f"{float(intro.get('seconds') or 4):g}s（静音转场）", ""]
        had_music = bool(mspec)
        rows += [
            f"**整体风格**：{plan.get('style', '') or '—'}",
            f"**背景音乐**：{mspec['prompt']}（音量 {mspec['level']}%）" if had_music
            else "**背景音乐**：无（默认不配乐；满意后可追加重烧："
                 "`director(project=\"<同名>\", patch='{\"music\":{\"prompt\":\"…\",\"level\":30}}')`）",
            "**音效**：关闭（`sfx_density=none`，蓝图里的 sfx 将被忽略）"
            if sfx_density == "none"
            else (f"**音效**：{len(sfx_events)} 个事件｜密度 {sfx_density_label}"
                  f"（{sfx_lo:g}~{sfx_hi:g} 个/分钟）｜画面吸附 {sfx_snap_label}"
                  f"（执行层按 2 秒最小间隔与 priority 裁剪）"
                  if sfx_events
                  else f"**音效**：无事件｜密度 {sfx_density_label}"
                       f"（{sfx_lo:g}~{sfx_hi:g} 个/分钟）｜画面吸附 {sfx_snap_label}"
                       f"（执行层会提示偏少）"),
            "",
            "## 分镜",
            "",
            "> 引擎列里的「HTML动画 + 3D渲染」= opendesign 内嵌 blender；"
            "「HTML动画 + Manim讲解」= 内嵌 manim；「HTML动画 + 高德地图」= 内嵌 map。",
            "",
            "| # | 引擎 | 风格 | 旁白 | 画面需求 | 标题包装 | 音效 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for i, p in enumerate(panels):
            engine_id = str(p.get("engine", "")).lower()
            eng = _panel_engine_label(p, engine_id)
            ov = p.get("overlay") if isinstance(p.get("overlay"), dict) else {}
            vs_cell = "见风格档案" if engine_id == "styled" else "—"
            visual_cell = str(p.get("visual") or "")
            embeds = _panel_embeds(p)
            if embeds:
                parts = []
                for e in embeds:
                    et = str(e.get("type") or "").lower()
                    brief = str(e.get("brief") or e.get("visual") or "").strip()
                    try:
                        st = float(e.get("start") or 0)
                        ed = float(e.get("duration") or 0)
                        timing = f"{st:.1f}s+{ed:.1f}s"
                    except (TypeError, ValueError):
                        timing = ""
                    parts.append(f"{_ENGINE_LABEL.get(et, et)}"
                                 + (f"（{timing}）" if timing else "")
                                 + (f"：{brief[:26]}" if brief else ""))
                visual_cell = "内嵌 " + " / ".join(parts) + "｜" + visual_cell
            if engine_id == "footage":
                visual_cell = f"素材：{p.get('video') or '—'}｜{visual_cell}"
            if engine_id == "amap":
                mp = p.get("map") if isinstance(p.get("map"), dict) else {}
                mk = str(mp.get("kind") or "—")
                extra = ""
                if mk == "route":
                    rt = mp.get("route") or {}
                    extra = f"{rt.get('origin', '?')} → {rt.get('destination', '?')}"
                elif mk == "flight":
                    ft = mp.get("flight") or {}
                    extra = f"{ft.get('from', '?')} → {ft.get('to', '?')}（航线示意）"
                elif mk == "region":
                    reg = mp.get("region") or {}
                    hl = reg.get("highlight") or []
                    extra = "、".join(str(x) for x in hl[:6]) if hl else str(reg.get("soc") or "")
                elif mk == "world":
                    w = mp.get("world") or {}
                    extra = "、".join(str(x) for x in (w.get("highlight") or [])[:8])
                visual_cell = f"地图：{mk}｜{extra}｜{visual_cell}"
            if engine_id == "webpage":
                w = p.get("web") if isinstance(p.get("web"), dict) else {}
                src = w.get("source") or {}
                parts = [f"网页：{src.get('title') or src.get('url') or '待抓取'}"]
                if src.get("url"):
                    parts.append(str(src["url"]))
                if src.get("reason"):
                    parts.append(f"理由：{src['reason']}")
                for j, mk in enumerate(w.get("marks") or [], 1):
                    r = mk.get("page_rect") or mk.get("rect") or [0, 0, 0, 0]
                    parts.append(
                        f"标注{j}：「{mk.get('quote', '')}」坐标 ({r[0]}, {r[1]}) {r[2]}×{r[3]}")
                if p.get("web_note"):
                    parts.append(str(p["web_note"]))
                visual_cell = "｜".join(parts) + "｜" + visual_cell
            def _cell(v):
                return str(v or "—").replace("|", "/").replace("\n", " ").strip()
            rows.append("| %d | %s | %s | %s | %s | %s | %s |" % (
                i + 1, _cell(eng), _cell(vs_cell), _cell(p.get("narration")),
                _cell(visual_cell), _cell(ov.get("title")), _cell(_sfx_cell(p))))
        rows += ["", "## 蓝图 JSON（执行用，请原样传回）", "", "```json",
                 json.dumps(plan, ensure_ascii=False, indent=2), "```", ""]
        name = self._slug(project or plan.get("title", ""), "video") + "_制作蓝图.md"
        path = Path(self.cwd) / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(rows), encoding="utf-8")
            return str(path)
        except Exception:
            return ""

    # ─── 逐项签名（微调/续做的判据） ───
    @staticmethod
    def _h(obj) -> str:
        import hashlib
        return hashlib.sha1(json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _narr_key(text, speaker, rate) -> str:
        import hashlib
        raw = f"{text}\x00{speaker or ''}\x00{rate}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:16]

    def _panel_sig(self, p, engine, dur, W, H, FPS, style, narr_text, overlay=None,
                   style_guide=None) -> str:
        # 只纳入"真正决定该段产物"的字段：引擎 / 画面 / 提示词 / 标题包装 / 旁白 / 实测时长 / 画布。
        # styled 段额外纳入全片风格档案——换画风必须重渲。
        # 刻意【不含】全局 style 与兜底 seconds —— 否则整片风格措辞微调或 seconds 微调会导致全片重渲。
        sig = {
            "engine": engine, "visual": p.get("visual"), "prompt": p.get("prompt"),
            "overlay": overlay, "narration": narr_text, "hook": p.get("hook"),
            "intro": p.get("intro"),
            "dur": round(float(dur or 0), 3), "whf": [W, H, FPS],
        }
        if engine == "styled":
            sig["styleGuide"] = style_guide or ""
            sig["styleNote"] = _style_note(p)
        # 用户素材段：素材文件本身进签名（路径 + mtime + 大小）——换文件/同名覆盖都能触发重做。
        if engine == "footage":
            src = str(p.get("video") or "").strip()
            sig["video"] = src
            sig["fit"] = str(p.get("fit") or "contain").strip().lower()
            try:
                sig["clip_seconds"] = round(float(p.get("clip_seconds") or 0), 3)
            except (TypeError, ValueError):
                sig["clip_seconds"] = 0
            sig["keep_audio"] = self._as_bool(p.get("keep_audio", True))
            try:
                sp = Path(src) if Path(src).is_absolute() else Path(self.cwd) / src
                st = sp.stat()
                sig["vfile"] = [round(st.st_mtime, 3), st.st_size]
            except OSError:
                sig["vfile"] = [0, 0]
        if engine == "remotion":
            # 改角色只重渲使用骨架的 Remotion 段；角色内容而不是文件路径进签名。
            sig["character"] = getattr(self, "_character_sha", "")
        # 真实地图段：spec 本身进签名；改地图类型/地点/路线只重做这一段。
        if engine == "amap":
            sig["map"] = p.get("map")
        # 网页取景段：来源、原文与坐标全部进签名；任何一处变化都只重做这一段。
        if engine == "webpage":
            sig["web"] = p.get("web")
        # opendesign 内嵌特效：spec 与子引擎版本都进签名，改特效/改矩形/改时间只重做这一段。
        if engine == "opendesign":
            sig["embeds"] = _panel_embeds(p)
            sig["embed_rev"] = {str(e.get("type") or "").lower(): _ENGINE_REV.get(
                str(e.get("type") or "").lower(), 0) for e in _panel_embeds(p)}
        # 引擎渲染器有实质变更时，只让该引擎的旧段失效；其他引擎的签名保持原样。
        rev = _ENGINE_REV.get(str(engine).lower())
        if rev:
            sig["erev"] = rev
        return self._h(sig)

    def _compose_sig(self, panel_sigs, sub_sig, videos, W, H, FPS, joints=None,
                     bgm=None, bgm_level=None, sfx=None) -> str:
        # 基于"内容签名"而非文件时间戳，避免同秒重渲染被判为未变而漏合成
        return self._h({"ps": list(panel_sigs), "sub": sub_sig,
                        "vids": [str(v) for v in videos], "whf": [W, H, FPS],
                        "tr": joints, "bgm": str(bgm or ""), "bvol": bgm_level,
                        "sfx": sfx,
                        "rev": _COMPOSE_REV})

    @staticmethod
    def _music_spec(plan: dict) -> dict:
        """归一化蓝图 music 字段：支持字符串简写或 {"prompt","level"}。无则返回 {}。"""
        raw = (plan or {}).get("music")
        if not raw:
            return {}
        if isinstance(raw, str):
            prompt, level = raw.strip(), 30
        elif isinstance(raw, dict):
            prompt = str(raw.get("prompt") or raw.get("description") or "").strip()
            level = raw.get("level", raw.get("volume", 30))
        else:
            return {}
        if not prompt:
            return {}
        try:
            level = int(round(float(level)))
        except (TypeError, ValueError):
            level = 30
        return {"prompt": prompt, "level": max(0, min(100, level))}

    def _music_available(self) -> bool:
        """音乐组是否可用（已配置 API Key）。用于把"能不能配乐"作为事实喂给导演 LLM。"""
        try:
            return bool(getattr(self.skill_manager.get_tool("music_generate"), "api_key", ""))
        except Exception:
            return False

    def _sfx_available(self) -> bool:
        """音效组是否可用（程序合成，无需 Key；技能被禁用时不可用）。"""
        try:
            return bool(self.skill_manager.get_tool("sfx"))
        except Exception:
            return False

    def _map_available(self) -> bool:
        """高德地图引擎是否可用（已配置 Key / 安全密钥）。"""
        try:
            return bool(getattr(self.skill_manager.get_tool("map_video"), "available", False))
        except Exception:
            return False

    def _web_search_available(self) -> bool:
        """联网搜索是否可用。用于判断网页取景能否自动找来源。"""
        try:
            return bool(getattr(self.skill_manager, "web_search_api_key", ""))
        except Exception:
            return False

    def _prepare_web_panels(self, plan: dict, *, project: str, brief: str,
                            user_urls: set[str] | None = None) -> str | None:
        """设计阶段完成网页取景：来源、高亮原文与坐标直接写进蓝图。

        返回 None 表示成功；返回字符串表示必须中止设计的错误。
        自动搜索来的来源失败时，该段降级为 opendesign 并在蓝图里注明；
        用户明确指定的网址失败则如实报错，不替换。
        """
        panels = plan.get("panels") or []
        targets = [(i, p) for i, p in enumerate(panels)
                   if isinstance(p, dict) and str(p.get("engine", "")).lower() == "webpage"]
        if not targets:
            return None
        try:
            from skills.webpage.scripts.prepare import PrepareError, prepare_web
        except Exception as e:
            return f"网页取景引擎不可用：{e}"

        canvas = plan.get("canvas") or {}
        width = int(canvas.get("width") or 1920)
        height = int(canvas.get("height") or 1080)
        import re as _re
        brief_urls = {u.rstrip("/") for u in
                      _re.findall(r"https?://[^\s\"'<>）)]+", brief or "")}
        explicit_urls = {u.rstrip("/") for u in (user_urls or set()) if u}
        for i, p in targets:
            web = p.get("web")
            if not isinstance(web, dict) or not web:
                return f"第 {i + 1} 段 webpage 缺少 web 对象"
            url = str(web.get("url") or "").strip()
            user_url = bool(url) and url.rstrip("/") in (brief_urls | explicit_urls)
            self._emit_progress(f"①b 网页取景 第 {i + 1} 段：解析来源并抓取真实页面...")
            try:
                enriched = prepare_web(
                    {**web, "width": width, "height": height},
                    project=project, cwd=self.cwd,
                    llm_config=self.llm_config, skill_manager=self.skill_manager,
                    narration=str(p.get("narration") or ""),
                    on_progress=lambda msg, _i=i: self._emit_progress(
                        f"  · 第 {_i + 1} 段 {msg}"),
                )
            except PrepareError as e:
                if e.user_url or user_url:
                    return f"第 {i + 1} 段网页取景失败（用户指定的网址不可替换）：{e}"
                note = f"未找到可用的真实来源，已改为 HTML 动画重绘（原因：{e}）"
                self._emit_progress(f"  ⚠ 第 {i + 1} 段降级为 HTML 动画：{e}")
                p["engine"] = "opendesign"
                p.pop("web", None)
                p["web_note"] = note
                p["visual"] = f"{p.get('visual') or ''}（{note}）".strip()
                continue
            except Exception as e:
                return f"第 {i + 1} 段网页取景异常：{e}"

            marks = enriched.get("marks") or []
            if not marks:
                if user_url:
                    return f"第 {i + 1} 段网页取景失败：页面里没有可标注的原文"
                note = "页面里没有找到可标注的原文，已改为 HTML 动画重绘"
                p["engine"] = "opendesign"
                p.pop("web", None)
                p["web_note"] = note
                p["visual"] = f"{p.get('visual') or ''}（{note}）".strip()
                continue

            p["web"] = enriched
            src = enriched.get("source") or {}
            self._emit_progress(
                f"  ✓ 第 {i + 1} 段来源：{src.get('title') or src.get('domain') or enriched.get('url')}"
                f"｜标注 {len(marks)} 处"
            )
        return None

    def _source_videos(self, limit: int = 20) -> list:
        """如实列出项目目录（cwd）顶层的视频文件，供蓝图设计判断用户是否已放入素材。

        只是"事实清单"，不做任何推荐/挑选：是否使用 footage 由用户在需求里明确说了算。
        按修改时间倒序（用户刚放进来的素材通常在最前面）。
        """
        try:
            paths = [p for p in Path(self.cwd).iterdir()
                     if p.is_file() and p.suffix.lower() in _SOURCE_VIDEO_EXTS]
        except OSError:
            return []

        def _mtime(p):
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        paths.sort(key=_mtime, reverse=True)
        return [{"name": p.name, "duration": round(_probe_dur(p), 1)} for p in paths[:limit]]

    @staticmethod
    def _sfx_density(plan: dict) -> str:
        """蓝图音效密度档位：none / light / normal / rich；脏值回落 normal。"""
        raw = str((plan or {}).get("sfx_density") or "normal").strip().lower()
        return raw if raw in _SFX_DENSITY else "normal"

    @staticmethod
    def _sfx_target(density: str, timeline_dur: float) -> tuple:
        """按成片分钟数换算音效目标区间（含 12 秒以下短片的兜底）。"""
        minutes = max(0.0, float(timeline_dur)) / 60.0
        lo, hi = _SFX_DENSITY.get(density, _SFX_DENSITY["normal"])
        tmin = int(math.ceil(minutes * lo)) if lo > 0 else 0
        tmax = min(_SFX_GLOBAL_CAP, int(math.ceil(minutes * hi))) if hi > 0 else 0
        if timeline_dur < 12:
            tmin = 0
        tmin = min(_SFX_GLOBAL_CAP, tmin)
        return tmin, min(_SFX_GLOBAL_CAP, max(tmax, tmin))

    @staticmethod
    def _visual_beats(video_path: str, sample_fps: float = 12.0) -> list:
        """检测成片里的明显画面变化点（元素入场/镜头切换/动画起点）。

        做法：ffmpeg 抽 12fps 的 48×48 RGB 小帧 → 逐帧差分 → 局部峰值。
        用 RGB 而不是灰度：红→绿这类“亮度接近、颜色突变”的切换灰度会漏检。

        ⚠️ 成本边界：**不落盘截图、不调用视觉模型、不消耗 token**。
        rawvideo 直接通过管道读进内存，单段 30s 约 2.5MB 临时数据，用完即释放；
        结果只缓存几个节拍秒数。不要把它误认为“抽帧+视觉调用”的方案。
        不依赖任何引擎输出元数据，对所有画面引擎通用。
        """
        import shutil
        import subprocess

        import numpy as np

        ff = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"
        side = 48
        frame_size = side * side * 3
        try:
            r = subprocess.run(
                [ff, "-v", "error", "-i", str(video_path), "-an",
                 "-vf", f"fps={sample_fps:g},scale={side}:{side}:flags=fast_bilinear,format=rgb24",
                 "-f", "rawvideo", "-"],
                capture_output=True, timeout=60,
            )
        except Exception:
            return []
        if r.returncode != 0 or not r.stdout:
            return []
        try:
            arr = np.frombuffer(r.stdout, dtype=np.uint8)
            n = len(arr) // frame_size
            if n < 3:
                return []
            frames = arr[:n * frame_size].reshape(n, frame_size).astype(np.float32)
            absdiff = np.abs(frames[1:] - frames[:-1])
            # mean 抓整体切换，p99 抓“小元素入场”这种局部变化（只占画面很小一块）
            diff = 0.6 * absdiff.mean(axis=1) + 0.4 * np.percentile(absdiff, 99, axis=1)
            if len(diff) >= 3:
                diff = np.convolve(diff, np.ones(3, dtype=np.float32) / 3, mode="same")
            mean, std = float(diff.mean()), float(diff.std())
            # 自适应阈值 + 绝对底噪，避免把压缩噪点当节拍
            thr = max(mean + 0.8 * std, mean * 1.35, 0.8)
            peaks = []
            for i in range(1, len(diff) - 1):
                if diff[i] < thr:
                    continue
                if diff[i] < diff[i - 1] or diff[i] < diff[i + 1]:
                    continue
                peaks.append((float(diff[i]), (i + 1) / sample_fps))
            peaks.sort(key=lambda x: x[1])
            # 0.4s 内只保留更强的一个峰
            picked = []
            for strength, t in peaks:
                if picked and t - picked[-1][1] < 0.4:
                    if strength > picked[-1][0]:
                        picked[-1] = (strength, t)
                    continue
                picked.append((strength, t))
            if len(picked) > 8:
                picked = sorted(sorted(picked, key=lambda x: -x[0])[:8], key=lambda x: x[1])
            return [round(t, 3) for _, t in picked]
        except Exception:
            return []

    @staticmethod
    def _snap_at(at: float, beats: list, window: float) -> tuple:
        """把音效时间吸附到窗口内最近的画面节拍；返回 (time, snapped)。"""
        if not beats:
            return at, False
        best = min(beats, key=lambda b: abs(float(b) - float(at)))
        if abs(float(best) - float(at)) <= window:
            return round(float(best), 3), True
        return at, False

    @staticmethod
    def _sfx_events_from_plan(plan: dict, panels: list) -> list:
        """收集蓝图里的音效事件：面板级 sfx + 顶层 sfx（顶层用 panel 指定第几段）。"""
        raw = []
        for i, p in enumerate(panels):
            evs = p.get("sfx")
            if isinstance(evs, list):
                for ev in evs:
                    if isinstance(ev, dict):
                        item = dict(ev)
                        item["_panel"] = i
                        raw.append(item)
        top = plan.get("sfx")
        if isinstance(top, list):
            for ev in top:
                if not isinstance(ev, dict):
                    continue
                try:
                    pi = int(ev.get("panel")) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= pi < len(panels):
                    item = dict(ev)
                    item["_panel"] = pi
                    raw.append(item)
        return raw

    def _resolve_sfx_assets(self, plan: dict, panels: list, panel_starts: list,
                            panel_durs: list, seg_videos: list, timeline_dur: float,
                            base: Path, proj: str,
                            state: dict, state_path: Path, force: bool) -> tuple:
        """把蓝图里的音效事件解析为可混音的绝对时间点，并按签名缓存资产。

        密度策略（在旁白实测时长确定后执行）：
          - 目标区间 = 成片分钟数 × 密度档位（light/normal/rich）；
          - 单段上限 = min(3, ceil(段长/10s))；
          - 全局最小间隔 2s；
          - 超出目标上限时按 priority（默认 50）保留，其余裁掉；
          - 低于目标下限不强行补，只通过 info 返回供调用方提示。

        返回 (events, redo, reuse, info)；
        events 元素：{path, at(成片时间轴秒), level(0~100), recipe, panel(1-based), rel_at}；
        info：{density, target_min, target_max, candidates, actual, dropped}。
        """
        density = self._sfx_density(plan)
        target_min, target_max = self._sfx_target(density, timeline_dur)
        raw = self._sfx_events_from_plan(plan, panels)
        if density == "none":
            if raw:
                self._emit_progress(f"④c sfx_density=none：忽略 {len(raw)} 个音效事件")
            return [], 0, 0, {"density": density, "target_min": 0, "target_max": 0,
                              "candidates": len(raw), "actual": 0, "dropped": 0}
        if not raw:
            return [], 0, 0, {"density": density, "target_min": target_min,
                              "target_max": target_max, "candidates": 0,
                              "actual": 0, "dropped": 0}
        if not self._sfx_available():
            self._emit_progress("④c 音效组不可用，跳过音效")
            return [], 0, 0, {"density": density, "target_min": target_min,
                              "target_max": target_max, "candidates": len(raw),
                              "actual": 0, "dropped": 0}
        try:
            from skills.sfx.scripts.synth import is_recipe
        except Exception:
            self._emit_progress("④c 音效组模块加载失败，跳过音效")
            return [], 0, 0, {"density": density, "target_min": target_min,
                              "target_max": target_max, "candidates": len(raw),
                              "actual": 0, "dropped": 0}

        # 视觉节拍：从成片画面变化里找“元素入场/镜头切换/动画起点”，用于把音效从
        # “旁白时间”拉回“画面时间”。检测结果按视频路径 + mtime 缓存。
        snap_mode = str(plan.get("sfx_snap") or "visual").strip().lower()
        if snap_mode not in ("visual", "none"):
            snap_mode = "visual"
        try:
            snap_window = float(plan.get("sfx_snap_window") or _SFX_SNAP_WINDOW)
        except (TypeError, ValueError):
            snap_window = _SFX_SNAP_WINDOW
        snap_window = max(0.3, min(3.0, snap_window))

        beats_by_panel = {}
        if snap_mode == "visual":
            vbeats_state = state.get("visual_beats") or {}
            for k, vpath in enumerate(seg_videos or []):
                if k >= len(panel_durs) or not vpath:
                    continue
                try:
                    mt = os.path.getmtime(vpath)
                except OSError:
                    mt = 0
                rec = vbeats_state.get(str(vpath))
                if rec and rec.get("mtime") == mt:
                    beats = rec.get("beats") or []
                else:
                    beats = self._visual_beats(vpath)
                    vbeats_state[str(vpath)] = {"mtime": mt, "beats": beats}
                    state["visual_beats"] = vbeats_state
                    self._save_state(state_path, state)
                if beats:
                    beats_by_panel[k] = beats
            if beats_by_panel:
                self._emit_progress(
                    f"④c 视觉节拍：{len(beats_by_panel)} 段检测到画面变化"
                    f"（零截图/零视觉调用），音效将在 ±{snap_window:.1f}s 内吸附到最近节拍")
            else:
                self._emit_progress("④c 未检测到明显画面节拍，音效保留原时间")
        else:
            self._emit_progress("④c sfx_snap=none：音效保留原时间，不吸附画面节拍")

        # 1) 归一化候选事件（不立即合成，先做密度筛选，避免浪费）
        candidates = []
        for ev in raw:
            k = ev.get("_panel", -1)
            if not (0 <= k < len(panel_durs)):
                continue
            pdur = float(panel_durs[k] or 0)
            if pdur <= 0:
                continue
            rid = str(ev.get("recipe") or "").strip()
            if not is_recipe(rid):
                self._emit_progress(f"④c 音效配方不存在，跳过：{rid}")
                continue
            try:
                rel_at = float(ev.get("at") or 0)
            except (TypeError, ValueError):
                rel_at = 0.0
            # 面板内相对时间：落在段尾之外时收进最后 50ms，避免整段错位
            rel_at = max(0.0, min(rel_at, max(0.0, pdur - 0.05)))
            orig_rel_at = rel_at
            # 吸附到最近的画面节拍（元素入场/镜头切换/动画起点）；可用 snap=false 关闭单条
            snap_ok = ev.get("snap", True)
            if isinstance(snap_ok, str):
                snap_ok = snap_ok.strip().lower() not in ("0", "false", "no", "none", "")
            snapped = False
            if snap_mode == "visual" and bool(snap_ok) and k in beats_by_panel:
                rel_at, snapped = self._snap_at(rel_at, beats_by_panel[k], snap_window)
            try:
                level = int(round(float(ev.get("level", 60))))
            except (TypeError, ValueError):
                level = 60
            level = max(0, min(100, level))
            try:
                priority = int(round(float(ev.get("priority", 50))))
            except (TypeError, ValueError):
                priority = 50
            priority = max(0, min(100, priority))
            params = ev.get("params") if isinstance(ev.get("params"), dict) else {}
            params = dict(params)
            if ev.get("seed") is not None and "seed" not in params:
                params["seed"] = ev.get("seed")
            candidates.append({
                "k": k,
                "panel": k + 1,
                "rel_at": round(rel_at, 3),
                "original_rel_at": round(orig_rel_at, 3),
                "at": round(float(panel_starts[k]) + rel_at, 3),
                "snapped": snapped,
                "level": level,
                "priority": priority,
                "recipe": rid,
                "params": params,
                "panel_dur": pdur,
            })

        # 2) 单段上限：短段最多 1 个，长段最多 3 个
        grouped = {}
        for c in candidates:
            grouped.setdefault(c["k"], []).append(c)
        kept, dropped_panel = [], 0
        for k, evs in grouped.items():
            cap = min(_SFX_PER_PANEL_CAP,
                      max(1, int(math.ceil(max(0.1, float(panel_durs[k])) / 10.0))))
            if len(evs) > cap:
                evs.sort(key=lambda c: (-c["priority"], c["at"]))
                dropped_panel += len(evs) - cap
                evs = evs[:cap]
            kept.extend(evs)

        # 3) 最小间隔：过密的两个事件保留 priority 更高的
        kept.sort(key=lambda c: (c["at"], -c["priority"]))
        spaced, dropped_gap = [], 0
        for c in kept:
            if spaced and c["at"] - spaced[-1]["at"] < _SFX_MIN_GAP:
                dropped_gap += 1
                if c["priority"] > spaced[-1]["priority"]:
                    spaced[-1] = c
                    while len(spaced) >= 2 and spaced[-1]["at"] - spaced[-2]["at"] < _SFX_MIN_GAP:
                        if spaced[-1]["priority"] > spaced[-2]["priority"]:
                            spaced.pop(-2)
                        else:
                            spaced.pop()
            else:
                spaced.append(c)

        # 4) 密度目标区间已在入口按成片时长算好（target_min / target_max）
        dropped_density = 0
        if target_max > 0 and len(spaced) > target_max:
            spaced.sort(key=lambda c: (-c["priority"], c["at"]))
            dropped_density = len(spaced) - target_max
            spaced = spaced[:target_max]
            spaced.sort(key=lambda c: c["at"])

        # 5) 生成/复用资产（只对最终保留的事件合成）
        assets_state = state.get("sfx_assets") or {}
        events, redo, reuse = [], 0, 0
        for c in spaced:
            k, rid, params = c["k"], c["recipe"], c["params"]
            key = self._h({"recipe": rid, "params": params})
            rec = assets_state.get(key)
            if (not force) and rec and self._ok_file(rec.get("path")):
                path = rec["path"]
                reuse += 1
            else:
                out = str(base / "sfx" / f"{rid.replace('.', '_')}_{key}.wav")
                self._emit_progress(
                    f"④c 音效生成：{rid}（第 {k + 1} 段 {c['rel_at']:.2f}s）...")
                r = self._dispatch("sfx", recipe=rid, output_path=out,
                                   project=proj, params=params)
                if not r.success:
                    self._emit_progress(f"④c 音效失败（跳过）：{r.content[:120]}")
                    continue
                path = r.details.get("output_path", out)
                assets_state[key] = {"path": path, "recipe": rid, "params": params}
                state["sfx_assets"] = assets_state
                self._save_state(state_path, state)
                redo += 1

            events.append({
                "path": path,
                "at": c["at"],
                "level": c["level"],
                "recipe": rid,
                "panel": c["panel"],
                "rel_at": c["rel_at"],
                "original_rel_at": c.get("original_rel_at"),
                "snapped": bool(c.get("snapped")),
            })

        failed = len(spaced) - len(events)
        info = {
            "density": density,
            "target_min": target_min,
            "target_max": target_max,
            "candidates": len(candidates),
            "actual": len(events),
            "dropped": dropped_panel + dropped_gap + dropped_density + failed,
            "snap_mode": snap_mode,
            "snap_window": snap_window,
            "snapped": sum(1 for e in events if e.get("snapped")),
        }
        return events, redo, reuse, info

    # ─── patch（微调） ───
    def _parse_patch(self, patch) -> dict:
        if isinstance(patch, dict):
            return patch
        if isinstance(patch, str):
            s = patch.strip()
            if s.startswith("```"):
                s = s.strip("`")
                s = s.split("\n", 1)[1] if "\n" in s else s
            try:
                d = json.loads(s)
                return d if isinstance(d, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _apply_patch(base_plan, patch) -> dict:
        import copy
        plan = copy.deepcopy(base_plan)
        panels = plan.get("panels") or []
        for k, v in patch.items():
            if k == "panels" and isinstance(v, dict):
                for idx_str, fields in v.items():
                    try:
                        idx = int(idx_str) - 1   # 1-based（用户口中的"第几段"）
                    except Exception:
                        continue
                    if isinstance(fields, dict) and 0 <= idx < len(panels):
                        panels[idx].update(fields)
            else:
                plan[k] = v
        plan["panels"] = panels
        return plan

    def _resolve_character(self, value: str) -> Path | None:
        """把「项目名 / 目录 / 文件路径」都收敛成角色参数文件。"""
        raw = (value or "").strip()
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = Path(self.cwd) / raw
        if p.is_dir():
            p = p / "character.json"
        elif not p.exists() and p.suffix != ".json":
            candidate = Path(self.cwd) / "video_work" / raw / "character.json"
            if candidate.exists():
                p = candidate
        return p if p.exists() else None

    # ─── 执行蓝图（逐项签名：支持微调/续做，只重做改动处） ───
    def _execute_plan(self, plan: dict, output_path: str, project: str, speaker: str,
                      speech_rate: int, force: bool, state_path: Path,
                      cinematic_count: int = _CINEMATIC_DEFAULT,
                      character: str = "") -> ToolResult:
        panels = [p for p in plan.get("panels", []) if isinstance(p, dict)]
        if not panels:
            return ToolResult.fail("蓝图缺少 panels")
        # 开场钩子最低画面时长：让状态与蓝图 md 也反映执行时的 10 秒下限。
        _apply_hook_min_duration(plan)
        canvas = plan.get("canvas") or {}
        W = int(canvas.get("width", 1920)); H = int(canvas.get("height", 1080)); FPS = int(canvas.get("fps", 30))
        style = plan.get("style", "")
        proj = project or "director"
        base = Path(self.cwd) / "video_work" / proj
        (base / "panels").mkdir(parents=True, exist_ok=True)

        # 用户素材先做存在性检查（在旁白等花钱的步骤之前）：找不到就直接如实失败。
        missing = []
        for i, p in enumerate(panels):
            if str(p.get("engine", "")).lower() != "footage":
                continue
            src = str(p.get("video") or "").strip()
            sp = None
            if src:
                sp = Path(src) if Path(src).is_absolute() else Path(self.cwd) / src
            try:
                ok_file = bool(sp and sp.exists() and sp.stat().st_size > 0)
            except OSError:
                ok_file = False
            if not src or not ok_file:
                missing.append(f"第 {i + 1} 段 → {src or '(未填 video)'}")
        if missing:
            return ToolResult.fail(
                "找不到用户提供的视频素材：\n" + "\n".join(missing)
                + "\n请把素材放进项目文件夹（或修正蓝图里的 video 路径）后重跑。")

        # 状态：不再因"蓝图变更"整片重置；改由各步的逐项签名决定重做范围
        state = {} if force else self._load_state(state_path)
        state["plan"] = plan
        state["output_path"] = output_path

        # 定妆资产：蓝图里有人物时，先用 character_sheet 让用户确认，再把参数带进来。
        # 这里只负责把它固化到项目目录，续跑时不必再传。
        char_src = self._resolve_character(character) or self._resolve_character(state.get("character") or "")
        char_file = base / "character.json"
        if char_src and char_src.resolve() != char_file.resolve():
            state["character"] = str(char_src)
            try:
                char_file.write_text(char_src.read_text(encoding="utf-8"), encoding="utf-8")
                self._emit_progress(f"定妆：已载入角色参数（{char_src.name}）")
            except Exception as e:
                self._emit_progress(f"角色参数读取失败：{e}")
        self._character_sha = ""
        if char_file.exists():
            try:
                self._character_sha = self._h(json.loads(char_file.read_text(encoding="utf-8-sig")))
            except Exception:
                self._character_sha = ""

        # 影视级预算：本地规则；默认每支片 1 段，用户可改 0/2/3。
        # 超出预算的 cinematic 段先用 3D 渲染（blender 是 cinematic 的 backup），3D 失败再降级 HTML。
        cine_budget = self._cine_count(cinematic_count)
        cine_have = self._count_cinematic(plan)
        self._emit_progress(f"⓪ 影视级预算：本次 {cine_budget} 段（默认 1，0=不用）")
        if cine_have < cine_budget:
            self._emit_progress(
                f"[导演] 蓝图只有 {cine_have} 段 cinematic，少于预算 {cine_budget}；"
                f"如需更多，请用 brief + cinematic_count={cine_budget} 重新设计蓝图")

        # 音色/语速是"项目级"设定：首次确定后写入 state，之后微调/续做一律沿用。
        # （主 LLM 微调时常常漏传 speech_rate，被默认值填成 0 → 旁白缓存键整体失效 → 旁白全量重配、
        #   时长随之变化 → 画面也跟着全片重渲。记住这套设定即可根治"微调变成重做"。）
        if force or not state.get("speaker"):
            state["speaker"] = (speaker or self.default_speaker or "").strip()
        if force or state.get("speech_rate") is None:
            state["speech_rate"] = int(speech_rate or 0)
        speaker = state["speaker"]
        speech_rate = int(state["speech_rate"])
        self._save_state(state_path, state)

        # 同步一份蓝图 md（反映本次"实际要执行"的蓝图，用户随时可查）
        self._write_blueprint_md(plan, proj, budget_text=self._cine_budget_text(cine_budget))

        narrations = [str(p.get("narration", "") or "").strip() for p in panels]

        # ② 旁白：逐句缓存（key=文案+音色+语速），只重配改动的句子；偏移在此重算
        voice_cache = state.get("voice_cache") or {}
        # 音色归一：缺省 speaker 归到默认音色，避免"这次没传 speaker"导致缓存整体失效、全部重配
        eff_speaker = (speaker or self.default_speaker or "").strip()
        narr_redo = narr_reuse = 0
        seg_by_panel, cum = {}, 0.0
        for i, _ in enumerate(panels):
            t = narrations[i]
            if not t:
                continue
            key = self._narr_key(t, eff_speaker, speech_rate)
            seg = voice_cache.get(key)
            if seg and self._ok_file(seg.get("audio_path")):
                narr_reuse += 1
                self._emit_progress(f"② 旁白第 {i + 1} 段未变，复用")
            else:
                narr_redo += 1
                self._emit_progress(f"② 旁白第 {i + 1} 段{'重配' if seg else '生成'}...")
                res = self._dispatch("narration", segments=[{"text": t}], project=proj,
                                     output_dir=str(base / "voice" / key),
                                     speaker=speaker, speech_rate=speech_rate)
                if not res.success:
                    return res
                s0 = (res.details.get("segments") or [{}])[0]
                seg = {"text": t, "audio_path": s0.get("audio_path"),
                       "duration": float(s0.get("duration") or 0), "words": s0.get("words", [])}
                voice_cache[key] = seg
                state["voice_cache"] = voice_cache
                self._save_state(state_path, state)
            seg_by_panel[i] = {
                "text": t, "audio_path": seg.get("audio_path"),
                "duration": float(seg.get("duration") or 0), "words": seg.get("words", []),
                "offset": round(cum, 3),
            }
            cum += float(seg.get("duration") or 0)
        if seg_by_panel:
            self._emit_progress(f"② 旁白就绪：{len(seg_by_panel)} 段，总时长 {round(cum, 3)}s")

        # ③ 画面：逐面板签名，只有签名变化才重渲染
        total = len(panels)
        saved_panels = state.get("panels") or []
        while len(saved_panels) < total:
            saved_panels.append({})
        cine_used = 0
        cine_downgraded = 0
        seg_videos, seg_audios = [], []
        panel_sigs = []
        panel_redo = panel_reuse = 0
        panel_durs = []
        # 全片风格档案：同片所有 styled 段共用，避免逐段各自成风
        guide = _style_guide(plan)
        self._current_guide = guide
        for i, p in enumerate(panels):
            engine = str(p.get("engine", "opendesign")).lower()
            if engine == "remotion" and i != 0:
                self._emit_progress(
                    f"[导演] 第 {i + 1} 段 remotion 只允许第一段，降级为 HTML 动画")
                engine = "opendesign"
            visual = str(p.get("visual", "") or p.get("narration", "") or "").strip()
            seg = seg_by_panel.get(i)
            dur = (seg.get("duration") if seg else None) or float(p.get("seconds") or 8)
            # 开场钩子最低画面时长：除 cinematic（6/10 秒）与 footage（素材原长）外，
            # 第一段画面至少 10 秒。旁白可以短于 10 秒——剩余画面留白（无旁白/字幕），
            # 且第二段从 10 秒处开始，旁白与字幕时间轴不受影响。
            if i == 0 and engine not in ("cinematic", "footage"):
                try:
                    dur = max(float(dur or 0), _HOOK_MIN_SECONDS)
                except (TypeError, ValueError):
                    dur = _HOOK_MIN_SECONDS
            # 标题包装只对支持的引擎生效（opendesign/manim 自带排版，叠蒙版会挡住正文）
            ov = p.get("overlay") if (isinstance(p.get("overlay"), dict) and engine in _OVERLAY_ENGINES) else None
            # styled 段：全片风格档案进签名，换画风只重做这一段
            psig = self._panel_sig(p, engine, dur, W, H, FPS, style, narrations[i],
                                   overlay=ov, style_guide=guide)
            panel_sigs.append(psig)

            prev = saved_panels[i] or {}
            if (not force) and prev.get("sig") == psig and self._ok_file(prev.get("video")) \
                    and not prev.get("embed_failed") and not prev.get("intro_failed"):
                panel_reuse += 1
                self._emit_progress(f"③ 画面 第 {i + 1}/{total} 段未变，复用")
                seg_videos.append(prev["video"])
                if isinstance(p.get("intro"), dict) and prev.get("audio"):
                    # 复用时要用上次裁到"钩子画面长度"的旁白；否则人声会压进 intro
                    seg_audios.append(prev["audio"])
                    panel_durs.append(_probe_dur(prev["video"]) or dur)
                    hd = float(prev.get("hook_dur") or 0)
                    if seg and hd > 0:
                        seg["audio_path"] = prev["audio"]
                        seg["duration"] = round(hd, 3)
                        seg["words"] = [w for w in (seg.get("words") or [])
                                        if float(w.get("endTime") or 0) <= hd + 1e-6]
                else:
                    # 有旁白用（本次的）旁白；没有旁白才回落到该段缓存的原声。
                    seg_audios.append(((seg or {}).get("audio_path") or prev.get("audio") or ""))
                    panel_durs.append(max(_probe_dur(prev["video"]) or dur,
                                          float((seg or {}).get("duration") or 0)))
                # 复用的影视级段不消耗本次额度（此前已生成过），故不计入预算
                continue

            if engine == "cinematic":
                if cine_used >= cine_budget:
                    cine_downgraded += 1
                    self._emit_progress(
                        f"[导演] 影视级预算已排满（{cine_budget} 段），第 {i + 1} 段改用 3D 渲染"
                        "（cinematic 的 backup，失败再退 HTML 动画）")
                    engine = "blender"
                    # 3D 不自带蒙版包装：标题/说明交给画面内的短标注。
                    ov = None
                    if i == 0:
                        dur = max(float(dur or 0), _HOOK_MIN_SECONDS)
                    psig = self._panel_sig(p, engine, dur, W, H, FPS, style, narrations[i],
                                           overlay=ov, style_guide=guide)
                    panel_sigs[i] = psig
                else:
                    cine_used += 1
            out_seg = str(base / "panels" / f"seg_{i:02d}_{engine}.mp4")
            panel_redo += 1
            self._emit_progress(
                f"③ 画面 第 {i + 1}/{total} 段（{_panel_engine_label(p, engine)}）生成中...")
            result = self._produce_panel(engine, p, visual, dur, out_seg, style, W, H, FPS,
                                         proj, seg, index=i, force=force)
            if not result.success:
                result, engine = self._degrade(i, p, visual, dur, base, style, W, H, FPS,
                                               proj, seg, engine, result, force=force)
            if not result.success:
                self._save_state(state_path, state)
                return ToolResult.fail(f"第 {i + 1}/{total} 段制作失败：{result.content}")
            vpath = result.details.get("output_path", out_seg)
            # 降级后按【实际产出引擎】重算签名：否则签名仍记着原引擎，
            # 续做时会命中复用、把降级产物当成原引擎产物，再也不会重试原引擎。
            if engine not in _OVERLAY_ENGINES:
                ov = None
            psig = self._panel_sig(p, engine, dur, W, H, FPS, style, narrations[i],
                                   overlay=ov, style_guide=guide)
            panel_sigs[i] = psig
            # 该段音频：有旁白用旁白；没有旁白时，用户素材保留原声（合成层只认独立音频轨）。
            seg_audio = (seg or {}).get("audio_path", "") if seg else ""
            if engine == "footage" and not seg_audio:
                seg_audio = (result.details or {}).get("audio_path", "") or ""
            # 可选「标题/蒙版包装」：仅当该段引擎支持且填了 overlay 才做（不写死，由导演决定）
            if ov and str(ov.get("title", "")).strip():
                out_ov = str(base / "panels" / f"seg_{i:02d}_title.mp4")
                self._emit_progress(f"③ 画面 第 {i + 1}/{total} 段：叠加 蒙版+标题 包装...")
                r2 = self._dispatch("title_overlay", input_video=vpath, output_path=out_ov,
                                    title=str(ov.get("title", "")),
                                    subtitle=str(ov.get("subtitle", "") or ""),
                                    accent=ov.get("accent") or "#ffffff",
                                    position=ov.get("position") or "upper",
                                    reveal_ratio=ov.get("reveal_ratio"),
                                    align=ov.get("align"), fps=FPS)
                if r2.success:
                    vpath = r2.details.get("output_path", out_ov)
                else:
                    self._emit_progress(f"③ 画面 第 {i + 1}/{total} 段标题包装失败（跳过）：{r2.content}")
            # 钩子之后接「标题入场」：原画面缩小 + 大标题 + Sigma 标签（固定模板，不走 LLM）
            intro_failed = False
            hook_dur = 0.0
            if isinstance(p.get("intro"), dict):
                self._emit_progress(
                    f"③ 画面 第 {i + 1}/{total} 段：标题入场（钩子画面缩小 + 大标题）...")
                try:
                    from .scripts.intro import concat_videos, render_intro
                    hook_only = vpath
                    intro_clip = render_intro(hook_only, p["intro"], base, i, W, H, FPS)
                    combined = str(base / "panels" / f"seg_{i:02d}_hook_intro.mp4")
                    concat_videos(Path(hook_only), intro_clip, Path(combined), W, H, FPS)
                    vpath = combined
                    # 钩子的声音（旁白或素材原声）只覆盖钩子画面；intro 是静音转场
                    hook_dur = _probe_dur(hook_only) or 0.0
                    seg = seg_by_panel.get(i)
                    audio_path = str((seg or {}).get("audio_path") or seg_audio or "")
                    audio_dur = _probe_dur(audio_path) if audio_path else 0.0
                    if hook_dur > 0 and audio_path and audio_dur > hook_dur + 0.02:
                        dst = base / "voice" / f"seg_{i:02d}_hook_clamp.wav"
                        from skills.compose_video.scripts.renderer import _exact_audio
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        _exact_audio(audio_path, hook_dur, str(dst))
                        seg_audio = str(dst)
                        if seg:
                            seg["audio_path"] = str(dst)
                            seg["duration"] = round(hook_dur, 3)
                            seg["words"] = [w for w in (seg.get("words") or [])
                                            if float(w.get("endTime") or 0) <= hook_dur + 1e-6]
                        self._emit_progress(
                            f"[导演] 第 {i + 1} 段钩子声音已裁到 {hook_dur:.1f}s，"
                            "避免压到标题入场")
                except Exception as e:
                    intro_failed = True
                    self._emit_progress(
                        f"[导演] 第 {i + 1} 段标题入场失败（保留钩子）：{str(e)[:180]}")
            saved_panels[i] = {"sig": psig, "engine": engine, "video": vpath,
                               "audio": seg_audio,
                               "embed_failed": int((result.details or {}).get("embed_failed") or 0),
                               "intro_failed": int(intro_failed),
                               "hook_dur": round(hook_dur, 3)}
            state["panels"] = saved_panels
            self._save_state(state_path, state)
            seg_videos.append(vpath)
            seg_audios.append(seg_audio)
            panel_durs.append(max(_probe_dur(vpath) or dur, float((seg or {}).get("duration") or 0)))

        # 定长画面音画等长：影视级 6/10 秒、Remotion 钩子（≥10 秒）、用户素材=素材原长，
        # 旁白**不得超过**画面（能少不能多）。
        # 旁白一旦长于画面，合成会为画面补末帧 → 成片结尾"卡在最后一帧"（像视频卡住）。
        # 这里把超长旁白裁到画面长度，并同步修正时长/字级时间戳，保证字幕与时间轴不错位。
        # 引擎以 saved_panels[i] 的**实际**引擎为准（降级后的段按 opendesign 处理）。
        _fixed_len_engines = ("cinematic", "remotion", "footage")
        for i, _p in enumerate(panels):
            sp = saved_panels[i] or {}
            eng = str(sp.get("engine", "")).lower()
            if eng not in _fixed_len_engines:
                continue
            seg = seg_by_panel.get(i)
            clip = _probe_dur(sp.get("video")) or 0.0
            if not seg or clip <= 0:
                continue
            narr = float(seg.get("duration") or 0)
            if narr <= clip + 0.02:
                continue
            dst = base / "voice" / f"seg_{i:02d}_clamp.wav"
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                from skills.compose_video.scripts.renderer import _exact_audio
                _exact_audio(str(seg.get("audio_path") or ""), clip, str(dst))
            except Exception as e:
                self._emit_progress(
                    f"[导演] 第 {i + 1} 段（{_ENGINE_LABEL.get(eng, eng)}）旁白超长，裁剪失败：{e}")
                continue
            seg["audio_path"] = str(dst)
            seg["duration"] = round(clip, 3)
            seg["words"] = [w for w in (seg.get("words") or [])
                            if float(w.get("endTime") or 0) <= clip + 1e-6]
            if i < len(seg_audios):
                seg_audios[i] = str(dst)
            if i < len(panel_durs):
                panel_durs[i] = clip
            self._emit_progress(
                f"[导演] 第 {i + 1} 段（{_ENGINE_LABEL.get(eng, eng)}）旁白 {narr:.1f}s "
                f"超画面 {clip:.1f}s，已裁到画面长度（宁短勿长）")

        # 段间转场：plan.transition / plan.transition_seconds 为默认；panel.transition 可逐段覆盖。
        # 有转场的接缝会让相邻两段重叠 → 时间轴按 (段时长 - 该接缝转场时长) 累加，
        # 否则字幕/旁白会因"重叠缩短"整体错位（与合成层保持同一套重叠量）。
        base_tr = plan.get("transition")
        base_ts = plan.get("transition_seconds")
        joints = []
        for k in range(1, total):
            p = panels[k]
            ttype = p.get("transition")
            if ttype is None:
                ttype = base_tr
            tsec = p.get("transition_seconds")
            if tsec is None:
                tsec = base_ts
            spec = None
            if ttype and str(ttype).lower() not in ("none", "cut"):
                try:
                    d = float(tsec) if tsec is not None else 0.6
                except (TypeError, ValueError):
                    d = 0.6
                lim = min(panel_durs[k - 1], panel_durs[k]) * 0.9
                spec = {"type": str(ttype), "duration": max(0.05, min(d, lim))}
            joints.append(spec)

        # 有出向转场的段：把转场重叠的 t 加进该段的占用时长（画面在合成层补末帧撑长）。
        # 与合成层 renderer 的 target = max(画面长, 旁白长 + t) 用同一套公式，
        # 否则字幕时间轴会比旁白早，越到后面越偏。
        for k in range(total - 1):
            if not (k < len(joints) and joints[k]):
                continue
            narr_k = float(((seg_by_panel.get(k) or {}).get("duration")) or 0)
            if narr_k > 0 and k < len(panel_durs):
                panel_durs[k] = round(max(panel_durs[k], narr_k + float(joints[k]["duration"])), 3)

        # 字幕/旁白的时间基准 = 【视频时间轴】（按各段实际时长累加，并扣除转场重叠），
        # 而不是"只累加有旁白的段"——否则遇到无旁白段 / 影视级段（时长≠旁白）就会整体错位。
        _start = 0.0
        panel_starts = []
        for k in range(total):
            panel_starts.append(round(_start, 3))
            if k in seg_by_panel:
                seg_by_panel[k]["offset"] = round(_start, 3)
            step = panel_durs[k] if k < len(panel_durs) else 0.0
            if k < total - 1 and k < len(joints) and joints[k]:
                step -= joints[k]["duration"]
            _start += step
        timeline_dur = max(0.05, _start)
        sub_state = state.get("subtitle") or {}
        subtitle_ass = sub_state.get("ass", "")
        # 签名必须含"字级时间戳"：字幕是按 words 逐字排的，旁白若换了 take（时长或断句变了），
        # 只比文案+时长会误判为"未变"而复用旧 ass，导致字幕与旁白整体错位。
        sub_sig = self._h({
            "n": [[s.get("text"), round(float(s.get("duration") or 0), 2), s.get("offset"),
                   [[w.get("word"), round(float(w.get("startTime") or 0), 2),
                     round(float(w.get("endTime") or 0), 2)] for w in (s.get("words") or [])]]
                  for s in seg_by_panel.values()],
            "wh": [W, H],
        })
        if plan.get("subtitles", True) and seg_by_panel:
            if (not force) and sub_state.get("sig") == sub_sig and self._ok_file(subtitle_ass):
                self._emit_progress("④ 字幕未变，复用")
            else:
                self._emit_progress("④ 生成字幕...")
                r = self._dispatch("subtitle", segments=list(seg_by_panel.values()),
                                   output_path=str(base / "subtitles" / "film.ass"),
                                   width=W, height=H)
                if r.success:
                    subtitle_ass = r.details.get("ass_path", "")
                    state["subtitle"] = {"sig": sub_sig, "ass": subtitle_ass}
                    self._save_state(state_path, state)
                    self._emit_progress(f"④ 字幕完成：{r.details.get('count')} 行")
                else:
                    subtitle_ass = ""
                    self._emit_progress(f"④ 字幕失败（跳过）：{r.content}")
        else:
            subtitle_ass = ""

        # ④b 配乐（音乐组，可选）：蓝图写了 music 才生成；按"描述"签名缓存，未变则复用。
        # 失败不阻断成片（缺 Key / 网络异常时跳过配乐，其余照常合成）。
        music_spec = self._music_spec(plan)
        bgm_path = ""
        if music_spec:
            # v3：纯音乐提示词改成「器乐外壳 + 正面编曲」并由工具强制加，
            # 旧缓存里可能是带人声的版本，签名加版本号强制重配一次。
            msig = self._h({"prompt": music_spec["prompt"], "instrumental": True, "v": 3})
            m_state = state.get("music") or {}
            if (not force) and m_state.get("sig") == msig and self._ok_file(m_state.get("path")):
                bgm_path = m_state["path"]
                self._emit_progress("④b 配乐未变，复用")
            else:
                self._emit_progress(f"④b 配乐生成：{music_spec['prompt'][:40]}...")
                mr = self._dispatch("music_generate",
                                    prompt=music_spec["prompt"],
                                    output_path=str(base / "music" / "bgm.mp3"),
                                    project=proj, instrumental=True)
                if mr.success:
                    bgm_path = mr.details.get("output_path", "")
                    state["music"] = {"sig": msig, "path": bgm_path}
                    self._save_state(state_path, state)
                    self._emit_progress(f"④b 配乐完成：{mr.details.get('duration')}s")
                else:
                    bgm_path = ""
                    self._emit_progress(f"④b 配乐失败（跳过）：{mr.content}")

        # ④c 音效（音效组，程序合成）：面板内相对时间 → 成片时间轴；
        # 按密度档位（每分钟事件数）+ 单段上限 + 最小间隔做筛选，再按签名缓存资产。
        # 单个失败只跳过该音效，不阻断成片。
        sfx_events, sfx_redo, sfx_reuse, sfx_info = self._resolve_sfx_assets(
            plan, panels, panel_starts, panel_durs, seg_videos, timeline_dur,
            base, proj, state, state_path, force)
        if sfx_info.get("density") != "none" and (
                sfx_info.get("candidates") or sfx_info.get("target_min", 0) > 0):
            density_label = _SFX_DENSITY_LABEL.get(sfx_info["density"], sfx_info["density"])
            line = (f"④c 音效：{sfx_info['actual']} 个"
                    f"（{density_label}密度目标 {sfx_info['target_min']}~{sfx_info['target_max']}）")
            if sfx_info.get("dropped"):
                line += f"，裁掉/合并 {sfx_info['dropped']} 个"
            if sfx_info.get("snapped"):
                line += f"，{sfx_info['snapped']} 个吸附到画面节拍"
            if sfx_info["actual"] < sfx_info["target_min"]:
                line += "，偏少（可用 patch 追加）"
            self._emit_progress(line)

        # ⑤ 合成：签名=各段内容签名 + 字幕签名 + 转场 + 画布 + 配乐 + 音效；无变化才跳过
        comp_sig = self._compose_sig(panel_sigs, sub_sig, seg_videos, W, H, FPS, joints=joints,
                                     bgm=bgm_path, bgm_level=music_spec.get("level"),
                                     sfx=sfx_events)
        cst = state.get("compose") or {}
        final = cst.get("final", "")
        comp = {"duration": cst.get("duration"), "subtitle_burned": bool(subtitle_ass)}
        if (not force) and cst.get("sig") == comp_sig and self._ok_file(final):
            self._emit_progress("⑤ 成片未变，跳过合成")
        else:
            if not seg_videos:
                return ToolResult.fail("没有可合成的画面段")
            tr_n = sum(1 for j in joints if j)
            self._emit_progress(
                f"⑤ 合成：归一化 → {'转场装配' if tr_n else '拼接'} → 旁白"
                f"{' → 背景音乐' if bgm_path else ''}"
                f"{' → 音效 ' + str(len(sfx_events)) + ' 个' if sfx_events else ''} → 烧字幕 ..."
                + (f"（{tr_n} 处转场）" if tr_n else "")
            )
            res = self._dispatch("compose_video", output_path=output_path,
                                 scene_videos=seg_videos, scene_audios=seg_audios,
                                 subtitle_ass=subtitle_ass or None, transitions=joints or None,
                                 bgm=bgm_path or None,
                                 bgm_volume=int(music_spec.get("level", 30)),
                                 sfx=sfx_events or None,
                                 width=W, height=H, fps=FPS)
            if not res.success:
                self._save_state(state_path, state)
                return res
            final = res.details.get("output_path", output_path)
            comp = res.details
            state["compose"] = {"sig": comp_sig, "final": final,
                                "duration": comp.get("duration")}
            self._save_state(state_path, state)
            self._emit_progress("⑤ 合成完成")

        # ⑤b 片尾：按视频类型生成不同的「Sigma 制作」动画并追加（幂等，失败不影响成片）
        try:
            from skills.compose_video.scripts.sigma_outro import (
                DEFAULT_DURATION, append_outro, recipe_for_director)
            from skills.compose_video.scripts.renderer import probe_duration
            recipe = recipe_for_director(plan, saved_panels or panels)
            final = append_outro(final, recipe, DEFAULT_DURATION)
            comp["duration"] = round(probe_duration(final) or comp.get("duration") or 0, 3)
            state["compose"] = {"sig": comp_sig, "final": final,
                                "duration": comp.get("duration")}
            self._save_state(state_path, state)
            self._emit_progress(f"⑤b 片尾已追加（{recipe}，{DEFAULT_DURATION:.1f}s）")
        except Exception as e:
            self._emit_progress(f"[导演] 片尾生成失败（不影响成片）：{e}")

        # ⑥ 审查
        review_note = ""
        if plan.get("review", True) and self._ok_file(final):
            self._emit_progress("⑥ 收尾审查：随机截帧 + 字幕位置校验 ...")
            rv = self._dispatch("video_review", video_path=final,
                                subtitle_ass=subtitle_ass or None,
                                output_dir=str(base / "review"))
            if rv.success:
                review_note = "\n" + rv.content
                self._emit_progress("⑥ 审查完成")

        return ToolResult.ok(
            f"成片完成：{final}\n时长 {comp.get('duration')}s｜"
            f"{'已烧字幕' if comp.get('subtitle_burned') else '无字幕'}\n"
            f"本次：画面 重做 {panel_redo} / 复用 {panel_reuse} 段；旁白 重配 {narr_redo} / 复用 {narr_reuse} 句；"
            f"音效 {len(sfx_events)} 个（重做 {sfx_redo} / 复用 {sfx_reuse}）；"
            f"影视级 新增 {cine_used}/预算 {cine_budget} 段"
            + (f"（{cine_downgraded} 段超出预算改用 3D 渲染）" if cine_downgraded else "")
            + review_note,
            output_path=final,
            duration=comp.get("duration"),
            plan=plan,
            state_file=str(state_path),
            redone=panel_redo, reused=panel_reuse,
            cine_used=cine_used, cine_budget=cine_budget, cine_downgraded=cine_downgraded,
        )

    @staticmethod
    def _non_deliverable(res: ToolResult) -> bool:
        """引擎结果是否"不可交付"（示例内容 / 占位画面）。

        只认结果里的**通用事实标记**（is_demo / deliverable / placeholder_frames），
        不对具体引擎做特判——任何引擎只要如实上报这些标记就会被拦，
        从而把这个"假成功"转成失败、交给 _degrade 降级到别的引擎，
        绝不把示例或占位画面当成成片交付。

        注意：这只能拦"没画"和"画炸了"，拦不住"画歪了"（如把牛画成四不像）——
        那种结果既不报错也不占位，只能靠选型边界规避。
        """
        d = getattr(res, "details", None) or {}
        try:
            if int(d.get("placeholder_frames", 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
        return bool(d.get("is_demo")) or d.get("deliverable") is False

    def _produce_panel(self, engine, p, visual, dur, out_seg, style, W, H, FPS, proj, seg,
                       index: int = 0, force: bool = False):
        """面板产出（含可交付性闸门）：引擎"成功"但内容是示例/占位时转失败。

        引擎可能不报错却给出不可交付的内容（如返回示例片、或章节没盖满时间线导致整片占位）。
        这类结果必须转成 fail，上层才会触发降级链（换个引擎重做），而不是拿它交差。
        """
        res = self._produce_panel_raw(engine, p, visual, dur, out_seg, style, W, H, FPS,
                                      proj, seg, index=index, force=force)
        if res.success and self._non_deliverable(res):
            self._emit_progress(
                f"[导演] {_ENGINE_LABEL.get(engine, engine)} 返回示例/占位内容，视为失败并降级")
            return ToolResult.fail(
                f"{_ENGINE_LABEL.get(engine, engine)} 返回示例/占位内容（不可交付）：{(res.content or '')[:200]}",
                **(res.details or {}),
            )
        return res

    def _produce_panel_raw(self, engine, p, visual, dur, out_seg, style, W, H, FPS, proj, seg,
                           index: int = 0, force: bool = False):
        tool = _ENGINE_TOOL.get(engine, "opendesign_video")
        brief = visual if not (seg and seg.get("text")) else f"{visual}\n本段旁白：{seg.get('text')}"
        if engine == "styled":
            secs = float(dur or 0) or float(p.get("seconds") or 8)
            # 段级 styleGuide 可覆盖全片档案；两者都没有就让 styled 按内容自定
            guide = str(p.get("styleGuide") or "").strip() or self._current_guide
            # 人物只用已确认的定妆；没有定妆就不给人物（styled 会自己避开具象人体）
            char_file = Path(self.cwd) / "video_work" / proj / "character.json"
            return self._dispatch("styled_video", brief=brief, style_guide=guide,
                                  style_note=_style_note(p),
                                  duration=round(secs, 2), output_path=out_seg, project=proj,
                                  width=W, height=H, fps=FPS,
                                  character=str(char_file) if char_file.exists() else "")
        if engine == "cinematic":
            prompt = str(p.get("prompt") or visual).strip()
            # 影视级只能 6 或 10 秒：按旁白实测时长选"≥旁白"的最小档，尽量减少音画不等长
            bd = float(dur or 0) or float(p.get("seconds") or 10)
            seconds = 6 if bd <= 6 else 10
            return self._dispatch(tool, prompt=prompt, output_path=out_seg,
                                  duration=seconds, resolution="768P")
        if engine == "manim":
            # Manim 讲解：按旁白实测时长定长（工具会精确对齐时长/画布）
            secs = float(dur or 0) or float(p.get("seconds") or 8)
            return self._dispatch("manim_video", brief=brief, output_path=out_seg, project=proj,
                                  duration=round(secs, 2), style_prompt=style,
                                  fps=FPS, width=W, height=H)
        if engine == "blender":
            # 真 3D 渲染：产品外观/设备展示/场景/3D 文字
            secs = float(dur or 0) or float(p.get("seconds") or 5)
            return self._dispatch("blender_video", brief=brief, output_path=out_seg, project=proj,
                                  duration=round(secs, 2), style_prompt=style,
                                  fps=FPS, width=W, height=H,
                                  screen_html=str(p.get("screen_html") or "").strip() or None,
                                  screen_size=str(p.get("screen_size") or "").strip() or None)
        if engine == "footage":
            # 用户素材：只做画布规整，段长=素材原长（clip_seconds 可截取）。
            src = str(p.get("video") or "").strip()
            if not src:
                return ToolResult.fail("footage 面板缺少 video（用户提供的视频文件路径）")
            try:
                clip_seconds = float(p.get("clip_seconds") or 0)
            except (TypeError, ValueError):
                clip_seconds = 0.0
            return self._dispatch("footage_video", input_path=src, output_path=out_seg,
                                  width=W, height=H, fps=FPS,
                                  fit=p.get("fit") or "contain",
                                  clip_seconds=max(0.0, clip_seconds),
                                  keep_audio=self._as_bool(p.get("keep_audio", True)))
        if engine == "amap":
            mp = p.get("map")
            if not isinstance(mp, dict) or not mp:
                return ToolResult.fail("amap 面板缺少 map 对象（kind/title/route/region/world）")
            secs = float(dur or 0) or float(p.get("seconds") or 6)
            return self._dispatch("map_video", spec=mp, output_path=out_seg,
                                  duration=round(secs, 2), width=W, height=H, fps=FPS)
        if engine == "remotion":
            char_path = Path(self.cwd) / "video_work" / proj / "character.json"
            hook = p.get("hook") if isinstance(p.get("hook"), dict) else {}
            hook_type = str(hook.get("type") or "").strip().lower()
            template = _REMOTION_TEMPLATE_BY_HOOK.get(hook_type, "title")
            text = str(hook.get("text") or "").strip() or visual
            kicker = str(_HOOK_TYPES.get(hook_type, {}).get("label") or "OPENING HOOK")
            sub = (str(hook.get("why") or "").strip()
                   or (str(seg.get("text") or "").strip() if seg else ""))
            ov = p.get("overlay") if isinstance(p.get("overlay"), dict) else {}
            accent = str(ov.get("accent") or "").strip()
            # 开场钩子按导演给的时长渲染（默认至少 10 秒）；不再压回 3~5 秒。
            secs = max(3.0, float(dur or 0) or float(p.get("seconds") or 10))
            return self._dispatch("remotion_hook_generate",
                                  mode="auto", template=template, text=text,
                                  kicker=kicker, sub=sub, accent=accent,
                                  hook_type=hook_type, style=style,
                                  duration=round(secs, 2), output_path=out_seg,
                                  width=W, height=H, fps=FPS,
                                  character=str(char_path) if char_path.exists() else "")
        if engine == "webpage":
            w = p.get("web")
            if not isinstance(w, dict) or not w:
                return ToolResult.fail("webpage 面板缺少 web 对象（应由设计阶段生成并回填）")
            secs = float(dur or 0) or float(p.get("seconds") or 8)
            seg_words = (seg or {}).get("words") or []
            return self._dispatch(
                "webpage_video", web=w, output_path=out_seg, project=proj,
                duration_s=round(secs, 2),
                narration=str((seg or {}).get("text") or ""),
                narration_words=seg_words, style_prompt=style,
                fps=FPS, width=W, height=H,
            )
        # opendesign：可选把 blender/manim/amap 作为版面图层嵌进去
        requested = len(_panel_embeds(p))
        assets_dir, embeds_meta = None, []
        if requested:
            assets_dir, embeds_meta = self._prepare_panel_embeds(
                p, index, out_seg, style, W, H, FPS, proj, dur, force=force)
        res = self._dispatch("opendesign_video", brief=brief, output_path=out_seg, project=proj,
                             duration_s=int(round(dur)), style_prompt=style,
                             with_images=bool(p.get("images")),
                             assets_dir=assets_dir, embeds=embeds_meta or None,
                             fps=FPS, width=W, height=H)
        # 有 embed 没渲染出来 / composer 没真正使用：标记本段不完整，
        # 下次续跑不要直接复用（否则永远缺这一层）。
        try:
            tool_failed = int((res.details or {}).get("embed_failed") or 0)
        except (TypeError, ValueError):
            tool_failed = 0
        if res.success and requested and (len(embeds_meta) < requested or tool_failed):
            try:
                res.details["embed_failed"] = (requested - len(embeds_meta)) + tool_failed
            except Exception:
                pass
        return res

    # ─── opendesign 内嵌特效：预渲染 → 帧雪碧图 → 交给 opendesign 当版面图层 ───
    def _prepare_panel_embeds(self, p, index: int, out_seg, style, W, H, FPS, proj,
                              dur, force: bool = False):
        """返回 (assets_dir, embeds_meta)。失败只跳过该 embed，不阻断整段。

        源片段放 <project>/embed_cache/<hash>/clip.mp4，雪碧图按 embed 指纹复用；
        每轮只把用到的 webp 复制进 <project>/embed_assets/seg_XX/，避免 assets 里堆源视频。
        """
        embeds = _panel_embeds(p)
        if not embeds:
            return None, []
        base = Path(out_seg).parent.parent
        cache_root = base / "embed_cache"
        assets_dir = base / "embed_assets" / f"seg_{index:02d}"
        # 本次重渲只带当前 embed；清掉上一版多出来的贴图，避免 composer 看到过期素材
        shutil.rmtree(assets_dir, ignore_errors=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        metas = []
        for j, e in enumerate(embeds):
            et = str(e.get("type") or "").strip().lower()
            if et not in _EMBED_TYPES:
                continue
            rect = e.get("rect") or [0, 0, 0, 0]
            try:
                x, y, rw, rh = (float(v) for v in rect)
            except (TypeError, ValueError):
                continue
            try:
                start = max(0.0, float(e.get("start") or 0))
                edur = float(e.get("duration") or 0)
            except (TypeError, ValueError):
                continue
            # 旁白实测时长可能和蓝图 seconds 不同：按本段实际时长收紧。
            # opendesign 收到的是 int(round(dur))，所以这里也按取整后的总长算，避免嵌入被片尾裁掉。
            room = float(int(round(float(dur or 0)))) - start
            if room < 0.8:
                self._emit_progress(
                    f"[导演] 第 {index + 1} 段嵌入 {et} 起点超出本段时长，跳过")
                continue
            edur = min(edur, room)
            if rw < 160 or rh < 90 or edur < 0.8:
                self._emit_progress(f"[导演] 第 {index + 1} 段嵌入 {et} 参数太小，跳过")
                continue

            brief = str(e.get("brief") or e.get("visual") or p.get("visual") or "").strip()
            spec = {
                "type": et, "brief": brief, "rect": [x, y, rw, rh],
                "start": round(start, 3), "duration": round(edur, 3),
                "map": e.get("map"), "screen_html": e.get("screen_html"),
                "screen_size": e.get("screen_size"), "prompt": e.get("prompt"),
                "mask": e.get("mask"), "style": style, "whf": [W, H, FPS],
                "erev": _ENGINE_REV.get(et, 0), "sheet_rev": _EMBED_SHEET_REV,
            }
            # blender 的屏内页面是外部文件：内容变了也要重渲，不能只看路径
            if e.get("screen_html"):
                try:
                    sp = Path(str(e["screen_html"]))
                    if not sp.is_absolute():
                        sp = Path(self.cwd) / sp
                    st = sp.stat()
                    spec["screen_html_file"] = [round(st.st_mtime, 3), st.st_size]
                except OSError:
                    spec["screen_html_file"] = [0, 0]
            key = self._h(spec)
            cache = cache_root / key
            sheet = cache / "sheet.webp"
            meta_path = cache / "meta.json"

            meta = None
            if (not force) and sheet.exists() and meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except Exception:
                    meta = None
            if meta is None:
                cache.mkdir(parents=True, exist_ok=True)
                clip = cache / "clip.mp4"
                ep = {"engine": et, "visual": brief, "seconds": edur}
                for k in ("map", "screen_html", "screen_size", "prompt"):
                    if e.get(k):
                        ep[k] = e.get(k)
                self._emit_progress(
                    f"[导演] 第 {index + 1} 段预渲染嵌入 {_ENGINE_LABEL.get(et, et)}"
                    f"（{edur:.1f}s）...")
                res = self._produce_panel(et, ep, brief, edur, str(clip), style,
                                          W, H, FPS, proj, None, index=index, force=force)
                if not res.success:
                    self._emit_progress(
                        f"[导演] 第 {index + 1} 段嵌入 {et} 渲染失败，跳过：{res.content[:160]}")
                    continue
                clip_dur = _probe_dur(clip) or edur
                meta = self._make_frame_sheet(clip, [x, y, rw, rh],
                                              min(edur, clip_dur), cache)
                if not meta:
                    self._emit_progress(f"[导演] 第 {index + 1} 段嵌入 {et} 转雪碧图失败，跳过")
                    continue
                meta.update({"type": et, "rect": [x, y, rw, rh],
                             "start": round(start, 3), "mask": e.get("mask")})
                try:
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
                except OSError:
                    pass

            name = f"seg_{index:02d}_e{j + 1}.webp"
            try:
                shutil.copy2(sheet, assets_dir / name)
            except OSError as exc:
                self._emit_progress(f"[导演] 第 {index + 1} 段嵌入素材复制失败：{exc}")
                continue
            item = dict(meta)
            item["file"] = name
            metas.append(item)
        if not metas:
            return None, []
        return str(assets_dir), metas

    def _make_frame_sheet(self, clip: Path, rect, dur: float, cache: Path):
        """mp4 → 帧雪碧图（webp）；返回 cols/rows/frames/fps/tile 元数据，失败返回 None。"""
        try:
            rw, rh = float(rect[2]), float(rect[3])
        except (TypeError, ValueError, IndexError):
            return None
        # 单帧目标尺寸：跟随嵌入矩形，capped 到 960×540，控制雪碧图总像素
        tw = int(min(max(rw, 160), 960))
        th = int(round(tw * rh / max(rw, 1)))
        if th > 540:
            tw = max(2, int(round(tw * 540 / th)))
            th = 540
        tw -= tw % 2
        th -= th % 2

        # 帧率：短镜头 30fps，长镜头降档；总帧数硬上限 180（解码内存可控）
        fps = 30 if float(dur) <= 5.0 else 24
        frames = max(2, int(round(float(dur) * fps)))
        while frames > 180 and fps > 16:
            fps -= 2
            frames = max(2, int(round(float(dur) * fps)))
        cols = min(10, max(1, int(math.ceil(math.sqrt(frames)))))
        rows = max(1, int(math.ceil(frames / cols)))
        # 雪碧图单边不超过 8000px（Chromium 图片解码/纹理限制）
        max_dim = 8000
        scale = min(1.0, max_dim / max(tw * cols, th * rows))
        if scale < 1.0:
            tw = max(2, int(tw * scale) // 2 * 2)
            th = max(2, int(th * scale) // 2 * 2)

        sheet = cache / "sheet.webp"
        ff = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [
            ff, "-y", "-loglevel", "error", "-i", str(clip),
            "-vf", f"fps={fps},scale={tw}:{th}:flags=lanczos,tile={cols}x{rows}",
            "-frames:v", "1", "-c:v", "libwebp", "-quality", "82", str(sheet),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except Exception as exc:
            self._emit_progress(f"[导演] 雪碧图生成失败：{exc}")
            return None
        if r.returncode != 0 or not sheet.exists() or sheet.stat().st_size <= 0:
            self._emit_progress(f"[导演] 雪碧图生成失败：{(r.stderr or '')[-160:]}")
            return None
        return {"cols": cols, "rows": rows, "frames": frames, "fps": fps,
                "tile_w": tw, "tile_h": th,
                "duration": round(frames / float(fps), 3)}

    def _degrade(self, i, p, visual, dur, base, style, W, H, FPS, proj, seg, engine, first_fail,
                 force: bool = False):
        """降级链：styled / manim / amap / blender → opendesign；cinematic → blender → opendesign。

        cinematic 的 backup 是 3D 渲染：影视级生成失败（或预算排满）时先用 blender 补一个
        有空间感/质感的 3D 画面，3D 也失败才退到 HTML 动画。
        返回 (结果, 实际产出引擎)：实际引擎要写回面板状态与签名，
        否则降级产物会被当成原引擎产物缓存住，续做时永不重试原引擎。
        opendesign 失败、或 footage（用户素材）失败则如实返回失败。"""
        # footage 不降级：用户明确指定了素材，用别的画面冒充会偏离需求；
        # 失败就如实报错（例如素材没放进项目文件夹），让用户补齐后重跑。
        order = {
            "manim": ["opendesign"],
            "cinematic": ["blender", "opendesign"],
            "styled": ["opendesign"],
            "remotion": ["opendesign"],
            "footage": [],
            "amap": ["opendesign"],
            "webpage": [],
            "blender": ["opendesign"],
            "opendesign": [],
        }.get(engine, ["opendesign"])
        last = first_fail
        for alt in order:
            self._emit_progress(f"[导演] 第 {i + 1} 段 {_ENGINE_LABEL.get(engine)} 失败，降级为 {_ENGINE_LABEL.get(alt)}")
            out_seg = str(base / "panels" / f"seg_{i:02d}_{alt}.mp4")
            # 开场钩子由 cinematic 降级后不再受 6/10 秒限制，仍需满足首段 ≥10 秒。
            alt_dur = dur
            if i == 0 and alt not in ("cinematic", "footage"):
                try:
                    alt_dur = max(float(dur or 0), _HOOK_MIN_SECONDS)
                except (TypeError, ValueError):
                    alt_dur = _HOOK_MIN_SECONDS
            last = self._produce_panel(alt, p, visual, alt_dur, out_seg, style, W, H, FPS, proj, seg,
                                       index=i, force=force)
            if last.success:
                return last, alt
        return last, engine

    # ─── 子部门调度 + 进度转发 ───
    def _dispatch(self, name: str, **kwargs) -> ToolResult:
        try:
            sub = self.skill_manager.get_tool(name)
        except Exception:
            sub = None

        def relay(ev):
            content = ev.get("content", "")
            if content:
                try:
                    self._emit_progress(f"[{name}] {content}")
                except Exception:
                    pass

        if sub is not None:
            try:
                sub.set_progress_callback(relay)
            except Exception:
                pass
        try:
            return self.skill_manager.dispatch(name, **kwargs)
        finally:
            if sub is not None:
                try:
                    sub.set_progress_callback(None)
                except Exception:
                    pass


__all__ = ["DirectorTool"]
