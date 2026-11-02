# -*- coding: utf-8 -*-
"""合成部门渲染器（合成组内部实现，自包含）。

职责：把若干段视频（各引擎产物）统一到同一画布规格后拼接，叠加旁白音频，
并按需烧录字幕组产出的 .ass 字幕，导出最终 mp4。

关键：**规格归一化**——各引擎产物分辨率/帧率/像素格式可能不同（如影视级 768P、
HTML 动画 1920x1080），直接 concat 会崩。本模块先把每段 scale+补边到目标画布、
统一 fps/pixfmt/SAR，再拼接；若各段本就同规格则走快速路径（不重编码）。
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or shutil.which("ffprobe.exe") or "ffprobe"


def _run(cmd: list, timeout: int = None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 失败: {' '.join(str(c) for c in cmd[:6])}...\n{(r.stderr or '')[-800:]}"
        )


def probe_duration(path: str) -> float:
    r = subprocess.run(
        [_ffprobe(), "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _media_info(path: str) -> dict:
    """返回画面流的完整规格；取不到返回 {}。

    拼接时只比对"尺寸/帧率"是不够的：concat demuxer 直接 copy 时按**首段的时间基**
    解释后续各包的时间戳。若不同引擎产物的 time_base 不同（如 Remotion 1/90000、
    ffmpeg/libx264 1/15360），后续段的 PTS 会被整体压缩，成片表现为"快进后定格"。
    因此这里把编码、时间基、像素格式、SAR 一并取回，规格不完全相同就必须先归一化。
    """
    r = subprocess.run(
        [_ffprobe(), "-v", "quiet", "-select_streams", "v:0",
         "-show_entries",
         "stream=codec_name,width,height,r_frame_rate,time_base,pix_fmt,sample_aspect_ratio",
         "-of", "json", path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        st = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    except Exception:
        return {}
    keys = ("codec_name", "width", "height", "r_frame_rate", "time_base",
            "pix_fmt", "sample_aspect_ratio")
    spec = {k: str(st.get(k) or "") for k in keys}
    return spec if spec.get("codec_name") and spec.get("width") else {}


def _fps_of(spec: dict) -> float:
    num, _, den = str(spec.get("r_frame_rate") or "0/1").partition("/")
    try:
        d = float(den or 1)
        return float(num) / d if d else 0.0
    except (TypeError, ValueError):
        return 0.0


def _normalize_clip(src: str, dst: str, W: int, H: int, fps: int) -> None:
    """把一段视频统一到目标画布：等比缩放 + 补边(黑) + 统一 fps/pixfmt/SAR，丢弃音轨。"""
    vf = (
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps},format=yuv420p"
    )
    _run([_ffmpeg(), "-y", "-i", src, "-vf", vf, "-an",
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", dst], timeout=None)


def _concat_videos(clips: list, dst: str, W: int, H: int, fps: int, progress=None) -> tuple:
    """拼接画面轨（丢弃音轨）。返回 (路径, 是否做了归一化)。

    快速路径（-c copy）只在**所有段的流规格完全一致**且都等于目标画布时使用；
    否则先逐段归一化重编码，再按同规格 copy 拼接。
    """
    specs = [_media_info(c) for c in clips]
    base = specs[0] if specs else {}
    mismatched = any(
        not s or s != base
        or int(s.get("width") or 0) != W or int(s.get("height") or 0) != H
        or abs(_fps_of(s) - fps) > 0.01
        for s in specs
    )
    work = Path(dst).parent

    def _normalize_all():
        norm = []
        for i, c in enumerate(clips):
            if progress:
                progress(f"归一化 {i + 1}/{len(clips)} 段...")
            n = str(work / f"_norm_{i}.mp4")
            _normalize_clip(c, n, W, H, fps)
            norm.append(n)
        return norm

    need_norm = mismatched
    if need_norm and progress:
        progress("各段流规格不一致（时间基/编码/画布），先归一化")
    if need_norm:
        clips = _normalize_all()

    def _copy_concat(srcs, out):
        lst = str(work / "_videos.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for c in srcs:
                f.write(f"file '{Path(c).resolve()}'\n")
        _run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", lst,
              "-c", "copy", "-an", out], timeout=None)

    if progress:
        progress("拼接画面...")
    _copy_concat(clips, dst)

    # 兜底校验：copy 拼接后的总长必须≈各段之和。若仍出现塌缩（规格之外的原因，
    # 如封装/时间戳异常），退回归一化重编码再拼，绝不把"快进"的片子当成功交付。
    expect = sum(probe_duration(c) or 0.0 for c in clips)
    got = probe_duration(dst) or 0.0
    if expect > 0 and abs(got - expect) > 0.5:
        if progress:
            progress(f"拼接后时长异常（{got:.2f}s ≠ 预期 {expect:.2f}s），回退归一化重拼...")
        clips = _normalize_all()
        need_norm = True
        _copy_concat(clips, dst)
    return dst, need_norm


def _exact_audio(src: str, dur: float, dst: str) -> None:
    """把一段音频（src 为空=静音）定长到 dur 秒，输出 44.1kHz 立体声 PCM(wav)，样本级精确。

    逐段 mp3 直接 concat 会因 mp3 编解码延迟、采样率不一、时间戳抖动导致段落错位，
    所以先统一成同规格 PCM 并"定长"，再做样本级拼接。
    """
    dur = max(0.05, float(dur))
    if src and str(src).strip() and Path(str(src)).exists():
        _run([_ffmpeg(), "-y", "-i", str(src), "-af", f"apad,atrim=0:{dur:.3f}",
              "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", dst], timeout=None)
    else:
        _run([_ffmpeg(), "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
              "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", dst], timeout=180)


def _concat_wavs(parts: list, dst: str) -> None:
    """把多段同规格 wav 用 concat demuxer 拼接（-c copy，样本级精确，无重采样与时间戳抖动）。"""
    lst = str(Path(dst).with_suffix(".txt"))
    with open(lst, "w", encoding="utf-8") as f:
        for p in parts:
            f.write(f"file '{Path(p).resolve().as_posix()}'\n")
    _run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", dst], timeout=None)


def _pad_video_to(src: str, dur: float, dst: str) -> None:
    """把一段视频用最后一帧补长到 dur 秒（重编码）。"""
    extra = max(0.0, dur - (probe_duration(src) or 0.0))
    _run([_ffmpeg(), "-y", "-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration={extra:.3f}",
          "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", dst], timeout=None)


def _bgm_bed(src: str, target: float, work: Path) -> tuple:
    """把背景音乐铺成恰好 target 秒的 PCM(wav)。

    - 音乐已够长 → 直接截断到 target；
    - 音乐偏短 → 复制多份并用 acrossfade **交叉淡化**首尾交叠拼接，
      避免 `-stream_loop` 那种"播完瞬间跳回开头"的硬接缝。

    返回 (wav 路径, 是否发生了循环)。
    """
    target = max(0.05, float(target))
    dst = str(work / "bgm_bed.wav")
    d = probe_duration(src) or 0.0
    if d <= 0 or d >= target:
        _run([_ffmpeg(), "-y", "-i", src, "-af", f"atrim=0:{target:.3f}",
              "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", dst], timeout=None)
        return dst, False

    # 交叠时长：够明显才有意义，同时不得超过音乐本身的一半（acrossfade 要求）。
    xf = min(2.0, max(0.5, d * 0.15), max(0.05, d * 0.5))
    # n 份首尾交叠后的总长 = n*d - (n-1)*xf，取满足 >= target 的最小份数。
    n = 2
    while n * d - (n - 1) * xf < target and n < 64:
        n += 1

    inputs, fc = [], []
    for _ in range(n):
        inputs += ["-i", src]
    for k in range(n):
        fc.append(f"[{k}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100[a{k}]")
    prev = "a0"
    for k in range(1, n):
        lab = f"ax{k}"
        fc.append(f"[{prev}][a{k}]acrossfade=d={xf:.3f}[{lab}]")
        prev = lab
    fc.append(f"[{prev}]atrim=0:{target:.3f},asetpts=N/SR/TB[aout]")
    _run([_ffmpeg(), "-y"] + inputs + ["-filter_complex", ";".join(fc),
                                       "-map", "[aout]", "-c:a", "pcm_s16le", dst], timeout=None)
    return dst, True


def _sfx_bed(events: list, target: float, work: Path) -> tuple:
    """把多个音效事件铺成恰好 target 秒的 PCM(wav)。

    events: [{path, at(秒), level(0~1), fade_in(秒)}]
    返回 (wav 路径, 实际使用的音效数)。没有可用事件时返回 ("", 0)。
    """
    target = max(0.05, float(target))
    usable = []
    for ev in (events or []):
        if not isinstance(ev, dict):
            continue
        p = str(ev.get("path") or "")
        if not p or not Path(p).exists():
            continue
        try:
            at = max(0.0, float(ev.get("at") or 0.0))
        except (TypeError, ValueError):
            at = 0.0
        if at >= target:
            continue
        try:
            lvl = max(0.0, min(1.0, float(ev.get("level", 0.6))))
        except (TypeError, ValueError):
            lvl = 0.6
        if lvl <= 0:
            continue
        try:
            fi = max(0.0, min(1.0, float(ev.get("fade_in") or 0.0)))
        except (TypeError, ValueError):
            fi = 0.0
        usable.append((p, at, lvl, fi))
    if not usable:
        return "", 0

    dst = str(work / "sfx_bed.wav")
    inputs, fc = [], []
    for k, (p, at, lvl, fi) in enumerate(usable):
        inputs += ["-i", p]
        ms = int(round(at * 1000))
        chain = (f"[{k}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"aresample=44100,volume={lvl:.3f}")
        if fi > 0.001:
            chain += f",afade=t=in:st=0:d={fi:.3f}"
        chain += f",adelay={ms}|{ms}[s{k}]"
        fc.append(chain)

    if len(usable) == 1:
        fc.append(f"[s0]apad,atrim=0:{target:.3f},alimiter=limit=0.98[out]")
    else:
        labels = "".join(f"[s{k}]" for k in range(len(usable)))
        fc.append(f"{labels}amix=inputs={len(usable)}:duration=longest:normalize=0,"
                  f"apad,atrim=0:{target:.3f},alimiter=limit=0.98[out]")

    _run([_ffmpeg(), "-y"] + inputs + ["-filter_complex", ";".join(fc),
                                       "-map", "[out]", "-c:a", "pcm_s16le", dst], timeout=None)
    return dst, len(usable)


# ── 转场（段与段之间的切换） ─────────────────────────────────────────────
# 直接透传 ffmpeg `xfade` 的 transition 名；下面只是一份"常见模板"说明，不做任何名称打分/映射。
DEFAULT_TRANSITION_SECONDS = 0.6

TRANSITION_TEMPLATES = (
    "fade", "dissolve", "pixelize", "radial", "hblur", "distance",
    "circleopen", "circleclose", "circlecrop", "rectcrop",
    "wipeleft", "wiperight", "wipeup", "wipedown", "wipetl", "wipetr", "wipebl", "wipebr",
    "slideleft", "slideright", "slideup", "slidedown",
    "smoothleft", "smoothright", "smoothup", "smoothdown",
    "coverleft", "coverright", "coverup", "coverdown",
    "revealleft", "revealright", "revealup", "revealdown",
    "diagtl", "diagtr", "diagbl", "diagbr",
    "hlslice", "hrslice", "vuslice", "vdslice",
    "squeezeh", "squeezev", "zoomin",
    "fadeblack", "fadewhite", "fadegrays", "fadefast", "fadeslow",
    "vertopen", "vertclose", "horzopen", "horzclose",
    "hlwind", "hrwind", "vuwind", "vdwind",
)


def _norm_spec(t, default_dur: float = DEFAULT_TRANSITION_SECONDS):
    """把单个转场描述归一为 {"type": str, "duration": float}；None/空/"none"/"cut" → None(硬切)。"""
    name, dur = "", default_dur
    if isinstance(t, str):
        name = t.strip()
    elif isinstance(t, dict):
        name = str(t.get("type") or t.get("transition") or "").strip()
        dur = t.get("duration", t.get("seconds", default_dur))
    if not name or name.lower() in ("none", "cut"):
        return None
    try:
        dur = float(dur)
    except (TypeError, ValueError):
        dur = default_dur
    return {"type": name, "duration": dur}


def _parse_transitions(transitions, n: int) -> list:
    """归一转场参数为长度 n-1 的列表（每处接缝一项，None=硬切）。

    支持：None / 单个 str(或 dict，应用到所有接缝) / 列表(逐接缝，元素可为 str/dict/None)。
    """
    joints = n - 1
    if joints <= 0:
        return []
    if transitions is None:
        return [None] * joints
    if isinstance(transitions, (list, tuple)):
        return [_norm_spec(transitions[i]) if i < len(transitions) else None for i in range(joints)]
    spec = _norm_spec(transitions)
    return [dict(spec) if spec else None for _ in range(joints)]


def _xfade_chain(clips: list, joints: list, dst: str, W: int, H: int, fps: int, progress=None) -> tuple:
    """用 xfade 把各段串起来：转场接缝=重叠溶解，硬切接缝=concat。返回 (dst, 总时长)。"""
    durs = [probe_duration(c) or 0.0 for c in clips]
    fc, inputs = [], []
    for c in clips:
        inputs += ["-i", c]
    prev = "[0:v]"
    acc = durs[0]
    for k in range(1, len(clips)):
        j = joints[k - 1] if k - 1 < len(joints) else None
        lab = f"[x{k}]"
        if j:
            t = float(j["duration"])
            off = max(0.0, acc - t)
            if progress:
                progress(f"转场 {k}/{len(clips) - 1}：{j['type']}（{t:.2f}s）")
            fc.append(f"{prev}[{k}:v]xfade=transition={j['type']}:duration={t:.3f}:offset={off:.3f}{lab}")
            acc = acc + durs[k] - t
        else:
            fc.append(f"{prev}[{k}:v]concat=n=2:v=1:a=0{lab}")
            acc = acc + durs[k]
        prev = lab
    fc.append(f"{prev}format=yuv420p[vout]")
    _run([_ffmpeg(), "-y"] + inputs + [
        "-filter_complex", ";".join(fc), "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-t", f"{acc:.3f}", dst], timeout=None)
    return dst, acc


def _ass_filter(ass_path: str) -> str:
    """构造 subtitles 滤镜路径（Windows 盘符冒号需转义）。"""
    p = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", "\\:")
    return f"subtitles='{p}'"


def compose(
    scene_videos: list,
    scene_audios: list = None,
    output_path: str = "",
    subtitle_ass: str = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    progress=None,
    transitions=None,
    bgm: str = None,
    bgm_volume: float = 0.25,
    sfx: list = None,
) -> dict:
    """合成最终 mp4。

    scene_videos: 各段视频路径（按顺序）；scene_audios 与之一一对应（可为空串/None=该段无旁白）。
    subtitle_ass: 字幕组产出的 .ass（自带样式）；给了就烧。
    transitions: 段间转场。None=全硬切；str/dict=应用到所有接缝；list=逐接缝(元素为 str/dict/None)。
                 每项形如 "dissolve" 或 {"type": "pixelize", "duration": 0.6}。
                 转场会让相邻两段重叠 → 成片时长变短，调用方需按同样重叠量计算字幕/旁白时间轴。
    bgm: 背景音乐音频路径（可选）。会铺满全片（音乐偏短则交叉淡化无缝循环），按 bgm_volume 压低后与旁白混音，旁白优先。
    bgm_volume: 背景音乐音量系数（0~1，默认 0.25）。
    sfx: 音效事件 [{path, at(成片时间轴秒), level(0~1), fade_in(秒)}]；铺成独立音效轨后混入。
    返回 {output_path, duration, video_norm, has_audio, has_bgm, bgm_looped, has_sfx, sfx_count,
          subtitle_burned, transitions_used}。
    """
    if not scene_videos:
        raise ValueError("scene_videos 不能为空")
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="compose_"))

    try:
        # 先探明每段画面/旁白的实际时长（段长公式见 0b）。
        audios = list(scene_audios or [])
        clips = list(scene_videos)
        vdurs, adurs = [], []
        for i, c in enumerate(clips):
            vdurs.append(probe_duration(c) or 1.0)
            a = audios[i] if i < len(audios) else ""
            adurs.append(probe_duration(str(a))
                         if (a and str(a).strip() and Path(str(a)).exists()) else 0.0)

        # 0. 转场：归一化并裁剪（不超过相邻两段"音画等长基准"的 90%，避免 xfade 越界）。
        joints = _parse_transitions(transitions, len(clips))
        for k, j in enumerate(joints):
            if not j:
                continue
            b0 = max(vdurs[k], adurs[k]) if adurs[k] > 0 else vdurs[k]
            b1 = max(vdurs[k + 1], adurs[k + 1]) if adurs[k + 1] > 0 else vdurs[k + 1]
            j["duration"] = max(0.05, min(float(j["duration"]), min(b0, b1) * 0.9))
        use_xfade = any(joints)

        # 0b. 逐段定长：段长 target = 该段"音/画"在成片时间轴上占用的长度。
        #     旁白短于画面 → 给旁白补静音；旁白长于画面 → 给画面补末帧。
        #     ⚠️ 有出向转场的段，画面要和后一段重叠 t 秒（xfade），这段 t 必须在段长里额外留出来
        #     （target = max(画面长, 旁白长 + t)），否则转场只能从旁白尾部扣走 t 秒——最后几个字被吃掉。
        #     多留的 t 恰好落在转场重叠区里，所以观众看不到额外的静止帧。
        targets = []
        for i, c in enumerate(clips):
            vdur, adur = vdurs[i], adurs[i]
            t_out = float(joints[i]["duration"]) if (i < len(joints) and joints[i]) else 0.0
            target = max(vdur, adur + t_out) if adur > 0 else max(vdur, t_out)
            targets.append(target)
            if target > vdur + 0.05:
                pv = str(tmp / f"_padv_{i}.mp4")
                _pad_video_to(c, target, pv)
                clips[i] = pv

        # 1. 画面轨
        if use_xfade:
            # xfade 要求各段严格同规格 → 全部归一化后再串。
            norm = []
            for i, c in enumerate(clips):
                if progress:
                    progress(f"转场装配：归一化 {i + 1}/{len(clips)} 段...")
                n = str(tmp / f"_xn_{i}.mp4")
                _normalize_clip(c, n, width, height, fps)
                norm.append(n)
            video_only = str(tmp / "video.mp4")
            _, _xacc = _xfade_chain(norm, joints, video_only, width, height, fps, progress=progress)
            need_norm = True
        else:
            video_only = str(tmp / "video.mp4")
            _, need_norm = _concat_videos(clips, video_only, width, height, fps, progress=progress)
        video_dur = probe_duration(video_only) or 0.0
        if progress:
            progress("画面轨就绪，构建旁白轨...")

        # 2. 旁白轨：每段先"定长"成同规格 PCM（长度 = 该段旁白的时间槽位），再样本级拼接成整轨。
        #    槽位 = 段长 - 出向转场时长。因为 0b 已把转场重叠的 t 留进了段长，
        #    这里槽位 >= 旁白原长，**不会裁掉任何语音**；旁白短于槽位时补静音。
        #    结果：每段旁白完整、首尾相接、互不重叠，与画面时间轴逐段对齐。
        has_audio = any(a and str(a).strip() and Path(str(a)).exists() for a in audios[:len(clips)])
        audio_bed = ""
        if has_audio:
            exact = []
            for i in range(len(clips)):
                a = audios[i] if i < len(audios) else ""
                src = str(a) if (a and str(a).strip() and Path(str(a)).exists()) else ""
                if progress:
                    progress(f"旁白定长 {i + 1}/{len(clips)} 段...")
                slot = targets[i]
                if i < len(joints) and joints[i]:
                    slot = max(0.05, slot - float(joints[i]["duration"]))
                w = str(tmp / f"_bed_{i}.wav")
                _exact_audio(src, slot, w)
                exact.append(w)
            audio_bed = str(tmp / "bed.wav")
            _concat_wavs(exact, audio_bed)
            if progress:
                progress("旁白轨就绪")

        # 3. 组装最终命令：画面（含烧字幕）与**单条整轨旁白**各自独立编码，最后合流。
        #    旁白不做"滤镜逐段 concat"（会与画面编码耦合、丢样本/漂移），而是先做成整轨再合。
        src_video = video_only
        if use_xfade:
            # 转场路径：旁白已在 2. 按同一批重叠量逐段让位并拼成整轨，这里直接用整轨
            # （不再 acrossfade——那会让相邻两段旁白真正叠在一起同时发声）。
            final_dur = video_dur
        else:
            bed_dur = probe_duration(audio_bed) if audio_bed else 0.0
            final_dur = max(video_dur, bed_dur) if bed_dur > 0 else video_dur
            # 画面与旁白必须等长：画面短一点也补齐（差值只在 1 帧内），
            # 否则两轨时长不一致会让不同播放器在片尾产生不同的音画漂移。
            if bed_dur > video_dur + 0.001:
                padded = str(tmp / "video_pad.mp4")
                _run([_ffmpeg(), "-y", "-i", video_only,
                      "-vf", f"tpad=stop_mode=clone:stop_duration={bed_dur - video_dur:.3f}",
                      "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", padded], timeout=None)
                src_video = padded

        if subtitle_ass and not Path(subtitle_ass).exists():
            raise FileNotFoundError(f"字幕文件不存在: {subtitle_ass}")

        # 3b. 背景音乐（可选）：先铺成恰好 final_dur 秒的整轨（音乐偏短则交叉淡化无缝循环），
        #     再压低音量与旁白混音（旁白优先）。
        bgm_path = ""
        bgm_bed = ""
        bgm_looped = False
        if bgm and str(bgm).strip():
            if not Path(str(bgm)).exists():
                raise FileNotFoundError(f"背景音乐文件不存在: {bgm}")
            bgm_path = str(bgm)
            if progress:
                progress("构建背景音乐轨...")
            bgm_bed, bgm_looped = _bgm_bed(bgm_path, final_dur, tmp)
            if progress and bgm_looped:
                progress(f"背景音乐已交叉淡化循环铺满 {final_dur:.1f}s")
        bgm_vol = max(0.0, min(1.0, float(bgm_volume)))

        # 3c. 音效（可选）：把带时间点的一次性音效铺成独立整轨，再与旁白/BGM 混音。
        sfx_bed = ""
        sfx_count = 0
        if sfx:
            if progress:
                progress("构建音效轨...")
            sfx_bed, sfx_count = _sfx_bed(sfx, final_dur, tmp)
            if progress and sfx_count:
                progress(f"音效轨就绪：{sfx_count} 个事件")

        vf = f"[0:v]{_ass_filter(subtitle_ass)}[v]" if subtitle_ass else "[0:v]null[v]"
        cmd = [_ffmpeg(), "-y", "-i", src_video]
        parts = [vf]
        labels = []

        if audio_bed:
            cmd += ["-i", audio_bed]
            parts.append("[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100[vo]")
            labels.append("vo")
        if bgm_bed:
            cmd += ["-i", bgm_bed]
            bi = 1 + (1 if audio_bed else 0)
            # 首尾淡入淡出：与画面同时结束，避免"音乐在半句上被硬切"。
            fade_out = min(2.0, max(0.4, final_dur * 0.1))
            fade_in = min(0.8, max(0.2, final_dur * 0.05))
            fade_out_start = max(0.0, final_dur - fade_out)
            parts.append(
                f"[{bi}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100,"
                f"afade=t=in:st=0:d={fade_in:.3f},"
                f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f},"
                f"volume={bgm_vol:.3f}[bgm]"
            )
            labels.append("bgm")
        if sfx_bed:
            cmd += ["-i", sfx_bed]
            si = 1 + (1 if audio_bed else 0) + (1 if bgm_bed else 0)
            parts.append(f"[{si}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,aresample=44100[sfx]")
            labels.append("sfx")

        has_audio_out = bool(labels)
        if len(labels) == 1:
            parts.append(f"[{labels[0]}]anull[aout]")
            cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[aout]"]
        elif len(labels) > 1:
            # duration=first：以第一条（旁白，若无则 BGM/音效）为基准长度；
            # normalize=0 保持各自音量；alimiter 防止多路叠加削波。
            mix = "".join(f"[{l}]" for l in labels)
            parts.append(f"{mix}amix=inputs={len(labels)}:duration=first:normalize=0,"
                         "alimiter=limit=0.95[aout]")
            cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[aout]"]
        else:
            cmd += ["-filter_complex", vf, "-map", "[v]"]
        # 恒定帧率 + 规整时间基 + 密集关键帧 + faststart：
        #  - CFR/时间基：各播放器对时间轴解释一致；
        #  - 密集关键帧(默认 0.5s)：拖动进度条时画面能就近定位。默认 x264 关键帧约 8s 一个，
        #    弱播放器只会跳到关键帧、音频却能精确定位 → 画面(含烧录字幕)与声音差出好几秒。
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                "-r", str(fps), "-fps_mode", "cfr",
                "-g", str(max(1, int(round(fps / 2)))), "-keyint_min", str(max(1, int(round(fps / 2)))),
                "-video_track_timescale", str(int(fps) * 1000)]
        if has_audio_out:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
        cmd += ["-movflags", "+faststart", "-t", f"{final_dur:.3f}", str(out)]
        if progress:
            progress("烧字幕 + 导出成片...")
        _run(cmd, timeout=None)

        return {
            "output_path": str(out),
            "duration": round(probe_duration(str(out)) or final_dur, 2),
            "video_norm": need_norm,
            "has_audio": has_audio_out,
            "has_voice": bool(audio_bed),
            "has_bgm": bool(bgm_path),
            "bgm_looped": bgm_looped,
            "has_sfx": bool(sfx_bed),
            "sfx_count": sfx_count,
            "subtitle_burned": bool(subtitle_ass),
            "transitions_used": sum(1 for j in joints if j),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
