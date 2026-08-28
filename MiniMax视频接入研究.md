# MiniMax 视频生成接入研究

> 研究日期：基于当前 MiniMax 开放平台官方文档
> 研究范围：MiniMax-H3 视频模型、文生视频(t2va)、图生视频(i2va)、多模态参考生视频(r2va)、任务管理、按量计费、Token Plan 订阅套餐、每日 3 个视频赠送

---

## 1. 总体架构

MiniMax 把视频生成能力统一收敛在 `MiniMax-H3` 一个模型下，通过 **多模态 `content[]` 数组** 的不同组合，区分文生视频 / 图生视频 / 多模态参考生视频等场景，而不是每个场景单独维护一套 API。

```
                         ┌──────────────────────────────────────┐
                         │         MiniMax-H3（一个模型）         │
                         └──────────────────────────────────────┘
                                          ▲
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            │                             │                             │
      v2/video_generation          v2/h3_context_ir            v2/video_regeneration
       创建视频生成任务          创建 H3-Context-IR 任务        创建视频再生成任务
       (t2va / i2va / r2va)       (提示词增强，不出视频)         (768P 视频 → 2K 视频)
            │                             │                             │
            └────────── 共用查询/列表/取消接口 ───────────────────────────┘
                     v2/query/video_generation/{task_id}
                     v2/query/video_generation       (列表)
                     v2/video_generation/{task_id}   (取消/删除)
```

注意：**Token Plan 订阅套餐不包含 MiniMax-H3**，订阅 Key 走不到 H3 视频生成。要使用 H3 必须：

- 用 **按量计费 API Key**（普通 API Key），余额扣费；或
- 先在控制台单独「按量购买 API」开通 H3，再调用。

> 文档原话：「视频资源包支持 Hailuo 系列视频模型，**暂不支持 MiniMax H3**。需要使用 H3？请点击 按量购买 API，或联系销售定制。」
>
> 文档原话：「可用模型覆盖 MiniMax 全系模型（M3 / M2.7 / 图像 / 语音），**少量特殊模型（MiniMax H3、音色设计、快速复刻等）暂不支持**。」

---

## 2. 关于「套餐用户每日 3 个视频」的限制

这一节直接回答用户提的"每日 3 个视频"问题。

### 2.1 这个限制的来源

在控制台的 **「套餐用量」** 页（`https://platform.minimaxi.com/console/usage`），订阅用户会看到 **「视频赠送」** 这一栏，描述为：

- 限额：`0 / 3 已用`（可看到当前周期已使用和总额度）
- 重置时间：`X 小时 Y 分钟后重置`（按订阅周期重置，文档原文为周限额体系的一部分）

控制台原文：

```
5h 限额            1 小时 50 分钟后重置  总额度 100%  已用 1%
周限额             10 小时 50 分钟后重置 总额度 100%  已用 3%
视频赠送           10 小时 50 分钟后重置 0 / 3 已用
积分余额           订阅积分 + 充值积分 + 赠送积分 …
```

### 2.2 关键结论

1. **这 3 次并不是 API 维度的硬配额**，而是 **Token Plan 订阅里"视频赠送"额度**——即订阅读者在订阅有效期内、对应重置窗口内可免费调用的视频次数。
2. 它是 **"视频赠送" 礼品**，而不是 API 配额开关：
   - 即使赠送用完，也仍然可以使用 **充值积分 / 按量计费** 继续调用 H3；
   - 也就是说，3 次/周 不构成技术上的"接口调用阻断"。
3. 对 **按量计费 API Key（普通 API Key）** 用户而言，并不存在这个 3 次限制——按量计费按实际调用从余额扣费。
4. 重置窗口与 5h 限额 / 周限额 同源——属于 Token Plan 的额度窗口机制的一部分，未使用额度不会结转。

### 2.3 一句话总结

**"每日 3 个视频"实际上是 Token Plan 订阅里"视频赠送"的额度（按订阅重置周期重置），不是 API 强制限流；普通按量计费 API Key 不受此限制。**

