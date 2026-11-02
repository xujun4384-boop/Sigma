import React from 'react';
import {Character} from './char-hero';
import {useE} from '../../engine/context';

export const BG = '#172554';
export const META = {10: {bg: '#172554'}};

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const easeOut = (v: number) => 1 - Math.pow(1 - clamp01(v), 3);
const easeIO = (v: number) => {
  const x = clamp01(v);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};

function PixelSigma({run, push, surprised}: {run: number; push: boolean; surprised: boolean}) {
  const step = Math.sin(run * Math.PI * 2);
  const bob = Math.abs(Math.sin(run * Math.PI * 2)) * 7;
  const legA = step * 28;
  const armA = step * 32;

  return (
    <g transform={`translate(0 ${-bob})`}>
      <g transform={`translate(-24 -70) rotate(${legA})`}>
        <rect x="-13" y="0" width="26" height="52" fill="#173A6B" />
        <rect x="-25" y="42" width="48" height="20" fill="#FFFFFF" />
        <rect x="-25" y="56" width="52" height="10" fill="#2878F0" />
      </g>
      <g transform={`translate(25 -70) rotate(${-legA})`}>
        <rect x="-13" y="0" width="26" height="52" fill="#173A6B" />
        <rect x="-20" y="42" width="48" height="20" fill="#FFFFFF" />
        <rect x="-24" y="56" width="52" height="10" fill="#2878F0" />
      </g>

      <rect x="-52" y="-174" width="104" height="112" fill="#2878F0" />
      <rect x="-42" y="-164" width="84" height="18" fill="#4397FF" />
      <rect x="-12" y="-142" width="24" height="36" fill="#173A6B" />
      <rect x="-48" y="-72" width="96" height="22" fill="#161A2B" />

      <g transform={`translate(-48 -154) rotate(${push ? -72 : -armA - 12})`}>
        <rect x="-17" y="0" width="34" height="76" fill="#2878F0" />
        <rect x="-21" y="65" width="42" height="34" fill="#FFFFFF" />
      </g>
      <g transform={`translate(48 -154) rotate(${push ? 72 : armA + 12})`}>
        <rect x="-17" y="0" width="34" height="76" fill="#2878F0" />
        <rect x="-21" y="65" width="42" height="34" fill="#FFFFFF" />
      </g>

      <g transform="translate(0 -238)">
        <polygon
          points="-28,-112 28,-112 28,-88 56,-88 56,-64 112,-64 112,-24 80,-24 80,0 104,0 104,40 80,40 80,72 48,72 48,96 16,96 16,72 -16,72 -16,96 -48,96 -48,72 -80,72 -80,40 -104,40 -104,0 -80,0 -80,-24 -112,-24 -112,-64 -56,-64 -56,-88 -28,-88"
          fill="#FFD93D"
          stroke="#FFF3A3"
          strokeWidth="7"
          strokeLinejoin="miter"
        />
        <rect x="-44" y="-30" width="17" height="25" fill="#161A2B" />
        <rect x="27" y="-30" width="17" height="25" fill="#161A2B" />
        {surprised ? (
          <rect x="-10" y="18" width="20" height="25" fill="#161A2B" />
        ) : (
          <>
            <rect x="-18" y="22" width="36" height="8" fill="#161A2B" />
            <rect x="-26" y="14" width="8" height="8" fill="#161A2B" />
            <rect x="18" y="14" width="8" height="8" fill="#161A2B" />
          </>
        )}
        <rect x="-79" y="-51" width="20" height="12" fill="#FFE979" />
      </g>
    </g>
  );
}

function PixelRocket({flame}: {flame: number}) {
  return (
    <g>
      <rect x="-92" y="-27" width="25" height="54" fill="#37E6E6" />
      <rect x="-112" y="-18" width={26 + flame * 20} height="36" fill="#FF8B3D" />
      <rect x={-137 - flame * 12} y="-10" width={38 + flame * 14} height="20" fill="#FFD43B" />
      <rect x="-72" y="-45" width="118" height="90" fill="#F4F7FF" />
      <rect x="-52" y="-58" width="74" height="13" fill="#C9D5F4" />
      <rect x="-52" y="45" width="74" height="13" fill="#AAB4D0" />
      <polygon points="46,-45 82,-45 82,-28 108,-28 108,28 82,28 82,45 46,45" fill="#FF5C78" />
      <rect x="-56" y="-76" width="46" height="31" fill="#FF5C78" />
      <rect x="-56" y="45" width="46" height="31" fill="#FF5C78" />
      <rect x="-16" y="-27" width="43" height="54" fill="#173A6B" />
      <rect x="-8" y="-19" width="27" height="27" fill="#37E6E6" />
      <rect x="-3" y="-14" width="9" height="9" fill="#FFFFFF" />
      <rect x="-69" y="-12" width="12" height="24" fill="#2878F0" />
    </g>
  );
}

