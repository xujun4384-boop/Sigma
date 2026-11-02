import type {E, Plan, Timeline, TimelineLine} from '../types';
import {clamp, clamp01, easeIn, easeIO, easeOut, elastic, hash, lerp, seg, wave} from './math';
import {DARK_PALETTE, LYRIC_BOX, hexA, isDark} from './theme';
import {pickLyricStyle} from './lyricStyle';

const ANTICIPATE_FRAMES = 2;

export type NodePick = {
  sceneId: string | null;
  kind: E['kind'];
  cardT: number;
  cardU: number;
  lineIdx: number;
  line: TimelineLine | null;
  shot: E['shot'];
  shotIndex: number;
};

const activeLine = (timeline: Timeline, t: number, anticipate: number) => {
  let idx = -1;
  const lines = timeline.lines || [];
  for (let k = 0; k < lines.length; k++) {
    if (t + anticipate >= lines[k].start) idx = k;
    else break;
  }
  if (idx < 0) return {idx, line: null as TimelineLine | null};
  const line = t <= lines[idx].end + 0.45 ? lines[idx] : null;
  return {idx, line};
};

const barsToTime = (plan: Plan, bars: number, barSec: number, offset: number) => offset + bars * barSec;

/** 按绝对时间选出这一帧该画哪个节点（镜头 → 逐句 → 片头 → 尾奏 → 间奏） */
export const pickNode = (t: number, timeline: Timeline, plan: Plan): {node: NodePick; dark: boolean} => {
  const fps = timeline.fps || 30;
  const anticipate = ANTICIPATE_FRAMES / fps;
  const barSec = (timeline.beat_seconds || 0.5) * 4;
  const offset = timeline.offset_seconds || 0;
  const lines = timeline.lines || [];
  const {idx: lineIdx, line} = activeLine(timeline, t, anticipate);

  const shots = plan.shots || [];
  const shotIdx = shots.findIndex((s) => t >= s.start && t < s.end);
  if (shotIdx >= 0) {
    const shot = shots[shotIdx];
    const span = Math.max(0.2, shot.end - shot.start);
    return {
      node: {
        sceneId: shot.scene,
        kind: 'scene',
        cardT: t - shot.start,
        cardU: clamp01((t - shot.start) / span),
        lineIdx,
        line,
        shot,
        shotIndex: shotIdx,
      },
      dark: shotDark(plan),
    };
  }

  if (line) {
    const scenes = plan.scenes || [];
    return {
      node: {
        sceneId: scenes[Math.min(Math.max(lineIdx, 0), Math.max(0, scenes.length - 1))] ?? null,
        kind: 'scene',
        cardT: t - line.start,
        cardU: clamp01((t - line.start) / Math.max(0.2, line.end - line.start)),
        lineIdx,
        line,
        shot: null,
        shotIndex: -1,
      },
      dark: shotDark(plan),
    };
  }

  const firstStart = lines.length ? lines[0].start : 0;
  const lastEnd = lines.length ? lines[lines.length - 1].end : 0;
  const scenes = plan.scenes || [];
  const nearest = (i: number) => scenes[Math.min(Math.max(i, 0), Math.max(0, scenes.length - 1))] ?? plan.filler ?? null;

  const pickCard = (cards: {bars: number; scene: string}[] | undefined, fromBar: number) => {
    if (!cards || !cards.length) return null;
    let acc = 0;
    for (const c of cards) {
      const n = c.bars || 4;
      if (fromBar < acc + n) return {card: c, start: acc, len: n};
      acc += n;
    }
    const last = cards[cards.length - 1];
    return {card: last, start: acc - (last.bars || 4), len: last.bars || 4};
  };

  if (t + anticipate < firstStart) {
    const fromBar = Math.floor((t - offset) / barSec);
    const p = pickCard(plan.intro, fromBar);
    if (p) {
      const start = barsToTime(plan, p.start, barSec, offset);
      const span = Math.max(0.2, p.len * barSec);
      return {
        node: {sceneId: p.card.scene, kind: 'intro', cardT: t - start, cardU: clamp01((t - start) / span), lineIdx, line, shot: null, shotIndex: -1},
        dark: shotDark(plan),
      };
    }
    // 没有片头卡：借用第一句的画面兜底，避免开场长时间黑屏
    return {
      node: {sceneId: nearest(0), kind: 'intro', cardT: t, cardU: clamp01(t / Math.max(0.2, firstStart)), lineIdx, line, shot: null, shotIndex: -1},
      dark: shotDark(plan),
    };
  }

  if (t > lastEnd) {
    const fromBar = Math.floor((t - lastEnd) / barSec);
    const p = pickCard(plan.outro, fromBar);
    if (p) {
      const start = lastEnd + p.start * barSec;
      const span = Math.max(0.2, p.len * barSec);
      return {
        node: {sceneId: p.card.scene, kind: 'outro', cardT: t - start, cardU: clamp01((t - start) / span), lineIdx, line, shot: null, shotIndex: -1},
        dark: shotDark(plan),
      };
    }
    return {
      node: {sceneId: nearest(scenes.length - 1), kind: 'outro', cardT: t - lastEnd, cardU: clamp01((t - lastEnd) / Math.max(0.2, timeline.duration - lastEnd)), lineIdx, line, shot: null, shotIndex: -1},
      dark: shotDark(plan),
    };
  }

  // 间奏：找最近一句唱完之后的空档
  let prev = -1;
  for (let k = 0; k < lines.length; k++) {
    if (lines[k].start < t) prev = k;
    else break;
  }
  const gapStart = prev >= 0 ? lines[prev].end : 0;
  const gapEnd = prev + 1 < lines.length ? lines[prev + 1].start : timeline.duration;
  const inter = (plan.interludes || []).find((x) => x.afterLine === prev);
  if (inter) {
    const localBar = Math.floor((t - offset) / barSec) - Math.floor((gapStart - offset) / barSec);
    const p = pickCard(inter.cards, Math.max(0, localBar));
    if (p) {
      const start = gapStart + p.start * barSec;
      const span = Math.max(0.2, p.len * barSec);
      return {
        node: {sceneId: p.card.scene, kind: 'interlude', cardT: Math.max(gapStart, start) - gapStart, cardU: clamp01((t - gapStart) / Math.max(0.2, gapEnd - gapStart)), lineIdx, line, shot: null, shotIndex: -1},
        dark: shotDark(plan),
      };
    }
  }

  return {
    node: {
      sceneId: inter ? null : nearest(prev),
      kind: 'gap',
      cardT: t - gapStart,
      cardU: clamp01((t - gapStart) / Math.max(0.2, gapEnd - gapStart)),
      lineIdx,
      line,
      shot: null,
      shotIndex: -1,
    },
    dark: shotDark(plan),
  };
};

