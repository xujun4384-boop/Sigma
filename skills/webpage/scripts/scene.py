"""把抓取结果整理成合成用的场景规格（页面带、滚动定位、批注内容、旁白落点）。

成片形态：画面里有一个模拟浏览器窗口，网页在视口内 1:1 滚动；
每处高亮配一条批注（原文摘录 + 解释）。窗口与批注的摆放位置由 LLM 决定，
这里只给几何数据（页面坐标、滚动目标、时间窗），不做版式硬编码。
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .select import split_sentences

# 建议视口尺寸：浏览器窗口约占画面 2/3 宽，留出批注区。
# 只是参考值，LLM 可以改；改视口高度时按 anchor_y 自行换算滚动值。
VIEW_RATIO_W = 0.66
VIEW_RATIO_H = 0.82
CHROME_H = 56


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _word_char_times(words: list[dict]) -> tuple[str, list[float]]:
    """把字级时间戳展开成「字符 → 开始时间」，忽略空白，用于旁白分句对齐。"""
    chars: list[str] = []
    times: list[float] = []
    for w in words or []:
        txt = str(w.get("word") or w.get("text") or "")
        if not txt:
            continue
        try:
            t = float(w.get("startTime") or 0.0)
        except (TypeError, ValueError):
            t = 0.0
        for ch in txt:
            if ch.isspace():
                continue
            chars.append(ch)
            times.append(t)
    return "".join(chars), times


def sentence_start_times(narration: str, words: list[dict]) -> list[float]:
    """按旁白分句返回每句开始时间；对不上时返回空列表，由调用方退化为均分。"""
    sentences = split_sentences(narration)
    compact, times = _word_char_times(words)
    if not sentences or not compact:
        return []
    out: list[float] = []
    cursor = 0
    for sent in sentences:
        key = "".join(ch for ch in sent if not ch.isspace())
        if not key:
            continue
        idx = compact.find(key, cursor)
        if idx == -1:
            # 长句可能被 TTS 标点切碎，退化用前 12 个字符找起点
            idx = compact.find(key[:12], cursor)
        if idx == -1:
            return []
        out.append(times[idx] if idx < len(times) else (times[-1] if times else 0.0))
        cursor = idx + max(1, len(key))
    return out


def scroll_target(anchor_y: float, viewport_h: float, page_h: float) -> int:
    """让标注竖向居中的滚动偏移（页面图上边缘为 0）。"""
    max_scroll = max(0.0, page_h - viewport_h)
    return int(round(_clamp(anchor_y - viewport_h / 2, 0, max_scroll)))


def min_read_seconds(quote: str, explain: str, slot: float) -> float:
    """按批注文字量估算"必须静止可读"的秒数，并保证不挤占入场/退场。"""
    chars = len(quote or "") + len(explain or "")
    need = _clamp(chars / 12.0, 1.4, 3.2)
    return round(min(need, max(0.8, float(slot) - 0.9)), 2)


def _timings(duration: float, count: int, narration: str, words: list[dict],
             cues: list[int]) -> tuple[float, list[float], list[float]]:
    """返回 (片头结束时间, 每处出现时间, 每处结束时间)。"""
    starts = sentence_start_times(narration, words)
    intro_end = min(1.8, max(0.8, duration * 0.12))
    if starts:
        # 旁白很早就讲到第一个重点时压缩片头，别让高亮比讲解晚太多
        intro_end = min(intro_end, max(0.5, starts[0] - 0.4))

    n = max(1, count)
    # 第一条的滚动要在片头结束之后才开始（留出一次滚动 + 落地缓冲）
    cursor = min(intro_end + 0.8, max(0.2, duration - 0.4))
    span = max(0.4, duration - cursor)
    slot = span / n
    begins: list[float] = []
    ends: list[float] = []
    prev = cursor
    for i, cue in enumerate(cues):
        if starts and isinstance(cue, int) and 0 <= cue < len(starts):
            t = starts[cue]
        else:
            t = cursor + i * slot
        t = _clamp(t, prev, max(prev, duration - 0.2))
        begins.append(t)
        ends.append(duration if i == n - 1 else min(duration, t + slot))
        prev = t
    return intro_end, begins, ends


def copy_assets(capture: dict, capture_dir: Path, assets_dir: Path) -> dict:
    """把页面带截图复制进 HyperFrames 项目的 assets/。"""
    assets_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    name = (capture.get("overview") or {}).get("file") or "overview.png"
    src = capture_dir / name
    if src.is_file():
        shutil.copyfile(src, assets_dir / "page.png")
        mapping[name] = "assets/page.png"
    return mapping


def build_scene(capture: dict, *, duration: float, width: int, height: int, fps: int,
                narration: str = "", narration_words: list[dict] | None = None,
                style_prompt: str = "", assets: dict | None = None) -> dict:
    assets = assets or {}
    ov = capture["overview"]
    page_w, page_h = int(ov["width"]), int(ov["height"])
    marks_in = capture.get("marks") or []

    view_w = int(round(width * VIEW_RATIO_W))
    view_h = int(round(height * VIEW_RATIO_H)) - CHROME_H
    view_h = int(_clamp(view_h, 240, page_h))

    marks = []
    for m in marks_in:
        rect = [int(v) for v in m["rect"]]
        lines = [[int(x) for x in ln] for ln in (m.get("lines") or [rect])]
        anchor_y = rect[1] + rect[3] / 2
        marks.append({
            "id": m["id"],
            "quote": m.get("quote", ""),
            "explain": m.get("reason", ""),
            "rect": rect,
            "lines": lines,
            "anchor_y": round(anchor_y, 1),
            "scroll_y": scroll_target(anchor_y, view_h, page_h),
        })

    intro_end, begins, ends = _timings(
        float(duration), len(marks), narration, narration_words or [],
        [m.get("cue", -1) for m in marks_in],
    )

    notes = []
    for i, m in enumerate(marks):
        slot = ends[i] - begins[i]
        notes.append({
            "id": m["id"],
            "index": i + 1,
            "quote": m["quote"],
            "explain": m["explain"],
            "mark": {"rect": m["rect"], "lines": m["lines"]},
            "anchor_y": m["anchor_y"],
            "scroll_y": m["scroll_y"],
            "at": round(begins[i], 2),
            "until": round(ends[i], 2),
            "min_read": min_read_seconds(m["quote"], m["explain"], slot),
        })

    return {
        "canvas": {"width": width, "height": height, "fps": fps},
        "duration": round(float(duration), 2),
        "source": capture.get("source") or {},
        "page": {
            "src": assets.get((ov.get("file") or "overview.png"), ""),
            "width": page_w,
            "height": page_h,
        },
        "viewport": {
            "width": view_w,
            "height": view_h,
            "chrome_height": CHROME_H,
            "note": "建议尺寸，可按版式调整；改高度后按 anchor_y - viewport.height/2 重算滚动值",
        },
        "intro": {"scroll_y": 0, "end": round(intro_end, 2)},
        # 节奏建议值：滚动慢一点，批纳入场从容，读得完再走
        "pacing": {"scroll": 0.7, "enter": 0.9, "exit_lead": 0.35},
        "notes": notes,
        "style": style_prompt or "",
    }


__all__ = ["build_scene", "copy_assets", "sentence_start_times", "scroll_target"]
