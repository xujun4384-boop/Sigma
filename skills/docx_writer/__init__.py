"""
docx_writer skill - 创建 Word 文档 (.docx)

提供 write_docx 工具，支持通用文档、合同、报告、技术文档、公文等多种类型。

推荐使用 outline 模式：主 LLM 只需提供写作大纲/指令，工具内部用 LLM 展开后直接写入。
content 模式仅适用于简短文档（<500字）。
"""
import json
import os
from typing import Any
from skills.base import BaseTool, ToolParameter, ToolResult


class WriteDocxTool(BaseTool):
    name = "write_docx"
    description = (
        "创建新的 Word (.docx) 文档。\n"
        "- outline: 传入写作大纲/指令，工具自动展开为完整文档（适合长文档）\n"
        "- content: 传入完整正文内容直接写入（适合短文档，<500字）\n"
        "- blocks: 精细排版，逐块指定标题/段落/表格/字体（适合特殊排版需求）\n"
        "支持 general/contract/report/documentation/official 五种类型。"
    )
    parameters = [
        ToolParameter("output_path", "string", "必填。输出文件路径，如 'output.docx' 或 '/path/to/report.docx'"),
        ToolParameter("doc_type", "string", "文档类型: general|contract|report|documentation|official", required=False, default="general"),
        ToolParameter("title", "string", "文档标题（可选）", required=False),
        ToolParameter("outline", "string", "【推荐】文档大纲/写作指令。子 Agent 将根据大纲生成完整内容并写入文档。示例: '一份关于AI发展趋势的报告，包含：1. 引言 2. 核心技术 3. 市场应用 4. 展望。数据参考上面搜索结果：...'", required=False),
        ToolParameter("content", "string", "【仅简短文档】直接传入的完整正文内容，多段落用换行分隔。仅适用 <500 字文档。", required=False),
        ToolParameter("blocks", "array", (
            "【精细排版】按顺序描述内容块，每块可单独指定字体/字号/颜色/加粗/斜体/对齐/间距。"
            "每项为对象，type 决定其余字段：\n"
            "- heading: {type:'heading', text, level(1-9), font, size, bold, color:[r,g,b], align}\n"
            "- paragraph: {type:'paragraph', text 或 runs:[{text,bold,italic,color:[r,g,b],font,size}], "
            "font, size, align, space_before, space_after, line_spacing, indent}\n"
            "- table: {type:'table', rows:[[cell,...],...], header:true, col_widths:[cm,...], "
            "font, size, header_color:[r,g,b]}\n"
            "- page_break: {type:'page_break'}\n"
            "align 取值: left|center|right|justify。颜色为 [R,G,B] 0-255 整数数组。"
        ), required=False),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict | None = None, skill_manager=None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self._skill_manager = skill_manager

    def execute(self, output_path: str, doc_type: str = "general", title: str = "",
                content: str = "", outline: str = "", blocks: list | None = None, **kwargs) -> ToolResult:
        # ── blocks 精细排版模式（优先级最高，显式声明逐块样式）──
        if blocks:
            return self._execute_via_blocks(output_path, title, blocks)

        # ── outline 模式（LLM 展开大纲后直接写入）──
        if outline:
            return self._execute_via_outline(output_path, doc_type, title, outline, **kwargs)

        # ── content 直写模式（兼容，适用简短文档）──
        full_path = output_path if os.path.isabs(output_path) else os.path.join(self.cwd, output_path)

        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("output_path 必须以 .docx 结尾")

        output_dir = os.path.dirname(full_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        try:
            from docx import Document
            from docx.shared import Cm, Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml.ns import qn
        except ImportError:
            return ToolResult.fail("缺少 python-docx 库，请运行: pip install python-docx")

        try:
            handlers = {
                "general": self._create_general,
                "contract": self._create_contract,
                "report": self._create_report,
                "documentation": self._create_documentation,
                "official": self._create_official,
            }
            handler = handlers.get(doc_type, self._create_general)
            handler(full_path, title, content, **kwargs)
            return ToolResult.ok(f"文档已创建: {full_path}", path=full_path, doc_type=doc_type)
        except Exception as e:
            return ToolResult.fail(f"创建文档失败: {e}")

    # ─── 公共样式方法 ───

    def _setup_document(self, doc):
        from docx.shared import Cm
        sections = doc.sections[0]
        sections.top_margin = Cm(2.54)
        sections.bottom_margin = Cm(2.54)
        sections.left_margin = Cm(3.17)
        sections.right_margin = Cm(3.17)

    def _set_font(self, run, name='仿宋', size=14, bold=False, color=None):
        from docx.shared import Pt, RGBColor
        from docx.oxml.ns import qn
        run.font.name = name
        run._element.rPr.rFonts.set(qn('w:eastAsia'), name)
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = RGBColor(*(color or (0, 0, 0)))

    def _safe_set_font(self, para, name='仿宋', size=14, bold=False, color=None):
        """安全设置段落首个 run 的字体。如果段落没有 run，自动创建一个。"""
        if para.runs:
            self._set_font(para.runs[0], name, size, bold, color)
        else:
            # 段落无 run（空标题等），添加一个空 run
            run = para.add_run('')
            self._set_font(run, name, size, bold, color)

    def _set_para_format(self, para, indent=0.74, spacing=1.5, space_before=0, space_after=0, alignment=None):
        from docx.shared import Cm, Pt
        para.paragraph_format.first_line_indent = Cm(indent)
        para.paragraph_format.line_spacing = spacing
        para.paragraph_format.space_before = Pt(space_before)
        para.paragraph_format.space_after = Pt(space_after)
        if alignment:
            para.alignment = alignment

    def _add_body(self, doc, content):
        """添加正文内容。支持 Markdown：#~#### 标题、| 表格 |、**加粗**"""
        if not content:
            return
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
        import re

        paragraphs = content.split('\n') if isinstance(content, str) else content
        table_rows = []  # 收集连续的表格行
        i = 0

        def is_table_line(s: str) -> bool:
            s = s.strip()
            return s.startswith('|') and s.endswith('|') and s.count('|') >= 2

        def is_sep_row(cells) -> bool:
            return all(re.fullmatch(r':?-{2,}:?', c.replace(' ', '')) for c in cells if c.strip())

        while i < len(paragraphs):
            text = paragraphs[i]

            # 空行：结束当前表格
            if not text.strip():
                if table_rows:
                    self._flush_table(doc, table_rows)
                    table_rows = []
                i += 1
                continue

            stripped = text.strip()

            # Markdown 标题 # ~ ####
            m = re.match(r'^(#{1,4})\s+(.*)$', stripped)
            if m:
                if table_rows:
                    self._flush_table(doc, table_rows)
                    table_rows = []
                level = len(m.group(1))  # 1~4
                h = doc.add_heading(m.group(2).strip(), level=level)
                # 分级字体大小
                sizes = {1: 18, 2: 16, 3: 14, 4: 13}
                self._safe_set_font(h, '黑体', sizes.get(level, 12), bold=True)
                i += 1
                continue

            # | 表格行（兼容行首有空格/制表符）
            if is_table_line(stripped):
                cells = [c.strip() for c in stripped[1:-1].split('|')]
                if is_sep_row(cells):
                    i += 1
                    continue
                table_rows.append(cells)
                i += 1
                continue

            # 普通段落
            if table_rows:
                self._flush_table(doc, table_rows)
                table_rows = []

            p = doc.add_paragraph()
            self._parse_inline_formatting(p, stripped)
            self._set_para_format(p)
            self._safe_set_font(p)
            i += 1

        # 结尾残余表格
        if table_rows:
            self._flush_table(doc, table_rows)

    def _parse_inline_formatting(self, para, text: str):
        """解析行内格式：**加粗**"""
        import re
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                run = para.add_run(part[2:-2])
                self._set_font(run, '仿宋', 14, bold=True)
            else:
                run = para.add_run(part)
                self._set_font(run, '仿宋', 14)

    def _flush_table(self, doc, rows: list):
        """将收集的表格行写入 docx 表格（Table Grid 样式自带边框）"""
        if not rows:
            return
        from docx.shared import Pt, RGBColor, Cm
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        table = doc.add_table(rows=len(rows), cols=len(rows[0]), style='Table Grid')
        for ri, row_cells in enumerate(rows):
            for ci, cell_text in enumerate(row_cells):
                if ci >= len(table.rows[ri].cells):
                    break
                cell = table.rows[ri].cells[ci]
                cell.text = ''
                p = cell.paragraphs[0]
                run = p.add_run(cell_text)
                run.font.name = '微软雅黑'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
                run.font.size = Pt(10)
                # 表头行加粗 + 浅蓝底
                if ri == 0:
                    run.font.bold = True
                    run.font.size = Pt(10.5)
                    shading = OxmlElement('w:shd')
                    shading.set(qn('w:fill'), 'D6E4F0')
                    shading.set(qn('w:val'), 'clear')
                    cell._element.get_or_add_tcPr().append(shading)
        doc.add_paragraph()  # 表后空行

    # ─── blocks 精细排版模式 ───

    def _execute_via_blocks(self, output_path: str, title: str, blocks: list) -> ToolResult:
        """按 blocks 逐块描述生成文档，每块可独立指定字体/字号/颜色/对齐等样式。

        用于覆盖 outline/content 模式无法精确表达的精细排版需求（如封面标题指定
        字体+字号+颜色+居中），避免 LLM 为此绕道用 sandbox_run 手写 python-docx 代码。
        """
        full_path = output_path if os.path.isabs(output_path) else os.path.join(self.cwd, output_path)
        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("output_path 必须以 .docx 结尾")

        output_dir = os.path.dirname(full_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if not isinstance(blocks, list) or not blocks:
            return ToolResult.fail(
                f"blocks 必须是非空数组（list），当前类型: {type(blocks).__name__}。"
                "如果你传入的是 JSON 字符串，请先解析为 list。"
            )

        # 入口校验：每项必须是 dict，且 type 合法
        _VALID_TYPES = {"heading", "paragraph", "table", "page_break"}
        for i, blk in enumerate(blocks):
            if not isinstance(blk, dict):
                return ToolResult.fail(
                    f"blocks[{i}] 必须是对象(dict)，当前类型: {type(blk).__name__}，"
                    f"值: {str(blk)[:100]}"
                )
            btype = blk.get("type")
            if btype not in _VALID_TYPES:
                return ToolResult.fail(
                    f"blocks[{i}].type 必须是 {sorted(_VALID_TYPES)} 之一，收到: {btype!r}"
                )
            # 校验 color 字段（如果存在）
            for color_field in ("color", "header_color"):
                if color_field in blk and blk[color_field] is not None:
                    if self._color_tuple(blk[color_field]) is None:
                        return ToolResult.fail(
                            f"blocks[{i}].{color_field} 颜色格式错误，应为 [r,g,b] 整数数组（0-255），"
                            f"收到: {blk[color_field]!r}"
                        )
            # 校验 table 类型的 rows
            if btype == "table":
                rows = blk.get("rows")
                if not isinstance(rows, list) or not rows:
                    return ToolResult.fail(
                        f"blocks[{i}] (table).rows 必须是非空二维数组"
                    )
                if not all(isinstance(r, list) for r in rows):
                    return ToolResult.fail(
                        f"blocks[{i}] (table).rows 每一项必须是数组"
                    )

        try:
            from docx import Document
        except ImportError:
            return ToolResult.fail("缺少 python-docx 库，请运行: pip install python-docx")

        try:
            doc = Document()
            self._setup_document(doc)
            if title:
                h = doc.add_heading(title, level=0)
                from docx.enum.text import WD_ALIGN_PARAGRAPH
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                self._safe_set_font(h, '黑体', 22, bold=True)

            for i, block in enumerate(blocks):
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "paragraph")
                try:
                    if btype == "heading":
                        self._block_heading(doc, block)
                    elif btype == "paragraph":
                        self._block_paragraph(doc, block)
                    elif btype == "table":
                        self._block_table(doc, block)
                    elif btype == "page_break":
                        doc.add_page_break()
                    else:
                        return ToolResult.fail(f"blocks[{i}] 未知类型: {btype}")
                except Exception as e:
                    return ToolResult.fail(f"blocks[{i}] ({btype}) 渲染失败: {e}")

            doc.save(full_path)
            return ToolResult.ok(f"文档已创建: {full_path}", path=full_path, doc_type="blocks")
        except Exception as e:
            return ToolResult.fail(f"创建文档失败: {e}")

    def _align_value(self, align: str | None):
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        mapping = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }
        return mapping.get((align or "").lower())

    def _color_tuple(self, color) -> tuple | None:
        """容错解析颜色：支持 [r,g,b] / (r,g,b) / "[r,g,b]" / "#FF0000" / {"item":[r,g,b]}"""
        if color is None:
            return None
        # 字典形式（LLM 偶尔会写成 {"item": [r,g,b]}）
        if isinstance(color, dict):
            color = color.get("item") or color.get("value") or color.get("color")
        # 字符串形式：可能是 "[0,0,0]" 或 "#FF0000" 或 "0,0,0"
        if isinstance(color, str):
            s = color.strip()
            # 去掉方括号
            if s.startswith("[") and s.endswith("]"):
                s = s[1:-1]
            # 十六进制 #RRGGBB
            if s.startswith("#") and len(s) in (4, 7):
                try:
                    if len(s) == 4:
                        s = "#" + "".join(c * 2 for c in s[1:])
                    return tuple(int(s[i:i+2], 16) for i in (1, 3, 5))
                except ValueError:
                    return None
            # "0,0,0" 形式
            if "," in s:
                color = [p.strip() for p in s.split(",")]
            else:
                return None
        # 列表/元组形式
        if isinstance(color, (list, tuple)) and len(color) == 3:
            try:
                rgb = tuple(max(0, min(255, int(c))) for c in color)
                return rgb
            except (TypeError, ValueError):
                return None
        return None

    def _block_heading(self, doc, block: dict):
        text = block.get("text", "")
        level = block.get("level", 1)
        try:
            level = max(1, min(9, int(level)))
        except (TypeError, ValueError):
            level = 1
        h = doc.add_heading(text, level=level)
        align = self._align_value(block.get("align"))
        if align is not None:
            h.alignment = align
        # 分级默认字号，block 显式传入的优先
        default_sizes = {1: 18, 2: 16, 3: 14, 4: 13, 5: 12, 6: 12, 7: 12, 8: 12, 9: 12}
        size = block.get("size", default_sizes.get(level, 14))
        font = block.get("font", "黑体")
        bold = block.get("bold", True)
        color = self._color_tuple(block.get("color"))
        self._safe_set_font(h, font, size, bold=bold, color=color)

    def _block_paragraph(self, doc, block: dict):
        p = doc.add_paragraph()
        align = self._align_value(block.get("align"))
        if align is not None:
            p.alignment = align
        self._set_para_format(
            p,
            indent=block.get("indent", 0.74),
            spacing=block.get("line_spacing", 1.5),
            space_before=block.get("space_before", 0),
            space_after=block.get("space_after", 0),
        )

        default_font = block.get("font", "仿宋")
        default_size = block.get("size", 14)
        default_bold = block.get("bold", False)
        default_italic = block.get("italic", False)
        default_color = self._color_tuple(block.get("color"))

        runs = block.get("runs")
        if runs and isinstance(runs, list):
            for r in runs:
                if not isinstance(r, dict):
                    continue
                run = p.add_run(r.get("text", ""))
                self._set_font(
                    run,
                    r.get("font", default_font),
                    r.get("size", default_size),
                    bold=r.get("bold", default_bold),
                    color=self._color_tuple(r.get("color")) or default_color,
                )
                if r.get("italic", default_italic):
                    run.font.italic = True
        else:
            run = p.add_run(block.get("text", ""))
            self._set_font(run, default_font, default_size, bold=default_bold, color=default_color)
            if default_italic:
                run.font.italic = True

    def _block_table(self, doc, block: dict):
        from docx.shared import Pt, Cm
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        rows = block.get("rows") or []
        if not rows or not isinstance(rows, list):
            return
        cols = len(rows[0]) if rows[0] else 0
        if cols == 0:
            return

        table = doc.add_table(rows=len(rows), cols=cols, style='Table Grid')
        font = block.get("font", "微软雅黑")
        size = block.get("size", 10)
        header = block.get("header", True)
        header_color = self._color_tuple(block.get("header_color")) or (214, 228, 240)
        header_hex = "%02X%02X%02X" % header_color
        col_widths = block.get("col_widths")

        for ri, row_cells in enumerate(rows):
            for ci, cell_text in enumerate(row_cells):
                if ci >= len(table.rows[ri].cells):
                    break
                cell = table.rows[ri].cells[ci]
                cell.text = ''
                p = cell.paragraphs[0]
                run = p.add_run(str(cell_text))
                run.font.name = font
                run._element.rPr.rFonts.set(qn('w:eastAsia'), font)
                is_header_row = header and ri == 0
                run.font.size = Pt(size + 0.5 if is_header_row else size)
                if is_header_row:
                    run.font.bold = True
                    shading = OxmlElement('w:shd')
                    shading.set(qn('w:fill'), header_hex)
                    shading.set(qn('w:val'), 'clear')
                    cell._element.get_or_add_tcPr().append(shading)
                if col_widths and ci < len(col_widths):
                    try:
                        cell.width = Cm(float(col_widths[ci]))
                    except (TypeError, ValueError):
                        pass
        doc.add_paragraph()  # 表后空行

    # ─── 文档类型生成 ───

    def _create_general(self, path, title, content, **kwargs):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        self._setup_document(doc)
        if title:
            h = doc.add_heading(title, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(h, '黑体', 22, bold=True)
        self._add_body(doc, content)
        doc.save(path)

    def _create_contract(self, path, title, content, **kwargs):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        self._setup_document(doc)
        if kwargs.get('number'):
            p = doc.add_paragraph(f"合同编号：{kwargs['number']}")
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            self._safe_set_font(p, '仿宋', 10.5)
        if title:
            h = doc.add_heading(title, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(h, '黑体', 22, bold=True)
        party_a = kwargs.get('party_a', '')
        party_b = kwargs.get('party_b', '')
        if party_a or party_b:
            p = doc.add_paragraph(f"甲方：{party_a}\n乙方：{party_b}")
            self._set_para_format(p)
            self._safe_set_font(p, '仿宋', 14)
        for idx, clause in enumerate(kwargs.get('clauses', []), 1):
            ct = doc.add_heading(f"第{idx}条 {clause.get('title', '')}", level=1)
            self._safe_set_font(ct, '黑体', 15, bold=True)
            for ctext in clause.get('contents', []):
                p = doc.add_paragraph(ctext)
                self._set_para_format(p)
                self._safe_set_font(p, '仿宋', 14)
        doc.add_paragraph()
        sig = doc.add_paragraph("甲方（盖章）：___________    乙方（盖章）：___________")
        self._safe_set_font(sig, '仿宋', 14)
        if kwargs.get('signature_date'):
            dp = doc.add_paragraph(f"签署日期：{kwargs['signature_date']}")
            self._safe_set_font(dp, '仿宋', 14)
        doc.save(path)

    def _create_report(self, path, title, content, **kwargs):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        self._setup_document(doc)
        if title:
            h = doc.add_heading(title, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(h, '黑体', 22, bold=True)
        if kwargs.get('subtitle'):
            st = doc.add_heading(kwargs['subtitle'], level=1)
            self._safe_set_font(st, '黑体', 16, bold=True)
        author = kwargs.get('author', '')
        date = kwargs.get('date', '')
        if author or date:
            info = doc.add_paragraph(f"作者：{author}    日期：{date}")
            info.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(info, '仿宋', 12)
        sections = kwargs.get('sections', [])
        if sections:
            doc.add_paragraph("_" * 50)
            for section in sections:
                h1 = doc.add_heading(section.get('title', ''), level=1)
                self._safe_set_font(h1, '黑体', 16, bold=True)
                for sub in section.get('subsections', []):
                    if sub.get('title'):
                        h2 = doc.add_heading(sub['title'], level=2)
                        self._safe_set_font(h2, '黑体', 15, bold=True)
                    for para in sub.get('paragraphs', []):
                        p = doc.add_paragraph(para)
                        self._set_para_format(p)
                        self._safe_set_font(p, '仿宋', 14)
        elif content:
            # 没有结构化 sections 时，回退到正文内容
            self._add_body(doc, content)
        doc.save(path)

    def _create_documentation(self, path, title, content, **kwargs):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        self._setup_document(doc)
        if title:
            h = doc.add_heading(title, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(h, '黑体', 22, bold=True)
        if kwargs.get('version'):
            vp = doc.add_paragraph(f"版本：{kwargs['version']}")
            vp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            self._safe_set_font(vp, '仿宋', 10.5)
        self._add_body(doc, content)
        doc.save(path)

    def _create_official(self, path, title, content, **kwargs):
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = Document()
        self._setup_document(doc)
        if kwargs.get('issuer'):
            ip = doc.add_paragraph(kwargs['issuer'])
            ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(ip, '小标宋体', 22, color=(255, 0, 0))
        if kwargs.get('doc_number'):
            np = doc.add_paragraph(kwargs['doc_number'])
            np.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(np, '仿宋', 16)
        if title:
            h = doc.add_heading(title, level=0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._safe_set_font(h, '方正小标宋体', 22, bold=True)
        if kwargs.get('recipient'):
            rp = doc.add_paragraph(kwargs['recipient'])
            self._set_para_format(rp, indent=0)
            self._safe_set_font(rp, '仿宋', 16)
        self._add_body_16(doc, content)
        if kwargs.get('issuer_name'):
            doc.add_paragraph()
            inp = doc.add_paragraph(kwargs['issuer_name'])
            inp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            self._safe_set_font(inp, '仿宋', 16)
        if kwargs.get('issue_date'):
            idp = doc.add_paragraph(kwargs['issue_date'])
            idp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            self._safe_set_font(idp, '仿宋', 16)
        doc.save(path)

    def _add_body_16(self, doc, content):
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        if not content:
            return
        paragraphs = content.split('\n') if isinstance(content, str) else content
        for text in paragraphs:
            if text.strip():
                p = doc.add_paragraph(text)
                self._set_para_format(p, indent=0.74)
                self._safe_set_font(p, '仿宋', 16)

    # ─── outline 模式（直接 LLM 展开大纲后写入，不走子 Agent）───

    def _execute_via_outline(self, output_path: str, doc_type: str,
                              title: str, outline: str, **kwargs) -> ToolResult:
        """通过 LLM 将大纲展开为完整内容后直接写入文档。

        主 LLM 只传 outline（写作大纲/指令），本方法用 LLM API 一次调用
        展开为完整正文，然后直接用 content 模式写入文件，不走子 Agent。
        """
        if not self.llm_config.get("api_key"):
            return ToolResult.fail("LLM 配置缺失，无法展开大纲。")

        full_path = os.path.abspath(
            output_path if os.path.isabs(output_path)
            else os.path.join(self.cwd, output_path)
        )
        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("output_path 必须以 .docx 结尾")

        output_dir = os.path.dirname(full_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # 构建 LLM 调用参数
        config = self.llm_config
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", "kimi-for-coding")
        protocol = config.get("protocol", "anthropic")

        extra_params = {k: v for k, v in kwargs.items() if v not in (None, "", [])}
        extra_hint = ""
        if extra_params:
            extra_hint = (
                f"附加参数（如果适用请用到文档中）:\n"
                + "\n".join(f"- {k}: {json.dumps(v, ensure_ascii=False)[:500]}" for k, v in extra_params.items())
                + "\n\n"
            )

        system_prompt = (
            f"你是专业的文档撰写助手。请根据大纲生成完整的文档正文内容。\n"
            f"文档类型: {doc_type}\n"
            f"标题: {title or '未命名文档'}\n"
            f"输出路径: {full_path}\n\n"
            f"要求：\n"
            f"1. 将大纲展开为完整、专业的内容（所有正文段落、章节、表格、关键数据）\n"
            f"2. 直接输出文档正文，不要回答任何其他内容\n"
            f"3. 不要使用问候语或前缀\n"
        )
        user_prompt = (
            f"{extra_hint}"
            f"--- 大纲/写作指令 ---\n"
            f"{outline}\n"
            f"--- 结束 ---\n\n"
            f"请输出完整的文档正文内容。"
        )

        try:
            import httpx

            # 超时可由调用方传入（秒），默认 120；流式下作用于数据块间隔
            timeout = float(kwargs.get("timeout", 120))

            if protocol == "anthropic":
                content_text = self._call_llm_anthropic(
                    base_url, api_key, model, system_prompt, user_prompt, timeout,
                )
            else:
                content_text = self._call_llm_openai(
                    base_url, api_key, model, system_prompt, user_prompt, timeout,
                )

            if not content_text or not content_text.strip():
                return ToolResult.fail("LLM 返回空内容，大纲展开失败。")

            # 直接使用 content 模式写入
            handlers = {
                "general": self._create_general,
                "contract": self._create_contract,
                "report": self._create_report,
                "documentation": self._create_documentation,
                "official": self._create_official,
            }
            handler = handlers.get(doc_type, self._create_general)
            handler(full_path, title, content_text, **kwargs)
            return ToolResult.ok(
                f"文档已创建: {full_path}",
                path=full_path,
                doc_type=doc_type,
                content_length=len(content_text),
            )
        except ImportError:
            return ToolResult.fail("缺少 httpx 库，请运行: pip install httpx")
        except httpx.ReadTimeout:
            return ToolResult.fail(
                f"大纲展开超时：LLM 在 {timeout:.0f} 秒内未返回数据。"
                "文档过长或模型响应较慢时易触发。建议：拆分大纲分多次生成，或传入更大的 timeout 参数。"
            )
        except Exception as e:
            return ToolResult.fail(f"大纲展开或文档创建失败: {e}")

    def _call_llm_anthropic(self, base_url: str, api_key: str, model: str,
                              system_prompt: str, user_prompt: str,
                              timeout: float = 120.0) -> str:
        """调用 Anthropic 协议 LLM，SSE 流式读取并拼接文本。

        采用流式（stream=True）：把"等待整个响应"变成"等待下一个数据块"，
        避免长文档一次性生成时超过固定 read 超时。
        """
        import httpx

        url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
        body = {
            "model": model,
            "max_tokens": 16384,
            "stream": True,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        parts: list[str] = []
        with httpx.Client(timeout=self._make_timeout(timeout)) as client:
            with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:300]}")
                for data_str in self._iter_sse_data(resp):
                    if data_str == "[DONE]":
                        break
                    try:
                        event = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    etype = event.get("type")
                    if etype == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            parts.append(delta.get("text", ""))
                    elif etype == "error":
                        err = event.get("error", {})
                        raise RuntimeError(f"LLM API stream error: {err.get('message', data_str)[:300]}")
        return "".join(parts)

    def _call_llm_openai(self, base_url: str, api_key: str, model: str,
                           system_prompt: str, user_prompt: str,
                           timeout: float = 120.0) -> str:
        """调用 OpenAI 协议 LLM，SSE 流式读取并拼接文本。"""
        import httpx

        url = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
        body = {
            "model": model,
            "max_tokens": 16384,
            "stream": True,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        parts: list[str] = []
        with httpx.Client(timeout=self._make_timeout(timeout)) as client:
            with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:300]}")
                for data_str in self._iter_sse_data(resp):
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        text = delta.get("content")
                        if text:
                            parts.append(text)
        return "".join(parts)

    # ─── 流式辅助 ───

    @staticmethod
    def _make_timeout(timeout: float):
        """构造 httpx 超时配置。

        流式下 read 超时作用于"相邻两个数据块之间的间隔"，
        而非整个响应总时长，因此长文档生成不会因总耗时超限。
        connect/write 保持较短，read 用传入值，pool 不限制。
        """
        import httpx
        return httpx.Timeout(connect=30.0, read=timeout, write=30.0, pool=None)

    @staticmethod
    def _iter_sse_data(resp):
        """逐条解析 SSE 响应中的 data: 行，yield 其内容。"""
        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                yield line[len("data:"):].strip()
