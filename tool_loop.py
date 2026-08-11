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
import asyncio
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from skills.manager import SkillManager, ALL_SKILLS
from skills.todo_manager import TodoManager
from custom_agent_manager import custom_agent_manager, is_agent_tool
from context_manager import (
    ContextTracker, SessionState, CompactResult,
    estimate_tokens, compact_if_needed,
    apply_model_specific_params, CHARS_PER_TOKEN,
)
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
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.protocol = protocol
        self.skill_manager = skill_manager
        self.max_iterations = max_iterations
        self.todo_manager = todo_manager
        if protocol == "openai":
            self.messages_url = f"{self.base_url}/chat/completions"
        else:
            self.messages_url = f"{self.base_url}/v1/messages"
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
            "- 所有文件读取必须使用 batch_read，不要逐个调用 read\n"
            "- 即使只读 1 个文件也优先用 batch_read（设置 purpose 可获得精准摘要）\n\n"
            "文件写入（重要）：\n"
            "- Word 文档：直接用 write_docx 工具，传 output_path + doc_type + outline（大纲/指令）\n"
            "  · write_docx 内置子 Agent 会独立生成完整文档，不占用主对话 token\n"
            "- 代码/文本文件：用 write 工具，传 file_path + content\n"
            "- 修改现有文件：用 edit 批量模式（edits [{old_str, new_str}, ...]），同一文件多处修改一次完成，不要多次调用 edit\n"
            "- Excel 表格：用 write_xlsx，content 传 JSON 格式的 sheets 数据\n"
            "- PPT：用 convert_pptx，content 传 .pptd 输入文件路径\n"
            "- 多个独立文件可并行调用，一次调用写一个文件\n"
            "- 不要在回复文本中直接输出文档内容，必须通过工具写入\n\n"
            "bash 使用边界（重要）：\n"
            "- bash 仅用于运行命令（测试、构建、安装、git、服务管理），不用于文件操作\n"
            "- ❌ 读文件 → 用 batch_read，不要 cat/type\n"
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

    async def run(self, user_message: str, queue: asyncio.Queue,
                  existing_messages: list[dict] | None = None,
                  cancel_event: asyncio.Event | None = None):
        """
        运行 tool use 循环，所有 SSE 事件通过 queue 发出。
        如果提供 existing_messages，则从已有对话历史继续。
        cancel_event 用于外部取消任务。

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
        # Build tools: SkillManager pool + CustomAgentManager pool (separate pools)
        tools = self.skill_manager.get_openai_tools() if self.protocol == "openai" else self.skill_manager.get_anthropic_tools()
        agent_tools = custom_agent_manager.get_agent_tools_openai() if self.protocol == "openai" else custom_agent_manager.get_agent_tools_anthropic()
        tools.extend(agent_tools)
        last_had_tool_calls = False

        log.info(f"[Chat Start] model={self.model}, max_iterations={self.max_iterations}")
        log.debug(f"[User Message] {user_message[:200]}...")

        # ── Pre-loop: 将未完成的 TodoList 注入上下文 ──
        self._inject_unfinished_todos(messages, queue)

        # ── 首次用量推送 ──
        await self._emit_context_usage(messages, queue)

        iteration = 0
        while iteration < self.max_iterations:
            # ── 检查取消信号 ──
            if cancel_event and cancel_event.is_set():
                log.info("[Cancelled] User stopped task")
                return

            # ── 检查后台任务完成情况，注入到上下文 ──
            self._check_background_tasks(messages, queue)

            # ── 上下文压缩 ──
            compact_res = await compact_if_needed(messages, self.model, self.base_url, self.api_key, self.system_prompt, self.protocol)
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

            # 构造 assistant 消息（含 tool_use blocks）
            assistant_content = []
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
                            "content": f"Tool execution error: {result}",
                        })
                    else:
                        all_results.append(result)

            # ── 处理 ask_user ──
            for tc in ask_user_calls:
                tc_input = tc.get("input", {})
                title = tc_input.get("title", "请回答以下问题")
                questions = tc_input.get("questions", [])

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
            consecutive_error_key = None
            for tr in all_results:
                err = tr.get("content", "")
                if "参数校验失败" in err or "缺少必填参数" in err:
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

        for file_path, is_new in changed_files:
            try:
                file_name = os.path.basename(file_path)
                suffix = Path(file_path).suffix.lower()
                file_type = {".xlsx": "xlsx", ".docx": "docx", ".md": "markdown"}.get(suffix, "file")

                # 推送修改开始
                await queue.put({
                    "type": "file_modification_start",
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_type": file_type,
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

    async def _call_llm(
        self, messages: list, tools: list, queue: asyncio.Queue
    ) -> dict | None:
        """
        调用 LLM 流式接口，按 protocol 分流 Anthropic / OpenAI。
        返回 {"tool_calls": [...], "had_text": bool}，
        """
        if self.protocol == "openai":
            return await self._call_llm_openai(messages, tools, queue)
        return await self._call_llm_anthropic(messages, tools, queue)

    async def _call_llm_anthropic(
        self, messages: list, tools: list, queue: asyncio.Queue
    ) -> dict | None:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 16384,
            "stream": True,
            "system": self.system_prompt,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
        apply_model_specific_params(payload, self.model, self.protocol)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", self.messages_url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        await queue.put({"type": "error", "message": f"API Error {resp.status_code}: {error_text.decode()}"})
                        return None

                    blocks: dict[int, dict] = {}
                    tool_calls = []
                    had_text = False
                    text_buf: list[str] = []      # 收集文本内容用于日志
                    thinking_buf: list[str] = []  # 收集思考内容用于日志
                    stop_reason: str = ""         # Anthropic stop_reason

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
                                # Kimi 等厂商把普通文本也走 thinking_delta，统一当作 text 处理
                                text = delta.get("thinking", "")
                                block["text"] += text
                                text_buf.append(text)
                                had_text = True
                                await queue.put({"type": "text", "content": text, "contentType": "text"})
                            elif delta_type == "input_json_delta":
                                block["input_json"] += delta.get("partial_json", "")

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

                    return {"tool_calls": tool_calls, "had_text": had_text}

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
            "max_tokens": 16384,
            "stream": True,
            "messages": self._convert_to_openai_messages(messages),
        }
        if tools:
            payload["tools"] = tools
        apply_model_specific_params(payload, self.model, self.protocol)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", self.messages_url, json=payload, headers=headers) as resp:
                    if resp.status_code != 200:
                        error_text = await resp.aread()
                        await queue.put({"type": "error", "message": f"API Error {resp.status_code}: {error_text.decode()}"})
                        return None

                    tool_calls: list[dict] = []
                    had_text = False
                    text_buf: list[str] = []
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

                    return {"tool_calls": tool_calls, "had_text": had_text}

        except Exception as e:
            log.error(f"[LLM Error] {e}")
            await queue.put({"type": "error", "message": str(e)})
            return None

    def _convert_to_openai_messages(self, messages: list) -> list:
        """将内部消息格式转为 OpenAI Chat Completions 格式。"""
        result = []
        # system prompt 作为第一条 system 消息
        result.append({"role": "system", "content": self.system_prompt})
        for m in messages:
            role = m["role"]
            content = m.get("content", "")
            if role == "assistant":
                entry: dict = {"role": "assistant", "content": content if isinstance(content, str) else None}
                # tool_calls
                if isinstance(content, list):
                    entry["content"] = None
                    entry["tool_calls"] = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            entry["tool_calls"].append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            })
                result.append(entry)
            elif role == "user" and isinstance(content, list):
                # tool results
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": item["content"],
                        })
            elif role == "user":
                result.append({"role": "user", "content": str(content)})
        return result

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
                "content": "用户已取消任务",
            }

        tool_name = tool_call["name"]
        tool_input = tool_call["input"]

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
            # sub_agent / batch_read 特殊处理：注入 progress callback 实现实时 SSE 推送
            if tool_name in ("sub_agent", "batch_read"):
                inst = self.skill_manager._get_instance(tool_name)

                def _on_progress(event):
                    try:
                        queue.put_nowait(event)
                    except asyncio.QueueFull:
                        pass

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

            timeout = self.tool_timeout
            # 长耗时工具：视频生成 / PPT 转换 / 深度研究 / 子 Agent 等
            if tool_name in ("video_auto", "video_compose"):
                timeout = max(timeout, 600)
            elif tool_name in ("video_scene", "convert_pptx", "deep_research",
                               "generate_image", "sandbox_run", "batch_read"):
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

            # sub_agent / batch_read 执行完清空 callback
            if tool_name in ("sub_agent", "batch_read"):
                inst = self.skill_manager._instances.get(tool_name)
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
            "content": content[:80000] if len(content) > 80000 else content,  # LLM 上下文上限 80K 字符
        }

    async def _handle_tool_timeout(
        self, tool_call: dict, tool_name: str, tool_input: dict,
        executor_future, timeout: int, queue: asyncio.Queue,
    ):
        """工具超时时弹出选择框，根据用户选择处理。"""
        request_id = uuid.uuid4().hex[:12]

        await queue.put({
            "type": "tool_timeout",
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "elapsed_seconds": timeout,
            "options": [
                {"value": "wait", "label": "继续等待", "description": f"再等待 {timeout} 秒"},
                {"value": "background", "label": "后台运行", "description": "让任务在后台继续，LLM 先进入下一轮"},
                {"value": "cancel", "label": "取消", "description": "终止该工具的执行"},
            ],
            "tool_use_id": tool_call["id"],
        })
        log.info(f"[Tool Timeout] {tool_name} 超时 {timeout}s, request_id={request_id}")

        # 阻塞等待用户选择（15 秒无人应答则自动转入后台）
        answer_future: asyncio.Future = asyncio.Future()
        _pending_tool_timeouts[request_id] = answer_future
        try:
            choice = await asyncio.wait_for(answer_future, timeout=15)
        except asyncio.TimeoutError:
            choice = "background"
            log.info(f"[Tool Timeout] {tool_name} 15s 无人应答，自动转入后台")
        finally:
            _pending_tool_timeouts.pop(request_id, None)

        log.info(f"[Tool Timeout] {tool_name} 用户选择: {choice}")

        if choice == "wait":
            # 继续等待，双倍超时：用 shield 防止取消状态传播导致 CancelledError 穿出
            try:
                wrapped = asyncio.wrap_future(executor_future)
                raw = await asyncio.wait_for(
                    asyncio.shield(wrapped),
                    timeout=timeout * 2,
                )
                return raw
            except asyncio.TimeoutError:
                return type("R", (), {
                    "success": False,
                    "content": f"工具 {tool_name} 再次超时 ({timeout * 2}s)，已放弃等待。",
                    "truncated": False,
                })()
            except BaseException as e:
                # 兜底：任何异常都转为 ToolResult 返回，不让 CancelledError 穿透到 LLM 循环
                return type("R", (), {
                    "success": False,
                    "content": f"工具 {tool_name} 等待过程异常: {e}",
                    "truncated": False,
                })()

        elif choice == "background":
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
                    f"工具 {tool_name} 正在后台执行中，完成后结果将自动汇报。\n"
                    f"你可以继续处理其他任务。"
                ),
                "truncated": False,
            })()

        else:  # cancel
            return type("R", (), {
                "success": False,
                "content": f"[已取消] 用户取消了工具 {tool_name} 的执行。",
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
