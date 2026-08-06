"""
image_generate skill - AI 图片生成（火山引擎 ARK / OpenAI 兼容接口）

提供 generate_image 工具，根据文本提示词生成图片并保存到本地。
"""
import os
import io
import json
import uuid
import urllib.request
from sigma_logger import log
from skills.base import BaseTool, ToolParameter, ToolResult

DEFAULT_MODEL = "doubao-seedream-4-5-251128"
DEFAULT_SIZE = "2K"


class ImageGenerateTool(BaseTool):
    name = "generate_image"
    description = (
        "根据文本提示词调用 AI 图像生成服务（火山引擎 ARK）生成图片，保存到本地目录。"
        "返回生成图片的文件路径和尺寸信息。"
    )
    parameters = [
        ToolParameter("prompt", "string", "图片生成提示词，描述想要的画面内容"),
        ToolParameter("save_dir", "string", "图片保存目录（LLM 应根据项目目标文件夹自行决定）"),
        ToolParameter("size", "string", "输出尺寸，默认 2K", required=False, default="2K"),
        ToolParameter("model", "string", "模型名称，默认 doubao-seedream-4-5-251128", required=False,
                      default=DEFAULT_MODEL),
        ToolParameter("watermark", "boolean", "是否添加水印，默认 true", required=False, default=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = "", base_url: str = ""):
        super().__init__(cwd)
        self.api_key = api_key
        self.base_url = (base_url or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")

    def execute(self, prompt: str, save_dir: str, size: str = DEFAULT_SIZE,
                model: str = DEFAULT_MODEL, watermark: bool = True, **kwargs) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail(
                "未配置 ImageGen API Key。请在 Settings → Skill Keys 中配置图片生成 Key。"
            )

        prompt = (prompt or "").strip()
        if not prompt:
            return ToolResult.fail("prompt 不能为空")

        save_dir = (save_dir or "").strip()
        if not save_dir:
            return ToolResult.fail("save_dir 不能为空，LLM 应根据项目目标文件夹自行决定保存位置")

        save_path = self._resolve_path(save_dir)
        try:
            save_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            import traceback
            log.error(f"[generate_image] mkdir 失败 | save_dir={save_dir} resolved={save_path} error={e}")
            log.error(traceback.format_exc())
            return ToolResult.fail(f"无法创建保存目录 {save_path}: {e}")

        # 1. 调用 ARK API 生成图片
        try:
            from openai import OpenAI
        except ImportError:
            return ToolResult.fail("缺少 openai 库，请运行: pip install openai")

        try:
            client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                response_format="url",
                extra_body={"watermark": bool(watermark)},
            )
        except Exception as e:
            return ToolResult.fail(f"图片生成 API 调用失败: {e}")

        # 2. 从响应中提取图片 URL
        response_dict = response.model_dump() if hasattr(response, "model_dump") else {}
        items = response_dict.get("data", [])
        if not items:
            return ToolResult.fail("API 响应中没有图片数据")

        image_url = str(items[0].get("url", "")).strip()
        if not image_url:
            return ToolResult.fail("API 响应中缺少图片 URL")

        # 3. 下载图片
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Sigma/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
                image_bytes = resp.read()
        except Exception as e:
            return ToolResult.fail(f"图片下载失败: {e}")

        # 4. 保存到本地
        ext = ".png" if "png" in content_type else ".jpg"
        filename = f"image_{uuid.uuid4().hex[:12]}{ext}"
        filepath = save_path / filename

        filepath.write_bytes(image_bytes)

        # 5. 获取尺寸
        img_size = "unknown"
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            img_size = f"{img.width}x{img.height}"
        except Exception:
            pass

        return ToolResult.ok(
            f"图片已生成: {filepath}\n尺寸: {img_size}\n格式: {content_type}",
            filename=filename,
            filepath=str(filepath.resolve()),
            size=img_size,
            mime_type=content_type,
            model=model,
        )
