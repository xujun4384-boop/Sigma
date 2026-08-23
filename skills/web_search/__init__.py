"""
联网搜索工具：web_search

支持多种搜索引擎（Kimi Search V2 / Tavily / Custom），通过 Skill Keys 配置选择。
独立于主 LLM 的 API Key，确保切换 LLM 时搜索功能不受影响。
"""
import json
import urllib.request
import urllib.error
from skills.base import BaseTool, ToolParameter, ToolResult

# 各 Provider 的默认 API 端点
PROVIDER_ENDPOINTS = {
    "kimi": "https://api.kimi.com/coding/v1",
    "tavily": "https://api.tavily.com",
}


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "联网搜索，获取最新信息。支持 Kimi Search V2 / Tavily / Custom 引擎。返回搜索结果摘要和链接。"
    parameters = [
        ToolParameter(name="query", type="string", description="搜索查询词", required=True),
        ToolParameter(name="limit", type="integer", description="返回结果数量，默认 5，最大 10", required=False),
    ]

    def __init__(self, cwd: str = ".", provider: str = "kimi",
                 api_key: str = "", custom_base_url: str = ""):
        super().__init__(cwd)
        self.provider = provider
        self.api_key = api_key
        self.custom_base_url = custom_base_url

    @property
    def base_url(self) -> str:
        if self.provider == "custom":
            return self.custom_base_url.rstrip("/")
        return PROVIDER_ENDPOINTS.get(self.provider, PROVIDER_ENDPOINTS["kimi"])

    def execute(self, query: str, limit: int = 5, **kwargs) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail(
                f"未配置 Web Search API Key。请在 Settings → Skill Keys 中配置 {self.provider.upper()} 搜索 Key。"
            )

        limit = min(max(limit, 1), 10)
        self._emit_progress(f"正在搜索: {query}")

        if self.provider == "kimi":
            return self._search_kimi(query, limit)
        elif self.provider == "tavily":
            return self._search_tavily(query, limit)
        else:
            return self._search_generic(query, limit)

    def _search_kimi(self, query: str, limit: int) -> ToolResult:
        """Kimi Search V2 API"""
        body = json.dumps({
            "text_query": query,
            "limit": limit,
            "enable_page_crawling": False,
            "timeout_seconds": 30,
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/search",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            return ToolResult.fail(f"Kimi 搜索失败 HTTP {e.code}: {detail}")
        except Exception as e:
            return ToolResult.fail(f"搜索请求异常: {e}")

        results = data.get("search_results", [])
        return self._format_results(query, results, limit)

    def _search_tavily(self, query: str, limit: int) -> ToolResult:
        """Tavily Search API"""
        body = json.dumps({
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/search",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            return ToolResult.fail(f"Tavily 搜索失败 HTTP {e.code}: {detail}")
        except Exception as e:
            return ToolResult.fail(f"搜索请求异常: {e}")

        results = data.get("results", [])
        return self._format_results(query, results, limit)

    def _search_generic(self, query: str, limit: int) -> ToolResult:
        """Generic OpenAI-compatible search API"""
        body = json.dumps({
            "query": query,
            "limit": limit,
        }).encode("utf-8")

        request = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            return ToolResult.fail(f"搜索失败 HTTP {e.code}: {detail}")
        except Exception as e:
            return ToolResult.fail(f"搜索请求异常: {e}")

        # 尝试通用格式解析
        results = data.get("results", data.get("search_results", data.get("data", [])))
        return self._format_results(query, results, limit)

    def _format_results(self, query: str, results: list, limit: int) -> ToolResult:
        if not isinstance(results, list) or not results:
            return ToolResult.ok(f"搜索 '{query}' 未找到结果")

        lines = [f"搜索查询: {query} (引擎: {self.provider})\n"]
        for i, item in enumerate(results[:limit], 1):
            title = item.get("title", "无标题")
            url = item.get("url", "")
            snippet = item.get("snippet", item.get("content", item.get("description", "")))
            snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
            lines.append(f"{i}. {title}")
            lines.append(f"   URL: {url}")
            lines.append(f"   摘要: {snippet}")
            lines.append("")

        return ToolResult.ok("\n".join(lines), result_count=len(results), provider=self.provider)
