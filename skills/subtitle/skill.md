# subtitle - 字幕组（单行 · 底部锚定 · 与旁白同步）

**把旁白的字级时间戳转成"一次一行、锚定画面底部"的字幕**，产出 `.ass`（自带样式）/`.srt`。

## 解决旧字幕的三个问题
| 旧问题 | 根因 | 本组做法 |
|---|---|---|
| 位置"中间靠下" | 烧录用 `force_style` 的 `MarginV/FontSize` 被 libass 按**默认 PlayRes(384×288)** 解释，换算到 1080p 底距≈20.8% | 生成**自带 `PlayResX/Y=视频尺寸`** 的 ASS，`Alignment=2`（底部居中）+ `MarginV≈6%H`，底部锚定 |
| 一次显示几行 | 一条字幕塞进一整句 → libass 自动换行成多行、整块上移盖住画面 | 按**标点/字数切分成一行一条**，ASS `WrapStyle=2`（禁止换行） |
| 尾行只剩 1~2 字（还会把数量词拆开，如 `2000\|万`） | 纯贪心装箱：填满即断，无回看 | 断行规则改为**句末标点必断、句内标点在整行够长时才断**，末尾再加**孤字护栏**（行不足 3 字时从上一行回填） |
| 与旁白不同步 | — | 每行起止**直接取自旁白字级时间戳**（+段偏移），随读速逐行推进 |

## 职责边界
- **只做字幕**：切行、定时、样式、导出 `.ass`/`.srt`。
- **不做**：不合成、不烧录（由合成部门直接烧本组产出的 `.ass`，无需再传样式）；不生成旁白。
- 时间源唯一：`narration` 部门输出的 `segments`（含 `text/offset/duration/words`）。

## 参数
- `segments`（array，必填）：narration 的 segments 输出。
- `output_path`（string，可选）：输出 `.ass` 路径；同目录同名 `.srt` 一并产出。省略则只返回条目。
- `max_chars`（integer，默认16）：单行最大字数，超出即断行。
- `min_duration`（number，默认0.8s）：单行最短停留；不足则顺延结束（不跨下一行重叠）。
- `width`/`height`（integer，默认1920/1080）：视频尺寸，决定 PlayRes 与样式换算。
- `font_size`（integer，可选）：字号 px，默认 `height*4.8%`。
- `margin_v`（integer，可选）：底部安全距离 px，默认 `height*6%`。
- `font`（string，默认 `Microsoft YaHei`）。

## 输出
```
{
  "entries": [["第一行文字", 0.2, 1.4], ["第二行文字", 1.4, 3.1], ...],
  "count": 12,
  "ass_path": ".../sub.ass",
  "srt_path": ".../sub.srt",
  "style": {"alignment": "bottom-center", "font_size": 52, "margin_v": 65, "wrap": false, ...}
}
```

## 与其它部门的关系
- 上游：**旁白组**（`narration`）的 `segments.words`。
- 下游：**合成部门**直接烧 `.ass`。
- 分句是通用规则（句末标点必断、句内标点整行够长才断、每行不超过 `max_chars` 字、末尾防孤字），非关键词匹配。

## 说明
- 本组在 Windows 渲染（libass）下默认字体 `Microsoft YaHei`；可换字体名。
- 若某段缺 `words`，回退为按字数均分该段时长。
