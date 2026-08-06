"""
longread skill - 大文档并行阅读

将超大文档按 token 数切分为多个 chunk（10% 重叠），
供 LLM 通过 sub_agent 并行阅读后汇总。
支持 PDF/DOCX/PPTX/TXT/MD。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from skills.longread.split_doc import DocumentSplitter, DEFAULT_CHUNK_SIZE


class LongreadTool(BaseTool):
    name = "longread"
    description = (
        "将超大文档（PDF/DOCX/PPTX/TXT/MD）按 token 数切分为多个 chunk，"
        "供 sub_agent 并行阅读后汇总。适用于文档超出单次读取上限时。"
        "自动使用 tiktoken 精准分块，10% 重叠避免信息丢失。"
    )
    parameters = [
        ToolParameter("file_path", "string", "文档文件路径"),
        ToolParameter("chunk_size", "integer", "每个 chunk 的 token 数上限（默认 32000）", required=False, default=DEFAULT_CHUNK_SIZE),
        ToolParameter("output_dir", "string", "chunk 输出目录，默认文件同目录下的 .longread_chunks", required=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, file_path: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
                output_dir: str = None, **kwargs) -> ToolResult:
        full_path = Path(self._resolve_path(file_path))
        if not full_path.exists():
            return ToolResult.fail(f"文件不存在: {file_path}")
        if full_path.suffix.lower() not in {".pdf", ".docx", ".doc", ".txt", ".md", ".pptx", ".ppt"}:
            return ToolResult.fail(f"不支持的格式: {full_path.suffix}")
        if not isinstance(chunk_size, int) or chunk_size < 1000 or chunk_size > 100000:
            return ToolResult.fail("chunk_size 必须是 1000-100000 之间的整数")

        out_dir = Path(self._resolve_path(output_dir)) if output_dir else full_path.parent / ".longread_chunks"
        out_dir.mkdir(parents=True, exist_ok=True)

        splitter = DocumentSplitter(output_dir=str(out_dir), chunk_size=chunk_size)

        # 获取信息
        info = splitter.get_file_info(full_path)
        if "error" in info:
            return ToolResult.fail(info["error"])

        total_tokens = info.get("total_tokens", 0)
        needs_split = info.get("needs_split", False)

        if not needs_split:
            return ToolResult.ok(
                f"文档较小（{total_tokens} tokens），不需要切分。直接用 read_pdf 或 read 读取即可。",
                file_name=full_path.name, total_tokens=total_tokens,
                needs_split=False,
            )

        # 切分
        chunk_files = splitter.process_file(full_path)
        if not chunk_files:
            return ToolResult.fail("切分失败，未能生成 chunk 文件")

        guide = (
            f"文档已切分为 {len(chunk_files)} 个 chunk（{total_tokens} tokens），存储在 {out_dir}。\n"
            "请使用 sub_agent 并行阅读每个 chunk，汇总后回答用户：\n\n"
            "```python\n"
            "sub_agent(tasks=[\n"
        )
        for i, cf in enumerate(chunk_files):
            guide += f"    {{\"type\": \"explore\", \"description\": \"读块{i+1}\", \"prompt\": \"阅读文件 {cf}，提取关键信息并总结。标注 chunk 编号。\"}},\n"
        guide += "])\n```\n\n汇总所有子Agent返回的内容，回答用户问题。"

        return ToolResult.ok(
            guide,
            file_name=full_path.name,
            total_tokens=total_tokens,
            num_chunks=len(chunk_files),
            chunk_files=chunk_files,
            needs_split=True,
        )
