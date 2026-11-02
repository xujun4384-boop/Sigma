# -*- coding: utf-8 -*-
"""开发自检：用假模型跑 remotion_scenes.generate_story，验证「分批写盘 → 注册表 → 闸门」。

用法：python scripts/smoke_generate.py
"""
import json
import sys
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent.parent
SKILLS = RUNTIME.parent
sys.path.insert(0, str(SKILLS / "lyric_mv" / "scripts"))

import remotion_scenes as rs  # noqa: E402

W = RUNTIME / "out" / "_smoke2"

TSX = r"""import React from 'react';
import {AbsoluteFill} from 'remotion';
import {useE} from '../../engine/context';

export const META = {1: {bg: '#0b1a2a'}, 2: {bg: '#241026'}, 3: {bg: '#102a1c'}};

const Sky: React.FC<{a: string; b: string}> = ({a, b}) => {
  const e = useE();
  return (
    <svg viewBox={`0 0 ${e.W} ${e.H}`} width={e.W} height={e.H}>
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={a} />
          <stop offset="100%" stopColor={b} />
        </linearGradient>
      </defs>
      <rect width={e.W} height={e.H} fill="url(#g)" />
      <circle cx={e.W * 0.5} cy={e.H * (0.62 - 0.05 * e.shotU)} r={140} fill="#ffe2a8" opacity={0.9} />
    </svg>
  );
};

export const Shot1: React.FC = () => (
  <AbsoluteFill><Sky a="#0d2133" b="#175b6b" /></AbsoluteFill>
);
export const Shot2: React.FC = () => (
  <AbsoluteFill><Sky a="#241026" b="#7a3f4f" /></AbsoluteFill>
);
export const Shot3: React.FC = () => (
  <AbsoluteFill><Sky a="#102a1c" b="#2d6b55" /></AbsoluteFill>
);
"""


def main() -> int:
    props = json.loads((RUNTIME / "demo-props.json").read_text(encoding="utf-8"))
    tl = props["timeline"]
    tl["duration"] = 18.0
    tl["lines"] = [l for l in tl["lines"] if l["start"] < 17.0]
    plan = {"lyricStyle": "band", "chrome": {"section": "zh", "sectionAt": "top-left", "progress": "top"}}
    story = {"shots": [
        {"id": "s1", "start": 0.0, "end": 6.0, "size": "全景", "action": "环礁航拍"},
        {"id": "s2", "start": 6.0, "end": 12.0, "size": "中景", "action": "水飞降落"},
        {"id": "s3", "start": 12.0, "end": 18.0, "size": "近景", "action": "栈桥搀扶"},
    ]}

    W.mkdir(parents=True, exist_ok=True)
    (W / "parts").mkdir(exist_ok=True)
    (W / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
    (W / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    calls = {"n": 0}

    def fake_llm(system, ctx, cfg, meta_label=""):
        calls["n"] += 1
        assert "{API}" not in system and "Shot<镜头编号>" in system
        return "```tsx\n" + TSX + "\n```"

    ok, note, path = rs.generate_story(
        W, tl, plan, story, {}, fake_llm, lambda *a, **k: None, force=True)
    print(f"generate_story → ok={ok} note={note} calls={calls['n']} path={path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
