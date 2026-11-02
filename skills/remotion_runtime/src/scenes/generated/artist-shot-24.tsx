import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';

export const BG = '#101a38';
export const META = {24: {bg: '#101a38'}};

const C = {
  ink: '#101a38',
  wall: '#172554',
  blue: '#2878F0',
  cyan: '#54E7F2',
  gold: '#FFD43B',
  star: '#FFD93D',
  cream: '#FFF4C6',
  navy: '#173A6B',
  skin: '#F2C7A5',
  pajama: '#243B6B',
};

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const smooth = (v: number) => {
  const x = clamp01(v);
  return x * x * (3 - 2 * x);
};
const mix = (a: number, b: number, u: number) => a + (b - a) * u;

const nodes = [
  {x: 960, y: 548, c: '#FFD43B', kind: 'code'},
  {x: 770, y: 484, c: '#54E7F2', kind: 'doc'},
  {x: 1150, y: 480, c: '#44D17A', kind: 'web'},
  {x: 824, y: 357, c: '#FF7CA8', kind: 'mail'},
  {x: 1104, y: 350, c: '#FFD43B', kind: 'map'},
  {x: 894, y: 236, c: '#9D8CFF', kind: 'music'},
  {x: 1044, y: 205, c: '#54E7F2', kind: 'plane'},
  {x: 960, y: 405, c: '#FF7CA8', kind: 'heart'},
];

function SkillIcon({kind}: {kind: string}) {
  const common = {
    fill: 'none',
    stroke: '#FFF9DF',
    strokeWidth: 4,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };
  if (kind === 'code') {
    return <g {...common}><path d="M-17 -10 L-27 0 L-17 10 M17 -10 L27 0 L17 10 M7 -18 L-7 18" /></g>;
  }
  if (kind === 'doc') {
    return <g {...common}><path d="M-17 -23 H7 L19 -11 V23 H-17 Z M7 -23 V-11 H19 M-8 0 H10 M-8 10 H7" /></g>;
  }
  if (kind === 'web') {
    return <g {...common}><circle r="22" /><path d="M-22 0 H22 M0 -22 C12 -10 12 10 0 22 C-12 10 -12 -10 0 -22" /></g>;
  }
  if (kind === 'mail') {
    return <g {...common}><rect x="-24" y="-17" width="48" height="34" rx="4" /><path d="M-22 -14 L0 4 L22 -14" /></g>;
  }
  if (kind === 'map') {
    return <g {...common}><path d="M-24 -18 L-8 -23 L8 -17 L24 -22 V18 L8 23 L-8 17 L-24 22 Z M-8 -23 V17 M8 -17 V23" /></g>;
  }
  if (kind === 'music') {
    return <g {...common}><path d="M-5 12 V-20 L20 -25 V7 M-5 -12 L20 -17" /><ellipse cx="-13" cy="14" rx="9" ry="7" /><ellipse cx="12" cy="9" rx="9" ry="7" /></g>;
  }
  if (kind === 'plane') {
    return <g {...common}><path d="M-27 -5 L27 -22 L8 25 L-2 6 Z M-2 6 L27 -22" /></g>;
  }
  return <path d="M0 22 C-5 13 -25 4 -25 -10 C-25 -25 -7 -28 0 -15 C7 -28 25 -25 25 -10 C25 4 5 13 0 22 Z" fill="#FFF9DF" />;
}

function LaunchBadge({x, y, s, opacity = 1}: {x: number; y: number; s: number; opacity?: number}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
      <circle r="59" fill="#14264F" stroke="#FFE889" strokeWidth="5" />
      <circle r="49" fill="url(#badgeGold)" stroke="#FFF4C6" strokeWidth="3" />
      <path d="M0 -37 L10 -25 L25 -27 L28 -12 L40 -3 L33 11 L36 26 L21 30 L12 42 L0 35 L-12 42 L-21 30 L-36 26 L-33 11 L-40 -3 L-28 -12 L-25 -27 L-10 -25 Z"
        fill="#E8A918" opacity="0.48" />
      <path d="M0 -27 V2" stroke="#173A6B" strokeWidth="9" strokeLinecap="round" />
      <path d="M-17 -17 A25 25 0 1 0 17 -17" fill="none" stroke="#173A6B" strokeWidth="9" strokeLinecap="round" />
      <path d="M-25 -35 L-17 -32 M25 -35 L17 -32" stroke="#FFF9DF" strokeWidth="4" strokeLinecap="round" />
    </g>
  );
}

