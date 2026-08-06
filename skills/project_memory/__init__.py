"""
project_memory skill - 项目记忆管理

在项目工作目录的 .sigma2.0/memory/ 下维护：
  - project_overview.md: 全局目录扫描 + 文件用途推测
  - task_history.md: 每次对话完成的任务记录
"""
import os
import re
from pathlib import Path
from datetime import datetime

from skills.base import BaseTool, ToolParameter, ToolResult

# 扫描时排除的目录
SCAN_EXCLUDE_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv', '.env',
    'dist', 'build', '.next', '.nuxt', 'coverage', '.sigma', '.sigma2.0',
    '.idea', '.vscode', '.cursor', '.electron-user-data', 'logs',
    '.pytest_cache', '.mypy_cache', '.tox', '.eggs',
}


def _get_memory_dir(working_dir: str, source: str = "project") -> Path:
    """获取记忆目录路径。
    source="project": {working_dir}/.sigma2.0/memory/
    source="sigma": {sigma_app}/.sigma/memory/
    """
    if source == "sigma":
        return Path(__file__).parent.parent.parent / ".sigma" / "memory"
    return Path(working_dir) / ".sigma2.0" / "memory"


def _get_overview_path(working_dir: str, source: str = "project") -> Path:
    prefix = "network_bridge_" if source == "sigma" else "project_"
    return _get_memory_dir(working_dir, source) / f"{prefix}overview.md"


def _get_history_path(working_dir: str, source: str = "project") -> Path:
    prefix = "network_bridge_" if source == "sigma" else "task_"
    return _get_memory_dir(working_dir, source) / f"{prefix}history.md"


def _ensure_memory_dir(working_dir: str, source: str = "project"):
    _get_memory_dir(working_dir, source).mkdir(parents=True, exist_ok=True)


def _walk_directory(root: Path, prefix: str = "") -> tuple[str, int]:
    """遍历目录树，返回 (listing, count)。排除隐藏文件和排除目录。"""
    try:
        entries = sorted(
            [e for e in root.iterdir()
             if e.name not in SCAN_EXCLUDE_DIRS and not e.name.startswith('.')],
            key=lambda e: (not e.is_dir(), e.name.lower()),
        )
    except (PermissionError, OSError):
        return "", 0

    lines = []
    total = 0
    for entry in entries:
        if entry.is_dir():
            total += 1
            lines.append(f"{prefix}📁 {entry.name}/")
            sub_listing, sub_count = _walk_directory(entry, prefix + "  ")
            if sub_listing:
                lines.append(sub_listing)
            total += sub_count
        else:
            total += 1
            lines.append(f"{prefix}📄 {entry.name}")

    return "\n".join(lines), total


class ProjectScanTool(BaseTool):
    """全局扫描目录结构，生成带用途标注的项目概览。"""

    name = "project_scan"
    description = (
        "全局扫描项目目录结构，列出所有文件和子目录，生成文件地图。"
        "仅基于路径和文件名，不读取文件内容。新扫描会覆盖旧的 project_overview.md。"
    )
    parameters = [
        ToolParameter("working_dir", "string", "项目工作目录的绝对路径", required=True),
    ]

    def execute(self, working_dir: str, **kwargs) -> ToolResult:
        wd = Path(working_dir)
        if not wd.exists():
            return ToolResult.fail(f"工作目录不存在: {working_dir}")

        listing, file_count = _walk_directory(wd)
        if not listing.strip():
            return ToolResult.ok(f"目录扫描完成，未发现可扫描的文件/目录（所有内容已被过滤）。", file_count=0)

        _ensure_memory_dir(working_dir)
        overview_path = _get_overview_path(working_dir)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = f"# 项目概览\n> 最后扫描: {now}\n> 文件/目录总数: {file_count}\n\n{listing}\n"

        overview_path.write_text(content, encoding="utf-8")
        return ToolResult.ok(
            f"全局扫描完成，共 {file_count} 个文件/目录。概览已写入 {overview_path}。",
            file_count=file_count,
            overview_path=str(overview_path),
        )


class MemoryReadTool(BaseTool):
    """读取项目记忆。"""

    name = "memory_read"
    description = (
        "读取项目的所有记忆。source='project'（默认）读取项目记忆（project_overview.md + task_history.md），"
        "source='sigma' 读取 Network Bridge 记忆（network_bridge_overview.md + network_bridge_history.md）。"
        "在开始任何涉及项目文件或浏览器自动化的操作前，建议先阅读相关记忆以了解上下文。"
    )
    parameters = [
        ToolParameter("working_dir", "string", "项目工作目录的绝对路径。source='sigma' 时此参数被忽略。", required=True),
        ToolParameter("source", "string", "记忆来源: 'project'(默认) 或 'sigma'", required=False, default="project"),
    ]

    def execute(self, working_dir: str, source: str = "project", **kwargs) -> ToolResult:
        overview_path = _get_overview_path(working_dir, source)
        history_path = _get_history_path(working_dir, source)

        parts = []
        if overview_path.exists():
            parts.append(overview_path.read_text(encoding="utf-8"))
        else:
            label = "Network Bridge 概览" if source == "sigma" else "项目概览"
            parts.append(f"# {label}\n> 尚未初始化。")

        parts.append("")
        if history_path.exists():
            parts.append(history_path.read_text(encoding="utf-8"))
        else:
            label = "Network Bridge 任务记录" if source == "sigma" else "项目任务记录"
            parts.append(f"# {label}\n> 暂无任务记录。")

        return ToolResult.ok("\n".join(parts))


