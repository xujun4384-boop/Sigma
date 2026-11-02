"""
batch_read skill - 批量文件读取与分析

取代单独的 read/read_docx/read_pdf/read_xlsx 工具，
所有文件读取统一通过 batch_read → sub_agent 通道，
每个文件由独立子 Agent 读取并返回智能摘要，token 可控。
"""
import os
from collections import deque
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class BatchReadTool(BaseTool):
    name = "batch_read"
    description = (
        "批量读取多个文件并返回智能摘要。每个文件由独立子 Agent 并行读取分析，"
        "统一返回结果。替代 read/read_docx/read_pdf/read_xlsx。"
        "适用场景：需要阅读 >=2 个文件时优先使用，避免大文件撑爆上下文。"
        "file_paths 可以传文件，也可以直接传目录：目录会自动展开为其中的文件"
        "（每个目录最多 20 个，单次最多 30 个）。"
        "设置 include_content=true 可同时获取摘要和文件原文。"
    )
    # 目录展开上限：每个目录最多取多少个文件（每个文件都会启动一个子 Agent）
    MAX_DIR_FILES = 20
    # 单次调用最多读取的文件数（防止传多个目录时子 Agent 数量失控）
    MAX_TOTAL_FILES = 30
    # 展开目录时跳过的依赖/缓存目录
    SKIP_DIR_NAMES = {
        ".git", ".svn", ".hg", "node_modules", "__pycache__",
        ".venv", "venv", "env", ".idea", ".vscode", ".next", ".cache",
    }
    EMPTY_PATHS_HINT = (
        "file_paths 为空，无法读取。请先确定要读哪些文件：\n"
        "1) 已知具体文件：传文件路径（绝对路径或相对当前工作目录的路径）；\n"
        f"2) 只知道目录：直接把目录路径传进来，会自动展开目录下的文件（最多 {MAX_DIR_FILES} 个）；\n"
        "3) 不知道文件在哪：先调用 project_scan / memory_read 查看项目结构，"
        "或用 search_code / search_document 定位后再读。\n"
        "不要传空数组。"
    )
    parameters = [
        ToolParameter(
            "file_paths",
            "array",
            f"要读取的文件或目录路径列表（绝对路径或相对路径）。传目录时会自动展开其中的文件（最多 {MAX_DIR_FILES} 个）",
        ),
        ToolParameter(
            "purpose",
            "string",
            "读取目的，帮助子 Agent 精准提取关键信息。如：'了解项目入口文件'、'查找数据库配置'、'审查错误处理逻辑'",
            required=False,
            default="了解文件内容并总结关键信息",
        ),
        ToolParameter(
            "include_content",
            "boolean",
            "是否在结果中包含文件原文。true 时子 Agent 同时返回摘要和原文（或关键段落），false 时仅返回摘要。默认 false。",
        ),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict | None = None, skill_manager=None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self._skill_manager = skill_manager
        self._on_progress = None

    def set_progress_callback(self, callback):
        """设置进度回调，转发给子 Agent 以实现前端实时显示"""
        self._on_progress = callback

    def _expand_dir(self, root: Path) -> list[Path]:
        """广度优先展开目录（浅层文件优先），跳过依赖/缓存目录，最多取 MAX_DIR_FILES 个文件。"""
        files: list[Path] = []
        queue = deque([root])
        while queue and len(files) < self.MAX_DIR_FILES:
            current = queue.popleft()
            try:
                entries = sorted(current.iterdir())
            except OSError:
                continue
            subdirs = []
            for entry in entries:
                try:
                    if entry.is_dir():
                        if entry.name not in self.SKIP_DIR_NAMES and not entry.name.startswith("."):
                            subdirs.append(entry)
                    elif entry.is_file() and len(files) < self.MAX_DIR_FILES:
                        files.append(entry)
                except OSError:
                    continue
            queue.extend(subdirs)
        return files

    def execute(self, file_paths: list, purpose: str = "", include_content: bool = False, **kwargs) -> ToolResult:
        # purpose 是引导性子 Agent 的提取目标，缺失时用中性默认值，不因此拒绝整次读取
        purpose = (purpose or "").strip() or "了解文件内容并总结关键信息"

        # 兼容模型把单一路径写成字符串的情况
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        # 过滤空字符串，避免空路径被解析成工作目录而被整目录展开
        if isinstance(file_paths, list):
            file_paths = [str(p).strip() for p in file_paths if str(p).strip()]

        if not file_paths or not isinstance(file_paths, list):
            return ToolResult.fail(self.EMPTY_PATHS_HINT, error_kind="validation")

        if not self.llm_config.get("api_key"):
            return ToolResult.fail("LLM 配置缺失，无法创建子 Agent。请先配置 API Key。")

        valid_paths: list[str] = []
        missing: list[str] = []
        notes: list[str] = []
        seen: set[str] = set()
        limit_hit = False

        def _add(path: Path) -> bool:
            """去重并加入待读列表；超过总上限时返回 False。"""
            key = str(path)
            if key in seen:
                return True
            if len(valid_paths) >= self.MAX_TOTAL_FILES:
                return False
            seen.add(key)
            valid_paths.append(key)
            return True

        for fp in file_paths:
            resolved = self._resolve_path(fp)
            if resolved.is_dir():
                before = len(valid_paths)
                expanded = self._expand_dir(resolved)
                for item in expanded:
                    if not _add(item):
                        limit_hit = True
                        break
                added = len(valid_paths) - before
                if not expanded:
                    notes.append(f"目录为空或没有可读取的文件: {resolved}")
                elif added < len(expanded):
                    notes.append(f"目录已展开: {resolved} → 加入 {added}/{len(expanded)} 个文件（受单次上限限制）")
                else:
                    notes.append(f"目录已展开: {resolved} → {added} 个文件")
                if len(expanded) >= self.MAX_DIR_FILES:
                    notes.append(f"注意：该目录文件较多，仅取前 {self.MAX_DIR_FILES} 个")
            elif resolved.is_file():
                if not _add(resolved):
                    limit_hit = True
            else:
                missing.append(str(resolved))

        if limit_hit:
            notes.append(f"注意：单次最多读取 {self.MAX_TOTAL_FILES} 个文件，其余已跳过")

        if not valid_paths:
            detail = "\n".join(f"- {p}" for p in (missing or [str(fp) for fp in file_paths])[:20])
            return ToolResult.fail(
                "没有找到可读取的文件：\n"
                f"{detail}\n"
                "请检查路径是否正确；目录会自动展开，不存在的路径无法读取。"
            )

        if missing:
            notes.append("以下路径不存在，已跳过: " + ", ".join(missing[:10]))

        self._emit_progress(f"准备读取 {len(valid_paths)} 个文件...")

        # 根据 include_content 构建不同的 prompt
        if include_content:
            read_prompt = (
                f"阅读文件: {{fp}}\n\n"
                f"读取目的: {{purpose}}\n\n"
                f"请读取该文件的完整内容，然后按以下格式返回：\n"
                f"1. 【摘要】先提供一份简洁摘要（不超过 200 字），重点说明与目的相关的部分\n"
                f"2. 【原文】然后返回文件完整原文（用 ``` 代码块包裹）\n"
                f"如果文件过大，返回与目的最相关的关键段落原文（标注行号范围，如 L10-L50）\n"
                f"如果文件内容完全无关，直接说'无关'即可。\n"
                f"不要修改文件。"
            )
        else:
            read_prompt = (
                f"阅读文件: {{fp}}\n\n"
                f"读取目的: {{purpose}}\n\n"
                f"请读取该文件的完整内容，然后提供一份简洁的摘要（不超过 400 字），"
                f"重点说明文件中与上述目的相关的部分。"
                f"如果文件内容完全无关，直接说'无关'即可。"
                f"不要修改文件。"
            )

        # 构建子 Agent 任务列表
        tasks = []
        for i, fp in enumerate(valid_paths):
            fname = Path(fp).name
            tasks.append({
                "type": "explore",
                "description": fname,
                "prompt": read_prompt.replace("{fp}", fp).replace("{purpose}", purpose),
                "allowed_tools": ["read", "read_docx", "read_pdf", "read_xlsx", "read_image", "read_pptx"],
            })

        self._emit_progress(f"已创建 {len(tasks)} 个并行读取任务，正在分析...")

        # 通过 SkillManager 调用 sub_agent
        manager = self._skill_manager
        if not manager:
            return ToolResult.fail("SkillManager 不可用")

        sub_agent_inst = manager._instances.get("sub_agent")
        if not sub_agent_inst:
            sub_agent_inst = manager._get_instance("sub_agent")

        # 转发进度回调：sub_agent 的事件桥接为 tool_progress，在 batch_read 卡片中显示
        if self._on_progress:
            original_cb = self._on_progress

            def _bridge_progress(event):
                # 桥接 sub_agent 事件为 batch_read 的 tool_progress
                etype = event.get("type", "")
                desc = event.get("description", "")
                if etype == "subagent_start":
                    original_cb({"type": "tool_progress", "tool_name": "batch_read",
                                 "content": f"开始读取: {desc}"})
                elif etype == "subagent_progress":
                    turn = event.get("turn", 0)
                    status = event.get("status", "")
                    original_cb({"type": "tool_progress", "tool_name": "batch_read",
                                 "content": f"[{desc}] 第{turn}轮 {status}..."})
                elif etype == "subagent_result":
                    success = event.get("success", False)
                    status = "✓" if success else "✗"
                    original_cb({"type": "tool_progress", "tool_name": "batch_read",
                                 "content": f"{status} {desc}"})
                # 其他事件透传
                else:
                    original_cb(event)

            sub_agent_inst.set_progress_callback(_bridge_progress)

        result = sub_agent_inst.execute(tasks=tasks)
        self._emit_progress(f"全部 {len(valid_paths)} 个文件读取完成")
        if notes:
            result.content = "；".join(notes) + "\n\n" + result.content
        return result
