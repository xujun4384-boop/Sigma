# image_to_image skill
# ---------------------------------------------------------------------------
# 摘要
# AI 图生图技能（工具名: `generate_image_from_images`，不要使用 `image_to_image`）。
# 根据文本提示词 + 参考图片调用图像生成服务（火山引擎 ARK Seedream
# 或 MiniMax image-01），支持单张参考图（图生图、风格迁移、主体一致性）和
# 多张参考图（多图融合、组图）。
#
# 复用 Settings → Skill Keys → ImageGen 中已经配置好的图片生成通道，按
# provider 自动适配请求 payload，不需要额外配置。
#
## 使用场景
# - 用户说"基于这张图帮我..."、"把这张图换成..."、"把这两张图融合成..."
# - 主体一致性：参考一张人物照片生成新场景
# - 风格迁移：参考风格图生成新画面
# - 多图融合：参考多张素材合成新图
# - 图像编辑：上传原图 + 编辑指令，输出新图
#
# 包含 1 种子操作:
#   generate_image_from_images - 根据参考图片和提示词生成新图
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── generate_image_from_images ──
# 调用 AI 图生图服务生成图片并保存到本地。
#
# 参数:
#   prompt (string, 必填) 图片生成提示词，描述想要的画面或对参考图的处理方式。
#         示例: "把图中人物换成在雪山背景下穿红色外套的写实摄影风格"
#   save_dir (string, 必填) 图片保存目录。LLM 应根据项目目标文件夹自行决定。
#         示例: "output/images"
#   images (array, 必填) 参考图片列表，至少 1 项，每项可以是:
#         - 本地文件路径（绝对路径或相对当前工作目录）
#         - http(s) URL（图片生成服务能直接访问）
#         - data:image/...;base64,...（纯 base64 也可）
#         本地图片会自动读取、压缩、编码为 JPEG 后上传；超过最长边 1024 px 的图片会被压缩。
#   size (string, 可选, 默认 "2K") 输出尺寸。
#         ARK Seedream 4/4.5/5.0: "2K"、"1024x1024"、像素字符串均可。
#         MiniMax: 仅识别比例字符串（"1:1"、"16:9"、"4:3"、"3:2"、"2:3"、"3:4"、"9:16"、"21:9"），
#                  其它形式会回落到 1:1。
#   model (string, 可选) 模型名称。不填则使用 Settings 中配置的模型
#         （Settings → Skill Keys → ImageGen → Model）。
#   watermark (boolean, 可选, 默认 true) 是否在生成的图片上添加水印。
#   n (integer, 可选, 默认 1) 生成图片数量（仅 ARK 适用，MiniMax 自动忽略）。
#
# 输出: 生成图片的文件路径、尺寸、格式、参考图数量信息。
#
# API key 配置:
#   与图片生成（image_generate）共用同一套配置。在 Settings → Skill Keys → ImageGen 中
#   选择 Provider（火山 ARK 或 MiniMax），填入对应的 Key / BaseURL / Model 即可。
#   - 火山 ARK 推荐: doubao-seedream-4-5-251128、doubao-seedream-4-0-250828
#   - MiniMax 推荐: image-01
# ---------------------------------------------------------------------------

# 注意事项
# 1. 与 image_generate 共用同一通道，无需在 Skill Keys 中新增任何字段
# 2. MiniMax image_generation 当前仅支持单张参考图；传入多张时工具会自动取首张并提示
# 3. ARK Seedream 4.5 / 4.0 最多支持 14 张参考图；过多时会被截断
# 4. 本地参考图会自动压缩到 1024 px 最长边，避免 payload 过大
# 5. 图片生成需要消耗 API 额度
# 6. 生成时间通常在 5-30 秒，多图融合略慢
# 7. save_dir 必须由 LLM 根据项目目标文件夹自行决定，不要写死