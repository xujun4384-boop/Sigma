"""
sandbox skill - Python 代码沙箱

标准 Python 执行环境，与本地 Python 几乎一致。
唯一限制：禁止删除文件/目录。
"""
import io
import os
import sys
import types
import builtins
import subprocess
import traceback
import threading
import time
from contextlib import contextmanager

from skills.base import BaseTool, ToolParameter, ToolResult

# ── 删除操作防护 ──

def _blocked_op(*args, **kwargs):
    raise PermissionError("sandbox: 文件/目录删除操作被禁止")

# os 安全版本
_safe_os = types.ModuleType("os")
_safe_os.__dict__.update(os.__dict__)
_safe_os.remove = _blocked_op
_safe_os.unlink = _blocked_op
_safe_os.rmdir = _blocked_op
_safe_os.removedirs = _blocked_op

# shutil 安全版本
try:
    import shutil as _real_shutil
    _safe_shutil = types.ModuleType("shutil")
    _safe_shutil.__dict__.update(_real_shutil.__dict__)
    _safe_shutil.rmtree = _blocked_op
except ImportError:
    _safe_shutil = None
    _real_shutil = None

# pathlib 安全版本 — 替换 Path.unlink / Path.rmdir
import pathlib as _real_pathlib

class _SafePathMixin:
    def unlink(self, missing_ok=False):
        raise PermissionError("sandbox: Path.unlink() 被禁止")
    def rmdir(self):
        raise PermissionError("sandbox: Path.rmdir() 被禁止")

_PlatformPath = _real_pathlib.WindowsPath if os.name == "nt" else _real_pathlib.PosixPath
_PurePlatformPath = _real_pathlib.PureWindowsPath if os.name == "nt" else _real_pathlib.PurePosixPath

class _SafePath(_SafePathMixin, _PlatformPath):
    pass

_safe_pathlib = types.ModuleType("pathlib")
_safe_pathlib.__dict__.update(_real_pathlib.__dict__)
if os.name == "nt":
    _safe_pathlib.WindowsPath = _SafePath
    _safe_pathlib.PureWindowsPath = _PurePlatformPath
else:
    _safe_pathlib.PosixPath = _SafePath
    _safe_pathlib.PurePosixPath = _PurePlatformPath

# 安全导入：os / shutil / pathlib 返回安全版本，其他正常
_real_import = builtins.__import__

_SAFE_MODULES = {
    "os": _safe_os,
    "pathlib": _safe_pathlib,
}
if _safe_shutil:
    _SAFE_MODULES["shutil"] = _safe_shutil


def _safe_import(name, *args, **kwargs):
    module = _real_import(name, *args, **kwargs)
    return _SAFE_MODULES.get(name, module)


# ── stdout 重定向 ──

@contextmanager
def _redirect_stdout(new_target):
    old = sys.stdout
    sys.stdout = new_target
    try:
        yield
    finally:
        sys.stdout = old


# ── 会话状态 ──

SESSION_TTL = 30 * 60

_session_lock = threading.Lock()
_sessions: dict[int, dict] = {}
_session_touched: dict[int, float] = {}


def _get_session_ns() -> dict:
    key = threading.get_ident()
    now = time.time()
    with _session_lock:
        expired = [k for k, t in _session_touched.items() if now - t > SESSION_TTL]
        for k in expired:
            _sessions.pop(k, None)
            _session_touched.pop(k, None)
        if key not in _sessions:
            _sessions[key] = {}
        _session_touched[key] = now
        return _sessions[key]


def _reset_session_ns():
    key = threading.get_ident()
    with _session_lock:
        _sessions.pop(key, None)
        _session_touched.pop(key, None)


def _new_sandbox_ns(cwd: str) -> dict:
    """构建沙箱命名空间，标准 Python 环境 + 删除防护。"""
    ns = {
        "__builtins__": dict(builtins.__dict__),
        "__name__": "__sandbox__",
        "__file__": None,
        "cwd": cwd,
    }
    ns["__builtins__"]["__import__"] = _safe_import
    return ns


# ── 工具 ──

