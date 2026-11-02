import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';

export const BG = '#101A3E';
export const META = {19: {bg: '#101A3E'}};

const PixelHeart: React.FC<{x: number; y: number; s?: number; opacity?: number}> = ({
  x, y, s = 1, opacity = 1,
}) => (
  <g transform={`translate(${Math.round(x)} ${Math.round(y)}) scale(${s})`} opacity={opacity}>
    <path
      d="M8 0H24V8H32V0H48V8H56V24H48V32H40V40H32V48H24V40H16V32H8V24H0V8H8Z"
      fill="#151A35"
      transform="translate(-4 5) scale(1.14)"
    />
    <path
      d="M8 0H24V8H32V0H48V8H56V24H48V32H40V40H32V48H24V40H16V32H8V24H0V8H8Z"
      fill="#FF4F8B"
    />
    <path d="M8 8H24V16H16V24H8Z" fill="#FF9FBD"/>
    <path d="M40 8H48V16H40Z" fill="#FF77A5"/>
    <path d="M24 40H32V48H24Z" fill="#D92D6D"/>
  </g>
);

const StarIcon: React.FC<{x: number; y: number; s?: number; color?: string}> = ({
  x, y, s = 1, color = '#FFD93D',
}) => (
  <path
    d="M24 0H32V16H48V24H32V32H40V48H32V40H16V48H8V32H16V24H0V16H16V0H24Z"
    fill={color}
    transform={`translate(${x} ${y}) scale(${s})`}
  />
);

