# sfx - 音效组（程序合成，无外部素材）

> 给视频加**短音效**：哔、duang、whoosh、盖章、金币、故障、重击等。
> 与 BGM 无关：BGM 是铺满全片的音乐床，sfx 是带时间点的一次性事件。

**核心特点**
- **不需要 API Key、不依赖外部素材**：全部由 numpy 程序合成，无版权问题。
- **配方化**：30 个核心配方，分 6 个风格家族；代码只做 DSP，选择由导演按语义决定。
- **可复现**：同一配方 + 同一参数 + 同一种子，输出完全一致。
- **统一响度**：输出约 -22 dB RMS、峰值 ≤ 0.95，混音时只需按 `level` 压音量。

## 用法

### 查看目录
```
sfx(action="list")
```

### 生成一个音效
```
sfx(recipe="cartoon.duang")
sfx(recipe="mg.whoosh", output_path="video_work/demo/sfx/whoosh.wav")
sfx(recipe="cartoon.boing", params={"pitch": -2, "brightness": 0.2, "seed": 7})
```

### 参数
| 参数 | 说明 |
|---|---|
| `recipe` | 配方 id，必填（见目录） |
| `output_path` | 输出 wav；留空落到 `video_work/<project>/sfx/` |
| `project` | 默认产物目录的项目名 |
| `params.pitch` | 半音，-12~12；正=更高更短，负=更低更长 |
| `params.brightness` | -1~1；负=更暗，正=更亮 |
| `params.seed` | 轻微音色扰动；同种子可复现 |
| `seed` | 顶层种子，等价于 `params.seed` |

## 配方目录（30 个）

### MG / 干净电子（扁平、信息图、UI 演示）
| id | 名称 | 用途 |
|---|---|---|
| `mg.blip` | 哔 | 最基础的电子提示音，数据出现、轻提示 |
| `mg.prompt` | 哔-嘟 | 两段式提示，状态切换、确认、流程节点 |
| `mg.pop` | 弹出 | 短促气泡感，卡片、标签、图标弹出 |
| `mg.click` | 轻点 | 极短瞬态，按钮、翻页、打字、选择 |
| `mg.whoosh` | 呼啸 | 扫频气流，溶解、擦除、场景切换 |

### 卡通 / 夸张（绘本、漫画、搞笑强调）
| id | 名称 | 用途 |
|---|---|---|
| `cartoon.duang` | Duang | 弹性低频 + 金属泛音，搞笑强调、重物落下 |
| `cartoon.boing` | Boing | 弹簧颤音，人物弹起、意外、卡通反应 |
| `cartoon.zip` | Zip | 快速掠过，角色冲刺、元素飞过 |
| `cartoon.twinkle` | 闪亮 | 三连高音铃，星星、灵感、魔法出现 |
| `cartoon.bounce` | 弹跳 | 连续四次落地，球、角色、节奏型动作 |

### 纸质 / 手作（白板、水墨、汉字、手绘）
| id | 名称 | 用途 |
|---|---|---|
| `paper.tap` | 笔尖轻点 | 铅笔/马克笔点纸，白板讲解强调点 |
| `paper.stroke` | 笔刷划过 | 纸感摩擦，手绘线条出现 |
| `paper.page` | 翻页 | 纸张翻动 + 轻微褶皱，章节/页面切换 |
| `paper.wood` | 木质轻敲 | 木头敲击，板书、印章、手工场景 |
| `paper.stamp` | 盖章 | 低频落章 + 纸面噪声，结论、判定 |

### 像素 / 8-bit（像素风、游戏怀旧）
| id | 名称 | 用途 |
|---|---|---|
| `pixel.coin` | 金币 | 经典双音上行，得分、获得 |
| `pixel.jump` | 跳跃 | 方波上滑，角色起跳、像素动作 |
| `pixel.blip` | 8-bit 提示 | 短方波提示，菜单、选择、对话推进 |
| `pixel.error` | 8-bit 错误 | 下行蜂鸣，失败、禁止、错误反馈 |
| `pixel.powerup` | 能量上升 | 四音琶音上行，升级、充能、连击 |

### 科技 / 数据（信息图、等距、数据演示）
| id | 名称 | 用途 |
|---|---|---|
| `tech.scan` | 扫描 | 上扫音 + 数据气流，识别、加载、扫描 |
| `tech.data` | 数据流 | 密集高频颗粒，数据传输、计算、处理 |
| `tech.glitch` | 故障 | Bitcrush + 门限抖动，错误、干扰、赛博感 |
| `tech.notify` | 系统通知 | 三音提示，消息、系统状态、提醒 |
| `tech.lock` | 锁定确认 | 低频落点 + 高音确认，锁定、完成、确认 |

### 电影感 / 冲击（开场钩子、章节冲击、氛围）
| id | 名称 | 用途 |
|---|---|---|
| `cinematic.impact` | 重击 | 低频 Boom，章节开始、黑场冲击 |
| `cinematic.riser` | 上升 | 噪声上升，高潮/反转前的铺垫 |
| `cinematic.subdrop` | 下潜 | 低频下沉，悬念、失重、转场落点 |
| `cinematic.hum` | 低频氛围 | 可循环低频底噪，紧张/科幻场景 |
| `cinematic.wind` | 风声 | 可循环风噪，空镜、荒野、孤独感 |

## 与导演组的关系

导演蓝图的面板里可以写 `sfx` 事件（**面板内相对时间**）：

```json
{
  "panels": [
    {
      "engine": "styled",
      "visualStyle": "crayon",
      "sfx": [
        {"at": 0.4, "recipe": "cartoon.pop", "level": 55},
        {"at": 2.1, "recipe": "cartoon.duang", "level": 65, "params": {"pitch": -2}}
      ]
    }
  ]
}
```

- `at`：相对本段开头的秒数；导演会换算成成片时间轴，旁白/转场变化后仍能对齐。
- `recipe`：从上面的目录选，按该段画面风格家族选最接近的。
- `level`：0~100，默认 60；实际混音时还会再与旁白/BGM 平衡。
- 每段建议 ≤ 3 个，全片 3~8 个；不要在旁白连续说话时堆音效。

## 产物与边界

- 产物：`video_work/<project>/sfx/<recipe>_<hash>.wav`
- 缓存：导演按「配方 + 参数 + 种子」签名复用，不重复合成。
- 密度：导演按 `sfx_density`（light/normal/rich/none）+ 成片时长换算目标区间，
  并用「单段上限 + 2 秒最小间隔 + priority」裁剪；音效组只负责合成，不管密度。
- 时间：导演按 `sfx_snap`（默认 `visual`）对成片做视觉节拍检测，把 `at` 从“旁白时间”
  吸附到最近的画面变化（元素入场 / 镜头切换 / 动画起点，默认 ±1.5 秒）；单条可写 `"snap": false` 关闭。
- 画面节拍检测**不落盘、不调用视觉模型、不消耗 token**：只把 12fps / 48×48 的 RGB 小帧读进内存做差分，
  结果按视频路径 + mtime 缓存。
- 边界：程序合成擅长 MG/UI/卡通/氛围；**写实类**（雨声、脚步、关门、人群）不在覆盖范围内，后续用 CC0 素材库补。
- 不要用它做 BGM（那是 `music_generate` 的职责）。
