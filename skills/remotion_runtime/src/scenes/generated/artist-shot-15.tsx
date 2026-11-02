import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#62D4F2';
export const META = {15: {bg: '#62D4F2'}};

const PixelStar = ({x, y, s = 1, color = '#FFD93D'}: {
  x: number; y: number; s?: number; color?: string;
}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <polygon
      points="0,-38 11,-13 38,-13 17,5 25,34 0,18 -25,34 -17,5 -38,-13 -11,-13"
      fill={color}
      stroke="#172554"
      strokeWidth="7"
      strokeLinejoin="miter"
    />
    <rect x="-12" y="-7" width="7" height="7" fill="#172554" />
    <rect x="6" y="-7" width="7" height="7" fill="#172554" />
  </g>
);

const SkillNode = ({x, y, label, color, kind, on}: {
  x: number; y: number; label: string; color: string; kind: number; on: boolean;
}) => (
  <g transform={`translate(${x} ${y})`}>
    {on && <rect x="-66" y="-53" width="132" height="106" fill={color} opacity="0.22" />}
    <rect x="-57" y="-45" width="114" height="90" fill="#172554" stroke={on ? color : '#6174A5'} strokeWidth="7" />
    <rect x="-48" y="-36" width="96" height="52" fill={on ? color : '#2A3B69'} />
    {kind === 0 && (
      <g fill="#172554">
        <rect x="-31" y="-25" width="47" height="7" />
        <rect x="-31" y="-11" width="61" height="7" />
        <rect x="-31" y="3" width="36" height="7" />
      </g>
    )}
    {kind === 1 && (
      <g>
        <polygon points="-17,-27 25,-10 -17,8" fill="#172554" />
        <rect x="-34" y="-29" width="8" height="39" fill="#172554" />
      </g>
    )}
    {kind === 2 && (
      <g fill="#172554">
        <rect x="-32" y="-27" width="64" height="31" />
        <rect x="-21" y="4" width="12" height="9" />
        <rect x="-22" y="-18" width="8" height="8" fill={color} />
        <rect x="-5" y="-18" width="8" height="8" fill={color} />
        <rect x="12" y="-18" width="8" height="8" fill={color} />
      </g>
    )}
    {kind === 3 && (
      <g>
        <rect x="-34" y="-28" width="68" height="40" fill="#F7FBFF" stroke="#172554" strokeWidth="6" />
        <rect x="-34" y="-28" width="68" height="10" fill="#FF5C8A" />
        <rect x="-20" y="-8" width="40" height="6" fill="#2878F0" />
      </g>
    )}
    {kind === 4 && (
      <g>
        <path d="M-27 7 L-20 -26 L26 -26 L26 -5 L-7 -5 Z" fill="#FFFFFF" stroke="#172554" strokeWidth="5" />
        <path d="M-12 -15 H15 M-12 -4 H7" stroke="#2878F0" strokeWidth="5" />
      </g>
    )}
    {kind === 5 && (
      <g>
        <path d="M0 -29 L25 5 H8 V13 H-8 V5 H-25 Z" fill="#172554" />
        <rect x="-5" y="-16" width="10" height="19" fill={color} />
      </g>
    )}
    <rect x="-57" y="27" width="114" height="27" fill="#101B3D" />
    <text x="0" y="47" textAnchor="middle" fill={on ? '#FFFFFF' : '#91A0C4'} fontSize="19" fontWeight="900" fontFamily="monospace">
      {label}
    </text>
  </g>
);

