---
name: lyric_mv
description: 把一首歌做成"卡点逐字歌词"的 MV 动画视频。支持两种音源（技能生成歌曲 / 用户指定音乐文件），自动测拍网格与逐字时间轴，由 LLM 自由创作画面与编导编排，逐帧确定性渲染出 mp4。
---

# lyric_mv —— 歌词 MV 制作

把「一首歌」变成「一条卡点 MV」。引擎持有契约（时间 / 拍 / 卡点 / 歌词 / 安全区 / 防闪 / 确定性渲染），
**画面与编排全部交给 LLM 自由创作**——引擎里没有固定演员表，也不做关键词匹配。

## 重要：走技能流程，不要自己写画面代码

主 LLM **不要绕过 `lyric_mv` 的 pipeline 手写或修改 `scenes.js` / `parts/*.tsx`**，
也不要在 pipeline 失败后自己写一段动画代码顶上。原因：

- pipeline 的每次调用都带着编导方案、视觉圣经、逐句上下文、前后批摘要和风格规定；
- 手写代码通常只看到当前报错，拿不到这些上下文，画面会突然换构图、换配色、换叙事主语，
  前后衔接直接断掉（实测：手工补的长间奏卡变成一封信在固定舞台上漂，故事没有延续）；
- 手工改动不在 `parts/` 的记录里，下一次重跑会被 pipeline 覆盖，或者留下前后不一致的两套代码。

正确做法：

1. 正常调用 `lyric_mv`，生成、过闸门、有界修复都交给 pipeline；
2. 失败时先看 `run.log` / `last_error.json`，把原因转成 `brief` 或参数调整，
   再用**同一个 `out_dir`** 重跑；已完成段会自动复用，不会从头再来；
3. 只有 pipeline 的有界修复也失败、且用户明确同意时才人工介入；
   人工改完必须落回 `parts/*.tsx` 或 `plan.json`，不要只改最终成片或 `generated/`；
4. 需要局部重跑时，仍然走 `lyric_mv` + 同一个 `out_dir`，让 pipeline 按签名只补缺的那一段；
   不要另写一套渲染脚本或另起一个输出目录。

## 断点续跑与产物保护（接手时先读这一节）

**同一个 `out_dir` 再调一次 `lyric_mv`，就是安全的续跑。**
不需要先检查、备份、复制目录，也不需要为了"保险"另起一个 `out_dir`——那样反而会丢掉全部已有产物。

### 复用规则

每个阶段都会把「输入签名 + 产物存在 + 上次通过」写进 `mv_state.json`，三者齐备才跳过：

| 阶段 | 产物 | 什么时候会重跑 |
|---|---|---|
| 音源 | `song.wav` | 换了 `audio` / `lyrics` |
| 拍网格 | `grid.json` | 换了歌曲 |
| 逐字对齐 | `timeline.json` | 换了歌曲 / 歌词 / `t0` / ASR 模型 |
| 模式 | `mode.json` | 显式传 `mode`，或强制重跑该段 |
| 编导 | `plan.json` | 改了 `brief`，或强制重跑该段 |
| 故事方向 / 蓝图 | `story.json` | status 不是 treatment/approved，或 `revise=true` |
| 视觉圣经 | `visual-bible.json` | 故事变了，或强制重跑该段 |
| 镜头表 | `shots.json` | 时间轴 / 编导方案 / 视觉圣经 / brief 变了（仅 performance） |
| 画面 | `parts/artist-shot-N.tsx` + `art/shots/shot-N.json` | 该镜缺失 / 代码哈希变了 / 强制重跑画面 |
| 渲染 | `mv.mp4` | `timeline` / `render-plan` / 音轨 / `look.json` 变了 |

### 镜头级断点

- 每画完一镜立刻真渲一帧校验，通过后把代码写进 `parts/`，把「代码哈希 → 通过」写进 `art/shots/shot-N.json`；
- 续跑时逐镜比对哈希：通过的直接复用，**只重画缺的、没过的那几镜**；
- 单镜渲帧失败会先**原样重渲一次**排除环境抖动（沙箱杀进程、打包超时），仍失败才回炉重画；
- 某镜最终仍画不出来时**不会让整片停摆**：写入 `missing-shots.json`，该时间段落引擎兜底黑场，其余照常渲染。

### 什么会覆盖产物

只有这些情况会丢弃已有结果：

- 强制重跑某一段（`--force scenes` / `--force plan` …），只影响点名的那一段；
- 删除 `parts/`、`art/`、`scenes.tsx`、`render-plan.json`、`mv_state.json`；
- 换 `out_dir`；改 `brief` / 歌词 / 音源（签名变化）。

其余情况下，已有产物只会被读取，不会被覆盖。

### 常见误判（不要再花时间排查这些）

