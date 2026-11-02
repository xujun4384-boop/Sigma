import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';

export const BG = '#172554';
export const META = {11: {bg: '#172554'}};

const PixelStar = ({x, y, s = 1, r = 0, color = '#FFD93D'}: {
  x: number; y: number; s?: number; r?: number; color?: string;
}) => (
  <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}>
    <path
      d="M-12-62H12V-38H28V-24H62V12H38V28H24V46H12V62H-12V46H-24V28H-38V12H-62V-24H-28V-38H-12Z"
      fill="#8B4E16"
      transform="translate(7 9)"
    />
    <path
      d="M-12-62H12V-38H28V-24H62V12H38V28H24V46H12V62H-12V46H-24V28H-38V12H-62V-24H-28V-38H-12Z"
      fill={color}
      stroke="#FFF3A6"
      strokeWidth="5"
      strokeLinejoin="miter"
    />
    <rect x="-26" y="-20" width="12" height="16" fill="#FFF8C7" />
  </g>
);

const Check = ({x, y}: {x: number; y: number}) => (
  <path
    d={`M${x - 30} ${y}l18 18 42-48`}
    fill="none"
    stroke="#FFFFFF"
    strokeWidth="14"
    strokeLinecap="square"
    strokeLinejoin="miter"
  />
);

const CompleteStamp = ({x, y, p, rotate}: {
  x: number; y: number; p: number; rotate: number;
}) => {
  const scale = Math.max(0.001, p);
  return (
    <g
      transform={`translate(${x} ${y}) rotate(${rotate}) scale(${scale})`}
      opacity={Math.min(1, p * 2)}
    >
      <rect x="-139" y="-57" width="278" height="114" fill="#102C35" opacity="0.45" transform="translate(9 10)" />
      <rect x="-139" y="-57" width="278" height="114" fill="#44D17A" stroke="#B9FFCB" strokeWidth="8" />
      <rect x="-123" y="-41" width="246" height="82" fill="none" stroke="#143D45" strokeWidth="5" strokeDasharray="18 7" />
      <text x="0" y="18" textAnchor="middle" fontFamily="monospace" fontSize="52" fontWeight="900" fill="#102C35">已完成</text>
    </g>
  );
};

