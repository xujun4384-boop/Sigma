# -*- coding: utf-8 -*-
"""product_director - 产品演示视频导演（独立于 director）

与 `director`（PPT/知识讲解叙事线）**明确分开**：这里只做"像真实产品录屏但不是录屏"的功能演示片。
流程：分镜蓝图 → **返回 need_confirm（由主 LLM 用 ask_user 与用户确认）** → 带 plan 二次调用 →
HTML+GSAP 逐段作画 → 渲染前闸门 → 渲染 → 拼接 → 铺音乐/旁白。

两条分流（由 audio_mode 决定）：
  bgm  纯音乐无旁白：**先分析音乐节奏**（BPM/小节/能量分段），切点对拍、文字承担叙事、运镜快但受可读性约束。
  vo   有旁白：旁白先行，镜头时长=实测句长，文字只留关键词，运镜慢且跟随语义停顿。

音乐节奏分析见 `scripts/rhythm.py`；两者的规则分别写在 `prompts/plan.md` 与 `prompts/compose.md`。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent
PROMPTS = SKILL_DIR / "prompts"
VENDOR_DIR = SKILL_DIR.parent / "opendesign" / "vendor"

MAX_PLAN_TRIES = 2         # 蓝图整份重写上限（只在原地修补救不回来时才用）
MAX_PLAN_REPAIRS = 3       # 蓝图不合规时先原地修补：只回要改的字段，不重跑整份
MAX_REPAIR_TRIES = 2       # 闸门失败先就地修补（只回 diff）；修补不动才整段重写一次
SEGMENT_MAX_SEC = 26.0
# 不设整条任务的总时长超时：这类长任务（尤其带 3D 段）本来就要跑十几分钟到几十分钟，
# 卡一个总预算只会在"快好了"的时候把活杀掉。真正的卡死由 LLM 停滞看门狗和用户取消兜底。
# 停滞超时：只在"连续这么久收不到任何数据"时才判失败。长思考的模型（如 K3.1 无法关闭思考）
# 思考期间可能长时间没有正文，这里给足余量，靠用户取消或下游看门狗兜底。
LLM_STALL_TIMEOUT = 600

_CAM_BGM = {"push-in", "pan", "whip", "tilt", "creep", "pull-back", "static"}
_CAM_VO = {"push-in", "pan", "creep", "static", "pull-back"}

# 产品演示片的配乐是"节奏骨架"：要清晰、稳定、可卡点的节拍重音，但**不限定乐器**——
# 鼓组、打击乐、合成脉冲、断奏弦乐/钢琴、贝斯律动、拨弦……任何能给出明确律动的声部都可以。
# 真正要排除的是"流行歌曲写法"（主歌副歌、旋律 hook、歌词/人声），而不是某种音色。
_MUSIC_PRESETS = {
    "trailer": (
        "电影预告片气质（cinematic / hybrid trailer），纯器乐，绝对无人声、无歌词、无吟唱采样。"
        "气质庄重、史诗、有压迫感和推进力，像科技发布会或产品大片的开场。"
        "节奏要清晰、稳定、可卡点：每拍有可感知的重音、小节首拍更明显；"
        "重音由哪些声部承担不限——打击乐、低频脉冲、断奏弦乐或铜管、合成重音、贝斯律动都可以，"
        "不需要是传统鼓组。"
        "结构：稀疏引入 → 4~8 小节内建立稳定律动 → 中段加层与 riser 抬升 → "
        "段落边界出现 impact / drop → 结尾保持律动不散。速度 100–126 BPM，4/4。"
        "不要：流行歌曲式主歌副歌、任何旋律性人声、歌曲化 hook、吉他扫弦、抒情钢琴、lo-fi、爵士、"
        "无节拍的环境铺底。"
    ),
    "industrial": (
        "工业电子 / tech-industrial 气质，纯器乐，无人声无歌词。"
        "强调机械感、精密与冲击力：金属质感敲击、门限噪声、硬质低音、工业氛围。"
        "律动由敲击、脉冲、失真贝斯或断奏合成器等任何声部承担都可以，不要求传统鼓组；"
        "速度 110–128 BPM，4/4，每拍清晰、小节首拍重音明确。"
        "不要流行歌曲结构、不要人声、不要旋律性 hook、不要轻音乐铺底。"
    ),
    "pulse": (
        "极简科技脉冲（minimal tech pulse）气质，纯器乐，无人声无歌词。"
        "以稳定脉冲推动节奏，少量合成器与质感点缀制造推进感；克制但有力量，适合高端产品演示。"
        "重音可以由合成脉冲、拨弦、贝斯或轻打击任一承担，不要求鼓组；"
        "速度 100–120 BPM，4/4，每拍清晰、小节首拍有重音。"
        "不要流行歌曲结构、不要人声、不要抒情旋律、不要 lo-fi 白噪。"
    ),
}
_DEFAULT_MUSIC_PROMPT = _MUSIC_PRESETS["trailer"]

# vo 分流的垫乐约束：旁白是主角，音乐只负责托住情绪，不能抢话。
# 这是"用途"层的约束，和上面选哪种气质无关，所以单独拼在预设后面。
_VO_BED_PROMPT = (
    "用途：作为中文旁白下方的垫乐（under-voice bed）。存在感要低：音量克制、"
    "频段避开人声的中频，少用密集高频敲击与大幅段落转折；律动可以有，但绝不能压住说话。"
    "整段平稳推进、首尾都能自然衔接；绝对不要人声、念白、合唱或任何语言类采样。"
)
# 垫乐基准音量（旁白 1.0 的前提下）；闪避会在此基础上再压 ~15dB
_VO_BED_GAIN = 0.20

# 用户没说时长时不套固定默认值：让模型按"要讲几个动作 + 每个动作要多久"自己定。
_DURATION_PROMPT = (
    "你在为一条产品演示片定时长。只输出 JSON：{\"duration_s\": 整数, \"reason\": \"一句话依据\"}\n"
    "判断依据：这次要演示几个功能动作、每个动作需要多少秒让观众看清（界面动作完成 + 文字读完）、"
    "开场与落版各需要多少；纯音乐片单镜 2–4 秒，一行字读完约 0.9+0.1×字数 秒；有旁白按句子字数累加。"
    "宁可删减动作，也不要用无意义停留凑时长。范围 10–90 秒整数。只输出 JSON。"
)

# 蓝图不合规时不重跑整份，只让模型回"要改哪几个字段"（反灌问题原地改）。
_PLAN_REPAIR_PROMPT = (
    "你是一位产品演示片导演，正在修订一份已经写好的分镜蓝图。下面给出当前蓝图 JSON 和校验报错。\n"
    "只修报错涉及的地方，**不要重写整份蓝图、不要改没被点名的镜头**。\n"
    "输出 JSON：{\"edits\": [{\"path\": \"字段路径\", \"value\": 新值}]}\n"
    "path 规则：根字段直接写名字（title / duration），嵌套用点号（style.tone），"
    "数组用下标（shots[2].title、shots[2].end）。\n"
    "修改原则：\n"
    "- 文字放不下就**砍字**（缩短 title/sub/kicker），不要为了塞字去改时间轴；\n"
    "- 切点不在小节线上就改 start/end 到给定网格值，并同步相邻镜头避免重叠或缝隙；\n"
    "- 标题压住主展示区就换 title_zone 或改 focus_panel，两者不能同侧；\n"
    "- 缺 ui_surface 就补上这块界面的标识（同一界面全片同名）；\n"
    "- stage3d 镜头必须是 ui 拍、连续排布、不超过全片一半且连拍不超过 3 个；"
    "laptop 的 3D 拍标题只能放 top/bottom；连续的 3D 镜头必须换机位"
    "（azimuth 差 ≥18° 或 elevation 差 ≥10°）；\n"
    "- 画布之外/越界就把该镜内容收进安全边距内。\n"
    "只输出 JSON，不要解释。"
)

# 多段片子的一致性靠「视觉圣经」：每种界面各自一份，从它第一次定稿的 HTML 提炼，
# 后面再出现同一界面时照着它画；不同界面之间绝不互相复用。
_BIBLE_PROMPT = (
    "你在为一条产品演示片做跨段一致性。下面是一段已经通过审查的 HyperFrames HTML（已去掉时间线脚本）。\n"
    "请把其中【本次只提炼这一块界面】点名的那块界面的视觉契约提炼成 JSON，供这块界面以后再次出现时照着重建；"
    "同一段画面里的其他界面、纯文字拍一律忽略，不要混进来。\n"
    "只写这份 HTML 里真实存在的值；看不清、没出现、或本来就是纯文字拍，就留空字符串，不要补全、不要发明。\n"
    "typography 只记**应用界面内部**的字号层级（正文、标签、按钮）；屏幕上的大标题/副标属于标题层，"
    "不写进 typography（标题字号每镜按 compose.md 的下限重新定，不要沿用界面小字号）。\n"
    "画布固定 1920×1080，几何优先写 HTML 实际使用的像素值；只有用百分比/弹性布局写的，才换算成占比并标 ≈。\n"
    "输出结构：\n"
    "{\n"
    '  "canvas": {"bg": "", "vignette_or_gradient": "", "safe_margin_px": ""},\n'
    '  "window": {"rect_px": "left/top/width/height", "width_pct": "", "radius": "", "border": "",'
    ' "shadow": "", "titlebar_h": "", "traffic_lights": ""},\n'
    '  "panels": [{"name": "", "width_px": "", "width_pct": "", "bg": "", "divider": "", "padding": ""}],\n'
    '  "typography": {"family": "", "h1": "", "h2": "", "body": "", "meta": "", "weight": ""},\n'
    '  "palette": {"accent": "", "text": "", "text_dim": "", "surface": "", "line": ""},\n'
    '  "controls": {"radius": "", "button": "", "tab": "", "icon_style": "", "input": ""},\n'
    '  "title_treatment": {"kicker": "", "title": "", "rule": "", "placement": ""},\n'
    '  "motion": {"easing": "", "camera": "", "text_in": ""},\n'
    '  "reuse": ["可直接复用的结构或样式要点"]\n'
    "}\n"
    "只输出 JSON，不要解释。"
)


def _log(msg: str) -> None:
    print(f"[product_director] {msg}", flush=True)


def _auto_output_path(output_path: str, project: str, cwd: str) -> Path:
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work = base / "video_work"
    if project:
        work = work / project
    return work / p


def _json_of(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        doc = json.loads(text)
        return doc if isinstance(doc, dict) else {}
    except Exception:
        i, j = text.find("{"), text.rfind("}")
        if i >= 0 and j > i:
            try:
                doc = json.loads(text[i:j + 1])
                return doc if isinstance(doc, dict) else {}
            except Exception:
                pass
    return {}


def _prompt_text(name: str) -> str:
    try:
        return (PROMPTS / name).read_text(encoding="utf-8")
    except OSError:
        return ""


# ───────────────────────────── 断点续跑 ─────────────────────────────
STATE_NAME = "product-state.json"


def _load_state(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _file_ok(p) -> bool:
    try:
        return bool(p) and Path(str(p)).exists() and Path(str(p)).stat().st_size > 0
    except Exception:
        return False


def _fingerprint(**kw) -> str:
    """把"决定这次要做什么"的输入压成指纹：输入没变才允许续跑旧进度。"""
    blob = json.dumps(kw, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _segment_key(seg: dict, width: int, height: int, fps: int, mode: str) -> str:
    """这一段"要画什么"的指纹：镜头内容/时间 + 渲染参数 + 作画提示词版本。

    带上提示词版本，改了 compose.md 之后旧片段会自动重画，不会继续复用按旧规则渲的画面。
    """
    prompt_ver = hashlib.md5(_prompt_text("compose.md").encode("utf-8")).hexdigest()[:8]
    if _segment_is_3d(seg):
        prompt_ver = _s3d_version()
    return _fingerprint(mode=mode, width=width, height=height, fps=fps, prompt=prompt_ver,
                        start=round(float(seg.get("start") or 0.0), 3),
                        end=round(float(seg.get("end") or 0.0), 3),
                        shots=seg.get("shots") or [])


def _resume_output_path(project: str, cwd: str) -> str:
    """续跑没传 output_path：从项目工作区找回上次的成片名（工作目录以成片名命名）。"""
    if not project:
        return ""
    base = (Path(cwd) if cwd else Path(os.getcwd())) / "video_work" / project
    found: list[tuple[float, str]] = []
    for d in base.glob("*_product"):
        marks = [p.stat().st_mtime for p in (d / STATE_NAME, d / "product-plan.json")
                 if p.is_file()]
        if marks:
            found.append((max(marks), d.name[:-len("_product")]))
    if not found:
        return ""
    return f"{max(found)[1]}.mp4"


def _stored_mode(state: dict) -> str:
    """旧工程没存 inputs 时，从已落盘的蓝图反推分流，避免续跑回落到默认 bgm。"""
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else {}
    mode = str(plan.get("audio_mode") or "").lower()
    if mode in {"vo", "bgm"}:
        return mode
    shots = plan.get("shots") or []
    if shots and all(str(s.get("narration") or "").strip() for s in shots):
        return "vo"
    return ""


def _ui_ctx_from_disk(work: Path, meta: dict) -> dict:
    """从 ui/ 目录重建 UI 上下文，避免续跑时重跑提取器（含读图调用）。"""
    ui_dir = work / "ui"
    digest = ""
    tokens = ""
    try:
        f = ui_dir / "ui-digest.md"
        if f.exists():
            digest = f.read_text(encoding="utf-8")
        t = ui_dir / "ui-tokens.css"
        if t.exists():
            tokens = t.read_text(encoding="utf-8")
    except OSError:
        pass
    assets_dir = ui_dir / "assets"
    assets = []
    if assets_dir.is_dir():
        assets = sorted(p.name for p in assets_dir.iterdir() if p.is_file())
    return {"digest": digest, "tokens_css": tokens,
            "assets_dir": str(assets_dir) if assets else "", "assets": assets,
            "files": int(meta.get("files") or 0), "tokens": int(meta.get("tokens") or 0),
            "components": int(meta.get("components") or 0), "skeleton": [],
            "mode": str(meta.get("mode") or "code")}


def _chars(s) -> int:
    return len(re.sub(r"\s", "", str(s or "")))


class ProductDirectorTool(BaseTool):
    name = "product_director"
    description = (
        "产品演示视频导演（与 director 完全分开）：把产品和功能讲成 16:9 演示片。"
        "画面用 HTML+GSAP 重建真实产品界面（像录屏但不是录屏），支持两条分流："
        "bgm=纯音乐（先分析音乐节奏，切点对拍、文字承担叙事、运镜快）；"
        "vo=有旁白（旁白先行、镜头跟句长、文字少、运镜慢）。"
        "首次调用只设计分镜蓝图并返回 need_confirm（请用 ask_user 让用户确认）；"
        "确认后带 plan 再调一次才开始制作。"
    )
    parameters = [
        ToolParameter("brief", "string", "产品与要演示的功能：做什么、给谁、这次要讲哪几个动作"
                                          "（二次执行/断点续跑时不要传：沿用项目已落盘的需求）",
                      required=False),
        ToolParameter("plan", "string", "已确认的分镜蓝图 JSON。首次调用返回 need_confirm 后，"
                                        "用户确认了就把蓝图原样传回来直接开工（跳过设计）；"
                                        "用户要改就把改好的蓝图传回来。"
                                        "**断点续跑（中断后继续）不要传 plan**：只带 project/output_path "
                                        "再调一次，工具会沿用已定稿蓝图继续", required=False),
        ToolParameter("output_path", "string", "输出 mp4 路径；相对路径放 video_work/<project>/ 下。"
                                                "二次执行（带 plan）时请传同一个路径，否则会落到另一个工作目录"),
        ToolParameter("project", "string", "项目名（决定 video_work 子目录），可空", required=False),
        ToolParameter("duration_s", "integer", "内容时长参考上限（秒）。用户没说就别传：工具会按要演示的内容体量自己定。"
                                                "它是规模参考而不是配额——成片长度由蓝图内容决定（讲完就收尾），"
                                                "配乐会被裁到与成片同样长；主动传这个值代表用户希望大致做到这么长",
                      required=False),
        ToolParameter("audio_mode", "string", "分流：bgm=纯音乐无旁白；vo=有旁白",
                      required=False, enum=["bgm", "vo"], default="bgm"),
        ToolParameter("music_path", "string", "bgm 分流的现成音乐（mp3/wav）；不给则用 music_prompt 生成",
                      required=False),
        ToolParameter("music_prompt", "string", "完全自定义配乐描述；给定时覆盖 music_style 预设",
                      required=False),
        ToolParameter("music_style", "string", "默认配乐风格预设：trailer=电影预告片气质（默认）/ "
                                                "industrial=工业电子 / pulse=极简科技脉冲。"
                                                "三者都只要求「节奏清晰可卡点」，不限定乐器（不必是鼓）",
                      required=False, enum=["trailer", "industrial", "pulse"], default="trailer"),
        ToolParameter("bgm_under_vo", "boolean", "vo 分流时是否给旁白垫一层低音量背景音乐"
                                                  "（按人声自动闪避/ducking）。默认 true；"
                                                  "关掉就是纯旁白", required=False, default=True),
        ToolParameter("style_prompt", "string", "视觉风格（配色/字体/动效基调）；留空由导演自己定", required=False),
        ToolParameter("product_name", "string", "产品名（出现在界面标题栏/落版）", required=False),
        ToolParameter("ui_note", "string", "界面要求：有哪些面板/配色/必须出现的元素；可空", required=False),
        ToolParameter("ui_source", "string", "真实 UI 来源：前端工程目录/文件/截图，多个用换行或分号分隔；"
                                              "给了就按真实 token 与布局还原，而不是让模型编界面", required=False),
        ToolParameter("ui_mode", "string", "UI 提取方式：code=读前端源码（默认）/ shots=只有截图（先用读图链路"
                                           "转写成界面规格，再由模型重建）/ hybrid=两者都有",
                      required=False, enum=["code", "shots", "hybrid"], default="code"),
        ToolParameter("width", "integer", "画布宽，默认 1920", required=False, default=1920),
        ToolParameter("height", "integer", "画布高，默认 1080", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
        ToolParameter("force", "boolean", "抛弃断点、从头重做（默认 false：同参再次调用会续跑已完成的部分）",
                      required=False, default=False),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict | None = None, skill_manager=None):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.skill_manager = skill_manager

    # ───────────────────────────── 入口 ─────────────────────────────
    def execute(self, brief: str = None, output_path: str = None, project: str = None,
                duration_s: int = None, audio_mode: str = None,
                music_path: str = None, music_prompt: str = None,
                music_style: str = None, bgm_under_vo: bool = None,
                style_prompt: str = None, product_name: str = None,
                ui_note: str = None, ui_source: str = None, ui_mode: str = None,
                width: int = None, height: int = None,
                fps: int = None, force: bool = False, plan=None, **kwargs) -> ToolResult:
        cfg = self.llm_config or {}
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            return ToolResult.fail("未配置主 LLM，product_director 需要现场写分镜与画面")

        # 二次执行：用户已经确认过蓝图，直接按它开工，不再设计
        confirmed_plan: dict = {}
        if plan:
            doc = _json_of(plan) if isinstance(plan, str) else (plan if isinstance(plan, dict) else {})
            if isinstance(doc, dict) and doc.get("shots"):
                confirmed_plan = doc
            else:
                return ToolResult.fail("plan 解析失败：需要含 shots 的分镜蓝图 JSON")

        if not output_path and not force:
            # 续跑没重复传 output_path：找回这个项目上次的工作目录，避免落到新目录从零重跑
            output_path = _resume_output_path(project, self.cwd)
        if not output_path:
            output_path = f"{project or 'product_demo'}.mp4"
        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)
        work = out.parent / f"{out.stem}_product"
        work.mkdir(parents=True, exist_ok=True)

        # 续跑参数继承：调用方往往只重复 project/output_path，其余参数省略。
        # 「省略」不等于「改成默认值」——项目级设定以首次调用落盘值为准，
        # 否则 audio_mode 会回落成 bgm，把按 vo 做的已确认蓝图判成不合规，逼模型重写整份分镜。
        state_path = work / STATE_NAME
        saved = {} if force else _load_state(state_path)
        inherited = {} if force else (saved.get("inputs") or {})
        if not force:
            brief = brief if brief is not None else inherited.get("brief")
            audio_mode = audio_mode or inherited.get("audio_mode") or _stored_mode(saved)
            duration_s = duration_s if duration_s is not None else inherited.get("duration_s")
            music_path = music_path if music_path is not None else inherited.get("music_path")
            music_prompt = (music_prompt if music_prompt is not None
                            else inherited.get("music_prompt"))
            music_style = music_style or inherited.get("music_style")
            bgm_under_vo = (bgm_under_vo if bgm_under_vo is not None
                            else inherited.get("bgm_under_vo"))
            style_prompt = style_prompt if style_prompt is not None else inherited.get("style_prompt")
            product_name = product_name if product_name is not None else inherited.get("product_name")
            ui_note = ui_note if ui_note is not None else inherited.get("ui_note")
            ui_source = ui_source if ui_source is not None else inherited.get("ui_source")
            ui_mode = ui_mode or inherited.get("ui_mode")
            width = width or inherited.get("width")
            height = height or inherited.get("height")
            fps = fps or inherited.get("fps")
        audio_mode = audio_mode or "bgm"
        music_style = music_style or "trailer"
        bgm_under_vo = True if bgm_under_vo is None else bool(bgm_under_vo)
        product_name = product_name or ""
        ui_note = ui_note or ""
        ui_mode = ui_mode or "code"
        width, height, fps = int(width or 1920), int(height or 1080), int(fps or 30)
        mode = "vo" if str(audio_mode).lower() == "vo" else "bgm"

        # 断点续跑：全量指纹一致 → 分镜/音乐/UI 全部复用；指纹变了 → 分镜重排，
        # 但已渲染的分段按「这一段要画什么」的内容指纹逐段判断能否复用（分段是最贵的一步）。
        fp = _fingerprint(brief=brief, duration_s=duration_s, audio_mode=mode,
                          music_path=music_path, music_prompt=music_prompt,
                          music_style=music_style, style_prompt=style_prompt,
                          bgm_under_vo=bgm_under_vo,
                          product_name=product_name, ui_note=ui_note,
                          ui_source=ui_source, ui_mode=ui_mode,
                          width=width, height=height, fps=fps)
        # 旧版 state 没记 inputs：它的指纹是用旧默认值算的，不能拿来否定这次继承出来的参数
        resumable = bool(saved) and (saved.get("fingerprint") == fp
                                     or not saved.get("inputs"))
        saved_ui = (saved.get("ui") or {}) if saved else {}
        if saved and not resumable:
            # 输入变了只意味着「分镜可能要重排」，不代表已渲好的画面作废：
            # 保留旧分段记录，后面按镜头内容指纹逐段比对（对不上自然重渲）。
            self._emit_progress("⓪ 输入与上次不同：分镜重排，已渲染分段按镜头内容判断复用")
            state = {"segments": saved.get("segments") or {},
                     "bibles": saved.get("bibles") or {},
                     "ui": saved_ui}
            if saved.get("confirmed"):
                # 旧蓝图是用户确认过的：只重排不重问，别让续跑又弹一次确认
                state["confirmed"] = True
        else:
            state = saved
        saved_ui = state.get("ui") or saved_ui
        done = [k for k, v in (state.get("segments") or {}).items() if _file_ok(v.get("path"))]
        if resumable:
            self._emit_progress(
                f"⓪ 断点续跑：蓝图{'已就绪' if state.get('plan') else '需重排'}，"
                f"音乐{'已就绪' if state.get('music') else '需重做'}，已完成 {len(done)} 段画面")
        elif done:
            self._emit_progress(f"⓪ 断点续跑：沿用已完成的 {len(done)} 段画面（按镜头内容比对）")
        state["fingerprint"] = fp
        state.setdefault("segments", {})
        # 记住这次真正生效的项目级参数：下次续跑没传的参数一律沿用，而不是回落默认值
        state["inputs"] = {
            "brief": brief, "duration_s": duration_s, "audio_mode": mode,
            "music_path": music_path, "music_prompt": music_prompt,
            "music_style": music_style, "bgm_under_vo": bgm_under_vo,
            "style_prompt": style_prompt, "product_name": product_name,
            "ui_note": ui_note, "ui_source": ui_source, "ui_mode": ui_mode,
            "width": width, "height": height, "fps": fps,
        }
        _save_state(state_path, state)

        # 兼容旧工程：没有 state 但磁盘上已有落盘的蓝图/音乐 → 当作续跑起点，不必重排分镜
        legacy_plan: dict = {}
        legacy_music = False
        if not resumable and not force:
            pj = work / "product-plan.json"
            if pj.exists():
                try:
                    doc = json.loads(pj.read_text(encoding="utf-8"))
                    if isinstance(doc, dict) and doc.get("shots"):
                        legacy_music = _file_ok(work / "audio" / "bgm.mp3")
                        # 落盘蓝图始终读出来：传入 plan 时要拿它做一致性比对，不能因为传了 plan 就当项目没蓝图
                        legacy_plan = doc
                        if not confirmed_plan:
                            self._emit_progress("⓪ 发现上次落盘的分镜蓝图：沿用（要重排请传 force=true）")
                except Exception:
                    legacy_plan = {}

        # ① UI 真值：先把真实前端的 token / 布局 / 资源抽出来，后面作画照抄
        ui_ctx: dict = {}
        if ui_source:
            # UI 提取只跟 ui_source / ui_mode 有关：这两个没变就直接复用已落盘的结果，
            # 不因为 brief 换个说法就重跑一遍读图/源码抽取。
            ui_fp = _fingerprint(ui_source=ui_source, ui_mode=ui_mode)
            cached_ui = saved_ui if (resumable or (saved_ui or {}).get("fp") == ui_fp) else None
            if cached_ui:
                ui_ctx = _ui_ctx_from_disk(work, cached_ui)
                if ui_ctx.get("digest") or ui_ctx.get("tokens_css"):
                    if state.get("ui") != {**cached_ui, "fp": ui_fp}:
                        state["ui"] = {**cached_ui, "fp": ui_fp}
                        _save_state(state_path, state)
            if not (ui_ctx.get("digest") or ui_ctx.get("tokens_css")):
                ui_ctx = self._build_ui_context(ui_source, work, ui_mode)
                if isinstance(ui_ctx, ToolResult):
                    return ui_ctx
                state["ui"] = {"mode": ui_ctx.get("mode"), "files": ui_ctx.get("files"),
                               "tokens": ui_ctx.get("tokens"),
                               "components": ui_ctx.get("components"), "fp": ui_fp}
                _save_state(state_path, state)
                tag = "截图转写" if ui_ctx.get("mode") == "shots" else "源码抽取"
                self._emit_progress(
                    f"⓪ UI 提取（{tag}）：{ui_ctx['files']} 文件 / {ui_ctx['tokens']} 个变量 / "
                    f"{len(ui_ctx.get('assets') or [])} 个资源")
            else:
                self._emit_progress("⓪ UI 提取：复用上次结果")
        elif saved_ui:
            # 续跑没重复传 ui_source：磁盘上的 UI 规格就是上次抽出来的真值，直接沿用
            ui_ctx = _ui_ctx_from_disk(work, saved_ui)
            if ui_ctx.get("digest") or ui_ctx.get("tokens_css"):
                self._emit_progress("⓪ UI 提取：复用上次结果")
            else:
                ui_ctx = {}

        # ① 内容体量参考：只作蓝图的"上限参考"，最终成片长度由蓝图实际需要决定。
        # （音乐是可裁剪的素材，内容不能注水：宁可成片短一点，也不要把同一个内容重复两遍凑时长）
        content_ref = float(duration_s or 0)
        known_plan = confirmed_plan if confirmed_plan.get("shots") else (
            state.get("plan") if isinstance(state.get("plan"), dict) else legacy_plan)
        if not content_ref and isinstance(known_plan, dict) and known_plan.get("shots"):
            # 续跑时蓝图已在盘上：直接按它算片长，不再重新问 LLM 定体量
            content_ref = round(float(known_plan["shots"][-1]["end"]), 3)
            self._emit_progress(f"① 内容体量：按已定稿蓝图 {content_ref:.0f}s")
        if not content_ref:
            if state.get("content_hint"):
                content_ref = float(state["content_hint"])
                self._emit_progress(f"① 内容体量参考：沿用上次 {content_ref:.0f}s")
            else:
                content_ref = float(self._decide_duration(brief or "", product_name, mode))
                state["content_hint"] = int(content_ref)
                _save_state(state_path, state)
                self._emit_progress(f"① 内容体量参考：约 {content_ref:.0f}s（最终以蓝图实际需要为准）")
        duration = content_ref or 15.0

        # ② 声音先行：bgm 先分析整曲节奏（不截取，等蓝图定稿后再按内容长度裁）
        audio_ctx: dict = {"mode": mode}
        if mode == "bgm":
            cached_music = state.get("music") if resumable else ""
            cached_rhythm = state.get("rhythm") if resumable else None
            if cached_music and _file_ok(cached_music) and cached_rhythm:
                music = Path(cached_music)
                rhythm = cached_rhythm
                audio_ctx.update({"music": str(music), "rhythm": rhythm, "music_cut": True})
                self._emit_progress(f"① 音乐：复用上次（BPM={rhythm.get('bpm')}）")
            else:
                music_fp = _fingerprint(music_path=music_path, music_prompt=music_prompt,
                                        music_style=music_style)
                # 配乐参数没变就复用已生成的文件（换风格/换 prompt 才重生成），避免无谓的几分钟
                reuse_music = (state.get("music_fp") in (None, music_fp)
                               and _file_ok(work / "audio" / "bgm.mp3"))
                music = self._ensure_music(music_path, music_prompt, work, project,
                                           content_ref or 45, product_name, music_style,
                                           reuse=reuse_music or legacy_music)
                if isinstance(music, ToolResult):
                    return music
                state["music_fp"] = music_fp
                _save_state(state_path, state)
                # 先分析整曲：蓝图在完整拍点上自由取用，用多少由内容决定
                rhythm = self._analyze_rhythm(music, work, None)
                audio_ctx.update({"music": str(music) if music else "", "rhythm": rhythm})
                self._emit_progress(f"① 音乐节奏：BPM={rhythm.get('bpm')}，"
                                    f"{len(rhythm.get('bars') or [])} 小节，"
                                    f"全曲 {float(rhythm.get('audio_duration') or 0):.1f}s（待按内容截取）")
        elif bgm_under_vo:
            # vo 分流：旁白是主角，音乐只做垫底（成片时按人声自动闪避）。
            # 这里不做节奏分析——vo 的切点跟句子走，不跟拍子走。
            cached_music = state.get("music") if resumable else ""
            if cached_music and _file_ok(cached_music):
                audio_ctx["music"] = cached_music
                self._emit_progress("① 旁白垫乐：复用上次的音乐")
            else:
                music_fp = _fingerprint(music_path=music_path, music_prompt=music_prompt,
                                        music_style=music_style, bed=True)
                reuse_music = (state.get("music_fp") in (None, music_fp)
                               and _file_ok(work / "audio" / "bgm.mp3"))
                music = self._ensure_music(
                    music_path, music_prompt, work, project, content_ref or 45,
                    product_name, music_style, reuse=reuse_music or legacy_music,
                    extra=_VO_BED_PROMPT)
                if isinstance(music, ToolResult):
                    # 垫乐失败不该拦住出片：降级为纯旁白
                    self._emit_progress(f"① 旁白垫乐不可用，改为纯旁白：{music.content[:80]}")
                else:
                    audio_ctx["music"] = str(music)
                    state["music"] = str(music)
                    state["music_fp"] = music_fp
                    _save_state(state_path, state)
                    self._emit_progress("① 旁白垫乐：已就绪（成片按人声自动闪避）")

        # ③ 分镜蓝图（vo 分支：先出句子，再按实测时长回填时间）
        t_plan = time.monotonic()
        plan_is_new = False
        stored_plan: dict = {}
        for cand in (state.get("plan"), legacy_plan):
            if isinstance(cand, dict) and cand.get("shots"):
                stored_plan = cand
                break
        # 这条任务已经开工（用户确认过，或已有渲好的分段）：已定稿蓝图是唯一真值，
        # 不再拿它去重新过审——重校验失败会逼主 LLM 重写整份分镜，等于把已跑过的全部推翻。
        disk_segments = any(_file_ok(p) for p in (work / "segments").glob("seg_*.mp4"))
        started = bool(state.get("confirmed")) or bool(done) or disk_segments
        if confirmed_plan:
            plan = confirmed_plan
            if stored_plan and _plan_sig(stored_plan) == _plan_sig(confirmed_plan):
                # 续跑时主 LLM 会把蓝图原样回传：内容一致就直接用落盘版，跳过校验
                plan = stored_plan
                self._emit_progress(
                    f"② 分镜蓝图：沿用已定稿蓝图（未重新校验，{len(plan.get('shots') or [])} 镜）")
            elif stored_plan and started:
                # 制作已开始：传入版与落盘版不同，多半是 LLM 复述时的轻微漂移。
                # 结构坏了就用落盘版；结构完好就按传入版（用户可能改了某几镜），且只做结构校验。
                errs = _plan_structure_errors(confirmed_plan)
                if errs:
                    plan = stored_plan
                    self._emit_progress("② 分镜蓝图：传入版结构不完整，改用已定稿蓝图续跑")
                else:
                    self._emit_progress(
                        f"② 分镜蓝图：沿用传入蓝图（制作已开始，跳过成片级校验，"
                        f"{len(plan.get('shots') or [])} 镜）")
            else:
                # 首次执行（还没开过工）：用户可能改过时间轴/镜头，必须确认版自带合规时间轴
                plan.setdefault("title", product_name or "产品演示")
                _end = round(float(plan["shots"][-1]["end"]), 3) if plan.get("shots") else 0.0
                errs = _validate_plan(plan, _end, mode, audio_ctx.get("rhythm") or {})
                if errs:
                    return ToolResult.fail(
                        "已确认的蓝图未通过校验：" + "；".join(errs[:4])
                        + f"\n蓝图文件：{work / 'product-plan.json'}")
                self._emit_progress(
                    f"② 分镜蓝图：使用已确认的蓝图（{len(plan.get('shots') or [])} 镜）")
            state["plan"] = plan
            state["confirmed"] = True
            _save_state(state_path, state)
        elif stored_plan:
            plan = stored_plan
            self._emit_progress(f"② 分镜蓝图：沿用落盘结果（{len(plan.get('shots') or [])} 镜）")
            state["plan"] = plan
            if (done or disk_segments) and not state.get("confirmed"):
                # 磁盘上已有渲好的分段 → 这份蓝图必然已过用户确认，别再弹一次确认
                state["confirmed"] = True
            _save_state(state_path, state)
        else:
            if not (brief or "").strip():
                return ToolResult.fail(
                    "缺少 brief：请先传 brief 让工具设计分镜蓝图；"
                    "若蓝图已确认，请带 plan 直接执行。")
            plan, errs = self._make_plan(brief, duration, mode, audio_ctx, style_prompt,
                                         product_name, ui_note, ui_ctx)
            if plan is None:
                return ToolResult.fail("分镜蓝图未通过校验：" + "；".join(errs[:4]))
            plan_is_new = True
            state["plan"] = plan
            state.pop("confirmed", None)
            _save_state(state_path, state)
            self._emit_progress(f"② 分镜蓝图 {time.monotonic() - t_plan:.0f}s"
                                f"（{len(plan.get('shots') or [])} 镜）")

        # 蓝图没被用户确认过就不开工（与 director 一致）：返回 need_confirm，
        # 由主 LLM 用 ask_user 确认后再带 plan 调一次。已确认/已续跑的蓝图不再打断。
        if plan_is_new or not state.get("confirmed"):
            return self._plan_confirm_result(plan, work, mode)

        narration_audio: list[dict] = []
        if mode == "vo":
            narration_audio, plan, err = self._prepare_voice(
                plan, work, project, saved=state.get("narration"))
            if err:
                return ToolResult.fail(err)
            duration = round(float(plan["shots"][-1]["end"]), 3)
            audio_ctx["narration"] = narration_audio
            self._emit_progress(f"② 旁白：{len(narration_audio)} 句，共 {duration:.1f}s")
            state["plan"] = plan
            state["duration"] = duration
            state["narration"] = narration_audio
            _save_state(state_path, state)

        # 成片长度由蓝图内容决定（音乐是素材，不是配额）：最后一镜结束就是成片长度
        plan_end = (round(float(plan["shots"][-1]["end"]), 3)
                    if plan.get("shots") else float(duration or 15))
        duration = plan_end
        if mode == "bgm" and audio_ctx.get("music") and not audio_ctx.get("music_cut"):
            cut, cut_rhythm = self._select_music_window(
                Path(audio_ctx["music"]), audio_ctx["rhythm"], duration, work)
            audio_ctx.update({"music": str(cut) if cut else audio_ctx["music"],
                              "rhythm": cut_rhythm})
            state["music"] = audio_ctx["music"]
            state["rhythm"] = cut_rhythm
        state["duration"] = duration
        _save_state(state_path, state)

        plan["duration"] = round(duration, 3)
        plan["audio_mode"] = mode
        (work / "product-plan.json").write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

        # ③ 分段作画 → 闸门 → 渲染
        segments = _split_segments(plan, SEGMENT_MAX_SEC)
        n_3d_seg = sum(1 for s in segments if _segment_is_3d(s))
        if n_3d_seg:
            self._emit_progress(f"③ 分段：{len(segments)} 段（其中 {n_3d_seg} 段 3D）")
        rendered: list[Path] = []
        # 界面标识 -> 视觉圣经；不同类型互不复用（续跑时从状态恢复）
        bibles: dict[str, dict] = dict(state.get("bibles") or {})
        reused_count = 0
        # 已渲片段按「内容指纹」索引，而不是按序号：蓝图重排（多一镜/少一镜/换顺序）会让下标整体错位，
        # 按下标比对等于把内容没变的段全部重渲。
        by_key: dict[str, str] = {}
        for v in (state.get("segments") or {}).values():
            k, p = (v or {}).get("key"), str((v or {}).get("path") or "")
            if k and p:
                by_key[k] = p
        for idx, seg in enumerate(segments, 1):
            seg_out = work / "segments" / f"seg_{idx:02d}.mp4"
            seg_key = _segment_key(seg, width, height, fps, mode)
            prev = by_key.get(seg_key)
            if prev and _file_ok(prev):
                if Path(prev) != seg_out:
                    seg_out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(prev, seg_out)
                self._emit_progress(f"③ 渲染分段 {idx}/{len(segments)}"
                                    f"（含 {len(seg['shots'])} 个镜头）：复用已完成片段")
                rendered.append(seg_out)
                reused_count += 1
                continue
            self._emit_progress(
                f"③ 渲染分段 {idx}/{len(segments)}（含 {len(seg['shots'])} 个镜头）："
                f"{seg['start']:.1f}-{seg['end']:.1f}s")
            if _segment_is_3d(seg):
                ok, err = self._render_segment_3d(seg, plan, work / "segments", idx,
                                                  width, height, fps, ui_ctx)
            else:
                ok, err = self._render_segment(seg, plan, audio_ctx, work / "segments", idx,
                                               width, height, fps, ui_ctx, bibles)
            if not ok:
                return ToolResult.fail(f"第 {idx} 段画面未通过：{err[:400]}")
            rendered.append(seg_out)
            state["segments"][str(idx)] = {"path": str(seg_out), "key": seg_key,
                                           "size": seg_out.stat().st_size}
            _save_state(state_path, state)
            # 多段片子：这一段的界面如果后面还会再出现，就提炼一份「视觉圣经」给后续段沿用。
            # 不同界面各自一份，绝不跨界面复用（同一款产品的不同界面必须各自读取）。
            if len(segments) > 1 and not _segment_is_3d(seg):
                later = {s for sg in segments[idx:] for s in _segment_surfaces(sg)}
                for surf in _segment_surfaces(seg):
                    if surf in later and surf not in bibles:
                        got = self._build_bible(
                            work / "segments" / f"hf_{idx:02d}" / "index.html", work, surf, seg)
                        if got:
                            bibles[surf] = got
                            state["bibles"] = bibles
                            _save_state(state_path, state)
                            (work / "visual-bible.json").write_text(
                                json.dumps({"surfaces": bibles}, ensure_ascii=False, indent=2),
                                encoding="utf-8")

        # ④ 拼接 + 铺声音
        video = rendered[0] if len(rendered) == 1 else work / "video-only.mp4"
        if len(rendered) > 1:
            ok, err = _concat(rendered, video)
            if not ok:
                return ToolResult.fail(f"片段拼接失败：{err[:300]}")

        self._emit_progress("④ 合成声音...")
        ok, err = self._attach_audio(video, out, audio_ctx, duration)
        if not ok:
            return ToolResult.fail(f"音轨合成失败：{err[:300]}")

        size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0
        total_shots = len(plan.get("shots") or [])
        reuse_note = ""
        if reused_count:
            reuse_note = (f"\n断点续跑：复用 {reused_count}/{len(segments)} 段已渲染画面，"
                          f"未重跑已完成的提取/音乐/蓝图")
        return ToolResult.ok(
            f"产品演示片完成：{out.name}（{duration:.1f}s，{total_shots} 个镜头，"
            f"{mode} 分流，分 {len(segments)} 次渲染拼接）{reuse_note}\n"
            f"分镜：{work / 'product-plan.json'}\n项目目录：{work}",
            output_path=str(out.absolute()),
            duration_s=round(duration, 3),
            audio_mode=mode,
            segments=len(segments),
            plan_path=str(work / "product-plan.json"),
            size_mb=round(size_mb, 2),
            resumed=resumable,
        )

    def _decide_duration(self, brief: str, product_name: str, mode: str) -> int:
        """用户没说时长：让模型按内容体量定，而不是套固定默认值。"""
        from skills.opendesign.scripts.renderer import call_llm_text

        ctx = (f"产品：{product_name or '（未给）'}\n"
               f"分流：{mode}（{'纯音乐，无旁白，文字承担叙事' if mode == 'bgm' else '有旁白'}）\n"
               f"要讲的内容：\n{brief}")
        try:
            with self._llm_ticker("时长判断") as beat:
                raw = call_llm_text(
                    system_prompt=_DURATION_PROMPT, context=ctx,
                    base_url=self.llm_config.get("base_url", ""),
                    api_key=self.llm_config.get("api_key", ""),
                    model=self.llm_config.get("model", ""),
                    protocol=self.llm_config.get("protocol", "anthropic"),
                    provider=self.llm_config.get("provider"),
                    thinking=self.llm_config.get("thinking"),
                    max_tokens=8000, timeout=LLM_STALL_TIMEOUT, attempts=1,
                    on_progress=beat,
                )
            doc = _json_of(raw)
            n = int(round(float(doc.get("duration_s"))))
            reason = str(doc.get("reason") or "").strip()
            if reason:
                self._emit_progress(f"  · 时长依据：{reason[:80]}")
            return max(10, min(90, n))
        except Exception as e:
            self._emit_progress(f"  · 时长判断失败（{e}），先按 20s 起跑")
            return 20

    def _select_music_window(self, music: Path | None, rhythm: dict, target: float, work: Path):
        """按内容需要的长度截取「节奏最密集」的一段；返回 (音乐文件, 该片段节奏)。

        成片长度先由蓝图定，音乐只是裁到同样长——所以截取起点必须落在原曲的小节线上，
        这样平移后蓝图里的切点仍然对拍。
        """
        if not music:
            return None, rhythm
        full = float(rhythm.get("audio_duration") or 0) or float(target)
        if full <= target * 1.25 + 2:
            return music, rhythm
        start = _pick_window(rhythm, target, full)
        cut = work / "audio" / f"bgm_cut_{int(start)}s_{int(round(target))}s.mp3"
        ok, err = _cut_audio(music, start, target, cut)
        if not ok:
            self._emit_progress(f"  · 音乐截取失败（{err[:80]}），改用整曲")
            return music, rhythm
        new_rhythm = self._analyze_rhythm(cut, work, target)
        self._emit_progress(
            f"① 音乐截取 {target:.1f}s（按内容长度）：全曲 {full:.1f}s，取节奏最密集的 "
            f"{start:.1f}-{start + target:.1f}s")
        return cut, new_rhythm

    # ───────────────────────────── 音乐 ─────────────────────────────
    def _ensure_music(self, music_path, music_prompt, work: Path, project,
                      duration_s: float, product_name: str = "", music_style: str = "trailer",
                      reuse: bool = False, extra: str = ""):
        """用户指定了音乐就用它；否则默认走音乐生成（纯器乐、节奏清晰可卡点，不限定乐器）。

        extra：用途层追加约束（如 vo 分流的"垫乐、不能抢话"），与气质预设正交。
        """
        if music_path:
            p = Path(music_path)
            if not p.is_absolute():
                p = Path(self.cwd) / p
            if not p.exists():
                return ToolResult.fail(f"音乐文件不存在：{p}")
            return p

        dst = work / "audio" / "bgm.mp3"
        if reuse and _file_ok(dst):
            self._emit_progress("① BGM：复用上次生成的文件（不再重新生成）")
            return dst

        preset = _MUSIC_PRESETS.get(str(music_style or "").lower(), _MUSIC_PRESETS["trailer"])
        prompt = (music_prompt or "").strip() or preset
        if not (music_prompt or "").strip():
            # 预设只管气质；节奏这件事统一强调一次，免得模型理解成"必须有鼓"
            prompt += ("\n用于卡点剪辑：节拍与重音要清晰可辨、分布均匀；"
                       "由哪些乐器/声部提供律动不限，不必是鼓组。")
        if product_name.strip():
            prompt += f"\n产品名：{product_name.strip()}（不要出现人声或人名列唱）"
        if (extra or "").strip():
            prompt += "\n" + extra.strip()
        # 生成时长留出余量：后面只会截取其中最有力的一段
        ask = int(max(90, min(150, float(duration_s or 45) + 40)))
        prompt += f"\n时长约 {ask} 秒，整段可循环（成片会截取其中最有力的段落）。"

        self._emit_progress("① 生成 BGM（纯音乐，无人声）...")
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = self._dispatch("music_generate", prompt=prompt, output_path=str(dst),
                           project=project, instrumental=True)
        if not r.success:
            return ToolResult.fail(f"BGM 生成失败：{r.content[:200]}")
        path = Path(r.details.get("output_path") or dst)
        return path if path.exists() else dst

    def _analyze_rhythm(self, music: Path | None, work: Path, duration: float | None = None) -> dict:
        from .scripts import rhythm as rhythm_mod
        res = rhythm_mod.analyze(music, None) if music else rhythm_mod._fixed_grid(
            {"ok": False, "reason": "无音乐"}, 0.0)
        total = float(res.get("audio_duration") or duration or 0)
        res["cut_grid"] = _cut_grid(res, total)
        rhythm_mod.save(res, work / "audio" / "rhythm.json")
        return res

    @contextmanager
    def _llm_ticker(self, label: str, every: float = 15.0):
        """心跳 + 看门狗：模型想很久、迟迟不吐 token 时，前端也能看到"还在等"。

        数据一到就按字数报进度；连续 every 秒没有任何数据，就报一次"等待模型响应"。
        """
        stop = threading.Event()
        state = {"last": time.monotonic()}
        t0 = time.monotonic()

        def cb(chars: int, elapsed: float) -> None:
            state["last"] = time.monotonic()
            phase = "编写中" if chars else "思考中"
            self._emit_progress(f"  · {label} {phase}：{int(elapsed)}s，已输出 {chars} 字")

        def watch() -> None:
            while not stop.wait(every):
                if time.monotonic() - state["last"] >= every:
                    state["last"] = time.monotonic()
                    self._emit_progress(
                        f"  · {label} 等待模型响应…已 {int(time.monotonic() - t0)}s（正常回落前不会中断）")

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        try:
            yield cb
        finally:
            stop.set()

    # ───────────────────────────── 蓝图 ─────────────────────────────
    def _make_plan(self, brief, duration, mode, audio_ctx, style_prompt, product_name,
                   ui_note, ui: dict | None = None):
        from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
        try:
            from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
        except Exception:
            LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS = 128_000, (96_000, 64_000, 32_000)

        rhythm = audio_ctx.get("rhythm") or {}
        system = _prompt_text("plan.md")
        last_errs: list[str] = []
        for attempt in range(1, MAX_PLAN_TRIES + 1):
            ctx = self._plan_context(brief, duration, mode, rhythm, style_prompt,
                                     product_name, ui_note, last_errs, ui)
            try:
                self._emit_progress(f"  · 分镜蓝图第 {attempt} 次生成...")
                with self._llm_ticker("分镜蓝图") as beat:
                    # 预算给足：思考 token 也计入 max_tokens，预算太小会被长思考吃光、正文为空
                    raw = _call_with_token_fallback(
                        lambda budget: call_llm_text(
                            system_prompt=system, context=ctx,
                            base_url=self.llm_config.get("base_url", ""),
                            api_key=self.llm_config.get("api_key", ""),
                            model=self.llm_config.get("model", ""),
                            protocol=self.llm_config.get("protocol", "anthropic"),
                            provider=self.llm_config.get("provider"),
                            thinking=self.llm_config.get("thinking"),
                            max_tokens=budget, timeout=LLM_STALL_TIMEOUT, attempts=1,
                            on_progress=beat,
                        ),
                        max_tokens=LONG_OUTPUT_MAX_TOKENS,
                        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                    )
            except Exception as e:
                last_errs = [f"调用失败：{e}"]
                self._emit_progress(f"  · 分镜蓝图第 {attempt} 次失败：{str(e)[:140]}")
                continue
            plan = _json_of(raw)
            if not plan:
                last_errs = ["输出不是合法 JSON"]
                self._emit_progress(f"  · 分镜蓝图第 {attempt} 次没拿到合法 JSON"
                                    f"（返回 {len(raw or '')} 字），重试")
                continue
            plan.setdefault("title", product_name or "产品演示")
            last_errs = _validate_plan(plan, duration, mode, rhythm)
            if not last_errs:
                return plan, []
            if all("全片都是 UI" in e for e in last_errs):
                # 只有这一条不合格时，机械补文字拍，不再烧一整轮 LLM 重写
                fixed = _rebalance_beats(plan)
                if not _validate_plan(fixed, duration, mode, rhythm):
                    return fixed, []
            self._emit_progress(f"  · 蓝图第 {attempt} 版不合规（{len(last_errs)} 条）："
                                f"{last_errs[0][:80]}；改为原地修补")
            # 反灌问题原地改：只让模型回要改的字段，不再整份重跑
            for r in range(1, MAX_PLAN_REPAIRS + 1):
                fixed, applied, failed = self._repair_plan(plan, last_errs, rhythm)
                if not applied:
                    self._emit_progress(f"  · 修补没有可应用的改动（{failed[:2]}）")
                    break
                plan = fixed
                last_errs = _validate_plan(plan, duration, mode, rhythm)
                self._emit_progress(f"  · 第 {attempt} 版就地修补 {r}：{applied} 处"
                                    + ("，仍有 " + last_errs[0][:60] if last_errs else "，已通过"))
                if not last_errs:
                    return plan, []
        return None, last_errs

    def _repair_plan(self, plan: dict, errs: list[str], rhythm: dict):
        """把校验问题反灌给模型，只回要改的字段；返回 (新蓝图, 已应用, 未应用)。"""
        from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
        try:
            from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
        except Exception:
            LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS = 128_000, (96_000, 64_000, 32_000)

        grid = [float(x) for x in (rhythm.get("cut_grid") or [])]
        ctx = (
            "【当前蓝图 JSON】\n" + json.dumps(plan, ensure_ascii=False, indent=1)[:24000] + "\n\n"
            "【校验报错】\n" + "\n".join(f"- {e}" for e in (errs or [])[:8]) + "\n\n"
            + (f"【可用的小节起点（秒）】{json.dumps([round(b, 2) for b in grid][:60])}\n\n" if grid else "")
            + "只输出 JSON 修改清单。"
        )
        try:
            with self._llm_ticker("蓝图修补") as beat:
                raw = _call_with_token_fallback(
                    lambda budget: call_llm_text(
                        system_prompt=_PLAN_REPAIR_PROMPT, context=ctx,
                        base_url=self.llm_config.get("base_url", ""),
                        api_key=self.llm_config.get("api_key", ""),
                        model=self.llm_config.get("model", ""),
                        protocol=self.llm_config.get("protocol", "anthropic"),
                        provider=self.llm_config.get("provider"),
                        thinking=self.llm_config.get("thinking"),
                        max_tokens=budget, timeout=LLM_STALL_TIMEOUT, attempts=1,
                        on_progress=beat,
                    ),
                    max_tokens=LONG_OUTPUT_MAX_TOKENS,
                    fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                )
        except Exception as e:
            self._emit_progress(f"  · 蓝图修补调用失败：{str(e)[:120]}")
            return plan, 0, [str(e)[:80]]
        doc = _json_of(raw)
        edits = doc.get("edits") if isinstance(doc, dict) else None
        if not isinstance(edits, list):
            return plan, 0, ["模型没返回 edits 清单"]
        new_plan, applied, failed = _apply_plan_edits(plan, edits)
        return new_plan, applied, failed

    def _plan_context(self, brief, duration, mode, rhythm, style_prompt, product_name,
                      ui_note, errs, ui: dict | None = None) -> str:
        from .scripts import rhythm as rhythm_mod
        lines = [
            f"产品/功能简报：\n{brief}",
            f"内容时长参考上限：{duration:.2f}s。这是「上限参考」而不是要填满的配额："
            f"把要演示的动作讲完就收尾，成片长度取最后一镜的 end——内容少就短一点，不要注水。",
            f"分流：{mode}（{'纯音乐 BGM，无旁白' if mode == 'bgm' else '有旁白'}）",
            f"产品名：{product_name or '（未给，可自行取一个中性名字）'}",
            f"视觉风格：{style_prompt or '（未指定，由你定一套统一调性）'}",
        ]
        if ui_note.strip():
            lines += ["界面要求：", ui_note.strip()]
        if ui:
            digest = (ui.get("digest") or "").strip()
            if digest:
                head = ("## UI 参照（依据截图转写的界面规格，分镜里的界面动作必须落在这些面板上）"
                        if ui.get("mode") == "shots" else
                        "## UI 真值（分镜里的界面动作必须落在这些真实面板上，不要虚构功能/按钮）")
                lines += ["", head + "；与上面的「界面要求」冲突时，一律以本节为准", digest[:2500]]
            if ui.get("assets"):
                lines += ["", '可用真实资源（已放在 assets/，直接 <img src="assets/…"> 使用，不要重画）：',
                          "、".join(ui["assets"][:12])]
            if ui.get("tokens_css"):
                lines += ["", "本段 HTML 已自动注入真实 ui-tokens，界面颜色/圆角/字号必须写成 var(--…)。"]
        if mode == "bgm":
            lines += ["", "音乐节奏网格：", rhythm_mod.summarize(rhythm)]
            grid = rhythm.get("cut_grid") or []
            if grid:
                lines += ["", "可用切点 cut_grid（除 0 外只能从这里取，已按各段密度算好间隔；"
                              "按内容需要用，讲到哪儿就用到哪儿，不必用完）：",
                          ", ".join(str(g) for g in grid)]
            targets = _shot_targets(rhythm)
            lines += ["", "节奏密度（切镜速度必须跟着它走，不要全片一个长度）："]
            for s in (rhythm.get("sections") or [])[:8]:
                lvl = str(s.get("level") or "mid")
                tgt = targets.get(lvl, 3.0)
                if lvl == "high":
                    tip = "只放 2–4 字标题、不要副标；切镜紧凑"
                elif lvl == "low":
                    tip = "标题 ≤12 字，可带副标；镜头可以慢下来"
                else:
                    tip = "标题 ≤8 字，副标短句；中速推进"
                lines.append(f"- {s['start']}-{s['end']}s {lvl}：建议单镜 ≈{tgt}s，{tip}")
            lines += ["", "硬要求：除第一镜外，每镜 start 必须等于 cut_grid 里的某个值（误差 ≤0.12s）；"
                          "并把用到的切点尽量用满（至少六成），镜头太粗节奏就会拖。",
                          "注意：相邻两个切点之间可能隔着 4~5 秒——那是那段音乐没有可用强拍，"
                          "直接按这个间隔定镜头时长即可，不要为了凑“建议秒数”去改时间轴或跳过切点。",
                          "内容优先：一镜能讲完的动作就让它一镜讲完。**严禁把同一个功能、同一组画面"
                          "拆成两三个镜头重复演示来凑时长**；内容不够就少讲一个次要动作、片子短一点，"
                          "也不要用重复内容把时间轴填满。"]
            n_shots = _shots_within(rhythm, duration)
            if n_shots:
                pattern = _suggest_beats(n_shots)
                lines += ["", f"按参考上限与节奏密度估算，全片**最多**约 {n_shots} 镜——"
                              "按真实内容需要取用，够表达就收尾，宁少不多（不要为了凑镜数拆重复内容）："
                              f"镜数接近上限时的建议拍子序列：{', '.join(pattern)}"
                              "（顺序可调，但首尾用 text，连续 ui 不超过 2 个）"]
            lines += ["", "标题位置：每镜写 focus_panel 与 title_zone，二者不能同侧；"
                          "focus_panel=whole 时 title_zone 只能用 top/bottom。"
                          "界面上没有留白就让窗口让位，不要用遮罩盖住正在演示的面板。"]
        else:
            lines += ["", "旁白：每镜写一句中文旁白，句子按内容需要写；"
                          "成片长度由各句实测语速累加得出（上面只是规模参考，讲完就收尾）。"]
        if errs:
            lines += ["", "上一版被校验打回，逐条修正："] + [f"- {e}" for e in errs]
        lines += ["", "只输出 JSON。"]
        return "\n".join(lines)

    def _plan_confirm_result(self, plan: dict, work: Path, mode: str) -> ToolResult:
        """蓝图定稿但尚未开工：交主 LLM 用 ask_user 给用户确认（与 director 同一套做法）。"""
        shots = plan.get("shots") or []
        end = round(float(shots[-1]["end"]), 3) if shots else 0.0
        plan["duration"] = end
        plan["audio_mode"] = mode
        rows = []
        for i, s in enumerate(shots, 1):
            try:
                a, b = float(s.get("start")), float(s.get("end"))
            except (TypeError, ValueError):
                a = b = 0.0
            kind = ("文字" if str(s.get("beat_type") or "ui").strip().lower() == "text"
                    else (str(s.get("ui_surface") or "").strip() or "界面"))
            if _shot_is_3d(s):
                st = s.get("stage3d") or {}
                kind = f"3D {st.get('device') or ''}/{st.get('action') or ''}".strip("/")
            text = "｜".join(x for x in (
                str(s.get("kicker") or "").strip(),
                str(s.get("title") or "").replace("\n", " / ").strip(),
                str(s.get("sub") or "").strip()) if x)
            rows.append(f"{i}. {a:.1f}-{b:.1f}s【{kind}】{text[:70]}")
        plan_path = work / "product-plan.json"
        try:
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        music_note = "配乐已生成（成片会裁到与蓝图同样长）。\n" if mode == "bgm" else ""
        content = (
            f"分镜蓝图已定稿：约 {end:.1f}s，{len(shots)} 个镜头。{music_note}"
            "**请立刻用 ask_user 把下面的分镜表交给用户确认**，不要自己开始制作。\n"
            "用户确认后 → 带同一 project / output_path，把下方「蓝图 JSON」原样作为 plan 参数再调用本工具开始制作；\n"
            "用户要改某几镜 → 按意见改蓝图 JSON 里对应字段（时间轴/文案/界面动作）后带 plan 调用；\n"
            "**制作中断后继续（断点续跑）→ 只带同一 project / output_path 再调一次，不要传 plan / brief**：\n"
            "工具会沿用已定稿蓝图继续，省略的参数按项目首次调用时的设定继承；重复附送蓝图反而可能把已跑过的重排。\n"
            "用户要整体重做 → 带 brief + force=true 重新设计（会再次进入确认）。\n\n"
            f"分镜表（{end:.1f}s / {len(shots)} 镜）：\n" + "\n".join(rows) +
            "\n\n蓝图 JSON：\n" + json.dumps(plan, ensure_ascii=False)
        )
        return ToolResult.ok(
            content, need_confirm=True, plan=plan, plan_path=str(plan_path),
            duration_s=end, audio_mode=mode, shots=len(shots))

    # ───────────────────────────── 旁白 ─────────────────────────────
    def _prepare_voice(self, plan: dict, work: Path, project, saved: list | None = None):
        shots = plan.get("shots") or []
        texts = [str(s.get("narration") or "").strip() for s in shots]
        if not all(texts):
            return [], plan, "vo 分流要求每镜都有 narration，蓝图里有空句子"
        saved = saved or []
        if (len(saved) == len(texts)
                and [str(x.get("text") or "").strip() for x in saved] == texts
                and all(_file_ok(x.get("path")) for x in saved)):
            # 文案没变：沿用上次合成好的旁白，不重新跑一遍 TTS；时间轴按同一套规则回填
            self._emit_progress("② 旁白：复用上次音频")
            cursor = 0.0
            audio = []
            for shot, item in zip(shots, saved):
                dur = float(item.get("duration") or 2.0)
                shot["start"] = round(cursor, 3)
                shot["end"] = round(cursor + dur + 0.28, 3)
                cursor = shot["end"]
                audio.append({"path": item.get("path"), "start": shot["start"],
                              "duration": dur, "text": item.get("text", "")})
            return audio, plan, ""
        segs = [{"text": t} for t in texts]
        r = self._dispatch("narration", segments=segs, project=project,
                           output_dir=str(work / "audio" / "voice"))
        if not r.success:
            return [], plan, f"旁白生成失败：{r.content[:200]}"
        got = r.details.get("segments") or []
        if len(got) != len(shots):
            return [], plan, f"旁白段数不一致（{len(got)} vs {len(shots)}）"

        cursor = 0.0
        audio = []
        for shot, seg in zip(shots, got):
            dur = float(seg.get("duration") or 2.0)
            shot["start"] = round(cursor, 3)
            shot["end"] = round(cursor + dur + 0.28, 3)
            cursor = shot["end"]
            audio.append({"path": seg.get("audio_path"), "start": shot["start"],
                          "duration": dur, "text": seg.get("text", "")})
        return audio, plan, ""

    # ───────────────────────────── UI 真值 ─────────────────────────────
    def _build_ui_context(self, ui_source: str, work: Path, ui_mode: str):
        """从真实前端工程抽 UI 规格；不是把源码塞进提示词，而是抽 token / 布局 / 资源。"""
        from .scripts.uidigest import build as build_ui

        roots = []
        for item in re.split(r"[\n;]+", str(ui_source)):
            item = item.strip()
            if not item:
                continue
            p = Path(item)
            if not p.is_absolute():
                p = Path(self.cwd) / p
            if not p.exists():
                return ToolResult.fail(f"ui_source 路径不存在：{p}")
            roots.append(p)
        if not roots:
            return ToolResult.fail("ui_source 为空")

        if str(ui_mode).lower() == "shots":
            shots = _image_files(roots)
            self._emit_progress(f"  · 截图转写中（{min(len(shots), 3)}/{len(shots)} 张，"
                                "先转成界面规格再由模型重建）...")
            return _shots_context(roots, work / "ui", self.llm_config)

        info = build_ui(roots, work / "ui")
        if not info.get("tokens") and not info.get("components"):
            # 没有可解析的前端样式时不要直接判死：目录里有截图就走截图转写，让模型照样能画
            if _image_files(roots):
                self._emit_progress("  · 源码里没有可解析的样式，改用截图转写...")
                info = _shots_context(roots, work / "ui", self.llm_config)
                info["digest"] = info["digest"] + (
                    "\n\n（注：ui_source 里没解析到 CSS 变量或组件样式，界面规格来自截图转写。）"
                    if info.get("shots") else
                    "\n\n（注：ui_source 里没有可解析的样式，截图也没能读出来，按 brief 自由还原。）")
                return info
            return ToolResult.fail(
                "ui_source 里既没有可解析的前端样式（.css/.tsx），也没有截图可用："
                "请给前端工程目录，或给 png/jpg 截图，或干脆不传 ui_source 让导演自由还原")
        info["mode"] = ui_mode
        if str(ui_mode).lower() == "hybrid":
            shots = _image_files(roots)
            if shots:
                self._emit_progress("  · 截图补充：转写中...")
            described = [(n, d) for n, d in _describe_shots(shots, self.llm_config)
                         if not d.startswith("（读图失败")]
            if described:
                extra = ["", "", "## 截图补充（和上面的代码抽取互相印证；文字/控件以截图为准）"]
                for i, (name, desc) in enumerate(described, 1):
                    extra += ["", f"### 截图 {i}（{name}）", desc]
                info["digest"] = (info.get("digest") or "") + "\n".join(extra)
        return info

    # ───────────────────────────── 画面 ─────────────────────────────
    def _build_bible(self, html_path: Path, work: Path, surface: str, seg: dict) -> dict:
        """给「一块界面」提炼视觉圣经：这块界面以后再次出现时照着它画。

        只提炼界面外壳与控件语言（窗口、面板、字体、配色、控件），不锁死标题与运镜；
        同段里的其他界面与纯文字拍一律忽略，避免不同类型界面互相串样式。
        """
        from skills.opendesign.scripts.renderer import call_llm_text

        html_path = Path(html_path)
        work = Path(work)
        try:
            html = html_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        # 时间线/动效脚本与视觉契约无关，去掉能显著省 token
        body = re.sub(r"<script[\s\S]*?</script>", "", html)
        body = re.sub(r"\n\s*\n+", "\n", body)[:20000]
        shots = [s for s in (seg.get("shots") or []) if _shot_surface(s) == surface]
        brief = "\n".join(
            f"- 第 {s.get('index')} 镜：{str(s.get('ui') or '')[:160]}"
            for s in shots)
        ctx = (f"【本次只提炼这一块界面】{surface}\n"
               f"这块界面在本段里的镜头（用于定位 HTML 中的对应部分）：\n{brief or '（无描述）'}\n\n"
               f"【已定稿 HTML】\n{body}")
        try:
            self._emit_progress(f"  · 界面「{surface}」定稿：提炼视觉圣经...")
            with self._llm_ticker("视觉圣经") as beat:
                raw = call_llm_text(
                    system_prompt=_BIBLE_PROMPT, context=ctx,
                    base_url=self.llm_config.get("base_url", ""),
                    api_key=self.llm_config.get("api_key", ""),
                    model=self.llm_config.get("model", ""),
                    protocol=self.llm_config.get("protocol", "anthropic"),
                    provider=self.llm_config.get("provider"),
                    thinking=self.llm_config.get("thinking"),
                    max_tokens=8000, timeout=LLM_STALL_TIMEOUT, attempts=1,
                    on_progress=beat,
                )
        except Exception as e:
            self._emit_progress(f"  · 界面「{surface}」视觉圣经提炼失败（后续不强行复用）：{e}")
            return {}
        bible = _json_of(raw)
        if not bible:
            self._emit_progress(f"  · 界面「{surface}」视觉圣经未解析到 JSON，后续不强行复用")
            return {}
        self._emit_progress(f"  · 界面「{surface}」视觉圣经已定："
                            + "、".join(list(bible.keys())[:6]))
        return bible

    def _render_segment(self, seg, plan, audio_ctx, out_dir: Path, idx: int,
                        width: int, height: int, fps: int, ui: dict | None = None,
                        bibles: dict | None = None):
        from skills.opendesign.scripts.renderer import localize_scripts, render, scaffold_project
        from skills.opendesign.scripts.gate import repair_html

        seg_dur = round(float(seg["end"]) - float(seg["start"]), 3)
        proj = out_dir / f"hf_{idx:02d}"
        scaffold_project(proj, f"product_seg_{idx:02d}")
        self._ensure_gsap(proj)
        _copy_ui_assets(proj, ui)

        t0 = time.monotonic()
        html = self._compose_html(seg, plan, audio_ctx, width, height, fps, "", ui, bibles)
        if not html:
            return False, "画面生成调用失败"
        t_compose = time.monotonic() - t0
        html = localize_scripts(html, proj)

        # 先"就地修补"再考虑重写：修补只让模型回几十行 diff，失败一次的代价是秒级而不是分钟级
        self._emit_progress(f"  · 第 {idx} 段落盘，闸门校验（结构/运行时/确定性）...")
        html, ok, errs, kind = self._gate_once(proj, html, seg_dur, width, height, seg=seg)
        repairs = 0
        while not ok and repairs < MAX_REPAIR_TRIES:
            self._emit_progress(f"  · 第 {idx} 段闸门未过（{kind}）：{(errs or ['未知原因'])[0][:70]}；"
                                f"就地修补 {repairs + 1}/{MAX_REPAIR_TRIES}...")
            with self._llm_ticker(f"第 {idx} 段修补") as beat:
                new_html, applied, failed = repair_html(html, errs, kind, self.llm_config,
                                                        seg_dur, width, height,
                                                        on_progress=beat)
            if not applied:
                break
            html = new_html
            repairs += 1
            self._emit_progress(f"  · 第 {idx} 段就地修补 {repairs}：{applied} 处"
                                + (f"，{len(failed)} 处未匹配" if failed else ""))
            html, ok, errs, kind = self._gate_once(proj, html, seg_dur, width, height, ui, seg)

        if not ok:
            # 兜底：修补救不回来才整段重写，并把真实错误带回去
            self._emit_progress(f"  · 第 {idx} 段修补无效，整段重写一次")
            last = "闸门未通过（" + kind + "）：" + "；".join(errs[:3])
            html2 = self._compose_html(seg, plan, audio_ctx, width, height, fps, last, ui, bibles)
            if html2:
                html = localize_scripts(html2, proj)
                html, ok, errs, kind = self._gate_once(proj, html, seg_dur, width, height, ui, seg)

        if not ok:
            return False, "闸门未通过（" + kind + "）：" + "；".join(errs[:3])

        self._emit_progress(f"  · 第 {idx} 段过闸（生成 {t_compose:.0f}s，修补 {repairs} 次）")
        dst = out_dir / f"seg_{idx:02d}.mp4"
        t2 = time.monotonic()
        self._emit_progress(f"  · 第 {idx} 段渲染 {width}×{height}@{fps}fps...")
        try:
            render(proj, dst, fps=fps)
        except Exception as e:
            return False, f"渲染失败：{e}"
        self._emit_progress(f"  · 第 {idx} 段渲染 {time.monotonic() - t2:.0f}s")
        return True, ""

    def _render_segment_3d(self, seg, plan, out_dir: Path, idx: int,
                           width: int, height: int, fps: int, ui_ctx: dict | None = None):
        """3D 设备镜头段：每个镜头单独渲一段（设备 + 真实屏显 + 镜头运动），再拼成这一段的 mp4。"""
        from skills.product_director.scripts.stage3d import render_shot

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        shots = seg.get("shots") or []
        clips: list[Path] = []
        for i, shot in enumerate(shots, 1):
            spec = (shot.get("stage3d") or {})
            clip = out_dir / f"clip_{idx:02d}_{i:02d}.mp4"
            self._emit_progress(
                f"  · 第 {idx} 段 3D 镜头 {i}/{len(shots)}"
                f"（{spec.get('device')} · {spec.get('action')} · "
                f"{float(shot['end']) - float(shot['start']):.1f}s）")
            ok, err = render_shot(shot=shot, plan=plan, work=out_dir, dest=clip,
                                  width=width, height=height, fps=fps,
                                  ui_ctx=ui_ctx or {}, llm_config=self.llm_config,
                                  log=self._emit_progress)
            if not ok:
                return False, err
            clips.append(clip)

        dst = out_dir / f"seg_{idx:02d}.mp4"
        if len(clips) == 1:
            shutil.copyfile(clips[0], dst)
            return True, ""
        ok, err = _concat(clips, dst)
        if not ok:
            return False, f"3D 片段拼接失败：{err[:200]}"
        return True, ""

    def _gate_once(self, proj: Path, html: str, seg_dur: float, width: int, height: int,
                   ui: dict | None = None, seg: dict | None = None):
        """落盘 + 跑代码闸门 + 读图兜底，返回 (html, ok, errs, kind)。

        代码闸门（结构/运行时/确定性）照旧生效；视觉这一步只保留"读图":
        - 只问"有没有明显的画面错误"（空屏/黑屏/内容缺失/严重错乱），
          不判可读性、对比度、底部安全区、标题压区这些审美与版式约束；
        - 只判动画已落位的帧，并跳过像素级空白帧（每段片头就是淡入黑场，不是错误）；
        - 少数帧说"没内容"只当参考：读图侧要"多数帧都异常"才判失败，避免暗色极简画面被反复否决；
        - 标题压区这类几何量只提示、不阻断——它反复在小地方打磨，收益远不如让片子出去。
        """
        from skills.opendesign.scripts.gate import review_frames, run_gates
        tokens_css = (ui or {}).get("tokens_css") or ""
        html = _sanitize_html(html, seg_dur, width, height, tokens_css)
        (proj / "index.html").write_text(html, encoding="utf-8")
        if tokens_css and "var(--" not in html:
            return html, False, ["没有使用真实设计变量 var(--…)：界面会偏离真实 UI"], "visual"
        # 先量最便宜的一项：标题是否压住主展示区（只提示，不拦）
        if seg:
            layout = _title_overlap_issues(proj, seg.get("shots") or [],
                                           float(seg.get("start") or 0.0), width, height)
            if layout:
                self._emit_progress("  · 布局提示（不阻断出片）：" + layout[0][:80])
        ok, _, errs, kind = run_gates(proj, seg_dur, width, height)
        if not ok:
            return html, False, errs, kind
        self._emit_progress("  · 闸门通过，读图兜底中...")
        details = review_frames(proj, self.llm_config, check_bottom_safe=False,
                                with_kind=True, simple=True)
        if details:
            # 读图侧已过滤过渡帧/黑场，且要求"多数帧都异常"才返回，这里拿到即为明确问题
            return html, False, ["画面明显异常：" + "；".join(d["text"] for d in details[:2])], "visual"
        return html, True, [], ""

    def _compose_html(self, seg, plan, audio_ctx, width, height, fps, last_err, ui=None,
                      bibles: dict | None = None):
        from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
        try:
            from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
        except Exception:
            LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS = 128_000, (96_000, 64_000, 32_000)

        ctx = self._compose_context(seg, plan, audio_ctx, width, height, fps, last_err, ui, bibles)
        try:
            with self._llm_ticker("画面") as beat:
                return _call_with_token_fallback(
                    lambda budget: call_llm_text(
                        system_prompt=_prompt_text("compose.md"), context=ctx,
                        base_url=self.llm_config.get("base_url", ""),
                        api_key=self.llm_config.get("api_key", ""),
                        model=self.llm_config.get("model", ""),
                        protocol=self.llm_config.get("protocol", "anthropic"),
                        provider=self.llm_config.get("provider"),
                        thinking=self.llm_config.get("thinking"),
                        max_tokens=budget, timeout=LLM_STALL_TIMEOUT, attempts=1,
                        on_progress=beat,
                    ),
                    max_tokens=LONG_OUTPUT_MAX_TOKENS,
                    fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                )
        except Exception as e:
            self._emit_progress(f"  · 画面生成失败：{e}")
            return ""

    def _compose_context(self, seg, plan, audio_ctx, width, height, fps, last_err,
                         ui: dict | None = None, bibles: dict | None = None) -> str:
        from .scripts import rhythm as rhythm_mod

        seg_start, seg_end = float(seg["start"]), float(seg["end"])
        seg_dur = round(seg_end - seg_start, 3)
        style = plan.get("style") or {}
        # 结尾落版只属于"全片最后一段"：每段都收到落版，模型就会在每段末尾都做一次片尾，
        # 拼起来每隔二十几秒出现一次 logo/标语收尾。
        endcard = plan.get("endcard") or {}
        all_shots = plan.get("shots") or []
        is_last_seg = bool(seg.get("shots")) and bool(all_shots) and abs(
            float(seg["shots"][-1].get("end") or 0) - float(all_shots[-1].get("end") or 0)) < 1e-3
        if endcard and is_last_seg:
            endcard_line = (f"结尾落版（全片只有本段有片尾，放在本段最后一镜）："
                            f"{json.dumps(endcard, ensure_ascii=False)}")
        else:
            endcard_line = ("结尾落版：无 —— 本段不是全片结尾。段尾不要做 logo/标语/片尾/淡出黑场，"
                            "画面保持到段末，下一段会无缝接上。")
        lines = [
            f"产品：{plan.get('title', '')}",
            f"本段时长：{seg_dur:.2f}s（本段是整片的 {seg_start:.1f}-{seg_end:.1f}s）",
            f"画布：{width}×{height} @ {fps}fps",
            # 字号写死具体像素：模型对"≥69px"的遵守度远高于抽象描述，侧边/底部的字就是太小
            f"文字尺寸下限（硬性）：1u = 画布宽/100 = {width / 100:.1f}px；"
            f"ui 拍主标题 ≥{width * 0.036:.0f}px（建议 {width * 0.04:.0f}–{width * 0.06:.0f}px），"
            f"sub ≥{width * 0.017:.0f}px，kicker/小标签 ≥{width * 0.0145:.0f}px；"
            f"整屏 text 拍主标题 ≥{width * 0.08:.0f}px。"
            "标题层任何位置（侧边/顶部/底部）都不许出现 12–24px；放不下就拆行、砍字或加宽标题带，不要缩字号。",
            f"分流：{plan.get('audio_mode')}",
            f"风格：{json.dumps(style, ensure_ascii=False)}",
            endcard_line,
            "",
            "本段镜头（时间已换算成本段内秒数，直接用）：",
        ]
        if ui:
            digest = (ui.get("digest") or "").strip()
            if digest:
                head = ("## UI 参照（依据截图转写的界面规格重建；截图不作为图片素材贴进画面；"
                        "不得自创配色/图标/栏宽）"
                        if ui.get("mode") == "shots" else
                        "## UI 真值（从真实前端工程抽取，必须照此还原；"
                        "不得自创配色/图标/栏宽）")
                lines += ["", head + "；与「界面要求」冲突时以本节为准", digest[:6000]]
            if ui.get("assets"):
                lines += ["", '可用真实资源（已放在 assets/，直接 <img src="assets/…"> 使用，不要重画）：',
                          "、".join(ui["assets"][:12])]
            if ui.get("tokens_css"):
                lines += ["", "本段 HTML 已自动注入真实 ui-tokens：界面内部的颜色/圆角/字号写成 var(--…)；"
                              "标题层（data-title）不受字体 token 限制，按上面的字号下限排。"]
            if ui.get("mode") == "shots":
                # 截图没有代码级的布局约束，作画更容易把标题排出边界/压住窗口：给保守几何
                lines += ["", "几何保守规则（截图模式没有代码级布局约束，按这个来）：",
                          "- 应用窗口整体控制在画面宽 72%–78%、上下各留 ≥120px，居中或偏向与标题相反的一侧；",
                          "- 标题块距画面边界 ≥64px；侧边带单行 ≤6 字、最多 3 行；顶部/底部带单行 ≤12 字；",
                          "- 标题按上面的字号下限排，放不下就拆行，不要缩字号；",
                          "- 界面细节不确定时少放控件、多留白，不要把不存在的元素编出来。"]
        if bibles:
            present = [s for s in _segment_surfaces(seg) if s in bibles]
            if present:
                lines += [
                    "",
                    "## 视觉契约（按界面标识，只对同一块界面生效）",
                    "本片已经画过的界面各自有一份契约。每镜用哪块界面看 shot 里的 surface 字段；"
                    "**同一个 surface 必须与它的契约一致（窗口外壳、面板几何、字体层级、控件语言、配色）；"
                    "不同 surface 是产品的不同界面，绝不能互相套用样式**。"
                    "标题排版、镜头运动、画面内容仍按本段分镜来，不要整段照抄。",
                ]
                for surf in present:
                    lines += ["", f"### surface: {surf}",
                              json.dumps(bibles[surf], ensure_ascii=False, indent=1)]
        for shot in seg["shots"]:
            s = round(float(shot["start"]) - seg_start, 3)
            e = round(float(shot["end"]) - seg_start, 3)
            lines.append(json.dumps({
                "start": s, "end": e,
                "kicker": shot.get("kicker", ""),
                "title": shot.get("title", ""),
                "sub": shot.get("sub", ""),
                "ui": shot.get("ui", ""),
                "camera": shot.get("camera", ""),
                "focus": shot.get("focus", ""),
                "focus_panel": shot.get("focus_panel", ""),
                "title_zone": shot.get("title_zone", ""),
                "surface": _shot_surface(shot),
                "beat_type": shot.get("beat_type", "ui"),
                "title_style": shot.get("title_style", ""),
                "narration": shot.get("narration", ""),
            }, ensure_ascii=False))
        if plan.get("audio_mode") == "bgm":
            beat = _slice_grid(audio_ctx.get("rhythm") or {}, seg_start, seg_end)
            lines += ["", "本段可用拍点（秒，已换算到本段起点）：",
                      json.dumps([round(b, 2) for b in beat["downbeats"]], ensure_ascii=False),
                      f"BPM={beat['bpm']}，切镜与大幅运镜尽量落在这些点上。"]
        else:
            lines += ["", "本段旁白已按实测时长排好；运镜要慢，文字只留关键词。"]
        if last_err:
            lines += ["", "上一版被打回的原因（必须改掉）：", last_err]
        lines += ["", "只输出 index.html 全文。"]
        return "\n".join(lines)

    def _ensure_gsap(self, proj: Path) -> None:
        dst = proj / "gsap.min.js"
        if dst.exists():
            return
        src = VENDOR_DIR / "gsap.min.js"
        if src.exists():
            shutil.copy2(src, dst)

    # ───────────────────────────── 声音合成 ─────────────────────────────
    def _attach_audio(self, video: Path, out: Path, audio_ctx: dict, duration: float):
        mode = audio_ctx.get("mode")
        if mode == "bgm" and audio_ctx.get("music"):
            fade = max(0.6, min(1.5, duration * 0.08))
            # apad + -t：音乐比成片短时补静音，不剪画面；比成片长时按成片长度截断
            fc = (f"[1:a]volume=0.9,afade=t=in:st=0:d=0.4,"
                  f"afade=t=out:st={max(0.0, duration - fade):.2f}:d={fade:.2f},apad[a]")
            return _run_ffmpeg(["-i", str(video), "-i", str(audio_ctx["music"]),
                                "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
                                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-t", f"{duration:.3f}", str(out)])
        if mode == "vo" and audio_ctx.get("narration"):
            inputs, filters, tags = ["-i", str(video)], [], []
            idx = 1
            for item in audio_ctx["narration"]:
                p = item.get("path")
                if not p or not Path(p).exists():
                    continue
                inputs += ["-i", str(p)]
                delay = max(0, int(round(float(item.get("start") or 0) * 1000)))
                filters.append(f"[{idx}:a]adelay={delay}|{delay}[a{idx}]")
                tags.append(f"[a{idx}]")
                idx += 1
            if not tags:
                return False, "没有可用的旁白音轨"
            if len(tags) == 1:
                filters.append(f"{tags[0]}anull[voice]")
            else:
                filters.append("".join(tags) + f"amix=inputs={len(tags)}:normalize=0[voice]")

            music = audio_ctx.get("music")
            if music and Path(music).exists():
                mi = idx
                inputs += ["-i", str(music)]
                fade = max(0.8, min(2.2, duration * 0.10))
                filters.append(
                    f"[{mi}:a]volume={_VO_BED_GAIN},"
                    f"afade=t=in:st=0:d=1.0,"
                    f"afade=t=out:st={max(0.0, duration - fade):.2f}:d={fade:.2f},"
                    "apad[bed]")
                # 闪避：人声一响就把垫乐压下去，人声停了几百毫秒内自动恢复。
                # 同一个 voice 流不能既当侧链又进 amix，所以先 asplit 成两路。
                # apad 必须在 asplit 之前：否则侧链在最后一句结束时断掉，
                # 垫乐会跟着一起收，成片尾巴上会留一段死寂。
                filters.append("[voice]apad,asplit=2[vside][vmix]")
                filters.append("[bed][vside]sidechaincompress="
                               "threshold=0.02:ratio=9:attack=12:release=420:makeup=1[ducked]")
                filters.append("[vmix][ducked]amix=inputs=2:normalize=0,"
                               "alimiter=limit=0.95,apad[a]")
            else:
                filters.append("[voice]apad[a]")
            return _run_ffmpeg(inputs + ["-filter_complex", ";".join(filters),
                                         "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                                         "-c:a", "aac", "-b:a", "192k",
                                         "-t", f"{duration:.3f}", str(out)])
        # 没有声音：直接搬运
        try:
            shutil.copy2(video, out)
            return True, ""
        except OSError as e:
            return False, str(e)

    # ───────────────────────────── 调度 ─────────────────────────────
    def _dispatch(self, name: str, **kwargs) -> ToolResult:
        if self.skill_manager is None:
            return ToolResult.fail(f"没有 skill_manager，无法调用 {name}")
        try:
            sub = self.skill_manager.get_tool(name)
            sub.set_progress_callback(
                lambda ev: self._emit_progress(f"[{name}] {ev.get('content', '')}"))
        except Exception:
            pass
        return self.skill_manager.dispatch(name, **kwargs)


# ───────────────────────────── 纯函数 ─────────────────────────────
def _parse_path(path: str) -> list:
    """把 `shots[2].title` 这类字段路径拆成 ['shots', 2, 'title']。"""
    tokens: list = []
    for m in re.finditer(r"\[(\d+)\]|([^.\[\]]+)", str(path or "")):
        tokens.append(int(m.group(1)) if m.group(1) is not None else m.group(2))
    return tokens


def _set_path(root, tokens: list, value) -> bool:
    """按路径写入；中间容器缺失就按下一级类型补出来，越界/类型不符返回 False。"""
    cur = root
    for i, tok in enumerate(tokens):
        last = i == len(tokens) - 1
        if isinstance(tok, int):
            if not isinstance(cur, list) or not 0 <= tok < len(cur):
                return False
            if last:
                cur[tok] = value
            else:
                cur = cur[tok]
        else:
            if not isinstance(cur, dict):
                return False
            if last:
                cur[tok] = value
            else:
                if tok not in cur or not isinstance(cur[tok], (dict, list)):
                    cur[tok] = [] if isinstance(tokens[i + 1], int) else {}
                cur = cur[tok]
    return True


def _apply_plan_edits(plan: dict, edits: list) -> tuple[dict, int, list[str]]:
    """把"字段路径 + 新值"应用到蓝图副本；返回 (新蓝图, 成功数, 失败项)。"""
    import copy

    new_plan = copy.deepcopy(plan)
    applied, failed = 0, []
    for item in edits or []:
        if not isinstance(item, dict):
            failed.append(f"非法编辑项：{str(item)[:40]}")
            continue
        path = item.get("path")
        if not str(path or "").strip():
            failed.append("缺少 path")
            continue
        if "value" not in item:
            failed.append(f"{path}: 缺少 value")
            continue
        tokens = _parse_path(path)
        if not tokens:
            failed.append(f"{path}: 路径无效")
            continue
        if _set_path(new_plan, tokens, item["value"]):
            applied += 1
        else:
            failed.append(str(path))
    return new_plan, applied, failed


def _plan_sig(plan: dict) -> str:
    """蓝图内容指纹：只比较决定"要做哪些镜头"的字段，忽略工具回填的 duration/audio_mode。"""
    core = {k: v for k, v in (plan or {}).items() if k not in ("duration", "audio_mode")}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _plan_structure_errors(plan: dict) -> list[str]:
    """只查"能不能安全切段渲染"，不查节奏/排版等成片级质量。"""
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        return ["shots 不能为空"]
    errs: list[str] = []
    prev = 0.0
    for i, shot in enumerate(shots, 1):
        if not isinstance(shot, dict):
            errs.append(f"第 {i} 镜不是对象")
            continue
        try:
            s, e = float(shot.get("start")), float(shot.get("end"))
        except (TypeError, ValueError):
            errs.append(f"第 {i} 镜 start/end 不是数字")
            continue
        if e <= s:
            errs.append(f"第 {i} 镜 end 不大于 start")
        if abs(s - prev) > 0.06:
            errs.append(f"第 {i} 镜与上一镜时间轴不连续")
        prev = e
    return errs[:8]


def _validate_plan(plan: dict, duration: float, mode: str, rhythm: dict) -> list[str]:
    errs: list[str] = []
    shots = plan.get("shots")
    if not isinstance(shots, list) or not shots:
        return ["shots 不能为空"]
    style = plan.get("style") if isinstance(plan.get("style"), dict) else {}
    for key in ("bg", "accent"):
        v = str(style.get(key) or "").strip()
        if v and not re.fullmatch(r"#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", v):
            errs.append(f"style.{key} 必须是 hex 色值（如 #0B0D12），现在是「{v[:20]}」")
    prev_end = 0.0
    grid = [float(x) for x in (rhythm.get("cut_grid") or [])]
    downbeats = grid or [float(x) for x in (rhythm.get("downbeats") or [])]
    used_marks = 0
    for i, shot in enumerate(shots, 1):
        try:
            s, e = float(shot.get("start")), float(shot.get("end"))
        except (TypeError, ValueError):
            errs.append(f"第 {i} 镜 start/end 不是数字")
            continue
        if e - s < 1.2:
            errs.append(f"第 {i} 镜只有 {e - s:.2f}s（≥1.2s）")
        if abs(s - prev_end) > 0.06:
            errs.append(f"第 {i} 镜从 {s:.2f}s 开始，与上一镜结束 {prev_end:.2f}s 不连续")
        prev_end = e
        cam = str(shot.get("camera") or "").strip().lower()
        if cam and mode == "vo" and cam not in _CAM_VO:
            errs.append(f"第 {i} 镜运镜 {cam} 不适合 vo 分流（只能用 {sorted(_CAM_VO)}）")
        if cam and cam not in _CAM_BGM and cam not in _CAM_VO:
            errs.append(f"第 {i} 镜运镜 {cam} 不在允许列表")
        fp = str(shot.get("focus_panel") or "").strip().lower()
        tz = str(shot.get("title_zone") or "").strip().lower()
        bt = str(shot.get("beat_type") or "ui").strip().lower()
        if bt not in {"text", "ui"}:
            errs.append(f"第 {i} 镜 beat_type 只能是 text 或 ui")
        if bt == "text":
            # 纯文字拍没有界面，不需要 focus/zone；但标题必须够长
            if _chars(shot.get("title")) < 2:
                errs.append(f"第 {i} 镜是 text 拍，标题不能为空")
            if _shot_is_3d(shot):
                errs.append(f"第 {i} 镜是 text 拍，不能同时写 stage3d")
        else:
            if fp not in {"left", "center", "right", "whole"}:
                errs.append(f"第 {i} 镜缺 focus_panel（left/center/right/whole）")
            if tz not in {"left", "right", "top", "bottom"}:
                errs.append(f"第 {i} 镜缺 title_zone（left/right/top/bottom）")
            if _shot_is_3d(shot):
                from .scripts.stage3d import DEVICE_ALIAS
                st = shot.get("stage3d") or {}
                dev = DEVICE_ALIAS.get(str(st.get("device") or "").strip().lower(), "")
                act = str(st.get("action") or "").strip().lower()
                if not dev:
                    errs.append(
                        f"第 {i} 镜 stage3d.device 只能是 laptop 或 phone："
                        f"**产品本身不是手机/笔记本、界面上也不出现这两种设备时，不要写 stage3d**，"
                        f"改用普通界面镜头（ui 拍）或纯文字拍")
                if act not in {"open", "scroll", "push", "tilt", "static"}:
                    errs.append(f"第 {i} 镜 stage3d.action 不在 open/scroll/push/tilt/static 里")
                if act == "open" and dev != "laptop":
                    errs.append(f"第 {i} 镜只有笔记本能写 action=open（开盖）")
                if not str(st.get("page") or "").strip():
                    errs.append(f"第 {i} 镜 stage3d 缺 page：屏幕上到底显示什么")
                if dev == "laptop" and tz not in {"top", "bottom"}:
                    errs.append(f"第 {i} 镜 3D 笔记本几乎占满画面，标题只能放 top 或 bottom")
                for key, lo, hi in (("azimuth", -78.0, 78.0), ("elevation", -6.0, 46.0)):
                    if st.get(key) in (None, ""):
                        continue
                    try:
                        v = float(st.get(key))
                    except (TypeError, ValueError):
                        errs.append(f"第 {i} 镜 stage3d.{key} 不是数字")
                        continue
                    if not (lo <= v <= hi):
                        errs.append(f"第 {i} 镜 stage3d.{key}={v} 超出范围（{lo:.0f}~{hi:.0f}）")
            elif not str(shot.get("ui_surface") or "").strip():
                errs.append(f"第 {i} 镜缺 ui_surface：同一块界面用同一个标识，换界面就换标识")
            if fp and tz:
                if fp == tz:
                    errs.append(f"第 {i} 镜标题区和主展示区都在 {tz}，会挡住内容，请换一侧")
                elif fp == "whole" and tz not in {"top", "bottom"}:
                    errs.append(f"第 {i} 镜 focus 是整窗，标题只能用 top/bottom 留白带")
        if mode == "bgm":
            if i > 1 and downbeats and min(abs(s - b) for b in downbeats) > 0.12:
                errs.append(f"第 {i} 镜起点 {s:.2f}s 没落在小节线上（最近 {_nearest(downbeats, s):.2f}s）")
            kick, title, sub = (_chars(shot.get("kicker")), _chars(shot.get("title")),
                                _chars(shot.get("sub")))
            if kick + title + sub < 4:
                errs.append(f"第 {i} 镜没有文字（bgm 分流靠文字叙事）")
            # 阅读预算：大标题按展示字计（0.09s/字），小字标签更快（0.05），副标居中（0.12）
            budget = 0.9 + 0.05 * kick + 0.09 * title + 0.12 * sub
            if budget > (e - s) + 1e-6:
                errs.append(f"第 {i} 镜文字需要 {budget:.1f}s，但只有 {e - s:.1f}s，请砍字")
            # 镜头时长不按段落标签硬卡：切点网格本身就是按段落密度生成的，
            # 两个相邻切点之间可能隔着 4~5 秒（那段音乐没有可用强拍），
            # 再拿"段落建议时长"卡它就会自相矛盾、怎么改都过不了。
            # 真正要防的是"镜头太粗、跳过了大量可用切点"，用切点使用率来判。
            if grid and i > 1 and min(abs(s - b) for b in grid) <= 0.12:
                used_marks += 1
        else:
            if _chars(shot.get("narration")) < 4:
                errs.append(f"第 {i} 镜缺旁白句子（vo 分流每镜都要有）")
    s3d_idx = [i for i, s in enumerate(shots) if _shot_is_3d(s)]
    if s3d_idx:
        limit_3d = max(2, int(round(len(shots) * 0.5)))
        if len(s3d_idx) > limit_3d:
            errs.append(f"3D 镜头 {len(s3d_idx)} 个，超过全片一半（{len(shots)} 镜最多 {limit_3d} 个）："
                        f"3D 只用来强调设备与真实屏显，其余用界面演示")
        if s3d_idx[-1] - s3d_idx[0] + 1 != len(s3d_idx):
            errs.append("3D 镜头必须连续排布（中间不要夹 HTML 镜头），否则要拆成多段单独渲染")
        run = best = 1
        for a, b in zip(s3d_idx, s3d_idx[1:]):
            run = run + 1 if b == a + 1 else 1
            best = max(best, run)
        if best > 3:
            errs.append(f"连续 3D 镜头 {best} 个，最多 3 个（再多就成了产品广告片，不是功能演示）")
        # 相邻 3D 镜头机位必须真的有差别：否则两镜画面几乎一样，观众会以为同一张图放了两遍
        for a, b in zip(s3d_idx, s3d_idx[1:]):
            if b != a + 1:
                continue
            az1, el1 = _shot_azel(shots[a])
            az2, el2 = _shot_azel(shots[b])
            if abs(az1 - az2) < 18 and abs(el1 - el2) < 10:
                errs.append(
                    f"第 {a + 1}、{b + 1} 镜是连续的 3D 镜头但机位几乎相同"
                    f"（方位差 {abs(az1 - az2):.0f}°、仰角差 {abs(el1 - el2):.0f}°）："
                    f"方位至少差 18°，或仰角差 10° 以上，两镜才看得出区别")
    if len(shots) >= 3:
        # 只校验"有没有变化"，不校验具体用哪种排版：风格库写在提示词里，由导演自由发挥
        styles = [str(s.get("title_style") or "").strip() for s in shots]
        if any(not x for x in styles):
            errs.append("有镜头没写 title_style（这一镜的标题排版方案）")
        else:
            if len(set(styles)) < 3:
                errs.append(f"标题排版只有 {len(set(styles))} 种，全片至少 3 种不同处理")
            for i in range(1, len(styles)):
                if styles[i] == styles[i - 1]:
                    errs.append(f"第 {i + 1} 镜与上一镜标题排版完全相同，请换一种")
    if duration >= 10 and len(shots) >= 4:
        beats = [str(s.get("beat_type") or "ui").strip().lower() for s in shots]
        if "text" not in beats:
            errs.append("全片都是 UI 演示：至少要有 1 个纯文字拍（先说清这次更新了什么）")
    if mode == "bgm" and len(grid) >= 3:
        # 防止"镜头太粗"：跳过太多可用切点会让整片节奏拖沓。
        # 只统计成片实际覆盖的时间窗内的切点——内容决定片长，不能拿整曲网格要求用满，
        # 否则等于逼模型把内容注水拉长到整曲长度。
        in_span = [g for g in grid if g < prev_end - 0.5]
        if len(in_span) >= 3:
            need = max(2, int(round(len(in_span) * 0.6)))
            if used_marks < need:
                errs.append(f"只用了 {used_marks} 个可用切点（本片时间窗内共 {len(in_span)} 个）："
                            f"镜头太粗，至少要用到 {need} 个，让切镜跟住音乐")
    # 不校验"镜头是否铺满目标时长"：成片长度由蓝图内容决定（最后一镜结束即成片长度），
    # 目标时长只是参考上限。否则模型会为了凑满配额把同一内容重复一遍。
    return errs[:8]


def _nearest(values, target: float) -> float:
    return min(values, key=lambda v: abs(v - target)) if values else target


def _suggest_beats(n: int) -> list[str]:
    """按镜头数给一条"文字拍/界面拍"的建议序列：首尾是文字，中间每三镜插一个文字拍。"""
    if n <= 0:
        return []
    out = []
    for i in range(n):
        if i == 0 or i == n - 1:
            out.append("text")
        elif n >= 5 and i % 3 == 2:
            out.append("text")
        else:
            out.append("ui")
    for i in range(2, n):
        if out[i] == out[i - 1] == out[i - 2] == "ui":
            out[i] = "text"
    return out


def _rebalance_beats(plan: dict) -> dict:
    """最后一招：如果只是因为"全片都是 UI"被打回，机械地把首尾改成文字拍再试一次。"""
    shots = plan.get("shots") or []
    if len(shots) < 3:
        return plan
    pattern = _suggest_beats(len(shots))
    for shot, beat in zip(shots, pattern):
        if str(shot.get("beat_type") or "ui").lower() != "text" and beat == "text":
            shot["beat_type"] = "text"
    return plan


def _cut_grid(rhythm: dict, duration: float, min_shot: float = 1.6) -> list:
    """按音乐密度给切点：快段一小节一切，慢段两小节一切。

    背景：固定"每镜 2.5–4s"会让快歌显得拖、慢歌显得赶。这里按能量分段
    （low=8 拍/镜、mid=6 拍、high=4 拍）反推每段该多长，再从小节线里挑安全切点。
    """
    if duration <= 0:
        return []
    targets = _shot_targets(rhythm)
    bars = sorted(float(b) for b in (rhythm.get("downbeats") or [])
                  if 0.0 < float(b) < duration - 1.2)
    grid, last = [], 0.0
    for b in bars:
        level = _level_at(rhythm, b)
        gap = max(min_shot, targets.get(level, 3.0) * 0.9)
        if b - last >= gap:
            grid.append(round(b, 3))
            last = b
    return grid


def _shot_targets(rhythm: dict) -> dict:
    """每种能量段落的建议单镜时长（秒）：low 8 拍 / mid 6 拍 / high 4 拍。"""
    beat = float(rhythm.get("beat_interval") or 0.5) or 0.5
    return {"low": round(8 * beat, 2), "mid": round(6 * beat, 2), "high": round(4 * beat, 2)}


def _shots_within(rhythm: dict, window: float) -> int:
    """按节奏密度估算 window 秒内大约能切几镜——只用来给蓝图一个规模感，不是配额。"""
    if window <= 0:
        return 0
    targets = _shot_targets(rhythm)
    total = 0.0
    for s in rhythm.get("sections") or []:
        try:
            a = max(0.0, float(s["start"]))
            b = min(float(s["end"]), window)
        except (KeyError, TypeError, ValueError):
            continue
        if b > a:
            lvl = str(s.get("level") or "mid")
            total += (b - a) / max(0.8, float(targets.get(lvl, 3.0)))
    return int(round(total))


def _level_at(rhythm: dict, t: float) -> str:
    for s in rhythm.get("sections") or []:
        try:
            if float(s["start"]) <= t < float(s["end"]):
                return str(s.get("level") or "mid")
        except (KeyError, TypeError, ValueError):
            continue
    return "mid"


def _slice_grid(rhythm: dict, start: float, end: float) -> dict:
    bars = [float(b) for b in (rhythm.get("downbeats") or []) if start - 0.05 <= float(b) < end]
    return {"bpm": rhythm.get("bpm"), "downbeats": [round(b - start, 3) for b in bars]}


def _window_energy(rhythm: dict, start: float, dur: float) -> float:
    """窗口内的平均能量（按段落能量加权）；用来判断哪一段节奏最密集。"""
    sections = rhythm.get("sections") or []
    if not sections:
        return 0.0
    end = start + dur
    total = 0.0
    for s in sections:
        a = max(float(s.get("start") or 0), start)
        b = min(float(s.get("end") or 0), end)
        if b > a:
            total += (b - a) * float(s.get("energy") or 0)
    return total / max(0.1, dur)


def _pick_window(rhythm: dict, target: float, full: float) -> float:
    """在整曲里挑 target 秒的起点：能量最高的一段，优先落在小节首拍、含 drop。"""
    target = min(float(target), float(full))
    latest = max(0.0, float(full) - target)
    starts = [float(b) for b in (rhythm.get("downbeats") or []) if 0.0 <= float(b) <= latest]
    if not starts:
        starts = [round(i * 0.5, 2) for i in range(int(latest / 0.5) + 1)]
    drops = [float(d.get("t") or 0) for d in (rhythm.get("drops") or []) if isinstance(d, dict)]
    best, best_score = 0.0, -1.0
    for start in starts:
        score = _window_energy(rhythm, start, target)
        score += 0.06 * sum(1 for t in drops if start <= t < start + target)
        if score > best_score:
            best, best_score = start, score
    return round(best, 3)


def _cut_audio(src: Path, start: float, dur: float, dst: Path) -> tuple[bool, str]:
    """截取一段音乐，并做短淡入淡出（避免切口爆音）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    fade = min(0.6, max(0.2, dur * 0.03))
    af = (f"afade=t=in:st=0:d=0.15,"
          f"afade=t=out:st={max(0.0, dur - fade):.2f}:d={fade:.2f}")
    return _run_ffmpeg(["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
                        "-af", af, "-c:a", "libmp3lame", "-q:a", "2", str(dst)])


