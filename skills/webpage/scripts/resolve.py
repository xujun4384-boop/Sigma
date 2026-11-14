"""来源解析：搜索 → 候选页轻量比对 → LLM 选定真实页面。

不做域名白名单、不做关键词打分；一切判断交给 LLM，代码只负责把真实页面内容喂进去并校验 URL 来源。
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .common import call_json, load_prompt

_URL_LINE = re.compile(r"^\s*URL:\s*(\S+)\s*$", re.IGNORECASE)
_NUM_LINE = re.compile(r"^\s*\d+\.\s*(.+?)\s*$")
_SNIPPET_LINE = re.compile(r"^\s*摘要:\s*(.*)$")


def parse_search_results(content: str) -> list[dict]:
    """解析 web_search 的文本结果（我们自己的稳定输出格式）。"""
    items: list[dict] = []
    cur: dict | None = None
    for line in (content or "").splitlines():
        m = _NUM_LINE.match(line)
        if m:
            if cur:
                items.append(cur)
            cur = {"title": m.group(1).strip(), "url": "", "snippet": ""}
            continue
        m = _URL_LINE.match(line)
        if m:
            if cur is None:
                cur = {"title": "", "url": "", "snippet": ""}
            cur["url"] = m.group(1).strip()
            continue
        m = _SNIPPET_LINE.match(line)
        if m and cur is not None:
            cur["snippet"] = m.group(1).strip()
    if cur:
        items.append(cur)
    return [i for i in items if i["url"].startswith(("http://", "https://"))]


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _same_url(a: str, b: str) -> bool:
    return (a or "").rstrip("/") == (b or "").rstrip("/")


def search_candidates(skill_manager, query: str, limit: int = 6) -> list[dict]:
    if skill_manager is None:
        raise RuntimeError("没有 skill_manager，无法调用 web_search 自动找来源")
    try:
        res = skill_manager.dispatch("web_search", query=query, limit=limit)
    except Exception as e:
        raise RuntimeError(f"搜索失败：{e}") from e
    if not getattr(res, "success", False):
        raise RuntimeError(f"搜索失败：{getattr(res, 'content', '') or '未知错误'}")
    items = parse_search_results(getattr(res, "content", "") or "")
    if not items:
        raise RuntimeError(f"搜索「{query}」没有返回可用网址")
    return items


def resolve_source(session, skill_manager, cfg: dict, *, query: str, focus: str,
                   narration: str = "", on_progress=None) -> dict:
    """返回 {url, title, reason}，url 保证来自真实搜索结果。"""
    if on_progress:
        on_progress(f"搜索来源：{query}")
    candidates = search_candidates(skill_manager, query, limit=6)

    # 只比对前几个候选：抓取太多会拖慢设计阶段
    probes: list[dict] = []
    for item in candidates[:3]:
        if on_progress:
            on_progress(f"读取候选页：{item['url']}")
        try:
            probe = session.probe(item["url"])
        except Exception as e:
            probes.append({"url": item["url"], "title": item.get("title", ""),
                           "excerpt": [], "error": str(e)[:120]})
            continue
        probe["snippet"] = item.get("snippet", "")
        probe["domain"] = _domain(item["url"])
        probes.append(probe)

    usable = [p for p in probes if p.get("excerpt")]
    if not usable:
        raise RuntimeError("候选页都无法读取正文（可能反爬或需要登录）")

    system = load_prompt("pick_source")
    context = (
        f"知识点：{focus}\n"
        + (f"本段旁白：{narration}\n" if narration else "")
        + "\n候选页面：\n"
        + "\n".join(
            f"[{i + 1}] {p.get('title') or '无标题'}\n"
            f"URL: {p['url']}\n"
            f"域名: {p.get('domain') or _domain(p['url'])}\n"
            f"搜索摘要: {p.get('snippet') or '—'}\n"
            f"正文摘录:\n" + "\n".join(f"- {x}" for x in p["excerpt"][:10])
            for i, p in enumerate(usable)
        )
        + "\n\n只输出 JSON。"
    )
    data = call_json(cfg, system, context, max_tokens=2500, timeout=120)
    url = str(data.get("url") or "").strip()
    reason = str(data.get("reason") or "").strip()

    chosen = next((p for p in usable if _same_url(p["url"], url)), None)
    if chosen is None:
        # 模型给了候选外地址或空：不采用幻觉 URL，退回第一个可读候选并留下原因
        chosen = usable[0]
        reason = (reason or "模型未给出有效候选") + "（已自动改用第一个可读候选）"

    return {
        "url": chosen["url"],
        "title": chosen.get("title") or "",
        "domain": chosen.get("domain") or _domain(chosen["url"]),
        "reason": reason,
    }


__all__ = ["search_candidates", "parse_search_results", "resolve_source"]
