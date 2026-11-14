"""webpage - 真实网页取景讲解引擎。

一段 = 一个真实网页：在模拟浏览器窗口里 1:1 滚动定位，高亮关键原文，旁边逐条浮现批注
（原文摘录 + 解释）。画面来自设计阶段冻结的页面带与坐标，执行阶段不再抓页，
保证"确认的是什么，成片就是什么"。
"""
from __future__ import annotations

import time
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

MAX_TRIES = 3
BUDGET_SEC = 600


class WebpageVideoTool(BaseTool):
    name = "webpage_video"
    description = (
        "把真实网页做成知识点讲解动画：模拟浏览器窗口内滚动网页（1:1），"
        "逐条浮现批注（原文摘录 + 解释），并在网页原文上做高亮标注。"
        "需要 web 对象（source/capture_dir/marks，由导演设计阶段生成），"
        "由 LLM 编写标注层 HTML+GSAP，再用 HyperFrames 确定性渲染成 mp4。"
    )
    parameters = [
        ToolParameter("web", "object", "网页取景数据（url/query/focus/source/marks/capture_dir）"),
        ToolParameter("output_path", "string", "输出 mp4 文件路径"),
        ToolParameter("project", "string", "项目名，用于定位 video_work/<project>/web 缓存", required=False),
        ToolParameter("duration_s", "integer", "本段时长（秒），通常等于旁白实测时长", required=False, default=8),
        ToolParameter("narration", "string", "本段旁白文案（用于高亮与讲解对齐）", required=False),
        ToolParameter("narration_words", "array", "旁白字级时间戳（startTime/endTime/word）", required=False),
        ToolParameter("style_prompt", "string", "标注与包装的视觉风格（可空）", required=False),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    def execute(
        self,
        web: dict,
        output_path: str,
        project: str = None,
        duration_s: float = 8,
        narration: str = "",
        narration_words: list = None,
        style_prompt: str = "",
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        **kwargs,
    ) -> ToolResult:
        from skills.opendesign.scripts.renderer import (
            ToolCancelledError, localize_scripts, render, scaffold_project,
        )
        from skills.opendesign.scripts.gate import review_frames, run_gates
        from .scripts.compose import (
            asset_issues, compose_html, geometry_issues, repair_webpage,
        )
        from .scripts.prepare import PrepareError, load_capture
        from .scripts.scene import build_scene, copy_assets

        cfg = self.llm_config or {}
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            return ToolResult.fail("webpage 需要主 LLM 配置（base_url / api_key / model）")
        if not isinstance(web, dict) or not web:
            return ToolResult.fail("webpage 缺少 web 对象（由导演设计阶段生成）")

        try:
            capture, capture_dir = load_capture(web, self.cwd)
        except PrepareError as e:
            return ToolResult.fail(str(e))

        out = self._auto_path(output_path, project)
        out.parent.mkdir(parents=True, exist_ok=True)
        proj_dir = out.parent / f"{out.stem}_hyperframes"
        try:
            scaffold_project(proj_dir, out.stem)
        except Exception as e:
            return ToolResult.fail(f"脚手架生成失败: {e}")

        assets = copy_assets(capture, capture_dir, proj_dir / "assets")
        dur = float(duration_s or 8)
        scene = build_scene(
            capture,
            duration=dur,
            width=int(width),
            height=int(height),
            fps=int(fps),
            narration=narration or "",
            narration_words=narration_words or [],
            style_prompt=style_prompt or "",
            assets=assets,
        )
        missing = asset_issues(proj_dir, scene)
        if missing:
            return ToolResult.fail("；".join(missing))

        source = capture.get("source") or {}
        self._emit_progress(
            f"网页取景：{source.get('title') or source.get('url') or '—'}"
            f"（{len(scene.get('notes') or [])} 处批注）"
        )

        deadline = time.monotonic() + BUDGET_SEC
        html = ""
        errs: list[str] = []
        last_kind = "static"
        force_full = False
        passed = False

        for k in range(1, MAX_TRIES + 1):
            if time.monotonic() > deadline:
                return ToolResult.fail(
                    f"webpage 超过时间预算（{BUDGET_SEC}s）：{'；'.join(errs[:3])}")
            if k == 1 or force_full or not html:
                force_full = False
                self._emit_progress(f"第 {k}/{MAX_TRIES} 次：LLM 编写标注层...")

                def _beat(chars: int, elapsed: float, _k=k) -> None:
                    phase = "编写中" if chars else "思考中"
                    self._emit_progress(f"LLM 第 {_k} 版{phase}：{int(elapsed)}s，已输出 {chars} 字")

                try:
                    html = compose_html(cfg, scene, on_progress=_beat)
                except ToolCancelledError:
                    raise
                except Exception as e:
                    errs = [f"标注层生成失败：{e}"]
                    force_full = True
                    continue
            else:
                self._emit_progress(f"第 {k}/{MAX_TRIES} 次：就地修补（{last_kind}）...")
                try:
                    html, applied, failed = repair_webpage(
                        html, errs, last_kind, cfg, scene)
                except ToolCancelledError:
                    raise
                except Exception as e:
                    errs = [f"修补调用失败：{e}"]
                    force_full = True
                    continue
                if applied == 0:
                    errs = ["修补清单无法应用：" + "；".join(failed[:2])]
                    force_full = True
                    continue

            html = localize_scripts(html, proj_dir)
            (proj_dir / "index.html").write_text(html, encoding="utf-8")

            self._emit_progress("渲染前闸门校验（结构 / 运行时 / 确定性）...")
            ok, _, gate_errs, kind = run_gates(proj_dir, dur, int(width), int(height))
            if not ok:
                errs = gate_errs[:3] or ["渲染前闸门未通过"]
                last_kind = kind
                self._emit_progress("  ✗ " + "；".join(errs))
                continue

            self._emit_progress("标注几何校验...")
            geo = geometry_issues(proj_dir, scene)
            if geo:
                errs = geo[:4]
                last_kind = "runtime"
                self._emit_progress("  ✗ " + "；".join(errs[:2]))
                continue

            self._emit_progress("视觉复审...")
            issues = review_frames(proj_dir, cfg, check_bottom_safe=False)
            if issues is None:
                self._emit_progress("  · 视觉复审跳过（视觉接口不可用）")
            elif issues:
                msg = "视觉复审未通过：" + "；".join(issues[:2])
                if k < MAX_TRIES:
                    errs = [msg + "。请提高截图与标注的对比，并避免标注遮挡原文。"]
                    last_kind = "visual"
                    self._emit_progress("  ✗ " + msg)
                    continue
                self._emit_progress("  ⚠ " + msg + "（已达重试上限，继续渲染）")
            else:
                self._emit_progress("  ✓ 闸门与视觉复审通过")

            passed = True
            break

        if not passed:
            return ToolResult.fail("webpage 未通过渲染前闸门：" + "；".join(errs[:3]))

        self._emit_progress(f"正在渲染视频 ({width}×{height}, {fps}fps)...")
        try:
            render(proj_dir, out, fps=int(fps))
        except FileNotFoundError:
            return ToolResult.fail("未找到 npx / node（hyperframes 依赖），无法渲染网页取景段")
        except Exception as e:
            return ToolResult.fail(f"渲染失败：{e}")

        size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0
        marks = scene.get("notes") or []
        return ToolResult.ok(
            f"网页取景完成：{out.name}｜来源 {source.get('domain') or '—'}｜批注 {len(marks)} 条",
            output_path=str(out.absolute()),
            duration_s=round(dur, 2),
            source=source,
            marks=[{"id": m["id"], "quote": m["quote"]} for m in marks],
            size_mb=round(size_mb, 1),
            project_dir=str(proj_dir),
        )

    def _auto_path(self, output_path: str, project: str | None) -> Path:
        p = Path(output_path)
        if p.is_absolute():
            return p
        base = Path(self.cwd) if self.cwd else Path.cwd()
        work = base / "video_work"
        if project:
            work = work / project
        return work / p


__all__ = ["WebpageVideoTool"]
