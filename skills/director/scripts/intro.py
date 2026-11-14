# -*- coding: utf-8 -*-
"""开场钩子 → 标题入场（intro）的固定模板。

不是 LLM 现场写 HTML：这个转场是品牌语法，固定成模板才能保证每次的缩放、
标题字号和 Sigma 标签一致。素材直接取钩子片段的**最后一帧**：
观众刚看完钩子，intro 从同一个画面开始缩小，不会出现时间倒跳。
卡片里是同一张高清静帧 + 缓慢推近，避免"缩小时画面突然换帧"。
"""
from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path

SIGMA_BG = "#07090E"
SIGMA_ACCENT = "#37C98B"
DEFAULT_TAG = "SIGMA 科普视频"


def _probe(path) -> float:
    try:
        from skills.compose_video.scripts.renderer import probe_duration
        return float(probe_duration(str(path)) or 0.0)
    except Exception:
        return 0.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _title_size(title: str) -> int:
    longest = max((len(x.strip()) for x in str(title or "").splitlines()), default=0)
    if longest <= 6:
        return 104
    if longest <= 8:
        return 88
    return 72


def _extract_still(src: Path, at: float, out_png: Path) -> None:
    ff = shutil.which("ffmpeg") or "ffmpeg"
    r = subprocess.run([
        ff, "-y", "-loglevel", "error", "-ss", f"{max(0.0, at):.3f}",
        "-i", str(src), "-frames:v", "1", str(out_png),
    ], capture_output=True, text=True, timeout=120)
    if r.returncode != 0 or not out_png.exists() or out_png.stat().st_size <= 0:
        raise RuntimeError("钩子静帧提取失败：" + (r.stderr or "")[-300:])


