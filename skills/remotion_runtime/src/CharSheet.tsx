import React from 'react';
import {AbsoluteFill} from 'remotion';
import {CHAR_REGISTRY} from './scenes/charRegistry';

/**
 * 定妆照：同一角色在若干「关节/视角参数」下的样子，横排成一张对照图。
 *
 * 它不只是看「是不是人」，还看**参数有没有真的接上**：
 * 五格分别改了 view / pose / armL / armR / tilt / mood，如果五格长得一模一样，
 * 说明角色是个静态图，镜头里的动作就只能靠画面作者自己拼人体（会变形）。
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

export const CharSheet: React.FC<{who?: string}> = ({who = 'hero'}) => {
  const C = CHAR_REGISTRY[who] as unknown as React.ComponentType<AnyProps> | undefined;
  const ground = 950;
  const scale = 1.62; // 角色本地高约 430 → 约 700px
  const cellW = 1920 / CELLS.length;

  return (
    <AbsoluteFill style={{background: 'linear-gradient(180deg,#f6f2ea 0%,#e6dfd2 62%,#cfc7b8 100%)'}}>
      <svg viewBox="0 0 1920 1080" width={1920} height={1080}>
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
                <text
                  x={cx}
                  y={ground - 300}
                  textAnchor="middle"
                  fontSize={28}
                  fill="#8a7f6d"
                  fontFamily="sans-serif"
                >
                  还没有角色
                </text>
              )}
              <text
                x={cx}
                y={ground + 48}
                textAnchor="middle"
                fontSize={24}
                fill="#6f6555"
                fontFamily="sans-serif"
              >
                {cell.label}
              </text>
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};
