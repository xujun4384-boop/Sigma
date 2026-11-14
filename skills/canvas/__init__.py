"""Canvas skill - 绘画画布指令工具。

模型输出的是绘图指令（少量控制点 + 图形描述），不是像素或坐标阵列。
引擎负责把指令展开成笔迹，并按笔刷质感逐笔绘制出来。
"""
from __future__ import annotations

from typing import Any, Callable

import paint_canvas
from skills.base import BaseTool, ToolParameter, ToolResult
from skills.image_reader import describe_image_b64
from . import audit

# 同一轮任务内允许的自我审查次数。超过后强制收敛，避免模型无限自审。
MAX_REVIEWS = 3

# 审查提示词：位置、越界、重复这些已经由几何审计精确核对过，
# 视觉模型只负责它真正擅长的事——看得出来画的是什么、比例形态像不像。
REVIEW_PROMPT = (
    "你在看一张刚画完的图。位置、越界、重复描边已经用坐标精确核对过，"
    "你不需要也不要去判断这些，不要评价是否居中、间距是否均匀、有没有出界。\n"
    "只回答两件事：\n"
    "1. 这画的是什么？主体是否一眼可辨\n"
    "2. 比例与形态有没有明显别扭的地方（头身比失衡、部件大小严重不符、形状走样、部件缺失）\n"
    "只输出问题，不要夸奖、不要复述画面内容。每条不超过 25 字，格式为「问题 → 修正」。最多 3 条。\n"
    "如果没有明显问题，只回答：通过"
)

# 与前端 src/paint/brushes.ts 的注册表保持一致
BRUSH_NAMES = ("pencil", "charcoal", "marker", "watercolor", "ink")

# 与前端 src/paint/protocol.ts 的指令集保持一致
COMMAND_OPS = ("stroke", "layer", "remove", "clearLayer", "clear")

PATH_TYPES = ("curve", "polyline", "bezier", "ellipse", "rect")

# 画风注册表：题材决定笔刷分配。不是关键词打分，而是模型显式声明本次画什么风格。
# 机械/建筑这类直线结构必须干净，动物/风景这类柔和题材可以晕染。
STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "precise": {
        "label": "精准线条（机械/车辆/建筑/产品/家具/平面图）",
        "outline": ("pencil", "ink"),
        "fill": ("marker", "watercolor"),
        "detail": ("ink", "pencil", "charcoal"),
        "note": "结构线与填色块用马克笔保持干净；水彩仅用于大面积背景铺底，禁止描边",
    },
    "organic": {
        "label": "自然晕染（动物/人物/植物/风景/食物）",
        "outline": ("pencil", "ink"),
        "fill": ("watercolor", "marker"),
        "detail": ("ink", "pencil", "marker", "charcoal"),
        "note": "轮廓用铅笔/墨水笔勾线，上色用水彩或马克笔",
    },
    "technical": {
        "label": "技术图解（流程图/示意图/表格/架构）",
        "outline": ("ink",),
        "fill": ("marker",),
        "detail": ("ink",),
        "note": "只用墨水笔和马克笔，禁止炭笔和水彩",
    },
}

DEFAULT_STYLE = "organic"

# 图层用途关键词：判断一条笔迹在该图层上是"勾线"还是"上色"
OUTLINE_LAYER_KEYS = ("outline", "line", "轮廓", "线稿", "勾线")
# background 放最后匹配，避免 "background-color" 被误判为勾线
FILL_LAYER_KEYS = ("color", "fill", "wash", "背景", "上色", "底色", "paint", "background")


def _layer_role(layer: str) -> str:
    lowered = layer.lower()
    if any(key in lowered for key in OUTLINE_LAYER_KEYS):
        return "outline"
    if any(key in lowered for key in FILL_LAYER_KEYS):
        return "fill"
    return "detail"

MIN_WIDTH = 0.4
MAX_WIDTH = 200


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_points(points: Any, field: str, min_count: int) -> str | None:
    if not isinstance(points, list):
        return f"{field} 必须是坐标数组，例如 [[100,100],[200,150]]"
    if len(points) < min_count:
        return f"{field} 至少需要 {min_count} 个点，收到 {len(points)} 个"
    for i, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return f"{field}[{i}] 应为 [x, y]"
        if not _is_number(point[0]) or not _is_number(point[1]):
            return f"{field}[{i}] 的坐标必须是数字"
    return None


