"""
batch_read skill - 批量文件读取与分析

取代单独的 read/read_docx/read_pdf/read_xlsx 工具，
所有文件读取统一通过 batch_read → sub_agent 通道，
每个文件由独立子 Agent 读取并返回智能摘要，token 可控。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class BatchReadTool(BaseTool):
    name = "batch_read"
    description = (
        "批量读取多个文件并返回智能摘要。每个文件由独立子 Agent 并行读取分析，"
        "统一返回结果。替代 read/read_docx/read_pdf/read_xlsx。"
        "适用场景：需要阅读 >=2 个文件时优先使用，避免大文件撑爆上下文。"
        "设置 include_content=true 可同时获取摘要和文件原文。"
    )
    parameters = [
        ToolParameter(
            "file_paths",
            "array",
            "要读取的文件路径列表（绝对路径或相对路径）",
        ),
        ToolParameter(
            "purpose",
            "string",
            "读取目的，帮助子 Agent 精准提取关键信息。如：'了解项目入口文件'、'查找数据库配置'、'审查错误处理逻辑'",
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

    def execute(self, file_paths: list, purpose: str, include_content: bool = False, **kwargs) -> ToolResult:
        if not file_paths or not isinstance(file_paths, list):
            return ToolResult.fail("file_paths 必须是非空列表")

        if not self.llm_config.get("api_key"):
            return ToolResult.fail("LLM 配置缺失，无法创建子 Agent。请先配置 API Key。")

        valid_paths = []
        for fp in file_paths:
            resolved = self._resolve_path(fp)
            if resolved.exists() and resolved.is_file():
                valid_paths.append(str(resolved))
            else:
                valid_paths.append(str(resolved))

        if not valid_paths:
            return ToolResult.fail("没有有效的文件路径")

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

        # 通过 SkillManager 调用 sub_agent
        manager = self._skill_manager
        if not manager:
            return ToolResult.fail("SkillManager 不可用")

        sub_agent_inst = manager._instances.get("sub_agent")
        if not sub_agent_inst:
            sub_agent_inst = manager._get_instance("sub_agent")

        # 转发进度回调
        if self._on_progress:
            sub_agent_inst.set_progress_callback(self._on_progress)

        result = sub_agent_inst.execute(tasks=tasks)
        return result
