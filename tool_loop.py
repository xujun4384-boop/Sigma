"""
Anthropic Tool Use 循环
处理 LLM 与工具之间的多轮交互，支持流式 SSE 输出
支持 LLM 自主规划并行工具调用
支持 TodoList 上下文注入与进度推送
支持上下文压缩与用量追踪
支持文件修改实时 diff 展示
支持 ask_user 中断等待用户输入

两级 Skill 暴露：
  1. system prompt → 只放 header（摘要 + 触发条件），轻量
  2. 首次调用某 skill 的工具 → 完整 skill.md 缓存到 system prompt（不被压缩）
"""
import json
import os
import re
import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from skills.manager import SkillManager, ALL_SKILLS, _norm_path
from skills.project_memory import _get_overview_path, _get_history_path
from skills.todo_manager import TodoManager
from custom_agent_manager import custom_agent_manager, is_agent_tool
from context_manager import (
    ContextTracker, SessionState, CompactResult,
    estimate_tokens, compact_if_needed,
    apply_model_specific_params, resolve_effective_protocol, keep_thinking_history,
    CHARS_PER_TOKEN,
)
from model_presets import find_preset
from file_diff_tracker import file_diff_tracker, _diff_has_changes
from sigma_logger import log

# session_id -> asyncio.Future (用于 ask_user 等待用户回答)
_pending_questionnaires: dict[str, asyncio.Future] = {}

# request_id -> asyncio.Task (问卷重传任务，确保前端一定收到)
_questionnaire_retransmit_tasks: dict[str, asyncio.Task] = {}


def _cancel_questionnaire_retransmit(request_id: str):
    """用户回答后取消问卷重传。"""
    task = _questionnaire_retransmit_tasks.pop(request_id, None)
    if task and not task.done():
        task.cancel()

# request_id -> asyncio.Future (用于 tool_timeout 等待用户选择)
_pending_tool_timeouts: dict[str, asyncio.Future] = {}

# 长任务视频工具：不设超时，一直跑到完成（避免没做完就被判超时/跳过）。
# 覆盖：影视级生成、HTML 动画、水彩逐帧渲染、合成（含规格归一化重编码）。
_NO_TIMEOUT_TOOLS = {
    "director",
    "video_cinematic_generate",
    "opendesign_video",
    "manim_video",
    "blender_video",
    "compose_video",
    "lyric_mv",
}


def resolve_tool_timeout(request_id: str, choice: str) -> bool:
    """由 server.py 调用，解析 tool_timeout 的用户选择"""
    future = _pending_tool_timeouts.pop(request_id, None)
    if future and not future.done():
        future.set_result(choice)
        return True
    return False


def resolve_questionnaire(session_id: str, answers: list[dict]) -> bool:
    """由 server.py 的 /api/user-answer 调用，解析等待中的问卷"""
    future = _pending_questionnaires.pop(session_id, None)
    if future and not future.done():
        future.set_result(answers)
        _cancel_questionnaire_retransmit(session_id)  # 安全取消重传
        return True
    return False


# 文本字段候选键：不同模型会用不同命名承载同一语义，在边界处统一取用。
_TEXT_KEYS = (
    "text", "label", "value", "title", "content",
    "question", "prompt", "name", "description", "desc",
)
# 集合容器候选键：分别用于从包裹对象中取出问题列表、选项列表。
_QUESTION_COLLECTION_KEYS = ("questions", "question_list", "questions_list", "items", "list", "data")
_OPTION_COLLECTION_KEYS = ("items", "item", "options", "choices", "values", "list", "data")

# 题型别名 -> 前端契约值。仅用于把外部输入的同义写法收敛到固定契约，
# 属于系统边界归一化，不参与任何打分或匹配决策。
_QUESTION_TYPE_ALIASES = {
    "single_choice": "single_choice", "single": "single_choice", "singlechoice": "single_choice",
    "single_select": "single_choice", "single-select": "single_choice", "radio": "single_choice",
    "choice": "single_choice", "select": "single_choice", "one": "single_choice",
    "单选": "single_choice", "单选题": "single_choice",
    "multi_choice": "multi_choice", "multiple_choice": "multi_choice", "multichoice": "multi_choice",
    "multi": "multi_choice", "multiple": "multi_choice", "multi_select": "multi_choice",
    "multi-select": "multi_choice", "checkbox": "multi_choice", "checkboxes": "multi_choice",
    "多选": "multi_choice", "多选题": "multi_choice",
    "open": "open", "text": "open", "input": "open", "textarea": "open", "free": "open",
    "freeform": "open", "free_text": "open", "open_ended": "open",
    "开放": "open", "问答": "open", "填空": "open",
}


def _load_json_like(value):
    """尝试把 JSON 字符串（含 ``` 代码围栏）解析为 Python 对象；失败则原样返回。

    某些模型/网关会把嵌套的数组或对象参数序列化成字符串再塞进 arguments，
    这里在边界处统一还原，避免把合法输入判为非法。"""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return value


def _questionnaire_text(value, field: str) -> str | None:
    """将 LLM 输出的文本值规范为前端可直接渲染的字符串。"""
    value = _load_json_like(value)
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        for key in _TEXT_KEYS:
            text = _questionnaire_text(value.get(key), field)
            if text:
                return text
    return None


def _questionnaire_options(value) -> list[str] | None:
    """从直接数组、JSON 字符串、包裹对象或映射中提取选择项，规范为字符串数组。"""
    value = _load_json_like(value)
    if isinstance(value, dict):
        for key in _OPTION_COLLECTION_KEYS:
            if key in value:
                picked = _questionnaire_options(value[key])
                if picked:
                    return picked
        # 形如 {"选项A": "说明", "选项B": "说明"} 的映射：取键作文本项
        if value and all(
            isinstance(v, (str, int, float)) and not isinstance(v, bool)
            for v in value.values()
        ):
            return [str(k) for k in value]
        # 单个选项对象：{"text": "..."} / {"label": "..."}
        single = _questionnaire_text(value, "option")
        return [single] if single else None
    if not isinstance(value, list):
        return None
    # 单层嵌套列表 [[...]] 展平
    if len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    options = [_questionnaire_text(option, "option") for option in value]
    options = [option for option in options if option is not None]
    return options or None


def _normalize_question_type(value, has_options: bool) -> str:
    """将题型写法归一化到契约枚举；无法识别时按有无选项推断，避免整体失败。"""
    text = _questionnaire_text(value, "type")
    if text:
        key = text.strip().lower().replace(" ", "_")
        if key in _QUESTION_TYPE_ALIASES:
            return _QUESTION_TYPE_ALIASES[key]
    return "single_choice" if has_options else "open"


def _coerce_question_list(value) -> list:
    """把 questions 的多种形态收敛为问题对象列表。

    兼容：JSON 字符串 / 包裹对象（含 questions、items 等键）/ 单个问题对象 / 数组。"""
    value = _load_json_like(value)
    if isinstance(value, dict):
        for key in _QUESTION_COLLECTION_KEYS:
            if key in value:
                nested = _coerce_question_list(value[key])
                if nested:
                    return nested
        # 看起来像一个问题对象时包成单元素列表
        if any(k in value for k in ("text", "question", "title", "type", "options", "id")):
            return [value]
        return []
    if isinstance(value, list):
        if len(value) == 1 and isinstance(value[0], list):
            value = value[0]
        return [item for item in value if isinstance(item, (dict, str))]
    return []


def _normalize_questionnaire(tool_input) -> tuple[dict | None, str | None]:
    """将不同模型的 ask_user 参数宽容地收敛为固定的前端问卷契约。

    只做边界归一化，尽量不因模型的表述差异而拒绝：questions 允许 JSON 字符串、
    包裹对象或单问题对象；题型允许同义写法；选项允许字符串/映射；id 缺失自动生成。
    """
    tool_input = _load_json_like(tool_input)
    if not isinstance(tool_input, dict):
        return None, "工具输入必须是对象"

    raw_title = _questionnaire_text(tool_input.get("title"), "title")
    title = raw_title or "请回答以下问题"

    raw_questions = tool_input.get("questions")
    if raw_questions is None:
        for key in ("question", "items", "list", "questions_list"):
            if key in tool_input:
                raw_questions = tool_input[key]
                break
    raw_list = _coerce_question_list(raw_questions)

    questions = []
    for index, raw_question in enumerate(raw_list, start=1):
        if isinstance(raw_question, str):
            raw_question = {"text": raw_question}
        text = None
        for key in ("text", "question", "title", "label", "content", "prompt", "description", "desc"):
            text = _questionnaire_text(raw_question.get(key), "text")
            if text:
                break
        if not text:
            continue  # 无题干的问题无法渲染，跳过而非整体失败

        question_id = _questionnaire_text(raw_question.get("id"), "id") or f"q{index}"
        raw_options = raw_question.get("options")
        options = _questionnaire_options(raw_options) if raw_options is not None else None
        question_type = _normalize_question_type(raw_question.get("type"), bool(options))

        question = {
            "id": question_id,
            "text": text,
            "type": question_type,
            "required": raw_question.get("required") is not False,
        }
        if question_type != "open":
            if not options:
                # 选择题却没给出可用选项：降级为开放问答，保证一定能渲染
                question["type"] = "open"
            else:
                question["options"] = options
        questions.append(question)

    if not questions:
        # 兜底：模型给出标题却没有可渲染的问题（如 questions 为空）时，
        # 用标题作为单个开放问题，保证问卷能渲染、任务能继续，而不是直接中断。
        if raw_title:
            questions.append({"id": "q1", "text": raw_title, "type": "open", "required": True})
        else:
            return None, "questions 未包含任何可渲染的问题"
    return {"title": title, "questions": questions}, None


