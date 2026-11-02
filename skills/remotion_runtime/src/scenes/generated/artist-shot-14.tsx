import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#101b46';
export const META = {14: {bg: '#101b46'}};

export function Shot14() {
  const e = useE();
  const t = e.shotT;
  const pop = e.back(e.clamp01((t - 0.28) / 0.48));
  const thumbs = e.easeOut(e.clamp01((t - 0.72) / 0.42));
  const beat = e.pulse(1);
  const zoom = 1 + 0.035 * e.easeIO(e.shotU);
  const earthShift = (t * 34) % 64;

  const landisQuestionR = [-158, -32];
  const landisThumbR = [-112, -88];
  const armR: [number, number] = [
    e.lerp(landisQuestionR[0], landisThumbR[0], thumbs),
    e.lerp(landisQuestionR[1], landisThumbR[1], thumbs),
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="s14-room" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#263b83"/>
          <stop offset="0.55" stopColor="#172554"/>
          <stop offset="1" stopColor="#0b1230"/>
        </linearGradient>
        <linearGradient id="s14-screen" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#194b91"/>
          <stop offset="1" stopColor="#102b62"/>
        </linearGradient>
        <linearGradient id="s14-card" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fffdf2"/>
          <stop offset="1" stopColor="#ffe991"/>
        </linearGradient>
        <radialGradient id="s14-globe" cx="35%" cy="28%" r="75%">
          <stop offset="0" stopColor="#68efff"/>
          <stop offset="0.6" stopColor="#2187e8"/>
          <stop offset="1" stopColor="#1552a4"/>
        </radialGradient>
        <pattern id="s14-scan" width="8" height="8" patternUnits="userSpaceOnUse">
          <rect width="8" height="3" fill="#ffffff" opacity="0.035"/>
        </pattern>
        <pattern id="s14-grid" width="48" height="48" patternUnits="userSpaceOnUse">
          <path d="M48 0H0V48" fill="none" stroke="#62dffc" strokeWidth="2" opacity="0.1"/>
        </pattern>
        <filter id="s14-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="16" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="s14-shadow" x="-40%" y="-40%" width="180%" height="190%">
          <feDropShadow dx="0" dy="18" stdDeviation="16" floodColor="#050a20" floodOpacity="0.65"/>
        </filter>
        <clipPath id="s14-screenClip">
          <rect x="102" y="102" width="1120" height="690" rx="24"/>
        </clipPath>
        <clipPath id="s14-earthClip">
          <circle cx="442" cy="402" r="205"/>
        </clipPath>
      </defs>

      <rect width="1920" height="1080" fill="url(#s14-room)"/>
      <circle cx="1600" cy="170" r="410" fill="#5138a8" opacity="0.2"/>
      <path d="M0 875L1920 700V1080H0Z" fill="#0b132f"/>
      <path d="M0 942L1920 770" stroke="#385397" strokeWidth="5" opacity="0.45"/>

      <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
        {/* 屏幕后光与机身 */}
        <rect x="65" y="62" width="1195" height="790" rx="48" fill="#267cf0" opacity="0.22" filter="url(#s14-glow)"/>
        <rect x="66" y="64" width="1192" height="780" rx="42" fill="#080e25" stroke="#5671a9" strokeWidth="10" filter="url(#s14-shadow)"/>
        <rect x="88" y="86" width="1148" height="724" rx="30" fill="#152344"/>

        <g clipPath="url(#s14-screenClip)">
          <rect x="102" y="102" width="1120" height="690" fill="url(#s14-screen)"/>
          <rect x="102" y="102" width="1120" height="690" fill="url(#s14-grid)"/>
          <circle cx="450" cy="400" r="310" fill="#3ee7ed" opacity="0.08"/>
          <path d="M110 685C330 590 520 710 735 610S1050 540 1230 620V800H110Z" fill="#102452"/>

          {/* 科普节目顶栏 */}
          <rect x="102" y="102" width="1120" height="66" fill="#0c1b41" opacity="0.94"/>
          <circle cx="142" cy="135" r="10" fill="#ff647c"/>
          <circle cx="174" cy="135" r="10" fill="#ffd93d"/>
          <circle cx="206" cy="135" r="10" fill="#44d17a"/>
          <text x="250" y="145" fill="#b8eaff" fontSize="25" fontWeight="700" fontFamily="sans-serif" letterSpacing="3">SIGMA 科普直播间</text>
          <rect x="1000" y="119" width="176" height="34" rx="17" fill="#ff4f79"/>
          <circle cx="1027" cy="136" r="6" fill="#ffffff"/>
          <text x="1044" y="144" fill="#ffffff" fontSize="20" fontWeight="800" fontFamily="sans-serif">升级演示中</text>

          {/* 像素地球 */}
          <g filter="url(#s14-glow)">
            <circle cx="442" cy="402" r="213" fill="none" stroke="#79f5ff" strokeWidth="8" opacity="0.65"/>
          </g>
          <circle cx="442" cy="402" r="205" fill="url(#s14-globe)"/>
          <g clipPath="url(#s14-earthClip)">
            <g transform={`translate(${-earthShift} 0)`} shapeRendering="crispEdges">
              {[0, 1, 2].map((k) => (
                <g key={k} transform={`translate(${k * 640} 0)`}>
                  <path d="M270 245h64v24h40v24h32v48h-24v48h-48v24h-40v72h-48v-48h-32v-72h24v-48h32z" fill="#55dc82"/>
                  <path d="M486 220h48v24h48v48h40v48h-24v24h-48v-24h-40v-48h-48v-48h24z" fill="#72e38e"/>
                  <path d="M550 458h72v24h32v72h-40v48h-32v72h-48v-48h-24v-96h40z" fill="#44c979"/>
                  <path d="M214 520h48v24h48v48h-24v24h-72z" fill="#8bea91"/>
                </g>
              ))}
            </g>
            <path d="M236 402H648M442 196V608" stroke="#b9f8ff" strokeWidth="4" opacity="0.25"/>
            <ellipse cx="442" cy="402" rx="205" ry="78" fill="none" stroke="#b9f8ff" strokeWidth="4" opacity="0.25"/>
            <ellipse cx="442" cy="402" rx="92" ry="205" fill="none" stroke="#b9f8ff" strokeWidth="4" opacity="0.22"/>
          </g>
          <path d="M190 400C210 202 403 112 589 209" fill="none" stroke="#ffd93d" strokeWidth="8" strokeDasharray="18 18"/>
          <path d="M578 188l38 31-45 14z" fill="#ffd93d"/>

          {/* 地球上的知识点标记 */}
          <g transform={`translate(0 ${-5 * beat})`}>
            <rect x="286" y="230" width="48" height="48" rx="8" fill="#ffd93d" stroke="#fff6bb" strokeWidth="5"/>
            <text x="310" y="265" textAnchor="middle" fontSize="32" fontWeight="900" fill="#173a6b" fontFamily="sans-serif">?</text>
            <path d="M322 282l28 34" stroke="#ffd93d" strokeWidth="6"/>
          </g>

          {/* 屏幕里的 Sigma：由提问姿势转为同时点赞 */}
          <Actor
            Character={Character}
            x={855}
            y={773}
            s={0.93}
            armL={[-105 - 12 * thumbs, -80]}
            armR={[-62 - 45 * thumbs, -72 - 18 * thumbs]}
            headTurn={-8}
            mood="calm"
          />
          <g transform="translate(826 632)" opacity={0.85}>
            <rect width="62" height="38" rx="8" fill="#2878f0"/>
            <path d="M31 0l7 12 14 2-10 10 3 14-14-7-13 7 2-14-10-10 14-2z" fill="#ffd93d"/>
          </g>

          <rect x="102" y="102" width="1120" height="690" fill="url(#s14-scan)" pointerEvents="none"/>
        </g>

        {/* 显示器下沿和经验条 */}
        <rect x="88" y="796" width="1148" height="34" fill="#111a35"/>
        <circle cx="662" cy="813" r="7" fill="#44d17a" filter="url(#s14-glow)"/>
        <path d="M588 844h150l36 94H552z" fill="#11182c"/>
        <rect x="500" y="928" width="326" height="30" rx="15" fill="#202c4a"/>
        <rect x="142" y="862" width="480" height="30" rx="15" fill="#0a1432" stroke="#5c76a8" strokeWidth="4"/>
        <rect x="148" y="868" width={250 + 190 * e.easeOut(e.shotU)} height="18" rx="9" fill="#ffd93d"/>
        <text x="148" y="850" fill="#ffe983" fontSize="20" fontWeight="800" fontFamily="monospace">EXP  +999  持续升级</text>

        {/* Landis 前景近景 */}
        <path d="M1210 1080C1230 880 1325 800 1470 772C1660 738 1850 850 1920 1000V1080Z" fill="#111a38" opacity="0.7"/>
        <Actor
          Character={Character}
          x={1570}
          y={1190}
          s={1.45}
          armL={[-104, -86]}
          armR={armR}
          headTurn={-10}
          tilt={-3}
          mood={thumbs > 0.6 ? 'calm' : 'surprised'}
        />

        {/* 弹到脸前的答案卡，故意遮挡一部分前景形成纵深 */}
        <g transform={`translate(1270 320) rotate(-7) scale(${Math.max(0.001, pop)})`} filter="url(#s14-shadow)">
          <rect x="-16" y="-16" width="526" height="270" rx="30" fill="#ffd93d" opacity="0.35" filter="url(#s14-glow)"/>
          <rect width="494" height="238" rx="25" fill="url(#s14-card)" stroke="#ffffff" strokeWidth="8"/>
          <rect x="22" y="20" width="116" height="42" rx="21" fill="#2878f0"/>
          <text x="80" y="50" textAnchor="middle" fill="#ffffff" fontSize="24" fontWeight="900" fontFamily="sans-serif">答案卡</text>
          <text x="28" y="112" fill="#173a6b" fontSize="32" fontWeight="900" fontFamily="sans-serif">问：为什么一直升级？</text>
          <text x="28" y="164" fill="#172554" fontSize="29" fontWeight="700" fontFamily="sans-serif">答：每学会一点，</text>
          <text x="28" y="205" fill="#172554" fontSize="29" fontWeight="700" fontFamily="sans-serif">技能树就亮一颗星！</text>
          <path d="M421 24l11 24 27 3-20 19 6 27-24-13-24 13 5-27-19-19 27-3z" fill="#ffd93d" stroke="#efaa22" strokeWidth="4"/>
          <path d="M8 224l-52 62 90-48z" fill="#ffe991" stroke="#ffffff" strokeWidth="7" strokeLinejoin="round"/>
        </g>

        {/* 双人点赞的节拍星光 */}
        <g opacity={thumbs} fill="#ffd93d">
          <path d="M1190 250l8 20 21 2-16 14 5 21-18-11-19 11 5-21-15-14 21-2z"/>
          <path d="M1780 350l7 16 18 2-14 12 4 18-15-9-16 9 5-18-14-12 18-2z"/>
          <rect x="1128" y="330" width="16" height="16" transform="rotate(25 1136 338)"/>
          <rect x="1822" y="268" width="14" height="14" transform="rotate(45 1829 275)"/>
        </g>
      </g>

      <rect width="1920" height="1080" fill="none" stroke="#080d24" strokeWidth="42" opacity="0.38"/>
    </svg>
  );
}