// 开发用：把 _e2e 的真实逐字时间轴裁成 27.7s 样片，生成 LyricMV 的 inputProps。
// 生产流程里这份 props 由 lyric_mv pipeline 直接产出，不需要这个脚本。
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const timelinePath = path.resolve(root, '../lyric_mv/_e2e/timeline.json');
const DURATION = 27.7;

const tl = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
const shift = (tl.lines?.[0]?.start ?? 0) - 0.2;

const lines = (tl.lines || [])
  .map((l) => ({
    ...l,
    start: +(l.start - shift).toFixed(3),
    end: +(l.end - shift).toFixed(3),
    chars: (l.chars || []).map(([c, t]) => [c, +(t - shift).toFixed(3)]),
  }))
  .filter((l) => l.start < DURATION - 0.5 && l.end > 0);

const props = {
  timeline: {
    song: 'demo',
    bpm: tl.bpm,
    beat_seconds: tl.beat_seconds,
    offset_seconds: tl.offset_seconds,
    duration: DURATION,
    fps: 30,
    lines,
  },
  plan: {
    title: 'DEMO',
    lyricStyle: process.env.STYLE || 'band',
    chrome: {section: 'zh', sectionAt: 'top-left', progress: 'top'},
    shots: [{start: 0, end: DURATION, scene: 'demo.maldives'}],
    scenes: [],
  },
  fps: 30,
  width: 1920,
  height: 1080,
};

const out = path.join(root, 'demo-props.json');
fs.writeFileSync(out, JSON.stringify(props, null, 2), 'utf8');
console.log(`wrote ${out} — ${lines.length} lines, ${DURATION}s`);
