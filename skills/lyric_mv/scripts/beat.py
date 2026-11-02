# -*- coding: utf-8 -*-
"""从音频实测「拍网格」(BPM + 相位)。不使用任何写死数值。

方法（直接优化"拍点是否落在起声上"，而非只靠自相关，避免倍频误判）：
  1. 谱通量(spectral flux) 求 onset 包络
  2. (BPM, 相位) 二维粗搜：最大化"拍点处的 onset 均值 × 120BPM 附近的先验"
  3. 相位精修：用每个拍点邻域内最近 onset 峰的中位偏移，纠正相位（一步 PLL）
  4. 在该解附近细搜 BPM，重复 3
  5. 输出网格 + 拟合质量（落在拍点 ±40ms 内的 onset 峰占比、中位偏移）

输出：beat.json、music_<length>s.mp3
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

SR = 22050
HOP = 256
NFFT = 1024
ENV_FPS = SR / HOP          # 包络帧率 ≈ 86.13 Hz
PRIOR_CENTER = 120.0        # 先验中心（人听感常见节拍区间）
PRIOR_SIGMA = 0.40          # 对数正态先验宽度（octave）


def _run(cmd):
    return subprocess.run(cmd, capture_output=True)


def decode(path: Path) -> np.ndarray:
    p = _run(["ffmpeg", "-v", "quiet", "-i", str(path), "-ac", "1",
              "-ar", str(SR), "-f", "f32le", "-"])
    return np.frombuffer(p.stdout, dtype=np.float32).astype(np.float64)


def onset_envelope(x: np.ndarray) -> np.ndarray:
    if len(x) < NFFT:
        raise RuntimeError("音频过短")
    n = 1 + (len(x) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(NFFT)[None, :], axis=1))
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (freqs >= 150) & (freqs <= 6000)
    spec = np.log1p(spec[:, band])
    flux = np.diff(spec, axis=0)
    env = np.maximum(flux, 0).sum(axis=1)
    env = np.concatenate([[0.0], env])
    return (env - env.mean()) / (env.std() + 1e-9)


def _beat_score(env, period, phase, tmin=0.0, tmax=None):
    """给定周期与相位，拍点处 onset 的均值（越多拍点踩在起声上越高）。"""
    n = len(env)
    tmax = n if tmax is None else tmax
    pos = np.arange(phase + np.ceil((tmin - phase) / period) * period, tmax, period)
    idx = np.round(pos).astype(int)
    idx = idx[(idx >= 0) & (idx < n)]
    if len(idx) < 6:
        return -1.0, idx
    return float(env[idx].mean()), idx


def _best_phase(env, period, tmin=0.0, tmax=None, step=0.5):
    best_off, best_v = 0.0, -1e18
    for off in np.arange(0.0, period, step):
        v, _ = _beat_score(env, period, off, tmin, tmax)
        if v > best_v:
            best_v, best_off = v, float(off)
    return best_off, best_v


def coarse_grid(env, bpm_lo=70.0, bpm_hi=190.0, bpm_step=0.5):
    """二维粗搜：返回 (bpm, phase, score)。score 已含先验。"""
    best = (-1e18, PRIOR_CENTER, 0.0)
    for bpm in np.arange(bpm_lo, bpm_hi + 1e-9, bpm_step):
        period = ENV_FPS * 60.0 / bpm
        off, v = _best_phase(env, period, step=0.5)
        prior = np.exp(-0.5 * (np.log2(bpm / PRIOR_CENTER) / PRIOR_SIGMA) ** 2)
        s = v * prior
        if s > best[0]:
            best = (s, float(bpm), off)
    return best[1], best[2], best[0]


def refine_phase(env, period, phase):
    """把相位对齐到拍点邻域内最近 onset 峰的中位偏移（一步 PLL）。"""
    n = len(env)
    pos = np.arange(phase, n, period)
    lags = []
    r = max(1, int(round(period * 0.35)))
    for p in pos:
        i = int(round(p))
        lo, hi = max(0, i - r), min(n, i + r + 1)
        if hi - lo < 3:
            continue
        j = lo + int(np.argmax(env[lo:hi]))
        lags.append(j - p)
    if not lags:
        return phase
    return (phase + float(np.median(lags))) % period


def fine_grid(env, bpm, phase, span=3.0, step=0.02):
    best = (-1e18, bpm, phase)
    for b in np.arange(bpm - span, bpm + span + 1e-9, step):
        period = ENV_FPS * 60.0 / b
        off, v = _best_phase(env, period, step=0.5)
        off = refine_phase(env, period, off)
        v2, _ = _beat_score(env, period, off)
        prior = np.exp(-0.5 * (np.log2(b / PRIOR_CENTER) / PRIOR_SIGMA) ** 2)
        s = v2 * prior
        if s > best[0]:
            best = (s, float(b), float(off))
    return best[1], best[2]


def quality(env, period, phase):
    """拟合质量：每个拍点邻域 ±0.3 拍内是否存在 onset 峰，以及其偏移。"""
    n = len(env)
    thr = env.max() * 0.30
    pos = np.arange(phase, n, period)
    r = max(1, int(round(period * 0.3)))
    lags, hit = [], 0
    for p in pos:
        i = int(round(p))
        lo, hi = max(0, i - r), min(n, i + r + 1)
        if hi - lo < 3:
            continue
        seg = env[lo:hi]
        j = lo + int(np.argmax(seg))
        if env[j] >= thr:
            hit += 1
            lags.append((j - p) / ENV_FPS * 1000.0)
    frac = hit / max(1, len(pos))
    med = float(np.median(np.abs(lags))) if lags else float("nan")
    return frac, med, len(pos)


def window_score(env, length):
    """窗口打分：onset 能量密度 × 自相关节奏清晰度（避免选到前奏/尾奏）。"""
    n = len(env)
    win = int(length * ENV_FPS)
    csum = np.concatenate([[0.0], np.cumsum(env)])
    energy = (csum[win:] - csum[:-win]) / win
    lag_lo = int(ENV_FPS * 60 / 190)
    lag_hi = int(ENV_FPS * 60 / 70)
    best = (0.0, 0)
    for s in range(0, max(1, n - win), int(ENV_FPS)):
        e = energy[s]
        if e <= 0:
            continue
        seg = env[s:s + win] - env[s:s + win].mean()
        ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
        ac = ac / (ac[0] + 1e-9)
        clarity = float(ac[lag_lo:lag_hi].max()) if lag_hi < len(ac) else 0.0
        score = e * clarity
        if score > best[0]:
            best = (score, s)
    return best[1] / ENV_FPS


def cut(src: Path, dst: Path, start: float, length: float):
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.4f}", "-i", str(src),
          "-t", f"{length:.4f}",
          "-af", "afade=t=in:st=0:d=0.04,afade=t=out:st=%.3f:d=0.30" % max(length - 0.30, 0),
          "-c:a", "libmp3lame", "-q:a", "2", str(dst)])
    if not dst.exists():
        raise RuntimeError("ffmpeg 切音频失败")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="music_raw.mp3")
    ap.add_argument("--length", type=float, default=20.0)
    ap.add_argument("--start", default="auto")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    if str(args.start) == "auto":
        start = window_score(onset_envelope(decode(src)), args.length)
        print(f"自动选窗 -> 起点 {start:.2f}s（能量密度 × 节奏清晰度最高）")
    else:
        start = float(args.start)

    dst = outdir / f"music_{int(args.length)}s.mp3"
    cut(src, dst, start, args.length)

    env = onset_envelope(decode(dst))
    bpm, phase, _ = coarse_grid(env)
    period = ENV_FPS * 60.0 / bpm
    phase = refine_phase(env, period, phase)
    bpm, phase = fine_grid(env, bpm, phase)
    period = ENV_FPS * 60.0 / bpm
    phase = refine_phase(env, period, phase)

    frac, med, nbeats = quality(env, period, phase)
    beat = period / ENV_FPS
    offset = phase / ENV_FPS

    grid = {
        "bpm": round(bpm, 3),
        "beat_seconds": round(beat, 6),
        "offset_seconds": round(offset, 6),
        "slice_start": round(start, 4),
        "slice_length": args.length,
        "n_beats": nbeats,
        "beats_hit_ratio": round(frac, 3),
        "median_peak_lag_ms": round(med, 1),
        "src": dst.name,
    }
    (outdir / "beat.json").write_text(json.dumps(grid, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(json.dumps(grid, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
