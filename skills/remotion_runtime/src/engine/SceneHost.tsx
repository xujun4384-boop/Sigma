import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {EngineProps} from '../types';
import {REGISTRY} from '../scenes/registry';
import {EngineProvider} from './context';
import {SceneBoundary} from './ErrorBoundary';
import {isDark} from './theme';
import {buildE, pickNode} from './useE';

const Fallback: React.FC<{width: number; height: number}> = ({width, height}) => (
  <AbsoluteFill style={{backgroundColor: '#0b0d16'}}>
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <rect width={width} height={height} fill="#0b0d16" />
    </svg>
  </AbsoluteFill>
);

/** 世界层：按时间选当前镜头/卡，把 e 注入给画面组件；崩溃只降级当前镜头 */
export const SceneHost: React.FC<EngineProps & {width: number; height: number; fps: number}> = ({
  timeline,
  plan,
  width,
  height,
  fps,
  strict,
}) => {
  const frame = useCurrentFrame();
  const {fps: vfps} = useVideoConfig();
  const {node} = pickNode(frame / (fps || vfps), timeline, plan);
  const entry = node.sceneId ? REGISTRY[node.sceneId] : undefined;
  const Comp = entry?.comp;
  const dark = entry?.bg ? !isDark(entry.bg) : true;
  const e = buildE({frame, timeline, plan, fps: fps || vfps, width, height, dark});

  if (typeof window !== 'undefined') window.__mvFrame = frame;

  return (
    <EngineProvider value={e}>
      <SceneBoundary
        key={`${node.sceneId ?? 'none'}-${node.shotIndex}`}
        scene={node.sceneId ?? 'none'}
        strict={strict}
        fallback={<Fallback width={width} height={height} />}
      >
        {Comp ? <Comp /> : <Fallback width={width} height={height} />}
      </SceneBoundary>
    </EngineProvider>
  );
};
