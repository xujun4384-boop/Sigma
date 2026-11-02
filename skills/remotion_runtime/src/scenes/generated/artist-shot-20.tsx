import React from 'react';
import {useE} from '../../engine/context';
import {Character} from './char-hero';

export const BG = '#172554';
export const META = {20: {bg: '#172554'}};

const ShotCard = ({
  x, y, r, title, level, accent, appear, t, index,
}: {
  x: number; y: number; r: number; title: string; level: string;
  accent: string; appear: number; t: number; index: number;
}) => {
  const p = Math.max(0, Math.min(1, (t - appear) / 0.42));
  const back = 1 + 2.7 * Math.pow(1 - p, 3) * Math.sin(p * Math.PI);
  const s = p <= 0 ? 0 : Math.min(1.08, p * 1.35) * back;
  return (
    <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`} opacity={p}>
      <rect x="-132" y="-92" width="264" height="198" rx="8" fill="#071226" opacity=".35" transform="translate(8 10)"/>
      <rect x="-132" y="-92" width="264" height="198" rx="8" fill="#F4F0DF"/>
      <rect x="-118" y="-78" width="236" height="142" rx="5" fill="#13264B"/>
      <rect x="-118" y="-78" width="236" height="24" rx="5" fill="#253D68"/>
      <circle cx="-101" cy="-66" r="4" fill="#FF6B6B"/>
      <circle cx="-87" cy="-66" r="4" fill="#FFD43B"/>
      <circle cx="-73" cy="-66" r="4" fill="#44D17A"/>
      <text x="101" y="-62" textAnchor="end" fontSize="10" fontFamily="monospace" fill="#9FB6DA">{level}</text>

      {index === 0 && <>
        <rect x="-98" y="-39" width="78" height="82" rx="4" fill="#EAF2FF"/>
        <rect x="-87" y="-27" width="55" height="6" rx="3" fill="#2878F0"/>
        <rect x="-87" y="-12" width="47" height="5" rx="2" fill="#8AA4CF"/>
        <rect x="-87" y="0" width="55" height="5" rx="2" fill="#8AA4CF"/>
        <path d="M-5 28 L24 -10 L46 8 L72 -28 L98 28Z" fill="#2878F0" opacity=".8"/>
        <path d="M-5 28 L24 -10 L46 8 L72 -28" fill="none" stroke="#7DE7F2" strokeWidth="4"/>
      </>}
      {index === 1 && <>
        <rect x="-96" y="-38" width="190" height="17" rx="8" fill="#EAF2FF"/>
        <circle cx="-83" cy="-29" r="5" fill="#44D17A"/>
        <path d="M-87 9 H85 M-87 30 H50" stroke="#7193C9" strokeWidth="7" strokeLinecap="round"/>
        <path d="M56 20 l15 15 27-37" fill="none" stroke="#44D17A" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round"/>
      </>}
      {index === 2 && <>
        <rect x="-98" y="-38" width="194" height="79" rx="7" fill="#244574"/>
        <path d="M-91-30 L-2 12 L88-30" fill="none" stroke="#9FC4FF" strokeWidth="5"/>
        <rect x="28" y="-8" width="57" height="34" rx="5" fill="#FFD43B"/>
        <path d="M35-1 L56 14 L78-1" fill="none" stroke="#8B5E16" strokeWidth="3"/>
      </>}
      {index === 3 && <>
        <path d="M-93 35 C-45-55 2 54 47-31 S92-8 96-34" fill="none" stroke="#344E78" strokeWidth="7" strokeDasharray="8 8"/>
        <path d="M-93 35 C-45-55 2 54 47-31 S92-8 96-34" fill="none" stroke="#FFD43B" strokeWidth="4"/>
        <circle cx="-91" cy="32" r="10" fill="#2878F0" stroke="#FFF" strokeWidth="3"/>
        <path d="M95-48 l7 15 16 1-12 11 4 16-15-8-14 8 3-16-12-11 17-1Z" fill="#FFD43B"/>
      </>}

      <text x="-116" y="88" fontSize="17" fontWeight="800" fontFamily="monospace" fill="#1A2A49">{title}</text>
      <text x="116" y="88" textAnchor="end" fontSize="12" fontFamily="monospace" fill="#64708A">TOGETHER</text>
      <g transform="translate(0 -91)">
        <path d="M0-20 L6-7 20-6 10 4 13 19 0 12-13 19-10 4-20-6-6-7Z" fill="#FFD93D" stroke="#B97B17" strokeWidth="3"/>
        <circle cx="-5" cy="-2" r="2.3" fill="#172554"/>
        <circle cx="5" cy="-2" r="2.3" fill="#172554"/>
      </g>
    </g>
  );
};

export function Shot20() {
  const e = useE();
  const t = e.shotT;
  const c01 = (v: number) => Math.max(0, Math.min(1, v));
  const io = (v: number) => v < .5 ? 2 * v * v : 1 - Math.pow(-2 * v + 2, 2) / 2;
  const out = (v: number) => 1 - Math.pow(1 - v, 3);
  const brochureP = io(c01((t - .25) / 1.25));
  const drawerClose = io(c01((t - 1.25) / .7));
  const drawerY = 52 * (1 - drawerClose);
  const lookP = io(c01((t - 1.8) / .8));
  const flagP = out(c01((t - 4.15) / .65));
  const zoom = 1 + .027 * io(e.shotU);
  const wave = Math.sin(t * 5.2) * 5 * flagP;

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080">
      <defs>
        <linearGradient id="wall20" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#111D43"/>
          <stop offset=".65" stopColor="#213866"/>
          <stop offset="1" stopColor="#172554"/>
        </linearGradient>
        <linearGradient id="dawn20" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#172554"/>
          <stop offset=".6" stopColor="#615083"/>
          <stop offset="1" stopColor="#F3A66F"/>
        </linearGradient>
        <linearGradient id="wood20" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#A86C45"/>
          <stop offset=".48" stopColor="#74462F"/>
          <stop offset="1" stopColor="#4B2C28"/>
        </linearGradient>
        <linearGradient id="cork20" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#C58C57"/>
          <stop offset="1" stopColor="#9A613D"/>
        </linearGradient>
        <linearGradient id="flag20" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#2878F0"/>
          <stop offset="1" stopColor="#44B4FF"/>
        </linearGradient>
        <radialGradient id="lamp20">
          <stop offset="0" stopColor="#FFD43B" stopOpacity=".24"/>
          <stop offset="1" stopColor="#FFD43B" stopOpacity="0"/>
        </radialGradient>
        <filter id="shadow20" x="-30%" y="-30%" width="170%" height="180%">
          <feDropShadow dx="0" dy="12" stdDeviation="12" floodColor="#050A18" floodOpacity=".48"/>
        </filter>
        <filter id="soft20" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="18"/>
        </filter>
        <pattern id="corkgrain20" width="37" height="31" patternUnits="userSpaceOnUse">
          <circle cx="7" cy="8" r="1.7" fill="#70432F" opacity=".3"/>
          <circle cx="26" cy="20" r="1.3" fill="#F0BE7D" opacity=".32"/>
          <path d="M13 25l5-3M29 5l4 2" stroke="#75452F" strokeWidth="1.3" opacity=".25"/>
        </pattern>
      </defs>

      <rect width="1920" height="1080" fill="url(#wall20)"/>
      <ellipse cx="570" cy="455" rx="680" ry="530" fill="url(#lamp20)"/>
      <path d="M0 861 H1920 V1080 H0Z" fill="#0D1733"/>
      <path d="M0 861 H1920" stroke="#32496F" strokeWidth="6"/>

      <g transform={`translate(960 540) scale(${zoom}) translate(-960 -540)`}>
        {/* 后景：黎明与书房轴线 */}
        <g opacity=".82">
          <rect x="82" y="105" width="410" height="365" rx="8" fill="#0A1330" stroke="#415273" strokeWidth="16"/>
          <rect x="101" y="124" width="372" height="327" fill="url(#dawn20)"/>
          <path d="M101 375 L157 332 203 362 272 282 333 346 389 305 473 366 V451 H101Z" fill="#222A4B"/>
          <path d="M286 124 V451 M101 292 H473" stroke="#263858" strokeWidth="12"/>
          <circle cx="392" cy="197" r="25" fill="#FFD99A" opacity=".7" filter="url(#soft20)"/>
        </g>
        <path d="M0 690 C260 652 480 664 777 640" fill="none" stroke="#334C73" strokeWidth="3" opacity=".38"/>

        {/* 软木板：Sigma 的共同升级档案 */}
        <g filter="url(#shadow20)">
          <rect x="978" y="91" width="805" height="630" rx="20" fill="#3A2730"/>
          <rect x="991" y="104" width="779" height="604" rx="12" fill="#D4A06A"/>
          <rect x="1011" y="124" width="739" height="564" rx="4" fill="url(#cork20)"/>
          <rect x="1011" y="124" width="739" height="564" rx="4" fill="url(#corkgrain20)"/>
        </g>
        <text x="1046" y="164" fontFamily="monospace" fontSize="18" fontWeight="700" letterSpacing="4" fill="#5D3B31">OUR PATCH NOTES</text>
        <path d="M1046 180 H1290" stroke="#704735" strokeWidth="3" opacity=".55"/>

        <ShotCard x={1190} y={305} r={-5} title="01 · FIRST DOC" level="v0.1" accent="#2878F0" appear={.85} t={t} index={0}/>
        <ShotCard x={1510} y={303} r={4} title="02 · WEB QUEST" level="v0.4" accent="#44D17A" appear={1.65} t={t} index={1}/>
        <ShotCard x={1195} y={545} r={3} title="03 · MAIL RUN" level="v0.7" accent="#FFD43B" appear={2.45} t={t} index={2}/>
        <ShotCard x={1500} y={548} r={-4} title="04 · NEW MAP" level="v1.0" accent="#FF7BA9" appear={3.25} t={t} index={3}/>

        {/* 升级连线随截图逐段点亮 */}
        <path d="M1190 208 C1370 150 1420 178 1510 208 M1600 380 C1655 445 1600 477 1580 490 M1375 560 C1325 600 1280 588 1320 555" fill="none" stroke="#F8D877" strokeWidth="3" strokeDasharray="7 10" opacity={c01((t - 3.5) / .7)}/>

        {/* 共同闯关的小旗 */}
        <g transform={`translate(1650 168) scale(${flagP})`} opacity={flagP}>
          <path d="M0 0 V383" stroke="#E8EDF5" strokeWidth="10" strokeLinecap="round"/>
          <circle cx="0" cy="-3" r="13" fill="#FFD43B" stroke="#A66A20" strokeWidth="3"/>
          <path d={`M5 18 C65 ${2 + wave} 123 ${39 - wave} 201 19 L184 119 C118 ${136 + wave} 65 ${101 - wave} 5 119Z`} fill="url(#flag20)" stroke="#173A6B" strokeWidth="4"/>
          <path d="M48 42 l8 17 19 2-14 13 4 19-17-9-17 9 4-19-14-13 19-2Z" fill="#FFD93D"/>
          <circle cx="111" cy="66" r="24" fill="#F2C7A5"/>
          <circle cx="102" cy="64" r="10" fill="none" stroke="#20242B" strokeWidth="4"/>
          <circle cx="121" cy="64" r="10" fill="none" stroke="#20242B" strokeWidth="4"/>
          <path d="M112 64h-1M91 85h45" stroke="#20242B" strokeWidth="4" strokeLinecap="round"/>
          <text x="104" y="112" textAnchor="middle" fontFamily="monospace" fontWeight="900" fontSize="15" fill="#FFFFFF" letterSpacing="2">NEXT LEVEL</text>
        </g>

        {/* 桌面后沿与台灯 */}
        <ellipse cx="625" cy="631" rx="430" ry="38" fill="#080E21" opacity=".35"/>
        <path d="M92 598 H932 L900 651 H113Z" fill="url(#wood20)" stroke="#C08759" strokeWidth="4"/>
        <path d="M126 606 H884" stroke="#E0A674" strokeWidth="4" opacity=".48"/>
        <g transform="translate(190 588)">
          <ellipse cx="0" cy="6" rx="69" ry="15" fill="#101B36"/>
          <path d="M0 0 L28-150 92-223" fill="none" stroke="#536787" strokeWidth="15" strokeLinecap="round"/>
          <circle cx="28" cy="-150" r="13" fill="#263A5D"/>
          <path d="M51-250 H151 L128-190 H73Z" fill="#2878F0" stroke="#78A7FF" strokeWidth="4"/>
          <path d="M78-190 H126 L172-35 H23Z" fill="#FFD43B" opacity=".07"/>
        </g>

        {/* Landis：把大厂宣传册收进抽屉 */}
        <g transform="translate(450 938) scale(1.04)">
          <Character
            view="side"
            pose="stand"
            mood="calm"
            tilt={3 * (1 - lookP)}
            headTurn={10 * lookP}
            armL={[-18, -36]}
            armR={[-52 + 34 * brochureP, -24 - 35 * brochureP]}
          />
        </g>

        {/* 抽屉黑洞与滑出的抽屉盒 */}
        <rect x="566" y="648" width="317" height="188" rx="6" fill="#251B24"/>
        <g transform={`translate(0 ${drawerY})`}>
          <path d="M552 657 H892 L864 782 H578Z" fill="#4B302C" stroke="#2E2026" strokeWidth="5"/>
          <path d="M578 677 H866 L849 749 H592Z" fill="#171728"/>
        </g>

        <g transform={`translate(${515 + 160 * brochureP} ${548 + 142 * brochureP}) rotate(${-11 + 18 * brochureP}) scale(${1 - .25 * brochureP})`} opacity={1 - c01((t - 1.48) / .25)}>
          <rect x="-66" y="-88" width="132" height="176" rx="5" fill="#E8ECF2" stroke="#F4C95D" strokeWidth="5" filter="url(#shadow20)"/>
          <rect x="-66" y="-88" width="132" height="44" rx="4" fill="#596579"/>
          <path d="M-35-66 h70" stroke="#37E6E6" strokeWidth="7" strokeLinecap="round"/>
          <rect x="-38" y="-22" width="76" height="49" rx="8" fill="#AAB4C8"/>
          <rect x="-55" y="-13" width="17" height="30" rx="4" fill="#596579"/>
          <rect x="38" y="-13" width="17" height="30" rx="4" fill="#596579"/>
          <path d="M-21 2 H21" stroke="#37E6E6" strokeWidth="7" strokeLinecap="round"/>
          <text x="0" y="54" textAnchor="middle" fontFamily="monospace" fontWeight="800" fontSize="14" fill="#374158">MEGA AGENT</text>
          <text x="0" y="72" textAnchor="middle" fontFamily="monospace" fontSize="9" fill="#7A8495">ONE SIZE FITS ALL</text>
        </g>

        {/* 抽屉面板关合，盖住宣传册 */}
        <g transform={`translate(0 ${drawerY})`}>
          <rect x="548" y="746" width="345" height="105" rx="8" fill="url(#wood20)" stroke="#C08759" strokeWidth="4"/>
          <path d="M571 767 H869" stroke="#D9A074" strokeWidth="3" opacity=".35"/>
          <rect x="676" y="770" width="91" height="15" rx="7" fill="#283149" stroke="#AAB4C8" strokeWidth="3"/>
        </g>
        <rect x="117" y="651" width="419" height="250" fill="url(#wood20)"/>
        <path d="M117 681 H536 M117 890 H536" stroke="#C08759" strokeWidth="4" opacity=".36"/>
        <rect x="137" y="696" width="154" height="174" rx="5" fill="#57382E" stroke="#986344" strokeWidth="3"/>
        <rect x="313" y="696" width="201" height="174" rx="5" fill="#57382E" stroke="#986344" strokeWidth="3"/>

        {/* 收束的小加载条：不是结束，而是下一段开始 */}
        <g transform="translate(1055 758)" opacity={c01((t - 4.45) / .5)}>
          <text x="0" y="0" fontFamily="monospace" fontSize="15" fill="#9FB6DA" letterSpacing="2">STORY_SAVE / CONTINUE</text>
          <rect x="0" y="18" width="570" height="15" rx="7" fill="#0B1530"/>
          <rect x="3" y="21" width={564 * c01((t - 4.45) / 1.65)} height="9" rx="4" fill="#37E6E6"/>
          <path d="M586 13 l7 14 15 2-11 10 3 15-14-7-13 7 2-15-11-10 15-2Z" fill="#FFD93D"/>
        </g>

        {/* 前景压暗，保留 medium shot 的桌面层次 */}
        <path d="M0 930 C340 898 644 946 947 916 C1300 881 1583 931 1920 895 V1080 H0Z" fill="#091229" opacity=".82"/>
        <path d="M0 932 C340 900 644 948 947 918 C1300 883 1583 933 1920 897" fill="none" stroke="#243B6B" strokeWidth="5" opacity=".55"/>
      </g>

      <rect width="1920" height="1080" fill="none" stroke="#080E22" strokeWidth="34" opacity=".38"/>
    </svg>
  );
}