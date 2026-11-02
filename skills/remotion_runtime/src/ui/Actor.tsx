import React from 'react';
import {useE} from '../engine/context';

/**
 * 可选的人物放置器：把角色放进场景里，并避免「头被歌词压住」。
 *
 * 它只是工具，不是强制流程——你完全可以直接 `<g transform={...}><Character/></g>` 自己摆。
 * 返回纯 `<g>`、不自带视口，所以能跟着场景自己的相机/图层顺序走：
 * 想让标题、黑场、前景座椅盖住人，就把它放在那些图元之前即可。
 *
 * 用法（x/y 是脚底，画布像素；s=1 时人高约 470px）：
 *   <Actor Character={Character} x={960} y={980} s={1.1} />
 */
export const Actor: React.FC<{
  Character: React.FC;
  x: number;
  y: number;
  s?: number;
  /** 角色本地总高（脚底到头顶的单位数） */
  height?: number;
  /** 角色本地半宽 */
  halfWidth?: number;
  /** 与歌词带之间留的空隙 */
  gap?: number;
  flip?: boolean;
  opacity?: number;
  /** SVG 滤镜 id，如 "url(#rim)" */
  filter?: string;
}> = ({
  Character,
  x,
  y,
  s = 1,
  height = 470,
  halfWidth = 130,
  gap = 24,
  flip,
  opacity = 1,
  filter,
}) => {
  const e = useE();
  const k = e.W / 1280;

  // 歌词占用区换算到画布坐标
  const [bx0, by0, bx1, by1] = e.lyricBox;
  const lx0 = bx0 * k - gap;
  const ly0 = by0 * k - gap;
  const lx1 = bx1 * k + gap;
  const ly1 = by1 * k + gap;

  // 只有「头」被歌词压住才让位；脚被压住不影响辨认，也不该把人缩成小点
  const headHit = (sc: number, fy: number) => {
    const hw = halfWidth * 0.38 * sc;
    const top = fy - height * sc;
    const bottom = fy - height * 0.52 * sc;
    return x + hw > lx0 && x - hw < lx1 && bottom > ly0 && top < ly1;
  };

  let sc = Math.max(0.05, s);
  let fy = y;

  if (headHit(sc, fy)) {
    const cands = [
      (fy - ly1) / height, // 头落到歌词带下方
      (fy - ly0) / (height * 0.52), // 头抬到歌词带上方
      (x - lx1) / (halfWidth * 0.38), // 头移到带右侧
      (lx0 - x) / (halfWidth * 0.38), // 头移到带左侧
    ].filter((v) => v > 0.15 && v < sc);
    if (cands.length) sc = Math.max(...cands);
  }

  if (headHit(sc, fy)) {
    const up = ly0;
    const down = ly1 + height * sc;
    const canUp = up - (24 + height * sc) > 0;
    const canDown = down < e.H - 24;
    if (canDown && (!canUp || e.H - ly1 > ly0)) fy = down;
    else if (canUp) fy = up;
  }

  fy = Math.min(Math.max(fy, 24 + height * sc), e.H - 24);

  return (
    <g transform={`translate(${x} ${fy}) scale(${flip ? -sc : sc} ${sc})`} opacity={opacity} filter={filter}>
      <Character />
    </g>
  );
};
