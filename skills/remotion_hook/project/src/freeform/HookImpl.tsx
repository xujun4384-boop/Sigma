import React from 'react';
import {AbsoluteFill} from 'remotion';
import {FreeformProps} from './types';

// 占位实现：自由发挥失败时保持工程可编译；每次生成会覆盖本文件。
export const GeneratedHook: React.FC<FreeformProps> = ({text}) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#04060c',
        color: '#f5f8ff',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 64,
        fontFamily: '"Microsoft YaHei", sans-serif',
      }}
    >
      {text}
    </AbsoluteFill>
  );
};