def _validate_path(path: Any, field: str = "path") -> str | None:
    if not isinstance(path, dict):
        return f"{field} 必须是对象"
    kind = path.get("type")
    if kind not in PATH_TYPES:
        return f"{field}.type 必须是 {' / '.join(PATH_TYPES)} 之一，收到 {kind}"
    if kind in ("curve", "polyline"):
        error = _check_points(path.get("points"), f"{field}.points", 2)
        if error:
            return error
        smooth = path.get("smooth")
        if smooth is not None and (not _is_number(smooth) or smooth < 0 or smooth > 30):
            return f"{field}.smooth 必须在 0 到 30 之间"
        return None
    if kind == "bezier":
        error = _check_points(path.get("points"), f"{field}.points", 4)
        if error:
            return error
        if (len(path["points"]) - 1) % 3 != 0:
            return f"{field}.points 数量必须是 1 + 3n，当前 {len(path['points'])} 个"
        return None
    if kind == "ellipse":
        for key in ("cx", "cy", "rx", "ry"):
            if not _is_number(path.get(key)):
                return f"{field}.{key} 必须是数字"
        for key in ("from", "to", "rotation"):
            if path.get(key) is not None and not _is_number(path.get(key)):
                return f"{field}.{key} 必须是数字（单位：度）"
        return None
    # rect
    for key in ("x", "y"):
        if not _is_number(path.get(key)):
            return f"{field}.{key} 必须是数字"
    for key in ("width", "height"):
        if not _is_number(path.get(key)) or path.get(key) <= 0:
            return f"{field}.{key} 必须是大于 0 的数字"
    radius = path.get("radius")
    if radius is not None and (not _is_number(radius) or radius < 0):
        return f"{field}.radius 必须是非负数字"
    return None


def validate_commands(commands: Any, style: str = DEFAULT_STYLE) -> tuple[list[dict], list[str]]:
    """校验绘图指令，返回（可用指令, 问题说明）。问题说明可直接回喂给模型去修。"""
    if not isinstance(commands, list):
        return [], ["commands 必须是数组"]
    if not commands:
        return [], ["commands 不能为空"]

    preset = STYLE_PRESETS.get(style, STYLE_PRESETS[DEFAULT_STYLE])
    usable: list[dict] = []
    issues: list[str] = []
    seen_ids: set[str] = set()

    for index, raw in enumerate(commands):
        label = f"第 {index + 1} 条指令"
        if not isinstance(raw, dict):
            issues.append(f"{label}必须是对象")
            continue
        op = raw.get("op")
        if op not in COMMAND_OPS:
            issues.append(f"{label}的 op 必须是 {' / '.join(COMMAND_OPS)} 之一，收到 {op}")
            continue

        if op == "stroke":
            stroke_id = raw.get("id")
            if not isinstance(stroke_id, str) or not stroke_id.strip():
                issues.append(f"{label}（stroke）必须带 id，用于后续修正与撤销")
                continue
            if stroke_id in seen_ids:
                issues.append(f"{label}的 id \"{stroke_id}\" 与前面的笔迹重复，每条笔迹的 id 必须唯一")
                continue
            layer = raw.get("layer")
            if not isinstance(layer, str) or not layer.strip():
                issues.append(f"{label}（{stroke_id}）必须指定 layer（图层 id，不存在会自动创建）")
                continue
            brush = raw.get("brush")
            if brush not in BRUSH_NAMES:
                issues.append(
                    f"{label}（{stroke_id}）的 brush 必须是 {' / '.join(BRUSH_NAMES)} 之一，收到 {brush}"
                )
                continue
            width = raw.get("width")
            if width is not None and (not _is_number(width) or width < MIN_WIDTH or width > MAX_WIDTH):
                issues.append(f"{label}（{stroke_id}）的 width 必须在 {MIN_WIDTH} 到 {MAX_WIDTH} 之间")
                continue
            opacity = raw.get("opacity")
            if opacity is not None and (not _is_number(opacity) or opacity < 0 or opacity > 1):
                issues.append(f"{label}（{stroke_id}）的 opacity 必须在 0 到 1 之间")
                continue
            path_error = _validate_path(raw.get("path"))
            if path_error:
                issues.append(f"{label}（{stroke_id}）的 {path_error}")
                continue

            # 画风约束：当前笔刷与该图层用途是否匹配
            role = _layer_role(str(layer))
            allowed = preset.get(role, preset["detail"])
            if brush not in allowed:
                issues.append(
                    f"{label}（{stroke_id}）在当前画风（{style}）下，"
                    f"图层「{layer}」允许的笔刷为 {' / '.join(allowed)}，收到 {brush}。"
                    f"建议：{'；'.join(preset.get('note', '').split('；'))}"
                )
                continue
            # 宽笔不能当描边笔：宽度超过 8 的水彩会糊成色块，强行收窄
            if brush == "watercolor" and role == "outline":
                issues.append(f"{label}（{stroke_id}）不允许用 watercolor 勾线")
                continue
            seen_ids.add(stroke_id)
            usable.append(raw)
            continue

        if op == "layer":
            layer_id = raw.get("id")
            if not isinstance(layer_id, str) or not layer_id.strip():
                issues.append(f"{label}（layer）必须带 id")
                continue
            opacity = raw.get("opacity")
            if opacity is not None and (not _is_number(opacity) or opacity < 0 or opacity > 1):
                issues.append(f"{label}（{layer_id}）的 opacity 必须在 0 到 1 之间")
                continue
            usable.append(raw)
            continue

        if op == "remove":
            if not isinstance(raw.get("id"), str) or not str(raw.get("id")).strip():
                issues.append(f"{label}（remove）必须带要删除的笔迹 id")
                continue
            usable.append(raw)
            continue

        if op == "clearLayer":
            if not isinstance(raw.get("layer"), str) or not str(raw.get("layer")).strip():
                issues.append(f"{label}（clearLayer）必须指定 layer")
                continue
            usable.append(raw)
            continue

        usable.append(raw)

    return usable, issues


