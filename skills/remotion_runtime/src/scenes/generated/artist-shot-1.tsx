import React from 'react';
import {useE} from '../../engine/context';

export const BG = '#DEC19B';
export const META = {1: {bg: '#DEC19B'}};

const F = (x: number) => x - Math.floor(x);
const R = (i: number) => F(Math.sin(i * 127.1 + 311.7) * 43758.5453);

export const Shot1: React.FC = () => {
  const e = useE();
  const t = e.shotT;
  const u = e.clamp01(e.shotU);

  // 极缓慢推
  const push = 1 + 0.065 * e.easeIO(u);
  const CX = 880;
  const CY = 520;

  /* ---------------- 木纹 ---------------- */
  const grain: React.ReactNode[] = [];
  for (let i = 0; i < 28; i++) {
    const y0 = 248 + i * 31 + R(i) * 14;
    const a = 5 + R(i + 40) * 12;
    const d = `M -140 ${y0} C 360 ${y0 - a} 740 ${y0 + a * 0.9} 1160 ${y0 - a * 0.4} S 1740 ${y0 + a * 0.8} 2060 ${y0 - a * 0.5}`;
    grain.push(
      <path
        key={'g' + i}
        d={d}
        stroke="#C5A57E"
        strokeWidth={1.3 + R(i + 9) * 2.2}
        fill="none"
        opacity={0.13 + R(i + 21) * 0.2}
        strokeLinecap="round"
      />
    );
  }

  /* ---------------- 木节 ---------------- */
  const knots: React.ReactNode[] = [];
  for (let i = 0; i < 5; i++) {
    const kx = 120 + R(i + 300) * 1700;
    const ky = 330 + R(i + 340) * 690;
    knots.push(
      <g key={'k' + i} opacity={0.22}>
        <ellipse cx={kx} cy={ky} rx={44 + R(i + 380) * 40} ry={16 + R(i + 400) * 14} fill="none" stroke="#B99169" strokeWidth={2.4}/>
        <ellipse cx={kx} cy={ky} rx={20 + R(i + 420) * 16} ry={8 + R(i + 440) * 6} fill="#C9AE8B" opacity={0.6}/>
      </g>
    );
  }

  /* ---------------- 纸屑 ---------------- */
  const cCols = ['#EBD3B4', '#C9AE8B', '#E2703A', '#9FBF8F', '#E9A63B', '#D8C3A2'];
  const confetti: React.ReactNode[] = [];
  for (let i = 0; i < 64; i++) {
    let x = -40 + R(i + 3) * 2000;
    let y = 275 + R(i + 61) * 830;
    const inPaper = Math.abs(x - 880) < 390 && Math.abs(y - 575) < 275;
    if (inPaper) {
      y = y < 575 ? 575 - 282 - R(i + 5) * 70 : 575 + 282 + R(i + 5) * 70;
    }
    if (y > 1060) y = 1060;
    if (y < 285) y = 285;
    const s = 7 + R(i + 131) * 13;
    const rot = R(i + 151) * 360;
    const col = cCols[Math.floor(R(i + 171) * cCols.length) % cCols.length];
    const drift = Math.sin(t * 0.85 + i * 1.3) * 3;
    confetti.push(
      <g
        key={'c' + i}
        transform={`translate(${x} ${y + drift}) rotate(${rot})`}
        opacity={0.55 + R(i + 191) * 0.45}
      >
        {i % 3 === 0 ? (
          <polygon points={`0,${-s} ${s * 0.9},${s * 0.6} ${-s * 0.8},${s * 0.5}`} fill={col}/>
        ) : (
          <rect x={-s / 2} y={-s / 3} width={s} height={s * 0.66} rx={1.2} fill={col}/>
        )}
      </g>
    );
  }

  /* ---------------- 光带微尘 ---------------- */
  const dust: React.ReactNode[] = [];
  for (let i = 0; i < 48; i++) {
    const yy = 40 + R(i + 7) * 960;
    const bandCx = 430 + yy * 0.62;
    const xx = bandCx + (R(i + 77) - 0.5) * 570;
    const s = 1.5 + R(i + 97) * 3.6;
    const fl = Math.sin(t * 0.55 + i * 1.7) * 11;
    const sw = Math.sin(t * 0.35 + i * 0.9) * 8;
    const op = 0.22 + 0.5 * (0.5 + 0.5 * Math.sin(t * 0.8 + i * 1.1));
    dust.push(
      <circle key={'d' + i} cx={xx + sw} cy={yy + fl} r={s} fill="#FFF3D0" opacity={op}/>
    );
  }

  /* ---------------- 缎带摆动 ---------------- */
  const swing = Math.sin(t * 0.9) * 34;
  const swing2 = Math.sin(t * 0.9 + 1.4) * 26;

  return (
    <svg
      viewBox="0 0 1920 1080"
      width="100%"
      height="100%"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <filter id="soft" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="15"/>
        </filter>
        <filter id="soft2" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="26"/>
        </filter>
        <filter id="fgBlur" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="7"/>
        </filter>

        <linearGradient id="lightGrad" x1="0" y1="0" x2="0.65" y2="1">
          <stop offset="0" stopColor="#FFF7E2" stopOpacity="0.9"/>
          <stop offset="0.5" stopColor="#FFF3D8" stopOpacity="0.38"/>
          <stop offset="1" stopColor="#FFF3D8" stopOpacity="0"/>
        </linearGradient>

        <linearGradient id="paperGrad" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0" stopColor="#FEFAF1"/>
          <stop offset="0.62" stopColor="#FAF3E6"/>
          <stop offset="1" stopColor="#F2E6D3"/>
        </linearGradient>

        <linearGradient id="fgRibbonGrad" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#E2703A"/>
          <stop offset="0.55" stopColor="#E9A63B"/>
          <stop offset="1" stopColor="#F2C368"/>
        </linearGradient>

        <radialGradient id="vig" cx="0.5" cy="0.46" r="0.8">
          <stop offset="0.52" stopColor="#7A5C3E" stopOpacity="0"/>
          <stop offset="1" stopColor="#7A5C3E" stopOpacity="0.36"/>
        </radialGradient>

        <linearGradient id="cupGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#D6EAE6" stopOpacity="0.75"/>
          <stop offset="0.4" stopColor="#EEF8F5" stopOpacity="0.5"/>
          <stop offset="1" stopColor="#C9E0DC" stopOpacity="0.7"/>
        </linearGradient>
      </defs>

      {/* 推镜兜底 */}
      <rect x={0} y={0} width={1920} height={1080} fill={BG}/>

      <g transform={`translate(${CX - CX * push} ${CY - CY * push}) scale(${push})`}>
        {/* ================= 远景：暖色墙面 ================= */}
        <rect x={-160} y={-200} width={2240} height={500} fill="#F3DFC2"/>
        <ellipse cx={1200} cy={80} rx={250} ry={115} fill="#EAD1AE" opacity="0.7"/>
        <ellipse cx={1660} cy={30} rx={200} ry={95} fill="#EFD9B8" opacity="0.8"/>
        <ellipse cx={960} cy={140} rx={150} ry={60} fill="#E6CBA6" opacity="0.5"/>

        {/* 窗 */}
        <g>
          <rect x={30} y={-170} width={810} height={410} fill="#FFFAEE"/>
          <polygon points="60,-160 300,-160 150,230 60,230" fill="#FFFFFF" opacity="0.6"/>
          <polygon points="340,-160 520,-160 430,230 290,230" fill="#FFF6DC" opacity="0.5"/>
          <rect x={30} y={-170} width={810} height={410} fill="none" stroke="#AE8551" strokeWidth={13}/>
          <line x1={300} y1={-170} x2={300} y2={240} stroke="#AE8551" strokeWidth={10}/>
          <line x1={560} y1={-170} x2={560} y2={240} stroke="#AE8551" strokeWidth={10}/>
          <line x1={30} y1={66} x2={840} y2={66} stroke="#AE8551" strokeWidth={10}/>
          <rect x={30} y={-170} width={810} height={14} fill="#C79A63" opacity="0.5"/>
        </g>
        {/* 窗台 */}
        <rect x={-160} y={240} width={1010} height={36} fill="#E9D2B0"/>
        <rect x={-160} y={240} width={1010} height={7} fill="#C9AE8B" opacity="0.75"/>
        <rect x={850} y={244} width={1300} height={22} fill="#D9BD98"/>

        {/* ================= 桌面 ================= */}
        <rect x={-160} y={256} width={2240} height={920} fill="#E5C9A3"/>
        <ellipse cx={300} cy={940} rx={440} ry={230} fill="#DCBC92" opacity="0.55"/>
        <ellipse cx={1560} cy={430} rx={400} ry={210} fill="#EFD8B7" opacity="0.5"/>
        <ellipse cx={900} cy={1020} rx={520} ry={180} fill="#D8B78C" opacity="0.4"/>
        {grain}
        {knots}

        {/* 光带（下层） */}
        <g opacity={0.62 + 0.06 * Math.sin(t * 0.5)}>
          <polygon points="150,-140 700,-140 1620,1200 860,1200" fill="url(#lightGrad)"/>
        </g>

        {/* ================= 中景物件 ================= */}
        {/* 麻绳卷 */}
        <g transform="translate(232 392) rotate(-14)">
          <ellipse cx={8} cy={16} rx={78} ry={62} fill="#8C6A48" opacity="0.22" filter="url(#soft)"/>
          <circle r={62} fill="#D3B790"/>
          <circle r={62} fill="none" stroke="#B2916B" strokeWidth={3}/>
          <path d="M 0 -62 A 62 62 0 1 1 -0.5 -38" fill="none" stroke="#C2A279" strokeWidth={7} opacity="0.9"/>
          <path d="M 0 -40 A 40 40 0 1 1 -0.5 -20" fill="none" stroke="#C7A87F" strokeWidth={6} opacity="0.9"/>
          <circle r={16} fill="#E5D2B4"/>
          <path d="M 46 42 C 92 66, 120 40, 148 58" stroke="#C9AE8B" strokeWidth={4} fill="none" strokeLinecap="round"/>
        </g>

        {/* 牛皮纸盒 */}
        <g transform="translate(1382 372) rotate(7)">
          <rect x={-146} y={-92} width={312} height={204} rx={7} fill="#8C6A48" opacity="0.26" filter="url(#soft)"/>
          <path d="M -150 92 L 162 92 L 158 112 L -146 112 Z" fill="#B98F60"/>
          <rect x={-158} y={-100} width={316} height={196} rx={6} fill="#D8B98C"/>
          <rect x={-158} y={-100} width={316} height={196} rx={6} fill="none" stroke="#B98F60" strokeWidth={3}/>
          <path d="M -158 -18 L 158 -18" stroke="#C9A273" strokeWidth={3} opacity="0.9"/>
          <path d="M -120 -70 L 30 -70 M -120 -52 L 80 -52 M -120 60 L 60 60" stroke="#C6A278" strokeWidth={2} opacity="0.7"/>
          <ellipse cx={-40} cy={20} rx={60} ry={30} fill="#E5CBA4" opacity="0.7"/>
          <path d="M 60 -30 C 120 -20, 140 40, 96 62" stroke="#E2703A" strokeWidth={6} fill="none" strokeLinecap="round" opacity={0.85}/>
        </g>

        {/* 水杯 */}
        <g transform="translate(1486 664)">
          <ellipse cx={12} cy={80} rx={92} ry={32} fill="#8C6A48" opacity="0.26" filter="url(#soft)"/>
          <path d="M -78 0 L -70 72 A 70 24 0 0 0 70 72 L 78 0 Z" fill="url(#cupGrad)" stroke="#B7CFCC" strokeWidth={3}/>
          <ellipse cx={0} cy={0} rx={78} ry={28} fill="#EAF5F2" stroke="#B7CFCC" strokeWidth={4}/>
          <ellipse cx={0} cy={5} rx={66} ry={22} fill="#CEE3DF" opacity={0.95}/>
          <ellipse
            cx={0}
            cy={5}
            rx={66 + Math.sin(t * 1.1) * 2}
            ry={22 + Math.sin(t * 1.1) * 1.2}
            fill="none"
            stroke="#FFFFFF"
            strokeWidth={3}
            opacity={0.55}
          />
          <path d="M -46 5 A 52 16 0 0 1 28 -7" stroke="#FFFFFF" strokeWidth={5} fill="none" opacity="0.85" strokeLinecap="round"/>
          <path d="M -60 18 L -56 66" stroke="#FFFFFF" strokeWidth={8} opacity="0.75" strokeLinecap="round"/>
          <path d="M 54 20 L 50 62" stroke="#FFFFFF" strokeWidth={5} opacity="0.5" strokeLinecap="round"/>
        </g>

        {/* 缎带卷 */}
        <g transform="translate(306 748) rotate(-12)">
          <ellipse cx={14} cy={20} rx={116} ry={104} fill="#8C6A48" opacity="0.24" filter="url(#soft)"/>
          <circle r={98} fill="#E9A63B"/>
          <circle r={98} fill="none" stroke="#C9822A" strokeWidth={3}/>
          <path d="M 0 -98 A 98 98 0 1 1 -0.6 -74" fill="none" stroke="#E2703A" strokeWidth={15} opacity={0.95}/>
          <path d="M 0 -74 A 74 74 0 1 1 -0.6 -50" fill="none" stroke="#F2C368" strokeWidth={14} opacity={0.95}/>
          <path d="M 0 -50 A 50 50 0 1 1 -0.6 -28" fill="none" stroke="#E2703A" strokeWidth={13} opacity={0.9}/>
          <circle r={16} fill="#C9822A"/>
          <path
            d={`M 84 46 C 130 ${64 + swing2 * 0.4}, 168 ${22 + swing2 * 0.3}, 206 ${58 + swing2}`}
            stroke="#E2703A"
            strokeWidth={13}
            fill="none"
            strokeLinecap="round"
          />
        </g>

        {/* 桌面花瓣/叶点缀 */}
        <g opacity={0.9}>
          <path d="M 1150 940 C 1178 916, 1214 930, 1206 962 C 1180 976, 1148 966, 1150 940 Z" fill="#9FBF8F" opacity={0.8}/>
          <path d="M 400 300 C 424 280, 456 292, 448 320 C 424 332, 396 324, 400 300 Z" fill="#9FBF8F" opacity={0.7}/>
          <ellipse cx={1620} cy={900} rx={26} ry={16} fill="#E2703A" opacity={0.55} transform="rotate(-18 1620 900)"/>
          <ellipse cx={1712} cy={846} rx={20} ry={12} fill="#E9A63B" opacity={0.55} transform="rotate(24 1712 846)"/>
        </g>

        {/* 空白水彩纸 */}
        <g transform="translate(880 575) rotate(-3.5)">
          <rect x={-336} y={-238} width={700} height={490} rx={6} fill="#8C6A48" opacity="0.25" filter="url(#soft)"/>
          <rect x={-350} y={-248} width={700} height={490} rx={4} fill="url(#paperGrad)"/>
          <rect x={-350} y={-248} width={700} height={490} rx={4} fill="none" stroke="#DFD0B8" strokeWidth={2}/>
          {/* 湿润反光 */}
          <ellipse
            cx={-80}
            cy={-70}
            rx={230 + Math.sin(t * 0.6) * 14}
            ry={152 + Math.sin(t * 0.6) * 8}
            fill="#FFFDF6"
            opacity={0.72 + 0.1 * Math.sin(t * 0.55)}
            filter="url(#soft2)"
          />
          <ellipse
            cx={140}
            cy={110}
            rx={160}
            ry={90}
            fill="#FFFDF8"
            opacity={0.4 + 0.12 * Math.sin(t * 0.45 + 2)}
            filter="url(#soft2)"
          />
          {/* 极淡的水渍 */}
          <ellipse cx={-150} cy={120} rx={120} ry={74} fill="#DCE7DE" opacity={0.18 + 0.05 * Math.sin(t * 0.4)}/>
          <ellipse cx={198} cy={-120} rx={90} ry={56} fill="#E6D9C4" opacity={0.2}/>
          {/* 纸面光斑 */}
          <polygon points="-350,-248 -120,-248 -60,242 -290,242" fill="#FFFFFF" opacity={0.3}/>
          {/* 右下纸边微微卷起 */}
          <path
            d={`M 350 190 L 350 242 L 296 242 C 320 ${222 + Math.sin(t * 0.8) * 4}, 340 ${208 + Math.sin(t * 0.8) * 3}, 350 190 Z`}
            fill="#EFE3CE"
          />
          <path
            d={`M 350 190 C 320 ${218 + Math.sin(t * 0.8) * 4}, 318 ${232 + Math.sin(t * 0.8) * 3}, 296 242`}
            stroke="#D6C4A7"
            strokeWidth={2.6}
            fill="none"
          />
        </g>

        {/* 铅笔横放在纸边 */}
        <g transform="translate(762 872) rotate(-2.5)">
          <rect x={-344} y={8} width={700} height={28} rx={14} fill="#9C7A52" opacity="0.3" filter="url(#soft)"/>
          <rect x={-336} y={-18} width={10} height={36} rx={3} fill="#C9822A"/>
          <rect x={-330} y={-18} width={500} height={36} rx={2} fill="#E9A63B"/>
          <rect x={-330} y={-18} width={500} height={12} fill="#F5C377" opacity="0.9"/>
          <rect x={-330} y={9} width={500} height={9} fill="#C98A2C" opacity="0.6"/>
          <line x1={-330} y1={-2} x2={170} y2={-2} stroke="#C9822A" strokeWidth={1.6} opacity="0.5"/>
          <path d="M 170 -18 L 306 -6 L 306 6 L 170 18 Z" fill="#F2D9B0"/>
          <path d="M 170 -18 L 306 -6 L 306 -1 L 170 1 Z" fill="#F9E7CB" opacity="0.85"/>
          <line x1={196} y1={-14} x2={300} y2={-5} stroke="#D9BC90" strokeWidth={1.4} opacity="0.85"/>
          <line x1={196} y1={12} x2={300} y2={4} stroke="#DFC59C" strokeWidth={1.2} opacity="0.8"/>
          <path d="M 306 -6 L 338 0 L 306 6 Z" fill="#4A4038"/>
          <path d="M 322 -3 L 338 0 L 322 3 Z" fill="#6A5F55"/>
        </g>

        {/* 光带（上层，落在物件上） */}
        <g opacity={0.2 + 0.05 * Math.sin(t * 0.5)}>
          <polygon points="150,-140 700,-140 1620,1200 860,1200" fill="url(#lightGrad)"/>
        </g>

        {/* 纸屑 */}
        {confetti}

        {/* 微尘 */}
        <g>{dust}</g>

        {/* ================= 前景：虚焦缎带末端 ================= */}
        <g filter="url(#fgBlur)">
          <path
            d={`M -120 1140 C 90 ${1010 + swing}, 330 ${880 + swing2}, 620 ${812 + swing * 0.8}`}
            stroke="url(#fgRibbonGrad)"
            strokeWidth={74}
            fill="none"
            strokeLinecap="round"
            opacity={0.95}
          />
          <path
            d={`M -120 1128 C 96 ${998 + swing}, 336 ${868 + swing2}, 626 ${800 + swing * 0.8}`}
            stroke="#F7D79A"
            strokeWidth={18}
            fill="none"
            strokeLinecap="round"
            opacity={0.55}
          />
        </g>
      </g>

      {/* 暗角 */}
      <rect x={0} y={0} width={1920} height={1080} fill="url(#vig)"/>
    </svg>
  );
};