---

## 3. 鉴权与基础信息

| 项 | 值 |
| --- | --- |
| Base URL | `https://api.minimaxi.com` |
| 鉴权方式 | HTTP Bearer Auth，`Authorization: Bearer <API_KEY>` |
| API Key 获取 | 控制台 `账户管理 → 接口密钥` 创建 |
| 请求体大小 | ≤ 64 MB（大文件请用公网 URL，**不要用 Base64**） |
| 内容类型 | `application/json` |
| API 文档索引 | `https://platform.minimaxi.com/docs/llms.txt` |

> 关键提醒：**订阅 Key（Token Plan Key） 和 按量计费 API Key 是两套独立体系，不可互换。**

---

## 4. 核心接口

H3 视频共 **5 个接口**：

| 方向 | 方法 | 路径 | 用途 |
| --- | --- | --- | --- |
| 创建视频生成任务 | POST | `/v2/video_generation` | 异步创建文生/图生/多模态参考生视频 |
| 查询任务 | GET | `/v2/query/video_generation/{task_id}` | 按 task_id 查最近 7 天内的单个任务 |
| 查询任务列表 | GET | `/v2/query/video_generation` | 分页批量查，支持状态/类型过滤 |
| 取消或删除任务 | DELETE | `/v2/video_generation/{task_id}` | 取消排队中的任务 / 删除已完成记录 |
| 创建 H3-Context-IR 任务 | POST | `/v2/h3_context_ir` | 多模态上下文理解，**只返回增强提示词**，不出视频 |
| 创建视频再生成任务 | POST | `/v2/video_regeneration` | 把符合 H3 768P 规格的视频再生成成 2K |

任务共用 `task_type` 字段区分：

- `generation` —— 视频生成（主接口产物）
- `h3_context_ir` —— 提示词增强
- `regeneration` —— 视频再生成

---

## 5. 创建视频生成任务（POST /v2/video_generation）

### 5.1 cURL 示例（文生视频 t2va）

```bash
curl --request POST \
  --url https://api.minimaxi.com/v2/video_generation \
  --header 'Authorization: Bearer <token>' \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "MiniMax-H3",
    "content": [
      {
        "type": "text",
        "text": "史诗级太空歌剧院线预告：女舰长独自站在巨大观景窗前，最后一支舰队正在集结并跃迁离去，强光爆闪、舰桥震动，她被留在原地。"
      }
    ],
    "resolution": "2K",
    "duration": 5,
    "ratio": "16:9"
  }'
```

返回：

```json
{
  "task_id": "424010985738629"
}
```

### 5.2 请求体参数

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `model` | ✅ | enum | 当前可用值：`MiniMax-H3` |
| `content` | ✅ | object[] | **多模态内容数组**，区分场景的核心 |
| `resolution` | ✅ | enum | `768P` 或 `2K` |
| `duration` | ✅ | int | 视频时长（秒），整数，**4~15** |
| `ratio` | 视场景 | enum | `adaptive` / `21:9` / `16:9` / `4:3` / `1:1` / `3:4` / `9:16` |
| `callback_url` | ❌ | string | 任务状态变更回调地址 |
| `aigc_watermark` | ❌ | bool | 是否添加 AIGC 标识水印，默认 `false` |

### 5.3 `content[]` 多模态元素（重点）

每个元素通过 `type` 区分种类，**可选** `role` 标注用途：

```json
{
  "type": "text",            // text / image_url / video_url / audio_url
  "role": "first_frame",     // 可选；见下表
  "text": "...",             // type=text 时必填
  "image_url": { "url": "..." } // type=image_url 时必填，建议公网 URL
}
```

**role 取值**：

| role | 含义 |
| --- | --- |
| `first_frame` | 图片作为视频首帧 |
| `last_frame` | 图片作为视频尾帧 |
| `reference_image` | 参考图片（多模态参考场景） |
| `reference_video` | 参考视频（多模态参考场景） |
| `reference_audio` | 参考音频（多模态参考场景） |
| `base_video` | 源视频（**仅视频再生成接口使用**） |