class CanvasDrawTool(BaseTool):
    """把绘图指令推送到前端画布，逐笔绘制出来。"""

    name = "canvas_draw"
    description = (
        "在 Sigma 绘画画布上作画。不要逐点描述像素，而是给少量控制点和图形描述，"
        "引擎会用真实笔刷（铅笔/炭笔/马克笔/水彩/墨水笔）把每一笔画出来，用户在屏幕上能看到笔迹逐步生长。\n"
        "画布逻辑尺寸 1600×1000，坐标 (0,0) 在左上角。\n"
        "核心规则：\n"
        "1. 必须分层画。用 layer 指令先声明图层，顺序即上下层关系（先声明的在下层）。"
        "推荐顺序：背景 → 上色 → 线稿 → 细节。\n"
        "2. 一条笔迹 = 一个 stroke 指令，必须带唯一 id、layer、brush、path。"
        "带文字或形状的部分不要用矩形拼接，直接用 path 描述轮廓。\n"
        "3. path 优先用图形原语，不要写密集坐标："
        "ellipse 画圆和椭圆，rect 画方框，bezier 画流畅曲线，curve 用 3~8 个控制点让引擎平滑插值。\n"
        "4. 修正已有内容用 remove 指令指定 id 删除后重画，不要整张重来。\n"
        "5. 线条要分笔：轮廓一笔、耳朵一笔、尾巴一笔。每笔 3~10 个控制点即可，"
        "点太密反而僵硬，点太少会失真。\n"
        "6. 必须显式选择 style（画风），由题材决定：\n"
        "   precise（精准线条）— 车辆/机械/建筑/产品/家具，勾线只允许 pencil 或 ink，上色只允许 marker\n"
        "   organic（自然晕染）— 动物/人物/植物/风景/食物，勾线 pencil/ink，上色 watercolor/marker\n"
        "   technical（技术图解）— 流程图/示意图/表格，只允许 ink 和 marker\n"
        "   选错风格或笔刷与图层用途不符的指令会被拒绝并返回修正提示。\n"
        "7. 几何对齐：precise 题材的同组元素（轮子、窗户、齿格）必须同高、同半径、等间距，"
        "先确定基准值再逐个算坐标；水平边 y 相同、垂直边 x 相同。\n"
        "8. 画完一轮后必须调用 canvas_review 自查。它会把画面问题列成「问题 → 修正」返回，"
        "按清单用 remove + stroke 修掉，直到审查通过或达到次数上限。\n"
        "笔刷选择：pencil 铅笔（勾线、草稿）、ink 墨水笔（干净硬边线）、"
        "marker 马克笔（色块、条纹）、watercolor 水彩（大面积上色）、charcoal 炭笔（阴影、质感）。"
    )
    parameters = [
        ToolParameter(
            "commands",
            "array",
            "绘图指令数组。支持的 op：stroke（画一笔）、layer（声明图层）、"
            "remove（按 id 删除一笔）、clearLayer（清空某图层）、clear（清空全部）。"
            "stroke 结构：{op:'stroke', id:'s1', layer:'outline', brush:'pencil', "
            "color:'#3a3733', width:3, opacity:1, path:{type:'curve', points:[[100,100],[200,150]], smooth:8}}。"
            "path.type 可选：curve（points+smooth）、polyline（points）、"
            "bezier（points，数量为 1+3n）、ellipse（cx/cy/rx/ry，可选 from/to/rotation，单位度）、"
            "rect（x/y/width/height，可选 radius）。"
            "layer 结构：{op:'layer', id:'outline', name:'线稿', visible:true, opacity:1}。",
            required=True,
        ),
        ToolParameter(
            "style",
            "string",
            "画风：precise（精准线条，机械/车辆/建筑）、organic（自然晕染，动物/人物/风景）、"
            "technical（技术图解）。必须由题材决定，不是按个人喜好选。",
            required=False,
            enum=list(STYLE_PRESETS.keys()),
            default=DEFAULT_STYLE,
        ),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)
        self._progress_callback: Callable[[dict[str, Any]], None] | None = None

    def set_progress_callback(self, callback: Callable[[dict[str, Any]], None] | None) -> None:
        self._progress_callback = callback

    def execute(self, commands: list[dict[str, Any]], style: str = DEFAULT_STYLE, **_: Any) -> ToolResult:
        usable, issues = validate_commands(commands, style=style)

        if not usable:
            detail = "\n".join(f"- {msg}" for msg in issues[:12])
            return ToolResult.fail(
                "绘图指令全部无效，没有画出任何内容。请修正后重新调用：\n" + detail
            )

        # 流式阶段前端已经边收边画；这里补发一次终态，保证非流式链路也能完整呈现。
        # 重复的笔迹由前端按 id 去重，不会画两遍。
        if self._progress_callback:
            self._progress_callback({
                "type": "paint_patch",
                "commands": usable,
                "is_final": True,
            })

        # 记下绘制时刻，放在补发之后：只有这次终态触发的回传才算"本次绘制后的画面"，
        # 否则可能把上一批指令回传的中间画面误认成当前结果。
        paint_canvas.note_draw()

        stroke_count = sum(1 for cmd in usable if cmd.get("op") == "stroke")
        layer_ids: list[str] = []
        for cmd in usable:
            if cmd.get("op") == "stroke":
                layer = str(cmd.get("layer"))
                if layer not in layer_ids:
                    layer_ids.append(layer)

        summary = f"已绘制 {stroke_count} 笔，涉及 {len(layer_ids)} 个图层（{'、'.join(layer_ids) or '无'}）"
        if issues:
            detail = "\n".join(f"- {msg}" for msg in issues[:8])
            summary += f"\n另有 {len(issues)} 条指令被跳过，原因：\n{detail}"

        return ToolResult.ok(
            summary,
            stroke_count=stroke_count,
            layers=layer_ids,
            skipped=len(issues),
        )


