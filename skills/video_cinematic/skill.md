# video_cinematic skill
# ⚠️ 制作视频统一走 director 导演组；本技能是「影视级画面引擎」，一般由导演调度（受套餐视频额度限制）。
# 电影级 AI 视频生成（纯 prompt，不走代码）。区别于 video_card（竖版无声卡片）与 video_produce（带旁白完整流水线）。
# ---------------------------------------------------------------------------
# 摘要
# 电影级 AI 视频生成。服务商由 Settings → Skill Keys → 影视级视频生成 选择：
#   - minimax（默认）：MiniMax-Hailuo-2.3
#   - ark：火山方舟 / 豆包 Seedance 系列
# 通过纯文本提示词驱动，生成具有电影感画面的高质量视频。
#
# 与现有视频 skill 的核心区别：
#   - video_generate → HTML Canvas 动画录制（程序化、可逐帧控制）
#   - video_auto     → 新闻竖版卡片视频（自动配图+打字机字幕）
#   - video_custom   → 自定义竖版视频（手动指定素材+样式）
#   - video_cinematic → 所选服务商的电影级 AI 视频（纯 prompt 驱动）
#
# ⚠️ 重要特性：
#   1. 纯提示词生成：只接受文本 prompt，不支持图片/视频/音频参考输入
#   2. 生成后不可修改：任务一旦提交即消耗配额，无法中途调整或重新编辑
#   3. 每次调用消耗一次视频额度；套餐不再单独显示每日视频条数，按统一周额度扣减。
#      - 不再查询视频额度接口；提交后按实际生成扣减，具体以对应服务商控制台为准。
#      - 导演组默认每支片只用 1 段 cinematic，用户可在 ask_user 明确要求 0/2/3 段。
#   4. 支持 [运镜指令] 语法（Hailuo 与 Seedance 均支持 prompt 内的镜头描述）
#   5. 【无声视频】两个服务商默认都生成无声视频，不含原生音轨。
#
# ## 使用场景
# - 电影级短片/预告片
# - 品牌概念片/氛围视频
# - 产品概念展示（非功能演示）
# - 艺术创意视频
# - 任何需要"AI 电影感画面"的场景
#
# 包含 2 种工具:
#   video_cinematic_storyboard - 分镜脚本设计（LLM 将用户意图拆解为电影分镜）
#   video_cinematic_generate   - 电影级视频生成（提交所选服务商的文生视频任务）
# ---------------------------------------------------------------------------

# ═══ 核心工作流程 ═══

# 步骤 1: 分镜脚本设计
#   video_cinematic_storyboard(
#     user_intent="用户想要视频的文字描述",
#     total_duration=30,           # 默认 30s = 3 个 10s 分镜（按实际需要调整）
#     style="cinematic"            # 视觉风格参考
#   )
#   → 返回: {"scenes": [{"prompt": "...", "duration": 10, "camera": "...", "mood": "..."}]}
#
# 步骤 2: 逐镜生成（每个 scene 调用一次，建议用满 10s）
#   video_cinematic_generate(
#     prompt="分镜详细提示词",
#     duration=10,                 # 默认 10s（768P 支持的最长时长）
#     resolution="768P",
#     output_path="scene_01.mp4"
#   )
#   → 返回: {"task_id": "...", "status": "succeeded", "output_path": "..."}
#
# 步骤 3: 多镜拼接（可选，使用 video_compose）
#   如果需要多个分镜拼接成完整短片，使用 video_generate 的 video_compose 工具。
#   ⚠️ 注意：video_compose 默认**不叠加字幕、不生成 BGM**，只做纯净拼接。
#   如需字幕，需显式传 subtitles 参数。

# ═══ 何时选用 video_cinematic（而非其他视频 skill） ═══

# ✅ 选用 video_cinematic：
#    - 用户要"电影感"、"大片感"、"AI 生成画面"
#    - 内容偏概念/氛围/艺术，不需要精确控制每帧
#    - 接受"生成后不可修改"的限制
#    - 接受按套餐视频额度扣减（不再单独赠送每日条数）
#
# ❌ 不选 video_cinematic：
#    - 需要精确控制动画每帧 → 选 video_generate
#    - 新闻资讯卡片视频 → 选 video_auto
#    - 需要自定义素材+样式 → 选 video_custom
#    - 需要后期编辑/修改 → 选 video_generate（可重新录制）