def _split_segments(plan: dict, limit: float) -> list[dict]:
    """按镜头边界切段，单段不超过 limit 秒（控制在一次 LLM 能写稳的体量）。

    3D 拍与 HTML 拍**必须分段**：前者整段交给 Blender 渲染，后者交给 HyperFrames，
    两者不能塞进同一个渲染单元里。
    """
    shots = plan["shots"]
    segments, cur = [], []
    for shot in shots:
        if cur and (_shot_is_3d(shot) != _shot_is_3d(cur[0])
                    or float(shot["end"]) - float(cur[0]["start"]) > limit):
            segments.append({"start": float(cur[0]["start"]), "end": float(cur[-1]["end"]),
                             "shots": cur})
            cur = []
        cur.append(shot)
    if cur:
        segments.append({"start": float(cur[0]["start"]), "end": float(cur[-1]["end"]),
                         "shots": cur})
    return segments


def _shot_surface(shot: dict) -> str:
    """这一镜展示的是产品的哪块界面（由导演命名；纯文字拍与 3D 拍为空）。"""
    if str(shot.get("beat_type") or "") == "text":
        return ""
    if _shot_is_3d(shot):
        return ""
    return str(shot.get("ui_surface") or "").strip()


def _shot_is_3d(shot: dict) -> bool:
    """这一镜是否走 3D 设备镜头（蓝图里给了 stage3d）。"""
    st = shot.get("stage3d")
    return isinstance(st, dict) and bool(st)


