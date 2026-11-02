"""
narration skill - 旁白组（多段旁白批量配音 + 权威时间轴）

从 produce 流水线的「旁白生成」阶段解耦而来，独立成一个部门：
  - 输入多段旁白文案，逐段调用豆包 TTS 2.0 合成 mp3（内部引擎 doubao_tts，实现不变）。
  - 每段返回：mp3 路径、**权威时长**（ffprobe 实测 mp3 时长，比字级时间戳更准）、字级时间戳。
  - 汇总总时长，供「字幕组」按字级时间戳生成字幕、「导演」据此编排画面时长。

长旁白分块合成（字幕漂移修复）：
  - 豆包单次合成超长文本时，返回的字级时间戳会随「数字/英文被朗读展开」而逐步漂移
    （实测 50 秒段尾部偏差可达 8 秒），表现为段内字幕越来越早、段尾直接没有字幕。
  - 因此每段文案按句切成 <= MAX_CHUNK_CHARS 的小块，逐块合成、逐块以实测块长定位，
    再按真实时长顺序拼接成整条音轨。误差被限制在单块内，不再跨块累积。
  - 每块仍做一次块内线性重标定（以实测块长为锚），消掉块内残余偏差，并对异常块告警。

设计原则（与 produce 一致，不改变实现原理）：
  - 时长由旁白实际读速决定，是画面时长的权威依据（不要预先定死时长）。
  - 字级时间戳是字幕的唯一时间源 → 字幕天然与旁白对齐（"语速↔字幕"无需额外对齐代码）。
  - speech_rate / loudness_rate 是"调节旋钮"，统一作用于所有段。
"""
import shutil
import subprocess
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from skills.doubao_tts.voices import resolve_voice

# 单块最大字数：中文读速约 10~15 秒语音。块越短，TTS 字级时间戳的累计漂移越小。
MAX_CHUNK_CHARS = 45
# 块尾漂移超过该阈值（秒）才做块内线性重标定
DRIFT_TOLERANCE = 0.8
# 重标定允许的拉伸/压缩范围；超出范围视为异常块，只告警不硬拉
RESCALE_RANGE = (0.8, 1.4)

