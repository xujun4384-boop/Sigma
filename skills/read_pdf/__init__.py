"""
read_pdf skill - PDF 读取（文本提取 + 图片页自动识别）

自动检测每页类型：文本页直接提取，图片页（扫描件）渲染为图片并回传给主 LLM 识别。
图片使用内存缓存（base64），不会写入磁盘，调用完成后自动清理。
"""
import base64
import io
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ReadPdfTool(BaseTool):
    name = "read_pdf"
    description = (
        "读取 PDF 文件内容。自动检测页面类型：文本页直接提取，"
        "图片页（扫描件）渲染为图片并返回给主 LLM 识别（需要主 LLM 支持视觉）。"
    )
    parameters = [
        ToolParameter("file_path", "string", "PDF 文件路径"),
        ToolParameter("page_range", "string", "页码范围，如 '1-5' 或 '1,3,5'（可选，默认全部）", required=False),
        ToolParameter("image_dpi", "integer", "图片页渲染 DPI（默认 150，影响清晰度和 token 消耗）", required=False, default=150),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, page_range: str = None, image_dpi: int = 150, **kwargs) -> ToolResult:
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
        image_files = []  # 存储图片页的文件路径

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
            else:
                # 图片页：渲染为图片文件，返回路径
                try:
                    img_path = self._render_page_as_image_file(page, pi + 1, image_dpi, full_path.stem)
                    image_files.append(img_path)
                    pages.append({
                        "page_num": pi + 1, "type": "image_page",
                        "content": f"[图片页 {pi+1} 已渲染到: {img_path}]",
                        "char_count": 0,
                    })
                    image_pages += 1
                except Exception as e:
                    pages.append({
                        "page_num": pi + 1, "type": "error",
                        "content": f"[图片页渲染失败: {e}]",
                        "char_count": 0,
                    })

        doc.close()

        total_chars = sum(p.get("char_count", 0) for p in pages)
        # 组装输出文本
        out_lines = [f"PDF: {full_path.name}, 共 {page_count} 页, 文本页 {text_pages} + 图片页 {image_pages}, 总 {total_chars} 字符"]
        for p in pages:
            out_lines.append(f"\n--- 第 {p['page_num']} 页 ({p.get('type','')}) ---")
            out_lines.append(p["content"])

        # 如果有图片页，提示使用 read_image 读取
        if image_files:
            out_lines.append(f"\n\n[系统提示: 检测到 {len(image_files)} 张扫描页面，可使用 read_image 工具读取上述图片文件]")

        return ToolResult.ok(
            "\n".join(out_lines),
            file_path=str(full_path), metadata=metadata,
            text_pages=text_pages, image_pages=image_pages,
            total_chars=total_chars,
            image_files=image_files,  # 返回图片文件路径列表
        )

    def _render_page_as_image(self, page, dpi: int) -> str:
        """渲染 PDF 页面为 JPEG 图片，返回 base64（内存缓存，不写磁盘）"""
        import fitz
        from PIL import Image

    def _render_page_as_image_file(self, page, page_num: int, dpi: int, pdf_name: str) -> str:
        """渲染 PDF 页面为 JPEG 图片文件，返回文件路径"""
        import fitz
        from PIL import Image
        import tempfile
        import os

        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # 压缩图片：限制最大尺寸，转 JPEG 降低大小
        max_size = 1568  # Claude 推荐的最大图片尺寸
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # 转 JPEG 格式（比 PNG 小很多）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # 保存到临时文件
        temp_dir = tempfile.gettempdir()
        img_filename = f"{pdf_name}_page_{page_num}.jpg"
        img_path = os.path.join(temp_dir, img_filename)
        img.save(img_path, format="JPEG", quality=85, optimize=True)
        
        return img_path

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
