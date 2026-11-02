import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Plan, Timeline, TimelineLine} from '../types';
import {FONT, KAI, BRUSH, measure} from './measure';
import {back, clamp01, lerp, noise1, seg, spring} from './math';
import {DARK_PALETTE, hexA} from './theme';
import {pickLyricCfg} from './lyricStyle';

const ANTICIPATE = 2 / 30;

type Parts = {
  chars: string[];
  n: number;
  gap: number;
  total: number;
  a: number;
  fade: number;
  sca: number;
  kara: boolean;
};

const partsOf = (line: TimelineLine, t: number, size: number): Parts => {
  const chars = Array.from(line.text);
  const n = chars.length;
  const gap = Math.round(size * 0.1);
  let total = 0;
  for (const c of chars) total += measure(c, size, 900);
  total += gap * Math.max(0, n - 1);
  return {
    chars,
    n,
    gap,
    total,
    a: seg(line.start, line.start + 0.2, t + ANTICIPATE),
    fade: 1 - seg(line.end - 0.26, line.end, t),
    sca: 0.9 + 0.1 * back(seg(line.start, line.start + 0.34, t + ANTICIPATE)),
    kara: Array.isArray(line.chars) && line.chars.length === n,
  };
};

const charTime = (line: TimelineLine, i: number, n: number, kara: boolean) =>
  kara && line.chars ? line.chars[i][1] : lerp(line.start, line.end, i / Math.max(1, n));

const charState = (line: TimelineLine, t: number, i: number, n: number, kara: boolean,
                   whole = false) => {
  // 整句呈现：所有字视为已出现，靠外层的 a/fade 整体淡入淡出
  if (whole) return {on: true, age: 99, pop: 0};
  const ct = charTime(line, i, n, kara);
  const age = t + ANTICIPATE - ct;
  const on = age >= 0;
  return {on, age, pop: on ? Math.exp(-age * 4) : 0};
};

const shadowStyle = (dark: boolean, blur = 4, dy = 4) => ({
  filter: `drop-shadow(0px ${dy}px ${Math.max(1, blur)}px ${dark ? 'rgba(8,12,24,0.55)' : 'rgba(207,198,180,0.75)'})`,
});

const Glyph: React.FC<{
  ch: string;
  x: number;
  y: number;
  size: number;
  fill: string;
  opacity: number;
  scale?: number;
  weight?: number;
  font?: string;
  dark?: boolean;
  blur?: number;
}> = ({ch, x, y, size, fill, opacity, scale = 1, weight = 900, font = FONT, dark = true, blur = 3}) => (
  <g transform={`translate(${x} ${y}) scale(${scale})`} opacity={opacity}>
    <text
      x={0}
      y={0}
      textAnchor="middle"
      dominantBaseline="central"
      fontFamily={font}
      fontWeight={weight}
      fontSize={size}
      fill={fill}
      style={shadowStyle(dark, blur)}
    >
      {ch}
    </text>
  </g>
);

