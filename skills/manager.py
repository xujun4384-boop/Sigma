"""
Skill 管理器：注册、调度、导出 Anthropic tools 格式

两级暴露机制 (用于主程序接入时的 LLM 交互):
  1. get_skill_headers() → 返回所有 skill 的 header (摘要+使用场景, 全量, 不截断)
     → LLM 了解有哪些 skill 可用, 选择需要的 skill
  2. get_skill_spec(name) → 返回选中 skill 的完整 skill.md (含所有参数详情)
     → LLM 知道如何精确填写参数, 避免调用报错
  3. dispatch(tool_name, **kwargs) → 执行具体工具
"""
from pathlib import Path
from typing import Any
import inspect

from skills.base import BaseTool, ToolResult
from skills.file_operations import ReadTool, WriteTool, EditTool, BashTool
from skills.web_search import WebSearchTool
from skills.task_management import TodoWriteTool
from skills.docx_reader import ReadDocxTool
from skills.docx_writer import WriteDocxTool
from skills.docx_editor import EditDocxTool
from skills.docx_analyzer import SearchDocxTool
from skills.image_reader import ImagePreviewTool, ImageReaderTool
from skills.image_search import ImageSearchTool
from skills.image_generate import ImageGenerateTool
from skills.sandbox import SandboxTool
from skills.sub_agent import SubAgentTool
from skills.custom_agent import CustomAgentTool
from skills.todo_manager import TodoManager, current_todo_manager
from skills.read_xlsx import ReadXlsxTool
from skills.edit_xlsx import EditXlsxTool
from skills.write_xlsx import WriteXlsxTool
from skills.pptx import ConvertPptxTool
from skills.get_time import GetCurrentTimeTool
from skills.deep_research import DeepResearchTool
from skills.search_document import SearchDocumentTool
from skills.search_code import SearchCodeTool
from skills.read_pdf import ReadPdfTool
from skills.read_pptx import ReadPptxTool
from skills.longread import LongreadTool
from skills.writing_polish import WritingPolishTool
from skills.ask_user import AskUserTool
from skills.network_bridge import NetworkBridgeTool
from skills.wechat_publisher import WeChatPublisherTool
from skills.project_memory import (
    ProjectScanTool, MemoryReadTool, MemoryRecordTool, MemoryUpdateTool,
)

from skills.batch_read import BatchReadTool
from skills.video_generate import VideoSceneTool, VideoTTSTool, VideoComposeTool
from skills.video_auto import VideoAutoTool
from skills.video_custom import VideoCustomTool
from skills.fengniao import (
    FengniaoFuzzySearch, FengniaoBasicInfo, FengniaoShareholders,
    FengniaoExecutives, FengniaoInvestments, FengniaoChanges,
    FengniaoExecuted, FengniaoDishonest, FengniaoLimitConsumption,
    FengniaoAbnormalOperation, FengniaoSeriousIllegal, FengniaoAdminPenalty,
)
from skills.flyai import (
    FlyAIKeywordSearch, FlyAIAISearch, FlyAISearchFlight, FlyAISearchTrain,
    FlyAISearchHotel, FlyAISearchPOI, FlyAISearchMarriottHotel, FlyAISearchMarriottPackage,
)

# 内部工具：仅供子 Agent 使用，不对外暴露给 LLM（只读工具由 batch_read 统一入口）
_INTERNAL_TOOLS = {"read", "read_docx", "read_pdf", "read_pptx"}

