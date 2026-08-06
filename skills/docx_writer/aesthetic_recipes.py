"""
minimax-docx 13 套审美配方 → sigma write_docx blocks 模式参数配置表

每套配方包含：
  - page: 页面设置（尺寸、边距、分栏）
  - defaults: 文档默认字体/字号/颜色
  - body: 正文段落预设
  - headings: H1-H5 各级标题预设
  - caption: 图表标题预设
  - header_footer: 页眉页脚预设
  - table_style: 表格风格预设

使用方式：
  from skills.docx_writer.aesthetic_recipes import RECIPES
  recipe = RECIPES["modern_corporate"]
  # 在 blocks 模式下，按 recipe["headings"]["h1"] 等填入 heading/paragraph 块参数
"""

from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助：十六进制颜色 → [R, G, B]
# ═══════════════════════════════════════════════════════════════════════════════

def hex_to_rgb(hex_str: str) -> list[int]:
    """将 '#1F3864' 或 '1F3864' 转为 [31, 56, 100]"""
    h = hex_str.lstrip("#")
    return [int(h[i:i+2], 16) for i in (0, 2, 4)]


# ═══════════════════════════════════════════════════════════════════════════════
# 配方数据结构
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class StylePreset:
    """单一样式预设"""
    font: str = "仿宋"
    east_asian_font: str = "仿宋"
    size: float = 14          # pt
    bold: bool = False
    italic: bool = False
    color: list[int] = field(default_factory=lambda: [0, 0, 0])
    align: str = "left"       # left|center|right|justify
    indent: float = 0.74      # 首行缩进 cm
    space_before: float = 0   # pt
    space_after: float = 0    # pt
    line_spacing: float = 1.5 # 倍数


@dataclass
class PageSetup:
    """页面设置"""
    width: float = 21.0       # cm (A4)
    height: float = 29.7      # cm (A4)
    top: float = 2.54         # cm
    bottom: float = 2.54      # cm
    left: float = 3.17        # cm
    right: float = 3.17       # cm
    columns: int = 1          # 分栏数
    gutter: float = 0         # 栏间距 cm


@dataclass
class TableStyle:
    """表格风格"""
    header_font: str = "微软雅黑"
    header_size: float = 10.5
    header_color: list[int] = field(default_factory=lambda: hex_to_rgb("D6E4F0"))
    header_text_color: list[int] = field(default_factory=lambda: [0, 0, 0])
    body_font: str = "微软雅黑"
    body_size: float = 10
    body_color: list[int] = field(default_factory=lambda: [0, 0, 0])
    border_style: str = "Table Grid"  # Table Grid | 三线表 | 无边框 | 仅水平线


