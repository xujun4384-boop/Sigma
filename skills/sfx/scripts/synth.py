"""
sfx 合成引擎：程序化音效原语 + 配方目录。

设计原则：
  - 代码只提供通用 DSP 原语（振荡器、噪声、包络、滤波、混响、限幅）；
  - 每个音效是「配方」（数据 + 一段可复现的合成函数），不依赖外部素材；
  - 选择由调用方（导演 LLM）按目录语义完成，代码不做关键词匹配或打分；
  - 所有配方使用固定随机种子，输出可复现；seed 参数只做轻微音色扰动。
"""
from __future__ import annotations

import os
import wave
from typing import Callable

import numpy as np

SAMPLE_RATE = 44100
TARGET_RMS_DB = -22.0
PEAK_CEILING = 0.95


# ── 基础 DSP ────────────────────────────────────────────────────────────
def _t(dur: float) -> np.ndarray:
    return np.arange(int(round(SAMPLE_RATE * dur)), dtype=np.float64) / SAMPLE_RATE


def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _perc(t, attack=0.003, tau=0.05):
    return (1 - np.exp(-t / attack)) * np.exp(-t / tau)


def _fade_edges(x, attack=0.003, release=0.02):
    n = len(x)
    na = min(n, max(1, int(SAMPLE_RATE * attack)))
    nr = min(n, max(1, int(SAMPLE_RATE * release)))
    x[:na] *= _smoothstep(np.linspace(0, 1, na))
    x[-nr:] *= _smoothstep(np.linspace(1, 0, nr))
    return x


def _lp(x, fc, order=2):
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
    h = 1.0 / np.sqrt(1.0 + (f / max(fc, 1e-6)) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x) * h, n)


def _hp(x, fc, order=2):
    n = len(x)
    f = np.maximum(np.fft.rfftfreq(n, 1 / SAMPLE_RATE), 1e-6)
    h = 1.0 / np.sqrt(1.0 + (max(fc, 1e-6) / f) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x) * h, n)


