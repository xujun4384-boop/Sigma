# image_reader skill
# ---------------------------------------------------------------------------
# 摘要
# 读取本地图片，并以压缩后的 Base64 图像调用视觉模型识别内容。
# 优先使用 Settings → Skill Keys → 图片读取 中指定的「读图模型」；未指定时跟随主 LLM。
# 根据识别目标选择三档处理策略，降低大图的网络传输与视觉 token 消耗。
# Vision 请求统一给 8K 输出额度（思考与正文共用），并强制压低思考：
# 各 provider 先尝试彻底关闭思考（thinking: disabled），端点拒绝（4xx）再退到低强度：
# MiniMax 关闭失败时退 output_config.effort=low（Anthropic）或 reasoning_effort=low（OpenAI）；
# Kimi Code 的 Anthropic 兼容端点无法关闭思考，自动切到同 host 的 OpenAI 端点 + reasoning_effort=low；
# Kimi 标准 / DeepSeek / 火山方舟 直接 thinking: disabled。
# 若端点拒绝思考字段（4xx），自动按候选列表降级重试；默认视觉超时 120 秒。
# 需要配置支持 Anthropic 协议的多模态模型（MiniMax M3 / Claude / GLM-4V / 豆包等）。
#
# 包含 2 种子操作:
#   preview_image - 生成缩略预览和图片元信息
#   read_image    - 压缩图片并调用 Vision API 识别
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── read_image ──
# 参数:
#   file_path (string, 必填) 图片文件路径，支持相对和绝对路径。
#   image_quality (string, 可选，默认 balanced) 图片传输档位：
#     - high: 文字、表格或细节识别。最长边 1600px，PNG 无损编码。
#     - balanced: 一般图片理解。最长边 1024px，JPEG quality=75。
#     - low: 不涉及读文字时的快速内容理解。最长边 512px，JPEG quality=50。
#   max_size (integer, 可选) 覆盖所选档位的最长边限制；不传则使用档位默认值。
#   max_tokens (integer, 可选，默认 8192) 每个识别区域的最大输出 token 数。
#   rotate (integer, 可选，默认 0) 顺时针旋转角度：0、90、180 或 270。
#   split_rows (integer, 可选，默认 1) 沿高度分区识别，密集表格可设为 2–4。
#   prompt (string, 可选) 自定义识别提示。
#   convert_to_base64 (boolean, 可选，默认 false) 未配置 Vision API 时，是否返回压缩后的 Base64 数据。
#   include_info (boolean, 可选，默认 true) 是否返回图片处理元信息。
#
# 注意事项
# 1. 文字、表格、票据和细节图必须使用 high；普通图片理解使用 balanced。
# 2. low 会明显缩小和有损压缩图片，不适用于文字提取。
# 3. 实际发送的 MIME 类型随档位变化：high 为 image/png，其余为 image/jpeg。
# 4. Base64 数据只会保存在 ToolResult.details 中，不会写入正文内容。
# ---------------------------------------------------------------------------
