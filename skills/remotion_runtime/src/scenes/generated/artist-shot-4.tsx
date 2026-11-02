import {Character} from './char-hero';
import {useE} from '../../engine/context';

export const BG = '#171638';
export const META = {4: {bg: '#171638'}};

const RED = '#FF5C6C';
const GREEN = '#52E58B';
const CYAN = '#55DDF5';
const YELLOW = '#FFD93D';

export function Shot4() {
  const e = useE();
  const t = e.shotT;
  const enter = e.easeOut(e.seg(0, 0.75, t));
  const camera = 1.015 + 0.025 * e.easeIO(e.shotU);
  const reach = e.easeOut(e.seg(0.15, 0.9, t));
  const armR: [number, number] = [-32 - 82 * reach, -18 - 28 * reach];
  const armL: [number, number] = [-24, -18];

  const cards = [
    {
      x: 570, y: 350, start: 1.05,
      dx: 92, dy: 46, rot: 5,
      kind: 'FILE NAME',
      wrong: 'final_FINAL_??.pptx',
      right: 'Q3_launch_FINAL.pptx',
      meta: 'PRESENTATION  ·  18.4 MB',
    },
    {
      x: 990, y: 410, start: 2.55,
      dx: -72, dy: 76, rot: -4,
      kind: 'VERSION',
      wrong: 'v0.9  /  UNKNOWN',
      right: 'v4.0  /  APPROVED',
      meta: 'CHECKSUM  ·  8F2A—71C0',
    },
    {
      x: 1410, y: 335, start: 4.0,
      dx: 72, dy: -42, rot: 4,
      kind: 'DEADLINE',
      wrong: 'DUE  /  -- : --',
      right: 'DUE  ·  FRI 18:00',
      meta: 'CALENDAR  ·  LAUNCH WEEK',
    },
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="100%" height="100%">
      <defs>
        <linearGradient id="s4bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#251958"/>
          <stop offset="0.52" stopColor="#172554"/>
          <stop offset="1" stopColor="#101B3D"/>
        </linearGradient>
        <radialGradient id="s4aura">
          <stop offset="0" stopColor="#7866FF" stopOpacity=".34"/>
          <stop offset=".6" stopColor="#2878F0" stopOpacity=".11"/>
          <stop offset="1" stopColor="#2878F0" stopOpacity="0"/>
        </radialGradient>
        <linearGradient id="s4panel" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#26376A"/>
          <stop offset="1" stopColor="#17254D"/>
        </linearGradient>
        <linearGradient id="s4root" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#374E91"/>
          <stop offset="1" stopColor="#202C62"/>
        </linearGradient>
        <filter id="s4glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="9" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="s4soft" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="22"/>
        </filter>
        <pattern id="s4dots" width="48" height="48" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="2" fill="#8195DB" opacity=".16"/>
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill="url(#s4bg)"/>
      <rect width="1920" height="1080" fill="url(#s4dots)"/>
      <ellipse cx="1070" cy="350" rx="920" ry="590" fill="url(#s4aura)"/>
      <ellipse cx="340" cy="615" rx="280" ry="250" fill="#FFD93D" opacity=".07" filter="url(#s4soft)"/>

      <g transform={`translate(960 540) scale(${camera}) translate(-960 -540)`}>
        {/* quiet depth layers */}
        <g fill="none" stroke="#7187D0" opacity=".1">
          <path d="M-80 790 C390 650 780 775 1160 650 S1760 530 2020 640" strokeWidth="2"/>
          <path d="M-80 842 C390 702 780 827 1160 702 S1760 582 2020 692" strokeWidth="2"/>
          <rect x="1510" y="85" width="310" height="210" rx="28" strokeWidth="3"/>
          <path d="M1550 140h210M1550 180h155M1550 220h185" strokeWidth="9" strokeLinecap="round"/>
          <path d="M85 190h300M85 230h190" strokeWidth="5" strokeLinecap="round"/>
        </g>

        <g opacity={0.35 + 0.65 * enter}>
          <text x="86" y="100" fill="#9EB5F4" fontFamily="monospace" fontSize="20" letterSpacing="5">PROJECT MEMORY</text>
          <text x="86" y="132" fill="#E9EEFF" fontFamily="sans-serif" fontWeight="700" fontSize="28" letterSpacing="1">LIVE RELINK</text>
          <rect x="86" y="153" width="184" height="5" rx="2.5" fill="#5068AD"/>
          <rect x="86" y="153" width={184 * e.seg(0, 4.6, t)} height="5" rx="2.5" fill={CYAN}/>
        </g>

        {/* memory graph unfolding above Sigma */}
        <g opacity={enter} transform={`translate(1080 260) scale(${0.82 + 0.18 * enter}) translate(-1080 -260)`}>
          <path
            d={`M410 ${490 - 18 * enter} C520 310 690 280 1040 218`}
            fill="none" stroke="#5F78CF" strokeWidth="3" strokeDasharray="8 14"
          />
          <path
            d={`M410 ${490 - 18 * enter} C520 310 690 280 1040 218`}
            fill="none" stroke={CYAN} strokeWidth="3" strokeDasharray="1 170"
            strokeLinecap="round" strokeDashoffset={-t * 120} filter="url(#s4glow)"
          />

          <g transform="translate(950 105)">
            <rect width="390" height="142" rx="25" fill="#0D1534" opacity=".45" transform="translate(0 10)"/>
            <rect width="390" height="142" rx="25" fill="url(#s4root)" stroke="#718BE0" strokeWidth="2"/>
            <rect x="18" y="18" width="54" height="54" rx="14" fill="#172554" stroke="#758DEB"/>
            <path d="M45 30l5.5 12 13 1.5-9.5 9 2.5 13L45 59l-11.5 6.5 2.5-13-9.5-9 13-1.5z" fill={YELLOW}/>
            <text x="90" y="45" fill="#AFC5FF" fontFamily="monospace" fontSize="17" letterSpacing="3">PROJECT ROOT</text>
            <text x="90" y="78" fill="#FFFFFF" fontFamily="sans-serif" fontWeight="800" fontSize="30">ORBIT LAUNCH</text>
            <text x="24" y="119" fill="#88A4E8" fontFamily="monospace" fontSize="15">3 LOST REFERENCES DETECTED</text>
            <circle cx="354" cy="34" r="6" fill={CYAN}>
              <animate attributeName="opacity" values=".35;1;.35" dur="1.2s" repeatCount="indefinite"/>
            </circle>
          </g>

          <path d="M1145 247V292" stroke="#7894E8" strokeWidth="4"/>
          <circle cx="1145" cy="294" r="8" fill="#172554" stroke={CYAN} strokeWidth="3"/>

          {cards.map((c, i) => {
            const f = e.easeOut(e.seg(c.start, c.start + 0.48, t));
            const bx = c.x + c.dx * (1 - f);
            const by = c.y + c.dy * (1 - f);
            const cx = bx + 175;
            const d = `M1145 294 C1145 ${330 + i * 12} ${cx} ${by - 80} ${cx} ${by}`;
            const done = e.seg(c.start + 0.2, c.start + 0.55, t);
            return (
              <g key={c.kind}>
                <path d={d} fill="none" stroke="#0A112C" strokeWidth="12" opacity=".45"/>
                <path d={d} fill="none" stroke={RED} strokeWidth="4" strokeDasharray="9 11" opacity={1 - f}/>
                <path d={d} fill="none" stroke={GREEN} strokeWidth="5" opacity={f} filter="url(#s4glow)"/>
                <circle cx={cx} cy={by} r={7 + 5 * done} fill={f > 0.45 ? GREEN : RED} opacity={0.7 + 0.3 * done}/>

                <g transform={`translate(${bx} ${by}) rotate(${c.rot * (1 - f)} 175 75)`}>
                  <rect x="5" y="10" width="350" height="150" rx="20" fill="#080E25" opacity=".48"/>
                  <rect width="350" height="150" rx="20" fill="url(#s4panel)" stroke="#5D72AF" strokeWidth="2"/>

                  <g opacity={1 - f}>
                    <rect x="-5" y="-5" width="360" height="160" rx="24" fill="none" stroke={RED} strokeWidth="5"/>
                    <path d="M-5 24V-5H24M326-5h29v29M355 126v29h-29M24 155H-5v-29" fill="none" stroke="#FF9AA5" strokeWidth="7"/>
                  </g>
                  <g opacity={f}>
                    <rect x="-3" y="-3" width="356" height="156" rx="22" fill="none" stroke={GREEN} strokeWidth="4" filter="url(#s4glow)"/>
                  </g>

                  <text x="24" y="35" fill="#9EB5E8" fontFamily="monospace" fontSize="16" letterSpacing="2.5">{c.kind}</text>
                  <g fontFamily="monospace" fontSize={i === 0 ? 22 : 24} fontWeight="700">
                    <text x="24" y="78" fill="#FFB1B9" opacity={1 - f}>{c.wrong}</text>
                    <text x="24" y="78" fill="#F3FFF7" opacity={f}>{c.right}</text>
                  </g>
                  <text x="24" y="119" fill="#829ACE" fontFamily="monospace" fontSize="14">{c.meta}</text>

                  <g opacity={1 - f} transform="translate(310 28)">
                    <circle r="17" fill={RED} opacity=".16"/>
                    <path d="M-6-6L6 6M6-6L-6 6" stroke={RED} strokeWidth="4" strokeLinecap="round"/>
                  </g>
                  <g opacity={f} transform={`translate(310 28) scale(${Math.max(0, e.back(f))})`}>
                    <circle r="18" fill={GREEN}/>
                    <path d="M-8 0l6 7L9-7" fill="none" stroke="#102C29" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </g>

                  <rect x="24" y="133" width="302" height="4" rx="2" fill="#101B3D"/>
                  <rect x="24" y="133" width={302 * done} height="4" rx="2" fill={GREEN}/>
                </g>

                {[0, 1, 2, 3].map((p) => {
                  const a = p * Math.PI / 2 + i;
                  const r = 28 + 48 * done;
                  return (
                    <circle
                      key={p}
                      cx={cx + Math.cos(a) * r}
                      cy={by + 75 + Math.sin(a) * r}
                      r={4 - p * 0.45}
                      fill={p % 2 ? YELLOW : GREEN}
                      opacity={Math.sin(Math.PI * done)}
                    />
                  );
                })}
              </g>
            );
          })}
        </g>

        {/* Sigma stays in the foreground, physically directing the repair */}
        <ellipse cx="335" cy="1034" rx="165" ry="30" fill="#080D23" opacity=".5"/>
        <g transform={`translate(335 ${1035 + Math.sin(t * 4.6) * 2}) scale(1.22)`}>
          <Character
            view="front"
            pose="stand"
            armL={armL}
            armR={armR}
            headTurn={9}
            tilt={-2 * reach}
            mood="calm"
          />
        </g>

        {/* command spark travelling from Sigma into the graph */}
        <g opacity={e.seg(0.45, 0.8, t) * (1 - e.seg(4.7, 5.2, t))}>
          <circle cx={450 + 440 * ((t * 0.7) % 1)} cy={475 - 170 * ((t * 0.7) % 1)} r="5" fill={YELLOW} filter="url(#s4glow)"/>
        </g>

        <g transform="translate(1510 900)" opacity={e.seg(4.45, 4.9, t)}>
          <rect width="310" height="82" rx="41" fill="#132B3D" stroke={GREEN} strokeWidth="2"/>
          <circle cx="43" cy="41" r="22" fill={GREEN}/>
          <path d="M32 41l8 9 15-19" fill="none" stroke="#14352C" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
          <text x="80" y="35" fill="#8DAEAF" fontFamily="monospace" fontSize="14" letterSpacing="2">MEMORY RESTORED</text>
          <text x="80" y="60" fill="#E9FFF1" fontFamily="sans-serif" fontWeight="700" fontSize="21">3 / 3 CONNECTED</text>
        </g>
      </g>

      <rect width="1920" height="1080" fill="none" stroke="#080D25" strokeOpacity=".32" strokeWidth="34"/>
    </svg>
  );
}