def _tv_bandpass(x, fc_arr, bw_oct=0.8, block=1024, hop=512):
    """时变带通：分块 FFT + Hann 重叠相加；fc 可为标量或逐样本数组。"""
    n = len(x)
    if np.ndim(fc_arr) == 0:
        fc_arr = np.full(n, float(fc_arr))
    out = np.zeros(n)
    wsum = np.zeros(n)
    w = np.hanning(block)
    freqs = np.maximum(np.fft.rfftfreq(block, 1 / SAMPLE_RATE), 1e-6)
    for s in range(0, max(1, n - block + 1), hop):
        seg = x[s:s + block]
        if len(seg) < block:
            seg = np.pad(seg, (0, block - len(seg)))
        c = max(fc_arr[min(s + block // 2, len(fc_arr) - 1)], 20.0)
        h = np.exp(-0.5 * (np.log2(freqs / c) / bw_oct) ** 2)
        y = np.fft.irfft(np.fft.rfft(seg * w) * h, block) * w
        out[s:s + block] += y
        wsum[s:s + block] += w * w
    return out / np.maximum(wsum, 1e-6)


def _make_ir(dur=0.7, decay=0.22, seed=1, cutoff=7000):
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * dur)
    t = np.arange(n) / SAMPLE_RATE
    ir = rng.standard_normal(n) * np.exp(-t / decay)
    ir = _lp(ir, cutoff, 2)
    na = max(1, int(SAMPLE_RATE * 0.002))
    ir[:na] *= np.linspace(0, 1, na)
    return ir / (np.sqrt(np.sum(ir ** 2)) + 1e-9)


def _reverb(x, wet=0.15, dur=0.7, decay=0.22, seed=1):
    ir = _make_ir(dur, decay, seed)
    n = len(x) + len(ir) - 1
    buf = np.zeros(n)
    buf[:len(x)] = x
    y = np.fft.irfft(np.fft.rfft(buf, n) * np.fft.rfft(ir, n), n)
    rx = np.sqrt(np.mean(x ** 2)) + 1e-9
    ry = np.sqrt(np.mean(y ** 2)) + 1e-9
    y *= rx / ry
    return (1 - wet) * buf + wet * y


def _pan(x, pan=0.0):
    p = np.asarray(pan, dtype=np.float64)
    theta = (p + 1.0) * np.pi / 4.0
    return np.stack([x * np.cos(theta), x * np.sin(theta)], axis=1)


def _mono(x):
    return np.stack([x, x], axis=1) if x.ndim == 1 else x


def _soft_clip(x, drive=1.6):
    return np.tanh(drive * x) / np.tanh(drive)


def _finish(x, peak=0.9):
    x = _mono(x)
    x = x - x.mean(axis=0, keepdims=True)
    m = float(np.max(np.abs(x))) + 1e-9
    return x / m * min(peak, 0.98)


def _trim(x, seconds, release=0.04):
    n = min(len(x), int(SAMPLE_RATE * seconds))
    x = x[:n].copy()
    nr = min(n, max(1, int(SAMPLE_RATE * release)))
    x[-nr:] *= _smoothstep(np.linspace(1, 0, nr))[:, None]
    return x


def _add_at(buf, y, offset):
    s = int(SAMPLE_RATE * max(0.0, offset))
    end = min(len(buf), s + len(y))
    if end <= s:
        return
    if buf.ndim == 2 and y.ndim == 1:
        buf[s:end, 0] += y[:end - s]
        buf[s:end, 1] += y[:end - s]
    elif buf.ndim == 1 and y.ndim == 2:
        buf[s:end] += y[:end - s].mean(axis=1)
    else:
        buf[s:end] += y[:end - s]


def _square(freq, dur, tau=0.2, attack=0.002, glide=1.0, duty=0.5):
    t = _t(dur)
    f = freq * (glide ** (t / max(dur, 1e-6)))
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    y = np.where((ph / (2 * np.pi)) % 1.0 < duty, 1.0, -1.0)
    return _lp(y * _perc(t, attack, tau), 8500)


# ══ MG / 干净电子 ════════════════════════════════════════════════════════
def _mg_blip():
    t = _t(0.22)
    f = 1150 * np.exp(-t * 0.8)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    x = (np.sin(ph) + 0.22 * np.sin(2 * ph) * np.exp(-t / 0.03)) * _perc(t, 0.003, 0.05)
    x = _hp(x, 180)
    x = _reverb(x, 0.05, 0.35, 0.12, 11)
    x = np.concatenate([x, np.zeros(int(SAMPLE_RATE * 0.02))])
    return _finish(_fade_edges(x, 0.002, 0.015), 0.82)


def _mg_prompt():
    a = np.sin(2 * np.pi * 1046 * _t(0.14)) * _perc(_t(0.14), 0.003, 0.035)
    b = np.sin(2 * np.pi * 784 * _t(0.22)) * _perc(_t(0.22), 0.003, 0.055)
    out = np.zeros(int(SAMPLE_RATE * 0.42))
    _add_at(out, a, 0.0)
    _add_at(out, b, 0.16)
    out = _hp(out, 160)
    out = _reverb(out, 0.06, 0.4, 0.14, 12)
    return _finish(_fade_edges(out, 0.002, 0.02), 0.82)


def _mg_pop():
    t = _t(0.14)
    u = np.clip(t / 0.055, 0, 1)
    f = 330 * (1200 / 330) ** u
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    env = _perc(t, 0.0015, 0.026)
    x = (np.sin(ph) + 0.18 * np.sin(2 * ph)) * env
    rng = np.random.default_rng(21)
    x += rng.standard_normal(len(t)) * np.exp(-t / 0.0025) * 0.22
    x = _soft_clip(x, 1.3)
    x = _reverb(x, 0.08, 0.3, 0.09, 13)
    return _finish(_fade_edges(x, 0.001, 0.012), 0.85)


def _mg_click():
    t = _t(0.07)
    rng = np.random.default_rng(22)
    nz = _hp(rng.standard_normal(len(t)) * np.exp(-t / 0.0035), 1800)
    x = nz * 0.9 + np.sin(2 * np.pi * 3200 * t) * np.exp(-t / 0.004) * 0.35
    x = _reverb(x, 0.05, 0.25, 0.07, 14)
    return _finish(_fade_edges(x, 0.0008, 0.008), 0.8)


def _mg_whoosh():
    dur = 0.75
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    rng = np.random.default_rng(24)
    nz = rng.standard_normal(len(t))
    fc = 300 * np.exp(np.log(10.0) * np.sin(np.pi * u) ** 1.3)
    x = _tv_bandpass(nz, fc, 0.75) * np.sin(np.pi * u) ** 2.2
    x += _lp(nz, 420) * np.sin(np.pi * u) ** 3 * 0.35
    x = _reverb(x, 0.12, 0.6, 0.2, 16)
    pan = np.linspace(-0.75, 0.75, len(x))
    return _finish(_pan(_fade_edges(x, 0.01, 0.05), pan), 0.8)


# ══ 卡通 / 夸张 ═════════════════════════════════════════════════════════
def _cartoon_duang():
    dur = 1.25
    t = _t(dur)
    f = 68 + 210 * np.exp(-t / 0.10) + 16 * np.sin(2 * np.pi * 6.2 * t) * np.exp(-t / 0.5)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    flutter = 1 + 0.22 * np.sin(2 * np.pi * 9.5 * t + 0.8) * np.exp(-t / 0.45)
    body = np.sin(ph) * np.exp(-t / 0.36) * flutter
    body += 0.28 * np.sin(2 * ph) * np.exp(-t / 0.18)
    body += 0.18 * np.sin(3 * ph) * np.exp(-t / 0.10)
    f2 = 200 + 450 * np.exp(-t / 0.15)
    ph2 = 2 * np.pi * np.cumsum(f2) / SAMPLE_RATE
    body += 0.45 * np.sin(ph2) * np.exp(-t / 0.28) * (1 + 0.15 * np.sin(2 * np.pi * 11 * t))
    sub = 0.35 * np.sin(2 * np.pi * 54 * t) * np.exp(-t / 0.5)
    rng = np.random.default_rng(26)
    thump = _lp(rng.standard_normal(len(t)) * np.exp(-t / 0.018), 480) * 0.55
    spring = _tv_bandpass(rng.standard_normal(len(t)) * np.exp(-t / 0.5),
                          180 + 420 * np.exp(-t / 0.55), 0.45) * 0.16
    crack = _tv_bandpass(rng.standard_normal(len(t)) * np.exp(-t / 0.045), 900.0, 1.4) * 0.38
    x = _soft_clip((body + sub + thump + spring + crack) * 1.5, 1.0) * 0.72
    x = _reverb(x, 0.18, 0.95, 0.3, 18)
    return _finish(_fade_edges(x, 0.002, 0.06), 0.92)


def _cartoon_boing():
    dur = 1.0
    t = _t(dur)
    f = 140 + 260 * np.exp(-t / 0.09) + 55 * np.sin(2 * np.pi * 13 * t) * np.exp(-t / 0.45)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    flutter = 1 + 0.18 * np.sin(2 * np.pi * 10 * t + 0.5) * np.exp(-t / 0.5)
    x = np.sin(ph) * _perc(t, 0.002, 0.42) * flutter
    x += 0.50 * np.sin(2 * ph) * np.exp(-t / 0.20)
    x += 0.18 * np.sin(3 * ph) * np.exp(-t / 0.12)
    rng = np.random.default_rng(31)
    x += _tv_bandpass(rng.standard_normal(len(t)) * np.exp(-t / 0.12), 900.0, 0.8) * 0.18
    x = _soft_clip(x * 1.3, 1.0) * 0.8
    x = _reverb(x, 0.15, 0.8, 0.25, 31)
    return _finish(_fade_edges(x, 0.002, 0.05), 0.9)


def _cartoon_zip():
    dur = 0.35
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    rng = np.random.default_rng(32)
    nz = rng.standard_normal(len(t))
    fc = 700 * (6000 / 700) ** (u ** 0.8)
    x = _tv_bandpass(nz, fc, 1.0)
    env = (u ** 0.4) * (1 - u) ** 1.6
    x *= env / (np.max(env) + 1e-9)
    f = 180 * (900 / 180) ** u
    saw = 2 * ((np.cumsum(f) / SAMPLE_RATE) % 1.0) - 1
    x += saw * env * 0.18
    x = _reverb(x, 0.08, 0.35, 0.1, 32)
    pan = np.linspace(-0.45, 0.5, len(x))
    return _finish(_pan(_fade_edges(x, 0.004, 0.03), pan), 0.82)


def _cartoon_twinkle():
    dur = 0.95
    out = np.zeros(int(SAMPLE_RATE * dur))
    for f, off in ((2093, 0.0), (2637, 0.06), (3136, 0.12)):
        tt = _t(0.6)
        y = np.sin(2 * np.pi * f * tt) * _perc(tt, 0.002, 0.18)
        y += 0.3 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt / 0.08)
        _add_at(out, y, off)
    rng = np.random.default_rng(33)
    shimmer = _tv_bandpass(rng.standard_normal(len(out)) * np.exp(-_t(dur) / 0.25), 6000.0, 1.0) * 0.06
    out += shimmer
    out = _reverb(out, 0.18, 0.7, 0.25, 33)
    return _finish(_fade_edges(out, 0.002, 0.05), 0.84)


def _cartoon_bounce():
    dur = 1.0
    out = np.zeros(int(SAMPLE_RATE * dur))
    for off, amp, f0 in ((0.0, 1.0, 95), (0.30, 0.62, 120), (0.52, 0.38, 145), (0.68, 0.22, 170)):
        tt = _t(0.28)
        ff = f0 * (1 + 0.4 * np.exp(-tt / 0.03))
        ph = 2 * np.pi * np.cumsum(ff) / SAMPLE_RATE
        y = np.sin(ph) * _perc(tt, 0.002, 0.07) * amp
        y += 0.25 * np.sin(2 * np.pi * 2.2 * f0 * tt) * np.exp(-tt / 0.04) * amp
        _add_at(out, y, off)
    tt = _t(0.22)
    rubber = np.sin(2 * np.pi * (420 * np.exp(-tt / 0.1) + 180) * tt) * np.exp(-tt / 0.09) * 0.22
    _add_at(out, rubber, 0.015)
    out = _reverb(out, 0.1, 0.5, 0.15, 34)
    return _finish(_fade_edges(out, 0.002, 0.05), 0.9)


# ══ 纸质 / 手作 ═════════════════════════════════════════════════════════
def _paper_tap():
    t = _t(0.13)
    rng = np.random.default_rng(41)
    nz = _hp(rng.standard_normal(len(t)) * np.exp(-t / 0.012), 1200)
    x = nz * 0.55
    x += np.sin(2 * np.pi * 1200 * t) * np.exp(-t / 0.02) * 0.4
    x += np.sin(2 * np.pi * 300 * t) * np.exp(-t / 0.04) * 0.3
    x = _reverb(x, 0.04, 0.25, 0.07, 41)
    return _finish(_fade_edges(x, 0.001, 0.012), 0.82)


def _paper_stroke():
    dur = 0.42
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    rng = np.random.default_rng(42)
    nz = rng.standard_normal(len(t))
    x = _tv_bandpass(nz, 1000 + 700 * np.sin(np.pi * u), 0.9) * np.sin(np.pi * u) ** 0.6
    x *= 1 + 0.18 * np.sin(2 * np.pi * 75 * t)
    x += _lp(nz, 300) * 0.08
    x = _reverb(x, 0.06, 0.3, 0.08, 42)
    return _finish(_fade_edges(x, 0.01, 0.04), 0.8)


def _paper_page():
    dur = 0.55
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    rng = np.random.default_rng(43)
    nz = rng.standard_normal(len(t))
    env = np.exp(-((t - 0.10) / 0.06) ** 2) + 0.8 * np.exp(-((t - 0.28) / 0.08) ** 2)
    x = _tv_bandpass(nz, 1800 + 1200 * np.sin(np.pi * u), 1.0) * env
    x *= 1 + 0.25 * np.sin(2 * np.pi * 110 * t)
    x += _lp(nz, 260) * np.exp(-((t - 0.30) / 0.05) ** 2) * 0.15
    x = _reverb(x, 0.1, 0.4, 0.14, 43)
    return _finish(_fade_edges(x, 0.004, 0.04), 0.8)


def _paper_wood():
    t = _t(0.30)
    x = 0.7 * np.sin(2 * np.pi * 220 * t) * np.exp(-t / 0.10)
    x += 0.4 * np.sin(2 * np.pi * 580 * t) * np.exp(-t / 0.05)
    x += 0.3 * np.sin(2 * np.pi * 1200 * t) * np.exp(-t / 0.025)
    rng = np.random.default_rng(44)
    x += rng.standard_normal(len(t)) * np.exp(-t / 0.004) * 0.2
    x = _hp(x, 80)
    x = _reverb(x, 0.06, 0.3, 0.1, 44)
    return _finish(_fade_edges(x, 0.001, 0.03), 0.86)


def _paper_stamp():
    dur = 0.55
    t = _t(dur)
    f = 55 + 95 * np.exp(-t / 0.2)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    body = np.sin(ph) * np.exp(-t / 0.16) * 0.7
    mid = 0.4 * np.sin(2 * np.pi * 450 * t) * np.exp(-t / 0.06)
    rng = np.random.default_rng(45)
    pn = _tv_bandpass(rng.standard_normal(len(t)) * np.exp(-t / 0.045), 1100.0, 1.0) * 1.2
    x = _soft_clip((body + mid + pn) * 1.6, 1.0) * 0.7
    x = _reverb(x, 0.08, 0.5, 0.16, 45)
    return _finish(_fade_edges(x, 0.001, 0.04), 0.9)


# ══ 像素 / 8-bit ════════════════════════════════════════════════════════
def _pixel_coin():
    a = _square(988, 0.07, tau=0.2)
    b = _square(1319, 0.32, tau=0.16)
    out = np.zeros(int(SAMPLE_RATE * 0.46))
    _add_at(out, a, 0.0)
    _add_at(out, b, 0.09)
    out = _reverb(out, 0.04, 0.3, 0.08, 51)
    return _finish(_fade_edges(out, 0.001, 0.03), 0.84)


def _pixel_jump():
    x = _square(300, 0.20, tau=0.14, glide=3.0)
    x = _reverb(x, 0.05, 0.3, 0.08, 52)
    return _finish(_fade_edges(x, 0.002, 0.03), 0.84)


def _pixel_blip():
    out = np.zeros(int(SAMPLE_RATE * 0.16))
    _add_at(out, _square(1400, 0.06, tau=0.06), 0.0)
    _add_at(out, _square(1400, 0.05, tau=0.05) * 0.35, 0.075)
    out = _reverb(out, 0.03, 0.22, 0.06, 53)
    return _finish(_fade_edges(out, 0.001, 0.02), 0.82)


def _pixel_error():
    out = np.zeros(int(SAMPLE_RATE * 0.3))
    _add_at(out, _square(220, 0.09, tau=0.5, duty=0.3), 0.0)
    _add_at(out, _square(165, 0.16, tau=0.4, duty=0.3), 0.11)
    out = _reverb(_hp(out, 90), 0.04, 0.3, 0.08, 54)
    return _finish(_fade_edges(out, 0.001, 0.03), 0.82)


def _pixel_powerup():
    out = np.zeros(int(SAMPLE_RATE * 0.62))
    for i, f in enumerate((523, 659, 784, 1047)):
        _add_at(out, _square(f, 0.07, tau=0.7) * 0.8, i * 0.07)
    _add_at(out, _square(1047, 0.24, tau=0.3), 0.29)
    out = _reverb(out, 0.06, 0.35, 0.1, 55)
    return _finish(_fade_edges(out, 0.001, 0.03), 0.84)


# ══ 科技 / 数据 ═════════════════════════════════════════════════════════
def _tech_scan():
    dur = 0.55
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    f = 400 * (2000 / 400) ** (u ** 1.2)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    x = np.sin(ph) * np.sin(np.pi * u) ** 1.4
    rng = np.random.default_rng(61)
    nz = rng.standard_normal(len(t))
    x += _tv_bandpass(nz, 500 * (4000 / 500) ** u, 0.9) * 0.16
    _add_at(x, np.sin(2 * np.pi * 2200 * _t(0.25)) * _perc(_t(0.25), 0.002, 0.07) * 0.22, 0.42)
    x = _reverb(x, 0.12, 0.5, 0.16, 61)
    return _finish(_fade_edges(x, 0.004, 0.04), 0.84)


def _tech_data():
    dur = 0.9
    out = np.zeros(int(SAMPLE_RATE * dur))
    rng = np.random.default_rng(62)
    for _ in range(16):
        off = float(rng.uniform(0, 0.85))
        f = float(rng.uniform(1500, 5000))
        d = float(rng.uniform(0.02, 0.05))
        tt = _t(d)
        y = np.sin(2 * np.pi * f * tt) * _perc(tt, 0.001, d * 0.7) * float(rng.uniform(0.3, 0.8))
        _add_at(out, y, off)
    out += _hp(rng.standard_normal(len(out)) * 0.03, 2000)
    out = _reverb(out, 0.08, 0.4, 0.1, 62)
    return _finish(_fade_edges(out, 0.002, 0.04), 0.82)


def _tech_glitch():
    dur = 0.38
    t = _t(dur)
    seg = np.floor(t / 0.045)
    f = 300 + 900 * (seg % 2) + 180 * np.sin(2 * np.pi * 3 * t)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    tone = np.where((ph / (2 * np.pi)) % 1.0 < 0.35, 1.0, -1.0)
    rng = np.random.default_rng(63)
    x = tone * 0.45 + rng.standard_normal(len(t)) * 0.35
    x = np.round(x * 5) / 5
    x *= 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 22 * t))
    x = _reverb(_lp(x, 8000), 0.05, 0.25, 0.07, 63)
    return _finish(_fade_edges(x, 0.001, 0.02), 0.8)


