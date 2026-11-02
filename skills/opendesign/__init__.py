"""
opendesign skill - 基于 OpenDesign/HyperFrames 契约的 HTML 视频生成

提供工具:
  opendesign_video - 输入内容描述，LLM 按 HyperFrames 契约写 index.html，
                     再用 npx hyperframes render 渲染成 mp4。

设计要点:
  - LLM 配置复用主 LLM（server.py 注入的 llm_config），无需额外前端配置。
  - 配图由引擎自己按需生成：LLM 在写 index.html 的同时用 data-gen 属性声明要什么图，
    引擎在这一版 HTML 落到磁盘前把它们生成到项目 assets/ 并回填 src。
    图片动效与声明是同一次推理的产物 —— 图不是贴图，而是画面运动的主体。
  - 上游预生成的图仍可通过 assets_dir 传入，与引擎自生成的图共存。
"""
import os
import re
import shutil
import time
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from skills import image_assets

SKILL_DIR = Path(__file__).resolve().parent

# 生图失败时的透明占位：避免浏览器显示破图图标，场景的氛围层照样在，动效不中断。
_TRANSPARENT_PX = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
    "QVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)

# 渲染前闸门的自愈预算：最多生成/修补 3 版；整体超过 BUDGET_SEC 就放弃，避免无限打转
MAX_TRIES = 3
BUDGET_SEC = 900

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
    image_brief: str = "",
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
        f"- 场景数：{n_scenes} 个（每个场景**至少停留 5 秒**，不要再增加场景）\n",
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
            "图片引用方式：<img src=\"assets/<文件名>\"> 或 CSS background-image: url(assets/<文件名>)。\n"
            "这些图同样必须参与动画（视差/推拉/揭示），不要静态铺底。\n",
        ]
    if image_brief:
        parts += ["\n## 图片素材与动效\n", image_brief]
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


def _attr(tag: str, name: str) -> str:
    """读标签属性值；用负向断言避免 data-gen 误匹配 data-gen-aspect。"""
    m = re.search(rf'\b{re.escape(name)}(?![\w-])\s*=\s*(["\'])(.*?)\1', tag, re.S | re.IGNORECASE)
    return m.group(2).strip() if m else ""


def _set_attr(tag: str, name: str, value: str) -> str:
    pat = re.compile(rf'(\b{re.escape(name)}(?![\w-])\s*=\s*)(["\'])(.*?)\2',
                     re.S | re.IGNORECASE)
    if pat.search(tag):
        return pat.sub(lambda m: f'{m.group(1)}"{value}"', tag, count=1)
    return tag[:-1].rstrip() + f' {name}="{value}">'


def _drop_attr(tag: str, name: str) -> str:
    return re.sub(rf'\s*\b{re.escape(name)}(?![\w-])\s*=\s*(["\']).*?\1', "", tag, flags=re.S | re.I)


def _image_brief(max_images: int) -> str:
    """告诉 LLM 怎么声明图、以及图必须怎么动。"""
    return (
        f"你可以在画面里使用 AI 生成图片，全片最多 {max_images} 张。\n"
        "声明方式：写在 <img> 标签上，引擎会在这一版 HTML 落盘前按描述生成图片、存进项目 assets/ 并回填 src：\n"
        '  <img src="assets/gen-1.png" data-gen="英文画面描述：主体 / 材质 / 光线 / 构图" data-gen-aspect="16:9">\n'
        "- src 必须是 assets/ 下的英文小写文件名，全片唯一（gen-1.png、gen-2.png …）。\n"
        "- data-gen-aspect 可选：16:9（场景底/满屏）、4:3（卡片/中景）、3:4（竖构图）、1:1（图标/方图）。\n"
        "- 描述只写画面本身，不要写文字；生成的图不含文字、logo、可辨识真人，是插画/抽象风格。\n"
        "- 同一张图只声明一次，多个场景要复用就重复引用同一个 src，不要重复描述。\n"
        "- **不要引用没有 data-gen 的 assets/ 文件**：除上游已同步进来的图（见「可用图片」清单），\n"
        "  assets/ 下不存在任何图片，写了就是破图。要用的图必须在这一轮用 data-gen 声明。\n\n"
        "**图片必须参与动效，这是硬要求：**\n"
        "- 每张图都要挂进 GSAP 时间轴：遮罩揭示（clip-path / scaleX 展开）、缓慢推拉（scale 1.0→1.08）、\n"
        "  多层视差（远景与前景不同速度位移）、跟随转场位移/旋转，至少要占两项中的一项。\n"
        "- 禁止只当静态 background-image 铺底不动；禁止一张图在整个场景里纹丝不动。\n"
        "- 需要纵深时把图拆成 2~3 层（远景/中景/前景），分别用不同速度位移。\n"
        "- 图和文字/数据要抢空间时，让图片承担氛围与空间感，信息和文案仍由排版完成。\n"
    )


