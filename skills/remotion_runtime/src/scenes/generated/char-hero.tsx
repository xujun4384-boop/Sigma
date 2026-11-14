// 由 character_sheet 的定妆参数生成：几何在 RigCharacter，改角色请改参数
import React from 'react';
import {RigCharacter} from '../../ui/RigCharacter';

const SPEC: any = {
  "id": "character",
  "name": "风格小样占位",
  "proportions": {
    "headRatio": 0.22,
    "legRatio": 0.34,
    "shoulderRatio": 0.95,
    "hipRatio": 1.0,
    "belly": 0.3,
    "armRatio": 1.0
  },
  "colors": {
    "skin": "#f2d5c0",
    "skinShade": "#bca695",
    "hair": "#4a3b32",
    "hairShade": "#392e27",
    "cloth": "#e8a87c",
    "clothShade": "#b48360",
    "apron": "#f1e7d4",
    "apronShade": "#bbb4a5",
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