def concat_videos(hook: Path, intro: Path, dest: Path, W: int, H: int, fps: int) -> None:
    """钩子 + intro 顺序拼接（画面重编码，音频不要；旁白走独立音轨）。"""
    ff = shutil.which("ffmpeg") or "ffmpeg"
    fc = (
        f"[0:v]fps={fps},scale={W}:{H},setsar=1[v0];"
        f"[1:v]fps={fps},scale={W}:{H},setsar=1[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[v]"
    )
    r = subprocess.run([
        ff, "-y", "-loglevel", "error", "-i", str(hook), "-i", str(intro),
        "-filter_complex", fc, "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-movflags", "+faststart", str(dest),
    ], capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not dest.exists() or dest.stat().st_size <= 0:
        raise RuntimeError("钩子 + intro 拼接失败：" + (r.stderr or "")[-400:])


_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>intro</title>
<style>
  :root{--bg:__BG__;--fg:#EEF2F6;--dim:#8D97A6;--accent:__ACCENT__}
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:__W__px;height:__H__px;overflow:hidden;background:var(--bg)}
  body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
  #root{position:relative;width:__W__px;height:__H__px;overflow:hidden;color:var(--fg);
    background:
      radial-gradient(90% 70% at 82% 30%, rgba(55,201,139,.10) 0%, rgba(7,9,14,0) 62%),
      radial-gradient(70% 60% at 10% 84%, rgba(91,140,255,.10) 0%, rgba(7,9,14,0) 65%),
      var(--bg);}
  .env{position:absolute;inset:0;pointer-events:none;overflow:hidden}
  .blob{position:absolute;border-radius:50%;filter:blur(100px);opacity:.5}
  .b1{width:880px;height:880px;left:1000px;top:-280px;background:rgba(55,201,139,.16)}
  .b2{width:760px;height:760px;left:-240px;top:560px;background:rgba(91,140,255,.14)}
  .grid{position:absolute;inset:0;opacity:.20;
    background-image:
      linear-gradient(rgba(255,255,255,.055) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.055) 1px, transparent 1px);
    background-size:96px 96px;
    -webkit-mask-image:radial-gradient(75% 65% at 55% 45%, #000 0%, transparent 78%);
            mask-image:radial-gradient(75% 65% at 55% 45%, #000 0%, transparent 78%);}
  .vig{position:absolute;inset:0;background:radial-gradient(120% 95% at 50% 45%, transparent 42%, rgba(0,0,0,.62) 100%)}
  .visual{position:absolute;left:0;top:0;width:__W__px;height:__H__px;transform-origin:top left;
    overflow:hidden;border-radius:0;background:#05070B;
    box-shadow:0 50px 140px rgba(0,0,0,.68), 0 10px 30px rgba(0,0,0,.45);will-change:transform}
  .visual img{position:absolute;inset:0;width:__W__px;height:__H__px;display:block;object-fit:cover;
    transform-origin:center center;will-change:transform}
  .copy{position:absolute;left:__COPY_LEFT__px;top:__COPY_TOP__px;width:__COPY_WIDTH__px}
  .kicker{display:flex;align-items:center;gap:12px;font-size:18px;letter-spacing:.20em;
    color:var(--accent);font-weight:600}
  .kicker i{display:block;width:26px;height:2px;background:var(--accent);border-radius:2px}
  .title{font-size:__TITLE_SIZE__px;line-height:1.06;font-weight:800;letter-spacing:-.04em;margin-top:26px}
  .title .line{display:block;overflow:hidden;padding-bottom:6px}
  .title .inner{display:block;will-change:transform}
  .title em{font-style:normal;color:var(--accent)}
  .rule{width:86px;height:3px;background:var(--accent);border-radius:2px;margin:30px 0 26px}
  .sub{font-size:24px;line-height:1.7;color:var(--dim);max-width:680px}
  .sigma-tag{position:absolute;left:__TAG_LEFT__px;top:__TAG_TOP__px;display:flex;align-items:center;gap:14px;
    padding:16px 26px;border-radius:999px;border:1px solid rgba(255,255,255,.16);
    background:rgba(11,14,20,.80);color:#E6EBF2;font-size:23px;letter-spacing:.10em;font-weight:700}
  .sigma-tag i{width:11px;height:11px;border-radius:50%;background:var(--accent);
    box-shadow:0 0 18px rgba(55,201,139,.9)}
  .sigma-tag span{color:#8B96A6;font-weight:500;letter-spacing:.18em;font-size:14px;margin-left:4px}
  .divider{position:absolute;left:__DIV_LEFT__px;top:__DIV_TOP__px;width:1px;height:__DIV_H__px;
    background:linear-gradient(180deg, rgba(55,201,139,0) 0%, rgba(55,201,139,.55) 22%,
      rgba(255,255,255,.10) 62%, rgba(255,255,255,0) 100%)}
</style>
</head>
<body>
<div id="root" data-composition-id="root" data-start="0" data-duration="__DUR__"
     data-width="__W__" data-height="__H__">
  <div class="env"><div class="blob b1"></div><div class="blob b2"></div>
    <div class="grid"></div><div class="vig"></div></div>
  <div class="visual" id="visual">
    <img id="full" src="assets/__STILL__" alt="">
  </div>
  <div class="copy">
    <div class="kicker"><i></i>__KICKER__</div>
    <h1 class="title">__TITLE__</h1>
    <div class="rule"></div>
    <p class="sub">__SUB__</p>
  </div>
  <div class="divider"></div>
  <div class="sigma-tag"><i></i>__TAG__ <span>EP. 01</span></div>
</div>
<script src="gsap.min.js"></script>
<script>
(function () {
  const full = document.getElementById('full');
  function build() {
    const tl = gsap.timeline({ paused: true });
    window.__timelines = window.__timelines || {};
    window.__timelines['root'] = tl;

    tl.to('.b1', { x: 40, y: -20, duration: __DUR__, ease: 'sine.inOut' }, 0);
    tl.to('.b2', { x: -36, y: 26, duration: __DUR__, ease: 'sine.inOut' }, 0);

    // 钩子最后一帧：从全屏缓慢推近，缩成卡片后继续轻微推近（不换帧、不回跳）
    tl.fromTo('#full', { scale: 1.0 }, { scale: 1.09, duration: __DUR__, ease: 'sine.inOut' }, 0);

    // 2.2s 左右：原画面连续缩到一侧
    tl.to('#visual', { x: __TARGET_X__, y: __TARGET_Y__, scale: __CARD_SCALE__,
      borderRadius: 28, duration: __SHRINK_DUR__, ease: 'power3.inOut' }, __SHRINK_START__);

    // 另一侧：大标题 / 副标 / Sigma 标签
    tl.from('.kicker', { opacity: 0, y: 16, duration: .5, ease: 'power2.out' }, __TITLE_START__);
    tl.from('.title .inner', { yPercent: 112, duration: .95, stagger: .09, ease: 'power3.out' }, __TITLE_START_2__);
    tl.from('.rule', { scaleX: 0, transformOrigin: 'left center', duration: .7, ease: 'power2.out' }, __RULE_START__);
    tl.from('.sub', { opacity: 0, y: 16, duration: .6, ease: 'power2.out' }, __SUB_START__);
    tl.from('.divider', { opacity: 0, duration: .7, ease: 'power2.out' }, __DIV_START__);
    tl.from('.sigma-tag', { opacity: 0, y: 14, duration: .55, ease: 'power3.out' }, __TAG_START__);
  }
  if (full.decode) { full.decode().then(build).catch(build); }
  else if (full.complete) { build(); }
  else { full.onload = build; }
})();
</script>
</body>
</html>
"""


def build_intro_html(meta: dict) -> str:
    side = str(meta.get("side") or "right").strip().lower()
    if side not in ("left", "right"):
        side = "right"
    # 兼容模型把换行写成字面量 "\n"（而不是 JSON 转义）的情况
    title = str(meta.get("title") or "").strip().replace("\\n", "\n")
    accent_text = str(meta.get("accent") or "").strip()
    lines = [ln.strip() for ln in title.splitlines() if ln.strip()] or [title]
    title_html = ""
    for ln in lines:
        esc = html.escape(ln) or "&nbsp;"
        if accent_text:
            esc_acc = html.escape(accent_text)
            if esc_acc in esc:
                esc = esc.replace(esc_acc, f"<em>{esc_acc}</em>", 1)
        title_html += f'<span class="line"><span class="inner">{esc}</span></span>'

    sub = html.escape(str(meta.get("sub") or "").strip())
    tag = html.escape(str(meta.get("tag") or DEFAULT_TAG).strip() or DEFAULT_TAG)
    dur = float(meta.get("duration") or 4.0)
    hold = float(meta.get("hold") or 1.35)
    shrink = float(meta.get("shrink_dur") or 1.15)
    shrink_start = hold
    title_start = shrink_start + 0.3
    title_start_2 = title_start + 0.08
    rule_start = title_start + 0.55
    sub_start = title_start + 0.72
    div_start = shrink_start + 0.15
    tag_start = min(dur - 0.45, shrink_start + shrink + 0.55)

    W = float(meta.get("width") or 1920)
    H = float(meta.get("height") or 1080)
    sx, sy = W / 1920.0, H / 1080.0
    copy_left = round((96 if side == "right" else 1024) * sx)
    copy_top = round(320 * sy)
    copy_width = round(760 * sx)
    tag_left = copy_left
    tag_top = round(818 * sy)
    div_left = round((858 if side == "right" else 1008) * sx)
    div_top = round(292 * sy)
    div_h = round(520 * sy)
    target_x = round((920 if side == "right" else 96) * sx)
    target_y = round(220 * sy)
    card_scale = (900.0 * sx) / max(1.0, W)
    title_size = max(56, int(round(_title_size(title) * sx)))

    rep = {
        "__BG__": SIGMA_BG,
        "__ACCENT__": SIGMA_ACCENT,
        "__W__": str(int(W)),
        "__H__": str(int(H)),
        "__DUR__": f"{dur:.3f}",
        "__STILL__": str(meta.get("still") or "full.png"),
        "__HOLD__": f"{hold:.3f}",
        "__SHRINK_START__": f"{shrink_start:.3f}",
        "__SHRINK_DUR__": f"{shrink:.3f}",
        "__TITLE_START__": f"{title_start:.3f}",
        "__TITLE_START_2__": f"{title_start_2:.3f}",
        "__RULE_START__": f"{rule_start:.3f}",
        "__SUB_START__": f"{sub_start:.3f}",
        "__TAG_START__": f"{tag_start:.3f}",
        "__DIV_START__": f"{div_start:.3f}",
        "__TARGET_X__": str(target_x),
        "__TARGET_Y__": str(target_y),
        "__CARD_SCALE__": f"{card_scale:.5f}",
        "__COPY_LEFT__": str(copy_left),
        "__COPY_TOP__": str(copy_top),
        "__COPY_WIDTH__": str(copy_width),
        "__TAG_LEFT__": str(tag_left),
        "__TAG_TOP__": str(tag_top),
        "__DIV_LEFT__": str(div_left),
        "__DIV_TOP__": str(div_top),
        "__DIV_H__": str(div_h),
        "__TITLE_SIZE__": str(title_size),
        "__KICKER__": "SIGMA 科普",
        "__TITLE__": title_html,
        "__SUB__": sub or "&nbsp;",
        "__TAG__": tag,
    }
    out = _HTML
    for k, v in rep.items():
        out = out.replace(k, v)
    return out


def render_intro(hook_video, intro: dict, base: Path, index: int,
                 W: int, H: int, fps: int) -> Path:
    """把钩子最后一帧渲染成 intro 转场 mp4（固定模板，不走 LLM）。"""
    from skills.opendesign.scripts.renderer import render, scaffold_project

    hook = Path(hook_video)
    if not hook.exists():
        raise RuntimeError("找不到钩子片段")
    intro = intro if isinstance(intro, dict) else {}
    dur = _clamp(float(intro.get("seconds") or 4.0), 2.5, 5.5)
    clip_dur = _probe(hook) or dur
    still_time = max(0.0, clip_dur - 0.05)

    proj = Path(base) / "intro" / f"intro_{index:02d}"
    if proj.exists():
        shutil.rmtree(proj, ignore_errors=True)
    scaffold_project(proj, f"intro_{index:02d}")
    assets = proj / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    still = assets / "full.png"
    _extract_still(hook, still_time, still)

    hold = min(1.35, dur * 0.36)
    shrink_dur = min(1.15, dur * 0.30)
    meta = {
        "duration": dur, "hold": hold, "shrink_dur": shrink_dur,
        "width": W, "height": H, "fps": fps,
        "still": still.name,
        "title": str(intro.get("title") or "").strip(),
        "accent": str(intro.get("accent") or "").strip(),
        "sub": str(intro.get("sub") or "").strip(),
        "tag": str(intro.get("tag") or DEFAULT_TAG).strip(),
        "side": str(intro.get("side") or "right").strip().lower(),
    }
    (proj / "index.html").write_text(build_intro_html(meta), encoding="utf-8")

    out = Path(base) / "panels" / f"seg_{index:02d}_intro.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    render(proj, out, fps=fps)
    return out
