# -*- coding: utf-8 -*-
"""remotion_hook - Remotion 开场钩子引擎。

两种模式：
  - auto（默认）：先让 LLM 自由写 TSX → 渲染 → 视觉闸门；不过再回退模板；
  - freeform：只走自由发挥；
  - template：只走 title / kinetic / ui 模板。
时长由导演给定（开场钩子至少 10 秒；不再固定 3~5 秒），动画铺满整段。
渲染由 ../project 的 Remotion 工程完成；失败由导演组降级到 opendesign。
"""
import subprocess
import sys
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

HERE = Path(__file__).resolve().parent
RENDERER = HERE / "scripts" / "render_hook.py"
TEMPLATES = ("title", "kinetic", "ui")


class RemotionHookTool(BaseTool):
    name = "remotion_hook_generate"
    description = (
        "Remotion 开场钩子引擎：默认先让 LLM 自由写 TSX，渲染后做视觉闸门；"
        "不过再回退 title/kinetic/ui 模板。mode=auto/freeform/template。"
        "时长由导演给定（开场钩子至少 10 秒），动画铺满整段。"
        "只传 text/kicker/sub/accent/duration/画布；失败由导演组降级到 opendesign。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 MP4 绝对路径"),
        ToolParameter("mode", "string", "auto=先自由发挥再回退模板；freeform=只自由发挥；template=只模板",
                      required=False, default="auto", enum=["auto", "freeform", "template"]),
        ToolParameter("template", "string", "回退模板：title / kinetic / ui",
                      required=False, default="title", enum=list(TEMPLATES)),
        ToolParameter("text", "string", "钩子主文案（屏幕上最大的一行）"),
        ToolParameter("kicker", "string", "顶部小标签，可空", required=False, default=""),
        ToolParameter("sub", "string", "副文案/解释，可空", required=False, default=""),
        ToolParameter("accent", "string", "强调色 #RRGGBB，可空（用模板默认）",
                      required=False, default=""),
        ToolParameter("hook_type", "string", "钩子类型（result/question/ui 等），供自由发挥提示词使用",
                      required=False, default=""),
        ToolParameter("style", "string", "整体风格描述，供自由发挥提示词使用",
                      required=False, default=""),
        ToolParameter("duration", "number", "时长秒，>=3；开场钩子由导演给定（通常 10，默认 10）",
                      required=False, default=10.0),
        ToolParameter("width", "integer", "画布宽，默认 1920", required=False, default=1920),
        ToolParameter("height", "integer", "画布高，默认 1080", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    def execute(
        self,
        output_path: str,
        text: str,
        mode: str = "auto",
        template: str = "title",
        kicker: str = "",
        sub: str = "",
        accent: str = "",
        hook_type: str = "",
        style: str = "",
        duration: float = 10.0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        **kwargs,
    ) -> ToolResult:
        template = str(template or "title").strip().lower()
        if template not in TEMPLATES:
            return ToolResult.fail(f"未知 template={template!r}；可用 {' / '.join(TEMPLATES)}")
        mode = str(mode or "auto").strip().lower()
        if mode not in ("auto", "freeform", "template"):
            mode = "auto"
        if not str(text or "").strip():
            return ToolResult.fail("text 不能为空")

        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        # 不做“文件已存在就复用”：时长/文案/模板任一变化都由导演签名判断，
        # 这里再按文件存在短路会把旧的 3~5 秒钩子当成新的 10 秒钩子交付。
        duration = max(3.0, float(duration or 10))
        spec = {
            "template": template,
            "hook_type": str(hook_type or template),
            "text": str(text),
            "kicker": str(kicker or ""),
            "sub": str(sub or ""),
            "accent": str(accent or ""),
            "style": str(style or ""),
            "duration": duration,
            "width": int(width or 1920),
            "height": int(height or 1080),
            "fps": int(fps or 30),
        }

        # 自由发挥：LLM 写 TSX → 渲染 → 视觉闸门；不过再回退模板。
        if mode in ("auto", "freeform"):
            cfg = self.llm_config or {}
            if cfg.get("base_url") and cfg.get("api_key") and cfg.get("model"):
                try:
                    from .scripts.freeform import run_freeform
                    self._emit_progress("Remotion 自由发挥：生成 → 渲染 → 视觉闸门...")
                    info = run_freeform(spec, cfg, out, on_progress=self._emit_progress)
                    real_dur = 0.0
                    try:
                        from skills.compose_video.scripts.renderer import probe_duration
                        real_dur = float(probe_duration(str(out)) or 0.0)
                    except Exception:
                        pass
                    size_mb = round(out.stat().st_size / 1048576, 2)
                    review = info.get("review") or {}
                    return ToolResult.ok(
                        f"Remotion 自由发挥通过：第 {info.get('attempt')} 次 / "
                        f"视觉 {review.get('score')} 分 / {size_mb} MB\n输出：{out}",
                        output_path=str(out.resolve()), status="succeeded",
                        template=template, renderer="remotion-freeform",
                        duration=real_dur or duration, size_mb=size_mb,
                        attempt=info.get("attempt"), review=review,
                        code_path=info.get("code_path", ""),
                        deliverable=True,
                    )
                except Exception as e:
                    if mode == "freeform":
                        return ToolResult.fail(f"Remotion 自由发挥失败：{e}")
                    self._emit_progress(f"自由发挥未通过（{str(e)[:160]}），回退模板")
            elif mode == "freeform":
                return ToolResult.fail("未配置多模态主 LLM，无法自由发挥")

        self._emit_progress(f"Remotion 钩子渲染中（{template} / {duration:g}s）...")
        cmd = [
            sys.executable, str(RENDERER),
            "--template", template,
            "--text", str(text),
            "--kicker", str(kicker or ""),
            "--sub", str(sub or ""),
            "--accent", str(accent or ""),
            "--duration", str(duration),
            "--width", str(int(width or 1920)),
            "--height", str(int(height or 1080)),
            "--fps", str(int(fps or 30)),
            "--out", str(out),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1000)
        except subprocess.TimeoutExpired:
            return ToolResult.fail("Remotion 渲染超时（1000s）")

        if r.returncode != 0 or not out.exists() or out.stat().st_size < 1024:
            tail = (r.stderr or r.stdout or "")[-1600:]
            return ToolResult.fail(f"Remotion 渲染失败：\n{tail}")

        real_dur = 0.0
        try:
            from skills.compose_video.scripts.renderer import probe_duration
            real_dur = float(probe_duration(str(out)) or 0.0)
        except Exception:
            pass
        size_mb = round(out.stat().st_size / 1048576, 2)
        self._emit_progress(f"Remotion 钩子完成：{template} / {real_dur or duration:g}s")
        return ToolResult.ok(
            f"Remotion 钩子完成：{template} / {real_dur or duration:g}s / {size_mb} MB\n"
            f"输出：{out}",
            output_path=str(out.resolve()),
            status="succeeded",
            template=template,
            duration=real_dur or duration,
            size_mb=size_mb,
            renderer="remotion",
            deliverable=True,
        )
