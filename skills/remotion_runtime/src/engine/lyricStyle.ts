import type {LyricStyleCfg, LyricStyleName, Plan, Timeline} from '../types';

/** 段落名常带编号（"Verse 1" / "Pre-Chorus 2"），匹配时先精确、再退到基名。 */
const baseSection = (s: string) => s.replace(/\s*\d+\s*$/, '').trim();

const norm = (v: LyricStyleName | LyricStyleCfg): LyricStyleCfg =>
  typeof v === 'string' ? {style: v} : v;

const lookup = (plan: Plan, section?: string): LyricStyleCfg | undefined => {
  const map = plan.lyricStyles || {};
  const key = (section || '').trim();
  if (key && map[key]) return norm(map[key]);
  const base = baseSection(key);
  if (base && map[base]) return norm(map[base]);
  const lower = base.toLowerCase();
  for (const k of Object.keys(map)) {
    if (lower && baseSection(k).toLowerCase() === lower) return norm(map[k]);
  }
  return undefined;
};

/**
 * 这一句该用哪种歌词呈现。
 *
 * `lyricStyles` 允许按段落指定「位置 + 是否 KTV 逐字」：语速快的歌用
 * `karaoke: false` 整句一起出现，慢歌才用逐字高亮。没配的段落回落到
 * 全局 `lyricStyle` / `lyricKaraoke`。
 */
export const pickLyricCfg = (plan: Plan, section?: string): LyricStyleCfg => {
  const hit = lookup(plan, section);
  return {
    style: hit?.style || plan.lyricStyle || 'band',
    karaoke: hit?.karaoke ?? plan.lyricKaraoke ?? true,
  };
};

/** 只要位置时用这个（蒙版、避让区等）。 */
export const pickLyricStyle = (plan: Plan, section?: string): LyricStyleName =>
  pickLyricCfg(plan, section).style;

/** 当前时刻属于哪一段（供歌词带蒙版等"跟着版式走"的层使用）。 */
export const sectionAt = (timeline: Timeline, t: number): string | undefined => {
  const lines = timeline.lines || [];
  for (let k = lines.length - 1; k >= 0; k--) {
    if (t >= lines[k].start - 0.1 && t <= lines[k].end + 0.45) return lines[k].section;
  }
  return undefined;
};
