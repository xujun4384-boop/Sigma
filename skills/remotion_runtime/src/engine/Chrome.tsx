import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Plan, Timeline} from '../types';
import {FONT} from './measure';
import {secZh} from './theme';
import {pickLyricStyle, sectionAt} from './lyricStyle';

const POS: Record<string, React.CSSProperties> = {
  'top-left': {left: 56, top: 46},
  'top-right': {right: 56, top: 46, textAlign: 'right'},
  'bottom-left': {left: 56, bottom: 42},
  'bottom-right': {right: 56, bottom: 42, textAlign: 'right'},
};

/** 歌词带蒙版：只保证歌词可读，不改变画面主体（深色画面压暗，浅色画面提亮） */
const LyricScrim: React.FC<{style: string; dark: boolean}> = ({style, dark}) => {
  const tone = dark ? 'rgba(8,12,20' : 'rgba(250,248,244';
  const stops = dark ? [0.5, 0.42, 0.28] : [0.55, 0.45, 0.3];
  if (style === 'brush') {
    return <AbsoluteFill style={{background: `linear-gradient(90deg, ${tone},${stops[0]}) 0%, ${tone},0) 26%, ${tone},0) 100%)`}} />;
  }
  if (style === 'vertical') {
    return <AbsoluteFill style={{background: `linear-gradient(270deg, ${tone},${stops[0]}) 0%, ${tone},0) 24%, ${tone},0) 100%)`}} />;
  }
  if (style === 'bottom') {
    return <AbsoluteFill style={{background: `linear-gradient(0deg, ${tone},${stops[1]}) 0%, ${tone},0) 28%, ${tone},0) 100%)`}} />;
  }
  return <AbsoluteFill style={{background: `linear-gradient(180deg, ${tone},${stops[1]}) 0%, ${tone},0) 26%, ${tone},0) 100%)`}} />;
};

/** 画面框：章节标签 + 进度条（引擎自动叠加，画面代码不用管） */
export const Chrome: React.FC<{timeline: Timeline; plan: Plan; width: number; height: number; dark?: boolean}> = ({
  timeline,
  plan,
  width,
  height,
  dark = true,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const chrome = plan.chrome || {};
  const secMode = chrome.section ?? 'en';
  const posKey = chrome.sectionAt ?? 'top-left';
  const progressMode = chrome.progress ?? 'top';
  const dur = timeline.duration || durationInFrames / fps;

  const lines = timeline.lines || [];
  let active: string | undefined;
  for (const l of lines) {
    if (l.start <= t && t < l.end + 0.4) active = l.section;
  }
  const secText = secMode === 'hide' || !active ? '' : secMode === 'zh' ? secZh(active) : String(active).toUpperCase();

  const p = Math.max(0, Math.min(1, t / Math.max(0.1, dur)));
  const k = Math.min(width, height) / 1080;
  const progressBar = (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        height: 2,
        background: dark ? 'rgba(255,255,255,0.16)' : 'rgba(0,0,0,0.12)',
        ...(progressMode === 'top' ? {top: 0} : {bottom: 0}),
      }}
    >
      <div style={{width: `${p * 100}%`, height: '100%', background: dark ? 'rgba(255,255,255,0.62)' : 'rgba(20,24,32,0.45)'}} />
    </div>
  );

  const scrimStyle = pickLyricStyle(plan, sectionAt(timeline, t));
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {!plan.plain ? <LyricScrim style={scrimStyle} dark={dark} /> : null}
      {secText ? (
        <div
          style={{
            position: 'absolute',
            ...POS[posKey],
            fontFamily: FONT,
            fontSize: 15 * k * 1.4,
            letterSpacing: '0.32em',
            color: dark ? 'rgba(255,255,255,0.5)' : 'rgba(20,24,32,0.55)',
            textShadow: dark ? '0 2px 10px rgba(0,0,0,0.45)' : '0 1px 8px rgba(255,255,255,0.5)',
          }}
        >
          {secText}
        </div>
      ) : null}
      {progressMode !== 'hide' ? progressBar : null}
    </AbsoluteFill>
  );
};
