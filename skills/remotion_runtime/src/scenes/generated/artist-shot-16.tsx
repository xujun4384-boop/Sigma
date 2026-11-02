import React from 'react';
import {useE} from '../../engine/context';
import {Actor} from '../../ui/Actor';
import {Character} from './char-hero';

export const BG = '#172554';
export const META = {16: {bg: '#172554'}};

const Sigma = ({x, y, s, rise}: {x: number; y: number; s: number; rise: number}) => (
  <g transform={`translate(${x} ${y + (1 - rise) * 185}) scale(${s})`} opacity={Math.min(1, rise * 2)}>
    <rect x={-43} y={-29} width={86} height={102} fill="#2878F0" />
    <rect x={-54} y={-16} width={13} height={64} fill="#1D5DC5" />
    <rect x={41} y={-16} width={13} height={64} fill="#1D5DC5" />
    <rect x={-28} y={69} width={23} height={47} fill="#173A6B" />
    <rect x={7} y={69} width={23} height={47} fill="#173A6B" />
    <rect x={-38} y={105} width={38} height={18} fill="#FFFFFF" />
    <rect x={2} y={105} width={40} height={18} fill="#FFFFFF" />
    <rect x={-38} y={117} width={38} height={7} fill="#2878F0" />
    <rect x={2} y={117} width={40} height={7} fill="#2878F0" />
    <rect x={-68} y={38} width={25} height={25} fill="#FFFFFF" />
    <rect x={43} y={38} width={25} height={25} fill="#FFFFFF" />
    <path
      d="M-20-200H20V-172H44V-148H92V-124H68V-100H44V-76H68V-52H44V-28H20V-52H-20V-28H-44V-52H-68V-76H-44V-100H-68V-124H-92V-148H-44V-172H-20Z"
      fill="#FFD93D"
      stroke="#E9A91B"
      strokeWidth={6}
      strokeLinejoin="miter"
    />
    <rect x={-38} y={-137} width={14} height={20} fill="#161A2B" />
    <rect x={24} y={-137} width={14} height={20} fill="#161A2B" />
    <rect x={-13} y={-102} width={26} height={7} fill="#B87618" />
    <rect x={-15} y={4} width={30} height={8} fill="#8DBBFF" />
    <rect x={-5} y={12} width={10} height={23} fill="#FFD93D" />
  </g>
);

const AppIcon = ({x, y, color, label, kind, delay}: {
  x: number; y: number; color: string; label: string; kind: number; delay: number;
}) => {
  const e = useE();
  const enter = e.back(e.seg(delay, delay + 0.45, e.shotT));
  const hop = Math.max(0, Math.sin(e.shotT * 13.6 + kind * 1.7)) * 5;
  return (
    <g transform={`translate(${x} ${y - hop + (1 - enter) * 90})`} opacity={enter}>
      <rect x={-48} y={-48} width={104} height={104} fill="#080E27" />
      <rect x={-52} y={-52} width={104} height={104} fill={color} stroke="#FFFFFF" strokeWidth={5} />
      {kind === 0 && <>
        <path d="M-30 24V-25L-6-12 18-28 32-18V28L8 15-16 31Z" fill="#FFFFFF" />
        <path d="M-6-12V18M18-28V13" stroke={color} strokeWidth={6} />
      </>}
      {kind === 1 && <>
        <rect x={-33} y={-8} width={66} height={28} fill="#FFFFFF" />
        <rect x={-20} y={-25} width={39} height={20} fill="#FFFFFF" />
        <rect x={-25} y={20} width={14} height={14} fill="#161A2B" />
        <rect x={14} y={20} width={14} height={14} fill="#161A2B" />
        <rect x={-12} y={-19} width={24} height={11} fill="#37E6E6" />
      </>}
      {kind === 2 && <>
        <rect x={-27} y={-32} width={54} height={66} fill="#FFFFFF" />
        <rect x={-17} y={-18} width={34} height={6} fill={color} />
        <rect x={-17} y={-3} width={34} height={6} fill={color} />
        <rect x={-17} y={12} width={23} height={6} fill={color} />
      </>}
      {kind === 3 && <>
        <rect x={-34} y={-25} width={68} height={51} fill="#FFFFFF" />
        <path d="M-34-25L0 4 34-25" fill="none" stroke={color} strokeWidth={7} />
      </>}
      <rect x={-50} y={62} width={100} height={26} fill="#080E27" />
      <text x={0} y={81} textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize={18} fill="#FFFFFF">{label}</text>
    </g>
  );
};

