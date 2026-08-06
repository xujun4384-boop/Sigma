# video_auto skill
# ---------------------------------------------------------------------------
# 摘要
# 新闻类竖版（9:16）无声短视频一键生成。接收新闻原文/标题/分镜后，自动配图并合成带标题卡片、图片和底部字幕的无声MP4。
# 纯视觉卡片视频，无旁白配音、无BGM。这是做新闻资讯竖版视频的最简路径，无需手写HTML Canvas动画。
# 与video_generate的区别：video_auto 是脚本+配图→合成无声卡片视频，video_generate 是从零AI生成Canvas动态画面。
#
## 使用场景
# - 新闻资讯竖版短视频
# - 热点事件卡片视频（标题+图片+字幕轮播）
# - 产品/行业快讯视频化
# - 社交媒体信息流竖版内容生成
# - 任何"一段文字内容 → 竖版无声短视频"的转换需求
#
# 包含 1 种工具:
#   video_auto - 新闻竖版无声短视频一键生成
# ---------------------------------------------------------------------------

# ═══ 推荐工作流 ═══

# 标准模式（输入新闻原文）:
#   1. video_auto(news_content="新闻原文...", output_path="news_video.mp4")
#   2. 自动完成：脚本提炼 → 配图 → 无声视频合成

# 手动模式（指定标题和分镜）:
#   1. video_auto(
#        title="新闻大标题",
#        subtitle="副标题",
#        scenes=[
#          {"text": "字幕文案1", "duration": 4},
#          {"text": "字幕文案2", "duration": 5},
#        ],
#        output_path="news_video.mp4"
#      )

# ═══ 何时选用 video_auto（而非 video_generate / canvas） ═══

# ✅ 选用 video_auto：
#    - 用户要的是"新闻/资讯"类视频（标题+图片+字幕的竖版卡片风）
#    - 有现成文案/新闻内容，需要转化为视频
#    - 纯视觉展示，不需要动画效果
#    - 无声视频（无旁白、无BGM）

# ❌ 不选 video_auto（应选 video_generate / canvas）：
#    - 用户要的是品牌宣传片/粒子动画/数据可视化动效
#    - 需要复杂的Canvas动画效果
#    - 内容不是新闻/资讯类，而是纯视觉创意
#    - 需要配音、BGM 等音频元素

# ═══ 输出目录约定 ═══

# 默认输出到当前工作目录，LLM 应根据项目组织自行决定 output_path。
# 配图缓存放在 video_work/images/ 目录。

# ═══ 依赖要求 ═══

# 首次使用需安装:
#   pip install moviepy pillow httpx numpy

# API 配置（由 Sigma 统一管理）:
#   - LLM API（Anthropic Messages 协议）：脚本提炼
#   - 火山方舟 ARK API：AI 图片生成
#   - Tavily API：图片搜索
#   - Vision API（Anthropic Messages 协议）：图片视觉判断
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── video_auto ──
# 新闻竖版无声短视频一键生成（纯视觉，无旁白/无BGM）。
#
# 参数:
#   output_path (string, 必填) 输出 MP4 文件路径（绝对路径或相对路径）
#   news_content (string, 可选) 新闻原文或内容，提供后自动提炼标题和分镜
#   title (string, 可选) 大标题（若提供 news_content 可留空自动提炼）
#   subtitle (string, 可选) 副标题
#   scenes (array, 可选) 场景列表 [{"text":"字幕文案","duration":5}]。提供 news_content 时自动生成
#   image_source (string, 可选, 默认auto) 图片来源策略: auto | search | generate | mixed
#   image_style (string, 可选) AI生成图片风格前缀，默认"现代科技新闻插画风格，高清，适合竖屏视频背景"
#   width (integer, 可选, 默认1080) 视频宽度
#   height (integer, 可选, 默认1920) 视频高度（竖版9:16）
#   fps (integer, 可选, 默认30) 帧率
#   title_height (integer, 可选, 默认560) 标题区域高度（px）
#   image_height (integer, 可选, 默认640) 图片卡片高度（px）
# ---------------------------------------------------------------------------
