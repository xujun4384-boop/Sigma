# -*- coding: utf-8 -*-
"""逐帧保真录制器：把 painter.html 渲染成 mp4。

对标 PDoomVideo 的 render.mjs 逐帧路径（而非 recorder.py 的实时录屏 webm），
因为 p5.brush 是重水墨渲染，实时录屏会掉帧/糊。本模块对每一帧独立调用
`window.renderAt(t)` 拿无损数据，再用 ffmpeg image2pipe 从 stdin 合成 mp4。

关键：帧是 t 的纯函数，因此可并行（选项），无序渲染结果一致。
"""
import asyncio
import argparse
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("animation_painter.frame_renderer")

DEFAULT_CRF = 17  # 同 PDoomVideo final 编码

# headless 下必须启用真实 GPU（ANGLE/D3D11）：默认软渲染时
# 读回 WEBGL 画布（drawImage/toDataURL）每帧可慢到 14s；
# 用原版 PDoomVideo render.mjs 同款参数后单帧 ~0.9s（96 帧实测）。
BROWSER_ARGS = [
    "--allow-file-access-from-files",
    "--ignore-gpu-blocklist",
    "--use-angle=d3d11",
    "--enable-gpu-rasterization",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
]


def _ffmpeg_avail() -> bool:
    return shutil.which("ffmpeg") is not None


def _split_html(html_path):
    """把 html_path 拆成 (真实文件路径, 查询串)。

    html_path 可能带 `?core=xxx.js`（引擎章节注入通道）。存在性校验/Path 解析必须
    用剥离 query 后的真实文件路径；而浏览器打开的 URL 要保留 query 才能触发注入。
    """
    s = str(html_path)
    if "?" in s:
        f, q = s.split("?", 1)
        return f, "?" + q
    return s, ""


async def _render_frames(html_path, duration, fps, width, height, workers, quality):
    from playwright.async_api import async_playwright
    total = int(round(duration * fps))
    os.makedirs(_tmp_dir(), exist_ok=True)  # will set below
    # 用内存管道给 ffmpeg? 这里简化：每帧 JPEG 直接进 ffmpeg stdin（单 worker）。
    # 并行时改为写临时帧文件再合成。
    pass