- **「跑了几十分钟没输出」不是卡死**：镜头是并行生成的，模型在写代码；整片渲染期还有每 30 秒的心跳。不要中途 kill。
- **「上次失败了」不等于产物作废**：先看 `run.log`、`last_error.json`、`missing-shots.json`，同一个 `out_dir` 直接重跑即可，已通过的部分会复用。
- **「想换模型重画画面」**：强制重跑画面段即可；角色是跨镜头独立资产，要一起换需 `LYRIC_MV_CHAR_REDO=1`。
- **「怕手工改动被覆盖」**：只有改在 `parts/*.tsx`、`plan.json` 或 `story.json` 里的内容才参与后续渲染，直接改 `mv.mp4` 或 `generated/` 没有意义。

## 工具

`lyric_mv`（唯一入口）。编排细节全部走 pipeline，不暴露子步骤。

| 参数 | 必填 | 说明 |
|---|---|---|
| `lyrics` | 二选一 | 歌词全文（含 `[Verse]`/`[Chorus]` 结构标签）。**不传则视为纯音乐/器乐**，画面按拍走，不出歌词 |
| `audio` | 否 | **用户指定的音乐文件路径**（mp3/wav/m4a/flac 任意 ffmpeg 可解格式）。不传则由本技能生成歌曲 |
| `brief` | 否 | 编导要求（题材、情绪、开场形式、禁止项…）。会作为硬约束传给 LLM 编导 |
| `out_dir` | 否 | 产物目录，默认 `cwd/lyric_mv_out` |
| `t0` | 否 | 首句人声起始秒数（人工锚点，ASR 失准时用） |
| `synth_prompt` | 否 | 生成歌曲时的音乐风格提示（仅在未给 `audio` 时生效） |
| `mode` | 否 | MV 模式：`auto`（默认，LLM 判断）/ `narrative` 叙事 / `performance` 表演 / `typographic` 文字 |
| `stage` | 否 | 叙事型阶段：`auto` / `pitch` 故事方向 / `treatment` 故事蓝图 / `produce` 产出；其他模式忽略 |
| `story_choice` | 否 | 叙事型：从 pitch 进入 treatment 时指定候选方向 id |
| `revise` | 否 | 叙事型：用户说换一批/不满意时传 `true`，强制重新生成故事方向或蓝图；修改意见写进 brief |
| `type_style` | 否 | 文字类：强制字效风格（`brutalist` / `editorial` / `neon` / `handwritten` / `pixel` / `kinetic`）；不传由 LLM 选 |
| `with_images` | 否 | 是否按段落生成 AI 氛围底图（只做背景层，主体仍由 canvas 画）。默认 false，需要已配置图片生成 Key |
| `max_images` | 否 | 最多生成几张段落底图，默认 6 |
| `force` | 否 | 强制重跑某几段（逗号分隔）：`plan` / `story` / `bible` / `shotlist` / `scenes` / `render`。只影响点名的段，其余照常复用 |
| `look` | 否 | 渲染外观（自由对象）：`{"pixel": {"block": 4, "colors": 24}}` = 引擎级像素化（低分辨率 + 调色板量化，整帧含字幕）；不传 = 原始高清。只影响渲染，不改画面代码 |

## 两种音源

| 场景 | `audio` | `lyrics` | 卡点方式 |
|---|---|---|---|
| 全自动 | 不传 | 传 | 生成歌曲 → 测拍 → ASR 强制对齐逐字 |
| **用户自带歌** | 传文件 | 传 | 测拍 → ASR 强制对齐逐字（**和全自动等价**） |
| 用户自带 + 无歌词 | 传文件 | 不传 | 测拍 → ASR 自动转写，用识别结果当歌词（标注"转写"来源） |
| 纯器乐 | 任意 | 不传 + `brief` 说明 | 只测拍；画面按拍与段落走，无歌词层 |

用户自带音乐的卡点与自动生成**完全同一条链路**——拍网格和逐字时间轴都是由音频本身实测出来的，
与实际音源无关。

## 画风：不预设

**没有风格库，也没有风格参数。** 画面怎么画由画面作者自己判断：

- 编导只负责故事、段落、配色母题、开场与收尾，不指定画法；
- 视觉圣经只写**故事事实**（角色造型、场景、时间与光线、跨镜头一致性），不写笔触/材质/画风名；
- 画面作者可以自己先造角色和道具组件再拍镜头，也可以用任意 Remotion 能力直接画。

需要统一感时，写进 `brief`（例如"温暖、克制、黄昏暖调"），而不是选一个风格 id。

## MV 模式（先判断，再分流）

三种模式决定整条产线的流程，不只是风格：

| 模式 | 讲什么 | 歌词层 | 视觉单位 | 当前状态 |
|---|---|---|---|---|
| narrative 叙事 | 整片讲一个完整故事，由 LLM 与用户共同拟定，不被歌词逐句约束 | **照常显示** | 故事节拍 / 镜头 | 已可用 |
| performance 表演 | 舞台、表演者、情绪与段落推进 | 照常显示 | 段落 / 逐句 | 已可用 |
| typographic 文字 | 文字本身就是画面，没有独立字幕层 | 关闭 | 拍 / 词 / 字 | 已可用 |

