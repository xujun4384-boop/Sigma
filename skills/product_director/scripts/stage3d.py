# -*- coding: utf-8 -*-
"""product_director 的 3D 镜头管线（设备 + 真实屏幕内容）。

一个 3D 镜头 = 五步，全部确定性可复现：
  1. 让 LLM 写屏内页面（screen.html，用 ?t= 驱动，禁止 CSS 动画）
  2. 无头 Chromium 逐帧截图 → 屏幕贴图序列
  3. Blender（stage3d_scene.py，参数全走环境变量）渲染 →
  4. 透明标题层（HTML 截图）→ ffmpeg 叠加
  5. 编码成 clip.mp4，交回 product_director 拼接

本模块不含任何具体产品/题材判断：设备型号、运镜、文案都来自分镜蓝图。
"""
from __future__ import annotations

import html as _html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# 设备屏幕的取景尺寸（CSS px, 设备像素比）——与 devices.py 里屏占比一致，避免贴图被拉伸
DEVICE_VIEW = {
    "laptop": {"w": 1440, "h": 938, "dsf": 1.0},
    "phone": {"w": 393, "h": 841, "dsf": 2.4},
}
ACTIONS = {"open", "scroll", "push", "tilt", "static"}
# 设备名归一化：只认手机与笔记本两种外观，其余一律不认（不要回退成别的设备）
DEVICE_ALIAS = {
    "phone": "phone", "smartphone": "phone", "mobile": "phone",
    "手机": "phone", "移动端": "phone", "小程序": "phone",
    "laptop": "laptop", "notebook": "laptop", "macbook": "laptop",
    "笔记本": "laptop", "笔记本电脑": "laptop", "电脑": "laptop",
}
ANGLES = {"three-quarter", "front", "side"}
# 命名简写只是缺省值，真正决定机位的是 azimuth/elevation 两个连续量
ANGLE_AZEL = {"three-quarter": (29.0, 16.5), "front": (6.0, 7.0), "side": (54.0, 11.5)}
AZ_RANGE = (-78.0, 78.0)     # 0=正面；负=绕到机身另一侧（露出另一条边）
EL_RANGE = (-6.0, 46.0)      # 0=平视；正=俯视

# 运镜缺省值：(方位角变化, 仰角变化, 结束距离系数)。只是"没写数字时"的兜底，
# 真正决定运镜的是蓝图里的 stage3d.move（orbit / rise / zoom 三个连续量）。
MOVE_DEFAULTS = {
    "open": (3.0, 7.0, 0.95),
    "scroll": (2.0, 1.0, 0.96),
    "push": (1.5, 1.5, 0.90),
    "tilt": (14.0, 0.0, 0.99),
    "static": (0.8, 0.5, 0.985),
}