def _tech_notify():
    out = np.zeros(int(SAMPLE_RATE * 0.55))
    for i, f in enumerate((880, 1175, 1568)):
        tt = _t(0.18)
        y = np.sin(2 * np.pi * f * tt) * _perc(tt, 0.002, 0.09)
        y += 0.25 * np.sin(2 * np.pi * 2 * f * tt) * np.exp(-tt / 0.05)
        _add_at(out, y, i * 0.11)
    out = _reverb(out, 0.12, 0.5, 0.16, 64)
    return _finish(_fade_edges(out, 0.002, 0.04), 0.84)


def _tech_lock():
    dur = 0.45
    t = _t(dur)
    f = 90 + 40 * np.exp(-t / 0.08)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    x = np.sin(ph) * np.exp(-t / 0.12) * 0.55
    rng = np.random.default_rng(65)
    x += rng.standard_normal(len(t)) * np.exp(-t / 0.004) * 0.4
    _add_at(x, np.sin(2 * np.pi * 1800 * _t(0.20)) * _perc(_t(0.20), 0.002, 0.05) * 0.60, 0.08)
    _add_at(x, np.sin(2 * np.pi * 600 * _t(0.10)) * _perc(_t(0.10), 0.002, 0.03) * 0.35, 0.08)
    x = _reverb(x, 0.07, 0.35, 0.1, 65)
    return _finish(_fade_edges(x, 0.001, 0.03), 0.86)


