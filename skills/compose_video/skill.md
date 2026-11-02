# compose_video - 合成部门（烧录 / 混音 / 拼接）

**把多段视频片段 + 旁白 + 字幕合成为最终 mp4。** 这是「烧录合成部门」的对外入口，只做合成这一步。

## 关键能力

1. **规格归一化（可混合引擎产物）**
   各段先 `scale + 补边(黑)` 到目标画布、统一 `fps / 像素格式 / SAR`，再拼接。
   因此可以把**不同来源、不同分辨率**的片段拼在一起——例如影视级 768P、HTML 动画 1920×1080、
   水彩 1920×1080 混排，不会因规格不一致而崩。
   若各段本就同规格，则走**快速路径**（不重编码，直接 concat copy）。

2. **旁白**
   `scene_audios` 与 `scene_videos` 一一对应；某段无旁白时用**等长静音占位**，保证时间对齐。
   旁白总长超过画面时，用最后一帧 `tpad` 补长画面（不截断旁白）。

3. **字幕（直接烧 .ass）**
   `subtitle_ass` 传「字幕组」产出的 `.ass` 即可——样式（底部锚定、单行、字号）已内嵌，
   合成不再传样式参数，避免旧的 "MarginV 按默认 PlayRes 解释导致中间靠下" 之类问题。

4. **背景音乐（BGM）**
   `bgm` 传音频路径；音乐偏短时用 `acrossfade` 交叉淡化无缝循环铺满全片，
   按 `bgm_volume` 压低后与旁白混音（旁白优先），首尾淡入淡出、与画面同时结束。

5. **音效（SFX）**
   `sfx` 传事件数组 `[{path, at, level, fade_in}]`；`at` 是成片时间轴秒数。
   各事件用 `adelay + volume` 铺成独立音效轨，再与旁白/BGM 混音。
   多路混音最后加 `alimiter`，避免叠加削波。

6. **段间转场**
   `transitions` 透传 ffmpeg `xfade` 的名称；转场会让相邻段重叠、成片时长变短，
   调用方需按同样重叠量计算字幕/旁白时间轴。

## 参数
- `output_path`（string，必填）最终 mp4 路径。
- `scene_videos`（array，必填）各段视频路径，按播放顺序。
- `scene_audios`（array，可选）各段旁白 mp3，与 `scene_videos` 一一对应，空串=该段无旁白。
- `subtitle_ass`（string，可选）字幕组的 `.ass`；给了就烧录。
- `bgm`（string，可选）背景音乐音频路径。
- `bgm_volume`（integer，可选）BGM 音量百分比 0~100，默认 25。
- `sfx`（array，可选）音效事件 `[{path, at, level, fade_in}]`；`level` 0~100，默认 60。
- `transitions`（string/object/array，可选）段间转场。
- `width` / `height` / `fps`（integer，可选）目标画布，默认 1920×1080@30。

## 输出
```
{
  "output_path": ".../final.mp4",
  "duration": 42.1,
  "scene_count": 5,
  "video_norm": true,        // 是否执行了规格归一化（重编码）
  "has_audio": true,         // 最终是否含任意音轨
  "has_voice": true,         // 是否含旁白
  "has_bgm": false,          // 是否含 BGM
  "bgm_looped": false,       // BGM 是否循环铺满
  "has_sfx": true,           // 是否含音效
  "sfx_count": 3,            // 实际混入的音效事件数
  "subtitle_burned": true
}
```

## 部门关系
- 上游：**各画面引擎**（opendesign_video / manim_video / video_cinematic_generate / footage_video / map_video）、
  **旁白组**（narration 的 mp3）、**字幕组**（subtitle 的 .ass）、
  **音乐组**（music_generate 的 bgm）、**音效组**（sfx 的 wav）。
- 本组：归一化 + 拼接/转场 + 混音（旁白/BGM/音效）+ 烧录。
- 不做：不生成画面/旁白/字幕/音乐/音效。

## 依赖
- `ffmpeg` / `ffprobe` 在 PATH。
- 烧中文字幕用 `.ass` 内声明的字体（字幕组默认 `Microsoft YaHei`）。

## 运行时长
合成（尤其含归一化重编码）耗时较长，属于**长任务**：工具层不对其设超时，会一直跑到完成。