def _segment_is_3d(seg: dict) -> bool:
    shots = seg.get("shots") or []
    return bool(shots) and _shot_is_3d(shots[0])


def _shot_azel(shot: dict) -> tuple[float, float]:
    """这一镜 3D 机位的（方位角, 仰角）。与渲染侧共用同一套归一化，避免校验与实拍不一致。"""
    from .scripts.stage3d import spec_of
    spec = spec_of(shot)
    return (spec["azimuth"], spec["elevation"]) if spec else (0.0, 0.0)


def _s3d_version() -> str:
    """3D 管线指纹：改了 stage3d 的实现，旧片段自动重渲。"""
    p = Path(__file__).resolve().parent / "scripts" / "stage3d.py"
    try:
        return hashlib.md5(p.read_bytes()).hexdigest()[:8]
    except OSError:
        return "s3d"


def _segment_surfaces(seg: dict) -> list[str]:
    """本段出现的界面标识（去重、保持出现顺序）。"""
    out: list[str] = []
    for shot in (seg.get("shots") or []):
        name = _shot_surface(shot)
        if name and name not in out:
            out.append(name)
    return out


_OVERLAP_JS = """() => {
  const vis = el => {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && cs.visibility !== 'hidden' &&
           parseFloat(cs.opacity || '1') > 0.05 && cs.display !== 'none';
  };
  const opacityOf = el => {
    let o = 1, n = el;
    while (n && n !== document.documentElement) {
      o *= parseFloat(getComputedStyle(n).opacity || '1');
      n = n.parentElement;
    }
    return o;
  };
  const textRect = el => {
    try {
      const r = document.createRange();
      r.selectNodeContents(el);
      const rects = [...r.getClientRects()].filter(x => x.width > 1 && x.height > 1);
      if (!rects.length) return el.getBoundingClientRect();
      return {
        left: Math.min(...rects.map(x => x.left)), top: Math.min(...rects.map(x => x.top)),
        right: Math.max(...rects.map(x => x.right)), bottom: Math.max(...rects.map(x => x.bottom))
      };
    } catch (e) { return el.getBoundingClientRect(); }
  };
  const inter = (a, b) =>
    Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
    Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const titles = [...document.querySelectorAll('[data-title]')].filter(vis);
  // 整窗压暗的落版镜不算"正在展示"，不能按遮挡处理
  const focus = [...document.querySelectorAll('[data-focus]')].filter(
    el => vis(el) && opacityOf(el) >= 0.4);
  let worst = 0, outside = false;
  for (const t of titles) {
    const r = textRect(t);
    const w = r.right - r.left, h = r.bottom - r.top;
    if (w < 4 || h < 4) continue;
    if (r.left < 48 || r.top < 48 || r.right > innerWidth - 48 || r.bottom > innerHeight - 48) {
      outside = true;
    }
    for (const f of focus) {
      const ia = inter(r, f.getBoundingClientRect());
      if (ia > 0) worst = Math.max(worst, ia / Math.max(1, w * h));
    }
  }
  return {titles: titles.length, worst, outside};
}"""


