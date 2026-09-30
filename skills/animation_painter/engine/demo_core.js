/* ============================================================================
   animation_painter 示例章节（demo_core.js）
   ----------------------------------------------------------------------------
   展示在通用运行时上，用【通用角色构件库】（char_Blob/char_Eye/char_Ear/
   char_Close + paint/inkLine/ellPts/rrPts…）**自行拼出任意角色**。

   不再依赖"某个角色的模板"：大脑、机器人、小猫都只是同一套构件的不同组合。
   如果 AI 需要新角色（狗/鹿/龙…），照下面的大脑/机器人/小猫"拼法"，用同样构件
   组合即可，**不需要给引擎加任何新函数**。这才是通用，不是换皮硬编码。

   关键约定（AI 与运行时的契约）：
   - 用 window.__P5FX 解构基础工具 + 通用构件；命名角色一律在章节脚本里**本地定义**。
   - 用 window.chapter(name, start, end, shots) 注册章节。
   - 每个镜头是 shot(t, lt, dur)：t=全局秒, lt=镜头内秒, dur=镜头时长。
   - 每帧是 t 的纯函数：禁止跨帧状态、禁止 Math.random()。用 hash(i) 稳定伪随机
     + jit(a) 手绘抖动（运行时每秒 12 次重置，模拟"画面沸腾"）。
   - 帧会无序并行渲染，所以镜头之间绝不能共享可变全局。
   ============================================================================ */