# 语言指令映射：根据前端语言设置注入，统一 LLM 的思考、工具调用与回复语言
_LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "zh": (
        "## 语言要求（必须遵守）\n"
        "全程使用简体中文进行思考、调用工具（包括工具参数中的文本内容）以及向用户回复。"
        "除非用户明确要求其他语言，否则不要输出英文。\n"
    ),
    "en": (
        "## Language Requirement (Mandatory)\n"
        "Always think, call tools (including text in tool arguments), and respond to the user in English. "
        "Do not output Chinese unless the user explicitly requests another language.\n"
    ),
}


class ToolLoop:
    """Anthropic tool use 循环引擎，支持并行工具执行、TodoList 追踪、上下文压缩"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        skill_manager: SkillManager,
        max_iterations: int = 10,
        todo_manager: TodoManager | None = None,
        session_state: SessionState | None = None,
        context_tracker: ContextTracker | None = None,
        session_id: str = "default",
        tool_timeout: int = 300,
        protocol: str = "anthropic",
        language: str = "zh",
        llm_params: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.language = language
        self.llm_params = llm_params or {}
        # 端点不支持当前思考档位时自动切到能生效的协议（如 Kimi Code 的 Anthropic 端点控制不了档位）。
        # 只在精确命中 provider + protocol + 档位时切换，其他组合保持原协议。
        self.provider = self.llm_params.get("provider", "generic")
        protocol = resolve_effective_protocol(
            self.provider,
            protocol,
            self.llm_params.get("thinking", "default"),
            self.model,
        )
        self.protocol = protocol
        # 是否把思考内容随 assistant 历史回传（由模型家族声明）
        self._keep_thinking_history = keep_thinking_history(self.provider, self.model)
        # 输出上限默认值由模型预设给出，避免各协议各写一套
        preset = find_preset(self.provider, self.model)
        self._default_max_tokens = preset.recommended_max_tokens if preset else 16384
        self.skill_manager = skill_manager
        self.max_iterations = max_iterations
        self.todo_manager = todo_manager
        self.sigma_root = Path(__file__).resolve().parent
        self.project_root = (
            Path(skill_manager.cwd).resolve()
            if skill_manager and str(skill_manager.cwd) not in ("", ".")
            else None
        )
        if protocol == "openai":
            self.messages_url = (
                f"{self.base_url}/chat/completions" if "/v1" in self.base_url
                else f"{self.base_url}/v1/chat/completions"
            )
        else:
            self.messages_url = (
                f"{self.base_url}/messages" if "/v1" in self.base_url
                else f"{self.base_url}/v1/messages"
            )
        self.session_id = session_id
        self.tool_timeout = tool_timeout  # 工具执行超时秒数，默认 300s

        # Session 持久化状态（跨重启保持 skill 缓存）
        self.session_state = session_state or SessionState()

        # 上下文追踪器
        self.context_tracker = context_tracker or ContextTracker(model)

        # 一级: 只放 header（轻量）
        self._base_system_prompt = self._build_system_prompt()
        # 压缩后的历史摘要（从 SessionState 恢复）
        self._history_summary: str = self.session_state.history_summary if self.session_state else ""
        # 当前对话的完整消息列表（跨请求保持）
        self.messages: list[dict] = []

        # 工具执行线程池
        self._executor = ThreadPoolExecutor(max_workers=4)
        # 后台运行的工具: bg_id -> {future, tool_name, tool_input, started_at}
        self._background_futures: dict[str, dict] = {}
        # 连续相同错误跟踪
        self._consecutive_error_count: int = 0
        self._last_consecutive_error: str | None = None

    @property
    def system_prompt(self) -> str:
        """完整的 system prompt = 基础 + 历史摘要 + 已激活 skill 文档"""
        parts = [self._base_system_prompt]
        if self._history_summary:
            parts.append(f"\n\n--- 此前对话摘要 ---\n{self._history_summary}")
        if self.session_state.skill_specs_cache:
            parts.append(self.session_state.skill_specs_cache)
        return "".join(parts)

    def _build_system_prompt(self) -> str:
        """一级暴露：只注入 skill headers（摘要 + 触发条件），不含参数详情"""
        headers = self.skill_manager.get_skill_headers()

        # 注入自定义 Agent 列表（放在最顶部，确保不被稀释）
        agent_list_text = custom_agent_manager.list_for_llm()

        prompt = ""

        # Agent 优先调用提示 —— 永远在提示词最头部
        if agent_list_text:
            prompt += (
                "## 自定义智能体（优先使用）\n\n"
                "你有专属自定义智能体可以代为处理特定类型的任务。\n"
                "当用户请求明显适合某个智能体时，必须优先调用对应的 Agent 专属工具（agent_ 前缀），\n"
                "把完整任务交给该智能体独立完成，它会用专属工具和提示词处理并把结果返回给你。\n"
                "这可以节省你的上下文和轮次，请不要自己处理这些任务。\n\n"
            )
            prompt += agent_list_text
            prompt += "\n\n"
            prompt += (
                "Agent 结果处理规则（重要）：\n"
                "- 当规划类 Agent 返回结构化的执行计划（步骤/阶段列表）时，你**必须**调用 todo_write\n"
                "  将其计划内容转为结构化的 TodoList（merge=false 新建），再向用户汇报。\n"
                "- 不要在回复文本中只展示 Agent 返回的 Markdown 计划来代替 TodoList。\n"
                "- TodoList 是你与用户之间的进度契约，用户需要通过它追踪执行状态。\n\n"
            )
            prompt += "─── 以下为通用工具和策略 ───\n\n"

        prompt += "你是 Sigma，一个拥有文件系统操作和联网搜索能力的 AI 助手。\n\n"

        lang_instruction = _LANGUAGE_INSTRUCTIONS.get(self.language)
        if lang_instruction:
            prompt += lang_instruction + "\n"

        prompt += (
            "## 目录边界（必须遵守）\n\n"
            f"- Sigma 本体目录：`{self.sigma_root}`。这里存放 Sigma 自身的后端代码、前端代码、`skills/`、`sigma.config.json` 等运行与配置文件。\n"
            f"- 当前项目目录：`{self.project_root}`。这是用户当前打开的项目，文件工具传入相对路径时默认以此目录为基准。\n"
            "- 用户询问 Sigma 本身的实现、内置 Skill、应用配置、后端或前端代码时，必须在 Sigma 本体目录中查找，并传入上述绝对路径；不要在当前项目目录中猜测或搜索。\n"
            "- 用户询问当前项目的代码、资源或配置时，才在当前项目目录中查找；相对路径仅用于当前项目文件。\n"
            "- 无法判断目标属于哪一类时，先向用户澄清，或分别检查两个明确目录后说明结果。\n\n"
        )

        prompt += self._build_memory_hint()

        prompt += (
            "## 视频制作（重要）\n\n"
            "- **凡是要「做视频 / 生成动画短片 / 出成片」的需求，统一调用 `director`（导演组）**，由它编排各部门；"
            "不要自己手写动画脚本，也不要尝试绕过导演直接控制画面引擎。\n"
            "- 导演首轮返回「制作蓝图 + need_confirm」：你必须用 `ask_user` 把蓝图给用户确认；确认后带 `plan` 再调 `director` 执行。\n"
            "- 导演自带断点续做：若上次中断/程序关闭，用同一 `project` 再次调用 `director` 即从断点继续，不要重头重排。\n"
            "- **微调/改几处：必须用 `director(project=\"同名\", patch=\"<只写改动项>\")`，绝不要重发整份 plan**"
            "（重发整份 plan 会因措辞/时长微差触发全片重渲——那不是微调，是重做）。patch 只写要改的那个别分镜字段。\n"
            "- 仅当用户明确要求「只做旁白 / 只做字幕」时，才直接调用 `narration` / `subtitle`；合成一般由导演调度。\n"
            "- **严禁把任何文件写入 Sigma 本体目录**（尤其 `skills/**/engine/`）；一切中间产物与成片都放当前项目目录。\n\n"
        )

        if headers:
            prompt += "可用技能：\n\n"
            for skill_name, header in headers.items():
                prompt += f"{header}\n\n"

        prompt += (
            "工具调用策略：\n"
            "- 如果有多个互相独立的操作，请在同一轮中一次性发出，它们会并行执行\n"
            "- 如果某些操作依赖前一个操作的结果，则分步进行\n"
            "- 目标是减少不必要的轮次，提升执行效率\n\n"
            "文件读取（重要）：\n"
            "- 文本/代码/文档/PDF/表格等文件一律用 batch_read，不要逐个调用 read\n"
            "- 即使只读 1 个文件也优先用 batch_read（设置 purpose 可获得精准摘要）\n"
            "- 图片文件（.png/.jpg/.jpeg/.webp/.gif/.bmp）直接用 read_image 读取，"
            "不要用 batch_read 绕一层，也不要用 read 去读图片\n"
            "- read_image 默认返回简要概述（最快）；需要逐字提取文字/表格/票据时用 image_quality=high "
            "或在 prompt 里明确要求，否则不要让它做详细转写\n"
            "- read_image 的 image_quality：文字/表格/票据用 high，一般理解用 balanced，快速预览用 low\n\n"
            "文件写入（重要）：\n"
            "- Word 文档：直接用 write_docx 工具，传 output_path + doc_type + outline（大纲/指令）\n"
            "  · write_docx 内置子 Agent 会独立生成完整文档，不占用主对话 token\n"
            "- 代码/文本文件：用 write 工具，传 file_path + content\n"
            "- 修改现有文件：用 edit 批量模式（edits [{old_str, new_str}, ...]），同一文件多处修改一次完成，不要多次调用 edit\n"
            "- Excel 表格：用 write_xlsx，content 传 JSON 格式的 sheets 数据\n"
            "- PPT：用 convert_pptx，input_path 传 .pptd 主文件路径（必须走该技能：先产出 .pptd + pages/*.page，再转换；不要自己写 python-pptx 脚本重建）\n"
            "- 多个独立文件可并行调用，一次调用写一个文件\n"
            "- 不要在回复文本中直接输出文档内容，必须通过工具写入\n\n"
            "bash 使用边界（重要）：\n"
            "- bash 仅用于运行命令（测试、构建、安装、git、服务管理），不用于文件操作\n"
            "- ❌ 读文件 → 用 batch_read（图片用 read_image），不要 cat/type\n"
            "- ❌ 搜索文本 → 用 grep，不要 grep -r\n"
            "- ❌ 搜索文件 → 用 find，不要 find / dir\n"
            "- ❌ 写文件 → 用 write/edit，不要 echo/cat >/New-Item\n\n"
            "sub_agent 使用原则（重要）：\n"
            "- 当需要阅读、分析、修改 >=3 个文件，或涉及多模块跨目录操作时，必须优先使用 sub_agent 并行派发任务，"
            "而不是自己逐文件 read/write\n"
            "- 子 Agent 有自己独立的上下文窗口，不会占用主对话的 token，能高效处理批量文件读写、多模块并行开发等场景\n"
            "- 如果你选择自己读文件，建议同一轮最多并行读 5-6 个文件，超过这个数量请改用 sub_agent"
        )

        return prompt

    def _build_memory_hint(self) -> str:
        """构建轻量的"记忆存在性提示"，只告知有历史记忆可查，不注入正文。

        设计原则：不把记忆内容塞进 system prompt（省 token、不分心），
        仅用一句话提示 LLM"该项目存在历史任务记忆"，由 LLM 按需调用 memory_read。
        仅当记忆文件存在且 memory_read 工具可用时才注入，否则返回空串。
        """
        try:
            # memory_read 工具不可用时（如未启用 project_memory skill），不提示
            if not self.skill_manager or "memory_read" not in self.skill_manager.get_all_tool_names():
                return ""
            if not self.project_root:
                return ""

            working_dir = str(self.project_root)
            history_path = _get_history_path(working_dir)
            overview_path = _get_overview_path(working_dir)
            has_history = history_path.exists() and history_path.stat().st_size > 0
            has_overview = overview_path.exists() and overview_path.stat().st_size > 0
            if not (has_history or has_overview):
                return ""

            # 统计历史任务条数（以 "- [" 开头的行），仅用于提示量级，不注入内容
            task_count = 0
            if has_history:
                try:
                    task_count = sum(
                        1 for line in history_path.read_text(encoding="utf-8").splitlines()
                        if line.strip().startswith("- [")
                    )
                except (OSError, UnicodeDecodeError):
                    task_count = 0

            parts = []
            if has_history:
                parts.append(f"{task_count} 条历史任务记录" if task_count else "历史任务记录")
            if has_overview:
                parts.append("项目结构概览")

            summary = "、".join(parts)
            return (
                "## 项目记忆（按需调用）\n\n"
                f"该项目已有 {summary}。"
                "当当前任务与项目历史相关（如延续之前的工作、需了解项目结构或过往修改）时，"
                "可调用 memory_read 读取后再继续；无关时无需调用。\n\n"
            )
        except Exception:
            return ""

    async def run(self, user_message: str | list, queue: asyncio.Queue,
                  existing_messages: list[dict] | None = None,
                  cancel_event: asyncio.Event | None = None):
        """
        运行 tool use 循环，所有 SSE 事件通过 queue 发出。
        如果提供 existing_messages，则从已有对话历史继续。
        cancel_event 用于外部取消任务。
        
        user_message 可以是:
          - str: 纯文本消息
          - list: anthropic/openai 格式的 content 块 (包含文本和图片)

        事件类型:
          - {"type": "text", "content": "...", "contentType": "text"|"thinking"}
          - {"type": "tool_start", "tool_name": "...", "tool_input": {...}}
          - {"type": "tool_result", "tool_name": "...", "success": bool, "content": "..."}
          - {"type": "todolist", "todos": [...], "progress": {...}}
          - {"type": "compact", "summary": "...", "boundary_id": "..."}
          - {"type": "context_usage", "current_tokens": N, "max_tokens": N, "usage_percent": N, "usage_ratio": 0.N}
          - {"type": "chat_complete"}
          - {"type": "error", "message": "..."}
        """
        self._cancel_event = cancel_event
        # 从已有对话历史继续，或从新对话开始
        messages = existing_messages.copy() if existing_messages else []
        messages.append({"role": "user", "content": user_message})
        # 让 self.messages 与 messages 指向同一列表，确保任意 return 路径（含取消）都能保存最新上下文
        self.messages = messages
        # Build tools: SkillManager pool + CustomAgentManager pool (separate pools)
        tools = self.skill_manager.get_openai_tools() if self.protocol == "openai" else self.skill_manager.get_anthropic_tools()
        agent_tools = custom_agent_manager.get_agent_tools_openai() if self.protocol == "openai" else custom_agent_manager.get_agent_tools_anthropic()
        tools.extend(agent_tools)
        last_had_tool_calls = False

        # 提取纯文本用于日志（如果是 content 块则取第一个 text）
        log_message = user_message if isinstance(user_message, str) else next((b["text"] for b in user_message if b.get("type") == "text"), "")
        log.info(f"[Chat Start] model={self.model}, max_iterations={self.max_iterations}")
        log.debug(f"[User Message] {log_message[:200]}...")

        # ── Pre-loop: 将未完成的 TodoList 注入上下文 ──
        self._inject_unfinished_todos(messages, queue)

        # ── 首次用量推送 ──
        await self._emit_context_usage(messages, queue)

        iteration = 0
        while iteration < self.max_iterations:
            # ── 检查取消信号 ──
            if cancel_event and cancel_event.is_set():
                log.info("[Cancelled] User stopped task")
                self._strip_dangling_tool_use(messages)
                return

            # ── 检查后台任务完成情况，注入到上下文 ──
            self._check_background_tasks(messages, queue)

            # ── 上下文压缩 ──
            compact_res = await compact_if_needed(messages, self.model, self.base_url, self.api_key, self.system_prompt, self.protocol, self.llm_params.get("context_size"))
            if compact_res:
                self._apply_compaction(compact_res, messages, queue)
                log.info(f"[Compact] Round {iteration}: compressed to {len(messages)} messages")

            # ── 安全底线: 超过 80% 窗口则丢弃最老的消息 ──
            messages = self._trim_to_safety(messages)

            llm_result = await self._call_llm(messages, tools, queue)

            if llm_result is None:
                self.messages = messages
                return

            tool_calls = llm_result["tool_calls"]
            had_text = llm_result["had_text"]

            if not tool_calls:
                self.messages = messages
                if last_had_tool_calls and not had_text:
                    messages.append({"role": "user", "content": (
                        "请根据上面的工具执行结果，向用户简要汇报当前进展："
                        "已完成什么、遇到什么问题、建议下一步怎么做。"
                    )})
                    await self._call_llm(messages, [], queue)
                return

            log.info(f"[Round {iteration}] {len(tool_calls)} tool call(s): {[tc['name'] for tc in tool_calls]}")
            last_had_tool_calls = True

            # 构造 assistant 消息（思考块在前 + tool_use blocks）
            # 仅对明确要求保留推理上下文的 provider 回传，其他模型保持原有消息结构不变。
            assistant_content = []
            if self._keep_thinking_history:
                if self.protocol == "openai":
                    reasoning_text = llm_result.get("reasoning_content") or ""
                    if reasoning_text:
                        assistant_content.append({"type": "thinking", "thinking": reasoning_text})
                else:
                    assistant_content.extend(llm_result.get("thinking_blocks") or [])
            for tc in tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # ── 文件 Diff 追踪：执行前保存快照 ──
            self._snapshot_trackable_files()

            # ── 分离 ask_user 与普通工具 ──
            normal_tools = [tc for tc in tool_calls if tc["name"] != "ask_user"]
            ask_user_calls = [tc for tc in tool_calls if tc["name"] == "ask_user"]

            all_results = []

            # 并行执行普通工具
            if normal_tools:
                tasks = [self._execute_tool(tc, queue) for tc in normal_tools]
                normal_results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(normal_results):
                    if isinstance(result, BaseException):
                        all_results.append({
                            "id": normal_tools[i]["id"],
                            "name": normal_tools[i]["name"],
                            "success": False,
                            "content": f"Tool execution error: {result}",
                        })
                    else:
                        all_results.append(result)

            # ── 处理 ask_user ──
            for tc in ask_user_calls:
                tc_input = tc.get("input", {})
                normalized_questionnaire, validation_error = _normalize_questionnaire(tc_input)
                if validation_error:
                    result_content = json.dumps({
                        "error": "ask_user 参数不符合问卷契约",
                        "details": validation_error,
                        "expected": {
                            "title": "string",
                            "questions": [{
                                "id": "string",
                                "text": "string",
                                "type": "single_choice|multi_choice|open",
                                "options": "string[]（选择题必填）",
                                "required": "boolean",
                            }],
                        },
                    }, ensure_ascii=False)
                    log.warning(f"[AskUser] 参数校验失败: {validation_error}")
                    all_results.append({"id": tc["id"], "name": "ask_user", "success": False, "content": result_content})
                    await queue.put({
                        "type": "tool_start",
                        "tool_name": "ask_user",
                        "tool_input": {"validation_error": validation_error},
                    })
                    await queue.put({
                        "type": "tool_result",
                        "tool_name": "ask_user",
                        "success": False,
                        "content": result_content,
                    })
                    continue

                title = normalized_questionnaire["title"]
                questions = normalized_questionnaire["questions"]

                request_id = uuid.uuid4().hex[:12]
                # 先发 tool_start 事件，让前端显示 ask_user 调用
                await queue.put({
                    "type": "tool_start",
                    "tool_name": "ask_user",
                    "tool_input": {"title": title, "questions_count": len(questions)},
                })
                await queue.put({
                    "type": "questionnaire",
                    "request_id": request_id,
                    "title": title,
                    "questions": questions,
                    "tool_use_id": tc["id"],
                })
                log.info(f"[AskUser] 问卷已推送, request_id={request_id}, title={title[:50]}, questions={len(questions)}")

                # ── 阻塞等待用户回答 ──
                future: asyncio.Future = asyncio.Future()
                _pending_questionnaires[request_id] = future

                # ── 启动重传任务：每秒重发问卷，直到用户回答 ──
                async def _retransmit():
                    retry = 0
                    while not future.done():
                        await asyncio.sleep(1)
                        retry += 1
                        if retry % 5 == 0:
                            log.info(f"[AskUser] 问卷重传 #{retry}: request_id={request_id}")
                        try:
                            queue.put_nowait({
                                "type": "questionnaire",
                                "request_id": request_id,
                                "title": title,
                                "questions": questions,
                                "tool_use_id": tc["id"],
                            })
                        except asyncio.QueueFull:
                            pass

                _questionnaire_retransmit_tasks[request_id] = asyncio.create_task(_retransmit())

                try:
                    answers = await future
                finally:
                    _pending_questionnaires.pop(request_id, None)
                    _cancel_questionnaire_retransmit(request_id)

                log.info(f"[AskUser] 收到用户回答: {len(answers)} 个答案")

                result_content = json.dumps({"answers": answers}, ensure_ascii=False)
                all_results.append({
                    "id": tc["id"],
                    "name": "ask_user",
                    "success": True,
                    "content": result_content,
                })

                # ── 发送 tool_result SSE 事件，让前端关闭工具调用块 ──
                await queue.put({
                    "type": "tool_result",
                    "tool_name": "ask_user",
                    "success": True,
                    "content": result_content[:10000],
                })

                # ── 计数器归零，继续循环 ──
                iteration = 0
                # 推送恢复提示
                await queue.put({
                    "type": "text",
                    "content": "\n\n[用户已提交答案，任务继续执行...]\n\n",
                    "contentType": "text",
                })

            # ── 二级暴露 ──
            activated_names = set()
            for tc in tool_calls:
                self._activate_skill_spec(tc["name"])
                activated_names.add(tc["name"])

            # ── 推送 TodoList ──
            self._emit_todolist_event(tool_calls, queue)

            # 构造 tool_result 消息
            result_content = []
            for tr in all_results:
                result_content.append({
                    "type": "tool_result",
                    "tool_use_id": tr["id"],
                    "content": tr["content"],
                })
            messages.append({"role": "user", "content": result_content})

            # ── 参数强化：已激活工具的必填参数概要，注入到上下文尾部防遗忘 ──
            if activated_names and self.protocol != "openai":
                param_hints = self._build_param_hints(activated_names)
                if param_hints:
                    messages.append({"role": "user", "content": param_hints})

            # ── 推送上下文用量 ──
            await self._emit_context_usage(messages, queue)

            # ── 文件 Diff ──
            await self._detect_and_push_file_diffs(queue)

            # ── 连续相同错误检测 ──
            # 同一工具连续返回 success=False 且错误消息一致时累计；达到 3 次则中断任务，避免死循环
            consecutive_error_key = None
            for tr in all_results:
                if tr.get("success") is not False:
                    continue
                err = tr.get("content", "")
                if not err:
                    continue
                # 结构化错误类别优先（如 validation）：同一工具的不同字段报错归为一类，
                # 避免两种参数错误交替出现时计数器反复归零、熔断失效。
                kind = tr.get("error_kind") or ""
                if kind:
                    consecutive_error_key = f"{tr['name']}:{kind}"
                else:
                    # 无类别时用「工具名 + 错误消息前 80 字符」作为指纹
                    consecutive_error_key = f"{tr['name']}:{err[:80]}"
                break
            if consecutive_error_key:
                if consecutive_error_key == self._last_consecutive_error:
                    self._consecutive_error_count += 1
                else:
                    self._consecutive_error_count = 1
                self._last_consecutive_error = consecutive_error_key

                if self._consecutive_error_count >= 3:
                    log.warning(f"[Consecutive Error] {self._consecutive_error_count}x: {consecutive_error_key}")
                    msg = (
                        f"\n\n[系统] ⚠️ 你已经连续 {self._consecutive_error_count} 次触发相同的工具参数错误："
                        f"{consecutive_error_key}。"
                        f"请检查工具描述中的必需参数，或换个方式完成任务。"
                    )
                    messages.append({"role": "user", "content": msg})
                    await queue.put({"type": "text", "content": msg, "contentType": "text"})
                    self.messages = messages
                    return
            else:
                self._consecutive_error_count = 0
                self._last_consecutive_error = None

            iteration += 1

        # 达到最大迭代次数
        if last_had_tool_calls:
            prompt = (
                f"\n\n已达到最大工具调用次数（{self.max_iterations} 轮）。"
                f"请根据当前的进展向用户说明情况：已完成的工作、当前状态、"
                f"以及建议的下一步。询问用户是否要继续或需要调整方式。"
            )
            messages.append({"role": "user", "content": prompt})
            await self._call_llm(messages, [], queue)

        self.messages = messages

    @staticmethod
    def _strip_dangling_tool_use(messages: list) -> None:
        """原地移除末尾因取消而悬挂的 assistant tool_use 消息（缺少配对 tool_result）。

        取消发生在工具执行中时，assistant 已写入 tool_use，但对应 tool_result 尚未追加，
        若直接保留会导致下次 LLM 调用报错（tool_use 缺少 tool_result 配对）。
        """
        while messages:
            last = messages[-1]
            if last.get("role") == "assistant" and isinstance(last.get("content"), list):
                if any(
                    isinstance(b, dict) and b.get("type") == "tool_use"
                    for b in last["content"]
                ):
                    messages.pop()
                    continue
            break

    @staticmethod
    def _strip_thinking_history(messages: list) -> None:
        """原地剥离历史 assistant 消息中的 thinking 块。

        同一任务内的多轮工具循环需要回传思考内容，避免每轮重复思考；
        任务结束后若继续保留，历史会不断累积大段 thinking/signature 挤占上下文，
        因此在任务收尾时清理，只影响跨任务的历史，不影响已经完成的轮次。
        """
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            kept = [
                b for b in content
                if not (isinstance(b, dict) and b.get("type") == "thinking")
            ]
            # 极端情况（assistant 只有 thinking 块）不剥离，避免产生空 content
            if kept and len(kept) != len(content):
                msg["content"] = kept

    # ─── 上下文压缩 ───

    # 安全底线：messages + system_prompt 不能超过模型窗口的 80%
    TOKEN_SAFETY_RATIO = 0.80

    def _trim_to_safety(self, messages: list) -> list:
        """如果总 token 超过安全线，从最老的消息开始丢弃（保留 system_prompt 和最后一条 user 消息）。"""
        from context_manager import estimate_tokens
        max_safe = int(self.context_tracker.max_tokens * self.TOKEN_SAFETY_RATIO)
        sys_tokens = int(len(self.system_prompt) / CHARS_PER_TOKEN)

        while len(messages) > 2:
            total = estimate_tokens(messages) + sys_tokens
            if total <= max_safe:
                break
            # 跳过 system 角色和仅剩最后一条时停止
            if messages[0].get("role") == "system":
                messages.pop(0)
                continue
            removed = messages.pop(0)
            log.warning(f"[Safety Trim] 丢弃消息 (role={removed.get('role')}), 剩余 {len(messages)} 条, token={total}/max_safe={max_safe}")

        return messages

    def _apply_compaction(self, compact_res: CompactResult, messages: list, queue: asyncio.Queue):
        """应用压缩结果：替换消息列表 + 累积摘要"""
        self._history_summary = (
            f"{self._history_summary}\n\n---\n{compact_res.summary}"
            if self._history_summary
            else compact_res.summary
        )
        # 持久化到 SessionState，下次请求时恢复
        self.session_state.history_summary = self._history_summary
        messages.clear()
        messages.extend(compact_res.preserved_tail)
        # 推送 compact SSE 事件
        asyncio.create_task(queue.put({
            "type": "compact",
            "summary": compact_res.summary,
            "boundary_id": compact_res.boundary_id,
        }))

    async def _emit_context_usage(self, messages: list, queue: asyncio.Queue):
        """计算并推送上下文用量 SSE 事件"""
        self.context_tracker.update(messages, self.system_prompt)
        await queue.put({
            "type": "context_usage",
            **self.context_tracker.to_dict(),
        })

    # ─── 两级 Skill 暴露 ───

    def _build_param_hints(self, tool_names: set[str]) -> str:
        """生成已激活工具的必填/可选参数速查摘要，注入上下文尾部。"""
        lines = ["[工具参数速查]"]
        seen = set()
        for name in tool_names:
            if name in seen:
                continue
            seen.add(name)
            try:
                inst = self.skill_manager._get_instance(name)
                required = [p.name for p in inst.parameters if p.required]
                optional = [p.name for p in inst.parameters if not p.required]
                parts = [f"{name}:"]
                if required:
                    parts.append("必填=" + ", ".join(required))
                if optional:
                    parts.append("可选=" + ", ".join(optional))
                lines.append("  " + " | ".join(parts))
            except Exception:
                pass
        return "\n".join(lines) if len(lines) > 1 else ""

    def _activate_skill_spec(self, tool_name: str):
        """
        二级暴露：LLM 首次调用某 skill 的工具时，将该 skill 的完整 skill.md
        及配套 guideline/generate_slides.md（如果存在）缓存到 SessionState 中。
        """
        skill_name = None
        for name, spec in ALL_SKILLS.items():
            if tool_name in spec["tool_names"]:
                skill_name = name
                break

        if skill_name is None:
            return

        spec = self.skill_manager.get_skill_spec(skill_name)
        if spec is None:
            return

        # 自动注入工作流指南（如果存在）
        guideline_dir = self.skill_manager.skills_root / skill_name / "guideline"
        guide_path = guideline_dir / "generate_slides.md"
        if guide_path.exists():
            try:
                guide_content = guide_path.read_text(encoding="utf-8")
                spec += f"\n\n--- 工作流指南 ({skill_name}) ---\n{guide_content}"
                log.debug(f"[Skill Activation] 已注入工作流指南: skills/{skill_name}/guideline/generate_slides.md")
            except Exception as e:
                log.warning(f"[Skill Activation] 读取工作流指南失败 ({skill_name}): {e}")

        self.session_state.activate_skill(skill_name, spec)

    # ─── TodoList 相关 ───

    def _inject_unfinished_todos(self, messages: list, queue: asyncio.Queue):
        """Pre-loop: 将上一轮未完成的任务注入上下文"""
        if not self.todo_manager or self.todo_manager.count == 0:
            return

        todo_dict = self.todo_manager.to_dict()
        unfinished = [t for t in todo_dict["todos"] if t["status"] != "completed"]
        if not unfinished:
            return

        tasks_summary = "\n".join(
            f"- [{t['status']}] {t['id']}: {t['content']}"
            for t in unfinished
        )
        progress = todo_dict["progress"]
        messages.append({
            "role": "user",
            "content": (
                f"[系统] 上一轮未完成的任务（{progress['completed']}/{progress['total']} 已完成，"
                f"{len(unfinished)} 项待继续）:\n{tasks_summary}\n"
                f"用户说\"继续\"则表示要接着上次的任务做。如果用户的新指令与这些任务无关，"
                f"你可以通过 todo_write merge=false 重新创建新的任务列表。"
            ),
        })

    def _emit_todolist_event(self, tool_calls: list, queue: asyncio.Queue):
        """Post-tool: 如果执行了 todo_write，推送 TodoList 状态给前端"""
        if not self.todo_manager:
            return
        had_todo = any(tc["name"] == "todo_write" for tc in tool_calls)
        if had_todo:
            data = self.todo_manager.to_dict()
            asyncio.create_task(queue.put({
                "type": "todolist",
                "todos": data["todos"],
                "progress": data["progress"],
            }))

    # ─── 文件 Diff 追踪 ───

    # 所有可追踪的文件后缀（变更时弹出标签页）
    TRACKABLE_EXTENSIONS = {
        # 文档
        ".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".csv",
        # 代码
        ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".less",
        ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".swift",
        # 数据/配置
        ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".env", ".properties",
        # 脚本
        ".sql", ".sh", ".bat", ".ps1", ".log",
    }
    # 支持结构化 diff 的类型
    DIFFABLE_EXTENSIONS = {".xlsx", ".docx", ".md"}
    _snapshot_cache: dict[str, float] = {}  # path -> mtime

    def _snapshot_trackable_files(self):
        """执行前：遍历工作目录，对可追踪文件保存内容快照（如 mtime 变化则重新快照）"""
        cwd = Path(self.skill_manager.cwd)
        if not cwd.exists():
            return
        for fpath in cwd.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in self.TRACKABLE_EXTENSIONS:
                continue
            if ".git" in fpath.parts or "node_modules" in fpath.parts or ".sigma2.0" in fpath.parts:
                continue
            try:
                path_str = str(fpath.resolve())
                mtime = fpath.stat().st_mtime
                old_mtime = self._snapshot_cache.get(path_str)
                self._snapshot_cache[path_str] = mtime
                # mtime 变化或首次遇到 → 重新快照
                if old_mtime is None or mtime != old_mtime:
                    file_diff_tracker.snapshot_file(path_str)
            except OSError:
                continue

    async def _detect_and_push_file_diffs(self, queue: asyncio.Queue):
        """扫描工作目录中新增或修改的可追踪文件，计算并推送 diff"""
        cwd = Path(self.skill_manager.cwd)
        if not cwd.exists():
            return

        changed_files: list[tuple[str, bool]] = []  # (path, is_new)
        for fpath in cwd.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in self.TRACKABLE_EXTENSIONS:
                continue
            if ".git" in fpath.parts or "node_modules" in fpath.parts or ".sigma2.0" in fpath.parts:
                continue
            try:
                mtime = fpath.stat().st_mtime
            except OSError:
                continue
            path_str = str(fpath.resolve())
            old_mtime = self._snapshot_cache.get(path_str)
            if old_mtime is None:
                # 新文件：之前快照中没有
                changed_files.append((path_str, True))
            elif mtime != old_mtime:
                # 已有文件被修改
                changed_files.append((path_str, False))
            self._snapshot_cache[path_str] = mtime

        # 一批新文件里只自动打开一个“交付物”，否则前端会逐个弹标签页，
        # 最后停在 scenes.js / timeline.json 这类内部文件上，真正的 HTML 反而看不到。
        # 优先级：HTML > 文档 > 图片 > 其他；同优先级取最新。
        def _preview_rank(p: str) -> int:
            ext = Path(p).suffix.lower()
            if ext == ".html":
                return 0
            if ext in {".docx", ".xlsx", ".pptx", ".pdf"}:
                return 1
            if ext in {".md", ".png", ".jpg", ".jpeg", ".webp", ".svg"}:
                return 2
            return 3

        def _mtime(p: str) -> float:
            try:
                return os.path.getmtime(p)
            except OSError:
                return 0.0

        new_paths = [p for p, is_new in changed_files if is_new]
        preview_path = (sorted(new_paths, key=lambda p: (_preview_rank(p), -_mtime(p)))[0]
                        if new_paths else None)

        for file_path, is_new in changed_files:
            try:
                file_name = os.path.basename(file_path)
                suffix = Path(file_path).suffix.lower()
                file_type = {
                    ".xlsx": "xlsx", ".docx": "docx", ".pptx": "pptx", ".pdf": "pdf",
                    ".md": "markdown", ".py": "python", ".js": "javascript",
                    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
                    ".html": "html", ".css": "css", ".json": "json",
                    ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
                    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
                    ".flac": "audio", ".ogg": "audio", ".opus": "audio", ".wma": "audio", ".aiff": "audio",
                }.get(suffix, "file")

                if is_new and file_path != preview_path:
                    # 同批次的其它新文件：只记快照，不自动打开（避免抢走交付物预览）
                    file_diff_tracker.snapshot_file(file_path)
                    continue

                # 推送修改开始
                await queue.put({
                    "type": "file_modification_start",
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_type": file_type,
                    "is_new": is_new,
                })

                if is_new:
                    # 新文件：仅保存快照，不生成 diff（没有旧版本对比）
                    file_diff_tracker.snapshot_file(file_path)
                    await queue.put({
                        "type": "file_modification_complete",
                        "file_path": file_path,
                        "file_name": file_name,
                        "file_type": file_type,
                    })
                    log.info(f"[Diff] 检测到新文件: {file_name} ({file_type})")
                else:
                    # 已修改文件：生成 diff
                    diff = file_diff_tracker.get_diff(file_path)
                    if diff is not None and _diff_has_changes(diff):
                        await queue.put({
                            "type": "file_diff_update",
                            "file_path": file_path,
                            "file_name": file_name,
                            "file_type": file_type,
                            "diff_data": diff,
                        })
                    await queue.put({
                        "type": "file_modification_complete",
                        "file_path": file_path,
                        "file_name": file_name,
                        "file_type": file_type,
                    })
                    # 更新快照为当前状态
                    file_diff_tracker.snapshot_file(file_path)
                    log.info(f"[Diff] 检测到文件变更: {file_name} ({file_type})")
            except Exception as e:
                log.warning(f"[Diff] 计算 diff 失败: {file_path}, {e}")

    # ─── LLM 调用 ───

    @staticmethod
    def _extract_canvas_elements(partial_json: str, already_pushed: int) -> int:
        """从部分 JSON 中提取 elements 数组中完整对象的数量。"""
        # 找到 "elements" 数组的起始位置
        match = re.search(r'"elements"\s*:\s*\[', partial_json)
        if not match:
            return 0
        start = match.end()
        depth = 1
        i = start
        count = 0
        in_string = False
        escape = False
        while i < len(partial_json) and depth > 0:
            c = partial_json[i]
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 1:  # 回到数组层级，说明一个完整元素结束
                        count += 1
                elif c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
            i += 1
        return count

    @staticmethod
    def _parse_canvas_elements_json(partial_json: str, count: int) -> list[dict]:
        """从部分 JSON 中解析 elements 数组的前 count 个完整对象。"""
        match = re.search(r'"elements"\s*:\s*\[', partial_json)
        if not match:
            return []
        start = match.end()
        depth = 1
        i = start
        elements = []
        in_string = False
        escape = False
        current_start = -1
        while i < len(partial_json) and depth > 0 and len(elements) < count:
            c = partial_json[i]
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"' and not escape:
                in_string = not in_string
            elif not in_string:
                if c == '{':
                    if depth == 1:
                        current_start = i
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 1 and current_start >= 0:
                        try:
                            elements.append(json.loads(partial_json[current_start:i + 1]))
                        except json.JSONDecodeError:
                            pass
                        current_start = -1
                elif c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
            i += 1
        return elements

    async def _call_llm(
        self, messages: list, tools: list, queue: asyncio.Queue
    ) -> dict | None:
        """
        调用 LLM 流式接口，按 protocol 分流 Anthropic / OpenAI。
        返回 {"tool_calls": [...], "had_text": bool}，
        并附带思考内容（Anthropic: thinking_blocks，OpenAI: reasoning_content），
        是否回传历史由 self._keep_thinking_history 决定。
        """
        if self.protocol == "openai":
            return await self._call_llm_openai(messages, tools, queue)
        return await self._call_llm_anthropic(messages, tools, queue)

    async def _call_llm_anthropic(
        self, messages: list, tools: list, queue: asyncio.Queue
    ) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.llm_params.get("max_tokens") or self._default_max_tokens,
            "stream": True,
            "system": self.system_prompt,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        apply_model_specific_params(payload, self.model, self.protocol, self.llm_params)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", self.messages_url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        error_msg = error_text.decode()
                        
                        # 检测是否为视觉能力不支持的错误
                        vision_keywords = ["image", "vision", "visual", "multimodal", "base64", "image_url", "media_type"]
                        has_images = any(
                            isinstance(m.get("content"), list) and 
                            any(b.get("type") in ("image", "image_url") for b in m.get("content", []))
                            for m in messages
                        )
                        
                        if has_images and any(kw in error_msg.lower() for kw in vision_keywords):
                            friendly_msg = (
                                f"API Error {resp.status_code}: 当前模型不支持直接读取图片。\n\n"
                                "解决方案：\n"
                                "1. 换用支持视觉的模型（如 deepseek-flash、deepseek-v4-pro、claude-sonnet-4、gpt-4o）\n"
                                "2. 或配置独立的 Vision API（Settings → Skill Keys → PDF Vision OCR），然后使用 read_image skill\n\n"
                                f"原始错误: {error_msg}"
                            )
                            await queue.put({"type": "error", "message": friendly_msg})
                        else:
                            await queue.put({"type": "error", "message": f"API Error {resp.status_code}: {error_msg}"})
                        return None

                    blocks: dict[int, dict] = {}
                    thinking_blocks: dict[int, dict] = {}  # index -> {thinking, signature}（供历史回传）
                    tool_calls = []
                    had_text = False
                    text_buf: list[str] = []      # 收集文本内容用于日志
                    thinking_buf: list[str] = []  # 收集思考内容用于日志
                    stop_reason: str = ""         # Anthropic stop_reason
                    # 流式 canvas 元素追踪：tool_use block index -> 已推送的元素数量
                    canvas_stream_state: dict[int, int] = {}

                    async for line in resp.aiter_lines():
                        # 流式读取中检查取消信号，及时中断
                        if self._cancel_event and self._cancel_event.is_set():
                            log.info("[Cancelled] 中断 LLM 流")
                            break

                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            data = json.loads(line[5:])
                        except json.JSONDecodeError:
                            continue

                        event_type = data.get("type")
                        index = data.get("index")

                        if event_type == "content_block_start":
                            block = data.get("content_block", {})
                            block_type = block.get("type", "text")
                            blocks[index] = {
                                "type": block_type,
                                "name": block.get("name", ""),
                                "id": block.get("id", ""),
                                "text": "",
                                "input_json": "",
                            }
                            if block_type == "thinking":
                                thinking_blocks[index] = {
                                    "thinking": block.get("thinking", ""),
                                    "signature": block.get("signature", ""),
                                }
                            # 初始化 canvas 流式追踪
                            if block_type == "tool_use" and block.get("name") == "canvas_update":
                                canvas_stream_state[index] = 0

                        elif event_type == "content_block_delta":
                            if index not in blocks:
                                continue
                            block = blocks[index]
                            delta = data.get("delta", {})
                            delta_type = delta.get("type", "")

                            if delta_type == "text_delta":
                                text = delta.get("text", "")
                                block["text"] += text
                                text_buf.append(text)
                                had_text = True
                                await queue.put({"type": "text", "content": text, "contentType": "text"})
                            elif delta_type == "thinking_delta":
                                # 思考过程单独标记为 thinking，主界面折叠显示
                                text = delta.get("thinking", "")
                                block["text"] += text
                                thinking_buf.append(text)
                                if index in thinking_blocks:
                                    thinking_blocks[index]["thinking"] += text
                                await queue.put({"type": "text", "content": text, "contentType": "thinking"})
                            elif delta_type == "signature_delta":
                                # Anthropic thinking 块的签名，回传历史时必须原样带上
                                if index in thinking_blocks:
                                    thinking_blocks[index]["signature"] += delta.get("signature", "")
                            elif delta_type == "input_json_delta":
                                block["input_json"] += delta.get("partial_json", "")
                                # canvas_update 流式解析：实时提取 elements 数组中的完整对象
                                if index in canvas_stream_state and block["name"] == "canvas_update":
                                    new_count = self._extract_canvas_elements(block["input_json"], canvas_stream_state[index])
                                    if new_count > canvas_stream_state[index]:
                                        canvas_stream_state[index] = new_count
                                        # 提取 operation 和 canvas_name（可能还未完整，用默认值）
                                        op_match = re.search(r'"operation"\s*:\s*"(\w+)"', block["input_json"])
                                        name_match = re.search(r'"canvas_name"\s*:\s*"([^"]*)"', block["input_json"])
                                        await queue.put({
                                            "type": "canvas_patch",
                                            "canvas_name": name_match.group(1) if name_match else "default",
                                            "operation": op_match.group(1) if op_match else "add",
                                            "elements": self._parse_canvas_elements_json(block["input_json"], new_count),
                                            "batch_index": new_count - 1,
                                            "batch_total": None,
                                            "is_final": False,
                                        })

                        elif event_type == "content_block_stop":
                            if index not in blocks:
                                continue
                            block = blocks.pop(index)
                            if block["type"] == "tool_use":
                                try:
                                    tool_input = json.loads(block["input_json"]) if block["input_json"] else {}
                                except json.JSONDecodeError:
                                    tool_input = {}
                                tool_calls.append({
                                    "id": block["id"],
                                    "name": block["name"],
                                    "input": tool_input,
                                })
                                # canvas_update 流式结束，发送最终标记
                                if index in canvas_stream_state:
                                    del canvas_stream_state[index]
                                    await queue.put({
                                        "type": "canvas_patch",
                                        "canvas_name": tool_input.get("canvas_name", "default"),
                                        "operation": tool_input.get("operation", "add"),
                                        "elements": [],
                                        "batch_index": -1,
                                        "batch_total": None,
                                        "is_final": True,
                                    })

                        elif event_type == "message_stop":
                            break

                        elif event_type == "message_delta":
                            delta = data.get("delta", {})
                            if "stop_reason" in delta:
                                stop_reason = delta["stop_reason"]

                        elif event_type == "error":
                            await queue.put({"type": "error", "message": str(data.get("error", {}).get("message", "Unknown error"))})
                            return None

                    # ── 日志：文本/思考内容 ──
                    if text_buf:
                        full_text = "".join(text_buf)
                        log.info(f"[LLM Text] {full_text[:500]}{'...(截断)' if len(full_text) > 500 else ''}")
                    if thinking_buf:
                        full_think = "".join(thinking_buf)
                        log.debug(f"[LLM Think] {full_think[:500]}{'...(截断)' if len(full_think) > 500 else ''}")

                    # ── 日志：工具调用摘要 ──
                    if tool_calls:
                        tc_names = [tc["name"] for tc in tool_calls]
                        log.info(f"[LLM Tool Calls] {tc_names}")
                        for tc in tool_calls:
                            inp = json.dumps(tc["input"], ensure_ascii=False)
                            log.debug(f"[LLM Tool Detail] {tc['name']}: {inp[:300]}")
                    elif had_text:
                        log.info(f"[LLM Response] text-only, {len(''.join(text_buf))} chars")

                    # ── 日志：stop_reason ──
                    if stop_reason:
                        log.info(f"[LLM Stop] reason={stop_reason}")
                        if stop_reason == "max_tokens":
                            log.warning("[LLM Warning] max_tokens 截断，工具调用参数可能不完整")
                    if tool_calls:
                        empty_inputs = [tc["name"] for tc in tool_calls if not tc.get("input")]
                        if empty_inputs:
                            log.warning(f"[LLM Warning] 以下工具调用输入为空（可能因 token 截断）: {empty_inputs}")

                    # 思考块按出现顺序返回，供需要保留推理上下文的模型回传历史
                    thinking_out = [
                        {"type": "thinking", "thinking": v["thinking"], "signature": v["signature"]}
                        for _, v in sorted(thinking_blocks.items())
                        if v.get("thinking")
                    ]
                    return {"tool_calls": tool_calls, "had_text": had_text, "thinking_blocks": thinking_out}

        except Exception as e:
            import traceback, sys
            traceback.print_exc(file=sys.stderr)
            log.error(f"[LLM Error] {e}")
            await queue.put({"type": "error", "message": str(e)})
            return None

    async def _call_llm_openai(
        self, messages: list, tools: list, queue: asyncio.Queue
    ) -> dict | None:
        """OpenAI / DeepSeek 协议流式调用。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": self.model,
            "max_tokens": self.llm_params.get("max_tokens") or self._default_max_tokens,
            "stream": True,
            "messages": self._convert_to_openai_messages(messages),
        }
        if tools:
            payload["tools"] = tools
        apply_model_specific_params(payload, self.model, self.protocol, self.llm_params)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", self.messages_url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        error_msg = error_text.decode()
                        
                        # 检测是否为视觉能力不支持的错误
                        vision_keywords = ["image", "vision", "visual", "multimodal", "base64", "image_url", "media_type"]
                        has_images = any(
                            isinstance(m.get("content"), list) and 
                            any(b.get("type") in ("image", "image_url") for b in m.get("content", []))
                            for m in messages
                        )
                        
                        if has_images and any(kw in error_msg.lower() for kw in vision_keywords):
                            friendly_msg = (
                                f"API Error {resp.status_code}: 当前模型不支持直接读取图片。\n\n"
                                "解决方案：\n"
                                "1. 换用支持视觉的模型（如 deepseek-flash、deepseek-v4-pro、claude-sonnet-4、gpt-4o）\n"
                                "2. 或配置独立的 Vision API（Settings → Skill Keys → PDF Vision OCR），然后使用 read_image skill\n\n"
                                f"原始错误: {error_msg}"
                            )
                            await queue.put({"type": "error", "message": friendly_msg})
                        else:
                            await queue.put({"type": "error", "message": f"API Error {resp.status_code}: {error_msg}"})
                        return None

                    tool_calls: list[dict] = []
                    had_text = False
                    text_buf: list[str] = []
                    reasoning_buf: list[str] = []  # 收集推理内容，供需要保留推理上下文的模型回传历史
                    tool_call_buf: dict[int, dict] = {}  # index -> {id, name, arguments}

                    async for line in resp.aiter_lines():
                        if self._cancel_event and self._cancel_event.is_set():
                            log.info("[Cancelled] 中断 LLM 流")
                            break
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})

                        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                        if reasoning:
                            reasoning_buf.append(reasoning)
                            await queue.put({"type": "text", "content": reasoning, "contentType": "thinking"})

                        # 文本
                        if "content" in delta and delta["content"]:
                            text = delta["content"]
                            text_buf.append(text)
                            had_text = True
                            await queue.put({"type": "text", "content": text, "contentType": "text"})

                        # 工具调用
                        tool_deltas = delta.get("tool_calls", [])
                        for td in tool_deltas:
                            idx = td.get("index", 0)
                            if idx not in tool_call_buf:
                                tool_call_buf[idx] = {"id": "", "name": "", "arguments": ""}
                                if "id" in td:
                                    tool_call_buf[idx]["id"] = td["id"]
                            entry = tool_call_buf[idx]
                            func = td.get("function", {})
                            if "name" in func:
                                entry["name"] = func["name"]
                            if "arguments" in func:
                                entry["arguments"] += func["arguments"]

                    # 收尾工具调用
                    for idx in sorted(tool_call_buf.keys()):
                        tc = tool_call_buf[idx]
                        tool_input = {}
                        if tc["arguments"]:
                            try:
                                tool_input = json.loads(tc["arguments"])
                            except json.JSONDecodeError:
                                tool_input = {"_raw": tc["arguments"]}
                        tool_calls.append({
                            "id": tc["id"] or f"call_{idx}",
                            "name": tc["name"],
                            "input": tool_input,
                        })

                    if text_buf:
                        full_text = "".join(text_buf)
                        log.info(f"[LLM Text] {full_text[:500]}{'...(截断)' if len(full_text) > 500 else ''}")
                    if tool_calls:
                        tc_names = [tc["name"] for tc in tool_calls]
                        log.info(f"[LLM Tool Calls] {tc_names}")
                        for tc in tool_calls:
                            inp = json.dumps(tc["input"], ensure_ascii=False)
                            log.debug(f"[LLM Tool Detail] {tc['name']}: {inp[:300]}")
                    elif had_text:
                        log.info(f"[LLM Response] text-only, {len(''.join(text_buf))} chars")

                    return {
                        "tool_calls": tool_calls,
                        "had_text": had_text,
                        "reasoning_content": "".join(reasoning_buf),
                    }

        except Exception as e:
            log.error(f"[LLM Error] {e}")
            await queue.put({"type": "error", "message": str(e)})
            return None

    def _convert_to_openai_messages(self, messages: list) -> list:
        """将内部消息格式转为 OpenAI Chat Completions 格式。

        关键约束：
        - assistant 消息若携带 tool_calls，content 可为 None；但同一轮的文本内容必须保留
        - role=tool 消息必须携带 tool_call_id 且每个 tool_call 独立一条
        - user 消息含多模态内容时保持 list 结构
        """
        result = []
        # system prompt 作为第一条 system 消息
        result.append({"role": "system", "content": self.system_prompt})
        for m in messages:
            role = m["role"]
            content = m.get("content", "")
            if role == "assistant":
                if isinstance(content, list):
                    # 含 tool_use 的 assistant 消息：拆出文本、推理内容与 tool_calls
                    text_parts = []
                    reasoning_parts = []
                    tool_calls = []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"], ensure_ascii=False),
                                },
                            })
                        elif block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "thinking":
                            # 内部 thinking 块 → OpenAI 协议的 reasoning_content（仅对开启回传的 provider 存在）
                            reasoning_parts.append(block.get("thinking", ""))
                    entry: dict = {
                        "role": "assistant",
                        # OpenAI 规范：有 tool_calls 时 content 可为 null；这里保留文本以兼容更多实现
                        "content": "".join(text_parts) if text_parts else None,
                    }
                    if reasoning_parts:
                        entry["reasoning_content"] = "".join(reasoning_parts)
                    if tool_calls:
                        entry["tool_calls"] = tool_calls
                    result.append(entry)
                else:
                    # 纯文本 assistant 消息
                    result.append({"role": "assistant", "content": content})
            elif role == "user" and isinstance(content, list):
                # 分离 tool_result 与普通多模态 content
                tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
                other_blocks = [b for b in content if not (isinstance(b, dict) and b.get("type") == "tool_result")]
                # 每个 tool_result 独立一条 role=tool 消息（OpenAI 协议要求）
                for item in tool_results:
                    result.append({
                        "role": "tool",
                        "tool_call_id": item["tool_use_id"],
                        "content": item["content"] if isinstance(item["content"], str) else json.dumps(item["content"], ensure_ascii=False),
                    })
                # 其余 content（文本/图片）保留为 user 消息
                if other_blocks:
                    # 转换为 OpenAI 多模态格式
                    openai_content = []
                    for block in other_blocks:
                        if not isinstance(block, dict):
                            openai_content.append({"type": "text", "text": str(block)})
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            openai_content.append({"type": "text", "text": block.get("text", "")})
                        elif btype == "image":
                            # Anthropic image 格式转 OpenAI image_url 格式
                            source = block.get("source", {})
                            if source.get("type") == "base64":
                                data_url = f"data:{source.get('media_type', 'image/jpeg')};base64,{source.get('data', '')}"
                                openai_content.append({"type": "image_url", "image_url": {"url": data_url}})
                        elif btype == "image_url":
                            openai_content.append(block)
                    if openai_content:
                        result.append({"role": "user", "content": openai_content})
            elif role == "user":
                result.append({"role": "user", "content": str(content)})
        return result

    def _guard_direct_script_call(self, command: str):
        """通用护栏：检测 bash/sandbox 是否在直调已注册技能的 scripts 脚本。
        命中返回提示信息 dict，否则返回 None。由 SkillManager._skill_scripts 通用判定，不硬编码技能名。"""
        cmd = _norm_path(command or "")
        if "python" not in cmd:
            return None
        index = getattr(self.skill_manager, "_skill_scripts", {})
        for key, (label, tools) in index.items():
            if key in cmd:
                tool_hint = ", ".join(tools) if tools else "技能内工具"
                msg = (
                    f"检测到你正直接执行技能脚本「{key}」。请勿用 bash/sandbox 直接执行技能内置脚本，"
                    f"请改用对应技能工具完成（{label} 技能可用工具：{tool_hint}）。"
                )
                return {"path": key, "message": msg}
        return None

    async def _execute_tool(self, tool_call: dict, queue: asyncio.Queue) -> dict:
        """执行单个工具调用并发送事件（可由 asyncio.gather 并行调用）。

        支持超时处理：超过 tool_timeout 秒后弹出选择框（继续等待/后台运行/取消）。
        后台运行的任务会在后续迭代中自动汇报结果。
        """
        # 工具执行前检查取消信号
        if self._cancel_event and self._cancel_event.is_set():
            log.info(f"[Cancelled] 跳过工具: {tool_call.get('name')}")
            return {
                "id": tool_call["id"],
                "name": tool_call["name"],
                "success": False,
                "content": "用户已取消任务",
            }

        tool_name = tool_call["name"]
        tool_input = tool_call["input"]

        # ── 通用护栏：禁止 bash/sandbox 直调技能 scripts 脚本，强制走技能工具 ──
        if tool_name in ("bash", "sandbox_run"):
            payload = tool_input.get("command") if tool_name == "bash" else tool_input.get("code")
            blocked = self._guard_direct_script_call(payload)
            if blocked:
                log.warning(f"[script-block] 拦截 {tool_name} 直调技能脚本: {blocked['path']}")
                return {
                    "id": tool_call["id"],
                    "name": tool_name,
                    "success": False,
                    "content": blocked["message"],
                }

        # 构建 tool_start 事件，Agent 工具额外附带显示名称
        tool_start_event = {"type": "tool_start", "tool_name": tool_name, "tool_input": tool_input}
        if is_agent_tool(tool_name):
            try:
                resolved = custom_agent_manager.get_agent_name_by_tool(tool_name)
                if resolved:
                    tool_start_event["display_name"] = resolved
            except Exception:
                pass
        await queue.put(tool_start_event)
        log.debug(f"[Tool Start] {tool_name} input={json.dumps(tool_input, ensure_ascii=False)[:200]}")

        try:
            # ── 通用进度回调：所有工具都支持实时进度推送 ──
            def _on_progress(event):
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass

            # Agent 工具不走 SkillManager，跳过进度回调设置
            inst = None
            if not is_agent_tool(tool_name):
                inst = self.skill_manager._get_instance(tool_name)
                if inst:
                    inst.set_progress_callback(_on_progress)

            # ── 文件修改 diff: 执行前保存快照 ──
            if tool_name in ("sandbox_run", "write"):
                self._snapshot_trackable_files()

            # ── 使用 ThreadPoolExecutor + 超时 ──
            loop = asyncio.get_running_loop()

            # Agent 工具走独立分发池，注入 progress callback 实现实时 SSE 推送
            if is_agent_tool(tool_name):
                def _on_agent_progress(event):
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

                executor_future = loop.run_in_executor(
                    self._executor,
                    lambda: custom_agent_manager.dispatch_agent(
                        tool_name, tool_input.get("prompt", ""), self.skill_manager,
                        progress_callback=_on_agent_progress,
                    ),
                )
            else:
                executor_future = loop.run_in_executor(
                    self._executor,
                    lambda: self.skill_manager.dispatch(tool_name, **tool_input),
                )

            if tool_name in _NO_TIMEOUT_TOOLS:
                # 长任务视频工具：不设超时，等到跑完（否则没做完就被判超时/跳过）
                result = await asyncio.wrap_future(executor_future)
            else:
                timeout = self.tool_timeout
                # 长耗时工具：PPT 转换 / 深度研究 / 子 Agent 等
                if tool_name == "video_produce":
                    # 完整流水线（旁白→画面→合成），最耗时，给足余量
                    timeout = max(timeout, 1800)
                elif tool_name in ("video_auto", "video_compose"):
                    timeout = max(timeout, 600)
                elif tool_name in ("video_scene", "convert_pptx", "deep_research",
                                   "generate_image", "sandbox_run", "batch_read",
                                   "doubao_tts"):
                    timeout = max(timeout, 300)
                elif tool_name in ("sub_agent", "custom_agent"):
                    timeout = max(timeout, 600)

                try:
                    result = await asyncio.wait_for(
                        asyncio.wrap_future(executor_future),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    result = await self._handle_tool_timeout(
                        tool_call, tool_name, tool_input, executor_future, timeout, queue,
                    )

            # ── 空输入检测：LLM 因 token 截断生成空工具调用时，注入 skill spec 帮助恢复 ──
            if not getattr(result, "success", False) and not tool_input:
                spec = self.skill_manager.get_skill_specs_for_tool(tool_name)
                if spec:
                    result = type("R", (), {
                        "success": False,
                        "content": f"{getattr(result, 'content', '')}\n\n─── 工具参数说明 ───\n{spec}",
                        "truncated": getattr(result, "truncated", False),
                    })()

            # ── 未知工具检测：LLM 误把 skill 名当工具名调用时，自动注入匹配 skill 的 spec 帮其纠错 ──
            if (not getattr(result, "success", False)
                    and "未知工具" in getattr(result, "content", "")):
                hint = self._suggest_skill_for_unknown_tool(tool_name)
                if hint:
                    result = type("R", (), {
                        "success": False,
                        "content": f"{getattr(result, 'content', '')}\n\n─── 你可能想调用的是 ───\n{hint}",
                        "truncated": getattr(result, "truncated", False),
                    })()

            # 执行完清空进度回调
            if inst:
                inst.set_progress_callback(None)

            # ── 文件修改 diff 追踪（执行后检测变化）──
            if tool_name in ("sandbox_run", "write") and getattr(result, "success", False):
                await self._detect_and_push_file_diffs(queue)

        except Exception as e:
            log.error(f"[Tool Error] {tool_name}: {e}")
            result = type("R", (), {"success": False, "content": str(e), "truncated": False})()

        content = getattr(result, "content", str(result))
        truncated = getattr(result, "truncated", False)
        success = getattr(result, "success", False)
        if truncated:
            content += "\n(输出已截断)"

        log.info(f"[Tool Result] {tool_name} success={success}, content={content[:200]}...")

        await queue.put({
            "type": "tool_result",
            "tool_name": tool_name,
            "success": success,
            "content": content[:10000],   # SSE 前端展示截断
        })

        return {
            "id": tool_call["id"],
            "name": tool_name,
            "success": success,  # 供熔断器识别失败结果
            "error_kind": (getattr(result, "details", None) or {}).get("error_kind", ""),
            "content": content[:80000] if len(content) > 80000 else content,  # LLM 上下文上限 80K 字符
        }

    def _suggest_skill_for_unknown_tool(self, tool_name: str) -> str:
        """
        LLM 把 skill 名当工具名调用时，给它推荐最相似的 skill 一级摘要 + 完整 spec。
        优先匹配同名 skill，其次按包含关系 / 字串相似度匹配。
        """
        sm = self.skill_manager
        if not sm:
            return ""

        # 1. 完全同名 skill → 直接用
        if tool_name in sm._skills:
            header = sm.get_skill_headers().get(tool_name, "")
            spec = sm.get_skill_spec(tool_name)
            tools = sm._skills[tool_name].get("tool_names", [])
            tool_hint = ", ".join(f"`{t}`" for t in tools) if tools else "(无)"
            return f"skill: `{tool_name}` → 工具: {tool_hint}\n\n{header}\n\n---\n\n{spec}"

        # 2. 字串包含 / 共同子串 → 找最相似
        norm = tool_name.replace("_", "").replace("-", "").lower()
        best_skill = None
        best_score = 0
        for skill_name, info in sm._skills.items():
            if not info.get("tool_names"):
                continue
            s_norm = skill_name.replace("_", "").replace("-", "").lower()
            for t in info["tool_names"]:
                t_norm = t.replace("_", "").replace("-", "").lower()
                # 简单相似度：共同子串长度 / 较长者
                if not norm or not t_norm:
                    continue
                common = 0
                shorter, longer = (norm, t_norm) if len(norm) <= len(t_norm) else (t_norm, norm)
                for size in range(min(len(shorter), 6), 2, -1):
                    if shorter in longer or any(shorter[i:i+size] in longer for i in range(len(shorter) - size + 1)):
                        common = max(common, size)
                        break
                if common > best_score:
                    best_score = common
                    best_skill = skill_name
        if best_skill and best_score >= 3:
            header = sm.get_skill_headers().get(best_skill, "")
            spec = sm.get_skill_spec(best_skill)
            tools = sm._skills[best_skill].get("tool_names", [])
            tool_hint = ", ".join(f"`{t}`" for t in tools) if tools else "(无)"
            return (
                f"你似乎想调用 skill `{tool_name}`，但这不是工具名。"
                f"最接近的 skill 是 `{best_skill}`，对应工具: {tool_hint}。"
                f"\n\n{header}\n\n---\n\n{spec}"
            )
        return ""

    async def _handle_tool_timeout(
        self, tool_call: dict, tool_name: str, tool_input: dict,
        executor_future, timeout: int, queue: asyncio.Queue,
    ):
        """工具超时后直接转入后台运行，不再询问用户。"""
        log.info(f"[Tool Timeout] {tool_name} 超时 {timeout}s，自动转入后台")

        # 推送 SSE 事件通知前端该工具已转入后台
        await queue.put({
            "type": "tool_progress",
            "tool_name": tool_name,
            "content": f"⏱ 执行超过 {timeout}s，已转入后台继续运行...",
        })

        bg_id = uuid.uuid4().hex[:8]
        self._background_futures[bg_id] = {
            "future": executor_future,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "started_at": time.time(),
        }
        return type("R", (), {
            "success": True,
            "content": (
                f"[后台运行中] 任务ID: {bg_id}\n"
                f"工具 {tool_name} 执行超过 {timeout}s，已自动转入后台运行。\n"
                f"完成后结果将自动注入对话，你可以继续处理其他任务。"
            ),
            "truncated": False,
        })()

    def _check_background_tasks(self, messages: list, queue: asyncio.Queue):
        """检查后台任务完成情况，将结果注入消息列表。"""
        if not self._background_futures:
            return

        # 检查已完成的
        completed = []
        for bg_id, info in list(self._background_futures.items()):
            future = info["future"]
            if not future.done():
                continue
            try:
                raw = future.result()
                content = getattr(raw, "content", str(raw))[:2000]
                completed.append({
                    "id": bg_id,
                    "tool_name": info["tool_name"],
                    "success": getattr(raw, "success", False),
                    "content": content,
                })
            except BaseException as e:
                completed.append({
                    "id": bg_id,
                    "tool_name": info["tool_name"],
                    "success": False,
                    "content": f"执行异常: {e}",
                })
            del self._background_futures[bg_id]

        # 正在运行的
        running = [
            {
                "id": bg_id,
                "tool_name": info["tool_name"],
                "elapsed": int(time.time() - info["started_at"]),
            }
            for bg_id, info in self._background_futures.items()
        ]

        if not completed and not running:
            return

        parts = []
        if completed:
            lines = []
            for c in completed:
                status = "成功" if c["success"] else "失败"
                lines.append(f"- [{c['id']}] {c['tool_name']}: {status}")
                lines.append(f"  {c['content'][:300]}")
            parts.append("后台任务已完成:\n" + "\n".join(lines))

        if running:
            lines = [f"- [{r['id']}] {r['tool_name']}: 已运行 {r['elapsed']}s" for r in running]
            parts.append("后台任务仍在运行:\n" + "\n".join(lines))

        if parts:
            msg = "[系统] " + "\n\n".join(parts)
            messages.append({"role": "user", "content": msg})
            log.info(f"[Background Tasks] completed={len(completed)}, running={len(running)}")

            # 推送 SSE 事件通知前端
            asyncio.create_task(queue.put({
                "type": "background_tasks",
                "completed": completed,
                "running": running,
            }))
