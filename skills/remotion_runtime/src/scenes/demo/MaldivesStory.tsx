import React from 'react';
import {noise} from '@remotion/effects/noise';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Solid,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const W = 1920;
const H = 1080;
const SANS = '"Microsoft YaHei","PingFang SC","Noto Sans SC","Segoe UI",sans-serif';

const EASE = Easing.bezier(0.16, 1, 0.3, 1);
const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

const inv = (
  v: number,
  input: number[],
  output: number[],
  easing: (t: number) => number = Easing.linear
) =>
  interpolate(v, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });

/** 确定性伪随机，避免逐帧抖动 */
const rnd = (seed: number) => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

const spiralPath = (cx: number, cy: number, R: number, turns = 2.1, steps = 44) => {
  let d = '';
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const a = t * Math.PI * 2 * turns;
    const r = R * (1 - t * 0.88);
    d += `${i === 0 ? 'M' : 'L'} ${(cx + Math.cos(a) * r).toFixed(1)} ${(
      cy +
      Math.sin(a) * r
    ).toFixed(1)} `;
  }
  return d;
};

/** 生成有机闭合轮廓：用谐波扰动半径，避免出现正圆的“甜甜圈”感 */
const blobPath = (cx: number, cy: number, rx: number, ry: number, seed: number, wob = 0.12) => {
  const n = 46;
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    const k =
      1 +
      Math.sin(a * 2 + seed) * wob +
      Math.sin(a * 3 + seed * 1.7) * wob * 0.7 +
      Math.sin(a * 5 + seed * 2.3) * wob * 0.35;
    pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
  }
  const mid = (p: [number, number], q: [number, number]) =>
    `${((p[0] + q[0]) / 2).toFixed(1)} ${((p[1] + q[1]) / 2).toFixed(1)}`;
  let d = `M ${mid(pts[n - 1], pts[0])} `;
  for (let i = 0; i < n; i++) {
    const p = pts[i];
    const q = pts[(i + 1) % n];
    d += `Q ${p[0].toFixed(1)} ${p[1].toFixed(1)} ${mid(p, q)} `;
  }
  return `${d}Z`;
};

// ---------------------------------------------------------------- 渐变定义

const Defs: React.FC = () => (
  <defs>
    <linearGradient id="skyDay" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#7fcfe6" />
      <stop offset="48%" stopColor="#bfeaf0" />
      <stop offset="100%" stopColor="#f6f1de" />
    </linearGradient>
    <linearGradient id="skyGolden" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#8fc9e0" />
      <stop offset="45%" stopColor="#ffd9a5" />
      <stop offset="78%" stopColor="#ffab74" />
      <stop offset="100%" stopColor="#ff8f63" />
    </linearGradient>
    <linearGradient id="skySunset" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#5d4a86" />
      <stop offset="32%" stopColor="#c76b86" />
      <stop offset="58%" stopColor="#ff9a72" />
      <stop offset="80%" stopColor="#ffc489" />
      <stop offset="100%" stopColor="#ffe0ae" />
    </linearGradient>
    <linearGradient id="seaDeep" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#0c6f8f" />
      <stop offset="55%" stopColor="#18a9b8" />
      <stop offset="100%" stopColor="#35c8bd" />
    </linearGradient>
    <linearGradient id="seaShallow" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#37c3bd" />
      <stop offset="100%" stopColor="#b6f3e2" />
    </linearGradient>
    <linearGradient id="seaDusk" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#c7685f" />
      <stop offset="55%" stopColor="#7a4667" />
      <stop offset="100%" stopColor="#332a4d" />
    </linearGradient>
    <linearGradient id="cabinWall" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#fbf6ec" />
      <stop offset="60%" stopColor="#e9e0d2" />
      <stop offset="100%" stopColor="#cfc3b2" />
    </linearGradient>
    <linearGradient id="roomWall" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#3c3a52" />
      <stop offset="55%" stopColor="#6b5d68" />
      <stop offset="100%" stopColor="#9a7d72" />
    </linearGradient>
    <linearGradient id="duvet" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#fffdf8" />
      <stop offset="60%" stopColor="#f0e6d8" />
      <stop offset="100%" stopColor="#cdbda8" />
    </linearGradient>
    <radialGradient id="sunGlow">
      <stop offset="0%" stopColor="rgba(255,246,214,0.95)" />
      <stop offset="38%" stopColor="rgba(255,203,130,0.42)" />
      <stop offset="100%" stopColor="rgba(255,180,110,0)" />
    </radialGradient>
    <radialGradient id="lampGlow">
      <stop offset="0%" stopColor="rgba(255,206,138,0.75)" />
      <stop offset="55%" stopColor="rgba(255,170,100,0.22)" />
      <stop offset="100%" stopColor="rgba(255,160,90,0)" />
    </radialGradient>
    <linearGradient id="lagoon" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor="#8ff0dd" />
      <stop offset="100%" stopColor="#25b7c0" />
    </linearGradient>
    <filter id="soft40" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="40" />
    </filter>
    <filter id="soft16" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="16" />
    </filter>
    <filter id="soft6" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" />
    </filter>
  </defs>
);

// ---------------------------------------------------------------- 角色

type Mood = 'happy' | 'excited' | 'dizzy' | 'worried' | 'weak' | 'calm' | 'sleep';
type Pose = 'stand' | 'sit' | 'walk';

const SKIN_G = '#ffd7bd';
const SKIN_B = '#f3c49d';
const HAIR_G = '#3a2a30';
const HAIR_B = '#2a2430';
const DRESS = '#ff7f9c';
const DRESS_DARK = '#e26684';
const SHIRT = '#2fb9b5';
const SHORTS = '#2f3f55';

const POSE_ARMS: Record<Pose, {L: [number, number]; R: [number, number]}> = {
  stand: {L: [-66, -92], R: [66, -92]},
  sit: {L: [-48, -134], R: [48, -134]},
  walk: {L: [-78, -88], R: [78, -88]},
};

interface ChibiProps {
  variant: 'male' | 'female';
  x: number;
  y: number;
  s?: number;
  flip?: boolean;
  mood?: Mood;
  pose?: Pose;
  bob?: number;
  tilt?: number;
  armL?: [number, number];
  armR?: [number, number];
  backView?: boolean;
  pale?: boolean;
  silhouette?: string;
  showFlower?: boolean;
  shadow?: boolean;
}

const Face: React.FC<{
  mood: Mood;
  frame: number;
  girl: boolean;
  silhouette?: string;
}> = ({mood, frame, girl, silhouette}) => {
  const ink = silhouette ?? '#35222c';
  const lash = silhouette ?? '#2a1a22';
  const blush = silhouette ?? '#ff8ea6';
  const eyeY = -322;

  const brows = (() => {
    if (mood === 'worried')
      return (
        <g stroke={ink} strokeWidth={6} strokeLinecap="round" opacity={0.85}>
          <path d="M -52 -362 L -26 -352" />
          <path d="M 52 -362 L 26 -352" />
        </g>
      );
    if (mood === 'dizzy')
      return (
        <g stroke={ink} strokeWidth={5} strokeLinecap="round" opacity={0.55}>
          <path d="M -52 -364 Q -40 -370 -26 -362" />
          <path d="M 52 -364 Q 40 -370 26 -362" />
        </g>
      );
    return (
      <g stroke={ink} strokeWidth={6} strokeLinecap="round" opacity={0.7}>
        <path d="M -50 -360 Q -38 -368 -26 -361" />
        <path d="M 50 -360 Q 38 -368 26 -361" />
      </g>
    );
  })();

  const eyes = (() => {
    if (mood === 'dizzy') {
      const rot = (frame * 7) % 360;
      return (
        <g>
          <g transform={`rotate(${rot} -38 ${eyeY})`}>
            <path d={spiralPath(-38, eyeY, 21)} fill="none" stroke={ink} strokeWidth={5} strokeLinecap="round" />
          </g>
          <g transform={`rotate(${-rot} 38 ${eyeY})`}>
            <path d={spiralPath(38, eyeY, 21)} fill="none" stroke={ink} strokeWidth={5} strokeLinecap="round" />
          </g>
        </g>
      );
    }
    if (mood === 'sleep' || (mood === 'calm' && !girl)) {
      return (
        <g stroke={lash} strokeWidth={6} fill="none" strokeLinecap="round">
          <path d="M -52 -320 Q -38 -336 -24 -320" />
          <path d="M 24 -320 Q 38 -336 52 -320" />
        </g>
      );
    }
    if (mood === 'weak') {
      return (
        <g>
          <ellipse cx={-38} cy={eyeY + 3} rx={11} ry={8} fill={ink} />
          <ellipse cx={38} cy={eyeY + 3} rx={11} ry={8} fill={ink} />
          <path d="M -52 -332 Q -38 -340 -24 -334" stroke={lash} strokeWidth={5} fill="none" strokeLinecap="round" />
          <path d="M 24 -334 Q 38 -340 52 -332" stroke={lash} strokeWidth={5} fill="none" strokeLinecap="round" />
        </g>
      );
    }
    const big = mood === 'excited';
    return (
      <g>
        <ellipse cx={-38} cy={eyeY} rx={big ? 12 : 11} ry={big ? 16 : 14} fill={ink} />
        <ellipse cx={38} cy={eyeY} rx={big ? 12 : 11} ry={big ? 16 : 14} fill={ink} />
        <circle cx={-33} cy={eyeY - 7} r={big ? 5.6 : 4.6} fill="#ffffff" />
        <circle cx={43} cy={eyeY - 7} r={big ? 5.6 : 4.6} fill="#ffffff" />
        <circle cx={-42} cy={eyeY + 7} r={2.4} fill="#ffffff" opacity={0.55} />
        <circle cx={34} cy={eyeY + 7} r={2.4} fill="#ffffff" opacity={0.55} />
      </g>
    );
  })();

  const mouth = (() => {
    if (mood === 'excited')
      return (
        <g>
          <path d="M -17 -278 Q 0 -242 17 -278 Z" fill={ink} />
          <path d="M -9 -256 Q 0 -250 9 -256" stroke="#ff8f9d" strokeWidth={5} fill="none" strokeLinecap="round" />
        </g>
      );
    if (mood === 'dizzy')
      return (
        <path
          d="M -18 -278 q 6 -8 12 0 q 6 8 12 0"
          stroke={ink}
          strokeWidth={5}
          fill="none"
          strokeLinecap="round"
        />
      );
    if (mood === 'worried')
      return <path d="M -12 -272 q 12 -8 24 0" stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round" />;
    if (mood === 'weak')
      return <path d="M -12 -276 q 12 7 24 0" stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round" />;
    if (mood === 'sleep') return <ellipse cx={0} cy={-274} rx={7} ry={5} fill={ink} />;
    return <path d="M -15 -278 q 15 14 30 0" stroke={ink} strokeWidth={5.5} fill="none" strokeLinecap="round" />;
  })();

  return (
    <g>
      <ellipse cx={-64} cy={-292} rx={20} ry={11} fill={blush} opacity={0.42} />
      <ellipse cx={64} cy={-292} rx={20} ry={11} fill={blush} opacity={0.42} />
      {brows}
      {eyes}
      {mouth}
    </g>
  );
};

