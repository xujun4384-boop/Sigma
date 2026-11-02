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
import base64
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

CHAR_SYSTEM = """你是一位动画角色设计师。现在只做一件事：画**主角本人**，但不是一个姿势，
而是一个**可以摆动作的角色组件**（有肩肘关节、会转视角、有表情），不画场景。

## 交付契约（只有这些）
1. **只导出一个组件** `export const Character: React.FC<CharacterProps>`（类型可以一起导出）。
   它必须接受下面这些参数，并且**每个参数都要真的改变画面**：

   | 参数 | 取值 | 含义 |
   |---|---|---|
   | `view` | `'front' \\| 'side' \\| 'back'` | 正面 / 侧面 / 背面，同一个人 |
   | `pose` | `'stand' \\| 'sit'` | 站 / 坐（坐下要屈膝、身体下沉，不是整体平移） |
   | `armL` / `armR` | `[肩角, 肘角]`，单位度 | 0 = 自然下垂；举臂方向你定，但必须能摆出「向前伸手 / 抬手扶额 / 打字」 |
   | `headTurn` | -30 ~ 30 | 转头 |
   | `tilt` | -15 ~ 15 | 整体倾斜（头晕、踉跄、倚靠） |
   | `mood` | `'calm' \\| 'tired' \\| 'surprised' \\| 'dizzy'` | 表情：平静 / 疲惫 / 惊讶 / 头晕（螺旋眼） |
   | `phase` | 0~1 | 呼吸/摆动的相位（可选） |

   不传参数时要有合理默认值：正面、站立、双臂下垂、calm。
2. **只返回 `<g>` 片段**：外层会做 `translate(960, 940) scale(1.62)`，
   所以绝对不要写 `<svg>`、`viewBox`、`AbsoluteFill`，也不要用 1920×1080 画布坐标。
3. 坐标系：脚底在 y=0，人站在 x=0 附近，**总高约 430 单位**（头顶约 y=-430）。
   三个视角的脚底与身高必须对齐；坐姿靠屈膝降低头顶，脚仍留在 y≈0。
4. 背景透明（不要铺底色），四周不要加边框、文字、装饰。
5. 三个视角必须是**同一个人**：同发型、同服装、同配色、同头身比；侧面要有身体厚度和鼻梁/后脑轮廓；
   背面不露脸。
6. **手臂必须是骨骼驱动**：肩关节一层 `rotate`，肘关节再来一层 `rotate`，手掌挂在肘的末端。
   不要用一条固定路径把手臂画死——那样 `armL/armR` 改了也不会动，整份会被否决。
7. 每个视角都要能被一眼认成人：头、脖子、躯干、两臂+手、两腿+鞋；正面/侧面要有五官。

示例骨架（只示范**骨骼结构**，造型自己定；角度正负自定，但必须看得出变化）：

```tsx
export type CharacterProps = {
  view?: 'front' | 'side' | 'back';
  pose?: 'stand' | 'sit';
  armL?: [number, number];
  armR?: [number, number];
  headTurn?: number;
  tilt?: number;
  mood?: 'calm' | 'tired' | 'surprised' | 'dizzy';
  phase?: number;
};

export const Character: React.FC<CharacterProps> = ({
  view = 'front', pose = 'stand', armL = [0, 0], armR = [0, 0],
  headTurn = 0, tilt = 0, mood = 'calm', phase = 0,
}) => {
  const sit = pose === 'sit';
  const hip = sit ? -120 : -100;           // 坐下时胯部下沉、膝盖前折
  const shoulderY = sit ? -272 : -300;
  return (
    <g transform={`rotate(${tilt} 0 -200)`}>
      {/* 腿 + 鞋（sit 时改膝角） */}
      {/* 躯干（view 决定宽度：side 只有正面的一半左右） */}
      {/* 手臂：肩 → 肘 → 手，两层 rotate */}
      <g transform={`translate(-46 ${shoulderY}) rotate(${armL[0]})`}>
        <rect x={-11} y={0} width={22} height={70} rx={11} fill="currentColor" />
        <g transform={`translate(0 70) rotate(${armL[1]})`}>
          <rect x={-10} y={0} width={20} height={62} rx={10} fill="currentColor" />
          <circle cx={0} cy={68} r={12} fill="currentColor" />
        </g>
      </g>
      {/* 右臂同理 */}
      {/* 头：view='side' 换侧脸；headTurn 用 rotate；mood 换眼/嘴（dizzy = 螺旋眼） */}
    </g>
  );
};
```

## 硬性质量线（会被否决）
- 定妆会渲染**五格参数网格**（正面/侧面/背面/坐姿伸手/倾斜头晕）。任意两格长得一样 = 参数没接上，整份打回。
- 头 / 手 / 脚的比例要读成人形，不能是"圆头 + 一根柱子"；手要有明确形状，不能和袖子粘成一根棒。
- 头发、皮肤、衣服三者在明度上要能分开；**不许整块纯黑剪影**。
- 至少 3 层明暗（暗部 / 本体 / 高光），让人有体积。
- 三个视角拼在一起要像同一个人；任一角度读不成人，整份打回。

## 可用能力
React + SVG 全部能力；可用 `useCurrentFrame`；可为内部拆分小组件。
禁止：外部图片、网络字体、随机数、定时器（同一帧必须渲出同样像素）。

只输出一个 TSX 文件（可带围栏），不要解释。
"""