判断放在逐字对齐之后、风格样片之前。由 LLM 综合歌词、brief、BPM、段落结构判断，结果写 `mode.json`。

- `confidence < 0.7`、两种模式都说得通、或 brief 与歌词冲突时，pipeline 停下并输出 `MODE_CHOICES=...`；
  主 LLM **必须调用 `ask_user`** 让用户选，不能替用户决定。
- 用户选完，带 `mode=<id>` + 同一个 `out_dir` 重跑，流程从断点继续。
- 用户显式指定 `mode` 时不询问。
- `mode.json.lyrics_layer` 是派生字段：narrative / performance = `full`，typographic = `none`
  （文字类由画面自己写字，不再叠加独立字幕层；叙事型保留完整歌词层）。
- 表演型在视觉圣经里强制生成 `stage`（地点/背景/光位/轴线）与 `continuity`（允许/禁止哪些变化）；
  画面提示词会注入固定舞台规则：只允许机位、景别、灯光、道具、动作变化，
  禁止换场景、换主体、换服装。视觉圣经版本升到 v3，旧产物会重建一次。
- 文字类不生成插画视觉圣经、不生成氛围底图、也不跑插画风格样片；改为生成 `type-plan.json`
  （字效方案），并把 `plan.plain` 置为 true，由画面代码自己画字。
- 叙事型不按歌词句出画面，而是走「故事方向 → 故事蓝图 → 视觉圣经 → 镜头表 → MV.shots」；
  歌词层照常显示，镜头按绝对时间覆盖全片，可跨多句歌词。

## 文字类（typographic）

文字类使用独立字效风格库 `type_styles.py`：
粗野主义 / 杂志排版 / 霓虹字 / 手写手账 / 像素字 / 动态字。
字体全部使用系统本地字体，不联网。

流程：

1. 编导方案照常生成（配色只作参考）；
2. `type-emphasis.json`：LLM 逐行挑 0~2 个连续片段作为「点睛」（转折/结论/反问/称呼/动作结果等语义重心），
   校验必须是原文子串；样片与全片共用同一份标注，保证主次一致。失败不拦片，画面按句自行判断；
3. 没指定 `type_style` 且 `samples=true`：先筛 2~4 种字效，各渲 10 秒样片（带重点字）→ 对比页 →
   `ask_user` 让用户选；选完带 `type_style=<id>` 重跑（同 out_dir）；
4. `type-plan.json`：LLM 选字效风格 + 全片排版系统（字体/字重/字距/行距/对齐/配色/每段 energy/规则）；
   用户明确指定风格时传 `type_style`，LLM 只负责排版与配色；
5. `plan.plain = true`：关闭引擎歌词层、章节与进度条，画面代码自己画字；
6. 每句一条画面，用 `e.line.text` / `e.chars` / `e.sung` 逐字驱动排版；
   重点片段按风格放大/换色/加色块，其余字保持基准字号与颜色；
7. 审查重点：可读性、阅读速度、遮挡、出框、重复叠字。

注意：文字类不跑插画样片，改为 2~4 种字效样片；也不生成 AI 氛围底图，
`with_images` 在文字类下会被忽略。

## 叙事型（narrative）

叙事型不按歌词句出画面，而是先和用户把故事定下来：

1. `stage=pitch`：LLM 出 2~3 个故事方向（logline/主角/世界/三幕），写 `story.json` status=pitch；
   pipeline 停下并输出 `STORY_PITCH=...`，主 LLM 必须 `ask_user` 让用户选；
   用户都不满意时带 `revise=true` + 修改意见（写进 brief）重出。
2. `stage=treatment` + `story_choice=<id>`：把选中的方向扩写成故事蓝图与镜头表
   （acts/beats/shots，shots 2~8 秒、连续铺满全片），status=treatment；
   停下输出 `STORY_TREATMENT=...`，主 LLM 再 `ask_user` 确认；
   要换一版蓝图带 `stage=treatment, revise=true` + 修改意见。
3. `stage=produce`：生成叙事视觉圣经（主角/配角/场景/连续性/配色/母题），
   再按镜头分批写 `MV.shots`，过闸门、抽查、渲染。

关键约定：

- `MV.shots` 按绝对时间覆盖全片，可以跨多句歌词；引擎优先用 shots，没有 shots 时才走逐句 scenes。
- 歌词层照常显示（`lyrics_layer=full`），镜头代码不要画歌词，构图避开 `e.lyricBox`。
- 镜头内动画用 `e.shotU` / `e.shotT` / `e.shotDur`，不要用 `e.i` / `e.line` 做分镜。
- 闸门会校验 shots 是否从 0 连续铺满到歌曲结束，空档/重叠会被拦下。
- 视觉圣经强制角色/场景/服装跨镜头一致；故事优先 1 主角、2~4 场景。
- 叙事型不跑插画风格样片、不生成氛围底图；视觉风格由编导方案决定。
- 截图自查的低分帧会按时间映射到镜头批，只重写这几批并重新过闸、复核；失败自动还原。