# 所有工具类的注册表
ALL_TOOL_CLASSES: dict[str, type] = {
    "edit": EditTool,
    "bash": BashTool,
    "web_search": WebSearchTool,
    "todo_write": TodoWriteTool,
    "edit_docx": EditDocxTool,
    "search_docx": SearchDocxTool,
    "read_image": ImageReaderTool,
    "preview_image": ImagePreviewTool,
    "search_image": ImageSearchTool,
    "generate_image": ImageGenerateTool,
    "sandbox_run": SandboxTool,
    "sub_agent": SubAgentTool,
    "custom_agent": CustomAgentTool,
    "get_current_time": GetCurrentTimeTool,
    "edit_xlsx": EditXlsxTool,
    "deep_research": DeepResearchTool,
    "search_document": SearchDocumentTool,
    "search_code": SearchCodeTool,
    "longread": LongreadTool,
    "writing_polish": WritingPolishTool,
    "ask_user": AskUserTool,
    "network_bridge": NetworkBridgeTool,
    "project_scan": ProjectScanTool,
    "memory_read": MemoryReadTool,
    "memory_record": MemoryRecordTool,
    "memory_update": MemoryUpdateTool,
    "batch_read": BatchReadTool,
    "video_scene": VideoSceneTool,
    "video_tts": VideoTTSTool,
    "video_compose": VideoComposeTool,
    "video_auto": VideoAutoTool,
    "video_custom": VideoCustomTool,
    "wechat_publish": WeChatPublisherTool,
    "fengniao_search": FengniaoFuzzySearch,
    "fengniao_basic_info": FengniaoBasicInfo,
    "fengniao_shareholders": FengniaoShareholders,
    "fengniao_executives": FengniaoExecutives,
    "fengniao_investments": FengniaoInvestments,
    "fengniao_changes": FengniaoChanges,
    "fengniao_executed": FengniaoExecuted,
    "fengniao_dishonest": FengniaoDishonest,
    "fengniao_limit_consumption": FengniaoLimitConsumption,
    "fengniao_abnormal_operation": FengniaoAbnormalOperation,
    "fengniao_serious_illegal": FengniaoSeriousIllegal,
    "fengniao_admin_penalty": FengniaoAdminPenalty,
    "flyai_keyword_search": FlyAIKeywordSearch,
    "flyai_ai_search": FlyAIAISearch,
    "flyai_search_flight": FlyAISearchFlight,
    "flyai_search_train": FlyAISearchTrain,
    "flyai_search_hotel": FlyAISearchHotel,
    "flyai_search_poi": FlyAISearchPOI,
    "flyai_search_marriott_hotel": FlyAISearchMarriottHotel,
    "flyai_search_marriott_package": FlyAISearchMarriottPackage,
    # 以下为内部工具，仅供子 Agent 使用，不对外暴露
    "read": ReadTool,
    "read_docx": ReadDocxTool,
    "read_pdf": ReadPdfTool,
    "read_pptx": ReadPptxTool,
    "read_xlsx": ReadXlsxTool,
    "write": WriteTool,
    "write_docx": WriteDocxTool,
    "write_xlsx": WriteXlsxTool,
    "convert_pptx": ConvertPptxTool,
}