# ══ 电影感 / 冲击 ═══════════════════════════════════════════════════════
def _cinematic_impact():
    dur = 1.5
    t = _t(dur)
    f = 42 + 62 * np.exp(-t / 0.22)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    body = np.sin(ph) * np.exp(-t / 0.35)
    sub = 0.15 * np.sin(2 * np.pi * 38 * t) * np.exp(-t / 0.7)
    mid = 0.45 * np.sin(2 * np.pi * 210 * t) * np.exp(-t / 0.2)
    crack_tone = 0.22 * np.sin(2 * np.pi * 720 * t) * np.exp(-t / 0.055)
    rng = np.random.default_rng(27)
    burst = _lp(rng.standard_normal(len(t)) * np.exp(-t / 0.09), 700) * 0.5
    smack = _tv_bandpass(rng.standard_normal(len(t)) * np.exp(-t / 0.05), 1500.0, 1.3) * 1.55
    x = _soft_clip((body + sub + mid + crack_tone + burst + smack) * 1.6, 1.0) * 0.64
    x = _reverb(_hp(x, 28), 0.18, 1.0, 0.34, 19)
    return _finish(_fade_edges(x, 0.001, 0.08), 0.94)


def _cinematic_riser():
    dur = 1.7
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    rng = np.random.default_rng(28)
    nz = rng.standard_normal(len(t))
    x = _tv_bandpass(nz, 200 * np.exp(np.log(30.0) * u ** 1.35), 0.85) * u ** 2.4
    x = x / (np.max(np.abs(x)) + 1e-9)
    tone_f = 120 * (900 / 120) ** u
    x += np.sin(2 * np.pi * np.cumsum(tone_f) / SAMPLE_RATE) * (u ** 2.2) * 0.12
    x = _reverb(x, 0.1, 0.7, 0.2, 20)
    x = np.concatenate([x, np.zeros(int(SAMPLE_RATE * 0.01))])
    pan = np.sin(2 * np.pi * 0.7 * np.linspace(0, 1, len(x))) * 0.25
    return _finish(_pan(_fade_edges(x, 0.02, 0.015), pan), 0.86)


