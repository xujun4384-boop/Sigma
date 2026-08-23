# video_custom skill
# ---------------------------------------------------------------------------
# 摘要
# 自定义竖版（9:16）视频生成。LLM 自行准备图片素材（本地文件/生图均可），
# 指定标题、副标题、每个场景的文案/时长/图片路径/转场动效，以及整体视觉样式。
# 不做任何自动配图，完全由 LLM 控制素材和内容。
# 复用 video_auto 的渲染引擎，固定竖版布局不变。
#
# ## 使用场景
# - 产品展示短视频
# - 品牌宣传片
# - 活动回顾/花絮
# - 教程演示
# - 社交媒体信息流内容
# - 任何非新闻类的竖版短视频（新闻类请用 video_auto 全自动）
#
# 包含 1 种工具:
#   video_custom - 自定义竖版视频生成
# ---------------------------------------------------------------------------

# ═══ 与 video_auto 的区别 ═══

# video_auto（新闻全自动）:
#   - 输入新闻原文 → 自动提炼标题/分镜 → 自动生图 → 合成
#   - 适合新闻资讯类内容
#
# video_custom（完全自定义）:
#   - LLM 自己准备图片（本地文件/生图结果）
#   - 自己组织 scenes 结构
#   - 可自定义所有视觉样式（颜色、字体大小等）
#   - 适合非新闻类的创意视频

# ═══ 推荐工作流 ═══

# 步骤 1: 准备图片素材
#   - 本地文件: 直接用绝对路径
#   - 生图: 调用 generate_image → 获取图片路径
#
# 步骤 2: 组织场景
#   video_custom(
#     output_path="output.mp4",
#     title="我的视频标题",
#     subtitle="可选副标题",
#     scenes=[
#       {"text": "第一幕字幕", "image": "C:/images/pic1.jpg", "duration": 4, "transition": "slide_left"},
#       {"text": "第二幕字幕", "image": "C:/images/pic2.jpg", "duration": 5, "transition": "fade"},
#     ],
#     style={"accent_color": "#ff6b35", "bg_gradient_top": "#0a0a2e"},
#   )

# ═══ 参数详情 ═══

# ── video_custom ──
# 自定义竖版（9:16）视频生成。
#
# 必填参数:
#   output_path (string) 输出 MP4 文件路径
#   title (string) 视频大标题
#   scenes (array) 场景列表（至少 1 个），每项:
#     {
#       "text": "字幕文案",
#       "image": "图片绝对路径（必填）",
#       "duration": 4,                    // 秒数，默认 4
#       "transition": "slide_left"        // 动效，默认 none
#     }
#
# 可选参数:
#   subtitle (string) 副标题，默认空
#   width (integer) 视频宽度，默认 1080
#   height (integer) 视频高度，默认 1920（竖版 9:16）
#   fps (integer) 帧率，默认 30
#   title_height (integer) 标题区高度(px)，默认 560
#   image_height (integer) 图片卡片高度(px)，默认 640
#   style (object) 视觉样式覆盖，可选键:
#     bg_gradient_top / bg_gradient_bottom  - 背景渐变色 (#RRGGBB)
#     title_color / subtitle_color          - 标题/副标题颜色
#     subtitle_text_color                   - 底部字幕颜色
#     subtitle_bg_color                     - 底部字幕背景色 (rgba(...))
#     accent_color                          - 强调色（分割线、光标）
#     card_radius                           - 图片卡片圆角 (px)
#     card_bg                               - 图片卡片背景色
#     title_font_size                       - 标题字号 (默认 64)
#     subtitle_font_size                    - 副标题字号 (默认 36)
#     subtitle_font_size_bottom             - 底部字幕字号 (默认 32)
#
# 视频结构（9:16 竖版，固定布局）:
#   ┌──────────────────────┐
#   │   标题 + 副标题       │ ← title_height px
#   │   ──── 分割线 ────   │
#   ├──────────────────────┤
#   │                      │
#   │   图片卡片（圆角）    │ ← image_height px
#   │                      │
#   ├──────────────────────┤
#   │   打字机动画字幕      │ ← 剩余高度
#   └──────────────────────┘
#
# 转场动效 (transition):
#   none        - 无动效
#   fade        - 淡入
#   slide_left  - 从右往左滑入
#   slide_right - 从左往右滑入
#   slide_up    - 从下往上滑入
#   zoom_in     - 放大进入
# ---------------------------------------------------------------------------
