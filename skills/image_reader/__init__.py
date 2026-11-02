"""
image_reader skill - 读取图片并通过主 LLM 识别内容。

已正式暴露给主 LLM（图片不再经 batch_read 绕子 Agent），子 Agent 也可直接复用；
继承主 LLM 配置，无需独立 Vision API。
"""
import base64
import io
import json
import urllib.request as ur
from pathlib import Path
from urllib.error import HTTPError

from context_manager import resolve_vision_request
from sigma_logger import log
from vision_llm import get_vision_llm_config
from skills.base import BaseTool, ToolParameter, ToolResult

# 读图默认只做「看懂 + 概述」，不要求逐字转写。
# 实测同一张 1024px 截图：详细描述提示 30.7s，概述提示 6.9s，差 4 倍以上——
# 因为「详细描述所有文字表格」本身就是分析任务，会放大思考量和输出长度。
DEFAULT_PROMPT = (
    "简要说明这张图片是什么，并列出关键可见信息（重要文字、数字、表格）。"
    "只描述看到的，不要推理、推测或展开，控制在 200 字以内。"
)
# 需要逐字提取时（OCR、票据、表格）由调用方显式传 prompt 或 image_quality=high。
DETAILED_PROMPT = "请详细描述这张图片的内容，包括所有文字、表格、图表和关键信息。"

# 输出上限。思考 token 与正文共用额度：详细模式需要 8K，
# 默认概述模式正文很短，4K 足够，也避免个别模型借额度写长文。
VISION_MAX_TOKENS = 8192
VISION_MAX_TOKENS_BRIEF = 4096

# 视觉请求默认超时。重思考模型（如 Kimi K3.1）单图思考可达 50~60 秒，
# 60 秒会卡在临界点反复超时，这里给到 120 秒。
VISION_TIMEOUT = 120.0


def _build_vision_request(base_url: str, api_key: str, model: str, protocol: str,
                          image_b64: str, mime_type: str, prompt: str,
                          extra: dict, max_tokens: int = VISION_MAX_TOKENS) -> tuple:
    """按协议组装视觉请求，返回 (url, body_bytes, headers)。extra 为思考控制参数。"""
    if protocol == "anthropic":
        request_url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_b64}},
        ]
        headers = {
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        request_url = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
        ]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    payload.update(extra or {})
    return request_url, json.dumps(payload).encode("utf-8"), headers


def _post_vision_request(api_key: str, base_url: str, model: str, protocol: str,
                         image_b64: str, mime_type: str, prompt: str,
                         provider: str = "generic", timeout: float = VISION_TIMEOUT,
                         max_tokens: int = VISION_MAX_TOKENS) -> str:
    """把一张图交给指定 LLM 识别，返回文本。协议自动适配 anthropic / openai。

    这是「主程序看图」的唯一底层出入口，read_image 与 computer_use 等共用，避免各写一套。
    思考控制：按 provider + protocol 注入低耗参数；端点无法控制思考时按登记表切换协议
    （如 Kimi Code 的 Anthropic 端点 → 同 host 的 OpenAI 端点）。
    """
    base_url = (base_url or "").rstrip("/")
    eff_protocol, param_list = resolve_vision_request(provider, protocol, model)

    def _send(url: str, data: bytes, hdrs: dict) -> dict:
        req = ur.Request(url, data=data, headers=hdrs)
        with ur.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # 依次尝试：关闭思考 → 低强度 → 不带参数 → 回退原协议（取第一个成功的结果）。
    # 只对 4xx（参数/能力不被接受）降级；超时或 5xx 直接抛出，避免把等待翻倍。
    attempts = [(eff_protocol, p) for p in param_list]
    for cand in ((eff_protocol, {}), (protocol, {})):
        if cand not in attempts:
            attempts.append(cand)

    data = None
    ok_protocol = eff_protocol
    last_err = None
    for idx, (proto, params) in enumerate(attempts):
        try:
            url, body, headers = _build_vision_request(
                base_url, api_key, model, proto, image_b64, mime_type, prompt, params, max_tokens)
            data = _send(url, body, headers)
            ok_protocol = proto
            break
        except HTTPError as e:
            if not (400 <= e.code < 500) or idx == len(attempts) - 1:
                raise
            last_err = e
            log.warning(
                f"[Vision] {provider}/{proto} 请求被拒({e.code})，改用降级方案重试")
    if data is None:
        raise last_err or RuntimeError("视觉请求失败")

    if ok_protocol == "anthropic":
        return "".join(
            b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
        ).strip()
    choices = data.get("choices", [])
    if choices:
        return (choices[0].get("message", {}).get("content") or "").strip()
    return ""


