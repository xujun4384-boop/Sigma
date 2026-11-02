import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#111936';
export const META = {17: {bg: '#111936'}};

const skills = [
  {name: '创作', en: 'CREATE', x: 735, y: 360, c: '#FFD93D', start: 0.15},
  {name: '发布', en: 'PUBLISH', x: 1175, y: 335, c: '#45E6E6', start: 1.12},
  {name: '攻略', en: 'GUIDE', x: 690, y: 565, c: '#FF6EAA', start: 2.09},
  {name: '导航', en: 'NAVIGATE', x: 1235, y: 555, c: '#69E58B', start: 3.06},
];

function PixelStar({x, y, s, c, o = 1}: {x: number; y: number; s: number; c: string; o?: number}) {
  return (
    <path
      d="M-3-12H3V-5H10V3H3V10H-3V3H-10V-5H-3Z"
      transform={`translate(${x} ${y}) scale(${s / 12})`}
      fill={c}
      opacity={o}
    />
  );
}

function SkillGlyph({i}: {i: number}) {
  if (i === 0) {
    return (
      <g>
        <path d="M-19 17L-13-10 12-24 23-13 8 12Z" fill="#FFF4C2" stroke="#172554" strokeWidth={4} />
        <path d="M-13-10L8 12M12-24L23-13" stroke="#172554" strokeWidth={4} />
        <path d="M-19 17L-7 12-15 5Z" fill="#172554" />
        <PixelStar x={22} y={-24} s={14} c="#FFD93D" />
      </g>
    );
  }
  if (i === 1) {
    return (
      <g>
        <path d="M-27-18L28 0-27 20-15 3Z" fill="#E9FFFF" stroke="#173A6B" strokeWidth={4} strokeLinejoin="round" />
        <path d="M-15 3L28 0-5 15Z" fill="#77EAEA" />
        <path d="M-31 31H29M0 30V13M-10 22L0 12 10 22" fill="none" stroke="#45E6E6" strokeWidth={5} strokeLinecap="round" />
      </g>
    );
  }
  if (i === 2) {
    return (
      <g>
        <path d="M-27-24Q-12-30 0-20Q12-30 27-24V24Q12 18 0 28Q-12 18-27 24Z" fill="#FFF3D8" stroke="#542B63" strokeWidth={4} />
        <path d="M0-20V28M-17 10L-6-3 5 6 17-10" fill="none" stroke="#FF6EAA" strokeWidth={4} strokeLinecap="round" />
        <circle cx={-17} cy={10} r={4} fill="#542B63" />
        <PixelStar x={18} y={-11} s={10} c="#FF6EAA" />
      </g>
    );
  }
  return (
    <g>
      <circle r={28} fill="#E9FFF0" stroke="#173A6B" strokeWidth={4} />
      <circle r={20} fill="none" stroke="#69E58B" strokeWidth={3} strokeDasharray="3 5" />
      <path d="M8-19L-3 4-17 15-8-8Z" fill="#FF6EAA" stroke="#173A6B" strokeWidth={3} strokeLinejoin="round" />
      <path d="M8-19L-3 4-8-8Z" fill="#FFD93D" />
    </g>
  );
}

