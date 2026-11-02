# -*- coding: utf-8 -*-
"""footage_video 渲染：把用户自备的视频素材规整为成片画布中的一段。

约束（与「直接运用」对齐）：
  - 不做任何创作：不重绘、不调色、不改变内容与节奏；
  - 输入不限容器：mp4 / mov / mkv / webm / avi …（只要 ffmpeg 能解码），
    输出**统一为 mp4**（H.264 + yuv420p），因此非 mp4 素材会被自动转成 mp4；
  - 只做规格统一：等比缩放 + 补边（contain）或等比裁切（cover）、统一 fps / 像素格式 / SAR；
    目标画布由调用方给定（导演组默认 1920×1080）；
  - 时长默认取素材原长：不补帧、不拉伸；只有显式 target 才截取前 N 秒；
  - 原声默认保留：从素材单独抽出音频轨返回，供导演作为该段音频使用
    （合成部门会丢弃视频内嵌音轨，所以必须独立抽出）。
"""
import shutil
import subprocess
from pathlib import Path


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe") or "ffprobe"


def probe_duration(path) -> float:
    """探测媒体时长（秒）；失败返回 0。"""
    r = subprocess.run(
        [_ffprobe(), "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _stream_types(path) -> set:
    """返回文件里实际存在的流类型集合（video / audio …）。"""
    r = subprocess.run(
        [_ffprobe(), "-v", "quiet", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    return {s.strip() for s in (r.stdout or "").splitlines() if s.strip()}


def _run(cmd: list, timeout=None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 失败: {' '.join(str(c) for c in cmd[:6])}...\n{(r.stderr or '')[-800:]}"
        )


def _video_filter(W: int, H: int, fps: int, fit: str) -> str:
    """画布适配：contain=完整保留画面并补黑边；cover=等比放大后居中裁切铺满。"""
    if fit == "cover":
        scale_crop = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H}"
        )
    else:
        scale_crop = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    return f"{scale_crop},setsar=1,fps={fps},format=yuv420p"


def render_footage(src, dst, W: int, H: int, fps: int, fit: str = "contain",
                   target: float = 0.0, keep_audio: bool = True) -> dict:
    """把 src 规整为 dst（目标画布/W/H/fps）。

    target>0 时只取素材前 target 秒（素材更短则取整段）；
    keep_audio 且素材含音轨时，另存同目录的 `<dst>_src.wav` 并返回其路径。
    """
    src = str(src)
    # 输出容器固定 mp4：ffmpeg 按扩展名选封装，非 .mp4 目标会写坏/报错，这里直接改名。
    dst_path = Path(dst)
    if dst_path.suffix.lower() != ".mp4":
        dst_path = dst_path.with_suffix(".mp4")
    dst = str(dst_path)
    types = _stream_types(src)
    if "video" not in types:
        raise RuntimeError("素材里没有视频流（不是可用的视频文件）")

    src_dur = probe_duration(src)
    dur = src_dur
    if target and target > 0:
        dur = min(src_dur, float(target)) if src_dur > 0 else float(target)

    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y", "-i", src,
        "-map", "0:v:0", "-an",
        "-vf", _video_filter(W, H, fps, fit),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
    ]
    if dur > 0:
        cmd += ["-t", f"{dur:.3f}"]
    cmd.append(dst)
    _run(cmd, timeout=None)

    out_dur = probe_duration(dst) or dur
    audio_path = ""
    if keep_audio and "audio" in types:
        audio_dst = str(Path(dst).with_name(Path(dst).stem + "_src.wav"))
        acmd = [_ffmpeg(), "-y", "-i", src, "-map", "0:a:0", "-vn",
                "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le"]
        if out_dur > 0:
            acmd += ["-t", f"{out_dur:.3f}"]
        acmd.append(audio_dst)
        _run(acmd, timeout=None)
        audio_path = audio_dst

    return {
        "output_path": dst,
        "duration": round(float(out_dur), 3),
        "source_duration": round(float(src_dur), 3),
        "clipped": bool(target and src_dur > 0 and float(target) < src_dur),
        "width": int(W),
        "height": int(H),
        "fps": int(fps),
        "fit": fit,
        "has_source_audio": "audio" in types,
        "audio_path": audio_path,
        "converted_to_mp4": Path(src).suffix.lower() != ".mp4",
    }
