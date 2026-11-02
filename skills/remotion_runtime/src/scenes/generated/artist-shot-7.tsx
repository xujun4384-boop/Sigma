import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#172554';
export const META = {7: {bg: '#172554'}};

const lerp = (a: number, b: number, u: number) => a + (b - a) * u;
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const smooth = (v: number) => {
  const x = clamp01(v);
  return x * x * (3 - 2 * x);
};

const PixelSpark = ({x, y, c = '#FFD93D', s = 1}: {x: number; y: number; c?: string; s?: number}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} fill={c}>
    <rect x="-4" y="-18" width="8" height="36" />
    <rect x="-18" y="-4" width="36" height="8" />
    <rect x="-4" y="-4" width="8" height="8" fill="#FFF7C2" />
  </g>
);

const Drone = ({x, y, tilt, t}: {x: number; y: number; tilt: number; t: number}) => (
  <g transform={`translate(${x} ${y}) rotate(${tilt})`}>
    <g transform="translate(-142 -48)">
      <rect x="-48" y="-34" width="96" height="68" fill="#596579" stroke="#161A2B" strokeWidth="8" />
      <rect x="-34" y="-22" width="68" height="44" fill="#25324E" />
      <g transform={`rotate(${t * 520})`}>
        <rect x="-43" y="-6" width="86" height="12" fill="#C8D2E2" />
        <rect x="-6" y="-28" width="12" height="56" fill="#C8D2E2" />
      </g>
      <rect x="-8" y="-8" width="16" height="16" fill="#37E6E6" />
    </g>
    <g transform="translate(142 -48)">
      <rect x="-48" y="-34" width="96" height="68" fill="#596579" stroke="#161A2B" strokeWidth="8" />
      <rect x="-34" y="-22" width="68" height="44" fill="#25324E" />
      <g transform={`rotate(${-t * 520})`}>
        <rect x="-43" y="-6" width="86" height="12" fill="#C8D2E2" />
        <rect x="-6" y="-28" width="12" height="56" fill="#C8D2E2" />
      </g>
      <rect x="-8" y="-8" width="16" height="16" fill="#37E6E6" />
    </g>
    <path d="M-92-25V3H92V-25" fill="none" stroke="#161A2B" strokeWidth="12" />
    <rect x="-106" y="-30" width="212" height="116" rx="8" fill="#AAB4C8" stroke="#161A2B" strokeWidth="9" />
    <rect x="-88" y="-14" width="176" height="56" fill="#8795AA" />
    <rect x="-64" y="3" width="128" height="17" fill="#172554" />
    <rect x="-54" y="7" width={72 + Math.sin(t * 8) * 12} height="9" fill="#37E6E6" />
    <rect x="-82" y="56" width="38" height="12" fill="#596579" />
    <rect x="44" y="56" width="38" height="12" fill="#596579" />
    <rect x="-30" y="86" width="60" height="24" fill="#596579" stroke="#161A2B" strokeWidth="7" />
    <path d="M-20 107V141H-46M20 107V141H46" fill="none" stroke="#AAB4C8" strokeWidth="12" strokeLinejoin="miter" />
    <rect x="-18" y="-57" width="36" height="27" fill="#596579" stroke="#161A2B" strokeWidth="7" />
    <rect x="-7" y="-76" width="14" height="20" fill="#F4C95D" />
  </g>
);