@dataclass
class AestheticRecipe:
    """一套完整的审美配方"""
    name: str
    description: str = ""
    source: str = ""           # 配方来源（IEEE / APA / GB/T 9704 等）
    page: PageSetup = field(default_factory=PageSetup)
    defaults: StylePreset = field(default_factory=StylePreset)
    body: StylePreset = field(default_factory=lambda: StylePreset(font="仿宋", size=14, indent=0.74, line_spacing=1.5))
    headings: dict[str, StylePreset] = field(default_factory=dict)
    caption: StylePreset = field(default_factory=lambda: StylePreset(font="仿宋", size=10.5, italic=True))
    header_footer: Optional[dict] = None
    table_style: TableStyle = field(default_factory=TableStyle)

    def to_blocks_heading(self, level: int, text: str, **overrides) -> dict:
        """生成 blocks 模式 heading 块参数"""
        key = f"h{level}"
        preset = self.headings.get(key, StylePreset())
        return {
            "type": "heading",
            "text": text,
            "level": level,
            "font": overrides.get("font", preset.font),
            "size": overrides.get("size", preset.size),
            "bold": overrides.get("bold", preset.bold),
            "color": overrides.get("color", preset.color),
            "align": overrides.get("align", preset.align),
        }

    def to_blocks_paragraph(self, text: str = "", runs: list = None, **overrides) -> dict:
        """生成 blocks 模式 paragraph 块参数"""
        preset = self.body
        block = {
            "type": "paragraph",
            "font": overrides.get("font", preset.font),
            "size": overrides.get("size", preset.size),
            "bold": overrides.get("bold", preset.bold),
            "italic": overrides.get("italic", preset.italic),
            "color": overrides.get("color", preset.color),
            "align": overrides.get("align", preset.align),
            "indent": overrides.get("indent", preset.indent),
            "space_before": overrides.get("space_before", preset.space_before),
            "space_after": overrides.get("space_after", preset.space_after),
            "line_spacing": overrides.get("line_spacing", preset.line_spacing),
        }
        if runs:
            block["runs"] = runs
        elif text:
            block["text"] = text
        return block

    def to_blocks_table(self, rows: list[list[str]], **overrides) -> dict:
        """生成 blocks 模式 table 块参数"""
        ts = self.table_style
        return {
            "type": "table",
            "rows": rows,
            "header": overrides.get("header", True),
            "font": overrides.get("font", ts.body_font),
            "size": overrides.get("size", ts.body_size),
            "header_color": overrides.get("header_color", ts.header_color),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 13 套审美配方定义
# ═══════════════════════════════════════════════════════════════════════════════

RECIPES: dict[str, AestheticRecipe] = {}


# ── Recipe 1: MODERN CORPORATE ────────────────────────────────────────────────

RECIPES["modern_corporate"] = AestheticRecipe(
    name="现代商务",
    description="适合企业报告、商业计划书、白皮书。使用 Aptos 字体，深蓝标题，留白充裕。",
    source="Modern Corporate (Aptos Display + 1.15x 行距)",
    page=PageSetup(
        width=21.59, height=27.94,  # US Letter
        top=2.54, bottom=2.54, left=2.54, right=2.54,
    ),
    defaults=StylePreset(font="Arial", east_asian_font="宋体", size=11),
    body=StylePreset(
        font="Arial", east_asian_font="宋体", size=11,
        color=hex_to_rgb("333333"),
        line_spacing=1.15, space_after=8, indent=0,
    ),
    headings={
        "h1": StylePreset(font="Arial", size=20, bold=False, color=hex_to_rgb("1F3864"),
                          space_before=24, space_after=6, align="left"),
        "h2": StylePreset(font="Arial", size=16, bold=False, color=hex_to_rgb("1F3864"),
                          space_before=18, space_after=4, align="left"),
        "h3": StylePreset(font="Arial", size=13, bold=True, color=hex_to_rgb("1F3864"),
                          space_before=12, space_after=4, align="left"),
    },
    caption=StylePreset(font="Arial", size=9, italic=True, color=hex_to_rgb("595959"), indent=0),
    table_style=TableStyle(
        header_font="Arial", header_size=10.5, header_color=hex_to_rgb("F2F2F2"),
        body_font="Arial", body_size=10, border_style="仅水平线",
    ),
)

# ── Recipe 2: ACADEMIC THESIS ─────────────────────────────────────────────────

RECIPES["academic_thesis"] = AestheticRecipe(
    name="学术论文",
    description="APA 风格学术论文。Times New Roman 12pt，双倍行距，首行缩进，三线表。",
    source="Academic Thesis (APA-style)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=2.54, bottom=2.54, left=3.81, right=2.54,  # 左 1.5in 装订
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=12),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=12,
        color=[0, 0, 0],
        line_spacing=2.0, space_after=0, indent=1.27,  # 0.5in 首行缩进
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="center", space_before=24, space_after=0),
        "h2": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", space_before=24, space_after=0),
        "h3": StylePreset(font="Times New Roman", size=12, bold=True, italic=True,
                          align="left", space_before=24, space_after=0),
    },
    caption=StylePreset(font="Times New Roman", size=12, italic=True, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=12, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=12, border_style="三线表",
    ),
)

# ── Recipe 3: EXECUTIVE BRIEF ─────────────────────────────────────────────────

