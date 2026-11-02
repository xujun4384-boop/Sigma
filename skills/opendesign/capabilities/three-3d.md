# T — three.js 真 3D 原语（WebGL）

库已在项目目录：`<script src="three.min.js"></script>` → 全局 `window.THREE`（r160 UMD 构建，**不是** ESM，别写 `import`）。
`data-track-index` / `.clip` 的显隐照旧由 `data-start` 控制；3D 只负责**画布里的内容**。

## 硬约束（不遵守必然翻车）

1. **逐帧 seek 驱动**。渲染器不会给你 `requestAnimationFrame` 循环，它只把 GSAP 时间轴 seek 到某个时刻。
   所以必须是：`tl.to(clockObj, {…, onUpdate: () => draw(clockObj.t)})`，`draw` 用 `t` 算出**每一帧的完整状态**。
   绝不在 `draw` 里读墙钟、累积增量（`+=`）或调 `Math.random()`——那样同一时刻两次渲染像素不同，确定性闸门会拦下。
2. **确定性伪随机**：需要散布时用固定种子的线性同余，不要 `Math.random()`。
   ```js
   let seed = 20261019;                              // 固定种子，换成别的常数也行，但每次渲染必须同一个
   const rand = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
   ```
3. **软件渲染成本**：渲染机可能没有 GPU，走 SwiftShader 软渲染，比真实 GPU 慢一到两个数量级。
   - 关阴影（`shadowMap.enabled = false`）、不加后期（`EffectComposer` 一律不用）、不用透明排序复杂的材质
   - 几何细分要低：`TorusKnotGeometry` 段数 ≤ 96，`SphereGeometry` ≤ 32×24；顶点总数 ≤ 3 万
   - `renderer.setPixelRatio(1)`，**不要**用 `window.devicePixelRatio`
   - 3D 只做**一两个主角镜头**（全片 10~25% 时长），其余场景用 CSS 层
4. **必须能降级**：WebGL 可能不可用。开头探测，失败就切到 CSS 3D 版本（见 C09~C12），
   否则 `new THREE.WebGLRenderer()` 抛错 → 页面报错 → 整片被闸门拒掉。

```js
const HAS_GL = (() => { try {
  const c = document.createElement('canvas');
  return !!(c.getContext('webgl') || c.getContext('experimental-webgl'));
} catch (e) { return false; } })();
```

---

## 完整可用模板

照抄改数值即可；`W/H/DUR/START` 换成实际的画布宽高、总时长、该场次起点（秒）。

```html
<div class="clip stage" id="s3" data-start="8" data-duration="6" data-track-index="3">
  <canvas id="gl"></canvas>
  <!-- 降级层：WebGL 不可用时顶上，平时隐藏 -->
  <div class="fallback3d" style="display:none">
    <div class="p3d"><div class="card"><!-- 用 CSS 3D 复刻同一个构图 --></div></div>
  </div>
</div>
```
```css
#s3{position:absolute;inset:0;overflow:hidden;background:#05060b}
#s3 #gl{position:absolute;inset:0;width:100%;height:100%;display:block}
```