# 为避免过度设计，采用与 PDoomVideo clip 一致的单 worker 流式管线，
# 但保留 workers>1 时降级为"多页并行写临时帧目录，再 ffmpeg 合成"的通用实现。
async def render_to_mp4(html_path: str, output_path: str, duration: float = 8,
                        fps: int = 24, width: int = 1920, height: int = 1080,
                        workers: int = 1, quality: float = 0.94,
                        audio_path: str = None) -> str:
    """渲染 HTML 动画为 mp4。返回输出路径。"""
    fpath, q = _split_html(html_path)
    html_abs = Path(fpath).resolve()
    out_abs = Path(output_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    total = int(round(duration * fps))
    file_url = html_abs.as_uri() + q

    _validate(html_abs, audio_path, total)

    if workers > 1:
        with tempfile.TemporaryDirectory() as frames_dir:
            await _render_frames_to_dir(file_url, frames_dir, total, fps, width, height, workers, quality)
            _encode_from_dir(frames_dir, out_abs, fps, width, height, audio_path)
    else:
        await _render_stream_into_ffmpeg(file_url, out_abs, total, fps, width, height, quality, audio_path)

    size_mb = out_abs.stat().st_size / 1024 / 1024 if out_abs.exists() else 0
    return {
        "output_path": str(out_abs),
        "duration": duration,
        "fps": fps,
        "resolution": f"{width}x{height}",
        "frames": total,
        "size_mb": round(size_mb, 1),
    }


def _validate(html_abs: Path, audio_path, total: int):
    if not html_abs.exists():
        raise FileNotFoundError(f"HTML 不存在: {html_abs}")
    if total <= 0:
        raise ValueError("duration*fps 必须大于 0")
    if audio_path and not Path(audio_path).exists():
        raise FileNotFoundError(f"音频不存在: {audio_path}")


async def _render_stream_into_ffmpeg(file_url, out_abs, total, fps, width, height, quality, audio_path):
    """单 worker：每帧 renderAt(t) 出新 JPEG，直接喂 ffmpeg image2pipe（带音频则混流）。"""
    from playwright.async_api import async_playwright
    if not _ffmpeg_avail():
        raise RuntimeError("未找到 ffmpeg，请安装并加入 PATH。")

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=BROWSER_ARGS)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(file_url, wait_until="networkidle")
        await page.wait_for_function("window.ready === true", timeout=60000)
        await page.evaluate("() => { window.ready = undefined; }")  # no-op safety

        fps_arg = str(fps)
        if audio_path:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe",
                "-framerate", fps_arg, "-c:v", "mjpeg", "-i", "-",
                "-i", str(Path(audio_path).resolve()),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "slow", "-crf", str(DEFAULT_CRF),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-shortest", str(out_abs),
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe",
                "-framerate", fps_arg, "-c:v", "mjpeg", "-i", "-",
                "-c:v", "libx264", "-preset", "slow", "-crf", str(DEFAULT_CRF),
                "-pix_fmt", "yuv420p", str(out_abs),
            ]
        ff = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        err_tail = []
        # Windows 下 Popen 的管道默认是文本模式，必须用二进制 fd 写 JPEG 字节
        stdin_bin = os.fdopen(ff.stdin.fileno(), 'wb', closefd=False)
        try:
            for i in range(total):
                t = i / fps
                data_url = await page.evaluate(
                    "async (a) => window.renderAt(a[0], 'image/jpeg', a[1])",
                    [t, quality],
                )
                buf = _data_url_to_bytes(data_url)
                stdin_bin.write(buf)
                if (i + 1) % (fps * 3) == 0 or i == total - 1:
                    pass  # 进度可回填（可选）
        finally:
            stdin_bin.flush()
            stdin_bin.close()
            ff.stdin.close()
            rc = ff.wait()
            err_tail = ff.stderr.read()[-1500:] if ff.stderr else b""
            await browser.close()
        if rc != 0:
            raise RuntimeError(f"ffmpeg 合成失败 (exit {rc}): {err_tail}")


