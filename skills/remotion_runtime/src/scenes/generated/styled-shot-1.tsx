import React from 'react';
import { useE } from '../../engine/context';

export const BG = '#F2EBDD';
export const META = { 1: { bg: '#F2EBDD' } };

const INK = '#1A1712';
const STAIR_A = '#E7DDC8';
const STAIR_B = '#DCD1B8';
const RED = '#D9412C';
const PAPER2 = '#FFFDF7';

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const lerp = (a: number, b: number, x: number) => a + (b - a) * x;
const easeOut2 = (x: number) => 1 - (1 - x) * (1 - x);
const easeIO = (x: number) => (x < 0.5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2);
const backOut = (x: number) => {
  const c = 1.9;
  const p = x - 1;
  return 1 + (c + 1) * p * p * p + c * p * p;
};

export const Shot1: React.FC = () => {
  const e = useE();
  const t = e.t;

  /* ---------- 冲刺 ---------- */
  const pDash = clamp01((t - 0.05) / 0.95);
  const sDash = 1 - Math.pow(1 - pDash, 2.4);

  /* ---------- 刹车 ---------- */
  const brakeP = clamp01((t - 0.98) / 0.42);
  const brakeOffset = 46 * Math.sin(Math.PI * Math.min(1, brakeP) * 0.75);
  const lean = 14 * clamp01(t / 0.22) + 16 * easeOut2(brakeP);

  const fx = lerp(620, 1355, sDash) + brakeOffset;
  const fy = lerp(880, 520, sDash) - Math.sin(Math.PI * sDash) * 70;

  /* ---------- 速度线强度 ---------- */
  const speedF = clamp01(1 - (t - 0.95) / 0.3);

  /* ---------- 刹车痕 ---------- */
  const skidP = clamp01((t - 1.04) / 0.34);

  /* ---------- 问号气泡 ---------- */
  const popP = clamp01((t - 1.38) / 0.34);
  const popS = popP <= 0 ? 0 : Math.max(0, backOut(popP));
  const popO = clamp01(popP * 5);

  /* ---------- 镜头收进右侧 ---------- */
  const zoomP = clamp01((t - 1.82) / 0.6);
  const z = easeIO(zoomP);
  const sc = lerp(1, 0.52, z);
  const tx = lerp(0, 1920 - 1920 * 0.52 - 88, z);
  const ty = lerp(0, (1080 - 1080 * 0.52) / 2, z);

  const titleO = clamp01((t - 2.02) / 0.34);

  /* ---------- 火柴人局部姿态 ---------- */
  const runAmt = 1 - clamp01((t - 0.98) / 0.25);
  const sw = Math.sin(t * 17) * runAmt;

  /* ---------- 头世界坐标 ---------- */
  const lr = (lean * Math.PI) / 180;
  const headX = fx + 14 * Math.cos(lr) + 154 * Math.sin(lr);
  const headY = fy + 14 * Math.sin(lr) - 154 * Math.cos(lr);

  const bx = headX + 62;
  const by = headY - 108 + Math.sin(t * 6) * 5;

  const stairs = [0, 1, 2, 3, 4].map((i) => ({
    i,
    x: 500 + i * 190,
    y: 880 - i * 90,
  }));

  const DX = 0.893;
  const DY = -0.45;

  return (
    <svg viewBox="0 0 1920 1080" width="100%" height="100%" style={{ display: 'block' }}>
      <defs>
        <pattern id="s1dots" width="20" height="20" patternUnits="userSpaceOnUse">
          <circle cx="4" cy="4" r="2.1" fill={INK} opacity="0.10" />
        </pattern>
        <filter id="s1soft" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="0" />
        </filter>
      </defs>

      <rect x="0" y="0" width="1920" height="1080" fill={BG} />

      <g transform={`translate(${tx} ${ty}) scale(${sc})`}>
        {/* 纸面 + 网点质感 */}
        <rect x="0" y="0" width="1920" height="1080" fill={BG} />
        <rect x="0" y="0" width="1920" height="1080" fill="url(#s1dots)" />

        {/* 背景流动墨线 */}
        {Array.from({ length: 9 }).map((_, k) => {
          const yy = 96 + k * 116;
          const span = 250 + (k % 3) * 90;
          const xx = ((t * 1500 + k * 431) % (1920 + span)) - span;
          return (
            <line
              key={`bg${k}`}
              x1={xx}
              y1={yy}
              x2={xx + span}
              y2={yy}
              stroke={INK}
              strokeWidth={3}
              strokeLinecap="round"
              opacity={0.075}
            />
          );
        })}

        {/* 台阶 */}
        {stairs.map((s) => (
          <rect
            key={`st${s.i}`}
            x={s.x}
            y={s.y}
            width={190}
            height={1080 - s.y}
            fill={s.i % 2 === 0 ? STAIR_A : STAIR_B}
            stroke={INK}
            strokeWidth={7}
          />
        ))}

        {/* 第五级强调线 */}
        <line
          x1={1262}
          y1={520}
          x2={1448}
          y2={520}
          stroke={RED}
          strokeWidth={11}
          strokeLinecap="round"
        />

        {/* 刹车痕 */}
        {Array.from({ length: 4 }).map((_, k) => {
          const yy = 514 + k * 7;
          const len = (56 + k * 26) * skidP;
          return (
            <line
              key={`sk${k}`}
              x1={1392 - k * 14}
              y1={yy}
              x2={1392 - k * 14 - len}
              y2={yy}
              stroke={INK}
              strokeWidth={7 - k * 1.1}
              strokeLinecap="round"
              opacity={0.75 * skidP}
            />
          );
        })}

        {/* 速度线拖尾 */}
        {speedF > 0.02 &&
          Array.from({ length: 7 }).map((_, k) => {
            const perp = (k - 3) * 26;
            const sx = fx + 0.45 * perp - DX * 34;
            const sy = fy + 0.893 * perp + 0.45 * 34;
            const flick = 0.62 + 0.48 * Math.abs(Math.sin(t * 19 + k * 2.1));
            const len = (74 + ((k * 41) % 64)) * speedF * flick;
            return (
              <line
                key={`sp${k}`}
                x1={sx}
                y1={sy}
                x2={sx - DX * len}
                y2={sy + 0.45 * len}
                stroke={INK}
                strokeWidth={7 - (k % 3)}
                strokeLinecap="round"
                opacity={0.6 * speedF}
              />
            );
          })}

        {/* 火柴人 */}
        <g transform={`translate(${fx} ${fy}) rotate(${lean})`}>
          <line
            x1={0}
            y1={-66}
            x2={-32 + sw * 22}
            y2={-4}
            stroke={INK}
            strokeWidth={12}
            strokeLinecap="round"
          />
          <line
            x1={2}
            y1={-66}
            x2={38 - sw * 22}
            y2={-12}
            stroke={INK}
            strokeWidth={12}
            strokeLinecap="round"
          />
          <line
            x1={0}
            y1={-66}
            x2={10}
            y2={-128}
            stroke={INK}
            strokeWidth={13}
            strokeLinecap="round"
          />
          <line
            x1={8}
            y1={-120}
            x2={-34 - sw * 18}
            y2={-76}
            stroke={INK}
            strokeWidth={11}
            strokeLinecap="round"
          />
          <line
            x1={8}
            y1={-120}
            x2={48 + sw * 18}
            y2={-112}
            stroke={INK}
            strokeWidth={11}
            strokeLinecap="round"
          />
          <circle cx={14} cy={-154} r={24} fill={INK} />
        </g>

        {/* 问号气泡 */}
        <g
          transform={`translate(${bx} ${by}) scale(${popS})`}
          opacity={popO}
        >
          <path
            d="M -24 46 L -62 100 L 2 64 Z"
            fill={PAPER2}
            stroke={INK}
            strokeWidth={8}
            strokeLinejoin="round"
          />
          <circle r={62} fill={PAPER2} stroke={INK} strokeWidth={9} />
          <path
            d="M -17 -18 C -17 -42, 17 -42, 17 -18 C 17 -3, 0 -1, 0 12"
            fill="none"
            stroke={RED}
            strokeWidth={12}
            strokeLinecap="round"
          />
          <circle cx={0} cy={31} r={8} fill={RED} />
        </g>

        {/* 分格边框 */}
        <rect
          x={10}
          y={10}
          width={1900}
          height={1070}
          fill="none"
          stroke={INK}
          strokeWidth={13}
        />
      </g>

      {/* 左侧大标题占位 */}
      <g opacity={titleO}>
        <rect x={110} y={328} width={122} height={14} rx={7} fill={RED} opacity={0.78} />
        <rect x={110} y={392} width={720} height={46} rx={10} fill={INK} opacity={0.14} />
        <rect x={110} y={470} width={560} height={46} rx={10} fill={INK} opacity={0.12} />
        <rect x={110} y={548} width={402} height={46} rx={10} fill={INK} opacity={0.1} />
        <rect x={110} y={644} width={230} height={12} rx={6} fill={INK} opacity={0.09} />
      </g>
    </svg>
  );
};