/* ============================================================================
   Trae vs WorkBuddy 水彩开场/收尾章节（compare_core.js）
   必须放在 engine/ 同目录（painter.html 用相对路径 ?core=compare_core.js 加载）
   镜头（总时长 22s，与录制参数 dur=22 一致）：
   - 0~6.5s  opening：「字节 vs 腾讯」路线之争，两侧旗帜对峙，中央标题逐字浮现
   - 6.5~15s split：左侧机器人（Trae·写代码，蓝紫）；右侧小人（WorkBuddy·干活，青绿）；中间 VS 分隔
   - 15~22s ending：两者靠拢并肩，中央收尾提问「你的工作，是哪一类？」
   ============================================================================ */
(function () {
  const {
    ease, easeOut, backOut, lerp, pulse, seg, jit, kf, mixCol, clamp, hash,
    paint, ellPts, rectPts, rrPts, inkLine,
    letter, sfx,
    char_Blob, char_Eye, char_Ear, char_Close,
    PAL, CFG, W, H, BPM
  } = window.__P5FX;
  const bob_ = t => Math.sin((t * 60 / (CFG.BPM || 88)) * Math.PI) * 2.2;
  const s_ = H / 800; // 尺寸随分辨率缩放

  // ── 角色①：程序员小机器人（Trae）────────────────────────────────────────
  function buildBot(cx, cy, sc, t, o = {}) {
    const col = o.col || PAL.indigo, dk = PAL.ink;
    const typing = o.typing ? Math.sin(t * 10) * 2 : 0;
    push(); translate(cx, cy + bob_(t) * sc); scale(sc);
    inkLine([[0, -66], [0, -80]], .8, dk, 'inkfine', .6);
    paint(ellPts(0, -86, 5, 5, 12, .6), { wash: PAL.ochre, washOp: 255, ink: dk, sw: .5 });
    paint(rrPts(-40, -64, 80, 68, 20, 1.2), { wash: mixCol(col, PAL.cream, .2), washOp: 225, fill: col, fillOp: 26, bleed: .08, tex: .3, ink: dk, sw: .95 });
    char_Eye(-17, -32, 9, o); char_Eye(17, -32, 9, o);
    inkLine([[-7, -16], [0, -13 + typing * .2], [7, -16]], .8, dk, 'ink', .7);
    paint(rrPts(-34, 14, 68, 62, 20, 1.1), { wash: mixCol(col, PAL.cream, .35), washOp: 200, fill: col, fillOp: 22, bleed: .08, tex: .3, ink: dk, sw: .9 });
    // 手臂伸向键盘
    inkLine([[-34, 26], [-52, 40 + typing]], .9, dk, 'ink', .6);
    inkLine([[34, 26], [52, 40 - typing]], .9, dk, 'ink', .6);
    paint(ellPts(-54, 42 + typing, 6, 5, 10, .6), { wash: PAL.clayLt, washOp: 220, ink: dk, sw: .5 });
    paint(ellPts(54, 42 - typing, 6, 5, 10, .6), { wash: PAL.clayLt, washOp: 220, ink: dk, sw: .5 });
    pop();
  }

  // ── 角色②：办公小人（WorkBuddy）────────────────────────────────────────
  function buildWorker(cx, cy, sc, t, o = {}) {
    const col = o.col || PAL.teal, dk = PAL.ink;
    const walk = o.walk ? Math.sin(t * 6) : 0;
    push(); translate(cx, cy + bob_(t) * sc); scale(sc);
    // 头
    paint(char_Close(char_Blob(0, -58, 30, 28, 30, 1.2, 11, 3)),
      { wash: mixCol(PAL.clay, PAL.cream, .35), washOp: 225, fill: PAL.clay, fillOp: 26, bleed: .08, tex: .3, ink: dk, sw: .9 });
    char_Eye(-10, -62, 6.5, o); char_Eye(10, -62, 6.5, o);
    inkLine([[-6, -46], [0, -44], [6, -46]], .8, dk, 'inkfine', .6);
    // 身体
    paint(char_Close(rrPts(-28, -30, 56, 58, 18, 1.1)),
      { wash: mixCol(col, PAL.cream, .25), washOp: 215, fill: col, fillOp: 24, bleed: .08, tex: .3, ink: dk, sw: .9 });
    // 抱着的文件
    paint(rrPts(-20, -18, 40, 30, 4, .6), { wash: PAL.cream, washOp: 240, fill: PAL.sky, fillOp: 40, ink: dk, sw: .7 });
    inkLine([[-13, -10], [13, -10]], .6, dk, 'inkfine', .5);
    inkLine([[-13, -3], [9, -3]], .6, dk, 'inkfine', .5);
    // 手臂
    inkLine([[-28, -18], [-24, -8]], .8, dk, 'ink', .6);
    inkLine([[28, -18], [24, -8]], .8, dk, 'ink', .6);
    // 腿
    inkLine([[-12, 28], [-14 + walk * 3, 52]], .9, dk, 'ink', .6);
    inkLine([[12, 28], [14 - walk * 3, 52]], .9, dk, 'ink', .6);
    pop();
  }

  // ── 背景（水彩纸 + 双色氛围）─────────────────────────────────────────────
  function bg(t, o = {}) {
    const leftCol = o.leftCol || PAL.sky, rightCol = o.rightCol || PAL.sap;
    paint(rectPts(-60, -60, W + 120, H + 120), { wash: PAL.paper, washOp: 255, ink: null });
    paint(ellPts(W * .2, H * .3, W * .5, H * .7, 36, 8), { fill: leftCol, fillOp: 80, bleed: .3, tex: .3, ink: null });
    paint(ellPts(W * .8, H * .32, W * .5, H * .7, 36, 8, 1.3), { fill: rightCol, fillOp: 70, bleed: .3, tex: .3, ink: null });
    paint(ellPts(W * .86, H * .15, W * .045, W * .045, 26, 2), { wash: PAL.ochre, washOp: 210, fill: PAL.cream, fillOp: 40, ink: null });
    paint(ellPts(W * .5, H * .98, W * .8, H * .16, 40, 9), { fill: PAL.sap, fillOp: 90, bleed: .25, tex: .5, border: .5, ink: null });
  }

  // ── 中央分隔 VS ─────────────────────────────────────────────────────────
  function drawVS(t, alpha) {
    push();
    const s = 1 + pulse(t) * .06;
    translate(W / 2, H * .46); scale(s);
    paint(char_Close(char_Blob(0, 0, 74, 74, 30, 1.4, 5, 4)),
      { wash: PAL.rose, washOp: 200 * alpha, fill: PAL.rose, fillOp: 40 * alpha, bleed: .15, tex: .3, ink: PAL.ink, sw: 1.1 });
    letter('VS', 0, 0, 64 * s_, PAL.cream, { ink: PAL.ink });
    pop();
  }

  // ── 镜头① 开场（0~6.5s）：路线之争 ──────────────────────────────────────
  function opening(t, lt, dur) {
    bg(t);
    const p = ease(clamp(lt / 1.2, 0, 1));            // 角色淡入
    const q = ease(clamp((lt - 1.0) / 1.6, 0, 1));    // 标题浮现
    if (p > .05) {
      buildBot(W * .25, H * .6, 1.35 * s_, t, { typing: false });
      buildWorker(W * .75, H * .62, 1.35 * s_, t, { walk: false });
    }
    // 旗帜
    if (p > .1) {
      paint(rectPts(W * .25 - 70, H * .22, 140, 46), { wash: PAL.indigo, washOp: 220 * p, fill: PAL.indigo, fillOp: 60, ink: PAL.ink, sw: .8 });
      letter('字节 · Trae', W * .25, H * .22 + 23, 30 * s_, PAL.cream, { ink: PAL.cream });
      paint(rectPts(W * .75 - 70, H * .22, 140, 46), { wash: PAL.teal, washOp: 220 * p, fill: PAL.teal, fillOp: 60, ink: PAL.ink, sw: .8 });
      letter('腾讯 · WorkBuddy', W * .75, H * .22 + 23, 27 * s_, PAL.cream, { ink: PAL.cream });
    }
    // 中央标题逐字浮现
    const title = '两条完全不同的路';
    const n = Math.floor(q * title.length);
    letter(title.slice(0, n), W / 2, H * .12, 64 * s_, PAL.ink, {});
  }

  // ── 镜头② 分屏（6.5~15s）：各干各的活 ───────────────────────────────────
  function split(t, lt, dur) {
    bg(t);
    inkLine([[W / 2, H * .18], [W / 2, H * .92]], 1.2, PAL.ink, 'inkfine', .35);
    drawVS(t, ease(clamp(lt / .8, 0, 1)));
    // 左侧：Trae 写代码
    buildBot(W * .25, H * .58, 1.5 * s_, t, { typing: true });
    for (let i = 0; i < 4; i++) {
      const yy = H * .3 + i * H * .07;
      const wLine = (60 + hash(i * 7 + 3) * 90) * s_;
      paint(rectPts(W * .08, yy, wLine, 14 * s_), { wash: i === 1 ? PAL.violet : PAL.sky, washOp: 170, ink: null });
    }
    letter('写代码', W * .25, H * .82, 44 * s_, PAL.indigo, {});
    // 右侧：WorkBuddy 搬文档
    buildWorker(W * .75, H * .6, 1.5 * s_, t, { walk: true });
    for (let i = 0; i < 3; i++) {
      paint(rrPts(W * .62, H * .8 - i * 12 * s_, 70 * s_, 20 * s_, 4, .6),
        { wash: [PAL.cream, PAL.sky, PAL.rose][i], washOp: 220, ink: PAL.ink, sw: .6 });
    }
    letter('干杂活', W * .75, H * .9, 44 * s_, PAL.teal, {});
  }

  // ── 镜头③ 收尾（15~22s）：并肩 + 提问 ───────────────────────────────────
  function ending(t, lt, dur) {
    bg(t);
    const p = ease(clamp(lt / 1.0, 0, 1));
    buildBot(W * (.3 + .07 * p), H * .6, 1.45 * s_, t, { typing: false });
    buildWorker(W * (.7 - .07 * p), H * .62, 1.45 * s_, t, { walk: false });
    const beat = 1 + pulse(t) * .08;
    push(); translate(W / 2, H * .38); scale(beat * p);
    paint(char_Close(char_Blob(0, 0, 40, 36, 24, 1.3, 9, 3)),
      { wash: PAL.rose, washOp: 220, fill: PAL.rose, fillOp: 50, bleed: .15, tex: .3, ink: PAL.ink, sw: .9 });
    pop();
    const title = '你的工作，是哪一类？';
    const q = ease(clamp((lt - .6) / 1.4, 0, 1));
    const n = Math.floor(q * title.length);
    letter(title.slice(0, n), W / 2, H * .16, 60 * s_, PAL.ink, {});
    if (lt > dur - 1.2) {
      letter('Trae × WorkBuddy', W / 2, H * .92, 30 * s_, PAL.cream, { ink: PAL.cream });
    }
  }

  const t0 = 0, t1 = 6.5, t2 = 15, t3 = 22;
  window.chapter('compare', t0, t3, [
    [t0, opening],
    [t1, split],
    [t2, ending],
  ]);
})();