export const Shot11 = () => {
  const e = useE();
  const t = e.shotT;
  const press = e.easeIO(e.seg(1.25, 1.72, t));
  const stamp = e.back(e.clamp01((t - 1.72) / 0.34));
  const burst = e.clamp01((t - 1.9) / 0.85);
  const push = 1 + 0.025 * e.easeIO(e.shotU);
  const bob = Math.sin(t * Math.PI * 4) * 3;
  const reelRotation = t * 245;

  const stars = [
    {delay: 0, x: 790, y: 160, r: -18},
    {delay: 0.16, x: 960, y: 100, r: 8},
    {delay: 0.32, x: 1135, y: 170, r: 22},
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <pattern id="pixelGrid" width="64" height="64" patternUnits="userSpaceOnUse">
          <path d="M64 0H0V64" fill="none" stroke="#2B477D" strokeWidth="2" opacity="0.36" />
          <rect x="7" y="7" width="4" height="4" fill="#3B5A91" opacity="0.4" />
        </pattern>
        <linearGradient id="deskTop" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#31589B" />
          <stop offset="1" stopColor="#203866" />
        </linearGradient>
      </defs>

      <rect width="1920" height="1080" fill={BG} />
      <rect width="1920" height="1080" fill="url(#pixelGrid)" />

      <g transform={`translate(960 540) scale(${push}) translate(-960 -540)`}>
        {/* 远景：系统城窗口与像素庆祝灯 */}
        <rect x="0" y="0" width="1920" height="92" fill="#101C42" />
        <rect x="0" y="88" width="1920" height="8" fill="#2878F0" />
        <rect x="70" y="30" width="18" height="18" fill="#FF5C8A" />
        <rect x="102" y="30" width="18" height="18" fill="#FFD93D" />
        <rect x="134" y="30" width="18" height="18" fill="#44D17A" />
        <text x="184" y="53" fontFamily="monospace" fontSize="30" fontWeight="900" fill="#83B8FF">SIGMA OS / CREATION DESK</text>
        <text x="1810" y="54" textAnchor="end" fontFamily="monospace" fontSize="27" fontWeight="900" fill="#FFD93D">CREATE × PUBLISH</text>

        {[
          [80, 138, '#2878F0'], [180, 92, '#FFD93D'], [1740, 136, '#FF5C8A'],
          [1830, 224, '#44D17A'], [1510, 116, '#2878F0'], [410, 116, '#FF5C8A'],
        ].map(([x, y, c], i) => (
          <g key={i} transform={`translate(${x} ${y})`} opacity={0.55 + 0.35 * Math.sin(t * 5 + i)}>
            <rect x="-6" y="-22" width="12" height="44" fill={c as string} />
            <rect x="-22" y="-6" width="44" height="12" fill={c as string} />
          </g>
        ))}

        {/* 左：科普视频胶片窗口 */}
        <g transform="translate(105 160)">
          <rect x="14" y="16" width="650" height="472" fill="#0B1432" opacity="0.65" />
          <rect width="650" height="472" fill="#233E78" stroke="#6EA8FF" strokeWidth="8" />
          <rect width="650" height="58" fill="#2878F0" />
          <rect x="20" y="18" width="20" height="20" fill="#FFD93D" />
          <rect x="52" y="18" width="20" height="20" fill="#FF5C8A" />
          <text x="94" y="40" fontFamily="monospace" fontSize="28" fontWeight="900" fill="#FFFFFF">科普视频_FINAL.mp4</text>

          <rect x="28" y="84" width="594" height="282" fill="#111B3D" stroke="#14213D" strokeWidth="8" />
          <rect x="46" y="102" width="558" height="246" fill="#5138A8" />
          <path d="M46 290L142 210 214 266 314 158 416 250 508 188 604 262V348H46Z" fill="#2878F0" />
          <path d="M46 318L164 258 268 324 388 236 498 316 604 270V348H46Z" fill="#173A6B" />

          {/* 像素原子与播放符号 */}
          <g transform="translate(325 218)">
            <path d="M-100 0H100M0-78V78" stroke="#7DE7FF" strokeWidth="9" strokeDasharray="18 9" />
            <path d="M-76-54L76 54M-76 54L76-54" stroke="#FFD93D" strokeWidth="9" strokeDasharray="16 10" />
            <rect x="-23" y="-23" width="46" height="46" fill="#FF5C8A" stroke="#FFFFFF" strokeWidth="6" />
            <rect x="-111" y="-10" width="22" height="22" fill="#FFFFFF" />
            <rect x="89" y="-10" width="22" height="22" fill="#FFFFFF" />
          </g>
          <path d="M301 185L301 251 357 218Z" fill="#FFFFFF" opacity="0.9" />

          <rect x="28" y="389" width="42" height="42" fill="#44D17A" />
          <path d="M40 398V422L60 410Z" fill="#143D45" />
          <rect x="86" y="401" width="492" height="18" fill="#101C42" />
          <rect x="86" y="401" width={492 * Math.min(1, 0.55 + t * 0.12)} height="18" fill="#FFD93D" />
          <rect x="578" y="394" width="20" height="32" fill="#FFFFFF" />
          <text x="32" y="458" fontFamily="monospace" fontSize="20" fontWeight="700" fill="#9CC7FF">RENDER 100%  •  SCIENCE MODE</text>

          <CompleteStamp x={440} y={282} p={stamp} rotate={-9} />
        </g>

        {/* 右：公众号文章卡片 */}
        <g transform="translate(1165 160)">
          <rect x="14" y="16" width="650" height="472" fill="#0B1432" opacity="0.65" />
          <rect width="650" height="472" fill="#F5F7FF" stroke="#9CC7FF" strokeWidth="8" />
          <rect width="650" height="58" fill="#6A4FD8" />
          <rect x="20" y="15" width="30" height="30" fill="#44D17A" />
          <path d="M27 25h16v12H27zM31 21h8v4h-8z" fill="#FFFFFF" />
          <text x="72" y="40" fontFamily="monospace" fontSize="28" fontWeight="900" fill="#FFFFFF">公众号 / 发布预览</text>

          <rect x="34" y="88" width="150" height="150" fill="#2878F0" />
          <rect x="48" y="102" width="122" height="122" fill="#14213D" />
          <PixelStar x={109} y={163} s={0.68} r={-8} />
          <text x="212" y="121" fontFamily="monospace" fontSize="30" fontWeight="900" fill="#172554">今天也要讲明白！</text>
          <text x="212" y="162" fontFamily="monospace" fontSize="23" fontWeight="700" fill="#52658A">Sigma 的奇妙科普小课堂</text>
          <rect x="212" y="184" width="356" height="13" fill="#C8D4EE" />
          <rect x="212" y="211" width="290" height="13" fill="#DCE4F5" />

          <rect x="34" y="266" width="582" height="12" fill="#D7E0F2" />
          <rect x="34" y="296" width="530" height="12" fill="#D7E0F2" />
          <rect x="34" y="326" width="558" height="12" fill="#D7E0F2" />
          <rect x="34" y="356" width="390" height="12" fill="#D7E0F2" />
          <rect x="34" y="404" width="168" height="40" fill="#DDE8FF" />
          <text x="118" y="431" textAnchor="middle" fontFamily="monospace" fontSize="20" fontWeight="900" fill="#2878F0"># 科普创作</text>
          <rect x="472" y="397" width="144" height="52" fill="#44D17A" />
          <text x="544" y="432" textAnchor="middle" fontFamily="monospace" fontSize="25" fontWeight="900" fill="#123B44">已发布</text>

          <CompleteStamp x={250} y={294} p={stamp} rotate={8} />
        </g>

        {/* 三连星爆发：从中央技能核心向外弹出 */}
        <g>
          {stars.map((star, i) => {
            const q = e.back(e.clamp01((t - 1.92 - star.delay) / 0.55));
            const visible = e.clamp01((t - 1.92 - star.delay) / 0.12);
            const x = e.lerp(960, star.x, q);
            const y = e.lerp(590, star.y, q) - Math.sin(q * Math.PI) * 80;
            return (
              <g key={i} opacity={visible}>
                <rect x={e.lerp(950, star.x - 22, q)} y={e.lerp(580, star.y + 55, q)} width="18" height="18" fill="#FFF3A6" />
                <PixelStar x={x} y={y} s={0.82 * Math.max(0.01, q)} r={star.r + Math.sin(t * 4 + i) * 4} />
              </g>
            );
          })}
          {burst > 0.55 && (
            <g transform={`translate(960 326) scale(${e.back(e.clamp01((burst - 0.55) / 0.35))})`}>
              <rect x="-176" y="-34" width="352" height="68" fill="#101C42" stroke="#FFD93D" strokeWidth="6" />
              <text x="0" y="13" textAnchor="middle" fontFamily="monospace" fontSize="35" fontWeight="900" fill="#FFD93D">创作技能 · 三连星!</text>
            </g>
          )}
        </g>

        {/* Sigma：左手转胶片，右手按发布 */}
        <g transform={`translate(0 ${bob})`}>
          <Actor
            Character={Character}
            x={950}
            y={1010}
            s={1.16}
            pose="stand"
            mood={t > 1.65 && t < 2.7 ? 'surprised' : 'calm'}
            tilt={-3 + press * 5}
            headTurn={-5 + press * 10}
            armL={[-62 - Math.sin(t * 12) * 10, -32]}
            armR={[-48 - press * 30, -28 + press * 20]}
          />
        </g>

        {/* 前景创作控制台，遮住脚部形成稳定桌面轴线 */}
        <g>
          <path d="M420 760H1500L1570 1018H350Z" fill="#101A37" opacity="0.55" transform="translate(0 18)" />
          <path d="M420 760H1500L1570 1018H350Z" fill="url(#deskTop)" stroke="#6EA8FF" strokeWidth="8" />
          <path d="M450 790H1470L1490 860H430Z" fill="#3C68A9" />
          <rect x="350" y="1008" width="1220" height="28" fill="#101C42" />
          <rect x="450" y="1036" width="70" height="44" fill="#101C42" />
          <rect x="1400" y="1036" width="70" height="44" fill="#101C42" />

          {/* 左手胶片卷轴 */}
          <g transform="translate(685 846)">
            <rect x="-136" y="64" width="272" height="30" fill="#14213D" />
            <g transform={`rotate(${reelRotation})`}>
              <path d="M-72-48L-48-72H48L72-48V48L48 72H-48L-72 48Z" fill="#D7E0F2" stroke="#101C42" strokeWidth="9" />
              <rect x="-17" y="-58" width="34" height="34" fill="#2878F0" />
              <rect x="-17" y="24" width="34" height="34" fill="#2878F0" />
              <rect x="-58" y="-17" width="34" height="34" fill="#2878F0" />
              <rect x="24" y="-17" width="34" height="34" fill="#2878F0" />
              <rect x="-16" y="-16" width="32" height="32" fill="#FFD93D" />
            </g>
            <path d="M68 50H170V72H194V94H108V72H68Z" fill="#161A2B" />
            {[0, 1, 2, 3].map(i => <rect key={i} x={86 + i * 25} y={i < 2 ? 54 : 76} width="10" height="10" fill="#D7E0F2" />)}
            <text x="0" y="128" textAnchor="middle" fontFamily="monospace" fontSize="22" fontWeight="900" fill="#9CC7FF">转胶片</text>
          </g>

          {/* 中央经验读数 */}
          <g transform="translate(960 878)">
            <rect x="-146" y="-64" width="292" height="105" fill="#14213D" stroke="#101C42" strokeWidth="7" />
            <text x="0" y="-30" textAnchor="middle" fontFamily="monospace" fontSize="22" fontWeight="900" fill="#83B8FF">CREATION EXP</text>
            <rect x="-120" y="-12" width="240" height="25" fill="#0B1432" />
            <rect x="-115" y="-7" width={230 * e.clamp01(0.35 + t * 0.22)} height="15" fill="#FFD93D" />
            {stamp > 0.5 && <text x="0" y="78" textAnchor="middle" fontFamily="monospace" fontSize="26" fontWeight="900" fill="#FFD93D">EXP +300!</text>}
          </g>

          {/* 右手发布键 */}
          <g transform="translate(1240 858)">
            <rect x="-118" y="-72" width="236" height="154" fill="#14213D" stroke="#101C42" strokeWidth="8" />
            <rect x="-89" y={-46 + press * 18} width="178" height="76" fill="#A9275D" />
            <rect x="-89" y={-58 + press * 18} width="178" height="76" fill={press > 0.8 ? '#44D17A' : '#FF5C8A'} stroke="#FFFFFF" strokeWidth="6" />
            <text x="0" y={-7 + press * 18} textAnchor="middle" fontFamily="monospace" fontSize="31" fontWeight="900" fill="#FFFFFF">发布!</text>
            {stamp > 0.5 && <Check x={0} y={118} />}
          </g>
        </g>

        {/* 按键冲击像素 */}
        {stamp > 0 && (
          <g opacity={e.clamp01(1.8 - t)} fill="#FFF3A6">
            <rect x="1110" y="724" width="18" height="52" transform="rotate(-35 1119 750)" />
            <rect x="1348" y="724" width="18" height="52" transform="rotate(35 1357 750)" />
            <rect x="1228" y="682" width="22" height="58" />
          </g>
        )}
      </g>
    </svg>
  );
};