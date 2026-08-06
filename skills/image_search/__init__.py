"""
image_search skill - 通过 Tavily API 在网络上搜索图片

提供 search_image 工具，搜索网络图片并下载到本地 searchImage 文件夹。
"""
import os
import json
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from io import BytesIO
from skills.base import BaseTool, ToolParameter, ToolResult


class ImageSearchTool(BaseTool):
    name = "search_image"
    description = (
        "通过 Tavily API 在网络上搜索图片，自动下载并保存到项目 searchImage 目录。"
        "适用于为文档、PPT 搜索配图，或查找特定主题的图片素材。"
    )
    parameters = [
        ToolParameter("query", "string", "图片搜索关键词"),
        ToolParameter("max_results", "integer", "下载数量，默认 5，最大 20", required=False, default=5),
        ToolParameter("save_dir", "string", "图片保存目录，默认 searchImage", required=False, default="searchImage"),
        ToolParameter("resize_to", "array", "可选目标尺寸 [width, height]，按比例缩放并居中裁剪", required=False),
        ToolParameter("quality", "integer", "JPEG 保存质量 1-100，默认 85", required=False, default=85),
        ToolParameter("search_depth", "string", "Tavily 搜索深度 basic 或 advanced，默认 basic", required=False, default="basic"),
    ]

    def __init__(self, cwd: str = ".", tavily_api_key: str = ""):
        super().__init__(cwd)
        self.tavily_api_key = tavily_api_key
        self.api_endpoint = "https://api.tavily.com/search"

    def execute(self, query: str, max_results: int = 5, save_dir: str = "searchImage",
                resize_to: list | tuple | None = None, quality: int = 85,
                search_depth: str = "basic", **kwargs) -> ToolResult:
        if not self.tavily_api_key:
            return ToolResult.fail(
                "未配置 Tavily API Key。请在 Settings → Skill Keys 中配置 Tavily Key。"
            )

        query = (query or "").strip()
        if not query:
            return ToolResult.fail("query 必须是非空字符串")
        max_results = min(max(int(max_results or 5), 1), 20)
        quality = min(max(int(quality or 85), 1), 100)
        search_depth = (search_depth or "basic").strip().lower()
        if search_depth not in {"basic", "advanced"}:
            search_depth = "basic"

        target_size = None
        if resize_to:
            try:
                if isinstance(resize_to, str):
                    parts = resize_to.lower().replace("x", ",").split(",")
                    target_size = (int(parts[0]), int(parts[1]))
                else:
                    target_size = (int(resize_to[0]), int(resize_to[1]))
                if target_size[0] <= 0 or target_size[1] <= 0:
                    target_size = None
            except Exception:
                return ToolResult.fail("resize_to 必须是 [width, height] 或 'WIDTHxHEIGHT'")

        # 1. 搜索
        body = json.dumps({
            "api_key": self.tavily_api_key,
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results * 2,
            "include_images": True,
            "include_answer": False,
            "include_raw_content": False,
        }).encode("utf-8")

        request = urllib.request.Request(
            self.api_endpoint,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            return ToolResult.fail(f"搜索请求失败 HTTP {e.code}: {detail}")
        except Exception as e:
            return ToolResult.fail(f"搜索请求异常: {e}")

        results = data.get("results", [])
        if not isinstance(results, list) or not results:
            return ToolResult.ok(f"搜索 '{query}' 未找到相关图片")

        # 2. 过滤有图片的搜索结果，保留来源信息
        results_with_images = [item for item in results if item.get("images")]
        if not results_with_images:
            return ToolResult.ok(f"搜索 '{query}' 未找到相关图片")

        # 3. 保存目录
        save_path = self._resolve_path(save_dir or "searchImage")
        save_path.mkdir(parents=True, exist_ok=True)

        # 4. 下载并保存：每个搜索结果尝试多个图片 URL，直到成功
        downloaded = []
        safe_query = "".join(c if c.isalnum() else "_" for c in query)[:20] or "image"
        for i, item in enumerate(results_with_images, 1):
            if len(downloaded) >= max_results:
                break
            for img_url in item.get("images", []):
                try:
                    req = urllib.request.Request(
                        img_url,
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        image_bytes = resp.read()

                    try:
                        from PIL import Image
                        img = Image.open(BytesIO(image_bytes))
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        original_size = f"{img.width}x{img.height}"
                        if target_size:
                            img = self._resize_image(img, target_size)
                        filename = f"{safe_query}_{len(downloaded) + 1}_{uuid.uuid4().hex[:8]}.jpg"
                        filepath = save_path / filename
                        img.save(filepath, "JPEG", quality=quality, optimize=True)
                        final_size = f"{img.width}x{img.height}"
                        mime_type = "image/jpeg"
                    except Exception:
                        ext = ".png" if img_url.lower().split("?")[0].endswith(".png") else ".jpg"
                        filename = f"{safe_query}_{len(downloaded) + 1}_{uuid.uuid4().hex[:8]}{ext}"
                        filepath = save_path / filename
                        filepath.write_bytes(image_bytes)
                        original_size = "unknown"
                        final_size = "unknown"
                        mime_type = "image/png" if ext == ".png" else "image/jpeg"

                    downloaded.append({
                        "filename": filename,
                        "filepath": str(filepath.resolve()),
                        "url": img_url,
                        "original_size": original_size,
                        "size": final_size,
                        "mime_type": mime_type,
                        "source_title": item.get("title", ""),
                        "source_url": item.get("url", ""),
                    })
                    break
                except Exception as e:
                    print(f"  [skip] 下载失败: {str(img_url)[:60]}... ({e})")

        if not downloaded:
            return ToolResult.fail("所有图片下载均失败，请检查网络连接")

        lines = [f"图片搜索: {query}\n"]
        for d in downloaded:
            lines.append(f"  {d['filename']} ({d['size']})")
            lines.append(f"  路径: {d['filepath']}")
            lines.append(f"  来源: {d['source_title']}")

        lines.append(f"\n共下载 {len(downloaded)} 张图片到: {save_path.resolve()}")

        return ToolResult.ok(
            "\n".join(lines),
            query=query,
            image_count=len(downloaded),
            save_dir=str(save_path.resolve()),
            images=downloaded,
        )

    def _resize_image(self, img, target_size: tuple[int, int]):
        from PIL import Image

        target_width, target_height = target_size
        img_ratio = img.width / img.height
        target_ratio = target_width / target_height
        if img_ratio > target_ratio:
            new_height = target_height
            new_width = int(new_height * img_ratio)
        else:
            new_width = target_width
            new_height = int(new_width / img_ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - target_width) // 2
        top = (new_height - target_height) // 2
        return img.crop((left, top, left + target_width, top + target_height))
