import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#111735';
export const META = {9: {bg: '#111735'}};

function PixelStar({x, y, s = 1, color = '#FFD93D', opacity = 1}: {
  x: number; y: number; s?: number; color?: string; opacity?: number;
}) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity} fill={color}>
      <rect x={-8} y={-38} width={16} height={76}/>
      <rect x={-38} y={-8} width={76} height={16}/>
      <rect x={-25} y={-25} width={16} height={16}/>
      <rect x={9} y={-25} width={16} height={16}/>
      <rect x={-25} y={9} width={16} height={16}/>
      <rect x={9} y={9} width={16} height={16}/>
      <rect x={-12} y={-12} width={24} height={24}/>
    </g>
  );
}

function SkillIcon({kind, active}: {kind: string; active: number}) {
  const ink = active > 0.5 ? '#172554' : '#7381AB';
  return (
    <g transform="translate(-32 -32)">
      {kind === 'doc' && <g>
        <path d="M12 3 H39 L52 16 V59 H12 Z" fill={ink}/>
        <path d="M39 3 V17 H52" fill="none" stroke={active > 0.5 ? '#FFF3B0' : '#A6B0D0'} strokeWidth={4}/>
        <path d="M21 28 H43 M21 38 H43 M21 48 H35" stroke={active > 0.5 ? '#FFF3B0' : '#A6B0D0'} strokeWidth={4}/>
      </g>}
      {kind === 'web' && <g>
        <rect x={3} y={8} width={58} height={47} rx={4} fill="none" stroke={ink} strokeWidth={6}/>
        <path d="M4 21 H60" stroke={ink} strokeWidth={5}/>
        <circle cx={13} cy={15} r={2.5} fill={ink}/>
        <circle cx={22} cy={15} r={2.5} fill={ink}/>
        <path d="M24 38 H42 M36 31 L43 38 L36 45" fill="none" stroke={ink} strokeWidth={5}/>
      </g>}
      {kind === 'mail' && <g>
        <rect x={3} y={12} width={58} height={43} rx={3} fill="none" stroke={ink} strokeWidth={6}/>
        <path d="M6 16 L32 38 L58 16" fill="none" stroke={ink} strokeWidth={6}/>
      </g>}
      {kind === 'motion' && <g fill={ink}>
        <rect x={6} y={28} width={10} height={26}/>
        <rect x={22} y={17} width={10} height={37}/>
        <rect x={38} y={7} width={10} height={47}/>
        <path d="M48 12 L62 24 L48 36 Z"/>
      </g>}
      {kind === 'video' && <g>
        <rect x={3} y={12} width={58} height={42} rx={4} fill="none" stroke={ink} strokeWidth={6}/>
        <path d="M26 22 L46 33 L26 44 Z" fill={ink}/>
        <path d="M14 4 V12 M50 4 V12 M14 54 V62 M50 54 V62" stroke={ink} strokeWidth={4}/>
      </g>}
      {kind === 'pin' && <g>
        <path d="M32 61 C32 61 8 37 8 24 A24 24 0 0 1 56 24 C56 37 32 61 32 61Z" fill={ink}/>
        <circle cx={32} cy={24} r={8} fill={active > 0.5 ? '#FFF3B0' : '#A6B0D0'}/>
      </g>}
    </g>
  );
}

