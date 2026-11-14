# -*- coding: utf-8 -*-
"""lyric_mv → Remotion 渲染 / 闸门入口。

约定：out_dir 里已经有 pipeline 产出的 timeline.json / plan.json，
画面组件已经生成到 remotion_runtime/src/scenes/generated/ 并同步进 registry.ts。

用法：
  python scripts/render_mv.py <out_dir>                       # 整片
  python scripts/render_mv.py <out_dir> --still 12.5          # 单帧
  python scripts/render_mv.py <out_dir> --gate --times 3,9,15 # 闸门：抽帧 + 确定性
  python scripts/render_mv.py <out_dir> --no-audio            # 不出声

产物：
  <out_dir>/remotion-props.json   实际传给合成的 props
  <out_dir>/mv.mp4                成片（有音频就混进去）
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO_EXT = (".wav", ".mp3", ".m4a", ".flac")


def _log(msg: str) -> None:
    print(f"[remotion] {msg}", flush=True)


def _run(cmd: str, timeout: int = 3600, env: dict | None = None) -> subprocess.CompletedProcess:
    _log(cmd)
    proc = subprocess.run(
        cmd, cwd=str(ROOT), shell=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, env=env,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").splitlines()[-25:])
        raise RuntimeError(f"渲染失败（退出码 {proc.returncode}）：{tail}")
    return proc


def _find_audio(out_dir: Path):
    for name in ("song.wav", "song.mp3", "song.m4a"):
        p = out_dir / name
        if p.exists():
            return p
    for p in sorted(out_dir.iterdir()):
        if p.suffix.lower() in AUDIO_EXT:
            return p
    return None


def build_props(out_dir: Path, fps: int, width: int, height: int, strict: bool = False) -> Path:
    # utf-8-sig：这些 JSON 可能被编辑器 / PowerShell 写成带 BOM 的 UTF-8
    timeline = json.loads((out_dir / "timeline.json").read_text(encoding="utf-8-sig"))
    plan_path = out_dir / "render-plan.json"
    if not plan_path.exists():
        plan_path = out_dir / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    timeline.setdefault("fps", fps)
    if "duration" not in timeline:
        raise ValueError("timeline.json 缺少 duration，无法确定片长")
    props = {"timeline": timeline, "plan": plan, "fps": fps, "width": width, "height": height}
    if strict:
        props["strict"] = True
    path = out_dir / "remotion-props.json"
    path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _still(props: Path, frame: int, dst: Path) -> None:
    _run(f'npx remotion still src/index.ts LyricMV "{dst}" --frame={frame} --props="{props}"', timeout=900)


def _img_diff(a: Path, b: Path) -> float:
    """4×4 均值降采样后逐像素比平均差：抹平光栅噪声，真实不确定性仍会被拦下。"""
    try:
        from PIL import Image
    except Exception:
        return 0.0
    pa = list(Image.open(a).convert("RGB").resize((4, 4), Image.BOX).getdata())
    pb = list(Image.open(b).convert("RGB").resize((4, 4), Image.BOX).getdata())
    total = 0
    for p, q in zip(pa, pb):
        for x, y in zip(p, q):
            total += abs(x - y)
    return total / max(1, len(pa) * 3)


def _brightness(path: Path, top: float = 0.30) -> float:
    """画面主体区（避开顶部歌词带）的平均亮度，用来抓『世界层没画出来』的黑帧。"""
    try:
        from PIL import Image
    except Exception:
        return 255.0
    im = Image.open(path).convert("L")
    w, h = im.size
    crop = im.crop((0, int(h * top), w, h)).resize((32, 32), Image.BOX)
    px = list(crop.getdata())
    return sum(px) / max(1, len(px))


def gate(out_dir: Path, times, fps: int, width: int, height: int) -> int:
    props = build_props(out_dir, fps, width, height, strict=True)
    gdir = out_dir / "_gate"
    gdir.mkdir(exist_ok=True)
    bad = 0
    for t in times:
        dst = gdir / f"g-{t:07.2f}.png"
        try:
            _still(props, int(round(t * fps)), dst)
            bright = _brightness(dst)
            if bright < 6:
                print(f"- t={t:.3f} 画面几乎纯黑（亮度 {bright:.1f}）：世界层没渲染出来", flush=True)
                bad += 1
        except RuntimeError as ex:
            msg = " ".join(str(ex).split())
            print(f"- t={t:.3f} 运行时报错：{msg[-260:]}", flush=True)
            bad += 1
    if times:
        t = times[0]
        a, b = gdir / "_det_a.png", gdir / "_det_b.png"
        try:
            _still(props, int(round(t * fps)), a)
            _still(props, int(round(t * fps)), b)
            diff = _img_diff(a, b)
            if diff > 3.0:
                print(f"- t={t:.3f} 确定性不通过：同一帧两次渲染平均差 {diff:.2f}", flush=True)
                bad += 1
        except RuntimeError as ex:
            print(f"- t={t:.3f} 确定性抽帧失败：{' '.join(str(ex).split())[-200:]}", flush=True)
            bad += 1
    print(f"GATE {'FAIL' if bad else 'OK'}", flush=True)
    return 0 if bad == 0 else 1


def render_still(props: Path, seconds: float, dst: Path, fps: int) -> Path:
    _still(props, int(round(seconds * fps)), dst)
    return dst


def _pixel_config(out_dir: Path) -> dict | None:
    """读 look.json 里的像素化配置。

    {"pixel": {"block": 4, "colors": 24}} → 整帧像素化；没有这个字段就原样输出。
    像素化在渲染出口统一做，画面代码与角色组件都不用关心画风。
    """
    p = out_dir / "look.json"
    if not p.exists():
        return None
    try:
        look = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        _log("look.json 解析失败，按原样输出")
        return None
    px = look.get("pixel") if isinstance(look, dict) else None
    if px is True:
        px = {}
    if not isinstance(px, dict):
        return None
    try:
        block = int(px.get("block") or 4)
        colors = int(px.get("colors") or 24)
    except (TypeError, ValueError):
        _log("look.pixel 参数不合法，按原样输出")
        return None
    return {"block": max(1, min(16, block)), "colors": max(2, min(256, colors))}


def _pixelate(src: Path, dst: Path, out_dir: Path, block: int, colors: int) -> Path:
    """整帧像素化（含字幕）：降采样 → 调色板量化 → 最近邻放大。

    降采样用 area 求块内均色，paletteuse 关抖动限制调色板，最后 neighbor 放大成硬边像素块。
    """
    pal = out_dir / "_palette.png"
    _run(
        f'ffmpeg -y -loglevel error -i "{src}" -vf '
        f'"scale=iw/{block}:ih/{block}:flags=area,'
        f'palettegen=max_colors={colors}:stats_mode=full" '
        f'-frames:v 1 "{pal}"', timeout=900,
    )
    chain = (f"scale=iw/{block}:ih/{block}:flags=area[a];"
             f"[a][1:v]paletteuse=dither=none[b];"
             f"[b]scale=iw*{block}:ih*{block}:flags=neighbor")
    _run(
        f'ffmpeg -y -loglevel error -i "{src}" -i "{pal}" -filter_complex "{chain}" '
        f'-c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p -an "{dst}"',
        timeout=1800,
    )
    pal.unlink(missing_ok=True)
    _log(f"像素化完成 → {dst.name}")
    return dst


def render_video(props: Path, out_dir: Path, audio: Path | None) -> Path:
    """整片渲染。Remotion 的进度是 \\r 刷新的，逐行读不到，所以另起心跳线程
    每 30 秒吐一行——否则用户在漫长的渲染期里看不到任何输出，会以为卡死。"""
    raw = out_dir / "_video_only.mp4"
    stop = threading.Event()
    t0 = time.time()

    def beat() -> None:
        while not stop.wait(30):
            _log(f"渲染中… {int(time.time() - t0)}s（进度条由 Remotion 内部刷新，这里只报心跳）")

    th = threading.Thread(target=beat, daemon=True)
    th.start()
    env = os.environ.copy()
    # Remotion 子进程的 FFmpeg 临时文件也放本次工作目录：系统 Temp 偶发拒绝写入，
    # 不能依赖临时目录的清理策略。工作目录会随项目续跑保留，最终只留下 mv.mp4。
    render_tmp = out_dir / "_remotion_tmp"
    render_tmp.mkdir(exist_ok=True)
    env["TEMP"] = env["TMP"] = str(render_tmp)
    binaries = ""
    ffmpeg = shutil.which("ffmpeg")
    if os.name == "nt" and ffmpeg:
        binaries = f' --binaries-directory="{Path(ffmpeg).parent}"'
    try:
        # Windows 上并行编码会先写临时 pre-encode.mp4；直接编码到目标文件更稳。
        _run(f'npx remotion render src/index.ts LyricMV "{raw}" --props="{props}" '
             f'--disallow-parallel-encoding{binaries}', env=env)
    finally:
        stop.set()
    _log(f"画面渲染完成，用时 {int(time.time() - t0)}s")

    px = _pixel_config(out_dir)
    if px:
        _log(f"像素化：1/{px['block']} 分辨率（{px['colors']} 色，含字幕）")
        pxy = out_dir / "_video_pixel.mp4"
        try:
            _pixelate(raw, pxy, out_dir, px["block"], px["colors"])
            raw.unlink(missing_ok=True)
            raw = pxy
        except RuntimeError as ex:
            # 像素化失败不能让整条片子没了：保留原样输出，并在日志里说清楚
            _log("像素化失败，按原样输出：" + " ".join(str(ex).split())[-200:])

    if not audio:
        final = out_dir / "mv.mp4"
        raw.replace(final)
        return final
    final = out_dir / "mv.mp4"
    _run(
        f'ffmpeg -y -loglevel error -i "{raw}" -i "{audio}" '
        f'-c:v copy -c:a aac -b:a 192k -shortest "{final}"'
    )
    raw.unlink(missing_ok=True)
    if out_dir.joinpath("mv.mp4").exists():
        _log(f"混音完成 → {final.name}")
    return final


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--still", type=float, default=None, help="只渲这一秒的静帧")
    ap.add_argument("--sheet", default="", help="渲染角色定妆照（CharSheet），值为角色名")
    ap.add_argument("--sheet-out", default="", help="定妆照输出路径")
    ap.add_argument("--strict", action="store_true", help="镜头崩溃不要兜底，直接失败（开发/闸门用）")
    ap.add_argument("--gate", action="store_true", help="闸门：抽帧 + 确定性校验")
    ap.add_argument("--times", default="", help="闸门抽帧时刻，逗号分隔（秒）")
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    if not out_dir.exists():
        _log(f"out_dir 不存在：{out_dir}")
        return 2

    if args.sheet:
        out = Path(args.sheet_out).resolve() if args.sheet_out else (out_dir / f"sheet-{args.sheet}.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        props = out_dir / "sheet-props.json"
        props.write_text(json.dumps({"who": args.sheet}, ensure_ascii=False), encoding="utf-8")
        _run(f'npx remotion still src/index.ts CharSheet "{out}" --frame=0 --props="{props}"', timeout=900)
        print(out)
        return 0 if out.exists() else 1

    if args.gate:
        times = [float(x) for x in args.times.split(",") if x.strip()]
        if not times:
            _log("--gate 需要 --times")
            return 2
        return gate(out_dir, times, args.fps, args.width, args.height)

    props = build_props(out_dir, args.fps, args.width, args.height, strict=args.strict)

    if args.still is not None:
        dst = out_dir / f"still-{args.still:.2f}.png"
        print(render_still(props, args.still, dst, args.fps))
        return 0

    audio = None if args.no_audio else _find_audio(out_dir)
    if audio:
        _log(f"音轨：{audio.name}")
    final = render_video(props, out_dir, audio)
    print(final)
    return 0


if __name__ == "__main__":
    sys.exit(main())
