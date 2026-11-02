import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#21164F';
export const META = {5: {bg: '#21164F'}};

const pxText = {
  fontFamily: 'monospace',
  fontWeight: 900,
  letterSpacing: 2,
} as const;

export const Shot5 = () => {
  const e = useE();
  const t = e.shotT;
  const beat = 60 / 129.82;
  const clickPhase = ((Math.max(0, t - 1.05) % beat) + beat) % beat;
  const click = t > 1.05 ? Math.max(0, 1 - clickPhase / 0.15) : 0;
  const clickIndex = Math.max(0, Math.floor((t - 1.05) / beat));
  const activeButton = clickIndex % 3;

  const cardU = e.easeIO(e.seg(0.38, 1.22, t));
  const cardScale = e.lerp(1.16, 0.19, cardU);
  const cardX = e.lerp(960, 1580, cardU);
  const cardY = e.lerp(540, 156, cardU);

  const jumpU = e.seg(0.72, 1.52, t);
  const jump = t < 1.52 ? Math.sin(jumpU * Math.PI) * 205 : 0;
  const runBounce = t > 1.45 ? Math.abs(Math.sin((t - 1.45) * Math.PI / beat)) * 18 : 0;
  const sigmaX = e.lerp(555, 825, e.easeOut(e.seg(0.75, 2.3, t))) + Math.max(0, t - 2.3) * 34;
  const sigmaY = 805 - jump - runBounce;
  const landisX = 275 + Math.max(0, t - 1.0) * 57;
  const landisY = 794 - Math.abs(Math.sin(Math.max(0, t - 1) * Math.PI / beat)) * 12;

  const beltOffset = -((t * 245) % 160);
  const camera = 1 + e.seg(1.1, 6.5, t) * 0.045;
  const sparkAge = clickPhase;
  const sparkOpacity = t > 1.05 ? Math.max(0, 1 - sparkAge / 0.28) : 0;

  const buttonColors = ['#FF5C7A', '#44D17A', '#42CDF5'];
  const buttonLabels = ['OPEN', 'CLICK', 'DONE'];

  return (
    <svg viewBox="0 0 1920 1080" shapeRendering="crispEdges">
      <rect width="1920" height="1080" fill={BG}/>

      {/* 远景：浏览器系统城 */}
      <g transform={`translate(960 540) scale(${camera}) translate(-960 -540)`}>
        <rect x="0" y="0" width="1920" height="710" fill="#2B1C67"/>
        <path d="M0 410H1920V710H0Z" fill="#34257B"/>
        {[80, 310, 565, 820, 1080, 1360, 1630].map((x, i) => (
          <g key={x} opacity={0.62}>
            <rect x={x} y={205 - (i % 3) * 45} width="190" height="300" fill="#19194B"/>
            <rect x={x + 16} y={224 - (i % 3) * 45} width="158" height="22" fill="#654CB3"/>
            {[0, 1, 2, 3].map((r) => (
              <g key={r}>
                <rect x={x + 22} y={270 + r * 48 - (i % 3) * 45} width="54" height="25" fill={(r + i) % 3 === 0 ? '#FFD93D' : '#2878F0'}/>
                <rect x={x + 91} y={270 + r * 48 - (i % 3) * 45} width="69" height="25" fill="#5138A8"/>
              </g>
            ))}
          </g>
        ))}

        {[45, 180, 440, 690, 930, 1210, 1480, 1770].map((x, i) => (
          <rect key={x} x={x} y={85 + (i % 4) * 44} width={i % 2 ? 10 : 16} height={i % 2 ? 10 : 16} fill={i % 3 ? '#6D5BC4' : '#37E6E6'}/>
        ))}

        {/* 后方浏览器窗口 */}
        <g transform="translate(1040 225)">
          <rect x="10" y="12" width="720" height="340" fill="#141433"/>
          <rect width="720" height="340" fill="#F4F0FF" stroke="#161A2B" strokeWidth="12"/>
          <rect width="720" height="62" fill="#6B52C7"/>
          <rect x="20" y="18" width="22" height="22" fill="#FF5C5C"/>
          <rect x="54" y="18" width="22" height="22" fill="#FFD93D"/>
          <rect x="88" y="18" width="22" height="22" fill="#44D17A"/>
          <rect x="138" y="14" width="548" height="32" fill="#30245F"/>
          <text x="160" y="37" fill="#BFF8FF" fontSize="20" {...pxText}>sigma.local / browser</text>
          <rect x="30" y="92" width="190" height="214" fill="#D8D0F4"/>
          <rect x="52" y="116" width="142" height="22" fill="#2878F0"/>
          <rect x="52" y="158" width="108" height="14" fill="#9C8DD0"/>
          <rect x="52" y="188" width="130" height="14" fill="#9C8DD0"/>
          <rect x="52" y="240" width="74" height="38" fill="#FFD93D"/>
          <text x="250" y="123" fill="#34257B" fontSize="28" {...pxText}>TASK QUEUE</text>
          {[0, 1, 2].map((i) => (
            <g key={i} transform={`translate(250 ${153 + i * 50})`}>
              <rect width="410" height="34" fill="#DDD6F5"/>
              <rect x="10" y="8" width="18" height="18" fill={i < Math.min(3, clickIndex) ? '#44D17A' : '#8C80BA'}/>
              <rect x="48" y="10" width={215 - i * 25} height="12" fill="#8C80BA"/>
            </g>
          ))}
        </g>

        {/* 后景中的 Landis 追赶，咖啡比人更慌 */}
        <g opacity={e.seg(0.92, 1.25, t)}>
          <g transform={`translate(${landisX - 18} ${landisY - 545})`}>
            <rect x="-72" y="-48" width="190" height="38" fill="#161A2B"/>
            <text x="-58" y="-20" fill="#FFFFFF" fontSize="23" {...pxText}>LANDIS</text>
            <path d="M98 40H125V49H134V67H125V76H98Z" fill="#F2C7A5"/>
          </g>
          <Actor
            Character={Character}
            x={landisX}
            y={landisY}
            s={1.06}
            view="side"
            tilt={9}
            mood="tired"
            armL={[-62, -78]}
            armR={[-30, -55]}
            headTurn={8}
          />
          <g transform={`translate(${landisX + 82} ${landisY - 300}) rotate(${Math.sin(t * 12) * 7})`}>
            <rect x="-4" y="-10" width="60" height="58" fill="#161A2B"/>
            <rect width="60" height="58" fill="#F7F4FF"/>
            <rect x="8" y="8" width="44" height="30" fill="#7A432D"/>
            <rect x="60" y="12" width="18" height="30" fill="#F7F4FF"/>
            <rect x="66" y="18" width="12" height="18" fill="#34257B"/>
            <rect x="12" y="-28" width="10" height="14" fill="#E6E1FF"/>
            <rect x="34" y="-42" width="10" height="16" fill="#E6E1FF"/>
          </g>
          {[0, 1, 2].map((i) => (
            <rect
              key={i}
              x={landisX + 139 + i * 17}
              y={landisY - 315 - i * 12 + Math.sin(t * 8 + i) * 8}
              width="10"
              height="10"
              fill="#B87345"
            />
          ))}
        </g>

        {/* 传送带后沿 */}
        <rect x="-50" y="688" width="2020" height="70" fill="#11162E"/>
        <rect x="-50" y="704" width="2020" height="32" fill="#596579"/>
        <rect x="-50" y="736" width="2020" height="226" fill="#252D4B"/>
        <rect x="-50" y="754" width="2020" height="30" fill="#445271"/>

        {/* 传送带上的网页卡片 */}
        {[-1, 0, 1, 2, 3].map((i) => {
          const x = beltOffset + i * 390;
          return (
            <g key={i} transform={`translate(${x} 627)`}>
              <rect x="8" y="10" width="278" height="82" fill="#10142B"/>
              <rect width="278" height="82" fill="#E9E5FA" stroke="#161A2B" strokeWidth="8"/>
              <rect width="278" height="23" fill="#2878F0"/>
              <rect x="14" y="7" width="10" height="10" fill="#FFD93D"/>
              <rect x="20" y="39" width="100" height="12" fill="#8C80BA"/>
              <rect x="20" y="60" width="168" height="10" fill="#B0A6D5"/>
              <rect x="218" y="38" width="40" height="30" fill="#44D17A"/>
            </g>
          );
        })}

        {/* 点击控制台 */}
        <g transform="translate(1000 475)">
          <rect x="12" y="14" width="625" height="215" fill="#12162E"/>
          <rect width="625" height="215" fill="#5138A8" stroke="#161A2B" strokeWidth="10"/>
          <rect x="22" y="22" width="581" height="42" fill="#312363"/>
          <text x="42" y="53" fill="#FFFFFF" fontSize="25" {...pxText}>BROWSER AUTO-PILOT</text>
          {[0, 1, 2].map((i) => {
            const depressed = activeButton === i ? click : 0;
            return (
              <g key={i} transform={`translate(${35 + i * 196} 92)`}>
                <rect x="7" y="12" width="166" height="88" fill="#171A35"/>
                <rect width="166" height="88" fill="#282349"/>
                <rect x="20" y={18 + depressed * 12} width="126" height="52" fill={buttonColors[i]} stroke="#161A2B" strokeWidth="7"/>
                <rect x="29" y={25 + depressed * 12} width="108" height="9" fill="#FFFFFF" opacity="0.45"/>
                <text x="37" y={54 + depressed * 12} fill="#161A2B" fontSize="21" {...pxText}>{buttonLabels[i]}</text>
              </g>
            );
          })}
        </g>

        {/* Sigma：跳上传送带后连续点击 */}
        <g opacity={e.seg(0.63, 0.86, t)}>
          <Actor
            Character={Character}
            x={sigmaX}
            y={sigmaY}
            s={0.76}
            view="side"
            tilt={t < 1.5 ? -8 : 5}
            mood="calm"
            armL={[-24 - click * 20, -50]}
            armR={[-38 - click * 48, -58 + click * 38]}
            headTurn={8}
          />
          <g transform={`translate(${sigmaX - 70} ${sigmaY - 425})`}>
            <rect x="-72" y="-45" width="166" height="35" fill="#161A2B"/>
            <text x="-59" y="-19" fill="#FFD93D" fontSize="21" {...pxText}>SIGMA</text>
          </g>
        </g>

        {/* 白手套点击的像素星芒与经验飘字 */}
        <g opacity={sparkOpacity} transform={`translate(${sigmaX + 137} ${sigmaY - 247})`}>
          <rect x="-8" y="-70" width="16" height="42" fill="#FFFFFF"/>
          <rect x="-8" y="30" width="16" height="42" fill="#FFFFFF"/>
          <rect x="-70" y="-8" width="42" height="16" fill="#FFFFFF"/>
          <rect x="30" y="-8" width="42" height="16" fill="#FFFFFF"/>
          <path d="M-48-48H-32V-32H-48ZM32-48H48V-32H32ZM-48 32H-32V48H-48ZM32 32H48V48H32Z" fill="#FFD93D"/>
          <rect x="-18" y="-18" width="36" height="36" fill="#FFD93D"/>
          <text x="45" y="-42" fill="#FFD93D" fontSize="32" {...pxText}>+10 XP</text>
        </g>

        {/* 前景履带，明确速度方向 */}
        <rect x="-50" y="810" width="2020" height="155" fill="#161A2B"/>
        <rect x="-50" y="819" width="2020" height="28" fill="#68758E"/>
        {[-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((i) => (
          <g key={i} transform={`translate(${beltOffset + i * 160} 0)`}>
            <path d="M0 861H112L82 926H-30Z" fill="#303A5B"/>
            <rect x="10" y="873" width="65" height="13" fill="#465371"/>
          </g>
        ))}
        <rect x="-50" y="958" width="2020" height="20" fill="#2878F0"/>
        {[100, 430, 760, 1090, 1420, 1750].map((x) => (
          <g key={x}>
            <rect x={x} y="846" width="42" height="84" fill="#0D1124"/>
            <rect x={x + 10} y="856" width="22" height="64" fill="#596579"/>
          </g>
        ))}

        {/* 前景速度线 */}
        <g opacity={0.65}>
          {[0, 1, 2, 3].map((i) => (
            <rect key={i} x={90 + i * 460 - ((t * 350) % 460)} y={995 + (i % 2) * 30} width="170" height="10" fill={i % 2 ? '#5138A8' : '#2878F0'}/>
          ))}
        </g>
      </g>

      {/* 顶部经验条 */}
      <g transform="translate(480 48)" opacity={e.seg(1.0, 1.35, t)}>
        <rect x="8" y="8" width="900" height="72" fill="#11142C"/>
        <rect width="900" height="72" fill="#F4F0FF" stroke="#161A2B" strokeWidth="8"/>
        <rect x="18" y="18" width="150" height="36" fill="#34257B"/>
        <text x="34" y="45" fill="#FFFFFF" fontSize="25" {...pxText}>LV.02</text>
        <rect x="190" y="20" width="680" height="32" fill="#C5BCE5"/>
        <rect x="190" y="20" width={Math.min(680, 80 + Math.max(0, t - 1) * 142)} height="32" fill="#FFD93D"/>
        <rect x="198" y="26" width={Math.min(650, 55 + Math.max(0, t - 1) * 142)} height="8" fill="#FFF3A6"/>
      </g>

      {/* 开场盖满画面、随后缩成角落徽章的升级牌 */}
      <g transform={`translate(${cardX} ${cardY}) scale(${cardScale})`}>
        <rect x="-742" y="-352" width="1510" height="740" fill="#11142C"/>
        <rect x="-760" y="-370" width="1510" height="740" fill="#5138A8" stroke="#161A2B" strokeWidth="18"/>
        <rect x="-720" y="-330" width="1430" height="660" fill="#2878F0" stroke="#FFD93D" strokeWidth="12"/>
        <path d="M-720-330H710V-250H-720ZM-720 250H710V330H-720Z" fill="#5138A8"/>
        <path d="M-680-290H-600V-270H-680ZM600-290H680V-270H600ZM-680 270H-600V290H-680ZM600 270H680V290H600Z" fill="#FFD93D"/>
        <text x="0" y="-130" textAnchor="middle" fill="#FFFFFF" fontSize="122" {...pxText}>LEVEL UP!</text>
        <text x="0" y="-12" textAnchor="middle" fill="#FFD93D" fontSize="94" {...pxText}>LV.01 → LV.02</text>
        <rect x="-510" y="55" width="1020" height="112" fill="#161A2B"/>
        <text x="0" y="130" textAnchor="middle" fill="#FFFFFF" fontSize="52" {...pxText}>+ BROWSER CONTROL</text>
        <text x="0" y="220" textAnchor="middle" fill="#BFF8FF" fontSize="34" {...pxText}>NEW SKILL: 点 来 点 去</text>
        {[-1, 1].map((side) => (
          <path key={side} transform={`translate(${side * 610} -40) scale(${side} 1)`} d="M0-70H22V-48H44V-26H66V26H44V48H22V70H0V48H-22V26H-44V-26H-22V-48H0Z" fill="#FFD93D"/>
        ))}
      </g>

      {/* 像素暗角框 */}
      <path d="M0 0H1920V18H0ZM0 1062H1920V1080H0ZM0 0H18V1080H0ZM1902 0H1920V1080H1902Z" fill="#11142C"/>
    </svg>
  );
};