import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#172554';
export const META = {18: {bg: '#172554'}};

const PixelHeart = ({x, y, s = 1, color = '#FF6B9D', opacity = 1}: {
  x: number; y: number; s?: number; color?: string; opacity?: number;
}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
    <path d="M-30-20h20v-10h20v10h20v20H20v10H10v10h-20V10h-20z" fill={color}/>
    <rect x="-20" y="-20" width="10" height="10" fill="#FFFFFF" opacity=".55"/>
  </g>
);

const Taxi = ({x, y, rotate, door, luggage}: {
  x: number; y: number; rotate: number; door: number; luggage: number;
}) => (
  <g transform={`translate(${x} ${y}) rotate(${rotate})`}>
    <ellipse cx="0" cy="82" rx="190" ry="29" fill="#071126" opacity=".42"/>

    {luggage > 0 && (
      <g transform={`translate(${-34 - luggage * 92} ${32 + luggage * 86}) rotate(${-10 + luggage * 16})`}>
        <rect x="-30" y="-62" width="60" height="70" rx="9" fill="#F04E78"/>
        <rect x="-22" y="-54" width="44" height="53" rx="5" fill="#C73565"/>
        <rect x="-13" y="-76" width="26" height="18" rx="7" fill="none" stroke="#FFD8E3" strokeWidth="6"/>
        <rect x="-21" y="-43" width="42" height="6" fill="#FF8BA8"/>
        <rect x="-5" y="-57" width="10" height="56" fill="#FFB3C6" opacity=".55"/>
        <circle cx="-18" cy="12" r="6" fill="#111A31"/>
        <circle cx="18" cy="12" r="6" fill="#111A31"/>
      </g>
    )}

    <path d="M-177 25v-53l45-13 48-66h128l62 65 58 16 19 51v35h-360z" fill="#F7B818"/>
    <path d="M-177 25v-53l45-13 48-66h128l62 65 58 16 19 51" fill="none" stroke="#FFE77B" strokeWidth="8" strokeLinejoin="round"/>
    <path d="M-72-94h106l48 53h-202z" fill="#172F54"/>
    <path d="M-57-82h36v38h-79zM-8-82h35l39 38H-8z" fill="#66DDEA"/>
    <path d="M-52-76h25v8h-32zM0-76h24l12 10H0z" fill="#D8FFFF" opacity=".75"/>
    <rect x="-28" y="-135" width="82" height="34" rx="7" fill="#FFE36A"/>
    <rect x="-20" y="-128" width="66" height="20" rx="3" fill="#172554"/>
    <text x="13" y="-113" textAnchor="middle" fill="#FFE36A" fontSize="15" fontWeight="900" fontFamily="monospace">TAXI</text>

    <rect x="-170" y="-13" width="337" height="56" fill="#FFD43B"/>
    {Array.from({length: 12}).map((_, i) => (
      <rect key={i} x={-155 + i * 27} y="-10" width="14" height="14" fill={i % 2 ? '#FFF2B5' : '#203052'}/>
    ))}
    <rect x="143" y="-17" width="30" height="22" rx="5" fill="#FFF7C7"/>
    <rect x="-178" y="-12" width="18" height="25" rx="4" fill="#FF5C5C"/>
    <rect x="-190" y="38" width="382" height="22" rx="8" fill="#D88A13"/>
    <rect x="174" y="43" width="30" height="12" rx="4" fill="#C9D5E7"/>

    <g transform={`translate(-70 0) skewY(${-door * 19}) scale(${1 - door * .48} 1)`}>
      <path d="M-48-41H24V45H-48z" fill="#F5B321" stroke="#9D6717" strokeWidth="5"/>
      <path d="M-39-34H15V-5H-39z" fill="#FFD95A"/>
      <rect x="-31" y="-22" width="25" height="5" rx="2" fill="#263A5E"/>
    </g>

    <g>
      <circle cx="-112" cy="55" r="39" fill="#10172A"/>
      <circle cx="-112" cy="55" r="22" fill="#AAB4C8"/>
      <circle cx="-112" cy="55" r="9" fill="#415473"/>
      <circle cx="112" cy="55" r="39" fill="#10172A"/>
      <circle cx="112" cy="55" r="22" fill="#AAB4C8"/>
      <circle cx="112" cy="55" r="9" fill="#415473"/>
    </g>
  </g>
);

