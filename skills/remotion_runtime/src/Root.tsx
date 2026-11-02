import React from 'react';
import {CalculateMetadataFunction, Composition} from 'remotion';
import {CharSheet} from './CharSheet';
import {LyricMV} from './LyricMV';
import type {EngineProps} from './types';

const defaultProps: EngineProps = {
  timeline: {duration: 10, beat_seconds: 0.5, offset_seconds: 0, lines: []},
  plan: {lyricStyle: 'band'},
  fps: 30,
  width: 1920,
  height: 1080,
};

const calculateMetadata: CalculateMetadataFunction<EngineProps> = ({props}) => {
  const fps = Math.max(1, Math.round(Number(props.fps) || props.timeline?.fps || 30));
  const seconds = Math.max(0.5, Number(props.timeline?.duration) || 10);
  return {
    fps,
    durationInFrames: Math.max(1, Math.round(seconds * fps)),
    width: Math.max(320, Math.round(Number(props.width) || 1920)),
    height: Math.max(180, Math.round(Number(props.height) || 1080)),
  };
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="LyricMV"
      component={LyricMV}
      durationInFrames={300}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="CharSheet"
      component={CharSheet}
      durationInFrames={1}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{who: 'hero'}}
    />
  </>
);