### 5.4 三种生成场景对照表

| 场景 | content 组合 | 是否图生视频 | ratio 行为 |
| --- | --- | --- | --- |
| **文生视频（t2va）** | 仅 1 个 `text` | ❌ | `ratio` **必填**，**不能是 adaptive**；可选 `21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16` |
| **图生视频-首帧** | `text` + 1 张 `image_url`（role=`first_frame` 或不填） | ✅ | ratio 由图片决定，**恒为 adaptive**；传其他值会被忽略 |
| **图生视频-尾帧** | `text` + 1 张 `image_url`（role=`last_frame`） | ✅ | 同上 |
| **图生视频-首尾帧** | `text` + 2 张 `image_url`（role 分别为 `first_frame`、`last_frame`） | ✅ | 同上 |
| **多模态参考生视频（r2va）** | `text` + `reference_image` + `reference_video` + `reference_audio` 的组合 | ✅（多参考） | ratio **可选**，默认 `adaptive`，也可显式指定具体比例 |

**互斥约束**：

> content 中出现 `reference_image` / `reference_video` / `reference_audio` 任一 role，**就不能再出现** `first_frame` / `last_frame`（反之亦然），**二者不可混用**。

### 5.5 输入媒体限制

**图片 `image_url`**：

| 项 | 限制 |
| --- | --- |
| 格式 | JPG / JPEG / PNG / WEBP / HEIC / HEIF |
| 单文件大小 | ≤ 30 MB |
| 宽高范围 | [256, 5760] px |
| 长宽比（宽/高） | [0.4, 2.5] |
| 数量 | 首帧 ≤ 1、尾帧 ≤ 1、参考图 ≤ 9 |

**视频 `video_url`**（仅多模态参考场景）：

| 项 | 限制 |
| --- | --- |
| 容器/格式 | MP4（.mp4）、MOV（.mov） |
| 编码 | 视频 H.264/AVC、H.265/HEVC；音频 AAC、MP3 |
| 单文件大小 | ≤ 50 MB |
| 个数 | ≤ 3 |
| 单段时长 | [2, 15] s；**总时长 ≤ 15 s** |
| 宽高范围 | [256, 5760] px |
| 长宽比（宽/高） | [0.4, 2.5] |
| 帧率 | [23.976, 60] |

**音频 `audio_url`**（仅多模态参考场景）：

| 项 | 限制 |
| --- | --- |
| 格式 | WAV、MP3 |
| 单文件大小 | ≤ 15 MB |
| 个数 | ≤ 3 |
| 单段时长 | [2, 15] s；**总时长 ≤ 15 s** |

---

## 6. 文生视频 vs 图生视频 具体实现方式

### 6.1 文生视频（t2va，text-to-video with audio）

**调用入口**：`POST /v2/video_generation`，`content[]` 中只有 1 个 `text` 元素。

**必填参数**：

- `model = "MiniMax-H3"`
- `content = [{ "type": "text", "text": "你的提示词" }]`
- `resolution`：768P 或 2K
- `duration`：4~15 秒整数
- `ratio`：**必填**，**不能是 adaptive**，二选一集合 `21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16`

**请求示例**：

```json
{
  "model": "MiniMax-H3",
  "content": [
    { "type": "text", "text": "一位女舰长站在太空战舰舰桥的观景窗前，远处的舰队正在跃迁离去。电影感、史诗感。" }
  ],
  "resolution": "2K",
  "duration": 6,
  "ratio": "16:9"
}
```

**特点**：

- 纯文本驱动，模型会同时生成画面 + 音轨（H3 内置音视频联合生成）。
- `ratio` 决定画面构图（横向、竖向、方形等）。
- 不依赖任何外部素材，调用最简单。

### 6.2 图生视频（i2va，image-to-video with audio）

**调用入口**：同样是 `POST /v2/video_generation`，但在 `content[]` 中加入 `image_url` 元素。

#### 6.2.1 首帧图生视频

