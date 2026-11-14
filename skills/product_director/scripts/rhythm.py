# -*- coding: utf-8 -*-
"""音乐节奏分析：给 product_director 的 BGM 分流提供「切点网格」。

只依赖 ffmpeg + numpy（librosa 可选但非必需）：
  1. ffmpeg 解码成 22.05kHz 单声道 float32
  2. 帧能量 → 起音包络（能量正向差分）
  3. 自相关估 BPM（60~190），再按拍长做梳状打分求相位
  4. 每 4 拍一个小节，按小节能量分段

输出的网格会被注入提示词：LLM 按 `bars / downbeats` 选切点、按 `bpm` 定单镜长度，
而不是凭感觉写秒数。
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

try:
    import numpy as np
except Exception:  # pragma: no cover - 没装 numpy 时退回固定网格
    np = None

_SR = 22050
_HOP = 512
_WIN = 1024


def _decode(path: Path) -> "np.ndarray | None":
    if np is None:
        return None
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(_SR), "-f", "f32le", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float32)


def _envelope(x: "np.ndarray"):
    """返回 (能量包络, 起音强度, 每秒帧数)。"""
    if len(x) < _WIN:
        return np.zeros(1, dtype=np.float32), np.zeros(1, dtype=np.float32), _SR / _HOP
    frames = np.lib.stride_tricks.sliding_window_view(x, _WIN)[::_HOP]
    rms = np.sqrt((frames.astype(np.float32) ** 2).mean(axis=1) + 1e-9)
    onset = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    return rms, onset, _SR / _HOP


def _estimate_bpm(onset: "np.ndarray", fps: float) -> float:
    """自相关找主周期，映射成 BPM。"""
    x = onset - float(onset.mean())
    if not len(x) or float(np.abs(x).sum()) <= 0:
        return 120.0
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    ac[0] = 0.0
    lags = np.arange(len(ac), dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        bpm = 60.0 * fps / np.maximum(lags, 1e-9)
    mask = (bpm >= 60.0) & (bpm <= 190.0)
    if not mask.any():
        return 120.0
    idx = np.argmax(np.where(mask, ac, -np.inf))
    # 抛物线插值，避免整数滞后带来的 1~2 BPM 抖动
    if 0 < idx < len(ac) - 1:
        y0, y1, y2 = ac[idx - 1], ac[idx], ac[idx + 1]
        denom = (y0 - 2 * y1 + y2)
        if abs(denom) > 1e-12:
            shift = 0.5 * (y0 - y2) / denom
            lags_peak = lags[idx] + shift
        else:
            lags_peak = lags[idx]
    else:
        lags_peak = lags[idx]
    bpm_val = 60.0 * fps / max(lags_peak, 1e-9)
    return float(round(bpm_val, 2))


def _beat_phase(onset: "np.ndarray", fps: float, bpm: float) -> float:
    """在 [0, 拍长) 内找让拍点能量最大的相位，返回相位（秒）。"""
    period_f = max((60.0 / bpm) * fps, 1.0)
    best_off, best_score = 0.0, -1.0
    steps = max(int(period_f * 4), 4)
    for i in range(steps):
        off = period_f * i / steps
        k = np.arange(0, len(onset), period_f) + off
        idx = np.round(k).astype(int)
        idx = idx[idx < len(onset)]
        if not len(idx):
            continue
        score = float(onset[idx].sum())
        if score > best_score:
            best_off, best_score = off, score
    return float(best_off / fps)


def _sections(rms: "np.ndarray", fps: float, duration: float):
    """按 2 秒窗口的均能量切成若干段，标注 low/mid/high。"""
    if not len(rms) or duration <= 0:
        return []
    win = max(int(2.0 * fps), 1)
    n = max(1, min(len(rms) // win, int(math.ceil(duration / 2.0))))
    energies = [float(rms[i * win:(i + 1) * win].mean()) for i in range(n)]
    peak = max(energies) or 1.0
    norm = [e / peak for e in energies]
    out = []
    for i, e in enumerate(norm):
        start = i * 2.0
        end = min(duration, start + 2.0)
        if end <= start:
            break
        label = "low" if e < 0.45 else ("high" if e > 0.75 else "mid")
        if out and out[-1]["level"] == label:
            out[-1]["end"] = round(end, 2)
        else:
            out.append({"start": round(start, 2), "end": round(end, 2), "level": label,
                        "energy": round(e, 3)})
    return out


def _accents(onset: "np.ndarray", fps: float, beats: list, limit: int = 10):
    """拍点上的重击：取每个拍点附近起音强度的峰值，挑最强的若干个。"""
    if not len(onset) or not beats:
        return []
    scores = []
    for b in beats:
        i = int(round(b * fps))
        seg = onset[max(0, i - 2): i + 3]
        scores.append(float(seg.max()) if len(seg) else 0.0)
    peak = max(scores) or 1.0
    ranked = sorted(range(len(scores)), key=lambda i: -scores[i])[:limit]
    return [{"t": round(float(beats[i]), 3), "strength": round(scores[i] / peak, 2)}
            for i in sorted(ranked)]


def _drops(rms: "np.ndarray", fps: float, bars: list, duration: float, ratio: float = 1.45):
    """小节能量突增处（drop / impact）：比前两个小节平均能量高出 ratio 倍。"""
    if not len(rms) or len(bars) < 3:
        return []
    step = (bars[1] - bars[0]) if len(bars) > 1 else 2.0
    energies = []
    for i, b in enumerate(bars):
        end = bars[i + 1] if i + 1 < len(bars) else min(duration, b + step)
        a, z = int(b * fps), min(int(end * fps), len(rms))
        energies.append(float(rms[a:z].mean()) if z > a else 0.0)
    out = []
    for i in range(2, len(energies)):
        prev = (energies[i - 1] + energies[i - 2]) / 2.0
        if prev > 1e-9 and energies[i] / prev >= ratio:
            out.append({"t": round(float(bars[i]), 3), "jump": round(energies[i] / prev, 2)})
    return out


def analyze(music_path, duration: float | None = None) -> dict:
    """分析音乐，返回节奏网格。任何一步失败都退回固定 120BPM 网格（不阻断出片）。"""
    p = Path(music_path) if music_path else None
    fallback = {
        "ok": False, "reason": "无音乐文件或解码失败，使用 120BPM 兜底网格",
        "bpm": 120.0, "beat_interval": 0.5,
    }
    if p is None or not p.exists():
        return _fixed_grid(fallback, duration or 0.0)

    x = _decode(p)
    if x is None or not len(x):
        fallback["reason"] = "ffmpeg 解码失败，使用 120BPM 兜底网格"
        return _fixed_grid(fallback, duration or 0.0)

    audio_duration = len(x) / float(_SR)
    total = float(duration or audio_duration)
    # 只要前 total 秒的包络：整首几分钟的歌没必要全量算
    if duration and duration < audio_duration:
        x = x[: int(duration * _SR)]
    rms, onset, fps = _envelope(x)
    bpm = _estimate_bpm(onset, fps)
    beat_interval = 60.0 / bpm
    phase = _beat_phase(onset, fps, bpm)

    beats = []
    t = phase
    while t < total - 1e-6:
        beats.append(round(t, 3))
        t += beat_interval
    if beats and beats[0] > 0.05:
        beats.insert(0, 0.0)

    # 小节：每 4 拍，选能量最高的一组相位作为强拍起点
    bar_candidates = []
    for shift in range(4):
        idx = [i for i in range(shift, len(beats), 4)]
        if not idx:
            continue
        score = sum(float(onset[min(int(beats[i] * fps), len(onset) - 1)]) for i in idx)
        bar_candidates.append((score, shift))
    shift = max(bar_candidates)[1] if bar_candidates else 0
    downbeats = [beats[i] for i in range(shift, len(beats), 4)]
    bars = downbeats

    return {
        "ok": True,
        "audio_duration": round(audio_duration, 3),
        "used_duration": round(total, 3),
        "bpm": bpm,
        "beat_interval": round(beat_interval, 4),
        "beats": beats,
        "downbeats": [round(b, 3) for b in downbeats],
        "bars": [round(b, 3) for b in bars],
        "accents": _accents(onset, fps, beats),
        "drops": _drops(rms, fps, [round(b, 3) for b in bars], total),
        "sections": _sections(rms, fps, total),
    }


def _fixed_grid(meta: dict, duration: float) -> dict:
    bpm = 120.0
    step = 60.0 / bpm
    beats = [round(i * step, 3) for i in range(int(max(duration, 0) / step) + 1)]
    down = beats[::4]
    return {**meta, "audio_duration": None, "used_duration": round(duration, 3),
            "beats": beats, "downbeats": down, "bars": down, "sections": []}


def summarize(rhythm: dict, limit: int = 24) -> str:
    """给提示词用的紧凑摘要：BPM + 小节表 + 重击/落点 + 能量分段。"""
    if not rhythm:
        return "（没有节奏数据：按 120BPM 4/4 处理）"
    bars = rhythm.get("bars") or []
    shown = bars[:limit]
    tail = "" if len(bars) <= limit else f" …共 {len(bars)} 小节"
    sections = "；".join(
        f"{s['start']}-{s['end']}s {s['level']}" for s in (rhythm.get("sections") or [])[:8])
    accents = rhythm.get("accents") or []
    drops = rhythm.get("drops") or []
    accent_txt = "、".join(f"{a['t']}s({a['strength']})" for a in accents[:8]) or "无"
    drop_txt = "、".join(f"{d['t']}s(×{d['jump']})" for d in drops[:6]) or "无"
    return (
        f"BPM={rhythm.get('bpm')}（一拍 {rhythm.get('beat_interval')}s，4/4）\n"
        f"小节起点（秒）：{', '.join(str(b) for b in shown)}{tail}\n"
        f"重击拍（秒/强度）：{accent_txt}\n"
        f"能量落点 drop（秒/跃升倍数）：{drop_txt}\n"
        f"能量分段：{sections or '未知'}"
    )


def save(rhythm: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rhythm, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":  # 便于单独调试：python rhythm.py <music>
    import sys
    res = analyze(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(res, ensure_ascii=False, indent=2))
