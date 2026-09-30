# read_pdf skill
# ---------------------------------------------------------------------------
# 摘要
# 读取 PDF 文件内容。自动检测页面类型:
#   - 文本型页面 → 直接提取文字 (PyMuPDF)
#   - 图片型页面（扫描件） → 渲染为 PNG → LLM Vision API 识别
# OCR 功能独立于主 LLM，需在 Skill Keys → PDF Vision OCR 中配置独立的 API Key。
#
## 使用场景
# - 读取文本型 PDF
# - 读取扫描件/图片型 PDF
# - 混合 PDF（部分文本 + 部分扫描页）
#
# 包含 1 种工具:
#   read_pdf - 读取 PDF 文件
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── read_pdf ──
# 读取 PDF 文件，自动处理文本页和图片页。
#
# 参数:
#   file_path (string, 必填) PDF 文件路径
#   page_range (string, 可选) 页码范围 "1-5" 或 "1,3,5"，默认全部
#   image_dpi (integer, 可选) 图片页渲染 DPI，默认 150
#       低 DPI (100-150) 省 token，高 DPI (200-300) 更高清晰度
#   ocr (boolean, 可选) 是否启用视觉识别，默认 true
#       关闭时图片页返回占位提示
#
# OCR 配置:
#   Settings → Skill Keys → PDF Vision OCR:
#     Vision API Key  - 支持 Anthropic 协议的多模态模型 API Key
#     Vision Model    - 模型名，如 MiniMax-M3 / claude-sonnet-4 / glm-4v
#     Vision Base URL - API 地址，如 https://api.minimaxi.com/anthropic
#     协议: Anthropic Messages API（已强制关闭 thinking，确保速度）
#
# 依赖: PyMuPDF (fitz), Pillow
# ---------------------------------------------------------------------------