class MemoryRecordTool(BaseTool):
    """追加任务记录。"""

    name = "memory_record"
    description = (
        "追加一条任务记录到记忆。source='project' 写入项目记忆，source='sigma' 写入 Network Bridge 记忆。"
        "仅记录简短的关键信息，包含做了什么。"
        "不是每次对话都需要记录——只在有实质性任务进展时才调用。"
    )
    parameters = [
        ToolParameter("working_dir", "string", "项目工作目录的绝对路径。source='sigma' 时此参数被忽略。", required=True),
        ToolParameter("summary", "string", "任务简述，一句话说明做了什么。", required=True),
        ToolParameter("files", "string", "涉及的关键文件/站点，逗号分隔。如无具体文件可留空。", required=False, default=""),
        ToolParameter("source", "string", "记忆来源: 'project'(默认) 或 'sigma'", required=False, default="project"),
    ]

    def execute(self, working_dir: str, summary: str, files: str = "", source: str = "project", **kwargs) -> ToolResult:
        _ensure_memory_dir(working_dir, source)
        history_path = _get_history_path(working_dir, source)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        today = datetime.now().strftime("%Y-%m-%d")

        # 读取现有内容，判断是否需要插入新的日期分组
        existing = ""
        if history_path.exists():
            existing = history_path.read_text(encoding="utf-8")

        # 构建单条记录
        record = f"- [{now.rsplit(' ', 1)[1]}] {summary}"
        if files.strip():
            record += f" (涉及: {files.strip()})"

        if not existing.strip():
            # 首次记录，创建完整文件
            content = f"# 项目任务记录\n\n## {today}\n{record}\n"
        else:
            # 检查是否已有今天的日期分组
            today_header = f"## {today}"
            if today_header in existing:
                # 在今天的日期分组末尾追加
                lines = existing.split("\n")
                new_lines = []
                inserted = False
                in_today = False
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if line.strip() == today_header:
                        in_today = True
                    elif in_today:
                        if line.strip().startswith("## ") and line.strip() != today_header:
                            # 进入下一个日期分组，在当前日期末尾插入
                            new_lines.insert(i, record)
                            inserted = True
                            in_today = False
                        elif i == len(lines) - 1:
                            # 文件末尾
                            new_lines.append(record)
                            inserted = True
                if not inserted and in_today:
                    # today 是最后一个分组
                    new_lines.append(record)
                content = "\n".join(new_lines)
            else:
                # 在第一个日期分组前插入今天的日期
                parts = existing.split("\n", 2)
                if len(parts) >= 2:
                    content = f"{parts[0]}\n{parts[1]}\n\n## {today}\n{record}\n{parts[2] if len(parts) > 2 else ''}"
                else:
                    content = f"{existing.strip()}\n\n## {today}\n{record}\n"

        history_path.write_text(content, encoding="utf-8")
        return ToolResult.ok(
            f"任务记录已追加到 {history_path}",
            summary=summary,
            files=files.strip(),
        )


class MemoryUpdateTool(BaseTool):
    """更新记忆概览中的某个条目。"""

    name = "memory_update"
    description = (
        "更新概览中的某个条目的标注。source='project' 更新项目概览，source='sigma' 更新 Network Bridge 概览。"
        "当你确认了新信息后，使用此工具更新标注。"
    )
    parameters = [
        ToolParameter("working_dir", "string", "项目工作目录的绝对路径。source='sigma' 时此参数被忽略。", required=True),
        ToolParameter("entry", "string", "概览中的条目名称", required=True),
        ToolParameter("purpose", "string", "该条目的用途描述", required=True),
        ToolParameter("source", "string", "记忆来源: 'project'(默认) 或 'sigma'", required=False, default="project"),
    ]

    def execute(self, working_dir: str, entry: str, purpose: str, source: str = "project", **kwargs) -> ToolResult:
        overview_path = _get_overview_path(working_dir, source)
        if not overview_path.exists():
            return ToolResult.fail(f"项目概览不存在: {overview_path}，请先运行 project_scan")

        content = overview_path.read_text(encoding="utf-8")
        entry_clean = entry.strip()

        # 匹配 📄 filename → ... 或 📁 dirname/ 结尾的行
        # 对于文件: 📄 main.py → [待判断]
        # 对于目录: 📁 src/   (目录没有 → 标注)
        pattern_file = re.compile(
            rf'^(\s*📄 )({re.escape(entry_clean)})(\s*→\s*).*$',
            re.MULTILINE,
        )
        pattern_dir = re.compile(
            rf'^(\s*📁 )({re.escape(entry_clean.rstrip("/"))})/(\s*)$',
            re.MULTILINE,
        )

        new_content = pattern_file.sub(
            rf'\g<1>\g<2>\g<3>{purpose}', content,
        )
        if new_content == content:
            # 尝试目录匹配
            new_content = pattern_dir.sub(
                rf'\g<1>\g<2>/ → {purpose}', content,
            )
            if new_content == content:
                return ToolResult.fail(
                    f"在概览中未找到匹配的条目: '{entry}'。"
                    f"请检查名称是否与概览中的一致（区分大小写）。"
                )

        overview_path.write_text(new_content, encoding="utf-8")
        return ToolResult.ok(
            f"已更新 '{entry}' 的用途标注为: {purpose}",
            entry=entry_clean,
            purpose=purpose,
        )