```json
{
  "model": "MiniMax-H3",
  "content": [
    { "type": "text", "text": "镜头从特写缓慢拉远，舰桥仪表盘灯光闪烁，镜头微微晃动。" },
    {
      "type": "image_url",
      "role": "first_frame",
      "image_url": { "url": "https://example.com/first-frame.jpg" }
    }
  ],
  "resolution": "2K",
  "duration": 5
}
```

- `role="first_frame"` 也可以省略，省略时默认视为首帧。
- `ratio` 无需传；图片本身的宽高决定画面比例，ratio 字段传值会被忽略并按 adaptive 处理。

#### 6.2.2 尾帧图生视频

```json
{
  "content": [
    { "type": "text", "text": "镜头从舰桥里推向舷窗外，远处的舰队逐渐远去。" },
    {
      "type": "image_url",
      "role": "last_frame",
      "image_url": { "url": "https://example.com/last-frame.jpg" }
    }
  ]
}
```

#### 6.2.3 首尾帧图生视频

```json
{
  "content": [
    { "type": "text", "text": "无人机视角从黄昏的街道缓缓飞向夜幕降临的霓虹街区。" },
    { "type": "image_url", "role": "first_frame", "image_url": { "url": "https://example.com/start.jpg" } },
    { "type": "image_url", "role": "last_frame",  "image_url": { "url": "https://example.com/end.jpg"   } }
  ]
}
```

**图生视频的实现要点**：

1. **必须配文字 prompt**：单纯丢图片不写 prompt 会报参数错误（文档原话：「每次请求必须包含一个非空 text 项（prompt 必填）」）。
2. **图片必须用公网 URL**：受 64MB 请求体限制，图片应放对象存储或 CDN；**不要用 Base64**。
3. **图片宽高比必须在 [0.4, 2.5]**，否则视频生成可能失败或被压缩变形。
4. **ratio 字段被忽略**：图生视频的画面比例由输入图片决定，强行传 16:9 等不会生效。
5. **首尾帧用法**：通过两张图约束视频的起点和终点，常用于"起手画面 → 终点画面"的精确控制。

### 6.3 多模态参考生视频（r2va）

把"参考图片 + 参考视频 + 参考音频 + 文字描述"组合，让 H3 学习素材风格后产出视频。常用于：

- 让生成的视频延续参考视频的镜头语言/色调；
- 让生成的视频使用参考音频的 BGM/口播节奏；
- 让生成的视频保留参考图片的角色形象。

**互斥提醒**：和首帧/尾帧不可混用。

---

## 7. 任务管理接口

### 7.1 查询任务（GET）

```
GET https://api.minimaxi.com/v2/query/video_generation/{task_id}
Authorization: Bearer <token>
```

返回结构：

```json
{
  "task": {
    "id": "424010985738629",
    "model": "MiniMax-H3",
    "status": "succeeded",          // queued / running / succeeded / failed / cancelled
    "created_at": 1785125529,
    "updated_at": 1785125946,
    "content": {
      "url": "https://...output.mp4"   // 视频成片地址（生成任务）
      // "prompt": "..."              // H3-Context-IR 任务返回增强提示词
    },
    "resolution": "2K",
    "duration": 5,
    "usage": {
      "total_seconds": 5,
      "input_seconds": 0,
      "output_seconds": 5,
      "input_image_count": 1,
      "input_audio_seconds": 6,
      "total_tokens": 273890,
      "prompt_tokens": 13500,
      "completion_tokens": 260390
    },
    "ratio": "16:9",
    "task_type": "generation",     // generation / h3_context_ir / regeneration
    "modality": "video"
  }
}
```

查询窗口：**最近 7 天内**创建的任务。

### 7.2 查询任务列表（GET）

```
GET https://api.minimaxi.com/v2/query/video_generation?page_num=1&page_size=20
```

支持的查询参数：

