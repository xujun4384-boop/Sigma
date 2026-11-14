# styled_video —— 导演组的单段风格动画引擎（内部，Remotion）

> 只由 `director` 调度，不直接暴露给用户，也不提供"让用户选风格"的入口。
> 画风由导演按用户需求写进蓝图的 `styleGuide`，不再有固定风格库。

## 输入

| 参数 | 必填 | 说明 |
|---|---|---|
| `brief` | 是 | 这一段要讲什么 / 画面需求（导演会把该段旁白一起带上） |
| `style_guide` | 否 | 全片风格档案（导演写，同片各 styled 段共用）；为空时引擎按内容自定一套并保持一致 |
| `style_note` | 否 | 本段局部风格要求（更冷/更暗等） |
| `duration` | 是 | 秒；一般等于该段旁白实测时长 |
| `output_path` | 是 | 输出 mp4 |
| `project` | 否 | 中间产物放 `video_work/<project>/styled/` |
| `width` / `height` / `fps` | 否 | 默认 1920×1080 / 30 |
| `character` | 否 | 已确认的定妆参数路径；这一段有人物时传入 |

## 怎么画

- 和 `lyric_mv` 的镜头走同一条路：模型直接写一个 Remotion 场景（`export const Shot1` + `BG` + `META`），
  只用一个 `<svg viewBox="0 0 1920 1080">`，所有运动由 `useE()` 的 `e.t` / `e.shotU` 驱动。
- 引擎用 `remotion_runtime` 的 `LyricMV` 组合、`plain` 模式渲染：不画歌词、章节、进度条。
- 一段超过 12 秒时，用 `<Sequence>` 切成 2~4 个镜头；每个镜头都要有可见运动。
- 可以画短标题/关键词/标签/数字/单字（≤12 字）；**不能画旁白/字幕原文**，底部 12% 是字幕安全区。
- 有人物时，人物只能来自已定妆的 `./char-hero`（`Character` / `CharacterSide` / `CharacterBack`），
  参数 `view/pose/armL/armR/headTurn/tilt/mood`；不要自己拼人体。

## 质量闸门

- 契约检查：静态禁用项、import 白名单、导出齐全、必须是 SVG 根。
- **真渲一帧（strict）**：崩了把报错原文回灌给模型重写，最多 2 次（`STYLED_REMOTION_TRIES` 可调）。
- 通过后才整段渲染；失败由导演组的降级链回退到 `opendesign`，不整片崩。

## 缓存

同一 `brief + styleGuide + styleNote + duration + 画布 + 角色参数` 命中签名时由导演组复用，
不重复渲染；换画风或换定妆只重做受影响的段。

## 边界

- 不负责旁白/字幕/音乐/合成。
- 不做"风格样片 / 用户选择"；风格由导演按用户需求决定。
- 与 `amap` 区分：真实地点/路线用 `amap`；styled 只画风格化插画（含虚构地图）。
