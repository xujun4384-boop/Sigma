"""
convert_pptx skill - PPTD 转 PPTX

将 .pptd 中间格式检查并转换为 .pptx 文件。
使用 kimi_ppt_dsl.pyz 工具进行格式校验和转换。
"""
import subprocess
import sys
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False


class ConvertPptxTool(BaseTool):
    name = "convert_pptx"
    description = (
        "将 .pptd (Kimi PPTD DSL) 中间格式检查并转换为 .pptx 演示文稿。"
        "支持 check（仅检查）/ convert（仅转换）/ check_convert（检查+转换）。"
        "自动规范化旧版 PPTD 格式。"
    )
    parameters = [
        ToolParameter("input_path", "string", ".pptd 主文件路径"),
        ToolParameter("output_path", "string", "输出 .pptx 路径（可选，默认与 .pptd 同名）", required=False),
        ToolParameter("action", "string", "操作: check / convert / check_convert（默认）", required=False, default="check_convert"),
        ToolParameter("target_project_folder", "string", "输出所在项目目录；未指定 output_path 时，会在该目录下生成同名 .pptx", required=False),
        ToolParameter("timeout", "integer", "PPTD 检查/转换命令超时时间（秒），默认 300", required=False, default=300),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)
        self.skill_dir = Path(__file__).resolve().parent
        self.pyz_path = self.skill_dir / "scripts" / "kimi_ppt_dsl.pyz"

    def execute(self, input_path: str, output_path: str = None,
                action: str = "check_convert", target_project_folder: str = None,
                timeout: int = 300, **kwargs) -> ToolResult:
        if not HAS_RUAMEL:
            return ToolResult.fail("缺少 ruamel.yaml 库，请执行: pip install ruamel.yaml")

        # 健壮性：确保 input_path 是字符串，防止 LLM 传入非字符串类型
        if not isinstance(input_path, str):
            return ToolResult.fail(f"input_path 必须是字符串，实际类型: {type(input_path).__name__}")

        resolved = self._resolve_path(input_path)
        try:
            input_file = Path(resolved)
        except (TypeError, ValueError) as e:
            return ToolResult.fail(f"无法解析 PPTD 路径: {input_path}（{e}）")

        if not input_file.exists():
            return ToolResult.fail(f"PPTD 文件不存在: {input_path}")
        if input_file.suffix.lower() != ".pptd":
            return ToolResult.fail("仅支持 .pptd 输入文件")

        try:
            pyz_exists = self.pyz_path.exists()
        except AttributeError:
            return ToolResult.fail(f"Kimi PPT DSL 工具路径异常: {type(self.pyz_path).__name__}")
        if not pyz_exists:
            return ToolResult.fail(f"Kimi PPT DSL 工具不存在: {self.pyz_path}")

        target_dir = Path(self._resolve_path(target_project_folder)) if target_project_folder else input_file.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        if output_path:
            output_candidate = Path(output_path).expanduser()
            output_file = output_candidate if output_candidate.is_absolute() else target_dir / output_candidate
        else:
            output_file = target_dir / f"{input_file.stem}.pptx"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        normalized_action = action.strip().lower().replace("-", "_")
        if normalized_action not in {"check", "convert", "check_convert"}:
            return ToolResult.fail(f"不支持的 action: {action}（仅支持 check/convert/check_convert）")

        # 1. 规范化
        repair = self._normalize_pptd(input_file)
        if not repair["success"]:
            return ToolResult.fail("PPTD 自动规范化失败", details=repair)

        # 2. 检查
        check_result = None
        if normalized_action in {"check", "check_convert"}:
            check_result = self._run_tool(["check", str(input_file)], cwd=input_file.parent, timeout=timeout)
            if check_result["returncode"] != 0 and self._has_errors(check_result):
                check_stdout = check_result.get("stdout", "")
                check_stderr = check_result.get("stderr", "")
                # 关键：将 checker 的完整输出写入 content，否则 LLM 永远看不到具体错误
                return ToolResult.fail(
                    f"PPTD 检查失败，以下为 checker 输出，请据此修复后重试：\n\n"
                    f"=== STDOUT ===\n{check_stdout}\n=== STDERR ===\n{check_stderr}",
                    details={"check": check_result, "repair": repair},
                )

        # 3. 转换
        convert_result = None
        if normalized_action in {"convert", "check_convert"}:
            convert_result = self._run_tool(
                ["convert", str(input_file), "-o", str(output_file)],
                cwd=input_file.parent,
                timeout=timeout,
            )
            if convert_result["returncode"] != 0:
                convert_stdout = convert_result.get("stdout", "")
                convert_stderr = convert_result.get("stderr", "")
                return ToolResult.fail(
                    f"PPTX 转换失败，以下为输出，请据此修复后重试：\n\n"
                    f"=== STDOUT ===\n{convert_stdout}\n=== STDERR ===\n{convert_stderr}",
                    details={"convert": convert_result, "repair": repair},
                )
            if not output_file.exists():
                return ToolResult.fail(
                    f"转换命令成功但未生成 PPTX: {output_file}",
                    details={"convert": convert_result},
                )

        warnings = self._extract_warnings(check_result)

        return ToolResult.ok(
            f"PPTX 生成成功: {output_file.name}",
            input_path=str(input_file),
            output_path=str(output_file),
            action=normalized_action,
            size=output_file.stat().st_size if output_file.exists() else None,
            warnings=warnings,
        )

    # ── 规范化 ──

    def _normalize_pptd(self, input_file: Path) -> dict:
        yaml = YAML()
        yaml.preserve_quotes = True
        changed_files = []
        warnings = []

        try:
            raw = input_file.read_text(encoding="utf-8")
            raw = raw.replace("\\n", "\n")
            data = yaml.load(raw)
            if not isinstance(data, dict):
                return {"success": False, "error": "主 PPTD 不是 YAML 对象"}

            changed = False

            # 清理旧版 PPTD 的无效字段（会被 LLM 误写为 title/subtitle/author/ratio 等）
            for old_field in ("title", "subtitle", "author", "description", "presenter"):
                if old_field in data:
                    data.pop(old_field)
                    changed = True

            # 兼容旧版 ratio / aspect_ratio → size
            ratio_value = None
            for ratio_key in ("ratio", "aspect_ratio"):
                if ratio_key in data and "size" not in data:
                    ratio_value = str(data.pop(ratio_key))
                    break
            if ratio_value:
                data["size"] = [1280, 720] if ratio_value == "16:9" else [960, 720]
                changed = True
            if "size" not in data:
                data["size"] = [1280, 720]
                changed = True

            theme = data.get("theme")
            if isinstance(theme, dict) and "fonts" in theme and "textStyles" not in theme:
                fonts = theme.pop("fonts") or {}
                title_font = fonts.get("title", "Microsoft YaHei") if isinstance(fonts, dict) else "Microsoft YaHei"
                body_font = fonts.get("body", title_font) if isinstance(fonts, dict) else title_font
                colors = theme.get("colors") if isinstance(theme.get("colors"), dict) else {}
                theme["textStyles"] = {
                    "title": {"fontSize": 44, "fontFamily": title_font, "color": colors.get("text", "#111827")},
                    "body": {"fontSize": 20, "fontFamily": body_font, "color": colors.get("textSecondary", colors.get("text", "#374151"))},
                }
                changed = True

            pages = data.get("pages")
            if isinstance(pages, list):
                normalized_pages = []
                for page in pages:
                    if isinstance(page, str) and "\\n" in page:
                        for part in page.split("\\n"):
                            cleaned = part.strip()
                            if cleaned.startswith("-"):
                                cleaned = cleaned[1:].strip()
                            if cleaned:
                                normalized_pages.append(cleaned)
                        changed = True
                    elif isinstance(page, str):
                        # 将 .ppage 后缀统一重命名为 .page
                        page_str = str(page)
                        if page_str.endswith(".ppage"):
                            new_page = page_str[:-6] + ".page"
                            old_path = input_file.parent / page_str
                            new_path = input_file.parent / new_page
                            if old_path.exists():
                                old_path.rename(new_path)
                                warnings.append(f"已重命名: {page_str} → {new_page}")
                            normalized_pages.append(new_page)
                            changed = True
                        else:
                            normalized_pages.append(page_str)
                data["pages"] = normalized_pages

            if changed:
                with input_file.open("w", encoding="utf-8") as f:
                    yaml.dump(data, f)
                changed_files.append(str(input_file))

            # 规范化每个 page 文件（也检测磁盘上遗留的 .ppage 文件）
            # 扫描 pages 目录下的 .ppage 文件并重命名
            pages_dir = input_file.parent / "pages"
            if pages_dir.is_dir():
                for ppage_file in pages_dir.glob("*.ppage"):
                    new_name = ppage_file.stem + ".page"
                    new_path = ppage_file.with_name(new_name)
                    ppage_file.rename(new_path)
                    warnings.append(f"已重命名遗留文件: {ppage_file.name} → {new_name}")
                    changed_files.append(str(new_path))

            for page_ref in data.get("pages", []) if isinstance(data.get("pages"), list) else []:
                page_path = (input_file.parent / page_ref).resolve()
                if not page_path.exists():
                    # 尝试 .ppage 回退
                    ppage_path = page_path.with_suffix(".ppage")
                    if ppage_path.exists():
                        ppage_path.rename(page_path)
                        warnings.append(f"已重命名: {ppage_path.name} → {page_path.name}")
                    else:
                        continue
                if page_path.suffix != ".page":
                    continue
                result = self._normalize_page(page_path, yaml, input_file.parent)
                if result.get("changed"):
                    changed_files.append(str(page_path))
                if result.get("warning"):
                    warnings.append(result["warning"])

            return {"success": True, "changed_files": changed_files, "warnings": warnings}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _normalize_page(self, page_path: Path, yaml, project_dir: Path) -> dict:
        raw = page_path.read_text(encoding="utf-8")
        expanded = raw.replace("\\n", "\n")
        try:
            data = yaml.load(expanded)
        except Exception:
            return {"changed": False, "warning": f"无法解析页面: {page_path}"}
        if not isinstance(data, dict):
            return {"changed": False}

        changed = False

        if "type" in data and "pageType" not in data:
            data["pageType"] = data.pop("type")
            changed = True
        # 清理旧版 page 文件的无效字段
        for old_key in ("layout", "decoration", "background_color", "background-image"):
            if old_key in data:
                data.pop(old_key)
                changed = True

        background = data.get("background")
        if isinstance(background, dict) and "color" in background and "type" not in background:
            background["type"] = "solid"
            changed = True

        elements = data.get("elements")
        if isinstance(elements, list):
            for index, element in enumerate(elements, 1):
                if not isinstance(element, dict):
                    continue
                if "type" in element and "elementType" not in element:
                    element["elementType"] = element.pop("type")
                    changed = True
                element.setdefault("elementId", f"el-{index:02d}")
                if "bounds" not in element:
                    x = element.pop("x", 0)
                    y = element.pop("y", 0)
                    w = element.pop("width", 100)
                    h = element.pop("height", 40)
                    element["bounds"] = [x, y, w, h]
                    changed = True
                if element.get("elementType") == "shape":
                    if "shape" in element and "shapeName" not in element:
                        shape = element.pop("shape")
                        element["shapeName"] = self._normalize_shape(shape)
                        changed = True
                    elif "shapeName" in element:
                        ns = self._normalize_shape(element["shapeName"])
                        if ns != element["shapeName"]:
                            element["shapeName"] = ns
                            changed = True
                    if isinstance(element.get("fill"), str):
                        element["fill"] = {"type": "solid", "color": element["fill"]}
                        changed = True
                    if isinstance(element.get("border"), str):
                        element["border"] = {"style": "solid", "width": 1, "color": element["border"]}
                        changed = True
                elif element.get("elementType") == "text":
                    content = element.get("content") if isinstance(element.get("content"), dict) else {}
                    for k in ("text", "font", "size", "color", "lineHeight", "wrap"):
                        if k in element:
                            mk = {"font": "fontFamily", "size": "fontSize"}.get(k, k)
                            content[mk] = element.pop(k)
                            changed = True
                    if "bold" in element:
                        if element.pop("bold"):
                            t = content.get("text", "")
                            content["text"] = f"<p><strong>{t}</strong></p>" if "<" not in str(t) else t
                        changed = True
                    align = element.pop("align", None)
                    valign = element.pop("valign", None)
                    if align or valign:
                        content["align"] = [align or "left", valign or "top"]
                        changed = True
                    if content:
                        element["content"] = content

        if changed:
            with page_path.open("w", encoding="utf-8") as f:
                yaml.dump(data, f)
        return {"changed": changed}

    def _normalize_shape(self, value: str) -> str:
        aliases = {
            "rectangle": "rect", "roundedRectangle": "roundRect",
            "rounded_rectangle": "roundRect", "roundRectangle": "roundRect",
            "line": "straightConnector1",
        }
        return aliases.get(value, value)

    # ── 工具执行 ──

    def _run_tool(self, args: list, cwd: Path, timeout: int = 300) -> dict:
        cmd = [sys.executable, str(self.pyz_path), *args]
        try:
            completed = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"command": cmd, "returncode": -1, "stdout": "", "stderr": "超时"}
        return {
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    def _has_errors(self, check_result: dict) -> bool:
        stdout = str(check_result.get("stdout") or "")
        if "Summary:" in stdout:
            return not ("Summary: 0 error(s)" in stdout or "Summary: 0 errors" in stdout)
        return any(marker in stdout for marker in ["[MissingFieldError]", "[YamlSyntaxError]", "[ValidationError]", " ERROR:"])

    def _extract_warnings(self, check_result: dict | None) -> list:
        if not check_result:
            return []
        warnings = []
        for line in str(check_result.get("stdout") or "").splitlines():
            s = line.strip()
            if "Warning]" in s or s.startswith("WARNING:"):
                warnings.append(s)
        return warnings
