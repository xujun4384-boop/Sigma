"""
自定义 Agent 管理器
在内存中持有前端同步来的自定义 Agent 定义。
供 CustomAgentTool 和 @ 触发模式查询使用。
同时为主 LLM 暴露独立的 Agent 工具池（与 SkillManager 分离）。
"""
import re
from sigma_logger import log

# Agent 工具名前缀，用于区分 Agent 工具和 Skill 工具
AGENT_TOOL_PREFIX = "agent_"


def _agent_name_to_tool(name: str) -> str:
    """将 Agent 名称转为合法的工具名：agent_{字母数字下划线_哈希}，符合 OpenAI tool name 规范"""
    slug = re.sub(r"[^a-zA-Z0-9]", "_", name).lower()
    # 追加短哈希防中文等非 ASCII 名称重名
    import hashlib
    h = hashlib.md5(name.encode()).hexdigest()[:6]
    return f"{AGENT_TOOL_PREFIX}{slug}_{h}"


def _tool_to_agent_name(tool_name: str) -> str:
    """从工具名反查 Agent 名称"""
    if not tool_name.startswith(AGENT_TOOL_PREFIX):
        return ""
    return tool_name[len(AGENT_TOOL_PREFIX):]


def is_agent_tool(tool_name: str) -> bool:
    """判断是否为 Agent 工具"""
    return tool_name.startswith(AGENT_TOOL_PREFIX)


class CustomAgentManager:
    """内存中持有所有自定义 Agent 的定义"""

    def __init__(self):
        self._agents: dict[str, dict] = {}  # name → agent_config
        # name → tool_name 映射，用于反查
        self._agent_tool_names: dict[str, str] = {}

    def sync(self, agents: list[dict]) -> int:
        """前端全量同步 Agent 配置，返回同步数量"""
        self._agents.clear()
        self._agent_tool_names.clear()
        for agent in agents:
            name = agent.get("name", "").strip()
            if not name:
                continue
            self._agents[name] = agent
            self._agent_tool_names[name] = _agent_name_to_tool(name)
        log.info(f"[CustomAgent] 同步完成: {len(self._agents)} 个 Agent")
        return len(self._agents)

    def get(self, name: str) -> dict | None:
        """按名称查找 Agent"""
        return self._agents.get(name)

    def get_by_tool(self, tool_name: str) -> dict | None:
        """按工具名查找 Agent"""
        for name, tn in self._agent_tool_names.items():
            if tn == tool_name:
                return self._agents.get(name)
        return None

    def get_agent_name_by_tool(self, tool_name: str) -> str:
        """按工具名返回 Agent 名称"""
        for name, tn in self._agent_tool_names.items():
            if tn == tool_name:
                return name
        return ""

    def list_all(self) -> list[dict]:
        """列出所有 Agent 的摘要信息（不含 system_prompt）"""
        return [
            {
                "name": a["name"],
                "description": a.get("description", ""),
                "tools": a.get("tools", []),
                "model": a.get("model", ""),
                "capabilities": a.get("capabilities", []),
            }
            for a in self._agents.values()
        ]

    def list_for_llm(self) -> str:
        """
        生成供主 LLM 系统提示用的 Agent 列表描述。
        """
        if not self._agents:
            return ""
        lines = ["## 可用的自定义 Agent"]
        for name, agent in self._agents.items():
            desc = agent.get("description", "").strip()
            tools = agent.get("tools", [])
            tool_str = ", ".join(tools) if tools else "无"
            caps = agent.get("capabilities", [])
            cap_str = f"，接管能力: {', '.join(caps)}" if caps else ""
            line = f"- **{name}**: {desc}（工具: {tool_str}{cap_str}）"
            lines.append(line)
        lines.append(
            "\n如需调用自定义 Agent，使用对应 Agent 的专属工具（agent_ 前缀）。"
        )
        return "\n".join(lines)

    def get_tool_names_for(self, name: str) -> set[str]:
        """获取指定 Agent 允许使用的工具名集合"""
        agent = self._agents.get(name)
        if not agent:
            return set()
        return set(agent.get("tools", []))

    # ── 独立 Agent 工具池（与 SkillManager 分离） ──

    def get_agent_tools_anthropic(self) -> list[dict]:
        """生成所有 Agent 的 Anthropic tool schema（独立池）"""
        tools = []
        for name, agent in self._agents.items():
            tool_name = self._agent_tool_names[name]
            desc = agent.get("description", "").strip()
            tools_str = ", ".join(agent.get("tools", []))
            description = (
                f"调用「{name}」自定义智能体处理任务。"
                f"{desc}。"
                f"该智能体可使用以下工具: {tools_str}。"
                f"对于此智能体擅长的任务类型，请优先使用此工具。"
            )
            tools.append({
                "name": tool_name,
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": f"发送给「{name}」的任务描述，应详细说明期望完成的工作。",
                        },
                    },
                    "required": ["prompt"],
                },
            })
        return tools

    def get_agent_tools_openai(self) -> list[dict]:
        """生成所有 Agent 的 OpenAI tool schema（独立池）"""
        tools = []
        for name, agent in self._agents.items():
            tool_name = self._agent_tool_names[name]
            desc = agent.get("description", "").strip()
            tools_str = ", ".join(agent.get("tools", []))
            description = (
                f"调用「{name}」自定义智能体处理任务。"
                f"{desc}。"
                f"该智能体可使用以下工具: {tools_str}。"
                f"对于此智能体擅长的任务类型，请优先使用此工具。"
            )
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {
                                "type": "string",
                                "description": f"发送给「{name}」的任务描述。",
                            },
                        },
                        "required": ["prompt"],
                    },
                },
            })
        return tools

    def dispatch_agent(self, tool_name: str, prompt: str, skill_manager, progress_callback=None):
        """
        分发 Agent 工具调用，返回 ToolResult。
        与 SkillManager.dispatch 分离，maintain 独立池。

        Args:
            progress_callback: 可选，Agent 内部进度回调，用于实时 SSE 推送
        """
        from skills.base import ToolResult

        agent_name = self.get_agent_name_by_tool(tool_name)
        if not agent_name:
            return ToolResult.fail(f"未找到对应 Agent: {tool_name}")

        agent = self._agents.get(agent_name)
        if not agent:
            return ToolResult.fail(f"Agent 配置不存在: {agent_name}")

        from skills.custom_agent import CustomAgentTool

        tool = CustomAgentTool(
            cwd=str(skill_manager.cwd),
            skill_manager=skill_manager,
            agent_manager=self,
            agent_llm_config=agent.get("llm_config"),  # Agent 自有 LLM 配置
        )
        if progress_callback:
            tool.set_progress_callback(progress_callback)
        try:
            return tool.execute(agent_name=agent_name, prompt=prompt)
        except Exception as e:
            log.error(f"[CustomAgent dispatch] {agent_name} 异常: {e}")
            return ToolResult.fail(f"Agent {agent_name} 执行异常: {e}")


# 全局单例
custom_agent_manager = CustomAgentManager()