def _cinematic_subdrop():
    dur = 1.8
    t = _t(dur)
    u = np.clip(t / dur, 0, 1)
    f = 80 * (30 / 80) ** (u ** 0.7)
    ph = 2 * np.pi * np.cumsum(f) / SAMPLE_RATE
    env = _perc(t, 0.01, 0.7) * (1 - 0.25 * u)
    x = np.sin(ph) * env
    x += 0.28 * np.sin(2 * ph) * env * 0.8
    x += 0.16 * np.sin(3 * ph) * env * 0.7
    x += 0.10 * np.sin(4 * ph) * env * 0.6
    rng = np.random.default_rng(71)
    x += _lp(rng.standard_normal(len(t)) * env, 220) * 0.18
    x = _soft_clip(x * 1.4, 1.0) * 0.8
    x = _reverb(x, 0.12, 0.9, 0.3, 71)
    return _finish(_fade_edges(x, 0.005, 0.08), 0.9)


def _cinematic_hum():
    dur = 2.5
    t = _t(dur)
    lfo = 1 + 0.15 * np.sin(2 * np.pi * 0.12 * t)
    x = 0.45 * np.sin(2 * np.pi * 55 * t)
    x += 0.28 * np.sin(2 * np.pi * 82.5 * t + 0.3)
    x += 0.18 * np.sin(2 * np.pi * 110 * t + 1.1)
    x += 0.12 * np.sin(2 * np.pi * 165 * t + 2.0)
    x += 0.16 * np.sin(2 * np.pi * 220 * t + 0.7)
    x += 0.10 * np.sin(2 * np.pi * 330 * t + 1.6)
    x += 0.05 * np.sin(2 * np.pi * 440 * t + 2.4)
    rng = np.random.default_rng(72)
    x += _tv_bandpass(rng.standard_normal(len(t)), 420.0, 1.2) * 0.06
    x += _lp(rng.standard_normal(len(t)), 180) * 0.10
    x *= lfo
    x = _reverb(x, 0.12, 0.8, 0.3, 72)
    return _finish(_fade_edges(x, 0.25, 0.3), 0.7)


