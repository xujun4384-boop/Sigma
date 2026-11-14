"""画面几何审计。

后端不持有笔迹数据，但前端会把每笔的包围盒、长度、是否闭合回传过来。
这些都是按真实采样点算出的数值，因此可以给出可核对的结论，
不依赖视觉模型的主观判断。

设计取舍：只报告**能确证**的问题。宁可漏报，也不报"看起来偏了"这类
无法核对的说法——上一版开放式的视觉审查就因此误报过一堆并不存在的对齐问题，
反而让模型把已经画对的结构改坏。
"""
from __future__ import annotations

from typing import Any

# 越界容差：边缘轻微压线不算问题，超过这个像素才算冲出画布
OUT_OF_BOUNDS_TOLERANCE = 2
# 判定重影的包围盒重合度阈值
DUPLICATE_IOU = 0.92
# 长度比容差：两笔长度差太多就不是同一根线的重画
DUPLICATE_LENGTH_RATIO = 0.2
# 大轮廓的判定下限：包围盒两边都超过这个尺寸，才算"外框级"线条
BIG_FRAME_MIN_SIDE = 300
BIG_FRAME_MIN_LENGTH = 400

# 用于勾线的笔刷；只有它们画出来的大线条才要求闭合
OUTLINE_BRUSHES = ("pencil", "ink")


def _iou(a: list[float], b: list[float]) -> float:
    """两个包围盒的交并比。"""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _num(value: Any, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def _normalize(stroke_audit: Any) -> list[dict[str, Any]]:
    """把前端回传的笔迹数据整理成统一结构，脏数据直接丢弃，不让审计崩溃。"""
    if not isinstance(stroke_audit, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in stroke_audit:
        if not isinstance(raw, dict):
            continue
        bbox = raw.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x0, y0, x1, y1 = (_num(v) for v in bbox)
        items.append({
            "id": str(raw.get("id") or ""),
            "layer": str(raw.get("layer") or ""),
            "brush": str(raw.get("brush") or ""),
            "color": str(raw.get("color") or ""),
            "bbox": [x0, y0, x1, y1],
            "length": _num(raw.get("length")),
            "closed": bool(raw.get("closed")),
        })
    return items


def audit(
    stroke_audit: Any,
    layers: list[str] | None = None,
    width: int = 1600,
    height: int = 1000,
) -> dict[str, Any]:
    """返回审计结论：图层几何摘要 + 可确证的问题列表。"""
    strokes = _normalize(stroke_audit)
    layer_ids = [str(x) for x in (layers or [])]
    issues: list[dict[str, Any]] = []
    facts: list[str] = []

    # ── 越界 ──
    for stroke in strokes:
        x0, y0, x1, y1 = stroke["bbox"]
        over = []
        if x0 < -OUT_OF_BOUNDS_TOLERANCE:
            over.append(f"左边界超出 {abs(x0):.0f}px")
        if y0 < -OUT_OF_BOUNDS_TOLERANCE:
            over.append(f"上边界超出 {abs(y0):.0f}px")
        if x1 > width + OUT_OF_BOUNDS_TOLERANCE:
            over.append(f"右边界超出 {x1 - width:.0f}px")
        if y1 > height + OUT_OF_BOUNDS_TOLERANCE:
            over.append(f"下边界超出 {y1 - height:.0f}px")
        if over:
            issues.append({
                "type": "out_of_bounds",
                "ids": [stroke["id"]],
                "message": f"{stroke['id']} 冲出画布：{'、'.join(over)}",
            })

    # ── 重影：同图层同色同笔刷、包围盒几乎重合、长度接近 ──
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for stroke in strokes:
        key = (stroke["layer"], stroke["brush"], stroke["color"])
        groups.setdefault(key, []).append(stroke)

    reported: set[str] = set()
    for group in groups.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["id"] in reported and b["id"] in reported:
                    continue
                if _iou(a["bbox"], b["bbox"]) < DUPLICATE_IOU:
                    continue
                base = max(a["length"], b["length"])
                if base <= 0:
                    continue
                if abs(a["length"] - b["length"]) / base > DUPLICATE_LENGTH_RATIO:
                    continue
                reported.add(a["id"])
                reported.add(b["id"])
                issues.append({
                    "type": "duplicate",
                    "ids": [a["id"], b["id"]],
                    "message": (
                        f"{a['id']} 与 {b['id']} 同图层、同笔刷、同颜色，"
                        f"包围盒重合 {_iou(a['bbox'], b['bbox']) * 100:.0f}%，长度也接近，疑似重复描边"
                    ),
                })

    # ── 大轮廓未闭合：外框级别的线条，勾线笔刷却没收口 ──
    for stroke in strokes:
        if stroke["brush"] not in OUTLINE_BRUSHES or stroke["closed"]:
            continue
        x0, y0, x1, y1 = stroke["bbox"]
        if (x1 - x0) < BIG_FRAME_MIN_SIDE or (y1 - y0) < BIG_FRAME_MIN_SIDE:
            continue
        if stroke["length"] < BIG_FRAME_MIN_LENGTH:
            continue
        issues.append({
            "type": "open_frame",
            "ids": [stroke["id"]],
            "message": (
                f"{stroke['id']} 是 {x1 - x0:.0f}×{y1 - y0:.0f} 的大轮廓但首尾未闭合，"
                "边缘可能留下开口断点"
            ),
        })

    # ── 图层几何摘要：给模型可核对的数字，用来否证"看起来偏了"这类猜测 ──
    per_layer: dict[str, list[dict[str, Any]]] = {layer: [] for layer in layer_ids}
    for stroke in strokes:
        per_layer.setdefault(stroke["layer"], []).append(stroke)

    for layer in layer_ids or list(per_layer.keys()):
        group = per_layer.get(layer) or []
        if not group:
            facts.append(f"图层 {layer}：空图层，没有任何笔迹")
            continue
        x0 = min(s["bbox"][0] for s in group)
        y0 = min(s["bbox"][1] for s in group)
        x1 = max(s["bbox"][2] for s in group)
        y1 = max(s["bbox"][3] for s in group)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        offset = cx - width / 2
        offset_text = "居中" if abs(offset) <= 4 else f"水平偏移 {offset:+.0f}px"
        facts.append(
            f"图层 {layer}：{len(group)} 笔，范围 x {x0:.0f}–{x1:.0f}，y {y0:.0f}–{y1:.0f}，"
            f"中心 ({cx:.0f}, {cy:.0f})，{offset_text}"
        )

    return {
        "stroke_count": len(strokes),
        "issues": issues,
        "facts": facts,
        "width": width,
        "height": height,
    }


def render(result: dict[str, Any]) -> str:
    """把审计结果渲染成给模型看的文本块。"""
    lines = [
        "【几何审计】以下数值由笔迹坐标精确计算，不是目测，可直接采信：",
        f"画布 {result['width']}×{result['height']}，共 {result['stroke_count']} 笔",
    ]
    lines.extend(result["facts"])

    issues = result["issues"]
    if issues:
        lines.append(f"确证问题 {len(issues)} 项：")
        lines.extend(f"- {item['message']}" for item in issues)
    else:
        lines.append("几何检查未发现越界、重影或大轮廓开口。")

    return "\n".join(lines)
