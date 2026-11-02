# video_review - 成片审查

**导演收尾用：随机截帧 + 信息核对 + 字幕位置校验**，避免盲盒交付。

## 做什么
- 读取视频信息：分辨率 / 帧率 / 时长 / 大小 / 是否含音轨。
- **随机截取 N 帧**到 `review/` 目录，返回路径供人和 LLM 直接查看。
- 若给 `subtitle_ass`，自动核对：
  - 字幕 `PlayRes` 是否等于视频尺寸（不等则底部锚定会错位）；
  - `Alignment` 是否 `2`（底部居中）、`MarginV` 是否在安全区；
  - 每行字数是否 ≤ `max_chars`（超了可能换行成多行）；
  - 条目时间是否落在 `[0, 时长]`、是否有重叠。

## 参数
- `video_path`（string，必填）成片 mp4。
- `subtitle_ass`（string，可选）字幕 `.ass`；给了才做字幕校验。
- `frames`（integer，默认6）随机截帧数量。
- `max_chars`（integer，默认16）单行字数阈值。
- `output_dir`（string，可选）截图目录，默认视频同目录 `review/`。
- `seed`（integer，可选）随机种子，便于复现。

## 输出
`ToolResult` 摘要 + `report`（含 `info` / `screenshots` / `subtitles.issues`）+ `passed`。

## 边界
- 不做修改，只审查；修正由对应部门重做该段后重新合成。
- 字幕位置是"结构和样式"层校验（PlayRes/Alignment/MarginV/行数/时间轴）；
  复杂背景下的逐像素 OCR 不做。