export function Shot9() {
  const e = useE();
  const t = e.shotT;
  const C = e.clamp01;
  const times = [0.35, 1.12, 1.88, 3.0, 3.78, 4.55];
  const acts = times.map((v) => e.easeOut(C((t - v) / 0.28)));
  const nodes = [
    {x: 642, y: 414, kind: 'doc', label: 'DOCS', color: '#58D68D'},
    {x: 960, y: 266, kind: 'web', label: 'BROWSER', color: '#4EB6FF'},
    {x: 1278, y: 414, kind: 'mail', label: 'MAIL', color: '#FF6E91'},
    {x: 708, y: 208, kind: 'motion', label: 'ANIMATION', color: '#FFD93D'},
    {x: 1212, y: 208, kind: 'video', label: 'VIDEO', color: '#B58AFF'},
    {x: 960, y: 448, kind: 'pin', label: 'GUIDE', color: '#45E6D4'},
  ];
  const paths = [
    'M960 735 C950 622 824 566 642 414',
    'M960 735 C960 590 960 426 960 266',
    'M960 735 C970 622 1096 566 1278 414',
    'M888 548 C820 426 772 308 708 208',
    'M1032 548 C1100 426 1148 308 1212 208',
    'M960 654 C960 570 960 510 960 448',
  ];
  const xp = 0.17 + 0.83 * e.easeOut(C((t - 0.1) / 5.15));
  const levelHit = C((t - 2.03) / 0.12);
  const levelScale = 0.7 + 0.3 * e.back(levelHit);
  const level = t < 2.03 ? 12 : 13;
  const bounce = (start: number, amp: number) => {
    const u = (t - start) / 0.88;
    return u > 0 && u < 1 ? Math.sin(u * Math.PI) * amp : 0;
  };
  const jump = bounce(2.02, 94) + bounce(4.48, 62);
  const cheer = jump > 3;
  const flash = Math.max(0, 1 - Math.abs(t - 2.08) / 0.2);
  const bursts = [2.08, 4.52];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="s9bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#151B46"/>
          <stop offset="0.62" stopColor="#25205A"/>
          <stop offset="1" stopColor="#111735"/>
        </linearGradient>
        <linearGradient id="s9trunk" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#273C78"/>
          <stop offset="0.5" stopColor="#4B69B5"/>
          <stop offset="1" stopColor="#202D62"/>
        </linearGradient>
        <linearGradient id="s9xp" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#FF9F43"/>
          <stop offset="0.55" stopColor="#FFD93D"/>
          <stop offset="1" stopColor="#FFF59A"/>
        </linearGradient>
        <radialGradient id="s9aura">
          <stop offset="0" stopColor="#6C5CE7" stopOpacity="0.52"/>
          <stop offset="1" stopColor="#6C5CE7" stopOpacity="0"/>
        </radialGradient>
        <filter id="s9glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="s9soft" x="-30%" y="-60%" width="160%" height="220%">
          <feGaussianBlur stdDeviation="22"/>
        </filter>
        <pattern id="s9grid" width="96" height="54" patternUnits="userSpaceOnUse">
          <path d="M96 0 H0 V54" fill="none" stroke="#6375BD" strokeOpacity="0.13" strokeWidth="2"/>
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill="url(#s9bg)"/>
      <circle cx="960" cy="470" r="620" fill="url(#s9aura)"/>
      <path d="M0 715 Q480 610 960 690 T1920 680 V1080 H0Z" fill="#141C42"/>
      <rect y="665" width="1920" height="415" fill="url(#s9grid)"/>

      {/* distant pixel plaza */}
      <g opacity="0.32" fill="#334479">
        <rect x="72" y="440" width="122" height="210"/>
        <rect x="211" y="510" width="86" height="140"/>
        <rect x="1604" y="480" width="100" height="170"/>
        <rect x="1724" y="402" width="132" height="248"/>
        <rect x="99" y="474" width="18" height="18" fill="#7791D4"/>
        <rect x="146" y="474" width="18" height="18" fill="#7791D4"/>
        <rect x="1760" y="440" width="20" height="20" fill="#7791D4"/>
        <rect x="1805" y="440" width="20" height="20" fill="#7791D4"/>
      </g>
      <g opacity="0.42">
        <PixelStar x={170} y={190} s={0.35} color="#7185CB"/>
        <PixelStar x={1740} y={235} s={0.28} color="#7185CB"/>
        <PixelStar x={380} y={310} s={0.2} color="#7185CB"/>
        <PixelStar x={1510} y={330} s={0.2} color="#7185CB"/>
      </g>

      {/* experience HUD */}
      <g>
        <text x="960" y="48" textAnchor="middle" fill="#DDE7FF" fontFamily="monospace" fontSize="25" fontWeight="700" letterSpacing="7">SKILL TREE · EXPERIENCE</text>
        <rect x="430" y="66" width="1060" height="58" rx="9" fill="#090E28" stroke="#5369AD" strokeWidth="4"/>
        <rect x="445" y="81" width="1030" height="28" rx="3" fill="#202A50"/>
        <rect x="445" y="81" width={1030 * xp} height="28" rx="3" fill="url(#s9xp)"/>
        {Array.from({length: 20}, (_, i) => (
          <rect key={i} x={445 + i * 51.5} y="81" width="4" height="28" fill="#111735" opacity="0.3"/>
        ))}
        <rect x={441 + 1030 * xp} y="73" width="8" height="44" fill="#FFF7C2" filter="url(#s9glow)"/>
        <text x="420" y="105" textAnchor="end" fill="#FFD93D" fontFamily="monospace" fontSize="30" fontWeight="900">XP</text>
        <text x="1505" y="105" fill="#FFF3B0" fontFamily="monospace" fontSize="25" fontWeight="700">+{Math.floor(120 + xp * 880)}</text>
      </g>

      {/* platform and tree silhouette */}
      <ellipse cx="960" cy="823" rx="500" ry="91" fill="#080D26" opacity="0.7"/>
      <ellipse cx="960" cy="800" rx="432" ry="68" fill="#263769" stroke="#516BB3" strokeWidth="4"/>
      <ellipse cx="960" cy="795" rx="350" ry="42" fill="#182550"/>
      <path d="M912 790 L924 650 L875 534 L924 552 L950 405 L975 552 L1036 522 L994 653 L1008 790Z"
        fill="url(#s9trunk)" stroke="#6581CA" strokeWidth="4"/>
      <path d="M960 742 V470" stroke="#7E9BE0" strokeOpacity="0.24" strokeWidth="8"/>

      {/* dormant connections, then illuminated energy */}
      <g fill="none" strokeLinecap="round" strokeLinejoin="round">
        {paths.map((d, i) => <path key={`b${i}`} d={d} stroke="#354574" strokeWidth="24" opacity="0.9"/>)}
        {paths.map((d, i) => <path key={`c${i}`} d={d} stroke="#6B7EB7" strokeWidth="4" strokeDasharray="8 18" opacity="0.6"/>)}
        {paths.map((d, i) => acts[i] > 0 && <g key={`a${i}`}>
          <path d={d} stroke={nodes[i].color} strokeWidth="18" opacity={0.24 * acts[i]} filter="url(#s9glow)"/>
          <path d={d} stroke={nodes[i].color} strokeWidth="7" pathLength="1"
            strokeDasharray="1" strokeDashoffset={1 - acts[i]}/>
          <path d={d} stroke="#FFFFFF" strokeOpacity={0.72 * acts[i]} strokeWidth="3"
            strokeDasharray="3 30" strokeDashoffset={-t * 75}/>
        </g>)}
      </g>

      {/* skill nodes */}
      {nodes.map((n, i) => {
        const a = acts[i];
        const pop = 0.88 + 0.12 * e.back(a);
        const beat = a > 0.99 ? 1 + Math.max(0, Math.sin((t - times[i]) * 5)) * 0.025 : 1;
        return (
          <g key={n.kind} transform={`translate(${n.x} ${n.y}) scale(${pop * beat})`}>
            {a > 0 && <circle r={76 + a * 15} fill={n.color} opacity={0.11 * a} filter="url(#s9soft)"/>}
            <circle r="67" fill="#101938" stroke="#3A4A78" strokeWidth="8"/>
            <circle r="57" fill={a > 0.01 ? n.color : '#27345D'} opacity={0.25 + a * 0.75}/>
            <circle r="57" fill="none" stroke={a > 0.5 ? '#FFF6C7' : '#52618D'} strokeWidth="3" strokeDasharray="7 8"/>
            <SkillIcon kind={n.kind} active={a}/>
            <rect x="-73" y="76" width="146" height="28" rx="4" fill="#0A102C" stroke={a > 0.5 ? n.color : '#3A4A78'} strokeWidth="2"/>
            <text y="97" textAnchor="middle" fill={a > 0.5 ? '#FFFFFF' : '#7280A7'} fontFamily="monospace" fontWeight="700" fontSize="16" letterSpacing="2">{n.label}</text>
            {a > 0 && a < 1 && <circle r={67 + 45 * a} fill="none" stroke="#FFFFFF" strokeWidth={5 * (1 - a)} opacity={1 - a}/>}
            {a >= 1 && <g transform="translate(47 -47)">
              <rect x="-14" y="-14" width="28" height="28" fill="#FFF6BD" transform="rotate(45)"/>
              <path d="M-7 0 L-1 7 L9 -7" fill="none" stroke="#243063" strokeWidth="4"/>
            </g>}
          </g>
        );
      })}

      {/* level number physically punches upward between the pair */}
      <g transform={`translate(960 ${805 - bounce(2.03, 45)}) scale(${levelScale})`} opacity={0.94}>
        <text x="0" y="-56" textAnchor="middle" fill="#FFF4B5" fontFamily="monospace" fontSize="27" fontWeight="900" letterSpacing="8">LEVEL UP!</text>
        <text x="7" y="64" textAnchor="middle" fill="#0A102A" stroke="#0A102A" strokeWidth="18" fontFamily="monospace" fontSize="164" fontWeight="900">{level}</text>
        <text x="0" y="54" textAnchor="middle" fill="#FFD93D" stroke="#FFF2A6" strokeWidth="3" fontFamily="monospace" fontSize="164" fontWeight="900">{level}</text>
        <path d="M-112 80 H112" stroke="#4EB6FF" strokeWidth="8"/>
      </g>

      {/* the upgrade jolt launches both partners */}
      <g transform={`translate(0 ${-jump * 0.82})`}>
        <Actor Character={Character} x={400} y={922} s={0.64}
          mood={cheer ? 'surprised' : 'calm'} tilt={cheer ? -5 : 2}
          armL={cheer ? [-155, -18] : [-32, -24]} armR={cheer ? [-25, -18] : [-12, -28]}
          headTurn={8}/>
      </g>
      <g transform={`translate(0 ${-jump})`}>
        <Actor Character={Character} x={1515} y={922} s={0.49} flip
          mood={cheer ? 'surprised' : 'calm'} tilt={cheer ? 6 : -2}
          armL={cheer ? [-155, -18] : [-25, -25]} armR={cheer ? [-25, -18] : [-12, -28]}
          headTurn={-8}/>
      </g>
      <g fill="none" stroke="#8EA7F4" strokeWidth="5" opacity={jump > 4 ? 0.65 : 0.12}>
        <path d="M330 946 H470 M1430 946 H1570"/>
        <path d="M355 962 H445 M1455 962 H1545"/>
      </g>

      {/* deterministic square confetti, two celebratory sprays */}
      {bursts.map((start, bi) => {
        const age = t - start;
        if (age < 0 || age > 2.8) return null;
        return <g key={bi}>
          {Array.from({length: 58}, (_, i) => {
            const r1 = e.hash(9000 + bi * 100 + i * 7);
            const r2 = e.hash(9100 + bi * 100 + i * 11);
            const r3 = e.hash(9200 + bi * 100 + i * 13);
            const side = i % 2 ? 1 : -1;
            const vx = side * (145 + r1 * 470);
            const vy = -(320 + r2 * 510);
            const x = 960 + vx * age;
            const y = 665 + vy * age + 255 * age * age;
            const rot = (r3 * 170 + age * (160 + r1 * 420)) * side;
            const colors = ['#FFD93D', '#4EB6FF', '#FF6E91', '#58D68D', '#B58AFF', '#FFFFFF'];
            const size = 7 + Math.floor(r2 * 4) * 3;
            return <rect key={i} x={-size / 2} y={-size / 2} width={size} height={size * (i % 3 === 0 ? 2 : 1)}
              transform={`translate(${x} ${y}) rotate(${rot})`} fill={colors[i % colors.length]}
              opacity={C((2.8 - age) / 0.55)}/>;
          })}
        </g>;
      })}

      {flash > 0 && <g opacity={flash * 0.65} filter="url(#s9glow)">
        <PixelStar x={960} y={590} s={4.8} color="#FFF4A8" opacity={0.22}/>
        <path d="M960 145 V800 M510 590 H1410" stroke="#FFF7CF" strokeWidth="5"/>
      </g>}

      {/* foreground pixels preserve the wide stage depth */}
      <g opacity="0.75">
        <rect x="0" y="1005" width="1920" height="75" fill="#090E25"/>
        <path d="M0 1005 H1920" stroke="#344C8A" strokeWidth="5"/>
        <rect x="90" y="978" width="70" height="27" fill="#233568"/>
        <rect x="1760" y="978" width="70" height="27" fill="#233568"/>
      </g>
    </svg>
  );
}