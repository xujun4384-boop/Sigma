# video_produce skill
# 完整视频流水线，带旁白+字幕。区别于 video_card（竖版无声卡片）与 video_cinematic（电影级AI生视频）。
# ---------------------------------------------------------------------------
# 摘要
# 视频制作流水线。主 LLM 只传用户需求，脚本/分镜/旁白/时长/图片全部由本工具内部的
# design LLM 完成。脚本设计后返回给主 LLM 让用户确认，确认后自动跑完剩余流水线。
# 产出带旁白 + 字幕的最终 mp4。
#
## 使用场景
# - 品牌宣传片 / 产品介绍 / 广告片
# - 任何「需求 → 脚本确认 → 自动化成片」的视频制作
#
# ═══ 分工（关键） ═══
#
# 主 LLM（只负责两件事，绝对不要自己创作内容）:
#   1. 把用户需求原样传给 video_produce（brief 参数）
#   2. 脚本设计完成后，用 ask_user 让用户确认（可修改），确认后再次调用 video_produce
#
# video_produce（内部由 design LLM 完成所有内容创作）:
#   Stage 0 脚本设计   design LLM 设计分镜 + 旁白文案 + 视觉风格
#   Stage 1 旁白       doubao_tts 生成 → 权威时长 + 字级时间戳
#   Stage 2 画面规划   design LLM 决定图需求
#   Stage 3 配图       image_generate 按图需求
#   Stage 4 画面       opendesign 写 HTML + 渲染（时长=旁白时长）
#   Stage 5 合成       video_compose 叠加旁白 + 字幕
#
# ⚠️ 铁律：
#   - 主 LLM 不要自己设计脚本、定时长、生成图片 —— 全部由 video_produce 内部的 design LLM 做
#   - 时长由旁白实际读速决定（Stage 1 产出）
#   - 图片由 design LLM 决定（Stage 2），主 LLM 在脚本阶段不碰图
#   - 每阶段失败自动重试 6 次，超过熔断停止（不回退、不跳步）
#
# ═══ 两阶段调用 ═══
#
# 第一次（设计脚本）:
#   video_produce(brief="<用户需求原文>", output_path="final.mp4", project="xxx")
#   → 返回 design LLM 设计的脚本，请用 ask_user 让用户确认（可修改）
#
# 第二次（确认后制作）:
#   video_produce(brief="<用户需求原文>", script="<确认后的脚本JSON>", output_path="final.mp4", project="xxx")
#   → 自动跑完 Stage 1-5，返回最终 mp4
#
# ═══ 参数 ═══
# brief (string, 必填) 用户需求描述
# output_path (string, 必填) 最终输出 mp4 路径
# script (string, 可选) 确认后的脚本 JSON（第二次调用时传，跳过脚本设计）
# project (string, 可选) 项目名
# speaker (string, 可选) 旁白音色ID，默认广告解说2.0
# fps / width / height (integer, 可选)
# ---------------------------------------------------------------------------