const Chibi: React.FC<ChibiProps> = ({
  variant,
  x,
  y,
  s = 1,
  flip,
  mood = 'happy',
  pose = 'stand',
  bob = 0,
  tilt = 0,
  armL,
  armR,
  backView,
  pale,
  silhouette,
  showFlower = true,
  shadow,
}) => {
  const frame = useCurrentFrame();
  const girl = variant === 'female';
  const c = (col: string) => silhouette ?? col;
  const skin = silhouette ?? (pale ? '#f7dcc4' : girl ? SKIN_G : SKIN_B);
  const hair = silhouette ?? (girl ? HAIR_G : HAIR_B);
  const outfit = silhouette ?? (girl ? DRESS : SHIRT);
  const outfitDark = silhouette ?? (girl ? DRESS_DARK : SHORTS);
  const defaultArms = POSE_ARMS[pose];
  const handL = armL ?? defaultArms.L;
  const handR = armR ?? defaultArms.R;
  const shoulderY = -192;
  const armW = girl ? 24 : 26;

  const arm = (sh: [number, number], hand: [number, number]) => (
    <g>
      <line
        x1={sh[0]}
        y1={sh[1]}
        x2={hand[0]}
        y2={hand[1]}
        stroke={skin}
        strokeWidth={armW}
        strokeLinecap="round"
      />
      <circle cx={hand[0]} cy={hand[1]} r={armW * 0.58} fill={skin} />
      <circle cx={sh[0]} cy={sh[1]} r={girl ? 18 : 19} fill={outfit} />
    </g>
  );

  return (
    <g transform={`translate(${x} ${y + bob}) scale(${flip ? -s : s} ${s}) rotate(${flip ? -tilt : tilt})`}>
      {shadow ? (
        <ellipse cx={0} cy={6} rx={96} ry={16} fill="rgba(20,30,40,0.22)" filter="url(#soft6)" />
      ) : null}

      {/* 后发（女孩长发在头后） */}
      {girl ? <ellipse cx={0} cy={-296} rx={112} ry={126} fill={hair} /> : null}

      {/* 腿 */}
      {pose !== 'sit' ? (
        <g>
          <rect x={-42} y={-92} width={32} height={84} rx={14} fill={skin} />
          <rect x={10} y={-92} width={32} height={84} rx={14} fill={skin} />
          <ellipse cx={-26} cy={-8} rx={26} ry={14} fill={c(girl ? '#fffaf2' : '#f0e6d6')} />
          <ellipse cx={26} cy={-8} rx={26} ry={14} fill={c(girl ? '#fffaf2' : '#f0e6d6')} />
        </g>
      ) : null}

      {/* 身体 */}
      {girl ? (
        <g>
          <path
            d="M -58 -212 C -64 -168 -76 -122 -100 -72 L 100 -72 C 76 -122 64 -168 58 -212 C 28 -226 -28 -226 -58 -212 Z"
            fill={outfit}
          />
          <path
            d="M -100 -72 C -60 -64 60 -64 100 -72 L 104 -60 C 60 -52 -60 -52 -104 -60 Z"
            fill={outfitDark}
            opacity={0.55}
          />
          <path d="M -20 -214 L 20 -214 L 18 -150 L -18 -150 Z" fill={c('#fff6ee')} opacity={0.28} />
        </g>
      ) : (
        <g>
          <rect x={-18} y={-104} width={36} height={34} rx={10} fill={outfitDark} />
          <path
            d="M -60 -206 C -62 -168 -58 -130 -54 -104 L 54 -104 C 58 -130 62 -168 60 -206 C 30 -218 -30 -218 -60 -206 Z"
            fill={outfit}
          />
          <rect x={-58} y={-136} width={116} height={34} rx={16} fill={outfitDark} />
          <path d="M -14 -206 L 14 -206 L 12 -110 L -12 -110 Z" fill="#ffffff" opacity={0.16} />
        </g>
      )}

      {arm([-54, shoulderY], handL)}
      {arm([54, shoulderY], handR)}

      {/* 脖子 */}
      <rect x={-14} y={-240} width={28} height={34} rx={8} fill={silhouette ?? (pale ? '#eec9ae' : skin)} />

      {/* 头 */}
      <circle cx={0} cy={-318} r={100} fill={skin} />

      {backView ? (
        <g>
          <path
            d="M -100 -318 C -100 -400 -58 -436 0 -436 C 58 -436 100 -400 100 -318 C 100 -246 62 -222 0 -222 C -62 -222 -100 -246 -100 -318 Z"
            fill={hair}
          />
          <path d="M -28 -424 Q 0 -444 28 -424" stroke={silhouette ?? '#ffffff'} strokeWidth={4} opacity={0.12} fill="none" />
        </g>
      ) : (
        <g>
          <path
            d="M -99 -318 C -101 -393 -56 -430 0 -430 C 58 -430 102 -392 99 -318 C 88 -345 68 -351 46 -370 C 26 -351 6 -357 -14 -371 C -36 -351 -70 -353 -99 -318 Z"
            fill={hair}
          />
          {girl ? (
            <>
              <rect x={-108} y={-336} width={30} height={116} rx={15} fill={hair} />
              <rect x={78} y={-336} width={30} height={116} rx={15} fill={hair} />
            </>
          ) : (
            <path d="M -14 -428 C 4 -452 26 -450 36 -430" stroke={hair} strokeWidth={14} fill="none" strokeLinecap="round" />
          )}
          <Face mood={mood} frame={frame} girl={girl} silhouette={silhouette} />
          {girl && showFlower && !silhouette ? (
            <g transform="translate(80 -384)">
              {[0, 72, 144, 216, 288].map((a) => (
                <ellipse key={a} rx={9} ry={14} fill="#fffdf6" transform={`rotate(${a}) translate(0 -13)`} />
              ))}
              <circle r={7} fill="#ffcf6b" />
            </g>
          ) : null}
        </g>
      )}
      {/* 晕眩符号 */}
      {mood === 'dizzy' && !backView ? (
        <g opacity={0.9}>
          <path
            d="M 74 -430 q 12 -8 18 2 q -12 8 -18 -2"
            fill={silhouette ?? '#9fe6ff'}
            stroke={silhouette ?? '#7fd4ee'}
            strokeWidth={2}
          />
          <circle cx={92} cy={-448} r={3} fill={silhouette ?? '#9fe6ff'} />
        </g>
      ) : null}
      {mood === 'worried' && !backView ? (
        <path
          d="M 86 -398 q 8 0 8 9 q 0 9 -8 14 q -8 -5 -8 -14 q 0 -9 8 -9"
          fill={silhouette ?? '#a8e3ff'}
          opacity={0.85}
        />
      ) : null}
    </g>
  );
};

// ---------------------------------------------------------------- 场景道具