export const Shot19: React.FC = () => {
  const e = useE();
  const t = e.shotT;
  const c01 = (v: number) => Math.max(0, Math.min(1, v));
  const sg = (a: number, b: number) => c01((t - a) / (b - a));
  const eo = (v: number) => 1 - Math.pow(1 - v, 3);
  const io = (v: number) => v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2;
  const bk = (v: number) => {
    const q = v - 1;
    return 1 + 2.70158 * q * q * q + 1.70158 * q * q;
  };
  const px = (v: number) => Math.round(v / 4) * 4;

  const fill = io(sg(0.08, 1.38));
  const exp = Math.round(680 + 320 * fill);
  const barW = 1136 * (0.68 + 0.32 * fill);
  const maxFlash = t > 1.25 && t < 1.8 ? (Math.floor(t * 12) % 2 === 0 ? 1 : 0) : 0;

  const born = sg(1.22, 1.72);
  const travel = eo(sg(1.42, 2.35));
  const heartScale = born <= 0 ? 0 : Math.max(0, bk(born)) * 1.8;
  const hx = 510 + (942 - 510) * travel;
  const hy = 704 + (526 - 704) * travel - Math.sin(travel * Math.PI) * 72;

  const handIn = eo(sg(2.35, 2.92));
  const handOut = eo(sg(3.28, 3.92));
  const handX = px(1570 - 620 * handIn + 510 * handOut);
  const handY = px(410 + 102 * handIn - 32 * Math.sin(handIn * Math.PI) + (t > 2.92 && t < 3.2 ? 14 : 0));
  const tap = sg(2.91, 3.05) * (1 - sg(3.06, 3.23));

  const duplicate = eo(sg(3.12, 3.72));
  const collide = eo(sg(3.94, 4.22));
  const settle = eo(sg(4.30, 4.72));
  const leftX = 942 - 142 * duplicate + 126 * collide - 58 * settle;
  const rightX = 942 + 142 * duplicate - 110 * collide + 58 * settle;
  const heartY = 526 - 22 * Math.sin(duplicate * Math.PI) + 10 * Math.sin(collide * Math.PI);
  const impact = sg(4.15, 4.22) * (1 - sg(4.55, 4.95));
  const full = Math.max(0, bk(sg(4.18, 4.72)));

  const pulse = 1 + 0.045 * Math.sin(t * 9) * (t > 4.2 ? 1 : 0);
  const mood = t > 1.2 && t < 2.1 ? 'surprised' : t > 4.1 && t < 4.8 ? 'surprised' : 'calm';

  const sparks = [
    [-176, -98, '#FFD93D'], [-116, -156, '#FF6FA5'], [-24, -184, '#37E6E6'],
    [86, -164, '#FFD93D'], [174, -98, '#FF6FA5'], [190, 22, '#37E6E6'],
    [136, 112, '#FFD93D'], [-146, 104, '#FF6FA5'], [-198, 16, '#37E6E6'],
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <pattern id="scan" width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="4" fill="#FFFFFF" opacity="0.018"/>
        </pattern>
        <pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse">
          <path d="M64 0H0V64" fill="none" stroke="#34519A" strokeWidth="2" opacity="0.22"/>
        </pattern>
        <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <rect width="1920" height="1080" fill={BG}/>
      <rect width="1920" height="1080" fill="url(#grid)"/>
      <path d="M0 742H1920V1080H0Z" fill="#0B1230"/>
      <path d="M0 742H1920V758H0Z" fill="#243B6B"/>
      <path d="M0 758H1920V766H0Z" fill="#37E6E6" opacity="0.35"/>

      {[
        [82, 250, 1], [1710, 246, 0.8], [1800, 586, 0.65], [132, 594, 0.55],
        [1532, 796, 0.55], [1190, 246, 0.45], [330, 250, 0.45],
      ].map(([x, y, s], i) => (
        <g key={i} opacity={0.35 + 0.25 * Math.sin(t * 3 + i)}>
          <StarIcon x={x} y={y} s={s} color={i % 2 ? '#37E6E6' : '#FFD93D'}/>
        </g>
      ))}

      {/* Close-up game HUD */}
      <rect x="112" y="54" width="1696" height="142" fill="#080D24"/>
      <rect x="120" y="62" width="1680" height="126" fill="#243B6B"/>
      <rect x="132" y="74" width="1656" height="102" fill="#111A3D"/>
      <rect x="150" y="88" width="88" height="76" fill="#080D24"/>
      <StarIcon x={164} y={96} s={1.15}/>
      <text x="266" y="112" fill="#FFD93D" fontSize="30" fontWeight="900" fontFamily="monospace">SIGMA · EXP</text>
      <text x="1728" y="112" textAnchor="end" fill="#FFFFFF" fontSize="28" fontWeight="700" fontFamily="monospace">
        {exp} / 1000
      </text>
      <rect x="266" y="130" width="1160" height="30" fill="#050918"/>
      <rect x="274" y="138" width="1144" height="14" fill="#263157"/>
      <rect x="274" y="138" width={barW} height="14" fill={maxFlash ? '#FFFFFF' : '#FFD93D'}/>
      <rect x="274" y="138" width={barW} height="5" fill="#FFF3A0"/>
      {Array.from({length: 20}).map((_, i) => (
        <rect key={i} x={330 + i * 56} y="132" width="4" height="26" fill="#101A3E" opacity="0.7"/>
      ))}
      <rect x="1450" y="91" width="278" height="62" fill={fill >= 1 ? '#FFD93D' : '#263157'}/>
      <text x="1589" y="133" textAnchor="middle" fill={fill >= 1 ? '#172554' : '#8FA4D8'} fontSize="30" fontWeight="900" fontFamily="monospace">
        {fill >= 1 ? 'LEVEL READY!' : 'LOADING…'}
      </text>

      {/* Sigma, held large in the left side of the close shot */}
      <g transform="translate(510 1020) scale(1.48)">
        <Character
          pose="stand"
          armL={[-18, -42]}
          armR={t > 4.1 ? [-58, -48] : [-12, -30]}
          mood={mood}
          headTurn={t > 2.1 ? 7 : 0}
        />
      </g>

      {/* Small experience pixels still flying into the filled gauge */}
      {t < 1.55 && [0, 1, 2, 3, 4].map((i) => {
        const u = (t * 0.85 + i * 0.19) % 1;
        return (
          <rect
            key={i}
            x={px(600 + u * 790)}
            y={px(610 - u * 450 - Math.sin(u * Math.PI) * 90)}
            width="14"
            height="14"
            fill="#FFD93D"
            opacity={1 - u * 0.6}
          />
        );
      })}

      {/* Heart born at Sigma's chest */}
      {born > 0 && duplicate < 0.02 && (
        <g filter="url(#glow)">
          <PixelHeart x={hx} y={hy} s={heartScale}/>
        </g>
      )}

      {/* Landis appears as a playful glove-cursor, keeping the shot tightly framed */}
      <g transform={`translate(${handX} ${handY}) scale(${1 - tap * 0.07})`}>
        <path d="M152 38H246V142H152Z" fill="#111318" transform="translate(8 8)"/>
        <path d="M152 30H246V134H152Z" fill="#243B6B"/>
        <path d="M174 30H190V134H174Z" fill="#36538B"/>
        <path
          d="M0 40H70V20H94V0H118V16H110V36H142V44H158V60H168V116H150V132H86V116H64V92H46V66H0Z"
          fill="#111318"
          transform="translate(7 8)"
        />
        <path
          d="M0 40H70V20H94V0H118V16H110V36H142V44H158V60H168V116H150V132H86V116H64V92H46V66H0Z"
          fill="#FFFFFF"
        />
        <path d="M70 40H110V56H70Z" fill="#DDE8FF"/>
        <path d="M86 92H150V116H134V124H86Z" fill="#DDE8FF"/>
        <rect x="0" y="40" width="18" height="26" fill="#F5FAFF"/>
      </g>
      <g opacity={1 - handOut}>
        <rect x={handX + 184} y={handY - 46} width="226" height="42" fill="#080D24"/>
        <text x={handX + 297} y={handY - 17} textAnchor="middle" fill="#37E6E6" fontSize="23" fontWeight="800" fontFamily="monospace">
          LANDIS · TAP
        </text>
      </g>

      {/* Tap ripple and duplication */}
      {tap > 0 && (
        <g opacity={tap} stroke="#37E6E6" strokeWidth="8" fill="none">
          <path d={`M${handX - 24} ${handY + 20}h-28v72h28`}/>
          <path d={`M${handX - 44} ${handY + 4}h-44v104h44`}/>
        </g>
      )}
      {duplicate >= 0.02 && (
        <g filter="url(#glow)">
          <g transform={`translate(${px(leftX)} ${px(heartY)}) scale(${pulse})`}>
            <PixelHeart x={0} y={0} s={1.8}/>
          </g>
          <g transform={`translate(${px(rightX)} ${px(heartY)}) scale(${pulse})`}>
            <PixelHeart x={0} y={0} s={1.8}/>
          </g>
        </g>
      )}

      {/* Copy sparkles */}
      {duplicate > 0.05 && duplicate < 0.95 && (
        <g fill="#FFFFFF">
          <rect x="926" y="480" width="14" height="42"/>
          <rect x="912" y="494" width="42" height="14"/>
          <rect x="1000" y="574" width="12" height="32"/>
          <rect x="990" y="584" width="32" height="12"/>
        </g>
      )}

      {/* Hearts bump: arcade impact and full-health announcement */}
      {impact > 0 && (
        <g transform="translate(1000 548)" opacity={impact}>
          {sparks.map(([x, y, color], i) => {
            const k = 0.45 + sg(4.16, 4.65) * 0.75;
            return (
              <g key={i} transform={`translate(${x * k} ${y * k}) rotate(${i * 23})`}>
                <rect x="-10" y="-22" width="20" height="44" fill={color}/>
                <rect x="-22" y="-10" width="44" height="20" fill={color}/>
              </g>
            );
          })}
        </g>
      )}

      {t > 4.16 && (
        <g transform={`translate(1280 356) scale(${full})`}>
          <rect x="-286" y="-80" width="572" height="174" fill="#080D24"/>
          <rect x="-274" y="-68" width="548" height="150" fill="#FF4F8B"/>
          <rect x="-258" y="-52" width="516" height="118" fill="#FFD93D"/>
          <rect x="-244" y="-38" width="488" height="90" fill="#172554"/>
          <text x="0" y="27" textAnchor="middle" fill="#FFFFFF" stroke="#161A2B" strokeWidth="5" paintOrder="stroke" fontSize="76" fontWeight="1000" fontFamily="monospace">
            FULL HP!
          </text>
          <rect x="-180" y="104" width="360" height="42" fill="#37E6E6"/>
          <text x="0" y="134" textAnchor="middle" fill="#102044" fontSize="23" fontWeight="900" fontFamily="monospace">
            NEXT STAGE UNLOCKED
          </text>
        </g>
      )}

      {/* Tiny status panel, not a subtitle */}
      <g transform="translate(1310 742)">
        <rect x="0" y="0" width="414" height="154" fill="#080D24"/>
        <rect x="10" y="10" width="394" height="134" fill="#1D2B57"/>
        <text x="30" y="48" fill="#8FA4D8" fontSize="23" fontFamily="monospace">PARTNER STATUS</text>
        <text x="30" y="91" fill="#FFFFFF" fontSize="31" fontWeight="900" fontFamily="monospace">HP</text>
        {Array.from({length: 8}).map((_, i) => (
          <rect key={i} x={100 + i * 32} y="66" width="24" height="30" fill={t > 4.16 || i < 3 ? '#FF4F8B' : '#384469'}/>
        ))}
        <text x="30" y="126" fill="#FFD93D" fontSize="21" fontFamily="monospace">SIGMA + LANDIS  ♥  LINKED</text>
      </g>

      <rect width="1920" height="1080" fill="url(#scan)" pointerEvents="none"/>
      <path d="M0 0H1920V18H0ZM0 1062H1920V1080H0Z" fill="#080D24"/>
    </svg>
  );
};

export default Shot19;