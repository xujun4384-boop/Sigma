import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';

export const BG = '#101B46';
export const META = {22: {bg: '#101B46'}};

const C = {
  ink: '#101B46',
  deep: '#172554',
  blue: '#2878F0',
  cyan: '#37E6E6',
  cyan2: '#A5FFFF',
  yellow: '#FFD93D',
  gold: '#F4C95D',
  white: '#F4FBFF',
  violet: '#5138A8',
  pink: '#FF5C8A',
  green: '#44D17A',
};

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const ease = (v: number) => {
  const x = clamp01(v);
  return x * x * (3 - 2 * x);
};
const out = (v: number) => 1 - Math.pow(1 - clamp01(v), 3);

function PixelSpark({x, y, s, color, opacity = 1}: {
  x: number; y: number; s: number; color: string; opacity?: number;
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} fill={color} opacity={opacity}>
      <rect x={-3} y={-15} width={6} height={30} rx={1} />
      <rect x={-15} y={-3} width={30} height={6} rx={1} />
      <rect x={-6} y={-6} width={12} height={12} />
    </g>
  );
}

function Controller({x, y, s = 1, flip = false, glow = false}: {
  x: number; y: number; s?: number; flip?: boolean; glow?: boolean;
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${flip ? -s : s} ${s})`}>
      {glow && <ellipse cx={0} cy={5} rx={80} ry={50} fill={C.cyan} opacity={0.15} />}
      <path
        d="M-58,-18 Q-75,-15 -78,7 L-82,29 Q-84,46 -69,46 Q-58,46 -48,28 L-34,17 L34,17 L48,28 Q58,46 69,46 Q84,46 82,29 L78,7 Q75,-15 58,-18 Z"
        fill="#182440"
        stroke={glow ? C.cyan2 : '#89A4C8'}
        strokeWidth={5}
      />
      <path d="M-57,-13 Q0,-27 57,-13" fill="none" stroke="#334A70" strokeWidth={4} />
      <rect x={-52} y={-7} width={12} height={34} rx={3} fill="#DCEAFF" />
      <rect x={-63} y={4} width={34} height={12} rx={3} fill="#DCEAFF" />
      <circle cx={43} cy={0} r={7} fill={C.yellow} />
      <circle cx={59} cy={13} r={7} fill={C.pink} />
      <circle cx={27} cy={14} r={7} fill={C.green} />
      <rect x={-10} y={-5} width={20} height={8} rx={4} fill={C.cyan} />
    </g>
  );
}

export function Shot22() {
  const e = useE();
  const t = e.shotT;
  const u = e.shotU;
  const open = out((t - 0.2) / 1.25);
  const road = out((t - 0.75) / 2.0);
  const ready = out((t - 1.25) / 1.0);
  const advance = ease((t - 2.0) / 5.0);
  const beat = 0.5 + 0.5 * Math.sin(t * Math.PI * 4.33);
  const zoom = 1 + 0.025 * ease(u);
  const drift = 12 * advance;

  const buildings = [
    [1080, 445, 54, 144], [1140, 405, 70, 184], [1218, 466, 46, 123],
    [1270, 365, 78, 224], [1356, 432, 52, 157], [1415, 390, 88, 199],
    [1512, 458, 48, 131], [1568, 415, 68, 174], [1642, 474, 50, 115],
    [690, 470, 50, 119], [746, 421, 64, 168], [817, 456, 44, 133],
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="sky22" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#101B46" />
          <stop offset="0.48" stopColor="#34327B" />
          <stop offset="0.78" stopColor="#2878F0" />
          <stop offset="1" stopColor="#37C7D6" />
        </linearGradient>
        <linearGradient id="road22" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#37E6E6" />
          <stop offset="0.52" stopColor="#2878F0" />
          <stop offset="1" stopColor="#172554" />
        </linearGradient>
        <linearGradient id="gate22" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#A5FFFF" />
          <stop offset="0.48" stopColor="#37E6E6" />
          <stop offset="1" stopColor="#2878F0" />
        </linearGradient>
        <radialGradient id="sun22">
          <stop offset="0" stopColor="#FFF5B8" />
          <stop offset="0.5" stopColor="#FFD93D" />
          <stop offset="1" stopColor="#FF9C5A" />
        </radialGradient>
        <filter id="glow22" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="soft22" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="28" />
        </filter>
        <clipPath id="world22">
          <rect x="0" y="0" width="1920" height="1080" />
        </clipPath>
      </defs>

      <rect width="1920" height="1080" fill="url(#sky22)" />
      <circle cx="965" cy="360" r="230" fill="#37E6E6" opacity={0.1 + open * 0.07} filter="url(#soft22)" />

      <g clipPath="url(#world22)">
        <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
          {/* 远景：像素晨空、山川与系统城 */}
          <g opacity={0.72}>
            {Array.from({length: 24}).map((_, i) => {
              const x = 55 + ((i * 173) % 1810);
              const y = 65 + ((i * 83) % 300);
              const twinkle = 0.45 + 0.5 * Math.sin(t * 2 + i * 1.7);
              return <rect key={i} x={x} y={y} width={i % 3 === 0 ? 7 : 4} height={i % 3 === 0 ? 7 : 4} fill={i % 4 === 0 ? C.cyan2 : C.white} opacity={twinkle} />;
            })}
          </g>

          <g transform={`translate(0 ${-18 * open})`} opacity={0.35 + 0.65 * open}>
            <circle cx="970" cy="360" r="105" fill="url(#sun22)" />
            <rect x="852" y="359" width="236" height="8" fill="#F9B95D" opacity={0.55} />
            <rect x="866" y="386" width="208" height="6" fill="#F9B95D" opacity={0.4} />
          </g>

          <path d="M0 505 L150 360 L250 438 L408 265 L560 448 L690 330 L820 472 L930 395 L1050 478 L1190 332 L1340 456 L1505 286 L1680 430 L1805 350 L1920 472 L1920 650 L0 650 Z" fill="#313674" />
          <path d="M0 548 L188 426 L312 514 L470 382 L620 516 L770 414 L910 526 L1080 426 L1230 521 L1390 403 L1540 520 L1740 390 L1920 520 L1920 690 L0 690 Z" fill="#24568B" />
          <path d="M343 342 L408 265 L466 337 L437 324 L409 340 L383 320 Z" fill="#9BD9E8" opacity={0.75} />
          <path d="M1440 353 L1505 286 L1570 354 L1532 338 L1504 353 L1476 334 Z" fill="#9BD9E8" opacity={0.75} />

          <g opacity={0.25 + open * 0.75}>
            {buildings.map(([x, y, w, h], i) => (
              <g key={i}>
                <rect x={x} y={y} width={w} height={h} fill={i % 3 === 0 ? '#263568' : '#1B2B59'} />
                <rect x={x + 7} y={y + 8} width={w - 14} height={5} fill="#537EB1" />
                {Array.from({length: Math.max(2, Math.floor(h / 34))}).map((__, j) => (
                  <g key={j}>
                    <rect x={x + 10} y={y + 25 + j * 30} width={9} height={11} fill={(i + j) % 3 === 0 ? C.yellow : C.cyan} opacity={0.78} />
                    {w > 60 && <rect x={x + w - 22} y={y + 25 + j * 30} width={9} height={11} fill={(i + j) % 2 === 0 ? C.yellow : '#6096C8'} opacity={0.7} />}
                  </g>
                ))}
                {i === 3 && <path d={`M${x + w / 2} ${y} L${x + w / 2} ${y - 55}`} stroke={C.cyan} strokeWidth={5} />}
              </g>
            ))}
            <path d="M0 592 H1920" stroke="#63C9D6" strokeWidth={4} opacity={0.45} />
          </g>

          {/* 中景：进度条铺成透视道路 */}
          <path d="M886 588 L1034 588 L1785 1080 L135 1080 Z" fill="#111D43" opacity={0.92} />
          <path d="M918 594 L1002 594 L1530 1080 L390 1080 Z" fill="url(#road22)" opacity={0.28 + road * 0.72} />
          <path d="M887 590 L135 1080" stroke={C.cyan} strokeWidth={12} opacity={road} filter="url(#glow22)" />
          <path d="M1033 590 L1785 1080" stroke={C.cyan} strokeWidth={12} opacity={road} filter="url(#glow22)" />
          <path d="M919 594 L390 1080 M1001 594 L1530 1080" stroke="#A5FFFF" strokeWidth={3} opacity={0.65 * road} />

          <g opacity={road}>
            {[0, 1, 2, 3, 4, 5].map((i) => {
              const p = ((i / 6 + advance * 0.75) % 1);
              const yy = 620 + p * p * 450;
              const half = 18 + p * p * 85;
              const hh = 5 + p * 18;
              return <rect key={i} x={960 - half} y={yy} width={half * 2} height={hh} rx={hh / 2} fill={i % 2 ? C.yellow : C.cyan2} opacity={0.35 + p * 0.65} />;
            })}
            <path d="M958 635 L958 1035" stroke={C.white} strokeWidth={7} strokeDasharray="20 42" opacity={0.55} />
          </g>

          {/* 道路两侧的任务节点 */}
          <g opacity={out((t - 1.8) / 1.2)}>
            <g transform="translate(735 705)">
              <path d="M0 75 V0" stroke="#62E6D9" strokeWidth={5} />
              <rect x="-38" y="-48" width="76" height="58" rx="10" fill="#172554" stroke={C.cyan} strokeWidth={4} />
              <path d="M-19 -18 L-3 -31 L13 -18 L27 -18 L27 -3 L-19 -3 Z" fill="none" stroke={C.yellow} strokeWidth={5} />
            </g>
            <g transform="translate(1200 710)">
              <path d="M0 75 V0" stroke="#62E6D9" strokeWidth={5} />
              <rect x="-38" y="-48" width="76" height="58" rx="10" fill="#172554" stroke={C.cyan} strokeWidth={4} />
              <path d="M-19 -31 H19 V-5 H-19 Z M-10 -22 H10 M-10 -13 H5" fill="none" stroke={C.yellow} strokeWidth={4} />
            </g>
          </g>

          {/* 回车键轮廓连续展开为加载门 */}
          <g transform={`translate(960 ${535 - 28 * open})`}>
            <ellipse cx="0" cy="94" rx={190 + open * 75} ry={35} fill={C.cyan} opacity={0.14 + beat * 0.05} filter="url(#soft22)" />
            <path
              d={`M${-172 - open * 26} ${-72 - open * 112} H${118 + open * 80} Q${170 + open * 28} ${-72 - open * 112} ${170 + open * 28} ${-20 - open * 60} V${70 + open * 25} H${-172 - open * 26} Z`}
              fill="#142653"
              stroke="url(#gate22)"
              strokeWidth={10 + open * 5}
              filter="url(#glow22)"
            />
            <path
              d={`M${-145 - open * 18} ${-48 - open * 102} H${105 + open * 68} V${48 + open * 29} H${-145 - open * 18} Z`}
              fill="#0E1D42"
              stroke="#6FFFF2"
              strokeWidth={3}
              opacity={0.9}
            />
            <path d={`M-150 ${73 + open * 25} H${172 + open * 26}`} stroke={C.cyan2} strokeWidth={8} />

            <g opacity={1 - open}>
              <path d="M94 -26 H35 V-56 M35 -56 L13 -34 M35 -56 L57 -34" fill="none" stroke={C.white} strokeWidth={11} strokeLinecap="square" strokeLinejoin="miter" />
              <text x="-104" y="33" fill={C.white} fontFamily="monospace" fontSize="39" fontWeight="800" letterSpacing="5">ENTER</text>
            </g>

            <g opacity={open}>
              <rect x="-148" y="-137" width="296" height="45" rx={7} fill="#173A6B" />
              <rect x="-139" y="-128" width={278 * clamp01((t - 0.25) / 2.5)} height="27" rx={4} fill={C.cyan} />
              <text x="0" y="-151" textAnchor="middle" fill={C.cyan2} fontFamily="monospace" fontSize="24" fontWeight="700" letterSpacing="6">NEXT LEVEL</text>
              <text x="0" y="45" textAnchor="middle" fill={C.white} fontFamily="monospace" fontSize="24" fontWeight="700" letterSpacing="8">LOADING WORLD</text>
              <path d="M-180 -170 H-130 M130 -170 H180" stroke={C.yellow} strokeWidth={7} />
            </g>
          </g>

          {/* 门中飞出的像素星 */}
          <g opacity={open}>
            {[0, 1, 2, 3, 4, 5].map((i) => {
              const p = (t * 0.23 + i / 6) % 1;
              const side = i % 2 ? 1 : -1;
              const x = 960 + side * (130 + p * 310);
              const y = 470 - p * 220 + Math.sin(p * Math.PI) * 35;
              return <PixelSpark key={i} x={x} y={y} s={0.35 + p * 0.35} color={i % 3 === 0 ? C.yellow : C.cyan2} opacity={Math.sin(p * Math.PI)} />;
            })}
          </g>

          {/* 前景地形框住道路，保留歌词区中央净空 */}
          <path d="M0 765 Q190 700 390 790 L480 1080 H0 Z" fill="#14244E" />
          <path d="M1920 750 Q1725 705 1535 792 L1450 1080 H1920 Z" fill="#14244E" />
          <path d="M0 805 Q205 746 390 824" fill="none" stroke="#28598A" strokeWidth={9} />
          <path d="M1920 794 Q1720 748 1540 825" fill="none" stroke="#28598A" strokeWidth={9} />

          {/* 两位玩家从两侧拿起任务手柄，中央道路完整可见 */}
          <g transform={`translate(390 ${1005 + 24 * (1 - ready) - drift})`}>
            <g transform={`scale(${0.78 + advance * 0.035})`}>
              <Character
                pose="stand"
                armL={[-48 - ready * 18, -70 - ready * 18]}
                armR={[-48 - ready * 18, -70 - ready * 18]}
                headTurn={8}
                mood="calm"
              />
              <g transform={`translate(8 ${-174 - ready * 54}) rotate(${-5 + beat * 2})`}>
                <Controller x={0} y={0} s={0.88} glow={ready > 0.5} />
              </g>
              <g transform="translate(-46 -263)">
                <rect x="-13" y="-13" width="26" height="26" rx={5} fill={C.gold} stroke="#FFF3A0" strokeWidth={3} />
                <path d="M-5 0 H5 M0 -5 V5" stroke="#173A6B" strokeWidth={3} />
              </g>
            </g>
          </g>

          <g transform={`translate(1515 ${1020 + 28 * (1 - ready) - drift})`}>
            <g transform={`scale(${1.14 + advance * 0.035})`}>
              <Character
                view="back"
                pose="stand"
                armL={[-45 - ready * 20, -67 - ready * 20]}
                armR={[-45 - ready * 20, -67 - ready * 20]}
                headTurn={-7}
                mood="calm"
              />
              <g transform={`translate(-5 ${-174 - ready * 56}) rotate(${4 - beat * 2})`}>
                <Controller x={0} y={0} s={0.92} flip glow={ready > 0.5} />
              </g>
            </g>
          </g>

          {/* 手柄连线汇向同一扇关卡门 */}
          <g fill="none" stroke={C.cyan} strokeWidth={3} strokeDasharray="7 13" opacity={0.28 * ready}>
            <path d="M410 760 Q570 610 755 590" />
            <path d="M1510 755 Q1350 610 1165 590" />
          </g>

          <g opacity={ready}>
            <PixelSpark x={270} y={630} s={0.85 + beat * 0.08} color={C.yellow} />
            <PixelSpark x={1650} y={610} s={0.72 + beat * 0.08} color={C.cyan2} />
            <text x="270" y="680" textAnchor="middle" fill={C.white} fontFamily="monospace" fontWeight="800" fontSize="23" letterSpacing={4}>PLAYER 1</text>
            <text x="1650" y="660" textAnchor="middle" fill={C.white} fontFamily="monospace" fontWeight="800" fontSize="23" letterSpacing={4}>PLAYER 2</text>
          </g>
        </g>
      </g>

      {/* 顶部关卡信息，不遮挡人物与歌词 */}
      <g transform="translate(74 70)">
        <rect width="330" height="62" rx="15" fill="#101B46" opacity={0.72} stroke="#4D80B5" strokeWidth={2} />
        <rect x="17" y="16" width="30" height="30" rx={5} fill={C.yellow} />
        <path d="M25 31 H39 M32 24 V38" stroke="#173A6B" strokeWidth={5} />
        <text x="63" y="40" fill={C.white} fontFamily="monospace" fontSize="25" fontWeight="800" letterSpacing={4}>CO-OP QUEST</text>
      </g>
      <g transform="translate(1550 76)" opacity={0.9}>
        <text x="0" y="0" fill={C.cyan2} fontFamily="monospace" fontSize="20" fontWeight="700" letterSpacing={3}>WORLD 02</text>
        <rect x="0" y="18" width="290" height="13" rx={6} fill="#172554" />
        <rect x="0" y="18" width={290 * clamp01(0.55 + u * 0.45)} height="13" rx={6} fill={C.yellow} />
      </g>

      <rect width="1920" height="1080" fill="none" stroke="#0B1537" strokeWidth={28} opacity={0.25} />
    </svg>
  );
}