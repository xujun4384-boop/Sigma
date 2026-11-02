# -*- coding: utf-8 -*-
"""Remotion 开场钩子渲染桥接。

只做三件事：
  1. 把内容参数写成 props.json（模板选择 + 文案 + 时长 + 画布）；
  2. 调 `remotion render` 渲染 Hook 组合；
  3. 校验产物存在，失败时把 Node 的 stderr 尾部带回给上层。

模板代码在 ../project/src/templates/，LLM 不直接写 TSX。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent / "project"
TEMPLATES = ("title", "kinetic", "ui")


def _which(name: str) -> str:
    return shutil.which(name) or shutil.which(name + ".cmd") or ""


def _node_cli() -> Path:
    p = PROJECT / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    if not p.exists():
        raise RuntimeError("Remotion CLI 未安装；请先运行一次 npm install（或重试，让脚本自动安装）。")
    return p


def ensure_deps() -> None:
    """首次运行自动安装项目依赖；已安装则跳过。

    Windows 上 npx/npm 是 .cmd，直接当可执行文件启动会失败；这里优先用
    `node <npm-cli.js>`，路径带空格也不会被 cmd 拆坏。
    """
    marker = PROJECT / "node_modules" / "remotion" / "package.json"
    if marker.exists():
        return
    node = _which("node")
    npm = _which("npm")
    if not node or not npm:
        raise RuntimeError("未找到 Node.js / npm；请先安装 Node.js 20+，再运行一次。")
    npm_cli = Path(npm).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
    if npm_cli.exists():
        cmd = [node, str(npm_cli), "install", "--loglevel=error"]
    elif os.name == "nt":
        cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c",
               f'"{npm}" install --loglevel=error']
    else:
        cmd = [npm, "install", "--loglevel=error"]
    sys.stderr.write("[remotion_hook] 首次运行：安装 Remotion 依赖（可能需要几分钟）...\n")
    r = subprocess.run(cmd, cwd=str(PROJECT), capture_output=True, text=True, timeout=1200)
    if r.returncode != 0 or not marker.exists():
        tail = (r.stderr or r.stdout or "")[-1200:]
        raise RuntimeError("Remotion 依赖安装失败：\n" + tail)


def _render_with_props(entry: str, composition: str, props: dict, out: Path) -> dict:
    ensure_deps()
    node = _which("node")
    if not node:
        raise RuntimeError("未找到 node；请先安装 Node.js 20+。")
    cli = _node_cli()

    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    # Remotion 在 Windows 上对带空格的输出路径不稳；先渲到无空格的临时目录，再搬过去。
    tmpdir = Path(tempfile.mkdtemp(prefix="remotion_hook_"))
    tmp_out = tmpdir / "hook.mp4"
    fd, props_path = tempfile.mkstemp(prefix="hook_props_", suffix=".json")
    os.close(fd)
    Path(props_path).write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")

    cmd = [
        node, str(cli), "render", entry, composition, str(tmp_out),
        "--props", props_path,
        "--codec", "h264",
        "--crf", "18",
        "--pixel-format", "yuv420p",
        "--concurrency", "1",
    ]
    try:
        r = subprocess.run(cmd, cwd=str(PROJECT), capture_output=True, text=True, timeout=900)
    finally:
        try:
            Path(props_path).unlink()
        except OSError:
            pass

    try:
        if r.returncode != 0 or not tmp_out.exists() or tmp_out.stat().st_size < 1024:
            tail = (r.stderr or r.stdout or "")[-2500:]
            raise RuntimeError(f"Remotion 渲染失败（exit {r.returncode}）：\n{tail}")
        if out.exists():
            out.unlink()
        shutil.move(str(tmp_out), str(out))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {"output_path": str(out), "size_bytes": out.stat().st_size, **props}


def render(template: str, text: str, kicker: str, sub: str, accent: str,
           duration: float, width: int, height: int, fps: int, out: Path) -> dict:
    template = (template or "title").strip().lower()
    if template not in TEMPLATES:
        raise RuntimeError(f"未知模板 {template!r}；可用 {' / '.join(TEMPLATES)}")
    if not text.strip():
        raise RuntimeError("text 不能为空")
    props = {
        "template": template,
        "text": text.strip(),
        "kicker": kicker.strip(),
        "sub": sub.strip(),
        "accent": accent.strip(),
        "duration": max(3.0, float(duration or 10)),
        "width": max(320, int(width or 1920)),
        "height": max(240, int(height or 1080)),
        "fps": max(1, int(fps or 30)),
    }
    return _render_with_props("src/index.ts", "Hook", props, out)


def render_freeform(props: dict, out: Path) -> dict:
    p = dict(props or {})
    p["text"] = str(p.get("text") or "").strip()
    if not p["text"]:
        raise RuntimeError("text 不能为空")
    p["kicker"] = str(p.get("kicker") or "").strip()
    p["sub"] = str(p.get("sub") or "").strip()
    p["accent"] = str(p.get("accent") or "").strip()
    p["duration"] = max(3.0, float(p.get("duration") or 10))
    p["width"] = max(320, int(p.get("width") or 1920))
    p["height"] = max(240, int(p.get("height") or 1080))
    p["fps"] = max(1, int(p.get("fps") or 30))
    return _render_with_props("src/freeform-entry.tsx", "FreeformHook", p, out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="title")
    ap.add_argument("--text", required=True)
    ap.add_argument("--kicker", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--accent", default="")
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        info = render(a.template, a.text, a.kicker, a.sub, a.accent,
                      a.duration, a.width, a.height, a.fps, Path(a.out))
    except Exception as e:
        sys.stderr.write(str(e) + "\n")
        return 1
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
