# animation_painter

把视频做成「程序化手绘水彩动画」的 sigma 技能。复用开源 **p5.js + p5.brush** 渲染引擎（非实时录屏，逐帧保真），支持节拍节奏、歌词卡拉OK、转场笔刷，并把外部音乐混流进成片。

## 目录结构

```
skills/animation_painter/
├── __init__.py          # AnimationPainterRenderTool（pdoom_render 工具声明）
├── skill.md             # LLM 创作规范（章节/镜头/纯函数契约）
├── engine/
│   ├── painter.html     # 通用运行时（core 引擎 + 双录制接口）
│   ├── p5.min.js        # p5.js 2.3.3（来自 npm）
│   ├── p5.brush.js      # p5.brush 2.2.3（来自 npm，水彩/墨水笔刷）
│   └── demo_core.js     # 示例章节（水彩角色 + 背景 + 节拍 + 歌词）
└── scripts/
    └── frame_renderer.py  # 逐帧保真录制器（renderAt → ffmpeg 合成）
```

## 运行原理

- **渲染引擎**：`painter.html` 复用 PDoomVideo 的 core 引擎 + timeline 核心通用化而来，保留 paint/几何/相机/文字/笔刷/节拍/章节注册全部能力，去掉 PDoom 特有绑定；参数通过 `window.PAINT_CONFIG` 注入（BPM/时长/分辨率/调色板/歌词/转场均可配，不硬编码）。
- **保真录制**：每一帧独立 `window.renderAt(t)` 拿无损数据，再 `ffmpeg image2pipe` 合成 mp4 —— 而非实时录屏，因而不会掉帧/糊。帧是 t 的纯函数，可安全并行/无序渲染。
- **配乐**：仅混流外部音频（`audio_path`），不做音乐生成 —— 音乐走 `music_generate`/`doubao_tts`/外部 mp3。

## 依赖

- **运行时**：系统需安装 `ffmpeg`,并 Python 环境装有 `playwright`（含 Chromium）。
- **授权**：p5.js / p5.brush 均为开源库，随技能内置在 `engine/`。

## 备注

- 本技能的渲染输出等效于仓库打包引擎（同一 p5.brush 管线 + 逐帧截帧）。
- 支持 LLM 依据 `skill.md` 自写自定义章节 HTML（`html_path` 传入）；否则用内置 demo。