def _cinematic_wind():
    dur = 2.6
    t = _t(dur)
    rng = np.random.default_rng(73)
    nz = rng.standard_normal(len(t))
    fc = 600 + 240 * np.sin(2 * np.pi * 0.23 * t + 0.5)
    x = _tv_bandpass(nz, fc, 1.2)
    x *= 0.55 + 0.25 * np.sin(2 * np.pi * 0.17 * t)
    x += _lp(nz, 150) * 0.20
    x = _reverb(x, 0.1, 0.8, 0.3, 73)
    return _finish(_fade_edges(x, 0.3, 0.35), 0.72)


# ══ 目录 ════════════════════════════════════════════════════════════════
FAMILIES: dict[str, dict] = {
    "mg": {"name": "MG / 干净电子", "desc": "扁平、信息图、UI 演示"},
    "cartoon": {"name": "卡通 / 夸张", "desc": "绘本、漫画、搞笑强调"},
    "paper": {"name": "纸质 / 手作", "desc": "白板、水墨、汉字、手绘"},
    "pixel": {"name": "像素 / 8-bit", "desc": "像素风、游戏怀旧"},
    "tech": {"name": "科技 / 数据", "desc": "信息图、等距、数据演示"},
    "cinematic": {"name": "电影感 / 冲击", "desc": "开场钩子、章节冲击、氛围"},
}


