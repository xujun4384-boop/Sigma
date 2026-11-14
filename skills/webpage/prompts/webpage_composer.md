# 网页取景合成契约

你要把一张**真实网页截图**做成一段「浏览器里滚动网页 + 逐条批注」的知识点讲解动画。
只输出一份完整的 `index.html`（`<!doctype html>` 开头，`</html>` 结尾），不要解释、不要 markdown 代码块。

---

## 一、给定数据（`scene`）

- `canvas`：画布尺寸（必须写进 `#root` 的 CSS 宽高）
- `page`：页面带截图 `src` 与尺寸 `width/height`；
  这是**一段可滚动的网页长图**，不是整页缩略图，请按 1:1 显示
- `viewport`：建议的浏览器视口尺寸 `width/height` 与 `chrome_height`
- `source`：`title` / `domain` / `url`，用于地址栏与来源标识
- `notes[]`：每处讲解点
  - `index`：序号（从 1 开始）
  - `quote`：网页上的原文（用于批注区展示）
  - `explain`：这句为什么值得看（一句话解释）
  - `mark.rect` / `mark.lines`：**页面坐标**，标注必须落在这些坐标上
  - `anchor_y`：标注中心的页面纵坐标
  - `scroll_y`：推荐滚动偏移（让标注竖向居中）
  - `at` / `until`：该条批注的出现与结束时间（秒）
- `intro`：`scroll_y`（开场滚动位置，通常 0）与 `end`（片头结束时间）
- `style`：整体视觉基调

坐标一律**原样使用**，不得估算、偏移或缩放；单位 CSS 像素。

---

## 二、画面组成

画面里要有两样东西：

1. **一个模拟浏览器窗口**：顶部是浏览器 chrome（三色圆点、地址栏显示真实 `source.url` 的域名与路径），
   下面是网页视口。网页在视口内 1:1 显示，靠纵向滚动定位。
2. **批注区**：显示当前这条 `notes` 的序号 + 原文摘录（`quote`）+ 解释（`explain`）。

### 版式：自由，但只能用「左右并排」或「浮层」

- 浏览器窗口可以在**左**，批注在右；也可以反过来：批注在左，浏览器在右。
- 也可以做**接近全屏的浏览器 + 浮层批注**（批注卡片贴在网页旁边，可用细线指向高亮处）。
- **不要上下堆叠**（浏览器在上、批注在下这种排法不好看，禁止）。
- 浏览器窗口应该有圆角、细描边、轻微投影，像一个真实的窗口，而不是一块贴着画布边缘的图片。

---

## 三、结构（可照此骨架）

```html
<div id="root" data-composition-id="root" data-start="0" data-duration="10"
     data-width="1920" data-height="1080" style="overflow:hidden">
  <section class="clip stage" data-start="0" data-duration="10">

    <!-- 浏览器窗口：位置/尺寸由你定 -->
    <div id="browser" style="position:absolute;left:80px;top:90px;width:1240px;height:890px;border-radius:14px;overflow:hidden">

      <!-- chrome：圆点 + 地址栏 -->
      <div id="chrome" style="height:56px;/* … */">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
        <div id="url">github.blog/octoverse-2024</div>
      </div>

      <!-- 视口：滚动发生在这里 -->
      <div id="page-viewport" style="position:relative;overflow:hidden;height:834px">
        <div id="page-stage" style="position:relative;width:1920px;height:6000px;overflow:hidden">
          <img id="page-image" src="assets/page.png"
               style="position:absolute;left:0;top:0;width:1920px;height:6000px">

          <!-- 每个 notes 一条，坐标用 mark.rect（页面坐标），必须是 #page-stage 的直接子元素 -->
          <div class="mark" data-mark="m1"
               style="position:absolute;left:476px;top:7472px;width:503px;height:57px;box-sizing:border-box;padding:0;border:0">
            <!-- 荧光笔、下划线、圈选、箭头… 自由 -->
          </div>
        </div>
      </div>
    </div>

    <!-- 批注区：位置自由（左/右/浮层），显示序号 + 原文 + 解释 -->
    <aside id="notes" style="position:absolute;/* … */">
      <div class="note" data-note="m1">
        <div class="idx">01</div>
        <p class="quote">India 28% YoY &gt;17M</p>
        <p class="explain">亚太增长最快的市场，一年新增 1700 万开发者</p>
      </div>
    </aside>

  </section>
</div>
```

硬规则：

1. `#page-stage` 宽高必须等于 `page.width/height`，`overflow:hidden`，`position:relative`。
2. 每个 `notes[]` 必须有对应的 `data-mark="<id>"` 元素：**`#page-stage` 的直接子元素**、`position:absolute`、
   left/top/width/height 与 `mark.rect` **逐像素一致**（闸门会实测，误差 >2px 直接打回），
   `box-sizing:border-box;padding:0;border:0`。装饰只能放进它的子元素。
3. 标注必须放在页面图层里（跟着网页一起滚动），**不要**放到画布层或批注区里。
4. 滚动只作用于 `#page-stage`：`gsap.to("#page-stage", { y: -scroll_y })`。
   **不要给 `#page-stage` 加 scale**（会糊，也会让标注坐标失准）。
