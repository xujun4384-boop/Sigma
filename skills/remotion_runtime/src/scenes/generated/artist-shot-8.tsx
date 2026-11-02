import {Character} from './char-hero';
import {useE} from '../../engine/context';

export const BG = '#172554';
export const META = {8: {bg: '#172554'}};

const PixelStar = ({
  x, y, s = 1, color = '#FFD93D', opacity = 1,
}: {x: number; y: number; s?: number; color?: string; opacity?: number}) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
    <path
      d="M-14-60H14V-30H26V-16H60V8H38V24H26V40H40V58H16V46H-16V58H-40V40H-26V24H-38V8H-60V-16H-26V-30H-14Z"
      fill="#7A451B"
      transform="translate(0 8)"
    />
    <path
      d="M-14-60H14V-30H26V-16H60V8H38V24H26V40H40V58H16V46H-16V58H-40V40H-26V24H-38V8H-60V-16H-26V-30H-14Z"
      fill={color}
    />
    <rect x="-14" y="-38" width="12" height="18" fill="#FFF4A8" />
    <rect x="-42" y="-8" width="18" height="8" fill="#FFF4A8" />
  </g>
);

export const Shot8 = () => {
  const e = useE();
  const t = e.shotT;
  const clamp01 = e.clamp01;

  const jumping = t >= 0.95 && t < 1.5;
  const jump = jumping ? Math.sin(((t - 0.95) / 0.55) * Math.PI) * 68 : 0;
  const stomped = t >= 1.45;
  const press = e.easeOut(clamp01((t - 1.45) / 0.12));
  const grow = Math.max(0, e.back(clamp01((t - 1.52) / 0.9)));
  const impact = clamp01(1 - Math.abs(t - 1.48) / 0.22);
  const shake = impact * Math.sin(t * 145) * 9;
  const xp = t < 1.45
    ? 0.18
    : t < 5.35
      ? e.lerp(0.18, 0.88, e.easeOut(clamp01((t - 1.45) / 2.7)))
      : e.lerp(0.88, 1, e.easeOut(clamp01((t - 5.35) / 0.25)));
  const finalPop = Math.max(0, e.back(clamp01((t - 5.35) / 0.38)));
  const idleBob = Math.sin(t * Math.PI * 4) * 3;

  const planeU = clamp01(t / 0.9);
  const planeX = e.lerp(-130, 960, e.easeIO(planeU));
  const planeY = e.lerp(360, 260, planeU) - Math.sin(planeU * Math.PI) * 85;
  const planeOpacity = 1 - clamp01((t - 0.72) / 0.2);
  const morphStarOpacity = clamp01((t - 0.7) / 0.18) * (1 - clamp01((t - 1.48) / 0.1));
  const morphU = clamp01((t - 0.86) / 0.64);
  const morphX = t < 0.86 ? planeX : 960;
  const morphY = t < 0.86 ? planeY : e.lerp(260, 805, e.easeIn(morphU));
  const morphScale = t < 0.86
    ? e.lerp(0.15, 1.05, clamp01((t - 0.7) / 0.18))
    : e.lerp(1.05, 0.38, morphU);

  const nodes = [
    {x: 960, y: 690, at: 2.05, label: '记忆', color: '#44D17A'},
    {x: 790, y: 515, at: 2.65, label: '创作', color: '#FF6B9E'},
    {x: 1130, y: 515, at: 3.25, label: '发布', color: '#37E6E6'},
    {x: 700, y: 365, at: 3.9, label: '旅行', color: '#FF9F43'},
    {x: 1220, y: 365, at: 4.48, label: '出行', color: '#8C7BFF'},
  ];

  return (
    <svg viewBox="0 0 1920 1080" shapeRendering="crispEdges">
      <rect width="1920" height="1080" fill={BG} />

      {/* 像素天空与远景系统城 */}
      <rect y="0" width="1920" height="540" fill="#111C46" />
      <rect y="540" width="1920" height="360" fill="#1D3470" />
      {[
        [90, 130, 8], [220, 250, 5], [370, 95, 6], [540, 195, 4],
        [1370, 125, 6], [1540, 235, 5], [1740, 105, 8], [1830, 310, 4],
        [1140, 160, 4], [760, 105, 5],
      ].map(([x, y, s], i) => (
        <g key={i} fill={i % 3 === 0 ? '#FFD93D' : '#6D8ED8'} opacity={0.45 + 0.35 * Math.sin(t * 3 + i) ** 2}>
          <rect x={x} y={y} width={s} height={s * 3} />
          <rect x={x - s} y={y + s} width={s * 3} height={s} />
        </g>
      ))}
      <g fill="#263C77">
        <rect x="90" y="170" width="250" height="24" />
        <rect x="130" y="146" width="130" height="24" />
        <rect x="1510" y="175" width="260" height="24" />
        <rect x="1570" y="151" width="120" height="24" />
      </g>
      <g opacity="0.8">
        <path d="M0 720V590H90V540H170V625H250V510H340V570H420V720Z" fill="#16254F" />
        <path d="M1500 720V565H1580V500H1660V610H1735V535H1825V585H1920V720Z" fill="#16254F" />
        <g fill="#37E6E6" opacity="0.45">
          <rect x="115" y="580" width="22" height="22" /><rect x="280" y="550" width="22" height="22" />
          <rect x="1600" y="545" width="22" height="22" /><rect x="1765" y="575" width="22" height="22" />
        </g>
      </g>

      <g transform={`translate(${shake} ${-shake * 0.35})`}>
        {/* 广场地面 */}
        <rect y="720" width="1920" height="360" fill="#274C87" />
        <rect y="720" width="1920" height="18" fill="#3B72B6" />
        <path d="M0 900H1920V1080H0Z" fill="#1B3767" />
        <g stroke="#37639A" strokeWidth="5" opacity="0.7">
          <path d="M0 970H1920M0 1030H1920" />
          <path d="M240 900L100 1080M600 900L540 1080M960 900V1080M1320 900L1380 1080M1680 900L1820 1080" />
        </g>
        <ellipse cx="960" cy="915" rx="355" ry="52" fill="#10264F" opacity="0.65" />

        {/* 技能树：主干从地面弹出 */}
        <g transform={`translate(960 900) scale(1 ${grow}) translate(-960 -900)`}>
          <g fill="none" strokeLinecap="square" strokeLinejoin="miter">
            <path d="M960 855V690L790 515L700 365" stroke="#10213F" strokeWidth="66" />
            <path d="M960 855V690L1130 515L1220 365" stroke="#10213F" strokeWidth="66" />
            <path d="M960 690V285" stroke="#10213F" strokeWidth="76" />
            <path d="M960 855V690L790 515L700 365" stroke="#2878F0" strokeWidth="42" />
            <path d="M960 855V690L1130 515L1220 365" stroke="#2878F0" strokeWidth="42" />
            <path d="M960 690V285" stroke="#2878F0" strokeWidth="50" />
            <path d="M948 830V690L790 515" stroke="#55C7FF" strokeWidth="10" />
            <path d="M972 825V690L1130 515" stroke="#55C7FF" strokeWidth="10" />
          </g>
          <rect x="912" y="842" width="96" height="58" fill="#173A6B" />
          <rect x="930" y="842" width="18" height="58" fill="#44D17A" />
          <path d="M930 885H860V905H800V925H960H1120V905H1060V885H990Z" fill="#2878F0" />
          <rect x="935" y="620" width="50" height="22" fill="#FFD93D" />
          <rect x="935" y="440" width="50" height="22" fill="#FFD93D" />
        </g>

        {/* 依次点亮的技能节点 */}
        {nodes.map((n, i) => {
          const p = Math.max(0, e.back(clamp01((t - n.at) / 0.35)));
          const lit = t >= n.at;
          return (
            <g key={n.label} transform={`translate(${n.x} ${n.y}) scale(${p})`}>
              {lit && <rect x="-75" y="-75" width="150" height="150" fill={n.color} opacity={0.12 + 0.08 * Math.sin(t * 8 + i)} />}
              <rect x="-58" y="-58" width="116" height="116" fill="#0D1938" />
              <rect x="-48" y="-48" width="96" height="96" fill={lit ? n.color : '#31446B'} />
              <rect x="-36" y="-36" width="72" height="72" fill="#172554" />
              {i === 0 && <g fill={n.color}><rect x="-20" y="-20" width="40" height="32" /><rect x="-12" y="12" width="24" height="10" /></g>}
              {i === 1 && <path d="M-24 18L-14-20L8-30L26-12L16 12L-14 28Z" fill={n.color} />}
              {i === 2 && <path d="M0-30L22 4L12 26H-12L-22 4ZM-8 26H8V36H-8Z" fill={n.color} />}
              {i === 3 && <path d="M0-30C22-30 28-8 18 6L0 32L-18 6C-28-8-22-30 0-30ZM-8-12H8V0H-8Z" fill={n.color} />}
              {i === 4 && <path d="M-28 8V-8L-16-24H16L28-8V8H20V22H8V10H-8V22H-20V8Z" fill={n.color} />}
              <rect x="-54" y="66" width="108" height="34" fill="#0D1938" />
              <text x="0" y="90" textAnchor="middle" fill={lit ? '#FFFFFF' : '#7184AA'} fontSize="23" fontWeight="900" fontFamily="monospace">{n.label}</text>
            </g>
          );
        })}

        {/* 最后一颗升级星 */}
        <g transform={`translate(960 250) scale(${finalPop})`}>
          <PixelStar x={0} y={0} s={1.65 + Math.sin(t * 8) * 0.04} />
          <rect x="-10" y="-12" width="20" height="20" fill="#FFF4A8" />
        </g>

        {/* 左右经验按钮 */}
        {[{x: 500, name: 'LANDIS'}, {x: 1400, name: 'SIGMA'}].map((b) => (
          <g key={b.name}>
            <rect x={b.x - 118} y="862" width="236" height="70" fill="#0B1836" />
            <rect x={b.x - 106} y="850" width="212" height="64" fill="#596579" />
            <rect x={b.x - 94} y={842 + press * 12} width="188" height="42" fill={stomped ? '#FFB52E' : '#FF5C5C'} />
            <rect x={b.x - 78} y={850 + press * 12} width="156" height="9" fill="#FFF0B3" opacity="0.75" />
            <text x={b.x} y={874 + press * 12} textAnchor="middle" fill="#172554" fontSize="28" fontWeight="900" fontFamily="monospace">EXP</text>
          </g>
        ))}

        {/* 双人同步起跳、踩按钮 */}
        <g transform={`translate(500 ${854 - jump + idleBob}) scale(1.08)`}>
          <Character
            view="front"
            pose="stand"
            armL={stomped ? [-135, -25] : jumping ? [-110, -30] : [-25, -15]}
            armR={stomped ? [-45, -25] : jumping ? [-70, -30] : [-15, -15]}
            headTurn={10}
            tilt={jumping ? -4 : 0}
            mood={stomped ? 'surprised' : 'calm'}
          />
        </g>
        <g transform={`translate(1400 ${854 - jump - idleBob}) scale(0.64)`}>
          <Character
            view="front"
            pose="stand"
            armL={stomped ? [-135, -25] : jumping ? [-110, -30] : [-25, -15]}
            armR={stomped ? [-45, -25] : jumping ? [-70, -30] : [-15, -15]}
            headTurn={-10}
            tilt={jumping ? 4 : 0}
            mood={stomped ? 'surprised' : 'calm'}
          />
        </g>

        <g fontFamily="monospace" fontWeight="900" textAnchor="middle">
          <rect x="402" y="944" width="196" height="38" fill="#101C3D" />
          <text x="500" y="971" fill="#AAB4C8" fontSize="24">LANDIS</text>
          <rect x="1310" y="944" width="180" height="38" fill="#101C3D" />
          <text x="1400" y="971" fill="#FFD93D" fontSize="24">SIGMA</text>
        </g>

        {/* 同步踩踏冲击波与经验飘字 */}
        <g opacity={impact}>
          <path d="M270 900H390V884H610V900H730V916H610V932H390V916H270Z" fill="#FFD93D" />
          <path d="M1170 900H1290V884H1510V900H1630V916H1510V932H1290V916H1170Z" fill="#FFD93D" />
          <rect x="936" y="820" width="48" height="90" fill="#FFF4A8" />
          <rect x="900" y="850" width="120" height="30" fill="#FFF4A8" />
        </g>
        {stomped && (
          <g opacity={1 - clamp01((t - 2.15) / 0.55)} fontFamily="monospace" fontSize="38" fontWeight="900" fill="#FFD93D">
            <text x="345" y={800 - clamp01((t - 1.45) / 0.8) * 80}>+64 EXP</text>
            <text x="1450" y={800 - clamp01((t - 1.45) / 0.8) * 80}>+64 EXP</text>
          </g>
        )}
      </g>

      {/* 纸飞机飞入，轮廓连续地变成升级星 */}
      {t < 1.6 && (
        <g>
          <g opacity={planeOpacity * 0.65} fill="#B9F6FF">
            <rect x={planeX - 190} y={planeY + 25} width="80" height="10" />
            <rect x={planeX - 280} y={planeY + 50} width="48" height="10" />
            <rect x={planeX - 135} y={planeY + 72} width="34" height="8" />
          </g>
          <g transform={`translate(${planeX} ${planeY}) rotate(-12)`} opacity={planeOpacity}>
            <path d="M-80-24L82-58L28 62L-4 18L-48 42L-34-2Z" fill="#FFFFFF" />
            <path d="M-34-2L82-58L-4 18L28 62Z" fill="#76DDF2" />
            <path d="M-48 42L-34-2L-4 18Z" fill="#2878F0" />
          </g>
          <PixelStar x={morphX} y={morphY} s={morphScale} opacity={morphStarOpacity} />
        </g>
      )}

      {/* 顶部游戏 HUD */}
      <g fontFamily="monospace" fontWeight="900">
        <rect x="594" y="44" width="732" height="96" fill="#0B1533" />
        <rect x="606" y="56" width="708" height="72" fill="#263B6D" />
        <text x="632" y="101" fontSize="30" fill="#FFD93D">LV.08</text>
        <rect x="770" y="75" width="502" height="32" fill="#101B38" />
        <rect x="778" y="83" width={486 * xp} height="16" fill="#FFD93D" />
        <rect x="778" y="83" width={486 * xp} height="5" fill="#FFF4A8" />
        <text x="1020" y="67" textAnchor="middle" fontSize="19" fill="#FFFFFF">SIGMA SKILL TREE</text>
        {xp >= 0.999 && <text x="960" y="180" textAnchor="middle" fontSize="42" fill="#FFD93D">LEVEL UP!</text>}
      </g>

      {/* 终结星点亮时的像素彩纸 */}
      {t > 5.35 && Array.from({length: 20}, (_, i) => {
        const a = (i / 20) * Math.PI * 2;
        const d = e.easeOut(clamp01((t - 5.35) / 0.65)) * (150 + (i % 5) * 30);
        const x = 960 + Math.cos(a) * d;
        const y = 250 + Math.sin(a) * d + clamp01((t - 5.35) / 0.65) ** 2 * 90;
        return <rect key={i} x={x} y={y} width="14" height="14" fill={['#FFD93D', '#37E6E6', '#FF6B9E', '#44D17A'][i % 4]} />;
      })}

      <g fill="#44D17A">
        <rect x="40" y="1010" width="24" height="70" /><rect x="64" y="1032" width="48" height="16" />
        <rect x="1810" y="1022" width="24" height="58" /><rect x="1768" y="1040" width="42" height="16" />
      </g>
    </svg>
  );
};