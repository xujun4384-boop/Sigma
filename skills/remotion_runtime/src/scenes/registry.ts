import React from 'react';
import {DefaultFiller} from './DefaultFiller';
import {Shot1, META as M0} from './generated/styled-shot-1';

export type SceneEntry = {comp: React.FC; bg?: string};

export const REGISTRY: Record<string, SceneEntry> = {
  'default.filler': {comp: DefaultFiller, bg: '#0b0d16'},
  'shot-1': {comp: Shot1, bg: M0[1]?.bg},
};
