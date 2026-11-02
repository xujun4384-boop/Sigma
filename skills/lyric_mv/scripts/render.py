# -*- coding: utf-8 -*-
"""逐帧渲染 + 渲染前闸门（通用，不依赖题材）

引擎契约：engine/stage.html 提供 window.seek(t) / window.probe(t)。
本脚本负责注入 TL / PLAN、加载 scenes.js、跑闸门、逐帧截图、交 ffmpeg 混流。

闸门（渲染前，抓 LLM 画面代码的问题）：
  1 运行时   任一抽查时刻抛错 -> 失败，回报错误原文
  2 确定性   同一 t 渲染两次，两次都从 0 顺序走到该时刻（与真实渲染路径一致），
             画面必须有容差地一致 —— 抓 Math.random / Date.now / 外部状态累积
  3 覆盖度   scenes 条数必须等于歌词行数
"""
import argparse
import asyncio
import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

ARGS = ["--allow-file-access-from-files", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--disable-lcd-text"]

# 与 opendesign 闸门同一套口径：先 4×4 均值降采样抹平光栅噪声，再按容差判等。
# 光栅噪声（filter/blur 图层的复用缓存 vs 重新光栅化）实测降采样后单点差 ≤12；
# 真正的不确定性（随机数/当前时间）会造成整片或大块差异，远超这个量级。
_FRAME_DOWNSCALE = 4
_FRAME_MAX_DIFF = 12
_FRAME_MEAN_DIFF = 0.5


def _same_frame(a: bytes, b: bytes) -> bool:
    """两帧是否有容差地相同；缺 PIL 时退回字节比较。"""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return a == b
    try:
        ia = Image.open(io.BytesIO(a)).convert("L")
        ib = Image.open(io.BytesIO(b)).convert("L")
    except Exception:
        return False
    k = _FRAME_DOWNSCALE
    w, h = ia.width // k, ia.height // k
    if ia.size != ib.size or w < 1 or h < 1:
        return False
    ia = ia.resize((w, h), Image.BOX)
    ib = ib.resize((w, h), Image.BOX)
    px = list(ImageChops.difference(ia, ib).getdata())
    return max(px) <= _FRAME_MAX_DIFF and sum(px) / len(px) <= _FRAME_MEAN_DIFF


def _mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _canvas_size(tl, plan=None):
    """从 timeline/plan 读画布尺寸；缺省 1280×720（lyric_mv 的老默认）。"""
    c = (tl.get("canvas") or (plan or {}).get("canvas") or {})
    try:
        w = int(c.get("width") or tl.get("width") or 1280)
        h = int(c.get("height") or tl.get("height") or 720)
    except (TypeError, ValueError):
        w, h = 1280, 720
    return max(320, w), max(180, h)


def _plan_with_assets(plan):
    """把 plan.assets 里的本地路径转成 file:// 绝对地址。

    渲染机无外网，素材只认本地文件；不存在的直接剔除，
    引擎侧 loadImages() 就不会多等一张永远加载不出来的图。
    """
    out = dict(plan or {})
    assets = out.get("assets")
    if isinstance(assets, dict):
        uris = {}
        for key, value in assets.items():
            p = Path(str(value)).expanduser()
            if p.is_file():
                uris[str(key)] = p.resolve().as_uri()
        out["assets"] = uris
    return out


async def _open(pw, engine, tl, plan, scenes_js):
    b = await pw.chromium.launch(args=ARGS)
    W, H = _canvas_size(tl, plan)
    plan = _plan_with_assets(plan)
    pg = await b.new_page(viewport={"width": W, "height": H})
    await pg.add_init_script(
        f"window.TL={json.dumps(tl, ensure_ascii=False)};"
        f"window.PLAN={json.dumps(plan, ensure_ascii=False)};")
    await pg.goto(Path(engine).resolve().as_uri(), wait_until="load")
    await pg.wait_for_function("window.ready === true", timeout=30000)
    if scenes_js:
        await pg.add_script_tag(path=str(Path(scenes_js).resolve()))
    return b, pg


def sample_times(tl, plan, n=48):
    """抽查时刻：覆盖每句中间、每句交界、每个卡、片头尾，以及随机点。"""
    lines = tl.get("lines") or []
    ts = []
    for L in lines:
        ts.append(round((L["start"] + L["end"]) / 2, 3))
        ts.append(round(max(0, L["start"] - 0.25), 3))
    dur = tl.get("duration", 0)
    if lines:
        ts += [round(max(0, L["start"] - 1.5), 3) for L in lines[:3]]
        ts += [round(min(dur - 0.1, lines[-1]["end"] + 1.5), 3)]
    ts += [0.5, 1.5, 3.0]
    if dur > 2:
        ts += [round(dur * k / 12, 3) for k in range(1, 12)]
    out, seen = [], set()
    for t in ts:
        t = max(0.0, min(dur - 1e-3, t))
        key = round(t, 2)
        if key not in seen:
            seen.add(key)
            out.append(t)
    if len(out) > n:
        step = len(out) / n
        out = [out[int(i * step)] for i in range(n)]
    return out


def _shot_errors(shots, duration):
    """MV.shots 覆盖度校验：必须从 0 连续铺满到歌曲结束，不能空档/重叠。"""
    errs, clean = [], []
    for i, s in enumerate(shots or []):
        try:
            a, b = float(s.get("start")), float(s.get("end"))
        except (TypeError, ValueError):
            errs.append(f"第 {i + 1} 个镜头 start/end 不是数字")
            continue
        clean.append((a, b, i))
    if not clean:
        return errs or ["MV.shots 为空"]
    clean.sort()
    if clean[0][0] > 0.05:
        errs.append(f"MV.shots 从 {clean[0][0]:.2f}s 开始，没有覆盖片头 0s")
    prev_end = 0.0
    for a, b, i in clean:
        if b <= a:
            errs.append(f"第 {i + 1} 个镜头 start >= end（{a:.2f}→{b:.2f}s）")
            continue
        if a - prev_end > 0.05:
            errs.append(f"第 {i + 1} 个镜头与上一个之间有空档 {prev_end:.2f}→{a:.2f}s")
        elif prev_end - a > 0.05:
            errs.append(f"第 {i + 1} 个镜头与上一个重叠 {a:.2f}→{prev_end:.2f}s")
        prev_end = max(prev_end, b)
    if duration and abs(prev_end - duration) > 0.1:
        errs.append(f"MV.shots 结束于 {prev_end:.2f}s，但歌曲时长 {duration:.2f}s")
    return errs


async def gate(engine, tl, plan, scenes_js, times=None):
    """返回 (ok, 详情字符串)。times 给定时只抽查这些时刻（供逐批校验用）。"""
    lines = tl.get("lines") or []
    errs, notes = [], []
    async with async_playwright() as pw:
        b, pg = await _open(pw, engine, tl, plan, scenes_js)
        try:
            # 版式必须由编导显式选择；可选清单从引擎实时读，避免校验器和引擎各抄一份
            styles = await pg.evaluate("()=> (window.MV && window.MV.lyricStyles) || []")
            ls = (plan or {}).get("lyricStyle")
            if not ls:
                errs.append("plan.lyricStyle 未声明：必须从 " + " / ".join(styles) + " 里显式选一个"
                            "（不设默认，因为版式决定画面上哪块要留白）")
            elif styles and ls not in styles:
                errs.append(f'plan.lyricStyle="{ls}" 不认识，只能从 ' + " / ".join(styles) + " 里选")
            n_sc = await pg.evaluate("()=> (window.MV && window.MV.scenes || []).length")
            n_sh = await pg.evaluate("()=> (window.MV && window.MV.shots || []).length")
            if n_sh:
                # 叙事型：镜头按绝对时间覆盖，不再按歌词行数一一对应
                shots = await pg.evaluate(
                    "()=> (window.MV.shots || []).map(s => ({start:s.start,end:s.end}))")
                errs.extend(_shot_errors(shots, tl.get("duration", 0)))
                exp = (plan or {}).get("_story_ranges")
                if isinstance(exp, list) and exp:
                    try:
                        got = sorted([[float(s["start"]), float(s["end"])] for s in shots])
                        want = sorted([[float(a), float(b)] for a, b in exp])
                        if len(got) != len(want):
                            errs.append(
                                f"MV.shots 有 {len(got)} 个镜头，但故事蓝图是 {len(want)} 个")
                        else:
                            bad = next((i for i, (g, e) in enumerate(zip(got, want))
                                        if abs(g[0] - e[0]) > 0.05 or abs(g[1] - e[1]) > 0.05), None)
                            if bad is not None:
                                errs.append(
                                    f"第 {bad + 1} 个镜头时间与故事蓝图不一致："
                                    f"{got[bad][0]:.2f}~{got[bad][1]:.2f}s vs "
                                    f"{want[bad][0]:.2f}~{want[bad][1]:.2f}s")
                    except (TypeError, ValueError):
                        errs.append("MV.shots 结构无法与故事蓝图对齐")
            elif lines and n_sc != len(lines):
                errs.append(f"MV.scenes 有 {n_sc} 条，但歌词有 {len(lines)} 行，必须一一对应")
            ts = list(times) if times else sample_times(tl, plan)
            errored, det_bad = [], []
            print(f"  闸门 · 运行时：抽查 {len(ts)} 个时刻", flush=True)
            for k, t in enumerate(ts, 1):
                p = await pg.evaluate("t => window.probe(t)", t)
                if p.get("error"):
                    errored.append((t, p["error"][:160]))
                    continue
                if k % 12 == 0 and k < len(ts):
                    print(f"    校验 {k}/{len(ts)}", flush=True)
            # 确定性：同一 t 渲染两次，两次都从 0 顺序走到 t（与真实渲染路径一致），
            # 4×4 降采样后按容差比对 —— 抓随机数 / 当前时间 / 外部状态累积。
            print("  闸门 · 确定性校验", flush=True)
            for t in ts[::max(1, len(ts) // 6)][:6]:
                await pg.evaluate("x => window.seek(x)", 0.0)
                await pg.evaluate("x => window.seek(x)", t)
                a = await pg.screenshot(type="png")
                await pg.evaluate("x => window.seek(x)", 0.0)
                await pg.evaluate("x => window.seek(x)", t)
                c = await pg.screenshot(type="png")
                if not _same_frame(a, c):
                    det_bad.append((t, hashlib.md5(a).hexdigest()[:8],
                                    hashlib.md5(c).hexdigest()[:8]))
            if errored:
                errs.append(f"{len(errored)}/{len(ts)} 个时刻画面代码抛错，例：t={errored[0][0]} "
                            f"{errored[0][1]}")
            if det_bad:
                errs.append(f"确定性失败：{len(det_bad)} 个时刻两次渲染像素不一致（"
                            f"例 t={det_bad[0][0]} {det_bad[0][1]}≠{det_bad[0][2]}）"
                            f"—— 画面代码里不能用 Math.random / Date.now / 累积外部状态")
            notes.append(f"抽查 {len(ts)} 个时刻｜抛错 {len(errored)}｜不确定 {len(det_bad)}")
        finally:
            await b.close()
    return (not errs), errs, notes


async def render_frames(engine, tl, plan, scenes_js, out_mp4, audio, proc_fps,
                        t_from=0.0, t_to=None):
    dur, fps = tl["duration"], proc_fps
    """t_from/t_to：只渲染这一段（秒）。用于快速试效果，不必等整片。"""
    if t_to is None or t_to > dur:
        t_to = dur
    t_from = max(0.0, min(t_from, t_to - 0.05))
    span = max(0.05, t_to - t_from)
    total = max(1, int(round(span * fps)))
    # 音频/输出路径先验：不存在就别启动 ffmpeg，否则只会得到"管道被重置"这种难懂的报错
    if audio and not Path(audio).exists():
        raise RuntimeError(f"音频文件不存在：{audio}")
    if not out_mp4:
        raise RuntimeError("未指定输出路径")
    Path(out_mp4).parent.mkdir(parents=True, exist_ok=True)
    probe = await asyncio.create_subprocess_exec(
        *["ffmpeg", "-y", "-v", "error",
          "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
          *( ["-ss", f"{t_from:.3f}", "-i", str(Path(audio).resolve())] if audio else [] ),
          "-c:v", "libx264", "-preset", "medium", "-crf", "18",
          "-pix_fmt", "yuv420p", "-r", str(fps),
          *( ["-c:a", "aac", "-b:a", "192k", "-shortest"] if audio else [] ),
          str(Path(out_mp4).resolve())],
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE)

    print(f"开始渲染：{total} 帧 @ {fps}fps（{span:.1f}s）", flush=True)
    t_start = time.monotonic()
    last_report = t_start
    async with async_playwright() as pw:
        b, pg = await _open(pw, engine, tl, plan, scenes_js)
        try:
            for i in range(total):
                await pg.evaluate("t => window.seek(t)", t_from + i / fps)
                shot = await pg.screenshot(type="png")
                probe.stdin.write(shot)
                done = i + 1
                now = time.monotonic()
                # 每 2 秒报一次：百分比 / 帧数 / 已用 / 剩余 / 速度。
                # 管道被 drain 一下，避免 ffmpeg 缓冲把进度憋住。
                if now - last_report >= 2.0 or done == total:
                    last_report = now
                    await probe.stdin.drain()
                    elapsed = now - t_start
                    speed = done / max(elapsed, 1e-6)
                    eta = (total - done) / max(speed, 1e-6)
                    print(f"  渲染 {done * 100.0 / total:5.1f}%  {done}/{total} 帧"
                          f"｜已用 {_mmss(elapsed)}｜剩余 {_mmss(eta)}"
                          f"｜{speed:.1f} 帧/秒", flush=True)
            await probe.stdin.drain()
        finally:
            await b.close()
    probe.stdin.close()
    err = (await probe.stderr.read()).decode("utf-8", "ignore")
    rc = await probe.wait()
    if rc != 0:
        raise RuntimeError("ffmpeg 失败：" + err[-500:])
    return total


async def capture_shots(engine, tl, plan, scenes_js, times, out_dir):
    """按时刻抽静态截图（给「截图自查」用）。整幅按时间轴画布尺寸，不做缩放，
    保证视觉模型看到的就是成片构图。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    async with async_playwright() as pw:
        b, pg = await _open(pw, engine, tl, plan, scenes_js)
        try:
            for i, t in enumerate(times):
                await pg.evaluate("t => window.seek(t)", t)
                await pg.screenshot(path=str(out / f"f_{i:02d}.png"))
                n += 1
        finally:
            await b.close()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--timeline", required=True)
    ap.add_argument("--plan", default="")
    ap.add_argument("--scenes", required=True, help="scenes.js（LLM 写的画面代码）")
    ap.add_argument("--audio", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--from", dest="t_from", type=float, default=0.0,
                    help="只渲染这一段：起始秒（试效果用，不必等整片）")
    ap.add_argument("--to", dest="t_to", type=float, default=None,
                    help="只渲染这一段：结束秒")
    ap.add_argument("--gate-only", action="store_true")
    ap.add_argument("--no-gate", action="store_true",
                    help="调用方已经过闸门时跳过渲染前的重复校验")
    ap.add_argument("--times", default="",
                    help="只抽查这些时刻（逗号分隔），用于逐批运行时校验")
    ap.add_argument("--shots", default="",
                    help="按这些时刻抽截图（逗号分隔），配合 --shots-out 使用")
    ap.add_argument("--shots-out", default="", help="截图输出目录")
    args = ap.parse_args()

    # utf-8-sig：手工用记事本改过的 plan.json / timeline.json 会带 BOM，
    # 普通 utf-8 读会直接抛 JSONDecodeError，这里顺手兼容掉。
    tl = json.loads(Path(args.timeline).read_text(encoding="utf-8-sig"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig")) if args.plan else {}

    times = [float(x) for x in args.times.split(",") if x.strip()] if args.times else None

    # 抽帧模式：不跑闸门、不渲染，只出图（供视觉自查）
    if args.shots:
        shots = [float(x) for x in args.shots.split(",") if x.strip()]
        n = asyncio.run(capture_shots(args.engine, tl, plan, args.scenes, shots,
                                      args.shots_out or "."))
        print(f"抽帧完成：{n} 张 → {args.shots_out}")
        return 0

    if not args.no_gate:
        ok, errs, notes = asyncio.run(gate(args.engine, tl, plan, args.scenes, times))
        for n in notes:
            print(n)
        if not ok:
            print("❌ 渲染前闸门未通过：")
            for e in errs:
                print("   - " + e)
            return 1
        print("✅ 渲染前闸门通过")
    if args.gate_only:
        return 0

    total = asyncio.run(render_frames(args.engine, tl, plan, args.scenes,
                                      args.out, args.audio, args.fps,
                                      args.t_from, args.t_to))
    print(f"done -> {args.out} ({total} 帧, {Path(args.out).stat().st_size / 1048576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
