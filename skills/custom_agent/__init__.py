"""
custom_agent skill - 调用用户自定义的专用 Agent

主 LLM 通过 custom_agent 工具调用用户创建的自定义 Agent。
每个 Agent 使用用户预设的 system_prompt、工具集和模型独立执行。
上下文隔离，与现有 sub_agent 行为一致。
"""
import json
import time
from pathlib import Path
import httpx
from dataclasses import dataclass, field

from skills.base import BaseTool, ToolParameter, ToolResult
from sigma_logger import log

DEFAULT_MAX_TURNS = 8  # fallback 值


class CustomAgentTool(BaseTool):
    name = "custom_agent"
    description = (
        "调用用户自定义的专用 Agent 执行特定领域任务。"
        "每个自定义 Agent 拥有独特的系统提示词、工具集和模型配置。"
        "适用于需要特定专业知识或固定工作流的任务。"
        "传入 agent_name 指定要调用的 Agent，prompt 描述任务内容。"
    )
    parameters = [
        ToolParameter(
            "agent_name",
            "string",
            "要调用的自定义 Agent 名称（用户在设置中创建的）",
        ),
        ToolParameter(
            "prompt",
            "string",
            "发送给 Agent 的任务描述。应详细说明期望 Agent 完成的工作。",
        ),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None, agent_manager=None, agent_llm_config: dict = None):
        super().__init__(cwd)
        self._skill_manager = skill_manager
        self._agent_manager = agent_manager
        self._agent_llm_config = agent_llm_config  # 特定 Agent 的自有 LLM 配置
        self._on_progress = None

    def _build_dynamic_description(self) -> str:
        """动态生成工具描述，包含可用的 Agent 列表"""
        base = self.description
        if not self._agent_manager:
            return base
        agents = self._agent_manager.list_all()
        if not agents:
            return base + "\n\n当前没有可用的自定义 Agent。"
        agent_lines = ["\n\n可用的自定义 Agent:"]
        for a in agents:
            tools_str = ", ".join(a.get("tools", []))
            agent_lines.append(
                f"- {a['name']}: {a.get('description', '无描述')}（工具: {tools_str}）"
            )
        return base + "\n".join(agent_lines)

    def to_anthropic_tool(self) -> dict:
        """导出 Anthropic 格式，动态注入 Agent 列表"""
        result = super().to_anthropic_tool()
        result["description"] = self._build_dynamic_description()
        return result

    def to_openai_tool(self) -> dict:
        """导出 OpenAI 格式，动态注入 Agent 列表"""
        result = super().to_openai_tool()
        result["function"]["description"] = self._build_dynamic_description()
        return result

    def set_progress_callback(self, callback):
        self._on_progress = callback

    def execute(self, agent_name: str, prompt: str, **kwargs) -> ToolResult:
        if not self._agent_manager:
            return ToolResult.fail("CustomAgentManager 未初始化")

        agent = self._agent_manager.get(agent_name)
        if not agent:
            available = [a["name"] for a in self._agent_manager.list_all()]
            return ToolResult.fail(
                f"未找到自定义 Agent: {agent_name}。"
                + (f"可用 Agent: {', '.join(available)}" if available else "当前没有可用的自定义 Agent。")
            )

        if not self._skill_manager:
            return ToolResult.fail("SkillManager 不可用")

        all_tool_names = self._skill_manager.get_all_tool_names()
        agent_tools = set(agent.get("tools", []))
        allowed_tools = (agent_tools & set(all_tool_names)) - {"ask_user", "custom_agent"}

        agent_model = agent.get("model", "")
        system_prompt = agent.get("system_prompt", "")

        if not system_prompt.strip():
            return ToolResult.fail(f"Agent {agent_name} 未设置 system_prompt")

        llm_config = self._resolve_llm_config(agent_model)
        if not llm_config:
            return ToolResult.fail(f"无法解析 Agent {agent_name} 的模型配置: {agent_model}")

        base_url = llm_config["base_url"].rstrip("/")
        api_key = llm_config["api_key"]
        model = llm_config["model"]
        protocol = llm_config.get("protocol", "anthropic")

        log.info(
            f"[CustomAgent] 启动 | name={agent_name} | model={model} "
            f"| tools={sorted(allowed_tools)} | protocol={protocol}"
        )

        # 构建消息，注入 Sigma 本体目录和当前项目目录等上下文
        enhanced_prompt = system_prompt.strip()
        sigma_root = (
            self._skill_manager.skills_root.parent.resolve()
            if self._skill_manager and hasattr(self._skill_manager, "skills_root")
            else Path(__file__).resolve().parents[2]
        )
        project_root = Path(self.cwd).resolve() if self.cwd and str(self.cwd) not in ("", ".") else None
        enhanced_prompt += (
            f"\n\nSigma 本体目录: {sigma_root}"
            f"\n当前项目目录: {project_root}"
            f"\n工作目录: {self.cwd}"
            "\n目录规则：Sigma 自身代码、skills 和配置只在 Sigma 本体目录查找；当前项目文件才在当前项目目录查找。"
        )

        messages = [
            {"role": "system", "content": enhanced_prompt},
            {"role": "user", "content": prompt},
        ]

        errors = []
        turn_count = 0
        cb = self._on_progress
        client = None

        # 使用系统设置中的 sub_agent_max_turns，与子 Agent 一致
        max_turns = DEFAULT_MAX_TURNS
        if self._skill_manager and hasattr(self._skill_manager, "sub_agent_max_turns"):
            max_turns = self._skill_manager.sub_agent_max_turns or DEFAULT_MAX_TURNS

        try:
            client = httpx.Client(timeout=120)

            # 发送 agent_start 事件（让前端创建 agent_execution 块）
            if cb:
                cb({
                    "type": "agent_start",
                    "agent_name": agent_name,
                    "tools": sorted(allowed_tools),
                    "model": model,
                })

            while turn_count < max_turns:
                turn_count += 1

                if cb:
                    cb({
                        "type": "agent_turn",
                        "agent_name": agent_name,
                        "turn": turn_count,
                        "status": "thinking",
                    })

                tools_schema = self._build_tools_schema(allowed_tools) if allowed_tools else None

                t_start = time.time()
                if protocol == "anthropic":
                    resp_data = self._call_anthropic(client, base_url, api_key, model, messages, tools_schema)
                else:
                    resp_data = self._call_openai(client, base_url, api_key, model, messages, tools_schema)
                elapsed = time.time() - t_start
                log.info(f"[CustomAgent {agent_name}] turn={turn_count} LLM响应 | elapsed={elapsed:.1f}s")

                if not resp_data:
                    errors.append(f"LLM 请求失败 (turn {turn_count})")
                    return ToolResult.fail(f"Agent {agent_name} LLM 调用失败（第 {turn_count} 轮）")

                content = resp_data.get("content", "")
                tool_calls = resp_data.get("tool_calls", [])

                # 推送 Agent 的思考内容到前端
                if cb and content:
                    cb({
                        "type": "agent_think",
                        "agent_name": agent_name,
                        "content": content,
                        "turn": turn_count,
                    })

                if not tool_calls:
                    log.info(f"[CustomAgent {agent_name}] 完成 | turns={turn_count} | len={len(content)}")
                    if cb:
                        cb({"type": "agent_complete", "agent_name": agent_name, "turns": turn_count})
                    return ToolResult.ok(content)

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
                        log.warning(f"[CustomAgent {agent_name}] 越权工具: {tool_name}")
                    else:
                        try:
                            args = json.loads(tc.get("function", {}).get("arguments", "{}"))

                            # 如果 agent 有进度回调且当前调用的是 sub_agent/batch_read，
                            # 注入回调以实时推送子 Agent 进度到前端
                            if cb and tool_name in ("sub_agent", "batch_read"):
                                inst = self._skill_manager._get_instance(tool_name)
                                if inst and hasattr(inst, "set_progress_callback"):
                                    inst.set_progress_callback(cb)

                            result = self._skill_manager.dispatch(tool_name, **args)
                            result_text = result.content[:8000]
                        except Exception as e:
                            result_text = f"工具执行失败: {e}"
                            log.error(f"[CustomAgent {agent_name}] 工具异常: {tool_name} | {e}")

                    tool_results_msg["content"].append({
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": result_text,
                    })

                    if cb:
                        cb({
                            "type": "agent_tool_call",
                            "agent_name": agent_name,
                            "turn": turn_count,
                            "tool_name": tool_name,
                        })
                        cb({
                            "type": "agent_tool_result",
                            "agent_name": agent_name,
                            "turn": turn_count,
                            "tool_name": tool_name,
                            "result": result_text,
                            "success": "工具执行失败" not in result_text,
                        })

                messages.append(tool_results_msg)

            # 达到最大轮次，请求总结
            log.warning(f"[CustomAgent {agent_name}] 达到最大轮次 {max_turns}")
            messages.append({
                "role": "user",
                "content": (
                    f"\n\n已达到最大工具调用轮次 ({max_turns} 轮)。"
                    f"请根据以上所有内容做阶段性总结，直接输出结果，不要调用工具。"
                ),
            })
            try:
                if protocol == "anthropic":
                    resp_data = self._call_anthropic(client, base_url, api_key, model, messages, None)
                else:
                    resp_data = self._call_openai(client, base_url, api_key, model, messages, None)
                if resp_data:
                    content = f"[已达 {max_turns} 轮上限，以下为阶段性总结]\n\n{resp_data.get('content', '')}"
            except Exception as e:
                content = f"已达到 {max_turns} 轮上限，未完成任务。错误: {e}"

            if cb:
                cb({"type": "agent_complete", "agent_name": agent_name, "turns": turn_count})
            return ToolResult.ok(content)

        except Exception as e:
            log.error(f"[CustomAgent {agent_name}] 异常: {type(e).__name__}: {e}")
            if cb:
                cb({"type": "agent_complete", "agent_name": agent_name, "turns": turn_count})
            return ToolResult.fail(f"Agent {agent_name} 执行异常: {e}")
        finally:
            if client:
                client.close()

    def _resolve_llm_config(self, agent_model: str) -> dict | None:
        """根据 Agent 指定的模型名解析完整 LLM 配置。
        优先使用 Agent 自身的 llm_config，回退到 SkillManager 的配置。
        模型名决定 API 端点（kimi-* → Kimi Anthropic，deepseek-* → DeepSeek）。"""
        # Agent 有自有 LLM 配置（通过 sync 携带的 llm_config）
        if self._agent_llm_config:
            cfg = dict(self._agent_llm_config)
            if agent_model:
                cfg["model"] = agent_model
            self._fix_provider_mismatch(cfg, agent_model)
            return cfg

        # 回退到 SkillManager 的 LLM 配置
        base = self._skill_manager.llm_config if self._skill_manager else {}
        if not base:
            return None
        config = dict(base)
        if agent_model:
            config["model"] = agent_model
        self._fix_provider_mismatch(config, agent_model)
        return config

    def _fix_provider_mismatch(self, config: dict, agent_model: str):
        """如果模型名指向 Kimi 但 base_url 不是 Kimi 端点，自动修正。"""
        if not agent_model:
            return
        base_url = config.get("base_url", "")
        # kimi-* 模型必须走 Kimi 端点
        if agent_model.startswith("kimi-") and "kimi.com" not in base_url:
            config["base_url"] = "https://api.kimi.com/coding/"
            config["protocol"] = "anthropic"

    # ── 以下方法复用 SubAgentTool 的 LLM 调用逻辑 ──

    def _build_tools_schema(self, tool_names: set) -> list:
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

    def _call_anthropic(self, client, base_url, api_key, model, messages, tools_schema) -> dict | None:
	        converted = self._convert_messages_anthropic(messages)
	        system_parts = [m["content"] for m in converted if m.get("role") == "system"]
	        non_system = [m for m in converted if m.get("role") != "system"]
	        body = {
	            "model": model,
	            "max_tokens": 16384,
	            "messages": non_system,
	        }
	        if system_parts:
	            body["system"] = "\n\n".join(system_parts)
	        if tools_schema:
	            body["tools"] = tools_schema

	        url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
	        try:
	            resp = client.post(
	                url,
	                headers={
	                    "Authorization": f"Bearer {api_key}",
	                    "x-api-key": api_key,
	                    "anthropic-version": "2023-06-01",
	                    "Content-Type": "application/json",
	                },
	                json=body,
	            )
	            if resp.status_code != 200:
	                log.warning(f"[CustomAgent API] Anthropic HTTP {resp.status_code} | {resp.text[:300]}")
	                return None
	            return self._parse_anthropic_response(resp.json())
	        except Exception as e:
	            log.warning(f"[CustomAgent API] Anthropic 异常: {e}")
	            return None

    def _call_openai(self, client, base_url, api_key, model, messages, tools_schema) -> dict | None:
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
                log.warning(f"[CustomAgent API] OpenAI HTTP {resp.status_code} | {resp.text[:300]}")
                return None
            return self._parse_openai_response(resp.json())
        except Exception as e:
            log.warning(f"[CustomAgent API] OpenAI 异常: {e}")
            return None

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