# ═══ ⚠️ 重要限制说明 ═══

# 1. 【生成后不可修改】
#    视频生成任务是异步的，提交后立即开始消耗配额。
#    无法在生成过程中调整 prompt、修改参数或取消任务。
#    因此，调用 video_cinematic_generate 前，必须确保 prompt 已经过精心打磨。
#
# 2. 【视频额度】
#    套餐不再单独赠送/显示每日视频条数；每次生成按套餐统一周额度扣减。
#    实测 6 秒 768P 约扣 7% 周额度，10 秒 768P 约扣 14%（以控制台为准）。
#    额度用完后，可购买积分或改用按量计费 API Key（768P 6s ≈ 2 元，10s ≈ 4 元）。
#
# 3. 【纯文本驱动】
#    本 skill 仅支持文生视频（T2V），不支持图片/视频/音频参考输入。
#    如需图生视频，请直接使用 MiniMax API 或后续扩展。
#
# 4. 【时长限制】
#    - MiniMax Hailuo：768P 下单镜最长 10 秒（1080P 仅支持 6 秒）。
#    - 火山方舟 Seedance 1.0 Pro：支持 2~12 秒整数时长；具体档位以所选模型为准。
#    额度按实际生成扣减：6 秒和 10 秒分别计价，不存在“按条数用满 10 秒更划算”。
#    按剪辑需要选时长即可；10 秒约为 6 秒消耗的两倍。

# ═══ 输出目录约定 ═══

# 默认输出到当前工作目录的 video_work/cinematic/ 目录。
# 每个分镜视频独立保存，最终可拼接。

# ═══ 依赖要求 ═══

# 首次使用需安装:
#   pip install httpx
#
# API 配置（由 Sigma 统一管理，Settings → Skill Keys → 影视级视频生成）:
#   - 选择 minimax：填 MiniMax Token Plan API Key（Hailuo2.3）
#   - 选择 ark：填火山方舟 API Key（豆包 Seedance；可填 Model ID 或 Endpoint ID）
#   - LLM API（Anthropic Messages 协议）：分镜脚本设计
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── video_cinematic_storyboard ──
# 将用户意图拆解为电影分镜脚本。
#
# 参数:
#   user_intent (string, 必填) 用户想要视频的文字描述
#   total_duration (integer, 可选, 默认30) 目标总时长（秒）。默认 30 = 3 个 10s 分镜
#   style (string, 可选, 默认"cinematic") 视觉风格参考
#   scene_count (integer, 可选) 分镜数量，不提供则自动计算
#
# 返回:
#   {
#     "title": "视频标题",
#     "logline": "一句话剧情概括",
#     "scenes": [
#       {
#         "scene_id": 1,
#         "prompt": "详细提示词（英文，包含镜头/光影/氛围/动作）",
#         "prompt_zh": "中文分镜说明",
#         "duration": 10,
#         "camera": "镜头运动描述",
#         "mood": "情绪/氛围关键词",
#         "lighting": "光影描述"
#       }
#     ],
#     "total_duration": 30,
#     "style_notes": "整体视觉风格说明"
#   }

# ── video_cinematic_generate ──
# 提交所选服务商（minimax / ark）的文生视频任务并等待完成。
#
# 参数:
#   prompt (string, 必填) 视频生成提示词（建议英文，效果最佳）
#   output_path (string, 必填) 输出 MP4 文件路径
#   duration (integer, 可选, 默认10) 视频时长（秒），通常 6 或 10
#   resolution (string, 可选, 默认"768P") 分辨率：768P / 1080P（ark 会自动换算为 720p / 1080p）
#   poll_interval (integer, 可选, 默认10) 轮询间隔（秒）
#   max_wait (integer, 可选, 默认1800) 最大等待时间（秒）
#
# 返回:
#   {
#     "task_id": "服务商任务 ID",
#     "status": "succeeded",
#     "output_path": "本地视频路径",
#     "video_url": "CDN 地址",
#     "duration": 10,
#     "resolution": "768P",
#     "size_mb": 12.5
#   }
# ---------------------------------------------------------------------------
