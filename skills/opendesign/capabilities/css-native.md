# C — CSS 原生动效原语（零依赖）

"高级感"来自**叠加的视觉层**，不是动画数量。顺序永远是：先铺满氛围/质感层，再让内容干净地入场。
下面每条都是可直接改写使用的代码，编号用于在别处引用。

## 使用约定

1. **动画一律由 GSAP 时间轴驱动**。禁止 CSS `@keyframes` / `transition`：渲染器是**逐帧 seek**的，
   墙钟驱动的 CSS 动画会错帧，且同一时刻两次渲染像素不一致，会被确定性闸门直接拦下。
2. 可 seek 属性白名单（渲染链路保证）：
   `opacity  x  y  scale  scaleX  scaleY  rotation  width  height  visibility`
   以及 GSAP 按数值解析的字符串属性：
   `filter(blur/brightness/saturate)  letterSpacing  boxShadow  textShadow  backgroundColor  backgroundPosition  strokeDashoffset  borderRadius  color  opacity`
   3D 旋转用 GSAP 属性名 `rotationX / rotationY / rotationZ`，**不要写 `rotateY(30deg)` 这种 CSS 函数**；
   透视写在元素的 `transformPerspective` 或父级的 CSS `perspective` 上。
3. 确定性：不用 `Math.random()` / `Date.now()` / `performance.now()`。需要散布时用固定种子（见 C05、C16）。
4. 每个叠加层都写 `pointer-events:none`，避免层与层互相吃事件。
5. 目标坐标一律写成画布比例（`%` / `vw` / `calc`），不要把某一分辨率的像素写死。

---

## 一、氛围底（铺在内容之下，决定"像不像宣传片"）

### C01 氛围光场
多层 `radial-gradient` 光斑 + `blur` + `mix-blend-mode:screen`，让暗底有"空气感"。
替代纯色背景——这一步是摆脱 PPT 感最廉价的改法。

```html
<div class="env">
  <div class="blob" style="left:8%;  top:16%; width:62%; height:56%;
       background:radial-gradient(closest-side, rgba(58,92,235,.58), transparent 100%)"></div>
  <div class="blob" style="left:56%; top:10%; width:56%; height:52%;
       background:radial-gradient(closest-side, rgba(120,66,220,.44), transparent 100%)"></div>
  <div class="blob" style="left:24%; top:58%; width:52%; height:50%;
       background:radial-gradient(closest-side, rgba(40,190,200,.28), transparent 100%)"></div>
</div>
```
```css
.env{position:absolute;inset:0;overflow:hidden}
.env .blob{position:absolute;border-radius:50%;filter:blur(58px);mix-blend-mode:screen;pointer-events:none}
```
```js
// 整片缓慢漂移：用正弦缓动走完全程，无随机、可 seek
tl.fromTo(".env .blob", {xPercent:-4, yPercent:-3, scale:1.06},
  {xPercent:4, yPercent:3, scale:1.0, duration:DUR, ease:"sine.inOut"}, 0);
```

### C02 网格底纹
双向 `linear-gradient` 画 1px 网格，给光场加"空间坐标"。密度按画布宽度取 60~120px。

```css
.grid{position:absolute;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(255,255,255,.028) 1px,transparent 1px);
  background-size:110px 110px}
```
```js
tl.fromTo(".grid", {backgroundPosition:"0px 0px"}, {backgroundPosition:"0px -110px", duration:DUR, ease:"none"}, 0);
```

### C03 暗角
`radial-gradient` 四角压暗，把视线收到画面中心。几乎每个场景都该有一层。

```css
.vig{position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 38%, rgba(0,0,0,.55) 78%, rgba(0,0,0,.92) 100%)}
```

### C04 胶片颗粒
内联 SVG `feTurbulence` 做静态噪声纹理，再用 `steps` 抖动位置——比 `@keyframes` 更可控且确定。
颗粒是"实拍感"的关键，透明度 0.08~0.16、混合模式 `overlay`。

