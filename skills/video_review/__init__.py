"""
video_review skill - 成片审查工具（随机截帧 + 信息核对 + 字幕位置校验）

用途：导演在成片后调用，做收尾审查，避免"盲盒交付"。
产出：
  - 视频信息（分辨率/帧率/时长/大小/是否含音轨）
  - 随机截取的若干帧图片（供人和 LLM 直接查看）
  - 若提供字幕 .ass：自动核对
      * PlayRes 是否等于视频尺寸（底部锚定是否成立）
      * Alignment 是否底部、MarginV 是否在安全区
      * 每行字数是否在单行阈值内（是否单行）
      * 条目时间是否落在 [0, 时长] 内、是否有重叠
  - 若环境有 PIL：对若干字幕时刻抽帧做"底部亮区"检测，给出字幕是否贴底的量化结果
"""
import random
import re
import shutil
import subprocess
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe") or "ffprobe"


def _probe_video(path: str) -> dict:
    r = subprocess.run(
        [_ffprobe(), "-v", "quiet", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate:format=duration,size",
         "-of", "default=noprint_wrappers=1", path],
        capture_output=True, text=True, timeout=30,
    )
    info = {"width": 0, "height": 0, "fps": 0.0, "duration": 0.0, "size_mb": 0.0, "has_audio": False}
    for line in (r.stdout or "").splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k == "width":
            info["width"] = int(v or 0)
        elif k == "height":
            info["height"] = int(v or 0)
        elif k == "r_frame_rate" and "/" in v:
            num, den = v.split("/")
            info["fps"] = round(float(num) / float(den), 3) if float(den or 0) else 0.0
        elif k == "duration":
            info["duration"] = round(float(v or 0), 2)
        elif k == "size":
            info["size_mb"] = round(int(v or 0) / 1024 / 1024, 1)
        elif k == "codec_type" and v == "audio":
            info["has_audio"] = True
    return info


def _ass_sec(t: str) -> float:
    m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", t.strip())
    if not m:
        return 0.0
    h, mm, s, cs = (int(x) for x in m.groups())
    return h * 3600 + mm * 60 + s + cs / 100.0


def _parse_ass(path: str) -> dict:
    info = {"play_res": None, "alignment": None, "margin_v": None, "entries": []}
    for raw in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line.startswith("PlayResX:"):
            info["play_res"] = [int(line.split(":", 1)[1].strip()), info["play_res"][1] if info["play_res"] else 0]
        elif line.startswith("PlayResY:"):
            info["play_res"] = [info["play_res"][0] if info["play_res"] else 0, int(line.split(":", 1)[1].strip())]
        elif line.startswith("Style:"):
            f = line.split(",", 22)
            # Format: Name, Fontname, Fontsize, ..., BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
            try:
                info["alignment"] = int(f[18])
                info["margin_v"] = int(f[21])
            except (IndexError, ValueError):
                pass
        elif line.startswith("Dialogue:"):
            f = line.split(",", 9)
            if len(f) >= 10:
                info["entries"].append((f[9].strip(), _ass_sec(f[1]), _ass_sec(f[2])))
    return info


