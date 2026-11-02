# -*- coding: utf-8 -*-
"""styled_video 的单段渲染管线。

给导演组的一个 panel 用：从 14 种视觉风格里选一种，确定性渲染成无声 mp4。
默认 linear（2~5 个镜头硬切）；可选 grid（一张大画布分格，camera 到点跳格，
每格独立播放，格内可推拉）。旁白/字幕/合成由导演组后续处理。
"""
import hashlib
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SKILLS = ROOT / "skills"
ENGINE = SKILLS / "lyric_mv" / "engine" / "stage.html"
RENDER = SKILLS / "lyric_mv" / "scripts" / "render.py"
API_SPEC = SKILLS / "lyric_mv" / "scripts" / "api_spec.py"

sys.path.insert(0, str(ROOT))
from skills import style_lib  # noqa: E402
from skills import image_assets  # noqa: E402

MAX_TRIES = 3
BUDGET_SEC = 900
# 输出预算与 opendesign/manim 等长输出生成保持同一水位：思考 token 计入 max_tokens，
# 按正文估算必然被思考吃光，因此统一按整体给足（回退档位见 LONG_OUTPUT_TOKEN_FALLBACKS）。
try:
    from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
except Exception:
    LONG_OUTPUT_MAX_TOKENS = 128_000
    LONG_OUTPUT_TOKEN_FALLBACKS = (96_000, 64_000, 32_000)
MAX_OUT_TOKENS = LONG_OUTPUT_MAX_TOKENS
_REPAIR_MAX_EDITS = 6

# 读 scenes.js 顶层的 MV.assets 声明（不执行 draw，不需要浏览器）：
# 声明是纯数据，用 node 的 vm 跑一遍最可靠，避免自己写 JS 解析器。
_ASSET_PROBE = r"""
const vm = require('vm'), fs = require('fs');
const MV = {};
try {
  vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'),
                     { MV, console, Math, JSON, Number, String, Array, Object, Boolean });
} catch (e) { /* 顶层报错时当作没有声明，不影响主流程 */ }
process.stdout.write(JSON.stringify(MV.assets || {}));
"""

_TEXT_REVIEW_PROMPT = """只检查这一帧里的文字（标题/标签/数字/关键词）是否清晰可读，不评价构图和风格。
只输出 JSON：
{"has_text": true/false, "legible": true/false,
 "issue": "具体问题（位置/颜色）", "fix": "一句可执行的修改"}
没有文字就 has_text=false；文字几乎看不见、与背景同色、被背景吞掉时 legible=false。"""