/** 歌词层：七种版式，整片只用一种，由 plan.lyricStyle 指定 */
export const LyricLayer: React.FC<{timeline: Timeline; plan: Plan; width: number; height: number; dark?: boolean}> = ({
  timeline,
  plan,
  width,
  height,
  dark: darkProp,
}) => {
  const frame = useCurrentFrame();
  const fps = useVideoConfig().fps;
  const t = frame / fps;
  const P = {
    ...DARK_PALETTE,
    ...(plan.palette?.base ? {night: plan.palette.base} : {}),
    ...(plan.palette?.accent ? {gold: plan.palette.accent} : {}),
  };
  const dark = darkProp ?? plan.palette?.mode !== 'light';

  // 当前句：与引擎同口径（提前 2 帧，尾韵留 0.45s）
  const lines = timeline.lines || [];
  let li = -1;
  const anticipate = 2 / fps;
  for (let k = 0; k < lines.length; k++) {
    if (t + anticipate >= lines[k].start) li = k;
    else break;
  }
  const line = li >= 0 && t <= lines[li].end + 0.45 ? lines[li] : null;
  // 版式按段落变化：副歌/主歌/桥段可以各不相同，缺省段落回落到全局 lyricStyle
  const {style, karaoke} = pickLyricCfg(plan, line?.section);
  // whole = 整句一起出现（不做 KTV 逐字）；语速快的歌/段落用这个
  const whole = !karaoke;

  const s = width / 1280;
  const want = plan.lyricSize || 84;
  const nc = line ? Array.from(line.text).length : 1;
  const size = Math.min(want, Math.floor((1280 - 180) / Math.max(1, nc)));
  const lit = P.gold;
  const base = dark ? P.paper : P.ink;

  const body = (() => {
    if (!line) return null;
    const K = partsOf(line, t, size);
    const {chars, n, gap, total, a, fade, sca, kara} = K;

    if (style === 'band') {
      let x = (1280 - total) / 2;
      let x0 = x;
      let lastLit: number | null = null;
      const y = 150;
      const nodes = [];
      for (let i = 0; i < n; i++) {
        const w = measure(chars[i], size, 900);
        const st = charState(line, t, i, n, kara, whole);
        const s2 = sca * (1 + 0.12 * st.pop);
        nodes.push(
          <Glyph key={i} ch={chars[i]} x={x + w / 2} y={y} size={size} fill={!whole && st.on ? lit : base} opacity={a * fade} scale={s2} dark={dark} blur={!whole && st.on ? 5 * st.pop + 3 : 1} />
        );
        if (!whole && st.on) lastLit = x + w;
        x += w + gap;
      }
      return (
        <g>
          {nodes}
          {!whole && kara && lastLit !== null ? (
            <rect x={x0} y={y + size * 0.72} width={Math.max(0, lastLit - x0)} height={5} fill={lit} opacity={0.72 * fade} rx={3} />
          ) : null}
        </g>
      );
    }

    if (style === 'shrink') {
      let x = (1280 - total) / 2;
      const y = 150;
      const nodes = [];
      for (let i = 0; i < n; i++) {
        const w = measure(chars[i], size, 900);
        const st = charState(line, t, i, n, kara, whole);
        if (!st.on) {
          x += w + gap;
          continue;
        }
        const sp = spring(st.age, {damping: 15, stiffness: 380, mass: 1});
        const enter = clamp01(sp);
        const scale = 1 + 0.42 * (1 - sp);
        const nx = noise1(t * 1.7 + i * 13) * 0.6;
        const ny = noise1(t * 2.1 + i * 7 + 100) * 0.5;
        nodes.push(
          <Glyph key={i} ch={chars[i]} x={x + w / 2 + nx} y={y + ny} size={size} fill={lit} opacity={a * fade * enter} scale={scale} dark={dark} blur={4 * st.pop + 2} />
        );
        x += w + gap;
      }
      return <g>{nodes}</g>;
    }

    if (style === 'bounce') {
      let x = (1280 - total) / 2;
      const x0 = x;
      const y = 150;
      let lastLit: number | null = null;
      const nodes = [];
      for (let i = 0; i < n; i++) {
        const w = measure(chars[i], size, 900);
        const st = charState(line, t, i, n, kara, whole);
        if (!st.on) {
          x += w + gap;
          continue;
        }
        const k = Math.exp(-st.age * 5.5);
        nodes.push(
          <Glyph key={i} ch={chars[i]} x={x + w / 2} y={y - 10 * k} size={size} fill={lit} opacity={a * fade * (1 - k)} scale={sca} dark={dark} blur={4 * st.pop + 2} />
        );
        lastLit = x + w;
        x += w + gap;
      }
      return (
        <g>
          {nodes}
          {!whole && kara && lastLit !== null ? <rect x={x0} y={y + size * 0.72} width={Math.max(0, lastLit - x0)} height={4} fill={lit} opacity={0.66 * fade} rx={2} /> : null}
        </g>
      );
    }

    if (style === 'bottom') {
      let x = (1280 - total) / 2;
      const x0 = x;
      const y = 720 - 92;
      let lastLit: number | null = null;
      const nodes = [];
      for (let i = 0; i < n; i++) {
        const w = measure(chars[i], size, 900);
        const st = charState(line, t, i, n, kara, whole);
        if (!st.on) {
          x += w + gap;
          continue;
        }
        const k = Math.exp(-st.age * 7);
        nodes.push(
          <Glyph key={i} ch={chars[i]} x={x + w / 2} y={y} size={size} fill={lit} opacity={a * fade * (1 - k)} scale={sca * (1 + 0.3 * k)} dark={dark} blur={4 * st.pop + 2} />
        );
        lastLit = x + w;
        x += w + gap;
      }
      return (
        <g>
          {nodes}
          {!whole && kara && lastLit !== null ? <rect x={x0} y={y + size * 0.72} width={Math.max(0, lastLit - x0)} height={5} fill={lit} opacity={0.7 * fade} rx={3} /> : null}
        </g>
      );
    }

    if (style === 'vertical') {
      const rows = chars.map((c, i) => ({c, i})).filter((r) => r.c !== ' ' && r.c !== '　' && r.c !== '\t');
      const rn = rows.length;
      if (!rn) return null;
      const vsize = Math.min(size * 0.74, (720 * 0.62) / rn / 1.24);
      const lh = vsize * 1.24;
      const x = 1280 - 96;
      const y0 = Math.max(126, (720 - rn * lh) / 2 - 30);
      let lastY: number | null = null;
      const nodes = [];
      for (let r = 0; r < rn; r++) {
        const st = charState(line, t, rows[r].i, n, kara, whole);
        if (!st.on) continue;
        const k = Math.exp(-st.age * 7);
        nodes.push(
          <Glyph key={r} ch={rows[r].c} x={x} y={y0 + r * lh + lh / 2} size={vsize} fill={lit} opacity={a * fade * (1 - k)} scale={1 + 0.24 * k} weight={700} font={KAI} dark={dark} blur={3} />
        );
        lastY = y0 + r * lh + lh / 2;
      }
      return (
        <g>
          {nodes}
          {!whole && kara && lastY !== null ? <rect x={x - vsize * 0.6} y={y0} width={3} height={Math.max(0, lastY - y0)} fill={lit} opacity={0.62 * fade} rx={2} /> : null}
        </g>
      );
    }

    if (style === 'walk') {
      const y = 150;
      let x = (1280 - total) / 2;
      const centers: number[] = [];
      let k = -1;
      for (let i = 0; i < n; i++) if (charState(line, t, i, n, kara, whole).on) k = i;
      const nodes = [];
      for (let i = 0; i < n; i++) {
        const w = measure(chars[i], size, 900);
        const st = charState(line, t, i, n, kara, whole);
        centers.push(x + w / 2);
        let dy = 0;
        let sq = 0;
        if (!whole && i === k && st.on) {
          sq = Math.exp(-st.age * 6) * Math.cos(st.age * 16);
          dy = 14 * sq;
        }
        nodes.push(
          <g key={i} opacity={a * fade * (whole || st.on ? 1 : 0.34)}>
            <Glyph ch={chars[i]} x={x + w / 2} y={y + dy} size={size} fill={!whole && st.on ? lit : base} opacity={1} scale={1 + sq * 0.006} dark={dark} blur={!whole && st.on ? 3 : 1} />
          </g>
        );
        x += w + gap;
      }
      if (k < 0) return <g>{nodes}</g>;
      const st = charState(line, t, k, n, kara, whole);
      const p = clamp01(st.age / 0.26);
      const fromX = k > 0 ? centers[k - 1] : centers[k];
      const wx = lerp(fromX, centers[k], 1 - Math.pow(1 - p, 3));
      const step = Math.sin(p * Math.PI);
      const ground = y - size * 0.44;
      const R = 16;
      const breath = Math.sin(t * 3.1) * 1.2 * (1 - step);
      const cy = ground - R - step * 14 + breath;
      return (
        <g>
          {nodes}
          <ellipse cx={wx} cy={ground + 5} rx={14 + 5 * step} ry={4.2} fill="#000" opacity={a * fade * (0.34 - 0.18 * step)} />
          <g stroke={lit} strokeWidth={4.2} strokeLinecap="round" opacity={a * fade}>
            <path d={`M ${wx - 5} ${cy + R - 2} L ${wx - 7} ${cy + R + 2 + 6 * step}`} />
            <path d={`M ${wx + 5} ${cy + R - 2} L ${wx + 8} ${cy + R + 2 - 5 * step}`} />
          </g>
          <circle cx={wx} cy={cy} r={R} fill={lit} opacity={a * fade} />
          <circle cx={wx - R * 0.34} cy={cy - R * 0.36} r={R * 0.26} fill="#fff" opacity={0.58 * a * fade} />
          <circle cx={wx - 4} cy={cy - 2} r={2.3} fill="#1A1006" opacity={a * fade} />
          <circle cx={wx + 4} cy={cy - 2} r={2.3} fill="#1A1006" opacity={a * fade} />
        </g>
      );
    }

    // brush：左侧竖两排，右列先写
    const rows = chars.map((c, i) => ({c, i})).filter((r) => r.c !== ' ' && r.c !== '　' && r.c !== '\t');
    const rn = rows.length;
    if (!rn) return null;
    const perCol = Math.ceil(rn / 2);
    const bsize = Math.min(size * 0.82, (720 * 0.6) / perCol / 1.26);
    const lh = bsize * 1.26;
    const xLeft = 96;
    const xRight = xLeft + bsize * 1.62;
    const y0 = Math.max(126, (720 - perCol * lh) / 2 - 30);
    const ink = dark ? '#F4EAD6' : '#1A1410';
    const nodes = [];
    for (let r = 0; r < rn; r++) {
      const st = charState(line, t, rows[r].i, n, kara, whole);
      if (!st.on) continue;
      const k = Math.exp(-st.age * 6);
      const col = Math.floor(r / perCol);
      const cx = col === 0 ? xRight : xLeft;
      const cy = y0 + (r % perCol) * lh + lh / 2;
      nodes.push(
        <g key={r}>
          {k > 0.02 ? <circle cx={cx} cy={cy} r={bsize * (1 + (1 - k))} fill={hexA(ink, 0.16 * k)} filter="url(#lyricInk)" /> : null}
          <Glyph ch={rows[r].c} x={cx} y={cy + bsize * 0.05 * k} size={bsize} fill={ink} opacity={a * fade * (1 - k)} scale={1 + 0.22 * k} weight={400} font={BRUSH} dark={dark} blur={7} />
        </g>
      );
    }
    return <g>{nodes}</g>;
  })();

  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{position: 'absolute', left: 0, top: 0}}>
        <defs>
          <filter id="lyricInk" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>
        <g transform={`scale(${s})`}>{body}</g>
      </svg>
    </AbsoluteFill>
  );
};
