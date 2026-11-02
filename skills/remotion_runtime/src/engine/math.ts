/** 确定性数学工具。与 engine/stage.html 的口径保持一致：所有函数都是纯函数。 */

export const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
export const clamp01 = (v: number) => clamp(v, 0, 1);
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const seg = (a: number, b: number, v: number) =>
  b === a ? (v >= b ? 1 : 0) : clamp01((v - a) / (b - a));

export const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);
export const easeIn = (t: number) => Math.pow(clamp01(t), 3);
export const easeIO = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
export const back = (t: number) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  const x = clamp01(t) - 1;
  return 1 + c3 * x * x * x + c1 * x * x;
};
export const elastic = (t: number) => {
  const x = clamp01(t);
  if (x === 0 || x === 1) return x;
  return Math.pow(2, -10 * x) * Math.sin((x * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
};
export const wave = (t: number, freq = 1) => Math.sin(t * Math.PI * 2 * freq);

/** 确定性伪随机（同 seed 恒同值；禁止 Math.random）。字符串 seed 先折成整数，方便按名字取值。 */
export const hash = (seed: number | string) => {
  let s = seed;
  if (typeof s === 'string') {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
    s = h;
  }
  const x = Math.sin(s * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

/** 一维平滑噪声，用于静止元素的细微漂移 */
export const noise1 = (x: number) => {
  const i = Math.floor(x);
  const f = x - i;
  const a = hash(i * 1.7 + 11.3);
  const b = hash((i + 1) * 1.7 + 11.3);
  return lerp(a, b, f * f * (3 - 2 * f)) * 2 - 1;
};

/** 欠阻尼弹簧：0→1 过程会过冲，入场更有重量 */
export const spring = (
  age: number,
  opts: { damping?: number; stiffness?: number; mass?: number } = {}
) => {
  const damping = opts.damping ?? 15;
  const stiffness = opts.stiffness ?? 380;
  const mass = opts.mass ?? 1;
  if (age <= 0) return 0;
  const w0 = Math.sqrt(stiffness / mass);
  const zeta = damping / (2 * Math.sqrt(stiffness * mass));
  if (zeta < 1) {
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    return 1 - Math.exp(-zeta * w0 * age) * (Math.cos(wd * age) + ((zeta * w0) / wd) * Math.sin(wd * age));
  }
  return 1 - Math.exp(-w0 * age) * (1 + w0 * age);
};