RECIPES["executive_brief"] = AestheticRecipe(
    name="高管简报",
    description="适合高管摘要、战略简报。Georgia 字体，深蓝灰色彩，优雅大气。",
    source="Executive Brief (Georgia + Helvetica Neue)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=3.175, bottom=3.175, left=3.175, right=3.175,  # 1.25in
    ),
    defaults=StylePreset(font="Georgia", east_asian_font="宋体", size=11,
                         color=hex_to_rgb("2C3E50")),
    body=StylePreset(
        font="Georgia", east_asian_font="宋体", size=11,
        color=hex_to_rgb("2C3E50"),
        line_spacing=1.4, space_after=10, indent=0,
    ),
    headings={
        "h1": StylePreset(font="Georgia", size=22, bold=False, color=hex_to_rgb("2C3E50"),
                          space_before=30, space_after=12, align="left"),
        "h2": StylePreset(font="Georgia", size=16, bold=False, color=hex_to_rgb("2C3E50"),
                          space_before=24, space_after=8, align="left"),
        "h3": StylePreset(font="Georgia", size=12, bold=True, color=hex_to_rgb("2C3E50"),
                          space_before=16, space_after=6, align="left"),
    },
    caption=StylePreset(font="Georgia", size=9, italic=True, color=hex_to_rgb("7F8C8D"), indent=0),
    table_style=TableStyle(
        header_font="Georgia", header_size=10.5,
        header_color=hex_to_rgb("2C3E50"), header_text_color=[255, 255, 255],
        body_font="Georgia", body_size=10, border_style="仅水平线",
    ),
)

# ── Recipe 4: CHINESE GOVERNMENT ──────────────────────────────────────────────

RECIPES["chinese_government"] = AestheticRecipe(
    name="中国公文",
    description="GB/T 9704-2012 党政机关公文格式标准。仿宋三号字，28磅固定行距，2字符缩进。",
    source="Chinese Government Document (GB/T 9704-2012)",
    page=PageSetup(
        width=21.0, height=29.7,  # A4
        top=3.7, bottom=3.5, left=2.8, right=2.6,  # 上37/下35/左28/右26mm
    ),
    defaults=StylePreset(font="仿宋", east_asian_font="仿宋", size=16, color=[0, 0, 0]),
    body=StylePreset(
        font="仿宋", east_asian_font="仿宋", size=16,
        color=[0, 0, 0],
        line_spacing=1.33,  # 固定28磅 ≈ 1.33x (相对于16pt字号: 28/21.33≈1.31)
        space_after=0, indent=0.74 * 2,  # 2字符缩进 (约1.48cm，但 sigma 以 cm 计需调整)
    ),
    headings={
        "h1": StylePreset(font="方正小标宋体", east_asian_font="方正小标宋体",
                          size=22, bold=True, align="center",
                          space_before=8, space_after=8),
        "h2": StylePreset(font="黑体", east_asian_font="黑体", size=16, bold=True,
                          align="left", space_before=8, space_after=4),
        "h3": StylePreset(font="楷体", east_asian_font="楷体", size=16, bold=False,
                          align="left", space_before=8, space_after=4),
    },
    caption=StylePreset(font="仿宋", east_asian_font="仿宋", size=16, italic=False, indent=0),
    table_style=TableStyle(
        header_font="黑体", header_size=16, header_color=[255, 255, 255],
        body_font="仿宋", body_size=16, border_style="三线表",
    ),
)

# ── Recipe 5: MINIMAL MODERN ──────────────────────────────────────────────────

RECIPES["minimal_modern"] = AestheticRecipe(
    name="极简现代",
    description="适合产品文档、设计说明。Inter 字体，大留白，窄文本列，清爽干净。",
    source="Minimal Modern (Inter + 1.5x 行距)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=2.54, bottom=2.54, left=3.81, right=3.81,  # 左右 1.5in 窄列
    ),
    defaults=StylePreset(font="Inter", east_asian_font="微软雅黑", size=10.5,
                         color=hex_to_rgb("444444")),
    body=StylePreset(
        font="Inter", east_asian_font="微软雅黑", size=10.5,
        color=hex_to_rgb("444444"),
        line_spacing=1.5, space_after=12, indent=0,
    ),
    headings={
        "h1": StylePreset(font="Inter", size=24, bold=False, color=hex_to_rgb("111111"),
                          space_before=36, space_after=16, align="left"),
        "h2": StylePreset(font="Inter", size=16, bold=False, color=hex_to_rgb("111111"),
                          space_before=28, space_after=10, align="left"),
        "h3": StylePreset(font="Inter", size=12, bold=True, color=hex_to_rgb("111111"),
                          space_before=20, space_after=6, align="left"),
    },
    caption=StylePreset(font="Inter", east_asian_font="微软雅黑", size=9,
                         italic=False, color=hex_to_rgb("999999"), indent=0),
    table_style=TableStyle(
        header_font="Inter", header_size=10, header_color=[255, 255, 255],
        body_font="Inter", body_size=9.5, border_style="无边框",
    ),
)

# ── Recipe 6: IEEE CONFERENCE ─────────────────────────────────────────────────

