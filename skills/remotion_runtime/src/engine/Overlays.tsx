import React from 'react';
import {noise} from '@remotion/effects/noise';
import {AbsoluteFill, Solid, useCurrentFrame} from 'remotion';

/** 全局质感：胶片颗粒 + 暗角。与画面内容无关，任何风格都叠（种子跟帧走，保证可复现） */
export const Overlays: React.FC<{width: number; height: number}> = ({width, height}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at 50% 46%, rgba(0,0,0,0) 42%, rgba(0,0,0,0.34) 82%, rgba(0,0,0,0.62) 100%)',
        }}
      />
      <AbsoluteFill style={{opacity: 0.055, mixBlendMode: 'overlay'}}>
        <Solid width={width} height={height} color="#808080" effects={[noise({amount: 0.8, seed: frame})]} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
