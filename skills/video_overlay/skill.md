# video_overlay skill
# 已并入 video_card(material_type=video)。此入口不再对主 LLM 暴露，仅作为 video_card 内部委托实现。
# ---------------------------------------------------------------------------
# 摘要
# 竖版（9:16）卡片视频生成，中部素材区域支持视频和图片。
# 顶部固定标题/副标题，中部圆角卡片叠加视频或图片，底部打字机动画字幕。
# 视频素材用 moviepy 原生叠加播放，支持保留音轨。
# 复用 video_auto 的视觉样式，布局固定竖版不变。
#
# ## 使用场景
# - 新闻解说（中部嵌入新闻现场视频）
# - 产品演示（中部播放产品功能录屏）
# - 教程讲解（中部叠加操作演示视频）
# - 活动回顾（中部轮播活动视频片段）
# - 任何需要在竖版卡片中间嵌入视频的场景
#
# 包含 1 种工具:
#   video_overlay - 竖版卡片视频生成（中部支持视频叠加）
# ---------------------------------------------------------------------------

# ═══ 与 video_custom 的区别 ═══

# video_custom（纯图片）:
#   - 中部只支持静态图片
#   - PIL 逐帧合成，输出无声视频
#
# video_overlay（视频/图片混合）:
#   - 中部支持视频和图片
#   - 视频用 moviepy 原生叠加播放，可保留音轨
#   - 图片作为静态素材处理

# ═══ 推荐工作流 ═══

# 步骤 1: 准备素材
#   - 视频: 本地 MP4/MOV 等文件绝对路径
#   - 图片: 本地文件或调用 generate_image 生成
#
# 步骤 2: 组织场景
#   video_overlay(
#     output_path="output.mp4",
#     title="视频标题",
#     subtitle="可选副标题",
#     scenes=[
#       {"text": "第一幕字幕", "media": "C:/videos/clip1.mp4", "duration": 5, "transition": "fade"},
#       {"text": "第二幕字幕", "media": "C:/images/pic2.jpg", "duration": 4, "transition": "slide_left"},
#     ],
#     keep_audio=True,
#     style={"accent_color": "#ff6b35"},
#   )

# ═══ 参数详情 ═══

# ── video_overlay ──
# 竖版卡片视频生成（中部支持视频/图片叠加）。
#
# 必填参数:
#   output_path (string) 输出 MP4 文件路径
#   title (string) 视频大标题
#   scenes (array) 场景列表（至少 1 个），每项:
#     {
#       "text": "字幕文案",
#       "media": "素材绝对路径（视频或图片）",
#       "duration": 4,                    // 秒数，默认 4
#       "transition": "fade"              // 动效，默认 none
#     }
#
# 可选参数:
#   subtitle (string) 副标题，默认空
#   width (integer) 视频宽度，默认 1080
#   height (integer) 视频高度，默认 1920（竖版 9:16）
#   fps (integer) 帧率，默认 30
#   title_height (integer) 标题区高度(px)，默认 560
#   media_height (integer) 素材卡片高度(px)，默认 640
#   keep_audio (boolean) 素材视频是否保留音轨，默认 true
#   style (object) 视觉样式覆盖，可选键:
#     bg_gradient_top / bg_gradient_bottom  - 背景渐变色 (#RRGGBB)
#     title_color / subtitle_color          - 标题/副标题颜色
#     subtitle_text_color                   - 底部字幕颜色
#     subtitle_bg_color                     - 底部字幕背景色 (rgba(...))
#     accent_color                          - 强调色（分割线、光标）
#     card_radius                           - 素材卡片圆角 (px)
#     card_bg                               - 素材卡片背景色
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
#   │   素材卡片（圆角）    │ ← media_height px
#   │   （视频/图片）       │
#   │                      │
#   ├──────────────────────┤
#   │   打字机动画字幕      │ ← 剩余高度
#   └──────────────────────┘
#
# 素材说明:
#   - 视频: 支持 mp4/mov/avi/mkv/webm 等常见格式，按场景时长自动循环或截断
#   - 图片: 支持 jpg/png/webp 等常见格式，作为静态素材
#   - 素材自动居中裁切适配卡片尺寸
#
# 转场动效 (transition):
#   none        - 无动效
#   fade        - 淡入
#   slide_left  - 从右往左滑入
#   slide_right - 从左往右滑入
#   slide_up    - 从下往上滑入
#   zoom_in     - 放大进入
#
# 音频说明:
#   - keep_audio=True 时，素材视频的原始音轨会保留并拼接到输出
#   - keep_audio=False 时，输出为无声视频
#   - 图片素材无音轨
# ---------------------------------------------------------------------------