| 参数 | 含义 |
| --- | --- |
| `page_num` | 页码，从 1 开始 |
| `page_size` | 每页数量 |
| `filter.status` | queued / running / succeeded / failed / cancelled |
| `filter.task_ids` | 按任务 ID 过滤，可多值 |
| `filter.model` | 模型名称，如 `MiniMax-H3` |
| `filter.task_type` | generation / h3_context_ir / regeneration |

返回：

```json
{
  "items": [ /* 与查询任务相同的 task 结构 */ ],
  "total": 476
}
```

`total` 仅统计最近 7 天内匹配的任务。

### 7.3 取消或删除任务（DELETE）

```
DELETE https://api.minimaxi.com/v2/video_generation/{task_id}
Authorization: Bearer <token>
```

按当前状态自动判断动作：

| 当前状态 | 执行动作（`action`） | 说明 |
| --- | --- | --- |
| `queued` 排队中 | `cancelled` | 取消，**未开始处理、无扣费** |
| `succeeded` 成功 | `deleted` | 删除任务记录 |
| `failed` 失败 | `deleted` | 删除任务记录 |
| `running` 运行中 | — | **不可操作，返回错误** |
| `cancelled` 已取消 | — | 不可操作，返回错误 |

返回：

```json
{ "task_id": "...", "action": "cancelled", "status": "cancelled" }
```

---

## 8. H3-Context-IR（提示词增强）

```
POST https://api.minimaxi.com/v2/h3_context_ir
```

- **只返回增强后的视频提示词，不会创建视频生成任务。**
- 接收同样的多模态 `content[]` 输入（text / image_url / video_url / audio_url）。
- 返回结构中 `task_type = "h3_context_ir"`，成功时从 `content.prompt` 获取增强提示词。
- 任务成功后 `modality = "text"`，而不是 `video`。

**用途**：用 H3-Context-IR 把粗糙的用户提示词扩写成结构化、语义丰富的英文提示词，再把扩写结果作为 `content` 的 text 项二次喂给 `/v2/video_generation`，是 MiniMax 推荐的"Full 2K-Workflow"。

**计费**：输入 5.80 元/百万 tokens，输出 23.00 元/百万 tokens。

---

## 9. 视频再生成（POST /v2/video_regeneration）

把符合 H3 768P 输出规格的视频再生成成 2K。

### 9.1 两种方式（二选一）

**方式一：按任务 ID**

```json
{
  "model": "MiniMax-H3",
  "source_task_id": "424010985738629",
  "resolution": "2K"
}
```

- 需开通白名单；
- 源任务必须属于当前账号、状态为 succeeded；
- 且仍可通过 `/v2/query/video_generation` 查到（创建于 **7 天内**）。

**方式二：按源视频**

```json
{
  "model": "MiniMax-H3",
  "content": [
    {
      "type": "video_url",
      "role": "base_video",
      "video_url": { "url": "https://..." }
    }
  ],
  "resolution": "2K"
}
```

> **本接口仅支持对符合 MiniMax-H3 768P 输出规格的生成视频进行再生成并输出 2K**，不支持任意视频的通用处理。

任务完成后 `task_type = "regeneration"`，可通过 H3 共用的查询/列表/取消接口管理。

---

## 10. 回调（callback_url）

如果不想轮询查询任务，可以在创建任务时传 `callback_url`：

- MiniMax 服务器会先发一个**带 `challenge` 字段的验证请求**；
- 需 **3 秒内原样返回 `challenge` 完成验证**；
- 验证成功后，每当任务状态变更即向该地址 POST 推送，推送体结构与查询任务接口的响应一致。

| 推送 status 取值 | 含义 |
| --- | --- |
| `queued` | 排队中 |
| `running` | 运行中 |
| `succeeded` | 成功 |
| `failed` | 失败 |
| `cancelled` | 已取消 |

---

## 11. 计费规则（按量计费 API Key）

> 来源：`https://platform.minimaxi.com/docs/guides/pricing-paygo`

### 11.1 视频生成-输出价格

