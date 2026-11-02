import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';

export const BG = '#172554';
export const META = {12: {bg: '#172554'}};

const Taxi: React.FC<{x: number; y: number; bounce: number}> = ({x, y, bounce}) => (
  <g transform={`translate(${x} ${y + bounce})`} shapeRendering="crispEdges">
    <rect x="20" y="92" width="438" height="108" fill="#D98E04" />
    <rect x="0" y="126" width="478" height="74" fill="#FFB914" />
    <rect x="28" y="74" width="92" height="70" fill="#FFD43B" />
    <rect x="112" y="26" width="224" height="118" fill="#FFD43B" />
    <rect x="328" y="64" width="94" height="80" fill="#FFD43B" />
    <rect x="142" y="42" width="82" height="72" fill="#83F3FF" />
    <rect x="238" y="42" width="76" height="72" fill="#42C7E8" />
    <rect x="150" y="50" width="18" height="14" fill="#D9FFFF" />
    <rect x="246" y="50" width="18" height="14" fill="#D9FFFF" />
    <rect x="204" y="-2" width="88" height="30" fill="#FFF4B0" />
    <rect x="216" y="-12" width="64" height="12" fill="#FFD43B" />
    <text x="248" y="20" textAnchor="middle" fontFamily="monospace" fontSize="20" fontWeight="900" fill="#172554">TAXI</text>
    <rect x="18" y="146" width="442" height="18" fill="#FFF0A6" />
    {[54, 86, 118, 150, 182, 214, 246, 278, 310, 342, 374].map((v, i) => (
      <rect key={v} x={v} y="146" width="18" height="18" fill={i % 2 ? '#FFF0A6' : '#172554'} />
    ))}
    <rect x="12" y="164" width="28" height="20" fill="#FFF8D8" />
    <rect x="438" y="164" width="28" height="20" fill="#FF5C5C" />
    <rect x="-12" y="190" width="502" height="20" fill="#173A6B" />
    <g>
      <rect x="66" y="176" width="82" height="62" fill="#161A2B" />
      <rect x="78" y="164" width="58" height="86" fill="#161A2B" />
      <rect x="86" y="180" width="42" height="54" fill="#AAB4C8" />
      <rect x="96" y="190" width="22" height="22" fill="#2878F0" />
    </g>
    <g>
      <rect x="346" y="176" width="82" height="62" fill="#161A2B" />
      <rect x="358" y="164" width="58" height="86" fill="#161A2B" />
      <rect x="366" y="180" width="42" height="54" fill="#AAB4C8" />
      <rect x="376" y="190" width="22" height="22" fill="#2878F0" />
    </g>
  </g>
);

const Landmark: React.FC<{
  x: number; y: number; p: number; label: string; kind: 'sight' | 'food' | 'hotel';
}> = ({x, y, p, label, kind}) => (
  <g transform={`translate(${x} ${y}) scale(${Math.max(0, p)})`} shapeRendering="crispEdges">
    <rect x="-80" y="-92" width="160" height="142" fill="#172554" opacity=".18" transform="translate(8 10)" />
    <rect x="-80" y="-92" width="160" height="142" fill="#FFF8DD" stroke="#173A6B" strokeWidth="8" />
    {kind === 'sight' && (
      <g>
        <rect x="-58" y="8" width="116" height="20" fill="#44D17A" />
        <polygon points="-54,8 -12,-56 24,8" fill="#2878F0" />
        <polygon points="-10,8 32,-42 60,8" fill="#5138A8" />
        <rect x="-20" y="-48" width="16" height="16" fill="#FFFFFF" />
        <rect x="-12" y="-58" width="16" height="12" fill="#FFFFFF" />
        <rect x="38" y="-62" width="20" height="20" fill="#FFD43B" />
      </g>
    )}
    {kind === 'food' && (
      <g>
        <rect x="-52" y="-8" width="104" height="38" fill="#FF5C5C" />
        <rect x="-42" y="-20" width="84" height="16" fill="#FFF0C2" />
        <rect x="-30" y="-30" width="60" height="12" fill="#FFD43B" />
        <rect x="-28" y="-60" width="8" height="28" fill="#AAB4C8" />
        <rect x="0" y="-70" width="8" height="38" fill="#AAB4C8" />
        <rect x="28" y="-56" width="8" height="24" fill="#AAB4C8" />
        <rect x="24" y="-72" width="8" height="58" fill="#173A6B" transform="rotate(18 28 -42)" />
      </g>
    )}
    {kind === 'hotel' && (
      <g>
        <rect x="-42" y="-68" width="84" height="96" fill="#2878F0" />
        <rect x="-52" y="18" width="104" height="12" fill="#173A6B" />
        {[-24, 4].map(xx => [-48, -20].map(yy => (
          <rect key={`${xx}-${yy}`} x={xx} y={yy} width="18" height="18" fill="#FFD43B" />
        )))}
        <rect x="-10" y="-2" width="20" height="30" fill="#FFFFFF" />
        <rect x="-54" y="-78" width="108" height="12" fill="#FF5C9E" />
      </g>
    )}
    <rect x="-92" y="54" width="184" height="40" fill="#173A6B" />
    <text x="0" y="82" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="25" fill="#FFFFFF">{label}</text>
  </g>
);

