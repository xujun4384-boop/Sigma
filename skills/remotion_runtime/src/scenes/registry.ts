import React from 'react';
import {DefaultFiller} from './DefaultFiller';
import {Shot1, META as M0} from './generated/artist-shot-1';
import {Shot10, META as M1} from './generated/artist-shot-10';
import {Shot11, META as M2} from './generated/artist-shot-11';
import {Shot12, META as M3} from './generated/artist-shot-12';
import {Shot13, META as M4} from './generated/artist-shot-13';
import {Shot14, META as M5} from './generated/artist-shot-14';
import {Shot15, META as M6} from './generated/artist-shot-15';
import {Shot16, META as M7} from './generated/artist-shot-16';
import {Shot17, META as M8} from './generated/artist-shot-17';
import {Shot18, META as M9} from './generated/artist-shot-18';
import {Shot19, META as M10} from './generated/artist-shot-19';
import {Shot2, META as M11} from './generated/artist-shot-2';
import {Shot20, META as M12} from './generated/artist-shot-20';
import {Shot21, META as M13} from './generated/artist-shot-21';
import {Shot22, META as M14} from './generated/artist-shot-22';
import {Shot23, META as M15} from './generated/artist-shot-23';
import {Shot24, META as M16} from './generated/artist-shot-24';
import {Shot3, META as M17} from './generated/artist-shot-3';
import {Shot4, META as M18} from './generated/artist-shot-4';
import {Shot5, META as M19} from './generated/artist-shot-5';
import {Shot6, META as M20} from './generated/artist-shot-6';
import {Shot7, META as M21} from './generated/artist-shot-7';
import {Shot8, META as M22} from './generated/artist-shot-8';
import {Shot9, META as M23} from './generated/artist-shot-9';

export type SceneEntry = {comp: React.FC; bg?: string};

export const REGISTRY: Record<string, SceneEntry> = {
  'default.filler': {comp: DefaultFiller, bg: '#0b0d16'},
  'shot-1': {comp: Shot1, bg: M0[1]?.bg},
  'shot-10': {comp: Shot10, bg: M1[10]?.bg},
  'shot-11': {comp: Shot11, bg: M2[11]?.bg},
  'shot-12': {comp: Shot12, bg: M3[12]?.bg},
  'shot-13': {comp: Shot13, bg: M4[13]?.bg},
  'shot-14': {comp: Shot14, bg: M5[14]?.bg},
  'shot-15': {comp: Shot15, bg: M6[15]?.bg},
  'shot-16': {comp: Shot16, bg: M7[16]?.bg},
  'shot-17': {comp: Shot17, bg: M8[17]?.bg},
  'shot-18': {comp: Shot18, bg: M9[18]?.bg},
  'shot-19': {comp: Shot19, bg: M10[19]?.bg},
  'shot-2': {comp: Shot2, bg: M11[2]?.bg},
  'shot-20': {comp: Shot20, bg: M12[20]?.bg},
  'shot-21': {comp: Shot21, bg: M13[21]?.bg},
  'shot-22': {comp: Shot22, bg: M14[22]?.bg},
  'shot-23': {comp: Shot23, bg: M15[23]?.bg},
  'shot-24': {comp: Shot24, bg: M16[24]?.bg},
  'shot-3': {comp: Shot3, bg: M17[3]?.bg},
  'shot-4': {comp: Shot4, bg: M18[4]?.bg},
  'shot-5': {comp: Shot5, bg: M19[5]?.bg},
  'shot-6': {comp: Shot6, bg: M20[6]?.bg},
  'shot-7': {comp: Shot7, bg: M21[7]?.bg},
  'shot-8': {comp: Shot8, bg: M22[8]?.bg},
  'shot-9': {comp: Shot9, bg: M23[9]?.bg},
};
