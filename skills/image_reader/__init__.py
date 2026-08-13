"""
image_reader skill - 读取图片并通过 Vision API 识别内容

使用 Vision API (Anthropic 协议) 识别图片内容，返回文字描述。
如未配置 Vision API，返回明确提示而非假数据。
"""
import base64
import io
import json
import os
import urllib.request as ur

from skills.base import BaseTool, ToolParameter, ToolResult


class ImagePreviewTool(BaseTool):
    name = "preview_image"
    description = (
        "生成图片缩略预览和元信息，不调用 Vision API。"
        "需要判断图片方向、是否为文字/表格/图表、是否应旋转或分区识别时，必须先调用本工具。"
        "结果附带缩略图，供视觉 LLM 观察后自行决定下一步调用 read_image 的 rotate、split_rows、max_size 和 prompt 参数。"
    )
    parameters = [
        ToolParameter("file_path", "string", "图片文件路径"),
        ToolParameter("max_size", "integer", "缩略图最长边像素，默认 512，范围 128–1024", required=False, default=512),
    ]

    def execute(self, file_path: str, max_size: int = 512, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")
        if full_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            return ToolResult.fail(f"不支持的格式: {full_path.suffix.lower()}")

        try:
            from PIL import Image, ImageOps
            max_size = min(max(int(max_size or 512), 128), 1024)
            img = ImageOps.exif_transpose(Image.open(full_path))
            original_size = f"{img.width}x{img.height}"
            original_format = img.format
            original_mode = img.mode
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80, optimize=True)
            preview_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            orientation = "横向" if img.width > img.height else "竖向" if img.height > img.width else "方形"
            return ToolResult.ok(
                f"图片预检完成：原始尺寸 {original_size}，预览尺寸 {img.width}x{img.height}，当前方向为{orientation}。"
                "请先观察附带缩略图，再自行决定是否使用 read_image；文字或表格图片应明确传入识别目标，必要时指定 rotate 与 split_rows。",
                file_path=str(full_path),
                format=original_format,
                mode=original_mode,
                original_size=original_size,
                preview_size=f"{img.width}x{img.height}",
                orientation=orientation,
                preview_image_base64=preview_b64,
            )
        except Exception as e:
            return ToolResult.fail(f"图片预检失败: {e}")


