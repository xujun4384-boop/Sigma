# compose_video - 多段视频合成

**把多段视频片段合成为最终视频。** 与 video_shot 搭配：video_shot 逐段产出 mp4，本工具把它们 + 旁白 + 字幕 + BGM 合成一个成片。

## 摘要
主 LLM 组合路径的"合成器"。拿各段 scene_videos（video_shot 产物）按播放顺序传入，scene_audios 一一对应（可空），可选字幕/BGM。产出最终 mp4 + srt 字幕 + 总时长。

## 与其它视频入口的区别
- **compose_video** —— 只做"合成"这一步（本入口）。
- **video_shot** —— 只做"产一段"这一步。
- **video_produce** —— 整套自动流水线，无需手动分步。

## 字幕
`subtitles` 为 `[[text, start, end], ...]`。各段旁白由 video_shot 返回 `words`（字级时间戳）——把所有段的 words 按起始偏移累加即可汇总成整体字幕。