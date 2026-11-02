# -*- coding: utf-8 -*-
"""map_video 渲染器：高德 JS API 2.0 + Playwright 逐帧 → mp4。

输入一个地图 spec（route / region / world），由 templates/player.html 按 spec 绘制；
渲染器只负责：启动本地页面、等待地图/路线就绪、预热、逐帧截图、ffmpeg 合成。

Key 从环境变量读取（由 MapVideoTool 注入）：
  AMAP_JS_KEY / AMAP_SECURITY_CODE
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"

BROWSER_ARGS = [
    "--ignore-gpu-blocklist",
    "--use-angle=d3d11",
    "--enable-gpu-rasterization",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--hide-scrollbars",
]


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(TEMPLATES), **kw)

    def log_message(self, *a):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="地图 spec JSON 文件")
    ap.add_argument("--out", required=True, help="输出 mp4")
    ap.add_argument("--poster", default="", help="可选：海报帧 jpg")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    key = os.environ.get("AMAP_JS_KEY", "").strip()
    code = os.environ.get("AMAP_SECURITY_CODE", "").strip()
    if not key or not code:
        print("缺少 AMAP_JS_KEY / AMAP_SECURITY_CODE")
        return 2

    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"spec 读取失败: {e}")
        return 2
    if not isinstance(spec, dict):
        print("spec 必须是 JSON 对象")
        return 2

    kind = str(spec.get("kind") or "region").lower()
    route_wait = kind in ("route", "flight")
    seconds = max(2.0, min(60.0, float(args.seconds or 6)))
    fps = max(12, min(60, int(args.fps or 30)))
    W, H = max(320, int(args.width)), max(240, int(args.height))
    total = int(round(seconds * fps))
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"缺少 playwright: {e}")
        return 2

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/player.html"
    print(f"[map] 页面: {url}｜{kind}｜{seconds:g}s / {fps}fps / {W}x{H}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=BROWSER_ARGS)
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            page.add_init_script(
                "window.__MAP_SPEC__ = " + json.dumps(spec, ensure_ascii=False) + ";"
                "window.__AMAP_CONFIG__ = " + json.dumps(
                    {"key": key, "securityCode": code}, ensure_ascii=False) + ";"
            )
            page.on("pageerror", lambda e: print(f"[pageerror] {e}"))
            page.on("console", lambda m: (
                print(f"[console:{m.type}] {m.text}")
                if m.type in ("error", "warning") else None
            ))
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            try:
                page.wait_for_function("window.__ready__ === true", timeout=90000)
            except Exception:
                err = page.evaluate("window.__error__ || ''")
                print("[map] 地图没有就绪。")
                print("      常见原因：Key 平台类型不是 Web端(JS API) / 缺安全密钥 / 域名白名单不允许 127.0.0.1。")
                print(f"      页面错误：{err}")
                browser.close()
                return 1

            err = page.evaluate("window.__error__ || ''")
            if err:
                print(f"[map] 页面错误：{err}")
                browser.close()
                return 1

            if route_wait:
                try:
                    page.wait_for_function("window.__route_ready__ === true", timeout=20000)
                except Exception:
                    print("[map] 路线未返回，页面会使用替代路线（如有坐标）")

            # 预热：沿动画进度把瓦片/数据先加载一遍
            warm_n = 11 if route_wait else 3
            for k in range(warm_n):
                page.evaluate("t => window.renderAt(t)", k / max(1, warm_n - 1))
                page.wait_for_timeout(420 if route_wait else 260)
            page.evaluate("t => window.renderAt(t)", 0.0)
            page.wait_for_timeout(300)

            ffmpeg = os.environ.get("FFMPEG_BIN") or "ffmpeg"
            cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(fps), "-i", "-",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

            prev_hash = None
            dup = 0
            for i in range(total):
                t = i / max(1, total - 1)
                page.evaluate("t => window.renderAt(t)", t)
                img = page.screenshot(type="jpeg", quality=95)
                h = hashlib.md5(img).hexdigest()
                if h == prev_hash:
                    dup += 1
                    page.wait_for_timeout(60)
                    img = page.screenshot(type="jpeg", quality=95)
                    h = hashlib.md5(img).hexdigest()
                prev_hash = h
                try:
                    proc.stdin.write(img)
                except BrokenPipeError:
                    break
                if (i + 1) % 30 == 0 or i == total - 1:
                    print(f"[map] 帧 {i + 1}/{total}（重复帧修正 {dup}）")

            try:
                proc.stdin.close()
            except Exception:
                pass
            err = proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else ""
            rc = proc.wait()
            if rc != 0:
                print(f"[map] ffmpeg 失败（exit {rc}）：{err[-800:]}")
                browser.close()
                return 1

            if args.poster:
                page.evaluate("t => window.renderAt(t)", 0.72)
                Path(args.poster).parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(args.poster).resolve()), type="jpeg", quality=95)
                print(f"[map] 海报: {Path(args.poster).resolve()}")

            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    print(f"[map] 完成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
