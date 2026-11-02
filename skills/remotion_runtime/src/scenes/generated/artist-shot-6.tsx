import {Character} from './char-hero';
import {Actor} from '../../ui/Actor';
import {useE} from '../../engine/context';

export const BG = '#172554';
export const META = {6: {bg: '#172554'}};

const Mail = ({
  x,
  y,
  r = 0,
  s = 1,
  color = '#FF5C7A',
  stamp = false,
  reply = false,
  opacity = 1,
}: {
  x: number;
  y: number;
  r?: number;
  s?: number;
  color?: string;
  stamp?: boolean;
  reply?: boolean;
  opacity?: number;
}) => (
  <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`} opacity={opacity}>
    <rect x="-66" y="-42" width="132" height="84" fill="#10172F" />
    <rect x="-58" y="-34" width="116" height="68" fill="#FFF6D8" />
    <rect x="-58" y="-34" width="116" height="10" fill={color} />
    <path d="M-56-22 L0 12 L56-22" fill="none" stroke="#D8CEB2" strokeWidth="7" />
    <path d="M-56 30 L-18 2 M56 30 L18 2" fill="none" stroke="#D8CEB2" strokeWidth="6" />
    <rect x="-48" y="20" width="25" height="7" fill={color} />
    {stamp && (
      <g transform="translate(29 8) rotate(-12)">
        <rect x="-25" y="-18" width="50" height="36" fill="none" stroke="#EF3E63" strokeWidth="5" />
        <text x="0" y="6" textAnchor="middle" fontFamily="monospace" fontSize="17" fontWeight="900" fill="#EF3E63">IN</text>
      </g>
    )}
    {reply && (
      <g fill="#2878F0">
        <rect x="18" y="-2" width="28" height="8" />
        <rect x="38" y="-10" width="8" height="24" />
        <rect x="46" y="-6" width="8" height="16" />
      </g>
    )}
  </g>
);

const ExitPipe = ({
  y,
  color,
  label,
  lit,
}: {
  y: number;
  color: string;
  label: string;
  lit: number;
}) => (
  <g>
    <path d={`M1200 ${y} H1708 V${y + 82} H1200`} fill="#26365F" stroke="#0B1430" strokeWidth="12" />
    <rect x="1210" y={y + 12} width="492" height="18" fill="#40547F" />
    <rect x="1500" y={y - 14} width="218" height="110" fill="#111B38" stroke="#080E24" strokeWidth="10" />
    <rect x="1522" y={y + 4} width="174" height="72" fill={lit > 0 ? color : '#080F26'} />
    <rect x="1522" y={y + 4} width="174" height="72" fill="#172554" opacity={lit > 0 ? 0.35 : 0} />
    {[0, 1, 2, 3, 4].map((i) => (
      <rect key={i} x={1534 + i * 32} y={y + 14} width="15" height="52" fill="#091129" opacity="0.48" />
    ))}
    <rect x="1552" y={y - 49} width="126" height="31" fill="#0B1430" />
    <text x="1615" y={y - 27} textAnchor="middle" fontFamily="monospace" fontSize="20" fontWeight="900" fill={color}>{label}</text>
    <rect x="1700" y={y - 25} width="24" height="24" fill={lit > 0 ? '#FFF3A1' : '#45506D'} />
  </g>
);

const Burst = ({x, y, p, color}: {x: number; y: number; p: number; color: string}) => {
  if (p <= 0 || p >= 1) return null;
  const s = 0.45 + p * 1.1;
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} opacity={1 - p} fill={color}>
      <rect x="-8" y="-92" width="16" height="42" />
      <rect x="-8" y="50" width="16" height="42" />
      <rect x="-92" y="-8" width="42" height="16" />
      <rect x="50" y="-8" width="42" height="16" />
      <rect x="-67" y="-67" width="25" height="25" />
      <rect x="43" y="-67" width="25" height="25" />
      <rect x="-67" y="43" width="25" height="25" />
      <rect x="43" y="43" width="25" height="25" />
    </g>
  );
};

const pointOnPath = (p: number, pts: number[][]) => {
  const lengths = pts.slice(1).map((pt, i) => Math.hypot(pt[0] - pts[i][0], pt[1] - pts[i][1]));
  const total = lengths.reduce((a, b) => a + b, 0);
  let d = Math.max(0, Math.min(0.999999, p)) * total;
  for (let i = 0; i < lengths.length; i++) {
    if (d <= lengths[i]) {
      const q = d / lengths[i];
      return {
        x: pts[i][0] + (pts[i + 1][0] - pts[i][0]) * q,
        y: pts[i][1] + (pts[i + 1][1] - pts[i][1]) * q,
        r: Math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0]) * 180 / Math.PI,
      };
    }
    d -= lengths[i];
  }
  return {x: pts[pts.length - 1][0], y: pts[pts.length - 1][1], r: 0};
};

export const Shot6 = () => {
  const e = useE();
  const t = e.shotT;
  const beat = t * 129.82 / 60;
  const bounce = Math.abs(Math.sin(beat * Math.PI)) * 5;
  const push = 1 + 0.025 * e.easeIO(e.shotU);
  const cartIn = 1 - e.easeOut(e.clamp01(t / 0.65));
  const cartX = -170 * cartIn;
  const cartY = Math.sin(beat * Math.PI * 2) * 3;

  const stamp = e.seg(1.02, 1.25, t) * (1 - e.seg(1.39, 1.68, t));
  const fire = e.seg(1.78, 1.9, t) * (1 - e.seg(2.02, 2.25, t));
  const stampBurst = e.clamp01((t - 1.25) / 0.48);
  const fireBurst = e.clamp01((t - 1.88) / 0.42);

  const flights = [
    {start: 2.48, dur: 1.02, pts: [[474, 588], [760, 572], [1110, 350], [1588, 292]], color: '#FF5C7A'},
    {start: 3.34, dur: 0.88, pts: [[968, 532], [1210, 510], [1588, 502]], color: '#37E6E6'},
    {start: 4.18, dur: 1.02, pts: [[555, 616], [890, 642], [1190, 710], [1588, 712]], color: '#FFD43B'},
  ];

  const arrivals = flights.map((f) => e.clamp01((t - f.start - f.dur + 0.12) / 0.18));
  const combo = arrivals.filter((v) => v > 0).length;

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <rect width="1920" height="1080" fill={BG} />

      <g transform={`translate(960 540) scale(${push}) translate(-960 -540)`}>
        {/* 后景：系统城与邮件管网 */}
        <rect x="0" y="0" width="1920" height="190" fill="#101A3B" />
        <rect x="0" y="184" width="1920" height="12" fill="#314577" />
        {Array.from({length: 24}, (_, i) => (
          <g key={i}>
            <rect x={i * 88 - 30} y={226 + (i % 3) * 35} width="56" height={170 + (i % 4) * 38} fill={i % 2 ? '#1D315C' : '#213968'} />
            <rect x={i * 88 - 17} y={251 + (i % 3) * 35} width="13" height="17" fill={i % 4 === 0 ? '#FFD43B' : '#38629A'} />
            <rect x={i * 88 + 7} y={251 + (i % 3) * 35} width="13" height="17" fill={i % 5 === 0 ? '#37E6E6' : '#38629A'} />
          </g>
        ))}

        <path d="M-60 166 H390 V92 H1000 V154 H1350" fill="none" stroke="#0A1330" strokeWidth="68" />
        <path d="M-60 166 H390 V92 H1000 V154 H1350" fill="none" stroke="#344A78" strokeWidth="48" />
        <path d="M-60 153 H390 V79 H1000 V141 H1350" fill="none" stroke="#526B99" strokeWidth="10" />
        {[170, 390, 650, 940, 1190].map((x, i) => (
          <rect key={i} x={x} y={i === 1 || i === 3 ? 62 : 136} width="24" height="70" fill="#172554" />
        ))}

        {/* 游戏 HUD */}
        <g transform="translate(62 54)">
          <rect width="510" height="92" fill="#0A1330" />
          <rect x="8" y="8" width="494" height="76" fill="#223763" />
          <rect x="25" y="23" width="52" height="52" fill="#FFD43B" />
          <path d="M51 28 L60 43 L75 46 L64 58 L67 72 L51 64 L36 72 L38 57 L27 46 L43 43 Z" fill="#FFF3A1" />
          <text x="96" y="43" fontFamily="monospace" fontSize="27" fontWeight="900" fill="#FFFFFF">MAIL RUSH!</text>
          <rect x="96" y="57" width="368" height="12" fill="#101A35" />
          <rect x="96" y="57" width={120 + combo * 82} height="12" fill="#FFD43B" />
          <text x="97" y="82" fontFamily="monospace" fontSize="13" fontWeight="700" fill="#8FEFFF">EXP +300</text>
        </g>

        {combo > 0 && (
          <g transform={`translate(1130 102) scale(${1 + 0.08 * Math.sin(beat * Math.PI)})`}>
            <rect x="-12" y="-8" width="262" height="78" fill="#0B1430" />
            <text x="10" y="42" fontFamily="monospace" fontSize="45" fontWeight="900" fill="#FFD43B">COMBO ×{combo}</text>
          </g>
        )}

        {/* 三个颜色明确的出口 */}
        <ExitPipe y={250} color="#FF5C7A" label="INBOX" lit={arrivals[0]} />
        <ExitPipe y={460} color="#37E6E6" label="REPLY" lit={arrivals[1]} />
        <ExitPipe y={670} color="#FFD43B" label="NOPE!" lit={arrivals[2]} />

        {/* 主输送管 */}
        <path d="M-80 716 H1800" stroke="#09122C" strokeWidth="202" />
        <path d="M-80 716 H1800" stroke="#2A416F" strokeWidth="174" />
        <path d="M-80 655 H1800" stroke="#5273A4" strokeWidth="20" />
        <path d="M-80 780 H1800" stroke="#172747" strokeWidth="24" />
        {Array.from({length: 15}, (_, i) => (
          <g key={i} transform={`translate(${i * 145 - ((t * 115) % 145)} 716)`}>
            <rect x="-35" y="-8" width="70" height="16" fill="#172747" />
            <rect x="-26" y="-5" width="52" height="5" fill="#44618C" />
          </g>
        ))}

        {/* 排队邮件 */}
        {t < 2.48 && (
          <Mail
            x={t < 0.72 ? 285 + e.easeIO(e.clamp01(t / 0.72)) * 189 : 474}
            y={588 - bounce * 0.35}
            color="#FF5C7A"
            stamp={t >= 1.25}
          />
        )}
        {t < 3.34 && (
          <Mail
            x={t < 1.42 ? 440 : 440 + e.easeIO(e.clamp01((t - 1.42) / 0.38)) * 528}
            y={t < 1.42 ? 610 : 610 - e.easeIO(e.clamp01((t - 1.42) / 0.38)) * 78}
            color="#37E6E6"
            reply={t >= 1.86}
          />
        )}
        {t < 4.18 && <Mail x={555} y={616 - bounce * 0.25} color="#FFD43B" reply />}

        {/* 滑车后半、人物 */}
        <g transform={`translate(${cartX} ${cartY})`}>
          <rect x="448" y="664" width="574" height="126" fill="#0A1330" />
          <rect x="466" y="650" width="540" height="102" fill="#3B5D91" />
          <rect x="486" y="664" width="500" height="22" fill="#6F91BC" />
          <rect x="476" y="733" width="520" height="27" fill="#1B3159" />

          <Actor
            Character={Character}
            x={724}
            y={724}
            s={1.12}
            pose="sit"
            view="front"
            mood="calm"
            tilt={-3 * fire + 2 * stamp}
            headTurn={7 * fire - 5 * stamp}
            armL={[-38 - 48 * stamp, -72 + 30 * stamp]}
            armR={[-42 - 48 * fire, -60 + 43 * fire]}
          />

          {/* 左手盖章台 */}
          <g transform={`translate(0 ${stamp * 13})`}>
            <rect x="413" y="536" width="74" height="24" fill="#0B1430" />
            <rect x="427" y="486" width="46" height="55" fill="#EF3E63" />
            <rect x="418" y="478" width="64" height="19" fill="#FF8CA4" />
            <rect x="438" y="442" width="24" height="39" fill="#FFD43B" />
          </g>
          <rect x="383" y="625" width="142" height="34" fill="#142447" />
          <rect x="397" y="616" width="114" height="15" fill="#37E6E6" />

          {/* 右手回信发射器 */}
          <g transform={`translate(${-fire * 14} 0)`}>
            <rect x="941" y="504" width="110" height="82" fill="#0A1330" />
            <rect x="956" y="516" width="96" height="55" fill="#2878F0" />
            <rect x="1035" y="527" width="62" height="34" fill="#37E6E6" />
            <rect x="1089" y="535" width="27" height="18" fill="#D8FFFF" />
            <rect x="959" y="493" width="53" height="18" fill={fire > 0.1 ? '#FFF3A1' : '#FFD43B'} />
          </g>

          <Burst x={454} y={533} p={stampBurst} color="#FFD43B" />
          <Burst x={1095} y={532} p={fireBurst} color="#37E6E6" />

          {/* 滑车前缘，明确人物坐在车里 */}
          <path d="M449 699 H1021 V772 H969 L942 807 H522 L493 772 H449 Z" fill="#101C3A" />
          <path d="M466 707 H1003 V750 H466 Z" fill="#2878F0" />
          <rect x="493" y="721" width="478" height="12" fill="#65A5FF" />
          <rect x="623" y="753" width="208" height="36" fill="#FFD43B" />
          <text x="727" y="779" textAnchor="middle" fontFamily="monospace" fontSize="24" fontWeight="900" fill="#172554">SIGMA-EXPRESS</text>
          <rect x="495" y="790" width="88" height="34" fill="#080F25" />
          <rect x="873" y="790" width="88" height="34" fill="#080F25" />
          <rect x="512" y="797" width="54" height="14" fill="#37E6E6" />
          <rect x="890" y="797" width="54" height="14" fill="#37E6E6" />
        </g>

        {/* 三封邮件沿不同路径钻进出口 */}
        {flights.map((f, i) => {
          const raw = (t - f.start) / f.dur;
          if (raw < 0 || raw > 1.05) return null;
          const p = e.clamp01(raw);
          const q = pointOnPath(e.easeIn(p) * 0.35 + p * 0.65, f.pts);
          const sc = 1 - 0.5 * e.seg(0.78, 1, p);
          return (
            <g key={i}>
              <g opacity={0.45 * (1 - p)}>
                <rect x={q.x - 155} y={q.y - 5} width="72" height="10" fill={f.color} />
                <rect x={q.x - 115} y={q.y + 17} width="45" height="8" fill={f.color} />
              </g>
              <Mail x={q.x} y={q.y} r={q.r * 0.28} s={sc} color={f.color} stamp={i === 0} reply={i > 0} opacity={1 - e.seg(0.94, 1.04, raw)} />
            </g>
          );
        })}

        {/* 出口前景唇边，吞没邮件 */}
        {[250, 460, 670].map((y, i) => (
          <g key={y}>
            <rect x="1572" y={y - 5} width="25" height="92" fill="#080F25" />
            <rect x="1572" y={y + 4} width="9" height="72" fill={['#FF5C7A', '#37E6E6', '#FFD43B'][i]} />
          </g>
        ))}

        {/* 得分弹跳 */}
        {flights.map((f, i) => {
          const p = e.clamp01((t - f.start - f.dur) / 0.75);
          if (p <= 0 || p >= 1) return null;
          return (
            <text
              key={i}
              x="1435"
              y={[230, 440, 650][i] - p * 65}
              fontFamily="monospace"
              fontSize="34"
              fontWeight="900"
              fill={f.color}
              opacity={1 - p}
            >+100</text>
          );
        })}

        {/* 前景速度线与像素尘 */}
        <g fill="#6E8AB6" opacity="0.7">
          <rect x={80 - (t * 180) % 300} y="880" width="170" height="12" />
          <rect x={520 - (t * 220) % 420} y="927" width="230" height="10" />
          <rect x={1240 - (t * 160) % 360} y="863" width="145" height="12" />
        </g>
        <rect x="0" y="1004" width="1920" height="76" fill="#0A1330" />
        <rect x="0" y="1004" width="1920" height="12" fill="#3D5683" />
        {Array.from({length: 20}, (_, i) => (
          <rect key={i} x={i * 104} y="1034" width="58" height="14" fill={i % 3 === 0 ? '#2878F0' : '#1C3158'} />
        ))}
      </g>
    </svg>
  );
};