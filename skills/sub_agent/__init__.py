"""
sub_agent skill - 并行子 Agent 创建与编排

提供 sub_agent 工具，让主 Agent 创建多个独立子 Agent 并行执行任务。
每个子 Agent 拥有独立上下文窗口和工具访问权限。
基于 concurrent.futures.ThreadPoolExecutor 实现真正的并行执行。

与 LLaMDA 的区别：
  - LLaMDA: export_agent 单次调用 → ToolRunner 拦截 → asyncio.gather 并行
  - Sigma:   sub_agent 一次传入多个 tasks → ThreadPoolExecutor 并行
"""
import json
import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import httpx

from skills.base import BaseTool, ToolParameter, ToolResult
from sigma_logger import log

# 子 Agent 最大工具调用轮次
MAX_SUBAGENT_TURNS = 8

# 默认允许的工具
DEFAULT_ALLOWED_TOOLS = ["read", "write", "bash", "web_search", "read_docx", "sandbox_run"]

# 只读类型的工具
READONLY_TOOLS = ["read", "web_search", "read_docx", "search_docx", "read_image", "search_image", "read_pdf", "read_xlsx", "read_pptx"]


@dataclass
class SubAgentResult:
    agent_id: str
    success: bool
    content: str
    turns: int
    description: str
    errors: list[str] = field(default_factory=list)


MAX_SUBAGENT_TURNS = 8  # 默认值，实际从 SkillManager.sub_agent_max_turns 读取