export function Shot18() {
  const e = useE();
  const t = e.shotT;
  const drive = e.easeIO(e.seg(.25, 3.75, t));
  const stop = e.seg(3.65, 4.05, t);
  const door = e.easeOut(e.seg(4.0, 4.48, t));
  const luggage = e.back(e.seg(4.28, 5.02, t));
  const wave = Math.sin(t * 7.4);
  const blink = .55 + .45 * Math.sin(t * 5.5);
  const camera = 1.012 + e.shotU * .012;

  const tx = e.lerp(600, 1135, drive) + Math.sin(drive * Math.PI) * 24;
  const ty = e.lerp(714, 555, drive) - Math.sin(drive * Math.PI) * 105 + Math.sin(stop * Math.PI) * 7;
  const tr = e.lerp(-18, -3, drive);

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="mapBg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#243B78"/>
          <stop offset=".58" stopColor="#172554"/>
          <stop offset="1" stopColor="#101A3B"/>
        </linearGradient>
        <linearGradient id="road" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#263754"/>
          <stop offset="1" stopColor="#17243E"/>
        </linearGradient>
        <radialGradient id="warmGlow">
          <stop offset="0" stopColor="#FFD93D" stopOpacity=".42"/>
          <stop offset="1" stopColor="#FFD93D" stopOpacity="0"/>
        </radialGradient>
        <pattern id="grid" width="64" height="64" patternUnits="userSpaceOnUse">
          <path d="M64 0H0V64" fill="none" stroke="#75A3DD" strokeOpacity=".08" strokeWidth="2"/>
          <rect x="5" y="5" width="4" height="4" fill="#A8C7F0" opacity=".09"/>
        </pattern>
        <filter id="softGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="smallGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="5" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <rect width="1920" height="1080" fill="url(#mapBg)"/>
      <rect width="1920" height="1080" fill="url(#grid)"/>

      <g transform={`translate(960 540) scale(${camera}) translate(-960 -540)`}>
        <path d="M0 164L205 103l185 49 225-105 215 73 201-73 256 82 236-70 293 84 304-57v642l-212 99-252-37-203 87-229-65-218 74-229-72-253 78-233-69L0 891z"
          fill="#214568" stroke="#315D7D" strokeWidth="8"/>
        <path d="M0 205l220-57 168 46 232-100 205 69 207-70 247 78 240-67 286 79 315-57" fill="none" stroke="#4E7E96" strokeWidth="4" opacity=".5"/>

        <g opacity=".8">
          <path d="M77 255h101v-49h78v108H77z" fill="#172B50"/>
          <path d="M95 238h18v18H95zm39 0h18v18h-18zm66-13h19v19h-19zM96 278h18v18H96zm104-12h19v19h-19z" fill="#54D8C5" opacity=".55"/>
          <path d="M1580 153h88V93h69v118h-157z" fill="#192D50"/>
          <path d="M1600 172h18v18h-18zm42 0h18v18h-18zm43-58h18v18h-18zm0 40h18v18h-18z" fill="#FFD43B" opacity=".55"/>
          <path d="M885 154h69V91h79v105H885z" fill="#1B3158"/>
          <path d="M905 126h18v18h-18zm48-18h18v18h-18zm29 43h18v18h-18z" fill="#6A9CF8" opacity=".6"/>
        </g>

        <path d="M-70 884C225 852 363 777 495 709C653 628 703 464 903 455C1124 445 1242 581 1437 457C1572 371 1690 258 1990 249"
          fill="none" stroke="#0D1730" strokeWidth="190" strokeLinecap="round"/>
        <path d="M-70 884C225 852 363 777 495 709C653 628 703 464 903 455C1124 445 1242 581 1437 457C1572 371 1690 258 1990 249"
          fill="none" stroke="url(#road)" strokeWidth="162" strokeLinecap="round"/>
        <path d="M495 709C560 583 538 414 446 282" fill="none" stroke="#0D1730" strokeWidth="156" strokeLinecap="round"/>
        <path d="M495 709C560 583 538 414 446 282" fill="none" stroke="#23344F" strokeWidth="130" strokeLinecap="round"/>

        <path d="M-30 883C230 847 366 776 495 709C653 628 703 464 903 455C1124 445 1242 581 1437 457C1572 371 1690 258 1940 250"
          fill="none" stroke="#91A9BC" strokeOpacity=".45" strokeWidth="5" strokeDasharray="28 30"/>
        <path d="M495 709C560 583 538 414 446 282" fill="none" stroke="#91A9BC" strokeOpacity=".25" strokeWidth="5" strokeDasharray="25 29"/>

        <path d="M501 697C651 617 703 486 892 476C1080 466 1183 573 1351 493"
          fill="none" stroke="#42E8DC" strokeOpacity=".18" strokeWidth="22" strokeLinecap="round"/>
        <path d="M501 697C651 617 703 486 892 476C1080 466 1183 573 1351 493"
          fill="none" stroke="#62F5E8" strokeWidth="6" strokeDasharray="3 24" strokeLinecap="round">
          <animate attributeName="stroke-dashoffset" values="0;-54" dur="1.2s" repeatCount="indefinite"/>
        </path>

        <g transform="translate(1065 617) rotate(-4)">
          <rect x="-145" y="-72" width="330" height="150" rx="18" fill="none" stroke="#66F2D8" strokeWidth="5" strokeDasharray="25 15" opacity={.35 + drive * .5}/>
          <path d="M-145-34v-38h38M147-72h38v38M185 40v38h-38M-107 78h-38V40" fill="none" stroke="#B7FFE9" strokeWidth="8"/>
          <text x="22" y="112" textAnchor="middle" fill="#9EF8E5" fontFamily="monospace" fontWeight="800" fontSize="20" letterSpacing="3">
            {drive > .985 ? 'PARKED • 0.0 m' : 'DROP-OFF'}
          </text>
        </g>

        <g transform="translate(1475 310)">
          <ellipse cx="0" cy="164" rx="235" ry="55" fill="#102643" opacity=".5"/>
          <circle cx="0" cy="10" r="220" fill="url(#warmGlow)"/>
          <path d="M-160 143V-7l53-55h213l55 55v150" fill="#283B68" stroke="#55739B" strokeWidth="8"/>
          <path d="M-185-4L-113-88H115L185-4 146 24-146 24z" fill="#FF6B9D"/>
          <path d="M-177-4h354l-31 28h-292z" fill="#FF91B5"/>
          {Array.from({length: 7}).map((_, i) => (
            <path key={i} d={`M${-158 + i * 48} 0h26l-7 42h-28z`} fill={i % 2 ? '#FFF0C5' : '#E54B83'}/>
          ))}
          <rect x="-117" y="54" width="88" height="89" rx="5" fill="#132B50"/>
          <rect x="-105" y="65" width="64" height="51" fill="#64DDE1" opacity=".8"/>
          <path d="M-73 65v51M-105 90h64" stroke="#D9FFFF" strokeWidth="5"/>
          <rect x="20" y="49" width="87" height="94" rx="7" fill="#162441"/>
          <rect x="32" y="62" width="63" height="81" fill="#FFD56A" opacity=".75"/>
          <circle cx="82" cy="105" r="5" fill="#6F412E"/>
          <rect x="-112" y="-68" width="224" height="43" rx="9" fill="#172554" stroke="#FFD43B" strokeWidth="4"/>
          <text x="0" y="-39" textAnchor="middle" fill="#FFE78A" fontFamily="monospace" fontSize="22" fontWeight="900" letterSpacing="2">HANDMADE BAY</text>
          <PixelHeart x={0} y={-124} s={.8 + Math.sin(t * 3) * .025} color="#FF7EAA"/>
          <g filter="url(#smallGlow)">
            <rect x="-130" y="143" width="260" height="10" rx="5" fill="#FFD93D" opacity={blink * .45}/>
          </g>
        </g>

        <g transform="translate(655 492)">
          <path d="M-126 58h255v51h-255z" fill="#17243D"/>
          {[
            [-108, 24, 55], [-47, -8, 65], [25, 17, 52], [82, -28, 62], [-18, 62, 48]
          ].map((b, i) => (
            <g key={i} transform={`translate(${b[0]} ${b[1]})`}>
              <rect width={b[2]} height={b[2]} fill="#E87532"/>
              <path d={`M0 0h${b[2]}v13H13v${b[2] - 13}H0z`} fill="#FFAB45"/>
              <path d={`M13 ${b[2] - 13}h${b[2] - 13}v13z`} fill="#A8482C"/>
            </g>
          ))}
          <path d="M-151-54h302" stroke="#FFCB4C" strokeWidth="17" strokeDasharray="38 22"/>
          <path d="M-137-54v145M137-54v145" stroke="#76859D" strokeWidth="12"/>
          <rect x="-72" y="-115" width="144" height="48" rx="5" fill="#253652" stroke="#FFCB4C" strokeWidth="4"/>
          <text x="0" y="-84" textAnchor="middle" fill="#FFDA73" fontFamily="monospace" fontWeight="900" fontSize="21">PIXEL WORK</text>
        </g>

        <g transform="translate(423 279)">
          <path d="M0 0v126" stroke="#90A2B9" strokeWidth="11"/>
          <path d="M-79-8H83L54 46H-79z" fill="#314766" stroke="#69809D" strokeWidth="4"/>
          <text x="-5" y="26" textAnchor="middle" fill="#AFC1D6" fontFamily="monospace" fontSize="21" fontWeight="800">OLD SERVER</text>
          <path d="M-63 75H58v42H-63z" fill="#E66C3F"/>
          <text x="-2" y="103" textAnchor="middle" fill="#FFF0CE" fontFamily="monospace" fontSize="18" fontWeight="900">CLOSED</text>
        </g>

        <g opacity=".8">
          <path d="M126 636h31v-31h31v31h31v31h-31v31h-31v-31h-31z" fill="#34775F"/>
          <path d="M1740 640h28v-28h28v28h28v28h-28v28h-28v-28h-28z" fill="#34775F"/>
          <path d="M1600 750h24v-24h24v24h24v24h-24v24h-24v-24h-24z" fill="#2B695A"/>
          <rect x="184" y="720" width="54" height="16" fill="#3A7767"/>
          <rect x="1660" y="549" width="72" height="17" fill="#3A7767"/>
        </g>

        {drive < .96 && [0, 1, 2, 3].map(i => {
          const q = (t * 1.8 + i * .23) % 1;
          return <rect key={i} x={tx - 200 - q * 95} y={ty + 52 + i * 7} width={18 - q * 10} height={18 - q * 10}
            fill="#B4D5D1" opacity={(1 - q) * .28}/>;
        })}

        <Taxi x={tx} y={ty} rotate={tr} door={door} luggage={Math.max(0, luggage)}/>

        {door > .75 && (
          <g opacity={e.seg(4.6, 5.2, t)}>
            <path d="M962 684l-12 20M1000 692v24M1033 676l15 19" stroke="#FFE890" strokeWidth="7" strokeLinecap="square"/>
            <rect x="922" y="642" width="15" height="15" fill="#FF8BAC"/>
            <rect x="1052" y="638" width="12" height="12" fill="#62F5E8"/>
          </g>
        )}

        <g transform="translate(445 670)">
          <path d="M0 0v-239" stroke="#F4F7FF" strokeWidth="10"/>
          <path d="M5-235C53-253 82-214 132-235v93C81-122 53-161 5-142z" fill="#37D9D2" stroke="#B8FFF4" strokeWidth="4">
            <animate attributeName="d"
              values="M5-235C53-253 82-214 132-235v93C81-122 53-161 5-142z;M5-235C48-213 91-255 132-225v93C91-151 48-119 5-142z;M5-235C53-253 82-214 132-235v93C81-122 53-161 5-142z"
              dur="1.1s" repeatCount="indefinite"/>
          </path>
          <path d="M38-211l20 20 39-42" fill="none" stroke="#173A6B" strokeWidth="12" strokeLinecap="square" strokeLinejoin="miter"/>
          <rect x="-13" y="-4" width="27" height="14" fill="#DFF9FF"/>
        </g>

        <g transform={`translate(0 ${Math.sin(t * 6.2) * 3})`}>
          <Actor Character={Character} x={350} y={825} s={.82}
            armL={[-18, -28]} armR={[-72 + wave * 10, -38 - wave * 14]}
            headTurn={8} tilt={-3} mood="calm"/>
        </g>

        <g transform="translate(287 859)">
          <ellipse cx="63" cy="8" rx="92" ry="20" fill="#0C1A32" opacity=".35"/>
          <path d="M0 0h126" stroke="#4DE2D5" strokeWidth="5" strokeDasharray="8 12" opacity=".55"/>
        </g>

        <g transform="translate(74 70)">
          <rect width="414" height="103" rx="18" fill="#101D3D" opacity=".92" stroke="#42678C" strokeWidth="3"/>
          <rect x="20" y="20" width="48" height="48" rx="10" fill="#2AD6C8"/>
          <path d="M31 53l10-10 9 7 11-16" fill="none" stroke="#102B4C" strokeWidth="6"/>
          <text x="84" y="43" fill="#E9FBFF" fontFamily="monospace" fontSize="23" fontWeight="900" letterSpacing="2">SIGMA NAVIGATION</text>
          <text x="84" y="74" fill={drive > .985 ? '#FFE178' : '#76F2E4'} fontFamily="monospace" fontSize="18" fontWeight="700">
            {drive > .985 ? 'ARRIVED  •  MADE WITH LOVE' : 'SCENIC ROUTE  •  AVOIDING BLOCKS'}
          </text>
        </g>

        <g transform="translate(1760 865)" opacity=".7">
          <circle r="58" fill="#142541" stroke="#6D8CA6" strokeWidth="3"/>
          <path d="M0-43L12-7 0 0-12-7z" fill="#FFE06A"/>
          <path d="M0 43L12 7 0 0-12 7z" fill="#607F9D"/>
          <text x="0" y="-68" textAnchor="middle" fill="#C4DAE8" fontFamily="monospace" fontSize="17">N</text>
        </g>
      </g>

      <rect y="907" width="1920" height="173" fill="#0D1734" opacity=".38"/>
      <path d="M0 915h1920" stroke="#5F8DA8" strokeOpacity=".12" strokeWidth="3"/>
    </svg>
  );
}