export const Shot16 = () => {
  const e = useE();
  const t = e.shotT;
  const press = e.easeIO(e.seg(0.18, 0.82, t));
  const boot = e.easeOut(e.seg(0.72, 1.55, t));
  const sigma = e.back(e.seg(1.22, 2.12, t));
  const list = e.back(e.seg(2.02, 2.82, t));
  const cheer = e.easeOut(e.seg(4.65, 5.12, t));
  const zoom = 1 + e.shotU * 0.025;
  const bob = Math.sin(t * 13.6) * 2;

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <clipPath id="screenClip"><rect x={914} y={300} width={590} height={382} /></clipPath>
        <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation={10} />
        </filter>
      </defs>

      <rect width={1920} height={1080} fill={BG} />
      <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
        <rect x={0} y={0} width={1920} height={820} fill="#1C2E63" />
        <rect x={0} y={820} width={1920} height={260} fill="#101A3B" />
        <rect x={0} y={796} width={1920} height={24} fill="#314577" />

        {/* 黎明窗与像素城市 */}
        <rect x={72} y={108} width={384} height={334} fill="#0B1538" stroke="#52699E" strokeWidth={16} />
        <rect x={92} y={128} width={344} height={294} fill="#5138A8" />
        <rect x={92} y={292} width={344} height={130} fill="#F56D78" />
        <rect x={92} y={350} width={344} height={72} fill="#FFB35C" />
        <rect x={122} y={296} width={48} height={126} fill="#26366B" />
        <rect x={183} y={250} width={64} height={172} fill="#26366B" />
        <rect x={264} y={316} width={43} height={106} fill="#26366B" />
        <rect x={324} y={270} width={74} height={152} fill="#26366B" />
        <rect x={264} y={104} width={13} height={340} fill="#52699E" />
        <rect x={72} y={258} width={384} height={12} fill="#52699E" />
        {[0, 1, 2, 3, 4].map(i => <rect key={i} x={126 + i * 58} y={163 + (i % 2) * 34} width={8} height={8} fill="#FFD93D" />)}

        {/* 后方排队等启动的软件 */}
        <text x={690} y={106} fontFamily="monospace" fontSize={24} fontWeight="900" fill="#8DBBFF">BOOT QUEUE / 等待启动</text>
        <rect x={690} y={125} width={740} height={8} fill="#0B1538" />
        <AppIcon x={735} y={215} color="#44D17A" label="MAP" kind={0} delay={0.05} />
        <AppIcon x={890} y={215} color="#FFB52E" label="TAXI" kind={1} delay={0.22} />
        <AppIcon x={1045} y={215} color="#2878F0" label="DOCS" kind={2} delay={0.39} />
        <AppIcon x={1200} y={215} color="#F15BB5" label="MAIL" kind={3} delay={0.56} />
        <g transform={`translate(1390 211)`} opacity={0.75}>
          <rect x={-42} y={-42} width={84} height={84} fill="none" stroke="#6D80AE" strokeWidth={5} strokeDasharray="10 8" />
          <text x={0} y={12} textAnchor="middle" fontFamily="monospace" fontSize={42} fill="#6D80AE">…</text>
        </g>

        {/* 椅子与 Landis */}
        <rect x={365} y={525} width={245} height={342} fill="#10162D" stroke="#354567" strokeWidth={14} />
        <rect x={392} y={552} width={191} height={205} fill="#243B6B" />
        <Actor
          Character={Character}
          x={585}
          y={922}
          s={1.08}
          pose="sit"
          mood={t > 1.65 && t < 3.2 ? 'surprised' : 'calm'}
          headTurn={13}
          armL={[-38, -76]}
          armR={[-35 - press * 28, -65 + press * 42]}
        />

        {/* 显示器后方的青光 */}
        <rect x={879} y={263} width={656} height={456} fill="#37E6E6" opacity={0.12 + boot * 0.12} filter="url(#softGlow)" />

        {/* 主显示器 */}
        <rect x={875} y={260} width={664} height={466} fill="#080D20" />
        <rect x={891} y={276} width={632} height={426} fill="#354567" />
        <rect x={914} y={300} width={590} height={382} fill={boot > 0.03 ? '#10275A' : '#080D20'} />
        <rect x={904} y={290} width={610} height={8} fill="#65789B" />
        <rect x={1180} y={710} width={52} height={79} fill="#354567" />
        <rect x={1092} y={777} width={230} height={24} fill="#080D20" />

        <g clipPath="url(#screenClip)">
          <g opacity={boot}>
            <rect x={914} y={300} width={590} height={40} fill="#2878F0" />
            <rect x={933} y={314} width={12} height={12} fill="#FFD93D" />
            <text x={958} y={327} fontFamily="monospace" fontWeight="900" fontSize={20} fill="#FFFFFF">SIGMA OS</text>
            <text x={1478} y={327} textAnchor="end" fontFamily="monospace" fontSize={17} fill="#D7F8FF">07:00  READY!</text>
            {[0, 1, 2, 3, 4, 5].map(i => (
              <rect key={i} x={942 + i * 102} y={651 - (i % 2) * 15} width={58} height={5} fill="#1B4385" />
            ))}
            <Sigma x={1080} y={572 + bob} s={0.93} rise={sigma} />
          </g>
          <rect x={914} y={300} width={590} height={382} fill="#37E6E6" opacity={Math.max(0, 0.5 - boot * 0.8)} />
        </g>

        {/* Sigma 从启动页递出的任务清单 */}
        <g transform={`translate(${1190 + (1 - list) * 190} ${385 - (1 - list) * 28}) rotate(${(1 - list) * 8})`} opacity={list}>
          <rect x={10} y={12} width={294} height={270} fill="#080D20" opacity={0.45} />
          <rect x={0} y={0} width={294} height={270} fill="#FFF8DC" stroke="#FFD93D" strokeWidth={8} />
          <rect x={0} y={0} width={294} height={54} fill="#FFD93D" />
          <text x={20} y={38} fontFamily="monospace" fontWeight="900" fontSize={28} fill="#173A6B">TODAY'S QUEST</text>
          {['攻略导航', '打车出发', '全都包在我身上'].map((s, i) => {
            const on = e.seg(2.75 + i * 0.35, 3.05 + i * 0.35, t);
            return <g key={s} transform={`translate(20 ${78 + i * 56})`}>
              <rect x={0} y={0} width={29} height={29} fill="#FFFFFF" stroke="#173A6B" strokeWidth={4} />
              <path d="M5 14L12 22 25 5" fill="none" stroke="#44D17A" strokeWidth={6} opacity={on} />
              <text x={43} y={24} fontFamily="sans-serif" fontWeight="900" fontSize={i === 2 ? 20 : 24} fill="#173A6B">{s}</text>
            </g>;
          })}
          <rect x={105} y={257} width={84} height={21} fill="#FFFFFF" />
          <rect x={117} y={249} width={25} height={25} fill="#FFFFFF" />
          <rect x={153} y={249} width={25} height={25} fill="#FFFFFF" />
        </g>

        {/* 开机第一名的游戏徽标 */}
        <g transform={`translate(1370 741) scale(${0.7 + cheer * 0.3})`} opacity={cheer}>
          <path d="M0-64L18-35 52-45 48-10 78 6 52 29 62 62 27 58 8 87-13 58-48 67-45 31-75 14-49-9-59-42-23-37Z" fill="#FFD93D" stroke="#FFFFFF" strokeWidth={6} />
          <text x={0} y={4} textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize={26} fill="#173A6B">#1</text>
          <text x={0} y={29} textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize={14} fill="#173A6B">BOOT</text>
        </g>

        {/* 木桌前景 */}
        <rect x={245} y={785} width={1395} height={45} fill="#8D512F" />
        <rect x={245} y={785} width={1395} height={12} fill="#D98A4A" />
        <rect x={275} y={830} width={45} height={250} fill="#5C3426" />
        <rect x={1555} y={830} width={45} height={250} fill="#5C3426" />
        <rect x={693} y={751} width={236} height={31} fill="#11182E" stroke="#63769C" strokeWidth={5} />
        {[0, 1, 2, 3, 4, 5, 6, 7].map(i => <rect key={i} x={706 + i * 26} y={760} width={17} height={10} fill={i === 6 ? '#FFD93D' : '#AAB4C8'} />)}
        <rect x={950} y={752} width={39} height={29} fill="#11182E" stroke="#63769C" strokeWidth={4} />
        <path d="M991 768H1040V714H1090" fill="none" stroke="#11182E" strokeWidth={7} />

        {/* 按下开机键 */}
        <g transform="translate(803 742)">
          <rect x={-26} y={-24} width={52} height={23} fill="#263B68" />
          <rect x={-17} y={-20} width={34} height={12} fill={press > 0.7 ? '#FFD93D' : '#44D17A'} />
          <g opacity={Math.max(0, press - boot) * 1.8} stroke="#FFD93D" strokeWidth={6}>
            <path d="M-37-38V-57M0-42V-67M37-38V-57" />
          </g>
        </g>

        {/* 杯子与便签 */}
        <rect x={1454} y={720} width={75} height={65} fill="#F15BB5" />
        <rect x={1527} y={735} width={24} height={34} fill="none" stroke="#F15BB5" strokeWidth={10} />
        <rect x={1465} y={707} width={10} height={14} fill="#AAB4C8" />
        <rect x={1492} y={699} width={10} height={22} fill="#AAB4C8" />
        <rect x={355} y={744} width={86} height={40} fill="#FFD93D" transform="rotate(-5 355 744)" />
        <text x={398} y={771} textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize={18} fill="#173A6B">GO!</text>

        {/* 欢快像素彩纸与经验条 */}
        <g opacity={cheer}>
          {[
            [830, 356, '#FFD93D'], [1570, 355, '#37E6E6'], [1640, 520, '#F15BB5'],
            [758, 486, '#44D17A'], [1535, 620, '#FFD93D'], [845, 640, '#F15BB5'],
          ].map(([x, y, c], i) => (
            <rect key={i} x={Number(x)} y={Number(y) + Math.sin(t * 5 + i) * 14} width={15} height={15} fill={String(c)} transform={`rotate(${i * 17} ${x} ${y})`} />
          ))}
        </g>
        <g transform="translate(83 493)">
          <rect x={0} y={0} width={332} height={58} fill="#0B1538" stroke="#52699E" strokeWidth={5} />
          <text x={17} y={23} fontFamily="monospace" fontSize={17} fontWeight="900" fill="#FFFFFF">DAILY PARTY EXP</text>
          <rect x={17} y={32} width={296} height={12} fill="#26366B" />
          <rect x={17} y={32} width={296 * e.seg(1.4, 5.8, t)} height={12} fill="#FFD93D" />
        </g>
      </g>
    </svg>
  );
};