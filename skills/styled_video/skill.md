# styled_video —— 导演组的「14 选 1」风格动画引擎（内部）

> 只由 `director` 调度，不直接暴露给用户，也不提供“让用户选风格”的入口。
> 风格由导演组在蓝图里按每段内容决定。

## 输入

| 参数 | 必填 | 说明 |
|---|---|---|
| `brief` | 是 | 这一段要讲什么 / 画面需求（导演会把该段旁白一起带上） |
| `visual_style` | 是 | 14 种之一：`crayon` / `shadow` / `flat` / `ink` / `pixel` / `comic` / `whiteboard` / `hanzi` / `timeline` / `isometric` / `scale` / `infographic` / `map` / `exploded` |
| `duration` | 是 | 秒；一般等于该段旁白实测时长 |
| `output_path` | 是 | 输出 mp4 |
| `project` | 否 | 中间产物放 `video_work/<project>/styled/` |
| `width` / `height` / `fps` | 否 | 默认 1920×1080 / 30 |
| `shots` | 否 | linear 镜头数 2~5，默认 3；grid 模式忽略 |
| `layout` | 否 | `linear`（默认，现有切镜）/ `grid`（大画布分格跳格） |
| `grid` | 否 | 仅 grid：`{cols, rows, order, weights, moves}`；默认 2×2 等权重 |
| `with_images` | 否 | 是否允许引擎按需生图，**默认关**；导演组按面板 `images` 字段开启 |
| `max_images` | 否 | 本段最多生成几张图，默认 3 |

## 配图（引擎按需生图）

- LLM 在 `scenes.js` 里用 `MV.assets` 声明素材：
  `MV.assets = { "skyline": { prompt: "英文画面描述", size: "16:9" } };`
- `draw(e)` 里用 `e.drawImg("skyline", x, y, w, h, {mode:"cover"})` 绘制；返回 `false` 表示该图不可用，
  用图形兜底即可。
- 引擎按声明生成图片到 `video_work/<project>/styled/assets/`，渲染器把它们作为 `file://` 绝对地址
  注入页面（本地文件，无外链）。生图失败只跳过该张，不阻断渲染。
- **图片必须参与运动**：跟相机推拉、在画面里横移/缩放、或用 `e.layer` 做视差；
  禁止在整段里把图钉死不动。

## 产出

- 一段**无声** mp4；旁白、字幕、配乐、合成由导演组后续完成。
- 可以画短标题/关键词/标签/数字/单字（≤12 字，按风格的「文字」规则）；
  **不能画旁白/字幕原文**，底部 12% 是字幕安全区。
- 画面用 `lyric_mv` 的 stage 引擎（`plain` 模式：不画歌词、章节、进度条），
  按 `visual_style` 的完整规格写镜头；linear 写 2~5 个镜头，grid 写 1 个分格场景。
- 每个镜头/每一格都必须有可见运动；确定性渲染（禁止 Math.random / Date.now）。
- 渲染前过闸门（语法 / 运行时 / 确定性）。**首次失败后优先原地修补**：
  把当前代码 + 具体报错交给模型，只返回最小 `find/replace` 清单，应用到原文件后直接再过闸；
  修补无法应用、修补后语法错或调用失败时，才回退整篇重写。总共最多 3 次。
- 闸门通过后还会抽帧做一次**文字可读性检查**：视觉模型专门看标题/标签/数字是否看得清；
  对比度不足时同样优先原地修补 `e.drawText` 的颜色/描边/底板，修补后再过闸并复查，
  避免白字压浅底、字被背景吞掉。
- 修补记录：`work/llm/styled-repair-{k}.txt`（模型返回的修改清单）、
  `styled-patched-{k}.js`（应用后的代码），便于排查；补丁只输出改动，不重发整份文件。
- 同一 `brief + style + duration + 画布 + shots + layout/grid + 风格规格` 命中缓存时直接复用。

## 可选：grid 分格模式（不替代 linear）

默认 `layout=linear`，行为与以前完全一致：2~5 个镜头、分镜硬切。

`layout=grid` 是给“这一段有多个互不相关的画面”用的另一条路：

- 一张大画布（`cols*W × rows*H`）分格，camera 到点**瞬间跳格**，每格独立播放；
  格内可以推拉/横移。
- `grid` 字段：`cols`/`rows`（1~3，默认 2×2）、`order`（播放顺序，格号从 0 开始）、
  `weights`（每格时长权重）、`moves`（格内推拉，如 `{"1":{"zoom":1.14}}`；
  x/y 是相对格中心的偏移，只写 zoom 就围绕中心推）。
- grid 只写 **1 个 scene**：`camera(e)` 用 `e.camGrid(...)`，`draw(e)` 画整张大画布；
  当前格用 `e.cam.cell` 判断，格内动画用 `e.cam.segU`（切进来才从 0 开始）。
- 适用：2~6 个互不相关的画面/信息点（分镜故事板）；连续动作/情绪推进仍用 linear。
- 时间：整段仍是一条时间线，格与格之间由 `weights` 分配；总时长不变。

## 边界

- 不负责旁白/字幕/合成。
- 不做“风格样片 / 用户选择”；风格由导演组决定。
- 失败时由导演组的降级链回退到 `opendesign`（HTML 动画），不整片崩。
