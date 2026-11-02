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

from model_presets import (
    find_preset,
    family_for,
    keep_thinking_history as _keep_thinking_history,
    max_tokens_field,
    normalize_thinking,
    resolve_effective_protocol as _resolve_effective_protocol,
    resolve_vision_request as _resolve_vision_request,
    thinking_params,
)

CHARS_PER_TOKEN = 1.8  # 中英混合估算（中文约1.3字符/token, 英文约4字符/token）

DEFAULT_CONTEXT_SIZE = 200_000

# 思考参数约定已经迁移到 model_presets.py 的 FAMILIES / MODELS。
# 这里只保留对外的兼容封装，供 tool_loop / sub_agent / image_reader 复用。


# 视觉识别（读图 / 抽帧复审）的低耗思考参数登记在 model_presets.VISION_THINKING_PARAMS，
# 这里转发一层，保持 image_reader 等调用方无需感知注册表位置。
def resolve_vision_request(
    provider: str, protocol: str, model: str | None = None
) -> tuple[str, list[dict]]:
    return _resolve_vision_request(provider, protocol, model)


# 长输出生成（视频代码 / HTML / TSX / 蓝图 / 脚本）的统一输出预算。
# 思考 token 与正文共用 max_tokens，且实际经常是思考量超过正文；若只按正文估算，
# 思考会先把额度吃光并触发截断。因此统一按整体给足，并保证回退档位仍是"正文能写完"的水位。
LONG_OUTPUT_MAX_TOKENS = 128_000
LONG_OUTPUT_TOKEN_FALLBACKS = (96_000, 64_000, 32_000)


def resolve_effective_protocol(
    provider: str, protocol: str, thinking_mode: str, model: str | None = None
) -> str:
    """返回实际应使用的协议（当前协议无法让该档位生效时自动切换）。"""
    return _resolve_effective_protocol(provider, protocol, thinking_mode, model)


def keep_thinking_history(provider: str, model: str | None = None) -> bool:
    """该模型是否需要把思考内容随历史回传（由模型家族声明）。"""
    return _keep_thinking_history(provider, model)


def thinking_preview(
    provider: str, protocol: str, thinking_mode: str, model: str | None = None
) -> str:
    """给前端显示「这一档实际会发什么」，避免设置是黑箱。"""
    effective = resolve_effective_protocol(provider, protocol, thinking_mode, model)
    params = thinking_params(provider, effective, thinking_mode, model)
    prefix = "" if effective == protocol else f"[{protocol} 端点不支持该档位，实际改用 {effective} 协议] "
    if params is None:
        return prefix + "不注入 thinking 参数（跟随模型默认）"
    return prefix + json.dumps(params, ensure_ascii=False)


def _inject_thinking_params(
    payload: dict, provider: str, protocol: str, thinking_mode: str, model: str | None = None
) -> None:
    """按模型家族注入该档位对应的 thinking 控制参数。"""
    params = thinking_params(provider, protocol, thinking_mode, model)
    if params:
        payload.update(params)

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


def get_context_size(
    model: str, configured_size: int | None = None, provider: str | None = None
) -> int:
    """获取模型上下文窗口大小（优先使用用户显式配置的窗口）。

    查找顺序：
    1. 用户配置的 configured_size
    2. 模型预设注册表（model_presets）
    3. 默认值 DEFAULT_CONTEXT_SIZE
    """
    if configured_size:
        return int(configured_size)

    preset = find_preset(provider, model)
    if preset:
        return int(preset.context)

    return DEFAULT_CONTEXT_SIZE


def get_compact_threshold(
    model: str, configured_size: int | None = None, provider: str | None = None
) -> int:
    """获取触发压缩的 token 阈值"""
    return int(get_context_size(model, configured_size, provider) * COMPACT_THRESHOLD)


def apply_model_specific_params(payload: dict, model: str, protocol: str, llm_params: dict | None = None) -> dict:
    """按模型预设注入请求参数。

    优先级：用户显式传值 > 预设默认值 > 不注入。
    模型不支持的采样参数不会出现在请求体里，避免把 400 抛给用户。
    """
    params = llm_params or {}
    provider = params.get("provider", "generic")
    thinking = normalize_thinking(params.get("thinking"))

    # 思考档位（协议切换已由 resolve_effective_protocol 在构造请求前完成）
    _inject_thinking_params(payload, provider, protocol, thinking, model)

    # 采样参数：只在模型声明支持时才注入
    preset = find_preset(provider, model)
    family = family_for(provider, model, protocol)
    specs = {
        "temperature": family.temperature,
        "top_p": family.top_p,
        "top_k": family.top_k,
    }
    for key, spec in specs.items():
        if not spec.supported:
            continue
        value = params.get(key)
        if value is None:
            # 调用方已显式设置的值优先于预设默认值
            if key in payload:
                continue
            value = spec.default
        if value is None:
            continue
        if spec.minimum is not None and value < spec.minimum:
            value = spec.minimum
        if spec.maximum is not None and value > spec.maximum:
            value = spec.maximum
        payload[key] = value

    # 输出上限：用户显式值 > 调用方已设置的值 > 预设推荐值；同时受模型最大输出约束
    field = max_tokens_field(provider, protocol, model)
    alt_field = "max_tokens" if field == "max_completion_tokens" else "max_completion_tokens"
    value = params.get("max_tokens")
    if value is None:
        value = payload.get(field, payload.get(alt_field))
    if value is None and preset:
        value = preset.recommended_max_tokens
    if value is not None:
        if preset and preset.max_output:
            value = min(int(value), int(preset.max_output))
        payload.pop(alt_field, None)
        payload[field] = int(value)

    return payload


class ContextTracker:
    """
    上下文用量追踪器

    - 追踪当前 messages 的估算 token 数
    - 计算用量百分比（相对模型上下文窗口）
    - 支持持久化到 session 文件
    """

    def __init__(self, model: str = "", context_size: int | None = None, provider: str | None = None):
        self.model = model
        self.provider = provider
        self._configured_context_size = context_size
        self.current_tokens: int = 0
        self.max_tokens: int = get_context_size(model, context_size, provider)

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
        self.max_tokens = get_context_size(model, self._configured_context_size, self.provider)

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
    context_size: int | None = None,
) -> CompactResult | None:
    """
    若上下文 token 超限，则用 LLM 对早期轮次生成摘要。
    返回 CompactResult 或 None（未触发压缩）。
    system_prompt 计入 token 判断，防止实际用量超出阈值。
    protocol: "anthropic" 或 "openai"，决定 API 调用方式。
    """
    threshold = int(get_context_size(model, context_size) * COMPACT_THRESHOLD)
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
                        "Authorization": f"Bearer {api_key}",
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