export const Shot7 = () => {
  const e = useE();
  const t = e.shotT;
  const bob = Math.round(Math.sin(t * 5.2) * 5);

  const arrive = smooth(t / 1.05);
  const droneX = lerp(-230, 405, arrive) + (t > 4.7 ? -smooth((t - 4.7) / 1.3) * 35 : 0);
  const droneY = 315 + bob;
  const droneTilt = lerp(-9, 0, arrive) + Math.sin(t * 3) * 1.5;

  const handoff = smooth((t - 0.78) / 0.72);
  const fold = smooth((t - 1.55) / 1.55);
  const sticker = smooth((t - 3.05) / 0.28);
  const launch = smooth((t - 4.18) / 1.48);

  const heldX = lerp(droneX + 4, 930, handoff);
  const heldY = lerp(droneY + 157, 526, handoff);
  const planeX = lerp(930, 270, launch);
  const planeY = lerp(526, 245, launch) - Math.sin(launch * Math.PI) * 105;
  const cardX = t < 4.18 ? heldX : planeX;
  const cardY = t < 4.18 ? heldY : planeY;
  const cardRot = t < 4.18 ? lerp(3, -5, handoff) : lerp(-5, -17, launch);
  const cardScale = lerp(1, 0.9, fold);

  const start = [
    [-150, -90], [150, -90], [150, 90], [-150, 90],
  ];
  const end = [
    [180, 0], [-130, -82], [-58, 0], [-130, 82],
  ];
  const pts = start.map((p, i) => `${lerp(p[0], end[i][0], fold)},${lerp(p[1], end[i][1], fold)}`).join(' ');

  const blow = clamp01((t - 3.55) / 0.7) * (1 - clamp01((t - 4.32) / 0.2));
  const receiving = t < 1.6;
  const armL: [number, number] = receiving ? [-68, -52] : t < 3.5 ? [-52, -82] : [-38, -58];
  const armR: [number, number] = receiving ? [-72, -48] : t < 3.5 ? [-55, -84] : [-82, -54];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <pattern id="wallPixels" width="48" height="48" patternUnits="userSpaceOnUse">
          <rect width="48" height="48" fill="#172554" />
          <rect x="0" y="0" width="24" height="4" fill="#213567" />
          <rect x="28" y="28" width="12" height="4" fill="#213567" />
        </pattern>
        <pattern id="goldPixels" width="16" height="16" patternUnits="userSpaceOnUse">
          <rect width="16" height="16" fill="#F4C95D" />
          <rect width="8" height="8" fill="#FFE88A" />
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill={BG} />
      <rect width="1920" height="1080" fill="url(#wallPixels)" />

      {/* 后景：邮件管道与像素化系统城 */}
      <g opacity="0.9">
        <path d="M0 180H240V80H530V180H720" fill="none" stroke="#0D1738" strokeWidth="76" />
        <path d="M0 180H240V80H530V180H720" fill="none" stroke="#2878F0" strokeWidth="48" />
        <path d="M0 180H240V80H530V180H720" fill="none" stroke="#44A5FF" strokeWidth="8" strokeDasharray="28 22" />
        {[90, 330, 585].map((x) => (
          <g key={x} transform={`translate(${x} ${x === 330 ? 80 : x === 585 ? 135 : 180})`}>
            <rect x="-13" y="-39" width="26" height="78" fill="#173A6B" />
            <rect x="-6" y="-29" width="12" height="58" fill="#37E6E6" opacity="0.55" />
          </g>
        ))}
      </g>

      <g transform="translate(1440 105)">
        <rect width="390" height="210" fill="#101B3E" stroke="#334D86" strokeWidth="8" />
        <rect x="22" y="24" width="346" height="42" fill="#213567" />
        <rect x="38" y="36" width="18" height="18" fill="#FF5C7A" />
        <rect x="68" y="36" width="18" height="18" fill="#FFD93D" />
        <rect x="98" y="36" width="18" height="18" fill="#44D17A" />
        <text x="30" y="111" fill="#8DA9DA" fontSize="27" fontFamily="monospace" fontWeight="bold">INCOMING MAIL</text>
        <text x="30" y="161" fill="#37E6E6" fontSize="34" fontFamily="monospace" fontWeight="bold">1 GOLDEN INVITE</text>
        <rect x="30" y="180" width="330" height="8" fill="#213567" />
        <rect x="30" y="180" width={Math.min(330, t * 85)} height="8" fill="#FFD93D" />
      </g>

      <g fill="#2A4075" opacity="0.8">
        <rect x="52" y="890" width="170" height="190" />
        <rect x="242" y="940" width="120" height="140" />
        <rect x="1510" y="885" width="150" height="195" />
        <rect x="1680" y="820" width="190" height="260" />
      </g>
      <g fill="#37E6E6" opacity="0.42">
        <rect x="82" y="924" width="32" height="18" />
        <rect x="142" y="924" width="32" height="18" />
        <rect x="1550" y="920" width="40" height="18" />
        <rect x="1720" y="860" width="40" height="18" />
        <rect x="1790" y="860" width="40" height="18" />
      </g>

      {/* 信使无人机 */}
      <Drone x={droneX} y={droneY} tilt={droneTilt} t={t} />

      {t < 0.9 && (
        <g transform={`translate(${droneX} ${droneY + 150})`} opacity={1 - handoff}>
          <path d="M-125-65H125V65H-125Z" fill="#FFF4CF" stroke="#161A2B" strokeWidth="9" />
          <path d="M-116-56H116V56H-116Z" fill="none" stroke="#F4C95D" strokeWidth="9" />
        </g>
      )}

      {/* Sigma：近景接信、折纸、嘟嘴轻吹 */}
      <g transform={`translate(0 ${Math.round(Math.sin(t * 4.2) * 2)})`}>
        <Actor
          Character={Character}
          x={1160}
          y={1000}
          s={1.48}
          armL={armL}
          armR={armR}
          headTurn={-9}
          tilt={t > 3.5 && t < 4.5 ? -4 : 0}
          mood={t > 3.55 && t < 4.35 ? 'surprised' : 'calm'}
        />
      </g>

      {/* 吹气像素，短促向左 */}
      {blow > 0 && (
        <g opacity={blow} fill="#B8FFFF">
          {[0, 1, 2, 3].map((i) => {
            const q = (t * 1.8 + i * 0.23) % 1;
            return (
              <g key={i} transform={`translate(${1080 - q * 190} ${430 + i * 17 - q * 20})`}>
                <rect width={28 - i * 3} height="8" />
                <rect x="8" y="-8" width="8" height="8" opacity="0.6" />
              </g>
            );
          })}
        </g>
      )}

      {/* 邀请函连续变形成纸飞机 */}
      <g transform={`translate(${cardX} ${cardY}) rotate(${cardRot}) scale(${cardScale})`}>
        <polygon points={pts} fill="#FFF4CF" stroke="#161A2B" strokeWidth="11" strokeLinejoin="miter" />
        <polygon points={pts} fill="none" stroke="url(#goldPixels)" strokeWidth="7" strokeLinejoin="miter" />

        {fold < 0.72 && (
          <g opacity={1 - fold / 0.72}>
            <path d="M-112-48H112M-112 48H112" stroke="#F4C95D" strokeWidth="5" />
            <path d="M0-70V70" stroke="#D7A93B" strokeWidth="4" strokeDasharray="12 8" />
            <text x="0" y="-4" textAnchor="middle" fill="#8A5B16" fontSize="30" fontFamily="monospace" fontWeight="bold">INVITATION</text>
            <text x="0" y="31" textAnchor="middle" fill="#B07A20" fontSize="18" fontFamily="monospace">BIG AGENT CORP.</text>
          </g>
        )}

        {fold > 0.45 && (
          <g opacity={(fold - 0.45) / 0.55}>
            <path d="M-119-71L-49-1L167 0" fill="none" stroke="#D7A93B" strokeWidth="5" />
            <path d="M-119 70L-49 1L167 0" fill="none" stroke="#F4C95D" strokeWidth="5" />
            <path d="M-49 0L68 0" stroke="#FFF9E8" strokeWidth="5" />
          </g>
        )}

        {sticker > 0 && (
          <g transform={`translate(10 -25) scale(${0.25 + sticker * 0.75}) rotate(-8)`}>
            <rect x="-48" y="-27" width="96" height="54" fill="#FF5C7A" stroke="#161A2B" strokeWidth="6" />
            <rect x="-40" y="-19" width="80" height="38" fill="#FF8BA1" />
            <text x="0" y="10" textAnchor="middle" fill="#FFFFFF" fontSize="30" fontFamily="monospace" fontWeight="900">THX!</text>
          </g>
        )}
      </g>

      {/* 折纸与贴纸的喜剧节拍 */}
      {t > 1.55 && t < 3.25 && (
        <g>
          <PixelSpark x={780} y={410} s={0.65 + Math.sin(t * 12) * 0.1} />
          <PixelSpark x={1090} y={570} s={0.45} c="#37E6E6" />
          <rect x={748} y={550} width="18" height="18" fill="#F4C95D" />
          <rect x={1050} y={390} width="14" height="14" fill="#FFF4CF" />
        </g>
      )}
      {t > 3.02 && t < 3.75 && (
        <g>
          <PixelSpark x={1020} y={430} s={0.8} c="#FF8BA1" />
          <PixelSpark x={860} y={455} s={0.5} />
        </g>
      )}

      {/* 返回来路的像素速度线 */}
      {launch > 0.04 && (
        <g opacity={Math.min(1, launch * 3)} fill="#37E6E6">
          <rect x={planeX + 190} y={planeY - 26} width={120 * launch} height="10" />
          <rect x={planeX + 230} y={planeY + 18} width={82 * launch} height="8" />
          <rect x={planeX + 150} y={planeY + 54} width={58 * launch} height="8" fill="#FFD93D" />
        </g>
      )}

      {/* 前景桌沿，提供近景遮挡关系 */}
      <path d="M0 1012H610V982H1320V1012H1920V1080H0Z" fill="#0D1738" />
      <rect x="0" y="1012" width="1920" height="18" fill="#2878F0" />
      <rect x="1400" y="1038" width="260" height="18" fill="#213567" />
      <rect x="1400" y="1038" width={80 + e.shotU * 180} height="18" fill="#FFD93D" />
    </svg>
  );
};