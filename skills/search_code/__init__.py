"""
search_code skill - 代码库检索

面向项目源码的文本、文件名和符号定义检索。
与 search_document 分离：本工具会过滤依赖、构建产物和缓存目录，
并返回代码文件的行号、上下文及可识别的符号信息。
"""
import ast
import os
import re
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class SearchCodeTool(BaseTool):
    name = "search_code"
    description = (
        "在代码项目中搜索文本、文件名、符号定义及代码关系。"
        "支持查找谁调用某个函数、某个函数调用了谁、文件依赖了哪些模块，"
        "会递归搜索源码并自动排除依赖、构建产物、版本控制和缓存目录，"
        "返回文件路径、行号、上下文与可识别的符号信息。"
    )
    parameters = [
        ToolParameter("path", "string", "代码文件或目录路径；不传则搜索当前工作目录", required=False, default="."),
        ToolParameter("query", "string", "要搜索的文本、文件名或符号名称"),
        ToolParameter(
            "mode", "string",
            "搜索模式：text 搜索代码文本；symbol 搜索定义；file 搜索文件名；relations 查询调用方/被调用者/依赖；auto 自动选择",
            required=False, enum=["auto", "text", "symbol", "file", "relations"], default="auto",
        ),
        ToolParameter(
            "relation", "string",
            "关系类型：callers 谁调用目标；callees 目标调用谁；dependencies 文件依赖谁；dependents 谁依赖文件；all 全部关系",
            required=False, enum=["callers", "callees", "dependencies", "dependents", "all"], default="all",
        ),
        ToolParameter("case_sensitive", "boolean", "是否区分大小写（默认 false）", required=False, default=False),
        ToolParameter("use_regex", "boolean", "是否将 query 作为正则表达式（默认 false）", required=False, default=False),
        ToolParameter("context_lines", "integer", "每个命中的前后上下文行数（默认 2）", required=False, default=2),
        ToolParameter("max_results", "integer", "最多返回多少条命中（默认 50，最大 100）", required=False, default=50),
    ]

    CODE_EXTS = {
        ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".vue", ".svelte", ".java", ".kt", ".kts", ".go", ".rs",
        ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".cs", ".php",
        ".rb", ".swift", ".scala", ".sh", ".bash", ".zsh", ".ps1",
        ".sql", ".graphql", ".gql", ".proto", ".tf",
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg",
        ".md", ".mdx", ".txt",
    }
    EXCLUDED_DIRS = {
        ".git", ".svn", ".hg", "node_modules", "bower_components", "vendor",
        "dist", "build", "out", ".next", ".nuxt", ".vite", ".cache", "coverage",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
        ".venv", "venv", "env", ".env", ".idea", ".vscode", ".sigma", ".sigma2.0",
        ".electron-user-data", "logs",
    }
    MAX_FILES = 5000
    MAX_FILE_BYTES = 2 * 1024 * 1024

    _SYMBOL_PATTERNS = [
        ("class", re.compile(r"^\s*(?:export\s+(?:default\s+)?)?class\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("interface", re.compile(r"^\s*(?:export\s+)?interface\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("type", re.compile(r"^\s*(?:export\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\s*=")),
        ("function", re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")),
        ("function", re.compile(r"^\s*def\s+(?P<name>[A-Za-z_][\w]*)\s*\(")),
        ("class", re.compile(r"^\s*class\s+(?P<name>[A-Za-z_][\w]*)")),
        ("function", re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_][\w]*)\s*\(")),
        ("type", re.compile(r"^\s*type\s+(?P<name>[A-Za-z_][\w]*)\s+(?:struct|interface)")),
        ("function", re.compile(r"^\s*(?:public|private|protected|internal|static|async|final|override|suspend|\s)+[\w<>\[\], ?]+\s+(?P<name>[A-Za-z_$][\w$]*)\s*\(")),
    ]

    def execute(
        self,
        query: str,
        path: str = ".",
        mode: str = "auto",
        relation: str = "all",
        case_sensitive: bool = False,
        use_regex: bool = False,
        context_lines: int = 2,
        max_results: int = 50,
        **kwargs,
    ) -> ToolResult:
        query = query.strip()
        if not query:
            return ToolResult.fail("搜索内容不能为空")
        if mode not in {"auto", "text", "symbol", "file", "relations"}:
            return ToolResult.fail(f"不支持的搜索模式: {mode}")
        if relation not in {"callers", "callees", "dependencies", "dependents", "all"}:
            return ToolResult.fail(f"不支持的关系类型: {relation}")

        target = Path(self._resolve_path(path))
        if not target.exists():
            return ToolResult.fail(f"路径不存在: {path}")
        if target.is_file() and target.suffix.lower() not in self.CODE_EXTS:
            return ToolResult.fail(f"不是支持的代码或配置文件: {target}")

        result_limit = max(1, min(int(max_results), 100))
        line_context = max(0, min(int(context_lines), 10))
        effective_mode = self._resolve_mode(query, mode)

        if effective_mode == "relations":
            return self._search_relations(target, query, relation, case_sensitive, result_limit)
        if effective_mode == "file":
            matches, scanned = self._search_files(target, query, case_sensitive, result_limit)
        elif effective_mode == "symbol":
            matches, scanned = self._search_symbols(target, query, case_sensitive, line_context, result_limit)
        else:
            try:
                pattern = re.compile(query if use_regex else re.escape(query), 0 if case_sensitive else re.IGNORECASE)
            except re.error as exc:
                return ToolResult.fail(f"无效的正则表达式: {exc}")
            matches, scanned = self._search_text(target, pattern, line_context, result_limit)

        if not matches:
            return ToolResult.ok(
                f"未找到与 \"{query}\" 匹配的代码。已扫描 {scanned} 个文件。",
                query=query, mode=effective_mode, scanned_files=scanned, total_matches=0, results=[],
            )

        lines = [f"代码搜索 \"{query}\"（{effective_mode}）：扫描 {scanned} 个文件，找到 {len(matches)} 条结果。", ""]
        for index, item in enumerate(matches, 1):
            location = item["file_path"]
            if item.get("line"):
                location += f":{item['line']}"
            symbol = f" [{item['symbol_type']} {item['symbol_name']}]" if item.get("symbol_name") else ""
            lines.append(f"  [{index}] {location}{symbol}")
            lines.append(f"      {item['context']}")
        return ToolResult.ok(
            "\n".join(lines),
            query=query, mode=effective_mode, scanned_files=scanned,
            total_matches=len(matches), results=matches,
        )

    def _resolve_mode(self, query: str, mode: str) -> str:
        if mode != "auto":
            return mode
        if "/" in query or "\\" in query or "." in Path(query).name:
            return "file"
        return "text"

    def _iter_files(self, target: Path):
        if target.is_file():
            yield target
            return
        count = 0
        for root, dirs, filenames in os.walk(target):
            dirs[:] = [name for name in dirs if name not in self.EXCLUDED_DIRS and not name.startswith(".")]
            for filename in filenames:
                file_path = Path(root) / filename
                if file_path.suffix.lower() not in self.CODE_EXTS:
                    continue
                try:
                    if file_path.stat().st_size > self.MAX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                yield file_path
                count += 1
                if count >= self.MAX_FILES:
                    return

    def _search_files(self, target: Path, query: str, case_sensitive: bool, limit: int):
        needle = query if case_sensitive else query.lower()
        results = []
        scanned = 0
        for file_path in self._iter_files(target):
            scanned += 1
            relative = self._display_path(file_path)
            haystack = relative if case_sensitive else relative.lower()
            if needle in haystack:
                results.append({"file_path": relative, "line": None, "context": relative})
                if len(results) >= limit:
                    break
        return results, scanned

    def _search_symbols(self, target: Path, query: str, case_sensitive: bool, context_lines: int, limit: int):
        needle = query if case_sensitive else query.lower()
        results = []
        scanned = 0
        for file_path in self._iter_files(target):
            scanned += 1
            lines = self._read_lines(file_path)
            if lines is None:
                continue
            for line_index, line in enumerate(lines):
                for symbol_type, pattern in self._SYMBOL_PATTERNS:
                    match = pattern.search(line)
                    if not match:
                        continue
                    name = match.group("name")
                    comparable = name if case_sensitive else name.lower()
                    if needle not in comparable:
                        continue
                    results.append({
                        "file_path": self._display_path(file_path),
                        "line": line_index + 1,
                        "symbol_type": symbol_type,
                        "symbol_name": name,
                        "context": self._format_context(lines, line_index, context_lines),
                    })
                    if len(results) >= limit:
                        return results, scanned
        return results, scanned

    def _search_text(self, target: Path, pattern: re.Pattern, context_lines: int, limit: int):
        results = []
        scanned = 0
        for file_path in self._iter_files(target):
            scanned += 1
            lines = self._read_lines(file_path)
            if lines is None:
                continue
            for line_index, line in enumerate(lines):
                if not pattern.search(line):
                    continue
                results.append({
                    "file_path": self._display_path(file_path),
                    "line": line_index + 1,
                    "context": self._format_context(lines, line_index, context_lines),
                })
                if len(results) >= limit:
                    return results, scanned
        return results, scanned

    def _search_relations(self, target: Path, query: str, relation: str, case_sensitive: bool, limit: int) -> ToolResult:
        files = list(self._iter_files(target))
        symbols = []
        dependencies = []
        calls = []
        for file_path in files:
            source = self._read_source(file_path)
            if source is None:
                continue
            file_symbols, file_dependencies, file_calls = self._analyze_file(file_path, source)
            symbols.extend(file_symbols)
            dependencies.extend(file_dependencies)
            calls.extend(file_calls)

        query_cmp = query if case_sensitive else query.lower()
        target_symbols = [
            s for s in symbols
            if query_cmp in (s["name"] if case_sensitive else s["name"].lower())
        ]
        target_files = [
            self._normalize_path(Path(query)) if self._looks_like_path(query) else ""
        ]
        if not target_symbols and target_files[0]:
            target_symbols = [s for s in symbols if s["file_path"] == target_files[0]]

        results = []
        sections = []
        if relation in {"callers", "all"} and target_symbols:
            target_names = {s["name"] for s in target_symbols}
            caller_edges = [c for c in calls if c["callee"] in target_names]
            sections.append(("调用方（谁调用了目标）", caller_edges))
            results.extend({**edge, "relation": "caller"} for edge in caller_edges[:limit])

        if relation in {"callees", "all"} and target_symbols:
            target_keys = {(s["file_path"], s["name"], s["line"]) for s in target_symbols}
            callee_edges = [c for c in calls if (c["caller_file"], c["caller"], c["caller_line"]) in target_keys]
            sections.append(("被调用者（目标调用了谁）", callee_edges))
            results.extend({**edge, "relation": "callee"} for edge in callee_edges[:limit])

        target_file_paths = {s["file_path"] for s in target_symbols}
        if target_files[0]:
            target_file_paths.add(target_files[0])
        if relation in {"dependencies", "all"} and target_file_paths:
            dependency_edges = [d for d in dependencies if d["file_path"] in target_file_paths]
            sections.append(("依赖（目标文件导入了什么）", dependency_edges))
            results.extend({**edge, "relation": "dependency"} for edge in dependency_edges[:limit])

        if relation in {"dependents", "all"} and target_file_paths:
            dependent_edges = [
                d for d in dependencies
                if self._dependency_matches_target(d["dependency"], target_file_paths)
            ]
            sections.append(("被依赖方（哪些文件导入了目标）", dependent_edges))
            results.extend({**edge, "relation": "dependent"} for edge in dependent_edges[:limit])

        if not results:
            return ToolResult.ok(
                f"未找到 \"{query}\" 的代码关系。已分析 {len(files)} 个文件。",
                query=query, mode="relations", relation=relation,
                scanned_files=len(files), total_matches=0, results=[],
            )

        lines = [f"代码关系 \"{query}\"（{relation}）：分析 {len(files)} 个文件。", ""]
        for title, section_edges in sections:
            if not section_edges:
                continue
            lines.append(f"【{title}】")
            for index, edge in enumerate(section_edges[:limit], 1):
                lines.append(f"  [{index}] {self._format_relation(edge)}")
            lines.append("")
        return ToolResult.ok(
            "\n".join(lines).rstrip(),
            query=query, mode="relations", relation=relation,
            scanned_files=len(files), total_matches=len(results), results=results[:limit * 4],
        )

    def _analyze_file(self, file_path: Path, source: str):
        display_path = self._display_path(file_path)
        symbols = []
        dependencies = []
        calls = []
        if file_path.suffix.lower() in {".py", ".pyi"}:
            try:
                tree = ast.parse(source, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
                        end_line = getattr(node, "end_lineno", node.lineno)
                        symbols.append({
                            "name": node.name, "symbol_type": symbol_type,
                            "file_path": display_path, "line": node.lineno, "end_line": end_line,
                        })
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            dependencies.append({"file_path": display_path, "line": node.lineno, "dependency": alias.name, "context": f"import {alias.name}"})
                    elif isinstance(node, ast.ImportFrom):
                        module = "." * node.level + (node.module or "")
                        dependencies.append({"file_path": display_path, "line": node.lineno, "dependency": module, "context": f"from {module} import ..."})
                for node in ast.walk(tree):
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            callee = self._python_call_name(child.func)
                            if callee:
                                calls.append({
                                    "caller": node.name, "caller_file": display_path,
                                    "caller_line": node.lineno, "callee": callee,
                                    "line": getattr(child, "lineno", node.lineno),
                                    "context": self._source_line(source, getattr(child, "lineno", node.lineno)),
                                })
                return symbols, dependencies, calls
            except (SyntaxError, ValueError):
                pass

        lines = source.splitlines()
        for line_number, line in enumerate(lines, 1):
            for symbol_type, pattern in self._SYMBOL_PATTERNS:
                match = pattern.search(line)
                if match:
                    symbols.append({
                        "name": match.group("name"), "symbol_type": symbol_type,
                        "file_path": display_path, "line": line_number,
                        "end_line": self._guess_block_end(lines, line_number - 1),
                    })
                    break
            for pattern in (
                re.compile(r"^\s*import\s+(.+?)\s+from\s+['\"]([^'\"]+)['\"]"),
                re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]"),
                re.compile(r"^\s*export\s+.*?from\s+['\"]([^'\"]+)['\"]"),
                re.compile(r"^\s*require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
            ):
                match = pattern.search(line)
                if match:
                    dependency = match.group(match.lastindex)
                    dependencies.append({"file_path": display_path, "line": line_number, "dependency": dependency, "context": line.strip()})
                    break
        for symbol in symbols:
            start = symbol["line"] - 1
            end = min(len(lines), symbol["end_line"])
            body = "\n".join(lines[start:end])
            for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", body):
                callee = match.group(1)
                if callee in {"if", "for", "while", "switch", "catch", "function"} or callee == symbol["name"]:
                    continue
                line_offset = body[:match.start()].count("\n")
                calls.append({
                    "caller": symbol["name"], "caller_file": display_path,
                    "caller_line": symbol["line"], "callee": callee,
                    "line": symbol["line"] + line_offset,
                    "context": self._source_line(source, symbol["line"] + line_offset),
                })
        return symbols, dependencies, calls

    @staticmethod
    def _python_call_name(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""

    @staticmethod
    def _source_line(source: str, line_number: int) -> str:
        lines = source.splitlines()
        return lines[line_number - 1].strip() if 0 < line_number <= len(lines) else ""

    @staticmethod
    def _guess_block_end(lines: list[str], start_index: int) -> int:
        if start_index >= len(lines):
            return start_index + 1
        base_indent = len(lines[start_index]) - len(lines[start_index].lstrip())
        end = start_index + 1
        while end < len(lines):
            line = lines[end]
            if line.strip() and len(line) - len(line.lstrip()) <= base_indent:
                break
            end += 1
        return end

    def _dependency_matches_target(self, dependency: str, target_files: set[str]) -> bool:
        dep = dependency.replace("\\", "/")
        dep_stem = dep.rsplit("/", 1)[-1].removesuffix(".js").removesuffix(".ts").removesuffix(".tsx")
        return any(
            target == dep or target.replace("\\", "/").endswith(dep)
            or Path(target).stem == dep_stem
            for target in target_files
        )

    def _normalize_path(self, path: Path) -> str:
        try:
            return self._display_path(Path(self._resolve_path(str(path))))
        except (TypeError, ValueError):
            return str(path).replace("\\", "/")

    @staticmethod
    def _looks_like_path(query: str) -> bool:
        return "/" in query or "\\" in query or query.endswith(tuple(SearchCodeTool.CODE_EXTS))

    @staticmethod
    def _format_relation(edge: dict) -> str:
        if edge.get("relation") == "dependency" or "dependency" in edge:
            return f"{edge['file_path']}:{edge.get('line', '?')} -> {edge.get('dependency', '')} | {edge.get('context', '')}"
        return f"{edge.get('caller_file', '')}:{edge.get('line', '?')} {edge.get('caller', '')} -> {edge.get('callee', '')} | {edge.get('context', '')}"

    def _read_source(self, file_path: Path):
        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None


    def _read_lines(self, file_path: Path):
        source = self._read_source(file_path)
        return source.splitlines() if source is not None else None

    def _display_path(self, file_path: Path) -> str:
        try:
            return str(file_path.relative_to(self.cwd))
        except ValueError:
            return str(file_path)

    @staticmethod
    def _format_context(lines: list[str], line_index: int, context_lines: int) -> str:
        start = max(0, line_index - context_lines)
        end = min(len(lines), line_index + context_lines + 1)
        chunks = []
        for index in range(start, end):
            marker = ">" if index == line_index else " "
            chunks.append(f"{marker}{index + 1}: {lines[index].strip()}")
        return "\n      ".join(chunks)
