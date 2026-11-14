// 由 character_sheet 的定妆参数生成：几何在 RigCharacter，改角色请改参数
import React from 'react';
import {RigCharacter} from '../../ui/RigCharacter';

const SPEC: any = {
  "id": "character",
  "name": "她",
  "proportions": {
    "headRatio": 0.3,
    "legRatio": 0.3,
    "shoulderRatio": 0.85,
    "hipRatio": 1.0,
    "belly": 0.25,
    "armRatio": 0.95
  },
  "colors": {
    "skin": "#f7d3b4",
    "skinShade": "#c0a48c",
    "hair": "#4b322c",
    "hairShade": "#3a2722",
    "cloth": "#ede3d2",
    "clothShade": "#b8b1a3",
    "apron": "#e8dcc8",
    "apronShade": "#b4ab9c",
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