const Seaplane: React.FC<{
  x: number;
  y: number;
  s: number;
  prop: number;
  tilt?: number;
  riders?: boolean;
}> = ({x, y, s, prop, tilt = 0, riders = true}) => (
  <g transform={`translate(${x} ${y}) scale(${s}) rotate(${tilt})`}>
    {/* 浮筒 */}
    <g>
      <rect x={-128} y={54} width={196} height={22} rx={11} fill="#eef3f7" />
      <path d="M -128 60 C -152 60 -160 66 -162 74 C -154 78 -140 76 -128 76 Z" fill="#dfe8ef" />
      <rect x={-112} y={78} width={168} height={16} rx={8} fill="#cfdae2" />
      <rect x={-92} y={54} width={134} height={6} rx={3} fill="#9fb4c4" />
    </g>
    {/* 支柱 */}
    <g stroke="#c8d6e0" strokeWidth={7} strokeLinecap="round">
      <path d="M -80 34 L -64 54" />
      <path d="M 30 34 L 14 54" />
      <path d="M -20 34 L -14 74" />
    </g>
    {/* 尾翼 */}
    <g>
      <path d="M -192 -6 L -150 -6 L -146 -74 L -178 -70 Z" fill="#f4f9fc" />
      <path d="M -190 -6 L -152 -6 L -150 -22 L -188 -22 Z" fill="#2b7fd0" opacity={0.85} />
      <rect x={-214} y={-22} width={54} height={13} rx={6} fill="#f4f9fc" />
    </g>
    {/* 机身 */}
    <path
      d="M -172 0 C -172 -26 -142 -36 -102 -36 L 118 -36 C 152 -36 172 -24 180 0 C 172 24 152 36 118 36 L -102 36 C -142 36 -172 26 -172 0 Z"
      fill="#f8fbfd"
    />
    <path
      d="M -168 10 L 172 10 L 170 20 L -166 20 Z"
      fill="#2b7fd0"
      opacity={0.9}
    />
    {/* 舷窗 */}
    <g>
      {[-92, -44, 8, 60].map((wx) => (
        <circle key={wx} cx={wx} cy={0} r={12} fill="#2f5060" />
      ))}
      {riders ? (
        <g>
          <circle cx={-44} cy={2} r={9} fill={SKIN_G} />
          <path d="M -54 4 C -54 -12 -34 -12 -34 4 Z" fill={HAIR_G} />
          <circle cx={8} cy={2} r={9} fill={SKIN_B} />
          <path d="M -2 4 C -2 -12 18 -12 18 4 Z" fill={HAIR_B} />
        </g>
      ) : null}
      {[-92, -44, 8, 60].map((wx) => (
        <circle key={`r${wx}`} cx={wx} cy={0} r={12} fill="none" stroke="#dbe6ee" strokeWidth={3} />
      ))}
    </g>
    {/* 机翼 */}
    <path d="M -46 -70 L 116 -70 C 128 -70 132 -62 126 -56 L 104 -50 L -40 -50 Z" fill="#f2f7fb" />
    <rect x={-46} y={-58} width={160} height={9} rx={4} fill="#2b7fd0" opacity={0.8} />
    <path d="M -22 -50 L -14 -36 M 78 -50 L 72 -36" stroke="#c8d6e0" strokeWidth={6} />
    {/* 机头 + 螺旋桨 */}
    <ellipse cx={182} cy={0} rx={9} ry={52} fill="#9cb0bf" opacity={0.16} />
    <g transform={`rotate(${prop} 182 0)`}>
      <rect x={176} y={-50} width={12} height={100} rx={6} fill="#7d93a4" opacity={0.75} />
      <rect x={132} y={-6} width={100} height={12} rx={6} fill="#7d93a4" opacity={0.55} />
    </g>
    <circle cx={182} cy={0} r={9} fill="#44586a" />
  </g>
);

const Cloud: React.FC<{x: number; y: number; s: number; o?: number}> = ({x, y, s, o = 0.9}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={o} filter="url(#soft16)">
    <ellipse cx={0} cy={0} rx={110} ry={38} fill="#ffffff" />
    <ellipse cx={-58} cy={-14} rx={62} ry={30} fill="#ffffff" />
    <ellipse cx={62} cy={-8} rx={70} ry={34} fill="#ffffff" />
  </g>
);

const Palm: React.FC<{x: number; y: number; s: number; sway: number; dark?: boolean}> = ({
  x,
  y,
  s,
  sway,
  dark,
}) => (
  <g transform={`translate(${x} ${y}) scale(${s}) rotate(${sway})`}>
    <path d="M -6 0 C -14 -80 6 -160 18 -230 L 34 -228 C 20 -156 4 -80 12 0 Z" fill={dark ? '#2a3a36' : '#9a6b47'} />
    <g fill={dark ? '#243230' : '#2f8f68'}>
      <path d="M 26 -228 C 70 -270 132 -276 168 -252 C 124 -256 76 -244 40 -218 Z" />
      <path d="M 26 -228 C 4 -286 40 -330 88 -342 C 58 -310 52 -268 48 -226 Z" />
      <path d="M 26 -228 C -26 -262 -84 -256 -112 -226 C -66 -242 -18 -234 20 -214 Z" />
      <path d="M 26 -228 C -8 -268 -6 -314 26 -344 C 22 -304 34 -268 44 -232 Z" />
      <path d="M 26 -228 C 66 -232 106 -206 118 -176 C 86 -200 54 -206 30 -206 Z" />
    </g>
    <circle cx={20} cy={-214} r={9} fill="#7a5231" />
    <circle cx={34} cy={-206} r={8} fill="#8a6038" />
  </g>
);

