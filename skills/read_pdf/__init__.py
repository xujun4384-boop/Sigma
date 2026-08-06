"""
read_pdf skill - PDF 读取（文本提取 + 视觉 OCR）

自动检测每页类型：文本页直接提取，图片页（扫描件）通过 LLM 视觉识别。
视觉识别使用独立的 Vision API 配置，不依赖主 LLM。
"""
import base64
import io
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ReadPdfTool(BaseTool):
    name = "read_pdf"
    description = (
        "读取 PDF 文件内容。自动检测页面类型：文本页直接提取，"
        "图片页（扫描件）使用 LLM 视觉 API 识别。"
        "OCR 功能需要用户在 Settings → Skill Keys → PDF Vision OCR 中配置。"
    )
    parameters = [
        ToolParameter("file_path", "string", "PDF 文件路径"),
        ToolParameter("page_range", "string", "页码范围，如 '1-5' 或 '1,3,5'（可选，默认全部）", required=False),
        ToolParameter("image_dpi", "integer", "图片页渲染 DPI（默认 150，影响清晰度和 token 消耗）", required=False, default=150),
        ToolParameter("ocr", "boolean", "是否对图片页启用视觉识别（默认 true）", required=False, default=True),
    ]

    def __init__(self, cwd: str = ".", vision_api_key: str = "",
                 vision_model: str = "kimi-for-coding",
                 vision_base_url: str = "https://api.moonshot.cn/anthropic"):
        super().__init__(cwd)
        self.vision_api_key = vision_api_key
        self.vision_model = vision_model
        self.vision_base_url = vision_base_url

    def execute(self, file_path: str, page_range: str = None,
                image_dpi: int = 150, ocr: bool = True, **kwargs) -> ToolResult:
        full_path = Path(self._resolve_path(file_path))
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {file_path}")
        if full_path.suffix.lower() != ".pdf":
            return ToolResult.fail("仅支持 .pdf 文件")

        try:
            import fitz
        except ImportError:
            return ToolResult.fail("缺少 PyMuPDF (fitz) 库: pip install PyMuPDF")

        doc = fitz.open(str(full_path))
        page_count = len(doc)

        # 解析页码范围
        page_indices = self._parse_range(page_range, page_count)

        # 元数据
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        metadata = {
            "page_count": page_count,
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "subject": meta.get("subject", ""),
        }

        pages = []
        text_pages = 0
        image_pages = 0
        errors = []

        has_vision_config = ocr and self.vision_api_key

        for pi in page_indices:
            page = doc[pi]
            text = page.get_text().strip()

            if text and len(text) > 20:
                # 文本页：足够文本量直接返回
                pages.append({
                    "page_num": pi + 1, "type": "text",
                    "content": text, "char_count": len(text),
                })
                text_pages += 1
                continue

            # 图片页或无文本页
            if not has_vision_config:
                image_pages += 1
                pages.append({
                    "page_num": pi + 1, "type": "image",
                    "content": "[图片页，未配置 Vision API。请在 Settings → Skill Keys → PDF Vision OCR 中配置]",
                    "char_count": 0,
                })
                continue

            # OCR: 渲染为图片 → LLM vision 识别
            try:
                ocr_text = self._ocr_page(page, image_dpi)
                if ocr_text:
                    pages.append({
                        "page_num": pi + 1, "type": "ocr",
                        "content": ocr_text, "char_count": len(ocr_text),
                    })
                    image_pages += 1
                else:
                    pages.append({
                        "page_num": pi + 1, "type": "image",
                        "content": "[视觉识别返回空]", "char_count": 0,
                    })
                    image_pages += 1
            except Exception as e:
                errors.append(f"第 {pi+1} 页 OCR 失败: {e}")
                # 回退：至少提供原始文本（如果有的话）
                pages.append({
                    "page_num": pi + 1, "type": "image",
                    "content": text or f"[识别失败: {e}]",
                    "char_count": len(text),
                })
                image_pages += 1

        doc.close()

        total_chars = sum(p.get("char_count", 0) for p in pages)
        # 组装输出文本，把实际内容放进 content
        out_lines = [f"PDF: {full_path.name}, 共 {page_count} 页, 文本 {text_pages} + OCR {image_pages}, 总 {total_chars} 字符"]
        for p in pages:
            out_lines.append(f"\n--- 第 {p['page_num']} 页 ({p.get('type','')}) ---")
            out_lines.append(p["content"])

        if errors:
            out_lines.append(f"\n⚠️ {len(errors)} 页识别失败")

        return ToolResult.ok(
            "\n".join(out_lines),
            file_path=str(full_path), metadata=metadata,
            text_pages=text_pages, image_pages=image_pages,
            total_chars=total_chars,
        )

    def _ocr_page(self, page, dpi: int) -> str:
        """使用 LLM vision API (Anthropic 协议) 识别图片页"""
        import fitz
        from PIL import Image

        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        import json
        import urllib.request as ur

        body = json.dumps({
            "model": self.vision_model,
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "请详细识别这个 PDF 页面的内容，包括所有文字、表格、数字。保持原有格式。只输出识别到的内容，不要加额外说明。"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                ],
            }],
        }).encode("utf-8")

        base_url = self.vision_base_url.rstrip("/")
        req = ur.Request(
            f"{base_url}/v1/messages",
            data=body,
            headers={
                "x-api-key": self.vision_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with ur.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        return content.strip()

    def _parse_range(self, page_range: str | None, page_count: int) -> list[int]:
        """解析页码范围字符串"""
        if not page_range:
            return list(range(page_count))

        indices = []
        parts = page_range.replace(" ", "").split(",")
        for part in parts:
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    start = max(1, int(a)) - 1
                    end = min(page_count, int(b))
                    indices.extend(range(start, end))
                except ValueError:
                    pass
            else:
                try:
                    n = int(part)
                    if 1 <= n <= page_count:
                        indices.append(n - 1)
                except ValueError:
                    pass
        return sorted(set(indices)) if indices else list(range(page_count))