def _title_overlap_issues(proj: Path, shots: list, seg_start: float,
                          width: int, height: int) -> list[str]:
    """实测每个镜头里标题块与主展示区是否重叠（量 data-title 与 data-focus 的矩形）。

    不猜模型"觉得"标题放哪：直接在同一时刻截图前量几何。重叠超过 15% 就算挡住内容。
    """
    import asyncio

    from skills.opendesign.scripts.gate import PLAY_ARGS, _READY_JS, _seek
    from playwright.async_api import async_playwright

    html_path = (Path(proj) / "index.html").resolve()

    async def _run() -> list[str]:
        issues: list[str] = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=PLAY_ARGS)
            page = await browser.new_page(viewport={"width": width, "height": height})
            try:
                await page.goto(html_path.as_uri(), wait_until="load")
                await page.wait_for_function(_READY_JS, timeout=20000)
                for idx, shot in enumerate(shots, 1):
                    s = float(shot["start"]) - seg_start
                    e = float(shot["end"]) - seg_start
                    if e <= 0:
                        continue
                    t = max(0.0, s + (e - s) * 0.55)
                    if t >= e - 0.05:
                        continue
                    await _seek(page, t)
                    data = await page.evaluate(_OVERLAP_JS) or {}
                    if not data.get("titles"):
                        issues.append(f"第 {idx} 镜没有 data-title 标记的标题块")
                        continue
                    if float(data.get("worst") or 0) > 0.15:
                        issues.append(f"第 {idx} 镜标题压住主展示区（重叠 {float(data['worst']) * 100:.0f}%）")
                    if data.get("outside"):
                        issues.append(f"第 {idx} 镜标题超出画布安全边距")
            finally:
                await browser.close()
        return issues

    try:
        return asyncio.run(_run())
    except Exception:
        return []          # 浏览器/环境异常不阻塞出片