```css
.grain{position:absolute;inset:-20%;width:140%;height:140%;pointer-events:none;
  opacity:.14;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E")}
```
```js
// steps 抖动：每秒约 12~20 次跳变，用 GIF 级的颗粒闪动换取确定性
tl.to(".grain", {backgroundPosition:"-8% -6%", duration:DUR, ease:"steps(300)"}, 0);
```

### C05 扫描线
`repeating-linear-gradient` 细线，缓慢纵向位移，做屏幕/监视器质感。透明度 ≤0.1。

```css
.scan{position:absolute;inset:0;pointer-events:none;opacity:.09;mix-blend-mode:overlay;
  background:repeating-linear-gradient(180deg, rgba(255,255,255,.55) 0 1px, transparent 1px 3px)}
```
```js
tl.fromTo(".scan", {backgroundPositionY:"0px"}, {backgroundPositionY:"-120px", duration:DUR, ease:"none"}, 0);
```

### C06 玻璃面板
`backdrop-filter:blur` + 1px 亮边 + 内高光 + 大范围投影，做"悬浮界面/玻璃卡片"。
配合 C01 光场时，卡片会透出背后的光，这是纯色卡片给不出的层次。

```css
.glass{position:relative;border-radius:22px;overflow:hidden;
  background:linear-gradient(160deg, rgba(255,255,255,.075), rgba(255,255,255,.028) 46%, rgba(255,255,255,.05));
  border:1px solid rgba(255,255,255,.14);
  backdrop-filter:blur(26px);
  box-shadow:0 60px 160px rgba(3,6,20,.75), inset 0 1px 0 rgba(255,255,255,.16)}
.glass::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(115deg, rgba(255,255,255,.14) 0%, rgba(255,255,255,0) 34%, rgba(255,255,255,0) 72%, rgba(255,255,255,.07) 100%)}
```

### C07 辉光
同一颜色的 `text-shadow` / `box-shadow` 叠 2~3 层（模糊半径递增），比单层阴影更像发光体。

```css
.glow{color:#f5f8ff;text-shadow:0 0 28px rgba(110,140,255,.5), 0 0 90px rgba(110,140,255,.35)}
.chip{box-shadow:0 0 22px rgba(107,140,255,.35)}
```

### C08 光扫
一条斜向白色渐变带，用 `x` 扫过画面，`mix-blend-mode:screen`。用于转场或给静止画面加"呼吸"。

```html
<div class="sweep"></div>
```
```css
.sweep{position:absolute;top:-30%;bottom:-30%;width:38%;pointer-events:none;
  background:linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.5) 50%, rgba(255,255,255,0) 100%);
  filter:blur(26px);mix-blend-mode:screen;transform:skewX(-14deg)}
```
```js
tl.fromTo(".sweep", {x:-W*0.6, opacity:0},
  {x:W*0.9, opacity:1, duration:1.4, ease:"power2.inOut"}, 0.6);
```

---

## 二、三维与景深（"准 3D"，不需要 WebGL）

### C09 透视舞台
父级给 `perspective`，子级用 `rotationX/Y` + `translateZ` 摆出真实纵深。

```css
.p3d{position:absolute;inset:0;perspective:1400px;perspective-origin:50% 46%;transform-style:preserve-3d}
.card{transform-style:preserve-3d}
```
```js
// 一个"从深处推近并摆正"的镜头感入场
tl.fromTo(".card", {rotationY:-38, z:-420, opacity:0},
  {rotationY:0,   z:0,    opacity:1, duration:1.1, ease:"power3.out"}, 0.3);
```

### C10 卡片倾角
静止状态下的小角度 `rotationY/rotationX`（±6~14°），会让平面元素立刻有厚度。

```js
tl.fromTo(".card", {rotationY:14, rotationX:6}, {rotationY:5, rotationX:-3, duration:DUR, ease:"sine.inOut"}, 0);
```

