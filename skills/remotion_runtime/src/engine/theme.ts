import type {Palette} from '../types';

export const DARK_PALETTE: Palette = {
  paper: '#F4EFE4',
  ink: '#20242E',
  night: '#141A2E',
  night2: '#1D2540',
  gold: '#E9A63B',
  coral: '#E2583C',
  teal: '#2E8C86',
  blue: '#3C6FD1',
  plum: '#7A4A86',
  green: '#4C8C46',
  dusk: '#E9884A',
  white: '#FFFFFF',
  black: '#000000',
  grey: '#8A8F9C',
};

export const isDark = (hex: string) => {
  const c = hex.replace('#', '');
  const n = parseInt(
    c.length === 3
      ? c
          .split('')
          .map((x) => x + x)
          .join('')
      : c,
    16
  );
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) < 140;
};

export const hexA = (hex: string, a: number) => {
  const c = hex.replace('#', '');
  const full = c.length === 3 ? c.split('').map((x) => x + x).join('') : c;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

/** 歌词占用矩形，1280×720 虚拟坐标系（与 engine/stage.html 的 LYRIC_BOX 一致） */
export const LYRIC_BOX: Record<string, [number, number, number, number]> = {
  band: [0, 96, 1280, 206],
  shrink: [0, 96, 1280, 206],
  bounce: [0, 96, 1280, 206],
  walk: [0, 52, 1280, 206],
  vertical: [1080, 130, 1280, 520],
  bottom: [0, 546, 1280, 664],
  brush: [80, 130, 340, 520],
};

export const SEC_ZH: Record<string, string> = {
  Intro: '前奏',
  Outro: '尾声',
  Interlude: '间奏',
  Bridge: '桥段',
  Chorus: '副歌',
  'Pre-Chorus': '导歌',
  Verse: '主歌',
};

export const secZh = (s: string) => {
  if (!s) return '';
  const m = /^([A-Za-z][A-Za-z-]*)\s*(\d*)$/.exec(s.trim());
  if (!m) return s;
  const base = SEC_ZH[m[1]] || m[1];
  if (!m[2]) return base;
  const n = +m[2];
  return base + ('一二三四五六七八九十'[n - 1] || n);
};
