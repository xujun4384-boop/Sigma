/** 引擎与画面代码之间的契约类型。timeline / plan 都由 lyric_mv pipeline 产出，格式与 stage.html 一致。 */
import type React from 'react';

export type CharHit = [string, number];

export type TimelineLine = {
  idx?: number;
  section?: string;
  text: string;
  start: number;
  end: number;
  beat?: number;
  hit_chars?: number;
  chars?: CharHit[];
};

export type Timeline = {
  song?: string;
  bpm?: number;
  beat_seconds?: number;
  offset_seconds?: number;
  duration: number;
  fps?: number;
  lines: TimelineLine[];
};

export type Shot = {
  id?: string;
  start: number;
  end: number;
  /** registry 里的组件 key */
  scene: string;
};

export type Card = {
  bars: number;
  scene: string;
};

export type LyricStyleName = 'band' | 'shrink' | 'bounce' | 'vertical' | 'bottom' | 'walk' | 'brush';

/** 一个段落的歌词呈现：放哪儿 + 要不要 KTV 逐字。
 * karaoke=false 表示整句一起出现（语速快、逐字来不及读时用）。 */
export type LyricStyleCfg = {style: LyricStyleName; karaoke?: boolean};

export type Plan = {
  title?: string;
  lyricStyle?: LyricStyleName;
  /** 按段落换歌词版式：{"Verse": "bottom", "Chorus": {"style": "bounce", "karaoke": false}} */
  lyricStyles?: Record<string, LyricStyleName | LyricStyleCfg>;
  /** 全局默认是否 KTV 逐字；段落配置可覆盖 */
  lyricKaraoke?: boolean;
  lyricSize?: number;
  plain?: boolean;
  palette?: { base?: string; accent?: string; mode?: string };
  sections?: { name: string; theme?: string; motion?: string }[];
  chrome?: {
    section?: 'en' | 'zh' | 'hide';
    sectionAt?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
    progress?: 'top' | 'bottom' | 'hide';
  };
  /** 叙事型：镜头表；给了就优先走 shots */
  shots?: Shot[];
  /** 逐句画面：长度等于歌词行数 */
  scenes?: string[];
  intro?: Card[];
  interludes?: { afterLine: number; cards: Card[] }[];
  outro?: Card[];
  filler?: string;
};

/** 注册表条目：场景组件 + 底色 */
export type SceneEntry = {
  comp: React.FC;
  bg?: string;
};

export type EngineProps = {
  timeline: Timeline;
  plan: Plan;
  fps?: number;
  width?: number;
  height?: number;
  /** 闸门模式：镜头崩溃不兜底，直接让渲染失败，方便把真实报错回灌给模型 */
  strict?: boolean;
};

export type Palette = {
  paper: string;
  ink: string;
  night: string;
  night2: string;
  gold: string;
  coral: string;
  teal: string;
  blue: string;
  plum: string;
  green: string;
  dusk: string;
  white: string;
  black: string;
  grey: string;
};

/** 画面代码拿到的环境对象：字段与 engine/stage.html 的 e 一一对应 */
export type E = {
  t: number;
  dt: number;
  W: number;
  H: number;
  i: number;
  n: number;
  line: TimelineLine;
  /** 当前是否真的有歌词句（空档/卡片时为 false；此时 e.line 是一个空对象，字段可直接读） */
  hasLine: boolean;
  kind: 'scene' | 'intro' | 'interlude' | 'outro' | 'gap';
  cardT: number;
  cardU: number;
  u: number;
  shot: Shot | null;
  shotIndex: number;
  isShot: boolean;
  shotU: number;
  shotT: number;
  shotDur: number;
  beat: number;
  beatIdx: number;
  bar: number;
  phase: number;
  bpm: number;
  strong: number;
  pulse: (k?: number) => number;
  hit: (every?: number) => boolean;
  rnd: (seed: number | string) => number;
  hash: (seed: number | string) => number;
  clamp: (v: number, a: number, b: number) => number;
  clamp01: (v: number) => number;
  lerp: (a: number, b: number, t: number) => number;
  seg: (a: number, b: number, v: number) => number;
  easeOut: (t: number) => number;
  easeIn: (t: number) => number;
  easeIO: (t: number) => number;
  back: (t: number) => number;
  elastic: (t: number) => number;
  wave: (t: number, freq?: number) => number;
  P: Palette;
  hexA: (hex: string, a: number) => string;
  isDark: (hex: string) => boolean;
  /** 歌词占用矩形 [x0,y0,x1,y1]，1280×720 坐标系；画面主体要避开它 */
  lyricBox: [number, number, number, number];
  /** 同一块区域的对象形式，方便直接用 x0/y0/w/h */
  lyricRect: {x0: number; y0: number; x1: number; y1: number; w: number; h: number};
  dark: boolean;
};
