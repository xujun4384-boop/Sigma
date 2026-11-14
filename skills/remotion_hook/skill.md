# remotion_hook - Remotion 开场钩子引擎

> 导演组内部引擎：只做第一段开场钩子，不接管整片。
> 默认让 LLM 自由写 TSX，再用视觉闸门检查；模板只作为兜底。
> **时长由导演给定：开场钩子至少 10 秒**（不再固定 3~5 秒），动画要铺满整段，不要提前静止。

## 模式

| mode | 行为 |
|---|---|
| `auto`（默认） | 先自由发挥：LLM 写 TSX → 渲染 → 视觉闸门；不过回灌重写，最多 3 次；仍不过回退模板 |
| `freeform` | 只走自由发挥，失败直接返回错误 |
| `template` | 只走 title / kinetic / ui 模板 |

## 自由发挥

- LLM 只写 `project/src/freeform/HookImpl.tsx`，导出 `GeneratedHook`。
- 允许的 import：`react`、`remotion`、`@remotion/effects/*`、`@remotion/motion-blur`、
  `@remotion/shapes`、`@remotion/paths`、`./types`。
- 禁止：`fetch` / `XMLHttpRequest` / `require` / 动态 import / `eval` / `new Function` /
  `process` / `fs` / `child_process` / `Date.now` / `Math.random` / `setTimeout` /
  `setInterval` / `requestAnimationFrame` / `window` / `document` / 外部 URL / CSS 动画。
- 静态检查通过后渲染；渲染错误或视觉问题会回灌给 LLM 重写。
- **只做 2D**：运行环境是 DOM / SVG / Canvas 2D，没有 three.js / WebGL，import 白名单也不含它们。
  需要真 3D 开场时不要在这里硬写——交给导演组改用 `blender` 或 `opendesign` 的 three.js。
- 视觉闸门：3 帧拼图交给主多模态 LLM，按空帧、可读性、裁切、覆盖、钩子力打分；
  6 分及以上且无硬伤才通过。视觉模型不可用时退化为“空白/纯色检测”。

## 模板兜底

| 模板 | 画面 | 适合的 hook.type |
|---|---|---|
| `title` | 极光光斑 + light leak + 扫描线 + 胶片颗粒 + 逐字标题 + 镜头缓推 | question / sound / object / handwritten |
| `kinetic` | 拖影条带 + 运动模糊 + 色差 + 光轨 + 动态大字 | result / countdown |
| `ui` | 仿浏览器/后台 UI + 统计卡 + 曲线 + 侧栏 | ui / wrongway / contrast / map |

## 契约

- 时长由导演给定（≥3 秒，开场通常 10 秒）；自由发挥与模板都不使用 `Math.random`/`Date.now`/CSS 动画。
- 时长在 Remotion 工程里是**动态元数据**（`calculateMetadata` 读取 duration），不再被夹到 3~5 秒。
- 字体使用系统字体，不联网下载。
- 无音频；旁白/音效仍由导演组负责。
- 自由发挥失败回退模板；模板再失败，导演组降级到 `opendesign`，不整片崩。

## 首次运行

`project` 是自包含 Remotion 工程。首次渲染会自动执行 `npm install`（可能需要几分钟）；
需要 Node.js 20+。之后复用 `project/node_modules`。