RECIPES["ieee_conference"] = AestheticRecipe(
    name="IEEE 会议论文",
    description="IEEEtran 会议格式。Times New Roman 10pt，双栏，罗马数字标题编号。",
    source="IEEE Conference (IEEEtran)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=1.905, bottom=2.54, left=1.588, right=1.588,  # 上0.75/下1/左右0.625in
        columns=2, gutter=0.635,  # 双栏 0.25in 间距
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=10),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=10,
        color=[0, 0, 0],
        line_spacing=1.0, space_after=0, indent=0.318,  # 0.125in ≈ 0.318cm
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=10, bold=True,
                          align="center", space_before=12, space_after=6),
        "h2": StylePreset(font="Times New Roman", size=10, bold=False, italic=True,
                          align="left", space_before=9, space_after=3),
    },
    caption=StylePreset(font="Times New Roman", size=8, italic=False, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=10, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=10, border_style="Table Grid",
    ),
)

# ── Recipe 7: ACM CONFERENCE ──────────────────────────────────────────────────

RECIPES["acm_conference"] = AestheticRecipe(
    name="ACM 会议论文",
    description="ACM acmart 会议格式。Times New Roman 9pt，双栏，阿拉伯数字编号。",
    source="ACM Conference (acmart)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=3.175, bottom=3.175, left=1.905, right=1.905,  # 上下1.25/左右0.75in
        columns=2, gutter=0.838,  # 双栏 0.33in
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=9),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=9,
        color=[0, 0, 0],
        line_spacing=1.0, space_after=0, indent=0.508,  # ~10pt ≈ 0.508cm
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=10, bold=True,
                          align="left", space_before=12, space_after=6),
        "h2": StylePreset(font="Times New Roman", size=10, bold=True,
                          align="left", space_before=10, space_after=4),
        "h3": StylePreset(font="Times New Roman", size=10, bold=True, italic=True,
                          align="left", space_before=8, space_after=3),
    },
    caption=StylePreset(font="Times New Roman", size=8, italic=False, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=9, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=9, border_style="Table Grid",
    ),
)

# ── Recipe 8: APA 7TH EDITION ─────────────────────────────────────────────────

RECIPES["apa_7th"] = AestheticRecipe(
    name="APA 第7版",
    description="APA 7th 专业论文格式。Times New Roman 12pt，双倍行距，五级标题体系。",
    source="APA 7th Edition (Professional Paper)",
    page=PageSetup(
        width=21.59, height=27.94,
        top=2.54, bottom=2.54, left=2.54, right=2.54,
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=12),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=12,
        color=[0, 0, 0],
        line_spacing=2.0, space_after=0, indent=1.27,
    ),
    headings={
        # Level 1: 居中加粗
        "h1": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="center", space_before=24, space_after=0),
        # Level 2: 左对齐加粗
        "h2": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", space_before=24, space_after=0),
        # Level 3: 左对齐加粗斜体
        "h3": StylePreset(font="Times New Roman", size=12, bold=True, italic=True,
                          align="left", space_before=24, space_after=0),
        # Level 4: 缩进加粗，句号后接正文
        "h4": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", indent=1.27, space_before=24, space_after=0),
        # Level 5: 缩进加粗斜体，句号后接正文
        "h5": StylePreset(font="Times New Roman", size=12, bold=True, italic=True,
                          align="left", indent=1.27, space_before=24, space_after=0),
    },
    caption=StylePreset(font="Times New Roman", size=12, italic=True, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=12, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=12, border_style="三线表",
    ),
)

# ── Recipe 9: MLA 9TH EDITION ─────────────────────────────────────────────────

RECIPES["mla_9th"] = AestheticRecipe(
    name="MLA 第9版",
    description="MLA 9th 论文格式。Times New Roman 12pt，双倍行距，悬挂缩进引用。",
    source="MLA 9th Edition",
    page=PageSetup(
        width=21.59, height=27.94,
        top=2.54, bottom=2.54, left=2.54, right=2.54,
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=12),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=12,
        color=[0, 0, 0],
        line_spacing=2.0, space_after=0, indent=1.27,
    ),
    headings={
        # MLA 无标题层级，仅通过居中区分
        "h1": StylePreset(font="Times New Roman", size=12, bold=False,
                          align="center", space_before=24, space_after=0),
    },
    caption=StylePreset(font="Times New Roman", size=12, italic=False, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=12, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=12, border_style="Table Grid",
    ),
)