def _ensure_images(html: str, proj_dir: Path, skill_manager, style_prefix: str,
                   max_images: int, progress=None) -> tuple[str, int, list[dict]]:
    """把 HTML 里 data-gen 声明的图就地生成并回填 src。

    返回 (新 HTML, 本次新生成张数, 失败清单)。失败清单每项是
    {name, prompt, error}，调用方要把它交给 LLM 修正 —— 只报"失败"而不说原因，
    模型下一轮还会用同一句描述踩同一个坑。

    失败时**保留 data-gen 属性**（只把 src 换成透明占位），这样修补时模型能看见
    原描述并直接改；重试成功后属性会被清掉。
    """
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    made, used, failed, seen = 0, 0, [], set()

    def on_tag(match):
        nonlocal made, used
        tag = match.group(0)
        prompt = _attr(tag, "data-gen")
        if not prompt:
            return tag
        declared = _attr(match.group(0), "src")
        name = image_assets.safe_name(declared)
        if not name:
            name = image_assets.asset_filename(
                _attr(match.group(0), "id") or "img", prompt)

        if used >= max_images:               # 超上限不是错误，改描述也没用，直接占位收尾
            if progress:
                progress(f"  · 超过 {max_images} 张上限，{name} 不再生成")
            return _set_attr(_drop_attr(_drop_attr(tag, "data-gen"), "data-gen-aspect"),
                             "src", _TRANSPARENT_PX)

        if name in seen:                     # 同一文件名声明多次：只生成一次，引用同一张
            return _set_attr(_drop_attr(_drop_attr(tag, "data-gen"), "data-gen-aspect"),
                             "src", f"assets/{name}")
        seen.add(name)
        used += 1

        path, err, created = image_assets.generate(
            skill_manager=skill_manager,
            prompt=prompt,
            save_dir=assets_dir,
            filename=name,
            aspect=_attr(match.group(0), "data-gen-aspect"),
            style_prefix=style_prefix,
            progress=progress,
        )
        if path is None:
            failed.append({"name": name, "prompt": prompt, "error": err})
            return _set_attr(tag, "src", _TRANSPARENT_PX)
        if created:
            made += 1
        return _set_attr(_drop_attr(_drop_attr(tag, "data-gen"), "data-gen-aspect"),
                         "src", f"assets/{path.name}")

    return _IMG_TAG_RE.sub(on_tag, html), made, failed