class SandboxTool(BaseTool):
    name = "sandbox_run"
    description = (
        "执行 Python 代码。标准 Python 环境，支持所有标准库和已安装的第三方库。\n"
        "唯一限制：禁止删除文件/目录（os.remove、shutil.rmtree 等会报错）。\n"
        "💡 有状态：多次调用共享变量/import/已定义函数，像 REPL 一样分步执行。\n"
        "传 reset=true 清空状态从头开始。"
    )
    parameters = [
        ToolParameter("code", "string", "Python 代码"),
        ToolParameter("language", "string", "python / bash。默认 python", required=False, default="python"),
        ToolParameter("reset", "boolean", "清空会话状态，从干净环境重新开始", required=False, default=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, code: str, language: str = "python", reset: bool = False, **kwargs) -> ToolResult:
        if reset:
            _reset_session_ns()

        if not code or not code.strip():
            if reset:
                return ToolResult.ok("会话状态已重置")
            return ToolResult.fail("code 不能为空")

        if language == "bash":
            return self._run_bash(code)
        return self._run_python(code)

    # ── Python ──

    def _run_python(self, code: str) -> ToolResult:
        self._emit_progress("正在执行 Python 代码...")
        cwd = str(self.cwd)
        stdout = io.StringIO()

        ns = _get_session_ns()
        if not ns:
            ns.update(_new_sandbox_ns(cwd))
        else:
            ns["cwd"] = cwd
            ns.setdefault("__builtins__", dict(builtins.__dict__))
            ns["__builtins__"]["__import__"] = _safe_import
            ns.setdefault("__name__", "__sandbox__")

        error = None

        try:
            with _redirect_stdout(stdout):
                compiled = compile(code, "<sandbox>", "exec")
                exec(compiled, ns, ns)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            traceback.print_exc(file=stdout)

        output = stdout.getvalue()
        truncated = False
        if len(output.encode("utf-8")) > 80 * 1024:
            output = output.encode("utf-8")[:80 * 1024].decode("utf-8", errors="ignore")
            output += "\n[输出已截断]"
            truncated = True

        if error:
            return ToolResult(success=False, content=f"{error}\n\n{output}", truncated=truncated)
        return ToolResult(success=True, content=output or "(无输出)", truncated=truncated)

    # ── Bash ──

    def _run_bash(self, code: str) -> ToolResult:
        self._emit_progress(f"正在执行命令: {code[:80]}{'...' if len(code) > 80 else ''}")
        try:
            process = subprocess.Popen(
                code,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.cwd),
                text=True,
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

            t_out = threading.Thread(target=_read_stdout, daemon=True)
            t_err = threading.Thread(target=_read_stderr, daemon=True)
            t_out.start()
            t_err.start()

            timeout = 60
            try:
                process.wait(timeout=timeout)
                t_out.join(timeout=2)
                t_err.join(timeout=2)

                output = "".join(stdout_lines)
                if stderr_lines:
                    output += "\n[stderr]\n" + "".join(stderr_lines)
                truncated = False
                if len(output.encode("utf-8")) > 80 * 1024:
                    output = output.encode("utf-8")[:80 * 1024].decode("utf-8", errors="ignore")
                    output += "\n[输出已截断]"
                    truncated = True

                if process.returncode != 0:
                    return ToolResult(success=False, content=f"退出码 {process.returncode}\n{output}", truncated=truncated)
                return ToolResult(success=True, content=output or "(无输出)", truncated=truncated)

            except subprocess.TimeoutExpired:
                time.sleep(0.5)
                output = "".join(stdout_lines)
                if stderr_lines:
                    output += "\n[stderr]\n" + "".join(stderr_lines)
                output = output.strip() or "(无输出)"
                timeout_truncated = False
                if len(output) > 3000:
                    output = output[:3000] + "\n...(输出已截断)"
                    timeout_truncated = True

                output = (
                    f"[进程仍在运行中，PID: {process.pid}]\n"
                    f"执行超过 {timeout}s，已捕获以下输出:\n{output}"
                )
                return ToolResult(success=False, content=output, truncated=timeout_truncated)

        except Exception as e:
            return ToolResult.fail(f"执行异常: {e}")
