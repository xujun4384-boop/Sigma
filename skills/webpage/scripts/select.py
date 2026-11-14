"""选点：从真实页面文本里挑出可标注的原文片段（两阶段，避免长文超出上下文）。"""
from __future__ import annotations

import re

from .common import call_json, load_prompt, normalized

MAX_SHORTLIST_BLOCKS = 240
MAX_SELECTED_BLOCKS = 10
SHORT_PREVIEW = 100
FULL_BLOCK_CHARS = 1400
DEFAULT_MARKS = 3
MAX_MARKS = 4


def split_sentences(text: str) -> list[str]:
    """按中英文句末标点切句；只用于旁白对齐，不改写原文。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", raw)
    return [p.strip() for p in parts if p.strip()]


def _compact_blocks(blocks: list[dict]) -> list[dict]:
    """长页面按正文长度取前 300 个块，再按文档顺序还原；不按关键词筛选。"""
    if len(blocks) <= MAX_SHORTLIST_BLOCKS:
        return blocks
    ranked = sorted(blocks, key=lambda b: -len(b.get("text") or ""))
    keep = {id(b) for b in ranked[:MAX_SHORTLIST_BLOCKS]}
    return [b for b in blocks if id(b) in keep]


def shortlist(cfg: dict, blocks: list[dict], *, focus: str, narration: str = "") -> list[dict]:
    picked = _compact_blocks(blocks)
    lines = []
    for b in picked:
        text = (b.get("text") or "").replace("\n", " ")
        lines.append(f"[{b['id']}] {b.get('section') or '—'} :: {text[:SHORT_PREVIEW]}")
    system = load_prompt("shortlist")
    context = (
        f"知识点（focus）：{focus}\n"
        + (f"本段旁白：{narration}\n" if narration else "")
        + f"\n页面文本块（共 {len(picked)} 个）：\n"
        + "\n".join(lines)
        + "\n\n只输出 JSON。"
    )
    data = call_json(cfg, system, context, max_tokens=3000, timeout=150)
    ids = data.get("blocks")
    if not isinstance(ids, list):
        return []
    wanted = []
    for v in ids:
        try:
            bid = int(v)
        except (TypeError, ValueError):
            continue
        if bid not in wanted:
            wanted.append(bid)
        if len(wanted) >= MAX_SELECTED_BLOCKS:
            break
    by_id = {b["id"]: b for b in picked}
    return [by_id[i] for i in wanted if i in by_id]


def extract_marks(cfg: dict, selected: list[dict], *, focus: str, max_marks: int,
                  narration_sentences: list[str] | None = None) -> list[dict]:
    max_marks = max(1, min(MAX_MARKS, int(max_marks or DEFAULT_MARKS)))
    sentences = narration_sentences or []
    blocks_text = "\n\n".join(
        f"[{b['id']}]（{b.get('section') or '无小标题'}）\n{(b.get('text') or '')[:FULL_BLOCK_CHARS]}"
        for b in selected
    )
    system = load_prompt("extract_marks")
    cues = ""
    if sentences:
        cues = "\n旁白分句：\n" + "\n".join(f"[{i}] {s}" for i, s in enumerate(sentences))
    errors: list[str] = []
    for attempt in range(1, 4):
        context = (
            f"知识点（focus）：{focus}\n"
            f"最多 {max_marks} 处高亮。\n"
            + cues + "\n\n"
            + f"可选文本块（原文完整内容，按块截断至 {FULL_BLOCK_CHARS} 字）：\n{blocks_text}\n\n"
            + ("上次输出有问题，只修这些：\n" + "\n".join(errors) + "\n\n" if errors else "")
            + "只输出 JSON。"
        )
        data = call_json(cfg, system, context, max_tokens=4000, timeout=150)
        marks = _validate(data, selected, max_marks, len(sentences))
        if marks:
            return marks
        errors = ["没有可用的 marks：quote 必须是所选文本块里逐字存在的连续原文，并且在 1~120 字之间"]
    return []


def _validate(data: dict, selected: list[dict], max_marks: int,
              cue_count: int) -> list[dict]:
    raw = data.get("marks")
    if not isinstance(raw, list):
        return []
    by_id = {b["id"]: b for b in selected}
    out: list[dict] = []
    seen_quotes: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            bid = int(item.get("block_id"))
        except (TypeError, ValueError):
            continue
        block = by_id.get(bid)
        if block is None:
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote or len(quote) < 4 or len(quote) > 120:
            continue
        if normalized(quote) not in normalized(block.get("text") or ""):
            continue
        if quote in seen_quotes:
            continue
        seen_quotes.add(quote)
        cue = item.get("cue")
        try:
            cue_i = int(cue)
        except (TypeError, ValueError):
            cue_i = -1
        if cue_count > 0 and not (0 <= cue_i < cue_count):
            cue_i = -1
        out.append({
            "block_id": bid,
            "quote": quote,
            "reason": str(item.get("reason") or "").strip()[:160],
            "cue": cue_i,
            "block_rect": block.get("rect") or [0, 0, 0, 0],
        })
        if len(out) >= max_marks:
            break
    if cue_count > 0:
        # cue 缺失时按顺序补，保证高亮有先后
        last = 0
        for m in out:
            if m["cue"] < 0:
                m["cue"] = min(last, cue_count - 1)
            last = max(last, m["cue"])
    return out


__all__ = ["split_sentences", "shortlist", "extract_marks"]