def _copy_ui_assets(proj: Path, ui: dict | None) -> None:
    """把抽取出的真实资源（logo/图标/截图）拷进本段工程，画面才能 <img src="assets/…">。"""
    src = (ui or {}).get("assets_dir") or ""
    if not src:
        return
    src_dir = Path(src)
    if not src_dir.is_dir():
        return
    dst = proj / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file():
            try:
                shutil.copy2(f, dst / f.name)
            except OSError:
                pass


def _image_files(roots: list[Path]) -> list[Path]:
    """收集 ui_source 里的截图，按文件大小降序（大的通常是主界面）。"""
    imgs: list[Path] = []
    for root in roots:
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for p in files:
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                imgs.append(p)
    imgs.sort(key=lambda p: p.stat().st_size, reverse=True)
    return imgs


_SHOT_DESC_PROMPT = (
    "把这张产品截图转写成「可以照着用 HTML/CSS 重建界面」的结构化规格。"
    "只写截图里看得见的内容，看不清就写「看不清」，不要推测或补全。按下面条目输出：\n"
    "1) 画布与整体：比例、背景基调、是否有外框/圆角/阴影；\n"
    "2) 布局分区：从左到右、从上到下的区块，写清每个区块的宽度占比与相对位置"
    "（例如 左侧栏 26% / 中间主区 48% / 右侧栏 26%），是否有标题栏与底部状态栏；\n"
    "3) 每个区块里的控件：按钮、输入框、标签页、列表项、卡片、图标——数量、形状、相对位置；\n"
    "4) 配色：主色、背景色、文字色（能判断就给近似十六进制）、分隔线、强调色；\n"
    "5) 字体层级：标题/正文/辅助文字的大致字号比例与字重；\n"
    "6) 可见文案：把能读到的文字按区块原样列出；\n"
    "7) 视觉风格关键词：如深色、毛玻璃、细描边、单色图标。\n"
    "中文条目式，600 字以内，不要寒暄。"
)