def _r(rid, family, title, desc, fn: Callable, max_duration: float) -> dict:
    return {"id": rid, "family": family, "title": title, "desc": desc,
            "fn": fn, "max_duration": max_duration}


RECIPES: dict[str, dict] = {r["id"]: r for r in (
    _r("mg.blip", "mg", "哔", "最基础的电子提示音，适合数据出现、轻提示。", _mg_blip, 0.38),
    _r("mg.prompt", "mg", "哔-嘟", "两段式提示，适合状态切换、确认、流程节点。", _mg_prompt, 0.58),
    _r("mg.pop", "mg", "弹出", "短促气泡感，适合卡片、标签、图标弹出。", _mg_pop, 0.22),
    _r("mg.click", "mg", "轻点", "极短瞬态，适合按钮、翻页、打字、选择。", _mg_click, 0.12),
    _r("mg.whoosh", "mg", "呼啸", "扫频气流，适合溶解、擦除、场景切换。", _mg_whoosh, 1.05),

    _r("cartoon.duang", "cartoon", "Duang", "弹性低频 + 金属泛音，搞笑强调、重物落下。", _cartoon_duang, 1.80),
    _r("cartoon.boing", "cartoon", "Boing", "弹簧颤音，适合人物弹起、意外、卡通反应。", _cartoon_boing, 1.30),
    _r("cartoon.zip", "cartoon", "Zip", "快速掠过，适合角色冲刺、元素飞过。", _cartoon_zip, 0.55),
    _r("cartoon.twinkle", "cartoon", "闪亮", "三连高音铃，适合星星、灵感、魔法出现。", _cartoon_twinkle, 1.20),
    _r("cartoon.bounce", "cartoon", "弹跳", "连续四次落地，适合球、角色、节奏型动作。", _cartoon_bounce, 1.20),

    _r("paper.tap", "paper", "笔尖轻点", "铅笔/马克笔点纸，适合白板讲解的强调点。", _paper_tap, 0.20),
    _r("paper.stroke", "paper", "笔刷划过", "一笔刷过的纸感摩擦，适合手绘线条出现。", _paper_stroke, 0.55),
    _r("paper.page", "paper", "翻页", "纸张翻动 + 轻微褶皱，适合章节/页面切换。", _paper_page, 0.75),
    _r("paper.wood", "paper", "木质轻敲", "木头敲击，适合板书、印章、手工场景。", _paper_wood, 0.42),
    _r("paper.stamp", "paper", "盖章", "低频落章 + 纸面噪声，适合结论、判定。", _paper_stamp, 0.70),

    _r("pixel.coin", "pixel", "金币", "经典 8-bit 双音上行，适合得分、获得。", _pixel_coin, 0.55),
    _r("pixel.jump", "pixel", "跳跃", "方波上滑，适合角色起跳、像素动作。", _pixel_jump, 0.35),
    _r("pixel.blip", "pixel", "8-bit 提示", "短方波提示，适合菜单、选择、对话推进。", _pixel_blip, 0.22),
    _r("pixel.error", "pixel", "8-bit 错误", "下行蜂鸣，适合失败、禁止、错误反馈。", _pixel_error, 0.42),
    _r("pixel.powerup", "pixel", "能量上升", "四音琶音上行，适合升级、充能、连击。", _pixel_powerup, 0.72),

    _r("tech.scan", "tech", "扫描", "上扫音 + 数据气流，适合识别、加载、扫描。", _tech_scan, 0.75),
    _r("tech.data", "tech", "数据流", "密集高频颗粒，适合数据传输、计算、处理。", _tech_data, 1.10),
    _r("tech.glitch", "tech", "故障", "Bitcrush + 门限抖动，适合错误、干扰、赛博感。", _tech_glitch, 0.55),
    _r("tech.notify", "tech", "系统通知", "三音提示，适合消息、系统状态、提醒。", _tech_notify, 0.70),
    _r("tech.lock", "tech", "锁定确认", "低频落点 + 高音确认，适合锁定、完成、确认。", _tech_lock, 0.60),

    _r("cinematic.impact", "cinematic", "重击", "低频 Boom，适合章节开始、黑场冲击。", _cinematic_impact, 1.70),
    _r("cinematic.riser", "cinematic", "上升", "噪声上升，适合高潮/反转前的铺垫。", _cinematic_riser, 2.00),
    _r("cinematic.subdrop", "cinematic", "下潜", "低频下沉，适合悬念、失重、转场落点。", _cinematic_subdrop, 2.00),
    _r("cinematic.hum", "cinematic", "低频氛围", "可循环的低频底噪，适合紧张/科幻场景。", _cinematic_hum, 2.70),
    _r("cinematic.wind", "cinematic", "风声", "可循环的风噪，适合空镜、荒野、孤独感。", _cinematic_wind, 2.80),
)}


