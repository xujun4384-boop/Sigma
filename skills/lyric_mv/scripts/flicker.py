# -*- coding: utf-8 -*-
"""客观测"闪不闪"：逐帧全画面平均亮度，再看帧间跳变。

闪烁 = 大面积亮度在帧间反复跳。所以：
  · 逐帧平均亮度序列 -> 帧间差分的分布
  · p99 / max 越小越稳；出现个别大跳变通常是硬切（正常）
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

GW, GH = 160, 90


def frames_gray(vid):
    p = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", str(vid), "-vf", f"scale={GW}:{GH}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    a = np.frombuffer(p.stdout, dtype=np.uint8)
    n = a.size // (GW * GH)
    return a[:n * GW * GH].reshape(n, GH, GW).astype(np.float32)


def main():
    here = Path(__file__).resolve().parents[1]
    vid = here / (sys.argv[1] if len(sys.argv) > 1 else "school_mv.mp4")
    f = frames_gray(vid)
    lum = f.reshape(f.shape[0], -1).mean(axis=1)
    d = np.abs(np.diff(lum))
    print(f"帧数 {len(lum)} | 平均亮度 {lum.mean():.1f} (min {lum.min():.1f} / max {lum.max():.1f})")
    print("帧间平均亮度的跳变：")
    for q in (50, 90, 99, 99.9):
        print(f"  p{q:<5} {np.percentile(d, q):6.2f}")
    print(f"  max   {d.max():6.2f}  (出现在第 {int(np.argmax(d))} 帧，多为硬切/段落切换)")
    big = int((d > 8).sum())
    print(f"  跳变 >8 的帧数：{big} / {len(d)}  ({big / len(d) * 100:.2f}%)  <- 超过 8 基本就是整幅换背景")
    return 0


if __name__ == "__main__":
    sys.exit(main())