## 引擎契约：LLM 写什么

LLM 产出两个文件：

### 1. `plan.json` —— 编导编排（可被用户 `brief` 覆盖）

```json
{
  "title": "歌名",
  "opening":  { "form": "标题先出|画面先出|黑场切入|直接入唱", "titleAt": "居中|左上|右下|底部",
                "subtitle": "副标题/署名", "exit": "淡出|推开|擦除" },
  "palette":  { "base": "#141A2E", "accent": "#E9A63B", "mood": "夜/暖/冷/纸质" },
  "sections": [ { "name": "Verse 1", "theme": "这一段的视觉母题", "motion": "推进/静止/漂移" } ],
  "interludes": [ { "afterLine": 11, "idea": "这段间奏讲什么" } ],
  "ending":   { "form": "标题回扣|定格|字幕|渐黑", "credit": "出品/词曲署名" },
  "lyricStyle": "vertical",
  "chrome": { "section": "zh", "sectionAt": "top-left", "progress": "top" }
}
```

`lyricStyle` 是全局默认版式（可省略，缺省按 `band`）；画风不预设，`brief` 里用户明确要求的部分
**优先级高于** LLM 的自选，冲突时以 brief 为准。

### 歌词版式与呈现（引擎负责画，LLM 只选不写）

编导按**段落**指定版式和是否逐字（KTV）。语速快的段落应当整句出现，逐字来不及读：

```json
"lyricStyles": {
  "Verse 1": {"style": "band",   "karaoke": false},
  "Chorus":  {"style": "shrink", "karaoke": true}
},
"lyricKaraoke": true
```

- `karaoke: false` = 整句一起出现（不做逐字填色）；字/秒 ≥ 2.6 的段落应这样；
- 没写 `lyricStyles` 的段落回落到 `plan.lyricStyle`（全局默认），并按字/秒自动判断是否整句；
- 版式决定歌词占用矩形，画面主体必须避开 `e.lyricBox`。

| 值 | 形态 | 适合 |
|---|---|---|
| `band` | 居中横幅，整句可见 + 逐字变金 + 进度线 | 跟唱友好，最稳 |
| `shrink` | 逐字缩着蹦出（未唱不显示） | 走心，情绪往里收 |
| `bounce` | 逐字从上方落下 | 轻快、少年感 |
| `vertical` | 右侧竖排、楷书、逐字淡入 | 国风、古意、安静 |
| `bottom` | 贴底居中、逐字蹦出 | 大场面，天地全让出来 |
| `walk` | 小球踩字往前走，压到的字下沉回弹 | 童趣、轻松 |
| `brush` | **左侧竖两排、行楷、落笔墨晕** | 书法、怀旧、思亲 |

**画面框**由 `plan.chrome` 指定（不写＝英文标签 + 顶部进度条）：

| 键 | 取值 |
|---|---|
| `section` | `en` / `zh`（主歌/副歌/桥段…）/ `hide` |
| `sectionAt` | `top-left` / `top-right` / `bottom-left` / `bottom-right` |
| `progress` | `top` / `bottom` / `hide` |

**画面主体必须避开歌词占的矩形**。引擎把它放在 `e.lyricBox = [x0, y0, x1, y1]`：

| 版式 | 占用区 | 形状 |
|---|---|---|
| `band` / `shrink` / `bounce` | `[0, 96, 1280, 206]` | 顶部横条 |
| `walk` | `[0, 52, 1280, 206]` | 顶部横条（含小球高度） |
| `vertical` | `[1080, 130, 1280, 520]` | 右侧一列 |
| `bottom` | `[0, 546, 1280, 664]` | 底部横条 |
| `brush` | `[80, 130, 340, 520]` | 左侧两列 |

人脸、手、关键道具、标题都不要压进这块；背景渐变可以铺满。引擎会自动在歌词区叠蒙版保证可读，但那只是兜底——**构图要先让开**。

### 2. `scenes.js` —— 画面代码（自由发挥）

```js
/* 正片：每句歌词一条，数量必须等于歌词行数 */
MV.scenes = [
  { bg: "#141A2E", draw(e) {
      e.sh.circle(900, 420, 120, e.P.gold);
      e.drawText(e.line.text, 640, 620, { size: 30, fill: e.P.paper });
  } },
  /* ... */
];

/* 片头 / 间奏 / 尾奏：按小节铺排（bars），用于承载叙事 */
MV.intro      = [ { bars: 2, bg: "#0E1428", draw(e){ /* 标题、署名 */ } } ];
MV.interludes  = [ { afterLine: 11, cards: [ { bars: 4, bg: "#1D2540", draw(e){/* 间奏叙事 */} } ] } ];
MV.outro      = [ { bars: 3, bg: "#0E1428", draw(e){ /* 回扣 */ } } ];
MV.filler     = { bg: "#101828", draw(e){ /* 兜底：没有任何卡覆盖时的画面 */ } };
```

