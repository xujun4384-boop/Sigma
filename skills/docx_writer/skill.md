# docx_writer skill
# ---------------------------------------------------------------------------
# 摘要
# Word 文档创建技能。推荐使用 outline 模式：主 LLM 只需提供写作大纲/指令，
# 由子 Agent 独立生成全文并写入，避免长文档内容撑爆主对话 token 上限。
#
## 使用场景
# - 需要根据内容生成格式化的 Word 文档
# - 需要创建合同、报告等特定类型的专业文档
# - 需要生成带标题层级、表格的标准排版文档
#
# 包含 1 种子操作:
#   write_docx - 创建 Word 文档
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── write_docx ──
# 创建新的 Word (.docx) 文档。
#
# ⚠️ 重要：blocks / outline（推荐）/ content（仅简短文档）三选一传入。
#   优先级: blocks > outline > content
#
# 通用参数:
#   output_path (string, 必填) 输出路径，必须以 .docx 结尾。
#   doc_type    (string, 可选, 默认 "general") 文档类型:
#               general | contract | report | documentation | official
#               (仅影响 outline/content 模式，blocks 模式不使用)
#   title       (string, 可选) 文档标题
#
# 【推荐】outline 模式（子 Agent 独立生成，不占主对话 token）:
#   outline     (string) 文档大纲/写作指令。子 Agent 将根据大纲生成完整内容。
#               必须包含: 文档结构（章节划分）、每章要点、关键数据/引用、写作风格。
#               示例: "一份关于2026年AI趋势的报告，结构: 1.引言（200字）2.核心技术..."
#
# 【精细排版】blocks 直写模式（需要精确控制字体/字号/颜色/对齐时使用）:
#   blocks      (array) 按顺序描述内容块，无需为此用 sandbox_run 手写 python-docx。
#               每项为对象，type 决定其余字段:
#               - heading: {type:"heading", text, level(1-9,可选默认1),
#                           font(可选默认黑体), size(可选按level推断), bold(可选默认true),
#                           color:[r,g,b](可选), align(可选 left|center|right|justify)}
#               - paragraph: {type:"paragraph",
#                           text 或 runs:[{text,bold,italic,color:[r,g,b],font,size}],
#                           font(可选默认仿宋), size(可选默认14), align(可选),
#                           space_before(可选,pt), space_after(可选,pt),
#                           line_spacing(可选默认1.5), indent(可选,cm,默认0.74)}
#                           - 一段内需要多种格式混排时用 runs，不需要时直接用 text
#               - table: {type:"table", rows:[["表头1","表头2"],["数据1","数据2"]],
#                           header(可选默认true,首行是否作表头样式),
#                           col_widths(可选,[cm,...]),
#                           font(可选默认微软雅黑), size(可选默认10),
#                           header_color:[r,g,b](可选默认浅蓝)}
#               - page_break: {type:"page_break"} 插入分页符
#               示例（精美封面 + 正文段落 + 表格）:
#               [
#                 {"type":"heading","text":"日照旅游攻略","level":0,
#                  "font":"微软雅黑","size":36,"bold":true,
#                  "color":[0,102,153],"align":"center"},
#                 {"type":"paragraph","text":"本攻略涵盖交通、住宿、景点...",
#                  "align":"center","size":12},
#                 {"type":"page_break"},
#                 {"type":"heading","text":"一、交通方案","level":1},
#                 {"type":"table","rows":[["方式","时长","价格"],["高铁","3小时","300元"]]}
#               ]
#
# 【仅简短文档】content 直写模式:
#   content     (string) 直接传入完整正文内容。仅适用 <500 字文档，长文档用 outline。
#               多段落用换行分隔。支持基本 Markdown: ## 二级标题 / ### 三级标题 /
#               | 表格行 | / **加粗**
#
# contract 合同专用:
#   number     (string, 可选) 合同编号
#   party_a    (string, 可选) 甲方名称
#   party_b    (string, 可选) 乙方名称
#   clauses    (array, 可选) 条款列表 [{"title":"...", "contents":["..."]}]
#   signature_date (string, 可选) 签署日期
#
# report 报告专用:
#   subtitle   (string, 可选) 副标题
#   author     (string, 可选) 作者
#   date       (string, 可选) 日期
#   sections   (array, 可选) 章节 [{title, subsections[{title, paragraphs[]}]}]
#
# official 公文专用:
#   issuer     (string, 可选) 发文机关
#   doc_number (string, 可选) 发文字号
#   recipient  (string, 可选) 主送机关
#   issuer_name(string, 可选) 发文机关署名
#   issue_date (string, 可选) 成文日期
#
# documentation 技术文档专用:
#   version    (string, 可选) 版本号
