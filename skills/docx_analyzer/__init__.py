"""
docx_analyzer skill - Word 文档内容搜索与分析

提供 search_docx 工具，类似 LSP findReferences，在文档中查找指定内容的所有出现位置。
"""
import os
import re
from skills.base import BaseTool, ToolParameter, ToolResult
from skills.utils.docx_text import get_paragraph_full_text, get_cell_full_text


class SearchDocxTool(BaseTool):
    name = "search_docx"
    description = (
        "在 Word (.docx) 文档中搜索指定内容的所有出现位置。类似 LSP 的 findReferences，"
        "支持精确匹配、数值匹配、百分比关系、语义关联四种搜索模式。"
    )
    parameters = [
        ToolParameter("file_path", "string", "Word 文档路径"),
        ToolParameter("search_value", "string", "要搜索的值"),
        ToolParameter("search_type", "string", "搜索类型: exact|numeric|percentage|semantic", required=False, default="exact"),
        ToolParameter("include_context", "boolean", "是否包含周围上下文", required=False, default=True),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, search_value: str, search_type: str = "exact",
                include_context: bool = True, **kwargs) -> ToolResult:
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.cwd, file_path)

        if not os.path.exists(full_path):
            return ToolResult.fail(f"文件不存在: {full_path}")
        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("仅支持 .docx 格式文件")
        if search_type not in ("exact", "numeric", "percentage", "semantic"):
            return ToolResult.fail(f"search_type 无效: {search_type}，可选: exact, numeric, percentage, semantic")

        try:
            from docx import Document
        except ImportError:
            return ToolResult.fail("缺少 python-docx 库，请运行: pip install python-docx")

        try:
            doc = Document(full_path)
            occurrences = self._find_all(doc, search_value, search_type, include_context)
            summary = self._summarize(occurrences)

            lines = [f"搜索: \"{search_value}\" (类型: {search_type})"]
            lines.append(f"文件: {full_path}")
            lines.append(f"找到 {summary['total_count']} 处匹配\n")
            for occ in occurrences[:30]:  # 最多显示前30条
                lines.append(f"  [{occ['type']}] {occ['location']}: {occ.get('content', '')[:80]}")
            if len(occurrences) > 30:
                lines.append(f"  ...还有 {len(occurrences) - 30} 处匹配")

            return ToolResult.ok(
                "\n".join(lines),
                total_count=summary["total_count"],
                by_type=summary["by_type"],
                occurrences=occurrences,
            )
        except Exception as e:
            return ToolResult.fail(f"搜索失败: {e}")

    def _find_all(self, doc, value, stype, ctx):
        results = []
        if stype in ("exact", "numeric"):
            results.extend(self._exact(doc, value, ctx))
        if stype == "numeric":
            results.extend(self._numeric(doc, value, ctx))
        if stype == "percentage":
            results.extend(self._percentage(doc, ctx))
        if stype == "semantic":
            results.extend(self._semantic(doc, value, ctx))

        seen = set()
        unique = []
        for r in results:
            loc = r["location"]
            if loc not in seen:
                seen.add(loc)
                unique.append(r)
        return unique

    def _exact(self, doc, value, ctx):
        results = []
        for i, para in enumerate(doc.paragraphs):
            para_text = get_paragraph_full_text(para)
            if value in para_text:
                r = {"location": f"段落 {i+1}", "content": para_text, "type": "paragraph",
                     "confidence": 1.0, "match_type": "exact"}
                if ctx:
                    r["context"] = self._para_ctx(doc, i)
                results.append(r)
        for ti, table in enumerate(doc.tables):
            for ri, row in enumerate(table.rows):
                for ci, cell in enumerate(row.cells):
                    cell_text = get_cell_full_text(cell)
                    if value in cell_text:
                        r = {"location": f"表格{ti+1}, 行{ri+1}, 列{ci+1}", "content": cell_text,
                             "type": "table", "confidence": 1.0, "match_type": "exact"}
                        if ctx:
                            r["context"] = self._table_ctx(table, ri, ci)
                        results.append(r)
        return results

    def _numeric(self, doc, value, ctx):
        try:
            target = float(str(value).replace(',', '').replace('%', '').replace(' ', ''))
        except ValueError:
            return []
        pattern = r'[\d,]+\.?\d*%?'
        results = []
        for i, para in enumerate(doc.paragraphs):
            para_text = get_paragraph_full_text(para)
            for m in re.finditer(pattern, para_text):
                try:
                    found = float(m.group().replace(',', '').replace('%', '').replace(' ', ''))
                    if abs(found - target) < 0.01:
                        r = {"location": f"段落 {i+1}", "content": m.group(), "full_text": para_text,
                             "type": "paragraph", "confidence": 0.95, "match_type": "numeric"}
                        if ctx:
                            r["context"] = self._para_ctx(doc, i)
                        results.append(r)
                except ValueError:
                    continue
        for ti, table in enumerate(doc.tables):
            for ri, row in enumerate(table.rows):
                for ci, cell in enumerate(row.cells):
                    cell_text = get_cell_full_text(cell)
                    for m in re.finditer(pattern, cell_text):
                        try:
                            found = float(m.group().replace(',', '').replace('%', '').replace(' ', ''))
                            if abs(found - target) < 0.01:
                                r = {"location": f"表格{ti+1}, 行{ri+1}, 列{ci+1}", "content": m.group(),
                                     "full_text": cell_text, "type": "table", "confidence": 0.95, "match_type": "numeric"}
                                if ctx:
                                    r["context"] = self._table_ctx(table, ri, ci)
                                results.append(r)
                        except ValueError:
                            continue
        return results

    def _percentage(self, doc, ctx):
        pattern = r'\d+\.?\d*%'
        keywords = ['基准', '参考', 'baseline', 'reference', '标准', '对比']
        results = []
        for i, para in enumerate(doc.paragraphs):
            para_text = get_paragraph_full_text(para)
            if any(kw in para_text.lower() for kw in keywords):
                for m in re.finditer(pattern, para_text):
                    r = {"location": f"段落 {i+1}", "content": m.group(), "full_text": para_text,
                         "type": "paragraph", "confidence": 0.8, "match_type": "percentage"}
                    if ctx:
                        r["context"] = self._para_ctx(doc, i)
                    results.append(r)
        return results

    def _semantic(self, doc, value, ctx):
        semantic_map = {
            '基准': ['参考', '标准', '对比', 'baseline', 'reference'],
            '增长': ['提升', '上升', '增加', 'growth', 'increase'],
            '下降': ['减少', '降低', 'decrease', 'decline'],
            '比例': ['百分比', '占比', 'percentage', 'ratio'],
        }
        keywords = [value]
        for k, related in semantic_map.items():
            if k in value:
                keywords.extend(related)
        results = []
        for i, para in enumerate(doc.paragraphs):
            para_text = get_paragraph_full_text(para)
            for kw in keywords:
                if kw.lower() in para_text.lower():
                    r = {"location": f"段落 {i+1}", "content": para_text, "type": "paragraph",
                         "confidence": 0.7, "match_type": "semantic", "matched_keyword": kw}
                    if ctx:
                        r["context"] = self._para_ctx(doc, i)
                    results.append(r)
                    break
        return results

    def _para_ctx(self, doc, idx, window=2):
        start = max(0, idx - window)
        end = min(len(doc.paragraphs), idx + window + 1)
        lines = []
        for i in range(start, end):
            prefix = ">>> " if i == idx else "    "
            lines.append(f"{prefix}[段落{i+1}] {get_paragraph_full_text(doc.paragraphs[i])[:100]}")
        return '\n'.join(lines)

    def _table_ctx(self, table, row_idx, cell_idx):
        ctx = []
        if len(table.rows) > 0 and cell_idx < len(table.rows[0].cells):
            ctx.append(f"列标题: {get_cell_full_text(table.rows[0].cells[cell_idx])}")
        if len(table.rows[row_idx].cells) > 0:
            ctx.append(f"行标题: {get_cell_full_text(table.rows[row_idx].cells[0])}")

        surrounding = []
        for r in range(max(0, row_idx - 1), min(len(table.rows), row_idx + 2)):
            for c in range(max(0, cell_idx - 1), min(len(table.columns), cell_idx + 2)):
                if r == row_idx and c == cell_idx:
                    continue
                if r < len(table.rows) and c < len(table.rows[r].cells):
                    cell_text = get_cell_full_text(table.rows[r].cells[c]).strip()
                    if cell_text:
                        surrounding.append(f"[{r+1},{c+1}]: {cell_text[:30]}")
        if surrounding:
            ctx.append(f"周围单元格: {', '.join(surrounding[:3])}")
        return ' | '.join(ctx)

    def _summarize(self, occurrences):
        summary = {"total_count": len(occurrences), "by_type": {}, "by_match_type": {}, "locations": []}
        for occ in occurrences:
            t = occ.get("type", "unknown")
            summary["by_type"][t] = summary["by_type"].get(t, 0) + 1
            mt = occ.get("match_type", "unknown")
            summary["by_match_type"][mt] = summary["by_match_type"].get(mt, 0) + 1
            summary["locations"].append(occ["location"])
        return summary
