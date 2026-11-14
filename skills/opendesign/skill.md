# opendesign skill
# ⚠️ 制作视频统一走 director 导演组；本技能是「HTML 动画引擎」，一般由导演调度（直接调用时给 brief 即可）。
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
#
# 离线与健壮性:
#   - 第三方脚本（GSAP / three.js，见 vendor/）内置在 skills/opendesign/vendor/，脚手架会自动落盘到
#     项目目录；生成后会把手写的外链 <script src> 自动改写为本地文件，渲染不依赖外网 CDN。
#   - 动效能力清单在 skills/opendesign/capabilities/*.md（CSS 原生动效 + three.js 真 3D 配方），
#     与框架契约一起拼进系统提示词；新增能力只需加一个 md 文件，不用改提示词或脚本。
#   - 生成后校验 HTML 完整性（</html> / 根元素 / window.__timelines）；疑似被截断会自动重写
#     （≤3 次），仍不完整则明确报"LLM 编写 HTML 失败"，不会带着残缺 HTML 去渲染。
#   - 渲染前闸门（scripts/gate.py）：静态结构 → 无头浏览器运行时 → 确定性比对 → 视觉复审，
#     任一不过先走自愈重试（原地修补 ≤8 处、失败则整篇重写，≤3 次），过不了才报错，
#     避免 LLM 写出的动画代码把导演组整体崩掉。
# ---------------------------------------------------------------------------

# ═══ 推荐工作流 ═══

# 基础流程:
#   1. 分析内容 → 确定项目名（如 brand_intro）和分场景脚本
#   2. （可选）用 generate_image 并行生图到 video_work/<项目名>/assets/
#   3. opendesign_video(project="brand_intro", brief="<确认后的脚本>", output_path="main.mp4")
#   4. 画面产出后交给 video_compose 合成（本 skill 不含配音/字幕）
#
# 配图（引擎按需生图，默认关闭，由导演按面板决定）:
#   - 只有面板写了 "images": true 时，导演组才会给这一段开生图通道；否则纯图形完成。
#   - 开启后，LLM 在写 index.html 时用 <img src="assets/gen-1.png" data-gen="英文画面描述"
#     data-gen-aspect="16:9"> 就地声明要什么图，并在同一条 GSAP 时间轴上把这张图编成动效
#     （遮罩揭示 / 推拉 / 多层视差 / 跟转场位移）。图不是贴图，是画面运动的主体。
#   - 引擎在这一版 HTML 落盘前生成图片、写进项目 assets/ 并回填 src；全程无外链。
#   - 生图失败只做透明占位，不阻断渲染；不要配图的段落不要开，配图反而会干扰示意画面。
#   - 上游已经预生成好图时，仍可传 assets_dir 让引擎同步进来，两种来源共存。

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
#   assets_dir (string, 可选) 上游预生成的配图目录，会同步进项目 assets/ 供 LLM 引用
#   embeds (array, 内部) director 传入的嵌入特效元数据：帧雪碧图/矩形/时间；
#     composer 会被要求用 canvas + GSAP steps() 逐帧绘制，禁止 video/iframe
#   with_images (boolean, 可选, 默认false) 是否允许引擎按需生图（导演组按面板 images 字段开启）
#   max_images (integer, 可选, 默认4) 本片最多生成几张图
#   fps (integer, 可选, 默认30) 帧率
#   width (integer, 可选, 默认1920) 视频宽度
#   height (integer, 可选, 默认1080) 视频高度
# ---------------------------------------------------------------------------
