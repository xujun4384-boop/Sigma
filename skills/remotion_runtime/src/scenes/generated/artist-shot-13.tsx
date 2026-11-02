import {useE} from '../../engine/context';
import {Actor} from '../../ui/Actor';
import {Character} from './char-hero';

export const BG = '#15173A';
export const META = {13: {bg: '#15173A'}};

const RouteIcon = ({x, y, s = 1, opacity = 1}: any) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
    <rect x="-42" y="-34" width="84" height="68" rx="15" fill="#E9F7FF" stroke="#172554" strokeWidth="6"/>
    <path d="M-25 19 C-28 -10, 2 -20, 10 -4 S30 4, 25 -20" fill="none" stroke="#2878F0" strokeWidth="7" strokeLinecap="round" strokeDasharray="8 8"/>
    <path d="M-31 -17 L-19 -24 L-9 -14 L-21 -4 Z" fill="#FF5C8A" stroke="#172554" strokeWidth="4"/>
    <path d="M15 -22 L31 -22 L31 -5 Q23 9 15 -5 Z" fill="#FFD93D" stroke="#172554" strokeWidth="4"/>
    <circle cx="-24" cy="20" r="7" fill="#44D17A" stroke="#172554" strokeWidth="4"/>
  </g>
);

const MailIcon = ({x, y, s = 1, opacity = 1}: any) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
    <rect x="-43" y="-31" width="86" height="62" rx="12" fill="#FFFFFF" stroke="#172554" strokeWidth="6"/>
    <path d="M-37 -22 L0 7 L37 -22" fill="#BEE9FF" stroke="#2878F0" strokeWidth="6" strokeLinejoin="round"/>
    <path d="M-37 23 L-10 0 M37 23 L10 0" fill="none" stroke="#2878F0" strokeWidth="5"/>
    <circle cx="35" cy="-28" r="15" fill="#FF5C8A" stroke="#172554" strokeWidth="5"/>
    <path d="M29 -28 L34 -23 L42 -34" fill="none" stroke="#FFF" strokeWidth="4" strokeLinecap="round"/>
  </g>
);

const MotionIcon = ({x, y, s = 1, opacity = 1}: any) => (
  <g transform={`translate(${x} ${y}) scale(${s})`} opacity={opacity}>
    <rect x="-43" y="-34" width="86" height="68" rx="14" fill="#202B64" stroke="#172554" strokeWidth="6"/>
    <rect x="-31" y="-22" width="25" height="22" rx="5" fill="#44D17A"/>
    <rect x="-1" y="-22" width="25" height="22" rx="5" fill="#FFD93D"/>
    <path d="M-25 18 Q-4 -3 22 15" fill="none" stroke="#69E7FF" strokeWidth="6" strokeLinecap="round"/>
    <path d="M14 7 L28 16 L15 25" fill="none" stroke="#69E7FF" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="29" cy="-25" r="7" fill="#FF5C8A"/>
  </g>
);

const WindowBar = ({x, y, w, title, color}: any) => (
  <g>
    <rect x={x} y={y} width={w} height="48" rx="18" fill="#293368"/>
    <rect x={x} y={y + 25} width={w} height="23" fill="#293368"/>
    <circle cx={x + 25} cy={y + 23} r="7" fill="#FF5C5C"/>
    <circle cx={x + 47} cy={y + 23} r="7" fill="#FFD43B"/>
    <circle cx={x + 69} cy={y + 23} r="7" fill="#44D17A"/>
    <text x={x + 96} y={y + 30} fill="#C8D7FF" fontSize="19" fontWeight="700" fontFamily="monospace">{title}</text>
    <rect x={x + w - 72} y={y + 14} width="45" height="18" rx="9" fill={color} opacity=".8"/>
  </g>
);

