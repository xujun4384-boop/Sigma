import React from 'react';
import {useE} from '../../engine/context';
import {Actor} from '../../ui/Actor';
import {Character} from './char-hero';

export const BG = '#172554';
export const META = {2: {bg: '#172554'}};

const PixelStar = ({
  x = 0,
  y = 0,
  s = 1,
  rotate = 0,
  face = false,
  opacity = 1,
}: {
  x?: number;
  y?: number;
  s?: number;
  rotate?: number;
  face?: boolean;
  opacity?: number;
}) => (
  <g transform={`translate(${x} ${y}) rotate(${rotate}) scale(${s})`} opacity={opacity}>
    <path
      d="M-38-112H38V-76H76V-40H116V2H78V38H58V94H20V68H-20V94H-58V38H-78V2H-116V-40H-76V-76H-38Z"
      fill="#FFD93D"
      stroke="#F5B91E"
      strokeWidth="7"
      strokeLinejoin="round"
    />
    <path d="M-30-96H30V-82H-30Z" fill="#FFF3A6" opacity=".8" />
    <path d="M-98-30H-80V-12H-98ZM80 12H96V30H80Z" fill="#FFF3A6" opacity=".55" />
    {face && (
      <g>
        <rect x="-43" y="-37" width="17" height="27" rx="7" fill="#161A2B" />
        <rect x="27" y="-37" width="17" height="27" rx="7" fill="#161A2B" />
        <rect x="-39" y="-33" width="5" height="7" rx="2" fill="#FFFFFF" />
        <rect x="31" y="-33" width="5" height="7" rx="2" fill="#FFFFFF" />
        <path d="M-15 4Q0 17 15 4" fill="none" stroke="#161A2B" strokeWidth="7" strokeLinecap="round" />
        <rect x="-66" y="-2" width="19" height="9" rx="4" fill="#FF9F68" opacity=".65" />
        <rect x="48" y="-2" width="19" height="9" rx="4" fill="#FF9F68" opacity=".65" />
      </g>
    )}
  </g>
);

const DocumentStack = ({caught = false}: {caught?: boolean}) => (
  <g>
    <g transform="rotate(-8)">
      <rect x="-66" y="-88" width="132" height="166" rx="8" fill="#B9D5FF" stroke="#173A6B" strokeWidth="6" />
      <path d="M38-88L66-60H38Z" fill="#78A7EB" />
    </g>
    <g transform="translate(9 -5) rotate(5)">
      <rect x="-66" y="-88" width="132" height="166" rx="8" fill="#FFFFFF" stroke="#173A6B" strokeWidth="6" />
      <path d="M36-88L66-58H36Z" fill="#C9DDF8" />
      <rect x="-40" y="-52" width="54" height="10" rx="3" fill="#2878F0" />
      <rect x="-40" y="-25" width="80" height="8" rx="3" fill="#AAB4C8" />
      <rect x="-40" y="-5" width="69" height="8" rx="3" fill="#AAB4C8" />
      <rect x="-40" y="24" width="35" height="28" rx="4" fill="#D9E9FF" />
      <path d="M-31 43L-23 34L-16 39L-9 29" fill="none" stroke="#44D17A" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="8" y="27" width="33" height="7" rx="3" fill="#FFD93D" />
      <rect x="8" y="43" width="26" height="6" rx="3" fill="#AAB4C8" />
    </g>
    {caught && <path d="M-51 91Q0 105 53 87" fill="none" stroke="#2878F0" strokeWidth="8" strokeLinecap="round" />}
  </g>
);