export const Shot10 = () => {
  const e = useE();
  const t = e.shotT;
  const pushU = easeIO(t / 1.25);
  const runU = easeOut((t - 3.25) / 2.15);
  const chasing = t >= 3.25;
  const sigmaX = chasing ? lerp(970, 420, runU) : lerp(755, 970, pushU);
  const sigmaTilt = chasing ? -10 : lerp(0, 11, pushU);
  const cubeU = clamp01(t / 1.25);
  const cubeGone = clamp01((t - 1.12) / 0.38);
  const rocketU = easeOut((t - 1.18) / 0.3);
  const launchU = easeOut((t - 1.35) / 1.55);
  const turnU = easeIO((t - 2.9) / 0.7);
  const chaseU = easeOut((t - 3.55) / 2.1);

  let rocketX = lerp(1100, 1190, launchU);
  let rocketY = lerp(655, 260, launchU);
  if (t > 3.55) {
    rocketX = lerp(1190, sigmaX + 225, chaseU);
    rocketY = lerp(260, 535, chaseU);
  }
  const rocketAngle = lerp(-90, -180, turnU);
  const flame = Math.floor(t * 14) % 2;
  const scoreU = easeOut((t - 3.75) / 0.55);
  const scoreY = lerp(610, 326, scoreU);
  const flash = 1 - clamp01(Math.abs(t - 1.3) / 0.28);

  return (
    <svg viewBox="0 0 1920 1080" width="1920" height="1080" shapeRendering="crispEdges">
      <defs>
        <linearGradient id="s10sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#10163F" />
          <stop offset="0.62" stopColor="#26347B" />
          <stop offset="1" stopColor="#5138A8" />
        </linearGradient>
        <filter id="s10glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="13" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <rect width="1920" height="1080" fill="url(#s10sky)" />
      <rect y="710" width="1920" height="370" fill="#111936" />
      <rect y="710" width="1920" height="12" fill="#5965D8" />

      {Array.from({length: 20}, (_, i) => (
        <g key={i} opacity={0.22}>
          <rect x={i * 104 - 30} y="760" width="52" height="52" fill={i % 2 ? '#2878F0' : '#5138A8'} />
          <rect x={i * 104 + 22} y="812" width="52" height="52" fill={i % 2 ? '#5138A8' : '#2878F0'} />
        </g>
      ))}
      {Array.from({length: 9}, (_, i) => (
        <rect key={i} x={i * 240} y="930" width="150" height="12" fill="#273768" />
      ))}

      <g opacity="0.35" fill="#37E6E6">
        <rect x="88" y="180" width="330" height="14" />
        <rect x="88" y="215" width="230" height="12" />
        <rect x="120" y="250" width="270" height="12" />
        <rect x="1470" y="170" width="280" height="14" />
        <rect x="1540" y="208" width="210" height="12" />
        <rect x="1490" y="246" width="185" height="12" />
      </g>
      <g fill="#FFD43B">
        <rect x="460" y="130" width="18" height="18" />
        <rect x="495" y="165" width="10" height="10" />
        <rect x="1350" y="105" width="16" height="16" />
        <rect x="1810" y="320" width="14" height="14" />
      </g>

      <g transform="translate(76 64)">
        <rect width="570" height="76" fill="#0B102D" stroke="#5965D8" strokeWidth="6" />
        <rect x="18" y="18" width="16" height="40" fill="#37E6E6" />
        <text x="54" y="50" fill="#FFFFFF" fontSize="31" fontWeight="900" fontFamily="monospace">CODE FOUNTAIN</text>
        <rect x="405" y="17" width="140" height="42" fill="#FFD43B" />
        <text x="425" y="48" fill="#172554" fontSize="27" fontWeight="900" fontFamily="monospace">LV.10</text>
      </g>

      <g opacity="0.5" filter="url(#s10glow)">
        <rect x="1058" y="335" width="28" height="355" fill="#37E6E6" />
        <rect x="1100" y="280" width="42" height="410" fill="#2878F0" />
        <rect x="1155" y="390" width="24" height="300" fill="#37E6E6" />
      </g>
      <g>
        <rect x="1048" y="350" width="20" height="340" fill="#37E6E6" />
        <rect x="1095" y="300" width="28" height="390" fill="#65FFFF" />
        <rect x="1133" y="370" width="18" height="320" fill="#2878F0" />
        <rect x="1170" y="420" width="14" height="270" fill="#37E6E6" />
      </g>

      {Array.from({length: 18}, (_, i) => {
        const p = (t * (0.52 + (i % 4) * 0.1) + i * 0.173) % 1;
        const x = 1015 + (i * 47) % 190;
        const y = 690 - p * (270 + (i % 3) * 70);
        const size = 8 + (i % 3) * 5;
        return <rect key={i} x={x} y={y} width={size} height={size} fill={i % 3 === 0 ? '#FFD43B' : '#65FFFF'} opacity={1 - p * 0.65} />;
      })}

      <g transform="translate(1100 715)">
        <rect x="-180" y="0" width="360" height="35" fill="#7183DA" />
        <rect x="-150" y="35" width="300" height="58" fill="#34499B" />
        <rect x="-180" y="0" width="360" height="10" fill="#A7B7FF" />
        <rect x="-118" y="14" width="236" height="18" fill="#10163F" />
        <rect x="-112" y="93" width="224" height="16" fill="#182451" />
        <text x="-86" y="73" fill="#8FFFFD" fontSize="29" fontWeight="900" fontFamily="monospace">{`</>  01`}</text>
      </g>

      {flash > 0 && (
        <g transform="translate(1100 540)" opacity={flash} filter="url(#s10glow)">
          <polygon points="0,-150 28,-42 130,-80 56,0 150,34 38,44 72,145 0,62 -72,145 -38,44 -150,34 -56,0 -130,-80 -28,-42" fill="#FFF59A" />
        </g>
      )}

      <g transform="translate(1590 900) scale(0.96)">
        <Character
          view="front"
          pose="stand"
          armL={[-145 - scoreU * 15, -18]}
          armR={[-145 - scoreU * 15, -18]}
          headTurn={-8}
          mood="surprised"
        />
      </g>

      {scoreU > 0 && (
        <g transform={`translate(1590 ${scoreY}) rotate(${Math.sin(t * 8) * 2})`} opacity={scoreU}>
          <polygon points="-190,-72 -150,-105 -90,-92 0,-125 90,-92 150,-105 190,-72 178,0 195,62 120,84 0,112 -120,84 -195,62 -178,0" fill="#FFD43B" opacity={scoreU * 0.35} />
          <rect x="-166" y="-76" width="332" height="150" fill="#F7FBFF" stroke="#161A2B" strokeWidth="12" />
          <rect x="-148" y="-58" width="296" height="114" fill="#FFF4B5" stroke="#FF8B3D" strokeWidth="6" />
          <text x="0" y="19" textAnchor="middle" fill="#FF4F70" fontSize="75" fontWeight="900" fontFamily="monospace">10/10</text>
          <text x="0" y="51" textAnchor="middle" fill="#173A6B" fontSize="23" fontWeight="900" fontFamily="monospace">PERFECT!</text>
          <rect x="-154" y="74" width="28" height="72" fill="#F2C7A5" />
          <rect x="126" y="74" width="28" height="72" fill="#F2C7A5" />
        </g>
      )}

      {cubeGone < 1 && (
        <g
          transform={`translate(${lerp(900, 1090, cubeU)} ${680 + cubeGone * 80}) rotate(${cubeU * 7}) scale(${1 - cubeGone * 0.45})`}
          opacity={1 - cubeGone}
        >
          <rect x="-73" y="-73" width="146" height="146" fill="#101A42" stroke="#65FFFF" strokeWidth="9" />
          <rect x="-55" y="-52" width="110" height="16" fill="#2878F0" />
          <text x="-52" y="-3" fill="#FFD43B" fontSize="34" fontWeight="900" fontFamily="monospace">{`{ }`}</text>
          <text x="-52" y="37" fill="#65FFFF" fontSize="30" fontWeight="900" fontFamily="monospace">01_</text>
          <rect x="39" y="54" width="18" height="10" fill="#FF5C78" />
        </g>
      )}

      {rocketU > 0 && (
        <g transform={`translate(${rocketX} ${rocketY}) rotate(${rocketAngle}) scale(${rocketU})`}>
          <PixelRocket flame={flame} />
        </g>
      )}

      {chasing && (
        <g opacity={clamp01((t - 3.45) * 3)}>
          {Array.from({length: 5}, (_, i) => {
            const p = (t * 1.8 + i * 0.2) % 1;
            return <rect key={i} x={sigmaX + 80 + i * 42 + p * 55} y={756 + (i % 2) * 24} width={38 - i * 4} height="10" fill="#8FFFFD" opacity={1 - p} />;
          })}
          <g transform={`translate(${sigmaX + 15} 390)`}>
            <rect x="-54" y="-48" width="108" height="70" fill="#FFFFFF" stroke="#161A2B" strokeWidth="7" />
            <polygon points="-15,22 5,52 20,22" fill="#FFFFFF" stroke="#161A2B" strokeWidth="7" />
            <text x="0" y="5" textAnchor="middle" fill="#FF4F70" fontSize="53" fontWeight="900" fontFamily="monospace">!</text>
          </g>
        </g>
      )}

      <g transform={`translate(${sigmaX} 813) rotate(${sigmaTilt}) scale(0.83)`}>
        <PixelSigma run={t * (chasing ? 3.8 : 1.5)} push={!chasing && t < 1.35} surprised={chasing || (t > 1.15 && t < 2.4)} />
      </g>

      <g opacity="0.8">
        <rect x="0" y="1032" width="1920" height="48" fill="#090E25" />
        {Array.from({length: 24}, (_, i) => (
          <rect key={i} x={i * 86} y={1004 + (i % 3) * 9} width="52" height="28" fill={i % 4 === 0 ? '#2878F0' : '#202E5B'} />
        ))}
      </g>

      {t > 3.8 && (
        <g transform={`translate(1320 ${160 - Math.sin(t * 5) * 8})`} opacity={clamp01((t - 3.8) * 3)}>
          <text x="0" y="0" fill="#FFD43B" stroke="#172554" strokeWidth="8" paintOrder="stroke" fontSize="50" fontWeight="900" fontFamily="monospace">FULL MARKS!</text>
        </g>
      )}
    </svg>
  );
};