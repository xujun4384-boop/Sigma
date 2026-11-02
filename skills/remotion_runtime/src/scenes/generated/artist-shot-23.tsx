import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#101B46';
export const META = {23: {bg: '#101B46'}};

const C = {
  navy: '#101B46',
  deep: '#172554',
  blue: '#2878F0',
  cyan: '#37E6E6',
  yellow: '#FFD93D',
  gold: '#F4C95D',
  white: '#FFFFFF',
  pink: '#FF5C8A',
  violet: '#6D5DF6',
  ink: '#161A2B',
};

function PixelStar({x, y, s = 1, opacity = 1}: {x: number; y: number; s?: number; opacity?: number}) {
  return (
    <path
      d="M0-12 4-4 12-4 6 2 8 11 0 6-8 11-6 2-12-4-4-4Z"
      transform={`translate(${x} ${y}) scale(${s})`}
      fill={C.yellow}
      opacity={opacity}
    />
  );
}

function SkillIcon({kind, lit}: {kind: number; lit: boolean}) {
  const color = lit ? C.deep : '#7D91BB';
  const common = {fill: 'none', stroke: color, strokeWidth: 7, strokeLinecap: 'square' as const, strokeLinejoin: 'miter' as const};
  return (
    <g>
      {kind === 0 && <g {...common}><path d="M-17-18-31 0-17 18M17-18 31 0 17 18M8-25-8 25" /></g>}
      {kind === 1 && <g {...common}><rect x="-29" y="-21" width="58" height="42" /><path d="M-28-18 0 5 28-18" /></g>}
      {kind === 2 && <g {...common}><path d="M-31 19-7-24 31-28 13 3 29 22 17 28-2 12-17 29Z" /><path d="M-7-24-2 12" /></g>}
      {kind === 3 && <g {...common}><path d="M-22-28H10L25-13V28H-22Z" /><path d="M10-27V-12H24M-10 0H13M-10 13H8" /></g>}
      {kind === 4 && <path d="M7-32-25 7H-3L-10 32 27-10H4Z" fill={color} />}
      {kind === 5 && <path d="M0-31 9-10 32-8 15 7 20 30 0 18-20 30-15 7-32-8-9-10Z" fill={color} />}
    </g>
  );
}