def _sha(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _sh(cmd, stream=False):
    args = [str(c) for c in cmd]
    if stream:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", bufsize=1)
        buf = []
        assert p.stdout is not None
        for line in p.stdout:
            line = line.rstrip()
            if line:
                buf.append(line)
                print(line, flush=True)
        p.wait()
        r = type("R", (), {})()
        r.returncode, r.stdout, r.stderr = p.returncode, "\n".join(buf), ""
        return r
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except FileNotFoundError:
        r = type("R", (), {})()
        r.returncode, r.stdout, r.stderr = 127, "", f"找不到可执行文件：{cmd[0]}"
        return r


def _api_text(work: Path) -> str:
    cache = work / "api-spec.txt"
    fresh = (cache.exists()
             and cache.stat().st_mtime >= ENGINE.stat().st_mtime
             and cache.stat().st_mtime >= API_SPEC.stat().st_mtime)
    if not fresh:
        _sh([sys.executable, str(API_SPEC), "--engine", str(ENGINE), "--out", str(cache)])
    try:
        return cache.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _timeline(duration: float, shots: int, w: int, h: int, fps: int) -> dict:
    seg = duration / shots
    lines = []
    for i in range(shots):
        start = round(i * seg, 3)
        end = round(duration if i == shots - 1 else (i + 1) * seg, 3)
        lines.append({
            "idx": i, "section": "Shot", "text": "", "start": start, "end": end,
            "chars": [], "aligned": True,
        })
    return {
        "bpm": 120, "beat_seconds": 0.5, "offset_seconds": 0.0,
        "duration": round(duration, 3), "plain": True,
        "canvas": {"width": w, "height": h, "fps": fps},
        "lines": lines,
    }


def _plan(style_id: str, w: int, h: int, fps: int) -> dict:
    return {
        "title": "styled panel",
        "visualStyle": style_id,
        "lyricStyle": "band",     # plain 模式不画歌词，但校验器要求显式声明
        "plain": True,
        "canvas": {"width": w, "height": h, "fps": fps},
        "chrome": {"section": "hide", "progress": "hide"},
    }


def _grid_norm(grid, w: int, h: int) -> dict:
    """归一化分格配置：cols/rows 1~3，order 唯一有效，weights 正数，moves 只留数值。

    默认 2×2、按行优先、等权重、无推拉——导演不写 grid 也能用。
    每格尺寸 = 视口尺寸；大画布 = cols*W × rows*H，camera 一次只截一格。
    """
    g = grid if isinstance(grid, dict) else {}
    try:
        cols = max(1, min(3, int(g.get("cols") or 2)))
    except (TypeError, ValueError):
        cols = 2
    try:
        rows = max(1, min(3, int(g.get("rows") or 2)))
    except (TypeError, ValueError):
        rows = 2
    total = cols * rows
    order, seen = [], set()
    raw_order = g.get("order")
    if isinstance(raw_order, list):
        for n in raw_order:
            try:
                i = int(n)
            except (TypeError, ValueError):
                continue
            if 0 <= i < total and i not in seen:
                order.append(i)
                seen.add(i)
    if not order:
        order = list(range(total))
    raw_w = g.get("weights")
    weights = []
    for i in range(len(order)):
        try:
            v = float(raw_w[i]) if isinstance(raw_w, list) and i < len(raw_w) else 1.0
        except (TypeError, ValueError):
            v = 1.0
        weights.append(v if v > 0 else 1.0)
    moves = {}
    raw_m = g.get("moves")
    if isinstance(raw_m, dict):
        for k, v in raw_m.items():
            if not isinstance(v, dict):
                continue
            item = {}
            for key in ("zoom", "x", "y"):
                try:
                    item[key] = float(v[key])
                except (TypeError, ValueError, KeyError):
                    continue
            if item:
                moves[str(k)] = item
    return {"cols": cols, "rows": rows, "cellW": w, "cellH": h,
            "order": order, "weights": weights, "moves": moves}


def _grid_times(duration: float, g: dict) -> list:
    """按 weights 把总时长分给每一格；返回 [{seq,cell,start,end}]。"""
    weights = g.get("weights") or []
    total = sum(weights) or 1.0
    out, acc = [], 0.0
    for seq, cell in enumerate(g.get("order") or []):
        w = float(weights[seq]) if seq < len(weights) else 1.0
        start = duration * acc / total
        acc += w
        end = duration * acc / total
        out.append({"seq": seq, "cell": cell, "start": round(start, 3), "end": round(end, 3)})
    return out


def _asset_specs(path: Path) -> dict:
    """读 MV.assets 声明；node 不可用或代码跑不通时返回 {}（这一段就不配图）。"""
    try:
        r = subprocess.run(["node", "-e", _ASSET_PROBE, str(path)],
                           capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.SubprocessError):
        return {}
    if r.returncode != 0:
        return {}
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _style_prefix(style_id: str) -> str:
    """从风格库派生生图用的美术方向，保证一段里的多张图是同一套视觉。"""
    s = style_lib.get(style_id) or {}
    v = s.get("visual") or {}
    parts = [s.get("label"), v.get("palette"), v.get("line"), v.get("texture")]
    return "；".join(str(p).strip() for p in parts if p and str(p).strip())


def _gen_assets(specs: dict, assets_dir: Path, skill_manager, style_prefix: str,
                max_n: int, emit) -> tuple[dict, list]:
    """按声明逐张生图，返回 ({key: 本地绝对路径}, 失败清单)。

    失败清单每项是 {key, prompt, error}：调用方要把原始报错交给 LLM，
    否则下一轮它会原样再写一遍同一句 prompt，必然复现同一个错误。
    """
    out, failed = {}, []
    for key, spec in list((specs or {}).items())[:max(0, int(max_n or 0))]:
        if isinstance(spec, str):
            spec = {"prompt": spec}
        if not isinstance(spec, dict):
            continue
        prompt = str(spec.get("prompt") or spec.get("desc") or spec.get("text") or "").strip()
        if not prompt:
            continue
        name = image_assets.asset_filename(str(key), f"{key}:{prompt}")
        path, err, created = image_assets.generate(
            skill_manager=skill_manager, prompt=prompt, save_dir=assets_dir,
            filename=name, aspect=spec.get("size") or spec.get("aspect"),
            style_prefix=style_prefix)
        if path is None:
            failed.append({"key": str(key), "prompt": prompt, "error": err})
            emit(f"  ⚠ 配图 {key} 失败：{err[:120]}")
            continue
        out[str(key)] = str(path.resolve())
        if created:
            emit(f"  · 配图 {key} → {path.name}")
    return out, failed


def _system_prompt(style_id: str, shots: int, duration: float, w: int, h: int,
                   layout: str = "linear", grid: dict | None = None,
                   with_images: bool = False, max_images: int = 3) -> str:
    style = style_lib.prompt(style_id, context="styled")
    grid_mode = layout == "grid" and isinstance(grid, dict)
    if grid_mode:
        cells = len(grid["order"])
        order = json.dumps(grid["order"], ensure_ascii=False)
        weights = json.dumps(grid["weights"], ensure_ascii=False)
        moves = json.dumps(grid.get("moves") or {}, ensure_ascii=False)
        head = (f"你是分段动画师。为一集视频中的一个 panel 写**一个分格场景**"
                f"（{grid['cols']}×{grid['rows']}，共 {cells} 格），只输出 JS 代码。")
        grid_block = f"""
### 分格模式（grid）—— 一张大画布，camera 跳格
- 大画布 = {grid['cols'] * w}×{grid['rows'] * h}；每格 {w}×{h}，按格号从左到右、从上到下排列。
- 只写 **1 个 scene**。camera(e) 返回 e.camGrid({{cols:{grid['cols']}, rows:{grid['rows']}, cellW:{w}, cellH:{h}, order:{order}, weights:{weights}, moves:{moves}}})。
- draw(e) 把整张大画布画出来：第 i 格平移到 (col*{w}, row*{h})，并 clip 到 {w}×{h}。
- 当前格用 e.cam.cell 判断，当前格的动画用 e.cam.segU（0~1）驱动；其他格用 0。
  **切进来才从 0 开始**，不要在没轮到的格子里提前播动画。
- 每格是一个独立画面，格与格之间可以没有叙事关联；不要把一条故事拆成跨格连续动作。
- 格内推拉/横移写在 moves 里（键是格号或播放序号）；x/y 是相对该格中心的偏移，只写 zoom 就围绕中心推。不要在 draw 里自己乘缩放。
- 每格都要有看得见的运动（格内元素动或格内推拉）。
- 底部 12% 字幕安全区是**屏幕空间**：每格构图都要避开底部 12%。
"""
        output = """### 输出格式
MV.scenes = [ { bg:"#141A2E", camera(e){ return e.camGrid({...}); }, draw(e){ ... } } ];
条数必须**严格等于 1**。"""
        motion_rule = ("2. **每一格都要有看得见的运动**：格内元素动或格内推拉都行；"
                       "0.5 秒内至少满足一条：主体移动 ≥ 画面宽度的 1.5%、缩放变化 ≥ 8%、"
                       "透明度变化 ≥ 15%，或一组元素整体位移 ≥ 20px。")
        extra_rule = "7. 每格是独立画面，不要写成跨格连续叙事；格与格之间可以没有关联。"
    else:
        head = f"你是分段动画师。为一集视频中的一个 panel 写 {shots} 段镜头动画，只输出 JS 代码。"
        grid_block = ""
        output = f"""### 输出格式
MV.scenes = [ {{bg:"#141A2E", draw(e){{ ... }}}}, ... ];
条数必须**严格等于 {shots}**，按时间顺序对应下面的镜头区间。
需要运镜时，在 scene 对象里加 camera(e){{ ... }}：
不写就是原来的固定机位；写了可以用 e.camPath([...]) 做推拉/横移（u=0~1 是本镜进度）。"""
        motion_rule = ("2. **每个镜头都要有看得见的运动**：主体位移/缩放/形变/粒子/光影漂移都行，"
                       "不能是一张静态图。0.5 秒内至少满足一条：主体移动 ≥ 画面宽度的 1.5%、"
                       "缩放变化 ≥ 8%、透明度变化 ≥ 15%，或一组元素整体位移 ≥ 20px。")
        extra_rule = "7. 各镜头之间要有叙事推进（前→后变化），不要重复同一个构图。"
    image_block = ""
    if with_images and max_images > 0:
        image_block = f"""
### 图片素材（可选）
- 可以在 `MV.assets` 里声明最多 {max_images} 张 AI 生成图片（引擎会生成并落到本段 assets/，无外链）：
  `MV.assets = {{ "skyline": {{ prompt: "英文画面描述", size: "16:9" }} }};`
  key 用英文小写短词；size 可选 16:9 / 4:3 / 3:4 / 1:1。
- draw(e) 里用 `e.drawImg("skyline", x, y, w, h, {{mode:"cover"}})` 绘制；
  返回 false 表示这张图不可用（未声明或加载失败），此时请用图形兜底。
- **图片必须动**：跟着相机推拉、在画面里横移/缩放、或用 e.layer 做视差，任选其一；
  禁止在整段里把图钉死在同一个位置不动。
- 图片只承担氛围/空间/局部质感，叙事主体仍用 canvas 图形与文字完成。
- 图是插画/抽象风格，不出现文字、logo、可辨识真人。
"""
    return f"""{head}

{style}
{grid_block}
{output}
{image_block}
### 硬性规则
1. draw 必须是 e.t 的**纯函数**：禁止 Math.random / Date.now / performance.now /
   setTimeout / requestAnimationFrame / 任何跨帧累积的外部变量。要随机用 e.rnd(seed)。
{motion_rule}
3. 不要画**旁白/字幕原文**（导演组后期叠加）；但可以画短标题、关键词、标签、数字、单字
   （≤12 字），用 e.drawText，字体/颜色/大小按风格的「文字」规则；不要写长段落。
   底部 12% 是导演组的字幕安全区，不要把主体或文字放进去。
   不要使用 e.lyricBox / e.lyricBand（这是无歌词模式）。
4. 画布 {w}×{h}；主体不要贴边，四周留 5% 以上余量。
5. 严格按上面的风格规定配色/线条/质感/构图/运动/禁止项。
6. **人物按本风格的「使用分寸」执行**：人物是代码逐帧画的，面部与手部精细度有限。
   风格规格里的「使用分寸」写了这条风格该怎么用人 —— 剪影类可以把人当叙事主体，
   有五官的尽量少用、只做小比例配角，图表类基本不用。
   通用底线：不画正面脸部特写、不画多人同框、人物高度不超过画面高度的 1/2；
   该有人的段落不要硬删，只是别把镜头怼到脸上。
{extra_rule}
"""


def _context(brief: str, shots: int, duration: float,
             layout: str = "linear", grid: dict | None = None) -> str:
    if layout == "grid" and isinstance(grid, dict):
        rows = [f"  格 {c['seq']}（格号 {c['cell']}）: {c['start']:.2f}~{c['end']:.2f}s"
                for c in _grid_times(duration, grid)]
        return (f"这一段要讲什么：\n{brief or '把这段拆成若干互不相关的画面，每格一个。'}\n\n"
                f"总时长 {duration:.2f}s，大画布 {grid['cols']}×{grid['rows']}，"
                f"播放顺序 {grid['order']}：\n" + "\n".join(rows) +
                "\n\n每格是一个独立画面；用 e.cam.segU 驱动当前格动画，切进来才从 0 开始。")
    seg = duration / shots
    rows = []
    for i in range(shots):
        s = i * seg
        e = duration if i == shots - 1 else (i + 1) * seg
        rows.append(f"  镜头 {i}: {s:.2f}~{e:.2f}s")
    return (f"这一段要讲什么：\n{brief or '按风格自由发挥，但要有明确的画面主体和叙事推进。'}\n\n"
            f"总时长 {duration:.2f}s，分 {shots} 个镜头：\n" + "\n".join(rows))


def _js_of(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    return raw.strip()


def _json_of(raw: str) -> dict:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except Exception:
                pass
    return {}


def _frame_b64(p, max_side=1280):
    """压成 JPEG 再送视觉接口：整幅 PNG 一张 1~2MB，直接 base64 容易超限。"""
    try:
        from PIL import Image
        im = Image.open(p)
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return base64.b64encode(Path(p).read_bytes()).decode("ascii"), "image/png"


def _text_review(work: Path, timeline: Path, plan: Path, scenes: Path,
                 times, cfg: dict):
    """抽帧让视觉模型检查文字可读性。返回问题列表；视觉接口不可用时返回 None（跳过）。"""
    out = work / "review-text"
    shutil.rmtree(out, ignore_errors=True)
    r = _sh([sys.executable, str(RENDER), "--engine", str(ENGINE),
             "--timeline", str(timeline), "--plan", str(plan), "--scenes", str(scenes),
             "--shots", ",".join(f"{t:.3f}" for t in times), "--shots-out", str(out)])
    frames = sorted(out.glob("f_*.png"))
    if r.returncode != 0 or not frames:
        return None
    try:
        from skills.image_reader import describe_image_b64
    except Exception:
        return None
    issues = []
    for f in frames:
        b64, mime = _frame_b64(f)
        try:
            txt = describe_image_b64(b64, mime, _TEXT_REVIEW_PROMPT, cfg, timeout=90)
        except Exception:
            return None
        doc = _json_of(txt)
        if not doc or doc.get("has_text") is False:
            continue
        if doc.get("legible") is False:
            issues.append(str(doc.get("issue") or doc.get("fix") or "文字与背景对比不足"))
    (work / "review-text.json").write_text(
        json.dumps({"issues": issues}, ensure_ascii=False, indent=2), encoding="utf-8")
    return issues


def _repair_prompt(style_id: str, shots: int, duration: float, w: int, h: int,
                   api: str, kind: str, layout: str = "linear",
                   grid: dict | None = None) -> str:
    """生成「原地修补」系统提示：只允许输出最小 find/replace 清单。"""
    style = style_lib.prompt(style_id, context="styled")
    grid_mode = layout == "grid" and isinstance(grid, dict)
    kind_rule = {
        "syntax": "这是 JS 语法错误：只修报错行及其直接相关的小段代码，不要改动其他镜头。",
        "gate": "这是渲染前闸门错误：只修报错涉及的镜头/属性（确定性、运行时），不要重写整个文件。",
        "text": "这是文字可读性错误：优先只改 e.drawText 的 color / stroke / strokeWidth / 底板，"
                "不要改文案内容和构图。",
        "image": "这是配图生成失败：只改 MV.assets 里报错那个 key 的 prompt（更短、更具体、"
                 "去掉人名/品牌/敏感内容），或者删掉这个 key 并改用图形画；不要动其他镜头。",
    }.get(kind, "只修与本次错误直接相关的部分。")
    if grid_mode:
        kind_rule += " 这是分格模式：保持 1 个 scene + camera(e) 的 e.camGrid(...)，不要改成多个 scene，只修报错的那一格。"
        project = (f"1 个 scene / {grid['cols']}×{grid['rows']} 分格"
                   f"（{len(grid['order'])} 格，e.camGrid）")
    else:
        project = f"{shots} 个镜头"
    return f"""你是动画代码修复器。下面会给你一段现有的 JS 动画代码和具体错误。
只输出 JSON 修改清单，不要解释、不要 markdown、不要输出整份文件。

{style}

### 可用 API
{api}

### 输出格式（严格）
{{"edits":[{{"find":"原文中逐字复制的一段唯一代码","replace":"修正后的代码"}}]}}

### 修复规则
1. 最小修改：{kind_rule}
2. `find` 必须从当前代码里**逐字复制**，且在全文**只出现一次**；太短容易重复，请带上足够上下文。
3. `replace` 保留原逻辑，只改必要部分；如果要删除，`replace` 用空字符串。
4. 最多 {_REPAIR_MAX_EDITS} 处编辑；不要输出整份文件，不要输出解释。
5. 不得违反原风格规则：确定性（禁止 Math.random / Date.now / performance.now）、
   每个{'格' if grid_mode else '镜头'}必须有可见运动、底部 12% 字幕安全区。
6. 当前工程：{project} / {duration:.2f}s / {w}×{h}。
"""


def _apply_edits(js: str, edits) -> tuple:
    """按 find/replace 原地修改；find 必须唯一。返回 (new_js, applied, failed)。"""
    if not isinstance(edits, list):
        return js, 0, ["edits 不是数组"]
    applied, failed = 0, []
    for ed in edits[:_REPAIR_MAX_EDITS]:
        if not isinstance(ed, dict):
            continue
        find = ed.get("find")
        if not isinstance(find, str) or not find:
            continue
        repl = ed.get("replace")
        repl = "" if repl is None else str(repl)
        n = js.count(find)
        if n != 1:
            failed.append(f"find 出现 {n} 次：{find[:60]!r}")
            continue
        js = js.replace(find, repl, 1)
        applied += 1
    return js, applied, failed


def _repair_scenes(current_js: str, errs: list, kind: str, cfg: dict,
                   style_id: str, shots: int, duration: float, w: int, h: int,
                   api: str, layout: str = "linear", grid: dict | None = None) -> tuple:
    """让 LLM 只返回最小修改清单，并应用到当前代码。

    返回 (new_js, applied, failed, raw)。applied=0 表示补丁无法落地，调用方应回退整篇重写。
    """
    from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
    grid_mode = layout == "grid" and isinstance(grid, dict)
    system_prompt = _repair_prompt(style_id, shots, duration, w, h, api, kind,
                                   layout=layout, grid=grid)
    project = (f"1 个 scene / {grid['cols']}×{grid['rows']} 分格（{len(grid['order'])} 格）"
               if grid_mode else f"{shots} 个镜头")
    ctx = (
        "【当前代码】\n```js\n" + current_js + "\n```\n\n"
        "【本次错误】\n" + "\n".join(f"- {e}" for e in (errs or [])[:5]) + "\n\n"
        f"【工程参数】{project} / {duration:.2f}s / {w}×{h}\n\n"
        "只输出 JSON 修改清单。"
    )
    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            system_prompt=system_prompt, context=ctx,
            base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
            protocol=cfg.get("protocol", "anthropic"), provider=cfg.get("provider"),
            thinking="disabled", max_tokens=budget, timeout=240, attempts=1),
        max_tokens=MAX_OUT_TOKENS,
        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    doc = _json_of(raw)
    if isinstance(doc, list):
        edits = doc
    elif isinstance(doc, dict):
        edits = doc.get("edits")
    else:
        edits = None
    new_js, applied, failed = _apply_edits(current_js, edits)
    return new_js, applied, failed, raw


def _gate(timeline: Path, plan: Path, scenes: Path, work: Path):
    r = _sh([sys.executable, str(RENDER), "--engine", str(ENGINE),
             "--timeline", str(timeline), "--plan", str(plan),
             "--scenes", str(scenes), "--gate-only"], stream=True)
    out = (r.stdout or "") + (r.stderr or "")
    errs = [ln.strip(" -") for ln in out.splitlines() if ln.strip().startswith("-")]
    return r.returncode == 0, out, errs


def run(brief: str, style_id: str, duration: float, output_path: str,
        work_dir: str, width: int = 1920, height: int = 1080, fps: int = 30,
        shots: int = 3, layout: str = "linear", grid: dict | None = None,
        with_images: bool = False, max_images: int = 3, skill_manager=None,
        llm_cfg: dict | None = None, progress=None) -> tuple:
    """返回 (ok, note, output_path)。

    layout="linear"（默认）：现有的 2~5 个镜头，分镜之间硬切。
    layout="grid"（可选）：一张大画布分格，camera 到点跳格，每格独立播放；格内可推拉。
    """
    def emit(msg):
        print(msg, flush=True)
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    if not style_lib.get(style_id):
        return False, f"未知风格 {style_id!r}；可用 {' / '.join(style_lib.ids())}", ""
    duration = max(1.5, min(60.0, float(duration or 0)))
    w, h, fps = max(320, int(width)), max(180, int(height)), max(10, int(fps))
    layout = "grid" if str(layout or "").strip().lower() == "grid" else "linear"
    grid_norm = _grid_norm(grid, w, h) if layout == "grid" else None
    shots = 1 if layout == "grid" else max(2, min(5, int(shots or 3)))
    project_label = (f"{grid_norm['cols']}×{grid_norm['rows']} 分格（{len(grid_norm['order'])} 格）"
                     if grid_norm else f"{shots} 镜头")
    work = Path(work_dir)
    (work / "llm").mkdir(parents=True, exist_ok=True)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cfg = llm_cfg or {}
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        return False, "styled_video 需要主 LLM 配置（base_url / api_key / model）", ""

    # 没有生图通道就不在提示词里许愿，LLM 会按纯图形写
    max_images = max(0, int(max_images or 0))
    can_images = bool(with_images) and skill_manager is not None and max_images > 0

    sig_obj = {"brief": brief, "style": style_id, "duration": round(duration, 3),
               "whf": [w, h, fps], "shots": shots,
               "spec": style_lib.spec_hash(style_id)}
    # 只有 grid 模式才加入 layout/grid：保持旧 linear 段的缓存签名完全不变
    if grid_norm:
        sig_obj.update({"layout": "grid", "grid": grid_norm})
    # 允许生图的段落单独记签名：同 brief 的纯图形版与配图版不能互相复用
    if can_images:
        sig_obj["images"] = max_images
    sig = _sha(sig_obj)
    sig_file = work / "output.sig"
    if out.exists() and sig_file.exists() and sig_file.read_text(encoding="utf-8").strip() == sig:
        return True, "复用", str(out)

    timeline = _timeline(duration, shots, w, h, fps)
    plan = _plan(style_id, w, h, fps)
    if grid_norm:
        plan["layout"] = "grid"
        plan["grid"] = grid_norm
    (work / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    (work / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    api = _api_text(work)
    if not api:
        return False, "引擎 API 清单导出失败", ""
    system_prompt = _system_prompt(style_id, shots, duration, w, h,
                                   layout=layout, grid=grid_norm,
                                   with_images=can_images, max_images=max_images)
    # 把运行时导出的 API 清单附在规则前，避免模型猜 API
    system_prompt = system_prompt.replace("### 输出格式", f"### 可用 API\n{api}\n\n### 输出格式")
    ctx0 = _context(brief, shots, duration, layout=layout, grid=grid_norm)
    if grid_norm:
        review_times = [round((c["start"] + c["end"]) / 2, 3)
                        for c in _grid_times(duration, grid_norm)][:4]
    else:
        review_times = [round((L["start"] + L["end"]) / 2, 3) for L in timeline["lines"]][:4]

    from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
    deadline = time.monotonic() + BUDGET_SEC
    errs = []
    scenes_path = work / "scenes.js"
    current_js = ""
    last_kind = "gate"
    force_full = False

    for k in range(1, MAX_TRIES + 1):
        if time.monotonic() > deadline:
            return False, f"styled_video 超过时间预算（{BUDGET_SEC}s）", ""

        # 首次整篇生成；之后优先原地修补（只回传报错处的最小 find/replace）。
        # 修补无法落地 / 修补后仍语法错 / 调用失败时，force_full 回退整篇重写。
        mode = "full" if (k == 1 or force_full or not current_js) else "repair"

        if mode == "repair":
            emit(f"styled_video {style_lib.label(style_id)}：第 {k}/{MAX_TRIES} 次原地修补"
                 f"（{last_kind}，只改报错处）...")
            try:
                js, applied, failed, raw = _repair_scenes(
                    current_js, errs, last_kind, cfg, style_id, shots, duration, w, h, api,
                    layout=layout, grid=grid_norm)
            except Exception as e:
                errs = [f"修补调用失败：{e}"]
                force_full = True
                emit(f"  ✗ {errs[0]}，下次回退整篇重写")
                continue
            (work / "llm" / f"styled-repair-{k}.txt").write_text(raw or "", encoding="utf-8")
            if applied == 0:
                errs = ["修补清单无法应用（find 未找到或不唯一）：" + "；".join(failed[:2])]
                force_full = True
                emit("  ✗ 修补无法应用，下次回退整篇重写")
                continue
            (work / "llm" / f"styled-patched-{k}.js").write_text(js, encoding="utf-8")
            emit(f"  · 已应用 {applied} 处修补" + (f"（{len(failed)} 处未应用）" if failed else ""))
        else:
            force_full = False
            ctx = ctx0 + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
            emit(f"styled_video {style_lib.label(style_id)}：第 {k}/{MAX_TRIES} 次生成"
                 f"（{project_label} / {duration:.1f}s）...")
            try:
                raw = _call_with_token_fallback(
                    lambda budget: call_llm_text(
                        system_prompt=system_prompt, context=ctx,
                        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
                        protocol=cfg.get("protocol", "anthropic"), provider=cfg.get("provider"),
                        thinking="disabled", max_tokens=budget, timeout=360, attempts=1),
                    max_tokens=MAX_OUT_TOKENS,
                    fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                )
            except Exception as e:
                errs = [f"调用失败：{e}"]
                force_full = True
                emit(f"  ✗ {errs[0]}")
                continue
            (work / "llm" / f"styled-raw-{k}.txt").write_text(raw or "", encoding="utf-8")
            js = _js_of(raw)

        tmp = work / f"_syn_styled_{k}.js"
        tmp.write_text(js, encoding="utf-8")
        r = _sh(["node", "--check", tmp])
        if r.returncode != 0:
            errs = [f"JS 语法错误：{(r.stderr or r.stdout)[-300:]}"]
            current_js = js
            last_kind = "syntax"
            if mode == "repair":
                force_full = True
            emit(f"  ✗ 语法错（第 {k} 次，原始输出见 work/llm/）")
            continue

        current_js = js
        scenes_path.write_text(js, encoding="utf-8")

        # 图片：LLM 在 MV.assets 里声明的素材，这里生成到本段 assets/ 并写进 plan，
        # 渲染器再把它们作为 file:// 绝对地址注入页面（本地文件，无外链）。
        if can_images:
            asset_map, asset_fail = _gen_assets(
                _asset_specs(scenes_path), work / "assets",
                skill_manager, _style_prefix(style_id), max_images, emit)
            if asset_map:
                plan["assets"] = asset_map
                (work / "plan.json").write_text(
                    json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
            if asset_fail:
                detail = "；".join(
                    f'{f["key"]}（{f["prompt"][:40]}）→ {f["error"][:100]}'
                    for f in asset_fail[:2])
                if k < MAX_TRIES:
                    errs = [
                        f"配图生成失败：{detail}。请改 MV.assets 里对应 key 的 prompt"
                        "（更短、更具体的英文描述，去掉人名/品牌/敏感内容），"
                        "或者删掉这个 key 并改用图形画；不要动其他镜头。"
                    ]
                    last_kind = "image"
                    emit("  ⚠ 配图失败，已把报错交给 LLM 修正：" + detail)
                    continue
                emit("  ⚠ 配图最终失败，继续用图形兜底渲染：" + detail)

        ok, gate_out, gate_errs = _gate(work / "timeline.json", work / "plan.json",
                                        scenes_path, work)
        (work / "llm" / f"styled-gate-{k}.txt").write_text(gate_out, encoding="utf-8")
        if not ok:
            errs = gate_errs[:3] or ["渲染前闸门未通过"]
            last_kind = "gate"
            emit("  ✗ " + "；".join(errs))
            continue
        # 硬检查：视觉模型专门看文字是否可读；对比度不足就带着问题修补/重写
        emit("  ✓ 闸门通过，检查文字可读性...")
        text_issues = _text_review(work, work / "timeline.json", work / "plan.json",
                                   scenes_path, review_times, cfg)
        if text_issues is None:
            emit("  · 文字可读性检查跳过（视觉接口不可用）")
        elif text_issues:
            msg = "文字可读性检查未通过：" + "；".join(text_issues[:2])
            if k < MAX_TRIES:
                errs = [msg + "。请换用与背景高对比的文字颜色（深底浅字/浅底深字），"
                              "必要时加 1~2px 描边或半透明底板。"]
                last_kind = "text"
                emit("  ✗ " + msg)
                continue
            emit("  ⚠ " + msg + "（已到重试上限，保留本版继续渲染，可后期 patch）")
        else:
            emit("  ✓ 文字可读性通过")
        emit(f"  ✓ 开始渲染 {w}×{h} @{fps}fps")
        rr = _sh([sys.executable, str(RENDER), "--engine", str(ENGINE),
                  "--timeline", str(work / "timeline.json"), "--plan", str(work / "plan.json"),
                  "--scenes", str(scenes_path), "--out", str(out), "--fps", str(fps),
                  "--no-gate"], stream=True)
        if rr.returncode != 0 or not out.exists():
            return False, f"渲染失败：{(rr.stderr or rr.stdout or '')[-300:]}", ""
        sig_file.write_text(sig, encoding="utf-8")
        return True, f"{out.stat().st_size / 1048576:.1f} MB", str(out)
    return False, "styled_video 3 次未通过：" + "；".join(errs[:3]), ""