class CanvasReviewTool(BaseTool):
    """把当前画面交给模型自己审一遍，返回可执行的修正清单。"""

    name = "canvas_review"
    description = (
        "审查当前画布上的画面，返回问题清单。画完一轮后调用，用来发现自己画错的地方。\n"
        "分两部分：\n"
        "① 几何审计——由笔迹坐标精确计算，包括越界、重复描边、大轮廓未闭合，"
        "以及每个图层的实际范围与中心坐标。这些数字可直接采信。\n"
        "② 视觉评审——只看得到画的是什么、比例形态是否走样；不看位置对齐（已由几何审计量过）。\n"
        "如果返回「通过」，说明画面已经合格，不要再改。\n"
        f"同一轮任务最多审查 {MAX_REVIEWS} 次，达到上限后会要求停止迭代，避免无限自审。"
    )
    parameters = [
        ToolParameter(
            "focus",
            "string",
            "可选：这次重点想检查什么（例如「轮子和货厢的比例」）。不填则做整体检查。",
            required=False,
        ),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict | None = None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    def execute(self, focus: str = "", **_: Any) -> ToolResult:
        # 前端收到绘图指令后会回传完整画面，先等它到位再审查，
        # 否则可能读到上一次绘制留下的旧图，得出错误结论。
        paint_canvas.wait_for_fresh_snapshot()

        snapshot = paint_canvas.get_snapshot()
        if not snapshot or not snapshot.get("image"):
            return ToolResult.fail(
                "画布上还没有可审查的画面。请先调用 canvas_draw 画出内容，再调用 canvas_review。"
            )

        used = paint_canvas.reviews_used()
        if used >= MAX_REVIEWS:
            return ToolResult.ok(
                f"本轮已审查 {used} 次，达到上限。请停止自我修正，把当前的成品和剩余问题直接汇报给用户，"
                "由用户决定是否继续调整。"
            )
        index = paint_canvas.next_review_index()

        # 先做几何审计：这部分是算出来的事实，不受视觉模型误判影响
        audit_result = audit.audit(
            snapshot.get("stroke_audit"),
            layers=snapshot.get("layers") or [],
            width=int(snapshot.get("width") or 1600),
            height=int(snapshot.get("height") or 1000),
        )
        audit_text = audit.render(audit_result)

        image_b64, mime_type = _split_data_url(str(snapshot["image"]))
        if not image_b64:
            return ToolResult.fail("画面数据为空，无法审查。请重新调用 canvas_draw 后再试。")

        prompt = REVIEW_PROMPT
        extra = (focus or "").strip()
        if extra:
            prompt += f"\n本次重点看：{extra}"

        try:
            critique = describe_image_b64(
                image_b64,
                mime_type,
                prompt,
                self.llm_config,
                max_tokens=4096,
            )
        except Exception as e:
            # 视觉环节失败不影响几何结论，把可用的事实返回给模型
            return ToolResult.ok(
                f"{audit_text}\n\n视觉评审失败（{e}）。以上几何结论仍可采信，"
                "如需确认观感请稍后重试 canvas_review。",
                passed=not audit_result["issues"],
                review_index=index,
                geometry_issues=len(audit_result["issues"]),
                vision_failed=True,
            )

        critique = (critique or "").strip()
        if not critique:
            return ToolResult.ok(
                f"{audit_text}\n\n视觉评审没有返回内容（可能超时）。以上几何结论仍可采信。",
                passed=not audit_result["issues"],
                review_index=index,
                geometry_issues=len(audit_result["issues"]),
                vision_failed=True,
            )

        vision_passed = critique.replace("。", "").replace("！", "").strip() in ("通过", "合格")
        passed = vision_passed and not audit_result["issues"]

        if passed:
            return ToolResult.ok(
                f"{audit_text}\n\n【视觉评审】\n{critique}\n\n"
                f"审查通过（第 {index}/{MAX_REVIEWS} 次）：几何与观感都没有发现问题。"
                "不要再修改，直接把结果汇报给用户。",
                passed=True,
                review_index=index,
                geometry_issues=0,
            )

        remaining = MAX_REVIEWS - index
        if remaining > 0:
            tail = (
                "请只修正上面列出的确证问题，用 remove 删除对应笔迹后用 canvas_draw 重画。"
                "几何审计给出的数值可以直接采信；视觉评审只针对形态与比例，"
                "如果它与几何数据冲突，以几何数据为准。修完可以再调用一次 canvas_review。"
            )
        else:
            tail = "这已是最后一次审查，请把以上问题汇报给用户，由用户决定后续调整。"

        return ToolResult.ok(
            f"{audit_text}\n\n【视觉评审（第 {index}/{MAX_REVIEWS} 次）】\n{critique}\n\n{tail}",
            passed=False,
            review_index=index,
            remaining=remaining,
            geometry_issues=len(audit_result["issues"]),
        )


def _split_data_url(data: str) -> tuple[str, str]:
    """把 data:image/png;base64,xxx 拆成 (base64, mime)；也接受裸 base64。"""
    text = data.strip()
    if text.startswith("data:") and "," in text:
        header, _, payload = text.partition(",")
        mime = header[5:].split(";")[0] or "image/png"
        return payload, mime
    return text, "image/png"