export const Shot12: React.FC = () => {
  const e = useE();
  const t = e.shotT;
  const unroll = e.easeOut(e.seg(0, .85, t));
  const routeP = e.seg(.72, 2.35, t);
  const flagP = e.back(e.seg(1.82, 2.48, t));
  const taxiIn = e.easeOut(e.seg(2.62, 3.82, t));
  const taxiOut = e.easeIn(e.seg(5.88, 6.5, t));
  const taxiX = e.lerp(2040, 1260, taxiIn) + taxiOut * 650;
  const taxiBounce = taxiIn > 0 && taxiIn < 1 ? Math.sin(t * 28) * 7 : Math.sin(t * 11) * 2;
  const hop = e.seg(3.88, 5.18, t);
  const hopEase = e.easeIO(hop);
  const landisX = e.lerp(1750, taxiX + 260, hopEase);
  const landisY = 936 - Math.sin(hop * Math.PI) * 210 - hopEase * 100;
  const landisS = e.lerp(1.02, .62, hopEase);
  const landed = e.seg(5.08, 5.35, t);
  const xpP = e.easeOut(e.seg(4.45, 5.5, t));
  const heartP = e.back(e.seg(4.95, 5.55, t));
  const taxiCall = e.back(e.seg(2.25, 2.75, t)) * (1 - e.seg(3.45, 3.8, t));

  const pin1 = e.back(e.seg(.6, 1.02, t));
  const pin2 = e.back(e.seg(1.04, 1.46, t));
  const pin3 = e.back(e.seg(1.48, 1.9, t));

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <clipPath id="scrollReveal">
          <rect x="128" y="190" width={1240 * unroll} height="650" />
        </clipPath>
        <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="10" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <rect width="1920" height="1080" fill={BG} />
      <rect y="0" width="1920" height="220" fill="#111B46" />
      <rect y="850" width="1920" height="230" fill="#101936" />
      <rect y="850" width="1920" height="12" fill="#2878F0" />
      <rect y="884" width="1920" height="8" fill="#213B73" />

      {/* pixel dawn and distant travel city */}
      <g shapeRendering="crispEdges" opacity=".95">
        <rect x="82" y="90" width="12" height="12" fill="#FFD43B" />
        <rect x="260" y="54" width="8" height="8" fill="#83F3FF" />
        <rect x="1480" y="86" width="12" height="12" fill="#FFD43B" />
        <rect x="1690" y="148" width="8" height="8" fill="#FF8FC7" />
        <rect x="1820" y="64" width="10" height="10" fill="#83F3FF" />
        <rect x="1140" y="122" width="8" height="8" fill="#FFFFFF" />
        <rect x="1470" y="152" width="160" height="12" fill="#28457D" />
        <rect x="1510" y="140" width="116" height="12" fill="#28457D" />
      </g>
      <g fill="#21366A" shapeRendering="crispEdges">
        <rect x="0" y="664" width="150" height="186" />
        <rect x="32" y="610" width="84" height="54" />
        <rect x="1390" y="596" width="110" height="254" />
        <rect x="1512" y="664" width="164" height="186" />
        <rect x="1690" y="546" width="92" height="304" />
        <rect x="1792" y="630" width="128" height="220" />
      </g>
      <g fill="#FFD43B" opacity=".55">
        {[1418, 1452, 1550, 1590, 1720, 1818, 1854].map((x, i) => (
          <rect key={x} x={x} y={i % 2 ? 700 : 646} width="18" height="24" />
        ))}
      </g>

      {/* game HUD */}
      <g fontFamily="monospace" shapeRendering="crispEdges">
        <rect x="420" y="62" width="1080" height="92" fill="#0C1435" stroke="#3E5CA8" strokeWidth="6" />
        <rect x="440" y="82" width="222" height="52" fill="#2878F0" />
        <text x="551" y="118" textAnchor="middle" fontSize="29" fontWeight="900" fill="#FFFFFF">TRAVEL LV.03</text>
        <rect x="692" y="88" width="560" height="36" fill="#172554" stroke="#FFF0A6" strokeWidth="4" />
        <rect x="700" y="96" width={544 * (.42 + .58 * xpP)} height="20" fill="#FFD43B" />
        <text x="1278" y="118" fontSize="27" fontWeight="900" fill="#83F3FF">+120 XP</text>
        <text x="1460" y="119" textAnchor="end" fontSize="20" fill="#AAB4C8">ROUTE READY!</text>
      </g>

      {/* unrolling strategy scroll */}
      <g clipPath="url(#scrollReveal)">
        <polygon points="156,214 1308,214 1308,242 1338,242 1338,778 1308,778 1308,812 156,812 156,784 128,784 128,242 156,242" fill="#E9C87C" />
        <rect x="158" y="238" width="1148" height="544" fill="#FFF1BE" />
        <rect x="158" y="238" width="1148" height="12" fill="#FFFFFF" opacity=".55" />
        <g stroke="#D9B96C" strokeWidth="4" opacity=".55">
          <path d="M188 310 H1278 M188 714 H1278" />
          <path d="M282 258 V760 M1172 258 V760" />
        </g>
        <g fill="#D9E8B0" opacity=".7">
          <rect x="190" y="330" width="130" height="80" />
          <rect x="1080" y="586" width="160" height="96" />
          <rect x="712" y="280" width="180" height="54" />
        </g>
        <text x="198" y="292" fontFamily="monospace" fontWeight="900" fontSize="30" fill="#173A6B">SIGMA'S PERFECT QUEST</text>
        <text x="1110" y="756" fontFamily="monospace" fontWeight="900" fontSize="22" fill="#9D6A31">3 STOPS · 0 DETOURS</text>

        <path d="M330 650 L330 540 L520 540 L520 406 L790 406 L790 640 L1080 640 L1080 392"
          fill="none" stroke="#173A6B" strokeWidth="24" strokeLinejoin="miter" opacity=".16" />
        <path d="M330 650 L330 540 L520 540 L520 406 L790 406 L790 640 L1080 640 L1080 392"
          fill="none" stroke="#FF5C9E" strokeWidth="14" strokeDasharray="28 18"
          strokeDashoffset={980 * (1 - routeP)} />
        <path d="M330 650 L330 540 L520 540 L520 406 L790 406 L790 640 L1080 640 L1080 392"
          fill="none" stroke="#FFD43B" strokeWidth="5" pathLength="1"
          strokeDasharray="1" strokeDashoffset={1 - routeP} filter="url(#softGlow)" />

        <Landmark x={330} y={618} p={pin1} label="景点 / LOOK" kind="sight" />
        <Landmark x={790} y={372} p={pin2} label="餐厅 / EAT" kind="food" />
        <Landmark x={1080} y={356} p={pin3} label="酒店 / REST" kind="hotel" />

        <g transform={`translate(1170 650) scale(${e.back(e.seg(2.05, 2.45, t))})`}>
          <rect x="-62" y="-42" width="124" height="84" fill="#44D17A" stroke="#173A6B" strokeWidth="6" />
          <text x="0" y="-5" textAnchor="middle" fontFamily="monospace" fontSize="22" fontWeight="900" fill="#173A6B">ROUTE</text>
          <text x="0" y="25" textAnchor="middle" fontFamily="monospace" fontSize="26" fontWeight="900" fill="#FFFFFF">OK!</text>
        </g>
      </g>

      {/* scroll rollers */}
      <g shapeRendering="crispEdges">
        <rect x="102" y="182" width="72" height="668" fill="#9D6A31" />
        <rect x="116" y="198" width="44" height="636" fill="#F4C95D" />
        <rect x="86" y="170" width="104" height="34" fill="#FFD93D" />
        <rect x="86" y="830" width="104" height="34" fill="#FFD93D" />
        <rect x={128 + 1240 * unroll} y="182" width="72" height="668" fill="#9D6A31" />
        <rect x={142 + 1240 * unroll} y="198" width="44" height="636" fill="#F4C95D" />
        <rect x={112 + 1240 * unroll} y="170" width="104" height="34" fill="#FFD93D" />
        <rect x={112 + 1240 * unroll} y="830" width="104" height="34" fill="#FFD93D" />
      </g>

      {/* Sigma and flag */}
      <g transform="translate(590 930) scale(.72)">
        <Character
          view="side"
          armL={[-32, -58]}
          armR={[-70 - 25 * flagP, -20]}
          headTurn={-8}
          tilt={-4 * flagP}
          mood={t > 4.8 ? 'surprised' : 'calm'}
        />
      </g>
      <g transform={`translate(666 760) rotate(${-34 + 34 * flagP})`} shapeRendering="crispEdges">
        <rect x="-6" y="-242" width="12" height="270" fill="#FFFFFF" />
        <rect x="-10" y="-248" width="20" height="20" fill="#FFD43B" />
        <g transform={`scale(${Math.max(.02, flagP)} 1)`}>
          <polygon points="6,-236 154,-236 154,-216 176,-216 176,-130 154,-130 154,-110 6,-110" fill="#FF5C9E" />
          <rect x="24" y="-214" width="100" height="12" fill="#FF9AC5" />
          <polygon points="54,-192 68,-158 104,-158 76,-136 86,-100 54,-122 22,-100 32,-136 4,-158 40,-158" fill="#FFD43B" />
          <text x="130" y="-134" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="25" fill="#FFFFFF">GO!</text>
        </g>
      </g>

      {/* taxi summon bubble */}
      <g transform={`translate(820 650) scale(${Math.max(0, taxiCall)})`} shapeRendering="crispEdges">
        <rect x="-104" y="-64" width="208" height="92" fill="#FFFFFF" stroke="#173A6B" strokeWidth="7" />
        <polygon points="-30,28 -4,28 -34,62" fill="#FFFFFF" />
        <text x="0" y="-3" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="42" fill="#2878F0">TAXI!</text>
      </g>

      {/* suitcase follows Landis in a comic arc */}
      <g transform={`translate(${landisX + 42} ${landisY - 12}) scale(${landisS})`} opacity={1 - landed} shapeRendering="crispEdges">
        <rect x="0" y="-114" width="12" height="60" fill="#AAB4C8" />
        <rect x="0" y="-120" width="54" height="12" fill="#AAB4C8" />
        <rect x="-24" y="-66" width="100" height="76" fill="#FF5C9E" stroke="#161A2B" strokeWidth="8" />
        <rect x="12" y="-66" width="12" height="76" fill="#FFD43B" />
        <rect x="-12" y="10" width="20" height="20" fill="#161A2B" />
        <rect x="50" y="10" width="20" height="20" fill="#161A2B" />
        <rect x="42" y="-50" width="22" height="22" fill="#FFF1BE" />
      </g>

      <g transform={`translate(${landisX} ${landisY}) scale(${landisS})`} opacity={1 - e.seg(5.2, 5.42, t)}>
        <Character
          view="side"
          armL={[-45, -62]}
          armR={[-25, -45]}
          headTurn={-10}
          tilt={hop > 0 && hop < 1 ? -12 : 5}
          mood={hop > 0 && hop < 1 ? 'surprised' : 'calm'}
        />
      </g>

      <Taxi x={taxiX} y={692} bounce={taxiBounce} />

      {/* rear door slams shut after the jump */}
      <g transform={`translate(${taxiX} ${692 + taxiBounce})`} opacity={landed} shapeRendering="crispEdges">
        <rect x="232" y="38" width="88" height="112" fill="#FFD43B" />
        <rect x="240" y="44" width="72" height="68" fill="#42C7E8" />
        <rect x="248" y="52" width="18" height="14" fill="#D9FFFF" />
        <rect x="246" y="126" width="34" height="8" fill="#173A6B" />
      </g>

      {/* speed pixels and celebratory heart */}
      {taxiOut > 0 && (
        <g fill="#83F3FF" shapeRendering="crispEdges">
          <rect x={taxiX - 90} y="760" width="80" height="12" />
          <rect x={taxiX - 150} y="810" width="130" height="12" />
          <rect x={taxiX - 70} y="860" width="60" height="12" />
        </g>
      )}
      <g transform={`translate(740 454) scale(${Math.max(0, heartP)})`} shapeRendering="crispEdges" filter="url(#softGlow)">
        <polygon points="0,0 24,0 24,12 48,12 48,0 72,0 72,12 84,12 84,48 72,48 72,60 60,60 60,72 48,72 48,84 36,84 36,96 24,96 24,84 12,84 12,72 0,72 0,60 -12,60 -12,48 -24,48 -24,12 -12,12 -12,0" fill="#FF5C9E" />
        <rect x="0" y="12" width="18" height="18" fill="#FFFFFF" />
      </g>

      <g opacity={e.seg(5.15, 5.55, t)} fontFamily="monospace">
        <rect x="472" y="196" width="400" height="62" fill="#44D17A" stroke="#FFFFFF" strokeWidth="5" />
        <text x="672" y="238" textAnchor="middle" fontWeight="900" fontSize="30" fill="#173A6B">PARTY +1 · ADVENTURE ON</text>
      </g>

      {/* foreground pixel curb */}
      <g shapeRendering="crispEdges">
        {[0, 160, 320, 480, 640, 800, 960, 1120, 1280, 1440, 1600, 1760].map((x, i) => (
          <rect key={x} x={x} y="1008" width="160" height="72" fill={i % 2 ? '#173A6B' : '#2878F0'} />
        ))}
        <rect y="994" width="1920" height="16" fill="#83F3FF" />
      </g>
    </svg>
  );
};