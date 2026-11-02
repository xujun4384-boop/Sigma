# -*- coding: utf-8 -*-
"""
blender skill - Blender 真 3D 引擎（写实物件 / 场景 / 产品级渲染）

把「Blender（bpy，真 3D：真遮挡 + PBR 材质 + 真实光照 + 相机运动）」封装为画面引擎：
  - 输入一段自然语言 brief（做什么物件/场景、材质、运镜、时长），
    由**画面生成 LLM 依 skill.md 自由撰写 bpy 场景脚本**（不是套模板）；
  - 用 `blender -b --python harness.py` 无头渲染（Cycles CPU）为 PNG 序列，再 ffmpeg 合成 mp4；
  - 渲染失败自动把报错回喂 LLM 重写（自愈，最多 3 次）；
  - 时长由"总帧数 = 时长 × 帧率"精确保证。

定位：**写实 3D 画面引擎**——产品外观、写实物件、空间/场景、3D 文字 Logo 等；
      与 opendesign（信息排版）、manim（数学讲解）、cinematic（实拍感）互补。

⚠️ 状态：**暂不进导演组**。稳定性/质量/速度尚未达标，先作为内部
   引擎保留、可单独调用，等后期完善（速度/成功率先行）再纳入导演阵容。
依赖：Blender 本体（便携版可解压即用）；调用方需能定位 blender.exe。
"""
import os
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


class BlenderVideoTool(BaseTool):
    name = "blender_video"
    description = (
        "Blender 真 3D 引擎：输入自然语言 brief，由 LLM 自由撰写 bpy 场景脚本并渲染成 mp4"
        "（真遮挡 + PBR 材质 + 真实光照）。适合写实物件/产品/场景/3D 文字。"
        "渲染失败会依据报错自动重写重渲（自愈）。"
        "注意：Cycles CPU 渲染较慢，建议控低采样/短时长/少多边形。"
        "状态：暂不进导演组（待完善）。"
    )
    parameters = [
        ToolParameter("brief", "string", "本段画面需求（自然语言：做什么物件/场景、材质、运镜、节奏）"),
        ToolParameter("output_path", "string", "输出 mp4 路径（相对路径自动放 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，产物集中管理；同一视频各工具保持一致", required=False),
        ToolParameter("duration", "number", "目标时长（秒）；成片按 帧数=时长×帧率 精确对齐", required=False, default=3),
        ToolParameter("fps", "integer", "帧率", required=False, default=24),
        ToolParameter("width", "integer", "画布宽度", required=False, default=1280),
        ToolParameter("height", "integer", "画布高度", required=False, default=720),
        ToolParameter("samples", "integer", "Cycles 采样数（越大越干净越慢），默认 20", required=False, default=20),
        ToolParameter("style_prompt", "string", "整体视觉风格（背景/光照/材质基调），不填则用深色棚拍风", required=False),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}

    @classmethod
    def authoring_spec(cls) -> str:
        md = SKILL_DIR / "skill.md"
        return md.read_text(encoding="utf-8") if md.exists() else ""

    def execute(self, brief: str, output_path: str, project: str = None,
                duration: float = 3, fps: int = 24, width: int = 1280,
                height: int = 720, samples: int = 20, style_prompt: str = None,
                **kwargs) -> ToolResult:
        from .scripts.renderer import (check_blender, encode, probe_duration,
                                       render, syntax_ok)

        if not brief or not brief.strip():
            return ToolResult.fail("brief 不能为空（需要描述要做什么画面）")
        if duration <= 0 or fps <= 0 or width <= 0 or height <= 0:
            return ToolResult.fail("duration/fps/width/height 必须大于 0")

        cfg = self.llm_config or {}
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            return ToolResult.fail("LLM 配置不完整，无法编写 Blender 场景脚本。请在前端配置 LLM。")

        ver = check_blender()
        if not ver:
            return ToolResult.fail("未检测到可用的 Blender（请安装 Blender 或在 PATH 提供 blender）")

        spec = self.authoring_spec()
        if not spec.strip():
            return ToolResult.fail("缺少 Blender 创作规范（skills/blender/skill.md）")

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)
        work = out.parent / f"{out.stem}_blender"
        work.mkdir(parents=True, exist_ok=True)
        scene_path = work / "scene.py"
        frames_dir = work / "frames"
        frames = max(2, int(round(float(duration) * fps)))

        style = (style_prompt or "").strip() or "深色棚拍风：深色背景 + 三点光（key/fill/rim）+ 地面/背景板"

        from skills.opendesign.scripts.renderer import (
            call_llm_text, strip_markdown_fences,
            _call_with_token_fallback, LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
        )

        last_err, code = "", ""
        for attempt in range(1, 4):
            self._emit_progress(f"正在撰写 Blender 场景脚本（第 {attempt}/3 次）...")
            ctx = (
                f"{brief}\n\n"
                "## 本段渲染参数\n"
                f"- 总帧数：{frames}（= {float(duration):.2f}s × {fps}fps；动画请安排在 frame 1~{frames}）\n"
                f"- 画布：{width} × {height} @ {fps}fps\n"
                f"- 视觉风格：{style}\n"
                f"- 采样：{samples}（Cycles CPU，注意别堆太多多边形/透射材质）\n\n"
                "契约：只输出一个 Python 源码，定义 `def build():` 来搭建场景"
                "（物体/材质/灯光/相机/关键帧）；**不要**设置渲染参数、不要自己渲染或存文件。"
                "只输出源码本身，不要解释、不要 Markdown 代码块标记。"
            )
            if attempt > 1:
                ctx += (
                    f"\n\n## 上一版失败原因（务必修正，不要重复同样错误）\n{last_err}\n\n"
                    "## 上一版代码（请在此基础上修正后，重新输出完整可运行代码）\n" + code
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
                return ToolResult.fail(f"Blender 场景脚本生成失败: {e}")

            code = strip_markdown_fences(raw).strip()
            if not code:
                last_err = "模型返回空代码"
                continue

            err = syntax_ok(code)
            if err:
                last_err = err
                self._emit_progress(f"Blender 脚本校验未过，自动修复重试：{err[:120]}")
                continue

            try:
                scene_path.write_text(code, encoding="utf-8")
            except OSError as e:
                return ToolResult.fail(f"场景脚本写入失败: {e}")

            self._emit_progress(f"Blender 渲染中（{width}x{height}, {frames} 帧, {samples} 采样，第 {attempt}/3 次）...")
            try:
                render(scene_path, frames_dir, width, height, fps, frames, samples)
                encode(frames_dir, out, fps)
            except Exception as e:
                last_err = str(e)
                self._emit_progress(f"Blender 渲染失败，自动修复重试：{last_err[:160]}")
                continue

            dur = probe_duration(out)
            size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0
            return ToolResult.ok(
                f"Blender 3D 画面已生成: {out.name}（{dur:.2f}s, {width}x{height}@{fps}, "
                f"{size_mb:.1f}MB，第 {attempt} 次成片）",
                output_path=str(out.absolute()),
                duration=round(dur, 2),
                resolution=f"{width}x{height}",
                fps=fps,
                samples=samples,
                size_mb=round(size_mb, 1),
                attempts=attempt,
                source=str(scene_path),
            )

        return ToolResult.fail(f"Blender 场景生成/渲染失败（已尝试 3 次）：{last_err}")


__all__ = ["BlenderVideoTool"]
