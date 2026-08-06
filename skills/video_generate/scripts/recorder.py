"""
HTML 动画录制 - Playwright 内置录像 + 帧注入
Playwright 实时录视频，同时逐帧注入 CURRENT_FRAME 控制动画时间轴
不做截图，只有 JS eval，轻量快速
"""
import os
import asyncio
import time
import shutil
import subprocess
from pathlib import Path


async def record_html(
    html_path: str,
    output_path: str,
    duration: int = 10,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    from playwright.async_api import async_playwright

    abs_path = os.path.abspath(html_path).replace("\\", "/")
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    record_dir = os.path.join(output_dir, f"_record_{Path(output_path).stem}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=record_dir,
            record_video_size={"width": width, "height": height},
        )
        page = await context.new_page()

        await page.goto(f"file:///{abs_path}", wait_until="networkidle")
        await asyncio.sleep(0.5)

        # Playwright 录视频 + 帧注入驱动动画时间轴
        total_frames = duration * fps
        frame_interval = 1.0 / fps
        print(f"  [录制] {duration}s @ {fps}fps ({total_frames} 帧), 实时录制...")

        start = time.perf_counter()
        for i in range(total_frames):
            await page.evaluate(f"window.CURRENT_FRAME = {i}")
            target = start + (i + 1) * frame_interval
            wait = target - time.perf_counter()
            if wait > 0:
                await asyncio.sleep(wait)

            if (i + 1) % (fps * 3) == 0:
                elapsed = time.perf_counter() - start
                print(f"  [录制] 帧 {i + 1}/{total_frames} ({(i + 1) / total_frames * 100:.0f}%) 用时 {elapsed:.1f}s")

        await context.close()
        await browser.close()

    # webm → mp4
    webm_files = list(Path(record_dir).glob("*.webm"))
    if not webm_files:
        shutil.rmtree(record_dir, ignore_errors=True)
        raise RuntimeError("Playwright 未生成录制文件")

    webm = str(webm_files[0])
    _webm_to_mp4(webm, output_path, fps)

    shutil.rmtree(record_dir, ignore_errors=True)

    actual_time = time.perf_counter() - start
    print(f"  [完成] 实际耗时 {actual_time:.1f}s (目标 {duration}s)")

    return output_path


def _webm_to_mp4(webm_path: str, output_path: str, fps: int):
    cmd = [
        "ffmpeg", "-y",
        "-i", webm_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 转换失败: {result.stderr}")


def record_sync(html_path: str, output_path: str, duration: int = 10,
                fps: int = 30, width: int = 1920, height: int = 1080) -> str:
    return asyncio.run(record_html(html_path, output_path, duration, width, height, fps))
