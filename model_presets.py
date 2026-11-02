"""模型预设注册表 —— Sigma 模型能力的唯一数据源。

参考 Trae 的分层：
    服务商预设(provider) → 模型预设(model) → 用户覆盖(高级配置)

本文件只描述「模型能做什么、默认值是多少、参数怎么发」，
不描述界面怎么画。前端通过 /api/model-presets 读取同一份数据渲染表单，
避免前后端各维护一套硬编码。

新增模型时只改这里：
    1. 如果是新的一类参数约定，新增 Family；
    2. 在 MODELS 里追加 ModelPreset，引用已有 Family；
    3. 不需要改 context_manager / server / tool_loop。
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ── 思考档位 ──

# 统一档位 id。default = 跟随模型默认（不注入任何参数）。
THINKING_OPTION_IDS = (
    "default", "off", "on", "auto", "low", "medium", "high", "xhigh", "max",
)

# 旧配置（adaptive/enabled/disabled）到新档位的映射，仅用于兼容读取
LEGACY_THINKING_ALIASES = {
    "adaptive": "default",
    "enabled": "on",
    "disabled": "off",
}


def normalize_thinking(mode: str | None) -> str:
    """把历史配置值归一成新的档位 id。"""
    value = (mode or "").strip()
    if not value:
        return "default"
    value = LEGACY_THINKING_ALIASES.get(value, value)
    return value if value in THINKING_OPTION_IDS else "default"


@dataclass(frozen=True)
class SamplingSpec:
    """一个采样参数在某个模型上是否可用及其默认值。"""

    supported: bool = False
    default: float | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class Family:
    """一类模型的参数约定。

    同一厂商的多个模型通常共用一套思考参数格式，差异放在 Family 里，
    ModelPreset 只引用 Family 并覆盖模型特有的窗口/输出等数值。
    """

    id: str
    label: str
    # 各协议下、各档位要注入的请求参数；None = 不注入（跟随模型默认）
    params: dict[str, dict[str, dict | None]] = field(default_factory=dict)
    # 当前协议下该档位无效时，改走哪个协议才能生效
    protocol_fallback: dict[str, dict[str, str]] = field(default_factory=dict)
    # 最大输出字段名：Kimi K3 的 OpenAI 端点要求 max_completion_tokens
    max_tokens_field: dict[str, str] = field(
        default_factory=lambda: {"openai": "max_tokens", "anthropic": "max_tokens"}
    )
    # 思考内容是否随 assistant 历史回传；None = 不回传
    history_field: str | None = None
    options: tuple[str, ...] = ("default",)
    temperature: SamplingSpec = SamplingSpec()
    top_p: SamplingSpec = SamplingSpec()
    top_k: SamplingSpec = SamplingSpec()
    # 给界面看的补充说明（例如关闭思考会路由到另一个模型）
    thinking_note: str = ""

    def options_for(self, protocol: str) -> tuple[str, ...]:
        """该协议下真正可用的档位：参数为 None 且没有回退协议的档位不展示。"""
        available = []
        for option in self.options:
            if option == "default":
                available.append(option)
                continue
            if (self.params.get(protocol) or {}).get(option) is not None:
                available.append(option)
                continue
            target = (self.protocol_fallback.get(protocol) or {}).get(option)
            if target and (self.params.get(target) or {}).get(option) is not None:
                available.append(option)
        return tuple(available)


# ── 厂商 ──

@dataclass(frozen=True)
class ProviderPreset:
    id: str
    label: str
    default_protocol: str
    # 各协议下的默认请求地址，仅用于新建时带出，用户可改
    base_urls: dict[str, str] = field(default_factory=dict)
    # 是否提供余额/用量查询接口（前端据此决定是否展示余额，后端据此决定是否受理）
    supports_balance: bool = False


PROVIDERS: dict[str, ProviderPreset] = {
    "kimi-code": ProviderPreset(
        id="kimi-code",
        label="Kimi Code",
        default_protocol="openai",
        base_urls={
            "openai": "https://api.kimi.com/coding",
            "anthropic": "https://api.kimi.com/coding",
        },
        supports_balance=True,
    ),
    "deepseek": ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        default_protocol="openai",
        base_urls={
            "openai": "https://api.deepseek.com",
            "anthropic": "https://api.deepseek.com/anthropic",
        },
        supports_balance=True,
    ),
    "minimax": ProviderPreset(
        id="minimax",
        label="MiniMax",
        default_protocol="anthropic",
        base_urls={
            # 与 Anthropic 端点保持同一 host；minimaxi.com / minimax.chat 亦可
            "openai": "https://api.minimax.cn/v1",
            "anthropic": "https://api.minimax.cn/anthropic",
        },
        supports_balance=True,
    ),
    "ark": ProviderPreset(
        id="ark",
        label="火山方舟",
        default_protocol="openai",
        base_urls={
            "openai": "https://ark.cn-beijing.volces.com/api/v3",
            "anthropic": "https://ark.cn-beijing.volces.com/api/compatible",
        },
        supports_balance=True,
    ),
    "anthropic": ProviderPreset(
        id="anthropic",
        label="Anthropic",
        default_protocol="anthropic",
        base_urls={"anthropic": "https://api.anthropic.com"},
    ),
    "generic": ProviderPreset(
        id="generic",
        label="通用 / 自定义",
        default_protocol="anthropic",
        base_urls={"anthropic": "", "openai": ""},
    ),
}


# ── 模型家族（参数约定） ──

FAMILIES: dict[str, Family] = {
    # Kimi 全系 temperature/top_p 都固定（1.0 / 0.95），传其他值会报错，所以一律不注入。
    #
    # K3（k3 / k3-256k）：reasoning_effort low/high/max（默认 high）。
    #   实测：OpenAI 端点 reasoning_effort=low 思考量约 300 字符，明显低于默认；
    #   Anthropic 端点忽略顶层 reasoning_effort，改用 output_config.effort；
    #   传 thinking.disabled 不会报错，服务端路由到 K2.8 Preview 的无思考版。
    "kimi-k3": Family(
        id="kimi-k3",
        label="Kimi K3 系列",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "low": {"reasoning_effort": "low"},
                "high": {"reasoning_effort": "high"},
                "max": {"reasoning_effort": "max"},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "low": {"output_config": {"effort": "low"}},
                "high": {"output_config": {"effort": "high"}},
                "max": {"output_config": {"effort": "max"}},
            },
        },
        max_tokens_field={"openai": "max_completion_tokens", "anthropic": "max_tokens"},
        history_field="thinking",
        options=("default", "off", "low", "high", "max"),
        temperature=SamplingSpec(supported=False, default=1.0),
        top_p=SamplingSpec(supported=False, default=0.95),
        thinking_note="关闭思考会由服务端路由到 K2.8 Preview 的无思考版。",
    ),
    # K3.1 Pro（k3.1-pro / k3.1-pro-highspeed）：仅支持思考模式，关闭会被 400 拒绝。
    # 档位与 K3 相同，low 在 Anthropic 端点走 output_config.effort。
    "kimi-k31": Family(
        id="kimi-k31",
        label="Kimi K3.1 Pro 系列",
        params={
            "openai": {
                "default": None,
                "low": {"reasoning_effort": "low"},
                "high": {"reasoning_effort": "high"},
                "max": {"reasoning_effort": "max"},
            },
            "anthropic": {
                "default": None,
                "low": {"output_config": {"effort": "low"}},
                "high": {"output_config": {"effort": "high"}},
                "max": {"output_config": {"effort": "max"}},
            },
        },
        max_tokens_field={"openai": "max_completion_tokens", "anthropic": "max_tokens"},
        history_field="thinking",
        options=("default", "low", "high", "max"),
        temperature=SamplingSpec(supported=False, default=1.0),
        top_p=SamplingSpec(supported=False, default=0.95),
        thinking_note="仅支持思考模式，关闭请求会被拒绝；低档走 output_config.effort。",
    ),
    # K2.8 Preview（kimi-for-coding）：reasoning_effort low/high/max（默认 max）。
    # 关闭思考会由服务端路由到 K2.8 的无思考版，实测返回 200 且无 reasoning 内容。
    "kimi-k28": Family(
        id="kimi-k28",
        label="Kimi K2.8 Preview",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "low": {"reasoning_effort": "low"},
                "high": {"reasoning_effort": "high"},
                "max": {"reasoning_effort": "max"},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "low": {"output_config": {"effort": "low"}},
                "high": {"output_config": {"effort": "high"}},
                "max": {"output_config": {"effort": "max"}},
            },
        },
        history_field="thinking",
        options=("default", "off", "low", "high", "max"),
        temperature=SamplingSpec(supported=False, default=1.0),
        top_p=SamplingSpec(supported=False, default=0.95),
        thinking_note="关闭思考会路由到 K2.8 Preview 的无思考版。",
    ),
    # K2.7 Code（kimi-for-coding-highspeed）：没有强度档，reasoning_effort 被忽略。
    # 官方文档说不支持关闭，但在 Kimi Code 端点实测 thinking.disabled 返回 200（路由到 K2.8 无思考版）。
    "kimi-k27": Family(
        id="kimi-k27",
        label="Kimi K2.7 Code",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
            },
        },
        history_field="thinking",
        options=("default", "off"),
        temperature=SamplingSpec(supported=False, default=1.0),
        top_p=SamplingSpec(supported=False, default=0.95),
        thinking_note="不支持强度档；选择关闭会路由到 K2.8 Preview 的无思考版。",
    ),
    # Kimi K2.6：只有 thinking 开关，没有强度档；温度固定，不可设置。
    "kimi-k26": Family(
        id="kimi-k26",
        label="Kimi K2.6 系列",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "enabled"}},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "enabled"}},
            },
        },
        history_field="thinking",
        options=("default", "off", "on"),
        temperature=SamplingSpec(supported=False),
        top_p=SamplingSpec(supported=False, default=0.95),
    ),
    # DeepSeek V4：thinking 开关 + reasoning_effort。OpenAI 端点直接用 effort，
    # Anthropic 兼容端点官方支持 output_config.effort，但没有 low 档（实测低档会被忽略）。
    "deepseek-v4": Family(
        id="deepseek-v4",
        label="DeepSeek V4 系列",
        params={
            "openai": {
                "default": None,
                "off": {"reasoning_effort": "none"},
                "low": {"reasoning_effort": "low"},
                "high": {"reasoning_effort": "high"},
                "max": {"reasoning_effort": "max"},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "high": {"thinking": {"type": "enabled"}, "output_config": {"effort": "high"}},
                "max": {"thinking": {"type": "enabled"}, "output_config": {"effort": "max"}},
            },
        },
        # 注意：DeepSeek 的 Anthropic 端点 baseUrl 带 /anthropic 后缀，
        # 不能像 Kimi 那样跨协议改发请求，因此低档在 Anthropic 端点不做协议切换。
        options=("default", "off", "low", "high", "max"),
        temperature=SamplingSpec(supported=True, default=None, minimum=0, maximum=2),
        top_p=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
        thinking_note="Anthropic 端点没有低档；实测关闭思考会让多步计算题出错，简单题不受影响。",
    ),
    # MiniMax M3：thinking 自适应开关，没有强度档；temperature/top_p 官方默认 1.0/0.95。
    "minimax-m3": Family(
        id="minimax-m3",
        label="MiniMax M3 系列",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "adaptive"}},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "adaptive"}},
            },
        },
        options=("default", "off", "on"),
        temperature=SamplingSpec(supported=True, default=1.0, minimum=0, maximum=2),
        top_p=SamplingSpec(supported=True, default=0.95, minimum=0, maximum=1),
    ),
    # MiniMax M3.1：reasoning_effort 多档；官方不接受 disabled（会 400），因此没有 off。
    "minimax-m31": Family(
        id="minimax-m31",
        label="MiniMax M3.1 系列",
        params={
            "openai": {
                "default": None,
                "low": {"reasoning_effort": "low"},
                "medium": {"reasoning_effort": "medium"},
                "high": {"reasoning_effort": "high"},
                "xhigh": {"reasoning_effort": "xhigh"},
                "max": {"reasoning_effort": "max"},
            },
            "anthropic": {
                "default": None,
                "low": {"output_config": {"effort": "low"}},
                "medium": {"output_config": {"effort": "medium"}},
                "high": {"output_config": {"effort": "high"}},
                "xhigh": {"output_config": {"effort": "xhigh"}},
                "max": {"output_config": {"effort": "max"}},
            },
        },
        options=("default", "low", "medium", "high", "xhigh", "max"),
        temperature=SamplingSpec(supported=True, default=1.0, minimum=0, maximum=2),
        top_p=SamplingSpec(supported=True, default=0.95, minimum=0, maximum=1),
        thinking_note="实测只有 3 档有效：low≈medium、high≈max≈xhigh、不传档位思考最深；两个协议都无法关闭思考。",
    ),
    # 火山方舟（豆包）：只有开关/自动三态，没有强度档；Anthropic 兼容端点用 budget_tokens。
    "ark-doubao": Family(
        id="ark-doubao",
        label="豆包 Seed 系列",
        params={
            "openai": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "enabled"}},
                "auto": {"thinking": {"type": "auto"}},
            },
            "anthropic": {
                "default": None,
                "off": {"thinking": {"type": "disabled"}},
                "on": {"thinking": {"type": "enabled", "budget_tokens": 16000}},
                "auto": {"thinking": {"type": "enabled", "budget_tokens": 8000}},
            },
        },
        options=("default", "off", "on", "auto"),
        temperature=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
        top_p=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
    ),
    # Claude 系列：Anthropic 协议用 budget_tokens 控思考预算；不能真正关闭思考。
    "claude": Family(
        id="claude",
        label="Claude 系列",
        params={
            "anthropic": {
                "default": None,
                "on": {"thinking": {"type": "enabled", "budget_tokens": 16000}},
                "low": {"thinking": {"type": "enabled", "budget_tokens": 2048}},
            },
        },
        # 保持既有行为：只有 Kimi Code 系回传思考内容，Claude 代理端不回传，避免签名校验问题
        history_field=None,
        options=("default", "low", "on"),
        temperature=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
        top_p=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
    ),
    # 自定义模型（未命中预设）：
    # OpenAI 协议只发规范内的 effort，Anthropic 协议用 budget_tokens，
    # 不支持的能力一律不注入，避免把 400 抛给用户。
    "generic-openai": Family(
        id="generic-openai",
        label="通用 OpenAI 兼容",
        params={
            "openai": {
                "default": None,
                "low": {"reasoning_effort": "low"},
                "medium": {"reasoning_effort": "medium"},
                "high": {"reasoning_effort": "high"},
            },
        },
        options=("default", "low", "medium", "high"),
        temperature=SamplingSpec(supported=True, default=None, minimum=0, maximum=2),
        top_p=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
    ),
    "generic-anthropic": Family(
        id="generic-anthropic",
        label="通用 Anthropic 兼容",
        params={
            "anthropic": {
                "default": None,
                "low": {"thinking": {"type": "enabled", "budget_tokens": 2048}},
                "on": {"thinking": {"type": "enabled", "budget_tokens": 16000}},
            },
        },
        options=("default", "low", "on"),
        temperature=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
        top_p=SamplingSpec(supported=True, default=None, minimum=0, maximum=1),
    ),
}


# ── 模型预设 ──

@dataclass(frozen=True)
class ModelPreset:
    provider: str
    model: str
    label: str
    family: str
    context: int
    max_output: int | None = None
    recommended_max_tokens: int = 16384
    vision: bool = False
    tool_call: bool = True
    # 模型级覆盖（不填则继承 Family）
    protocol: str | None = None


# 顺序即前端下拉顺序
MODELS: tuple[ModelPreset, ...] = (
    # Kimi Code（官方模型 ID 见 kimi.com/code/docs/kimi-code/models）
    ModelPreset("kimi-code", "k3.1-pro", "Kimi K3.1 Pro", "kimi-k31", 1_048_576, 1_048_576, 131_072, vision=True),
    ModelPreset("kimi-code", "k3.1-pro-highspeed", "Kimi K3.1 Pro Highspeed", "kimi-k31", 1_048_576, 1_048_576, 131_072, vision=True),
    # 旧配置里出现过 kimi-k3.1-pro，保留别名以便自动匹配
    ModelPreset("kimi-code", "kimi-k3.1-pro", "Kimi K3.1 Pro (旧 ID)", "kimi-k31", 1_048_576, 1_048_576, 131_072, vision=True),
    ModelPreset("kimi-code", "k3", "Kimi K3", "kimi-k3", 1_048_576, 1_048_576, 131_072, vision=True),
    ModelPreset("kimi-code", "k3-256k", "Kimi K3 (256K)", "kimi-k3", 262_144, 1_048_576, 131_072, vision=True),
    ModelPreset("kimi-code", "kimi-for-coding", "Kimi K2.8 Preview", "kimi-k28", 1_048_576, 65_536, 32_768, vision=True),
    ModelPreset("kimi-code", "kimi-for-coding-highspeed", "Kimi K2.7 Code Highspeed", "kimi-k27", 262_144, 32_768, 32_768, vision=True),
    # 开放平台 ID（api.moonshot.ai），与 Kimi Code 套餐 ID 区分
    ModelPreset("kimi-code", "kimi-k2.7-code", "Kimi K2.7 Code (开放平台 ID)", "kimi-k27", 262_144, 32_768, 32_768, vision=True),
    ModelPreset("kimi-code", "kimi-k2.6", "Kimi K2.6", "kimi-k26", 262_144, 32_768, 32_768, vision=True),

    # DeepSeek（官方：OpenAI 与 Anthropic 两种格式都是 1M 上下文、最大输出 384K）
    # 视觉能力只有 flash 支持，v4-pro 官方明确标注 Not supported。
    ModelPreset("deepseek", "deepseek-flash", "DeepSeek V4.1 Flash", "deepseek-v4", 1_000_000, 393_216, 32_768, vision=True),
    ModelPreset("deepseek", "deepseek-v4-pro", "DeepSeek V4 Pro", "deepseek-v4", 1_000_000, 393_216, 32_768),
    # 兼容旧模型 ID（官方仍保留，分别对应非思考 / 思考模式）
    ModelPreset("deepseek", "deepseek-chat", "DeepSeek Chat (旧 ID)", "deepseek-v4", 1_000_000, 393_216, 32_768),
    ModelPreset("deepseek", "deepseek-reasoner", "DeepSeek Reasoner (旧 ID)", "deepseek-v4", 1_000_000, 393_216, 32_768),

    # MiniMax（M3 起官方支持文本 / 图片 / 视频输入，两种协议都支持）
    ModelPreset("minimax", "MiniMax-M3", "MiniMax M3", "minimax-m3", 1_000_000, 65_536, 32_768, vision=True),
    ModelPreset("minimax", "minimax-m3", "MiniMax M3 (小写)", "minimax-m3", 1_000_000, 65_536, 32_768, vision=True),
    ModelPreset("minimax", "MiniMax-M3.1", "MiniMax M3.1", "minimax-m31", 1_000_000, 65_536, 32_768, vision=True),
    ModelPreset("minimax", "MiniMax-M3.1-Flash", "MiniMax M3.1 Flash", "minimax-m31", 1_000_000, 65_536, 32_768, vision=True),

    # 火山方舟
    ModelPreset("ark", "doubao-seed-2-1-pro-260628", "豆包 Seed 2.1 Pro", "ark-doubao", 256_000, 32_768, 16_384, vision=True),
    ModelPreset("ark", "doubao-seed-2-1-pro", "豆包 Seed 2.1 Pro (别名)", "ark-doubao", 256_000, 32_768, 16_384, vision=True),

    # Anthropic（官方直连）
    ModelPreset("anthropic", "claude-opus-5-5", "Claude Opus 5.5", "claude", 200_000, 64_000, 16_384, vision=True),
    ModelPreset("anthropic", "claude-sonnet-5-5", "Claude Sonnet 5.5", "claude", 200_000, 64_000, 16_384, vision=True),
    ModelPreset("anthropic", "claude-opus-4-6", "Claude Opus 4.6", "claude", 200_000, 32_000, 16_384, vision=True),
    ModelPreset("anthropic", "claude-fable-5", "Claude Fable 5", "claude", 200_000, 32_000, 16_384, vision=True),
)


# ── 查询 ──

def _match_model(model: str) -> ModelPreset | None:
    """按模型 id 精确匹配，其次按最长前缀匹配（兼容日期后缀等差异）。"""
    target = (model or "").strip().lower()
    if not target:
        return None
    for preset in MODELS:
        if preset.model.lower() == target:
            return preset
    best: ModelPreset | None = None
    for preset in MODELS:
        key = preset.model.lower()
        if target.startswith(key) and (best is None or len(key) > len(best.model)):
            best = preset
    return best


def find_preset(provider: str | None, model: str | None) -> ModelPreset | None:
    """先按 provider + model 精确命中，再退化为按 model 全局命中。

    退化匹配是为了让用户挂在自定义中转地址上的官方模型也能拿到能力描述，
    同时保留用户自己的 baseUrl / provider 不变。
    """
    target_provider = (provider or "").strip().lower()
    target_model = (model or "").strip().lower()
    if target_model:
        for preset in MODELS:
            if preset.provider == target_provider and preset.model.lower() == target_model:
                return preset
    return _match_model(target_model)


def get_family(family_id: str | None, protocol: str = "anthropic") -> Family:
    if family_id and family_id in FAMILIES:
        return FAMILIES[family_id]
    return FAMILIES["generic-openai" if protocol == "openai" else "generic-anthropic"]


def family_for(provider: str | None, model: str | None, protocol: str = "anthropic") -> Family:
    preset = find_preset(provider, model)
    if preset:
        return FAMILIES[preset.family]
    return get_family(None, protocol)


def resolve_effective_protocol(
    provider: str | None, protocol: str, thinking: str | None, model: str | None = None
) -> str:
    """当前协议无法让该档位生效时，返回真正能生效的协议。"""
    option = normalize_thinking(thinking)
    family = family_for(provider, model, protocol)
    if option == "default":
        return protocol
    if (family.params.get(protocol) or {}).get(option) is not None:
        return protocol
    target = (family.protocol_fallback.get(protocol) or {}).get(option)
    if target and (family.params.get(target) or {}).get(option) is not None:
        return target
    return protocol


def thinking_params(
    provider: str | None, protocol: str, thinking: str | None, model: str | None = None
) -> dict | None:
    """返回该档位在指定协议下应注入的参数；None 表示不注入。"""
    option = normalize_thinking(thinking)
    family = family_for(provider, model, protocol)
    return (family.params.get(protocol) or {}).get(option)


def max_tokens_field(
    provider: str | None, protocol: str, model: str | None = None
) -> str:
    family = family_for(provider, model, protocol)
    return family.max_tokens_field.get(protocol, "max_tokens")


def keep_thinking_history(provider: str | None, model: str | None = None) -> bool:
    """该模型是否需要把思考内容随 assistant 历史回传。"""
    return family_for(provider, model).history_field is not None


# ── 视觉请求的思考压制策略（读图 / 截图理解 / 抽帧复审） ──
# 技能级覆盖：无论用户给该模型配了什么档位，视觉请求都按下面的顺序压制思考。
#   1. 模型支持关闭 → 强制关闭；
#   2. 不支持关闭（如 K3.1 / M3.1 / Claude）→ 退到最低强度档；
#   3. 当前协议都控制不了 → 不注入，由模型默认决定。
# 参数本身来自模型家族，不在视觉层重复维护厂商映射。
def vision_thinking_candidates(
    provider: str | None, protocol: str, model: str | None = None
) -> list[dict]:
    family = family_for(provider, model, protocol)
    params_for = family.params.get(protocol) or {}
    candidates: list[dict] = []
    for option in ("off", "low"):
        params = params_for.get(option)
        if params:
            candidates.append(dict(params))
    candidates.append({})
    return candidates


def resolve_vision_request(
    provider: str, protocol: str, model: str | None = None
) -> tuple[str, list[dict]]:
    """返回视觉请求应使用的（协议，按优先级排列的思考参数候选列表）。"""
    return protocol, vision_thinking_candidates(provider, protocol, model)


# ── 给前端的序列化 ──

def _sampling_payload(spec: SamplingSpec) -> dict | None:
    if not spec.supported:
        return None
    return {
        "default": spec.default,
        "min": spec.minimum,
        "max": spec.maximum,
    }


def preset_payload(preset: ModelPreset) -> dict:
    family = FAMILIES[preset.family]
    protocol = preset.protocol or PROVIDERS[preset.provider].default_protocol
    return {
        "provider": preset.provider,
        "providerLabel": PROVIDERS[preset.provider].label,
        "model": preset.model,
        "label": preset.label,
        "family": family.id,
        "familyLabel": family.label,
        "protocol": protocol,
        "baseUrl": PROVIDERS[preset.provider].base_urls.get(protocol, ""),
        "context": preset.context,
        "maxOutput": preset.max_output,
        "recommendedMaxTokens": preset.recommended_max_tokens,
        "vision": preset.vision,
        "toolCall": preset.tool_call,
        # 两种协议都支持的档位取并集，具体选项由用户在表单里切换协议后仍可用
        "thinkingOptions": sorted(
            set(family.options_for("openai")) | set(family.options_for("anthropic")),
            key=lambda o: (THINKING_OPTION_IDS.index(o) if o in THINKING_OPTION_IDS else 99),
        ),
        # 表单按当前协议只展示该协议真正支持/可切换的档位
        "thinkingOptionsByProtocol": {
            "anthropic": list(family.options_for("anthropic")),
            "openai": list(family.options_for("openai")),
        },
        "thinkingNote": family.thinking_note,
        "sampling": {
            "temperature": _sampling_payload(family.temperature),
            "topP": _sampling_payload(family.top_p),
            "topK": _sampling_payload(family.top_k),
        },
    }


def registry_payload() -> dict:
    """前端渲染用：服务商 + 模型 + 家族清单。"""
    grouped: dict[str, list[dict]] = {pid: [] for pid in PROVIDERS}
    for preset in MODELS:
        grouped.setdefault(preset.provider, []).append(preset_payload(preset))
    providers = [
        {
            "id": provider.id,
            "label": provider.label,
            "defaultProtocol": provider.default_protocol,
            "baseUrls": provider.base_urls,
            "supportsBalance": provider.supports_balance,
            "models": grouped.get(provider.id, []),
        }
        for provider in PROVIDERS.values()
    ]
    families = [
        {
            "id": family.id,
            "label": family.label,
            "options": list(family.options),
            "thinkingOptions": list(
                family.options_for("openai") if "openai" in family.params else family.options_for("anthropic")
            ),
            "temperature": _sampling_payload(family.temperature) is not None,
            "topP": _sampling_payload(family.top_p) is not None,
            "topK": _sampling_payload(family.top_k) is not None,
        }
        for family in FAMILIES.values()
    ]
    return {"providers": providers, "families": families}
