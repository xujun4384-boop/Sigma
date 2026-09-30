"""
compose_video skill - 把多段视频片段合成为最终视频

组合路径的合成器：接收多段 scene_videos（由 video_shot 产出），
按索引叠加 scene_audios（可空），可选字幕与 BGM，统一合成最终 mp4。

复用 skills/video_generate/scripts/composer.py 的 compose（ffmpeg 拼接）。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class ComposeVideoTool(BaseTool):
    name = "compose_video"
    description = (
        "把多段视频片段合成为最终视频。把 video_shot 逐段产出的 mp4 传入 scene_videos，"
        "scene_audios 与之一一对应（可空串表示该段无旁白），subtitles 为字幕列表 "
        "[[text, 起始秒, 结束秒], ...]，可选加背景音乐。产出拼接后的完整 mp4。"
    )
    parameters = [
        ToolParameter("output_path", "string", "最终输出 mp4 路径（绝对路径）"),
        ToolParameter("scene_videos", "array", "各段视频 mp4 路径列表（video_shot 产物），按播放顺序"),
        ToolParameter("scene_audios", "array", "各段旁白 mp3 路径列表（与 scene_videos 一一对应，可空串）", required=False),
        ToolParameter("subtitles", "array", "字幕列表 [[text, start_sec, end_sec], ...]，可按各段 words 汇总", required=False),
        ToolParameter("bgm_enabled", "boolean", "是否生成背景音乐", required=False, default=False),
        ToolParameter("bgm_volume", "number", "BGM 音量 (0-1)", required=False, default=0.18),
        ToolParameter("width", "integer", "输出宽度", required=False, default=1920),
        ToolParameter("height", "integer", "输出高度", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率", required=False, default=30),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(
        self,
        output_path: str,
        scene_videos: list,
        scene_audios: list = None,
        subtitles: list = None,
        bgm_enabled: bool = False,
        bgm_volume: float = 0.18,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        **kwargs,
    ) -> ToolResult:
        from skills.video_generate.scripts.composer import _probe_duration, _write_srt, compose, get_video_duration

        if not scene_videos or not isinstance(scene_videos, list) or not scene_videos:
            return ToolResult.fail("scene_videos 不能为空")

        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # 归一化旁白：空串/缺失 -> None
        audios = []
        for i, v in enumerate(scene_videos):
            a = (scene_audios or [None] * len(scene_videos))[i] if scene_audios else None
            audios.append(str(a) if a and str(a).strip() else None)

        # 归一化字幕
        sub_list = None
        if subtitles:
            sub_list = [(str(s[0]), float(s[1]), float(s[2]))
                        for s in subtitles if isinstance(s, (list, tuple)) and len(s) >= 3]

        # 可选 BGM：按所有段视频总时长生成
        bgm_path = None
        if bgm_enabled:
            total = 0.0
            for v in scene_videos:
                try:
                    total += get_video_duration(str(v))
                except Exception:
                    pass
            from skills.video_generate.scripts.bgm import generate as generate_bgm
            bgm_path = str(out.parent / "_bgm.wav")
            try:
                generate_bgm(int(total) + 2, bgm_path)
            except Exception:
                bgm_path = None

        self._emit_progress(f"正在合成最终视频（{len(scene_videos)} 段）...")
        try:
            compose(
                scene_videos=[str(v) for v in scene_videos],
                scene_audios=audios,
                output_path=str(out),
                subtitles=sub_list,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                width=width, height=height, fps=fps,
            )
        except Exception as e:
            return ToolResult.fail(f"合成失败: {e}")

        # 全片 SRT 一并导出，供后期微调
        srt_path = out.parent / f"{out.stem}.srt"
        if sub_list:
            try:
                _write_srt(sub_list, str(srt_path))
            except Exception:
                srt_path = None
        else:
            srt_path = None

        total_dur = _probe_duration(str(out))
        size_mb = out.stat().st_size / 1024 / 1024 if out.exists() else 0

        return ToolResult.ok(
            f"组合视频合成完成: {out.name} ({round(size_mb, 1)} MB, 时长 {round(total_dur, 2)}s)",
            output_path=str(out.resolve()),
            duration=round(total_dur, 2),
            scene_count=len(scene_videos),
            subtitle_file=str(srt_path) if srt_path else "",
            size_mb=round(size_mb, 1),
        )


__all__ = ["ComposeVideoTool"]