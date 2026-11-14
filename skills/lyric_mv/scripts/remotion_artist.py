# -*- coding: utf-8 -*-
"""开放模式 · 两段式：先出「可摆动作的角色」（关节 + 视角 + 表情）并通过参数网格验收，再逐镜拍。

与 remotion_scenes 的区别（刻意为之）：
  - 不给 API 白名单、不限定每镜多少行、不分批；
  - 只保留 4 条交付契约（组件形态 / 时间来源 / 歌词层归引擎 / 确定性）；
  - 角色阶段把同一个角色的五种参数组合（正面/侧面/背面/坐姿伸手/倾斜头晕）渲成一张网格，
    由视觉模型判定「参数有没有真的接上、每个姿态能不能读成人」，不通过只重画角色；
  - 镜头阶段**一镜一过闸门**：每画完一镜立刻真渲一帧（strict），崩了当场带着报错重画，
    不再等 39 镜凑齐后一次性判坏；通过后静帧留在 art/shots/shot-N.png。

用法：
  python remotion_artist.py --work <out_dir> --rounds 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from tsx_exports import has_named_export as _has_named_export

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parents[1] / "remotion_runtime"
GENERATED = RUNTIME / "src/scenes/generated"
REGISTRY = RUNTIME / "src/scenes/registry.ts"
CHAR_REG = RUNTIME / "src/scenes/charRegistry.tsx"
RENDER = RUNTIME / "scripts/render_mv.py"

SHOT_SYSTEM = """你是一位动画美术导演，用 Remotion 画 MV 的一个镜头。

## 可用素材（用不用、怎么用、用哪个角度，你定）
{CAST_BLOCK}
  每个角色组件都支持这些参数：

  | 参数 | 取值 | 用途 |
  |---|---|---|
  | `view` | `front` / `side` / `back` | 角度：要情绪给正面，要方向给侧面，离开才用背面 |
  | `pose` | `stand` / `sit` | 站 / 坐（桌前、地面都可用坐姿） |
  | `armL` / `armR` | 度数，或 `[手x, 手y]` | 度数：0 = 自然下垂，正值向外张开；也可直接给手的位置（本地坐标，脚底 y=0） |
  | `headTurn` | 度数 | 转头看屏幕 / 看人 |
  | `tilt` | 度数 | 身体倾斜（头晕、疲惫、倚靠） |
  | `mood` | `calm` / `tired` / `surprised` / `dizzy` / `happy` / `worried` | 表情 |

  **要什么动作就调参数，不要自己拼人体**：不要用 rect / path 另画一条手臂、一个头。
  同一镜里的人物只能来自上面列出的角色组件，否则比例和连接处一定崩。

- 可选放置器（只是工具，不是必须）：

```tsx
import {Actor} from '../../ui/Actor';
<Actor Character={Hero} x={820} y={980} s={1.15} flip />
```

  `x/y` 是脚底画布坐标，`s` 是缩放（1 ≈ 470px 高）。它只在「头被歌词压住」时让位，其余不管你。
  不想用就直接 `<g transform={...}><Hero /></g>`。

**人、镜头、谁挡住谁，都是你的镜头语言**：这一镜不需要人就别画；要让标题/黑场/前景座椅盖住人，
就把人画在那些图元**之前**。没有人会替你强加图层顺序。

## 你的工作方式
1. 场景自己设计、自己画；推镜、人物、前中后景都在你自己的 SVG 图层里安排。
2. 写完先自己过一遍这一帧的构图；引擎会立刻真渲一帧，崩了会把报错原文回灌给你。
3. 不要为了"过检查"简化画面。
4. **相邻镜不许同一个画面**：拿到上一镜的镜头信息后，景别 / 机位 / 主体 / 动作至少换一项；
   编导给了这一镜的景别或机位，就按它拍。
5. 认为可以交付时，最后单独一行写：<DONE>

## 交付契约（只拦「一定会静默出事」的）
1. 导出 `{EXPORT}`（`export const {EXPORT}` 或 `export function {EXPORT}` 均可）、
   `export const BG = '#rrggbb';` 和 `export const META = {META_ID: {bg: '#rrggbb'}};`
   （`META` 的键必须是 `{META_ID}`，引擎靠它取底色决定歌词用浅字还是深字）
2. **整个镜头就是一个 `<svg viewBox="0 0 1920 1080">`**；所有图元都放在它里面。
   **禁止**在这些文件里使用 HTML 标签（`<div>`/`<span>`/`AbsoluteFill`）：它们嵌在 SVG 里不会被渲染，
   画面会静默丢内容。需要滤镜就用 `<filter>` + `<g filter="url(#myFilter)">`（滤镜区域给足，别把内容裁掉）。
3. 时间只从 `const e = useE();` 的 `e.t` / `e.shotU` 读（秒），不用外部时钟。
   `e.shotT` 是本镜内已过秒数（从 0 开始），`e.shotU` 是本镜 0~1 进度。
4. 不画歌词字幕（引擎画），主体尽量避开 `e.lyricBox`（1280×720 坐标系元组 `[x0,y0,x1,y1]`；
   也可以用对象形式 `e.lyricRect`，含 `x0,y0,x1,y1,w,h`）。
