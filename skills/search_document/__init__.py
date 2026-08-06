"""
search_document skill - 跨格式文档搜索

在多种文档格式（DOCX, PDF, XLSX, PPTX, TXT, MD 等）中搜索关键词。
支持正则、大小写、全词匹配、近义词扩展搜索、目录批量搜索。
"""
import os
import re
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class SearchDocumentTool(BaseTool):
    name = "search_document"
    description = (
        "在多种文档格式中搜索关键词：DOCX/PDF/XLSX/PPTX/TXT/MD/JSON 等。"
        "支持单文件或整个目录搜索，返回匹配位置的上下文。"
        "支持近义词扩展搜索（LLM 先扩展关键词再搜索，提高召回率）。"
        "与 search_docx 的区别：search_docx 仅搜索 DOCX 文件内容，"
        "search_document 支持所有文档格式。"
    )
    parameters = [
        ToolParameter("file_path", "string", "文档路径或目录路径"),
        ToolParameter("keyword", "string", "搜索关键词"),
        ToolParameter("context_chars", "integer", "匹配上下文前后字符数（默认 50）", required=False, default=50),
        ToolParameter("case_sensitive", "boolean", "区分大小写（默认 false）", required=False, default=False),
        ToolParameter("whole_word", "boolean", "全词匹配（默认 false）", required=False, default=False),
        ToolParameter("use_regex", "boolean", "关键词为正则表达式（默认 false）", required=False, default=False),
        ToolParameter("extended_keywords", "array", "近义词/关联词扩展列表（如 ['预算','费用','成本']），由 LLM 生成以提高召回率", required=False),
    ]

    SUPPORTED_EXTS = {
        ".docx", ".pdf", ".xlsx", ".pptx",
        ".txt", ".md", ".mdx", ".py", ".pyi", ".json", ".csv", ".xml", ".html", ".htm",
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte",
        ".java", ".kt", ".kts", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".cs", ".php", ".rb", ".swift", ".scala",
        ".sh", ".bash", ".zsh", ".ps1", ".sql", ".graphql", ".gql", ".proto", ".tf",
        ".css", ".scss", ".sass", ".less", ".yaml", ".yml", ".toml", ".log", ".ini", ".cfg",
    }
    EXCLUDED_DIRS = {
        ".git", ".svn", ".hg", "node_modules", "bower_components", "vendor",
        "dist", "build", "out", ".next", ".nuxt", ".vite", ".cache", "coverage",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
        ".venv", "venv", "env", ".env", ".idea", ".vscode", ".sigma", ".sigma2.0",
        ".electron-user-data", "logs",
    }

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, keyword: str, context_chars: int = 50,
                case_sensitive: bool = False, whole_word: bool = False,
                use_regex: bool = False, extended_keywords: list = None, **kwargs) -> ToolResult:
        full_path = Path(self._resolve_path(file_path))
        if not full_path.exists():
            return ToolResult.fail(f"路径不存在: {file_path}")

        # 近义词扩展模式
        if extended_keywords and len(extended_keywords) > 0:
            return self._search_extended(
                full_path, keyword, extended_keywords,
                context_chars, case_sensitive, whole_word, use_regex,
            )

        # 目录 or 单文件
        if full_path.is_dir():
            return self._search_directory(
                full_path, keyword, context_chars,
                case_sensitive, whole_word, use_regex,
            )
        else:
            result = self._search_file(
                full_path, keyword, context_chars,
                case_sensitive, whole_word, use_regex,
            )
            return self._wrap_result(result)

    # ── 模式构建 ──

    def _make_pattern(self, keyword: str, whole_word: bool, use_regex: bool,
                      case_sensitive: bool) -> tuple:
        pat = keyword if use_regex else re.escape(keyword)
        if whole_word:
            pat = r'\b' + pat + r'\b'
        flags = 0 if case_sensitive else re.IGNORECASE
        return pat, flags

    # ── 单文件搜索 ──

    def _search_file(self, path: Path, keyword: str, ctx: int,
                     cs: bool, ww: bool, rx: bool) -> dict:
        ext = path.suffix.lower()
        if ext == '.docx':
            return self._search_docx(path, keyword, ctx, cs, ww, rx)
        elif ext == '.pdf':
            return self._search_pdf(path, keyword, ctx, cs, ww, rx)
        elif ext == '.xlsx':
            return self._search_xlsx(path, keyword, ctx, cs, ww, rx)
        elif ext == '.pptx':
            return self._search_pptx(path, keyword, ctx, cs, ww, rx)
        elif ext in self.SUPPORTED_EXTS:
            return self._search_text(path, keyword, ctx, cs, ww, rx)
        else:
            return {"success": False, "file_path": str(path), "error": f"不支持的文件格式: {ext}"}

    def _search_docx(self, path, keyword, ctx, cs, ww, rx):
        try:
            from docx import Document
            from skills.utils.docx_text import get_paragraph_full_text, get_cell_full_text
            doc = Document(str(path))
        except Exception as e:
            return {"success": False, "file_path": str(path), "error": f"无法打开文档: {e}"}
        results = []
        pat, flags = self._make_pattern(keyword, ww, rx, cs)
        for pi, para in enumerate(doc.paragraphs, 1):
            para_text = get_paragraph_full_text(para)
            for m in re.finditer(pat, para_text, flags):
                s = max(0, m.start() - ctx)
                e = min(len(para_text), m.end() + ctx)
                results.append({"type": "paragraph", "location": f"段落 {pi}", "context": para_text[s:e].strip(), "match": m.group()})
        for ti, table in enumerate(doc.tables, 1):
            for ri, row in enumerate(table.rows, 1):
                for ci, cell in enumerate(row.cells, 1):
                    cell_text = get_cell_full_text(cell)
                    for m in re.finditer(pat, cell_text, flags):
                        s = max(0, m.start() - ctx)
                        e = min(len(cell_text), m.end() + ctx)
                        results.append({"type": "table", "location": f"表格{ti} 行{ri}列{ci}", "context": cell_text[s:e].strip(), "match": m.group()})
        return {"success": True, "file_path": str(path), "keyword": keyword, "total_matches": len(results), "results": results[:50]}

    def _search_pdf(self, path, keyword, ctx, cs, ww, rx):
        try:
            import fitz
        except ImportError:
            return {"success": False, "file_path": str(path), "error": "缺少 PyMuPDF (fitz) 库"}
        doc = fitz.open(str(path))
        results = []
        pat, flags = self._make_pattern(keyword, ww, rx, cs)
        for pn in range(len(doc)):
            text = doc[pn].get_text()
            for m in re.finditer(pat, text, flags):
                s = max(0, m.start() - ctx)
                e = min(len(text), m.end() + ctx)
                results.append({"type": "text", "location": f"第 {pn+1} 页", "page": pn+1, "context": text[s:e].strip(), "match": m.group()})
        doc.close()
        return {"success": True, "file_path": str(path), "keyword": keyword, "total_matches": len(results), "results": results[:50]}

    def _search_xlsx(self, path, keyword, ctx, cs, ww, rx):
        from openpyxl import load_workbook
        wb = load_workbook(str(path), data_only=True)
        results = []
        pat, flags = self._make_pattern(keyword, ww, rx, cs)
        for sn in wb.sheetnames:
            ws = wb[sn]
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        text = str(cell.value)
                        for m in re.finditer(pat, text, flags):
                            s = max(0, m.start() - ctx)
                            e = min(len(text), m.end() + ctx)
                            results.append({"type": "cell", "location": f'工作表 "{sn}" {cell.coordinate}', "context": text[s:e].strip(), "match": m.group()})
        wb.close()
        return {"success": True, "file_path": str(path), "keyword": keyword, "total_matches": len(results), "results": results[:50]}

    def _search_pptx(self, path, keyword, ctx, cs, ww, rx):
        from pptx import Presentation
        prs = Presentation(str(path))
        results = []
        pat, flags = self._make_pattern(keyword, ww, rx, cs)
        for si, slide in enumerate(prs.slides, 1):
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    for m in re.finditer(pat, shape.text, flags):
                        s = max(0, m.start() - ctx)
                        e = min(len(shape.text), m.end() + ctx)
                        results.append({"type": "text", "location": f"第 {si} 页", "page": si, "context": shape.text[s:e].strip(), "match": m.group()})
                if shape.has_table:
                    for ri, row in enumerate(shape.table.rows, 1):
                        for ci, cell in enumerate(row.cells, 1):
                            for m in re.finditer(pat, cell.text, flags):
                                s = max(0, m.start() - ctx)
                                e = min(len(cell.text), m.end() + ctx)
                                results.append({"type": "table", "location": f"第{si}页 表格 行{ri}列{ci}", "context": cell.text[s:e].strip(), "match": m.group()})
        return {"success": True, "file_path": str(path), "keyword": keyword, "total_matches": len(results), "results": results[:50]}

    def _search_text(self, path, keyword, ctx, cs, ww, rx):
        content = None
        for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
            try:
                content = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                return {"success": False, "file_path": str(path), "error": f"无法读取文件: {e}"}
        if content is None:
            return {"success": False, "file_path": str(path), "error": "无法读取文件（编码问题或二进制文件）"}
        results = []
        pat, flags = self._make_pattern(keyword, ww, rx, cs)
        lines = content.split('\n')
        for ln, line in enumerate(lines, 1):
            for m in re.finditer(pat, line, flags):
                s = max(0, m.start() - ctx)
                e = min(len(line), m.end() + ctx)
                results.append({"type": "line", "location": f"第 {ln} 行", "line": ln, "context": line[s:e].strip(), "match": m.group()})
        return {"success": True, "file_path": str(path), "keyword": keyword, "total_matches": len(results), "results": results[:50]}

    # ── 目录搜索 ──

    def _iter_supported_files(self, dir_path: Path, max_files: int = 500) -> list[Path]:
        files = []
        for root, dirs, filenames in os.walk(str(dir_path)):
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS and not d.startswith(".")]
            for fn in filenames:
                if Path(fn).suffix.lower() in self.SUPPORTED_EXTS:
                    files.append(Path(root) / fn)
                    if len(files) >= max_files:
                        return files
        return files

    def _search_directory(self, dir_path: Path, keyword, ctx, cs, ww, rx) -> ToolResult:
        """递归搜索目录中所有支持的文档"""
        files = self._iter_supported_files(dir_path)

        if not files:
            return ToolResult.ok(f"目录中没有支持的文件格式 ({len(self.SUPPORTED_EXTS)} 种)", directory=str(dir_path), keyword=keyword, total_files=0, total_matches=0, results=[])

        all_results = []
        total = 0
        failed_count = 0
        for fp in files:
            try:
                r = self._search_file(fp, keyword, ctx, cs, ww, rx)
                if r.get("success") and r.get("total_matches", 0) > 0:
                    all_results.append(r)
                    total += r["total_matches"]
                elif not r.get("success"):
                    failed_count += 1
            except Exception:
                failed_count += 1

        # 格式化搜索结果为 LLM 可读的文本
        lines = [
            f"在目录 {dir_path} 中搜索 \"{keyword}\": {len(files)} 个文件, {total} 处匹配{f', {failed_count} 个文件读取失败' if failed_count else ''}",
            "",
        ]
        idx = 0
        for fr in all_results[:30]:
            fp = fr.get("file_path", "")
            for m in fr.get("results", [])[:10]:  # 每文件最多显示 10 条
                idx += 1
                lines.append(f"  [{idx}] {fp} | {m.get('location', '')} | {m.get('context', '')}")
            remaining = fr.get("total_matches", 0) - min(len(fr.get("results", [])), 10)
            if remaining > 0:
                lines.append(f"  ... 该文件还有 {remaining} 处匹配未显示")
        if total > idx:
            lines.append(f"  ... 还有 {total - idx} 处匹配未显示")
        return ToolResult.ok(
            "\n".join(lines),
            directory=str(dir_path), keyword=keyword,
            total_files=len(files), total_matches=total,
            matched_files=len(all_results), failed_files=failed_count,
            results=all_results[:30],
        )

    # ── 近义词扩展搜索 ──

    def _search_extended(self, full_path: Path, original: str, keywords: list,
                         ctx, cs, ww, rx) -> ToolResult:
        kw_matches = {}
        all_results = []
        search_targets = [full_path] if full_path.is_file() else self._iter_supported_files(full_path)
        for kw in keywords:
            kw_total = 0
            for target in search_targets:
                r = self._search_file(target, kw, ctx, cs, ww, rx)
                if isinstance(r, dict) and r.get("success") and r.get("total_matches", 0) > 0:
                    kw_total += r["total_matches"]
                    for m in r.get("results", []):
                        m["file_path"] = r.get("file_path", str(target))
                        m["matched_keyword"] = kw
                        m["is_synonym"] = kw != original
                        all_results.append(m)
            if kw_total:
                kw_matches[kw] = kw_total

        # 去重
        seen = set()
        unique = []
        for x in all_results:
            k = (x.get("file_path", ""), x.get("location", ""), x.get("context", "")[:40])
            if k not in seen:
                seen.add(k)
                unique.append(x)
        unique.sort(key=lambda x: (not x.get("is_synonym", False), x.get("location", "")))

        # 格式化扩展搜索结果
        lines = [
            f"扩展搜索 \"{original}\" ({len(keywords)} 个关键词), 去重后 {len(unique)} 处匹配：",
            "",
        ]
        for i, m in enumerate(unique[:50], 1):
            synonym_mark = " [近义词]" if m.get("is_synonym") else ""
            lines.append(
                f"  [{i}] {m.get('file_path', '')} | {m.get('location', '')}"
                f" | {m.get('matched_keyword', '')}{synonym_mark} | {m.get('context', '')}"
            )
        if len(unique) > 50:
            lines.append(f"  ... 还有 {len(unique) - 50} 处匹配未显示")
        return ToolResult.ok(
            "\n".join(lines),
            original_keyword=original,
            extended_keywords=keywords,
            keyword_matches=kw_matches,
            total_matches=len(unique),
            results=unique[:50],
        )

    def _wrap_result(self, r: dict) -> ToolResult:
        if not r.get("success"):
            return ToolResult.fail(r.get("error", "搜索失败"))
        results = r.get("results", [])[:50]
        # 格式化匹配详情到 content，让 LLM 能看到文件名、行号、上下文
        lines = [
            f"在 {r.get('file_path', '')} 中找到 {r['total_matches']} 处 \"{r.get('keyword', '')}\" 匹配：",
            "",
        ]
        for i, m in enumerate(results, 1):
            lines.append(f"  [{i}] {m.get('location', '')} | {m.get('context', '')}")
        if r["total_matches"] > 50:
            lines.append(f"  ... 还有 {r['total_matches'] - 50} 处匹配未显示")
        return ToolResult.ok(
            "\n".join(lines),
            file_path=r.get("file_path"), keyword=r.get("keyword"),
            total_matches=r["total_matches"], results=results,
        )
