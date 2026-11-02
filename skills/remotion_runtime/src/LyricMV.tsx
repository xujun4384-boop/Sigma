import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EngineProps} from './types';
import {Chrome} from './engine/Chrome';
import {LyricLayer} from './engine/LyricLayer';
import {Overlays} from './engine/Overlays';
import {SceneHost} from './engine/SceneHost';
import {isDark} from './engine/theme';
import {pickNode} from './engine/useE';
import {REGISTRY} from './scenes/registry';

/**
 * 一条 MV 的合成体：
 *   世界层（LLM 画的镜头） → 引擎叠加（歌词带蒙版/歌词/KTV/章节/进度/颗粒/暗角）
 * 画面代码永远碰不到歌词与卡点，引擎永远不碰画面内容。
 */
export const LyricMV: React.FC<EngineProps> = ({timeline, plan, fps, width, height, strict}) => {
  const frame = useCurrentFrame();
  const cfg = useVideoConfig();
  const w = width || cfg.width;
  const h = height || cfg.height;
  const f = fps || cfg.fps;
  const t = frame / f;

  const {node} = pickNode(t, timeline, plan);
  const entry = node.sceneId ? REGISTRY[node.sceneId] : undefined;
  const dark = plan.palette?.mode === 'light' ? false : entry?.bg ? isDark(entry.bg) : true;

  if (typeof window !== 'undefined') window.__mvFrame = frame;

  return (
    <AbsoluteFill style={{backgroundColor: '#05060a'}}>
      <SceneHost timeline={timeline} plan={plan} width={w} height={h} fps={f} strict={strict} />
      {!plan.plain ? <LyricLayer timeline={timeline} plan={plan} width={w} height={h} dark={dark} /> : null}
      <Chrome timeline={timeline} plan={plan} width={w} height={h} dark={dark} />
      <Overlays width={w} height={h} />
    </AbsoluteFill>
  );
};
