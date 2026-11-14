"""设计阶段预处理：解析来源 → 抓取页面 → 选出高亮原文 → 算坐标 → 冻结页面带。

产物目录：video_work/<project>/web/<capture_id>/
  overview.png   覆盖标注区域的页面带（1:1，供成片里在浏览器视口内滚动）
  capture.json   页面尺寸、文本块哈希、高亮矩形与页面带偏移
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .capture import (
    DEFAULT_DPR, DEFAULT_VIEW_H, DEFAULT_VIEW_W, MAX_OVERVIEW_H, PageSession, save_png,
)
from .resolve import resolve_source
from .select import DEFAULT_MARKS, extract_marks, shortlist, split_sentences

CAPTURE_VERSION = 3


class PrepareError(RuntimeError):
    """网页取景准备失败。user_url=True 表示用户明确指定的网址不可用，不应被替换。"""

    def __init__(self, message: str, *, user_url: bool = False):
        super().__init__(message)
        self.user_url = user_url


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _valid_url(url: str) -> bool:
    try:
        u = urlparse(url)
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def _rel(path: Path, cwd: Path) -> str:
    try:
        return str(path.resolve().relative_to(cwd.resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def _capture_dir(cwd: Path, project: str, cid: str) -> Path:
    return cwd / "video_work" / project / "web" / cid


def _cluster_marks(marks: list[dict], max_span: int) -> list[dict]:
    """超长页面里把高亮收敛到同一区域：选能装进概览窗口、且标注最多的那一段。"""
    if not marks:
        return []
    ordered = sorted(marks, key=lambda m: m["union"][1])
    best: list[dict] = []
    for i, anchor in enumerate(ordered):
        top = anchor["union"][1]
        group = [m for m in ordered[i:]
                 if m["union"][1] + m["union"][3] <= top + max_span]
        if len(group) > len(best):
            best = group
    return best or ordered[:1]


def _slim_marks(marks: list[dict], overview_y: int) -> list[dict]:
    out = []
    for m in marks:
        union = m["union"]
        stage_rect = [int(union[0]), int(union[1] - overview_y), int(union[2]), int(union[3])]
        lines = [
            [int(r[0]), int(r[1] - overview_y), int(r[2]), int(r[3])]
            for r in m["rects"]
        ]
        out.append({
            "quote": m["quote"],
            "reason": m.get("reason", ""),
            "cue": m.get("cue", -1),
            "block_id": m.get("block_id"),
            "page_rect": [int(v) for v in union],
            "rect": stage_rect,
            "lines": lines,
        })
    return out


def prepare_web(web: dict, *, project: str = "director", cwd: str = ".",
                llm_config: dict | None = None, skill_manager=None,
                narration: str = "", on_progress=None) -> dict:
    """执行一次完整取景，返回可直接写进蓝图的 web 对象（含 source/marks/坐标）。"""
    cfg = llm_config or {}
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        raise PrepareError("网页取景需要主 LLM 配置（base_url / api_key / model）")
    cwd_p = Path(cwd or ".")
    project = project or "director"

    web = dict(web or {})
    url = str(web.get("url") or "").strip()
    query = str(web.get("query") or "").strip()
    focus = str(web.get("focus") or "").strip()
    if not focus:
        focus = str(web.get("visual") or web.get("narration") or "").strip()
    try:
        max_marks = int(web.get("max_marks") or DEFAULT_MARKS)
    except (TypeError, ValueError):
        max_marks = DEFAULT_MARKS
    max_marks = max(1, min(4, max_marks))
    if not focus:
        raise PrepareError("webpage 段缺少 focus：必须写清这段要讲哪个知识点")

    user_url = bool(url)
    if url and not _valid_url(url):
        raise PrepareError(f"网址不是合法的 http(s) 地址：{url}", user_url=True)
    if not url and not query:
        raise PrepareError("webpage 段需要 web.url 或 web.query 至少一个")

    w = int(web.get("width") or DEFAULT_VIEW_W)
    h = int(web.get("height") or DEFAULT_VIEW_H)

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    try:
        with PageSession(width=w, height=h, dpr=DEFAULT_DPR) as sess:
            resolved = None
            if not url:
                log(f"自动解析来源：{query}")
                resolved = resolve_source(
                    sess, skill_manager, cfg,
                    query=query, focus=focus, narration=narration, on_progress=log,
                )
                url = resolved["url"]
                log(f"已选来源：{resolved.get('title') or url}（{resolved.get('reason') or '—'}）")

            log(f"打开页面：{url}")
            try:
                sess.open(url)
            except Exception as e:
                raise PrepareError(f"页面打开失败：{e}", user_url=user_url) from e

            metrics = sess.metrics()
            page_w, page_h = metrics["width"], metrics["height"]
            page_title = sess.title()
            log(f"页面已载入：{page_w}×{page_h}px")

            blocks = sess.extract_blocks()
            if not blocks:
                raise PrepareError("页面没有可读取的正文文本（可能是纯图片/视频页或反爬拦截）",
                                   user_url=user_url)
            page_hash = sess.text_hash(blocks)
            log(f"抽取文本块 {len(blocks)} 个")

            sentences = split_sentences(narration)
            log("挑选讲解段落与高亮原文...")
            picked = shortlist(cfg, blocks, focus=focus, narration=narration)
            if not picked:
                raise PrepareError("选段失败：模型没有从页面里挑出可讲的段落", user_url=user_url)
            raw_marks = extract_marks(
                cfg, picked, focus=focus, max_marks=max_marks,
                narration_sentences=sentences,
            )
            if not raw_marks:
                raise PrepareError("选点失败：模型没有挑出可逐字标注的原文", user_url=user_url)

            # 逐条回填精确矩形；定位失败的条目丢弃，全部失败则报错
            located: list[dict] = []
            for m in raw_marks:
                hit = sess.locate(m["quote"], m.get("block_rect"))
                if not hit:
                    log(f"标注定位失败，已跳过：{m['quote'][:24]}…")
                    continue
                located.append({**m, **hit})
            if not located:
                raise PrepareError("选中的原文在当前页面里定位不到（页面可能刚刷新），请重试",
                                   user_url=user_url)

            # 超长页面：把高亮收敛到同一区域，避免镜头横跨几万像素
            if page_h > MAX_OVERVIEW_H:
                clustered = _cluster_marks(located, MAX_OVERVIEW_H - 400)
                if len(clustered) < len(located):
                    log(f"标注跨度过大，已保留同一区域的 {len(clustered)} 处"
                        f"（原 {len(located)} 处）")
                    located = clustered

            # 概况图窗口：长页面以标注区域为中心取窗口，保证标注都落在图内
            all_top = min(m["union"][1] for m in located)
            all_bottom = max(m["union"][1] + m["union"][3] for m in located)
            if page_h <= MAX_OVERVIEW_H:
                overview_y, overview_h = 0, page_h
            else:
                span = all_bottom - all_top
                if span + 200 > MAX_OVERVIEW_H:
                    raise PrepareError(
                        f"页面过长（{page_h}px）且标注跨度 {span}px 超过单张概览图上限，"
                        "请换更聚焦的来源页", user_url=user_url)
                overview_y = int(_clamp(
                    (all_top + all_bottom) / 2 - MAX_OVERVIEW_H / 2,
                    0, page_h - MAX_OVERVIEW_H))
                overview_h = MAX_OVERVIEW_H
                if overview_y > all_top - 60:
                    overview_y = max(0, int(all_top - 60))
                if overview_y + overview_h < all_bottom + 60:
                    overview_y = min(page_h - overview_h, int(all_bottom + 60 - overview_h))
            # 标注必须完整落在舞台内
            bad = [m for m in located
                   if m["union"][1] < overview_y or m["union"][1] + m["union"][3] > overview_y + overview_h]
            if bad:
                raise PrepareError("标注区域落在概览图窗口之外，抓取失败", user_url=user_url)

            # 这条"页面带"会在成片里放进模拟浏览器视口内滚动，所以只需覆盖标注区域
            log(f"截图：页面带 {page_w}×{overview_h}px")
            overview_png, _ = sess.capture_overview(overview_y, overview_h, page_w)

            cid = hashlib.sha1(
                f"{url}|{focus}|{max_marks}|{page_hash}|{w}x{h}|v{CAPTURE_VERSION}"
                .encode("utf-8")
            ).hexdigest()[:12]
            cdir = _capture_dir(cwd_p, project, cid)
            cdir.mkdir(parents=True, exist_ok=True)
            save_png(cdir / "overview.png", overview_png)

            marks_out = _slim_marks(located, overview_y)
            for i, m in enumerate(marks_out, 1):
                m["id"] = f"m{i}"

            capture = {
                "version": CAPTURE_VERSION,
                "source": {
                    "url": url,
                    "title": page_title or (resolved or {}).get("title") or "",
                    "domain": (resolved or {}).get("domain") or (urlparse(url).netloc or ""),
                    "reason": (resolved or {}).get("reason") or web.get("reason") or "",
                },
                "viewport": {"width": w, "height": h, "dpr": DEFAULT_DPR},
                "page": {"width": page_w, "height": page_h, "hash": page_hash},
                "overview": {
                    "file": "overview.png",
                    "width": page_w,
                    "height": overview_h,
                    "y": overview_y,
                },
                "marks": marks_out,
                "captured_at": datetime.now().isoformat(timespec="seconds"),
            }
            (cdir / "capture.json").write_text(
                json.dumps(capture, ensure_ascii=False, indent=2), encoding="utf-8")

            enriched = {
                **web,
                "url": url,
                "query": query,
                "focus": focus,
                "max_marks": max_marks,
                "source": capture["source"],
                "capture_id": cid,
                "capture_dir": _rel(cdir, cwd_p),
                "page": capture["page"],
                "overview": capture["overview"],
                "marks": marks_out,
            }
            log(f"取景完成：{len(marks_out)} 处标注，来源 {capture['source']['domain']}")
            return enriched
    except PrepareError:
        raise
    except Exception as e:
        raise PrepareError(f"网页取景失败：{e}", user_url=user_url) from e


def load_capture(web: dict, cwd: str = ".") -> tuple[dict, Path]:
    """执行阶段读取设计阶段冻结的抓取结果；缓存缺失时明确报错。"""
    cdir_raw = str(web.get("capture_dir") or "").strip()
    cid = str(web.get("capture_id") or "").strip()
    cwd_p = Path(cwd or ".")
    if not cdir_raw:
        raise PrepareError("蓝图里没有 capture_dir：网页取景未在设计阶段完成")
    cdir = Path(cdir_raw)
    if not cdir.is_absolute():
        cdir = cwd_p / cdir
    meta_path = cdir / "capture.json"
    if not meta_path.is_file():
        raise PrepareError(f"网页取景缓存缺失：{meta_path}（请重新设计蓝图或重跑该段）")
    try:
        capture = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise PrepareError(f"网页取景缓存损坏：{e}") from e
    for name in ["overview.png"] + [m.get("zoom", {}).get("file", "") for m in capture.get("marks", [])]:
        if name and not (cdir / name).is_file():
            raise PrepareError(f"网页取景图片缺失：{cdir / name}")
    if cid and capture.get("version") != CAPTURE_VERSION:
        raise PrepareError("网页取景缓存版本过旧，请重新设计蓝图")
    return capture, cdir


__all__ = ["PrepareError", "prepare_web", "load_capture", "CAPTURE_VERSION"]