(function () {
  const {
    ease, easeOut, backOut, lerp, pulse, seg, jit, kf, mixCol,
    paint, ellPts, rectPts, rrPts, inkLine,
    letter, sfx,
    char_Blob, char_Eye, char_Ear, char_Close,
    PAL, CFG, W, H, BPM
  } = window.__P5FX;
  const bob_ = t => Math.sin((t * 60 / (CFG.BPM || 88)) * Math.PI) * 2.5; // 随音乐呼吸

  // ── 拼法①：大脑（模型/认知感）────────────────────────────────────────────────
  // 用 char_Blob 做皮层外轮廓、char_Eye 做眼睛；剩下沟回/纵裂/天线是普通 inkLine/ellPts 组合。
  function buildBrain(cx, cy, s, t, o = {}) {
    const col = o.col || PAL.clay, dk = o.dk || PAL.clayDk, seed = o.seed != null ? o.seed : 7;
    push(); translate(cx, cy + bob_(t) * s); scale(s);
    const rx = 62, ry = 54;
    paint(char_Close(char_Blob(0, 0, rx, ry, 46, 1.5, seed, 4)),
      { wash: mixCol(col, PAL.cream, .3), washOp: 210, fill: col, fillOp: 30, bleed: .1, tex: .35, ink: dk, sw: 1.0 });
    const fiss = [];
    for (let i = 0; i <= 24; i++) { const u = i / 24; fiss.push([jit(.8), (u * 2 - 1) * ry - 6 + Math.sin(u * 4.2 + seed) * 6 + jit(.8)]); }
    inkLine(fiss, .8, dk, 'inkfine', .6);
    const gyri = o.gyri != null ? o.gyri : 3;
    for (let g = 0; g < gyri; g++) {
      const vert = -0.36 + g * 0.34, sw = Math.sqrt(Math.max(0, 1 - vert * vert)), line = [];
      for (let i = 0; i <= 26; i++) { const u = i / 26; line.push([(u * 2 - 1) * rx * .92 * sw + jit(1), -2 + vert * ry * .94 + Math.sin(u * 3.5 + seed + g * 3.1) * rx * .92 * .13 + jit(1)]); }
      inkLine(line, .7 + (g % 2) * .15, dk, 'inkfine', .65);
    }
    if (o.tech) {
      inkLine([[0, -ry - 8], [0, -ry - 22 - Math.sin((t * 60 / (CFG.BPM || 88)) * Math.PI) * 2]], .7, dk, 'inkfine', .5);
      paint(ellPts(0, -ry - 30, 4.5, 4.5, 12, .6), { wash: o.techCol || PAL.ochre, washOp: 255, ink: null });
    }
    if (o.eyes !== false) { char_Eye(-rx * .24, -ry * .18, 7, o); char_Eye(rx * .24, -ry * .18, 7, o); }
    pop();
  }
  // ── 拼法②：智能体/机器人（圆头 + 修长躯干）──────────────────────────────────
  // 头/身体用 rrPts，眼睛用 char_Eye，天线/插孔是 inkLine/rectPts。无任何新构件。
  function buildBot(cx, cy, s, t, o = {}) {
    const col = o.col || PAL.indigo, dk = o.dk || PAL.ink;
    push(); translate(cx, cy + bob_(t) * s); scale(s);
    inkLine([[0, -92], [0, -110]], .8, dk, 'inkfine', .6);
    paint(ellPts(0, -118, 6, 6, 14, .7), { wash: o.techCol || PAL.ochre, washOp: 255, ink: dk, sw: .6 });
    paint(rrPts(-54, -92, 108, 96, 26, 1.4), { wash: mixCol(col, PAL.cream, .2), washOp: 225, fill: col, fillOp: 26, bleed: .08, tex: .3, ink: dk, sw: 1.0 });
    char_Eye(-24, -44, 12, o); char_Eye(24, -44, 12, o);
    paint(ellPts(-42, -20, 6, 4, 12, .9), { fill: PAL.rose, fillOp: 60, bleed: .2, ink: null });
    paint(ellPts(42, -20, 6, 4, 12, .9), { fill: PAL.rose, fillOp: 60, bleed: .2, ink: null });
    inkLine([[-9, -12], [0, -9], [9, -12]], .9, dk, 'ink', .7);
    paint(rrPts(-13, 4, 26, 14, 7, .6), { wash: mixCol(col, PAL.cream, .45), washOp: 210, ink: dk, sw: .6 });
    paint(rrPts(-46, 18, 92, 84, 24, 1.2), { wash: mixCol(col, PAL.cream, .35), washOp: 195, fill: col, fillOp: 22, bleed: .08, tex: .3, ink: dk, sw: .95 });
    paint(ellPts(0, 46, 15, 19, 20, .7), { wash: o.techCol || PAL.ochre, washOp: 200, fill: PAL.rose, fillOp: 40, ink: dk, sw: .6 });
    pop();
  }
  // ── 拼法③：小猫（证明同一套构件可拼出与大脑/机器人都无关的角色）────────────
  // 头 = ellPts，耳 = char_Ear×2，眼 = char_Eye，须/嘴 = inkLine，身尾 = ellPts。
  function buildCat(cx, cy, s, t, o = {}) {
    const col = o.col || PAL.ochre, dk = o.dk || PAL.ink;
    push(); translate(cx, cy + bob_(t) * s); scale(s);
    // 尾巴（先画，被身体压住根部）
    inkLine([[54, 60], [74, 48], [86, 30], [96, 12]], 1.1, dk, 'ink', .55);
    // 耳朵
    char_Ear(-34, -86, 20, 26, -0.45, { wash: mixCol(col, PAL.rose, .3), washOp: 230, fill: PAL.rose, fillOp: 40, ink: dk, sw: .8 });
    char_Ear(34, -86, 20, 26, 0.45, { wash: mixCol(col, PAL.rose, .3), washOp: 230, fill: PAL.rose, fillOp: 40, ink: dk, sw: .8 });
    // 头
    paint(char_Close(ellPts(0, -40, 56, 52, 30, 1.5)), { wash: mixCol(col, PAL.cream, .2), washOp: 225, fill: col, fillOp: 26, bleed: .08, tex: .3, ink: dk, sw: .95 });
    // 眼 + 鼻子 + 嘴 + 须
    char_Eye(-20, -46, 8, o); char_Eye(20, -46, 8, o);
    paint(ellPts(0, -32, 5, 4, 12, .6), { wash: PAL.rose, washOp: 220, ink: null });
    inkLine([[-6, -26], [0, -23], [6, -26]], .8, dk, 'inkfine', .6);
    inkLine([[-34, -34], [-56, -40], [-70, -46]], .6, dk, 'inkfine', .5);
    inkLine([[34, -34], [56, -40], [70, -46]], .6, dk, 'inkfine', .5);
    // 身体 + 前爪
    paint(char_Close(rrPts(-44, 4, 88, 66, 26, 1.2)), { wash: mixCol(col, PAL.cream, .3), washOp: 205, fill: col, fillOp: 22, bleed: .08, tex: .3, ink: dk, sw: .9 });
    paint(ellPts(-26, 74, 14, 12, 16, 1), { wash: mixCol(col, PAL.cream, .45), washOp: 200, ink: dk, sw: .6 });
    paint(ellPts(26, 74, 14, 12, 16, 1), { wash: mixCol(col, PAL.cream, .45), washOp: 200, ink: dk, sw: .6 });
    pop();
  }
  // ── 拼法④：通用对话框（同一套 paint/rrPts/inkLine 组合，带指向尾）────────────
  function buildBubble(cx, cy, w, h, tail, o = {}) {
    const r = o.radius || 14;
    const box = char_Close(rrPts(cx - w / 2, cy - h / 2, w, h, r, 1.2));
    paint(box, { wash: o.wash || PAL.cream, washOp: 235, fill: o.fill || PAL.violet, fillOp: o.fillOp || 24, bleed: .1, tex: .3, ink: o.ink || PAL.ink, sw: .9 });
    if (tail) {
      const ax = cx + w / 2, ay = cy + h / 2, [tdx, tdy] = tail, L = Math.hypot(tdx, tdy) || 1;
      const bx = ax - (tdx / L) * r * .9, by = ay - (tdy / L) * r * .9, tx = bx + tdx, ty = by + tdy;
      paint([[bx, by], [bx + (tx - bx) * .35, by + (ty - by) * .35], [tx, ty], [bx + (tx - bx) * .22, by + (ty - by) * .22]],
        { wash: o.fill || PAL.violet, washOp: 90, ink: o.ink || PAL.ink, sw: .7 });
    }
    if (o.txt) letter(o.txt, cx, cy, o.size || Math.min(w, h) * .22, o.color || PAL.ink, {});
  }

  // ── 背景 ─────────────────────────────────────────────────────────────────────
  function bg(t, o = {}) {
    const skyLo = o.skyLo || PAL.cream;
    paint(rectPts(-60, -60, W + 120, H + 120), { wash: PAL.paper, washOp: 255, ink: null });
    paint(ellPts(W * .3, H * .28, W * .7, H * .8, 40, 8), { fill: skyLo, fillOp: 90, bleed: .35, tex: .25, border: .2, ink: null });
    paint(ellPts(W * .7, H * .25, W * .7, H * .7, 40, 8, 1.2), { fill: skyLo, fillOp: 80, bleed: .3, tex: .3, ink: null });
    paint(ellPts(W * .8, H * .2, W * .09, W * .09, 30, 3), { wash: PAL.ochre, washOp: 220, fill: PAL.cream, fillOp: 40, ink: null });
    paint(ellPts(W * .5, H * .92, W * .9, H * .28, 44, 10), { fill: PAL.sap, fillOp: 120, bleed: .25, tex: .5, border: .5, ink: null });
    paint(ellPts(W * .5, H * 1.02, W * 1.1, H * .3, 44, 12), { fill: PAL.sap, fillOp: 100, bleed: .2, tex: .5, border: .4, ink: null });
  }

  // ── 镜头们：每帧先画完整背景，再叠角色（都是上面通用构件的组合示范） ────────
  function intro(t, lt, dur) {
    bg(t);
    const p = ease(lt / dur);
    buildBrain(W * .5, H * .6, 4 * (H / 800), t, { col: PAL.clay, dk: PAL.clayDk, tech: true, techCol: PAL.ochre });
    letter('你好', W / 2, H * .24, Math.max(30, H * .06) * (0.6 + 0.4 * backOut(p)), PAL.ink, { pop: p });
  }
  function dance(t, lt, dur) {
    bg(t);
    const pk = pulse(t, 5);
    buildBot(W * .3, H * .72, 1.7 * (H / 800), t, { col: PAL.clay, blink: true });
    buildCat(W * .7, H * .78, 1.15 * (H / 800), t, { col: PAL.ochre, dk: PAL.ink });
    buildBubble(W * .52, H * .36, W * .32, H * .12, [-36, 22], { txt: '机器人 + 猫', size: H * .032 });
    if (pk > .3 && Math.floor(t * 4) % 8 === 0) sfx('BOOM', W / 2, H * .28, H * .07, PAL.ochre, lt * .4, {});
    letter('跟着节拍', W / 2, H * .14, H * .05, PAL.indigo, {});
  }
  function finale(t, lt, dur) {
    bg(t);
    buildBrain(W / 2, H * .62, 4.5 * (H / 800) + Math.sin(t * 3) * H * .002, t, { col: PAL.teal, dk: PAL.ink });
    paint(ellPts(W / 2, H * .24, W * .05 + Math.sin(t * 2) * W * .004, W * .05, 24, 2), { wash: PAL.rose, washOp: 100, ink: null });
    letter('END', W / 2, H * .1, H * .07, PAL.cream, { ink: PAL.cream });
  }

  const D = CFG.DUR || 8;
  const tA = 0, tB = D * .3, tC = D * .7, tD = D;
  window.chapter('demo', tA, tD, [
    [tA, intro],
    [tB, dance],
    [tC, finale],
  ]);

  if (!window.PAINT_CONFIG.lyrics || window.PAINT_CONFIG.lyrics.length === 0) {
    window.PAINT_CONFIG.lyrics = [
      [tA, tB, 'Hello world'],
      [tB, tC, 'Dance with the beat'],
      [tC, tD, 'The end'],
    ];
  }
})();