export function Shot24() {
  const e = useE();
  const t = e.shotT;

  const converge = smooth((t - 0.35) / 1.05);
  const badgeBirth = smooth((t - 0.88) / 0.48);
  const badgeFly = smooth((t - 1.42) / 0.92);
  const pinned = t >= 2.32;
  const bumpIn = smooth((t - 2.66) / 0.40);
  const bumpOut = smooth((t - 3.52) / 0.38);
  const bump = clamp01(bumpIn - bumpOut);
  const impact = Math.max(0, 1 - Math.abs(t - 3.24) / 0.22);

  const jumpU = smooth((t - 4.02) / 1.12);
  const jumpArc = Math.sin(Math.PI * jumpU);
  const anticipation = smooth((t - 3.72) / 0.28) * (1 - smooth((t - 4.02) / 0.12));

  const cx = mix(664, 1400, jumpU);
  const cy = mix(930, 690, jumpU) - 178 * jumpArc + 14 * anticipation
    + (t > 5.14 ? Math.sin((t - 5.14) * 5) * 3 : 0);
  const cs = mix(1.12, 0.50, jumpU);
  const rotation = -9 * jumpArc + 4 * anticipation;
  const screenOn = smooth((t - 5.02) / 0.62);
  const chestX = cx + 31 * cs;
  const chestY = cy - 282 * cs;

  let armR: [number, number] = [0, 0];
  let armL: [number, number] = [0, 0];
  if (t > 1.45 && t < 2.72) {
    const pin = Math.sin(clamp01((t - 1.45) / 1.27) * Math.PI);
    armR = [-48 * pin, -70 * pin];
    armL = [-12 * pin, -22 * pin];
  } else if (t >= 2.72 && t < 3.82) {
    armR = [-68 - 8 * impact, -12];
    armL = [-12, -18];
  } else if (t >= 3.82 && t < 5.15) {
    armR = [-112, -20];
    armL = [-104, -24];
  }
  const mood = t > 1.25 && t < 2.15 ? 'surprised' : 'calm';

  const fistX = mix(1510, 842, bumpIn) + 668 * bumpOut;
  const fistY = mix(555, 585, bumpIn) - 10 * impact;

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="wall24" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#101a38" />
          <stop offset="0.68" stopColor="#1b315b" />
          <stop offset="1" stopColor="#244267" />
        </linearGradient>
        <linearGradient id="dawn24" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#18244D" />
          <stop offset="0.65" stopColor="#675D91" />
          <stop offset="1" stopColor="#F3A96B" />
        </linearGradient>
        <linearGradient id="desk24" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#AD704C" />
          <stop offset="1" stopColor="#65432F" />
        </linearGradient>
        <linearGradient id="badgeGold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFF3A1" />
          <stop offset="0.42" stopColor="#FFD43B" />
          <stop offset="1" stopColor="#E5A51C" />
        </linearGradient>
        <radialGradient id="screenGlow">
          <stop offset="0" stopColor="#4BDDEB" stopOpacity="0.52" />
          <stop offset="0.55" stopColor="#2878F0" stopOpacity="0.25" />
          <stop offset="1" stopColor="#10254E" stopOpacity="0" />
        </radialGradient>
        <filter id="glow24" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="10" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="soft24" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="24" />
        </filter>
        <clipPath id="screenClip24">
          <rect x="1162" y="274" width="486" height="423" rx="20" />
        </clipPath>
      </defs>

      <rect width="1920" height="1080" fill="url(#wall24)" />
      <ellipse cx="1400" cy="430" rx="520" ry="410" fill="#2878F0" opacity={0.035 + screenOn * 0.08} filter="url(#soft24)" />

      {/* 黎明书房后景 */}
      <g opacity="0.92">
        <rect x="72" y="105" width="420" height="460" rx="10" fill="#0C1530" stroke="#3B4B6D" strokeWidth="14" />
        <rect x="91" y="124" width="382" height="422" fill="url(#dawn24)" />
        <path d="M282 124 V546 M91 337 H473" stroke="#263757" strokeWidth="12" />
        <path d="M91 478 L155 422 L217 459 L290 381 L364 450 L473 393 V546 H91 Z" fill="#263859" opacity="0.75" />
        <circle cx="398" cy="203" r="29" fill="#FFF1C2" opacity="0.55" />
      </g>
      <g opacity="0.58">
        <path d="M540 190 H725 M540 202 H725" stroke="#0B132C" strokeWidth="16" />
        <rect x="563" y="121" width="31" height="67" fill="#2878F0" />
        <rect x="600" y="137" width="27" height="51" fill="#D8A839" />
        <rect x="633" y="111" width="38" height="77" fill="#445B86" />
        <path d="M695 187 C673 151 689 129 714 150 C731 122 754 153 725 187" fill="#44D17A" />
      </g>

      {/* 桌面与电脑 */}
      <rect x="0" y="842" width="1920" height="238" fill="url(#desk24)" />
      <rect x="0" y="842" width="1920" height="20" fill="#D39766" />
      <path d="M0 943 H1920" stroke="#513626" strokeWidth="4" opacity="0.35" />
      <ellipse cx="1396" cy="849" rx="235" ry="30" fill="#071126" opacity="0.38" />
      <path d="M1370 714 H1440 L1452 817 H1358 Z" fill="#202B44" />
      <rect x="1280" y="811" width="250" height="26" rx="13" fill="#303E59" />
      <rect x="1138" y="250" width="534" height="478" rx="31" fill="#0A1022" stroke="#3B4A65" strokeWidth="10" />
      <rect x="1162" y="274" width="486" height="423" rx="20" fill="#0D1B38" />
      <g clipPath="url(#screenClip24)">
        <rect x="1162" y="274" width="486" height="423" fill="#10254E" opacity={screenOn} />
        <ellipse cx="1405" cy="488" rx="310" ry="280" fill="url(#screenGlow)" opacity={screenOn} />
        <g opacity={0.12 + screenOn * 0.15} stroke="#70DDE8" strokeWidth="2">
          {Array.from({length: 9}, (_, i) => <path key={`v${i}`} d={`M${1180 + i * 58} 274 V697`} />)}
          {Array.from({length: 8}, (_, i) => <path key={`h${i}`} d={`M1162 ${292 + i * 55} H1648`} />)}
        </g>
        <g opacity={0.30 + 0.7 * screenOn}>
          <circle cx="1405" cy="430" r={105 + screenOn * 8} fill="none" stroke="#4FDDE7" strokeWidth="3" strokeDasharray="8 12" />
          <circle cx="1405" cy="430" r="82" fill="#173A6B" stroke="#83F3F0" strokeWidth="4" />
          <path d="M1405 370 V421" stroke="#CFFFF7" strokeWidth="13" strokeLinecap="round" />
          <path d="M1369 388 A53 53 0 1 0 1441 388" fill="none" stroke="#CFFFF7" strokeWidth="13" strokeLinecap="round" />
        </g>
        <text x="1405" y="324" textAnchor="middle" fill="#DFFFF8" fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="25" letterSpacing="7" opacity={screenOn}>SIGMA</text>
        <text x="1405" y="662" textAnchor="middle" fill="#FFD43B" fontFamily="system-ui, sans-serif" fontWeight="800" fontSize="21" letterSpacing="5" opacity={screenOn}>READY</text>
        <rect x="1162" y={274 + ((t * 80) % 423)} width="486" height="3" fill="#B6FFFF" opacity={0.10 * screenOn} />
      </g>
      <circle cx="1405" cy="713" r="4" fill={screenOn > 0.4 ? '#54E7F2' : '#43506A'} />
      <g transform="translate(1080 895) rotate(-4)" opacity="0.78">
        <rect x="-150" y="-28" width="370" height="70" rx="12" fill="#D8DFE9" />
        {Array.from({length: 10}, (_, i) => <rect key={i} x={-133 + i * 33} y="-12" width="25" height="20" rx="4" fill="#728099" />)}
        <rect x="-38" y="17" width="150" height="14" rx="4" fill="#728099" />
      </g>

      {/* 完整技能树收束 */}
      <g opacity={1 - smooth((t - 1.0) / 0.55)}>
        <path d="M960 622 V530 M960 548 L770 484 M960 548 L1150 480 M960 490 L824 357 M960 490 L1104 350 M960 405 L894 236 M960 405 L1044 205"
          fill="none" stroke="#4D78A7" strokeWidth="12" strokeLinecap="round" />
        <path d="M960 622 V530 M960 548 L770 484 M960 548 L1150 480 M960 490 L824 357 M960 490 L1104 350 M960 405 L894 236 M960 405 L1044 205"
          fill="none" stroke="#70E8EA" strokeWidth="3" strokeLinecap="round" opacity={0.45 + 0.25 * Math.sin(t * 8)} />
        <path d="M920 625 H1000 L984 590 H936 Z" fill="#263D69" stroke="#6C8EB7" strokeWidth="4" />
      </g>
      {nodes.map((n, i) => {
        const p = smooth((t - 0.28 - i * 0.055) / 0.82);
        const nx = mix(n.x, 960, p);
        const ny = mix(n.y, 372, p);
        const ns = mix(1, 0.12, p);
        return (
          <g key={n.kind}>
            <path d={`M${n.x} ${n.y} L${nx} ${ny}`} stroke={n.c} strokeWidth="5" opacity={p > 0 && p < 1 ? 0.34 : 0} />
            <g transform={`translate(${nx} ${ny}) scale(${ns})`} opacity={1 - p * 0.72}>
              <circle r="48" fill="#14264F" stroke={n.c} strokeWidth="6" />
              <circle r="39" fill={n.c} opacity="0.18" />
              <SkillIcon kind={n.kind} />
              <circle cx="-28" cy="-31" r="6" fill="#FFFFFF" opacity="0.75" />
            </g>
          </g>
        );
      })}
      {badgeBirth > 0 && badgeBirth < 1 && (
        <g transform="translate(960 372)" opacity={(1 - badgeBirth) * 0.8}>
          <circle r={60 + badgeBirth * 150} fill="none" stroke="#FFD43B" strokeWidth="5" />
          <circle r={35 + badgeBirth * 95} fill="none" stroke="#54E7F2" strokeWidth="3" />
        </g>
      )}

      {/* Sigma：佩戴、碰拳、跃回启动页 */}
      <g transform={`rotate(${rotation} ${cx} ${cy - 220 * cs})`} opacity={1 - smooth((t - 5.72) / 0.7) * 0.08}>
        <g transform={`translate(${cx} ${cy}) scale(${cs})`}>
          <Character
            view="front"
            pose="stand"
            mood={mood}
            armL={armL}
            armR={armR}
            headTurn={t > 2.65 && t < 3.8 ? 10 : t > 4 ? -7 : 0}
            tilt={-3 * anticipation}
          />
        </g>
      </g>

      {/* 徽章始终位于连帽衫之上 */}
      {badgeBirth > 0 && (
        <LaunchBadge
          x={pinned ? chestX : mix(mix(960, chestX, badgeFly), chestX, pinned ? 1 : 0)}
          y={pinned ? chestY : mix(mix(372, chestY, badgeFly), chestY, pinned ? 1 : 0)}
          s={pinned ? 0.47 * (cs / 1.12) : mix(0.15, mix(1, 0.47, badgeFly), badgeBirth)}
          opacity={badgeBirth}
        />
      )}
      {t > 2.25 && t < 2.58 && (
        <g transform={`translate(${chestX} ${chestY})`} stroke="#FFF4C6" strokeWidth="6" strokeLinecap="round" opacity={1 - Math.abs(t - 2.36) / 0.22}>
          <path d="M0 -75 V-105 M54 -52 L76 -74 M75 0 H108 M-54 -52 L-76 -74 M-75 0 H-108" />
        </g>
      )}

      {/* Landis 以前景睡衣袖口与拳头入画，保留 medium 构图 */}
      {bump > 0.001 && (
        <g transform={`translate(${fistX} ${fistY}) rotate(-8)`} opacity={bump}>
          <path d="M69 -37 C175 -60 311 -100 540 -147 L574 22 C353 41 203 52 72 45 Z"
            fill={C.pajama} stroke="#17284B" strokeWidth="6" />
          <path d="M116 -34 C249 -57 362 -91 498 -119" fill="none" stroke="#405983" strokeWidth="7" opacity="0.7" />
          <rect x="51" y="-43" width="58" height="94" rx="19" fill="#314A77" stroke="#17284B" strokeWidth="5" />
          <path d="M58 -31 C38 -54 10 -60 -7 -44 C-27 -58 -51 -45 -50 -24 C-72 -24 -82 -1 -67 15 C-77 36 -54 55 -31 47 L27 48 C53 42 66 22 64 -4 Z"
            fill={C.skin} stroke="#B8795E" strokeWidth="5" />
          <path d="M-47 -23 L-11 -20 M-55 2 L-15 3 M-42 27 L-5 25 M4 -42 C21 -29 24 -12 12 2"
            fill="none" stroke="#C98D70" strokeWidth="4" strokeLinecap="round" />
          <path d="M18 7 C43 -4 54 9 46 27 C39 39 23 38 9 29" fill={C.skin} stroke="#B8795E" strokeWidth="4" />
        </g>
      )}
      {impact > 0 && (
        <g transform="translate(810 574)" stroke="#FFD43B" strokeWidth="8" strokeLinecap="round" opacity={impact} filter="url(#glow24)">
          <path d="M-12 -61 L-19 -96 M38 -48 L61 -76 M58 -10 L96 -16 M-48 -42 L-72 -68" />
          <path d="M0 -30 L9 -9 L31 -6 L14 9 L19 31 L0 20 L-19 31 L-14 9 L-31 -6 L-9 -9 Z" fill="#FFF4C6" stroke="none" />
        </g>
      )}

      {/* 跳跃轨迹与启动完成 */}
      {jumpU > 0 && jumpU < 1 && (
        <g fill="none" strokeLinecap="round">
          <path d={`M${cx - 145} ${cy - 90} Q${cx - 80} ${cy - 190} ${cx - 15} ${cy - 230}`} stroke="#54E7F2" strokeWidth="9" opacity="0.45" />
          <path d={`M${cx - 190} ${cy - 35} Q${cx - 125} ${cy - 105} ${cx - 76} ${cy - 130}`} stroke="#FFD43B" strokeWidth="6" opacity="0.48" />
        </g>
      )}
      {screenOn > 0 && (
        <g opacity={screenOn * (0.5 + 0.2 * Math.sin(t * 6))} filter="url(#glow24)">
          <path d="M1168 282 H1230 M1580 282 H1642 M1168 690 H1230 M1580 690 H1642" stroke="#8FFFF4" strokeWidth="5" />
        </g>
      )}

      {/* 前景桌沿，收住中景 */}
      <path d="M0 1038 H1920 V1080 H0 Z" fill="#493225" opacity="0.78" />
      <path d="M0 1038 H1920" stroke="#C0875D" strokeWidth="4" opacity="0.42" />
    </svg>
  );
}