function Sigma({x, y, run, jump, reach}: {x: number; y: number; run: number; jump: number; reach: number}) {
  const leg = Math.sin(run * Math.PI * 2) * (jump > 0 ? 0 : 1);
  const squash = jump > 0 ? 1 : 1 + Math.abs(Math.sin(run * Math.PI * 2)) * 0.025;
  return (
    <g transform={`translate(${x} ${y}) scale(${1 / squash} ${squash})`}>
      {/* 身后的小速度残影 */}
      <polygon points="-122,-250 -105,-264 -84,-250 -70,-266 -51,-246 -54,-220 -39,-204 -55,-185 -48,-161 -75,-158 -89,-140 -104,-159 -128,-154 -128,-181 -145,-198 -130,-218" fill={C.yellow} opacity=".10" transform={`translate(${-24 - Math.abs(leg) * 10} 0)`} />
      {/* 腿与鞋 */}
      <g transform={`translate(-29 -48) rotate(${leg * 28 - jump * 18})`}>
        <rect x="-10" y="0" width="20" height="38" rx="7" fill="#F2C7A5" />
        <path d="M-15 28H11L25 39V50H-18Z" fill={C.white} />
        <path d="M-18 43H25V51H-18Z" fill={C.blue} />
      </g>
      <g transform={`translate(28 -48) rotate(${-leg * 28 + jump * 24})`}>
        <rect x="-10" y="0" width="20" height="38" rx="7" fill="#F2C7A5" />
        <path d="M-15 28H11L25 39V50H-18Z" fill={C.white} />
        <path d="M-18 43H25V51H-18Z" fill={C.blue} />
      </g>
      <path d="M-52-86H52V-42H14V-55H-13V-42H-52Z" fill="#173A6B" />
      {/* 连帽衫 */}
      <path d="M-57-150Q-48-166-26-166H28Q50-164 58-145L50-75H-50Z" fill={C.blue} />
      <path d="M-36-154Q0-132 36-154" fill="none" stroke="#72A7FF" strokeWidth="7" />
      <path d="M-14-145V-123M14-145V-123" stroke={C.white} strokeWidth="4" />
      {/* 金色启动徽章 */}
      <circle cx="30" cy="-116" r="13" fill={C.gold} stroke="#FFF2A8" strokeWidth="3" />
      <path d="M30-124V-116M24-120Q17-108 30-104Q43-108 36-120" fill="none" stroke={C.deep} strokeWidth="3" strokeLinecap="round" />
      {/* 手臂：拉人时左手后伸 */}
      <g transform={`translate(-48 -139) rotate(${-18 - leg * 24 - reach * 68})`}>
        <rect x="-15" y="0" width="25" height="61" rx="12" fill={C.blue} />
        <circle cx="-2" cy="64" r="17" fill={C.white} />
        <rect x="-19" y="57" width="12" height="18" rx="5" fill={C.white} />
      </g>
      <g transform={`translate(47 -139) rotate(${18 + leg * 24 + jump * 38})`}>
        <rect x="-8" y="0" width="25" height="61" rx="12" fill={C.blue} />
        <circle cx="5" cy="64" r="17" fill={C.white} />
        <rect x="10" y="56" width="12" height="18" rx="5" fill={C.white} />
      </g>
      {/* 五角像素星头 */}
      <polygon
        points="0,-292 25,-292 25,-270 42,-240 86,-240 86,-218 103,-218 103,-197 82,-197 59,-174 67,-143 67,-120 44,-120 44,-133 0,-154 -44,-133 -44,-120 -67,-120 -67,-143 -59,-174 -82,-197 -103,-197 -103,-218 -86,-218 -86,-240 -42,-240 -25,-270 -25,-292"
        fill={C.yellow}
        stroke="#FFE98A"
        strokeWidth="4"
        strokeLinejoin="miter"
      />
      <rect x="-36" y="-224" width="12" height="16" rx="5" fill={C.ink} />
      <rect x="25" y="-224" width="12" height="16" rx="5" fill={C.ink} />
      <path d="M-11-195Q0-187 12-196" fill="none" stroke={C.ink} strokeWidth="6" strokeLinecap="round" />
      <rect x="-65" y="-214" width="13" height="7" fill="#FFB62E" opacity=".65" />
    </g>
  );
}

