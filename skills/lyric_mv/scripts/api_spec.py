# -*- coding: utf-8 -*-
"""从**运行中的引擎**导出「可用 API 清单」，供系统提示词注入。

为什么必须有这个：
  提示词里若手写 API 说明，必然与引擎漂移。实测就发生过——
  提示词写着 sh.tri(三点, 色)，引擎实际要 sh.tri(x1,y1,x2,y2,x3,y3, 色)，
  模型老老实实照提示词写，于是每一批都在闸门处报错；
  还有模型写 e.sh.drawText(...)，而 drawText 是挂在 e 上、不在 e.sh 上。
  这类错误的共同点是：**提示词与引擎不一致**，靠人工同步迟早再错。

  所以这里改为从引擎运行时**真实导出**：引擎一改，清单自动跟着变，
  提示词永远等于引擎的真实能力面（模型也就没有"猜"的余地）。

用法：
  python api_spec.py --engine ../engine/stage.html [--out api-spec.txt]
不指定 --out 就打到 stdout。
"""
import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ARGS = ["--allow-file-access-from-files", "--hide-scrollbars",
        "--force-device-scale-factor=1", "--disable-lcd-text"]

# 最小时间轴：只要引擎能 seek(0) 构造出 e 对象即可
MIN_TL = ('{"lines":[],"beat_seconds":0.5,"offset_seconds":0,"duration":2,"bpm":120}')

# 在页面里读 e / e.sh / MV，导出「函数→形参名」与「值字段→类型」
PROBE = r"""
() => {
  /* 取形参名。箭头函数单参数不带括号（k => ...），函数体里又有括号，
     老正则会把函数体里的 (1 - k, 3) 当成参数，误导模型。按优先级逐个匹配。*/
  const sig = f => {
    if (typeof f !== 'function') return '';
    const s = f.toString().replace(/\s+/g, ' ').trim();
    let m = s.match(/^(?:async\s+)?function\s*[A-Za-z0-9_$]*\s*\(([^)]*)\)/);
    if (m) return m[1].trim();
    m = s.match(/^(?:async\s+)?\(([^)]*)\)\s*=>/);
    if (m) return m[1].trim();
    m = s.match(/^([A-Za-z0-9_$]+)\s*=>/);
    if (m) return m[1];
    m = s.match(/^[^(]*\(([^)]*)\)/);
    return m ? m[1].trim() : '';
  };
  const MV = window.MV || {}, e = window.__e || {}, sh = (MV && MV.sh) || {};
  const isFn = o => Object.keys(o).filter(k => typeof o[k] === 'function');
  const isVal = o => Object.keys(o).filter(k => typeof o[k] !== 'function'
                                              && typeof o[k] !== 'undefined');
  return {
    e_fn:  isFn(e).map(k => [k, sig(e[k])]),
    e_val: isVal(e).map(k => [k, typeof e[k]]),
    sh_fn: isFn(sh).map(k => [k, sig(sh[k])]),
    mv_fn: isFn(MV).map(k => [k, sig(MV[k])]),
    mv_val: isVal(MV).map(k => [k, typeof MV[k]]),
    pal:   Object.entries(MV.P || {}).map(([k, v]) => [k, String(v)]),
    /* 引擎自带的对象参数说明（window.__apiDoc），有就一并导出 */
    doc:   window.__apiDoc || {},
  };
}
"""


async def dump(engine: str) -> dict:
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=ARGS)
        pg = await b.new_page(viewport={"width": 1280, "height": 720})
        await pg.add_init_script(f"window.TL={MIN_TL};window.PLAN={{}};")
        await pg.goto(Path(engine).resolve().as_uri(), wait_until="load")
        await pg.wait_for_function("window.ready === true", timeout=30000)
        await pg.evaluate("() => window.seek(0)")          # 构造出 e 并挂到 __e
        info = await pg.evaluate(PROBE)
        await b.close()
    return info


def to_text(info: dict) -> str:
    L = []
    L.append("### e —— 每帧给你的画面环境对象（**只有下列成员存在，没列的就是不存在，不许猜**）")
    if info.get("e_fn"):
        L.append("函数（**必须带括号调用**）： " + "  ".join(f"e.{k}({a})" for k, a in info["e_fn"]))
    if info.get("e_val"):
        # 之前这里渲染成 e.W(number)，和函数签名长得一模一样，模型就写成 e.W() 调用，
        # 于是每批都报 "e.W is not a function"（实测占了约 2/3 的重写）。
        L.append("取值（**是属性，不是函数：直接写 e.W，不要写 e.W()**）： "
                 + " | ".join(f"e.{k}: {t}" for k, t in info["e_val"]))
    L.append("")
    L.append("### e.sh —— 形状工具（**只有这些方法**，不要往 e.sh 上挂别的东西）")
    for k, a in info.get("sh_fn", []):
        L.append(f"  e.sh.{k}({a})")
    L.append("")
    if info.get("mv_fn") or info.get("mv_val"):
        L.append("### window.MV 上还有")
        if info.get("mv_fn"):
            L.append("  函数（要带括号）： " + "  ".join(f"MV.{k}({a})" for k, a in info["mv_fn"]))
        if info.get("mv_val"):
            L.append("  取值（是属性，不要加括号）： "
                     + " | ".join(f"MV.{k}: {t}" for k, t in info["mv_val"]))
        L.append("")
    if info.get("pal"):
        L.append("### e.P 调色板")
        L.append("  " + "  ".join(f"{k}={v}" for k, v in info["pal"]))
    if info.get("doc"):
        L.append("")
        L.append("### 对象参数说明（引擎自带，随实现一起更新）")
        for k, v in info["doc"].items():
            L.append(f"  {k}")
            L.extend("    " + ln for ln in str(v).splitlines())
    return "\n".join(L).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    try:
        info = asyncio.run(dump(args.engine))
    except Exception as e:
        print(f"导出 API 清单失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    txt = to_text(info)
    if args.out:
        Path(args.out).write_text(txt, encoding="utf-8")
    else:
        sys.stdout.write(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