export function Shot13() {
  const e = useE();
  const t = e.shotT;
  const beat = e.pulse(1);

  const travel1 = e.seg(1.75, 3.15, t);
  const travel2 = e.seg(3.55, 4.65, t);
  const x = t < 1.75 ? 455 : t < 3.15 ? e.lerp(455, 925, e.easeIO(travel1)) : t < 3.55 ? 925 : t < 4.65 ? e.lerp(925, 1370, e.easeIO(travel2)) : 1370;
  const moving = (t > 1.75 && t < 3.15) || (t > 3.55 && t < 4.65);
  const hop = moving ? Math.abs(Math.sin(t * 11)) * 15 : Math.sin(t * 3.2) * 3;
  const y = 918 - hop;
  const plateX = x + (t < 5.1 ? 78 : 8);
  const plateY = y - 211 + Math.sin(t * 4) * 2;

  const pRoute = e.easeIO(e.seg(1.02, 1.68, t));
  const pMail = e.easeIO(e.seg(2.82, 3.48, t));
  const pMotion = e.easeIO(e.seg(4.12, 4.82, t));
  const eat = e.easeIO(e.seg(5.28, 5.9, t));
  const eaten = t >= 5.9;
  const mouthX = x + (t < 5.1 ? 38 : 0);
  const mouthY = y - 337;

  const routePos = {
    x: e.lerp(e.lerp(330, plateX - 43, pRoute), mouthX, eat),
    y: e.lerp(e.lerp(326, plateY - 39, pRoute) - Math.sin(pRoute * Math.PI) * 105, mouthY, eat),
  };
  const mailPos = {
    x: e.lerp(e.lerp(917, plateX, pMail), mouthX, eat),
    y: e.lerp(e.lerp(330, plateY - 47, pMail) - Math.sin(pMail * Math.PI) * 90, mouthY, eat),
  };
  const motionPos = {
    x: e.lerp(e.lerp(1480, plateX + 43, pMotion), mouthX, eat),
    y: e.lerp(e.lerp(345, plateY - 39, pMotion) - Math.sin(pMotion * Math.PI) * 110, mouthY, eat),
  };

  const camX = -18 * Math.sin(e.shotU * Math.PI);
  const camScale = 1 + 0.018 * e.easeIO(e.shotU);

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="s13bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#111532"/>
          <stop offset=".58" stopColor="#24255A"/>
          <stop offset="1" stopColor="#101D42"/>
        </linearGradient>
        <linearGradient id="s13floor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#263E75"/>
          <stop offset="1" stopColor="#111B3C"/>
        </linearGradient>
        <linearGradient id="s13pipe" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#405281"/>
          <stop offset=".45" stopColor="#9AB8D8"/>
          <stop offset=".65" stopColor="#526A98"/>
          <stop offset="1" stopColor="#29365F"/>
        </linearGradient>
        <radialGradient id="s13plate" cx="50%" cy="30%" r="70%">
          <stop offset="0" stopColor="#FFF5A6"/>
          <stop offset=".55" stopColor="#FFD43B"/>
          <stop offset="1" stopColor="#E79722"/>
        </radialGradient>
        <filter id="s13glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="s13soft" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="24"/>
        </filter>
        <pattern id="s13grid" width="80" height="80" patternUnits="userSpaceOnUse">
          <path d="M80 0 H0 V80" fill="none" stroke="#5474B8" strokeWidth="2" opacity=".16"/>
          <circle cx="0" cy="0" r="3" fill="#69E7FF" opacity=".22"/>
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill="url(#s13bg)"/>
      <ellipse cx="390" cy="250" rx="410" ry="280" fill="#5138A8" opacity=".22" filter="url(#s13soft)"/>
      <ellipse cx="1530" cy="280" rx="390" ry="280" fill="#2878F0" opacity=".18" filter="url(#s13soft)"/>
      <rect width="1920" height="850" fill="url(#s13grid)"/>

      <g opacity=".42" fill="#7488D0">
        <rect x="35" y="100" width="8" height="8"/><rect x="73" y="100" width="8" height="8"/>
        <rect x="1810" y="125" width="8" height="8"/><rect x="1848" y="125" width="8" height="8"/>
        <rect x="675" y="95" width="120" height="8" rx="4"/>
        <rect x="1120" y="118" width="160" height="8" rx="4"/>
      </g>

      <g transform={`translate(${camX} 0) scale(${camScale})`}>
        {/* 后景：三座程序窗口 */}
        <g>
          <rect x="95" y="157" width="455" height="410" rx="28" fill="#080E27" opacity=".45" transform="translate(12 16)"/>
          <rect x="95" y="157" width="455" height="410" rx="28" fill="#D8F2FF" stroke="#5874B8" strokeWidth="7"/>
          <WindowBar x={95} y={157} w={455} title="ROUTES / browser" color="#44D17A"/>
          <rect x="124" y="231" width="397" height="303" rx="17" fill="#B9E6E3"/>
          <path d="M124 420 L195 350 L247 386 L320 277 L379 333 L432 280 L521 361 V534 H124 Z" fill="#74C69D"/>
          <path d="M124 456 Q202 389 270 450 T411 408 T521 431 V534 H124 Z" fill="#3BA7A0"/>
          <path d="M152 484 C219 408 248 484 310 409 S405 379 483 298" fill="none" stroke="#FFF7CF" strokeWidth="13" strokeLinecap="round"/>
          <path d="M152 484 C219 408 248 484 310 409 S405 379 483 298" fill="none" stroke="#2878F0" strokeWidth="5" strokeDasharray="12 15" strokeLinecap="round"/>
          <circle cx="160" cy="480" r="13" fill="#FF5C8A" stroke="#FFF" strokeWidth="5"/>
          <path d="M470 276 L495 276 L495 305 Q482 329 470 305 Z" fill="#FFD93D" stroke="#172554" strokeWidth="5"/>
          <RouteIcon x={330} y={326} s={1.05} opacity={1 - pRoute}/>
          <rect x="130" y="185" width="120" height="4" rx="2" fill="#FFFFFF" opacity=".35"/>
        </g>

        <g>
          <rect x="690" y="155" width="455" height="365" rx="28" fill="#080E27" opacity=".45" transform="translate(12 16)"/>
          <rect x="690" y="155" width="455" height="365" rx="28" fill="#D6E4FF" stroke="#5874B8" strokeWidth="7"/>
          <WindowBar x={690} y={155} w={455} title="MAIL / pipeline" color="#FF5C8A"/>
          <rect x="720" y="232" width="395" height="253" rx="18" fill="#172554"/>
          <path d="M738 420 H1093 M738 388 H1015 M738 356 H1060" stroke="#344A83" strokeWidth="5" strokeDasharray="20 12"/>
          <MailIcon x={917} y={330} s={1.18} opacity={1 - pMail}/>
          <g fill="#69E7FF" opacity=".7">
            <rect x="755" y="265" width="90" height="8" rx="4"/>
            <rect x="755" y="283" width="54" height="8" rx="4"/>
            <rect x="1010" y="437" width="65" height="8" rx="4"/>
          </g>
        </g>

        {/* 邮件管从窗口探入中景 */}
        <path d="M918 492 V590 Q918 632 960 632 H1115" fill="none" stroke="#172554" strokeWidth="58"/>
        <path d="M918 492 V590 Q918 632 960 632 H1115" fill="none" stroke="url(#s13pipe)" strokeWidth="42"/>
        <path d="M918 500 V580 Q918 610 952 610 H1090" fill="none" stroke="#C8E5F5" strokeWidth="5" opacity=".6"/>
        <g fill="#26365F" stroke="#91AACD" strokeWidth="5">
          <rect x="888" y="520" width="60" height="19" rx="6"/>
          <rect x="1000" y="601" width="20" height="62" rx="6"/>
        </g>

        <g>
          <rect x="1265" y="145" width="500" height="430" rx="28" fill="#080E27" opacity=".45" transform="translate(12 16)"/>
          <rect x="1265" y="145" width="500" height="430" rx="28" fill="#15234C" stroke="#5874B8" strokeWidth="7"/>
          <WindowBar x={1265} y={145} w={500} title="MOTION / code fountain" color="#69E7FF"/>
          <rect x="1295" y="220" width="440" height="318" rx="18" fill="#0B1536"/>
          <g fontFamily="monospace" fontSize="22" fontWeight="700">
            <text x="1320" y="263" fill="#7C8FD4">01</text><text x="1360" y="263" fill="#FF8DB5">spring</text><text x="1440" y="263" fill="#D8E6FF">(icon, {'{'}</text>
            <text x="1320" y="300" fill="#7C8FD4">02</text><text x="1390" y="300" fill="#69E7FF">bounce</text><text x="1470" y="300" fill="#FFD93D">: 1.28,</text>
            <text x="1320" y="337" fill="#7C8FD4">03</text><text x="1390" y="337" fill="#69E7FF">joy</text><text x="1440" y="337" fill="#FFD93D">: true</text>
            <text x="1320" y="374" fill="#7C8FD4">04</text><text x="1360" y="374" fill="#D8E6FF">{'}'});</text>
          </g>
          <path d="M1480 475 C1375 424 1390 355 1480 349 C1570 355 1585 424 1480 475 Z" fill="#2878F0" opacity=".25" filter="url(#s13glow)"/>
          <path d="M1480 477 C1408 423 1420 386 1480 361 C1540 386 1552 423 1480 477 Z" fill="none" stroke="#69E7FF" strokeWidth="7" strokeDasharray="12 10"/>
          <MotionIcon x={1480} y={345} s={1.12} opacity={1 - pMotion}/>
          <g fill="#FFD93D">
            <rect x="1350" y={420 - ((t * 75) % 115)} width="10" height="10"/>
            <rect x="1605" y={445 - ((t * 92) % 140)} width="12" height="12"/>
            <rect x="1555" y={400 - ((t * 65) % 100)} width="8" height="8"/>
          </g>
        </g>

        {/* 地面与传送轨迹 */}
        <path d="M0 690 Q480 650 960 688 T1920 675 V1080 H0 Z" fill="url(#s13floor)"/>
        <path d="M0 704 Q480 664 960 702 T1920 689" fill="none" stroke="#5E82C2" strokeWidth="7"/>
        <path d="M80 833 H1840" stroke="#0C1532" strokeWidth="116" strokeLinecap="round"/>
        <path d="M80 818 H1840" stroke="#365484" strokeWidth="82" strokeLinecap="round"/>
        <path d="M90 811 H1830" stroke="#172554" strokeWidth="48" strokeLinecap="round"/>
        <path d="M110 811 H1810" stroke="#69E7FF" strokeWidth="4" strokeDasharray="35 28" opacity=".65"/>
        <g fill="#7B95BD">
          {[170, 390, 610, 830, 1050, 1270, 1490, 1710].map((cx) => <circle key={cx} cx={cx} cy="811" r="23" fill="#263B66" stroke="#7B95BD" strokeWidth="5"/>)}
        </g>

        {/* 收集时的目标提示 */}
        {t < 1.8 && <g opacity={.5 + beat * .4}><rect x="270" y="565" width="170" height="43" rx="20" fill="#44D17A"/><text x="355" y="594" textAnchor="middle" fill="#10244A" fontSize="22" fontWeight="900" fontFamily="sans-serif">路线 +EXP</text></g>}
        {t > 2.5 && t < 3.65 && <g opacity={.5 + beat * .4}><rect x="835" y="548" width="170" height="43" rx="20" fill="#FF5C8A"/><text x="920" y="577" textAnchor="middle" fill="#FFF" fontSize="22" fontWeight="900" fontFamily="sans-serif">沟通 +EXP</text></g>}
        {t > 3.9 && t < 5 && <g opacity={.5 + beat * .4}><rect x="1390" y="570" width="180" height="43" rx="20" fill="#69E7FF"/><text x="1480" y="599" textAnchor="middle" fill="#10244A" fontSize="22" fontWeight="900" fontFamily="sans-serif">动画 +EXP</text></g>}

        {moving && <g stroke="#8FEAFF" strokeWidth="7" strokeLinecap="round" opacity=".55">
          <path d={`M${x - 220} ${y - 300} h95`}/><path d={`M${x - 260} ${y - 250} h120`}/><path d={`M${x - 205} ${y - 200} h70`}/>
        </g>}

        {/* Sigma：中景端盘穿梭 */}
        <Actor
          Character={Character}
          x={x}
          y={y}
          s={.9}
          view={t < 5.1 ? 'side' : 'front'}
          pose="stand"
          tilt={moving ? 7 : t > 5.8 ? -3 : 0}
          mood={t > 5.25 && t < 6.05 ? 'surprised' : 'calm'}
          armL={t > 5.1 ? [-48, -35] : [-58, -24]}
          armR={t > 5.25 && t < 6 ? [-128, -52] : [-64, -22]}
          headTurn={t < 5.1 ? 5 : 0}
        />

        {/* 经验盘 */}
        <g transform={`translate(${plateX} ${plateY}) rotate(${t > 5.1 ? -10 * e.seg(5.1, 5.5, t) : 0})`}>
          <ellipse cx="0" cy="17" rx="105" ry="28" fill="#09132E" opacity=".35"/>
          <path d="M-108 -4 Q-94 45 0 48 Q94 45 108 -4 Z" fill="#D89020" stroke="#172554" strokeWidth="7"/>
          <ellipse rx="110" ry="31" fill="url(#s13plate)" stroke="#172554" strokeWidth="7"/>
          <ellipse rx="88" ry="19" fill="#FFF3A0" opacity=".72"/>
          <rect x="-48" y="25" width="96" height="25" rx="11" fill="#172554"/>
          <text x="0" y="44" textAnchor="middle" fill="#FFD93D" fontSize="18" fontWeight="900" fontFamily="monospace">EXP × 3</text>
        </g>

        {/* 三个技能沿弧线装盘，最后汇成一口 */}
        {!eaten && <>
          <RouteIcon x={routePos.x} y={routePos.y} s={pRoute < 1 ? .82 : .58 * (1 - eat * .45)} opacity={pRoute > 0 ? 1 : 0}/>
          <MailIcon x={mailPos.x} y={mailPos.y} s={pMail < 1 ? .82 : .58 * (1 - eat * .45)} opacity={pMail > 0 ? 1 : 0}/>
          <MotionIcon x={motionPos.x} y={motionPos.y} s={pMotion < 1 ? .82 : .58 * (1 - eat * .45)} opacity={pMotion > 0 ? 1 : 0}/>
        </>}

        {t > 5.28 && t < 6.25 && <g transform={`translate(${mouthX} ${mouthY})`} filter="url(#s13glow)">
          <path d="M0 -24 L7 -7 L25 -7 L11 4 L16 22 L0 12 L-16 22 L-11 4 L-25 -7 L-7 -7 Z" fill="#FFF6A5" opacity={Math.sin(e.seg(5.28, 6.25, t) * Math.PI)}/>
        </g>}

        {t > 5.9 && <g transform={`translate(${x} ${y - 450})`}>
          {[0, 1, 2, 3, 4, 5].map((i) => {
            const a = i * Math.PI / 3 + .2;
            const d = 35 + e.seg(5.9, 6.4, t) * 70;
            return <rect key={i} x={Math.cos(a) * d - 6} y={Math.sin(a) * d - 6} width="12" height="12" fill={i % 2 ? '#69E7FF' : '#FFD93D'} transform={`rotate(${i * 17} ${Math.cos(a) * d} ${Math.sin(a) * d})`}/>;
          })}
          <text x="0" y="-72" textAnchor="middle" fill="#FFD93D" stroke="#172554" strokeWidth="8" paintOrder="stroke" fontSize="42" fontWeight="1000" fontFamily="sans-serif">技能满载！</text>
        </g>}

        {/* 前景漂浮像素，强化穿梭纵深 */}
        <g opacity=".7">
          <rect x={40 + (t * 85) % 210} y="930" width="85" height="24" rx="8" fill="#5138A8"/>
          <rect x={1640 - (t * 70) % 180} y="760" width="115" height="28" rx="9" fill="#2878F0"/>
          <path d="M60 1010 H500" stroke="#69E7FF" strokeWidth="5" opacity=".35"/>
          <path d="M1470 970 H1900" stroke="#FFD93D" strokeWidth="5" opacity=".28"/>
        </g>
      </g>

      <rect width="1920" height="1080" fill="none" stroke="#080D24" strokeWidth="34" opacity=".5"/>
    </svg>
  );
}