# opendesign skill
# ---------------------------------------------------------------------------
# 摘要
# 基于 OpenDesign / HyperFrames 框架的 HTML 视频生成技能。
# LLM 按 HyperFrames 契约编写 HTML + GSAP 动画，再由本地无头浏览器确定性渲染成 mp4。
# 相比 video_generate 的「手写 canvas + Playwright 实时录制」，本方案用框架契约保证
# 视觉一致性，且渲染结果逐帧可复现。
#
## 使用场景
# - 品牌宣传片 / 产品介绍动画
# - 数据报告动画展示
# - 需要「好看、可控、可复现」的 HTML 动画视频
#
# 包含 1 种工具:
#   opendesign_video - 输入内容描述 → LLM 写 HTML → npx hyperframes render → mp4
# ---------------------------------------------------------------------------

# ═══ 推荐工作流 ═══

# 基础流程:
#   1. 分析内容 → 确定项目名（如 brand_intro）和分场景脚本
#   2. （可选）用 generate_image 并行生图到 video_work/<项目名>/assets/
#   3. opendesign_video(project="brand_intro", brief="<确认后的脚本>", output_path="main.mp4")
#   4. 画面产出后交给 video_compose 合成（本 skill 不含配音/字幕）
#
# 配图时（生图解耦，图片由 image_generate 预生成）:
#   - 先用 generate_image 生图到 video_work/<项目名>/assets/（可 sub_agent 并行）
#   - opendesign_video 传 assets_dir="video_work/<项目名>/assets/"
#   - 工具会把图片同步到 HyperFrames 项目 assets/，并让 LLM 在 HTML 里引用

# ═══ 输出目录约定 ═══

# output_path 为相对路径时，自动放在 video_work/<项目名>/ 下:
#   video_work/
#   └── brand_intro/
#       ├── final_hyperframes/   # HyperFrames 项目中间产物（index.html 等）
#       └── final.mp4            # 最终视频
#
# ⚠️ 重要规则:
# 1. 同一个视频的所有工具调用 MUST 使用相同的 project 名称
# 2. opendesign_video 返回的 output_path 是绝对路径，后续直接使用
# 3. 配图时图片也请写入 video_work/<项目名>/assets/ 目录

# ═══ 依赖要求 ═══

# 需要本机已安装:
#   - Node.js + npx（hyperframes CLI 依赖，会自动拉取）
#   - FFmpeg（render 编码 mp4 用）
# 首次运行会自动 npx 拉取 hyperframes，可能需联网。
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── opendesign_video ──
# 输入内容描述，由 LLM 按 HyperFrames 契约编写 HTML+GSAP 动画并渲染成 mp4。
#
# 参数:
#   brief (string, 必填) 视频内容描述：主题、文案、要点、结构
#   output_path (string, 必填) 输出 mp4 文件路径
#   project (string, 可选) 项目名，用于创建独立输出目录
#   duration_s (integer, 可选, 默认8) 视频总时长（秒）
#   n_scenes (integer, 可选, 默认3) 场景数量
#   style_prompt (string, 可选) 视觉风格描述（配色/字体/动效）
#   tone (string, 可选, 默认product) 语气: academic / product / editorial / technical
#   assets_dir (string, 可选) 配图目录，图片会同步到项目 assets/ 供 LLM 引用（配合 generate_image）
#   fps (integer, 可选, 默认30) 帧率
#   width (integer, 可选, 默认1920) 视频宽度
#   height (integer, 可选, 默认1080) 视频高度
# ---------------------------------------------------------------------------
