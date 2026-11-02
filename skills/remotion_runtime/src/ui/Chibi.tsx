import React from 'react';
import {useCurrentFrame} from 'remotion';

/**
 * 参数化 Q 版角色骨架（从一支已验证的成片里提取）。
 * 本地坐标系：脚底在 y=0，头顶约 y=-430，总高约 436；实际尺寸靠外层 scale 控制。
 * 只描述「一个人长什么样」，不含任何题材/场景/画风设定。
 */

export type Mood = 'happy' | 'excited' | 'dizzy' | 'worried' | 'weak' | 'calm' | 'sleep';
export type Pose = 'stand' | 'sit' | 'walk';

export const SKIN_G = '#ffd7bd';
export const SKIN_B = '#f3c49d';
export const HAIR_G = '#3a2a30';
export const HAIR_B = '#2a2430';
export const DRESS = '#ff7f9c';
export const DRESS_DARK = '#e26684';
export const SHIRT = '#2fb9b5';
export const SHORTS = '#2f3f55';

export const POSE_ARMS: Record<Pose, {L: [number, number]; R: [number, number]}> = {
  stand: {L: [-66, -92], R: [66, -92]},
  sit: {L: [-48, -134], R: [48, -134]},
  walk: {L: [-78, -88], R: [78, -88]},
};

export interface ChibiProps {
  variant: 'male' | 'female';
  x?: number;
  y?: number;
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
  /** 覆盖身体主色（默认粉裙/青衫），用于统一角色配色 */
  outfit?: string;
  outfitDark?: string;
  hairColor?: string;
}

const spiralPath = (cx: number, cy: number, R: number, turns = 2.1, steps = 44) => {
  let d = '';
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const a = t * Math.PI * 2 * turns;
    const r = R * (1 - t * 0.88);
    d += `${i === 0 ? 'M' : 'L'} ${(cx + Math.cos(a) * r).toFixed(1)} ${(cy + Math.sin(a) * r).toFixed(1)} `;
  }
  return d;
};

const Face: React.FC<{mood: Mood; frame: number; girl: boolean; silhouette?: string}> = ({
  mood,
  frame,
  girl,
  silhouette,
}) => {
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
        <path d="M -18 -278 q 6 -8 12 0 q 6 8 12 0" stroke={ink} strokeWidth={5} fill="none" strokeLinecap="round" />
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

export const Chibi: React.FC<ChibiProps> = ({
  variant,
  x = 0,
  y = 0,
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
  outfit,
  outfitDark,
  hairColor,
}) => {
  const frame = useCurrentFrame();
  const girl = variant === 'female';
  const c = (col: string) => silhouette ?? col;
  const skin = silhouette ?? (pale ? '#f7dcc4' : girl ? SKIN_G : SKIN_B);
  const hair = silhouette ?? hairColor ?? (girl ? HAIR_G : HAIR_B);
  const cloth = silhouette ?? outfit ?? (girl ? DRESS : SHIRT);
  const clothDark = silhouette ?? outfitDark ?? (girl ? DRESS_DARK : SHORTS);
  const defaultArms = POSE_ARMS[pose];
  const handL = armL ?? defaultArms.L;
  const handR = armR ?? defaultArms.R;
  const shoulderY = -192;
  const armW = girl ? 24 : 26;

  const arm = (sh: [number, number], hand: [number, number]) => (
    <g>
      <line x1={sh[0]} y1={sh[1]} x2={hand[0]} y2={hand[1]} stroke={skin} strokeWidth={armW} strokeLinecap="round" />
      <circle cx={hand[0]} cy={hand[1]} r={armW * 0.58} fill={skin} />
      <circle cx={sh[0]} cy={sh[1]} r={girl ? 18 : 19} fill={cloth} />
    </g>
  );

  return (
    <g transform={`translate(${x} ${y + bob}) scale(${flip ? -s : s} ${s}) rotate(${flip ? -tilt : tilt})`}>
      {shadow ? <ellipse cx={0} cy={6} rx={96} ry={16} fill="rgba(20,30,40,0.22)" /> : null}

      {girl ? <ellipse cx={0} cy={-296} rx={112} ry={126} fill={hair} /> : null}

      {pose !== 'sit' ? (
        <g>
          <rect x={-42} y={-92} width={32} height={84} rx={14} fill={skin} />
          <rect x={10} y={-92} width={32} height={84} rx={14} fill={skin} />
          <ellipse cx={-26} cy={-8} rx={26} ry={14} fill={c(girl ? '#fffaf2' : '#f0e6d6')} />
          <ellipse cx={26} cy={-8} rx={26} ry={14} fill={c(girl ? '#fffaf2' : '#f0e6d6')} />
        </g>
      ) : null}

      {girl ? (
        <g>
          <path
            d="M -58 -212 C -64 -168 -76 -122 -100 -72 L 100 -72 C 76 -122 64 -168 58 -212 C 28 -226 -28 -226 -58 -212 Z"
            fill={cloth}
          />
          <path
            d="M -100 -72 C -60 -64 60 -64 100 -72 L 104 -60 C 60 -52 -60 -52 -104 -60 Z"
            fill={clothDark}
            opacity={0.55}
          />
          <path d="M -20 -214 L 20 -214 L 18 -150 L -18 -150 Z" fill={c('#fff6ee')} opacity={0.28} />
        </g>
      ) : (
        <g>
          <rect x={-18} y={-104} width={36} height={34} rx={10} fill={clothDark} />
          <path
            d="M -60 -206 C -62 -168 -58 -130 -54 -104 L 54 -104 C 58 -130 62 -168 60 -206 C 30 -218 -30 -218 -60 -206 Z"
            fill={cloth}
          />
          <rect x={-58} y={-136} width={116} height={34} rx={16} fill={clothDark} />
          <path d="M -14 -206 L 14 -206 L 12 -110 L -12 -110 Z" fill="#ffffff" opacity={0.16} />
        </g>
      )}

      {arm([-54, shoulderY], handL)}
      {arm([54, shoulderY], handR)}

      <rect x={-14} y={-240} width={28} height={34} rx={8} fill={silhouette ?? (pale ? '#eec9ae' : skin)} />

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
          ) : null}
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

export default Chibi;