| 模型 | 分辨率 | 计费规则 | 刊例价 |
| --- | --- | --- | --- |
| MiniMax-H3 | 2K | 按秒计费 | **0.80 元/秒** |
| MiniMax-H3 | 768P | 按秒计费 | **0.50 元/秒** |

### 11.2 视频生成-输入素材价格

| 模型 | 素材 | 计费规则 |
| --- | --- | --- |
| MiniMax-H3 | 音频 | 免费 |
| MiniMax-H3 | 图片 | 5 张以内免费，超出部分 **0.20 元/张** |
| MiniMax-H3 | 视频 | 按输入视频时长及生成视频分辨率计费：2K 0.80 元/秒，768P 0.50 元/秒 |

### 11.3 视频再生成-输出价格

| 模型 | 分辨率 | 计费规则 | 刊例价 |
| --- | --- | --- | --- |
| MiniMax-H3-Regeneration | 768P → 2K | 按视频再生成输出秒数计费 | **0.30 元/秒** |

### 11.4 视频再生成-输入素材价格

| 模型 | 素材 | 计费规则 |
| --- | --- | --- |
| MiniMax-H3-Regeneration | 音频 | 免费 |
| MiniMax-H3-Regeneration | 图片 | 5 张以内免费，超出部分 0.15 元/张 |
| MiniMax-H3-Regeneration | 视频 | 按原 768P 生成任务中输入视频的秒数计费：0.30 元/秒 |

### 11.5 H3-Context-IR 任务价格

| 模型 | 输入价格 | 输出价格 |
| --- | --- | --- |
| MiniMax-H3-Context-IR | 5.80 元/百万 tokens | 23.00 元/百万 tokens |

### 11.6 几个样例成本估算

- **5 秒 768P 文生视频**：5 × 0.5 = **2.5 元**
- **5 秒 2K 文生视频**：5 × 0.8 = **4.0 元**
- **5 秒 2K 图生视频**（带 1 张首帧图）：5 × 0.8 + 0 = **4.0 元**（5 张内图片免费）
- **5 秒 2K 多模态参考**（1 张参考图 + 1 段 5 秒参考视频）：5 × 0.8 + 0 + 5 × 0.8 = **8.0 元**
- **5 秒 2K 视频再生成**：5 × 0.3 = **1.5 元**

---

## 12. Token Plan 套餐

> 来源：`https://platform.minimaxi.com/docs/token-plan/intro`

### 12.1 套餐档位

| 档位 | 价格 | 额度窗口 | Agent 用量 |
| --- | --- | --- | --- |
| Plus | **¥49 /月** | 5 小时固定窗口 + 周窗口 | 3-4 个 Agent |
| Max | **¥119 /月** | 5 小时固定窗口 + 周窗口 | 4-5 个 Agent |
| Ultra | **¥469 /月** | 5 小时固定窗口 + 周窗口 | 6-7 个 Agent |

### 12.2 关键限制

- **Token Plan 不支持 MiniMax H3**——这是订阅读者要特别注意的点。
- 支持模型：M3 / M2.7 / 图像 / 语音；H3、音色设计、快速复刻等 **不支持**。
- 额度窗口为 **5h 固定窗口 + 周窗口**。
- 未使用完的订阅额度 **不结转**。
- 达到上限后可选：使用已购积分 / 升级订阅 / 切换至按量计费 / 等待窗口重置。

### 12.3 积分包

| 购买价格 | 获得积分 |
| --- | --- |
| ¥30 | 4,285 |
| ¥150 | 21,430 |
| ¥500 | 71,435 |

- 1,000 积分 = ¥7。
- 有效期 365 天。
- 积分与 Token Plan 覆盖相同资源；若同时可由套餐额度和积分覆盖，**优先使用套餐额度**，超出部分由积分抵扣。

### 12.4 套餐里的"视频赠送"（每日 3 个视频的真相）

控制台「套餐用量」页有 **"视频赠送"** 栏，重置时间和周窗口一致（如 `10 小时 50 分钟后重置`，可看到 `0 / 3 已用`）。

