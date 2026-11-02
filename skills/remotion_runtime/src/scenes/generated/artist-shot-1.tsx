import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#101936';
export const META = {1: {bg: '#101936'}};

const CODE = [
  'from stars import Spark',
  'sigma = Spark("Sigma")',
  'sigma.learn("docs")',
  'sigma.remember(projects)',
  'while awake:',
  '    sigma.level_up()',
  'print("HELLO, LANDIS!")',
  '# first_light.exe',
];

const KEYS = [
  ['ESC', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['TAB', 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
  ['CAP', 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', 'ENT'],
  ['SHIFT', 'Z', 'X', 'C', 'V', 'B', 'N', 'M', ',', '.', '/'],
];

export const Shot1 = () => {
  const e = useE();
  const t = e.shotT;
  const zoom = 1 + 0.022 * e.easeIO(e.shotU);
  const typingBeat = t * 7.4;
  const keyIndex = Math.floor(typingBeat) % 11;
  const handL = Math.sin(typingBeat * Math.PI) * 3;
  const handR = Math.sin((typingBeat + 0.55) * Math.PI) * 3;
  const screenKick = Math.max(0, Math.sin(typingBeat * Math.PI)) * 1.4;
  const cupRock = Math.sin(t * 17.5) * (2.2 + 1.2 * Math.sin(t * 3.1));
  const activeLine = Math.min(CODE.length - 1, Math.floor(t / 0.62));
  const lineProgress = Math.min(1, (t - activeLine * 0.62) / 0.48);
  const cursorVisible = Math.floor(t * 5) % 2 === 0 || lineProgress < 1;

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#101936"/>
          <stop offset="1" stopColor="#243B6B"/>
        </linearGradient>
        <linearGradient id="dawn" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#172554"/>
          <stop offset="0.65" stopColor="#5138A8"/>
          <stop offset="1" stopColor="#FF8B6A"/>
        </linearGradient>
        <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#081426"/>
          <stop offset="1" stopColor="#102A48"/>
        </linearGradient>
        <filter id="blueGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="12" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="24"/>
        </filter>
        <pattern id="wallPixels" width="48" height="48" patternUnits="userSpaceOnUse">
          <rect width="48" height="48" fill="none"/>
          <rect x="4" y="4" width="3" height="3" fill="#3D4E79" opacity="0.22"/>
        </pattern>
        <clipPath id="windowClip">
          <rect x="88" y="105" width="370" height="350"/>
        </clipPath>
      </defs>

      <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
        {/* 黎明前的书房 */}
        <rect x="-80" y="-80" width="2080" height="1240" fill="url(#wall)"/>
        <rect x="0" y="0" width="1920" height="680" fill="url(#wallPixels)"/>
        <rect x="0" y="628" width="1920" height="24" fill="#0B1228"/>
        <rect x="0" y="652" width="1920" height="428" fill="#11182E"/>

        {/* 窗户与城市 */}
        <rect x="66" y="83" width="414" height="394" fill="#090F24"/>
        <rect x="82" y="99" width="382" height="362" fill="#324674"/>
        <g clipPath="url(#windowClip)">
          <rect x="88" y="105" width="370" height="350" fill="url(#dawn)"/>
          <rect x="88" y="330" width="370" height="125" fill="#192449"/>
          <rect x="105" y="260" width="54" height="195" fill="#17203F"/>
          <rect x="168" y="300" width="70" height="155" fill="#111A37"/>
          <rect x="248" y="225" width="48" height="230" fill="#1B2446"/>
          <rect x="306" y="280" width="82" height="175" fill="#131D3A"/>
          <rect x="398" y="245" width="45" height="210" fill="#192444"/>
          {[0,1,2,3,4,5].map((i) => (
            <g key={i}>
              <rect x={116 + (i % 2) * 22} y={286 + Math.floor(i / 2) * 43} width="9" height="13" fill={i === 2 ? '#FFD43B' : '#334268'}/>
              <rect x={260 + (i % 2) * 20} y={252 + Math.floor(i / 2) * 48} width="8" height="12" fill={i === 4 ? '#FFCA6A' : '#35436B'}/>
              <rect x={320 + (i % 3) * 20} y={306 + Math.floor(i / 3) * 55} width="10" height="12" fill={i === 1 ? '#6DE7FF' : '#2D3C62'}/>
            </g>
          ))}
          <rect x="88" y="401" width="370" height="10" fill="#FF9E78" opacity="0.35"/>
        </g>
        <rect x="264" y="99" width="16" height="362" fill="#0A122B"/>
        <rect x="82" y="274" width="382" height="16" fill="#0A122B"/>
        <rect x="52" y="468" width="442" height="24" fill="#344567"/>
        <rect x="52" y="488" width="442" height="10" fill="#121C37"/>

        {/* 背景书架与便签 */}
        <rect x="1510" y="100" width="310" height="22" fill="#0A1228"/>
        <rect x="1530" y="122" width="18" height="154" fill="#33466F"/>
        <rect x="1790" y="122" width="18" height="154" fill="#33466F"/>
        <rect x="1510" y="270" width="310" height="22" fill="#0A1228"/>
        <rect x="1560" y="153" width="40" height="112" fill="#2878F0"/>
        <rect x="1605" y="171" width="34" height="94" fill="#FF5C5C"/>
        <rect x="1645" y="141" width="46" height="124" fill="#FFD43B"/>
        <rect x="1698" y="181" width="28" height="84" fill="#44D17A"/>
        <rect x="1734" y="160" width="38" height="105" fill="#7456D8"/>
        <rect x="1554" y="166" width="52" height="8" fill="#9AC8FF"/>
        <rect x="1645" y="153" width="46" height="8" fill="#FFF0A0"/>
        <rect x="1120" y="125" width="76" height="68" fill="#FFD43B" transform="rotate(-4 1120 125)"/>
        <rect x="1210" y="151" width="70" height="62" fill="#FF7F9F" transform="rotate(5 1210 151)"/>
        <rect x="1134" y="145" width="46" height="6" fill="#9D6B24"/>
        <rect x="1134" y="160" width="34" height="6" fill="#9D6B24"/>
        <rect x="1222" y="172" width="42" height="6" fill="#9F4568"/>
        <rect x="1222" y="187" width="28" height="6" fill="#9F4568"/>

        {/* 屏幕冷光 */}
        <rect x="280" y="145" width="770" height="520" fill="#2878F0" opacity="0.13" filter="url(#softGlow)"/>

        {/* 主显示器 */}
        <g transform={`translate(${screenKick} 0)`}>
          <rect x="284" y="160" width="752" height="488" fill="#080D1B"/>
          <rect x="300" y="176" width="720" height="440" fill="#263757"/>
          <rect x="316" y="192" width="688" height="408" fill="url(#screen)"/>
          <rect x="316" y="192" width="688" height="42" fill="#173A6B"/>
          <rect x="334" y="207" width="12" height="12" fill="#FF5C5C"/>
          <rect x="356" y="207" width="12" height="12" fill="#FFD43B"/>
          <rect x="378" y="207" width="12" height="12" fill="#44D17A"/>
          <text x="660" y="220" textAnchor="middle" fill="#B9D8FF" fontSize="18" fontFamily="monospace" fontWeight="700">sigma_core.py — PYTHON</text>
          <rect x="316" y="234" width="52" height="366" fill="#0A172B"/>
          {CODE.map((line, i) => {
            const start = i * 0.62;
            const amount = i < activeLine ? 1 : i === activeLine ? Math.max(0, lineProgress) : 0;
            const shown = line.slice(0, Math.ceil(line.length * amount));
            return (
              <g key={line}>
                <text x="338" y={274 + i * 37} textAnchor="middle" fill="#496589" fontSize="17" fontFamily="monospace">{String(i + 1).padStart(2, '0')}</text>
                {i === activeLine && <rect x="369" y={251 + i * 37} width="620" height="31" fill="#173A6B" opacity="0.45"/>}
                <text x="390" y={274 + i * 37} fill={i === 0 ? '#FF8BC7' : i === 6 ? '#FFD93D' : '#A8E6FF'} fontSize="22" fontFamily="monospace">{shown}</text>
              </g>
            );
          })}
          {cursorVisible && (
            <rect
              x={390 + CODE[activeLine].slice(0, Math.ceil(CODE[activeLine].length * Math.max(0, lineProgress))).length * 13.25}
              y={253 + activeLine * 37}
              width="12"
              height="25"
              fill="#FFD43B"
              filter="url(#blueGlow)"
            />
          )}
          <rect x="316" y="568" width="688" height="32" fill="#142C4D"/>
          <rect x="334" y="580" width="10" height="10" fill="#44D17A"/>
          <text x="354" y="590" fill="#79F2B1" fontSize="15" fontFamily="monospace">READY</text>
          <text x="970" y="590" textAnchor="end" fill="#6E91BB" fontSize="14" fontFamily="monospace">UTF-8  LF  Python 3.12</text>
          <rect x="610" y="648" width="100" height="68" fill="#111B31"/>
          <rect x="542" y="704" width="236" height="22" fill="#263757"/>
          <rect x="566" y="726" width="188" height="10" fill="#080D1B"/>
          <rect x="962" y="630" width="24" height="6" fill="#37E6E6"/>
        </g>

        {/* 桌后的人物：深蓝睡衣、圆眼镜由角色组件统一造型 */}
        <Actor
          Character={Character}
          x={1320}
          y={824}
          s={1.18}
          pose="sit"
          mood="calm"
          headTurn={-10}
          tilt={-2}
          armL={[-40 + handL, -80 - handL]}
          armR={[-34 - handR, -75 + handR]}
        />

        {/* 桌面与前缘 */}
        <rect x="190" y="690" width="1530" height="34" fill="#9A5A3A"/>
        <rect x="170" y="716" width="1570" height="34" fill="#633A32"/>
        <rect x="190" y="750" width="1530" height="22" fill="#39283A"/>
        <rect x="248" y="772" width="48" height="308" fill="#39283A"/>
        <rect x="1608" y="772" width="48" height="308" fill="#39283A"/>
        <rect x="190" y="690" width="1530" height="8" fill="#D0834C"/>
        <rect x="220" y="728" width="130" height="8" fill="#7D4938"/>
        <rect x="1450" y="728" width="180" height="8" fill="#7D4938"/>

        {/* 机械键盘 */}
        <g transform="translate(856 746) skewX(-8)">
          <rect x="-18" y="-14" width="532" height="190" fill="#0A1022"/>
          <rect x="0" y="0" width="496" height="158" fill="#263454"/>
          <rect x="8" y="8" width="480" height="140" fill="#141E36"/>
          {KEYS.map((row, r) => row.map((key, c) => {
            const pressed = (c + r * 3) % 11 === keyIndex;
            const x = 16 + c * 42 + (r === 3 ? 5 : 0);
            const y = 16 + r * 31 + (pressed ? 4 : 0);
            return (
              <g key={`${r}-${c}`}>
                <rect x={x} y={y + 4} width="35" height="25" fill="#070C18"/>
                <rect x={x} y={y} width="35" height="23" fill={key === 'ENT' ? '#FFD43B' : pressed ? '#37E6E6' : (c + r) % 4 === 0 ? '#40547A' : '#71819F'}/>
                <text x={x + 17.5} y={y + 16} textAnchor="middle" fill={key === 'ENT' || pressed ? '#12213E' : '#E8F3FF'} fontSize={key.length > 1 ? 8 : 11} fontFamily="monospace" fontWeight="700">{key}</text>
              </g>
            );
          }))}
          <rect x="116" y="140" width="238" height="24" fill="#070C18"/>
          <rect x="116" y={keyIndex === 7 ? 138 : 134} width="238" height="22" fill={keyIndex === 7 ? '#37E6E6' : '#71819F'}/>
          <rect x="434" y="8" width="10" height="6" fill="#44D17A"/>
          <rect x="452" y="8" width="10" height="6" fill="#FFD43B"/>
        </g>

        {/* 被屏幕震动带着摇晃的泡面杯 */}
        <g transform={`rotate(${cupRock} 500 806)`}>
          <rect x="442" y="784" width="116" height="18" fill="#070C18" opacity="0.55"/>
          <rect x="454" y="636" width="94" height="20" fill="#F4F0DB"/>
          <rect x="446" y="650" width="110" height="16" fill="#FFFFFF"/>
          <polygon points="454,666 548,666 536,790 466,790" fill="#F4F0DB"/>
          <polygon points="466,682 538,682 530,774 474,774" fill="#FF5C5C"/>
          <rect x="472" y="702" width="60" height="44" fill="#FFF4D2"/>
          <text x="502" y="722" textAnchor="middle" fill="#D83450" fontSize="14" fontFamily="monospace" fontWeight="900">NOODLE</text>
          <text x="502" y="740" textAnchor="middle" fill="#243B6B" fontSize="12" fontFamily="monospace" fontWeight="900">+EXP</text>
          <rect x="476" y="760" width="48" height="6" fill="#D83450"/>
          <rect x="470" y="618" width="8" height="52" fill="#D69A56" transform="rotate(-19 470 618)"/>
          <rect x="488" y="616" width="8" height="54" fill="#F1B86B" transform="rotate(-19 488 616)"/>
          <g opacity={0.5 + 0.25 * Math.sin(t * 4)}>
            <rect x="474" y={602 - (t * 18 % 20)} width="10" height="22" fill="#B9D8FF"/>
            <rect x="484" y={578 - (t * 18 % 20)} width="10" height="22" fill="#B9D8FF"/>
            <rect x="516" y={594 - ((t * 14 + 8) % 22)} width="10" height="24" fill="#B9D8FF"/>
            <rect x="526" y={568 - ((t * 14 + 8) % 22)} width="10" height="22" fill="#B9D8FF"/>
          </g>
        </g>

        {/* 鼠标、数据线和桌面小游戏状态灯 */}
        <path d="M1360 790 C1440 770 1470 720 1410 680 C1370 650 1390 620 1440 620" fill="none" stroke="#080D1B" strokeWidth="12"/>
        <rect x="1410" y="742" width="102" height="116" rx="34" fill="#111B31"/>
        <rect x="1420" y="750" width="82" height="94" rx="28" fill="#40547A"/>
        <rect x="1456" y="762" width="10" height="28" fill="#37E6E6"/>
        <rect x="1540" y="700" width="142" height="50" fill="#111B31"/>
        <rect x="1552" y="712" width="78" height="10" fill="#253A5C"/>
        <rect x="1552" y="712" width={30 + 40 * e.shotU} height="10" fill="#FFD43B"/>
        <text x="1552" y="740" fill="#7CE7FF" fontSize="12" fontFamily="monospace">COMPILING...</text>
        <rect x="1646" y="712" width="12" height="12" fill={Math.floor(t * 4) % 2 ? '#44D17A' : '#173A6B'}/>

        {/* 前景暗角，强化 medium 景别 */}
        <rect x="0" y="1020" width="1920" height="60" fill="#080D1B"/>
        <rect x="0" y="0" width="24" height="1080" fill="#080D1B" opacity="0.5"/>
        <rect x="1896" y="0" width="24" height="1080" fill="#080D1B" opacity="0.5"/>
      </g>
    </svg>
  );
};