### `draw(e)` 里的环境对象

| 字段 | 含义 |
|---|---|
| `e.t` `e.dt` | 秒；`e.dt` 恒为 1/FPS |
| `e.i` `e.n` `e.line` | 当前句序号 / 总数 / 该句对象（含 `text` `start` `end` `chars`） |
| `e.kind` | `scene` / `intro` / `interlude` / `outro` / `gap` |
| `e.u` `e.cardT` | 当前卡内的 0~1 进度 / 卡内已过秒数 |
| `e.beat` `e.beatIdx` `e.bar` `e.phase` | 连续拍位置 / 第几拍 / 第几小节 / 拍内相位 0~1 |
| `e.strong` | 每 4 拍一次的强拍包络（0~1） |
| `e.pulse(k)` | 每拍衰减包络，k 越大越干脆（**卡点主用**） |
| `e.hit(every)` | 是否踩在每 `every` 拍的拍点上 |
| `e.sung` | 该句已唱到第几个字（-1 = 还没开口），**做逐字叙事用** |
| `e.rnd(seed)` `e.hash(seed)` | 确定性伪随机（**禁止 `Math.random`**） |
| `e.clamp/lerp/seg/easeOut/easeIn/easeIO/back/elastic/wave` | 缓动与插值 |
| `e.P` | 调色板；`e.hexA(c,a)` 加透明度；`e.isDark(c)` |
| `e.sh.rect/circle/ring/tri/line/speckle` | 常用形状 |
| `e.actor(opts)` | 人物：一套骨架 + 四种皮肤。`style` 取 `crayon/shadow/flat/ink`；`x,y` 是脚底中心，`dir` 朝向（1 右 / -1 左），`pose` 取 `stand/walk/run/bow/hug/reach`，`phase` 一般传 `e.t*1.6`，`hug` 0~1 叠加拥抱；`hair`、`cloth`、`dress` 微调外观；`pixelate`（≥2）把人物附近连同背景按像素块重采样，给像素风格用。**要画人就用它，不要用圆/矩形自己拼人形** |
| `scene.camera(e)` | 可选：返回 `{x,y,zoom}`，整镜用一台摄影机；不写 = 固定机位（默认） |
| `e.camPath(keys)` | 摄影机关键帧：`u`=0~1，`cut:true` 硬切；返回 `{x,y,zoom,seg,segU}` |
| `e.camGrid(opts)` | 大画布分格跳格：`{cols,rows,cellW,cellH,order,weights,moves}`；`e.cam.cell`/`segU` 驱动当前格 |
| `e.screen(fn)` | 屏幕空间绘制（标题/标签/颗粒，不受 camera 缩放影响） |
| `e.layer(depth,fn)` | 视差层：0=锁屏，1=主世界，>1 前景移动更快 |
| `e.sprite(name,x,y,opts)` | 序列帧素材（离线烘焙的透明 PNG） |
| `e.drawText(s,x,y,opts)` `e.drawParagraph(...)` `e.measure(s,size)` | 文本（**自动实测字宽、支持 maxW 缩字号**） |
| `e.bg(hex,{vignette,glow})` | 背景（含静态光晕） |
| `e.dark` | 当前背景是否深色，用于自动选文字颜色 |

引擎自动叠加（LLM 不必管）：KTV 逐字跳字、歌词带安全蒙版、章节标签、进度条。

### 硬性约束（校验器会拦）

1. **确定性**：`draw` 必须是 `t` 的纯函数。禁止 `Math.random` / `Date.now` / `performance.now` / 外部状态累积 / `setTimeout` / rAF。校验器会对同一 `t` 渲染两次并比对像素哈希。
2. **不要画歌词**：歌词所占的矩形是引擎的。别写死坐标，读 `e.lyricBox`（`[x0,y0,x1,y1]`）
   拿当前版式的位置，画面主体避开它——`brush` 在左、`vertical` 在右、`bottom` 在底、其余在顶部横条。
   短标题、标签、数字、关键词**可以写**（`e.drawText`，≤12 字，写成什么样见风格的「文字」规则）；
   但不要重复歌词原文、不要做字幕、不要把文字放进歌词带。
3. **禁止整帧亮度脉动**：节拍只能用**位移/形变/缩放**表达。全画面明暗往复＝闪，观感极差，且会被出片验收拦下。
4. **`MV.scenes.length` 必须等于歌词行数**；`intro`/`interludes`/`outro` 的每张卡必须给 `bars`。
5. **歌词空档（>2 小节）必须有间奏卡**，用叙事填满，不允许留静态空画面。

## Remotion 引擎（`engine=remotion`，默认）

画面从 canvas `draw(e)` 换成 **React 组件**，其余阶段（音源/拍网格/逐字/模式/编导/视觉圣经/故事）完全不变。