export function Shot23() {
  const e = useE();
  const t = e.shotT;
  const u = e.clamp01(t / 6.5);
  const beat = t * 129.82 / 60;
  const bob = Math.abs(Math.sin(beat * Math.PI)) * 10;

  const stumble = e.seg(2.05, 2.65, t) * (1 - e.seg(3.05, 3.55, t));
  const reach = e.seg(2.25, 2.75, t) * (1 - e.seg(3.65, 4.2, t));
  const jumpU = e.clamp01((t - 3.55) / 1.45);
  const jumping = t >= 3.55 && t <= 5.0 ? 1 : 0;
  const arc = jumping ? Math.sin(jumpU * Math.PI) : 0;

  let baseX = 690 + Math.min(t, 3.55) * 102;
  if (t > 3.55) baseX = 1052 + e.easeOut(jumpU) * 390 + Math.max(0, t - 5) * 75;
  const sigmaX = baseX + 90;
  const landisX = baseX - 105;
  const floorY = 792;
  const sigmaY = floorY - bob - arc * 255;
  const landisY = floorY - bob * 0.7 + stumble * 76 - arc * 245;
  const shake = stumble * Math.sin(t * 38) * 3;

  const tileXs = [410, 555, 700, 845, 990, 1135, 1280];
  const progress = e.clamp01((baseX - 260) / 1430);

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="sky23" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#101B46" />
          <stop offset=".58" stopColor="#25347A" />
          <stop offset="1" stopColor="#5138A8" />
        </linearGradient>
        <linearGradient id="road23" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#203064" />
          <stop offset=".6" stopColor="#172554" />
          <stop offset="1" stopColor="#101B46" />
        </linearGradient>
        <filter id="glow23" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="10" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="soft23" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="22" />
        </filter>
        <pattern id="checks23" width="40" height="40" patternUnits="userSpaceOnUse">
          <rect width="40" height="40" fill={C.white} />
          <rect width="20" height="20" fill={C.ink} />
          <rect x="20" y="20" width="20" height="20" fill={C.ink} />
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill="url(#sky23)" />
      <circle cx="1510" cy="240" r="170" fill="#6D5DF6" opacity=".18" filter="url(#soft23)" />

      {/* 远景：系统城与像素星 */}
      <g opacity=".42" transform={`translate(${-u * 55} 0)`}>
        {[90, 280, 510, 770, 1010, 1270, 1570, 1810].map((x, i) => (
          <g key={x}>
            <rect x={x} y={380 - (i % 3) * 65} width={150 + (i % 2) * 45} height={360 + (i % 3) * 65} fill="#18265A" />
            <rect x={x + 18} y={405 - (i % 3) * 65} width="16" height="12" fill={i % 3 === 0 ? C.cyan : '#596DA4'} />
            <rect x={x + 55} y={445 - (i % 3) * 65} width="16" height="12" fill="#596DA4" />
            <rect x={x + 92} y={405 - (i % 3) * 65} width="16" height="12" fill={i % 2 ? C.yellow : '#596DA4'} opacity=".7" />
          </g>
        ))}
      </g>
      <g opacity=".75">
        <PixelStar x={190} y={175} s={.8} />
        <PixelStar x={450} y={275} s={.45} opacity={.55} />
        <PixelStar x={820} y={145} s={.65} />
        <PixelStar x={1180} y={255} s={.4} opacity={.6} />
        <PixelStar x={1690} y={120} s={.7} />
      </g>

      {/* 中景速度线 */}
      <g stroke={C.cyan} strokeWidth="5" opacity={.18 + u * .15}>
        {[0, 1, 2, 3, 4, 5].map((i) => {
          const x = ((i * 390 - t * 270) % 2300 + 2300) % 2300 - 160;
          return <path key={i} d={`M${x} ${330 + i * 57}h${115 + i * 17}`} />;
        })}
      </g>
      <g transform={`translate(${shake} 0)`}>
        {/* 终点门与旗帜，置于人物后 */}
        <g transform="translate(1490 0)">
          <rect x="-20" y="250" width="24" height="565" fill="#AAB4C8" />
          <rect x="-26" y="250" width="36" height="28" fill={C.yellow} />
          <path d="M5 275H210V465H5Z" fill="url(#checks23)" stroke={C.white} strokeWidth="6" />
          <path d="M-78 285V810M78 285V810" stroke={C.cyan} strokeWidth="10" opacity=".3" filter="url(#glow23)" />
          <rect x="-101" y="212" width="178" height="57" rx="8" fill={C.deep} stroke={C.cyan} strokeWidth="4" />
          <text x="-12" y="251" textAnchor="middle" fill={C.white} fontSize="30" fontWeight="900" fontFamily="monospace" letterSpacing="4">NEXT!</text>
        </g>

        {/* 跑道 */}
        <path d="M0 805H1920V1080H0Z" fill="url(#road23)" />
        <path d="M0 805H1920" stroke="#6F82C5" strokeWidth="6" />
        <path d="M0 960 1920 875M0 1040 1920 930" stroke="#2A3D78" strokeWidth="4" />
        <path d="M230 1080 500 805M760 1080 840 805M1320 1080 1180 805M1830 1080 1510 805" stroke="#2A3D78" strokeWidth="4" />

        {/* 加载条 */}
        <rect x="245" y="832" width="1430" height="35" rx="17" fill="#0B1234" stroke="#536AA8" strokeWidth="4" />
        <rect x="253" y="840" width={1414 * progress} height="19" rx="9" fill={C.cyan} filter="url(#glow23)" />
        <rect x="253" y="840" width={1414 * progress} height="7" rx="3" fill="#B9FFFF" opacity=".8" />
        <text x="250" y="908" fill="#91A5D6" fontSize="24" fontWeight="700" fontFamily="monospace" letterSpacing="3">LOADING NEXT ADVENTURE</text>
        <text x="1668" y="908" textAnchor="end" fill={C.yellow} fontSize="26" fontWeight="900" fontFamily="monospace">{Math.round(progress * 100)}%</text>

        {/* 技能跳板 */}
        {tileXs.map((x, i) => {
          const on = t > .28 + i * .39;
          const just = e.clamp01(1 - Math.abs(t - (.28 + i * .39)) * 3);
          return (
            <g key={x} transform={`translate(${x} ${790 - just * 12})`}>
              {on && <rect x="-63" y="-62" width="126" height="112" rx="18" fill={C.yellow} opacity={.16 + just * .25} filter="url(#soft23)" />}
              <path d="M-59-57H59V39L43 53H-59Z" fill={on ? C.yellow : '#2A3B70'} stroke={on ? '#FFF2A8' : '#657BAC'} strokeWidth="5" />
              <path d="M59 39 43 53V39Z" fill={on ? '#D7A928' : '#172554'} />
              <g transform="translate(0 -7) scale(.72)"><SkillIcon kind={i % 6} lit={on} /></g>
              {on && <path d="M-48 67H48" stroke={C.yellow} strokeWidth="5" opacity={.25 + just * .6} />}
            </g>
          );
        })}

        {/* 踩空裂口 */}
        <g transform="translate(1065 805)" opacity={.35 + stumble * .65}>
          <path d="M-48 0-24 24-5 5 18 31 43 0" fill="none" stroke={C.pink} strokeWidth="7" />
          <path d="M-25 28-8 57M20 34 32 59" stroke={C.pink} strokeWidth="5" />
        </g>

        {/* 人物：Sigma 始终略前，黄星头无遮挡 */}
        <Actor
          Character={Character}
          x={landisX}
          y={landisY}
          s={1.03}
          CharacterProps={{
            view: 'side',
            pose: 'stand',
            armL: [-48 + Math.sin(beat * Math.PI * 2) * 24, -62],
            armR: [-65 - reach * 20, -38 - reach * 32],
            headTurn: -8 * reach,
            tilt: 9 + stumble * 23 - arc * 7,
            mood: stumble > .35 ? 'surprised' : 'calm',
          }}
        />
        <Sigma x={sigmaX} y={sigmaY} run={beat} jump={arc} reach={reach} />

        {/* 拉住的白色手套之间的强调线 */}
        {reach > .35 && !jumping && (
          <g opacity={reach} filter="url(#glow23)">
            <path d={`M${landisX + 68} ${landisY - 245}Q${baseX} ${landisY - 285} ${sigmaX - 75} ${sigmaY - 116}`} fill="none" stroke={C.white} strokeWidth="5" strokeDasharray="10 12" />
            <PixelStar x={baseX + 8} y={landisY - 292} s={.75} />
          </g>
        )}

        {/* 起跳与落地星屑 */}
        {jumping && (
          <g opacity={Math.sin(jumpU * Math.PI)}>
            {[0, 1, 2, 3, 4].map((i) => <PixelStar key={i} x={baseX - 150 + i * 90} y={650 - arc * 170 - (i % 2) * 90} s={.45 + i * .06} />)}
            <path d={`M${baseX - 250} 745Q${baseX - 40} ${350 - arc * 60} ${baseX + 260} 710`} fill="none" stroke={C.yellow} strokeWidth="6" strokeDasharray="18 24" opacity=".45" />
          </g>
        )}
      </g>

      {/* 前景速度块，不压人物与歌词主体 */}
      <g opacity=".55">
        <path d="M0 1010H190L245 1080H0Z" fill="#0A1232" />
        <path d="M1750 1000H1920V1080H1690Z" fill="#0A1232" />
        <path d="M0 1010H190" stroke={C.violet} strokeWidth="8" />
        <path d="M1750 1000H1920" stroke={C.cyan} strokeWidth="8" />
      </g>
      <rect width="1920" height="1080" fill="none" stroke="#080E29" strokeWidth="34" opacity=".45" />
    </svg>
  );
}