SHOT_SYSTEM = """你是一位动画美术导演，用 Remotion 画 MV 的一个镜头。

## 可用素材（用不用、怎么用、用哪个角度，你定）
- 主角是一个**可摆动作**的组件：`import {IMPORTS} from './char-hero';`

  | 参数 | 取值 | 用途 |
  |---|---|---|
  | `view` | `front` / `side` / `back` | 角度：要情绪给正面，要方向给侧面，离开才用背面 |
  | `pose` | `stand` / `sit` | 站 / 坐（桌前、地面都可用坐姿） |
  | `armL` / `armR` | `[肩角, 肘角]` | 0 = 自然下垂；用来做伸手、打字、扶额、指向 |
  | `headTurn` | 度数 | 转头看屏幕 / 看人 |
  | `tilt` | 度数 | 身体倾斜（头晕、疲惫、倚靠） |
  | `mood` | `calm` / `tired` / `surprised` / `dizzy` | 表情 |

  ```tsx
  <Character pose="sit" armL={[-38, -78]} armR={[-30, -72]} />   // 坐在桌前打字
  <Character pose="sit" armR={[-52, -20]} headTurn={8} />        // 伸手按运行
  <Character view="side" tilt={10} mood="tired" />               // 侧身、疲惫
  ```

  **要什么动作就调参数，不要自己拼人体**：不要用 rect / path 另画一条手臂、一个头。
  同一镜里的人物只能来自这个组件，否则比例和连接处一定崩。

- 可选放置器（只是工具，不是必须）：

```tsx
import {Actor} from '../../ui/Actor';
<Actor Character={Character} x={820} y={980} s={1.15} flip />
```

  `x/y` 是脚底画布坐标，`s` 是缩放（1 ≈ 470px 高）。它只在「头被歌词压住」时让位，其余不管你。
  不想用就直接 `<g transform={...}><Character /></g>`。

**人、镜头、谁挡住谁，都是你的镜头语言**：这一镜不需要人就别画；要让标题/黑场/前景座椅盖住人，
就把人画在那些图元**之前**。没有人会替你强加图层顺序。

## 你的工作方式
1. 场景自己设计、自己画；推镜、人物、前中后景都在你自己的 SVG 图层里安排。
2. 写完先自己过一遍这一帧的构图；引擎会立刻真渲一帧，崩了会把报错原文回灌给你。
3. 不要为了"过检查"简化画面。
4. 认为可以交付时，最后单独一行写：<DONE>

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


# 角色姿态的导出名（有哪个就注册哪个；新契约只要求 Character，另两个是兼容旧镜头的包装）
POSES = (("Character", "hero", "正面 / 侧面 / 背面（view 参数）"),
         ("CharacterSide", "hero-side", "侧身包装"),
         ("CharacterBack", "hero-back", "背面包装"))


def _char_exports(code: str) -> list[str]:
    return [name for name, _, _ in POSES if _has_named_export(code, name)]


def _sync_char() -> None:
    """按 char-hero.tsx 实际导出的姿态写注册表；缺哪个就不注册哪个，避免编译失败。"""
    src = GENERATED / "char-hero.tsx"
    code = src.read_text(encoding="utf-8") if src.exists() else ""
    have = set(_char_exports(code))
    rows = [(alias, name) for name, alias, _ in POSES if name in have]
    imports = ", ".join(f"{name} as {name}" for _, name in rows)
    entries = ", ".join(f"'{alias}': {name}" for alias, name in rows)
    body = "import React from 'react';\n"
    body += ("import {" + imports + "} from './generated/char-hero';\n\n" if rows else "")
    body += "export const CHAR_REGISTRY: Record<string, React.FC> = {" + entries + "};\n"
    CHAR_REG.write_text(body, encoding="utf-8")


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


def _ask_vision(png: Path, prompt: str, cfg: dict) -> str:
    from skills.image_reader import describe_image_b64
    b64 = base64.b64encode(png.read_bytes()).decode()
    return describe_image_b64(b64, "image/png", prompt, cfg, timeout=120)


def _verdict(text: str) -> bool:
    m = re.search(r"VERDICT\s*:\s*(PASS|FAIL)", text or "", re.I)
    return bool(m and m.group(1).upper() == "PASS")


CHAR_REVIEW = """这是同一个角色的定妆参数网格，从左到右五格：
正面站立 / 侧面站立 / 背面站立 / 坐姿伸手 / 倾斜头晕。
先只回答一个问题并放在第一行：`VERDICT: PASS` 或 `VERDICT: FAIL`。
判定标准：
- **五格必须明显不同**：视角、坐姿、手臂角度、倾斜、表情都要看得出来。
  任意两格长得一样 = 参数没有接进绘制，直接 FAIL（这种角色进镜头后，动作只能靠画面作者自己拼人体）。