def _num(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def spec_of(shot: dict) -> dict | None:
    """把蓝图里的 stage3d 归一化成可执行参数；不合法返回 None。

    ⚠️ 只认识手机和笔记本两种外观。**不要**把未知设备偷偷套成笔记本——
    "Mac mini 被渲染成笔记本并贴上界面"就是这种静默回退造成的。认不出来就返回 None，
    让这一镜退回普通界面镜头。
    """
    raw = shot.get("stage3d")
    if not isinstance(raw, dict):
        return None
    device = DEVICE_ALIAS.get(str(raw.get("device") or "").strip().lower())
    if not device:
        return None
    action = str(raw.get("action") or "").strip().lower()
    if action not in ACTIONS:
        action = "push"
    if action == "open" and device != "laptop":
        action = "push"
    angle = str(raw.get("angle") or "").strip().lower()
    if angle not in ANGLES:
        angle = "three-quarter"
    az_def, el_def = ANGLE_AZEL[angle]
    az = _clamp(_num(raw.get("azimuth"), az_def), *AZ_RANGE)
    el = _clamp(_num(raw.get("elevation"), el_def), *EL_RANGE)

    # 运镜：三个连续量（绕行角度 / 抬升角度 / 结束距离），缺省才用动作预设
    mv = raw.get("move") if isinstance(raw.get("move"), dict) else {}
    d_orbit, d_rise, d_zoom = MOVE_DEFAULTS.get(action, MOVE_DEFAULTS["push"])
    orbit = _clamp(_num(mv.get("orbit"), d_orbit), -80.0, 80.0)
    rise = _clamp(_num(mv.get("rise"), d_rise), -35.0, 35.0)
    zoom = _clamp(_num(mv.get("zoom"), d_zoom), 0.55, 1.8)
    az0 = _clamp(az - orbit, *AZ_RANGE)
    el0 = _clamp(el - rise, *EL_RANGE)

    return {
        "device": device,
        "action": action,
        "angle": angle,
        "azimuth": round(az, 2),
        "elevation": round(el, 2),
        "az0": round(az0, 2),
        "el0": round(el0, 2),
        "zoom": round(zoom, 3),
        "page": str(raw.get("page") or shot.get("ui") or "").strip(),
        "open_deg": float(raw.get("open_deg") or 108),
    }


# ══════════════════════════ 1. 屏内页面 ══════════════════════════

_SCREEN_SYSTEM = """你是一位界面工程师。你要写一个**单文件 HTML**，它会被逐帧截图后贴到 3D 设备屏幕上。

硬性要求（违反任何一条都会失败）：
1. 只输出 HTML 源码本身，不要 markdown 围栏、不要解释。
2. 全部资源内联：不许外链图片/字体/脚本/CDN；图形用 CSS 或内联 SVG。
3. **禁止任何 CSS 动画、过渡、@keyframes、视频**。画面状态只能由 JS 计算。
4. 必须实现 `window.render(t)`，t 是秒。页面加载时读 `?t=` 调一次；
   同一 t 必须永远得到同一结果（截图是逐帧重放，不允许有随机、时间戳、Math.random）。
5. 画布固定为给定尺寸，`html,body{margin:0;overflow:hidden;width:Wpx;height:Hpx}`。
6. 这是"真实产品的界面"，不是示意图：要有真实的中文文案、真实的控件、真实的层级与留白，
   看起来像真机截图。禁止出现"示例""占位""Lorem"。

时间轴：整段时长 D 秒。如果这一镜有滚动/输入/点击等动作，用 render(t) 在 0→D 之间把它演完
（例如滚动用 translateY 缓动，输入用截取字符串），动作结束后保持静止。
如果这一镜画面是静止的，render(t) 里什么都不用做。"""


def _screen_user(shot_page: str, shot_ui: str, spec: dict, dur: float,
                 view: dict, ui_ctx: dict, palette: str) -> str:
    w, h = view["w"], view["h"]
    kind = ("手机竖屏（iPhone 类）" if spec["device"] == "phone"
            else "笔记本横屏（macOS 桌面 + 浏览器窗口）")
    lines = [
        f"设备：{kind}，画布 {w}×{h} CSS px。",
        f"整段时长：{dur:.2f} 秒。",
        f"这一镜屏幕上要看到的内容：{shot_page or shot_ui or '产品主界面'}",
    ]
    if shot_ui and shot_ui != shot_page:
        lines.append(f"这一镜的界面动作：{shot_ui}")
    if palette:
        lines.append(f"全片配色基调（可参考，不必照搬）：{palette}")
    if spec["device"] == "phone":
        lines.append("顶部要留出约 9% 高度的状态栏（时间/信号/电量），中间那块会被 3D 灵动岛挡住，"
                     "所以状态栏文字要靠两侧排。")
    else:
        lines.append("顶部要有 macOS 菜单栏；如果展示的是网页，就用一个带红绿灯和地址栏的浏览器窗口框住内容。")
    tokens = (ui_ctx or {}).get("tokens_css") or ""
    if tokens:
        lines.append("产品真实设计变量（尽量用这些颜色与字体）：\n" + tokens[:2500])
    digest = (ui_ctx or {}).get("digest") or ""
    if digest:
        lines.append("产品界面真值摘要：\n" + digest[:2500])
    lines.append(f"现在输出 HTML（{w}×{h}，含 window.render(t)）。")
    return "\n\n".join(lines)


def write_screen_html(shot, spec, dur, view, ui_ctx, palette, out_path: Path,
                      llm_config: dict, log=None) -> tuple[bool, str]:
    """让 LLM 写屏内页面；落盘后做结构检查。"""
    from skills.opendesign.scripts.renderer import call_llm_text, _call_with_token_fallback
    try:
        from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
    except Exception:
        LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS = 64_000, (32_000, 16_000)

    shot_page = str((shot.get("stage3d") or {}).get("page") or "")
    shot_ui = str(shot.get("ui") or "")
    ctx = _screen_user(shot_page, shot_ui, spec, dur, view, ui_ctx, palette)

    last = ""
    for attempt in range(2):
        text = _call_with_token_fallback(
            lambda budget: call_llm_text(
                system_prompt=_SCREEN_SYSTEM,
                context=(ctx if not last else ctx + "\n\n上一次生成的页面有问题：" + last),
                base_url=llm_config.get("base_url", ""),
                api_key=llm_config.get("api_key", ""),
                model=llm_config.get("model", ""),
                protocol=llm_config.get("protocol", "anthropic"),
                provider=llm_config.get("provider"),
                thinking=llm_config.get("thinking"),
                max_tokens=budget, timeout=600, attempts=1,
            ),
            max_tokens=LONG_OUTPUT_MAX_TOKENS, fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
        )
        code = _strip_fence(text or "")
        err = _check_html(code)
        if err:
            last = err
            if log:
                log(f"  · 屏内页面不合格（{err}），重写一次")
            continue
        out_path.write_text(code, encoding="utf-8")
        return True, ""
    return False, f"屏内页面生成失败：{last}"


def _strip_fence(text: str) -> str:
    t = (text or "").strip()
    m = re.search(r"```(?:html)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    return t


def _check_html(code: str) -> str:
    low = code.lower()
    if "<html" not in low and "<body" not in low:
        return "不是完整 HTML"
    if "function render" not in low and "render =" not in low and "render=" not in low:
        return "缺少 window.render(t)"
    if "@keyframes" in low:
        return "用了 @keyframes（必须是确定性逐帧）"
    for bad in ("Math.random", "Date.now", "performance.now"):
        if bad in code:
            return f"用了 {bad}（破坏确定性）"
    return ""


# ══════════════════════════ 2. 逐帧截图 ══════════════════════════

def _shoot(exe: str, html: Path, out: Path, w: int, h: int, dsf: float,
           t: float | None = None, transparent: bool = False, timeout: int = 120) -> bool:
    if out.exists():
        out.unlink()
    uri = "file:///" + html.as_posix()
    if t is not None:
        uri += f"?t={t:.4f}"
    cmd = [exe, "--headless=new", "--hide-scrollbars", "--no-sandbox",
           f"--window-size={w},{h}", "--virtual-time-budget=1000"]
    if dsf and abs(dsf - 1.0) > 1e-3:
        cmd.append(f"--force-device-scale-factor={dsf}")
    if transparent:
        cmd.append("--default-background-color=00000000")
    cmd += [f"--screenshot={out}", uri]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception:
        return False
    return out.exists() and out.stat().st_size > 1000


def capture_screen(html: Path, out_dir: Path, dur: float, fps: int, view: dict,
                   log=None) -> tuple[bool, int, str]:
    """按 fps 截出屏幕贴图序列。页面无动画时只截 1 帧并复用。"""
    from skills.blender.scripts.renderer import find_chromium
    exe = find_chromium()
    if not exe:
        return False, 0, "未找到 Chrome/Edge，无法截屏"

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("ui_*.png"):
        old.unlink()

    w, h, dsf = view["w"], view["h"], view["dsf"]

    # 先探两帧：完全一样就说明这一镜屏幕是静止的，整段复用同一张图
    probe_a = out_dir / "_a.png"
    probe_b = out_dir / "_b.png"
    if not _shoot(exe, html, probe_a, w, h, dsf, 0.0):
        return False, 0, "屏内页面首帧截图为空（页面可能有脚本错误）"
    still = True
    if dur > 0.05:
        _shoot(exe, html, probe_b, w, h, dsf, dur)
        still = probe_b.exists() and probe_a.stat().st_size == probe_b.stat().st_size
        if still:
            still = probe_a.read_bytes() == probe_b.read_bytes()
    if still:
        shutil.move(str(probe_a), str(out_dir / "ui_0001.png"))
        for p in (probe_b,):
            p.unlink(missing_ok=True)
        if log:
            log("  · 屏幕内容静止，复用单帧贴图")
        return True, 1, ""

    n = max(1, int(round(dur * fps)))
    shutil.move(str(probe_a), str(out_dir / "ui_0001.png"))
    probe_b.unlink(missing_ok=True)
    for i in range(2, n + 1):
        dst = out_dir / f"ui_{i:04d}.png"
        if not _shoot(exe, html, dst, w, h, dsf, (i - 1) / float(fps)):
            return False, 0, f"屏内页面第 {i} 帧截图失败"
        if i % 30 == 0 and log:
            log(f"  · 屏幕贴图 {i}/{n}")
    return True, n, ""


# ══════════════════════════ 3. 标题层 ══════════════════════════

_TITLE_TPL = """<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1920px;height:1080px;overflow:hidden;background:transparent}}
body{{font-family:"PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif;
 -webkit-font-smoothing:antialiased}}
.block{{position:absolute;{pos}}}
.kicker{{font-size:21px;font-weight:600;color:{accent};letter-spacing:.06em;margin-bottom:18px}}
.title{{font-size:{fs}px;line-height:1.16;font-weight:800;color:{fg};letter-spacing:-.02em;
 white-space:pre-line}}
.sub{{margin-top:20px;font-size:23px;line-height:1.5;color:{dim}}}
.rule{{margin:{rule_margin};width:78px;height:3px;background:{accent};border-radius:2px}}
</style></head><body><div class="block">
<div class="kicker">{kicker}</div><div class="title">{title}</div>
{sub}<div class="rule"></div></div></body></html>"""


def hex_rgb(s):
    """#RRGGBB / #RGB → (r,g,b) 0~1（sRGB）；解析不了返回 None。"""
    t = str(s or "").strip().lstrip("#")
    if len(t) == 3:
        t = "".join(ch * 2 for ch in t)
    if len(t) != 6:
        return None
    try:
        return tuple(int(t[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def is_dark_bg(hex_color) -> bool:
    """画布底色是不是深色（按相对亮度判断，不靠颜色名字）。"""
    rgb = hex_rgb(hex_color)
    if not rgb:
        return False
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) < 0.42


def _accent_of(style: dict) -> str:
    """强调色：优先用蓝图显式给的 style.accent，其次退回 palette 里第一个色值。"""
    acc = str((style or {}).get("accent") or "").strip()
    if hex_rgb(acc):
        return acc if acc.startswith("#") else "#" + acc
    m = re.search(r"#[0-9a-fA-F]{6}", str((style or {}).get("palette") or ""))
    return m.group(0) if m else "#2f6bff"


def make_title(shot: dict, style: dict, out_png: Path, log=None, depth: bool = False) -> bool:
    """把这一镜的标题渲成透明 PNG（3D 段没有 HTML 画面，标题单独叠加）。

    depth=True：这一层会被合成到设备后面并虚化，所以字号放大、给硬件留出压字的余地。
    """
    from skills.blender.scripts.renderer import find_chromium
    exe = find_chromium()
    if not exe:
        return False

    kicker = str(shot.get("kicker") or "").strip()
    title = str(shot.get("title") or "").strip()
    sub = str(shot.get("sub") or "").strip()
    if not (kicker or title or sub):
        return False

    # 深浅底要反过来用字色，否则深色片上的深灰标题直接看不见
    dark = is_dark_bg((style or {}).get("bg"))
    fg = "#F2F4F8" if dark else "#14161B"
    dim = "#98A1B0" if dark else "#6B7280"
    accent = _accent_of(style)

    zone = str(shot.get("title_zone") or "left").strip().lower()
    pos = {
        "left": "left:112px;top:50%;transform:translateY(-50%);width:660px;text-align:left",
        "right": "right:112px;top:50%;transform:translateY(-50%);width:660px;text-align:right",
        "top": "left:50%;top:96px;transform:translateX(-50%);width:1240px;text-align:center",
        "bottom": "left:50%;bottom:104px;transform:translateX(-50%);width:1240px;text-align:center",
    }.get(zone, "left:112px;top:50%;transform:translateY(-50%);width:660px;text-align:left")
    rule_margin = ("18px auto 0" if zone in ("top", "bottom")
                   else ("18px 0 0 auto" if zone == "right" else "18px 0 0"))

    longest = max((len(x) for x in title.split("\n")), default=0)
    fs = 78 if longest <= 7 else (66 if longest <= 10 else 54)
    if depth:
        # 背景层字号更大，设备压上来时才看得出"字在后面"
        fs = int(fs * 1.34)
    sub_html = f'<div class="sub">{_html.escape(sub)}</div>' if sub else ""

    page = _TITLE_TPL.format(pos=pos, accent=accent, fs=fs, fg=fg, dim=dim,
                             kicker=_html.escape(kicker), title=_html.escape(title),
                             sub=sub_html, rule_margin=rule_margin)
    tmp = out_png.with_suffix(".html")
    tmp.write_text(page, encoding="utf-8")
    ok = _shoot(exe, tmp, out_png, 1920, 1080, 1.0, transparent=True)
    tmp.unlink(missing_ok=True)
    if not ok and log:
        log("  · 标题层生成失败，本镜不加字")
    return ok


# ══════════════════════════ 4. 渲染 + 合成 ══════════════════════════

def render_shot(shot: dict, plan: dict, work: Path, dest: Path,
                width: int, height: int, fps: int, ui_ctx: dict,
                llm_config: dict, log=None, samples: int = 24) -> tuple[bool, str]:
    """把一个 3D 镜头渲成 mp4。"""
    log = log or (lambda _m: None)
    spec = spec_of(shot)
    if not spec:
        return False, "stage3d 参数不合法"
    dur = max(0.5, float(shot["end"]) - float(shot["start"]))
    view = DEVICE_VIEW[spec["device"]]
    tag = dest.stem or f"{int(shot.get('index') or 0):02d}"
    # 项目里只留「屏内页面」这个源文件（方便复现/调试）；屏幕贴图、Blender 帧、
    # 标题层全部放系统临时目录，编码完立即清理——不在项目里堆几十上百张 PNG
    # （与 director 的 blender 引擎一致）。
    root = work / f"s3d_{tag}"
    root.mkdir(parents=True, exist_ok=True)
    # 旧版本会把屏幕贴图/帧序列/标题落在项目里：重渲这个镜头时顺手清掉，
    # 避免升级后旧的一两百张 PNG 继续占空间。
    for legacy in (root / "frames", root / "ui"):
        shutil.rmtree(legacy, ignore_errors=True)
    (root / "title.png").unlink(missing_ok=True)
    frames = max(2, int(round(dur * fps)))

    style = plan.get("style")
    style = style if isinstance(style, dict) else {}
    palette = str(style.get("palette") or "")
    bg_hex = str(style.get("bg") or "").strip()

    # ① 屏内页面
    screen = root / "screen.html"
    ok, err = write_screen_html(shot, spec, dur, view, ui_ctx, palette, screen,
                                llm_config, log)
    if not ok:
        return False, err

    # ②③④ 屏幕贴图 / Blender 帧 / 标题层 → 临时目录，编码完随上下文清理
    with tempfile.TemporaryDirectory(prefix=f"sigma_s3d_{tag}_",
                                     ignore_cleanup_errors=True) as _tmp:
        tmp_root = Path(_tmp)
        ui_dir = tmp_root / "ui"
        frames_dir = tmp_root / "frames"
        title = tmp_root / "title.png"

        # ② 屏幕贴图
        ok, n_ui, err = capture_screen(screen, ui_dir, dur, fps, view, log)
        if not ok:
            return False, err

        # ③ Blender 渲染（设备/动作/机位全部走环境变量）
        from skills.blender.scripts import renderer as blr

        zone = str(shot.get("title_zone") or "left").strip().lower()
        # 标题在左/右 → 设备横移让位；标题在上/下 → 设备竖移 + 整体缩小，避免压住机身
        shift = {"left": -0.16, "right": 0.16}.get(zone, 0.0)
        shift_y = {"top": 0.14, "bottom": -0.14}.get(zone, 0.0)
        fit = 1.55 if (spec["device"] == "laptop" and zone in ("top", "bottom")) else 1.22
        # 上下大标题走"景深分层"：设备在最前、标题压到焦外。
        # 左右分屏时标题与设备互不重叠，不需要这层，保持清晰。
        depth = zone in ("top", "bottom") and bool(hex_rgb(bg_hex))
        if depth:
            # 推近会在结尾把设备放大 1/zoom 倍，取景余量必须按结尾算，否则尾巴会顶出画面
            fit = min(1.9, max(1.30, 1.30 / max(0.55, spec["zoom"])))
            shift_y = 0.03          # 略微下移，让机身顶沿压进标题下缘
        env = {
            "S3D_DEVICE": spec["device"],
            "S3D_ACTION": spec["action"],
            "S3D_ANGLE": spec["angle"],
            "S3D_AZIMUTH": str(spec["azimuth"]),
            "S3D_ELEVATION": str(spec["elevation"]),
            "S3D_AZ0": str(spec["az0"]),
            "S3D_EL0": str(spec["el0"]),
            "S3D_AZ1": str(spec["azimuth"]),
            "S3D_EL1": str(spec["elevation"]),
            "S3D_D0": "1.0",
            "S3D_D1": str(spec["zoom"]),
            "S3D_BG": bg_hex,
            "S3D_UI_DIR": str(ui_dir.resolve()),
            "S3D_UI_FRAMES": str(n_ui),
            "S3D_OPEN_DEG": str(spec["open_deg"]),
            "S3D_SHIFT": str(shift),
            "S3D_SHIFT_Y": str(shift_y),
            "S3D_FIT": str(fit),
            "SIGMA_BLENDER_ALPHA": "1" if depth else "",
        }
        scene = Path(blr.__file__).resolve().parent / "stage3d_scene.py"
        log(f"  · 3D 渲染 {spec['device']}/{spec['action']} {frames} 帧...")
        try:
            blr.render(scene, frames_dir, width, height, fps, frames, samples,
                       extra_env=env, timeout=1800)
        except Exception as e:
            return False, f"3D 渲染失败：{str(e)[-400:]}"

        # ④ 标题层 + 编码
        has_title = make_title(shot, style, title, log, depth=depth)
        ok, err = _encode(frames_dir, dest, fps, title if has_title else None,
                          bg_hex=bg_hex, depth=depth, width=width, height=height)
        if not ok:
            return False, err
    return True, ""


def _encode(frames_dir: Path, dest: Path, fps: int, title: Path | None,
            bg_hex: str = "", depth: bool = False,
            width: int = 1920, height: int = 1080) -> tuple[bool, str]:
    """把帧序列编码成 mp4。

    depth=True 时走三层合成：底色 → 虚化标题 → 设备（RGBA）。
    标题因此落在设备**后面**、处在另一条焦平面上，得到"硬件在前、字在后"的景深层次。
    这要求渲染时开了 film_transparent（SIGMA_BLENDER_ALPHA=1）。
    """
    ff = shutil.which("ffmpeg") or "ffmpeg"
    n = len(list(frames_dir.glob("f_*.png")))
    if n == 0:
        return False, "没有渲染出任何帧"

    has_title = bool(title and title.exists())
    if depth and hex_rgb(bg_hex):
        g = hex_rgb(bg_hex)
        col = "0x%02X%02X%02X" % tuple(int(round(c * 255)) for c in g)
        base = f"color=c={col}:s={width}x{height}:r={fps}"
        if has_title:
            sigma = max(2.4, width / 560.0)     # 1080p≈3.4：够虚但还能读
            fc = ("[1:v]format=rgba,fade=t=in:st=0:d=0.28:alpha=1,"
                  f"gblur=sigma={sigma:.1f}[fz];"
                  "[0:v][fz]overlay=0:0:format=auto[b];"
                  "[b][2:v]overlay=0:0:format=auto[v]")
            cmd = [ff, "-y", "-loglevel", "error",
                   "-f", "lavfi", "-i", base,
                   "-loop", "1", "-i", str(title),
                   "-framerate", str(fps), "-start_number", "1",
                   "-i", str(frames_dir / "f_%04d.png"),
                   "-filter_complex", fc, "-map", "[v]", "-frames:v", str(n),
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                   "-movflags", "+faststart", str(dest)]
        else:
            # 没标题也要铺底色：透明帧直接编码会被压成黑底
            fc = "[0:v][1:v]overlay=0:0:format=auto[v]"
            cmd = [ff, "-y", "-loglevel", "error",
                   "-f", "lavfi", "-i", base,
                   "-framerate", str(fps), "-start_number", "1",
                   "-i", str(frames_dir / "f_%04d.png"),
                   "-filter_complex", fc, "-map", "[v]", "-frames:v", str(n),
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                   "-movflags", "+faststart", str(dest)]
    elif has_title:
        cmd = [ff, "-y", "-loglevel", "error",
               "-framerate", str(fps), "-start_number", "1", "-i", str(frames_dir / "f_%04d.png"),
               "-loop", "1", "-i", str(title),
               "-filter_complex",
               "[1:v]format=rgba,fade=t=in:st=0:d=0.28:alpha=1[t];[0:v][t]overlay=0:0:format=auto",
               "-frames:v", str(n),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
               "-movflags", "+faststart", str(dest)]
    else:
        cmd = [ff, "-y", "-loglevel", "error",
               "-framerate", str(fps), "-start_number", "1",
               "-i", str(frames_dir / "f_%04d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
               "-movflags", "+faststart", str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not dest.exists():
        return False, "编码失败：" + (r.stderr or "")[-300:]
    return True, ""