export const Shot15 = () => {
  const e = useE();
  const t = e.shotT;
  const c01 = (v: number) => Math.max(0, Math.min(1, v));
  const drive = e.easeIO(c01(t / 6.15));
  const carX = e.lerp(285, 1110, drive);
  const carY = 858 - (carX - 285) * 0.235;
  const bob = Math.round(Math.sin(t * Math.PI * 4.33) * 3);
  const mapOpen = e.easeOut(c01((t - 0.18) / 1.05));
  const buttonUp = e.back(c01((t - 2.45) / 2.15));
  const buttonY = 280 + (1 - buttonUp) * 245;
  const blink = Math.floor(t * 4) % 2 === 0;
  const activation = [0.45, 0.85, 1.25, 2.0, 2.4, 2.8];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <linearGradient id="sea15" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#278DEB" />
          <stop offset="1" stopColor="#1755B5" />
        </linearGradient>
      </defs>

      {/* 高饱和像素山海 */}
      <rect width="1920" height="1080" fill={BG} />
      <rect x="0" y="0" width="1920" height="94" fill="#79E0F4" />
      <rect x="1420" y="80" width="138" height="138" fill="#FFE979" />
      <rect x="1442" y="58" width="94" height="182" fill="#FFE979" />
      <rect x="1398" y="102" width="182" height="94" fill="#FFE979" />
      <rect x="1442" y="102" width="94" height="94" fill="#FFF4B0" />

      {[
        [120, 128, 1.1], [590, 195, 0.8], [1130, 95, 1.0], [1660, 310, 0.65],
      ].map(([x, y, s], i) => (
        <g key={i} transform={`translate(${Number(x) - t * (8 + i * 2)} ${y}) scale(${s})`} fill="#F5FCFF">
          <rect x="0" y="20" width="174" height="42" />
          <rect x="30" y="0" width="62" height="62" />
          <rect x="92" y="10" width="48" height="52" />
          <rect x="18" y="62" width="125" height="9" fill="#BDEAF3" />
        </g>
      ))}

      <path d="M0 525 L0 365 L115 365 L115 318 L182 318 L182 259 L250 259 L250 318 L320 318 L320 391 L414 391 L414 300 L478 300 L478 229 L540 229 L540 300 L616 300 L616 392 L720 392 L720 340 L790 340 L790 407 L905 407 L905 525 Z" fill="#6556B8" />
      <path d="M0 525 L0 433 L110 433 L110 385 L195 385 L195 345 L255 345 L255 411 L365 411 L365 455 L480 455 L480 372 L550 372 L550 329 L628 329 L628 414 L734 414 L734 468 L900 468 L900 525 Z" fill="#3D438F" />
      <path d="M176 318 H250 V359 H209 V342 H176 Z M477 300 H541 V338 H510 V322 H477 Z" fill="#F5E8FF" />
      <rect x="0" y="506" width="1920" height="574" fill="url(#sea15)" />
      <rect x="0" y="506" width="1920" height="18" fill="#A5F4EA" />

      {/* 海面像素波光 */}
      {[
        [1040, 570, 120], [1310, 548, 85], [1570, 595, 170], [920, 665, 80],
        [1210, 720, 150], [1500, 772, 100], [1740, 670, 110], [1080, 900, 160],
        [1430, 940, 210], [1700, 860, 90], [800, 590, 75],
      ].map(([x, y, w], i) => (
        <g key={i} transform={`translate(${x + ((i % 2 ? -1 : 1) * Math.floor(t * 12) % 24)} ${y})`}>
          <rect width={w} height="10" fill={i % 3 === 0 ? '#8CF5ED' : '#54C9F2'} />
          <rect x="24" y="17" width={w * 0.55} height="8" fill="#1B6DCC" />
        </g>
      ))}

      {/* 左侧大陆与攻略路线 */}
      <path d="M0 492 H400 L465 550 L610 572 L705 640 L815 670 L875 735 L795 810 L620 832 L530 900 L355 930 L285 1080 H0 Z" fill="#44D17A" />
      <path d="M0 521 H367 L441 582 L572 604 L664 672 L764 695 L817 738 L762 774 L602 795 L501 861 L330 895 L250 1080 H0 Z" fill="#75E36F" />
      <path d="M0 930 H292 L350 891 L503 858 L603 793 L762 774 L817 738 L774 716 L663 689 L576 624 L443 602 L367 548 H0" fill="none" stroke="#F7D477" strokeWidth="24" strokeLinejoin="miter" />

      {/* 路线横跨山海，尽头是开机键 */}
      <path d="M-60 1015 L285 858 L530 816 L790 732 L1085 659 L1300 524 L1570 280" fill="none" stroke="#172554" strokeWidth="88" strokeLinejoin="miter" />
      <path d="M-60 1015 L285 858 L530 816 L790 732 L1085 659 L1300 524 L1570 280" fill="none" stroke="#596579" strokeWidth="66" strokeLinejoin="miter" />
      <path d="M-60 1015 L285 858 L530 816 L790 732 L1085 659 L1300 524 L1570 280" fill="none" stroke="#FFD93D" strokeWidth="10" strokeDasharray="38 30" strokeDashoffset={-t * 85} />

      {/* 路边像素设施 */}
      <g transform="translate(108 633)">
        <rect x="0" y="72" width="18" height="115" fill="#70452C" />
        <rect x="-55" y="0" width="162" height="91" fill="#172554" />
        <rect x="-45" y="10" width="142" height="67" fill="#FF5C8A" />
        <text x="26" y="39" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="24" fill="#FFFFFF">NEXT</text>
        <text x="26" y="67" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="25" fill="#FFFFFF">LEVEL →</text>
      </g>
      <g transform="translate(520 500)">
        <rect x="0" y="65" width="22" height="96" fill="#70452C" />
        <rect x="-55" y="0" width="132" height="80" fill="#2878F0" stroke="#172554" strokeWidth="9" />
        <path d="M-26 40 H47 M25 17 L50 40 L25 63" fill="none" stroke="#FFFFFF" strokeWidth="12" />
      </g>

      {/* 开机按钮从路线尽头升起 */}
      <g transform={`translate(1570 ${buttonY})`}>
        <rect x="-130" y="-150" width="260" height="300" fill="#7DFFF2" opacity={0.09 + buttonUp * 0.11} />
        <rect x="-100" y="-123" width="200" height="246" fill="#7DFFF2" opacity={0.12 + buttonUp * 0.12} />
        <path d="M-108 85 H108 V126 H78 V153 H-78 V126 H-108 Z" fill="#172554" />
        <path d="M-93 65 H93 V108 H65 V130 H-65 V108 H-93 Z" fill="#596579" />
        <polygon points="-82,-76 -48,-108 48,-108 82,-76 82,45 48,77 -48,77 -82,45" fill={blink ? '#FFF17A' : '#FFD93D'} stroke="#172554" strokeWidth="13" />
        <path d="M0 -68 V-5 M-37 -47 A55 55 0 1 0 37 -47" fill="none" stroke="#172554" strokeWidth="18" strokeLinecap="square" />
        <rect x="-62" y="91" width="124" height="12" fill="#37E6E6" opacity={buttonUp} />
      </g>
      {buttonUp > 0.15 && (
        <g fill="#FFF3A0">
          <rect x="1360" y={215 - buttonUp * 30} width="22" height="22" />
          <rect x="1742" y={320 - buttonUp * 50} width="30" height="30" />
          <rect x="1680" y={105 - buttonUp * 20} width="18" height="18" />
          <rect x="1430" y={405 - buttonUp * 45} width="16" height="16" />
        </g>
      )}

      {/* 从车顶展开的完整技能地图 */}
      <path d={`M${carX} ${carY - 170} L${carX - 30} 390 L960 350`} fill="none" stroke="#6DFFF2" strokeWidth="8" strokeDasharray="16 13" opacity={mapOpen * 0.65} />
      <g transform={`translate(960 62) scale(${Math.max(0.02, mapOpen)} 1) translate(-450 0)`} opacity={c01(mapOpen * 1.5)}>
        <path d="M0 20 H24 V0 H876 V20 H900 V328 H876 V350 H24 V328 H0 Z" fill="#101B3D" stroke="#172554" strokeWidth="10" />
        <rect x="16" y="18" width="868" height="312" fill="#1D3262" stroke="#37E6E6" strokeWidth="5" />
        <rect x="32" y="30" width="246" height="43" fill="#2878F0" />
        <text x="48" y="60" fill="#FFFFFF" fontFamily="monospace" fontSize="28" fontWeight="900">SIGMA // SKILL MAP</text>
        <text x="850" y="58" textAnchor="end" fill="#FFD93D" fontFamily="monospace" fontSize="23" fontWeight="900">6 / 6 UNLOCKED</text>

        <g fill="none" stroke="#6F8CCB" strokeWidth="8" strokeLinecap="square">
          <path d="M450 188 L205 145 M450 188 L450 111 M450 188 L695 145" />
          <path d="M450 188 L205 275 M450 188 L450 265 M450 188 L695 275" />
        </g>
        <g fill="none" stroke="#FFD93D" strokeWidth="4" strokeDasharray="12 12">
          <path d="M205 145 L450 111 L695 145 M205 275 L450 265 L695 275" />
        </g>

        <SkillNode x={155} y={148} label="WRITE" color="#FF7A66" kind={0} on={t > activation[0]} />
        <SkillNode x={450} y={112} label="VIDEO" color="#FF5C8A" kind={1} on={t > activation[1]} />
        <SkillNode x={745} y={148} label="POST" color="#A96BFF" kind={2} on={t > activation[2]} />
        <SkillNode x={155} y={270} label="WEB" color="#37E6E6" kind={3} on={t > activation[3]} />
        <SkillNode x={450} y={270} label="DOCS" color="#68DFFF" kind={4} on={t > activation[4]} />
        <SkillNode x={745} y={270} label="NAV" color="#7CEA72" kind={5} on={t > activation[5]} />
        <PixelStar x={450} y={190} s={0.72 + Math.sin(t * 7) * 0.035} />
        <rect x="35" y="307" width="210" height="9" fill="#314A80" />
        <rect x="35" y="307" width={210 * c01(t / 3.1)} height="9" fill="#FFD93D" />
      </g>

      {/* 出租车尾速线 */}
      <g transform={`translate(${carX} ${carY + bob})`} fill="#D7FAFF" opacity="0.85">
        <rect x="-340" y="-115" width="105" height="12" />
        <rect x="-385" y="-73" width="150" height="10" />
        <rect x="-305" y="-34" width="70" height="9" />
      </g>

      {/* 像素出租车 */}
      <g transform={`translate(${carX} ${carY + bob}) scale(0.9)`}>
        <ellipse cx="0" cy="8" rx="232" ry="31" fill="#102D68" opacity="0.35" />
        <path d="M-220 -53 H-191 V-112 H-119 V-153 H-80 V-177 H83 V-153 H124 V-112 H190 V-76 H220 V-14 H194 V8 H-194 V-14 H-220 Z" fill="#FFD93D" stroke="#172554" strokeWidth="12" strokeLinejoin="miter" />
        <path d="M-103 -145 H-72 V-163 H72 V-145 H103 V-102 H-121 V-126 H-103 Z" fill="#75E7F2" stroke="#172554" strokeWidth="9" />
        <rect x="-6" y="-158" width="12" height="58" fill="#172554" />
        <path d="M-184 -91 H-128 V-53 H-196 Z M132 -91 H181 V-55 H142 Z" fill="#FFF2A8" />
        <rect x="-222" y="-46" width="30" height="22" fill="#FF5C5C" />
        <rect x="193" y="-48" width="29" height="24" fill="#F7FBFF" />
        <rect x="-81" y="-90" width="153" height="24" fill="#F0B927" />
        {Array.from({length: 8}).map((_, i) => (
          <rect key={i} x={-77 + i * 19} y="-88" width="10" height="10" fill={i % 2 ? '#FFFFFF' : '#172554'} />
        ))}
        <rect x="-62" y="-207" width="124" height="40" fill="#172554" />
        <rect x="-49" y="-198" width="98" height="25" fill="#FFF2A8" />
        <text x="0" y="-178" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="24" fill="#172554">TAXI</text>
        {[-139, 139].map((x) => (
          <g key={x} transform={`translate(${x} -2)`}>
            <rect x="-43" y="-43" width="86" height="86" fill="#172554" />
            <rect x="-29" y="-29" width="58" height="58" fill="#30384D" />
            <rect x="-14" y="-14" width="28" height="28" fill="#C8D6E5" />
            <rect x="-7" y="-25" width="14" height="50" fill="#172554" transform={`rotate(${t * 240})`} />
          </g>
        ))}
        <rect x="-30" y="-56" width="62" height="12" fill="#172554" />
      </g>

      {/* Sigma 站在车顶，展开双臂展示地图 */}
      <Actor
        Character={Character}
        x={carX}
        y={carY - 151 + bob}
        s={0.57}
        view="front"
        pose="stand"
        armL={[-76, -18]}
        armR={[-76, -18]}
        headTurn={0}
        tilt={Math.sin(t * 4) * 1.5}
        mood="calm"
      />

      {/* 经验值与导航游戏 UI */}
      <g transform="translate(42 40)">
        <rect width="360" height="62" fill="#172554" />
        <rect x="14" y="13" width="91" height="36" fill="#2878F0" />
        <text x="59" y="40" textAnchor="middle" fontFamily="monospace" fontSize="24" fontWeight="900" fill="#FFFFFF">LV.15</text>
        <rect x="119" y="20" width="222" height="22" fill="#0A1432" />
        <rect x="124" y="25" width={212 * c01(0.42 + t / 9)} height="12" fill="#FFD93D" />
      </g>

      {/* 前景像素草与路标，增强 wide 景深 */}
      <g fill="#1A9D63">
        <path d="M0 1005 H36 V969 H54 V1005 H88 V946 H109 V1005 H143 V980 H166 V1080 H0 Z" />
        <path d="M1810 1080 V989 H1832 V950 H1850 V989 H1880 V932 H1900 V989 H1920 V1080 Z" />
      </g>
      <g transform="translate(1710 865)">
        <rect x="0" y="0" width="17" height="150" fill="#70452C" />
        <path d="M-92 0 H85 V69 H-92 L-122 34 Z" fill="#44D17A" stroke="#172554" strokeWidth="9" />
        <text x="-5" y="44" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="26" fill="#172554">START!</text>
      </g>
    </svg>
  );
};