"""
docx_reader skill - 读取 Word 文档 (.docx)

提供 read_docx 工具，读取文档内容、元数据、表格、图片信息，支持分段读取。
"""
import os
from skills.base import BaseTool, ToolParameter, ToolResult
from skills.utils.docx_text import get_paragraph_full_text, get_cell_full_text


class ReadDocxTool(BaseTool):
    name = "read_docx"
    description = (
        "读取 Word (.docx) 文档的内容。支持提取文本段落、表格、图片信息和文档元数据。"
        "大文档可通过 chunk_size 分段读取。"
    )
    parameters = [
        ToolParameter("file_path", "string", "Word 文档的路径（支持相对路径和绝对路径）"),
        ToolParameter("extract_tables", "boolean", "是否提取表格内容", required=False, default=False),
        ToolParameter("extract_images", "boolean", "是否提取图片信息", required=False, default=False),
        ToolParameter("include_metadata", "boolean", "是否包含文档元数据（标题、作者、日期等）", required=False, default=False),
        ToolParameter("chunk_size", "integer", "分段大小（按段落数），不设置则读取全部", required=False),
        ToolParameter("chunk_index", "integer", "分段索引（从0开始），配合 chunk_size 使用", required=False, default=0),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, extract_tables: bool = False, extract_images: bool = False,
                include_metadata: bool = False, chunk_size: int | None = None,
                chunk_index: int = 0, **kwargs) -> ToolResult:
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.cwd, file_path)

        if not os.path.exists(full_path):
            return ToolResult.fail(f"文件不存在: {full_path}")
        if not full_path.lower().endswith('.docx'):
            return ToolResult.fail("仅支持 .docx 格式文件")

        try:
            from docx import Document
        except ImportError:
            return ToolResult.fail("缺少 python-docx 库，请运行: pip install python-docx")

        try:
            doc = Document(full_path)
            content_result = self._read_paragraphs(doc, chunk_size, chunk_index)
            metadata = self._extract_metadata(doc) if include_metadata else None
            tables = self._extract_tables(doc) if extract_tables else []
            images = self._extract_images(doc) if extract_images else []

            lines = [f"[文件] {full_path}"]
            if metadata:
                lines.append(f"\n--- 元数据 ---")
                for k, v in metadata.items():
                    if v:
                        lines.append(f"  {k}: {v}")
            lines.append(f"\n--- 正文 ---")
            lines.append(content_result["content"])
            # 分块信息拼进正文，让 LLM 知道总数与当前位置，避免盲猜反复调用
            total_paragraphs = content_result["total_paragraphs"]
            chunk_info = content_result.get("chunk_info") or {}
            if chunk_info.get("is_chunked"):
                total_chunks = chunk_info.get("total_chunks", 1)
                current = chunk_info.get("current_chunk", 0)
                if chunk_info.get("error"):
                    chunk_desc = chunk_info["error"]
                else:
                    count_in_chunk = chunk_info.get("paragraphs_in_chunk")
                    chunk_desc = (
                        f"第 {current + 1}/{total_chunks} 块"
                        + (f"（本块 {count_in_chunk} 段）" if count_in_chunk is not None else "")
                        + f" | 全文共 {total_paragraphs} 段"
                    )
            else:
                chunk_desc = f"全文共 {total_paragraphs} 段（未分块）"
            lines.append(f"\n--- 分块信息 ---\n{chunk_desc}")
            if tables:
                lines.append(f"\n--- 表格 ({len(tables)} 个) ---")
                for t in tables:
                    lines.append(f"  表格 {t['table_index']}: {t['rows']}行 x {t['columns']}列")
            if images:
                lines.append(f"\n--- 图片 ({len(images)} 个) ---")

            return ToolResult.ok(
                "\n".join(lines),
                total_paragraphs=content_result["total_paragraphs"],
                chunk_info=content_result.get("chunk_info"),
                metadata=metadata,
                table_count=len(tables),
                image_count=len(images),
            )
        except Exception as e:
            return ToolResult.fail(f"读取文档失败: {e}")

    def _read_paragraphs(self, doc, chunk_size: int | None, chunk_index: int) -> dict:
        all_paragraphs = [get_paragraph_full_text(p) for p in doc.paragraphs if get_paragraph_full_text(p).strip()]
        total = len(all_paragraphs)

        if chunk_size is None:
            return {
                "content": "\n".join(all_paragraphs),
                "total_paragraphs": total,
                "chunk_info": {"is_chunked": False, "total_chunks": 1, "current_chunk": 0},
            }

        total_chunks = (total + chunk_size - 1) // chunk_size
        if chunk_index >= total_chunks:
            return {"content": "", "total_paragraphs": total, "chunk_info": {
                "is_chunked": True, "total_chunks": total_chunks, "current_chunk": chunk_index,
                "error": f"chunk_index {chunk_index} 超出范围，共 {total_chunks} 段"
            }}

        start = chunk_index * chunk_size
        end = min(start + chunk_size, total)
        return {
            "content": "\n".join(all_paragraphs[start:end]),
            "total_paragraphs": total,
            "chunk_info": {"is_chunked": True, "total_chunks": total_chunks,
                           "current_chunk": chunk_index, "chunk_start": start, "chunk_end": end,
                           "paragraphs_in_chunk": end - start},
        }

    def _extract_metadata(self, doc) -> dict:
        try:
            props = doc.core_properties
            return {
                "title": props.title or "",
                "author": props.author or "",
                "created": str(props.created) if props.created else "",
                "modified": str(props.modified) if props.modified else "",
                "subject": props.subject or "",
                "keywords": props.keywords or "",
            }
        except Exception:
            return {}

    def _extract_tables(self, doc) -> list:
        tables_data = []
        for idx, table in enumerate(doc.tables):
            content = [[get_cell_full_text(cell).strip() for cell in row.cells] for row in table.rows]
            tables_data.append({
                "table_index": idx,
                "rows": len(table.rows),
                "columns": len(table.columns) if table.rows else 0,
                "content": content,
            })
        return tables_data

    def _extract_images(self, doc) -> list:
        images_info = []
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                images_info.append({
                    "relationship_id": rel.rId,
                    "target": rel.target_ref,
                })
        return images_info