### C11 多层视差
按"远→近"分层，用不同速度平移同一方向，制造镜头推移。远层慢、近层快。

```js
tl.fromTo(".far",  {x:0, scale:1.00}, {x:-40, scale:1.02, duration:DUR, ease:"none"}, 0);
tl.fromTo(".mid",  {x:0, scale:1.00}, {x:-120, scale:1.05, duration:DUR, ease:"none"}, 0);
tl.fromTo(".near", {x:0, scale:1.00}, {x:-260, scale:1.10, duration:DUR, ease:"none"}, 0);
```

### C12 赛博地平线
`rotateX(60~72deg)` 的网格 + 长距离平移，做出向消失点收拢的地面。

```css
.floor{position:absolute;left:-50%;right:-50%;bottom:-12%;height:62%;
  transform:rotateX(68deg);transform-origin:50% 100%;opacity:.5;
  background-image:linear-gradient(rgba(120,170,255,.22) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(120,170,255,.22) 1px,transparent 1px);
  background-size:90px 90px;
  -webkit-mask-image:linear-gradient(180deg, transparent, #000 60%);mask-image:linear-gradient(180deg, transparent, #000 60%)}
```
```js
tl.fromTo(".floor", {backgroundPositionY:"0px"}, {backgroundPositionY:"1800px", duration:DUR, ease:"none"}, 0);
```

---

## 三、文字（最容易露怯的地方）

### C13 逐字入场
把标题按字拆成 `<span>`（JS 循环生成，确定），再 `stagger` 上浮 + 模糊收敛。
**关键**：水平 `letterSpacing` 由紧到松、`blur` 由大到 0 与位移同步衰减——这才是"速度感"。
不要用 `SplitText` 之类的插件，自己拆字更可控。

```js
const chars = [...document.querySelectorAll("[data-split]")];
chars.forEach(el => { el.innerHTML = [...el.textContent].map(c => `<span class="ch">${c}</span>`).join(""); });
tl.fromTo(".ch", {y:64, opacity:0, filter:"blur(14px)"},
  {y:0, opacity:1, filter:"blur(0px)", duration:0.85, stagger:0.045, ease:"power3.out"}, 0.5);
```
```css
.ch{display:inline-block;will-change:transform,filter}
```

### C14 字距展开
eyebrow / 小标题的字距由紧到松，是最省力的"设计感"信号。

```js
tl.fromTo(".eyebrow", {letterSpacing:"0.04em", opacity:0},
  {letterSpacing:"0.34em", opacity:1, duration:1.0, ease:"power2.out"}, 0.2);
```

### C15 渐变字与空心字
`background-clip:text` 做金属/渐变字；`-webkit-text-stroke` 做空心字。

```css
.metal{background:linear-gradient(96deg,#dfe8ff 0%,#8fa8ff 38%,#e9f2ff 62%,#6b8cff 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.hollow{-webkit-text-stroke:2px rgba(190,214,255,.85);color:transparent}
```

### C16 数值滚动
数字用"更小步长"的定值 tween 驱动 `textContent`，配合 `tabular-nums` 防宽度抖动。

```js
const st = {v: 0};
tl.to(st, {v: 4.2, duration:1.6, ease:"power2.out",
  onUpdate(){ box.textContent = st.v.toFixed(1); }}, 0.6);
```
```css
.num{font-variant-numeric:tabular-nums}
```

### C17 运动模糊
元素高速位移时叠 `blur`（与位移同步衰减），或复制 2~3 层低透明度残影错位叠放。
残影法更接近真实快门：把同一元素复制若干份，`x` 依次滞后几像素、透明度递减。

```js
// 单层近似：位移 + 模糊同源驱动
tl.fromTo(".fast", {x:-W*0.35, filter:"blur(18px)"},
  {x:W*0.35, filter:"blur(0px)", duration:1.0, ease:"power2.inOut"}, 2.0);
```

---

## 四、图形与数据

