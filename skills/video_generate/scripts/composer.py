"""
视频合成 - MoviePy 拼接、配音、字幕
"""
import os
from pathlib import Path


def _find_font() -> str:
    """查找可用的中文字体"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
        "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑 Bold
        "C:/Windows/Fonts/simhei.ttf",     # 黑体
        "C:/Windows/Fonts/simsun.ttc",     # 宋体
        "C:/Windows/Fonts/Noto Sans SC (TrueType).otf",
    ]
    for f in candidates:
        if os.path.exists(f):
            return f
    return "Microsoft-YaHei"  # 最后的 fallback


def compose(
    scene_videos: list,
    scene_audios: list,
    output_path: str,
    subtitles: list = None,
    bgm_path: str = None,
    bgm_volume: float = 0.18,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> str:
    """
    scene_videos: [video_path, ...]  每个场景的视频文件
    scene_audios: [audio_path | None, ...]  每个场景的旁白音频（可为None）
    subtitles: [(text, start_sec, end_sec), ...] or None
    bgm_path: 背景音乐路径 or None
    """
    from moviepy import (
        VideoFileClip, AudioFileClip, CompositeAudioClip,
        TextClip, CompositeVideoClip, concatenate_videoclips,
    )
    from moviepy.audio.fx.MultiplyVolume import MultiplyVolume

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 加载视频片段
    clips = []
    for path in scene_videos:
        if not os.path.exists(path):
            raise FileNotFoundError(f"视频文件不存在: {path}")
        clips.append(VideoFileClip(path))

    # 拼接视频
    if len(clips) == 1:
        video = clips[0]
    else:
        video = concatenate_videoclips(clips, method="compose")
    total_dur = video.duration

    # 构建音频
    audio_clips = []

    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).with_effects([
            MultiplyVolume(bgm_volume),
        ]).subclipped(0, total_dur)
        audio_clips.append(bgm)

    # 添加旁白（按场景时间对齐）
    time_offset = 0.0
    for i, audio_path in enumerate(scene_audios):
        if i < len(clips):
            clip_dur = clips[i].duration if hasattr(clips[i], "duration") else clips[i].duration
        else:
            clip_dur = 0

        if audio_path and os.path.exists(audio_path):
            vo = AudioFileClip(audio_path)
            if time_offset + vo.duration > total_dur:
                vo = vo.subclipped(0, total_dur - time_offset)
            vo = vo.with_start(time_offset)
            audio_clips.append(vo)

        time_offset += clip_dur

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
        video = video.with_audio(final_audio)

    # 字幕叠加
    if subtitles:
        subtitle_clips = []
        for text, start_t, end_t in subtitles:
            dur = end_t - start_t
            if dur <= 0:
                continue
            sub = TextClip(
                text=text,
                font_size=36,
                color="white",
                font=_find_font(),
                stroke_color="black",
                stroke_width=2,
                size=(width - 200, None),
                method="caption",
            ).with_position(("center", height - 120)).with_start(start_t).with_duration(dur)
            subtitle_clips.append(sub)

        if subtitle_clips:
            video = CompositeVideoClip([video] + subtitle_clips, size=(width, height))

    # 渲染
    video.write_videofile(
        output_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        logger=None,
    )

    for c in clips:
        c.close()
    video.close()

    return output_path


def get_video_duration(video_path: str) -> float:
    from moviepy import VideoFileClip
    clip = VideoFileClip(video_path)
    dur = clip.duration
    clip.close()
    return dur
