# -*- coding: utf-8 -*-
"""
animation_painter skill - 程序化水彩动画渲染

把 PDoomVideo 的「p5.brush 水彩动画」能力封装为 sigma 技能。
- 提供通用运行时 engine/painter.html（含 p5.js + p5.brush 引擎 + 纯函数 shot 规范）。
- LLM 通过 sandbox 依据 skill.md 创作一个自定义 <场景名>.html（复用运行时舞台），
  或让本技能用内置 engine/demo_core.js 渲染示例。
- 逐帧保真渲染（非实时录屏）：每一帧独立 `renderAt(t)` 出无损/JPEG，再 ffmpeg 合成 mp4，
  可选混入外部音频（音乐走 music_generate / doubao_tts / 外部 mp3；本技能只混流）。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SKILL_DIR / "engine"
DEFAULT_HTML = ENGINE_DIR / "painter.html"
DEFAULT_SCRIPT = ENGINE_DIR / "demo_core.js"


def _auto_output_path(output_path: str, project: str = None, cwd: str = None) -> Path:
    """自动将路径放入 video_work/<project>/ 目录下（与 video_generate 约定一致）。"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    if project:
        work_dir = work_dir / project
    return work_dir / p


class AnimationPainterRenderTool(BaseTool):
    """把 p5.brush 水彩动画渲染成 mp4（逐帧保真）。"""

    name = "pdoom_render"
    description = (
        "把 p5.brush 水彩动画渲染为 mp4。两种用法：\n"
        "1. 自定义：html_path 指向 LLM 依据 animation_painter skill.md 写好的 HTML（复用其 engine/painter.html 运行时，用 window.chapter 注册镜头），本工具逐帧渲染。\n"
        "2. 示例：不传 html_path 则渲染内置 demo_core.js。\n"
        "支持外部音频混流（audio_path，音乐请先用 music_generate/doubao_tts 生成或提供 mp3），\n"
        "帧是时间的纯函数，可并行、质量无损（逐帧 renderAt，非实时录屏）。\n"
        "支持两种模式（mode 参数）：full=整片 mp4（默认），preview=低分辨率拼图预览图。\n"
        "【重要】预览/检查画面请用 mode=preview，禁止用 bash 直调本技能的 scripts 脚本。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 mp4 文件路径（相对路径自动放 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，所有产物集中管理；同一视频各工具保持一致", required=False),
        ToolParameter("html_path", "string", "自定义动画 HTML 路径；缺省用内置 engine/painter.html + demo_core.js", required=False),
        ToolParameter("duration", "number", "视频时长（秒）", required=False, default=8),
        ToolParameter("fps", "integer", "帧率", required=False, default=24),
        ToolParameter("width", "integer", "画面宽度", required=False, default=1920),
        ToolParameter("height", "integer", "画面高度", required=False, default=1080),
        ToolParameter("bpm", "number", "节拍速度（拍/分钟），驱动动画节拍；demo 默认 88。传给用于说明动画节奏的元信息", required=False),
        ToolParameter("audio_path", "string", "外部音频路径（mp3 等），会把音频渲染进 mp4", required=False),
        ToolParameter("workers", "integer", "并行渲染工作数；帧是纯函数可安全并行", required=False, default=1),
        ToolParameter("quality", "number", "JPEG 质量 0~1，默认 0.94", required=False, default=0.94),
        ToolParameter("mode", "string", "渲染模式：full=整片 mp4（默认）；preview=低分辨率拼图预览图（出片前快速检查画面，勿用 bash 直调脚本）", required=False, default="full"),
    ]

    def execute(self, output_path: str, project: str = None, html_path: str = None,
                duration: float = 8, fps: int = 24, width: int = 1920, height: int = 1080,
                bpm: float = None, audio_path: str = None, workers: int = 1,
                quality: float = 0.94, mode: str = "full", **kwargs) -> ToolResult:
        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 确定 html：优先自定义，否则内置 demo
        target_html = DEFAULT_HTML
        if html_path:
            # html_path 可能带 `?core=xxx.js`（章节注入通道）：存在性校验用剥离
            # query 后的真实文件；渲染目标保留 query，frame_renderer 会拼回 URL。
            html_str = html_path
            query = ("?" + html_str.split("?", 1)[1]) if "?" in html_str else ""
            p = self._resolve_path(html_str.split("?", 1)[0])
            if not p.exists():
                return ToolResult.fail(f"HTML 不存在: {html_path}")
            target_html = str(Path(p)) + query
        elif not DEFAULT_HTML.exists():
            return ToolResult.fail(
                f"缺失引擎运行时: {DEFAULT_HTML}\n请确认 skills/animation_painter/engine/painter.html 存在。"
            )

        if duration <= 0 or fps <= 0:
            return ToolResult.fail("duration 与 fps 必须大于 0")

        mode = mode or "full"
        if mode == "preview":
            try:
                from .scripts.frame_renderer import render_preview_sync
                self._emit_progress(f"生成预览图 ({width}x{height} 拼图)..")
                res = render_preview_sync(
                    str(target_html), str(out),
                    width=width, height=height, w=min(640, width),
                )
            except Exception as e:
                return ToolResult.fail(f"预览渲染失败: {e}")
            return ToolResult.ok(
                f"预览图已生成: {res['output_path']}（{len(res['frames'])} 帧拼图，每帧 {res['ms']}ms）",
                output_path=res["output_path"],
                frames=len(res["frames"]),
                frame_ms=res["ms"],
                mode="preview",
            )

        # 检查 ffmpeg（逐帧渲染成 mp4 必需）；preview 不需要
        import shutil
        if not shutil.which("ffmpeg"):
            return ToolResult.fail("未找到 ffmpeg，请在系统安装并加入 PATH")
        try:
            import playwright  # noqa
        except ImportError:
            return ToolResult.fail(
                "缺少 playwright，请执行: pip install playwright && playwright install chromium"
            )

        try:
            from .scripts.frame_renderer import render_sync
            self._emit_progress(f"开始逐帧渲染 ({duration}s @ {fps}fps, {width}x{height})...")
            res = render_sync(
                str(target_html), str(out),
                duration=duration, fps=fps, width=width, height=height,
                workers=int(workers), quality=float(quality),
                audio_path=audio_path,
            )
        except Exception as e:
            return ToolResult.fail(f"渲染失败: {e}")

        return ToolResult.ok(
            f"动画渲染完成: {res['output_path']} "
            f"({res['size_mb']}MB, {res['frames']} 帧, {res['duration']}s, {res['resolution']})",
            output_path=res["output_path"],
            duration=res["duration"],
            fps=res["fps"],
            resolution=res["resolution"],
            frames=res["frames"],
            size_mb=res["size_mb"],
            bpm=bpm,
            audio_attached=bool(audio_path),
        )


__all__ = ["AnimationPainterRenderTool"]