const Villa: React.FC<{x: number; y: number; s: number; dark?: boolean}> = ({x, y, s, dark}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`}>
    <rect x={-90} y={-70} width={180} height={70} fill={dark ? '#3a2a2c' : '#f6ead4'} />
    <path d="M -118 -70 L 0 -132 L 118 -70 Z" fill={dark ? '#2b2023' : '#b3763f'} />
    <path d="M -118 -70 L 0 -132 L 118 -70" fill="none" stroke={dark ? '#1d1618' : '#8f5a2d'} strokeWidth={8} />
    <rect x={-24} y={-52} width={48} height={52} rx={4} fill={dark ? '#1f1719' : '#5b7f8c'} />
    <g stroke={dark ? '#221a1c' : '#cbb08a'} strokeWidth={4}>
      <path d="M -100 -86 L 0 -122 M 0 -122 L 100 -86" />
    </g>
    <g stroke={dark ? '#2b2023' : '#a06a3d'} strokeWidth={7}>
      <path d="M -70 0 L -70 24 M 70 0 L 70 24" />
    </g>
  </g>
);

const Bird: React.FC<{x: number; y: number; s: number; flap: number}> = ({x, y, s, flap}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} stroke="#3b4a5a" strokeWidth={3} fill="none" strokeLinecap="round">
    <path d={`M -10 0 Q -4 ${-6 - flap * 6} 0 0 Q 4 ${-6 - flap * 6} 10 0`} />
  </g>
);

const Star: React.FC<{x: number; y: number; r: number; o: number; fill: string}> = ({x, y, r, o, fill}) => (
  <path
    transform={`translate(${x} ${y}) scale(${r / 10})`}
    d="M 0 -13 L 3.6 -4 L 13 0 L 3.6 4 L 0 13 L -3.6 4 L -13 0 L -3.6 -4 Z"
    fill={fill}
    opacity={o}
  />
);

// ---------------------------------------------------------------- 字幕

// 样片用：这段画面原本自带字幕；进了 MV 之后字幕由引擎歌词层接管，这里关掉。
const Caption: React.FC<{local: number; dur: number; kicker: string; text: string}> = () => null;

const Scrim: React.FC = () => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      right: 0,
      bottom: 0,
      height: 340,
      background: 'linear-gradient(to top, rgba(8,22,30,0.55) 0%, rgba(8,22,30,0) 100%)',
      pointerEvents: 'none',
    }}
  />
);

// ---------------------------------------------------------------- 分镜 1：环礁

const Scene1: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const planeX = inv(local, [0, dur], [240, 1520], easeInOut);
  const planeY = 330 + Math.sin(local * 0.045) * 14 - inv(local, [0, dur], [0, 34]);
  const drift = local * 0.5;

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#skyDay)" />
        <circle cx={1640} cy={170} r={440} fill="url(#sunGlow)" opacity={0.9} />
        <circle cx={1640} cy={170} r={58} fill="#fffdf4" opacity={0.92} filter="url(#soft6)" />

        {[
          {x: 300, y: 200, s: 1.15, o: 0.78, sp: 0.35},
          {x: 820, y: 120, s: 0.8, o: 0.62, sp: 0.5},
          {x: 1280, y: 250, s: 0.95, o: 0.5, sp: 0.28},
          {x: 1760, y: 100, s: 0.62, o: 0.48, sp: 0.42},
        ].map((cl, i) => (
          <Cloud key={i} x={cl.x - drift * cl.sp * 4} y={cl.y} s={cl.s} o={cl.o} />
        ))}

        {/* 海面 */}
        <rect x={0} y={452} width={W} height={H - 452} fill="url(#seaDeep)" />
        <rect x={0} y={452} width={W} height={18} fill="#cdeef2" opacity={0.5} />
        <g opacity={0.28} fill="#7fe3d6">
          <path d={blobPath(380, 900, 420, 150, 1.2, 0.18)} />
          <path d={blobPath(1500, 780, 380, 120, 3.4, 0.2)} />
          <path d={blobPath(1050, 1040, 520, 110, 5.1, 0.16)} opacity={0.7} />
        </g>

        {/* 环礁：沙洲 + 潟湖，形状做不规则处理 */}
        <g transform={`translate(${980 + Math.sin(local * 0.018) * 4} ${812 + Math.sin(local * 0.022) * 3})`}>
          <path d={blobPath(0, 0, 760, 258, 0.6, 0.1)} fill="#0a6d86" opacity={0.55} />
          <path d={blobPath(0, 0, 706, 232, 1.1, 0.1)} fill="#1fb3bd" />
          <path d={blobPath(0, 0, 664, 206, 1.7, 0.11)} fill="#f2e4bf" />
          <path d={blobPath(0, 0, 606, 176, 2.4, 0.12)} fill="url(#lagoon)" />
          <path d={blobPath(-120, 20, 300, 92, 4.6, 0.2)} fill="#3fcfc4" opacity={0.55} />
          <path d={blobPath(320, -30, 200, 58, 6.2, 0.2)} fill="#5cdccd" opacity={0.45} />
          <path d={blobPath(-330, -40, 150, 44, 8.1, 0.22)} fill="#8cefe0" opacity={0.5} />

          {/* 沙洲上的椰林与浅滩 */}
          <g fill="#2f7d5f" opacity={0.85}>
            {Array.from({length: 16}, (_, i) => {
              const a = (i / 16) * Math.PI * 2 + 0.3;
              const x = Math.cos(a) * 660;
              const y = Math.sin(a) * 205;
              return <ellipse key={i} cx={x} cy={y} rx={7 + rnd(i) * 9} ry={4 + rnd(i + 4) * 4} />;
            })}
          </g>
          <g fill="#ffffff" opacity={0.4}>
            {Array.from({length: 34}, (_, i) => {
              const a = (i / 34) * Math.PI * 2;
              const k = 1 + Math.sin(a * 2 + 0.6) * 0.1;
              const x = Math.cos(a) * 640 * k;
              const y = Math.sin(a) * 196 * k;
              return (
                <ellipse
                  key={i}
                  cx={x}
                  cy={y}
                  rx={18 + rnd(i) * 26}
                  ry={2.6}
                  transform={`rotate(${(a * 180) / Math.PI} ${x} ${y})`}
                />
              );
            })}
          </g>
          <g fill="#ffffff" opacity={0.2}>
            {Array.from({length: 26}, (_, i) => (
              <ellipse
                key={i}
                cx={(rnd(i + 40) - 0.5) * 1100}
                cy={(rnd(i + 80) - 0.5) * 320}
                rx={8 + rnd(i + 120) * 30}
                ry={1.8}
              />
            ))}
          </g>
        </g>

        {/* 海面高光 */}
        <g opacity={0.18} stroke="#ffffff" strokeWidth={2}>
          {Array.from({length: 18}, (_, i) => (
            <path
              key={i}
              d={`M ${((rnd(i + 7) * W + local * 1.6) % (W + 200)) - 100} ${490 + i * 33} q 40 -7 80 0`}
              fill="none"
            />
          ))}
        </g>

        <Seaplane x={planeX} y={planeY} s={0.96} prop={local * 46} tilt={2} />
        <g opacity={0.35}>
          <Cloud x={planeX - 250} y={planeY + 30} s={0.55} o={0.4} />
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="MALDIVES" text="印度洋上，一串散落的环礁" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 2：机舱

const Scene2: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const buzz = Math.sin(local * 2.2) * 1.8;
  const sway = Math.sin(local * 0.42) * 0.55;

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#cabinWall)" />
        {/* 舱顶弧面与行李架 */}
        <path d="M 0 0 L 1920 0 L 1920 150 C 1500 118 420 118 0 150 Z" fill="#e2d7c6" />
        <path d="M 0 0 L 1920 0 L 1920 150 C 1500 118 420 118 0 150 Z" fill="#ffffff" opacity={0.25} />
        <rect x={0} y={196} width={W} height={44} fill="#cdbfab" opacity={0.8} />
        <rect x={0} y={196} width={W} height={6} fill="#fff8ec" opacity={0.55} />
        <g opacity={0.35}>
          {Array.from({length: 9}, (_, i) => (
            <rect key={i} x={i * 240 - 4} y={250} width={6} height={430} fill="#c4b6a2" />
          ))}
          {[0, 1].map((i) => (
            <rect key={`r${i}`} x={0} y={300 + i * 190} width={W} height={3} fill="#cabba6" opacity={0.4} />
          ))}
        </g>

        <g transform={`translate(0 ${buzz}) rotate(${sway} ${W / 2} ${H / 2})`}>
          {/* 舷窗 */}
          <g>
            <circle cx={430} cy={352} r={258} fill="#c9bcaa" />
            <circle cx={430} cy={352} r={240} fill="#8fb7c4" />
            <clipPath id="portholeClip">
              <circle cx={430} cy={352} r={234} />
            </clipPath>
            <g clipPath="url(#portholeClip)">
              <rect x={180} y={112} width={520} height={240} fill="url(#skyDay)" />
              <rect x={180} y={352} width={520} height={260} fill="url(#seaDeep)" />
              <g stroke="#ffffff" opacity={0.32} strokeWidth={3} fill="none">
                {Array.from({length: 9}, (_, i) => (
                  <path key={i} d={`M ${160 + ((i * 96 + local * 5) % 560)} ${380 + i * 24} q 28 -6 56 0`} />
                ))}
              </g>
              <path d="M 210 392 L 560 360 L 560 382 L 210 416 Z" fill="#f2f7fb" opacity={0.72} />
              <path d="M 210 392 L 560 360" stroke="#ffffff" strokeWidth={6} opacity={0.7} />
              <ellipse cx={620} cy={430} rx={90} ry={34} fill="#ffffff" opacity={0.2} />
              <Cloud x={300} y={210} s={0.5} o={0.45} />
            </g>
            <circle cx={430} cy={352} r={258} fill="none" stroke="#f4ecdf" strokeWidth={18} />
            <circle cx={430} cy={352} r={234} fill="none" stroke="#b9a894" strokeWidth={5} />
            <circle cx={262} cy={352} r={9} fill="#ad9c88" />
            <circle cx={430} cy={352} r={240} fill="none" stroke="#ffffff" strokeWidth={3} opacity={0.5} />
          </g>

          {/* 座椅（椅背） */}
          {[700, 1180].map((sx) => (
            <g key={sx}>
              <rect x={sx - 165} y={744} width={330} height={340} rx={44} fill="#37636f" />
              <rect x={sx - 138} y={780} width={276} height={310} rx={34} fill="#4c8493" />
              <rect x={sx - 120} y={800} width={240} height={120} rx={30} fill="#3f7482" opacity={0.7} />
            </g>
          ))}

          {/* 人物：坐姿，靠背在身后 */}
          <Chibi
            variant="female"
            x={700}
            y={1104}
            s={1.3}
            mood="excited"
            pose="sit"
            tilt={-7}
            armL={[-96, -178]}
            armR={[64, -132]}
            bob={buzz * 0.4}
          />
          <Chibi
            variant="male"
            x={1180}
            y={1104}
            s={1.3}
            mood="happy"
            pose="sit"
            flip
            tilt={5}
            armL={[-58, -146]}
            armR={[70, -128]}
            bob={buzz * 0.4}
          />

          {/* 座垫前景：压住人物下半身，形成“坐着”的读法 */}
          {[700, 1180].map((sx) => (
            <g key={`c${sx}`}>
              <rect x={sx - 178} y={986} width={356} height={110} rx={26} fill="#325a66" />
              <rect x={sx - 178} y={986} width={356} height={12} rx={6} fill="#6fa3af" opacity={0.7} />
              <rect x={sx - 196} y={952} width={24} height={80} rx={12} fill="#2a4d58" />
              <rect x={sx + 172} y={952} width={24} height={80} rx={12} fill="#2a4d58" />
            </g>
          ))}

          {/* 窗外反射的暖光 */}
          <ellipse cx={430} cy={620} rx={280} ry={90} fill="#ffe9c9" opacity={0.14} filter="url(#soft40)" />
          <g opacity={0.9}>
            {[
              {x: 560, y: 250, r: 9},
              {x: 330, y: 200, r: 6},
              {x: 480, y: 170, r: 5},
            ].map((st, i) => (
              <Star key={i} x={st.x} y={st.y + Math.sin(local * 0.12 + i) * 5} r={st.r} o={0.5 + 0.5 * Math.sin(local * 0.16 + i)} fill="#fffdf2" />
            ))}
          </g>
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="SEAPLANE" text="水飞，载着我们飞向密度帕茹" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 3：降落

const Scene3: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const shake = Math.sin(local * 2.7) * 3.4;
  const settle = inv(local, [0, 34], [1, 0], easeInOut);
  const sprayP = inv(local, [16, 46], [0, 1], EASE);
  const planeX = 1120;
  const planeY = 512;
  const s = 1.14;
  const waterY = planeY + 94 * s;

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#skyGolden)" />
        <circle cx={390} cy={372} r={360} fill="url(#sunGlow)" opacity={0.9} />
        <circle cx={390} cy={372} r={52} fill="#fff9e9" opacity={0.96} />
        <Cloud x={1500} y={210} s={1.15} o={0.45} />
        <Cloud x={1000} y={160} s={0.78} o={0.36} />
        <Cloud x={620} y={230} s={0.5} o={0.3} />

        <rect x={0} y={430} width={W} height={H - 430} fill="url(#seaDeep)" />
        <rect x={0} y={430} width={W} height={16} fill="#ffe9c4" opacity={0.55} />
        <rect x={0} y={446} width={W} height={10} fill="#ffffff" opacity={0.14} />
        <g stroke="#ffeccb" opacity={0.2} strokeWidth={2}>
          {Array.from({length: 24}, (_, i) => (
            <path
              key={i}
              d={`M ${((i * 130 + local * 4) % 2100) - 100} ${470 + i * 26} q 70 -8 140 0`}
              fill="none"
            />
          ))}
        </g>
        {/* 阳光在水面的倒影 */}
        <g opacity={0.4}>
          {Array.from({length: 16}, (_, i) => (
            <ellipse key={i} cx={390 + Math.sin(local * 0.06 + i) * 14} cy={450 + i * 17} rx={70 - i * 2.4} ry={3.4} fill="#ffe4b5" opacity={0.6 - i * 0.03} />
          ))}
        </g>

        <g transform={`translate(${shake} ${-settle * 26})`}>
          {/* 尾迹：从机尾一直拖到画面左侧 */}
          <g>
            <path d={`M 120 ${waterY - 8} C 380 ${waterY - 30} 720 ${waterY - 26} 940 ${waterY - 6} L 940 ${waterY + 8} C 700 ${waterY + 20} 360 ${waterY + 16} 120 ${waterY + 14} Z`} fill="#ffffff" opacity={0.26} />
            <path d={`M 40 ${waterY + 34} C 340 ${waterY + 12} 700 ${waterY + 10} 952 ${waterY + 26} L 952 ${waterY + 40} C 680 ${waterY + 46} 300 ${waterY + 44} 40 ${waterY + 50} Z`} fill="#ffffff" opacity={0.16} />
            <g stroke="#ffffff" opacity={0.5} strokeWidth={3} strokeLinecap="round">
              <path d={`M 180 ${waterY - 22} q 220 -12 460 4`} fill="none" />
              <path d={`M 300 ${waterY + 26} q 260 -8 520 6`} fill="none" />
            </g>
          </g>

          {/* 水面下的机身倒影 */}
          <g opacity={0.18} filter="url(#soft6)">
            <Seaplane x={planeX} y={planeY + 74} s={s * 0.98} prop={0} tilt={-3} riders={false} />
          </g>

          <Seaplane x={planeX} y={planeY} s={s} prop={local * 62} tilt={-3.5 + settle * 1.5} riders />

          {/* 浮筒接触水面的水花 */}
          <g opacity={sprayP}>
            <g fill="#ffffff">
              <path d={`M 906 ${waterY - 6} C 850 ${waterY - 74} 770 ${waterY - 96} 700 ${waterY - 62} C 760 ${waterY - 56} 830 ${waterY - 30} 880 ${waterY + 4} Z`} opacity={0.92} />
              <path d={`M 950 ${waterY} C 918 ${waterY - 70} 872 ${waterY - 106} 812 ${waterY - 104} C 868 ${waterY - 74} 900 ${waterY - 38} 918 ${waterY + 6} Z`} opacity={0.78} />
              <path d={`M 1156 ${waterY - 4} C 1182 ${waterY - 78} 1226 ${waterY - 104} 1290 ${waterY - 88} C 1232 ${waterY - 66} 1200 ${waterY - 34} 1188 ${waterY + 6} Z`} opacity={0.86} />
            </g>
            {Array.from({length: 34}, (_, i) => {
              const side = i % 2 === 0 ? 0 : 1;
              const t = Math.max(0, sprayP * 1.25 - rnd(i + 3) * 0.55);
              const baseX = side === 0 ? 860 : 1170;
              return (
                <circle
                  key={i}
                  cx={baseX + (rnd(i) - 0.5) * 260 - t * 90}
                  cy={waterY - 10 - t * (110 + rnd(i + 9) * 220)}
                  r={2.2 + rnd(i + 15) * 6}
                  fill="#ffffff"
                  opacity={0.9 - t * 0.4}
                />
              );
            })}
            <ellipse cx={1010} cy={waterY + 6} rx={300} ry={26} fill="#ffffff" opacity={0.3} filter="url(#soft16)" />
            <ellipse cx={906} cy={waterY + 2} rx={90} ry={16} fill="#ffffff" opacity={0.55} filter="url(#soft6)" />
            <ellipse cx={1160} cy={waterY + 2} rx={80} ry={14} fill="#ffffff" opacity={0.5} filter="url(#soft6)" />
          </g>
        </g>

        <path d="M 0 1002 C 320 936 640 1000 960 982 C 1280 964 1600 1000 1920 962 L 1920 1080 L 0 1080 Z" fill="#0b7d94" opacity={0.45} />
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="LANDING" text="贴着海面，缓缓滑落" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 4：抵达栈桥

const Scene4: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const walk = inv(local, [8, 88], [0, 1], easeInOut);
  // 栈道透视：消失点与近端边缘
  const vpX = 960;
  const vpY = 590;
  const edge = (y: number) => {
    const t = (y - vpY) / (1080 - vpY);
    return [vpX - 590 * t, vpX + 600 * t] as const;
  };

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#skyGolden)" />
        <circle cx={1560} cy={250} r={380} fill="url(#sunGlow)" opacity={0.9} />
        <circle cx={1560} cy={250} r={48} fill="#fff9ea" opacity={0.95} />
        <Cloud x={400} y={180} s={1.05} o={0.5} />
        <Cloud x={1060} y={130} s={0.72} o={0.4} />

        <rect x={0} y={430} width={W} height={H - 430} fill="url(#seaDeep)" />
        <rect x={0} y={430} width={W} height={14} fill="#ffe9c4" opacity={0.5} />

        {/* 远岛 */}
        <path d="M 0 560 C 240 536 480 552 720 542 C 1000 530 1320 556 1920 536 L 1920 590 C 1500 606 1180 584 940 592 C 640 602 320 590 0 606 Z" fill="#f3e3c0" />
        <path d="M 0 560 C 240 536 480 552 720 542 C 1000 530 1320 556 1920 536" fill="none" stroke="#ffffff" strokeWidth={5} opacity={0.6} />
        <path d="M 0 606 C 320 590 640 602 940 592 C 1180 584 1500 606 1920 590 L 1920 640 L 0 640 Z" fill="#1a8fa4" opacity={0.35} />
        <g opacity={0.9}>
          <Palm x={210} y={560} s={0.42} sway={Math.sin(local * 0.04) * 1.4} />
          <Palm x={360} y={562} s={0.3} sway={Math.sin(local * 0.05 + 1) * 1.6} />
          <Palm x={1520} y={548} s={0.34} sway={Math.sin(local * 0.045 + 2) * 1.5} />
          <Palm x={1680} y={552} s={0.42} sway={Math.sin(local * 0.05 + 3) * 1.3} />
        </g>
        <g opacity={0.75}>
          <Villa x={1250} y={566} s={0.28} />
          <Villa x={1810} y={552} s={0.24} />
        </g>

        {/* 停泊的水上飞机 */}
        <g>
          <ellipse cx={330} cy={706} rx={150} ry={16} fill="#ffffff" opacity={0.28} filter="url(#soft6)" />
          <Seaplane x={330} y={640} s={0.56} prop={0} tilt={-1.5} riders={false} />
          <g opacity={0.2} filter="url(#soft6)">
            <Seaplane x={330} y={700} s={0.5} prop={0} tilt={-1.5} riders={false} />
          </g>
        </g>

        {/* 木栈道 */}
        <g>
          <path d={`M ${edge(590)[0]} ${590} L ${edge(590)[1]} 590 L 1540 1080 L 380 1080 Z`} fill="#a8733f" />
          <path d={`M ${vpX - 390} 1080 L ${vpX + 400} 1080 L ${vpX + 214} 700 L ${vpX - 200} 700 Z`} fill="#ffd9a0" opacity={0.12} />
          {Array.from({length: 22}, (_, i) => {
            const t = i / 22;
            const y = 592 + Math.pow(t, 1.65) * 480;
            const [xl, xr] = edge(y);
            return <rect key={i} x={xl} y={y} width={xr - xl} height={Math.max(2, 3.4 * t)} fill="#7c5230" opacity={0.6} />;
          })}
          <g stroke="#6f4828" strokeWidth={5} opacity={0.5}>
            {Array.from({length: 9}, (_, i) => {
              const t = i / 9;
              const y1 = 600 + Math.pow(t, 1.6) * 460;
              const y2 = 600 + Math.pow((i + 1) / 9, 1.6) * 460;
              return <path key={i} d={`M ${vpX - 560 * t} ${y1} L ${vpX + 570 * t} ${y2}`} />;
            })}
          </g>

          {/* 栏杆 */}
          <g>
            {[0.18, 0.34, 0.5, 0.66, 0.82, 0.97].map((t, i) => {
              const y = 590 + Math.pow(t, 1.55) * 470;
              const [xl, xr] = edge(y);
              const h = 26 + t * 54;
              return (
                <g key={i}>
                  <rect x={xl - 7} y={y - h} width={12 + t * 4} height={h} rx={4} fill="#7a5334" />
                  <rect x={xr - 3} y={y - h} width={12 + t * 4} height={h} rx={4} fill="#7a5334" />
                </g>
              );
            })}
            <g stroke="#c9a877" strokeWidth={3} opacity={0.8} fill="none">
              <path d={`M ${edge(590 + Math.pow(0.18, 1.55) * 470)[0]} ${590 + Math.pow(0.18, 1.55) * 470 - 33} C 800 700 900 760 960 780`} />
              <path d={`M ${edge(590 + Math.pow(0.18, 1.55) * 470)[1]} ${590 + Math.pow(0.18, 1.55) * 470 - 33} C 1120 700 1020 760 960 780`} />
            </g>
          </g>
        </g>

        <Chibi variant="female" x={860 + walk * 26} y={958} s={1.22} mood="happy" tilt={-3} bob={Math.sin(local * 0.3) * 3} shadow armR={[92, -250]} showFlower />
        <Chibi variant="male" x={1104 + walk * 26} y={958} s={1.24} mood="happy" flip tilt={2} bob={Math.sin(local * 0.3 + 1.4) * 3} shadow armR={[118, -150]} />

        {/* 行李 */}
        <g transform={`translate(${1326 + walk * 30} 948)`}>
          <ellipse cx={0} cy={6} rx={58} ry={10} fill="rgba(20,30,40,0.2)" />
          <rect x={-46} y={-70} width={92} height={72} rx={12} fill="#e9b04c" />
          <rect x={-46} y={-52} width={92} height={9} fill="#c98f2f" />
          <path d="M -16 -88 q 16 -14 32 0" stroke="#8a6a2f" strokeWidth={7} fill="none" />
          <circle cx={-24} cy={4} r={9} fill="#3a3a44" />
          <circle cx={24} cy={4} r={9} fill="#3a3a44" />
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="ARRIVAL" text="踏上木栈道，海风正好" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 5：晕眩

const Scene5: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const wob = Math.sin(local * 0.24) * 13;
  const roll = Math.sin(local * 0.19) * 2.2;
  const surge = Math.sin(local * 0.16) * 7;

  return (
    <AbsoluteFill>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width={W}
        height={H}
        style={{position: 'absolute', left: 0, top: 0, transform: `rotate(${roll * 0.4}deg) scale(1.05)`}}
      >
        <Defs />
        <rect width={W} height={H} fill="url(#skyGolden)" />
        <rect x={0} y={440} width={W} height={H - 440} fill="url(#seaDeep)" />
        <rect x={0} y={440} width={W} height={10} fill="#ffe9c4" opacity={0.5} />

        {/* 虚化的栈道与海面，保留地点感 */}
        <g filter="url(#soft16)" opacity={0.8}>
          <path d="M 760 470 L 1160 470 L 1700 1080 L 220 1080 Z" fill="#a8733f" opacity={0.85} />
          <g stroke="#7c5230" strokeWidth={6} opacity={0.55}>
            {Array.from({length: 12}, (_, i) => (
              <path key={i} d={`M ${760 - i * 44} ${478 + i * 48} L ${1160 + i * 46} ${478 + i * 48}`} />
            ))}
          </g>
          <Palm x={140} y={700} s={1.5} sway={Math.sin(local * 0.03) * 2} />
          <Palm x={1800} y={740} s={1.6} sway={Math.sin(local * 0.035 + 1) * 2} />
        </g>

        <g opacity={0.5} filter="url(#soft40)">
          <ellipse cx={330} cy={470} rx={280} ry={140} fill="#ffe6b8" />
          <ellipse cx={1620} cy={520} rx={300} ry={150} fill="#bfeef5" />
        </g>
        <g opacity={0.18} stroke="#ffffff" strokeWidth={7}>
          {Array.from({length: 5}, (_, i) => (
            <path key={i} d={`M -100 ${510 + i * 70 + Math.sin(local * 0.2 + i) * 14} q 480 -26 960 0 t 1060 0`} fill="none" />
          ))}
        </g>

        <g transform={`translate(0 ${surge}) rotate(${roll} 960 560)`}>
          {/* 轻微的双影，只用低透明度 + 模糊，避免出现“多一只耳朵” */}
          <g opacity={0.1} filter="url(#soft6)">
            <Chibi variant="female" x={960 - wob * 1.7} y={1122} s={1.72} mood="dizzy" pale tilt={-2} showFlower={false} />
            <Chibi variant="female" x={960 + wob * 1.7} y={1122} s={1.72} mood="dizzy" pale tilt={2} showFlower={false} />
          </g>
          <Chibi
            variant="female"
            x={960 + wob * 0.35}
            y={1122}
            s={1.72}
            mood="dizzy"
            pale
            tilt={Math.sin(local * 0.2) * 3.5}
            armL={[-94, -150]}
            armR={[112, -286]}
            showFlower
          />

          {/* 环绕的晕眩星星 */}
          <g>
            {Array.from({length: 8}, (_, i) => {
              const a = local * 0.05 + (i / 8) * Math.PI * 2;
              const rx = 360;
              const ry = 96;
              const x = 960 + wob * 0.35 + Math.cos(a) * rx;
              const y = 430 + Math.sin(a) * ry + 20;
              const front = Math.sin(a) > -0.2;
              return <Star key={i} x={x} y={y} r={front ? 16 : 9} o={front ? 0.95 : 0.4} fill="#fff3b0" />;
            })}
          </g>

          {/* 汗珠 */}
          <g fill="#bdefff" opacity={0.9}>
            <path d={blobPath(1122, 640, 14, 18, 2.2, 0.15)} />
            <path d={blobPath(1150, 700, 9, 12, 4.1, 0.15)} />
          </g>
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="WOBBLE" text="可脚下的木板，好像还在随浪起伏" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 6：搀扶

const Scene6: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const push = inv(local, [0, dur], [1.0, 1.06]);

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#skyGolden)" />
        <circle cx={260} cy={330} r={420} fill="url(#sunGlow)" opacity={0.95} />
        <g transform={`translate(${(1 - push) * 60} ${(1 - push) * 30}) scale(${push})`}>
          <rect x={0} y={430} width={W} height={H - 430} fill="url(#seaDeep)" />
          <rect x={0} y={430} width={W} height={10} fill="#ffe9c4" opacity={0.55} />

          {/* 虚化的栈道与椰林，交代环境 */}
          <g filter="url(#soft16)" opacity={0.95}>
            <path d="M 820 470 L 1100 470 L 1760 1080 L 160 1080 Z" fill="#a8733f" />
            <g stroke="#7c5230" strokeWidth={7} opacity={0.5}>
              {Array.from({length: 10}, (_, i) => (
                <path key={i} d={`M ${820 - i * 66} ${480 + i * 62} L ${1100 + i * 68} ${480 + i * 62}`} />
              ))}
            </g>
            <Palm x={120} y={700} s={1.7} sway={Math.sin(local * 0.03) * 1.6} />
            <Palm x={1830} y={720} s={1.8} sway={Math.sin(local * 0.035 + 1) * 1.6} />
          </g>
          <g opacity={0.45} filter="url(#soft40)">
            <ellipse cx={1500} cy={520} rx={320} ry={150} fill="#ffe6b8" />
            <ellipse cx={400} cy={620} rx={300} ry={140} fill="#8fe6da" />
          </g>

          {/* 男孩先画，手臂环到女孩肩后 */}
          <Chibi
            variant="male"
            x={1160}
            y={1015}
            s={1.35}
            mood="worried"
            tilt={-3}
            armL={[-267, -204]}
            armR={[150, -120]}
            shadow
          />

          {/* 女孩靠向他 */}
          <Chibi
            variant="female"
            x={830}
            y={1010}
            s={1.35}
            mood="weak"
            pale
            tilt={8}
            armL={[-104, -196]}
            armR={[78, -250]}
            shadow
          />

          {/* 环过去的手：单独画在女孩身上 */}
          <g>
            <circle cx={800} cy={742} r={17} fill={SKIN_B} />
            <circle cx={800} cy={742} r={22} fill={SHIRT} opacity={0.9} />
            <circle cx={800} cy={742} r={16} fill={SKIN_B} />
          </g>

          {/* 椰子 */}
          <g transform="translate(1382 846)">
            <circle r={50} fill="#7d522f" />
            <circle r={50} fill="#9a6739" opacity={0.5} />
            <ellipse cx={0} cy={-42} rx={40} ry={13} fill="#f6ecd9" />
            <ellipse cx={0} cy={-42} rx={28} ry={9} fill="#dcc7a5" />
            <path d="M 2 -44 C 8 -78 22 -96 40 -104" stroke="#f3e3c2" strokeWidth={8} fill="none" strokeLinecap="round" />
            <path d="M 44 -106 q 26 -6 30 20" stroke="#ff7f9c" strokeWidth={8} fill="none" strokeLinecap="round" />
          </g>

          {/* 小星星：她还在缓 */}
          <g opacity={0.8}>
            {Array.from({length: 4}, (_, i) => {
              const a = local * 0.06 + (i / 4) * Math.PI * 2;
              return (
                <Star
                  key={i}
                  x={886 + Math.cos(a) * 190}
                  y={470 + Math.sin(a) * 42}
                  r={Math.sin(a) > 0 ? 9 : 5}
                  o={Math.sin(a) > 0 ? 0.8 : 0.3}
                  fill="#fff3b0"
                />
              );
            })}
          </g>
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="TAKE CARE" text="“慢一点，我扶着你”" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 7：夕阳栈桥

const Scene7: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const t = inv(local, [0, dur], [0, 1], easeInOut);
  const sunY = 610;
  const walkStyle = 0.62;

  return (
    <AbsoluteFill>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#skySunset)" />
        <circle cx={1400} cy={sunY} r={520} fill="url(#sunGlow)" opacity={0.95} />
        <circle cx={1400} cy={sunY} r={96} fill="#fff3cf" />
        <circle cx={1400} cy={sunY} r={92} fill="#fffdf0" opacity={0.6} filter="url(#soft6)" />

        <Cloud x={360} y={280} s={1.4} o={0.32} />
        <Cloud x={980} y={200} s={0.9} o={0.26} />

        {/* 落日海面 */}
        <rect x={0} y={sunY} width={W} height={H - sunY} fill="url(#seaDusk)" />
        <g>
          {Array.from({length: 26}, (_, i) => {
            const y = sunY + 16 + i * 17;
            const w = 90 + i * 16;
            return (
              <ellipse
                key={i}
                cx={1400 + Math.sin(local * 0.05 + i * 0.6) * 8}
                cy={y}
                rx={w * (0.45 + 0.5 * Math.sin((local * 0.08 + i) % Math.PI))}
                ry={4}
                fill="#ffe3ae"
                opacity={0.32 - i * 0.008}
              />
            );
          })}
        </g>

        {/* 远处岛屿 */}
        <path d="M 0 604 C 260 586 520 600 760 596 C 1020 592 1280 606 1500 600 L 1920 606 L 1920 640 L 0 640 Z" fill="#5b3350" opacity={0.85} />

        {/* 水上屋 */}
        <Villa x={1500} y={620} s={0.5} dark />
        <Villa x={1690} y={614} s={0.36} dark />

        {/* 栈桥 */}
        <g>
          <path d="M 1000 616 L 1450 618 L 1560 1080 L 780 1080 Z" fill="#4b2b40" />
          <path d="M 1000 616 L 1450 618 L 1560 1080 L 780 1080 Z" fill="#ff9e6e" opacity={0.18} />
          <g stroke="#3a2033" strokeWidth={3} opacity={0.7}>
            {Array.from({length: 18}, (_, i) => {
              const p = i / 18;
              const y = 618 + Math.pow(p, 1.7) * 462;
              const xl = 1000 - 220 * Math.pow(p, 1.5);
              const xr = 1450 + 110 * Math.pow(p, 1.5);
              return <rect key={i} x={xl} y={y} width={xr - xl} height={4} />;
            })}
          </g>
          <g fill="#3a2033">
            {[0.16, 0.34, 0.52, 0.7, 0.88].map((p, i) => {
              const y = 618 + Math.pow(p, 1.7) * 462;
              const xl = 1000 - 220 * Math.pow(p, 1.5);
              const xr = 1450 + 110 * Math.pow(p, 1.5);
              return (
                <g key={i}>
                  <rect x={xl - 8} y={y} width={12} height={Math.max(6, 26 * p)} opacity={0.9} />
                  <rect x={xr - 4} y={y} width={12} height={Math.max(6, 26 * p)} opacity={0.9} />
                </g>
              );
            })}
          </g>
        </g>

        {/* 牵手走远的两个人 */}
        <g transform={`translate(${t * 40} ${-t * 26})`}>
          <Chibi
            variant="male"
            x={920}
            y={866}
            s={walkStyle}
            mood="calm"
            pose="walk"
            backView
            silhouette="#2b1a26"
            bob={Math.abs(Math.sin(local * 0.16)) * -5}
            armL={[-64, -96]}
            armR={[129, -112]}
          />
          <Chibi
            variant="female"
            x={1078}
            y={866}
            s={walkStyle}
            mood="calm"
            pose="walk"
            backView
            silhouette="#2b1a26"
            bob={Math.abs(Math.sin(local * 0.16 + 2.4)) * -5}
            armL={[-129, -112]}
            armR={[64, -96]}
          />
        </g>

        <g opacity={0.6}>
          <Bird x={420} y={250} s={1.6} flap={Math.sin(local * 0.2)} />
          <Bird x={520} y={210} s={1.2} flap={Math.sin(local * 0.2 + 1)} />
          <Bird x={1600} y={300} s={1.2} flap={Math.sin(local * 0.22 + 2)} />
        </g>
      </svg>
      <Scrim />
      <Caption local={local} dur={dur} kicker="SUNSET" text="沿着栈桥，慢慢走回房间" />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 分镜 8：房间

const Scene8: React.FC<{local: number; dur: number}> = ({local, dur}) => {
  const titleP = inv(local, [82, 120], [0, 1], EASE);
  const dim = inv(local, [74, 112], [0, 0.55]);
  const breathe = Math.sin(local * 0.07) * 2;

  return (
    <AbsoluteFill style={{backgroundColor: '#2c2a3f'}}>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} style={{position: 'absolute', left: 0, top: 0}}>
        <Defs />
        <rect width={W} height={H} fill="url(#roomWall)" />

        {/* 木质墙板 */}
        <g opacity={0.5}>
          {Array.from({length: 17}, (_, i) => (
            <rect key={i} x={i * 118} y={0} width={58} height={700} fill="#241f2e" opacity={0.35} />
          ))}
          <rect x={0} y={0} width={W} height={120} fill="#1c1826" opacity={0.5} />
        </g>

        {/* 窗 */}
        <g>
          <rect x={1288} y={120} width={548} height={470} rx={12} fill="#1f1c2b" />
          <rect x={1306} y={138} width={512} height={434} rx={6} fill="url(#skySunset)" />
          <clipPath id="roomWinClip">
            <rect x={1306} y={138} width={512} height={434} rx={6} />
          </clipPath>
          <g clipPath="url(#roomWinClip)">
            <circle cx={1600} cy={430} r={330} fill="url(#sunGlow)" opacity={0.9} />
            <circle cx={1600} cy={430} r={72} fill="#fff5d4" />
            <rect x={1306} y={452} width={512} height={120} fill="url(#seaDusk)" opacity={0.92} />
            {Array.from({length: 14}, (_, i) => (
              <ellipse key={i} cx={1600 + Math.sin(local * 0.05 + i) * 6} cy={470 + i * 9} rx={66 + i * 12} ry={3} fill="#ffe3ae" opacity={0.34} />
            ))}
            <path d="M 1306 486 C 1420 480 1540 492 1660 486" stroke="#4a2f47" strokeWidth={9} fill="none" opacity={0.55} />
            <path d="M 1306 500 C 1450 496 1560 506 1680 500" stroke="#4a2f47" strokeWidth={6} fill="none" opacity={0.35} />
            <Palm x={1500} y={500} s={0.24} sway={0} dark />
            <ellipse cx={1450} cy={220} rx={140} ry={30} fill="#ffd6a8" opacity={0.4} filter="url(#soft16)" />
          </g>
          <rect x={1556} y={138} width={10} height={434} fill="#1f1c2b" opacity={0.9} />
          <rect x={1288} y={120} width={548} height={470} rx={12} fill="none" stroke="#2b2437" strokeWidth={20} />
        </g>

        {/* 窗帘 */}
        <g>
          <path d="M 1240 96 C 1310 240 1272 430 1300 620 L 1214 620 C 1196 420 1200 224 1204 96 Z" fill="#c9a994" opacity={0.92} />
          <g stroke="#a9866f" strokeWidth={4} opacity={0.5} fill="none">
            <path d="M 1230 130 C 1276 280 1250 440 1264 610" />
            <path d="M 1252 120 C 1296 280 1270 440 1282 610" />
          </g>
          <path d="M 1762 96 C 1830 240 1800 430 1828 620 L 1748 620 C 1730 420 1734 224 1738 96 Z" fill="#c9a994" opacity={0.92} />
          <g stroke="#a9866f" strokeWidth={4} opacity={0.5} fill="none">
            <path d="M 1770 130 C 1812 280 1790 440 1800 610" />
            <path d="M 1792 120 C 1834 280 1812 440 1822 610" />
          </g>
        </g>

        {/* 床 */}
        <g>
          <rect x={286} y={520} width={110} height={250} rx={18} fill="#4a3549" />
          <rect x={300} y={538} width={82} height={232} rx={14} fill="#5c4258" />
          <rect x={330} y={744} width={860} height={90} rx={18} fill="url(#duvet)" />
          <rect x={330} y={826} width={860} height={54} fill="#8a7484" opacity={0.75} />
          <rect x={322} y={872} width={876} height={26} rx={10} fill="#4a3549" />
          <rect x={352} y={892} width={22} height={70} rx={8} fill="#35263a" />
          <rect x={1136} y={892} width={22} height={70} rx={8} fill="#35263a" />
        </g>

        {/* 枕头 + 女孩 */}
        <g>
          <ellipse cx={520} cy={742} rx={196} ry={64} fill="#fffdf8" />
          <ellipse cx={520} cy={752} rx={176} ry={44} fill="#efe2d1" opacity={0.55} />
          <g transform={`translate(500 ${706 + breathe * 0.4})`}>
            <ellipse cx={-34} cy={-14} rx={132} ry={104} fill={HAIR_G} />
            <circle cx={8} cy={0} r={94} fill={SKIN_G} />
            <path
              d="M -86 -8 C -90 -88 -42 -126 8 -126 C 60 -126 102 -86 96 -8 C 82 -38 56 -44 30 -62 C 8 -42 -14 -48 -34 -64 C -58 -42 -76 -44 -86 -8 Z"
              fill={HAIR_G}
            />
            <g stroke="#3b2a35" strokeWidth={5.5} fill="none" strokeLinecap="round">
              <path d="M -46 -4 q 15 -16 30 0" />
              <path d="M 24 -4 q 15 -16 30 0" />
            </g>
            <path d="M -14 30 q 16 11 32 0" stroke="#3b2a35" strokeWidth={5} fill="none" strokeLinecap="round" />
            <ellipse cx={-58} cy={26} rx={17} ry={9} fill="#ff8ea6" opacity={0.42} />
            <ellipse cx={66} cy={26} rx={17} ry={9} fill="#ff8ea6" opacity={0.42} />
            <ellipse cx={-30} cy={26} rx={10} ry={4} fill="#ff9a72" opacity={0.25} />
          </g>
          {/* 被子 */}
          <path d="M 340 760 C 520 736 760 776 940 754 C 1030 744 1090 754 1150 746 L 1150 830 C 900 848 600 842 340 830 Z" fill="#fffaf1" />
          <path d="M 340 760 C 520 736 760 776 940 754 C 1030 744 1090 754 1150 746" stroke="#dccbb6" strokeWidth={5} fill="none" opacity={0.8} />
          <path d="M 470 770 C 560 730 700 736 800 764" stroke="#e6d6c2" strokeWidth={6} fill="none" opacity={0.6} />
        </g>

        {/* 男孩坐在床沿 */}
        <g>
          <g>
            <rect x={1092} y={790} width={36} height={210} rx={16} fill={SKIN_B} />
            <rect x={1132} y={790} width={36} height={206} rx={16} fill={SKIN_B} />
            <ellipse cx={1110} cy={998} rx={26} ry={13} fill="#f0e6d6" />
            <ellipse cx={1150} cy={994} rx={26} ry={13} fill="#f0e6d6" />
          </g>
          <Chibi variant="male" x={1120} y={820} s={1.05} mood="calm" pose="sit" flip tilt={2} armL={[-62, -150]} armR={[92, -160]} />
          <g transform="translate(1042 650)">
            <rect x={-19} y={-30} width={38} height={58} rx={8} fill="#dff2f6" opacity={0.9} />
            <rect x={-19} y={-20} width={38} height={26} rx={5} fill="#a9dae4" opacity={0.85} />
            <rect x={-19} y={-30} width={38} height={58} rx={8} fill="none" stroke="#ffffff" strokeWidth={3} />
          </g>
        </g>

        {/* 床头柜与灯 */}
        <g>
          <rect x={120} y={640} width={210} height={20} rx={8} fill="#4a3549" />
          <rect x={140} y={660} width={170} height={220} fill="#3d2c40" />
          <circle cx={244} cy={520} r={210} fill="url(#lampGlow)" opacity={0.85} />
          <rect x={238} y={560} width={12} height={82} fill="#2f2434" />
          <path d="M 186 560 L 302 560 L 272 486 L 216 486 Z" fill="#ffd9a2" opacity={0.96} />
          <ellipse cx={244} cy={560} rx={58} ry={10} fill="#ffe9c0" opacity={0.75} />
        </g>

        {/* 尘埃 */}
        <g opacity={0.55}>
          {Array.from({length: 30}, (_, i) => {
            const x = 140 + rnd(i + 3) * 1000;
            const y = 200 + (((rnd(i + 9) * 640 - local * (0.4 + rnd(i) * 0.8)) % 640) + 640) % 640;
            return <circle key={i} cx={x} cy={y} r={1.6 + rnd(i + 21) * 2.8} fill="#ffe9c6" opacity={0.3 + rnd(i + 40) * 0.45} />;
          })}
        </g>

        <rect width={W} height={H} fill="#ff9a55" opacity={0.05} style={{mixBlendMode: 'screen'}} />
      </svg>

      <AbsoluteFill style={{backgroundColor: '#0a0812', opacity: dim}} />

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: 0,
          bottom: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: SANS,
          opacity: titleP,
          transform: `translateY(${(1 - titleP) * 24}px)`,
        }}
      >
        <div style={{fontSize: 22, letterSpacing: '0.7em', color: 'rgba(255,224,190,0.7)', marginBottom: 30}}>
          HONEYMOON · 2026
        </div>
        <div style={{fontSize: 76, letterSpacing: '0.3em', color: '#fff6e4', fontWeight: 500, textShadow: '0 14px 50px rgba(0,0,0,0.8)'}}>
          密度帕茹岛
        </div>
        <div style={{width: 300 * titleP, height: 1, margin: '30px 0 22px', background: 'rgba(255,235,205,0.55)'}} />
        <div style={{fontSize: 17, letterSpacing: '0.62em', color: 'rgba(255,238,214,0.66)'}}>MEEDHUPPARU · MALDIVES</div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- 时间轴

const SCENES = [
  {dur: 130, render: (l: number, d: number) => <Scene1 local={l} dur={d} />},
  {dur: 122, render: (l: number, d: number) => <Scene2 local={l} dur={d} />},
  {dur: 116, render: (l: number, d: number) => <Scene3 local={l} dur={d} />},
  {dur: 122, render: (l: number, d: number) => <Scene4 local={l} dur={d} />},
  {dur: 118, render: (l: number, d: number) => <Scene5 local={l} dur={d} />},
  {dur: 116, render: (l: number, d: number) => <Scene6 local={l} dur={d} />},
  {dur: 132, render: (l: number, d: number) => <Scene7 local={l} dur={d} />},
  {dur: 156, render: (l: number, d: number) => <Scene8 local={l} dur={d} />},
];

const OVERLAP = 26;
const STARTS: number[] = [];
SCENES.reduce((acc, s) => {
  STARTS.push(acc);
  return acc + s.dur - OVERLAP;
}, 0);

export const MALDIVES_DURATION =
  STARTS[STARTS.length - 1] + SCENES[SCENES.length - 1].dur;

const SceneLayer: React.FC<{index: number; local: number; dur: number}> = ({index, local, dur}) => {
  const frame = useCurrentFrame();
  const start = STARTS[index];
  const end = start + dur;
  const opacity = interpolate(frame, [start, start + OVERLAP, end - OVERLAP, end], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (opacity <= 0.002) return null;

  return <AbsoluteFill style={{opacity}}>{SCENES[index].render(local, dur)}</AbsoluteFill>;
};

const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{opacity: 0.1, mixBlendMode: 'overlay', pointerEvents: 'none'}}>
      <Solid width={width} height={height} color="#808080" effects={[noise({amount: 0.8, seed: frame})]} />
    </AbsoluteFill>
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      background:
        'radial-gradient(ellipse at 50% 44%, rgba(0,0,0,0) 42%, rgba(0,0,0,0.32) 78%, rgba(0,0,0,0.7) 100%)',
    }}
  />
);

export const MaldivesStory: React.FC = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();

  const fadeOut = inv(frame, [durationInFrames - 22, durationInFrames], [0, 1]);

  return (
    <AbsoluteFill style={{backgroundColor: '#06171f'}}>
      {SCENES.map((scene, i) => (
        <SceneLayer key={i} index={i} local={frame - STARTS[i]} dur={scene.dur} />
      ))}
      <FilmGrain />
      <Vignette />
      <AbsoluteFill style={{backgroundColor: '#000', opacity: fadeOut}} />
    </AbsoluteFill>
  );
};
