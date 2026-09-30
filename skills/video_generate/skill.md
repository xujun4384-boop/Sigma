# video_generate skill
# ---------------------------------------------------------------------------
# 摘要
# 视频生成工具集。推荐入口是 video_produce 流水线：主 LLM 设计脚本并确认后，
# 交给 video_produce 自动按固定顺序跑完「旁白 → 画面规划 → 配图 → 画面生成 → 合成」。
# 画面用 opendesign（HyperFrames），旁白用 doubao_tts，图片由 design LLM 决定，不生成 BGM。
#
## 使用场景
# - 产品宣传视频制作
# - 数据报告动画展示
# - 品牌介绍动画
# - 教育培训内容视频化
# - 将文档/PPT 内容转化为视频
#
# 涉及的工具（跨 skill 协作）:
#   video_produce    - 视频制作流水线（推荐入口，内部固化五阶段）
#   ask_user         - 脚本交互确认（脚本设计后、流水线前）
#   doubao_tts       - 旁白生成（流水线内部使用）
#   image_generate   - 生图（流水线内部使用，由 design LLM 决定）
#   opendesign_video - 画面生成（流水线内部使用）
#   video_compose    - 合成（流水线内部使用）
# ---------------------------------------------------------------------------

# ═══ 流程分工（关键） ═══

# 视频制作是「固定流水线」，顺序由代码写死，LLM 不能乱序/跳步：
#
#   主 LLM 层（本 skill 负责）:
#     1. 分析需求 → 设计脚本：分镜 + 旁白文案 + 画面描述 + 视觉风格
#     2. ask_user 确认脚本（可迭代修改）
#     3. 整理成 scenes 结构，调用 video_produce
#
#   video_produce 流水线（自动执行，固定五阶段）:
#     Stage 1 旁白   → doubao_tts 生成 → 权威时长 + 字级时间戳
#     Stage 2 画面规划 → design LLM 决定图需求
#     Stage 3 配图   → image_generate 按图需求
#     Stage 4 画面   → opendesign 写 HTML + 渲染（时长=旁白时长）
#     Stage 5 合成   → video_compose 叠加旁白 + 字幕
#
# ⚠️ 铁律：
#   - 时长由旁白实际读速决定（Stage 1 产出），不要自己预先定总时长
#   - 图片由 design LLM 决定（Stage 2），不要主 LLM 在脚本阶段盲目生图
#   - 脚本确认后直接调 video_produce，不要自己手写 canvas/html
#   - 每阶段失败自动重试 6 次，超过熔断停止（不回退、不跳步）

# ═══ 推荐工作流 ═══

# ═══ 第一步：脚本设计 + ask_user 确认（主 LLM 负责）═══
#
# 1. 分析需求 → 设计脚本：标题、视觉风格、分镜（每镜：旁白文案 + 画面描述）
# 2. 用 ask_user 把脚本呈现给用户，确认或修改，直到用户确认
# 3. 把确认后的脚本整理成 scenes 结构（见下）
#
# 脚本写作经验（人类经验，设计脚本时务必遵循）:
#   - 前3秒钩子：用「变化/对比/缺口(悬念)/威胁(冲突)」抓住注意力
#   - 脚本三段式：钩子(0-3秒) → 正文(留人给价值) → 收尾(行动/金句)
#   - 情绪共鸣：让观众觉得「这说的就是我」
#   - 标题要像真人刷到会想点开的标题，不要报告腔/AI味
#   - 节奏：一镜一句、快进快出，画面跟着文案走
#
# scenes 结构（整理成此结构传给 video_produce）:
#   [
#     {"narration": "第1镜旁白文案", "visual": "第1镜画面描述"},
#     {"narration": "第2镜旁白文案", "visual": "第2镜画面描述"},
#   ]
#
# 示例：
#   scenes = [
#     {"narration": "你的 AI 办公副驾，SIGMA", "visual": "品牌名 SIGMA 从下淡入放大"},
#     {"narration": "一句话总结、一键生成文档", "visual": "三个功能卡片错落入场"},
#   ]

# ═══ 第二步：调用 video_produce（流水线自动执行）═══
#
# video_produce(
#     scenes=[{"narration":"...","visual":"..."}, ...],
#     title="...", style_prompt="...",
#     project="...", output_path="final.mp4",
# )
#
# video_produce 内部自动跑完五阶段（旁白 → 画面规划 → 配图 → 画面生成 → 合成），
# 每阶段失败重试 6 次，超过熔断。你不需要（也不应该）自己拆步骤调 doubao_tts / opendesign / image_generate。

# ═══ 备选：模板快速生成（简单品牌/数据动画，无需脚本确认）═══
#   1. video_scene(project="...", template="particle_brand", params={...}, output_path="scene1.mp4")
#   2. video_compose(project="...", scene_videos=["scene1.mp4"], output_path="final.mp4")

# ═══ HTML 动画规范（sandbox 自定义模式，备选） ═══