const shotDark = (plan: Plan) => plan.palette?.mode !== 'light';

export const buildE = ({
  frame,
  timeline,
  plan,
  fps,
  width,
  height,
  dark: darkOverride,
}: {
  frame: number;
  timeline: Timeline;
  plan: Plan;
  fps: number;
  width: number;
  height: number;
  dark?: boolean;
}): E => {
  const duration = timeline.duration || 1;
  const t = clamp(frame / fps, 0, Math.max(0, duration - 1e-6));
  const beatSec = timeline.beat_seconds || 0.5;
  const offset = timeline.offset_seconds || 0;
  const bp = (t - offset) / beatSec;
  const bi = Math.floor(bp);
  const ph = bp - bi;
  const picked = pickNode(t, timeline, plan);
  const dark = darkOverride ?? picked.dark;

  const palette = {
    ...DARK_PALETTE,
    ...(plan.palette?.base ? {night: plan.palette.base} : {}),
    ...(plan.palette?.accent ? {gold: plan.palette.accent} : {}),
  };

  const node = picked.node;
  // 歌词版式按段落变化；空档（无歌词）回落到全局 lyricStyle
  const lyricStyle = pickLyricStyle(plan, node.line?.section);

  return {
    t,
    dt: 1 / fps,
    W: width,
    H: height,
    i: node.lineIdx,
    n: timeline.lines.length,
    line: node.line ?? {text: '', start: 0, end: 0, chars: []},
    hasLine: !!node.line,
    kind: node.kind,
    cardT: node.cardT,
    cardU: node.cardU,
    u: node.cardU,
    shot: node.shot,
    shotIndex: node.shotIndex,
    isShot: node.shotIndex >= 0,
    shotU: node.cardU,
    shotT: node.cardT,
    shotDur: node.shot ? Math.max(0.2, node.shot.end - node.shot.start) : node.line ? Math.max(0.2, node.line.end - node.line.start) : duration,
    beat: bp,
    beatIdx: bi,
    bar: Math.floor(bp / 4),
    phase: ph,
    bpm: timeline.bpm || 60 / beatSec,
    strong: Math.pow(1 - ph, 4),
    pulse: (k = 6) => Math.exp(-ph * k),
    hit: (every = 1) => bi % every === 0 && ph < 0.5,
    rnd: hash,
    hash,
    clamp,
    clamp01,
    lerp,
    seg,
    easeOut,
    easeIn,
    easeIO,
    back: (x: number) => {
      const c1 = 1.70158;
      const c3 = c1 + 1;
      const v = clamp01(x) - 1;
      return 1 + c3 * v * v * v + c1 * v * v;
    },
    elastic,
    wave,
    P: palette,
    hexA,
    isDark,
    lyricBox: LYRIC_BOX[lyricStyle] || LYRIC_BOX.band,
    lyricRect: (() => {
      const [x0, y0, x1, y1] = LYRIC_BOX[lyricStyle] || LYRIC_BOX.band;
      return {x0, y0, x1, y1, w: x1 - x0, h: y1 - y0};
    })(),
    dark,
  };
};

/** 引擎在 1280×720 虚拟坐标系里排版，这里换算到实际画布 */
export const LAYOUT_W = 1280;
export const LAYOUT_H = 720;