```js
function init3D(W, H) {
  const canvas = document.querySelector("#gl");
  const renderer = new THREE.WebGLRenderer({canvas, antialias:false, alpha:true});
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  renderer.shadowMap.enabled = false;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, W / H, 0.1, 100);

  // 三点布光：主光冷白 + 两盏异色点光，是最低成本的"高级感"
  scene.add(new THREE.AmbientLight(0xffffff, 0.35));
  const key = new THREE.DirectionalLight(0xe8f0ff, 1.4); key.position.set(2, 6, 4);  scene.add(key);
  const p1 = new THREE.PointLight(0x7c5cff, 90, 18); p1.position.set(5, 2, 5);   scene.add(p1);
  const p2 = new THREE.PointLight(0x22d3ee, 70, 18); p2.position.set(-5, -1, 4); scene.add(p2);

  // 主体：低细分金属结。金属感来自环境贴图，不是来自材质本身
  const knot = new THREE.Mesh(
    new THREE.TorusKnotGeometry(0.95, 0.30, 96, 24),
    new THREE.MeshStandardMaterial({color: 0xdfe6ff, metalness: 1, roughness: 0.12, envMapIntensity: 1.6}),
  );
  scene.add(knot);

  // 线框外壳：拉开"科技感"的反差，反向自转
  const shell = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1, 1),
    new THREE.MeshBasicMaterial({color: 0x6ea8ff, wireframe: true, transparent: true, opacity: 0.28}),
  );
  shell.scale.setScalar(1.95);
  scene.add(shell);

  // 确定性星尘：LCG 种子生成坐标，生成后不再变动
  const COUNT = 260, pos = new Float32Array(COUNT * 3);
  let seed = 20261019;
  const rand = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  for (let i = 0; i < COUNT; i++) {
    pos[i*3] = (rand() - .5) * 14; pos[i*3+1] = (rand() - .5) * 7; pos[i*3+2] = (rand() - .5) * 14;
  }
  const dust = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(pos, 3)),
    new THREE.PointsMaterial({size: 0.028, color: 0x9fd0ff, transparent: true, opacity: 0.75, sizeAttenuation: true}),
  );
  scene.add(dust);

  // 程序化环境贴图：一块 canvas 就能让金属有反射，不需要任何素材文件
  const ec = document.createElement("canvas"); ec.width = 256; ec.height = 128;
  const cx = ec.getContext("2d");
  const gr = cx.createLinearGradient(0, 0, 0, 128);
  gr.addColorStop(0, "#243a80"); gr.addColorStop(.42, "#7fa4ff"); gr.addColorStop(.55, "#e8f0ff");
  gr.addColorStop(.75, "#2a3358"); gr.addColorStop(1, "#0a0d1a");
  cx.fillStyle = gr; cx.fillRect(0, 0, 256, 128);
  const env = new THREE.CanvasTexture(ec);
  env.mapping = THREE.EquirectangularReflectionMapping;
  scene.environment = env;

  scene.fog = new THREE.Fog(0x05060b, 5.5, 18);
  const grid = new THREE.GridHelper(22, 44, 0x2b4070, 0x141e36);
  grid.position.y = -1.35;
  scene.add(grid);

  // draw(t)：t 为该场次**相对**秒数。全部状态由 t 纯函数算出，无累积、无随机
  return function draw(t) {
    camera.position.set(Math.sin(t * 0.32) * 4.9, 2.35 + Math.sin(t * 0.47) * 0.35, Math.cos(t * 0.32) * 4.9);
    camera.lookAt(0, 0.15, 0);
    knot.rotation.set(t * 0.5, t * 0.85, t * 0.2);
    shell.rotation.set(-t * 0.22, t * 0.16, 0);
    dust.rotation.y = t * 0.06;
    renderer.render(scene, camera);
  };
}

const W = 1920, H = 1080, DUR = 20, START = 8, CLIP_DUR = 6;
let draw = null;
if (HAS_GL) {
  try { draw = init3D(W, H); draw(0); }      // 先画一帧：时间轴还没 seek 时画布不能空着
  catch (e) { draw = null; }                 // 探测通过但初始化仍可能失败，兜住它
}
if (!draw) {                                  // 降级：切到 CSS 3D 版本（C09/C10）
  document.querySelector("#gl").style.display = "none";
  document.querySelector(".fallback3d").style.display = "";
}

const clock = {t: START};                     // 只用一个哑对象承载时间
tl.to(clock, {
  t: START + CLIP_DUR, duration: CLIP_DUR, ease: "none",  // 只覆盖本场次窗口，别拉满全片
  onUpdate() { if (draw) draw(Math.max(0, clock.t - START)); },
}, START);

if (!draw) {
  tl.fromTo(".fallback3d .card", {rotationY: -34, z: -360, opacity: 0},
    {rotationY: 6, z: 0, opacity: 1, duration: 1.6, ease: "power3.out"}, START + 0.3);
}
```

要点：
- 哑补间的 `onUpdate` 是**唯一**的取帧通道；`draw(0)` 是它的补丁，别省。
- 补间的 `duration` 与位置参数都用**本场次**的窗口（`START` / `CLIP_DUR`），不要用全片时长——
  否则 6 秒的镜头会摊成一整条缓慢动画。`draw` 内部再减去 `START`，图像才与场次对齐。
- canvas 用 CSS `width/height:100%`，`setSize(W,H,false)` 的第二参给 `false`（不让 three 改 CSS 尺寸）。

---

## 可替换的配方（自由组合）

- **T01 金属结 + 环境反射**：见上。想换形：`SphereGeometry / IcosahedronGeometry(1,3) / TubeGeometry`。
- **T02 线框外壳**：见上。`wireframe:true` + `opacity:0.2~0.35`，反向自转制造层次。
- **T03 星尘粒子**：见上。`sizeAttenuation:true` 才有纵深；颜色取冷色，别用纯白（会糊成一片）。
- **T04 相机环绕**：`sin/cos` 轨道 + `lookAt`，周期 ≥ 20s，太快会晕。
- **T05 雾 + 地面网格**：`Fog` + `GridHelper`，把 3D 物体锚在"空间"里而不是浮在虚空。
- **T06 色散/发光**：不用后期。用两盏异色点光从相对方向打，或用第二个半透明 Mesh 做辉光。
- **T07 形态过渡**：换几何体只能"跳变"（没有 MorphTarget，除非自带 `morphTargets` 的模型）。
  想做"变形"就改用 **C09~C12 的 CSS 3D**＋遮罩揭示（C24），比在 WebGL 里做 morph 便宜得多。

## 何时**不要**用 three.js

- 主体是文字排版/数据图表 → 用 CSS + SVG（C13~C21），清晰度、可读性、渲染速度全面更好。
- 需要 3 个以上 3D 镜头 → 软渲染会超时；改成 1 个真 3D + 其余用 CSS 3D 假纵深。
- 画面主要靠精确文字对齐 → WebGL 里的文字要么贴图要么 3D 文字，都不如 DOM 可控。