- 引擎实现：`skills/remotion_runtime`（共享 Remotion 4.0.536，依赖已离线安装）。
- 画面作者：`scripts/remotion_artist.py`（开放模式，pipeline 在 `engine=remotion` 时直接调用）。
  流程：**自动分镜 → 主角定妆（读确认过的角色参数）→ 并行拍镜（每镜真渲一帧）→ 整片闸门**。
  - 分镜：编导给了 `story.shots` 就用它（逐镜的 action / 景别会原样传给画面作者）；
    否则按「段落边界 + 目标时长」自动切（`LYRIC_MV_SHOT_SECONDS`，默认 12s）。
  - 定妆：角色不再由画面作者现画。调用顺序是
    **`character_sheet(spec=<主角>, cast=[{role, spec}...], project="<项目名>")` → 用户在画布上一次确认整组 →
    `lyric_mv(..., character="video_work/<项目名>/characters.json")`**。
    角色是参数化骨架（体型系数 / 配色 / 发型 / 服装），每个角色一个模块（`char-<role>.tsx`），
    镜头统一从 `./char-cast` 导入：主角 `Hero`、配角 `FriendA` 等，正面/侧面/背面/坐姿/表情是同一个人的同一套几何。
    不传 `character` 时读 `<out_dir>/art/characters.json`，再退回 `art/character.json`；都没有则停下提示先定妆。
    参数改了会自动重出定妆图并让镜头重渲；参数没改则复用。
  - 配角：视觉圣经的 `cast` 数组是建议（role / name / hair / outfit / colors / note）。
    定妆时按它给每个配角填一份 spec，和主角一起传给 `character_sheet` 的 `cast`；
    没有 `cast` 或不需要配角时只定主角。镜头表会给每一镜标注 `cast`（出场角色 role）。
  - 镜头：**画完一镜立刻真渲一帧（strict）**，崩了带着报错重画；通过后静帧存 `art/shots/shot-N.png`
    并记录代码哈希，续跑时直接复用通过的镜头。
  - 镜头文件落在 `<out_dir>/parts/artist-shot-N.tsx`，注册表 `shot-N`，导出 `ShotN` + `META`。
  - 一镜可跨多句；渲染用 `render-plan.json` 的 `shots`（绝对时间覆盖），不按行索引。
  - 单镜反复失败不拖垮整片：记 `missing-shots.json`，该处落兜底黑场，其余照常渲染。
- 契约：每个组件用 `useE()` 拿环境对象（字段与 canvas 版 e 一致：`t/beat/pulse/sung/lyricBox/P…`），
  模块导出 `META = {镜头编号: {bg: '#底色'}}`；引擎据此决定歌词深浅与蒙版方向。
- 分工不变：**歌词层、KTV、章节、进度条、颗粒、暗角全部由引擎画**，画面代码只画世界层，也不能画歌词。

### 人物与图层：交给画面作者

引擎**不**替画面决定人在哪、谁挡住谁。人物、推镜、前景遮挡全部写在同一个 `<svg>` 的图层顺序里：

```tsx
// 整组角色统一入口：主角 Hero，配角按定妆时的 role 命名（FriendA / FriendB …）
import {Hero, FriendA} from './char-cast';
import {Actor} from '../../ui/Actor';                                  // 可选：带歌词避让的放置器

<Actor Character={Hero} x={820} y={980} s={1.15} flip />
<FriendA x={1240} y={980} />
```

- 角度按这一镜的叙事选：要情绪和眼神给人脸，要空间和方向给侧身，人物真的离开才用背面。
- 人可以有，也可以没有：角色造型是参考、不是出场清单。纯环境、物体、终端、群像远景不必画人，
  按 `story.shots` 的 `action` / `cast` / 景别来定。标题、黑场、前景遮挡要不要盖住人，
  取决于它画在人之前还是之后。
- `Actor` 只是工具：返回纯 `<g>`，跟随场景自己的相机变换；只在「头被歌词压住」时收缩/让位。
- 背面视图（`HeroBack` / `FriendABack`）在定妆阶段一并产出，背对镜头的镜头直接用它。
- **每个角色只能用对应的导出名**：不要把 `Hero` 复制成配角；没定妆的人不要画；这一镜不需要的角色不要出现。
- 闸门只拦「一定会静默出事」的问题：HTML 标签嵌在 SVG 里、缺 `<svg>` 根、缺导出。
- 闸门（比 canvas 多一层编译期）：
  1. 静态：禁用项（`Math.random`/`Date.now`/`window`/`document`/定时器/外链/CSS 动画）+ import 白名单；
  2. 编译：`tsc --noEmit`，错误按文件映射回镜头时刻；
  3. 运行时：`remotion still` + `strict`（崩溃直接失败，不兜底），报错带 `t=`；
  4. 确定性：同一帧渲两次，4×4 降采样容差比对。
