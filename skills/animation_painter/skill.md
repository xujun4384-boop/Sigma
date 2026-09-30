# animation_painter（动画绘制 · p5.brush 水彩）

把视频做成「程序化手绘水彩动画」。复用开源 **p5.js + p5.brush** 渲染引擎（非实时录屏，逐帧保真），可叠加节拍节奏、歌词卡拉OK、转场笔刷，并把外部音乐混流进成片。

---

## 能力边界

- **做**：依据剧情/歌词创作逐帧绘制的 2D 手绘/水彩风格动画 MP4。
- **不做**：不生成图片素材、不生成配音/音乐。配乐走 `music_generate`/`doubao_tts`/外部 mp3，本技能只在合成时把 `audio_path` 混入 mp4。
- **效果**：等效于仓库打包的引擎输出（同一 p5.brush 渲染管线 + 逐帧 renderAt）。

## 工作流

1. 用**专用 LLM**（如 Kimi K3）依据需求写一段动画脚本：章节划分、每章镜次、时间轴、节拍、歌词落点。
2. 依据下面的「创作规范」生成一个自定义 `<场景名>.html`：`<script src>` 引用引擎运行时 `skills/animation_painter/engine/painter.html` 同目录的 `p5.min.js`/`p5.brush.js`，并用 `window.chapter()` 注册镜头。（也可先用内置 `demo_core.js` 作模板。）
3. 调用 `pdoom_render` 渲染成 mp4；如需配乐，先把音乐生成到本地，再把 `audio_path` 传入混流。

> 若嫌自定义麻烦：不传 `html_path` 即用内置 demo 出示例片。

## 创作规范（AI 与运行时的硬契约）

复用 `window.__P5FX`，镜头是**时间的纯函数**：

- 从 `window.__P5FX` 解构工具：`paint / inkLine / letter / sfx / flushLetters / camBegin / camEnd / rectPts / ellPts / rrPts / starPts / heartPts / kf / mobile / mixCol / shakeXY / pulse / beatN / wob / seg / hash / ease*` 及 `PAL / CFG / W / H / DUR / BPM / BEAT`。
- **角色 = 用「通用构件 + 质量护栏」自己拼**，引擎只提供积木，不提供特定角色的模板
  （给小猫小狗新角色，绝不会要求往引擎加函数，只需照下面拼法换组合参数即可）。部件：
  - `char_Blob(cx,cy,rx,ry,n,jitter,seed,bumps)`：**有机闭合基座**（头/身体轮廓），正弦叠加凸叶打破"呆板蛋形"。
  - `char_Ear(cx,cy,w,h,rot,o)`：**耳朵/角/翼**，任意旋向，猫狗鹿龙皆可用。
  - `char_Eye(ex,ey,es,o)`：**眼睛**（圆瞳+高光+可调睑缝）。任何角色都能配。
  - `char_Close(pts)` / `char_Closed(pts)`：**质量护栏**——把点列强制闭合 / 自检是否闭环。AI 手拼多边形常开口，画出来是断线脏相；关键轮廓绘制前用它保证闭合。
  - 其它基础：`ellPts/rrPts/rectPts/inkLine/paint/letter` 照常自由组合勾细节（嘴/须/天线/沟回等）。
- **如何拼**（详见 `demo_core.js` 的 buildBrain/buildBot/buildCat/buildBubble 四个示例）：大脑=Blob头+Eye+沟回线条；机器人=rrPts头身+Eye+天线；小猫=ellPts头+Ear×2+Eye+须+身尾；对话框=rrPts+指向尾。**同一套构件，换组合即任意角色**——不要复制命名函数当模板填空，要读 demo 学"拼法"。
- **护栏使用**：任何手拼的轮廓多边形，绘制前套 `char_Close`；避免自相交多边形配水彩 `fill/wash`（如 `heartPts` 心形 + 水彩填充会触发 p5.brush shader 崩溃）。
- **禁止乱画独立的实心纯色小图形当"装饰"**（如画面角落紫色实心圆/六边形）：与水墨割裂且被判脏点；装饰用 `paint` 水彩填色层并贴合 PAL 调色。
- 用 `window.chapter(name, start, end, shots)` 注册章节；`shots` 是 `[t0, fn]` 的时序数组。
- 镜头函数 `fn(t, lt, dur)`：`t`=全局秒、`lt`=镜头内秒、`dur`=镜头时长。每帧**自己先画完整背景**再叠角色。
- **禁止跨帧状态**：帧会无序并行渲染，不能靠上一帧结果；不共享可变全局。
- **禁止 `Math.random()`**：用 `hash(i)` 稳定伪随机 + `jit(a)` 制造手绘抖动（运行时按帧重置，做成"画面沸腾"）。
- 形状绘制 `paint(pts, {wash, fill, hatch, ink})`：可选纯色层、水彩填充(bleed/tex/border)、排线、墨线描边。
- 动画节奏用 `pulse(t)/beatN(t)` 对齐 `BPM`；画面对拍子：主打拍放大、弱拍复位。
- 字幕安全区：预留画面底部 **8~12%**，歌词文字落点在安全区内，避免顶到边缘或被遮挡。

## 参数

`pdoom_render` 参数：`output_path`(必填)、`project`、`html_path`、`duration`、`fps`、`width`、`height`、`bpm`、`audio_path`、`workers`、`quality`、`mode`。

- `html_path`：自定义动画 HTML；省略 → 内置 `engine/painter.html`（含 demo 章节）。
  自定义章节无需复制/改写引擎文件：`html_path=…/engine/painter.html?core=你的章节.js`，并把章节
  JS 放到 `engine/` 同目录即可。系统自动注入该章节，缺省回落 `demo_core.js`。
- `duration/fps`：时长(秒)、帧率，默认 8s/24fps。
- `audio_path`：外部音频，合成时混入并截断到时长。
- `bpm`:节拍速度，驱动动画节拍同步（非硬编码，可配）。
- `mode`：`full`=整片 mp4（默认）；`preview`=低分辨率拼图预览图，出片前快速检查画面。

> **禁止用 bash/sandbox 直调`scripts/` 下的脚本**（包括 frame_renderer.py）。预览/检查用
> `pdoom_render(mode=preview)`，出片用 `pdoom_render(mode=full)`。系统会对直调技能脚本做拦截。
> **禁止手动 `copy`/改写 `engine/*.html`**（PowerShell 的 `Get-Content -replace … Set-Content`
> 会破坏 UTF-8 中文注释、损坏内联 JS 导致 `window.ready` 永不置位）。自定义章节一律走
> `?core=` 注入通道。

## 依赖

- `ffmpeg`（PATH 可用）、`playwright`（含 Chromium）：逐帧渲染必需。
- 引擎资源已随技能内置：`engine/p5.min.js`、`engine/p5.brush.js`、`engine/painter.html`（运行时）、`engine/demo_core.js`（示例章节）。