# ── Recipe 10: CHICAGO / TURABIAN ─────────────────────────────────────────────

RECIPES["chicago_turabian"] = AestheticRecipe(
    name="芝加哥/图拉宾格式",
    description="Chicago/Turabian 论文格式。Times New Roman 12pt，双倍行距，脚注10pt单倍。",
    source="Chicago / Turabian",
    page=PageSetup(
        width=21.59, height=27.94,
        top=2.54, bottom=2.54, left=3.81, right=2.54,  # 左 1.5in
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=12),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=12,
        color=[0, 0, 0],
        line_spacing=2.0, space_after=0, indent=1.27,
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="center", space_before=24, space_after=0),
        # Turabian 特点：H2 不加粗
        "h2": StylePreset(font="Times New Roman", size=12, bold=False,
                          align="center", space_before=24, space_after=0),
        "h3": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", space_before=24, space_after=0),
        "h4": StylePreset(font="Times New Roman", size=12, bold=False,
                          align="left", space_before=24, space_after=0),
        "h5": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", indent=1.27, space_before=24, space_after=0),
    },
    caption=StylePreset(font="Times New Roman", size=12, italic=False, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=12, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=12, border_style="Table Grid",
    ),
)

# ── Recipe 11: SPRINGER LNCS ──────────────────────────────────────────────────

RECIPES["springer_lncs"] = AestheticRecipe(
    name="Springer LNCS",
    description="Springer 计算机科学讲义格式。Times New Roman 10pt，三级标题+run-in格式。",
    source="Springer LNCS",
    page=PageSetup(
        width=21.59, height=27.94,
        top=4.7, bottom=5.5, left=4.4, right=4.4,  # 文本区域限制
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=10),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=10,
        color=[0, 0, 0],
        line_spacing=1.0, space_after=0, indent=0.5,  # ~0.5cm
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=12, bold=True,
                          align="left", space_before=12, space_after=6),
        "h2": StylePreset(font="Times New Roman", size=10, bold=True,
                          align="left", space_before=10, space_after=5),
        # H3: run-in 加粗斜体
        "h3": StylePreset(font="Times New Roman", size=10, bold=True, italic=True,
                          align="left", space_before=10, space_after=5),
        # H4: run-in 斜体
        "h4": StylePreset(font="Times New Roman", size=10, bold=False, italic=True,
                          align="left", space_before=10, space_after=5),
    },
    caption=StylePreset(font="Times New Roman", size=9, italic=False, indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=10, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=10, border_style="Table Grid",
    ),
)

# ── Recipe 12: NATURE JOURNAL ─────────────────────────────────────────────────

RECIPES["nature_journal"] = AestheticRecipe(
    name="Nature 期刊",
    description="Nature 期刊格式。Times New Roman 9pt，双栏，上标引用，三线表。",
    source="Nature Journal",
    page=PageSetup(
        width=21.0, height=29.7,  # A4
        top=1.905, bottom=1.905, left=1.905, right=1.905,  # 0.75in
        columns=2, gutter=0.5,  # 双栏 5mm
    ),
    defaults=StylePreset(font="Times New Roman", east_asian_font="宋体", size=9),
    body=StylePreset(
        font="Times New Roman", east_asian_font="宋体", size=9,
        color=[0, 0, 0],
        line_spacing=1.0, space_after=0, indent=0,
    ),
    headings={
        "h1": StylePreset(font="Times New Roman", size=14, bold=True,
                          align="left", space_before=10, space_after=4),
        "h2": StylePreset(font="Times New Roman", size=9, bold=True,
                          align="left", space_before=10, space_after=4),
    },
    caption=StylePreset(font="Times New Roman", size=8, italic=False,
                         color=hex_to_rgb("000000"), indent=0),
    table_style=TableStyle(
        header_font="Times New Roman", header_size=9, header_color=[255, 255, 255],
        body_font="Times New Roman", body_size=9, border_style="三线表",
    ),
)

# ── Recipe 13: HARVARD BUSINESS REVIEW ────────────────────────────────────────

