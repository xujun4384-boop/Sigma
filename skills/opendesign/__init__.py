"""
opendesign skill - 基于 OpenDesign/HyperFrames 契约的 HTML 视频生成

提供工具:
  opendesign_video - 输入内容描述，LLM 按 HyperFrames 契约写 index.html，
                     再用 npx hyperframes render 渲染成 mp4。

设计要点:
  - LLM 配置复用主 LLM（server.py 注入的 llm_config），无需额外前端配置。
  - 与生图解耦：图片由 image_generate 技能预生成，通过 assets_dir 参数传入，
    本 skill 只负责把它们同步到 HyperFrames 项目并让 LLM 引用。
"""
import os
import shutil
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent

_TONE_HINTS = {
    "academic": "学术严谨，克制内敛，信息密度高，避免花哨动效",
    "product": "产品商务，现代简洁，突出卖点与品牌质感",
    "editorial": "编辑杂志，强排版与字体层级，留白优雅",
    "technical": "技术专业，清晰的数据与图表呈现，冷静理性",
}


def _auto_output_path(output_path: str, project: str, cwd: str) -> Path:
    """相对路径自动放入 video_work/<project>/ 下，与 video_generate 约定一致。"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    if project:
        work_dir = work_dir / project
    return work_dir / p


def _build_composer_context(
    brief: str,
    duration_s: int,
    n_scenes: int,
    style_prompt: str,
    tone: str,
    width: int,
    height: int,
    assets: list[str] | None = None,
) -> str:
    """构建给 LLM 的内容简报（composer_context）。"""
    tone_hint = _TONE_HINTS.get(tone, _TONE_HINTS["product"])
    style = (style_prompt or "").strip() or "现代简洁，留白充足，配色克制，动效平滑"
    parts = [
        "请生成一段视频的 HyperFrames 合成（index.html）。\n\n",
        "## 内容简报\n",
        f"{brief}\n\n",
        "## 视频参数\n",
        f"- 总时长：{duration_s} 秒\n",
        f"- 场景数：约 {n_scenes} 个\n",
        f"- 画布：{width} × {height}\n\n",
        "## 视觉风格\n",
        f"{style}\n\n",
        "## 语气\n",
        f"{tone_hint}\n",
    ]
    if assets:
        lines = "\n".join(f"- assets/{a}" for a in assets)
        parts += [
            "\n## 可用图片（已同步到项目 assets/ 目录，请直接引用）\n",
            f"{lines}\n",
            "图片引用方式：<img src=\"assets/<文件名>\"> 或 CSS background-image: url(assets/<文件名>)。\n",
        ]
    return "".join(parts)


def _sync_assets(assets_dir: str, cwd: str, proj_dir: Path) -> list[str]:
    """把 assets_dir 目录下的文件复制到 HyperFrames 项目的 assets/，返回文件名列表。"""
    src = Path(assets_dir).expanduser()
    if not src.is_absolute():
        src = (Path(cwd) if cwd else Path(os.getcwd())) / src
    if not src.is_dir():
        return []

    dst = proj_dir / "assets"
    dst.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(src.iterdir()):
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            copied.append(f.name)
    return copied


class OpendesignVideoTool(BaseTool):
    name = "opendesign_video"
    description = (
        "基于 HyperFrames 框架生成 HTML 视频（mp4）。输入内容描述，由 LLM 编写 "
        "HTML+GSAP 动画，再用本地无头浏览器确定性渲染成视频。"
        "适合品牌宣传片、产品介绍、数据动画等。"
        "如需配图，先用 generate_image 生图到目录，再通过 assets_dir 传入，"
        "LLM 会自动引用这些图片。"
    )
    parameters = [
        ToolParameter("brief", "string", "视频内容描述：主题、文案、要点、结构等"),
        ToolParameter("output_path", "string", "输出 mp4 文件路径（相对路径自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，用于创建独立输出目录，如 brand_intro", required=False),
        ToolParameter("duration_s", "integer", "视频总时长（秒）", required=False, default=8),
        ToolParameter("n_scenes", "integer", "场景数量", required=False, default=3),
        ToolParameter("style_prompt", "string", "视觉风格描述（配色/字体/动效），不填则用现代简洁风格", required=False),
        ToolParameter("tone", "string", "语气: academic / product / editorial / technical", required=False, default="product"),
        ToolParameter("assets_dir", "string", "配图目录，图片会同步到 HyperFrames 项目 assets/ 供 LLM 引用（配合 generate_image 使用）", required=False),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 opendesign_llm_config: dict = None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.opendesign_llm_config = opendesign_llm_config or {}

    def execute(
        self,
        brief: str,
        output_path: str,
        project: str = None,
        duration_s: int = 8,
        n_scenes: int = 3,
        style_prompt: str = None,
        tone: str = "product",
        assets_dir: str = None,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        **kwargs,
    ) -> ToolResult:
        from .scripts.renderer import call_llm_compose, render, scaffold_project

        # 优先用 opendesign 专用 LLM（写 HTML 需强代码模型），未配置完整时回退主 LLM
        cfg = self.opendesign_llm_config
        if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
            cfg = self.llm_config
        base_url = cfg.get("base_url", "")
        api_key = cfg.get("api_key", "")
        model = cfg.get("model", "")
        protocol = cfg.get("protocol", "anthropic")

        if not base_url or not api_key or not model:
            return ToolResult.fail(
                "LLM 配置不完整，无法编写视频 HTML。请在前端配置 LLM（base_url, api_key, model）。"
            )

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        # HyperFrames 项目目录（中间产物，与最终 mp4 同目录）
        proj_dir = out.parent / f"{out.stem}_hyperframes"

        # 1. 生成脚手架
        try:
            scaffold_project(proj_dir, out.stem)
        except Exception as e:
            return ToolResult.fail(f"脚手架生成失败: {e}")

        # 2. 同步配图（解耦：图片由 image_generate 预生成，这里只复制进来）
        assets = []
        if assets_dir:
            try:
                assets = _sync_assets(assets_dir, self.cwd, proj_dir)
            except Exception as e:
                return ToolResult.fail(f"配图同步失败: {e}")

        context = _build_composer_context(
            brief, duration_s, n_scenes, style_prompt, tone, width, height, assets
        )

        # 3. LLM 写 index.html
        self._emit_progress(f"正在由 LLM 编写视频 HTML ({duration_s}s, {n_scenes} 场景)...")
        try:
            html = call_llm_compose(
                context=context,
                base_url=base_url,
                api_key=api_key,
                model=model,
                protocol=protocol,
            )
        except Exception as e:
            return ToolResult.fail(f"LLM 编写 HTML 失败: {e}")

        (proj_dir / "index.html").write_text(html, encoding="utf-8")

        # 4. npx hyperframes render
        self._emit_progress(f"正在渲染视频 ({width}x{height}, {fps}fps)...")
        try:
            result_path = render(proj_dir, out, fps=fps)
        except FileNotFoundError:
            return ToolResult.fail(
                "未找到 npx / node，请确认已安装 Node.js（npx hyperframes 依赖）。"
            )
        except Exception as e:
            return ToolResult.fail(f"渲染失败: {e}")

        size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0

        return ToolResult.ok(
            f"视频生成完成: {out.name}",
            output_path=str(out.absolute()),
            duration_s=duration_s,
            resolution=f"{width}x{height}",
            fps=fps,
            size_mb=round(size_mb, 1),
            assets_count=len(assets),
            project_dir=str(proj_dir),
        )


__all__ = ["OpendesignVideoTool"]
