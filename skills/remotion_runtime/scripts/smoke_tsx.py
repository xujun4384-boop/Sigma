# -*- coding: utf-8 -*-
"""开发自检：不走 LLM，用一段手写画面验证「注册表 → 编译 → 闸门 → 渲染」整条链路。

用法：python scripts/smoke_tsx.py
"""
import json
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent.parent
SKILLS = RUNTIME.parent
sys.path.insert(0, str(SKILLS / "lyric_mv" / "scripts"))

import remotion_scenes as rs  # noqa: E402

W = RUNTIME / "out" / "_smoke"
PARTS = W / "parts"

TSX = r"""import React from 'react';
import {AbsoluteFill} from 'remotion';
import {useE} from '../../engine/context';

export const META = {1: {bg: '#0b1a2a'}, 2: {bg: '#241026'}};

export const Shot1: React.FC = () => {
  const e = useE();
  const bob = Math.sin(e.t * 1.6) * 26;
  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${e.W} ${e.H}`} width={e.W} height={e.H}>
        <defs>
          <linearGradient id="sm1" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0d2133" />
            <stop offset="55%" stopColor="#175b6b" />
            <stop offset="100%" stopColor="#f0b070" />
          </linearGradient>
        </defs>
        <rect width={e.W} height={e.H} fill="url(#sm1)" />
        <circle cx={e.W * 0.5} cy={e.H * 0.58 + bob} r={150} fill="#ffe2a8" opacity={0.9} />
        <rect x={0} y={e.H * 0.72} width={e.W} height={e.H * 0.28} fill="#08303c" opacity={0.5} />
      </svg>
    </AbsoluteFill>
  );
};

export const Shot2: React.FC = () => {
  const e = useE();
  const p = e.shotU;
  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${e.W} ${e.H}`} width={e.W} height={e.H}>
        <rect width={e.W} height={e.H} fill="#241026" />
        <circle cx={e.W * (0.2 + 0.6 * p)} cy={e.H * 0.6} r={90} fill="#e98a5a" />
      </svg>
    </AbsoluteFill>
  );
};
"""

MANIFEST = {
    "shot-1": {"key": "shot-1", "file": "shots-b1.tsx", "export": "Shot1", "index": 1, "t": 3.0},
    "shot-2": {"key": "shot-2", "file": "shots-b1.tsx", "export": "Shot2", "index": 2, "t": 16.0},
}


def main() -> int:
    props = json.loads((RUNTIME / "demo-props.json").read_text(encoding="utf-8"))
    tl = props["timeline"]
    tl["duration"] = 20.0
    tl["lines"] = [l for l in tl["lines"] if l["start"] < 19.0]
    plan = {
        "lyricStyle": "band",
        "chrome": {"section": "zh", "sectionAt": "top-left", "progress": "top"},
        "shots": [
            {"start": 0.0, "end": 10.0, "scene": "shot-1"},
            {"start": 10.0, "end": 20.0, "scene": "shot-2"},
        ],
    }

    PARTS.mkdir(parents=True, exist_ok=True)
    (PARTS / "shots-b1.tsx").write_text(TSX, encoding="utf-8")
    (PARTS / "registry.json").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=2), encoding="utf-8")
    (W / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    (W / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (W / "render-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    ok, out = rs.gate(W, tl, plan, [3.0, 12.0, 16.0], MANIFEST)
    print(("GATE OK" if ok else "GATE FAIL"))
    if out:
        print(out[:1200])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
