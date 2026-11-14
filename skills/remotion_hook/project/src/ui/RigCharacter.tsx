import React from 'react';
import {buildCharacter} from '../character/rig';
import type {
  CharacterSpec,
  DrawOp,
  EyeMood,
  MouthMood,
  Pose,
  PoseParams,
  View,
} from '../character/types';
import {DEFAULT_POSE} from '../character/types';

/**
 * 参数化角色（SVG 版）。
 *
 * 和画布上的预览共用同一份骨架：`buildCharacter` 吐出的是路径指令，
 * Canvas2D 用 Path2D 吃，SVG 用 <path> 吃。所以「用户确认过的定妆」
 * 与「成片里的这个人」是同一份几何，不是两套画法。
 *
 * 本地坐标：脚底 (0,0)，向上为负 y，总高约 430；外层用 scale 控制大小。
 */

/** 老版本的镜头代码传的是手的位置 [x,y]，这里换算成摆臂角度，保持兼容。 */
function armAngleFromHand(
  hand: [number, number],
  side: 'L' | 'R',
  totalHeight: number,
): number {
  const dir = side === 'L' ? -1 : 1;
  const shoulderX = dir * totalHeight * 0.155;
  const shoulderY = -totalHeight * 0.553;
  const outward = (hand[0] - shoulderX) * dir;
  const upward = shoulderY - hand[1];
  const deg = (Math.atan2(outward, Math.max(1, upward)) * 180) / Math.PI;
  // 0 为自然下垂，正值向外张开；限制在两段手臂不会打结的范围内
  return Math.max(-40, Math.min(150, deg));
}

const MOOD_FACE: Record<string, {eyes: EyeMood; mouth: MouthMood}> = {
  happy: {eyes: 'open', mouth: 'smile'},
  excited: {eyes: 'happy', mouth: 'open'},
  dizzy: {eyes: 'worried', mouth: 'neutral'},
  worried: {eyes: 'worried', mouth: 'sad'},
  tired: {eyes: 'closed', mouth: 'neutral'},
  surprised: {eyes: 'surprised', mouth: 'open'},
  weak: {eyes: 'closed', mouth: 'sad'},
  calm: {eyes: 'open', mouth: 'neutral'},
  sleep: {eyes: 'closed', mouth: 'neutral'},
};

export interface RigCharacterProps {
  spec: CharacterSpec;
  view?: View;
  pose?: Pose;
  mood?: string;
  eyes?: EyeMood;
  mouth?: MouthMood;
  armL?: number | [number, number];
  armR?: number | [number, number];
  headTurn?: number;
  tilt?: number;
  bob?: number;
  /** 本地总高，与道具/场景做比例对齐时用 */
  height?: number;
}

function hasFill(op: DrawOp): string {
  return op.fill ?? 'none';
}

export const RigCharacter: React.FC<RigCharacterProps> = ({
  spec,
  view = 'front',
  pose = 'stand',
  mood,
  eyes,
  mouth,
  armL,
  armR,
  headTurn = 0,
  tilt = 0,
  bob = 0,
  height = 430,
}) => {
  const face = MOOD_FACE[mood ?? ''] ?? {eyes: 'open' as EyeMood, mouth: 'smile' as MouthMood};
  const poseParams: PoseParams = {
    ...DEFAULT_POSE,
    view,
    pose,
    eyes: eyes ?? face.eyes,
    mouth: mouth ?? face.mouth,
    armL: typeof armL === 'number' ? armL : armL ? armAngleFromHand(armL, 'L', height) : DEFAULT_POSE.armL,
    armR: typeof armR === 'number' ? armR : armR ? armAngleFromHand(armR, 'R', height) : DEFAULT_POSE.armR,
    headTurn,
    tilt,
    bob,
  };

  const drawing = buildCharacter(spec, poseParams, height);

  return (
    <g transform={`rotate(${drawing.tilt}) translate(0 ${-drawing.bob})`}>
      {drawing.ops.map((op, i) => (
        <path
          key={i}
          d={op.d}
          fill={hasFill(op)}
          stroke={op.stroke ?? 'none'}
          strokeWidth={op.strokeWidth ?? 0}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={op.opacity ?? 1}
        />
      ))}
    </g>
  );
};

export default RigCharacter;
