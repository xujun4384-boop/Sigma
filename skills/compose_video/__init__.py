"""
compose_video skill - 合成部门（烧录/混音/拼接）

把多段视频 + 旁白 + 字幕合成为最终 mp4：
  - 规格归一化：各段先 scale+补边到目标画布、统一 fps/像素格式/SAR，再拼接
    （因此可混合不同引擎产物，如影视级 768P 与 HTML 1920x1080）。
  - 字幕：直接烧「字幕组」产出的 .ass（自带底部单行样式），无需再传样式。
  - 背景音乐：可选（bgm）。音乐偏短时用 acrossfade 交叉淡化无缝循环铺满，再与旁白混音（旁白优先）。
本入口只做合成这一步，是「烧录合成部门」的对外入口。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ComposeVideoTool(BaseTool):
    name = "compose_video"
    description = (
        "合成部门：把多段视频片段 + 旁白 + 字幕合成为最终 mp4。"
        "各段会先统一到目标画布规格（分辨率/帧率/像素格式）再拼接，可混合不同引擎产物；"
        "字幕直接烧字幕组产出的 .ass（底部单行）。"
        "可用 bgm 传入背景音乐：会自动循环铺满全片并与旁白混音（旁白优先）。"
        "可用 sfx 传入音效事件（带时间点的一次性音效），会铺成独立音效轨并与旁白/BGM 混音。"
        "支持段间转场（transitions）：可传入 ffmpeg xfade 的 transition 名，"
        "常用如 fade/dissolve/pixelize/radial/hblur/distance/circleopen/circleclose/"
        "wipeleft…wipebr/slideleft…slidedown/smooth*/cover*/reveal*/diag*/hlslice/hrslice/vuslice/vdslice/"
        "squeezeh/squeezev/zoomin/fadeblack/fadewhite/fadegrays/fadefast/fadeslow/"
        "vertopen/vertclose/horzopen/horzclose/hlwind/hrwind/vuwind/vdwind。"
        "注意：转场会让相邻两段重叠、成片时长变短，字幕/旁白时间轴需按同样重叠量计算。"
    )
    parameters = [
        ToolParameter("output_path", "string", "最终输出 mp4 路径"),
        ToolParameter("scene_videos", "array", "各段视频 mp4 路径（按播放顺序）"),
        ToolParameter("scene_audios", "array", "各段旁白 mp3 路径（与 scene_videos 一一对应，可空串=无旁白）", required=False),
        ToolParameter("subtitle_ass", "string", "字幕组产出的 .ass 路径；给了就烧录", required=False),
        ToolParameter("bgm", "string", "背景音乐音频路径（可选）。会铺满全片（音乐偏短则交叉淡化无缝循环），按 bgm_volume 压低后与旁白混音，旁白优先。", required=False),
        ToolParameter("bgm_volume", "integer", "背景音乐音量百分比 0-100，默认 25（相对旁白压低）", required=False, default=25),
        ToolParameter("sfx", "array",
                      "音效事件数组：[{path, at, level, fade_in}]。at 是成片时间轴秒数；"
                      "level 是音量百分比 0-100（默认 60）；fade_in 是淡入秒数（可选）。"
                      "各事件会铺成独立音效轨，与旁白/BGM 混音。", required=False),
        ToolParameter("transitions", "object",
                      "段间转场。可传单个字符串（应用到所有接缝）、单个对象 {type,duration}、"
                      "或数组（逐接缝，元素可为字符串/对象/null=硬切）。默认不转场(硬切)。",
                      required=False),
        ToolParameter("width", "integer", "输出宽度，默认 1920", required=False, default=1920),
        ToolParameter("height", "integer", "输出高度，默认 1080", required=False, default=1080),
        ToolParameter("fps", "integer", "输出帧率，默认 30", required=False, default=30),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, output_path: str, scene_videos: list, scene_audios: list = None,
                subtitle_ass: str = None, transitions=None, width: int = 1920,
                height: int = 1080, fps: int = 30, bgm: str = None,
                bgm_volume: int = 25, sfx=None, **kwargs) -> ToolResult:
        from .scripts.renderer import compose

        if not scene_videos or not isinstance(scene_videos, list):
            return ToolResult.fail("scene_videos 不能为空")

        out = self._resolve_path(output_path)
        ass = self._resolve_path(subtitle_ass) if subtitle_ass else None
        bgm_path = self._resolve_path(bgm) if (bgm and str(bgm).strip()) else None
        try:
            volume = max(0.0, min(1.0, float(bgm_volume) / 100.0))
        except (TypeError, ValueError):
            volume = 0.25

        # 音效事件：路径解析 + 音量归一化；缺失文件跳过（不因一个音效拖垮整片）
        sfx_events = []
        for ev in (sfx or []):
            if not isinstance(ev, dict):
                continue
            raw_path = ev.get("path") or ev.get("file")
            if not raw_path:
                continue
            p = self._resolve_path(str(raw_path))
            if not p.exists():
                self._emit_progress(f"音效文件不存在，跳过：{raw_path}")
                continue
            try:
                at = max(0.0, float(ev.get("at") or 0.0))
            except (TypeError, ValueError):
                at = 0.0
            try:
                level = max(0.0, min(1.0, float(ev.get("level", 60)) / 100.0))
            except (TypeError, ValueError):
                level = 0.6
            if level <= 0:
                continue
            item = {"path": str(p), "at": at, "level": level}
            if ev.get("fade_in") is not None:
                item["fade_in"] = ev.get("fade_in")
            sfx_events.append(item)

        self._emit_progress(
            f"正在合成（{len(scene_videos)} 段：归一化 → 拼接/转场 → 旁白"
            f"{' → 背景音乐' if bgm_path else ''}"
            f"{' → 音效' + str(len(sfx_events)) + '个' if sfx_events else ''} → 字幕）..."
        )
        try:
            res = compose(
                scene_videos=[str(v) for v in scene_videos],
                scene_audios=[str(a) if a else "" for a in (scene_audios or [])],
                output_path=str(out),
                subtitle_ass=str(ass) if ass else None,
                transitions=transitions,
                width=width, height=height, fps=fps,
                bgm=str(bgm_path) if bgm_path else None,
                bgm_volume=volume,
                sfx=sfx_events or None,
                progress=self._emit_progress,
            )
        except Exception as e:
            return ToolResult.fail(f"合成失败: {e}")

        tr = res.get("transitions_used", 0)
        looped = res.get("bgm_looped", False)
        sfx_n = res.get("sfx_count", 0)
        return ToolResult.ok(
            f"合成完成: {Path(out).name}（{res['duration']}s"
            f"{'，已归一化' if res['video_norm'] else ''}"
            f"{'，含旁白' if res.get('has_voice') else ''}"
            f"{'，含背景音乐' if res.get('has_bgm') else ''}"
            f"{'（无缝循环铺满）' if looped else ''}"
            f"{'，含音效 ' + str(sfx_n) + ' 个' if sfx_n else ''}"
            f"{'，已烧字幕' if res['subtitle_burned'] else ''}"
            f"{'，' + str(tr) + ' 处转场' if tr else ''}）",
            output_path=res["output_path"],
            duration=res["duration"],
            scene_count=len(scene_videos),
            video_norm=res["video_norm"],
            has_audio=res["has_audio"],
            has_voice=res.get("has_voice", False),
            has_bgm=res.get("has_bgm", False),
            bgm_looped=looped,
            has_sfx=res.get("has_sfx", False),
            sfx_count=sfx_n,
            subtitle_burned=res["subtitle_burned"],
            transitions_used=tr,
        )


__all__ = ["ComposeVideoTool"]