export const Shot2 = () => {
  const e = useE();
  const t = e.shotT;
  const {lerp, clamp01, seg, easeOut, easeIO, back} = e;

  const zoom = lerp(1, 1.045, easeIO(e.shotU));
  const pop = clamp01(seg(0.48, 1.55, t));
  const flyY = lerp(493, 846, pop) - Math.sin(pop * Math.PI) * 285;
  const flyX = lerp(535, 874, pop);
  const landed = t >= 1.5;
  const grow = Math.max(0.04, back(clamp01(seg(1.5, 2.2, t))));
  const landingSquash = 1 - Math.sin(clamp01(seg(1.48, 1.83, t)) * Math.PI) * 0.12;
  const docP = easeIO(clamp01(seg(2.25, 3.22, t)));
  const caught = t >= 3.18;
  const recoil = Math.sin(clamp01(seg(3.15, 3.85, t)) * Math.PI) * -9;
  const salute = easeOut(clamp01(seg(3.95, 4.48, t)));
  const hop = Math.sin(clamp01(seg(3.15, 3.58, t)) * Math.PI) * 24;
  const titleP = back(clamp01(seg(4.35, 5.08, t)));
  const terminalPulse = 0.55 + 0.25 * Math.sin(t * 8);
  const blink = t > 5.38 && t < 5.5 ? 0.12 : 1;

  const sparks = [
    [-112, -18, 12, '#FFD93D'], [-78, -92, 9, '#FFFFFF'], [-22, -128, 13, '#2878F0'],
    [55, -105, 8, '#FFD93D'], [111, -42, 12, '#44D17A'], [92, 43, 8, '#FFFFFF'],
    [-128, 52, 8, '#2878F0'], [35, 65, 10, '#FFD93D'],
  ];

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="roomBg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#101B3E" />
          <stop offset=".55" stopColor="#172554" />
          <stop offset="1" stopColor="#263B75" />
        </linearGradient>
        <linearGradient id="dawn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#172554" />
          <stop offset=".72" stopColor="#5138A8" />
          <stop offset="1" stopColor="#FF9F68" />
        </linearGradient>
        <linearGradient id="deskTop" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#805A49" />
          <stop offset="1" stopColor="#4A3540" />
        </linearGradient>
        <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#08142C" />
          <stop offset="1" stopColor="#102B45" />
        </linearGradient>
        <linearGradient id="titlePanel" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#101B3E" stopOpacity=".96" />
          <stop offset="1" stopColor="#173A6B" stopOpacity=".96" />
        </linearGradient>
        <radialGradient id="starHalo">
          <stop offset="0" stopColor="#FFD93D" stopOpacity=".52" />
          <stop offset="1" stopColor="#FFD93D" stopOpacity="0" />
        </radialGradient>
        <filter id="softGlow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="18" />
        </filter>
        <filter id="smallGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="7" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="shadow" x="-60%" y="-60%" width="220%" height="240%">
          <feDropShadow dx="0" dy="15" stdDeviation="13" floodColor="#050917" floodOpacity=".48" />
        </filter>
        <clipPath id="windowClip"><rect x="1275" y="80" width="510" height="390" rx="18" /></clipPath>
      </defs>

      <rect width="1920" height="1080" fill={BG} />

      <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
        <rect x="-90" y="-80" width="2100" height="1230" fill="url(#roomBg)" />
        <path d="M0 710L1920 610V1080H0Z" fill="#10182F" />
        <path d="M0 742L1920 644" stroke="#304675" strokeWidth="5" opacity=".55" />

        {/* 黎明前的窗景 */}
        <g clipPath="url(#windowClip)">
          <rect x="1275" y="80" width="510" height="390" fill="url(#dawn)" />
          <circle cx="1680" cy="350" r="78" fill="#FFD93D" opacity=".15" filter="url(#softGlow)" />
          <path d="M1275 375L1340 337L1397 366L1464 311L1528 354L1595 325L1688 367L1785 315V470H1275Z" fill="#1A2851" />
          <path d="M1275 411H1330V360H1370V411H1425V335H1475V411H1540V377H1585V411H1650V346H1708V411H1785V470H1275Z" fill="#101B3E" />
          <g fill="#FFD93D" opacity=".65">
            <rect x="1441" y="357" width="9" height="12" /><rect x="1670" y="368" width="9" height="12" />
            <rect x="1350" y="386" width="8" height="10" /><rect x="1736" y="398" width="8" height="10" />
          </g>
        </g>
        <rect x="1275" y="80" width="510" height="390" rx="18" fill="none" stroke="#52638E" strokeWidth="18" />
        <path d="M1530 88V462M1283 267H1777" stroke="#52638E" strokeWidth="12" />
        <path d="M1248 62V489M1811 62V489" stroke="#0B132C" strokeWidth="18" opacity=".7" />

        {/* 后景便签与书架 */}
        <g opacity=".72">
          <rect x="858" y="112" width="270" height="25" rx="8" fill="#0A122A" />
          <rect x="886" y="55" width="35" height="57" fill="#2878F0" />
          <rect x="928" y="42" width="31" height="70" fill="#5138A8" />
          <rect x="967" y="67" width="43" height="45" fill="#44D17A" />
          <rect x="1020" y="50" width="28" height="62" fill="#FF5C5C" />
          <rect x="1060" y="74" width="45" height="38" fill="#FFD93D" />
          <rect x="1130" y="204" width="92" height="78" rx="5" fill="#FFD93D" transform="rotate(5 1130 204)" />
          <path d="M1150 232H1200M1150 250H1185" stroke="#8B6814" strokeWidth="6" strokeLinecap="round" />
        </g>

        {/* Landis 位于右侧， Sigma 朝他敬礼 */}
        <g opacity={clamp01(seg(1.85, 2.5, t))}>
          <ellipse cx="1630" cy="956" rx="155" ry="28" fill="#080D20" opacity=".45" />
          <Actor
            Character={Character}
            x={1640}
            y={955}
            s={1.06}
            flip
            view="side"
            mood="calm"
            headTurn={-8}
            armL={[-18, -35]}
            armR={[-10, -25]}
          />
        </g>

        {/* 木桌与近景终端 */}
        <path d="M-80 703L775 650L1125 810L-80 924Z" fill="url(#deskTop)" />
        <path d="M-80 893L1125 786V838L-80 966Z" fill="#362838" />
        <path d="M90 727L698 687" stroke="#B38260" strokeWidth="5" opacity=".35" />
        <path d="M54 805L835 729" stroke="#B38260" strokeWidth="4" opacity=".22" />

        <g filter="url(#shadow)">
          <path d="M104 301Q104 275 132 275H692Q720 275 720 303V673Q720 696 692 696H132Q104 696 104 673Z" fill="#202B49" stroke="#5E719A" strokeWidth="8" />
          <rect x="132" y="310" width="560" height="334" rx="12" fill="url(#screen)" />
          <rect x="132" y="310" width="560" height="42" rx="12" fill="#26395C" />
          <circle cx="158" cy="331" r="7" fill="#FF5C5C" />
          <circle cx="181" cy="331" r="7" fill="#FFD93D" />
          <circle cx="204" cy="331" r="7" fill="#44D17A" />
          <text x="242" y="338" fill="#9BB4DA" fontSize="19" fontFamily="monospace">sigma — terminal</text>
          <text x="158" y="393" fill="#7DE2D1" fontSize="24" fontFamily="monospace">landis@night ~ %</text>
          <text x="158" y="435" fill="#E8F1FF" fontSize="26" fontFamily="monospace">python sigma.py</text>
          <rect x="158" y="463" width="342" height="3" fill="#1D4160" />
          <text x="158" y="510" fill="#44D17A" fontSize="22" fontFamily="monospace" opacity={clamp01(seg(.15, .45, t))}>
            boot: first_star()
          </text>
          <text x="158" y="552" fill="#FFD93D" fontSize="24" fontFamily="monospace" opacity={clamp01(seg(.34, .58, t))}>
            ✦ HELLO, WORLD!
          </text>
          <rect x="158" y="583" width="16" height="26" fill="#7DE2D1" opacity={terminalPulse} />
          <path d="M350 696H474L500 737H324Z" fill="#354567" />
          <rect x="281" y="731" width="260" height="24" rx="12" fill="#52638A" />
        </g>

        <ellipse cx="544" cy="496" rx="215" ry="190" fill="url(#starHalo)" opacity={clamp01(seg(.25, .72, t)) * (1 - clamp01(seg(1.2, 1.75, t)))} />

        {/* 键盘与桌面细节 */}
        <g transform="translate(230 756) skewX(-18)">
          <rect width="410" height="95" rx="16" fill="#1A2541" stroke="#617497" strokeWidth="5" />
          {Array.from({length: 10}).map((_, i) => (
            <g key={i}>
              <rect x={20 + i * 36} y="17" width="27" height="22" rx="4" fill={i === 8 ? '#2878F0' : '#3B4C6C'} />
              <rect x={20 + i * 36} y="49" width="27" height="22" rx="4" fill="#3B4C6C" />
            </g>
          ))}
        </g>
        <g transform="translate(740 693) rotate(5)">
          <rect width="112" height="112" rx="15" fill="#182542" stroke="#617497" strokeWidth="5" />
          <rect x="15" y="17" width="82" height="57" rx="9" fill="#2878F0" />
          <text x="56" y="57" textAnchor="middle" fill="#FFFFFF" fontSize="25" fontWeight="800" fontFamily="monospace">↵</text>
        </g>

        {/* 落地冲击 */}
        {t > 1.38 && t < 2.05 && (
          <g transform="translate(875 881)" opacity={1 - clamp01(seg(1.48, 2.02, t))}>
            <ellipse rx={lerp(30, 190, clamp01(seg(1.42, 1.9, t)))} ry="22" fill="none" stroke="#FFD93D" strokeWidth="9" />
            {sparks.map(([x, y, size, color], i) => {
              const p = clamp01(seg(1.42, 1.95, t));
              return <rect key={i} x={Number(x) * p} y={Number(y) * p} width={Number(size)} height={Number(size)} fill={String(color)} transform={`rotate(${p * 80} ${Number(x) * p} ${Number(y) * p})`} />;
            })}
          </g>
        )}

        {/* 从终端跳出的像素星 */}
        {!landed && t > .43 && (
          <g filter="url(#smallGlow)">
            <PixelStar
              x={flyX}
              y={flyY}
              s={lerp(.12, .64, easeOut(pop))}
              rotate={lerp(-22, 350, pop)}
              opacity={clamp01(seg(.43, .58, t))}
            />
          </g>
        )}

        {/* 飞来的文档 */}
        {t > 2.22 && !caught && (
          <g transform={`translate(${lerp(1480, 918, docP)} ${lerp(370, 626, docP) - Math.sin(docP * Math.PI) * 100}) rotate(${lerp(28, -8, docP)}) scale(.83)`} filter="url(#shadow)">
            <path d="M180-25H330M195 10H375M170 45H290" stroke="#8FC5FF" strokeWidth="8" strokeLinecap="round" opacity={.45 * (1 - docP)} />
            <DocumentStack />
          </g>
        )}

        {/* Sigma：落地生长、接文档、敬礼 */}
        {landed && (
          <g transform={`translate(882 ${899 - hop})`}>
            <ellipse cx="0" cy={8 + hop} rx={105 * grow} ry="24" fill="#070D21" opacity=".5" />
            <g transform={`rotate(${recoil}) scale(${grow * .78} ${grow * .78 * landingSquash})`}>
              {/* 腿与运动鞋 */}
              <path d="M-57-133L-51-42" stroke="#F2C7A5" strokeWidth="32" strokeLinecap="round" />
              <path d="M49-133L45-42" stroke="#F2C7A5" strokeWidth="32" strokeLinecap="round" />
              <path d="M-82-57Q-47-73-24-47L-18-18H-91Q-104-33-82-57Z" fill="#FFFFFF" stroke="#173A6B" strokeWidth="7" />
              <path d="M23-49Q55-71 79-42L94-18H19Q7-31 23-49Z" fill="#FFFFFF" stroke="#173A6B" strokeWidth="7" />
              <path d="M-83-38H-24M28-38H80" stroke="#2878F0" strokeWidth="10" />
              <path d="M-99-157Q0-177 96-154L77-95H18L0-125L-17-95H-78Z" fill="#173A6B" stroke="#102747" strokeWidth="7" />

              {/* 连帽衫 */}
              <path d="M-78-302Q0-338 78-302L105-164Q54-135 0-148Q-57-135-105-164Z" fill="#2878F0" stroke="#1552B8" strokeWidth="8" />
              <path d="M-57-292Q0-252 57-292" fill="none" stroke="#79AEFF" strokeWidth="10" strokeLinecap="round" />
              <path d="M-17-274V-214M20-274V-214" stroke="#FFFFFF" strokeWidth="7" strokeLinecap="round" />
              <circle cx="-17" cy="-209" r="8" fill="#FFD93D" />
              <circle cx="20" cy="-209" r="8" fill="#FFD93D" />
              <path d="M-45-186Q0-169 45-186" fill="none" stroke="#1552B8" strokeWidth="7" strokeLinecap="round" />

              {/* 左臂抱文档 */}
              <path d="M-77-277Q-132-248-107-182Q-82-159-45-184" fill="none" stroke="#2878F0" strokeWidth="47" strokeLinecap="round" />
              <circle cx="-47" cy="-185" r="27" fill="#FFFFFF" stroke="#C9D9ED" strokeWidth="5" />
              {caught && (
                <g transform="translate(-3 -213) rotate(-5) scale(.78)">
                  <DocumentStack caught />
                </g>
              )}
              {caught && <path d="M66-248Q106-215 57-172" fill="none" stroke="#2878F0" strokeWidth="39" strokeLinecap="round" />}
              {caught && <circle cx="54" cy="-174" r="25" fill="#FFFFFF" stroke="#C9D9ED" strokeWidth="5" />}

              {/* 右臂由体侧抬至星角敬礼 */}
              {!caught && (
                <g>
                  <path d="M78-278Q125-249 119-183" fill="none" stroke="#2878F0" strokeWidth="46" strokeLinecap="round" />
                  <circle cx="118" cy="-174" r="27" fill="#FFFFFF" stroke="#C9D9ED" strokeWidth="5" />
                </g>
              )}
              {caught && salute > .02 && (
                <g transform={`translate(76 -278) rotate(${-140 * salute})`}>
                  <path d="M0 0L63 81" stroke="#2878F0" strokeWidth="46" strokeLinecap="round" />
                  <circle cx="65" cy="87" r="28" fill="#FFFFFF" stroke="#C9D9ED" strokeWidth="5" />
                  <path d="M51 73L76 94M58 65L84 86" stroke="#D8E4F2" strokeWidth="4" strokeLinecap="round" />
                </g>
              )}

              {/* 星头 */}
              <g transform={`translate(0 -394) scale(.92 ${.92 * blink})`}>
                <PixelStar face />
              </g>
            </g>
          </g>
        )}

        {/* 敬礼成功的小星星 */}
        {salute > .65 && (
          <g opacity={clamp01(seg(4.28, 4.55, t))}>
            <path d="M1080 373V417M1058 395H1102" stroke="#FFD93D" strokeWidth="9" strokeLinecap="square" />
            <path d="M1137 433V463M1122 448H1152" stroke="#FFFFFF" strokeWidth="7" />
            <rect x="1044" y="328" width="14" height="14" fill="#44D17A" transform="rotate(18 1051 335)" />
          </g>
        )}

        {/* 前景桌沿强化近景层次 */}
        <path d="M-60 1000L583 895L755 1080H-60Z" fill="#241C2C" opacity=".8" />
        <path d="M-30 994L580 898" stroke="#9B6C50" strokeWidth="9" opacity=".35" />
      </g>

      {/* 右下角片名，作为独立图形层滑入 */}
      <g transform={`translate(${lerp(1970, 1228, titleP)} 842)`} opacity={clamp01(seg(4.34, 4.62, t))}>
        <path d="M0 22Q0 0 22 0H614Q636 0 636 22V174Q636 196 614 196H22Q0 196 0 174Z" fill="url(#titlePanel)" stroke="#496AAF" strokeWidth="3" />
        <rect x="0" y="0" width="13" height="196" rx="6" fill="#FFD93D" />
        <rect x="39" y="31" width="112" height="30" rx="15" fill="#2878F0" />
        <text x="95" y="53" textAnchor="middle" fill="#FFFFFF" fontSize="17" fontWeight="700" fontFamily="Arial, sans-serif" letterSpacing="2">PLAYER 01</text>
        <text x="38" y="119" fill="#FFFFFF" fontSize="54" fontWeight="900" fontFamily="Arial, 'Noto Sans SC', sans-serif" letterSpacing="-1">
          Sigma AI
        </text>
        <text x="260" y="119" fill="#FFD93D" fontSize="43" fontWeight="900" fontFamily="'Noto Sans SC', 'Microsoft YaHei', sans-serif">
          ：开机第一名
        </text>
        <text x="41" y="161" fill="#AFC8ED" fontSize="20" fontFamily="'Noto Sans SC', 'Microsoft YaHei', sans-serif" letterSpacing="3">
          手搓伙伴 · 启动完成
        </text>
        <g transform="translate(568 46)">
          <PixelStar s=".25" />
        </g>
      </g>
    </svg>
  );
};