"""
image_reader skill - 读取图片并通过 Vision API 识别内容。
"""
import base64
import io
import json
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

        self._emit_progress(f"正在预检图片: {full_path.name}")
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
                "请先观察附带缩略图，再自行决定是否使用 read_image；文字或表格图片应选择 image_quality=high，内容理解可选择 balanced 或 low。",
                file_path=str(full_path), format=original_format, mode=original_mode,
                original_size=original_size, preview_size=f"{img.width}x{img.height}",
                orientation=orientation, preview_image_base64=preview_b64,
            )
        except Exception as e:
            return ToolResult.fail(f"图片预检失败: {e}")


class ImageReaderTool(BaseTool):
    name = "read_image"
    description = (
        "读取本地图片并通过 Vision API (Anthropic 协议) 识别内容。"
        "image_quality=high 用于文字、表格或细节识别；balanced 用于一般图片理解；low 用于无需读取文字的快速内容理解。"
        "需要先在 Settings → Skill Keys → PDF Vision OCR 中配置 Vision API。"
    )
    parameters = [
        ToolParameter("file_path", "string", "图片文件路径"),
        ToolParameter("image_quality", "string", "图片传输档位：high（文字/表格）、balanced（一般理解，默认）、low（不读文字的快速理解）", required=False, default="balanced"),
        ToolParameter("max_size", "integer", "处理后最长边像素；不传时由 image_quality 决定（high 1600、balanced 1024、low 512）", required=False),
        ToolParameter("max_tokens", "integer", "Vision API 每个区域的最大输出 token 数，默认 8192，最高 16384", required=False, default=8192),
        ToolParameter("rotate", "integer", "顺时针旋转角度：0、90、180 或 270", required=False, default=0),
        ToolParameter("split_rows", "integer", "沿图片高度自动分成多个区域识别。密集表格建议 2–4，默认 1，最高 8", required=False, default=1),
        ToolParameter("prompt", "string", "自定义识别提示", required=False),
        ToolParameter("convert_to_base64", "boolean", "未配置 Vision API 时，是否返回压缩后的 base64 图片数据", required=False, default=False),
        ToolParameter("include_info", "boolean", "是否返回图片格式、原始尺寸和处理后尺寸信息", required=False, default=True),
    ]

    _QUALITY_PROFILES = {
        "high": {"max_size": 1600, "format": "PNG", "mime_type": "image/png", "save_options": {"optimize": True}},
        "balanced": {"max_size": 1024, "format": "JPEG", "mime_type": "image/jpeg", "save_options": {"quality": 75, "optimize": True}},
        "low": {"max_size": 512, "format": "JPEG", "mime_type": "image/jpeg", "save_options": {"quality": 50, "optimize": True}},
    }

    def __init__(self, cwd: str = ".", vision_api_key: str = "",
                 vision_model: str = "kimi-for-coding",
                 vision_base_url: str = "https://api.moonshot.cn/anthropic"):
        super().__init__(cwd)
        self.vision_api_key = vision_api_key
        self.vision_model = vision_model
        self.vision_base_url = vision_base_url

    @staticmethod
    def _to_rgb(img):
        from PIL import Image
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.getchannel("A"))
            return background
        if img.mode == "P" and "transparency" in img.info:
            return ImageReaderTool._to_rgb(img.convert("RGBA"))
        return img.convert("RGB") if img.mode != "RGB" else img

    def execute(self, file_path: str, image_quality: str = "balanced", max_size: int = None,
                max_tokens: int = 8192, rotate: int = 0, split_rows: int = 1,
                prompt: str = None, convert_to_base64: bool = False,
                include_info: bool = True, **kwargs) -> ToolResult:
        full_path = self._resolve_path(file_path)
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {full_path}")
        if full_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}:
            return ToolResult.fail(f"不支持的格式: {full_path.suffix.lower()}")
        if image_quality not in self._QUALITY_PROFILES:
            return ToolResult.fail("image_quality 只支持 high、balanced 或 low")

        try:
            from PIL import Image, ImageOps
            profile = self._QUALITY_PROFILES[image_quality]
            img = ImageOps.exif_transpose(Image.open(full_path))
            original_size = f"{img.width}x{img.height}"
            original_format = img.format
            original_mode = img.mode
            if rotate not in (0, 90, 180, 270):
                return ToolResult.fail("rotate 只支持 0、90、180 或 270")
            if rotate:
                img = img.rotate(-rotate, expand=True)
            img = self._to_rgb(img)

            target_size = profile["max_size"] if max_size is None else int(max_size)
            if target_size > 0 and (img.width > target_size or img.height > target_size):
                img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
            processed_size = f"{img.width}x{img.height}"
            split_rows = min(max(int(split_rows or 1), 1), 8)

            regions = []
            for row in range(split_rows):
                top = img.height * row // split_rows
                bottom = img.height * (row + 1) // split_rows
                buf = io.BytesIO()
                img.crop((0, top, img.width, bottom)).save(buf, format=profile["format"], **profile["save_options"])
                regions.append(base64.b64encode(buf.getvalue()).decode("utf-8"))

            if not self.vision_api_key:
                self._emit_progress("未配置 Vision API，仅返回图片信息")
                details = {"file_path": str(full_path), "filename": full_path.name, "mime_type": profile["mime_type"]}
                if include_info:
                    details.update({"format": original_format, "mode": original_mode, "original_size": original_size,
                                    "processed_size": processed_size, "processed_width": img.width, "processed_height": img.height,
                                    "rotate": rotate, "split_rows": split_rows, "image_quality": image_quality})
                if convert_to_base64:
                    details["base64"] = regions[0]
                    details["llm_message"] = {"type": "image_url", "image_url": {"url": f"data:{profile['mime_type']};base64,{regions[0]}"}}
                    return ToolResult.ok("未配置 Vision API，已返回压缩后的图片元信息和 base64 数据。", **details)
                return ToolResult.fail("未配置 Vision API。请在 Settings → Skill Keys → PDF Vision OCR 中配置 Key/Model/BaseURL。\n"
                                       "如果只需要交给外部视觉模型处理，可设置 convert_to_base64=true。", **details)

            max_tokens = min(max(int(max_tokens or 8192), 256), 16384)
            body_text = prompt or "请详细描述这张图片的内容。如果有文字，请完整识别可见文字；如果文字很多，请优先按区域整理重点内容。如果有图表，请描述数据趋势。直接输出内容，不要加额外说明。"
            base_url = self.vision_base_url.rstrip("/")
            contents = []
            for row, region_b64 in enumerate(regions, start=1):
                self._emit_progress(f"正在识别区域 {row}/{split_rows}..." if split_rows > 1 else "正在调用 Vision API 识别图片...")
                region_prompt = body_text if split_rows == 1 else f"{body_text}\n这是整张图片从上到下分割后的第 {row}/{split_rows} 个区域；仅识别当前区域，不要猜测其他区域。"
                body = json.dumps({"model": self.vision_model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": [
                    {"type": "text", "text": region_prompt},
                    {"type": "image", "source": {"type": "base64", "media_type": profile["mime_type"], "data": region_b64}},
                ]}]}).encode("utf-8")
                req = ur.Request(f"{base_url}/v1/messages", data=body, headers={"Authorization": f"Bearer {self.vision_api_key}", "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
                with ur.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                content = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
                if not content:
                    stop = data.get("stop_reason", "unknown")
                    if stop == "max_tokens":
                        return ToolResult.fail(f"Vision API 在第 {row}/{split_rows} 个区域达到 max_tokens={max_tokens} 上限，未返回可用文本。请增加 split_rows 后重试。")
                    return ToolResult.fail(f"Vision API 在第 {row}/{split_rows} 个区域未返回文本 (stop_reason={stop})。")
                contents.append(content)

            content = "\n\n".join(f"## 区域 {row}\n{text}" if split_rows > 1 else text for row, text in enumerate(contents, start=1))
            return ToolResult.ok(content, file_path=str(full_path), original_size=original_size, processed_size=processed_size,
                                 rotate=rotate, split_rows=split_rows, max_tokens=max_tokens, model=self.vision_model,
                                 image_quality=image_quality, mime_type=profile["mime_type"])
        except ur.HTTPError as e:
            return ToolResult.fail(f"Vision API HTTP {e.code}: {e.reason}")
        except Exception as e:
            return ToolResult.fail(f"图片识别失败: {e}")