- 渲染：`render_mv.py`（bundle 一次 → renderMedia → ffmpeg 混音轨），断点续做按段复用。
- 不注入任何预设画风：画法由画面作者自己判断（编导只管故事与基调）。
- 截图自查（5·5）在 Remotion 引擎下暂未接入（闸门已含运行时与确定性校验），`review.json` 不会产出。

## 流程

```
[0] 环境自检 ── ffmpeg / node / playwright / ASR venv
[1] 音源准备 ── 生成歌曲 或 接纳用户文件（统一转 wav / 取时长 / 分段信息）
[2] 拍网格   ── 自相关估 BPM → 二维优化相位 → PLL 精修（全部实测，不假设）
[3] 逐字对齐 ── whisper 转写 + 歌词先验做单调对齐（DP）；无歌词则自动转写
[3.4] 模式判断 ── LLM 判断 narrative / performance / typographic，写 mode.json
                └ 低把握 → 停，输出 MODE_CHOICES → ask_user → 带 --mode 重跑
                ├ typographic → 重点标注 → 字效方案/样片 → 文字画面（plain，关闭歌词层）
                └ narrative → 故事方向 → 故事蓝图 → 视觉圣经 → 镜头画面（歌词层保留）
[4] 编导     ── LLM 出 plan.json（开场/标题/段落主题/配色/间奏/收尾），brief 覆盖
[4T] 字效样片 ── typographic 且未指定 type_style：先逐句标重点 → 2~4 种字效 × 10 秒 → 对比页 → ask_user
[4.5] 视觉圣经 ── performance：LLM 出 visual-bible.json（视觉主体/角色/舞台/连续性/配色弧线/母题/构图/运动），后面每一批照它画
[4.5T] 字效方案 ── typographic：LLM 出 type-plan.json（字效风格/字体/排版/配色/每段 energy），plan.plain=true 关闭歌词层
[4.5N] 故事方向/蓝图 ── narrative：pitch → ask_user → treatment → ask_user，story.json（故事 + acts/beats + shots）
[4.5B] 叙事视觉圣经 ── narrative produce：主角/配角/场景/连续性/配色/母题 → visual-bible.json
[4.6] 段落底图 ── 仅 performance 且 with_images=true：每段一张 AI 氛围底图 → assets/sec_*.png，只做背景层
[5] 画面     ── performance/typographic：逐句 scenes.js；narrative：按镜头写 MV.shots（绝对时间覆盖，可跨多句）
[5.5] 截图自查 ── 抽 8 帧交给视觉模型审（模型不支持看图则自动跳过）
                └ 低分帧 → 按歌词行（叙事型按镜头时间）定位到批次 → 只重写那几批 → 重新过闸 → 复核
[6] 校验闸门 ── 语法 → 运行时 → 确定性 → 覆盖度 → 安全区
                └ 整体闸门失败时：按失败时刻定位到「某一批 / 卡片」，有上限地重写后重过闸门
[7] 渲染     ── 逐帧 seek(t) 截图 → ffmpeg 混流（失败自动重试一次）
[8] 出片验收 ── 帧间亮度跳变（防闪）
```

每段记录「输入签名 + 产物存在 + 验收通过」，三者齐备才跳过 → **可断点续做**。
整链 30~60 分钟量级（歌曲 2~3 分钟、ASR 5~8 分钟、画面生成/修复、渲染 8 分钟）；
画面段有独立的修复预算（默认 3 轮 / 30 分钟 / 24 次调用），不会无限重试。

> Remotion 引擎下 [5]/[6] 的实际行为：**逐镜生成、逐镜真渲一帧校验**；
> 通过即落 `parts/` + `art/shots/`，失败当场带报错重画；个别镜头几轮后仍失败会记入
> `missing-shots.json` 并继续，不再等整片凑齐后一次性判坏。

## 可选：段落 AI 氛围底图（`with_images`）

- 生成时机：视觉圣经之后、写画面前；每个段落一张（`sec_0..sec_n`），落 `<out_dir>/assets/`，写入 `plan.json.assets`。
- 提示词由三部分组成：完整风格规格（配色/线条/质感/光/构图）+ 视觉圣经（主角/母题/角色档案）+ 该段主题与情绪；
  统一追加「无文字 / 无 logo / 无真人正脸」负向约束。
- 画面里只能用 `e.drawImg("sec_i", ...)` 当背景/氛围层；主体、人物与叙事仍由 canvas 和 `e.actor` 画，
  并且必须让底图参与运动（视差/横移/缩放），不能整段钉死。
- 未配置图片 Key、单张生成失败都只跳过该图，不影响成片；换风格或换段落会作废旧底图。
- 已经生成过底图的产物，重跑时会继续复用（保持画面一致）；要回到纯 canvas 请换 `out_dir`，
  或删掉 `plan.json` 里的 `assets` 并重跑画面段。
- 画面签名包含底图 key：开/关底图、增删段落图都会触发对应画面重写。

## 截图自查 → 有界修复

