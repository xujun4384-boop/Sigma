"""真实网页取景：单次浏览器会话里完成文本块抽取、原文定位与页面带截图。

坐标系统一约定：
- 页面坐标（page）：以文档左上角为原点，CSS 像素；
- 页面带坐标：页面坐标 − overview.y，合成时直接用这套坐标定位标注；
- 设备像素比（dpr）：页面带按 CSS 尺寸 1:1 截取，成片里不再缩放。
"""
from __future__ import annotations

import math
from pathlib import Path

DEFAULT_VIEW_W = 1920
DEFAULT_VIEW_H = 1080
DEFAULT_DPR = 3
MAX_OVERVIEW_H = 15000
MAX_OVERVIEW_W = 3000
SETTLE_MS = 700

_FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
html { scroll-behavior: auto !important; }
"""

# 抽取页面里的"叶子文本块"：带文本、且没有块级子元素的最小容器。
# 只做结构判定，不按关键词筛选内容。
_JS_EXTRACT_BLOCKS = r"""
() => {
  const BLOCK = new Set(['block','list-item','table-cell','table-caption','flow-root','flex','grid']);
  const SKIP_TAG = new Set(['script','style','noscript','svg','canvas','video','audio','iframe','textarea','select','option']);
  const out = [];
  const seen = new Set();
  const body = document.body;
  if (!body) return out;
  const pageW = Math.max(
    document.documentElement ? document.documentElement.scrollWidth : 0,
    window.innerWidth
  );
  const pageH = Math.max(
    document.documentElement ? document.documentElement.scrollHeight : 0,
    window.innerHeight
  );
  // 结构性排除站点外框：导航、页头、页脚、侧栏。只按页面结构判断，不按文字内容筛选。
  const CHROME = 'nav,header,footer,aside,[role="navigation"],[role="banner"],[role="contentinfo"]';
  for (const el of body.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    if (SKIP_TAG.has(tag)) continue;
    if (el.closest(CHROME)) continue;
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') continue;
    if (parseFloat(st.opacity || '1') === 0) continue;
    if (!BLOCK.has(st.display)) continue;
    let hasBlockChild = false;
    for (const c of el.children) {
      const ct = c.tagName.toLowerCase();
      if (SKIP_TAG.has(ct)) continue;
      const cd = getComputedStyle(c).display;
      if (BLOCK.has(cd) && (c.innerText || '').trim()) { hasBlockChild = true; break; }
    }
    if (hasBlockChild) continue;
    const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (text.length < 8) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 12) continue;
    const fs = parseFloat(st.fontSize) || 0;
    if (fs < 12) continue;
    if (el.checkVisibility && !el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    const x = Math.round(r.left + window.scrollX);
    const y = Math.round(r.top + window.scrollY);
    // 被 transform 移到画布外的抽屉/菜单，不作为正文
    if (x + r.width / 2 < 0 || x + r.width / 2 > pageW) continue;
    if (y + r.height / 2 < 0 || y + r.height / 2 > pageH) continue;
    const key = text.slice(0, 80) + '@' + x + ',' + y;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      tag,
      text,
      rect: [x, y, Math.round(r.width), Math.round(r.height)],
      fontSize: Math.round(fs * 10) / 10
    });
  }
  return out;
}
"""

_JS_METRICS = r"""
() => ({
  w: Math.max(
    document.documentElement ? document.documentElement.scrollWidth : 0,
    document.body ? document.body.scrollWidth : 0,
    window.innerWidth
  ),
  h: Math.max(
    document.documentElement ? document.documentElement.scrollHeight : 0,
    document.body ? document.body.scrollHeight : 0,
    window.innerHeight
  ),
  vw: window.innerWidth,
  vh: window.innerHeight
})
"""

# 在整页文本节点里定位原文片段；返回所有命中位置的矩形（页面坐标）。
# 规范化仅折叠空白，不做任何语义改写。
_JS_LOCATE_QUOTE = r"""
(quote) => {
  const norm = s => s.replace(/\s+/g, ' ').trim();
  const target = norm(quote || '');
  if (!target) return {found: false, matches: []};
  const walker = document.createTreeWalker(
    document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        const tag = p.tagName.toLowerCase();
        if (['script','style','noscript','textarea','select','option','svg'].includes(tag)) {
          return NodeFilter.FILTER_REJECT;
        }
        const st = getComputedStyle(p);
        if (st.display === 'none' || st.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
        return node.nodeValue ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    }
  );
  const nodes = [];
  const spans = [];
  let full = '';
  let n;
  while ((n = walker.nextNode())) {
    const raw = n.nodeValue || '';
    const start = full.length;
    full += raw;
    spans.push([start, start + raw.length, n]);
  }
  if (!full) return {found: false, matches: []};

  // 折叠空白并建立"规范化位置 → 原始位置"的映射
  let nfull = '';
  const map = [];
  let prevSpace = false;
  for (let i = 0; i < full.length; i++) {
    const ch = full[i];
    if (/\s/.test(ch)) {
      if (!prevSpace && nfull.length) { nfull += ' '; map.push(i); }
      prevSpace = true;
    } else {
      nfull += ch;
      map.push(i);
      prevSpace = false;
    }
  }
  while (nfull.endsWith(' ')) { nfull = nfull.slice(0, -1); map.pop(); }

  const nodeAt = off => {
    for (const sp of spans) {
      if (off >= sp[0] && off < sp[1]) return [sp[2], off - sp[0]];
    }
    if (off === full.length && spans.length) {
      const sp = spans[spans.length - 1];
      return [sp[2], sp[1] - sp[0]];
    }
    return null;
  };

  const toPage = r => [
    Math.round(r.left + window.scrollX),
    Math.round(r.top + window.scrollY),
    Math.round(r.width),
    Math.round(r.height)
  ];

  const matches = [];
  let from = 0;
  while (matches.length < 5) {
    const idx = nfull.indexOf(target, from);
    if (idx === -1) break;
    from = idx + Math.max(1, target.length);
    const rawStart = map[idx];
    const rawEnd = map[idx + target.length - 1] + 1;
    const s = nodeAt(rawStart);
    const e = nodeAt(Math.max(rawStart, rawEnd - 1));
    if (!s || !e) continue;
    const range = document.createRange();
    try {
      range.setStart(s[0], s[1]);
      range.setEnd(e[0], e[1] + 1);
    } catch (err) {
      continue;
    }
    const rects = [];
    for (const r of range.getClientRects()) {
      if (r.width < 2 || r.height < 2) continue;
      rects.push(toPage(r));
    }
    if (!rects.length) continue;
    const rr = range.getBoundingClientRect();
    matches.push({rects, union: toPage(rr)});
  }
  return {found: matches.length > 0, matches};
}
"""


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _union(rects: list[list[int]]) -> list[int]:
    if not rects:
        return [0, 0, 0, 0]
    x1 = min(r[0] for r in rects)
    y1 = min(r[1] for r in rects)
    x2 = max(r[0] + r[2] for r in rects)
    y2 = max(r[1] + r[3] for r in rects)
    return [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]


def _center_distance(a: list[int], b: list[int]) -> float:
    ax, ay = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
    return math.hypot(ax - bx, ay - by)


def _clean_rects(rects: list[list[int]]) -> list[list[int]]:
    """同行矩形合并、完全重复去重。Range 在嵌套内联元素上会返回重叠碎片。"""
    uniq: list[list[int]] = []
    seen: set[tuple] = set()
    for r in rects:
        key = (r[0], r[1], r[2], r[3])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(list(r))
    lines: list[list[int]] = []
    for r in sorted(uniq, key=lambda x: (x[1], x[0])):
        merged = False
        for ln in lines:
            if (abs(ln[1] - r[1]) <= 2 and abs(ln[3] - r[3]) <= 2
                    and r[0] <= ln[0] + ln[2] + 6):
                x2 = max(ln[0] + ln[2], r[0] + r[2])
                ln[0] = min(ln[0], r[0])
                ln[2] = x2 - ln[0]
                merged = True
                break
        if not merged:
            lines.append(list(r))
    return lines


class PageSession:
    """一次 Playwright 会话：所有坐标与截图都来自同一份页面状态。"""

    def __init__(self, width: int = DEFAULT_VIEW_W, height: int = DEFAULT_VIEW_H,
                 dpr: int = DEFAULT_DPR, timeout_ms: int = 45000):
        self.view_w = int(width or DEFAULT_VIEW_W)
        self.view_h = int(height or DEFAULT_VIEW_H)
        self.dpr = max(1, int(dpr or DEFAULT_DPR))
        self.timeout_ms = int(timeout_ms)
        self._pw = None
        self._browser = None
        self._ctx = None
        self.page = None

    def __enter__(self) -> "PageSession":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            viewport={"width": self.view_w, "height": self.view_h},
            device_scale_factor=self.dpr,
            locale="zh-CN",
            reduced_motion="reduce",
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        for obj in (self._ctx, self._browser):
            try:
                obj.close()
            except Exception:
                pass
        try:
            self._pw.stop()
        except Exception:
            pass

    # ── 打开与冻结 ──
    def open(self, url: str, *, settle_ms: int = SETTLE_MS) -> None:
        """打开主页面；新页面沿用同一 context（同视口、同字体）。"""
        if self.page is not None:
            self.close_page(self.page)
        self.page = self._new_page()
        self._goto(self.page, url, settle_ms=settle_ms)

    def _new_page(self):
        pg = self._ctx.new_page()
        pg.set_default_timeout(self.timeout_ms)
        pg.on("dialog", lambda d: d.dismiss())
        return pg

    def _goto(self, pg, url: str, *, settle_ms: int = SETTLE_MS,
              wait_until: str = "domcontentloaded") -> None:
        resp = pg.goto(url, wait_until=wait_until, timeout=self.timeout_ms)
        if resp is not None and resp.status >= 400:
            raise RuntimeError(f"页面返回 HTTP {resp.status}：{url}")
        try:
            pg.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        if settle_ms > 0:
            pg.wait_for_timeout(settle_ms)
        self.freeze(pg)

    @staticmethod
    def freeze(pg) -> None:
        try:
            pg.add_style_tag(content=_FREEZE_CSS)
        except Exception:
            pass
        try:
            pg.evaluate(
                "() => {"
                "  document.querySelectorAll('video,audio').forEach(m => {"
                "    try { m.pause(); m.currentTime = 0; } catch (e) {}"
                "  });"
                "  window.scrollTo(0, 0);"
                "}"
            )
        except Exception:
            pass

    def close_page(self, pg) -> None:
        try:
            pg.close()
        except Exception:
            pass

    # ── 页面信息 ──
    def metrics(self) -> dict:
        raw = self.page.evaluate(_JS_METRICS)
        return {
            "width": int(min(max(320, raw["w"]), MAX_OVERVIEW_W)),
            "height": int(max(240, raw["h"])),
            "viewport_width": int(raw["vw"]),
            "viewport_height": int(raw["vh"]),
        }

    def title(self) -> str:
        try:
            return (self.page.title() or "").strip()
        except Exception:
            return ""

    def extract_blocks(self) -> list[dict]:
        raw = self.page.evaluate(_JS_EXTRACT_BLOCKS) or []
        blocks = []
        for i, b in enumerate(raw):
            rect = [int(v) for v in (b.get("rect") or [0, 0, 0, 0])]
            blocks.append({
                "id": i + 1,
                "tag": str(b.get("tag") or ""),
                "text": str(b.get("text") or ""),
                "rect": rect,
                "fontSize": float(b.get("fontSize") or 0),
            })
        blocks.sort(key=lambda b: (b["rect"][1], b["rect"][0]))
        # 标题上下文：按文档顺序记录最近的标题，供选点模型判断段落归属
        section = ""
        for b in blocks:
            if b["tag"] in ("h1", "h2", "h3", "h4", "h5", "h6"):
                section = b["text"][:80]
            b["section"] = section
        return blocks

    def text_hash(self, blocks: list[dict]) -> str:
        import hashlib

        h = hashlib.sha1()
        for b in blocks:
            h.update(b["text"].encode("utf-8", errors="ignore"))
        h.update(self.title().encode("utf-8", errors="ignore"))
        return h.hexdigest()[:16]

    # ── 原文定位 ──
    def locate(self, quote: str, block_rect: list[int] | None = None) -> dict | None:
        """在页面里定位原文，返回离目标文本块最近的命中（页面坐标）。"""
        res = self.page.evaluate(_JS_LOCATE_QUOTE, quote) or {}
        matches = res.get("matches") or []
        if not matches:
            return None
        if block_rect:
            matches = sorted(matches, key=lambda m: _center_distance(m["union"], block_rect))
        best = matches[0]
        lines = _clean_rects([[int(v) for v in r] for r in (best.get("rects") or [])])
        if not lines:
            return None
        return {
            "rects": lines,
            "union": _union(lines),
        }

    # ── 截图 ──
    def capture_overview(self, y: int, h: int, width: int) -> tuple[bytes, dict]:
        import io

        from PIL import Image

        clip = {
            "x": 0,
            "y": max(0, int(y)),
            "width": int(width),
            "height": max(40, int(h)),
        }
        # Playwright 的 clip 不支持视口外区域（超长页会直接报错），统一整页截图再裁切
        Image.MAX_IMAGE_PIXELS = None
        full = self.page.screenshot(full_page=True, scale="css", type="png")
        im = Image.open(io.BytesIO(full))
        if (clip["x"], clip["y"], clip["width"], clip["height"]) != (0, 0, im.width, im.height):
            im = im.crop((
                clip["x"], clip["y"],
                clip["x"] + clip["width"], clip["y"] + clip["height"],
            ))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue(), clip

    # ── 候选页轻量摘要（不截图，只看标题与首屏文本） ──
    def probe(self, url: str, max_blocks: int = 14) -> dict:
        pg = self._new_page()
        try:
            self._goto(pg, url, settle_ms=450, wait_until="domcontentloaded")
            blocks = pg.evaluate(_JS_EXTRACT_BLOCKS) or []
            blocks.sort(key=lambda b: (b["rect"][1], b["rect"][0]))
            picked = []
            for b in blocks:
                text = str(b.get("text") or "").strip()
                if len(text) < 12:
                    continue
                picked.append(text[:180])
                if len(picked) >= max_blocks:
                    break
            return {"url": url, "title": (pg.title() or "").strip(), "excerpt": picked}
        finally:
            self.close_page(pg)


def save_png(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


__all__ = ["PageSession", "save_png", "MAX_OVERVIEW_H"]
