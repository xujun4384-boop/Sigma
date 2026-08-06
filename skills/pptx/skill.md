# convert_pptx skill
# ---------------------------------------------------------------------------
# 摘要
# 使用 Kimi PPTD DSL 中间格式生成 PowerPoint/PPTX 演示文稿。
# LLM 按以下规范生成 .pptd + .page 文件，再调用 convert_pptx 转换为 .pptx。
# 支持多智能体协作：超过 20 页的 PPT 通过 sub_agent 并行生成。
#
## 使用场景
# - 从零创建 PPT 演示文稿（支持大规模多页 PPT）
# - 将长文档/论文/报告转化为演示文稿
# - 基于大纲快速生成结构化 PPT
# - 按主题搜索并生成 PPT
# - 自动兼容旧版 PPTD 格式（type→elementType, shape→shapeName, ratio→size 等）
#
# 创建 PPT 的完整流程（按顺序执行）:
#   1. 读取用户上传的所有文件
#   2. 分析需求 → 确定内容模式（摘要/大纲/搜索）+ 视觉模式（创意/参考）
#   3. 内容设计: write_file 产出 <项目>/pptx_work/<名称>/outline.md
#   4. 视觉设计: write_file 产出 <项目>/pptx_work/<名称>/design.md
#   5. 生成文件:
#      a. write_file 产出 <项目>/pptx_work/<名称>/<名称>.pptd（主文件，定义主题+页列表）
#      b. write_file 产出 <项目>/pptx_work/<名称>/pages/*.page（每页一个文件）
#      注意: 文件后缀必须用 .page 而非 .ppage！
#   6. 检查+转换: convert_pptx(input_path=".../<名称>.pptd", action="check_convert")
#      → 如有错误，按输出修复后重试
#
# 文件目录结构:
#   <项目>/pptx_work/<名称>/
#   ├── design.md
#   ├── outline.md
#   ├── <名称>.pptd
#   └── pages/
#       ├── cover.page
#       ├── slide_01.page
#       └── ...
#
# 关键格式禁忌（常见错误）:
#   ❌ 不要用: title: / subtitle: / author: / ratio: / aspect_ratio: / layout: / type:
#   ✅ 必须用: size: / elementType: / pageType: / bounds: / content.text: / elementId:
#   ❌ 页面文件后缀: .ppage ❌  →  .page ✅
#   ❌ 分散的 x/y/width/height → 必须用 bounds: [x, y, w, h]
#   ❌ content.text 用的引号包裹 → 必须用 YAML block scalar | 格式
#
# 包含 1 种工具:
#   convert_pptx - 检查并转换 .pptd 为 .pptx（含自动格式规范化）
# ---------------------------------------------------------------------------

# ═══ .pptd 主文件格式（必须严格遵守）═══

# .pptd 文件是 YAML，结构:
#
# size: [1280, 720]            # 必须，不用 aspect_ratio
# theme:
#   name: "自定义主题"
#   colors:
#     background: "#FFFFFF"
#     text: "#111827"
#     textSecondary: "#374151"
#     accent: "#0B2545"
#     primary: "#0B2545"
#   textStyles:                 # 必须，不用 theme.fonts
#     title:
#       fontFamily: "Microsoft YaHei"
#       fontSize: 40
#       color: "#F8FAFC"
#     body:
#       fontFamily: "Microsoft YaHei"
#       fontSize: 18
#       color: "#111827"
# pages:                        # YAML 列表，每项是 .page 文件路径
#   - pages/cover.page
#   - pages/slide_01.page
#   - pages/slide_02.page
#
# ❌ 绝对不要用: title: / subtitle: / author: / ratio: / layout: 这些不是 PPTD DSL 字段
# ---------------------------------------------------------------------------

# ═══ .page 文件格式（必须严格遵守）═══

