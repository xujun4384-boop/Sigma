/** 文字实测宽度：与 canvas 版引擎同口径（同一字体栈、同一 weight），保证排版一致。 */

export const FONT = '"Noto Sans SC","Source Han Sans SC","Microsoft YaHei","PingFang SC",sans-serif';
export const KAI = '"KaiTi","STKaiti","Kaiti SC","BiauKai","楷体",serif';
export const BRUSH = '"STXingkai","KaiTi","STKaiti","Kaiti SC","楷体",serif';

let ctx: CanvasRenderingContext2D | null = null;
const cache = new Map<string, number>();

const getCtx = () => {
  if (ctx) return ctx;
  if (typeof document === 'undefined') return null;
  const c = document.createElement('canvas');
  c.width = 8;
  c.height = 8;
  ctx = c.getContext('2d');
  return ctx;
};

export const measure = (str: string, size: number, weight: number | string = 900, font: string = FONT) => {
  const key = `${weight}|${size}|${font}|${str}`;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  const c = getCtx();
  let w: number;
  if (!c) {
    // 无 DOM 的兜底：中文按 1em、其他按 0.55em 估算
    w = Array.from(str).reduce((acc, ch) => acc + (/[\u3000-\u9fff\uff00-\uffef]/.test(ch) ? size : size * 0.55), 0);
  } else {
    c.font = `${weight} ${size}px ${font}`;
    w = c.measureText(str).width;
  }
  cache.set(key, w);
  return w;
};