# ── 公开 API ────────────────────────────────────────────────────────────
def is_recipe(recipe_id: str) -> bool:
    return str(recipe_id or "").strip() in RECIPES


def get_recipe(recipe_id: str) -> dict | None:
    return RECIPES.get(str(recipe_id or "").strip())


def catalog() -> list[dict]:
    return [
        {"id": r["id"], "family": r["family"], "title": r["title"],
         "desc": r["desc"], "duration": r["max_duration"]}
        for r in RECIPES.values()
    ]


def catalog_menu() -> str:
    """给 LLM 看的紧凑目录：按家族分组，列出 id 与用途。"""
    lines = []
    for fid, fam in FAMILIES.items():
        items = [f"`{r['id']}` {r['title']}（{r['desc']}）"
                 for r in RECIPES.values() if r["family"] == fid]
        lines.append(f"- **{fam['name']}**（{fam['desc']}）：" + "；".join(items))
    return "\n".join(lines)


def _pitch_shift(x: np.ndarray, semitones: float) -> np.ndarray:
    if abs(semitones) < 1e-3:
        return x
    rate = float(2.0 ** (semitones / 12.0))
    n = len(x)
    n_out = max(1, int(round(n / rate)))
    src = np.arange(n, dtype=np.float64)
    dst = np.arange(n_out, dtype=np.float64) * rate
    return np.stack([np.interp(dst, src, x[:, c]) for c in range(x.shape[1])], axis=1)


def _tilt(x: np.ndarray, brightness: float) -> np.ndarray:
    """brightness ∈ [-1, 1]：负值变暗，正值提亮。"""
    if abs(brightness) < 1e-3:
        return x
    out = x.copy()
    for c in range(x.shape[1]):
        high = _hp(x[:, c], 1800, 1)
        out[:, c] = x[:, c] + brightness * high * 0.6
    return out


def render(recipe_id: str, params: dict | None = None) -> np.ndarray:
    """按配方渲染一段立体声 float32（峰值 ≤ 1），并统一响度。"""
    rec = RECIPES.get(str(recipe_id or "").strip())
    if not rec:
        raise KeyError(f"未知音效配方: {recipe_id}")
    params = params or {}
    x = _mono(rec["fn"]()).astype(np.float64)

    # 参数：pitch（半音）、brightness（-1~1）、seed（轻微音色扰动）
    try:
        pitch = float(params.get("pitch", 0) or 0)
    except (TypeError, ValueError):
        pitch = 0.0
    try:
        brightness = float(params.get("brightness", 0) or 0)
    except (TypeError, ValueError):
        brightness = 0.0
    pitch = max(-12.0, min(12.0, pitch))
    brightness = max(-1.0, min(1.0, brightness))

    seed = params.get("seed")
    if seed is not None:
        try:
            rng = np.random.default_rng(int(seed))
            pitch += float(rng.uniform(-0.5, 0.5))
            brightness += float(rng.uniform(-0.08, 0.08))
        except (TypeError, ValueError):
            pass

    x = _pitch_shift(x, pitch)
    x = _tilt(x, brightness)
    x = _trim(x, rec["max_duration"])
    x = _finish(x, 0.95)

    # 统一到目标 RMS，并做峰值保护
    rms = float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    gain = 10 ** ((TARGET_RMS_DB - 20 * np.log10(rms)) / 20.0)
    x = x * gain
    peak = float(np.max(np.abs(x))) + 1e-9
    if peak > PEAK_CEILING:
        x = x * (PEAK_CEILING / peak)
    return x.astype(np.float32)


def write_wav(path: str, x: np.ndarray) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    y = np.clip(x, -1.0, 1.0)
    pcm = (y * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return path