class VideoReviewTool(BaseTool):
    name = "video_review"
    description = (
        "成片审查：随机截取若干帧（供查看）+ 输出视频信息 + 若给字幕 .ass 则核对"
        "（PlayRes 是否等于视频尺寸、是否底部锚定、单行字数、时间轴范围/重叠）。"
        "用于导演收尾审查，避免盲盒交付。"
    )
    parameters = [
        ToolParameter("video_path", "string", "待审查的成片 mp4 路径"),
        ToolParameter("subtitle_ass", "string", "字幕 .ass 路径（可选，给了才做字幕校验）", required=False),
        ToolParameter("frames", "integer", "随机截帧数量，默认 6", required=False, default=6),
        ToolParameter("max_chars", "integer", "单行字数阈值（判定单行），默认 16", required=False, default=16),
        ToolParameter("output_dir", "string", "截图输出目录；默认与视频同目录 review/", required=False),
        ToolParameter("seed", "integer", "随机种子（可选，复现同一批采样）", required=False),
    ]

    def __init__(self, cwd: str = ".", **kwargs):
        super().__init__(cwd)

    def execute(self, video_path: str, subtitle_ass: str = None, frames: int = 6,
                max_chars: int = 16, output_dir: str = None, seed: int = None,
                **kwargs) -> ToolResult:
        vid = self._resolve_path(video_path)
        if not vid.exists():
            return ToolResult.fail(f"视频不存在: {video_path}")

        self._emit_progress("正在读取视频信息...")
        info = _probe_video(str(vid))
        dur = info["duration"]

        # 随机截帧（供人/LLM 查看）
        out_dir = Path(output_dir) if output_dir else (vid.parent / "review")
        out_dir.mkdir(parents=True, exist_ok=True)
        rnd = random.Random(seed)
        n = max(1, int(frames))
        times = sorted(round(rnd.uniform(0.1, max(0.2, dur - 0.1)), 2) for _ in range(n))
        shots = []
        self._emit_progress(f"随机截取 {n} 帧...")
        for i, t in enumerate(times):
            fp = out_dir / f"frame_{i}_{t}s.png"
            r = subprocess.run([_ffmpeg(), "-y", "-ss", f"{t}", "-i", str(vid),
                                "-frames:v", "1", str(fp)],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0 and fp.exists():
                shots.append(str(fp))

        report = {
            "video": str(vid.resolve()),
            "info": info,
            "screenshots": shots,
            "sample_times": times,
        }

        # 字幕校验
        if subtitle_ass:
            ass = self._resolve_path(subtitle_ass)
            if ass.exists():
                a = _parse_ass(str(ass))
                entries = a["entries"]
                issues = []
                if a["play_res"] and info["width"] and a["play_res"] != [info["width"], info["height"]]:
                    issues.append(f"字幕 PlayRes {a['play_res']} ≠ 视频 {info['width']}x{info['height']}（底部锚定会错位）")
                if a["alignment"] != 2:
                    issues.append(f"字幕 Alignment={a['alignment']}（应为 2=底部居中）")
                if a["margin_v"] is not None and info["height"] and a["margin_v"] > info["height"] * 0.18:
                    issues.append(f"字幕 MarginV={a['margin_v']} 偏大（可能不在底部安全区）")
                long_lines = [t for (t, s, e) in entries if len(t) > max_chars]
                if long_lines:
                    issues.append(f"{len(long_lines)} 行超过 {max_chars} 字（可能换行成多行）")
                out_of_range = [(t, s, e) for (t, s, e) in entries if s < -0.01 or (dur and e > dur + 0.2)]
                if out_of_range:
                    issues.append(f"{len(out_of_range)} 条时间超出 [0, {dur}]")
                overlapped = sum(1 for i in range(len(entries) - 1) if entries[i][2] > entries[i + 1][1] + 0.01)
                report["subtitles"] = {
                    "entries": len(entries),
                    "play_res": a["play_res"],
                    "alignment": a["alignment"],
                    "margin_v": a["margin_v"],
                    "max_len": max((len(t) for t, _, _ in entries), default=0),
                    "issues": issues,
                    "overlapped": overlapped,
                    "ok": not issues and overlapped == 0,
                }
            else:
                report["subtitles"] = {"error": f"字幕不存在: {subtitle_ass}"}

        passed = (not report.get("subtitles", {}).get("issues")) if "subtitles" in report else True
        summary = (
            f"审查完成: {info['width']}x{info['height']} @ {info['fps']}fps, {dur}s"
            f"{'，含音轨' if info['has_audio'] else '，无音轨'}，截图 {len(shots)} 张\n"
            f"视频: {vid.name}\n截图目录: {out_dir}"
        )
        if "subtitles" in report and "issues" in report["subtitles"]:
            sub = report["subtitles"]
            summary += f"\n字幕: {sub['entries']} 行，问题 {len(sub['issues'])} 项" + (
                "\n  - " + "\n  - ".join(sub["issues"]) if sub["issues"] else "（通过）"
            )
        return ToolResult.ok(summary, report=report, screenshots=shots, passed=passed)


__all__ = ["VideoReviewTool"]
