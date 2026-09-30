"""
视频合成 - 优先 ffmpeg（快、内存占用小），moviepy 仅作时长探测兜底
"""
import os
import subprocess
import shutil
import tempfile
from pathlib import Path


def _find_ffmpeg() -> str:
    """定位 ffmpeg 可执行文件。"""
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = shutil.which(name)
        if p:
            return p
    return "ffmpeg"


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


def _probe_duration(path: str) -> float:
    """用 ffprobe 获取媒体时长（秒）。"""
    ffprobe = _find_ffmpeg().replace("ffmpeg", "ffprobe")
    r = subprocess.run(
        [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    return float(r.stdout.strip())


def _escape_subtitle_path(path: str) -> str:
    """ffmpeg subtitles 滤镜的路径转义（Windows 盘符冒号要转）。"""
    return path.replace("\\", "/").replace(":", "\\:")


def _write_srt(subtitles: list, path: str):
    """把 [(text, start, end), ...] 写成 SRT 字幕文件。"""
    def _fmt(sec: float) -> str:
        h = int(sec // 3600); sec -= h * 3600
        m = int(sec // 60);   sec -= m * 60
        s = int(sec);         ms = int(round((sec - s) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, (text, start, end) in enumerate(subtitles, 1):
        lines.append(f"{i}\n{_fmt(start)} --> {_fmt(end)}\n{text}\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def compose_tracks(
    scene_videos: list,
    scene_audios: list,
    video_out: str,
    audio_out: str,
) -> str:
    """交付双轨（供用户自行后期）：画面轨 mp4（无字幕、无混音）+ 旁白轨 mp3。

    画面轨 = 各段按序拼接并丢弃原音轨（保证纯净无声）；
    旁白轨 = 各段旁白按序拼接；
    若旁白总长超过画面总长，画面最后一帧补长到与旁白等长（不截断旁白）。
    """
    os.makedirs(os.path.dirname(video_out) or ".", exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="tracks_"))
    tmp_prefix = tmp_dir / "t"
    ffmpeg = _find_ffmpeg()

    # ── 1. 拼接画面（concat copy，保留编码）──
    vlist = f"{tmp_prefix}_videos.txt"
    with open(vlist, "w", encoding="utf-8") as f:
        for v in scene_videos:
            f.write(f"file '{os.path.abspath(v)}'\n")
    raw_video = f"{tmp_prefix}_raw.mp4"
    r = subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", vlist, "-c", "copy", raw_video],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"画面拼接失败: {r.stderr[-500:]}")
    vdur = _probe_duration(raw_video)

    # ── 2. 拼接旁白（concat copy）──
    valid_audios = [a for a in scene_audios if a and os.path.exists(a)]
    adur = 0.0
    if valid_audios:
        alist = f"{tmp_prefix}_audios.txt"
        with open(alist, "w", encoding="utf-8") as f:
            for a in valid_audios:
                f.write(f"file '{os.path.abspath(a)}'\n")
        r = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", alist, "-c", "copy", audio_out],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"旁白拼接失败: {r.stderr[-500:]}")
        adur = _probe_duration(audio_out)

    # ── 3. 画面轨处理：丢弃音轨 + 必要时补长到旁白总长 ──
    if adur > vdur + 0.3:
        # 补长最后一帧（必须重编码）
        padded = f"{tmp_prefix}_padded.mp4"
        r = subprocess.run(
            [ffmpeg, "-y", "-i", raw_video,
             "-vf", f"tpad=stop_mode=clone:stop={adur - vdur:.2f}",
             "-an", "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", padded],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise RuntimeError(f"画面补长失败: {r.stderr[-500:]}")
        src = padded
    else:
        src = raw_video

    # 丢弃音轨输出最终画面轨（若无需重编码则 copy）
    r = subprocess.run(
        [ffmpeg, "-y", "-i", src, "-map", "0:v:0", "-an",
         "-c:v", "copy", video_out],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        # copy 失败（编码不兼容）则重编码一次兜底
        r = subprocess.run(
            [ffmpeg, "-y", "-i", src, "-an",
             "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", video_out],
            capture_output=True, text=True, timeout=300,
        )
    if r.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"画面轨输出失败: {r.stderr[-500:]}")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return video_out


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
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    work_dir = Path(output_path).parent
    # 临时文件放系统 TEMP，避免沙箱/权限对工作目录的限制
    tmp_dir = Path(tempfile.mkdtemp(prefix="compose_"))
    tmp_prefix = tmp_dir / Path(output_path).stem

    ffmpeg = _find_ffmpeg()

    # ── 1. 拼接视频（concat demuxer，直接复用编码，秒级完成）──
    video_list = f"{tmp_prefix}_videos.txt"
    with open(video_list, "w", encoding="utf-8") as f:
        for v in scene_videos:
            f.write(f"file '{os.path.abspath(v)}'\n")

    video_only = f"{tmp_prefix}_video.mp4"
    r = subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", video_list,
         "-c", "copy", video_only],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"视频拼接失败: {r.stderr[-500:]}")

    # 视频实际总时长（拼接后以 ffprobe 为准）
    total_dur = _probe_duration(video_only)

    # ── 2. 拼接音频（音频优先，超出视频则拉长画面）──
    valid_audios = [a for a in scene_audios if a and os.path.exists(a)]
    vo_total = 0.0
    if valid_audios:
        audio_list = f"{tmp_prefix}_audios.txt"
        with open(audio_list, "w", encoding="utf-8") as f:
            for a in valid_audios:
                f.write(f"file '{os.path.abspath(a)}'\n")
        vo_merged = f"{tmp_prefix}_vo.mp3"
        r = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", audio_list,
             "-c", "copy", vo_merged],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"音频拼接失败: {r.stderr[-500:]}")
        vo_total = _probe_duration(vo_merged)
    else:
        vo_merged = None

    # 旁白超出视频总长时，用视频最后一帧补长
    final_dur = max(total_dur, vo_total)
    if vo_total > total_dur:
        pad = f"{tmp_prefix}_video_padded.mp4"
        r = subprocess.run(
            [ffmpeg, "-y", "-i", video_only,
             "-vf", f"tpad=stop_mode=clone:stop={vo_total - total_dur:.2f}",
             "-c:v", "libx264", "-preset", "fast", "-an", pad],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            raise RuntimeError(f"视频补长失败: {r.stderr[-500:]}")
        video_only = pad
        total_dur = vo_total

    # ── 3. 合成视频 + 旁白（+BGM）──
    merged = f"{tmp_prefix}_av.mp4"
    if vo_merged and bgm_path and os.path.exists(bgm_path):
        # 视频 + 旁白 + BGM 三路混音
        r = subprocess.run(
            [ffmpeg, "-y",
             "-i", video_only, "-i", vo_merged, "-i", bgm_path,
             "-filter_complex",
             f"[2:a]volume={bgm_volume}[bgm];[1:a][bgm]amix=inputs=2:duration=first[aout]",
             "-map", "0:v", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-t", f"{final_dur:.2f}",
             merged],
            capture_output=True, text=True, timeout=180,
        )
    elif vo_merged:
        r = subprocess.run(
            [ffmpeg, "-y",
             "-i", video_only, "-i", vo_merged,
             "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-t", f"{final_dur:.2f}",
             merged],
            capture_output=True, text=True, timeout=180,
        )
    elif bgm_path and os.path.exists(bgm_path):
        r = subprocess.run(
            [ffmpeg, "-y",
             "-i", video_only, "-i", bgm_path,
             "-filter_complex", f"[1:a]volume={bgm_volume}[aout]",
             "-map", "0:v", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-t", f"{final_dur:.2f}",
             merged],
            capture_output=True, text=True, timeout=180,
        )
    else:
        shutil.copy2(video_only, merged)
        r = type("R", (), {"returncode": 0})()
    if r.returncode != 0:
        raise RuntimeError(f"音视频合成失败: {r.stderr[-500:]}")

    # ── 4. 烧录字幕（drawtext 或 subtitles 滤镜，硬字幕）──
    if subtitles:
        srt_path = f"{tmp_prefix}.srt"
        _write_srt(subtitles, srt_path)
        font_name = Path(_find_font()).stem
        style = (
            f"FontName={font_name},FontSize=22,"
            "PrimaryColour=&HFFFFFF,OutlineColour=&H80000000,"
            "BackColour=&H80000000,BorderStyle=4,Outline=1,Shadow=0,"
            "Alignment=2,MarginV=60"
        )
        r = subprocess.run(
            [ffmpeg, "-y", "-i", merged,
             "-vf", f"subtitles='{_escape_subtitle_path(srt_path)}':force_style='{style}'",
             "-c:v", "libx264", "-preset", "fast", "-c:a", "copy",
             "-t", f"{final_dur:.2f}",
             output_path],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError(f"字幕烧录失败: {r.stderr[-500:]}")
    else:
        shutil.move(merged, output_path)

    # ── 5. 清理临时目录 ──
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path


def get_video_duration(video_path: str) -> float:
    try:
        return _probe_duration(video_path)
    except Exception:
        from moviepy import VideoFileClip
        clip = VideoFileClip(video_path)
        dur = clip.duration
        clip.close()
        return dur