def _describe_shots(images: list[Path], llm_config: dict | None,
                    limit: int = 3) -> list[tuple[str, str]]:
    """用主 LLM 的读图链路把截图转成文字规格（作画的是纯文本模型，看不到图）。"""
    from skills.image_reader import describe_image_b64

    out: list[tuple[str, str]] = []
    for p in images[:limit]:
        try:
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            mime = "image/jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            desc = describe_image_b64(b64, mime, _SHOT_DESC_PROMPT, llm_config or {})
        except Exception as e:  # 读图不可用不该阻断出片，退化成自由还原
            desc = f"（读图失败：{e}）"
        out.append((p.name, (desc or "").strip()[:1400]))
    return out


def _shots_context(roots: list[Path], out_dir: Path, llm_config: dict | None = None) -> dict:
    """只有截图时：先把截图转写成界面规格文字，再让模型照着描述重建界面。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    images = _image_files(roots)
    described = _describe_shots(images, llm_config)

    lines = [
        "# UI 参照（没有前端源码，依据截图转写的文字规格）",
        "下面是产品截图转写出来的界面规格（是文字，不是图片）。用 div/CSS 按这些描述重建界面："
        "栏位比例、控件形状、配色、文字层级都要对得上；不要自创品牌色与图标。",
        "**截图不能当背景铺满画面**：界面必须用 DOM 重建，否则一推镜就露馅。",
    ]
    for i, (name, desc) in enumerate(described, 1):
        lines += ["", f"## 截图 {i}（{name}）", desc or "（没有描述）"]
    if not described:
        lines += ["", "没有可用的截图（或读图不可用）：按分镜里的界面动作与 brief 自由还原，"
                      "不要声称照抄了截图。"]

    digest = "\n".join(lines)
    (out_dir / "ui-digest.md").write_text(digest, encoding="utf-8")
    (out_dir / "ui-tokens.css").write_text("", encoding="utf-8")
    ok = sum(1 for _, d in described if not d.startswith("（读图失败"))
    # 截图本身不进工程：这里要的是重建，不是贴图
    return {"digest": digest, "tokens_css": "", "assets_dir": "", "assets": [],
            "files": len(images), "tokens": 0, "components": 0, "skeleton": [],
            "mode": "shots", "shots": ok}


def _sanitize_html(html: str, duration: float, width: int, height: int,
                   extra_css: str = "") -> str:
    """补齐 HyperFrames 的样板契约（这些是格式约定，不是创作内容，交给模型反复改很浪费）。

    - 根元素必须有 data-composition-id="root" / data-duration / data-width / data-height
    - 根与舞台必须 overflow:hidden（否则渲染会露出画布外的元素）
    """
    attrs = {
        "data-composition-id": "root",
        "data-duration": f"{duration:.3f}",
        "data-width": str(width),
        "data-height": str(height),
        "data-start": "0",
    }
    m = re.search(r"<div\b[^>]*\bid=\"root\"[^>]*>", html)
    if m:
        tag = m.group(0)
        for key, val in attrs.items():
            if re.search(rf'{key}="', tag):
                tag = re.sub(rf'{key}="[^"]*"', f'{key}="{val}"', tag)
            else:
                tag = tag[:-1].rstrip() + f' {key}="{val}">'
        html = html[:m.start()] + tag + html[m.end():]

    guard_css = "#root,.stage,[data-composition-id]{overflow:hidden !important}"
    if extra_css:
        # 真实设计变量必须比模型写的样式更晚生效，直接放在守卫样式后面
        guard_css += "\n" + extra_css
    guard = f"<style>{guard_css}</style>"
    if "</head>" in html:
        html = html.replace("</head>", guard + "</head>", 1)
    else:
        html = html.replace("<body", guard + "<body", 1)
    # CSS transition 依赖墙钟：逐帧 seek 时同一时刻会算出不同中间值，直接去掉
    html = re.sub(r"transition(?:-[a-z]+)?\s*:[^;}\n]*;?", "", html)
    return html


def _run_ffmpeg(args: list[str]) -> tuple[bool, str]:
    cmd = ["ffmpeg", "-y", "-v", "error"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    except Exception as e:
        return False, str(e)
    if r.returncode != 0:
        return False, " ".join(((r.stderr or r.stdout or "").splitlines())[-4:])
    return True, ""


def _concat(parts: list[Path], dst: Path) -> tuple[bool, str]:
    listing = dst.parent / "concat.txt"
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    return _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                        "-c", "copy", str(dst)])


__all__ = ["ProductDirectorTool"]