# Skill → 包含的工具名映射
ALL_SKILLS: dict[str, dict] = {
    "file_operations": {
        "label": "文件操作",
        "tool_names": ["edit", "bash"],
    },
    "web_search": {
        "label": "网页搜索",
        "tool_names": ["web_search"],
    },
    "task_management": {
        "label": "任务管理",
        "tool_names": ["todo_write"],
    },
    "docx_editor": {
        "label": "Word 编辑",
        "tool_names": ["edit_docx"],
    },
    "docx_analyzer": {
        "label": "Word 分析",
        "tool_names": ["search_docx"],
    },
    "image_reader": {
        "label": "图片读取",
        "tool_names": ["preview_image", "read_image"],
    },
    "image_search": {
        "label": "图片搜索",
        "tool_names": ["search_image"],
    },
    "image_generate": {
        "label": "图片生成",
        "tool_names": ["generate_image"],
    },
    "sandbox": {
        "label": "沙箱执行",
        "tool_names": ["sandbox_run"],
    },
    "sub_agent": {
        "label": "子智能体",
        "tool_names": ["sub_agent"],
    },
    "custom_agent": {
        "label": "自定义智能体",
        "tool_names": ["custom_agent"],
    },
    "read_xlsx": {
        "label": "Excel 读取",
        "tool_names": ["read_xlsx"],
    },
    "write_xlsx": {
        "label": "Excel 创建",
        "tool_names": ["write_xlsx"],
    },
    "edit_xlsx": {
        "label": "Excel 编辑",
        "tool_names": ["edit_xlsx"],
    },
    "get_time": {
        "label": "获取当前时间",
        "tool_names": ["get_current_time"],
    },
    "deep_research": {
        "label": "深度研究",
        "tool_names": ["deep_research"],
    },
    "search_document": {
        "label": "文档搜索",
        "tool_names": ["search_document"],
    },
    "search_code": {
        "label": "代码搜索",
        "tool_names": ["search_code"],
    },
    "longread": {
        "label": "长文阅读",
        "tool_names": ["longread"],
    },
    "writing_polish": {
        "label": "写作润色",
        "tool_names": ["writing_polish"],
    },
    "ask_user": {
        "label": "询问用户",
        "tool_names": ["ask_user"],
    },
    "network_bridge": {
        "label": "网络桥接",
        "tool_names": ["network_bridge"],
    },
    "project_memory": {
        "label": "项目记忆",
        "tool_names": ["project_scan", "memory_read", "memory_record", "memory_update"],
    },
    "batch_read": {
        "label": "批量读取",
        "tool_names": ["batch_read"],
    },
    "video_generate": {
        "label": "视频生成",
        "tool_names": ["video_scene", "video_tts", "video_compose"],
    },
    "video_auto": {
        "label": "视频自动生成",
        "tool_names": ["video_auto"],
    },
    "video_custom": {
        "label": "视频自定义生成",
        "tool_names": ["video_custom"],
    },
    "wechat_publisher": {
        "label": "公众号发布",
        "tool_names": ["wechat_publish"],
    },
    "fengniao": {
        "label": "风鸟企业查询",
        "tool_names": [
            "fengniao_search", "fengniao_basic_info", "fengniao_shareholders",
            "fengniao_executives", "fengniao_investments", "fengniao_changes",
            "fengniao_executed", "fengniao_dishonest", "fengniao_limit_consumption",
            "fengniao_abnormal_operation", "fengniao_serious_illegal", "fengniao_admin_penalty",
        ],
    },
    "flyai": {
        "label": "飞猪旅行搜索",
        "tool_names": [
            "flyai_keyword_search", "flyai_ai_search", "flyai_search_flight",
            "flyai_search_train", "flyai_search_hotel", "flyai_search_poi",
            "flyai_search_marriott_hotel", "flyai_search_marriott_package",
        ],
    },
}