# .page 文件是 YAML，结构:
#
# pageType: content             # cover / table_of_contents / chapter / content / ending
# background:
#   type: solid                 # solid / gradient / image
#   color: "#FFFFFF"            # type=solid 时用
# elements:
#   - elementId: title_text
#     elementType: text
#     bounds: [80, 60, 1120, 70]    # [x, y, width, height] px
#     content:
#       text: "<p>页面标题</p>"      # HTML 标签
#       fontFamily: "Microsoft YaHei"
#       fontSize: 40
#       color: "#111827"
#   - elementId: body_text
#     elementType: text
#     bounds: [80, 160, 1120, 400]
#     content:
#       text: "<p>正文内容</p><p>第二段</p>"
#       fontFamily: "Microsoft YaHei"
#       fontSize: 18
#       color: "#374151"
#   - elementId: rect_shape
#     elementType: shape
#     shapeName: rect            # rect / roundRect / ellipse / line
#     bounds: [50, 50, 200, 40]
#     fill:
#       type: solid
#       color: "#0B2545"
#     border:
#       style: solid
#       width: 1
#       color: "#0B2545"
#   - elementId: logo_image
#     elementType: image
#     bounds: [1000, 20, 180, 60]
#     src: "C:/absolute/path/to/logo.png"    # 必须绝对路径或 http(s) URL
#
# ❌ 绝对不要用: type: / layout: / background_color: / decoration:
#   content.text 必须在 content 对象里面，不是顶级字段
#   bounds 是四元素数组 [x, y, w, h]，不是单独的 x/y/width/height
# ---------------------------------------------------------------------------

# ═══ 最小完整示例 ═══

# 主 .pptd 文件（presentation.pptd）:
# ```yaml
# size: [1280, 720]
# theme:
#   name: "商务主题"
#   colors:
#     background: "#FFFFFF"
#     text: "#111827"
#     textSecondary: "#374151"
#     accent: "#2563EB"
#     primary: "#2563EB"
#   textStyles:
#     title:
#       fontFamily: "Microsoft YaHei"
#       fontSize: 40
#       color: "#111827"
#     body:
#       fontFamily: "Microsoft YaHei"
#       fontSize: 18
#       color: "#374151"
# pages:
#   - pages/cover.page
#   - pages/content.page
# ```

# 封面页（pages/cover.page）:
# ```yaml
# pageType: cover
# background:
#   type: solid
#   color: "#0B2545"
# elements:
#   - elementId: title
#     elementType: text
#     bounds: [80, 200, 1120, 100]
#     content:
#       text: "<p>演示标题</p>"
#       fontFamily: "Microsoft YaHei"
#       fontSize: 48
#       color: "#FFFFFF"
#   - elementId: subtitle
#     elementType: text
#     bounds: [80, 340, 1120, 60]
#     content:
#       text: "<p>副标题</p>"
#       fontFamily: "Microsoft YaHei"
#       fontSize: 24
#       color: "#C5A572"
# ```

# 内容页（pages/content.page）:
# ```yaml
# pageType: content
# background:
#   type: solid
#   color: "#FFFFFF"
# elements:
#   - elementId: title
#     elementType: text
#     bounds: [80, 60, 1120, 60]
#     content:
#       text: "<p>标题</p>"
#       fontFamily: "Microsoft YaHei"
#       fontSize: 36
#       color: "#0B2545"
#   - elementId: body
#     elementType: text
#     bounds: [80, 150, 1120, 500]
#     content:
#       text: "<p>正文第一段</p><p>正文第二段</p>"
#       fontFamily: "Microsoft YaHei"
#       fontSize: 18
#       color: "#111827"
# ```

# ═══ convert_pptx 工具参数 ═══

# ── convert_pptx ──
# 参数:
#   input_path (string, 必填) .pptd 主文件路径
#   output_path (string, 可选) 输出 .pptx 路径
#   action (string, 可选) check / convert / check_convert（默认）

# 自动规范化（转换前自动修复旧格式）:
#   - ratio / aspect_ratio → size
#   - type → elementType / pageType
#   - shape → shapeName
#   - fonts → textStyles
#   - .ppage 文件自动重命名为 .page
#   - 清理无效字段（title/subtitle/author/layout/decoration 等）

# 工作流程:
#   1. 在 <项目>/pptx_work/<名称>/ 下生成 presentation.pptd + pages/*.page
#   2. 调用 convert_pptx(input_path=".../presentation.pptd")
#   3. 如有错误，按 checker 输出修复后重试
#   4. .pptx 输出到项目根目录
#
# 详细格式规范: format/pptd.md
# 多智能体工作流: guideline/generate_slides.md
# ---------------------------------------------------------------------------
