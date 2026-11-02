import React from 'react';
import {useE} from '../../engine/context';
import {CharacterSide} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#101a3b';
export const META = {21: {bg: '#101a3b'}};

export function Shot21() {
  const e = useE();
  const t = e.shotT;
  const press = e.easeOut(e.clamp01((t - 3.02) / 0.18));
  const burst = e.easeOut(e.clamp01((t - 3.12) / 1.25));
  const push = 1 + 0.035 * e.easeIO(e.shotU) + 0.025 * burst;
  const count = t < 0.7 ? 3 : t < 1.4 ? 2 : t < 2.15 ? 1 : 0;
  const beatGlow = 0.5 + 0.5 * Math.sin(t * Math.PI * 4.33);
  const cyan = '#42F5E9';
  const yellow = '#FFD93D';

  const cracks = [
    'M960 318 L918 270 L930 214 L866 154 L880 92',
    'M960 318 L1018 278 L1050 214 L1128 184 L1160 104 L1240 70',
    'M960 318 L1050 342 L1100 396 L1210 402 L1270 470 L1400 492',
    'M960 318 L902 370 L824 366 L770 438 L654 454 L590 526',
    'M960 318 L968 404 L930 452 L950 536',
    'M960 318 L888 312 L826 266 L714 282 L640 218 L500 202',
  ];

  const pixels = Array.from({length: 52}, (_, i) => {
    const a = i * 2.39996;
    const r = 80 + (i % 13) * 42;
    const x = 960 + Math.cos(a) * r * burst * 1.65;
    const y = 320 + Math.sin(a) * r * burst * 0.82;
    const size = 5 + (i % 4) * 4;
    return {x, y, size, color: i % 3 === 0 ? yellow : cyan, rot: (i % 5) * 9};
  });

  return (
    <svg viewBox="0 0 1920 1080" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="s21bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#172554"/>
          <stop offset="1" stopColor="#090f28"/>
        </linearGradient>
        <linearGradient id="s21screen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#122854"/>
          <stop offset="0.55" stopColor="#091b3d"/>
          <stop offset="1" stopColor="#173a6b"/>
        </linearGradient>
        <linearGradient id="s21desk" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9c5f55"/>
          <stop offset="1" stopColor="#4b2b42"/>
        </linearGradient>
        <radialGradient id="s21flash">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.95"/>
          <stop offset="0.25" stopColor="#42f5e9" stopOpacity="0.62"/>
          <stop offset="1" stopColor="#42f5e9" stopOpacity="0"/>
        </radialGradient>
        <filter id="s21glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="s21soft" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="28"/>
        </filter>
        <clipPath id="s21screenClip">
          <rect x="302" y="62" width="1316" height="530" rx="25"/>
        </clipPath>
      </defs>

      <rect width="1920" height="1080" fill="url(#s21bg)"/>
      <circle cx="960" cy="340" r="690" fill="#2878f0" opacity={0.09 + burst * 0.12} filter="url(#s21soft)"/>

      <g transform={`translate(960 540) scale(${push}) translate(-960 -540)`}>
        {/* monitor and the three-beat countdown */}
        <rect x="268" y="30" width="1384" height="600" rx="42" fill="#080d20" stroke="#344a79" strokeWidth="12"/>
        <rect x="302" y="62" width="1316" height="530" rx="25" fill="url(#s21screen)"/>
        <g clipPath="url(#s21screenClip)">
          <path d="M302 505 L680 325 L935 450 L1260 230 L1618 360 V592 H302Z" fill="#2878f0" opacity="0.09"/>
          <g opacity="0.16" fill="#71a7ff">
            {Array.from({length: 15}, (_, i) => <rect key={i} x={340 + i * 88} y="102" width="2" height="450"/>)}
            {Array.from({length: 6}, (_, i) => <rect key={i} x="330" y={122 + i * 82} width="1250" height="2"/>)}
          </g>

          <g opacity={1 - burst * 0.75}>
            <text x="960" y="190" textAnchor="middle" fill="#9db9e8" fontSize="30" fontWeight="700" letterSpacing="9">NEXT LEVEL · READY</text>
            <g transform="translate(0 8)">
              {[0, 1, 2].map((i) => {
                const lit = (count === 3 && i === 0) || (count === 2 && i === 1) || (count === 1 && i === 2) || count === 0;
                return (
                  <g key={i}>
                    <rect x={785 + i * 125} y="242" width="100" height="100" rx="15" fill={lit ? yellow : '#1c3662'} stroke={lit ? '#fff3a6' : '#45618e'} strokeWidth="5"/>
                    <rect x={803 + i * 125} y="260" width="64" height="64" rx="8" fill={lit ? '#fff4a8' : '#284675'} opacity={lit ? 0.35 + beatGlow * 0.25 : 0.3}/>
                  </g>
                );
              })}
            </g>
            <text x="960" y="450" textAnchor="middle" fill={count === 0 ? cyan : '#ffffff'} fontSize={count === 0 ? 68 : 116} fontWeight="900" fontFamily="monospace">
              {count === 0 ? 'PRESS ENTER' : count}
            </text>
          </g>

          <circle cx="960" cy="318" r={520 * burst} fill="url(#s21flash)" opacity={burst * 0.9}/>
          <g fill="none" strokeLinecap="square" strokeLinejoin="miter" filter="url(#s21glow)">
            {cracks.map((d, i) => (
              <path key={i} d={d} pathLength="1" stroke={i % 2 ? yellow : cyan} strokeWidth={i % 2 ? 7 : 10} strokeDasharray="1" strokeDashoffset={1 - burst}/>
            ))}
          </g>
        </g>

        <rect x="850" y="624" width="220" height="82" rx="18" fill="#11182e"/>
        <path d="M735 720 H1185 L1125 680 H795Z" fill="#263653"/>

        {/* desktop close-up */}
        <path d="M0 680 L1920 680 V1080 H0Z" fill="url(#s21desk)"/>
        <path d="M0 680 H1920 V710 H0Z" fill="#d28a68" opacity="0.48"/>
        <path d="M355 750 L1565 750 L1740 1040 H180 L355 750Z" fill="#111a31" stroke="#334768" strokeWidth="8"/>
        <g fill="#263754" stroke="#4d6488" strokeWidth="3">
          {Array.from({length: 10}, (_, i) => <rect key={i} x={390 + i * 113} y="778" width="92" height="55" rx="10"/>)}
          {Array.from({length: 9}, (_, i) => <rect key={i} x={345 + i * 125} y="858" width="102" height="58" rx="10"/>)}
          {Array.from({length: 7}, (_, i) => <rect key={i} x={300 + i * 138} y="944" width="112" height="58" rx="10"/>)}
        </g>

        {/* Sigma reaches in from the left; Landis remains an off-screen sleeve and glove */}
        <g transform={`translate(0 ${press * 24})`}>
          <Actor Character={CharacterSide} x={330} y={1060} s={1.38} armR={[-67 - press * 7, -30 + press * 8]} headTurn={10} mood="calm"/>
        </g>

        <g transform={`translate(${press * 4} ${-38 + press * 48})`}>
          <path d="M1920 610 L1635 668 L1435 786 L1510 920 L1765 805 L1920 785Z" fill="#243b6b" stroke="#17264b" strokeWidth="8"/>
          <path d="M1510 741 L1395 773 L1374 856 L1518 895 L1560 817Z" fill="#aab4c8"/>
          <g transform="translate(1340 770) rotate(-10)">
            <rect x="0" y="32" width="132" height="100" rx="42" fill="#f7fbff" stroke="#c8d7ed" strokeWidth="6"/>
            <rect x="74" y="0" width="45" height="92" rx="22" fill="#ffffff"/>
            <rect x="30" y="8" width="42" height="82" rx="21" fill="#ffffff"/>
            <path d="M14 98 Q-28 75 -22 119 Q-4 155 42 148" fill="#ffffff" stroke="#c8d7ed" strokeWidth="5"/>
          </g>
        </g>

        {/* oversized enter key, the visual anchor */}
        <g transform={`translate(0 ${press * 18})`}>
          <rect x="716" y="824" width="488" height="174" rx="28" fill="#080f24" opacity={0.65} transform="translate(0 18)"/>
          <rect x="716" y="812" width="488" height="174" rx="28" fill={press ? '#d9fffa' : cyan} stroke="#b8fffa" strokeWidth="8" filter={press ? 'url(#s21glow)' : undefined}/>
          <path d="M770 842 H1150" stroke="#ffffff" strokeWidth="8" opacity="0.6" strokeLinecap="round"/>
          <path d="M846 880 V927 H1035 M1035 927 L995 895 M1035 927 L995 959" fill="none" stroke="#12345c" strokeWidth="18" strokeLinecap="square" strokeLinejoin="miter"/>
          <text x="1090" y="948" textAnchor="middle" fill="#12345c" fontSize="25" fontWeight="900" letterSpacing="3">ENTER</text>
        </g>

        {/* crack-light escapes the screen as square pixels */}
        <g opacity={burst}>
          {pixels.map((p, i) => (
            <rect key={i} x={p.x} y={p.y} width={p.size} height={p.size} fill={p.color} transform={`rotate(${p.rot} ${p.x} ${p.y})`} filter={i % 6 === 0 ? 'url(#s21glow)' : undefined}/>
          ))}
        </g>
        <rect width="1920" height="1080" fill="#dfffff" opacity={Math.max(0, 0.32 - (t - 3.12) * 0.7)}/>
      </g>

      <path d="M0 0 H1920 V1080 H0Z" fill="none" stroke="#060b20" strokeWidth="54" opacity="0.35"/>
    </svg>
  );
}