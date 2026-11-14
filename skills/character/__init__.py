"""角色定妆工具。

模型只填参数（体型系数、配色、发型、服装），几何由前端骨架展开。
工具把参数推到应用画布上，等用户在画布上确认后再落盘，
所以 lyric_mv / director 拿到的一定是用户看过的那一版。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import character_sheet as store
from skills.base import BaseTool, ToolParameter, ToolResult

# ── 参数契约 ──

HAIR_STYLES = ("bun", "short", "long", "baldTop")
OUTFITS = ("apron", "dress", "shirt")

# 键 → (默认值, 允许区间)。全部是相对总高的系数或 0~1 的强度，换体型只改数字。
PROPORTIONS: dict[str, tuple[float, float, float]] = {
    "headRatio": (0.24, 0.12, 0.48),
    "legRatio": (0.32, 0.16, 0.55),
    "shoulderRatio": (0.92, 0.45, 1.35),
    "hipRatio": (1.04, 0.45, 1.55),
    "belly": (0.5, 0.0, 1.0),
    "armRatio": (1.0, 0.6, 1.5),
}

COLORS: dict[str, str] = {
    "skin": "#f6d3b8",
    "skinShade": "#dfb096",
    "hair": "#4a3a33",
    "hairShade": "#2f2521",
    "cloth": "#8fa4bd",
    "clothShade": "#6d8299",
    "apron": "#f1e7d4",
    "apronShade": "#d5c4a8",
    "ink": "#4a4038",
}

# 缺省时必须从主色推导的暗部，而不是硬塞一个不相干的颜色
SHADE_SOURCE = {"skinShade": "skin", "hairShade": "hair", "clothShade": "cloth", "apronShade": "apron"}

DEFAULT_SPEC: dict[str, Any] = {
    "id": "character",
    "name": "角色",
    "proportions": {key: value[0] for key, value in PROPORTIONS.items()},
    "colors": dict(COLORS),
    "hair": "short",
    "outfit": "shirt",
    "glasses": False,
    "wrinkle": 0.0,
}

# 配角上限：再多也没有镜头能逐个交代清楚，只会让画面变成人堆
CAST_MAX = 6
ROLE_HERO = "hero"


def role_key(raw: Any, fallback: str = "friend") -> str:
    """角色 key：小写、只留字母数字与连字符，用来生成组件名与文件名。"""
    s = re.sub(r"[^0-9a-zA-Z_-]+", "-", str(raw or "").strip()).strip("-").lower()
    return s or fallback

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    m = _HEX.match(value.strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return f"#{digits.lower()}"


def _darken(hex_color: str, amount: float = 0.22) -> str:
    """把颜色压暗，用来从主色推导暗部。amount 越大越暗。"""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    k = max(0.0, min(1.0, 1 - amount))
    return f"#{int(r * k):02x}{int(g * k):02x}{int(b * k):02x}"


def _number(value: Any, default: float, low: float, high: float) -> tuple[float, str | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default, None
    clamped = max(low, min(high, float(value)))
    if abs(clamped - float(value)) > 1e-6:
        return clamped, f"取值 {value} 超出 {low}~{high}，已收敛到 {round(clamped, 3)}"
    return clamped, None


def normalize_spec(raw: Any) -> tuple[dict[str, Any], list[str]]:
    """把模型给的半成品参数收敛成完整契约。

    缺字段补默认值、超范围收敛、颜色非法回退，
    并把每一处修正都作为 issue 返回——模型下一轮就知道自己哪里写错了。
    """
    issues: list[str] = []
    spec = json.loads(json.dumps(DEFAULT_SPEC))  # 深拷贝
    if not isinstance(raw, dict):
        return spec, ["spec 必须是对象"]

    if isinstance(raw.get("name"), str) and raw["name"].strip():
        spec["name"] = raw["name"].strip()[:24]
        spec["id"] = re.sub(r"[^0-9a-zA-Z_-]+", "-", spec["name"]).strip("-").lower() or "character"

    props = raw.get("proportions")
    if isinstance(props, dict):
        for key, (default, low, high) in PROPORTIONS.items():
            value, warn = _number(props.get(key), default, low, high)
            spec["proportions"][key] = round(value, 3)
            if warn:
                issues.append(f"proportions.{key}：{warn}")

    colors = raw.get("colors")
    if isinstance(colors, dict):
        for key, default in COLORS.items():
            if key not in colors:
                continue
            parsed = _hex(colors.get(key))
            if parsed:
                spec["colors"][key] = parsed
            elif key in SHADE_SOURCE:
                continue  # 暗部交给下面统一推导
            else:
                issues.append(f"colors.{key} 不是合法颜色（要 #rrggbb），已用默认值")

    # 只给了主色的，暗部按主色压暗推导，保证同一角色配色自洽
    for shade_key, base_key in SHADE_SOURCE.items():
        if isinstance(colors, dict) and shade_key in colors:
            continue
        base = spec["colors"].get(base_key)
        if _hex(base or ""):
            spec["colors"][shade_key] = _darken(spec["colors"][base_key])

    hair = raw.get("hair")
    if hair in HAIR_STYLES:
        spec["hair"] = hair
    elif hair is not None:
        issues.append(f"hair 必须是 {' / '.join(HAIR_STYLES)} 之一，收到 {hair}，已用默认值")

    outfit = raw.get("outfit")
    if outfit in OUTFITS:
        spec["outfit"] = outfit
    elif outfit is not None:
        issues.append(f"outfit 必须是 {' / '.join(OUTFITS)} 之一，收到 {outfit}，已用默认值")

    if isinstance(raw.get("glasses"), bool):
        spec["glasses"] = raw["glasses"]

    wrinkle, warn = _number(raw.get("wrinkle"), spec["wrinkle"], 0.0, 1.0)
    spec["wrinkle"] = round(wrinkle, 2)
    if warn:
        issues.append(f"wrinkle：{warn}")

    return spec, issues


def _style(raw: Any) -> dict[str, Any]:
    name = "flat"
    if isinstance(raw, str) and raw in ("flat", "pixel"):
        name = raw
    elif isinstance(raw, dict) and raw.get("style") in ("flat", "pixel"):
        return {
            "style": raw["style"],
            "pixelSize": int(raw.get("pixelSize") or 4),
            "colorLevels": int(raw.get("colorLevels") or 6),
        }
    return {"style": name, "pixelSize": 4, "colorLevels": 6}


def character_dir(project: str) -> Path:
    """角色资产放在项目目录下，和成片产物同一处，续跑时能直接读到。"""
    name = (project or "").strip().strip("/\\") or "default"
    return Path("video_work") / name


def save_spec(spec: dict[str, Any], project: str) -> Path:
    target = character_dir(project) / "character.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def save_cast(characters: list[dict[str, Any]], project: str) -> Path:
    """把整组角色写进项目：characters.json 是唯一数据源，character.json 保留为主角。"""
    d = character_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    target = d / "characters.json"
    target.write_text(json.dumps({"characters": characters}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    hero = next((c["spec"] for c in characters if c.get("role") == ROLE_HERO), None)
    if hero is not None:
        (d / "character.json").write_text(
            json.dumps(hero, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def normalize_cast(raw: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """配角参数：每个都是完整的角色 spec，另带一个 role。

    角色 key 不能是 hero（主角用 spec 参数），并且不能重复。
    """
    issues: list[str] = []
    out: list[dict[str, Any]] = []
    if raw is None:
        return out, issues
    if not isinstance(raw, list):
        return out, ["cast 必须是数组"]
    if len(raw) > CAST_MAX:
        issues.append(f"cast 最多 {CAST_MAX} 个配角，超出部分已忽略")
    seen = {ROLE_HERO}
    for i, item in enumerate(raw[:CAST_MAX]):
        if not isinstance(item, dict):
            issues.append(f"cast[{i}] 必须是对象")
            continue
        spec_raw = item.get("spec") if isinstance(item.get("spec"), dict) else item
        spec, sub = normalize_spec(spec_raw)
        issues.extend(f"cast[{i}] {x}" for x in sub)
        role = role_key(item.get("role") or spec.get("name"), f"friend-{i + 1}")
        if role == ROLE_HERO:
            issues.append(f"cast[{i}] 不能用 hero（主角由 spec 定义）")
            continue
        if role in seen:
            issues.append(f"cast[{i}] 角色 {role} 重复")
            continue
        seen.add(role)
        out.append({"role": role, "spec": spec})
    return out, issues


def load_spec(project: str) -> dict[str, Any] | None:
    path = character_dir(project) / "character.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _spec_brief(spec: dict[str, Any]) -> str:
    p = spec["proportions"]
    return (
        f"{spec['name']}：头身比 {p['headRatio']}、腿长 {p['legRatio']}、"
        f"体宽 {p['belly']}；发型 {spec['hair']}、服装 {spec['outfit']}"
        + ("、戴眼镜" if spec["glasses"] else "")
        + f"；主色 皮肤 {spec['colors']['skin']} / 头发 {spec['colors']['hair']} / 衣服 {spec['colors']['cloth']}"
    )


class CharacterSheetTool(BaseTool):
    """定妆：把角色参数推到画布，等用户确认。"""

    name = "character_sheet"
    description = (
        "给一个角色（可带一组配角）做定妆，并推送到应用画布上等用户确认。**它会阻塞到用户点按钮为止**。\n"
        "主角用 spec；配角用 cast（每个配角一份 spec + 一个 role），整组会在同一张对照图里一次确认。\n"
        "角色是参数化骨架，不是图：你只填「长什么样」，几何由骨架展开，所以同一个参数在任何镜头、"
        "任何表情下都是同一个人，也能直接进动画。\n"
        "参数分四块：\n"
        "1. proportions（体型系数，都是相对总高的比例）：\n"
        "   headRatio 头高占比 0.24（越大越幼态，成年约 0.2，老人小孩 0.28~0.36）\n"
        "   legRatio 腿长占比 0.32　shoulderRatio 半肩宽/头宽 0.92　hipRatio 半髋宽/头宽 1.04\n"
        "   belly 躯干圆润度 0~1（0.2 瘦，0.7 微胖）　armRatio 手臂长/躯干长 1.0\n"
        "2. colors：skin / hair / cloth / apron / ink 给主色即可（#rrggbb），"
        "skinShade / hairShade / clothShade / apronShade 不填会按主色自动压暗。\n"
        "3. hair：bun（盘发）/ short（短发）/ long（长发）/ baldTop（谢顶只剩两鬓）\n"
        "4. outfit：apron（围裙）/ dress（连衣裙）/ shirt（衬衫）；glasses 布尔；wrinkle 0~1 皱纹强度。\n"
        "调用后画布会出五格对照图（正面/侧面/背面/坐姿伸手/倾斜惊讶），由用户确认或要求调整。\n"
        "返回里带 verdict：confirmed 表示用户认可，revise 表示用户提了修改要求（按 note 改参数后重新调用）。"
    )
    parameters = [
        ToolParameter(
            "spec",
            "object",
            "角色参数：{name, proportions:{headRatio,legRatio,shoulderRatio,hipRatio,belly,armRatio}, "
            "colors:{skin,hair,cloth,...}, hair, outfit, glasses, wrinkle}。只写你要改的字段，其余用默认值。",
            required=True,
        ),
        ToolParameter(
            "cast",
            "array",
            "配角数组：每项 {role, spec}。role 是角色 key（如 friend-a，不能用 hero），"
            "spec 与主角参数同构。整组会和主角一起在一张定妆网格里确认；最多 6 个。",
            required=False,
        ),
        ToolParameter("title", "string", "画布上显示的标题，例如「MV 主角 · 阿岚」", required=False),
        ToolParameter("note", "string", "这一版的说明：为什么这样定、相比上一版改了什么", required=False),
        ToolParameter(
            "project",
            "string",
            "项目名：确认后把整组角色存到 video_work/<project>/characters.json"
            "（主角同时保留 character.json），供后续镜头复用。",
            required=False,
        ),
        ToolParameter(
            "style",
            "string",
            "画布预览的渲染风格：flat（平涂，默认）/ pixel（像素）。只影响预览，几何不变。",
            required=False,
            enum=["flat", "pixel"],
            default="flat",
        ),
    ]

    def execute(
        self,
        spec: Any,
        title: str = "角色定妆",
        note: str = "",
        project: str = "",
        style: str = "flat",
        cast: Any = None,
        **_: Any,
    ) -> ToolResult:
        normalized, issues = normalize_spec(spec)
        extras, cast_issues = normalize_cast(cast)
        issues.extend(cast_issues)
        characters = [{"role": ROLE_HERO, "spec": normalized}] + extras
        style_opts = _style(style)

        token = store.publish(
            normalized,
            title=(title or "角色定妆").strip(),
            note=(note or "").strip(),
            style=style_opts,
            project=(project or "").strip(),
            characters=characters,
        )

        # 事件走 progress 通道：前端按 type 分流到定妆总线上
        if self._progress_callback:
            try:
                self._progress_callback({
                    "type": "character_preview",
                    "token": token,
                    "spec": normalized,
                    "characters": characters,
                    "title": (title or "角色定妆").strip(),
                    "note": (note or "").strip(),
                    "style": style_opts,
                })
            except Exception:
                pass

        timeout = float(os.environ.get("CHARACTER_CONFIRM_TIMEOUT", "900"))
        self._emit_progress("已推到画布，等你确认（确认或写下修改要求）")
        answer = store.wait_for_verdict(token, timeout=timeout)
        store.dismiss(token)

        saved = ""
        # 参数未定稿时不能覆盖项目里已确认的角色资产。
        if project and answer and answer.get("verdict") == store.VERDICT_CONFIRM:
            try:
                saved = str(save_cast(characters, project))
            except Exception as e:
                issues.append(f"角色文件写入失败：{e}")

        brief = _spec_brief(normalized)
        if extras:
            brief += "\n配角：" + "；".join(
                f"{c['role']}（{_spec_brief(c['spec'])}）" for c in extras)
        detail = ("\n参数修正：\n" + "\n".join(f"- {msg}" for msg in issues)) if issues else ""
        save_line = f"\n已保存：{saved}" if saved else ""

        if answer is None:
            return ToolResult.ok(
                f"定妆已推送到画布，但 {int(timeout)} 秒内没有收到用户确认。\n角色参数：{brief}{save_line}"
                f"{detail}\n可以先把这一版当作待定稿继续，但涉及人物的画面要以用户确认后的版本为准。",
                verdict="timeout",
                spec=normalized,
                token=token,
                issues=issues,
            )

        verdict = answer.get("verdict")
        user_note = answer.get("note") or ""
        if verdict == store.VERDICT_CONFIRM:
            return ToolResult.ok(
                f"用户已确认这一版定妆。\n角色参数：{brief}{save_line}{detail}\n"
                "后续镜头/画面都用这一组角色，不要把主角复制成配角，也不要另画没定妆的人。",
                verdict="confirmed",
                spec=normalized,
                token=token,
                note=user_note,
                saved=saved,
                issues=issues,
            )

        return ToolResult.ok(
            f"用户要求调整：{user_note or '（没有具体说明，按定妆图自行判断）'}\n"
            f"当前参数：{brief}{save_line}{detail}\n"
            "请按上面的意见修改 spec 后重新调用 character_sheet，不要跳过确认直接往下做。",
            verdict="revise",
            spec=normalized,
            token=token,
            note=user_note,
            saved=saved,
            issues=issues,
        )