# 断句标点（按字符类别划分，通用规则、非关键词匹配）：
#   句末标点 = 强边界，必断；句内标点 = 弱边界，仅在单句超长时用于二次切分
_PUNCT_HARD = set("。！？；…!?;")
_PUNCT_SOFT = set("，、,：:")


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _probe_duration(path: str) -> float:
    """ffprobe 实测媒体时长（秒）；不可用时返回 0（由调用方回落字级时间戳）。"""
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if not exe:
        return 0.0
    try:
        r = subprocess.run(
            [exe, "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list:
    """把旁白文案切成句级小块。

    规则：①按句末标点切成句子；②单句超过 max_chars 时，在句内标点处二次切分；
    ③仍超长则按字数硬切；④相邻小块在不超 max_chars 的前提下合并，减少请求数。
    """
    text = (text or "").strip()
    if not text:
        return []

    sentences, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _PUNCT_HARD:
            sentences.append(buf)
            buf = ""
    if buf.strip():
        sentences.append(buf)

    pieces = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        # 超长句：优先在句内标点处断开（避免拆碎词/数字），找不到就近按字数硬切
        while len(s) > max_chars:
            cut = -1
            for idx in range(max_chars, 0, -1):
                if s[idx - 1] in _PUNCT_SOFT:
                    cut = idx
                    break
            if cut <= 0:
                cut = max_chars
            pieces.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            pieces.append(s)

    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur += p
    if cur:
        chunks.append(cur)
    return chunks


def _normalize_words(words: list, chunk_dur: float) -> tuple:
    """按块实测时长校正字级时间戳，返回 (校正后的 words, 校正前后的漂移秒数)。

    豆包对数字/英文等会被“朗读展开”的 token 时间戳偏短，导致整块时间轴比音频短。
    这里以实测块长为锚做一次线性重标定：块短，拉伸幅度小，不会破坏语速节奏。
    漂移超出 RESCALE_RANGE 时不做硬拉，只把漂移值返回给调用方告警。
    """
    clean = []
    for w in words or []:
        try:
            s = float(w.get("startTime", 0.0))
            e = float(w.get("endTime", 0.0))
        except (TypeError, ValueError):
            continue
        item = dict(w)
        item["startTime"], item["endTime"] = s, e
        clean.append(item)
    if not clean or chunk_dur <= 0:
        return clean, 0.0

    last_end = max(w["endTime"] for w in clean)
    drift = chunk_dur - last_end
    if abs(drift) <= DRIFT_TOLERANCE or last_end <= 0:
        return clean, drift

    factor = chunk_dur / last_end
    lo, hi = RESCALE_RANGE
    if not (lo <= factor <= hi):
        return clean, drift

    for w in clean:
        w["startTime"] = round(w["startTime"] * factor, 3)
        w["endTime"] = round(w["endTime"] * factor, 3)
    return clean, 0.0


def _concat_audio(parts: list, out_path: Path) -> None:
    """把分块音频按顺序拼成一条整轨。

    优先无损流拷贝（同一接口产出的 mp3 参数一致）；若拼接失败或时长对不上，
    回退为统一采样参数后重新编码，保证输出时长与各块之和一致。
    """
    if not parts:
        raise ValueError("没有可拼接的音频块")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.parent / f"._{out_path.stem}_concat.txt"
    list_file.write_text(
        "\n".join("file '%s'" % Path(p).as_posix() for p in parts), encoding="utf-8"
    )
    expected = sum(_probe_duration(p) for p in parts)
    try:
        r = subprocess.run(
            [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c", "copy", str(out_path)],
            capture_output=True, text=True, timeout=300,
        )
        got = _probe_duration(str(out_path))
        if r.returncode == 0 and got > 0 and abs(got - expected) <= 0.2:
            return

        # 回退：解码为统一 PCM 再拼，最后编码 mp3
        wavs = []
        for i, p in enumerate(parts):
            w = out_path.parent / f"._{out_path.stem}_{i}.wav"
            subprocess.run(
                [_ffmpeg(), "-y", "-i", str(p), "-ar", "24000", "-ac", "1",
                 "-c:a", "pcm_s16le", str(w)],
                capture_output=True, text=True, timeout=300,
            )
            wavs.append(str(w))
        wlist = out_path.parent / f"._{out_path.stem}_wav.txt"
        wlist.write_text(
            "\n".join("file '%s'" % Path(w).as_posix() for w in wavs), encoding="utf-8"
        )
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(wlist),
             "-c:a", "libmp3lame", "-b:a", "128k", str(out_path)],
            capture_output=True, text=True, timeout=300,
        )
        for w in wavs:
            Path(w).unlink(missing_ok=True)
        wlist.unlink(missing_ok=True)
    finally:
        list_file.unlink(missing_ok=True)


class NarrationTool(BaseTool):
    name = "narration"
    description = (
        "旁白组：把多段旁白文案批量合成为配音（豆包 TTS 2.0）。每段返回 mp3 路径、实测（权威）时长与"
        "字级时间戳。长文案会自动按句切块分别合成再拼接，避免长文本字级时间戳漂移导致字幕错位。"
        "旁白时长是画面时长的权威依据；字级时间戳供字幕组生成字幕。"
        "支持统一 speech_rate/loudness_rate 调节语速音量。"
    )
    parameters = [
        ToolParameter("segments", "array", "旁白分段列表，每项 {text} 或直接字符串（至少 1 段）"),
        ToolParameter("project", "string", "项目名；产物默认放 video_work/<project>/voice/", required=False),
        ToolParameter("output_dir", "string", "输出目录（可选，覆盖默认 video_work/<project>/voice/）", required=False),
        ToolParameter("speaker", "string", "音色ID；留空用 Settings 配置音色", required=False),
        ToolParameter("speech_rate", "integer", "统一语速 -50~100（100=2倍速）", required=False, default=0),
        ToolParameter("loudness_rate", "integer", "统一音量 -50~100", required=False, default=0),
    ]

    def __init__(self, cwd: str = ".", skill_manager=None, default_speaker: str = "", **kwargs):
        super().__init__(cwd)
        self.skill_manager = skill_manager
        self.default_speaker = (default_speaker or "").strip()

    def execute(self, segments, project: str = None, output_dir: str = None,
                speaker: str = None, speech_rate: int = 0, loudness_rate: int = 0,
                **kwargs) -> ToolResult:
        if not self.skill_manager:
            return ToolResult.fail("narration 需要 skill_manager 上下文")
        texts = self._normalize(segments)
        if not texts:
            return ToolResult.fail("segments 至少需要 1 段旁白文案")

        speaker = resolve_voice(speaker, self.default_speaker)

        out_dir = Path(output_dir) if output_dir else (
            Path(self.cwd) / "video_work" / (project or "narration") / "voice"
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        items, total = [], 0.0
        max_drift = 0.0
        chunk_total = 0
        for i, text in enumerate(texts):
            self.raise_if_cancelled()
            chunks = _split_text(text)
            chunk_total += len(chunks)
            self._emit_progress(f"旁白 {i + 1}/{len(texts)} 段（{len(chunks)} 块）...")

            seg_start = total
            chunk_cum = 0.0
            chunk_files, words_all = [], []
            for k, chunk in enumerate(chunks):
                self.raise_if_cancelled()
                mp3 = str(out_dir / f"vo_{i}_p{k}.mp3")
                res = self.skill_manager.dispatch(
                    "doubao_tts", text=chunk, output_path=mp3,
                    project=project or "", speaker=speaker,
                    speech_rate=speech_rate, loudness_rate=loudness_rate,
                )
                if not res.success:
                    return res
                audio_path = res.details.get("output_path", mp3)
                # 权威块长用 ffprobe 实测（TTS 自报的末字时间可能偏短）
                chunk_dur = _probe_duration(audio_path) or float(res.details.get("duration", 0) or 0)
                words, drift = _normalize_words(res.details.get("words", []) or [], chunk_dur)
                if abs(drift) > DRIFT_TOLERANCE:
                    self._emit_progress(
                        f"[旁白] 第 {i + 1} 段第 {k + 1} 块时间戳漂移 {drift:.2f}s，"
                        f"超出可校正范围（块长 {chunk_dur:.2f}s），保留原始时间戳")
                max_drift = max(max_drift, abs(drift))
                for w in words:
                    w["startTime"] = round(w["startTime"] + seg_start + chunk_cum, 3)
                    w["endTime"] = round(w["endTime"] + seg_start + chunk_cum, 3)
                words_all.extend(words)
                chunk_files.append(audio_path)
                chunk_cum += chunk_dur

            final = str(out_dir / f"vo_{i}.mp3")
            if len(chunk_files) == 1:
                # 单块无需拼接：直接作为该段音轨，避免多余重编码
                Path(final).unlink(missing_ok=True)
                shutil.move(chunk_files[0], final)
            else:
                _concat_audio(chunk_files, Path(final))
                for p in chunk_files:
                    Path(p).unlink(missing_ok=True)

            dur = _probe_duration(final) or chunk_cum
            if not Path(final).exists():
                return ToolResult.fail(f"旁白音轨拼接失败: {final}")
            items.append({
                "index": i, "text": text, "audio_path": final,
                "offset": round(total, 3),
                "duration": round(dur, 3), "words": words_all,
            })
            total += dur

        summary = "\n".join(
            f"  [{it['index']}] {it['duration']}s  {it['text'][:24]}" for it in items
        )
        return ToolResult.ok(
            f"旁白生成完成：{len(items)} 段（共 {chunk_total} 块），总时长 {round(total, 2)}s\n{summary}",
            segments=items,
            total_duration=round(total, 3),
            segment_count=len(items),
            chunk_count=chunk_total,
            max_drift=round(max_drift, 3),
            speaker=speaker,
            speech_rate=speech_rate,
        )

    @staticmethod
    def _normalize(segments) -> list:
        """把 segments 归一化为纯文案列表：支持 [str] / [{text}] / 单个 str。"""
        out = []
        if isinstance(segments, list):
            for s in segments:
                if isinstance(s, str):
                    t = s.strip()
                elif isinstance(s, dict):
                    t = str(s.get("text", "")).strip()
                else:
                    t = ""
                if t:
                    out.append(t)
        elif isinstance(s, str) and segments.strip():
            out.append(segments.strip())
        return out


__all__ = ["NarrationTool"]