class SubAgentTool(BaseTool):
    name = "sub_agent"
    description = (
        "创建多个并行子 Agent 执行独立任务。子 Agent 拥有独立的上下文窗口和工具访问权限，"
        "所有子 Agent 并行执行（ThreadPoolExecutor），提高多任务处理效率。"
        "适用于：多模块并行开发、批量文件处理、分离的前后端任务、并行代码审查等。"
        "一次调用可创建多个子 Agent，每个子 Agent 独立运行并返回结果。"
    )
    parameters = [
        ToolParameter(
            "tasks",
            "array",
            "子 Agent 任务列表。每项包含: type(plan/coder/explore), prompt(任务描述), "
            "description(简短标签), cwd(可选工作目录), allowed_tools(可选工具列表)",
        ),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict | None = None,
                 skill_manager=None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self._skill_manager = skill_manager
        self._on_progress = None  # callback(event) for real-time SSE

    def set_progress_callback(self, callback):
        """设置进度回调，用于实时推送 SSE 事件"""
        self._on_progress = callback

    def execute(self, tasks: list, **kwargs) -> ToolResult:
        if not tasks or not isinstance(tasks, list):
            return ToolResult.fail("tasks 必须是非空列表")

        if not self.llm_config.get("api_key"):
            return ToolResult.fail("LLM 配置缺失，无法创建子 Agent")

        # 过滤有效任务，并提前发送 subagent_start 事件
        valid_tasks = [t for t in tasks if isinstance(t, dict) and t.get("prompt")]
        if not valid_tasks:
            return ToolResult.fail("没有有效的子 Agent 任务（缺少 prompt）")

        # 发送 subagent_start 事件
        cb = self._on_progress
        for i, task in enumerate(valid_tasks):
            if cb:
                cb({
                    "type": "subagent_start",
                    "agent_id": f"sub-{i}",
                    "description": task.get("description", f"task-{i}"),
                })

        # 获取工具定义列表
        tool_manager = self._skill_manager
        all_tool_names = tool_manager.get_all_tool_names() if tool_manager else []

        results: list[SubAgentResult] = []
        with ThreadPoolExecutor(max_workers=min(len(valid_tasks), 6)) as executor:
            futures = {
                executor.submit(
                    self._run_subagent,
                    task, all_tool_names, i
                ): i
                for i, task in enumerate(valid_tasks)
            }
            for future in as_completed(futures):
                results.append(future.result())

        # 恢复原始顺序
        results.sort(key=lambda r: int(r.agent_id.rsplit("-", 1)[-1]) if r.agent_id else 0)

        # 格式化输出
        lines = [f"子 Agent 执行完成: {sum(1 for r in results if r.success)}/{len(results)} 成功\n"]
        for r in results:
            status = "✅" if r.success else "❌"
            lines.append(f"{status} [{r.description}] ({r.turns} 轮)")
            # 输出完整结果（调度器 80K 硬上限保护），末尾截断才加警告
            text = r.content
            if len(text) > 60000:
                text = text[:60000] + "\n...(子Agent输出过长，已截断)"
            lines.append(f"   {text}")
            if r.errors:
                lines.append(f"   错误: {'; '.join(r.errors[:2])}")
            lines.append("")

        return ToolResult.ok(
            "\n".join(lines),
            subagent_count=len(results),
            success_count=sum(1 for r in results if r.success),
            details=[{
                "agent_id": r.agent_id,
                "description": r.description,
                "success": r.success,
                "turns": r.turns,
                "content": r.content,
            } for r in results],
        )

    def _run_subagent(self, task: dict, all_tool_names: list, idx: int) -> SubAgentResult:
        agent_id = f"sub-{idx}"
        subagent_type = task.get("type", "coder")
        prompt = task["prompt"]
        description = task.get("description", f"task-{idx}")
        cwd = task.get("cwd") or self.cwd

        # 确定工具集
        allowed_raw = task.get("allowed_tools")
        if allowed_raw and isinstance(allowed_raw, list):
            allowed_tools = set(allowed_raw)
        elif subagent_type in ("plan", "explore"):
            allowed_tools = set(READONLY_TOOLS)
        else:
            allowed_tools = set(DEFAULT_ALLOWED_TOOLS)

        # 过滤为实际存在的工具，并排除 ask_user（sub agent 不能向用户提问）
        allowed_tools = (allowed_tools & set(all_tool_names)) - {"ask_user"}

        # 读取配置的 max turns；单个任务可通过 max_turns 覆盖
        task_max_turns = task.get("max_turns")
        if isinstance(task_max_turns, int) and task_max_turns > 0:
            max_turns = task_max_turns
        else:
            max_turns = (self._skill_manager.sub_agent_max_turns
                         if self._skill_manager and hasattr(self._skill_manager, 'sub_agent_max_turns')
                         else MAX_SUBAGENT_TURNS)

        config = self.llm_config
        base_url = config.get("base_url", "").rstrip("/")
        api_key = config.get("api_key", "")
        model = config.get("model", "kimi-for-coding")
        protocol = config.get("protocol", "anthropic")

        log.info(
            f"[SubAgent {agent_id}] 启动 | desc={description[:60]} | type={subagent_type} "
            f"| tools={sorted(allowed_tools)} | max_turns={max_turns} "
            f"| model={model} | protocol={protocol}"
        )
        log.debug(f"[SubAgent {agent_id}] prompt: {prompt[:300]}...")

        # 构建 system prompt
        type_desc = {
            "plan": "设计师/规划者，负责设计、架构。只读模式。",
            "coder": "实现者，负责编写代码、修改文件。",
            "explore": "探索者，负责调研、搜索、分析。只读模式。",
        }
        sigma_root = (
            self._skill_manager.skills_root.parent.resolve()
            if self._skill_manager and hasattr(self._skill_manager, "skills_root")
            else Path(__file__).resolve().parents[2]
        )
        project_root = Path(cwd).resolve() if str(cwd) not in ("", ".") else None
        system_prompt = (
            f"你是 Sigma 的子 Agent（{type_desc.get(subagent_type, '')}）。\n"
            f"Sigma 本体目录: {sigma_root}\n"
            f"当前项目目录: {project_root}\n"
            f"工作目录: {cwd}\n"
            "目录规则：Sigma 自身代码、skills 和配置只在 Sigma 本体目录查找；当前项目文件才在当前项目目录查找。\n"
            f"可用工具: {', '.join(sorted(allowed_tools)) if allowed_tools else '无'}\n\n"
            "规则:\n"
            "- 只做分配给你的任务，不越界\n"
            "- 不要与用户交互，直接执行任务\n"
            "- 如果需要创建/修改文件，必须调用 write 工具，不要在回复中只输出内容\n"
            "- 你的回复不会自动保存为文件，必须显式调用工具\n"
            "- 完成任务后输出简洁总结\n"
            "- 遇到无法解决的问题，如实汇报\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        errors: list[str] = []
        turn_count = 0
        client = None
        cb = self._on_progress

        try:
            client = httpx.Client(timeout=120)

            while turn_count < max_turns:
                turn_count += 1

                if cb:
                    cb({"type": "subagent_progress", "agent_id": agent_id, "turn": turn_count,
                        "status": "thinking", "description": description})

                # 构建工具 schema
                tools_schema = self._build_tools_schema(allowed_tools) if allowed_tools else None

                # 调用 LLM
                t_start = time.time()
                log.info(f"[SubAgent {agent_id}] turn={turn_count} 请求 LLM | msg_count={len(messages)}")
                if protocol == "anthropic":
                    resp_data = self._call_anthropic(client, base_url, api_key, model, messages, tools_schema)
                else:
                    resp_data = self._call_openai(client, base_url, api_key, model, messages, tools_schema)
                elapsed = time.time() - t_start
                log.info(f"[SubAgent {agent_id}] turn={turn_count} LLM 响应 | elapsed={elapsed:.1f}s | ok={resp_data is not None}")

                if not resp_data:
                    errors.append(f"LLM 请求失败 (turn {turn_count})")
                    log.warning(
                        f"[SubAgent {agent_id}] LLM 调用失败 | turn={turn_count} "
                        f"| protocol={protocol} | errors_so_far={errors}"
                    )
                    # LLM 调用失败 → 直接返回失败，不走 max-turns 总结路径
                    result = SubAgentResult(
                        agent_id=agent_id, success=False,
                        content=f"LLM 调用失败（第 {turn_count} 轮）", turns=turn_count,
                        description=description, errors=errors,
                    )
                    if cb:
                        cb({"type": "subagent_result", "agent_id": agent_id,
                            "success": False, "content": f"LLM 调用失败 (turn {turn_count})",
                            "turns": turn_count, "description": description})
                    return result

                # 解析响应
                content = resp_data.get("content", "")
                tool_calls = resp_data.get("tool_calls", [])

                if tool_calls:
                    log.info(
                        f"[SubAgent {agent_id}] turn={turn_count} | "
                        f"tool_calls={[tc['function']['name'] for tc in tool_calls]} "
                        f"| text_len={len(content)}"
                    )
                else:
                    log.info(
                        f"[SubAgent {agent_id}] turn={turn_count} | "
                        f"no tools | text_len={len(content)} | text_preview={content[:150]}"
                    )

                if not tool_calls:
                    result = SubAgentResult(
                        agent_id=agent_id, success=True,
                        content=content or "(空回复)", turns=turn_count,
                        description=description, errors=errors,
                    )
                    log.info(
                        f"[SubAgent {agent_id}] 完成 | turns={turn_count} "
                        f"| content_len={len(content)} | errors={errors}"
                    )
                    if cb:
                        cb({"type": "subagent_result", "agent_id": agent_id,
                            "success": True, "content": content[:200], "turns": turn_count,
                            "description": description})
                    return result

                # 添加 assistant 消息
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                messages.append(assistant_msg)

                # 执行工具
                tool_results_msg = {"role": "user", "content": []}
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    call_id = tc.get("id", "")

                    if tool_name not in allowed_tools:
                        result_text = f"无权使用工具: {tool_name}"
                        log.warning(f"[SubAgent {agent_id}] 越权工具调用: {tool_name}")
                    else:
                        try:
                            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            log.debug(f"[SubAgent {agent_id}] 执行工具: {tool_name} | args_keys={list(args.keys())}")
                            tool_manager = self._skill_manager
                            if tool_manager:
                                result = tool_manager.dispatch(tool_name, **args)
                                result_text = result.content[:8000]
                                log.debug(
                                    f"[SubAgent {agent_id}] 工具结果: {tool_name} "
                                    f"| success={getattr(result, 'success', '?')} "
                                    f"| len={len(result_text)}"
                                )
                            else:
                                result_text = "SkillManager 不可用"
                                log.error(f"[SubAgent {agent_id}] SkillManager 不可用")
                        except Exception as e:
                            result_text = f"工具执行失败: {e}"
                            log.error(f"[SubAgent {agent_id}] 工具异常: {tool_name} | {e}")

                    tool_results_msg["content"].append({
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": result_text,
                    })
                messages.append(tool_results_msg)

            # 达到最大轮次 → 让 LLM 做阶段性总结再返回
            log.warning(
                f"[SubAgent {agent_id}] 达到最大轮次 | turns={turn_count}/{max_turns} "
                f"| errors={errors}"
            )
            max_turns_msg = (
                f"\n\n⚠️ 已达到最大工具调用轮次 ({max_turns} 轮)。"
                f"请根据以上所有已读内容做阶段性总结，说明：\n"
                f"1. 已完成的子任务和关键发现\n"
                f"2. 尚未完成的部分\n"
                f"3. 对未完成部分的建议搜索词或操作\n\n"
                f"直接输出总结，不要调用工具。"
            )
            messages.append({"role": "user", "content": max_turns_msg})

            # 再做一次 LLM 调用获取总结
            try:
                log.info(f"[SubAgent {agent_id}] 请求总结 | errors={errors}")
                t_start = time.time()
                if protocol == "anthropic":
                    resp_data = self._call_anthropic(client, base_url, api_key, model, messages, tools_schema=None)
                else:
                    resp_data = self._call_openai(client, base_url, api_key, model, messages, tools_schema=None)
                elapsed = time.time() - t_start
                if resp_data:
                    content = resp_data.get("content", "")
                    content = f"[已达 {max_turns} 轮工具调用上限, 以下为阶段性总结]\n\n{content}"
                    log.info(f"[SubAgent {agent_id}] 总结完成 | elapsed={elapsed:.1f}s | len={len(content)}")
                else:
                    content = f"已达到 {max_turns} 轮上限, 未完成任务请主 Program 重新调度。"
                    log.warning(f"[SubAgent {agent_id}] 总结调用失败 | elapsed={elapsed:.1f}s")
            except Exception as e:
                content = f"已达到 {max_turns} 轮上限, 未完成任务请主 Program 重新调度。"
                log.error(f"[SubAgent {agent_id}] 总结异常: {e}")

            result = SubAgentResult(
                agent_id=agent_id, 
                success=len(errors) == 0,  # 有错误则视为失败
                content=content, turns=turn_count,
                description=description, errors=errors,
            )
            if cb:
                cb({"type": "subagent_result", "agent_id": agent_id,
                    "success": True, "content": content[:200], "turns": turn_count,
                    "description": description})
            return result

        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")
            log.error(
                f"[SubAgent {agent_id}] 异常终止 | {type(e).__name__}: {e} "
                f"| turns={turn_count} | errors={errors}"
            )
            result = SubAgentResult(
                agent_id=agent_id, success=False,
                content=f"执行异常: {e}", turns=turn_count,
                description=description, errors=errors,
            )
            if cb:
                cb({"type": "subagent_result", "agent_id": agent_id,
                    "success": False, "content": str(e)[:200], "turns": turn_count,
                    "description": description})
            return result
        finally:
            if client:
                client.close()

    def _call_anthropic(self, client, base_url, api_key, model, messages, tools_schema) -> dict | None:
        """Anthropic Messages API"""
        body = {
            "model": model,
            "max_tokens": 16384,
            "messages": self._convert_messages_anthropic(messages),
        }
        if tools_schema:
            body["tools"] = tools_schema

        url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
        try:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code != 200:
                log.warning(
                    f"[SubAgent API] Anthropic HTTP {resp.status_code} | "
                    f"url={url} | body={resp.text[:300]}"
                )
                return None
            data = resp.json()
            return self._parse_anthropic_response(data)
        except Exception as e:
            log.warning(f"[SubAgent API] Anthropic 异常: {type(e).__name__}: {e} | url={url}")
            return None

    def _call_openai(self, client, base_url, api_key, model, messages, tools_schema) -> dict | None:
        """OpenAI Chat Completions API"""
        openai_msgs = self._convert_messages_openai(messages)
        body = {
            "model": model,
            "messages": openai_msgs,
            "max_tokens": 16384,
        }
        if tools_schema:
            body["tools"] = tools_schema

        url = f"{base_url}/chat/completions"
        try:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if resp.status_code != 200:
                log.warning(
                    f"[SubAgent API] OpenAI HTTP {resp.status_code} | "
                    f"url={url} | body={resp.text[:300]}"
                )
                return None
            data = resp.json()
            return self._parse_openai_response(data)
        except Exception as e:
            log.warning(f"[SubAgent API] OpenAI 异常: {type(e).__name__}: {e} | url={url}")
            return None

    def _build_tools_schema(self, tool_names: set) -> list:
        """从 tool_names 构建 Anthropic 格式的 tools schema"""
        if not self._skill_manager:
            return []
        tools = []
        for name in tool_names:
            try:
                inst = self._skill_manager._get_instance(name)
                tools.append(inst.to_anthropic_tool())
            except Exception:
                pass
        return tools

    # ── 消息格式转换 ──

    def _convert_messages_anthropic(self, messages: list) -> list:
        result = []
        for m in messages:
            role = m["role"]
            if role == "system":
                result.append({"role": "system", "content": m["content"]})
            elif role == "assistant":
                entry: dict = {"role": "assistant", "content": []}
                if m.get("content"):
                    entry["content"].append({"type": "text", "text": m["content"]})
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        entry["content"].append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"]),
                        })
                result.append(entry)
            elif role == "user" and isinstance(m.get("content"), list):
                entry = {"role": "user", "content": []}
                for item in m["content"]:
                    if item.get("type") == "tool_result":
                        entry["content"].append({
                            "type": "tool_result",
                            "tool_use_id": item["tool_use_id"],
                            "content": item["content"],
                        })
                result.append(entry)
            else:
                result.append({"role": "user", "content": str(m.get("content", ""))})
        return result

    def _convert_messages_openai(self, messages: list) -> list:
        result = []
        for m in messages:
            role = m["role"]
            if role == "assistant":
                entry: dict = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    entry["tool_calls"] = m["tool_calls"]
                result.append(entry)
            elif role == "user" and isinstance(m.get("content"), list):
                entry = {"role": "tool", "content": ""}
                for item in m["content"]:
                    if item.get("type") == "tool_result":
                        entry["content"] = item["content"]
                result.append(entry)
            else:
                result.append({"role": m["role"], "content": str(m.get("content", ""))})
        return result

    def _parse_anthropic_response(self, data: dict) -> dict:
        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
        return {"content": "".join(text_parts), "tool_calls": tool_calls}

    def _parse_openai_response(self, data: dict) -> dict:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        return {
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls", []),
        }
