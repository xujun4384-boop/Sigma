"""
Sigma 上下文管理器 —— token 估算、压缩、用量追踪

参照 LLaMDA 设计：
  - estimate_tokens() 按 JSON 字符数 / 2.5 估算
  - compact_if_needed() 在超限时用 LLM 生成历史摘要
  - 每次 LLM 调用后更新用量百分比，推送 SSE 事件给前端
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

CHARS_PER_TOKEN = 1.8  # 中英混合估算（中文约1.3字符/token, 英文约4字符/token）

# 各模型上下文窗口大小（tokens）
MODEL_CONTEXT_SIZES: dict[str, int] = {
    "kimi-for-coding": 200_000,
    "kimi-for-coding-thinking": 200_000,
    "k3": 1_048_576,
    "deepseek-chat": 1_000_000,
    "deepseek-reasoner": 1_000_000,
}
DEFAULT_CONTEXT_SIZE = 200_000

# 需要强制开启 thinking 的模型配置（Anthropic 协议格式）
MODEL_THINKING_CONFIGS: dict[str, dict] = {
    "k3": {"type": "enabled", "effort": "max", "budget_tokens": 16000},
}
THINKING_OUTPUT_PAD = 4096

# 压缩触发阈值（上下文 50% 时触发压缩，防止 LLM 在大上下文下失焦漏参数）
COMPACT_THRESHOLD = 0.50


@dataclass
class CompactResult:
    summary: str                  # LLM 生成的中文摘要
    removed_messages: list[dict]  # 被移除的早期消息
    preserved_tail: list[dict]    # 保留的近期消息
    boundary_id: str              # 保留尾部的索引标识


def estimate_tokens(msgs: list[dict]) -> int:
    """估算消息列表的 token 数量（字符数 / 2.5）"""
    chars = sum(
        len(json.dumps(m, ensure_ascii=False, default=str))
        for m in msgs
    )
    return int(chars / CHARS_PER_TOKEN)


def get_context_size(model: str) -> int:
    """获取模型上下文窗口大小"""
    return MODEL_CONTEXT_SIZES.get(model, DEFAULT_CONTEXT_SIZE)


def get_compact_threshold(model: str) -> int:
    """获取触发压缩的 token 阈值"""
    return int(get_context_size(model) * COMPACT_THRESHOLD)


def apply_model_specific_params(payload: dict, model: str, protocol: str) -> dict:
    """
    根据模型特性注入额外参数（如 K3 强制 thinking）。
    仅在配置表中命中的模型才会被修改，不影响其他模型。
    """
    cfg = MODEL_THINKING_CONFIGS.get(model)
    if not cfg:
        return payload

    if protocol == "anthropic":
        payload["thinking"] = cfg.copy()
        # Anthropic 要求 max_tokens 必须大于 thinking budget
        min_tokens = cfg["budget_tokens"] + THINKING_OUTPUT_PAD
        payload["max_tokens"] = max(payload.get("max_tokens", 0), min_tokens)
    elif protocol == "openai":
        payload["reasoning_effort"] = cfg.get("effort", "max")

    return payload


class ContextTracker:
    """
    上下文用量追踪器

    - 追踪当前 messages 的估算 token 数
    - 计算用量百分比（相对模型上下文窗口）
    - 支持持久化到 session 文件
    """

    def __init__(self, model: str = ""):
        self.model = model
        self.current_tokens: int = 0
        self.max_tokens: int = get_context_size(model)

    @property
    def usage_ratio(self) -> float:
        """当前用量比例 0.0 ~ 1.0"""
        if self.max_tokens == 0:
            return 0.0
        return min(self.current_tokens / self.max_tokens, 1.0)

    @property
    def usage_percent(self) -> int:
        """当前用量百分比 0 ~ 100"""
        return int(self.usage_ratio * 100)

    def update(self, messages: list[dict], system_prompt: str = ""):
        """根据当前消息列表 + system prompt 更新 token 估算"""
        msg_tokens = estimate_tokens(messages)
        # system prompt 的 token 估算（字符数 / 2.5）
        sys_tokens = int(len(system_prompt) / CHARS_PER_TOKEN) if system_prompt else 0
        self.current_tokens = msg_tokens + sys_tokens

    def set_model(self, model: str):
        """切换模型时更新上下文窗口大小"""
        self.model = model
        self.max_tokens = get_context_size(model)

    def to_dict(self) -> dict:
        return {
            "current_tokens": self.current_tokens,
            "max_tokens": self.max_tokens,
            "usage_percent": self.usage_percent,
            "usage_ratio": self.usage_ratio,
        }


def _find_message_boundary(msgs: list[dict]) -> int:
    """确定压缩边界：保留最近 2 轮完整交互（含 tool_call/tool_result 配对），不拆散"""
    user_indices = [i for i, m in enumerate(msgs) if m["role"] == "user"]
    if len(user_indices) <= 2:
        return -1  # 轮次太少，不压缩

    # 从倒数第 2 个 user 消息开始，往前找到完整的轮次边界
    boundary = user_indices[-2]

    # 如果边界 user 消息包含 tool_result，往前找对应的 assistant (tool_call)
    # 确保不会拆散 tool_call ↔ tool_result 配对
    if boundary > 0:
        prev_msg = msgs[boundary - 1]
        if prev_msg.get("role") == "assistant":
            has_tool_use = any(
                isinstance(b, dict) and b.get("type") == "tool_use"
                for b in (prev_msg.get("content") or []) if isinstance(b, dict)
            )
            if has_tool_use:
                # 这个 assistant 消息是边界 user 的配对 tool_call，必须保留
                boundary = boundary - 1

    return boundary


def _format_messages_for_summary(msgs: list[dict]) -> str:
    """将消息列表格式化为摘要用的纯文本"""
    parts = []
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        # 处理 tool_use / tool_result 类型的 content（可能是数组）
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "tool_use":
                        text_parts.append(f"[调用工具 {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        c = block.get("content", "")
                        text_parts.append(f"[工具结果] {str(c)[:200]}")
                    elif block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                else:
                    text_parts.append(str(block))
            content = " ".join(text_parts)
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


async def compact_if_needed(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    system_prompt: str = "",
    protocol: str = "anthropic",
) -> CompactResult | None:
    """
    若上下文 token 超限，则用 LLM 对早期轮次生成摘要。
    返回 CompactResult 或 None（未触发压缩）。
    system_prompt 计入 token 判断，防止实际用量超出阈值。
    protocol: "anthropic" 或 "openai"，决定 API 调用方式。
    """
    threshold = get_compact_threshold(model)
    sys_tokens = int(len(system_prompt) / CHARS_PER_TOKEN) if system_prompt else 0
    if estimate_tokens(messages) + sys_tokens <= threshold:
        return None

    boundary = _find_message_boundary(messages)
    if boundary == -1:
        return None  # 轮次太少，即使超长也不压缩

    head = messages[:boundary]
    tail = messages[boundary:]

    summary = await _generate_summary(head, model, base_url, api_key, protocol)
    if summary is None:
        return None

    boundary_id = str(boundary)
    return CompactResult(
        summary=summary,
        removed_messages=head,
        preserved_tail=tail,
        boundary_id=boundary_id,
    )


async def _generate_summary(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    protocol: str = "anthropic",
) -> str | None:
    """调用 LLM 对历史消息生成摘要。支持 Anthropic 和 OpenAI 协议。"""
    formatted = _format_messages_for_summary(messages)
    summary_system = "你是一个对话摘要助手。请用中文总结以下用户和 AI 的对话，保留关键事实、文件路径、操作内容和结论。尽可能详细，确保后续对话能接续。字数控制在 800 字以内。"

    try:
        import httpx

        if protocol == "openai":
            payload = {
                "model": model,
                "max_tokens": 1500,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": summary_system},
                    {"role": "user", "content": f"请总结以下对话：\n\n{formatted}"},
                ],
            }
            apply_model_specific_params(payload, model, protocol)

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/v1/chat/completions" if "/v1" not in base_url else f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                return text.strip() or None
        else:
            # Anthropic 协议（默认）
            payload = {
                "model": model,
                "max_tokens": 1500,
                "temperature": 0.3,
                "system": summary_system,
                "messages": [
                    {"role": "user", "content": f"请总结以下对话：\n\n{formatted}"}
                ],
            }
            apply_model_specific_params(payload, model, "anthropic")

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                content = data.get("content", [])
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
                return text.strip() or None
    except Exception:
        return None


# ─── Session 状态（纯内存） ───

class SessionState:
    """会话状态：已激活 skill 列表 + skill_specs_cache + 压缩历史摘要。纯内存，重启即清空。"""

    def __init__(self):
        self.injected_skills: set[str] = set()
        self.skill_specs_cache: str = ""
        self.history_summary: str = ""      # 上下文压缩后的历史摘要，跨请求持久

    def activate_skill(self, skill_name: str, spec: str):
        """激活一个 skill，追加其完整文档到缓存"""
        if skill_name in self.injected_skills:
            return
        self.injected_skills.add(skill_name)
        self.skill_specs_cache += (
            f"\n\n[已激活技能: {skill_name}]\n{spec}"
        )
