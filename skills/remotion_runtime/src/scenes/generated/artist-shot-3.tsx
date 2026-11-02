import {useE} from '../../engine/context';
import {CharacterSide} from './char-hero';

export const BG = '#171B3E';
export const META = {3: {bg: '#171B3E'}};

const flying = [
  {x: 880, y: 360, dx: -480, dy: 240, r: -210, d: 0.00, s: 1.00},
  {x: 910, y: 330, dx: -240, dy: -40, r: 160, d: 0.04, s: 0.82},
  {x: 930, y: 350, dx: 80, dy: -100, r: 250, d: 0.08, s: 1.10},
  {x: 900, y: 390, dx: 350, dy: 60, r: -170, d: 0.12, s: 0.90},
  {x: 940, y: 370, dx: 570, dy: 250, r: 300, d: 0.02, s: 1.05},
  {x: 870, y: 350, dx: -610, dy: 390, r: -320, d: 0.16, s: 0.76},
  {x: 920, y: 340, dx: 230, dy: 350, r: 190, d: 0.20, s: 0.88},
  {x: 900, y: 370, dx: -80, dy: 440, r: -130, d: 0.10, s: 1.15},
];

function Sheet({x = 0, y = 0, r = 0, s = 1, accent = '#2878F0'}: {
  x?: number; y?: number; r?: number; s?: number; accent?: string;
}) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}>
      <rect x="-45" y="-58" width="90" height="116" rx="4" fill="#F7F3E8" stroke="#B9C8E8" strokeWidth="4"/>
      <rect x="-32" y="-43" width="42" height="8" rx="3" fill={accent}/>
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <line x1="-31" y1={-20 + i * 18} x2="31" y2={-20 + i * 18} stroke="#9DB4D2" strokeWidth="3"/>
          <line x1={-8 + i * 12} y1={-24 + i * 18} x2={-8 + i * 12} y2={-4 + i * 18} stroke="#C2D0E2" strokeWidth="2"/>
        </g>
      ))}
    </g>
  );
}

function Sigma({run, slide, carry}: {run: number; slide: number; carry: boolean}) {
  const stride = Math.sin(run * Math.PI * 12) * (1 - slide);
  const bob = Math.abs(Math.sin(run * Math.PI * 12)) * 5;
  return (
    <g transform={`translate(0 ${-bob})`}>
      {carry && (
        <g transform={`rotate(${stride * 2} 0 -290)`}>
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <g key={i} transform={`translate(${i % 2 ? 7 : -5} ${-318 - i * 25}) rotate(${i % 2 ? 2 : -2})`}>
              <rect x="-91" y="-17" width="182" height="28" rx="3" fill={i === 6 ? '#FFF8DB' : '#EAF2FF'} stroke="#A7B9DE" strokeWidth="3"/>
              <rect x="-72" y="-9" width={70 + (i % 3) * 22} height="5" rx="2" fill={i === 6 ? '#FF5C5C' : '#7192C7'}/>
            </g>
          ))}
          <rect x="-94" y="-495" width="188" height="12" rx="4" fill="#FFD43B"/>
        </g>
      )}

      <g transform={`rotate(${-26 * stride} -28 -82)`}>
        <path d="M-28-86 L-40-28" stroke="#173A6B" strokeWidth="29" strokeLinecap="round"/>
        <path d="M-57-24 Q-37-36-17-22 L-12-10 L-61-10Z" fill="#F7FBFF" stroke="#2878F0" strokeWidth="6"/>
      </g>
      <g transform={`rotate(${27 * stride + slide * 18} 28 -82)`}>
        <path d="M28-86 L40-28" stroke="#173A6B" strokeWidth="29" strokeLinecap="round"/>
        <path d="M18-23 Q39-35 57-18 L64-7 L15-8Z" fill="#F7FBFF" stroke="#2878F0" strokeWidth="6"/>
      </g>

      <path d="M-55-170 Q0-192 55-170 L48-75 Q0-58-48-75Z" fill="#2878F0" stroke="#161A2B" strokeWidth="7"/>
      <path d="M-39-163 Q0-180 39-163" fill="none" stroke="#67A5FF" strokeWidth="8" strokeLinecap="round"/>
      <path d="M-20-149 L-14-121 M20-149 L14-121" stroke="#F4F7FF" strokeWidth="5" strokeLinecap="round"/>
      <path d="M-45-88 L-42-61 L-5-61 L0-86 L6-61 L43-61 L45-88Z" fill="#173A6B"/>

      <path d="M-43-151 L-75-211 L-69-281" fill="none" stroke="#2878F0" strokeWidth="29" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M43-151 L75-211 L69-281" fill="none" stroke="#2878F0" strokeWidth="29" strokeLinecap="round" strokeLinejoin="round"/>
      <circle cx="-69" cy="-286" r="20" fill="#FFFFFF" stroke="#161A2B" strokeWidth="5"/>
      <circle cx="69" cy="-286" r="20" fill="#FFFFFF" stroke="#161A2B" strokeWidth="5"/>

      <g transform={`translate(0 -225) rotate(${stride * 2})`}>
        <polygon
          points="0,-91 24,-31 89,-28 39,14 55,78 0,43 -55,78 -39,14 -89,-28 -24,-31"
          fill="#FFD93D"
          stroke="#161A2B"
          strokeWidth="8"
          strokeLinejoin="round"
        />
        <path d="M-68-25 L-25-24 L-20-67 L0-80" fill="none" stroke="#FFF29A" strokeWidth="9" strokeLinecap="square"/>
        <circle cx="-25" cy="-4" r="8" fill="#161A2B"/>
        <circle cx="25" cy="-4" r="8" fill="#161A2B"/>
        <path d={slide > 0.2 ? 'M-10 24 Q0 14 10 24' : 'M-12 20 Q0 31 12 20'} fill="none" stroke="#161A2B" strokeWidth="6" strokeLinecap="round"/>
        <rect x="-52" y="11" width="13" height="7" fill="#FF9E57" opacity="0.75"/>
        <rect x="39" y="11" width="13" height="7" fill="#FF9E57" opacity="0.75"/>
      </g>
    </g>
  );
}

