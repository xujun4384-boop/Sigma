# -*- coding: utf-8 -*-
"""
manim skill - Manim 讲解动画部门（数学 / 几何 / 公式 / 原理讲解）

把「Manim（3Blue1Brown 同款，用 Python 描述数学几何对象与动画）」封装为画面引擎：
  - 输入一段自然语言 brief（讲什么、分几步、要哪些元素/公式、时长），
    由**画面生成 LLM 依 skill.md 自由撰写场景代码**（不是套模板）；
  - 用 `python -m manim render` 渲染成 mp4；
  - 渲染失败自动把报错回喂 LLM 重写（自愈，最多 3 次）；
  - 成片自动对齐到目标时长与画布，保证与导演的时间轴/旁白一致。

定位：**讲解型画面引擎**——适合科普、数学、几何、公式推导、原理分步演示；
      与 opendesign（文字/排版/信息动画）、cinematic（实拍感空镜）并列。
注意：Manim 无遮挡剔除，不适合"写实实体建模"（多个实心零件会互相透视）。
本工具是「导演组」的内部引擎，一般由 director 调度，不直接暴露给用户。
"""
import os
import shutil
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent


def _auto_output_path(output_path: str, project: str = None, cwd: str = None) -> Path:
    """相对路径自动放入 video_work/<project>/ 下（与其它画面引擎一致）。"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work = base / "video_work"
    if project:
        work = work / project
    return work / p


class ManimVideoTool(BaseTool):
    name = "manim_video"
    description = (
        "Manim 讲解动画引擎：输入自然语言 brief，由 LLM 自由撰写 Manim 场景代码并渲染成 mp4。"
        "适合数学/几何/公式/原理的分步讲解（科普型画面）。"
        "渲染失败会自动依据报错重写重渲（自愈）；成片自动对齐到指定时长与画布。"
        "注意：Manim 无遮挡剔除，不适合写实实体建模。"
    )
    parameters = [
        ToolParameter("brief", "string", "本段画面需求（自然语言：讲什么、分几步、要哪些元素/公式、节奏）"),
        ToolParameter("output_path", "string", "输出 mp4 路径（相对路径自动放 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，产物集中管理；同一视频各工具保持一致", required=False),
        ToolParameter("duration", "number", "目标时长（秒）；成片会精确对齐到此长度", required=False, default=8),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "画布宽度", required=False, default=1920),
        ToolParameter("height", "integer", "画布高度", required=False, default=1080),
        ToolParameter("style_prompt", "string", "整体视觉风格（配色/背景/字体基调），不填则用深色高对比", required=False),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self._work_dir = None

    # ── 供编排器读取创作规范（"契约在哪"只有本技能一个事实来源）──
    @classmethod
    def authoring_spec(cls) -> str:
        md = SKILL_DIR / "skill.md"
        return md.read_text(encoding="utf-8") if md.exists() else ""

    def execute(self, brief: str, output_path: str, project: str = None,
                duration: float = 8, fps: int = 30, width: int = 1920,
                height: int = 1080, style_prompt: str = None, **kwargs) -> ToolResult:
        from .scripts.renderer import (SCENE_CLASS, check_manim, fit_to_duration,
                                       render_code, syntax_ok)

        if not brief or not brief.strip():
            return ToolResult.fail("brief 不能为空（需要描述要讲解的内容）")
        if duration <= 0 or fps <= 0 or width <= 0 or height <= 0:
            return ToolResult.fail("duration/fps/width/height 必须大于 0")

        # 画面生成 LLM：复用主 LLM
        cfg = self.llm_config or {}
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            return ToolResult.fail("LLM 配置不完整，无法编写 Manim 场景代码。请在前端配置 LLM。")

        ver = check_manim()
        if not ver:
            return ToolResult.fail("未检测到可用的 manim（请先安装：pip install manim）")

        spec = self.authoring_spec()
        if not spec.strip():
            return ToolResult.fail("缺少 Manim 创作规范（skills/manim/skill.md）")

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)
        work = out.parent / f"{out.stem}_manim"
        work.mkdir(parents=True, exist_ok=True)
        code_path = work / "scene.py"

        style = (style_prompt or "").strip() or "深色背景、高对比、克制配色、动效平滑"
        # Manim 的可视高度固定 8 单位，宽度按画布比例推导（与 renderer._frame_size 一致）。
        # 竖屏 1080×1920 → 4.5×8；如果按 16:9 的 14 单位宽来排版，文字会显得非常小。
        frame_h = 8.0
        frame_w = frame_h * float(width) / max(1.0, float(height))
        if height > width:
            orientation = (
                f"竖屏（可视区域仅 {frame_w:.2f} 单位宽）。内容以**纵向堆叠**为主；"
                f"单行文字尽量 ≤ 8~10 个汉字，字号建议 48~72；不要左右并排多列；"
                f"文字总宽度不超过 {frame_w * 0.9:.2f} 单位；四周留 0.3 单位以上余量。"
            )
        elif width > height:
            orientation = (
                f"横屏（可视区域 {frame_w:.2f} 单位宽）。可用左右分栏；"
                f"单行文字总宽度不超过 {frame_w * 0.9:.2f} 单位。"
            )
        else:
            orientation = (
                f"方形（可视区域 {frame_w:.2f} 单位宽）。按纵向主构图、左右留白；"
                f"单行文字总宽度不超过 {frame_w * 0.9:.2f} 单位。"
            )
        base_ctx = (
            f"{brief}\n\n"
            "## 本段渲染参数\n"
            f"- 目标时长：{float(duration):.2f} 秒（**必须精确定长**：用 run_time 与 self.wait 让整段正好 ≈ 该时长）\n"
            f"- 画布：{width} × {height} @ {fps}fps\n"
            f"- Manim 可视区域：{frame_w:.2f} × {frame_h:.2f} 单位（宽 × 高）\n"
            f"- 构图：{orientation}\n"
            f"- 视觉风格：{style}\n\n"
            f"入口类名必须为 `class {SCENE_CLASS}`（Scene 或 ThreeDScene）。"
            "只输出 Python 源码本身，不要解释、不要 Markdown 代码块标记。"
        )

        from skills.opendesign.scripts.renderer import (
            call_llm_text, strip_markdown_fences,
            _call_with_token_fallback, LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
        )

        last_err, code = "", ""
        for attempt in range(1, 4):
            self._emit_progress(f"正在撰写 Manim 场景代码（第 {attempt}/3 次）...")
            ctx = base_ctx if attempt == 1 else (
                base_ctx
                + f"\n\n## 上一版失败原因（务必修正，不要重复同样错误）\n{last_err}\n\n"
                + "## 上一版代码（请在此基础上修正后，重新输出完整可运行的 Python）\n" + code
            )
            try:
                raw = _call_with_token_fallback(
                    lambda budget: call_llm_text(
                        system_prompt=spec, context=ctx,
                        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
                        protocol=cfg.get("protocol", "anthropic"),
                        provider=cfg.get("provider"), thinking=cfg.get("thinking"),
                        max_tokens=budget, timeout=300,
                    ),
                    max_tokens=LONG_OUTPUT_MAX_TOKENS,
                    fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
                )
            except Exception as e:
                return ToolResult.fail(f"Manim 场景代码生成失败: {e}")

            code = strip_markdown_fences(raw).strip()
            if not code:
                last_err = "模型返回空代码"
                continue

            err = syntax_ok(code)
            if err is None and f"class {SCENE_CLASS}" not in code:
                err = f"未找到入口类 `class {SCENE_CLASS}`（必须定义且只暴露这一个入口类）"
            if err:
                last_err = err
                self._emit_progress(f"Manim 代码校验未过，自动修复重试：{err[:120]}")
                continue

            try:
                code_path.write_text(code, encoding="utf-8")
            except OSError as e:
                return ToolResult.fail(f"场景代码写入失败: {e}")

            self._emit_progress(f"Manim 渲染中（{width}x{height}@{fps}fps，第 {attempt}/3 次）...")
            try:
                raw_mp4 = render_code(code_path, work / "media", width, height, fps,
                                      output_name=out.stem)
                fit_to_duration(raw_mp4, out, float(duration), width, height, fps)
            except Exception as e:
                last_err = str(e)
                self._emit_progress(f"Manim 渲染失败，自动修复重试：{last_err[:160]}")
                continue

            size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0
            return ToolResult.ok(
                f"Manim 讲解动画已生成: {out.name}（{float(duration):.2f}s, "
                f"{width}x{height}@{fps}, {size_mb:.1f}MB，第 {attempt} 次成片）",
                output_path=str(out.absolute()),
                duration=float(duration),
                resolution=f"{width}x{height}",
                fps=fps,
                size_mb=round(size_mb, 1),
                attempts=attempt,
                source=str(code_path),
            )

        return ToolResult.fail(f"Manim 场景生成/渲染失败（已尝试 3 次）：{last_err}")


__all__ = ["ManimVideoTool"]