def describe_image_b64(image_b64: str, mime_type: str, prompt: str,
                       llm_config: dict, timeout: float = VISION_TIMEOUT,
                       prefer_vision_llm: bool = True,
                       max_tokens: int = VISION_MAX_TOKENS) -> str:
    """用「读图专用 LLM」识别一张 base64 图片，返回文字描述。

    统一入口：read_image、computer_use、抽帧复审等共用同一条看图链路。
    若 Settings 里指定了读图专用模型，优先使用它（强制低耗思考）；
    未指定时才回落到调用方传入的 llm_config。
    配置键同时兼容 snake_case（主程序内部）与 camelCase（前端同步）。
    """
    vision_cfg = get_vision_llm_config() if prefer_vision_llm else None
    cfg = vision_cfg or llm_config or {}
    api_key = cfg.get("api_key") or cfg.get("apiKey") or ""
    base_url = cfg.get("base_url") or cfg.get("baseUrl") or ""
    model = cfg.get("model") or ""
    protocol = cfg.get("protocol") or "anthropic"
    provider = cfg.get("provider") or "generic"
    if not api_key or not base_url or not model:
        raise RuntimeError("LLM 配置不完整，无法识别图片")
    return _post_vision_request(api_key, base_url, model, protocol,
                                image_b64, mime_type, prompt, provider, timeout, max_tokens)


class ImageReaderTool(BaseTool):
    name = "read_image"
    description = (
        "读取本地图片并识别内容（优先使用 Settings 中指定的读图专用模型，未配置则用主 LLM）。"
        "默认只返回简要概述（快）；需要逐字提取文字/表格/票据时传 prompt 或 image_quality=high（慢但完整）。"
        "image_quality：high 文字/表格、balanced 一般理解（默认）、low 快速预览。"
    )
    parameters = [
        ToolParameter("file_path", "string", "图片文件路径"),
        ToolParameter("image_quality", "string", "图片传输档位：high（文字/表格）、balanced（一般理解，默认）、low（快速预览）", required=False, default="balanced"),
        ToolParameter("prompt", "string", "自定义识别提示", required=False),
    ]

    _QUALITY_PROFILES = {
        "high": {"max_size": 1568, "format": "JPEG", "mime_type": "image/jpeg", "save_options": {"quality": 90, "optimize": True}},
        "balanced": {"max_size": 1024, "format": "JPEG", "mime_type": "image/jpeg", "save_options": {"quality": 75, "optimize": True}},
        "low": {"max_size": 512, "format": "JPEG", "mime_type": "image/jpeg", "save_options": {"quality": 50, "optimize": True}},
    }

    def __init__(self, cwd: str = ".", llm_config: dict | None = None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    def execute(self, file_path: str, image_quality: str = "balanced", prompt: str = None, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")

        # 检查文件格式
        ext = full_path.suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            return ToolResult.fail(f"不支持的图片格式: {ext}")

        # 配置校验交给 describe_image_b64：它会优先取读图专用模型，未配置时才用主 LLM
        try:
            # 读取并压缩图片
            img_b64, mime_type = self._compress_image(full_path, image_quality)

            # 复用「主程序看图」统一入口（读图专用模型优先，未配置则回主 LLM）
            custom_prompt = (prompt or "").strip()
            detailed = bool(custom_prompt) or image_quality == "high"
            final_prompt = custom_prompt or (DETAILED_PROMPT if detailed else DEFAULT_PROMPT)
            result_text = describe_image_b64(
                img_b64, mime_type,
                final_prompt,
                self.llm_config,
                max_tokens=VISION_MAX_TOKENS if detailed else VISION_MAX_TOKENS_BRIEF,
            )
            
            return ToolResult.ok(
                result_text,
                file_path=str(full_path),
                image_quality=image_quality,
            )
        except Exception as e:
            return ToolResult.fail(f"图片识别失败: {e}")

    def _compress_image(self, img_path: Path, quality: str) -> tuple[str, str]:
        """压缩图片并转为 base64"""
        from PIL import Image

        profile = self._QUALITY_PROFILES.get(quality, self._QUALITY_PROFILES["balanced"])
        max_size = profile["max_size"]

        img = Image.open(img_path)
        
        # 限制尺寸
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # 转 RGB
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # 保存为 JPEG
        buf = io.BytesIO()
        img.save(buf, format=profile["format"], **profile["save_options"])
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        return img_b64, profile["mime_type"]