- `review.json` 记录每个抽帧的 score / issues / fix。
- score ≤ 4 的帧会按时间映射回歌词行，再定位到所属批次（每批 6 句）；默认最多重写 1 批，
  其余批次与卡片全部复用，避免整片重跑。
- 重写时把 issues 原文回灌给模型；重写后重新组装并重新过闸门。失败会还原原画面，
  不会把已经通过的片子改坏。
- 修复后复核写 `review-after.json`；可用 `LYRIC_MV_REVIEW_MAX_BATCHES`、`LYRIC_MV_REVIEW_FLOOR`
  调整成本上限，`--no-review-repair` 可让自查只出报告、不回灌修复。

## 闸门与已知坑

| 坑 | 机制 |
|---|---|
| LLM 写的画面代码抛错 → 整片红屏 | `seek` 内 try/catch + `window.__mvError` 探针；校验器抽时刻必查 |
| `Math.random` 导致逐帧不可复现、重渲结果不同 | **确定性校验**：两次都从 0 顺序走到该时刻截帧，4×4 降采样后按容差比对（与 opendesign 同一口径） |
| 整帧闪 | 引擎不提供整帧亮度原语；出片后 `flicker` 验收（p99 跳变阈值） |
| 整体闸门失败后直接放弃、退回主 LLM | 按失败时刻定位到出错批次或卡片，自动重写并重过闸门；上限 **3 轮 / 30 分钟 / 24 次调用**，可用 `LYRIC_MV_REPAIR_ROUNDS`、`LYRIC_MV_SCENES_BUDGET`、`LYRIC_MV_SCENES_MAX_ASKS` 调整 |
| 漏写间奏 → 长空档只剩定画面 | 覆盖度校验：所有 >2 小节空档必须有间奏卡 |
| 正片条数与歌词行数不匹配 | 结构校验（写盘前，重试循环内） |
| 用户自带音乐格式杂 | 统一经 ffmpeg 转 wav；时长/采样率归一 |
| whisper 输出繁体导致匹配率骤降 | 内置 t2s 转换 |
| ASR 被伴奏压住、首句错位 | 命中率门槛 + `vocal_start` 交叉验证；**`t0` 人工锚点兜底** |
| 逐字时间跨行串味 / 被拉长十几秒 | 行内插值 + 夹在本行区间 + 行尾封顶；断言逐字时间必须落在本行内 |
| 渲染中途崩 | 按帧区间分块，记录已完成块，续做只补缺块 |
| 依赖缺失 / 模型下载被墙 | 环境自检；venv 自举并锁定 `HF_ENDPOINT`、关闭 Xet |

## 通用性准则

- **不硬编码内容**：段落结构、BPM、拍相位、首句位置、角色、配色全部由输入推导或由 LLM 创作。
- **不做关键词匹配**：歌词的情感与分段交给 LLM 判断，代码里不出现"如果出现某个词就画某个东西"。
- **引擎只管契约，不管内容**：引擎里没有"学校/妈妈/老师"这类题材实体；换一个题材不必改引擎。
- **失败要显式**：任何闸门不通过都报**具体原因**并给出可执行的下一步，不静默降级。

## 交付物

```
<out_dir>/
  lyrics.txt  song.mp3/wav  grid.json  timeline.json
  mode.json   plan.json   visual-bible.json
  story.json          # 可选：叙事型的故事方向/蓝图/镜头表
  type-plan.json      # 可选：文字类的字效方案（字体/排版/配色/每段 energy）
  type-emphasis.json  # 可选：文字类逐句重点片段（idx / text / picks / why）
  style-shortlist.json  # 可选：样片阶段的 2~4 个候选及理由
  samples/            # 可选：候选风格的 10 秒样片与各自 timeline/plan/scenes
  assets/             # 可选：with_images 生成的段落氛围底图 sec_*.png
  review.json         # 可选：截图自查结果（模型不支持看图时不存在）
  review-after.json   # 可选：自查修复后的复核结果

  # Remotion 引擎（默认）
  parts/artist-shot-N.tsx   # 每镜源码（续跑复用依据）
  parts/registry.json       # 镜头注册表
  art/shots/shot-N.png      # 每镜通过校验时的静帧
  art/shots/shot-N.json     # 每镜「代码哈希 → 通过」记录
  render-plan.json          # 时间 → 组件映射（含每段歌词版式）
  missing-shots.json        # 可选：最终没画出来的镜头（该处为兜底黑场）

  # canvas 引擎（engine=canvas）
  scenes.js  scenes.js.md（编导说明，便于用户改）

  mv.mp4
  mv_state.json       # 各阶段签名/验收，支持续做
  run.log             # 全量日志
  last_error.json     # 可选：未捕获异常时的 traceback
  llm/                # 每次模型调用的提问与原始输出（排错用）
```

样片对比页写到**项目工作目录**：`style-samples-<时间戳>-<hash>.html`（不是 out_dir，Sigma 只监听项目目录里的新 html）。