export function Shot17() {
  const e = useE();
  const t = e.shotT;
  const zoom = e.lerp(1.015, 1.065, e.easeIO(e.clamp01(t / 6.5)));
  const finished = skills.filter(s => t > s.start + 0.64).length;
  const beatBounce = Math.max(0, Math.sin((t * 129.82 / 60) * Math.PI * 2)) * 3;
  const celebration = e.seg(4.0, 4.65, t);

  const stars = [
    [150, 180, 8], [280, 310, 5], [410, 130, 7], [535, 245, 4], [675, 105, 6],
    [1320, 125, 7], [1460, 255, 5], [1645, 150, 8], [1770, 335, 5], [1530, 440, 4],
    [225, 520, 4], [370, 435, 6], [1700, 570, 6], [110, 690, 5],
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <radialGradient id="s17sky" cx="50%" cy="42%" r="76%">
          <stop offset="0" stopColor="#343071" />
          <stop offset="0.48" stopColor="#1D2754" />
          <stop offset="1" stopColor={BG} />
        </radialGradient>
        <linearGradient id="s17ground" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#263668" />
          <stop offset="1" stopColor="#10172F" />
        </linearGradient>
        <linearGradient id="s17trunk" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5138A8" />
          <stop offset="0.5" stopColor="#2878F0" />
          <stop offset="1" stopColor="#5138A8" />
        </linearGradient>
        <linearGradient id="s17xp" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#FF9F43" />
          <stop offset="1" stopColor="#FFD93D" />
        </linearGradient>
        <filter id="s17glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="10" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="s17soft" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="24" />
        </filter>
      </defs>

      <rect width="1920" height="1080" fill="url(#s17sky)" />
      <circle cx={960} cy={480} r={350} fill="#6048C8" opacity={0.12 + celebration * 0.08} filter="url(#s17soft)" />
      <path d="M0 610Q260 530 480 615T900 590T1370 600T1920 565V820H0Z" fill="#222B59" opacity={0.65} />
      <path d="M0 700Q280 625 570 690T1110 665T1510 680T1920 640V850H0Z" fill="#19244B" />

      {stars.map(([x, y, s], i) => {
        const tw = 0.42 + 0.38 * Math.sin(t * 2.2 + i * 1.7);
        return <PixelStar key={i} x={x} y={y} s={s} c={i % 3 === 0 ? '#45E6E6' : '#FFD93D'} o={tw} />;
      })}

      <g opacity={0.32} stroke="#6475BD" strokeWidth={2}>
        <path d="M100 760H1820" strokeDasharray="8 20" />
        <path d="M250 720L160 900M510 700L460 900M1410 700L1460 900M1670 720L1760 900" />
      </g>
      <ellipse cx={960} cy={905} rx={770} ry={190} fill="url(#s17ground)" />
      <ellipse cx={960} cy={875} rx={480} ry={92} fill="#2878F0" opacity={0.12} />
      <ellipse cx={960} cy={875} rx={355} ry={62} fill="none" stroke="#546AC0" strokeWidth={3} strokeDasharray="12 16" />

      <g transform={`translate(960 560) scale(${zoom}) translate(-960 -560)`}>
        {/* Skill tree: the persistent middle ground */}
        <g fill="none" strokeLinecap="round" strokeLinejoin="round">
          <path d="M960 840C945 725 970 650 955 550C940 450 970 340 955 210" stroke="#11182F" strokeWidth={66} />
          <path d="M960 840C945 725 970 650 955 550C940 450 970 340 955 210" stroke="url(#s17trunk)" strokeWidth={48} />
          <path d="M958 650C875 625 815 590 690 565M956 515C850 485 820 395 735 360M957 430C1040 410 1090 355 1175 335M960 650C1060 635 1125 575 1235 555M957 310C900 265 875 225 830 195M958 280C1035 245 1060 205 1100 165" stroke="#151B39" strokeWidth={34} />
          <path d="M958 650C875 625 815 590 690 565M956 515C850 485 820 395 735 360M957 430C1040 410 1090 355 1175 335M960 650C1060 635 1125 575 1235 555M957 310C900 265 875 225 830 195M958 280C1035 245 1060 205 1100 165" stroke="#4355A0" strokeWidth={20} />
          <path d="M955 805C955 690 970 610 958 520" stroke="#7C96FF" strokeWidth={5} opacity={0.65} />
        </g>

        {[[830, 195], [1100, 165], [955, 205]].map(([x, y], i) => (
          <g key={i} transform={`translate(${x} ${y})`}>
            <circle r={28} fill="#202A55" stroke="#6577C4" strokeWidth={5} />
            <PixelStar x={0} y={0} s={22} c="#8190CF" o={0.75} />
          </g>
        ))}

        {skills.map((s, i) => {
          const active = e.clamp01((t - s.start - 0.52) / 0.25);
          const pulse = active * (1 + 0.08 * Math.sin(t * 5 + i));
          return (
            <g key={`node-${i}`} transform={`translate(${s.x} ${s.y}) scale(${pulse || 1})`}>
              <circle r={61} fill={s.c} opacity={active * 0.17} filter="url(#s17soft)" />
              <circle r={53} fill="#182345" stroke={active ? s.c : '#53639D'} strokeWidth={6} />
              <circle r={43} fill="none" stroke={s.c} strokeWidth={2} opacity={0.25 + active * 0.65} strokeDasharray="5 7" />
              {!active && <PixelStar x={0} y={0} s={25} c="#6171A8" />}
            </g>
          );
        })}

        {/* Falling skills become the same icons embedded in the branch sockets */}
        {skills.map((s, i) => {
          const u = e.clamp01((t - s.start) / 0.62);
          if (u <= 0) return null;
          const landed = u >= 1;
          const yy = landed ? s.y : e.lerp(-110, s.y, e.easeIn(u));
          const xx = landed ? s.x : s.x + Math.sin(u * Math.PI) * (i % 2 ? 70 : -70);
          const pop = landed ? 1 + 0.16 * Math.exp(-(t - s.start - 0.62) * 7) * Math.sin((t - s.start - 0.62) * 22) : 0.82 + u * 0.18;
          return (
            <g key={`skill-${i}`}>
              {!landed && (
                <path d={`M${s.x} ${Math.max(0, yy - 190)}L${xx} ${yy - 52}`} stroke={s.c} strokeWidth={9} opacity={0.35} strokeLinecap="round" />
              )}
              <g transform={`translate(${xx} ${yy}) rotate(${landed ? 0 : (1 - u) * (i % 2 ? 150 : -150)}) scale(${pop})`}>
                <circle r={48} fill={s.c} opacity={0.22} filter="url(#s17glow)" />
                <SkillGlyph i={i} />
              </g>
              {landed && (
                <g transform={`translate(${s.x} ${s.y + 76})`}>
                  <rect x={-61} y={-17} width={122} height={34} rx={17} fill="#111936" stroke={s.c} strokeWidth={2} />
                  <text x={0} y={6} textAnchor="middle" fill="#FFFFFF" fontSize={19} fontWeight={800} fontFamily="sans-serif" letterSpacing={2}>{s.name}</text>
                </g>
              )}
            </g>
          );
        })}

        {/* Impact spokes behind the pair */}
        {skills.map((s, i) => {
          const q = e.clamp01((t - s.start - 0.58) / 0.45);
          if (q <= 0 || q >= 1) return null;
          return (
            <g key={`burst-${i}`} transform={`translate(${s.x} ${s.y})`} opacity={1 - q} stroke={s.c} strokeWidth={6} strokeLinecap="round">
              {[0, 45, 90, 135, 180, 225, 270, 315].map(a => (
                <path key={a} d="M0-68V-92" transform={`rotate(${a}) scale(${1 + q})`} />
              ))}
            </g>
          );
        })}

        {/* Back-to-back partners, Landis larger and Sigma smaller */}
        <g transform={`translate(0 ${-beatBounce})`}>
          <ellipse cx={875} cy={914} rx={90} ry={20} fill="#080E22" opacity={0.55} />
          <ellipse cx={1030} cy={914} rx={120} ry={24} fill="#080E22" opacity={0.55} />
          <Actor
            Character={Character}
            x={1035}
            y={910}
            s={1.08}
            view="side"
            armL={[-126, -28]}
            armR={[-48, -50]}
            headTurn={-5}
            tilt={-3 - Math.sin(t * 3) * 1.2}
            mood="calm"
          />
          <Actor
            Character={Character}
            x={875}
            y={910}
            s={0.65}
            flip
            view="side"
            armL={[-45, -55]}
            armR={[-132, -24]}
            headTurn={5}
            tilt={3 + Math.sin(t * 3.4) * 2}
            mood="surprised"
          />
          <g fill="#FFF" opacity={0.8}>
            <circle cx={788} cy={625 + Math.sin(t * 4) * 6} r={6} />
            <circle cx={1135} cy={590 + Math.cos(t * 4) * 6} r={6} />
          </g>
        </g>

        {/* Combo numerals orbit as a readable game HUD */}
        <g transform={`translate(960 655) rotate(${t * 24})`}>
          {['×1', '×2', '×3', '×4'].map((label, i) => {
            const a = i * 90;
            const on = i < Math.max(1, finished);
            const rad = a * Math.PI / 180;
            const x = Math.cos(rad) * 350;
            const y = Math.sin(rad) * 205;
            return (
              <g key={label} transform={`translate(${x} ${y}) rotate(${-a - t * 24})`} opacity={on ? 1 : 0.18}>
                <rect x={-49} y={-30} width={98} height={60} rx={18} fill="#131D40" stroke={skills[i].c} strokeWidth={4} />
                <text x={0} y={13} textAnchor="middle" fill={on ? skills[i].c : '#7581AD'} fontSize={38} fontWeight={900} fontFamily="monospace">{label}</text>
              </g>
            );
          })}
        </g>

        {/* Twin-heart daily promise motif */}
        <g transform={`translate(960 748) scale(${0.85 + celebration * 0.25})`} opacity={0.35 + finished * 0.16}>
          <path d="M-12 0H12V12H24V24H12V36H0V24H-12V36H-24V24H-36V12H-24V0H-12Z" fill="#FF5C9A" transform="translate(-25 0) scale(.65)" />
          <path d="M-12 0H12V12H24V24H12V36H0V24H-12V36H-24V24H-36V12H-24V0H-12Z" fill="#FF5C9A" transform="translate(25 0) scale(.65)" />
        </g>
      </g>

      {/* Foreground plaza rim */}
      <path d="M0 960Q350 915 650 970T1260 960T1920 945V1080H0Z" fill="#0B122A" />
      <path d="M0 960Q350 915 650 970T1260 960T1920 945" fill="none" stroke="#354477" strokeWidth={5} />
      {[95, 240, 1580, 1760].map((x, i) => (
        <g key={x} transform={`translate(${x} ${946 + (i % 2) * 18})`} fill="#182448">
          <path d="M0 28L8-15 16 28M28 28L40-35 48 28M58 28L66-5 76 28Z" />
        </g>
      ))}

      {/* Experience bar */}
      <g transform="translate(540 62)">
        <rect x={0} y={0} width={840} height={72} rx={25} fill="#0B1230" opacity={0.94} stroke="#5367AF" strokeWidth={3} />
        <text x={28} y={31} fill="#AFC2FF" fontSize={18} fontWeight={700} fontFamily="monospace" letterSpacing={3}>DAILY SYNC</text>
        <text x={810} y={32} textAnchor="end" fill="#FFD93D" fontSize={22} fontWeight={900} fontFamily="monospace">COMBO {Math.max(1, finished)}/4</text>
        <rect x={28} y={43} width={784} height={14} rx={7} fill="#26345F" />
        <rect x={28} y={43} width={784 * e.clamp01(0.38 + t * 0.09)} height={14} rx={7} fill="url(#s17xp)" filter="url(#s17glow)" />
      </g>

      <g transform="translate(960 987)">
        <text textAnchor="middle" fill="#7F92CF" fontSize={18} fontWeight={700} fontFamily="monospace" letterSpacing={6}>CREATE · PUBLISH · GUIDE · NAVIGATE</text>
      </g>
    </svg>
  );
}