class ImageReaderTool(BaseTool):
    name = "read_image"
    description = (
        "读取本地图片并通过 Vision API (Anthropic 协议) 识别图片中的文字和内容。"
        "需要先在 Settings → Skill Keys → PDF Vision OCR 中配置 Vision API。"
        "遇到方向、表格或密集文字不明确的图片，应先调用 preview_image，再由模型自行选择 rotate、split_rows、max_size 和 prompt。"
        "未配置时返回明确提示，不会输出假数据。"
    )
    parameters = [
        ToolParameter("file_path", "string", "图片文件路径"),
        ToolParameter("max_size", "integer", "图片最大尺寸（像素），超出等比例缩放。默认 1024", required=False, default=1024),
        ToolParameter("max_tokens", "integer", "Vision API 每个区域的最大输出 token 数，默认 8192，最高 16384", required=False, default=8192),
        ToolParameter("rotate", "integer", "顺时针旋转角度：0、90、180 或 270。扫描件横置时使用 90 或 270；split_rows>1 且图片为竖向密集表格时会自动旋转 90", required=False, default=0),
        ToolParameter("split_rows", "integer", "沿图片高度自动分成多个区域识别。密集表格建议 2–4，默认 1，最高 8", required=False, default=1),
        ToolParameter("prompt", "string", "自定义识别提示，如 '请描述这个图表中的数据趋势'", required=False),
        ToolParameter("convert_to_base64", "boolean", "未配置 Vision API 时，是否返回压缩后的 base64 图片数据", required=False, default=False),
        ToolParameter("include_info", "boolean", "是否返回图片格式、原始尺寸和处理后尺寸信息", required=False, default=True),
    ]

    def __init__(self, cwd: str = ".", vision_api_key: str = "",
                 vision_model: str = "kimi-for-coding",
                 vision_base_url: str = "https://api.moonshot.cn/anthropic"):
        super().__init__(cwd)
        self.vision_api_key = vision_api_key
        self.vision_model = vision_model
        self.vision_base_url = vision_base_url

    def execute(self, file_path: str, max_size: int = 1024, max_tokens: int = 8192,
                rotate: int = 0, split_rows: int = 1, prompt: str = None, convert_to_base64: bool = False,
                include_info: bool = True, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")

        ext = full_path.suffix.lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}:
            return ToolResult.fail(f"不支持的格式: {ext}")

        try:
            from PIL import Image
        except ImportError:
            return ToolResult.fail("缺少 Pillow 库")

        try:
            from PIL import ImageOps
            img = Image.open(full_path)
            img = ImageOps.exif_transpose(img)
            original_size = f"{img.width}x{img.height}"
            original_format = img.format
            original_mode = img.mode

            if rotate not in (0, 90, 180, 270):
                return ToolResult.fail("rotate 只支持 0、90、180 或 270")
            if rotate:
                img = img.rotate(-rotate, expand=True)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            if max_size and max_size > 0 and (img.width > max_size or img.height > max_size):
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            processed_size = f"{img.width}x{img.height}"
            split_rows = min(max(int(split_rows or 1), 1), 8)

            regions = []
            for row in range(split_rows):
                top = img.height * row // split_rows
                bottom = img.height * (row + 1) // split_rows
                region = img.crop((0, top, img.width, bottom))
                buf = io.BytesIO()
                region.save(buf, format="PNG", optimize=True)
                regions.append(base64.b64encode(buf.getvalue()).decode("utf-8"))

            img_b64 = regions[0]

            if not self.vision_api_key:
                details = {
                    "file_path": str(full_path),
                    "filename": full_path.name,
                    "mime_type": "image/png",
                }
                if include_info:
                    details.update({
                        "format": original_format,
                        "mode": original_mode,
                        "original_size": original_size,
                        "processed_size": processed_size,
                        "processed_width": img.width,
                        "processed_height": img.height,
                        "rotate": rotate,
                        "split_rows": split_rows,
                    })
                if convert_to_base64:
                    details["base64"] = img_b64
                    details["llm_message"] = {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    }
                    return ToolResult.ok(
                        "未配置 Vision API，已返回图片元信息和 base64 数据。",
                        **details,
                    )
                return ToolResult.fail(
                    "未配置 Vision API。请在 Settings → Skill Keys → PDF Vision OCR 中配置 Key/Model/BaseURL。\n"
                    "如果只需要读取图片文件信息或交给外部视觉模型处理，可设置 convert_to_base64=true。",
                    **details,
                )

            # Vision API 输出上限与主对话无关；限制范围避免模型端拒绝异常值。
            max_tokens = min(max(int(max_tokens or 8192), 256), 16384)
            body_text = prompt or "请详细描述这张图片的内容。如果有文字，请完整识别可见文字；如果文字很多，请优先按区域整理重点内容。如果有图表，请描述数据趋势。直接输出内容，不要加额外说明。"
            base_url = self.vision_base_url.rstrip("/")
            contents = []
            for row, region_b64 in enumerate(regions, start=1):
                region_prompt = body_text
                if split_rows > 1:
                    region_prompt += f"\n这是整张图片从上到下分割后的第 {row}/{split_rows} 个区域；仅识别当前区域，不要猜测其他区域。"
                body = json.dumps({
                    "model": self.vision_model,
                    "max_tokens": max_tokens,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": region_prompt},
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": region_b64}},
                        ],
                    }],
                }).encode("utf-8")
                req = ur.Request(
                    f"{base_url}/v1/messages",
                    data=body,
                    headers={
                        "Authorization": f"Bearer {self.vision_api_key}",
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                )
                with ur.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                content = "".join(
                    block.get("text", "") for block in data.get("content", [])
                    if block.get("type") == "text"
                )
                if not content:
                    stop = data.get("stop_reason", "unknown")
                    if stop == "max_tokens":
                        return ToolResult.fail(
                            f"Vision API 在第 {row}/{split_rows} 个区域达到 max_tokens={max_tokens} 上限，未返回可用文本。"
                            "请增加 split_rows 后重试，以缩小每个区域。"
                        )
                    return ToolResult.fail(
                        f"Vision API 在第 {row}/{split_rows} 个区域未返回文本 (stop_reason={stop})。"
                    )
                contents.append(content)

            content = "\n\n".join(
                f"## 区域 {row}\n{text}" if split_rows > 1 else text
                for row, text in enumerate(contents, start=1)
            )
            return ToolResult.ok(
                content,
                file_path=str(full_path),
                original_size=original_size,
                processed_size=processed_size,
                rotate=rotate,
                split_rows=split_rows,
                max_tokens=max_tokens,
                model=self.vision_model,
            )

        except ur.HTTPError as e:
            return ToolResult.fail(f"Vision API HTTP {e.code}: {e.reason}")
        except Exception as e:
            return ToolResult.fail(f"图片识别失败: {e}")