export function Shot3() {
  const e = useE();
  const t = e.shotT;
  const run = e.clamp01(t / 3.3);
  const slip = e.easeOut(e.seg(3.15, 3.85, t));
  const slide = e.easeOut(e.seg(3.45, 5.0, t));
  const caught = e.easeOut(e.seg(4.85, 5.45, t));
  const x = 270 + 610 * run + 580 * slide;
  const y = 858 - 18 * Math.sin(slide * Math.PI) - 18 * caught;
  const rotation = 64 * slide - 24 * caught;
  const carry = t < 3.28;
  const reach = e.easeOut(e.seg(4.15, 5.05, t));
  const shake = e.seg(3.15, 3.35, t) * (1 - e.seg(3.35, 3.8, t));

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="hallBg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5138A8"/>
          <stop offset="0.55" stopColor="#25265F"/>
          <stop offset="1" stopColor="#171B3E"/>
        </linearGradient>
        <linearGradient id="floorBg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#28356B"/>
          <stop offset="1" stopColor="#10162F"/>
        </linearGradient>
        <linearGradient id="screenGlow" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#44D17A" stopOpacity="0.24"/>
          <stop offset="1" stopColor="#2878F0" stopOpacity="0.04"/>
        </linearGradient>
        <filter id="softGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="14" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <rect width="1920" height="1080" fill="url(#hallBg)"/>
      <circle cx="950" cy="260" r="390" fill="#7662D0" opacity="0.13"/>
      <path d="M0 655 L1920 655 L1920 1080 L0 1080Z" fill="url(#floorBg)"/>
      <path d="M0 654 H1920" stroke="#7085D0" strokeWidth="8"/>
      <path d="M210 1080 L690 655 M720 1080 L875 655 M1230 1080 L1050 655 M1760 1080 L1240 655" stroke="#3B477B" strokeWidth="4"/>
      <path d="M0 810 H1920 M0 960 H1920" stroke="#3B477B" strokeWidth="4"/>

      <g opacity="0.9">
        <rect x="50" y="115" width="340" height="540" rx="22" fill="#202453" stroke="#7768C8" strokeWidth="8"/>
        {[0, 1, 2, 3].map((i) => (
          <g key={i} transform={`translate(82 ${160 + i * 120})`}>
            <rect width="275" height="91" rx="9" fill="#303573"/>
            {[0, 1, 2, 3, 4].map((j) => (
              <rect key={j} x={12 + j * 51} y={10 - (j % 2) * 5} width="43" height="70" rx="3" fill={j === 2 ? '#FFD93D' : '#D8E5FA'} transform={`rotate(${j % 2 ? 4 : -3} ${32 + j * 51} 45)`}/>
            ))}
          </g>
        ))}
      </g>

      <g opacity="0.68">
        <rect x="505" y="70" width="250" height="585" rx="18" fill="#24275B" stroke="#655BB5" strokeWidth="7"/>
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <rect x="536" y={105 + i * 105} width="188" height="75" rx="6" fill="#353A79"/>
            <rect x="551" y={117 + i * 105} width="116" height="10" rx="4" fill="#91A7DE"/>
            <rect x="551" y={140 + i * 105} width="150" height="8" rx="4" fill="#6279B8"/>
          </g>
        ))}
      </g>

      <g opacity="0.72">
        <path d="M1245 655 V225 Q1245 105 1365 105 H1515 Q1635 105 1635 225 V655" fill="#24275B" stroke="#655BB5" strokeWidth="10"/>
        {[0, 1, 2].map((i) => (
          <g key={i} transform={`translate(1290 ${160 + i * 145})`}>
            <rect width="300" height="102" rx="9" fill="#343977"/>
            <rect x="20" y="18" width="260" height="14" rx="5" fill="#D7E3F7"/>
            <rect x="20" y="48" width="190" height="12" rx="5" fill="#7D96CE"/>
            <rect x="20" y="73" width="225" height="10" rx="5" fill="#7D96CE"/>
          </g>
        ))}
      </g>

      <rect x="1690" y="95" width="300" height="770" rx="34" fill="#11162F" stroke="#44D17A" strokeWidth="12"/>
      <rect x="1715" y="122" width="260" height="700" rx="18" fill="url(#screenGlow)"/>
      <path d="M1740 185 H1880 M1740 220 H1830 M1740 750 H1900" stroke="#44D17A" strokeWidth="8" opacity="0.45"/>
      <circle cx="1810" cy="835" r="8" fill="#FFD93D" filter="url(#softGlow)"/>

      {t < 3.55 && (
        <g stroke="#9BC5FF" strokeWidth="8" strokeLinecap="round" opacity={0.25 + 0.45 * run}>
          <path d="M95 470 H345"/><path d="M35 535 H285"/><path d="M150 605 H420"/>
          <path d="M420 280 H590"/><path d="M280 350 H500"/>
        </g>
      )}

      <g transform={`translate(${Math.sin(t * 95) * shake * 7} ${Math.cos(t * 83) * shake * 4})`}>
        <g transform={`translate(865 865) rotate(${-8 + slip * 24})`}>
          <rect x="-75" y="-44" width="150" height="88" rx="5" fill="#F7F3E8" stroke="#FF5C5C" strokeWidth="5"/>
          {[0, 1, 2, 3].map((i) => <line key={i} x1="-60" y1={-24 + i * 17} x2="60" y2={-24 + i * 17} stroke="#7BA0C9" strokeWidth="3"/>)}
          <line x1="-15" y1="-32" x2="-15" y2="34" stroke="#7BA0C9" strokeWidth="3"/>
          <line x1="27" y1="-32" x2="27" y2="34" stroke="#7BA0C9" strokeWidth="3"/>
        </g>
        <Sheet x={690} y={900} r={12} s={0.72} accent="#44D17A"/>
        <Sheet x={1060} y={935} r={-17} s={0.66} accent="#FFD43B"/>
      </g>

      {flying.map((p, i) => {
        const q = e.clamp01(e.seg(3.22 + p.d, 5.15 + p.d, t));
        if (q <= 0) return null;
        const px = p.x + p.dx * q;
        const py = p.y + p.dy * q - Math.sin(q * Math.PI) * (190 + i * 12) + q * q * 110;
        return <Sheet key={i} x={px} y={py} r={p.r * q} s={p.s} accent={i % 3 === 0 ? '#FF5C5C' : i % 3 === 1 ? '#2878F0' : '#44D17A'}/>;
      })}

      {slide > 0.03 && caught < 0.95 && (
        <g opacity={(1 - caught) * 0.85} stroke="#FFD93D" strokeWidth="9" strokeLinecap="round">
          <path d="M890 760 L760 725"/><path d="M960 805 L770 805"/><path d="M1010 845 L825 885"/>
        </g>
      )}

      <g transform={`translate(${x} ${y}) rotate(${rotation})`}>
        <Sigma run={run} slide={slide} carry={carry}/>
      </g>

      {slip > 0 && slip < 1 && (
        <g transform="translate(920 690)" fill="#FFD93D" stroke="#161A2B" strokeWidth="4">
          <path d="M0-54 L12-14 L53-16 L20 10 L31 50 L0 26 L-31 50 L-20 10 L-53-16 L-12-14Z" transform="scale(.55)"/>
          <path d="M-105-40 L-90-55 M-112 5 L-137 9 M70-75 L83-99" fill="none" stroke="#FFD93D" strokeWidth="10" strokeLinecap="round"/>
        </g>
      )}

      {reach > 0 && (
        <g opacity={reach} transform={`translate(${1990 - 85 * reach} 1015) scale(${-1.28 * reach} 1.28)`}>
          <CharacterSide pose="stand" armL={[-82, -18]} armR={[-72, -12]} headTurn={-8} mood="surprised"/>
        </g>
      )}

      {caught > 0 && (
        <g transform={`translate(1615 690) scale(${0.5 + caught * 0.6})`} opacity={1 - e.seg(5.55, 6.35, t)} filter="url(#softGlow)">
          <path d="M0-45 L11-12 L46-10 L18 11 L28 44 L0 24 L-28 44 L-18 11 L-46-10 L-11-12Z" fill="#FFD93D"/>
          <circle r="70" fill="none" stroke="#44D17A" strokeWidth="7" opacity="0.65"/>
        </g>
      )}

      <g opacity="0.9">
        <path d="M0 1015 L180 970 L330 1080 H0Z" fill="#0C1129"/>
        <Sheet x={125} y={1010} r={-16} s={1.45} accent="#2878F0"/>
        <path d="M1760 1015 L1920 960 V1080 H1690Z" fill="#0C1129"/>
      </g>

      <path d="M35 1000 H460" stroke="#2878F0" strokeWidth="10" opacity="0.4"/>
      <path d="M35 1025 H300" stroke="#FFD93D" strokeWidth="6" opacity="0.65"/>
    </svg>
  );
}