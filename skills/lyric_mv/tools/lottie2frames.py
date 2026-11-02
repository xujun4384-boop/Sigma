# -*- coding: utf-8 -*-
"""把 Lottie JSON 离线烘焙成 PNG 帧序列（透明背景）。

为什么这么做：
  引擎的 seek(t) 是同步纯函数，而 lottie-web 的加载/解析是异步的。
  与其在渲染时跟异步打架，不如一次性把素材烘成帧，运行时只剩 drawImage——确定、简单、不依赖运行时库。

用法：
  python lottie2frames.py <input.json> <out_dir> [--w 640] [--step 1]
输出：
  out_dir/frame_00000.png ...  以及 out_dir/meta.json（w/h/frames/fps）
"""
import argparse
import asyncio
import json
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
LOTTIE_JS = HERE.parent / "engine" / "vendor" / "lottie.min.js"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--w", type=int, default=0, help="输出宽度（0=原尺寸）")
    ap.add_argument("--step", type=int, default=1, help="抽帧步长")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    data = json.loads(src.read_text(encoding="utf-8"))
    ow, oh = data.get("w", 500), data.get("h", 500)
    fr = data.get("fr", 30)
    op = data.get("op", 60)
    total = int(op - data.get("ip", 0))

    scale = (args.w / ow) if args.w else 1.0
    vw, vh = int(ow * scale), int(oh * scale)

    html = HERE / "_bake.html"
    html.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:transparent}}#c{{width:{vw}px;height:{vh}px}}</style>
</head><body><div id="c"></div>
<script src="{LOTTIE_JS.as_uri()}"></script>
<script>
window.__ready = false;
const anim = lottie.loadAnimation({{
  container: document.getElementById('c'),
  renderer: 'canvas', loop: false, autoplay: false,
  path: {json.dumps(src.as_uri())},
}});
anim.setSubframe(false);
anim.addEventListener('DOMLoaded', () => {{
  const cv = document.querySelector('#c canvas');
  if (cv) {{ cv.style.width = '{vw}px'; cv.style.height = '{vh}px'; }}
  window.__ready = true;
}});
window.__seek = (f) => anim.goToAndStop(f, true);
</script></body></html>""", encoding="utf-8")

    n = 0
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--allow-file-access-from-files", "--hide-scrollbars"])
        pg = await b.new_page(viewport={"width": vw, "height": vh},
                              device_scale_factor=1)
        await pg.goto(html.as_uri(), wait_until="load")
        await pg.wait_for_function("window.__ready === true", timeout=30000)
        for f in range(0, total, args.step):
            await pg.evaluate("f => window.__seek(f)", f)
            await pg.wait_for_timeout(12)
            shot = await pg.screenshot(omit_background=True,
                                       clip={"x": 0, "y": 0, "width": vw, "height": vh})
            (out / f"frame_{n:05d}.png").write_bytes(shot)
            n += 1
        await b.close()

    (out / "meta.json").write_text(json.dumps({
        "w": vw, "h": vh, "frames": n, "fps": round(fr / args.step, 3),
        "source": src.name,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    html.unlink(missing_ok=True)
    print(f"done: {n} frames -> {out}  ({vw}x{vh} @ {round(fr / args.step, 3)}fps)")


asyncio.run(main())