class SkillManager:
    def __init__(self, cwd: str = ".", web_search_provider: str = "kimi",
                 web_search_api_key: str = "", web_search_base_url: str = "",
                 tavily_api_key: str = "", image_gen_api_key: str = "",
                 image_gen_base_url: str = "",
                 vision_api_key: str = "", vision_model: str = "",
                 vision_base_url: str = "",
                 wechat_appid: str = "", wechat_appsecret: str = "",
                 wechat_relay_url: str = "", wechat_relay_key: str = "",
                 fengniao_api_key: str = "", flyai_api_key: str = "",
                 llm_config: dict | None = None,
                 todo_manager: TodoManager | None = None,
                 backup_enabled: bool = True,
                 skills_root: str | None = None,
                 enabled_skills: list[str] | None = None):
        self.cwd = Path(cwd)
        self.skills_root = Path(skills_root) if skills_root else Path(__file__).resolve().parent
        self.backup_enabled = backup_enabled
        self.web_search_provider = web_search_provider
        self.web_search_api_key = web_search_api_key
        self.web_search_base_url = web_search_base_url
        self.tavily_api_key = tavily_api_key
        self.image_gen_api_key = image_gen_api_key
        self.image_gen_base_url = image_gen_base_url
        self.vision_api_key = vision_api_key
        self.vision_model = vision_model
        self.vision_base_url = vision_base_url
        self.wechat_appid = wechat_appid
        self.wechat_appsecret = wechat_appsecret
        self.wechat_relay_url = wechat_relay_url
        self.wechat_relay_key = wechat_relay_key
        self.fengniao_api_key = fengniao_api_key
        self.flyai_api_key = flyai_api_key
        self.llm_config = llm_config or {}
        self.todo_manager = todo_manager
        self.sub_agent_max_turns = 8  # 可被 server.py 动态设置
        self._instances: dict[str, BaseTool] = {}
        self._skill_cache: dict[str, str] = {}
        self._header_cache: dict[str, str] = {}

        # 根据 enabled_skills 过滤可用的 tools 和 skills
        if enabled_skills:
            enabled_set = set(enabled_skills)
            self._skills = {
                name: spec for name, spec in ALL_SKILLS.items()
                if name in enabled_set
            }
            enabled_tool_names = set()
            for spec in self._skills.values():
                enabled_tool_names.update(spec.get("tool_names", []))
            # 内部工具始终包含，不因 enabled_skills 过滤而丢失
            self._tool_classes = {
                name: cls for name, cls in ALL_TOOL_CLASSES.items()
                if name in enabled_tool_names or name in _INTERNAL_TOOLS
            }
        else:
            self._skills = dict(ALL_SKILLS)
            self._tool_classes = dict(ALL_TOOL_CLASSES)

    def clear_cache(self):
        """清除所有内部缓存，配合热重载使用。"""
        self._instances.clear()
        self._skill_cache.clear()
        self._header_cache.clear()

    # ─── 工具注册与实例化 ───

    def get_all_tool_names(self) -> list[str]:
        return list(self._tool_classes)

    def get_anthropic_tools(self) -> list[dict]:
        """导出所有工具为 Anthropic tool use 格式（排除内部工具）"""
        tools = []
        for tool_name in self._tool_classes:
            if tool_name in _INTERNAL_TOOLS:
                continue
            inst = self._get_instance(tool_name)
            tools.append(inst.to_anthropic_tool())
        return tools

    def get_openai_tools(self) -> list[dict]:
        """导出所有工具为 OpenAI function calling 格式（排除内部工具）"""
        tools = []
        for tool_name in self._tool_classes:
            if tool_name in _INTERNAL_TOOLS:
                continue
            inst = self._get_instance(tool_name)
            tools.append(inst.to_openai_tool())
        return tools

    def dispatch(self, tool_name: str, **kwargs) -> ToolResult:
        """调度执行工具。执行 todo_write 前自动设置 ContextVar。"""
        # 在执行前将 TodoManager 注入 ContextVar
        if tool_name == "todo_write" and self.todo_manager:
            current_todo_manager.set(self.todo_manager)
        try:
            inst = self._get_instance(tool_name)
            kwargs = self._normalize_tool_input(inst, kwargs)
            ok, msg = inst.validate_input(**kwargs)
            if not ok:
                return ToolResult.fail(f"参数校验失败: {msg}")
            ok, msg = inst.check_permission(**kwargs)
            if not ok:
                return ToolResult.fail(f"权限拒绝: {msg}")
            try:
                return inst.execute(**kwargs)
            except TypeError as e:
                return ToolResult.fail(
                    f"工具参数不兼容: {e}",
                    tool_name=tool_name,
                    accepted_parameters=[p.name for p in inst.parameters],
                    received_parameters=list(kwargs.keys()),
                )
        finally:
            if tool_name == "todo_write":
                current_todo_manager.set(None)

    def _normalize_tool_input(self, inst: BaseTool, kwargs: dict[str, Any]) -> dict[str, Any]:
        """兼容旧 skill/LLM 常见别名，并过滤 execute 不接收的多余字段。"""
        data = dict(kwargs or {})
        param_names = [p.name for p in inst.parameters]
        param_set = set(param_names)

        alias_candidates = {
            "file_path": ["path", "filepath", "file", "filename", "input", "input_path", "output", "output_file"],
            "output_path": ["save_path", "save_as", "output", "target_path", "target"],
            "save_as": ["output_path", "save_path", "output", "target_path", "target"],
            "input_path": ["file_path", "path", "filepath", "file", "source_path"],
            "query": ["keyword", "keywords", "search_query", "q"],
            "keyword": ["query", "search_query", "q", "text"],
            "search_value": ["keyword", "query", "text", "search_query"],
            "topic": ["query", "question", "prompt", "subject"],
            "prompt": ["query", "text", "description"],
            "content": ["text", "body", "markdown"],
            "text": ["content", "input", "body"],
            "sheets": ["worksheets", "sheet_data", "data"],
            "sheet_name": ["sheet", "worksheet", "tab"],
            "modifications": ["operations", "edits", "changes", "actions"],
            "edit_instructions": ["instructions", "edits", "changes", "operations", "modifications"],
            "tasks": ["task", "prompts", "agents"],
            "todos": ["todo", "items", "tasks"],
            "page_range": ["pages", "range"],
            "extended_keywords": ["expanded_keywords", "synonyms", "related_keywords"],
            "max_results": ["limit", "count", "num_results", "max_images"],
            "max_images": ["max_results", "limit", "count", "num_results"],
            "save_dir": ["output_dir", "target_dir", "folder", "directory", "dir"],
            "output_dir": ["save_dir", "target_dir", "folder", "directory", "dir"],
            "target_project_folder": ["project_folder", "output_dir", "save_dir", "target_dir", "folder", "directory"],
            "resize_to": ["size", "target_size", "dimensions"],
            "quality": ["jpeg_quality", "image_quality"],
            "search_depth": ["depth"],
            "watermark": ["with_watermark"],
            "limit": ["max_results", "count", "num_results"],
        }
        for canonical, aliases in alias_candidates.items():
            if canonical in param_set and canonical not in data:
                for alias in aliases:
                    if alias in data:
                        data[canonical] = data[alias]
                        break

        for param in inst.parameters:
            if param.name not in data and param.default is not None:
                data[param.name] = param.default

        try:
            sig = inspect.signature(inst.execute)
            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if accepts_kwargs:
                return data
            accepted = {name for name in sig.parameters if name != "self"}
            return {k: v for k, v in data.items() if k in accepted}
        except (TypeError, ValueError):
            return {k: v for k, v in data.items() if k in param_set}

    def _get_instance(self, tool_name: str) -> BaseTool:
        """惰性实例化工具"""
        if tool_name not in self._instances:
            cls = self._tool_classes.get(tool_name)
            if cls is None:
                raise ValueError(f"未知工具: {tool_name}")
            if tool_name == "web_search":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    provider=self.web_search_provider,
                    api_key=self.web_search_api_key,
                    custom_base_url=self.web_search_base_url,
                )
            elif tool_name == "search_image":
                self._instances[tool_name] = cls(cwd=str(self.cwd), tavily_api_key=self.tavily_api_key)
            elif tool_name == "generate_image":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.image_gen_api_key,
                    base_url=self.image_gen_base_url,
                )
            elif tool_name == "sub_agent":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "custom_agent":
                from custom_agent_manager import custom_agent_manager
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    skill_manager=self,
                    agent_manager=custom_agent_manager,
                )
            elif tool_name == "read_pdf":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    vision_api_key=self.vision_api_key,
                    vision_model=self.vision_model,
                    vision_base_url=self.vision_base_url,
                )
            elif tool_name == "read_image":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    vision_api_key=self.vision_api_key,
                    vision_model=self.vision_model,
                    vision_base_url=self.vision_base_url,
                )
            elif tool_name == "preview_image":
                self._instances[tool_name] = cls(cwd=str(self.cwd))
            elif tool_name == "edit_docx":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    backup_enabled=self.backup_enabled,
                )
            elif tool_name == "batch_read":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "write_docx":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "video_auto":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    llm_config=self.llm_config,
                    skill_manager=self,
                )
            elif tool_name == "wechat_publish":
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    appid=self.wechat_appid,
                    appsecret=self.wechat_appsecret,
                    relay_url=self.wechat_relay_url,
                    relay_key=self.wechat_relay_key,
                )
            elif tool_name in (
                "fengniao_search", "fengniao_basic_info", "fengniao_shareholders",
                "fengniao_executives", "fengniao_investments", "fengniao_changes",
                "fengniao_executed", "fengniao_dishonest", "fengniao_limit_consumption",
                "fengniao_abnormal_operation", "fengniao_serious_illegal", "fengniao_admin_penalty",
            ):
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.fengniao_api_key,
                )
            elif tool_name in (
                "flyai_keyword_search", "flyai_ai_search", "flyai_search_flight",
                "flyai_search_train", "flyai_search_hotel", "flyai_search_poi",
                "flyai_search_marriott_hotel", "flyai_search_marriott_package",
            ):
                self._instances[tool_name] = cls(
                    cwd=str(self.cwd),
                    api_key=self.flyai_api_key,
                )
            else:
                self._instances[tool_name] = cls(cwd=str(self.cwd))
        return self._instances[tool_name]

    # ─── 两级暴露机制 ───

    def _read_skill_md(self, skill_name: str) -> str | None:
        """读取 skill.md 文件内容。"""
        if skill_name in self._skill_cache:
            return self._skill_cache[skill_name]

        candidates = [
            self.skills_root / skill_name / "skill.md",
            self.skills_root / skill_name / "SKILL.md",
            self.cwd / "skills" / skill_name / "skill.md",
            self.cwd / "skills" / skill_name / "SKILL.md",
        ]
        for path in candidates:
            if path.exists():
                text = path.read_text(encoding="utf-8")
                self._skill_cache[skill_name] = text
                return text
        return None

    def _parse_header(self, text: str) -> str:
        """截取 skill.md 的 header 部分：标题 + 摘要 + 使用场景（到 ═══ 分隔线之前）。"""
        lines = text.split("\n")
        header_lines = []
        found_title = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and not found_title:
                found_title = True
                header_lines.append(line)
                continue
            if found_title:
                # 遇到 ## 二级标题或 ═══ 参数分隔线则停止
                if stripped.startswith("## ") or "\u2550" in stripped:
                    break
                header_lines.append(line)
        if not found_title:
            return "\n".join(lines[:20])
        return "\n".join(header_lines)

    def get_skill_headers(self) -> dict[str, str]:
        """一级暴露：返回所有 skill 的 header 摘要，供 LLM 选择。"""
        headers: dict[str, str] = {}
        for skill_name in self._skills:
            text = self._read_skill_md(skill_name)
            if text is None:
                continue
            if skill_name not in self._header_cache:
                self._header_cache[skill_name] = self._parse_header(text)
            headers[skill_name] = self._header_cache[skill_name]
        return headers

    def get_skill_spec(self, skill_name: str) -> str | None:
        """二级暴露：返回指定 skill 的完整 skill.md 内容，含所有参数详情。"""
        if skill_name not in self._skills:
            return None
        return self._read_skill_md(skill_name)

    def get_skill_specs_for_tool(self, tool_name: str) -> str | None:
        """根据工具名找到所属 skill，返回完整 skill.md。"""
        for skill_name, spec in self._skills.items():
            if tool_name in spec["tool_names"]:
                return self._read_skill_md(skill_name)
        return None
