export type TemplateId = 'title' | 'kinetic' | 'ui';

export type TemplateProps = {
  text: string;
  kicker?: string;
  sub?: string;
  accent?: string;
};

export type Palette = {
  bg: string;
  fg: string;
  accent: string;
  accent2: string;
  muted: string;
};

export const PALETTES: Record<TemplateId, Palette> = {
  title: {
    bg: '#04060c',
    fg: '#f5f8ff',
    accent: '#7fb0ff',
    accent2: '#8b5bff',
    muted: 'rgba(200,214,240,0.72)',
  },
  kinetic: {
    bg: '#07080d',
    fg: '#ffffff',
    accent: '#5b8cff',
    accent2: '#4be1c4',
    muted: 'rgba(210,222,245,0.72)',
  },
  ui: {
    bg: '#06070d',
    fg: '#f2f5ff',
    accent: '#6b8cff',
    accent2: '#4be1c4',
    muted: 'rgba(190,205,232,0.72)',
  },
};

export const SERIF =
  '"Songti SC","SimSun","Noto Serif SC",Georgia,"Times New Roman",serif';
export const SANS =
  '"Arial Black","Microsoft YaHei","PingFang SC",Impact,sans-serif';
export const UI_SANS =
  '"Microsoft YaHei","PingFang SC","Segoe UI",Arial,sans-serif';

export const clamp = (v: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, v));

export const splitChars = (text: string) => Array.from(text || '');

export const fitFontSize = (
  text: string,
  width: number,
  ratio: number,
  max: number,
) => {
  const n = Math.max(1, splitChars(text).length);
  return Math.min(max, width * ratio, (width * 0.86) / Math.max(4, n));
};

export const pickAccent = (palette: Palette, accent?: string) => {
  const v = (accent || '').trim();
  return /^#[0-9a-f]{6}$/i.test(v) ? v : palette.accent;
};