# 自定义 HTML 必须满足以下接口:
#
# ```html
# <!DOCTYPE html>
# <html>
# <body>
# <canvas id="c"></canvas>
# <script>
# const W = 1920, H = 1080;
# const canvas = document.getElementById("c");
# canvas.width = W; canvas.height = H;
# const ctx = canvas.getContext("2d");
#
# let frame = 0;
# function draw() {
#   const progress = frame / (DURATION_SECONDS * 30);  // 0~1
#   // ... 你的动画逻辑 ...
#   frame++;
#   if (frame < DURATION_SECONDS * 30) requestAnimationFrame(draw);
# }
#
# // ⚠️ 必须暴露这两个接口
# window.CURRENT_FRAME = 0;
# window.updateAnimation = draw;
#
# draw();
# </script>
# </body>
# </html>
# ```

# ═══ 预置模板列表 ═══

# particle_brand  - 粒子汇聚 + 打字机品牌动画
#   参数: BRAND_NAME, SUBTITLE, TAGLINE, PRIMARY_COLOR, BG_COLOR,
#         PARTICLE_COUNT(200-2000), REVEAL_STYLE(typewriter/fade_in),
#         GLOW_INTENSITY(0-1), TITLE_SIZE
#
# data_counter    - 数字滚动 + 数据统计动画
#   参数: TITLE_TEXT, SUBTITLE, ACCENT_COLOR, STATS_JSON([{key,label,value},...])

# ═══ 输出目录约定 ═══

# 所有工具支持 project 参数，LLM 应根据内容分析为视频项目取名。
# 例如：project="vibe_coding_intro" 会产生:
#   video_work/
#   └── vibe_coding_intro/
#       ├── assets/               # image_generate 生图（可选，解耦）
#       ├── main_hyperframes/     # opendesign 的 HyperFrames 项目中间产物
#       ├── main.mp4              # opendesign 产出的画面视频
#       ├── vo.mp3                # doubao_tts 旁白音频
#       └── final.mp4             # video_compose 最终合成

# ⚠️ 重要规则:
# 1. 同一个视频的所有工具调用 MUST 使用相同的 project 名称
# 2. video_scene/opendesign_video 返回的 output_path 是绝对路径，后续直接使用
# 3. 配图统一放 video_work/<项目名>/assets/，opendesign_video 通过 assets_dir 引用
# 4. 自定义 HTML 也请写入 video_work/<项目名>/ 目录内
# 5. 旁白用 doubao_tts（不生成 BGM），合成时 video_compose 传 scene_audios，bgm_enabled 保持 false

# ═══ 依赖要求 ═══

# 首次使用需安装:
#   pip install playwright moviepy numpy
#   playwright install chromium
# 使用 opendesign 画面生成时，另需本机安装 Node.js + npx + FFmpeg（详见 opendesign skill）。
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── video_scene ──
# 录制单个视频场景。支持模板模式和自定义HTML模式。
#
# 参数:
#   output_path (string, 必填) 输出 mp4 文件路径
#   template (string, 可选) 模板名: particle_brand / data_counter
#   html_path (string, 可选) 自定义 HTML 文件路径（sandbox 创作）
#   params (object, 可选) 模板参数 JSON
#   duration (integer, 可选, 默认10) 录制时长（秒）
#   fps (integer, 可选, 默认30) 帧率
#   width (integer, 可选, 默认1920) 视频宽度
#   height (integer, 可选, 默认1080) 视频高度

# ── video_compose ──
# 多场景拼接合成，叠加旁白音频和字幕。无 BGM。
#
# 参数:
#   output_path (string, 必填) 最终输出 mp4 路径
#   scene_videos (array, 必填) 场景视频路径列表
#   scene_audios (array, 可选) 旁白音频路径列表（与 scene_videos 一一对应，空字符串=无旁白）
#   subtitles (array, 可选) [[text, start_sec, end_sec], ...]（可由 doubao_tts 的 words 时间戳聚合）
#   width (integer, 可选, 默认1920)
#   height (integer, 可选, 默认1080)
#   fps (integer, 可选, 默认30)
#   （bgm_enabled 保持 false，不生成 BGM）

# ── doubao_tts（独立 skill，此处列关键参数） ──
# 旁白生成。详见 doubao_tts skill。
#
# 参数:
#   text (string, 必填) 旁白文本
#   output_path (string, 必填) 输出 mp3 路径
#   project (string, 可选) 项目名
#   speaker (string, 可选) 音色ID，默认广告解说2.0
#   speech_rate (integer, 可选) 语速 -50~100
#   loudness_rate (integer, 可选) 音量 -50~100
# 输出: output_path + duration（旁白时长）+ words（字级时间戳）

# ── opendesign_video（独立 skill，此处列关键参数） ──
# 画面生成主力。详见 opendesign skill。
#
# 参数:
#   brief (string, 必填) 视频内容描述（用确认后的脚本）
#   output_path (string, 必填) 输出 mp4 路径
#   project (string, 可选) 项目名
#   duration_s (integer, 可选, 默认8) 总时长
#   n_scenes (integer, 可选, 默认3) 场景数
#   style_prompt (string, 可选) 视觉风格
#   tone (string, 可选) 语气: academic / product / editorial / technical
#   assets_dir (string, 可选) 配图目录（配合 generate_image）
#   fps / width / height (integer, 可选)
# ---------------------------------------------------------------------------
