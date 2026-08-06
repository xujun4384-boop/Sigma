"""
文件操作工具：read, write, bash
"""
import os
import subprocess
import tempfile
import threading
import time
from skills.base import BaseTool, ToolParameter, ToolResult


class ReadTool(BaseTool):
    name = "read"
    description = (
        "读取文件内容。推荐不传 offset/limit 以一次性读取整个文件，"
        "仅在文件被截断后才用 offset 继续读取剩余部分。支持文本文件和代码文件。"
    )
    parameters = [
        ToolParameter(
            name="file_path", type="string",
            description="要读取的文件路径（绝对路径或相对于工作目录的路径）",
            required=True,
        ),
        ToolParameter(
            name="offset", type="integer",
            description="从第几行开始。仅在返回结果被截断后继续读取时使用，不要主动分段。",
            required=False,
        ),
        ToolParameter(
            name="limit", type="integer",
            description="最多读取行数。仅在收到 [TRUNCATED] 信号后用于读取剩余部分，不要预先设置此参数。",
            required=False,
        ),
    ]

    # 默认读取上限（行），超限自动截断并通知 LLM
    DEFAULT_READ_LIMIT = 2000

    def execute(self, file_path: str, offset: int = 0, limit: int = 0, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")
        if not full_path.is_file():
            return ToolResult.fail(f"路径不是文件: {full_path}")

        try:
            with full_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = max(0, offset - 1) if offset > 0 else 0

            # 用户显式传了 limit → 尊重用户意图
            if limit > 0:
                end = start + limit
            else:
                # 没传 limit → 自动截断上限
                end = start + self.DEFAULT_READ_LIMIT
                if end >= total_lines:
                    end = total_lines  # 文件不大，全部读取
                    limit = 0

            selected = lines[start:end]
            auto_truncated = (end < total_lines) and (limit == 0)

            # 行号格式化
            max_ln = len(str(start + len(selected)))
            output = "".join(f"{i + start + 1:>{max_ln}}|{line}" for i, line in enumerate(selected))

            header_parts = [f"[文件] {full_path}  (第 {start + 1}-{start + len(selected)} 行 / 共 {total_lines} 行)"]
            prefix = ""

            if auto_truncated:
                remaining = total_lines - end
                prefix = (
                    f"\u250c [TRUNCATED] 仅显示文件前 {end} 行，"
                    f"剩余约 {remaining} 行省略。"
                    f"如需继续阅读，请用 offset={end + 1}。"
                    f"如需完整分析大文件，建议使用 longread 切分 + sub_agent 并行阅读。\n"
                    f"\u2514{'─' * 60}\n\n"
                )

            header = "\n".join(header_parts) + "\n\n"
            suffix = ""
            if not auto_truncated and limit == 0 and total_lines > 0:
                # 成功一次读完 → 末尾追加提醒，防止 LLM 后续回退到分块模式
                suffix = (
                    f"\n\n(已完整读取 {total_lines} 行。"
                    f"阅读其他文件时同样不要传 offset/limit，一次性完整读取。"
                    f"多个文件请用 sub_agent 并行处理。)"
                )
            return ToolResult.ok(
                prefix + header + output + suffix,
                truncated=auto_truncated or (limit > 0 and end < total_lines),
                total_lines=total_lines,
                path=str(full_path),
            )
        except Exception as e:
            return ToolResult.fail(f"读取文件失败: {e}")


class WriteTool(BaseTool):
    name = "write"
    description = "将内容写入指定文件。如果文件已存在则覆盖，不存在则创建。"
    parameters = [
        ToolParameter(name="file_path", type="string", description="要写入的文件路径", required=True),
        ToolParameter(name="content", type="string", description="要写入的文件内容", required=True),
    ]

    def execute(self, file_path: str, content: str, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            return ToolResult.ok(f"文件已写入: {full_path} ({size} 字节)", path=str(full_path), size=size)
        except Exception as e:
            return ToolResult.fail(f"写入文件失败: {e}")


class EditTool(BaseTool):
    name = "edit"
    description = (
        "精确搜索替换文件内容。支持批量替换（推荐）和单次替换。\n"
        "推荐：传 edits [{old_str, new_str}, ...] 一次完成多处修改。\n"
        "单次（不推荐，请尽量用批量）：传 old_str + new_str。\n"
        "old_str 必须精确匹配（含所有空格、缩进、空行）。\n"
        "批量模式下，所有 old_str 先在原始文件中预校验（存在且唯一），全部通过才写入。"
    )
    parameters = [
        ToolParameter(name="file_path", type="string", description="要编辑的文件路径", required=True),
        ToolParameter(name="edits", type="array", description="批量替换列表 [{old_str, new_str}, ...]。同一文件多处修改时务必使用此参数，不要多次调用 edit。", required=False),
        ToolParameter(name="old_str", type="string", description="要替换的原文本。仅单次替换时使用，批量模式优先用 edits。", required=False),
        ToolParameter(name="new_str", type="string", description="替换后的新文本。仅单次替换时使用。", required=False),
    ]

    def execute(self, file_path: str, old_str: str = "", new_str: str = "", edits: list = None, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")
        if not full_path.is_file():
            return ToolResult.fail(f"路径不是文件: {full_path}")

        try:
            original = full_path.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"无法读取文件: {e}")

        # ── 批量模式 ──
        if edits and isinstance(edits, list) and len(edits) > 0:
            return self._execute_batch(full_path, original, edits)

        # ── 单次模式（向后兼容）──
        if not old_str:
            return ToolResult.fail("缺少 old_str 参数")

        count = original.count(old_str)
        if count == 0:
            return ToolResult.fail(
                f"未找到匹配的 old_str。请确认原文精确匹配（含空格、缩进）。"
                f"可以先 read 文件确认内容。"
            )
        if count > 1:
            idx = original.find(old_str)
            context_start = max(0, idx - 40)
            context_end = min(len(original), idx + len(old_str) + 40)
            return ToolResult.fail(
                f"old_str 在文件中出现了 {count} 处，不够唯一。"
                f"请包含更多上下文使匹配唯一。"
                f"首处上下文: ...{original[context_start:context_end]}..."
            )

        modified = original.replace(old_str, new_str, 1)
        try:
            full_path.write_text(modified, encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"无法写入文件: {e}")

        line_no = original[:original.find(old_str)].count("\n") + 1
        return ToolResult.ok(
            f"已编辑: {full_path} 第 {line_no} 行 (替换 1 处)",
            path=str(full_path),
            line=line_no,
            replacements=1,
        )

    def _execute_batch(self, full_path, original: str, edits: list) -> ToolResult:
        """批量编辑：预校验所有 old_str → 全部通过后按序执行替换"""
        total = len(edits)

        # ── 阶段1: 预校验全部 old_str（基于原始文件）──
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return ToolResult.fail(f"edits[{i}] 格式错误：每项必须为 {{old_str, new_str}}")
            old = edit.get("old_str", "")
            new = edit.get("new_str", "")
            if not old:
                return ToolResult.fail(f"edits[{i}] 缺少 old_str")

            count = original.count(old)
            if count == 0:
                return ToolResult.fail(
                    f"edits[{i}] 未找到匹配的 old_str。"
                    f"请确认原文精确匹配（含空格、缩进）。"
                )
            if count > 1:
                idx = original.find(old)
                ctx_start = max(0, idx - 40)
                ctx_end = min(len(original), idx + len(old) + 40)
                return ToolResult.fail(
                    f"edits[{i}] 的 old_str 出现了 {count} 处，不够唯一。"
                    f"首处上下文: ...{original[ctx_start:ctx_end]}..."
                )

        # ── 阶段2: 全部通过，按序执行替换 ──
        modified = original
        lines_info: list[str] = []
        for i, edit in enumerate(edits):
            old = edit["old_str"]
            new = edit.get("new_str", "")
            line_no = modified[:modified.find(old)].count("\n") + 1
            modified = modified.replace(old, new, 1)
            lines_info.append(f"  第{i + 1}处: 第{line_no}行")

        try:
            full_path.write_text(modified, encoding="utf-8")
        except Exception as e:
            return ToolResult.fail(f"无法写入文件: {e}")

        return ToolResult.ok(
            f"已编辑: {full_path} (批量替换 {total} 处)\n" + "\n".join(lines_info),
            path=str(full_path),
            replacements=total,
            details=lines_info,
        )


class BashTool(BaseTool):
    name = "bash"
    description = (
        "执行 shell 命令并返回输出。\n\n"
        "✅ 适用场景：\n"
        "- 运行脚本、测试（pytest, npm test, go test）\n"
        "- 安装依赖（pip install, npm install）\n"
        "- 构建项目（make, go build, cargo build）\n"
        "- Git 操作（git status, git diff, git log）\n"
        "- 启动/管理服务，进程管理，端口检查\n\n"
        "❌ 禁止场景（有专用工具）：\n"
        "- 读取文件 → 用 read / batch_read\n"
        "- 搜索文本内容 → 用 grep\n"
        "- 搜索文件 → 用 find\n"
        "- 列出目录 → 文件树已显示，要用请用 ls 工具\n"
        "- 创建/写入文件 → 用 write（不要用 echo、cat、New-Item 等写文件）\n\n"
        "长时间运行的服务会后台继续，通过检查端口确认状态。"
    )
    parameters = [
        ToolParameter(name="command", type="string", description="要执行的 shell 命令", required=True),
        ToolParameter(name="timeout", type="integer", description="最长等待秒数，默认 30 秒。超时后返回已捕获的输出，进程继续后台运行", required=False),
    ]

    def execute(self, command: str, timeout: int = 30, **kwargs) -> ToolResult:
        """
        使用 Popen 执行命令，实时捕获输出。
        如果命令在 timeout 秒内未结束，返回已捕获的输出并让进程继续后台运行。
        """
        try:
            # Windows: 强制控制台编码为 UTF-8，解决中文文件名/输出乱码
            if os.name == "nt":
                command = f"chcp 65001 > nul && {command}"

            # 使用 Popen 而非 subprocess.run，支持实时输出捕获
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.cwd),
                encoding="utf-8",
                errors="replace",
                # Windows: 创建新进程组，便于管理
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            stdout_lines = []
            stderr_lines = []

            def _read_stdout():
                try:
                    for line in iter(process.stdout.readline, ""):
                        if line:
                            stdout_lines.append(line)
                except Exception:
                    pass

            def _read_stderr():
                try:
                    for line in iter(process.stderr.readline, ""):
                        if line:
                            stderr_lines.append(line)
                except Exception:
                    pass

            # 启动读取线程
            t_stdout = threading.Thread(target=_read_stdout, daemon=True)
            t_stderr = threading.Thread(target=_read_stderr, daemon=True)
            t_stdout.start()
            t_stderr.start()

            # 等待进程结束，或超时
            try:
                process.wait(timeout=timeout)
                # 进程正常结束，等待读取线程完成
                t_stdout.join(timeout=2)
                t_stderr.join(timeout=2)

                output = "".join(stdout_lines)
                if stderr_lines:
                    output += "\n[stderr]\n" + "".join(stderr_lines)
                output = output.strip() or "(无输出)"
                max_chars = 20000
                if len(output) > max_chars:
                    # 保留开头（import 日志等）+ 结尾（实际结果），中间省略
                    head = output[:max_chars // 2]
                    tail = output[-(max_chars // 2):]
                    output = (
                        f"\u250c [TRUNCATED] 输出过长 ({len(output)} 字符)，已保留开头和结尾各 {max_chars // 2} 字符\n"
                        f"\u2502 完整输出被截断，如结果不完整请精简命令或用管道过滤\n"
                        f"\u2514{'─' * 60}\n\n"
                        f"{head}\n"
                        f"\n\u250c ... 中间省略 {len(output) - max_chars} 字符 ...\n"
                        f"\u2514{'─' * 40}\n\n"
                        f"{tail}"
                    )
                    truncated = True
                else:
                    truncated = False

                return ToolResult.ok(
                    output,
                    exit_code=process.returncode,
                    truncated=truncated,
                    command=command,
                )

            except subprocess.TimeoutExpired:
                # 进程还在运行（典型场景：启动了一个服务）
                # 等待读取线程收集更多输出
                time.sleep(0.5)
                output = "".join(stdout_lines)
                if stderr_lines:
                    output += "\n[stderr]\n" + "".join(stderr_lines)
                output = output.strip() or "(无输出)"
                if len(output) > 3000:
                    output = output[:3000] + "\n...(输出已截断)"

                pid = process.pid
                output = (
                    f"[进程仍在运行中，PID: {pid}]\n"
                    f"命令在 {timeout}s 内未结束，已捕获以下初始输出:\n"
                    f"{output}\n\n"
                    f"提示：进程将在后台继续运行。如需检查服务状态，可使用 "
                    f"netstat -ano | findstr LISTENING 查看端口监听情况。"
                )

                return ToolResult.ok(
                    output,
                    exit_code=None,
                    command=command,
                    background_pid=pid,
                    truncated=len(output) > 4000,
                )

        except Exception as e:
            return ToolResult.fail(f"命令执行失败: {e}")
