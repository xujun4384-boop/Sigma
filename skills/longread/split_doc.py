"""
文档切分工具 — 适配 Sigma。

将 PDF / DOCX / TXT / MD / PPTX 文档按 token 数切分为多个 chunk，
每个 chunk 之间保留 10% 重叠，避免信息在切分边界丢失。

来源：Kimi Desktop longread skill (split_doc.py)，针对 Sigma 做路径适配。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

try:
    from pypdf import PdfReader as PyPdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".pptx", ".ppt"}
DEFAULT_CHUNK_SIZE = 32000       # tokens
DEFAULT_OVERLAP_RATIO = 0.1      # 10%


class DocumentSplitter:
    """将大文档切分为多个小 chunk 文件。"""

    def __init__(
        self,
        output_dir: str = ".",
        model_name: str = "cl100k_base",
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
    ):
        self.output_dir = Path(output_dir)
        self.chunk_size = chunk_size
        self.overlap_ratio = overlap_ratio

        if TIKTOKEN_AVAILABLE:
            self.encoding = tiktoken.get_encoding(model_name)
            self.use_tiktoken = True
            self.overlap_size = int(chunk_size * overlap_ratio)
        else:
            self.encoding = None
            self.use_tiktoken = False
            self.chunk_size_chars = chunk_size * 4
            self.overlap_size_chars = int(self.chunk_size_chars * overlap_ratio)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── public ──────────────────────────────────────────────

    def process_file(self, file_path: str | Path) -> List[str]:
        """提取文本 → 切分 → 写出 chunk 文件，返回绝对路径列表。"""
        path = Path(file_path)
        if not path.exists():
            print(f"[split_doc] 文件不存在: {path}")
            return []

        full_text = self._extract_text(path)
        if not full_text:
            print(f"[split_doc] 无法提取文本: {path.name}")
            return []

        return self._chunk_and_write(full_text, path.stem)

    def get_file_info(self, file_path: str | Path) -> dict:
        """返回文件大小信息（估算 token 数），不实际切分。"""
        path = Path(file_path)
        if not path.exists():
            return {"exists": False, "error": "文件不存在"}

        text = self._extract_text(path)
        if not text:
            return {"exists": True, "error": "无法提取文本内容"}

        if self.use_tiktoken and self.encoding:
            tokens = self.encoding.encode(text)
            total_tokens = len(tokens)
        else:
            total_tokens = len(text) // 4

        return {
            "exists": True,
            "file_name": path.name,
            "suffix": path.suffix.lower(),
            "total_tokens": total_tokens,
            "total_chars": len(text),
            "estimated_chunks": max(1, -(-total_tokens // (self.chunk_size - self.overlap_size))) if self.use_tiktoken else max(1, -(-(len(text)) // (self.chunk_size_chars - self.overlap_size_chars))),
            "needs_split": total_tokens > self.chunk_size,
        }

    # ── internal ────────────────────────────────────────────

    def _chunk_and_write(self, text: str, base_name: str) -> List[str]:
        generated: List[str] = []
        if self.use_tiktoken and self.encoding:
            tokens = self.encoding.encode(text)
            total = len(tokens)
            part_num = 0
            i = 0
            step = self.chunk_size - self.overlap_size
            while i < total:
                chunk_tokens = tokens[i : i + self.chunk_size]
                chunk_text = self.encoding.decode(chunk_tokens)
                part_num += 1
                out = self._write_chunk(base_name, part_num, chunk_text)
                if out:
                    generated.append(out)
                i += step
            print(f"[split_doc] 切分完成: {part_num} 个 chunk (共 {total} tokens)")
        else:
            total = len(text)
            part_num = 0
            i = 0
            step = self.chunk_size_chars - self.overlap_size_chars
            while i < total:
                chunk_text = text[i : i + self.chunk_size_chars]
                part_num += 1
                out = self._write_chunk(base_name, part_num, chunk_text)
                if out:
                    generated.append(out)
                i += step
            print(f"[split_doc] 切分完成: {part_num} 个 chunk (共 {total} 字符, ~{total // 4} tokens)")

        return generated

    def _write_chunk(self, base_name: str, part: int, text: str) -> Optional[str]:
        name = f"{base_name}_part_{part}.txt"
        path = self.output_dir / name
        try:
            path.write_text(text, encoding="utf-8")
            return str(path.absolute())
        except Exception as e:
            print(f"[split_doc] 写入 {name} 失败: {e}")
            return None

    # ── text extraction ─────────────────────────────────────

    def _extract_text(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            print(f"[split_doc] 不支持的文件类型: {ext}")
            return ""
        try:
            if ext == ".pdf":
                return self._extract_pdf(path)
            if ext in (".docx", ".doc"):
                return self._extract_docx(path) if DOCX_AVAILABLE else ""
            if ext in (".pptx", ".ppt"):
                return self._extract_pptx(path) if PPTX_AVAILABLE else ""
            return self._extract_plain(path)
        except Exception as e:
            print(f"[split_doc] 提取失败: {e}")
            return ""

    def _extract_plain(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")

    def _extract_pdf(self, path: Path) -> str:
        for method_name, available, fn in (
            ("PyMuPDF", PYMUPDF_AVAILABLE, self._pdf_pymupdf),
            ("pypdf", PYPDF_AVAILABLE, self._pdf_pypdf),
            ("pdfminer", PDFMINER_AVAILABLE, self._pdf_pdfminer),
        ):
            if not available:
                continue
            try:
                result = fn(path)
                if result and result.strip():
                    return result
            except Exception as e:
                print(f"[split_doc] {method_name} 失败: {e}")
        print("[split_doc] 无可用的 PDF 解析库")
        return ""

    def _pdf_pymupdf(self, path: Path) -> str:
        doc = fitz.open(str(path))
        text: List[str] = []
        for page in doc:
            text.append(page.get_text())
        doc.close()
        return "\n".join(text)

    def _pdf_pypdf(self, path: Path) -> str:
        reader = PyPdfReader(str(path))
        text: List[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text.append(t)
        return "\n".join(text)

    def _pdf_pdfminer(self, path: Path) -> str:
        return pdfminer_extract(str(path))

    def _extract_docx(self, path: Path) -> str:
        doc = Document(str(path))
        parts: List[str] = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts)

    def _extract_pptx(self, path: Path) -> str:
        prs = Presentation(str(path))
        parts: List[str] = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    parts.append(shape.text)
        return "\n".join(parts)


# ── CLI 入口（兼容 Kimi 调用方式）────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "chunks"
        splitter = DocumentSplitter(output_dir=output_dir)
        generated = splitter.process_file(file_path)
        result = {
            "status": "success" if generated else "failed",
            "chunk_files": generated,
            "num_chunks": len(generated),
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("Usage: python split_doc.py <file_path> [output_dir]")