async def _render_frames_to_dir(file_url, frames_dir, total, fps, width, height, workers, quality):
    """并行渲染核心：每个 worker 用【独立 browser 实例】，从共享帧队列取帧索引，
    渲染 renderAt(i/fps) 出 JPEG 写入临时目录（f%05d.jpg，原子重命名防冲突）。
    帧是 t 的纯函数，无序完成结果一致。

    设计要点（踩坑实证）：
    - 不能单 browser 多 page 共享 context：p5.brush 重渲染抢 GPU/canvas，
      单帧可扛、长时间并发会 TargetClosed 崩溃或整体挂起。
    - 每 worker 独立 browser 进程级隔离最稳；单帧渲染加 asyncio 超时防御，
      即使个别帧挂起也只丢该 worker，不拖死全局。"""
    from playwright.async_api import async_playwright

    queue: asyncio.Queue = asyncio.Queue()
    for i in range(total):
        queue.put_nowait(i)

    FRAME_TIMEOUT = 60  # 单帧渲染最长秒数，防个别帧挂起拖死全局

    async def worker(worker_id):
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=BROWSER_ARGS)
            try:
                ctx = await browser.new_context(
                    viewport={"width": width, "height": height})
                page = await ctx.new_page()
                await page.goto(file_url, wait_until="networkidle")
                await page.wait_for_function("window.ready === true", timeout=60000)
                while True:
                    try:
                        i = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    t = i / fps
                    try:
                        data_url = await asyncio.wait_for(
                            page.evaluate(
                                "async (a) => window.renderAt(a[0], 'image/jpeg', a[1])",
                                [t, quality],
                            ),
                            timeout=FRAME_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        log.warning(f"[anim_painter] 帧 {i} 渲染超时，跳过")
                        continue
                    buf = _data_url_to_bytes(data_url)
                    tmp = os.path.join(frames_dir, f"f{i:05d}.jpg.tmp")
                    final = os.path.join(frames_dir, f"f{i:05d}.jpg")
                    with open(tmp, "wb") as f:
                        f.write(buf)
                    os.replace(tmp, final)
            finally:
                await browser.close()

    await asyncio.gather(*(worker(k) for k in range(workers)))


def _encode_from_dir(frames_dir, out_abs, fps, width, height, audio_path):
    seq = os.path.join(frames_dir, "f%05d.jpg")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", seq,
           "-c:v", "libx264", "-preset", "slow", "-crf", str(DEFAULT_CRF),
           "-pix_fmt", "yuv420p", str(out_abs)]
    if audio_path:
        cmd += ["-i", str(Path(audio_path).resolve()), "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _data_url_to_bytes(data_url: str) -> bytes:
    import base64
    return base64.b64decode(data_url.split(",", 1)[1])


def _tmp_dir() -> str:
    return tempfile.gettempdir()


def render_sync(html_path, output_path, duration=8, fps=24, width=1920, height=1080,
                workers=1, quality=0.94, audio_path=None):
    """同步入口（供工具类调用）。"""
    return asyncio.run(render_to_mp4(
        html_path, output_path, duration, fps, width, height, workers, quality, audio_path
    ))


async def _launch_page(p, url, width, height):
    """打开动画页并等待就绪，返回 (browser, page)。预览与整片渲染共用。"""
    browser = await p.chromium.launch(args=BROWSER_ARGS)
    try:
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_function("window.ready === true", timeout=60000)
        return browser, page
    except Exception:
        await browser.close()
        raise


async def render_preview(html_path: str, output_path: str, times: list = None,
                         cols: int = 3, w: int = 640,
                         width: int = 1920, height: int = 1080) -> dict:
    """渲染低分辨率拼图预览图（复用运行时 window.renderSheet）。

    供 LLM 在出片前快速检查画面，产出单张拼图文件，避免为预览绕道 bash 直调脚本。
    """
    from playwright.async_api import async_playwright

    fpath, q = _split_html(html_path)
    html_abs = Path(fpath).resolve()
    out_abs = Path(output_path).resolve()
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    if not html_abs.exists():
        raise FileNotFoundError(f"HTML 不存在: {html_abs}")
    if not times:  # 默认等分 6 帧
        n = 6
        times = [round((t + 0.5) / n, 3) for t in range(n)]

    async with async_playwright() as p:
        browser, page = await _launch_page(p, html_abs.as_uri() + q, width, height)
        try:
            res = await page.evaluate(
                "(a) => window.renderSheet(a[0], a[1], a[2])",
                [times, cols, w],
            )
        finally:
            await browser.close()

    data_url = res["url"]
    buf = _data_url_to_bytes(data_url)
    mime = (data_url.split(",", 1)[0].split(":", 1)[1].split(";", 1)[0] or "image/png")
    ext = ".jpg" if mime.endswith("jpeg") else ".png"
    # 预览图固定按实际内容决定扩展名（png/jpg），忽略调用方传入的后缀（如 .mp4）
    final_path = out_abs.with_suffix(ext)
    with open(final_path, "wb") as f:
        f.write(buf)

    return {"output_path": str(final_path), "frames": times, "ms": res.get("ms", [])}


def render_preview_sync(html_path: str, output_path: str, times: list = None,
                        cols: int = 3, w: int = 640,
                        width: int = 1920, height: int = 1080) -> dict:
    """同步入口（供工具类调用）。"""
    return asyncio.run(render_preview(
        html_path, output_path, times, cols, w, width, height))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="逐帧保真渲染 painter.html 到 mp4")
    ap.add_argument("html_path")
    ap.add_argument("output_path")
    ap.add_argument("--duration", type=float, default=8)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--audio", default=None)
    a = ap.parse_args()
    res = render_sync(a.html_path, a.output_path, a.duration, a.fps,
                      a.width, a.height, a.workers, 0.94, a.audio)
    print(f"done → {res['output_path']} ({res['size_mb']} MB, {res['frames']} 帧)")