5. 确定性：同帧同像素；禁止随机数/时间戳/定时器/网络/外链图片。

## 环境
画布 1920×1080，30fps。`useE()` 来自 `'../../engine/context'`，字段：
`t, dt, W, H, i, n, line{text,start,end,chars}, hasLine, kind, u, cardT, shotU, shotT, shotDur,
 beat, beatIdx, bar, phase, strong, pulse(k), hit(n), P, hexA(c,a), isDark(c), rnd(seed), hash(seed),
 lerp(a,b,t), clamp(v,a,b), clamp01(v), seg(a,b,v), easeOut(x), easeIn(x), easeIO(x), back(x), elastic(x), wave(x), lyricBox`

只输出一个 TSX 文件（可带围栏），不要解释。
"""


def _log(msg: str) -> None:
    print(f"[artist] {msg}", flush=True)


def _run(cmd: str, cwd: Path, timeout: int = 1200) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _clean(txt: str) -> str:
    m = re.search(r"```(?:tsx|ts|jsx)?\s*(.*?)```", txt or "", re.S)
    return (m.group(1) if m else (txt or "")).strip()


def _sync_char() -> None:
    """按 char-hero.tsx 实际导出的姿态写注册表（与 styled 共用同一实现）。"""
    from skills.remotion_runtime.character_module import sync_char_registry
    sync_char_registry(RUNTIME / "src")


def _still(w: Path, t: float, dst: Path) -> tuple[bool, str]:
    r = _run(f'"{sys.executable}" "{RENDER}" "{w}" --still {t:.3f} --strict', RUNTIME, timeout=900)
    produced = w / f"still-{t:.2f}.png"
    if r.returncode != 0 or not produced.exists():
        return False, "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-12:])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(produced.read_bytes())
    return True, ""


def _sheet(w: Path, who: str, dst: Path) -> tuple[bool, str]:
    r = _run(f'"{sys.executable}" "{RENDER}" "{w}" --sheet {who} --sheet-out "{dst}"',
             RUNTIME, timeout=900)
    if r.returncode != 0 or not dst.exists():
        return False, "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-12:])
    return True, ""


SHOT_REVIEW = """这是 MV 的一个镜头。先在第一行给出结论：`VERDICT: PASS` 或 `VERDICT: FAIL`。
PASS 的标准：人物一眼读成人、主体清楚、没有穿帮、层次和光成立、没被歌词压住。
之后用 2~5 条**能直接改代码**的意见说明问题（每条一句话，指出具体位置/部件/数值）。"""



def _bible_excerpt(bible: str, section: str, limit: int = 1400) -> str:
    """只截与当前段落/角色相关的部分，避免每镜都塞整篇圣经。"""
    if not bible:
        return ""
    text = bible
    try:
        doc = json.loads(bible)
        keep = {}
        if isinstance(doc, dict):
            for k in ("protagonist", "character", "cast", "motifs", "composition", "motion"):
                if k in doc:
                    keep[k] = doc[k]
            for k in ("paletteArc", "locations", "continuity", "stage"):
                v = doc.get(k)
                if isinstance(v, list):
                    hit = [x for x in v if section and section in json.dumps(x, ensure_ascii=False)]
                    keep[k] = hit or v[:2]
                elif v is not None:
                    keep[k] = v
        text = json.dumps(keep or doc, ensure_ascii=False)
    except Exception:
        pass
    return text[:limit]




# 镜头缓存指纹的版本号：画面契约/取景方式变了就 +1，强制所有旧缓存失效
SHOT_SIG_VERSION = "4"


def _shot_sig(tl: dict, plan: dict, bible: str, w0: dict, brief: str, char_sha: str,
              prev: str = "") -> str:
    """这一镜「该画成什么样」的指纹。

    时间窗、覆盖的歌词、编导对这一镜的要求（景别/机位/主体/动作/与上镜差异）、
    编导方案、视觉圣经、用户要求、定妆参数、上一镜的镜头摘要，
    任何一项变了都必须重画；全部没变才允许复用上次的镜头文件。
    """
    lines = tl.get("lines") or []
    idxs = [i for i in (w0.get("lines") or []) if 0 <= i < len(lines)]
    doc = {
        "v": SHOT_SIG_VERSION,
        "win": [round(float(w0.get("start") or 0), 3), round(float(w0.get("end") or 0), 3)],
        "section": w0.get("section") or "",
        "brief": w0.get("brief") or "",
        "size": w0.get("size") or "",
        "camera": w0.get("camera") or "",
        "subject": w0.get("subject") or "",
        "change": w0.get("change") or "",
        "cast": w0.get("cast") or [],
        "prev": prev or "",
        "lines": [{"text": lines[i].get("text") or "",
                   "start": round(float(lines[i].get("start") or 0), 3),
                   "end": round(float(lines[i].get("end") or 0), 3)} for i in idxs],
        "plan": json.dumps(plan, ensure_ascii=False, sort_keys=True)[:4000],
        "bible": _bible_excerpt(bible, str(w0.get("section") or "")),
        "user": brief or "",
        "char": char_sha or "",
    }
    return hashlib.sha1(json.dumps(doc, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def character_sources(w: Path) -> list[dict]:
    """整组定妆角色的来源：characters.json 优先，其次单个 character.json / 环境变量。

    返回 [{"role": "hero", "spec": {...}}, ...]；hero 一定排第一。
    """
    from skills.remotion_runtime.character_module import role_slug

    env = os.environ.get("LYRIC_MV_CHARACTER", "").strip()
    if env:
        p = Path(env)
        p = p if p.is_absolute() else (Path.cwd() / p).resolve()
        candidates = [p.parent / "characters.json", p]
    else:
        candidates = [w / "art" / "characters.json", w / "art" / "character.json"]

    for p in candidates:
        if not p.exists():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if isinstance(doc, dict) and isinstance(doc.get("characters"), list):
            out = []
            for i, c in enumerate(doc["characters"]):
                if not isinstance(c, dict):
                    continue
                spec = c.get("spec") if isinstance(c.get("spec"), dict) else c
                if not isinstance(spec, dict) or not spec:
                    continue
                role = role_slug(c.get("role") or spec.get("name"),
                                 "hero" if i == 0 else f"friend-{i}")
                out.append({"role": role, "spec": spec})
            if out:
                return out
        if isinstance(doc, dict) and isinstance(doc.get("proportions"), dict):
            return [{"role": "hero", "spec": doc}]
    return []


def _char_module(spec: dict) -> str:
    from skills.remotion_runtime.character_module import character_module
    return character_module(spec, "../../ui/RigCharacter")


def _cast_sha(chars: list[dict]) -> str:
    """整组定妆的指纹：任一角色的参数变了都要重画镜头。"""
    return hashlib.sha1(json.dumps(chars, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _cast_block(chars: list[dict]) -> str:
    """镜头提示词里的可用角色表：每个角色只能用对应的导出名。"""
    from skills.remotion_runtime.character_module import component_name

    rows, names = [], []
    for i, c in enumerate(chars):
        spec = c["spec"]
        name = component_name(c["role"])
        names.append(name)
        role_label = (f"主角（{c['role']}）" if c["role"] == "hero"
                      else f"配角 {i}（{c['role']}）")
        look = (f"{spec.get('name') or c['role']}：发型 {spec.get('hair') or '?'} / "
                f"服装 {spec.get('outfit') or '?'} / 衣服色 {((spec.get('colors') or {}).get('cloth')) or '?'}")
        rows.append(f"  | `{name}` | {role_label} | {look} |")
    sample = ", ".join(names[:3]) + (", ..." if len(names) > 3 else "")
    return (
        "- 可用角色（都是**用户确认过的定妆资产**，只能用这里列出的组件）：\n\n"
        "  | 导出名 | 角色 | 固定造型 |\n  |---|---|---|\n" + "\n".join(rows) + "\n\n"
        "  ```tsx\n"
        f"  import {{{sample}}} from './char-cast';\n"
        f"  <{names[0]} pose=\"sit\" armL={{30}} armR={{-10}} />\n"
        "  ```\n\n"
        "  每个角色只能用**对应的**导出名，不要把主角组件复制成配角，也不要画没有定妆的人；\n"
        "  这一镜不需要的角色就不要出现。\n"
    )


def phase_character(w: Path, plan: dict, brief: str, cfg: dict, llm, rounds: int = 3) -> tuple[bool, str]:
    """定妆接线：读取用户确认过的整组角色参数，生成角色模块并渲一张对照图存档。"""
    art = w / "art"
    art.mkdir(exist_ok=True)
    chars = character_sources(w)
    if not chars:
        return False, (
            "未定妆：没有找到角色参数。请先调用 character_sheet 让用户在画布上确认角色，"
            "确认后带上 character 参数（video_work/<project>/characters.json）重跑。"
        )

    _atomic_text(art / "characters.json",
                 json.dumps({"characters": chars}, ensure_ascii=False, indent=2))
    hero = next((c["spec"] for c in chars if c["role"] == "hero"), chars[0]["spec"])
    _atomic_text(art / "character.json", json.dumps(hero, ensure_ascii=False, indent=2))

    GENERATED.mkdir(parents=True, exist_ok=True)
    for c in chars:
        (GENERATED / f"char-{c['role']}.tsx").write_text(_char_module(c["spec"]), encoding="utf-8")
    from skills.remotion_runtime.character_module import cast_module
    (GENERATED / "char-cast.tsx").write_text(
        cast_module([c["role"] for c in chars]), encoding="utf-8")
    _sync_char()

    dst = art / "sheet.png"
    ok, err = _sheet(w, ",".join(c["role"] for c in chars), dst)
    if not ok:
        _log("定妆照渲染失败")
        return False, f"定妆照渲染失败：{err}"

    _atomic_text(art / "char-approved.json", json.dumps(
        {"sha": _cast_sha(chars), "at": datetime.now().strftime("%Y-%m-%d %H:%M")},
        ensure_ascii=False))
    return True, str(dst)


def _check_shot(code: str, export: str) -> str:
    """只拦「一定会静默出事」的结构问题，画法与人物取舍交给模型。"""
    bad = []
    if re.search(r"<div\b", code) or "AbsoluteFill" in code:
        bad.append("不要用 <div>/<span>/AbsoluteFill：它们嵌在 SVG 里不会渲染，内容会静默消失；"
                   "整个镜头用一个 <svg>，滤镜用 <filter> + <g filter=...>")
    if "<svg" not in code:
        bad.append("镜头必须有 <svg viewBox=\"0 0 1920 1080\"> 根")
    if not _has_named_export(code, export):
        bad.append(f"必须导出 {export}（export const / export function / export {{ {export} }} 均可）")
    if "export const BG" not in code:
        bad.append("必须导出 BG")
    if "export const META" not in code:
        bad.append("必须导出 META（引擎靠它取底色决定歌词深浅）")
    return "；".join(bad)


# ============================ pipeline 入口 ============================
# 与 remotion_scenes.generate_lines / generate_story 同签名（ok, note, scenes），
# pipeline 在 engine=remotion 时走这里：自动分镜 → 定妆 → 并行拍镜 → 闸门。

DEFAULT_SHOT_SEC = 12.0


def _shot_windows(tl: dict, target: float, story: dict | None = None,
                  shots: list[dict] | None = None) -> list[dict]:
    """分镜表。[{start, end, lines:[idx], section, size, camera, subject, action, change}]
    优先用编导/镜头表给的 shots；否则按「段落边界 + 目标时长」自动切，不依赖歌词关键词。"""
    lines = tl.get("lines") or []
    dur = float(tl.get("duration") or 0)
    if not lines:
        return []

    shots = shots or (story or {}).get("shots") or []
    if shots:
        out = []
        for s in shots:
            a, b = float(s.get("start") or 0), float(s.get("end") or 0)
            if b - a < 0.2:
                continue
            idxs = [i for i, ln in enumerate(lines) if ln["end"] > a and ln["start"] < b]
            # 镜头表没写段落时，按它覆盖的第一句歌词补上
            sec = str(s.get("section") or "")
            if not sec and idxs:
                sec = str(lines[idxs[0]].get("section") or "")
            out.append({
                "start": a, "end": b, "lines": idxs, "section": sec,
                "brief": s.get("action") or s.get("desc") or "",
                "size": s.get("size") or "",
                "camera": s.get("camera") or "",
                "subject": s.get("subject") or "",
                "change": s.get("change") or "",
                "cast": [str(x) for x in (s.get("cast") or []) if str(x).strip()]
                        if isinstance(s.get("cast"), list) else [],
            })
        if out:
            return out

    out: list[dict] = []
    cur: dict | None = None
    for i, ln in enumerate(lines):
        sec = str(ln.get("section") or "")
        if cur is None:
            cur = {"start": ln["start"], "end": ln["end"], "lines": [i], "section": sec}
            continue
        section_changed = bool(sec and cur["section"] and sec != cur["section"])
        # 切点在句首：段落变化 → 立刻切；够长 → 把这句算进本镜再切（避免每镜只有一句）
        if section_changed:
            out.append(cur)
            cur = {"start": ln["start"], "end": ln["end"], "lines": [i], "section": sec}
        elif ln["end"] - cur["start"] >= target:
            cur["end"] = ln["end"]
            cur["lines"].append(i)
            out.append(cur)
            cur = None
        else:
            cur["end"] = ln["end"]
            cur["lines"].append(i)
    if cur:
        out.append(cur)

    # 首尾对齐到全片：开场前奏与尾奏也要有画面
    if out:
        out[0]["start"] = min(out[0]["start"], 0.0)
        if dur > out[-1]["end"]:
            out[-1]["end"] = dur
        for a, b in zip(out, out[1:]):
            a["end"] = b["start"]

    # 超长片段（间奏 / 尾奏没有歌词）按目标时长均分，避免一个镜头里几十秒无事可做
    final: list[dict] = []
    for w0 in out:
        span = w0["end"] - w0["start"]
        n = max(1, min(6, int(span // max(target, 6)))) if span > target * 2 else 1
        if n == 1:
            final.append(w0)
            continue
        step = span / n
        for j in range(n):
            a = w0["start"] + j * step
            b = w0["end"] if j == n - 1 else a + step
            idxs = [i for i in w0["lines"]
                    if lines[i]["start"] >= a - 1e-6 and lines[i]["start"] < b]
            final.append({"start": a, "end": b, "lines": idxs,
                          "section": w0.get("section") or ""})
    return final


def _shot_line(w0: dict) -> str:
    """一镜的镜头语言摘要：景别 / 机位 / 主体 / 动作 / 出场角色 / 与上一镜的差异。"""
    bits = []
    for key, label in (("size", "景别"), ("camera", "机位"),
                       ("subject", "主体"), ("brief", "动作"), ("change", "与上一镜的差异")):
        v = str(w0.get(key) or "").strip()
        if v:
            bits.append(f"{label}：{v}")
    cast = [str(x) for x in (w0.get("cast") or []) if str(x).strip()]
    if cast:
        bits.insert(4, "出场角色：" + "、".join(cast))
    return "；".join(bits)


def _win_ctx(tl: dict, plan: dict, bible: str, wins: list[dict], k: int, brief: str) -> str:
    """第 k 镜（1 基）的完整上下文。"""
    w0 = wins[k - 1]
    lines = tl.get("lines") or []
    idxs = [i for i in w0["lines"] if 0 <= i < len(lines)]
    body = "\n".join(
        f"第 {i} 句（{lines[i]['start']:.2f}~{lines[i]['end']:.2f}s，{lines[i].get('section', '')}）："
        f"「{lines[i]['text']}」\n  逐字：{json.dumps(lines[i].get('chars') or [], ensure_ascii=False)}"
        for i in idxs
    ) or "（这一镜没有歌词，是纯音乐段）"

    prev_txt = ""
    if k > 1:
        p = [i for i in wins[k - 2]["lines"] if 0 <= i < len(lines)]
        p_lyric = f"{lines[p[0]]['text']} … {lines[p[-1]]['text']}" if p else "（纯音乐段）"
        p_shot = _shot_line(wins[k - 2])
        prev_txt = f"\n\n【上一镜】歌词：{p_lyric}" + (f"\n镜头：{p_shot}" if p_shot else "")
    next_txt = ""
    if k < len(wins):
        n = [i for i in wins[k]["lines"] if 0 <= i < len(lines)]
        n_lyric = f"{lines[n[0]]['text']} … {lines[n[-1]]['text']}" if n else "（纯音乐段）"
        n_shot = _shot_line(wins[k])
        next_txt = f"\n【下一镜】歌词：{n_lyric}" + (f"\n镜头：{n_shot}" if n_shot else "")

    shot_brief = ""
    this_shot = _shot_line(w0)
    if this_shot:
        shot_brief = "\n\n【编导对这一镜的要求】\n" + this_shot

    return (
        f"【这一镜】第 {k} 镜 / 共 {len(wins)} 镜\n"
        f"时间 {w0['start']:.2f}~{w0['end']:.2f}s（{w0['end'] - w0['start']:.2f}s）\n"
        f"段落：{w0.get('section') or '（未标注）'}"
        + shot_brief + "\n\n"
        f"【这一镜覆盖的歌词】\n{body}"
        + prev_txt + next_txt
        + f"\n\n【编导方案】\n{json.dumps(plan, ensure_ascii=False)[:4000]}"
        + (f"\n\n【视觉圣经（造型与场景参考，不是出场清单）】\n{bible}" if bible else "")
        + (f"\n\n【用户要求】\n{brief}" if brief else "")
        + "\n\n现在拍这一镜：镜头、主体、前中后景都由你安排（图层顺序就是你的镜头语言）。"
        "\n与上一镜相比，**景别 / 机位 / 主体 / 动作至少换一项**，不要重复上一镜的构图；"
        "编导给了镜头要求就以它为准。"
        "\n主角和配角都是**造型参考**，不是出场要求：这一镜的主体按上面的镜头要求与歌词来定，"
        "纯环境、物体、桌面细节、终端、群像远景都可以没有人；"
        "人物只在剧本确实需要他出现时才画。"
    )


def _manifest_entry(k: int, w0: dict, fname: str) -> dict:
    return {
        "key": f"shot-{k}",
        "file": fname,
        "export": f"Shot{k}",
        "index": k,
        "start": round(w0["start"], 3),
        "end": round(w0["end"], 3),
        "t": round((w0["start"] + w0["end"]) / 2, 3),
    }


def _atomic_text(p: Path, text: str) -> None:
    """原子写：并行拍镜时，别的线程/进程不会读到半个文件。"""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def _write_manifest(parts: Path, manifest: dict) -> None:
    _atomic_text(parts / "registry.json", json.dumps(manifest, ensure_ascii=False, indent=2))


def generate(w: Path, tl: dict, plan: dict, brief: str, cfg: dict, llm, dump_fn,
             mode: str = "performance", story: dict | None = None,
             shots: list[dict] | None = None,
             force: bool = False, workers: int = 4, rounds: int = 2) -> tuple[bool, str, Path | None]:
    """pipeline 的画面段入口。"""
    sys.path.insert(0, str(HERE))
    import remotion_scenes as rs  # noqa: WPS433

    parts = w / "parts"
    parts.mkdir(exist_ok=True)
    art = w / "art"
    shots_dir = art / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)

    target = float(os.environ.get("LYRIC_MV_SHOT_SECONDS", str(DEFAULT_SHOT_SEC)))
    wins = _shot_windows(tl, target, story, shots)
    if not wins:
        return False, "没有歌词行，无法分镜", None
    _log(f"分镜：{len(wins)} 镜（目标 {target:.0f}s/镜，mode={mode}）")

    # 1 定妆：角色是跨镜头的共同资产，来自用户确认过的参数，只接线一次。
    # 复用只看「参数指纹」：参数没改就不重做；参数一改（哪怕只换发色）就重新出图。
    chars = character_sources(w)
    char_file = GENERATED / "char-cast.tsx"
    char_sha = _cast_sha(chars) if chars else ""
    marker = w / "art" / "char-approved.json"
    approved = False
    if char_sha and marker.exists():
        try:
            approved = json.loads(marker.read_text(encoding="utf-8-sig")).get("sha") == char_sha
        except Exception:
            approved = False
    char_ready = bool(char_sha) and approved and char_file.exists()
    redo_char = os.environ.get("LYRIC_MV_CHAR_REDO", "").strip() in ("1", "true", "yes")
    if redo_char or not char_ready:
        if not char_sha:
            return False, (
                "还没有定妆：请先调用 character_sheet，让用户在画布上确认角色，"
                "再把 character 参数传给 lyric_mv。"
            ), None
        ok, sheet = phase_character(w, plan, brief, cfg, llm, int(os.environ.get("LYRIC_MV_CHAR_ROUNDS", "3")))
        if not ok:
            return False, f"定妆接线失败：{sheet}", None
        _log(f"定妆完成：{sheet}")
    else:
        _sync_char()
        _log("复用已确认的角色参数（不重做）")

    bpath = w / "visual-bible.json"
    bible_full = bpath.read_text(encoding="utf-8") if bpath.exists() else ""
    # 镜头提示词只能宣传真实存在的角色，否则会写出 import 不到的名字
    char_final = char_file.read_text(encoding="utf-8") if char_file.exists() else ""
    from skills.remotion_runtime.character_module import component_name
    cast_names = [component_name(c["role"]) for c in chars]
    # char-cast 里每个角色都导出 主组件 / Side / Back；hero 另外兼容旧的 Character*
    cast_exports = set(cast_names) | {n + "Side" for n in cast_names} | {n + "Back" for n in cast_names}
    if any(c["role"] == "hero" for c in chars):
        cast_exports |= {"Character", "CharacterSide", "CharacterBack"}
    cast_block = _cast_block(chars)
    # 定妆指纹：整组参数 + 实际角色模块代码（模块实现升级也应让旧镜头失效）
    char_sig = hashlib.sha1((char_sha + "\n" + char_final).encode("utf-8")).hexdigest()
    manifest: dict = {}
    state = {k: {"code": "", "note": "", "done": False} for k in range(1, len(wins) + 1)}
    lock = threading.Lock()
    tries = max(1, int(os.environ.get("LYRIC_MV_SHOT_TRIES", "2")))

    def register(k: int, code: str, sig: str) -> None:
        with lock:
            _atomic_text(parts / f"artist-shot-{k}.tsx", code)
            _atomic_text(parts / f"artist-shot-{k}.meta.json",
                         json.dumps({"sig": sig}, ensure_ascii=False))
            manifest[f"shot-{k}"] = _manifest_entry(k, wins[k - 1], f"artist-shot-{k}.tsx")
            _write_manifest(parts, manifest)

    def unregister(k: int) -> None:
        with lock:
            manifest.pop(f"shot-{k}", None)
            (parts / f"artist-shot-{k}.tsx").unlink(missing_ok=True)
            (parts / f"artist-shot-{k}.meta.json").unlink(missing_ok=True)
            (GENERATED / f"artist-shot-{k}.tsx").unlink(missing_ok=True)
            _write_manifest(parts, manifest)

    def render_shot(k: int, t: float) -> tuple[bool, str]:
        with lock:
            rs.sync_registry(w, namespace="artist")
            rs._plan_for_gate(w, plan, manifest)
            return _still(w, t, shots_dir / f"shot-{k:02d}.png")

    def validate(k: int, code: str, w0: dict) -> tuple[bool, str]:
        """这一镜现在就真渲一帧（strict）：崩了当场重画，不等到最后 39 镜一起判。"""
        sha = hashlib.sha1(code.encode("utf-8")).hexdigest()
        vp = shots_dir / f"shot-{k:02d}.json"
        if vp.exists():
            try:
                v = json.loads(vp.read_text(encoding="utf-8"))
                if v.get("sha") == sha and v.get("ok"):
                    return True, ""
            except Exception:
                pass
        t = (w0["start"] + w0["end"]) / 2
        ok, err = render_shot(k, t)
        if not ok:
            # 别的镜头文件语法坏了会拖垮整次打包：把被点名的那些镜头放回待画队列。
            others = sorted({int(x) for x in re.findall(r"artist-shot-(\d+)\.tsx", err)
                             if int(x) != k and int(x) in state})
            if others:
                _log(f"  镜 {k}/{len(wins)} 打包被 {others} 的语法错误拖累，已标记重画")
                for j in others:
                    state[j]["code"] = ""
                    state[j]["note"] = "语法错误"
                    unregister(j)
                ok, err = render_shot(k, t)
        if not ok:
            return False, "【这一镜真渲了一帧，崩了；按报错修】\n" + err
        _atomic_text(vp, json.dumps({"sha": sha, "ok": True, "t": round(t, 3)}, ensure_ascii=False))
        return True, ""

    def one(k: int, feedback: str = "") -> tuple[int, str | None, str]:
        w0 = wins[k - 1]
        fname = f"artist-shot-{k}.tsx"
        dst = parts / fname
        sig = _shot_sig(tl, plan, bible_full, w0, brief, char_sig,
                        _shot_line(wins[k - 2]) if k > 1 else "")

        # 已有成品：结构合规 + 真渲一帧过了就直接复用（续跑不重复烧钱）。
        # 只在「同一项目 + 这一镜内容没变」时复用：指纹对不上（换了歌/改了分镜/
        # 换了编导方案/换了定妆）就重画；绝不从共享 runtime 目录捡别的项目的旧镜头。
        cand = ""
        if not force and dst.exists():
            try:
                meta = json.loads((parts / f"artist-shot-{k}.meta.json")
                                  .read_text(encoding="utf-8-sig"))
                if meta.get("sig") == sig:
                    cand = dst.read_text(encoding="utf-8")
            except Exception:
                cand = ""
        if cand and _has_named_export(cand, f"Shot{k}") and not _check_shot(cand, f"Shot{k}") \
                and not rs.static_check(cand):
            register(k, cand, sig)
            ok, err = validate(k, cand, w0)
            if ok:
                return k, cand, "复用"
            _log(f"  镜 {k}/{len(wins)} 旧文件未过逐镜闸门，重画")
            feedback = err
        unregister(k)

        system = (SHOT_SYSTEM
                  .replace("{EXPORT}", f"Shot{k}")
                  .replace("META_ID", str(k))
                  .replace("{CAST_BLOCK}", cast_block))
        bible = _bible_excerpt(bible_full, str(w0.get("section") or ""))
        base = _win_ctx(tl, plan, bible, wins, k, brief) + "\n\n只输出完整 TSX 文件。"
        last = ""
        for attempt in range(1, tries + 1):
            ask = base
            if feedback:
                ask += (f"\n\n【上一版被拦下的原因，必须修正】\n{feedback}"
                        "\n只输出修正后的完整文件。")
            dump_fn(f"artist-shot-{k}-prompt", ask)
            try:
                raw = llm(system, ask, cfg, meta_label=f"artist-shot-{k}-t{attempt}")
            except Exception as ex:
                last = f"调用失败：{ex}"
                continue
            code = _clean(raw)
            dump_fn(f"artist-shot-{k}", code)
            bad = _check_shot(code, f"Shot{k}") or "；".join(rs.static_check(code))
            if not bad:
                m = re.search(
                    r"import\s*\{([^}]*)\}\s*from\s*['\"](?:\./char-cast|\./char-hero)['\"]", code)
                if m:
                    used = [x.split(" as ")[0].strip() for x in m.group(1).split(",") if x.strip()]
                    miss = [u for u in used if u not in cast_exports]
                    if miss:
                        bad = (f"角色模块没有导出 {miss}（可用：{sorted(cast_exports)}），"
                               "只能用角色表里的导出名")
            if bad:
                last = bad
                feedback = bad + ("\n（如果是输出被截断：精简画面元素，但必须完整保留导出、"
                                  "BG 和 META。）")
                _log(f"  镜 {k}/{len(wins)} 第 {attempt} 次不合规：{bad[:80]}")
                continue
            register(k, code, sig)
            ok, err = validate(k, code, w0)
            if not ok:
                # 渲帧失败也可能只是环境抖动（进程被沙箱杀、打包超时）：同一份代码
                # 原样再渲一次，仍失败才判定是这个镜头的代码问题，避免白烧一次模型调用。
                _log(f"  镜 {k}/{len(wins)} 第 {attempt} 次渲帧失败，原样重渲一次（排除环境抖动）")
                ok, err = validate(k, code, w0)
            if ok:
                return k, code, ("重画" if attempt > 1 else "")
            last = err
            feedback = err
            unregister(k)
            _log(f"  镜 {k}/{len(wins)} 第 {attempt} 次未过逐镜闸门：{err.splitlines()[-1][:90]}")
        return k, None, last or "未产出"

    def safe_one(k: int, feedback: str = "") -> tuple[int, str | None, str]:
        try:
            return one(k, feedback)
        except Exception as ex:  # 单镜异常不该炸掉整条流水线
            return k, None, f"生成异常：{type(ex).__name__}: {ex}"

    def run(ks: list[int], fb: dict[int, str] | None = None) -> None:
        fb = fb or {}
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            for k, code, note in ex.map(lambda k: safe_one(k, fb.get(k, "")), ks):
                if code:
                    state[k]["code"] = code
                    state[k]["note"] = ""
                    _log(f"  镜 {k}/{len(wins)} 完成{('（' + note + '）') if note else ''}")
                else:
                    state[k]["note"] = note
                    _log(f"  镜 {k}/{len(wins)} 失败：{note.splitlines()[-1][:120]}")

    def run_until_settled(ks: list[int], fb: dict[int, str] | None = None) -> None:
        """并行校验里，某镜可能被别的镜头的语法错误连坐清掉；补画到稳定为止。"""
        pending, fb = list(ks), (fb or {})
        for _ in range(3):
            if not pending:
                return
            run(pending, fb)
            pending = []
            for k, st in state.items():
                if st["code"] and f"shot-{k}" not in manifest:
                    st["code"] = ""
                    st["note"] = "被并行校验连坐"
                    pending.append(k)
            fb = {}

    run_until_settled([k for k in state if not state[k]["code"]])

    # 2 整片闸门：编译 → 运行时(strict) → 确定性；报错按 t 映射回镜头，定向重画
    entries = [v for v in manifest.values() if v["key"].startswith("shot-")]
    times = rs._pick_times(entries)
    out, warn, ok = "", "", False
    for attempt in range(max(1, rounds)):
        ok, out, warn = rs.gate(w, tl, plan, times, manifest, namespace="artist")
        if ok:
            break
        bad = set()
        for line in out.splitlines():
            m = re.search(r"t=([0-9]+(?:\.[0-9]+)?)", line)
            if not m:
                continue
            t = float(m.group(1))
            ent = min(entries, key=lambda v: abs(float(v.get("t") or 0) - t))
            bad.add(int(ent["key"].split("-")[1]))
        if attempt == max(1, rounds) - 1:
            return False, "闸门未通过：" + out[-300:], None
        if not bad:
            bad = {k for k in state if not state[k]["code"]} or set(state)
        _log("闸门未过，逐条原因：\n" + "\n".join(out.splitlines()[:20]))
        _log(f"闸门：重画 {sorted(bad)}")
        fb = {k: "【整片闸门报的这一镜错误，必须修掉】\n" + out for k in bad}
        for k in bad:
            state[k]["code"] = ""
            state[k]["note"] = "整片闸门未过"
            unregister(k)
        run_until_settled([k for k in sorted(bad) if k in state], fb)
        entries = [v for v in manifest.values() if v["key"].startswith("shot-")]
        times = rs._pick_times(entries)

    if out and not ok:
        return False, "闸门未通过：" + out[-300:], None
    if warn:
        _log(f"  ⚠ {len(warn.splitlines())} 条类型告警（已放行）")

    missing = [k for k in state if not state[k]["code"]]
    if missing:
        # 一镜画不出来不该让整片停在这里：如实记录，成片该处会落到引擎兜底黑场，
        # 后续也还能单独重画（parts 存在即复用）。
        _log(f"⚠ 以下镜头最终没有产出，成片里会是黑场：{missing}")
        _atomic_text(w / "missing-shots.json",
                     json.dumps(sorted(missing), ensure_ascii=False, indent=2))
    else:
        (w / "missing-shots.json").unlink(missing_ok=True)

    # 逐镜静帧索引，方便人工快速翻看每一镜长什么样
    _atomic_text(shots_dir / "index.json", json.dumps(
        {f"shot-{k}": {"t": round((wins[k - 1]["start"] + wins[k - 1]["end"]) / 2, 3),
                       "png": f"shot-{k:02d}.png"} for k in sorted(state)},
        ensure_ascii=False, indent=2))

    scenes = w / "scenes.tsx"
    scenes.write_text(json.dumps(sorted(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return True, f"{len(wins)} 镜 / {len(tl.get('lines') or [])} 句", scenes


def main() -> int:
    ap = argparse.ArgumentParser(description="开放模式：自动分镜 → 定妆 → 拍镜头 → 闸门")
    ap.add_argument("--work", required=True)
    ap.add_argument("--workers", type=int, default=4, help="并行生成的镜头数")
    ap.add_argument("--rounds", type=int, default=2, help="闸门不过时最多重画几轮")
    ap.add_argument("--char-rounds", type=int, default=3)
    ap.add_argument("--force", action="store_true", help="忽略缓存，全部重画")
    ap.add_argument("--brief", default="")
    args = ap.parse_args()
    w = Path(args.work).resolve()

    sys.path.insert(0, str(HERE))
    import pipeline  # noqa: WPS433

    # 画面作者可以单独指定模型（不改 pipeline 其它阶段）：
    #   LYRIC_MV_ARTIST_LLM={"api_key":...,"base_url":...,"model":...,"protocol":"openai"}
    raw = os.environ.get("LYRIC_MV_ARTIST_LLM", "")
    cfg = None
    if raw:
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = None
    cfg = cfg or pipeline._llm_cfg()
    if not cfg:
        _log("没有 LLM 配置")
        return 2
    tl = json.loads((w / "timeline.json").read_text(encoding="utf-8-sig"))
    plan = json.loads((w / "plan.json").read_text(encoding="utf-8-sig"))
    story = None
    sp = w / "story.json"
    if sp.exists():
        story = json.loads(sp.read_text(encoding="utf-8-sig"))

    if args.char_rounds:
        os.environ["LYRIC_MV_CHAR_ROUNDS"] = str(args.char_rounds)
    ok, note, scenes = generate(w, tl, plan, args.brief, cfg, pipeline._llm,
                                pipeline.dump, story=story, force=args.force,
                                workers=args.workers, rounds=args.rounds)
    print(f"SCENES={scenes}", flush=True)
    _log(("完成：" if ok else "失败：") + note)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
