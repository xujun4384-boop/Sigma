// 由 character_sheet 的定妆参数生成：几何在 RigCharacter，改角色请改参数
import React from 'react';
import {RigCharacter} from './ui/RigCharacter';

const SPEC: any = {
  "id": "character",
  "name": "角色",
  "proportions": {
    "headRatio": 0.24,
    "legRatio": 0.32,
    "shoulderRatio": 0.92,
    "hipRatio": 1.04,
    "belly": 0.5,
    "armRatio": 1.0
  },
  "colors": {
    "skin": "#f6d3b8",
    "skinShade": "#dfb096",
    "hair": "#4a3a33",
    "hairShade": "#2f2521",
    "cloth": "#8fa4bd",
    "clothShade": "#6d8299",
    "apron": "#f1e7d4",
    "apronShade": "#d5c4a8",
    "ink": "#4a4038"
  },
  "hair": "short",
  "outfit": "shirt",
  "glasses": false,
  "wrinkle": 0.0
};

export const Character: React.FC<any> = (p) => <RigCharacter spec={SPEC} view="front" {...p} />;
export const CharacterSide: React.FC<any> = (p) => <RigCharacter spec={SPEC} view="side" {...p} />;
export const CharacterBack: React.FC<any> = (p) => <RigCharacter spec={SPEC} view="back" {...p} />;
