import React from 'react';
import {AbsoluteFill} from 'remotion';
import {CHAR_REGISTRY} from './scenes/charRegistry';

/**
 * 定妆照。
 *
 * 单个角色：五格参数网格，验证 view/pose/armL/armR/tilt/mood 有没有真的接进绘制。
 * 多个角色：每个角色一格正面站姿，横向排开，用来确认「是不是不同的人」。
 *
 * 不参与成片，只在角色阶段渲染单帧供审阅。
 */
type AnyProps = Record<string, unknown>;

const CELLS: {label: string; props: AnyProps}[] = [
  {label: '正面 / 站', props: {view: 'front', pose: 'stand'}},
  {label: '侧面 / 站', props: {view: 'side', pose: 'stand'}},
  {label: '背面 / 站', props: {view: 'back', pose: 'stand'}},
  {
    label: '坐姿 / 伸手',
    props: {view: 'front', pose: 'sit', armL: [-40, -80], armR: [-54, -22], headTurn: 6},
  },
  {label: '倾斜 / 头晕', props: {view: 'front', pose: 'stand', tilt: 12, mood: 'dizzy'}},
];

const SINGLE: React.FC<{who: string}> = ({who}) => {
  const C = CHAR_REGISTRY[who] as unknown as React.ComponentType<AnyProps> | undefined;
  const ground = 950;
  const scale = 1.62;
  const cellW = 1920 / CELLS.length;

  return (
    <>
      <text x={40} y={52} fontSize={22} fill="#8a7f6d" fontFamily="sans-serif">
        定妆参数网格：五格应当是同一个人的不同视角 / 姿态；若五格一样，说明参数没有接进绘制
      </text>
      {CELLS.map((cell, i) => {
        const cx = cellW * (i + 0.5);
        return (
          <g key={cell.label}>
            <line
              x1={cx - cellW * 0.42}
              y1={ground}
              x2={cx + cellW * 0.42}
              y2={ground}
              stroke="#b9ad9a"
              strokeWidth={1.5}
              strokeDasharray="6 8"
              opacity={0.7}
            />
            {C ? (
              <g transform={`translate(${cx} ${ground}) scale(${scale})`}>
                <C {...cell.props} />
              </g>
            ) : (
              <text x={cx} y={ground - 300} textAnchor="middle" fontSize={28}
                fill="#8a7f6d" fontFamily="sans-serif">
                还没有角色
              </text>
            )}
            <text x={cx} y={ground + 48} textAnchor="middle" fontSize={24}
              fill="#6f6555" fontFamily="sans-serif">
              {cell.label}
            </text>
          </g>
        );
      })}
    </>
  );
};

const GROUP: React.FC<{roles: string[]}> = ({roles}) => {
  const ground = 930;
  const cellW = 1920 / Math.max(1, roles.length);
  const scale = roles.length > 2 ? 1.15 : 1.45;

  return (
    <>
      <text x={40} y={52} fontSize={22} fill="#8a7f6d" fontFamily="sans-serif">
        整组定妆：每个角色一格正面站姿。确认他们是不是不同的人，再进入镜头。
      </text>
      {roles.map((role, i) => {
        const C = CHAR_REGISTRY[role] as unknown as React.ComponentType<AnyProps> | undefined;
        const cx = cellW * (i + 0.5);
        return (
          <g key={role}>
            <line x1={cx - cellW * 0.36} y1={ground} x2={cx + cellW * 0.36} y2={ground}
              stroke="#b9ad9a" strokeWidth={1.5} strokeDasharray="6 8" opacity={0.7} />
            {C ? (
              <g transform={`translate(${cx} ${ground}) scale(${scale})`}>
                <C view="front" pose="stand" />
              </g>
            ) : (
              <text x={cx} y={ground - 320} textAnchor="middle" fontSize={26}
                fill="#8a7f6d" fontFamily="sans-serif">
                缺少角色组件
              </text>
            )}
            <text x={cx} y={ground + 52} textAnchor="middle" fontSize={26}
              fill="#6f6555" fontFamily="sans-serif">
              {role}
            </text>
          </g>
        );
      })}
    </>
  );
};

export const CharSheet: React.FC<{who?: string}> = ({who = 'hero'}) => {
  const roles = (who || 'hero').split(',').map(s => s.trim()).filter(Boolean);
  return (
    <AbsoluteFill style={{background: 'linear-gradient(180deg,#f6f2ea 0%,#e6dfd2 62%,#cfc7b8 100%)'}}>
      <svg viewBox="0 0 1920 1080" width={1920} height={1080}>
        {roles.length > 1 ? <GROUP roles={roles} /> : <SINGLE who={roles[0] || 'hero'} />}
      </svg>
    </AbsoluteFill>
  );
};
