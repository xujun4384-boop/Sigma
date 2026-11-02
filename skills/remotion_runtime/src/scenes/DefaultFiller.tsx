import React from 'react';
import {AbsoluteFill} from 'remotion';

/** 引擎自带的兜底画面：歌词空档、卡片缺失时用，保证不会出现黑帧 */
export const DefaultFiller: React.FC = () => (
  <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 38%, #18203a 0%, #0b0d16 62%, #05060a 100%)'}} />
);