RECIPES["hbr"] = AestheticRecipe(
    name="哈佛商业评论",
    description="HBR 风格。Georgia 字体，暖深灰色调，Pull Quote 引用块，Exhibit 表格。",
    source="Harvard Business Review",
    page=PageSetup(
        width=21.59, height=27.94,
        top=3.175, bottom=3.175, left=3.175, right=3.175,  # 1.25in
    ),
    defaults=StylePreset(font="Georgia", east_asian_font="宋体", size=11,
                         color=hex_to_rgb("333333")),
    body=StylePreset(
        font="Georgia", east_asian_font="宋体", size=11,
        color=hex_to_rgb("333333"),
        line_spacing=1.3, space_after=10, indent=0,
    ),
    headings={
        "h1": StylePreset(font="Georgia", size=18, bold=True, color=hex_to_rgb("1A1A1A"),
                          space_before=24, space_after=6, align="left"),
        "h2": StylePreset(font="Georgia", size=14, bold=True, color=hex_to_rgb("1A1A1A"),
                          space_before=18, space_after=4, align="left"),
    },
    caption=StylePreset(font="Georgia", size=9, italic=False, color=hex_to_rgb("666666"), indent=0),
    table_style=TableStyle(
        header_font="Georgia", header_size=10, header_color=hex_to_rgb("F5F5F0"),
        body_font="Georgia", body_size=10, border_style="仅水平线",
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# 快捷查阅：配方速查表
# ═══════════════════════════════════════════════════════════════════════════════

RECIPE_QUICK_REFERENCE = """
┌─────────────────────────┬──────────────────────┬────────┬────────┬───────────┬────────────┐
│ 配方                    │ 应用场景             │ 字体   │ 字号   │ 行距      │ 页边距     │
├─────────────────────────┼──────────────────────┼────────┼────────┼───────────┼────────────┤
│ modern_corporate        │ 企业报告/白皮书      │ Aptos  │ 11pt   │ 1.15x     │ 1in        │
│ academic_thesis         │ 学术论文(APA)        │ TNR    │ 12pt   │ 2.0x      │ 1in/1.5in  │
│ executive_brief         │ 高管摘要/战略简报    │Georgia │ 11pt   │ 1.4x      │ 1.25in     │
│ chinese_government      │ 公文(GB/T 9704)      │ 仿宋   │ 16pt   │ 28磅固定  │ 37/35/28/26│
│ minimal_modern          │ 产品文档/设计说明    │ Inter  │ 10.5pt │ 1.5x      │ 1in/1.5in  │
│ ieee_conference         │ IEEE 会议论文        │ TNR    │ 10pt   │ 1.0x 双栏 │ 0.75/1/0.6 │
│ acm_conference          │ ACM 会议论文         │ TNR    │ 9pt    │ 1.0x 双栏 │1.25/0.75in │
│ apa_7th                 │ APA 7th 专业论文     │ TNR    │ 12pt   │ 2.0x      │ 1in        │
│ mla_9th                 │ MLA 9th 人文论文     │ TNR    │ 12pt   │ 2.0x      │ 1in        │
│ chicago_turabian        │ Chicago/Turabian     │ TNR    │ 12pt   │ 2.0x      │ 1in/1.5in  │
│ springer_lncs           │ Springer LNCS        │ TNR    │ 10pt   │ 1.0x      │ 4.7/5.5/4.4│
│ nature_journal          │ Nature 期刊          │ TNR    │ 9pt    │ 1.0x 双栏 │ 0.75in     │
│ hbr                     │ HBR 风格             │Georgia │ 11pt   │ 1.3x      │ 1.25in     │
└─────────────────────────┴──────────────────────┴────────┴────────┴───────────┴────────────┘
""".strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 使用示例
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 示例：用 modern_corporate 配方生成 blocks
    recipe = RECIPES["modern_corporate"]
    blocks = [
        recipe.to_blocks_heading(1, "第一章 项目概述"),
        recipe.to_blocks_paragraph("这是正文内容，自动使用 Modern Corporate 配方的 11pt Aptos 字体。"),
        recipe.to_blocks_heading(2, "1.1 背景分析"),
        recipe.to_blocks_paragraph("二级标题下的正文内容..."),
        recipe.to_blocks_table([
            ["指标", "2025", "2026"],
            ["营收", "500万", "650万"],
            ["利润", "80万", "120万"],
        ]),
    ]
    print(f"配方: {recipe.name}")
    print(f"生成 {len(blocks)} 个 blocks 块")
    print(f"正文字体: {recipe.body.font} {recipe.body.size}pt")
    print(f"\n{'-'*60}")
    print(RECIPE_QUICK_REFERENCE)