5. 根元素、`.clip.stage`、浏览器窗口、`#page-viewport`、`#page-stage` 都要 `overflow:hidden`。
6. **第一帧就要有画面**：页面图从 t=0 可见，不要从纯黑/纯白空帧开始。

---

## 四、节奏（宁慢勿快）

`pacing` 给了三档建议值：`scroll`（滚动时长）、`enter`（批纳入场时长）、`exit_lead`（提前淡出）。

1. **开场**（0s）：滚到 `intro.scroll_y`（一般是页面顶部），浏览器窗口淡入/轻推，让观众看清这是真网页。
2. **逐条讲解**：对每个 `notes[i]`：
   - 在 `at - pacing.scroll` 开始滚动到 `scroll_y`，**滚动一到位就停下**，用 `ease: "power2.inOut"`；
   - **滚完再入场**：滚动结束后才让批注卡片出现，不要边滚边弹字；
   - 入场用 `pacing.enter`（约 0.9s）：卡片整体淡入 + 轻微上移，内部按「序号 → 原文 → 解释」顺序 stagger，
     每段 0.4~0.5s，让观众看清顺序；
   - 高亮可以和批注同时出现，也可以晚 0.1~0.2s，形成"指过去→亮起来"的关系。
3. **静止可读**：批注落位后必须**完全静止 `min_read` 秒**（每条 note 自带这个数值，通常 1.4~3.2s）。
   这段时间里不要滚动、不要有其他补间在跑，让观众读完。
4. **退场**：在下一条 `at - pacing.exit_lead` 时，把当前标注与批注淡出（0.3s 左右），再开始下一次滚动。
   不要两条批注同时出现抢注意力。
5. 最后一条保持到片尾，不提前黑屏、不要收场动画。

> **常见的"太快"错误**：批注 0.2s 闪入、边滚边弹、刚落位就开始滚下一条、三段文字同一时刻全出现。
> 以上都算不合格：入场少于 0.6s、或 `min_read` 期间还有动画在跑，请重做这段。

---

## 五、标注与批注的视觉（自由发挥）

- **标注**：荧光笔、下划线、手绘圈选、箭头、序号徽章、标签气泡，任选组合。
  逐行高亮用 `mark.lines` 里的每个矩形，避免一个大色块盖住整段。
  不要遮住被标注的原文本身（半透明荧光笔压在文字底部可以）。
- **批注**：序号 + 原文摘录 + 解释，可以配细线/引线指向对应高亮。
  `quote` 太长时只展示其中最关键的一段，**不要改写原文**。
- `scene.style` 决定整体基调（配色/线条/质感），页面截图本身**不要改色、不要重绘**。
- 底部约 12% 留白给字幕，这一带不放正文内容。

---

## 六、HyperFrames 契约（违反会被闸门拒绝）

```html
<div id="root" data-composition-id="root" data-start="0" data-duration="10"
     data-width="1920" data-height="1080" style="overflow:hidden">
  <section class="clip stage" data-start="0" data-duration="10"> ... </section>
</div>
```

页面级样式至少要有（宽高换成实际数值）：

```css
html, body { margin: 0; background: #0b0b0f; font-family: system-ui, sans-serif; }
#root { position: relative; width: 1920px; height: 1080px; overflow: hidden; }
.clip.stage { position: absolute; inset: 0; overflow: hidden; }
```

- 所有带 `data-start` 的元素必须有合法 `data-duration`，时间范围落在 `[0, 总时长]`；至少一个片段覆盖整片（误差 ≤2s）。
- 注册一条 **paused** 时间轴：先 `window.__timelines = window.__timelines || {}`，
  再 `window.__timelines["root"] = gsap.timeline({paused:true})`；所有动画挂在它上面，位置参数写绝对秒数。
- GSAP 用本地 `gsap.min.js`：`<script src="gsap.min.js"></script>`，**不要**写 CDN 外链。
- 禁止：`fetch()` / `XMLHttpRequest` / `WebSocket`、`Math.random()`、`Date.now()`、`performance.now()`、`setInterval`、`repeat:-1`、CSS `@keyframes` / `animation`。
- 中文使用 `font-family: system-ui, sans-serif;`，不要写具体中文字体名。
- 只用相对路径引用 `assets/` 下的图片，不要引用任何网络地址。

---

## 七、输出前自查

- `#root` 有明确 CSS 宽高；第一帧就能看到浏览器窗口与网页。
- 浏览器窗口与批注区是**左右并排**或**浮层**关系，没有上下堆叠。
- `#page-stage` 尺寸正确；每个 `data-mark` 是它的直接子元素，几何与 `mark.rect` 一致。
- 滚动只对 `#page-stage` 做 translateY，没有 scale。
- 每条批注都有序号、原文摘录、解释；时间落在对应 `at`/`until` 区间。
- 批注入场不短于 `pacing.enter`，落位后 `min_read` 秒内画面完全静止。
- 底部 12% 没有正文内容。