- 每一格单独看都能一眼读成「一个人」：头/手/脚比例正常，手臂从肩膀连出来，关节处不断裂。
- 五格像同一个人：同发型、同服装、同配色、同身高。
- 侧面要有身体厚度和鼻梁/后脑轮廓；背面不露脸；坐姿要真的坐下（屈膝、重心下沉），不是整体平移。
不合格的典型：只有圆头和柱子、没有手、手和袖子粘成一根棒、头身粘连、整块黑影、五格一模一样。
第一行之后，列出 2~5 条**能直接改代码**的具体问题（关节/比例/明暗/部件），每条一句话。"""

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




def _char_brief(w: Path, plan: dict, cfg_brief: str) -> str:
    bible = ""
    p = w / "visual-bible.json"
    if p.exists():
        bible = p.read_text(encoding="utf-8")[:5000]
    return (
        "【主角设定】\n"
        + (bible or "（无视觉圣经，按编导方案推断）")
        + "\n\n【编导方案】\n" + json.dumps(plan, ensure_ascii=False)[:3000]
        + (f"\n\n【用户要求】\n{cfg_brief}" if cfg_brief else "")
        + "\n\n现在画这个主角的定妆照：同一个人，但要画成**可摆动作**的组件"
          "（view / pose / armL / armR / headTurn / tilt / mood 都要真的接进绘制），"
          "定妆会渲成五格参数网格来验收。"
    )


def _check_char(code: str) -> str:
    """角色必须是「可摆动作」的 <g> 组件：参数要真的接进绘制，否则镜头里只能自己拼人体。"""
    bad = []
    if "<svg" in code:
        bad.append("不要写 <svg> 标签：外层已经给了 translate/scale，你只返回 <g>…</g>")
    if "viewBox" in code:
        bad.append("不要写 viewBox / 画布坐标")
    if "AbsoluteFill" in code:
        bad.append("不要用 AbsoluteFill，只返回 <g> 片段")
    if re.search(r"(?:cx|cy|x|y)=\{?\s*(?:9[0-9]{2}|1[0-9]{3})", code):
        bad.append("坐标里出现了 900 以上的绝对画布值，请改用本地坐标（脚底 y=0、总高约 430）")
    if not _has_named_export(code, "Character"):
        bad.append("必须导出 Character（export const / export function / export {Character} 均可）")
    # 参数必须在签名和绘制里都出现；只写类型不接进图形 = 调了也不动
    need = ("view", "pose", "armL", "armR", "headTurn", "tilt", "mood")
    miss = [n for n in need if code.count(n) < 2]
    if miss:
        bad.append("这些参数没有真正接进绘制（签名和图形里都要用到）：" + "、".join(miss))
    return "；".join(bad)


def phase_character(w: Path, plan: dict, brief: str, cfg: dict, llm, rounds: int = 3) -> tuple[bool, str]:
    art = w / "art"
    art.mkdir(exist_ok=True)
    fpath = GENERATED / "char-hero.tsx"
    ctx = _char_brief(w, plan, brief)
    code = ""
    history = ""
    for r in range(1, rounds + 1):
        ask = ctx + (f"\n\n【你上一版】\n{code}\n\n" if code else "\n\n")
        ask += f"这是第 {r} 轮。" + (history + "\n\n" if history else "") + "只输出完整 TSX 文件。"
        _log(f"角色 第 {r} 轮：作画…（{cfg.get('model')}）")
        raw = llm(CHAR_SYSTEM, ask, cfg, meta_label=f"char-r{r}")
        code = _clean(raw)
        bad = _check_char(code)
        if bad:
            _log(f"角色 契约不合规：{bad[:80]}")
            history = f"【上一版不符合交付契约，必须改】\n{bad}"
            continue
        (art / f"char-r{r}.tsx").write_text(code, encoding="utf-8")
        fpath.write_text(code, encoding="utf-8")
        _sync_char()

        dst = art / f"sheet-r{r}.png"
        ok, err = _sheet(w, "hero", dst)
        if not ok:
            _log("定妆照渲染失败，回灌报错")
            history = f"【上一版渲染失败，必须修掉】\n{err}"
            continue
        view = dst
        try:
            note = _ask_vision(view, CHAR_REVIEW, cfg)
        except Exception as ex:
            _log(f"看图失败（{type(ex).__name__}），本轮无法判定")
            note = ""
        passed = _verdict(note)
        _log(f"角色 第 {r} 轮：{'通过' if passed else '未通过'} ｜ {view.name}")
        if passed and r >= 2:
            # 批准标记：续跑时只要角色文件没被改动，就永远复用它，
            # 绝不再因为「契约升级了」把已经验收过的角色重画一遍。
            _atomic_text(art / "char-approved.json", json.dumps(
                {"sha": hashlib.sha1(code.encode("utf-8")).hexdigest(),
                 "at": datetime.now().strftime("%Y-%m-%d %H:%M")},
                ensure_ascii=False))
            return True, str(view)
        history = ("【定妆照自评】\n" + (note or "视觉模型不可用：请自己再检查一次三个角度的人体结构"))
    return False, str(art / f"sheet-r{rounds}-all.png")


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


def _shot_windows(tl: dict, target: float, story: dict | None = None) -> list[dict]:
    """分镜表。[{start, end, lines:[idx], section}]
    有编导给的 story.shots 就用它；否则按「段落边界 + 目标时长」自动切，不依赖歌词关键词。"""
    lines = tl.get("lines") or []
    dur = float(tl.get("duration") or 0)
    if not lines:
        return []

    shots = (story or {}).get("shots") or []
    if shots:
        out = []
        for s in shots:
            a, b = float(s.get("start") or 0), float(s.get("end") or 0)
            if b - a < 0.2:
                continue
            idxs = [i for i, ln in enumerate(lines) if ln["end"] > a and ln["start"] < b]
            out.append({"start": a, "end": b, "lines": idxs, "section": s.get("section") or "",
                        "brief": s.get("action") or s.get("desc") or "",
                        "size": s.get("size") or ""})
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
        if p:
            prev_txt = f"\n\n【上一镜】{lines[p[0]]['text']} … {lines[p[-1]]['text']}"
    next_txt = ""
    if k < len(wins):
        n = [i for i in wins[k]["lines"] if 0 <= i < len(lines)]
        if n:
            next_txt = f"\n【下一镜】{lines[n[0]]['text']} … {lines[n[-1]]['text']}"

    shot_brief = ""
    if w0.get("brief"):
        shot_brief = ("\n\n【编导对这一镜的要求】\n" + str(w0["brief"])
                      + (f"\n景别：{w0['size']}" if w0.get("size") else ""))

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
    wins = _shot_windows(tl, target, story)
    if not wins:
        return False, "没有歌词行，无法分镜", None
    _log(f"分镜：{len(wins)} 镜（目标 {target:.0f}s/镜，mode={mode}）")

    # 1 定妆：角色是跨镜头的共同资产，只画一次；重做要显式开 LYRIC_MV_CHAR_REDO=1
    # 复用只看「验收标记 + 文件哈希」，不看当前契约是否升级——否则改一版契约，
    # 所有续跑都会把已验收的角色重画一遍。
    char_file = GENERATED / "char-hero.tsx"
    char_code = char_file.read_text(encoding="utf-8") if char_file.exists() else ""
    char_sha = hashlib.sha1(char_code.encode("utf-8")).hexdigest() if char_code else ""
    marker = GENERATED / "char-approved.json"
    approved = False
    if char_code:
        if marker.exists():
            try:
                approved = json.loads(marker.read_text(encoding="utf-8-sig")).get("sha") == char_sha
            except Exception:
                approved = False
        if not approved and any((w / "art").glob("sheet-r*.png")):
            # 旧项目没有批准标记：只要这个项目出过定妆图，就按「已验收」处理
            approved = True
            _atomic_text(marker, json.dumps({"sha": char_sha, "legacy": True}, ensure_ascii=False))
            _log("旧项目没有角色验收标记，按已出过定妆图处理：复用，不重画")
    char_ready = bool(char_code) and approved
    redo_char = os.environ.get("LYRIC_MV_CHAR_REDO", "").strip() in ("1", "true", "yes")
    if redo_char or not char_ready:
        if char_code and not char_ready:
            _log("已有角色但没有验收标记，重新定妆")
        ok, sheet = phase_character(w, plan, brief, cfg, llm, int(os.environ.get("LYRIC_MV_CHAR_ROUNDS", "3")))
        if not ok:
            # 已有一版能用的角色时，不因为拿不到三视角就把整条片子卡死
            if _has_named_export(char_code, "Character"):
                _atomic_text(char_file, char_code)
                _sync_char()
                _log("新定妆未通过，退回上一版可用角色（可能仍然只有两个视角）")
            else:
                return False, "主角定妆未通过（先解决人物，再拍镜头）", None
        else:
            _log(f"定妆通过：{sheet}")
    else:
        _sync_char()
        _log("复用已验收的角色（不重画）")

    bpath = w / "visual-bible.json"
    bible_full = bpath.read_text(encoding="utf-8") if bpath.exists() else ""
    # 镜头提示词只能宣传真实存在的姿态，否则会写出 import 不到的名字
    char_final = char_file.read_text(encoding="utf-8") if char_file.exists() else ""
    poses = _char_exports(char_final) or ["Character"]
    pose_imports = ", ".join(poses)
    manifest: dict = {}
    state = {k: {"code": "", "note": "", "done": False} for k in range(1, len(wins) + 1)}
    lock = threading.Lock()
    tries = max(1, int(os.environ.get("LYRIC_MV_SHOT_TRIES", "2")))

    def register(k: int, code: str) -> None:
        with lock:
            _atomic_text(parts / f"artist-shot-{k}.tsx", code)
            manifest[f"shot-{k}"] = _manifest_entry(k, wins[k - 1], f"artist-shot-{k}.tsx")
            _write_manifest(parts, manifest)

    def unregister(k: int) -> None:
        with lock:
            manifest.pop(f"shot-{k}", None)
            (parts / f"artist-shot-{k}.tsx").unlink(missing_ok=True)
            (GENERATED / f"artist-shot-{k}.tsx").unlink(missing_ok=True)
            _write_manifest(parts, manifest)

    def render_shot(k: int, t: float) -> tuple[bool, str]:
        with lock:
            rs.sync_registry(w)
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

        # 已有成品：结构合规 + 真渲一帧过了就直接复用（续跑不重复烧钱）
        cand = ""
        if not force:
            if dst.exists():
                cand = dst.read_text(encoding="utf-8")
            elif (GENERATED / fname).exists():
                gen_copy = GENERATED / fname
                cand = gen_copy.read_text(encoding="utf-8")
        if cand and _has_named_export(cand, f"Shot{k}") and not _check_shot(cand, f"Shot{k}") \
                and not rs.static_check(cand):
            register(k, cand)
            ok, err = validate(k, cand, w0)
            if ok:
                return k, cand, "复用"
            _log(f"  镜 {k}/{len(wins)} 旧文件未过逐镜闸门，重画")
            feedback = err
        unregister(k)

        system = (SHOT_SYSTEM
                  .replace("{EXPORT}", f"Shot{k}")
                  .replace("META_ID", str(k))
                  .replace("{IMPORTS}", "{" + pose_imports + "}"))
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
                m = re.search(r"import\s*\{([^}]*)\}\s*from\s*['\"]\./char-hero['\"]", code)
                if m:
                    used = [x.split(" as ")[0].strip() for x in m.group(1).split(",") if x.strip()]
                    miss = [u for u in used if u not in poses]
                    if miss:
                        bad = f"char-hero 没有导出 {miss}（现有：{poses}），改用现有姿态"
            if bad:
                last = bad
                feedback = bad + ("\n（如果是输出被截断：精简画面元素，但必须完整保留导出、"
                                  "BG 和 META。）")
                _log(f"  镜 {k}/{len(wins)} 第 {attempt} 次不合规：{bad[:80]}")
                continue
            register(k, code)
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
        ok, out, warn = rs.gate(w, tl, plan, times, manifest)
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