这是 **订阅读者在订阅周期内可免费使用的视频次数（典型为 3 次/周，按订阅档位/周期不同）**，定位为"视频赠送"礼品额度，并不是技术上的接口强制限流——

- 用完后仍可继续调用 H3 接口，但会走 **充值积分 / 按量计费** 扣费路径；
- 文档明确：Token Plan **不支持 H3**，所以"视频赠送"很可能是按 **视频资源包**（Hailuo 系列）等其他模型计入，与 H3 是两套体系。

> **结论**：对订阅读者：
> 1. 如果你想用 H3，**仅靠订阅套餐是不够的**——必须走按量计费 API Key 或单独购买视频资源包。
> 2. 控制台上的"视频赠送"3 次，是订阅读者用其他视频模型（Hailuo 系列）的赠送额度，**不是 H3 配额**。
> 3. H3 真正的限制只有：**账户余额 / 视频资源包余量 / 资源包 RPM 上限**。

---

## 13. 视频资源包（按量购买的另一种形式）

> 来源：`https://platform.minimaxi.com/docs/guides/pricing-video`

视频资源包面向 Hailuo 系列视频模型，**不支持 MiniMax H3**。

| 类型 | 折扣 | 折扣价 | 原价 | 有效期 | 视频点数 | RPM |
| --- | --- | --- | --- | --- | --- | --- |
| 视频基础包 | 5% | ¥7,000 | ¥7,368 | 1 个月 | 3,680 | 20 |
| 视频高级包 | 10% | ¥15,000 | ¥16,667 | 1 个月 | 8,330 | 30 |
| 视频进阶包 | 15% | ¥30,000 | ¥35,294 | 1 个月 | 17,650 | 40 |
| 视频企业包 | 20% | ¥40,000 | ¥50,000 | 1 个月 | 25,000 | 50 |
| 商务定制 | — | — | — | — | — | 无限 RPM/TPM + 模型更新优先体验 + 专属稳定性保障 |

不同模型生成视频的扣减次数（点数）：

| 模型 | 输出规格 | 扣减点数 |
| --- | --- | --- |
| MiniMax-Hailuo-2.3-Fast | 768p 6s | 0.7 |
| MiniMax-Hailuo-2.3-Fast | 768p 10s | 1.1 |
| MiniMax-Hailuo-2.3-Fast | 1080p 6s | 1.3 |
| MiniMax-Hailuo-02 | 512p 6s | 0.3 |
| MiniMax-Hailuo-02 | 512p 10s | 0.5 |
| MiniMax-Hailuo-02 / Hailuo-2.3 | 768p 6s | 1 |
| MiniMax-Hailuo-02 / Hailuo-2.3 | 768p 10s | 2 |
| MiniMax-Hailuo-02 / Hailuo-2.3 | 1080p 6s | 2 |

注意：生成失败或命中安全审核的视频不会扣减视频点数；资源包余量不继承，过期会自动清零。

---

## 14. 一个完整的 Python 接入示例