class OpendesignVideoTool(BaseTool):
    name = "opendesign_video"
    description = (
        "基于 HyperFrames 框架生成 HTML 视频（mp4）。输入内容描述，由 LLM 编写 "
        "HTML+GSAP 动画，再用本地无头浏览器确定性渲染成视频。"
        "适合品牌宣传片、产品介绍、数据动画等。"
        "引擎会按需自己生成配图：LLM 在 HTML 里用 data-gen 声明画面描述并同时编排动效，"
        "图片落盘到项目 assets/ 后被引用，全程无外链。"
        "上游预生成的图也可以通过 assets_dir 传入。"
    )
    parameters = [
        ToolParameter("brief", "string", "视频内容描述：主题、文案、要点、结构等"),
        ToolParameter("output_path", "string", "输出 mp4 文件路径（相对路径自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，用于创建独立输出目录，如 brand_intro", required=False),
        ToolParameter("duration_s", "integer", "视频总时长（秒）", required=False, default=8),
        ToolParameter("n_scenes", "integer", "场景数量；留空则按时长自动（约每 5 秒 1 个场景，最少 1、最多 4）", required=False, default=None),
        ToolParameter("style_prompt", "string", "视觉风格描述（配色/字体/动效），不填则用现代简洁风格", required=False),
        ToolParameter("tone", "string", "语气: academic / product / editorial / technical", required=False, default="product"),
        ToolParameter("assets_dir", "string", "上游预生成的配图目录，图片会同步进项目 assets/ 供 LLM 引用（可选）", required=False),
        ToolParameter("with_images", "boolean", "是否允许引擎按需生图（默认关；导演组按面板的 images 字段显式开启）", required=False, default=False),
        ToolParameter("max_images", "integer", "本片最多生成几张图（默认 4）", required=False, default=4),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 skill_manager=None, **kwargs):
        super().__init__(cwd)
        self.llm_config = llm_config or {}
        self.skill_manager = skill_manager

    def execute(
        self,
        brief: str,
        output_path: str,
        project: str = None,
        duration_s: int = 8,
        n_scenes: int = None,
        style_prompt: str = None,
        tone: str = "product",
        assets_dir: str = None,
        with_images: bool = False,
        max_images: int = 4,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        **kwargs,
    ) -> ToolResult:
        from .scripts.renderer import (
            ToolCancelledError, call_llm_compose, localize_scripts, render, scaffold_project,
        )
        from .scripts.gate import repair_html, review_frames, run_gates

        # 复用主 LLM（写 HTML 需强代码模型，由主 LLM 承担）
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

        # 2. 同步上游预生成的配图（引擎自己生成的图在每一版 HTML 落盘前补进同一个目录）
        assets = []
        if assets_dir:
            try:
                assets = _sync_assets(assets_dir, self.cwd, proj_dir)
            except Exception as e:
                return ToolResult.fail(f"配图同步失败: {e}")

        # 场景数：未显式指定则按时长自动（每场 ≥5s，最多 4 场），避免段内切得太频
        if not n_scenes or int(n_scenes) <= 0:
            n_scenes = max(1, min(4, int(duration_s // 5)))
            self._emit_progress(f"按时长自动定场景数：{n_scenes} 个（每场 ≥ 5s）")

        # 生图开关：没有 skill_manager 就没有生图通道，此时不向 LLM 许愿
        can_generate = bool(with_images) and self.skill_manager is not None
        max_images = max(0, int(max_images or 0))
        can_generate = can_generate and max_images > 0
        style_prefix = (style_prompt or "").strip() or _TONE_HINTS.get(tone, "")

        context = _build_composer_context(
            brief, duration_s, n_scenes, style_prompt, tone, width, height, assets,
            _image_brief(max_images) if can_generate else "",
        )

        # 3. 生成 HTML → 渲染前闸门 → 渲染：最多 MAX_TRIES 次。
        #    k=1 整篇生成；失败后优先"原地修补"（只回传报错处的最小改动）；
        #    修补无法落地则 force_full 回退整篇重写。
        #    闸门不过就不送渲染 —— 免得 LLM 写出运行时报错的 HTML 把整个导演组拖崩。
        deadline = time.monotonic() + BUDGET_SEC
        html = ""
        errs: list[str] = []
        last_kind = "static"
        force_full = False
        passed = False
        generated_images = 0

        for k in range(1, MAX_TRIES + 1):
            if time.monotonic() > deadline:
                return ToolResult.fail(
                    f"opendesign 超过时间预算（{BUDGET_SEC}s），最后一次错误：{'；'.join(errs[:3])}"
                )

            mode = "full" if (k == 1 or force_full or not html) else "repair"
            if mode == "repair":
                self._emit_progress(f"第 {k}/{MAX_TRIES} 次：原地修补（{last_kind}，只改报错处）...")
                try:
                    html, applied, failed = repair_html(
                        html, errs, last_kind, cfg, duration_s, width, height
                    )
                except ToolCancelledError:
                    raise
                except Exception as e:
                    errs = [f"修补调用失败：{e}"]
                    force_full = True
                    self._emit_progress(f"  ✗ {errs[0]}，下次回退整篇重写")
                    continue
                if applied == 0:
                    errs = ["修补清单无法应用（find 未找到或不唯一）：" + "；".join(failed[:2])]
                    force_full = True
                    self._emit_progress("  ✗ 修补无法应用，下次回退整篇重写")
                    continue
                self._emit_progress(
                    f"  · 已应用 {applied} 处修补" + (f"（{len(failed)} 处未应用）" if failed else "")
                )
            else:
                force_full = False
                ctx = context + ("\n\n上次被闸门拒绝，本次务必修正：\n" + "\n".join(errs) if errs else "")
                self._emit_progress(
                    f"第 {k}/{MAX_TRIES} 次：LLM 编写视频 HTML ({duration_s}s, {n_scenes} 场景)..."
                )

                def _on_llm_progress(chars: int, elapsed: float, _k=k) -> None:
                    # 心跳：让前端看到确实在写；真正停滞由 renderer 的停滞超时兜底
                    phase = "编写中" if chars else "思考中"
                    self._emit_progress(f"LLM 第 {_k} 版 {phase}：{int(elapsed)}s，已输出 {chars} 字")

                try:
                    html = call_llm_compose(
                        context=ctx,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        protocol=protocol,
                        provider=cfg.get("provider"),
                        thinking=cfg.get("thinking"),
                        on_progress=_on_llm_progress,
                    )
                except ToolCancelledError:
                    raise
                except Exception as e:
                    errs = [f"调用失败：{e}"]
                    force_full = True
                    self._emit_progress(f"  ✗ {errs[0]}")
                    continue

            # 离线加固：把外部 CDN 的 <script src> 改写为项目内的本地内置脚本（如 gsap.min.js），
            # 避免渲染机连不上 jsDelivr 等 CDN 时整段渲染失败。
            html = localize_scripts(html, proj_dir)

            # 图片：LLM 在 HTML 里用 data-gen 声明的素材，这里就地生成、落盘并回填 src。
            # 必须在写 index.html 之前完成 —— 闸门和渲染都要读到真实存在的本地文件。
            if can_generate:
                html, made, img_failed = _ensure_images(
                    html, proj_dir, self.skill_manager, style_prefix, max_images,
                    progress=self._emit_progress)
                generated_images += made
                if made:
                    self._emit_progress(f"  · 已生成 {made} 张配图（assets/）")
                if img_failed:
                    detail = "；".join(
                        f'{f["name"]}（{f["prompt"][:40]}）→ {f["error"][:100]}'
                        for f in img_failed[:2])
                    if k < MAX_TRIES:
                        # 把原始报错交给模型：改描述或换图形，否则下一轮必然复现同一个错误
                        errs = [
                            f"配图生成失败：{detail}。请把对应 <img> 的 data-gen 改成"
                            "更短、更具体的英文画面描述（去掉人名/品牌/敏感内容），"
                            "或者删掉这张图改用 CSS 图形；不要动其他版式。"
                        ]
                        last_kind = "image"
                        self._emit_progress("  ⚠ 配图失败，已把报错交给 LLM 修正：" + detail)
                        continue
                    self._emit_progress("  ⚠ 配图最终失败，用占位继续渲染：" + detail)

            (proj_dir / "index.html").write_text(html, encoding="utf-8")

            # 闸1 静态结构 / 闸2 运行时 / 闸3 确定性
            self._emit_progress("渲染前闸门校验（结构 / 运行时 / 确定性）...")
            ok, _, gate_errs, kind = run_gates(proj_dir, duration_s, width, height)
            if not ok:
                errs = gate_errs[:3] or ["渲染前闸门未通过"]
                last_kind = kind
                self._emit_progress("  ✗ " + "；".join(errs))
                continue

            # 闸5 视觉复审：文字可读性 + 底部字幕安全区
            issues = review_frames(proj_dir, cfg)
            if issues is None:
                self._emit_progress("  · 视觉复审跳过（视觉接口不可用）")
            elif issues:
                msg = "视觉复审未通过：" + "；".join(issues[:2])
                if k < MAX_TRIES:
                    errs = [msg + "。请提高文字与背景对比，并把底部 8~12% 区域留白（不放文字/按钮/logo）。"]
                    last_kind = "visual"
                    self._emit_progress("  ✗ " + msg)
                    continue
                self._emit_progress("  ⚠ " + msg + "（已达重试上限，保留本版继续渲染）")
            else:
                self._emit_progress("  ✓ 闸门与视觉复审通过")

            passed = True
            break

        if not passed:
            return ToolResult.fail("opendesign 3 版均未通过渲染前闸门：" + "；".join(errs[:3]))

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
            generated_images=generated_images,
            project_dir=str(proj_dir),
        )


__all__ = ["OpendesignVideoTool"]