### C18 路径生长
SVG 路径 `pathLength="1"` + `strokeDasharray="1"`，只 tween `strokeDashoffset` 1→0。
比 `DrawSVG` 插件更稳（不引插件）。

```html
<svg viewBox="0 0 1000 400" width="1000" height="400">
  <path class="line" d="M0 360 L200 300 L400 320 L600 180 L800 120 L1000 40"
        fill="none" stroke="#8fb4ff" stroke-width="5" stroke-linecap="round"
        pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>
</svg>
```
```js
tl.fromTo(".line", {strokeDashoffset:1}, {strokeDashoffset:0, duration:1.6, ease:"power2.inOut"}, 2.4);
```

### C19 环形进度
同上，加 `transform:rotate(-90 cx cy)` 让起点在 12 点方向。

```js
tl.fromTo(".ring", {strokeDashoffset:1}, {strokeDashoffset:0.25, duration:1.2, ease:"power2.out"}, 3.0);
```

### C20 柱状/条状生长
`scaleY` 0→1，`transformOrigin:bottom`。整组用 `stagger` 造出波浪。
**CSS 里不要预写 `transform:scaleY(0)`**，初始态交给 GSAP（否则内联 transform 会打架）。

```js
tl.fromTo(".bar", {scaleY:0, transformOrigin:"bottom center"},
  {scaleY:1, duration:0.7, stagger:0.05, ease:"back.out(1.6)"}, 5.0);
```

### C21 条带穿梭
细长条（渐变两端透明）+ 同色辉光，快速横向掠过。两三根就够，多了变花。

```css
.streak{position:absolute;width:10px;border-radius:5px;
  background:linear-gradient(180deg, transparent 0%, #5b8cff 22%, #ffffff 50%, #5b8cff 78%, transparent 100%);
  box-shadow:0 0 26px #5b8cff}
```
```js
tl.fromTo(".streak", {x:-W*0.5, opacity:0}, {x:W*1.1, opacity:1, duration:1.6, ease:"power2.inOut"}, 1.0);
```

---

## 五、转场（克制使用：全片最多 1 个全屏转场，其余交叉淡化）

场景边界默认只用约 0.75 秒交叉淡化或硬切。**全片最多一个**全屏转场层，不要在每个边界循环使用。

转场若用全屏层，必须 `z-index` 高于内容（`data-track-index` 不控制层级，别指望它）；
但**禁止整屏纯色横扫/擦除**，转场应作用在局部内容元素上，否则看起来像页面刷新。

### C22 色块横扫
主色块 `scaleX` 展开→从另一侧收起，细线同时横穿。

```js
tl.fromTo(".wipe .bar", {scaleX:0, transformOrigin:"left center"},
  {scaleX:1, duration:0.42, ease:"power3.inOut"}, TS);
tl.to(".wipe .bar", {scaleX:0, transformOrigin:"right center", duration:0.42, ease:"power3.inOut"}, TS+0.42);
tl.fromTo(".wipe .rule", {x:-40, opacity:0}, {x:W+40, opacity:1, duration:0.84, ease:"power2.inOut"}, TS);
```

### C23 闪白 / 压黑
全屏层透明度脉冲，最通用也最"剪辑感"的转场。

```js
tl.fromTo(".flash", {opacity:0}, {opacity:1, duration:0.12, ease:"power2.in"}, TS);
tl.to(".flash", {opacity:0, duration:0.4, ease:"power2.out"}, TS+0.12);
```

### C24 遮罩揭示
元素外面套 `overflow:hidden` 的框，tween 框内元素的 `x`/`width`/`scaleX`，做出"擦除/揭示"。
比 `clip-path` 动画更稳（`clip-path` 的插值支持不保证）。
只包住局部内容元素，**不要**套在整屏容器上做全屏擦除。

```js
// 左→右擦除：内层整体移动一首屏宽度
tl.fromTo(".reveal > .inner", {xPercent:-100}, {xPercent:0, duration:0.9, ease:"power3.out"}, TS);
```