```python
import time
import requests

API_KEY = "your_api_key_here"
BASE    = "https://api.minimaxi.com"


def create_video(prompt: str, image_url: str | None = None,
                 resolution: str = "2K", duration: int = 6,
                 ratio: str = "16:9") -> str:
    """创建视频生成任务，返回 task_id"""
    content = []
    if image_url:
        # 图生视频（首帧）
        content.append({"type": "text", "text": prompt})
        content.append({
            "type": "image_url",
            "role": "first_frame",
            "image_url": {"url": image_url},
        })
        # 图生视频 ratio 字段会被忽略，由图片决定
        ratio = "adaptive"
    else:
        # 文生视频
        content.append({"type": "text", "text": prompt})

    payload = {
        "model": "MiniMax-H3",
        "content": content,
        "resolution": resolution,
        "duration": duration,
        "ratio": ratio,
    }

    r = requests.post(
        f"{BASE}/v2/video_generation",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["task_id"]


def query_video(task_id: str) -> dict:
    """查询任务状态"""
    r = requests.get(
        f"{BASE}/v2/query/video_generation/{task_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def wait_for_video(task_id: str, poll_interval: int = 10, max_wait: int = 1800):
    """轮询等待任务完成"""
    waited = 0
    while waited < max_wait:
        data = query_video(task_id)
        task = data["task"]
        status = task["status"]
        print(f"[{task_id}] status = {status}")
        if status == "succeeded":
            return task["content"]["url"]
        if status in ("failed", "cancelled"):
            raise RuntimeError(f"task {task_id} {status}: {task.get('error')}")
        time.sleep(poll_interval)
        waited += poll_interval
    raise TimeoutError(f"task {task_id} timeout after {max_wait}s")


# ----- 文生视频 -----
task_id = create_video(
    prompt="一只柴犬在樱花树下奔跑，镜头跟随，电影感，浅景深。",
    resolution="2K",
    duration=5,
    ratio="16:9",
)
video_url = wait_for_video(task_id)
print("文生视频成片：", video_url)

# ----- 图生视频（首帧）-----
task_id = create_video(
    prompt="镜头从静止缓慢推进，柴犬抬头望向镜头，阳光从树缝洒下。",
    image_url="https://your-cdn.example.com/first-frame.jpg",
    resolution="2K",
    duration=5,
)
video_url = wait_for_video(task_id)
print("图生视频成片：", video_url)
```

---

## 15. 接入注意事项清单

1. **Key 体系分离**：订阅 Key（Token Plan）和按量计费 API Key 互不可用；H3 必须用按量计费 API Key。
2. **Token Plan 不支持 H3**：不要以为订阅了就有 H3 视频额度。
3. **每日 3 个视频**：是订阅读者在订阅周期内的视频赠送额度，**不针对 H3**；按量计费 API Key 不受此限制。
4. **首尾帧和多模态参考互斥**：一次请求只能选一种范式。
5. **`ratio` 行为差异**：
   - 文生视频：`ratio` 必填，不能是 `adaptive`；
   - 图生视频：ratio 由图片决定，传值被忽略；
   - 多模态参考：可选，默认 `adaptive`。
6. **媒体大小**：请求体 ≤ 64 MB，图片 ≤ 30 MB，视频 ≤ 50 MB；**不要用 Base64，用公网 URL**。
7. **图生视频必须配文字 prompt**：不能只丢图片。
8. **异步任务**：返回 `task_id`，建议用 **callback_url 推送** 或 **轮询查询** 两种方式获取结果。
9. **取消/删除自动判定**：DELETE 接口按任务当前状态自动选择 `cancelled` 或 `deleted`，不可手动指定。
10. **H3-Context-IR 只返回提示词**：不出视频；想"先增强提示词，再生成视频"可以串行调用。
11. **资源包余量不继承**：过期清零；失败/审核被拒不扣费。
12. **视频再生成**：仅支持符合 H3 768P 输出规格的源视频再生成为 2K，**不是通用视频处理工具**。

---

## 16. 关键文档地址汇总

| 内容 | URL |
| --- | --- |
| 接口概览 | https://platform.minimaxi.com/docs/api-reference/api-overview |
| 创建视频生成任务 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-create |
| 查询任务 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-query |
| 查询任务列表 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-list |
| 取消或删除任务 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-delete |
| 创建 H3-Context-IR 任务 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-h3-context-ir |
| 创建视频再生成任务 | https://platform.minimaxi.com/docs/api-reference/video-generation-v2-regeneration |
| 按量计费定价 | https://platform.minimaxi.com/docs/guides/pricing-paygo |
| 视频资源包定价 | https://platform.minimaxi.com/docs/guides/pricing-video |
| Token Plan 订阅概要 | https://platform.minimaxi.com/docs/token-plan/intro |
| Token Plan 定价 | https://platform.minimaxi.com/docs/guides/pricing-token-plan |
| 控制台套餐用量 | https://platform.minimaxi.com/console/usage |
| 文档索引 | https://platform.minimaxi.com/docs/llms.txt |
