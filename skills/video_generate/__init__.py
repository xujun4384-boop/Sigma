"""
video_generate skill - 视频生成工具集

提供三个工具:
  video_scene   - 单个场景录制（模板 or 自定义 HTML → mp4）
  video_tts     - 文本语音合成（text → mp3）
  video_compose - 多场景拼接合成（video+audio+bgm+subtitle → mp4）

LLM 可通过 sandbox 编写自定义 HTML 动画，然后调用 video_scene 录制。
"""
import json
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

SKILL_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SKILL_DIR / "templates"


def _auto_output_path(output_path: str, project: str = None, cwd: str = None) -> Path:
    """自动将路径放入 video_work/<project>/ 目录下，每个视频独立文件夹"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    if project:
        work_dir = work_dir / project
    return work_dir / p


# ─── 默认模板参数 ───

DEFAULT_PARAMS = {
    "particle_brand": {
        "WIDTH": 1920, "HEIGHT": 1080, "DURATION": 8, "FPS": 30,
        "BRAND_NAME": "", "SUBTITLE": "", "TAGLINE": "",
        "PRIMARY_COLOR": "#4A90D9", "BG_COLOR": "#0a0a14",
        "PARTICLE_COUNT": 800, "TEXT_SPREAD": 500,
        "GRID_COUNT": 30, "TITLE_SIZE": 140,
        "REVEAL_STYLE": "typewriter", "GLOW_INTENSITY": 0.6,
    },
    "data_counter": {
        "WIDTH": 1920, "HEIGHT": 1080, "DURATION": 10,
        "TITLE_TEXT": "", "SUBTITLE": "",
        "BG_COLOR": "linear-gradient(180deg, #1e3c72 0%, #2a5298 50%, #1e3c72 100%)",
        "ACCENT_COLOR": "#ffd700", "ACCENT_GLOW": "rgba(255,215,0,0.6)",
        "TITLE_SIZE": 80, "STAT_SIZE": 100,
        "TITLE_FRAMES": 60, "SUB_FRAMES": 90, "STAT_FRAMES": 120, "NUM_FRAMES": 150,
        "STATS_JSON": json.dumps([]),
    },
}


def _resolve_template_path(template_name: str) -> Path:
    """模板名可以是 'particle_brand' 或自定义路径"""
    tpl_path = TEMPLATES_DIR / f"{template_name}.html"
    if tpl_path.exists():
        return tpl_path
    # 尝试作为绝对/相对路径
    candidate = Path(template_name)
    if candidate.exists():
        return candidate
    return None


def _render_template(template_path: Path, params: dict, cwd: str = None) -> Path:
    """将参数替换到 HTML 模板中，写入临时文件"""
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    work_dir.mkdir(parents=True, exist_ok=True)
    output = work_dir / f"_rendered_{template_path.stem}.html"

    html = template_path.read_text(encoding="utf-8")
    for key, value in params.items():
        html = html.replace(f"{{{{{key}}}}}", str(value))
    output.write_text(html, encoding="utf-8")
    return output


# ═══════════════════════════════════════════════════
# video_scene - 场景录制
# ═══════════════════════════════════════════════════

class VideoSceneTool(BaseTool):
    name = "video_scene"
    description = (
        "录制单个视频场景。支持两种模式：\n"
        "1. 模板模式：指定 template 和 params，使用预置动画模板录制\n"
        "2. 自定义模式：指定 html_path，录制 LLM 通过 sandbox 编写的自定义 HTML 动画\n"
        "HTML 页面需暴露 window.CURRENT_FRAME 和 window.updateAnimation() 供帧同步。"
    )
    parameters = [
        ToolParameter("output_path", "string", "输出 mp4 文件路径（相对路径会自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名称，用于创建独立输出文件夹，如 vibe_coding。所有同一视频的产物放一起", required=False),
        ToolParameter("template", "string", "模板名 (particle_brand / data_counter)，与 html_path 二选一", required=False),
        ToolParameter("html_path", "string", "自定义 HTML 文件路径，与 template 二选一", required=False),
        ToolParameter("params", "object", "模板参数 JSON 对象（仅 template 模式）", required=False),
        ToolParameter("duration", "integer", "录制时长（秒）", required=False, default=10),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
    ]

    def execute(self, output_path: str, project: str = None, template: str = None, html_path: str = None,
                params: dict = None, duration: int = 10, fps: int = 30,
                width: int = 1920, height: int = 1080, **kwargs) -> ToolResult:
        # 参数校验
        if template and html_path:
            return ToolResult.fail("template 和 html_path 不能同时指定，请二选一")
        if not template and not html_path:
            return ToolResult.fail("必须指定 template 或 html_path 之一")

        from .scripts.recorder import record_sync

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 模式1: 模板
        if template:
            tpl_path = _resolve_template_path(template)
            if tpl_path is None:
                available = [f.stem for f in TEMPLATES_DIR.glob("*.html")]
                return ToolResult.fail(
                    f"模板 '{template}' 不存在。可用模板: {', '.join(available)}"
                )

            # 合并默认参数和用户参数
            merged = dict(DEFAULT_PARAMS.get(template, {}))
            if params:
                merged.update(params)
            merged["WIDTH"] = width
            merged["HEIGHT"] = height
            merged["DURATION"] = duration
            merged["FPS"] = fps

            try:
                rendered = _render_template(tpl_path, merged, self.cwd)
            except Exception as e:
                return ToolResult.fail(f"模板渲染失败: {e}")

            html_file = str(rendered)

        # 模式2: 自定义 HTML
        else:
            p = Path(self._resolve_path(html_path))
            if not p.exists():
                return ToolResult.fail(f"HTML 文件不存在: {html_path}")
            html_file = str(p)

        try:
            self._emit_progress(f"正在录制场景 ({duration}s, {width}x{height})...")
            result_path = record_sync(html_file, str(out), duration, fps, width, height)
        except ImportError as e:
            return ToolResult.fail(
                f"缺少 Python 依赖，请用户在终端执行:\n"
                f"  pip install playwright\n"
                f"  playwright install chromium\n"
                f"错误详情: {e}"
            )
        except Exception as e:
            return ToolResult.fail(f"录制失败: {e}")

        return ToolResult.ok(
            f"场景录制完成: {out.name}",
            output_path=str(out.absolute()),
            duration=duration,
            resolution=f"{width}x{height}",
        )


# ═══════════════════════════════════════════════════
# video_tts - 语音合成
# ═══════════════════════════════════════════════════

class VideoTTSTool(BaseTool):
    name = "video_tts"
    description = (
        "将文本合成为语音文件 (mp3)。支持多种中文音色。"
        "适用于为视频生成旁白/配音。"
    )
    parameters = [
        ToolParameter("text", "string", "要合成的文本内容"),
        ToolParameter("output_path", "string", "输出 mp3 文件路径（相对路径会自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名称，与 video_scene 保持一致，所有产物集中管理", required=False),
        ToolParameter("voice", "string", "音色: xiaoxiao/xiaoyi(女声) / yunxi/yunjian(男声)", required=False, default="yunxi"),
    ]

    def execute(self, text: str, output_path: str, project: str = None, voice: str = "yunxi", **kwargs) -> ToolResult:
        from .scripts.tts import generate

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        self._emit_progress(f"正在合成语音 ({len(text)} 字, 音色: {voice})...")
        try:
            result = generate(text, str(out), voice)
        except ImportError:
            return ToolResult.fail(
                "缺少 Python 依赖，请用户在终端执行:\n"
                "  pip install edge-tts"
            )
        except Exception as e:
            return ToolResult.fail(f"语音合成失败: {e}")

        return ToolResult.ok(
            f"语音合成完成: {out.name}",
            output_path=str(out.absolute()),
            text_length=len(text),
            voice=voice,
        )


# ═══════════════════════════════════════════════════
# video_compose - 最终合成
# ═══════════════════════════════════════════════════

class VideoComposeTool(BaseTool):
    name = "video_compose"
    description = (
        "将多个视频场景拼接为最终视频，叠加旁白音频、背景音乐和字幕。\n"
        "scene_videos 和 scene_audios 按索引一一对应（audio 可为空字符串表示无旁白）。\n"
        "subtitles 为 [(文本, 起始秒, 结束秒), ...] 列表。"
    )
    parameters = [
        ToolParameter("output_path", "string", "最终输出 mp4 路径（相对路径会自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名称，与 video_scene/video_tts 保持一致", required=False),
        ToolParameter("scene_videos", "array", "场景视频文件路径列表"),
        ToolParameter("scene_audios", "array", "场景旁白音频路径列表（与scene_videos一一对应，可含空字符串）", required=False),
        ToolParameter("subtitles", "array", "字幕列表 [[text, start_sec, end_sec], ...]", required=False),
        ToolParameter("bgm_enabled", "boolean", "是否生成背景音乐", required=False, default=True),
        ToolParameter("bgm_volume", "number", "BGM 音量 (0-1)", required=False, default=0.18),
        ToolParameter("width", "integer", "视频宽度", required=False, default=1920),
        ToolParameter("height", "integer", "视频高度", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
    ]

    def execute(self, output_path: str, scene_videos: list,
                project: str = None, scene_audios: list = None, subtitles: list = None,
                bgm_enabled: bool = True, bgm_volume: float = 0.18,
                width: int = 1920, height: int = 1080,
                fps: int = 30, **kwargs) -> ToolResult:
        from .scripts.composer import compose
        from .scripts.bgm import generate as generate_bgm

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        if not scene_videos:
            return ToolResult.fail("scene_videos 不能为空")

        # 处理 scene_audios: 空字符串 → None
        audios = []
        if scene_audios:
            for a in scene_audios:
                if a and str(a).strip():
                    audios.append(str(a))
                else:
                    audios.append(None)
        else:
            audios = [None] * len(scene_videos)

        if len(audios) != len(scene_videos):
            return ToolResult.fail(
                f"scene_audios 长度 ({len(audios)}) 与 scene_videos ({len(scene_videos)}) 不匹配"
            )

        # 字幕格式处理
        sub_list = None
        if subtitles:
            sub_list = []
            for s in subtitles:
                if isinstance(s, (list, tuple)) and len(s) >= 3:
                    sub_list.append((str(s[0]), float(s[1]), float(s[2])))

        # BGM
        bgm_path = None
        if bgm_enabled:
            self._emit_progress("正在生成背景音乐...")
            try:
                from .scripts.composer import get_video_duration
                total_dur = 0
                for v in scene_videos:
                    try:
                        total_dur += get_video_duration(str(v))
                    except Exception:
                        pass
                if total_dur == 0:
                    total_dur = 30
                work_dir = Path(self.cwd) / "video_work"
                if project:
                    work_dir = work_dir / project
                work_dir = work_dir / "output"
                work_dir.mkdir(parents=True, exist_ok=True)
                bgm_path = str(work_dir / "_bgm.wav")
                generate_bgm(total_dur + 2, bgm_path)
            except Exception as e:
                # BGM 生成失败不阻塞
                bgm_path = None

        try:
            self._emit_progress(f"正在合成最终视频 ({len(scene_videos)} 个场景)...")
            result = compose(
                scene_videos=[str(v) for v in scene_videos],
                scene_audios=audios,
                output_path=str(out),
                subtitles=sub_list,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                width=width,
                height=height,
                fps=fps,
            )
        except ImportError as e:
            return ToolResult.fail(
                "缺少 Python 依赖，请用户在终端执行:\n"
                "  pip install moviepy numpy\n"
                f"错误详情: {e}"
            )
        except Exception as e:
            return ToolResult.fail(f"合成失败: {e}")

        size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0

        return ToolResult.ok(
            f"视频合成完成: {out.name}",
            output_path=str(out.absolute()),
            scene_count=len(scene_videos),
            size_mb=round(size_mb, 1),
            bgm_enabled=bgm_enabled and bgm_path is not None,
        )


# ─── 导出 ───

__all__ = ["VideoSceneTool", "VideoTTSTool", "VideoComposeTool"]
