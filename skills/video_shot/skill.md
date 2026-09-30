# video_shot - 产一段视频片段（自由组合长视频的积木）

**产出一段独立视频片段（mp4）。** 通过 engine 指定内容引擎，主 LLM 逐段决定视觉内容与引擎，多段产物统一交给 compose_video 合成——适合 5 分钟以上、混合多种风格的组合长视频。

## 摘要
给主 LLM 的"片段级"积木。想用几段就调几次，每段渲染为独立 mp4，最后 `compose_video` 拼接。参数量聚焦，不用一次想清整片。

## 与其它视频入口的区别（主 LLM 据此选择）
- **video_shot** —— 先产多段、自由混搭引擎、再 compose 合成的**组合路径**的积木（本入口）。
- **compose_video** —— 把多段 mp4 + 旁白 + 字幕 + BGM 合成最终成片的合成器。
- **video_produce** —— 整套流水线（脚本→旁白→画面→合成）自动跑完，无需逐段手拼。
- **video_card / video_cinematic** —— 单品捷径：单独一段竖版卡 / 单独一段影视级 AI 视频。

## 引擎（engine）
- `opendesign`：文字/排版/图表画面（HTML 渲染）。配 `brief`/`n_scenes`/`style_prompt`。
- `card`：竖版卡片短视频。配 `title`/`scenes`/`material_type`/`asset_source`。
- `cinematic`：影视级 AI 视频（纯 prompt）。配 `prompt`/`duration`/`resolution`。
- `pdoom`：水彩动画。需提供 `html_path`（含 `?core=章节脚本`），本入口不做自动写章节。

## 旁白
可加 `narration`（本段旁白文本），内部走 doubao TTS 产 mp3 + 字级时间戳；返回 `audio`/`words` 供字幕对齐。旁白可作为时长依据传给支持时长参数的引擎。