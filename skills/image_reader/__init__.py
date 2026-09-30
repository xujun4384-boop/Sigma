"""
image_reader skill - 读取图片并通过主 LLM 识别内容。

子 Agent 模式下使用，继承主 LLM 配置，无需独立 Vision API。
"""
import base64
import io
import json
import urllib.request as ur
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ImageReaderTool(BaseTool):
    name = "read_image"
    description = (
        "读取本地图片并通过主 LLM 识别内容。"
        "自动压缩图片以减少 token 消耗，返回文本描述。"
        "image_quality=high 用于文字/表格，balanced 用于一般理解，low 用于快速预览。"
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

        # 检查 LLM 配置
        api_key = self.llm_config.get("api_key")
        base_url = self.llm_config.get("base_url", "").rstrip("/")
        model = self.llm_config.get("model", "")
        protocol = self.llm_config.get("protocol", "anthropic")

        if not api_key or not base_url or not model:
            return ToolResult.fail("LLM 配置不完整，无法识别图片")

        try:
            # 读取并压缩图片
            img_b64, mime_type = self._compress_image(full_path, image_quality)
            
            # 调用主 LLM 识别图片
            result_text = self._call_llm_with_image(
                api_key=api_key,
                base_url=base_url,
                model=model,
                protocol=protocol,
                image_b64=img_b64,
                mime_type=mime_type,
                prompt=prompt or "请详细描述这张图片的内容，包括所有文字、表格、图表和关键信息。"
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

    def _call_llm_with_image(self, api_key: str, base_url: str, model: str, protocol: str,
                             image_b64: str, mime_type: str, prompt: str) -> str:
        """调用主 LLM API 识别图片"""
        if protocol == "anthropic":
            return self._call_anthropic(api_key, base_url, model, image_b64, mime_type, prompt)
        else:
            return self._call_openai(api_key, base_url, model, image_b64, mime_type, prompt)

    def _call_anthropic(self, api_key: str, base_url: str, model: str,
                       image_b64: str, mime_type: str, prompt: str) -> str:
        """调用 Anthropic 协议 API（强制关闭 thinking）"""
        request_url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
        
        body = json.dumps({
            "model": model,
            "max_tokens": 2000,
            "thinking": {"type": "disabled"},  # 强制关闭 thinking，避免拖慢速度
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_b64}},
                ],
            }],
        }).encode("utf-8")

        req = ur.Request(
            request_url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        
        with ur.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        # 提取文本内容
        content = data.get("content", [])
        text = ""
        for block in content:
            if block.get("type") == "text":
                text += block.get("text", "")
        
        return text.strip()

    def _call_openai(self, api_key: str, base_url: str, model: str,
                    image_b64: str, mime_type: str, prompt: str) -> str:
        """调用 OpenAI 协议 API（强制关闭 thinking）"""
        request_url = f"{base_url}/v1/chat/completions" if "/v1" not in base_url else f"{base_url}/chat/completions"
        
        body = json.dumps({
            "model": model,
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }],
        }).encode("utf-8")

        req = ur.Request(
            request_url,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        
        with ur.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        # 提取文本内容
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
        
        return ""
