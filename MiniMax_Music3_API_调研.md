# MiniMax Music 3.0 API 调研报告（国内版）

> 调研时间：2026 年  
> 调研目标：搞清楚 **MiniMax 国内开放平台**（`platform.minimax.cn` / `api.minimaxi.com`）的 Music 3.0 API 调用方式，以及如何通过订阅套餐获得调用权限。  
> 适用对象：注册在国内开放平台（手机号/国内主体）的开发者。

---

## 0. 重要前提（先看这个）

Music 3.0 的"付费 API 入口"对**新用户已不开放**，国内版同样如此。这是决定后面怎么走的核心事实。

| 事项 | 状态 | 时间 |
|---|---|---|
| 付费 Music Generation API（含 music-3.0） | **不再面向新用户提供服务** | 2026-08-20 起 |
| 历史付费用户 | 可继续使用现有 API 服务 | — |
| 免费 Music API（music-3.0-free / music-2.6-free / music-cover-free） | **已停止服务** | 2026-08-20 起 |
| 开源权重 `MiniMax-Music3`（11.1B） | 仍可在 Hugging Face 下载 | 持续可用 |

官方推荐的两条替代路径：
1. **开源权重自部署**：`https://huggingface.co/MiniMaxAI/MiniMax-Music3`
2. **C 端产品海螺 AI / 星野**：`https://hailuoai.com/`（部分套餐含 Music 3.0 积分）

> 来源：`https://platform.minimax.cn/docs/guides/pricing-paygo`（顶部公告）

---

## 一、API 调用方式

### 1.1 端点与基础信息

| 项 | 值 |
|---|---|
| **Endpoint（国内）** | `https://api.minimaxi.com/v1/music_generation` |
| Endpoint（国际） | `https://api.minimax.io/v1/music_generation` |
| 方法 | `POST` |
| 鉴权 | `Authorization: Bearer <MINIMAX_API_KEY>` |
| 同步/异步 | **同步**（请求内直接返回音频 URL，不需要轮询 task_id） |
| Content-Type | `application/json` |
| API Key 环境变量 | `MINIMAX_API_KEY` |
| 文档 | `https://platform.minimax.cn/docs/api-reference/music-generation` |

> 国内/国际端点**只差域名**，协议、字段完全一致。两套账号体系独立，API Key 不能跨域用。

### 1.2 可用模型 ID（国内开放平台）

| model 字段值 | 状态 | 单价（国内） | RPM |
|---|---|---|---|
| `music-3.0` | **已下线（对新用户）**，历史付费用户可继续用 | **¥1.0 / 首**（最长 5 分钟） | 120 |
| `music-2.6` | 已下线 | — | 120 |
| `music-2.5+` | 已下线 | — | — |
| `music-3.0-free` | 已下线 | — | — |
| `music-2.6-free` / `music-cover-free` | 已下线 | — | — |

> ⚠️ `model` 字段务必填 `music-3.0`，社区里有人填 `music-01` 或 `music-2.5` 会直接报错（**"Wrong model for native API. Use music-3.0"**）。

### 1.3 完整 cURL 示例（官方文档原样）

```bash
curl --request POST \
  --url https://api.minimaxi.com/v1/music_generation \
  --header 'Authorization: Bearer <MINIMAX_API_KEY>' \
  --header 'Content-Type: application/json' \
  --data '{
    "model": "music-3.0",
    "prompt": "Indie folk, melancholic, fingerpicked acoustic guitar, soft male vocal, 75 BPM, verse-chorus structure",
    "lyrics": "[Verse]\nStreetlights fading in the morning rain\nI walk the same old roads again\n\n[Chorus]\nCarry me home, where the silence stays\nCarry me home, through the empty days"
  }'
```

### 1.4 完整 Python 示例

```python
import requests
import json
import os

url = "https://api.minimaxi.com/v1/music_generation"  # 国内端点
api_key = os.environ.get("MINIMAX_API_KEY")

payload = {
    "model": "music-3.0",
    "prompt": "Indie folk, melancholic, fingerpicked acoustic guitar, soft male vocal, 75 BPM",
    "lyrics": "[Verse]\nStreetlights fading in the morning rain\n...\n\n[Chorus]\nCarry me home..."
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

resp = requests.post(url, headers=headers, json=payload)
print(resp.status_code, resp.json())
```

### 1.5 请求体字段说明

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `model` | ✅ | string | 填 `"music-3.0"` |
| `prompt` | ✅ | string | 风格/情绪/场景/乐器/语速/BPM 的自然语言描述（英文效果最好） |
| `lyrics` | ⚠️ | string | 歌词文本，**必须用结构标签**：`[Verse]`、`[Chorus]`、`[Bridge]`、`[Outro]` 等分隔段落。空字符串或 `is_instrumental=true` 时表示纯音乐 |
| `is_instrumental` | ❌ | bool | `true` = 纯器乐（无人声），不传默认 false |
| `refer_voice` | ❌ | string / file id | 参考人声（Cover 翻唱模式） |
| `refer_instrumental` | ❌ | string / file id | 参考伴奏 |
| `audio_reference` | ❌ | string / file id | 参考音频 URL/ID（用于风格/编曲迁移） |
| `seed` | ❌ | int | 复现用随机种子 |
| `stream` | ❌ | bool | 是否流式返回 |

> 结构标签规则（`[Verse]/[Chorus]`…）是 Music 3.0 强依赖的，不加标签容易出"漂"。

### 1.6 响应体结构

```json
{
  "id": "music-3.0-xxxxxxxxxxxx",
  "status": "success",
  "audio_url": "https://cdn.minimaxi.com/music/xxxxx.mp3",
  "duration": 195.4,
  "model": "music-3.0",
  "created_at": "2026-08-21T10:32:11Z"
}
```

- `audio_url`：生成的 mp3 文件，**约 5 分钟内有效**（CDN 链接），用完要立刻下载到自己存储。
- `duration`：实际生成时长（秒）。
- 没有 `task_id`，**不需要轮询**，一次请求直接拿结果。

### 1.7 输入限制

- 单曲最长 **5 分钟**。
- `prompt` 建议 50–500 字符。
- `lyrics` 建议 1500 字符以内（超出会被截断）。
- 参考音频：≤ 10 MB，≤ 5 分钟，mp3/wav 均可。

### 1.8 配套：歌词生成接口

如果要先把提示词扩成完整歌词，可以先用 Lyrics Generation：

```
POST https://api.minimaxi.com/v1/lyrics_generation
```

```json
{
  "mode": "write_full_song",
  "prompt": "A song about missing home in autumn",
  "lyrics_optimizer": true,
  "is_instrumental": false
}
```

返回纯文本歌词，再丢给上面的 `/v1/music_generation` 即可。

---

## 二、套餐 / 价格（国内版）

### 2.1 套餐总览

国内版 2026-10-01 也跟国际版同步把 **Token Plan 替换成了 M Plan**，老的 Plus / Max / Ultra 改名为 **Go / Explore / Build**，月费按**人民币**标价（国际版按美元，国内版更贵）。

| 套餐 | 国内月费（人民币） | 定位 | 是否能用 Music 3.0 |
|---|---|---|---|
| **Free Tier** | ¥0 | 注册即送少量试用额度 | ❌ 免费 Music API 已下线（2026-08-20） |
| **M Plan · Go** | **¥588 / 月**（年付 ¥5,880） | 个人轻度使用 | ⚠️ 仅 2026-08-20 前的存量付费用户能用 Music 3.0 |
| **M Plan · Explore** | **¥1,490 / 月**（年付 ¥14,900） | 中度使用 | ⚠️ 同上 |
| **M Plan · Build** | **¥5,628 / 月**（年付 ¥56,280） | 重度使用 | ⚠️ 同上 |
| **按量计费（Pay-as-you-go）** | 充值 Credits，按量扣费 | 用多少付多少 | ⚠️ Music 3.0 仍标 **¥1.0 / 首**，但**新用户已无法开通** |
| **海螺 AI 会员**（C 端） | 基础版 / 标准版 / 大师版 / 至臻版 | 视频+多模态，包含音乐 | ✅ 走积分池（贝壳/积分），可调 Music 3.0 |

### 2.2 按量计费（Pay-as-you-go）单价表

来源：`https://platform.minimax.cn/docs/guides/pricing-paygo`

| 模型 | 单价 | 备注 |
|---|---|---|
| `music-3.0` | **¥1.0 / 首** | RPM 120，新用户已不开放（2026-08-20 起） |
| `music-2.6` | 历史价格（已下线） | RPM 120 |
| `music-2.5+` | ¥0.25 / 首（已下线） | — |

> 1 首 = 1 次生成 = 最长 5 分钟的完整歌曲（带人声/纯器乐/Cover 都算 1 首）。

### 2.3 M Plan 权益（Go / Explore / Build）

- **基础额度**：分别为 1× / 3× / 10× 基础额度（按调用次数换算）。
- **多模态覆盖**：文本、图像、语音、**音乐（Music 3.0）**、视频（部分档位）共用**同一个积分池**，按各模型按量计费的刊例价实时扣减。
- **Music 3.0 配额**：M Plan 内的 Music 3.0 调用走积分池扣费，1 次 = 1 元刊例价额度（Go 档的额度对应约 588 次/月）。
- **M Plan 不能跨域**：国内 M Plan 的 key 只能在 `api.minimaxi.com` 用；国际 M Plan 的 key 只能在 `api.minimax.io` 用。

### 2.4 海螺 AI 会员（C 端，含 Music 3.0 积分）

如果只是想把 Music 3.0 用起来（不写代码），海螺 AI 会员是最直接的入口。Music 3.0 2026-08-13 发布后，已并入海螺 AI 会员的积分池。

| 会员 | 价格 | 月度积分（贝壳） | 约等于 Music 3.0 次数 |
|---|---|---|---|
| 基础版 | ¥数十 / 月 | 1,000 贝壳 | 约 20 首（按 50 贝壳/首折算，实际以控制台为准） |
| 标准版 | ¥数十 / 月 | 4,500 贝壳 | 约 90 首 |
| 大师版 | ¥一百多 / 月 | 10,500 贝壳 | 约 200+ 首 |
| **至臻版** | **¥10,788 / 年**（约 ¥899/月） | 12,000 贝壳/月 | 约 240+ 首/月 + 全模态高级权益 |

> 海螺 AI 会员的 Music 3.0 消耗积分以控制台实时显示为准；至臻版上线后引发过"万元年费"争议，官方回应是"行业底价"。

### 2.5 关键结论

1. **国内新用户想用 Music 3.0 API**：
   - **历史付费用户** → 走 Pay-as-you-go 或保留原 Token Plan 续费，能继续调 `music-3.0`（¥1.0/首）。
   - **新用户** → 国内开放平台**没有直接的 API 入口**了（2026-08-20 起新购不开放）。
2. **新用户想用 Music 3.0 能力**：
   - 走 C 端海螺 AI 会员（最便宜可从基础版起步，但 Music 3.0 积分不单独标，看综合性价比）。
   - 或者**自部署开源权重**（`https://huggingface.co/MiniMaxAI/MiniMax-Music3`）。
3. **不要开 Go/Explore/Build 指望直接用 Music 3.0**——M Plan 是 LLM token 套餐，Music 3.0 单独计费（¥1.0/首），M Plan 内的 Music 3.0 配额是用积分池额度换算来的。
4. **价格锚点**：Music 3.0 = **¥1.0 / 首**（5 分钟以内），100 首 = ¥100。

### 2.6 文档里关于 Music 3.0 权限的原文

> 自 2026 年 8 月 20 日起，付费接口（音乐生成、歌词生成）不再面向新用户提供服务，历史付费用户可继续使用现有 API 服务；免费音乐生成接口（Music-3.0-free、Music-2.6-free、music-cover-free）停止服务。如需体验或使用音乐生成能力，请前往海螺 AI，或使用开源模型 MiniMax Music 3 开源模型。
>
> — `https://platform.minimax.cn/docs/guides/pricing-paygo`（顶部公告）

> 国内音乐 API 文档里同样写着：Music 3.0 "Available to M Plan and paid users only, with an RPM of 120"（限 M Plan 和历史付费用户，RPM 120）。

---

## 三、操作建议（结合你"目前套餐不包含"的情况）

按推荐顺序给你三条路：

### 推荐路径 A：开海螺 AI 会员（C 端，按月付费）
- 进 `https://hailuoai.com/` 选基础版/标准版即可。
- 拿到会员权益后，在海螺 AI 里直接用 Music 3.0 生成。
- 适合：调用量小、偶尔生成、不想写代码。

### 推荐路径 B：保留/升级 M Plan（API 方向）
- 在 `https://www.minimax.cn/m-plan` 订阅 **M Plan · Go（¥588/月）** 或更高。
- 在 `https://platform.minimax.cn/` 控制台生成 API Key（`MINIMAX_API_KEY`），按 1.4 的代码调 `https://api.minimaxi.com/v1/music_generation`。
- 注意：M Plan 是 token 积分池套餐，Music 3.0 调用按 ¥1.0/首从积分池扣费；Go 档 ¥588 的额度可以支撑约 **588 次** Music 3.0 调用（按刊例价 1:1 折算）。
- 适合：调用量大、要自己集成到产品里。

### 推荐路径 C：自部署开源权重
- 不订阅任何套餐。
- 拉 `huggingface.co/MiniMaxAI/MiniMax-Music3`，本地/云端 GPU 跑推理。
- 适合：长期大量调用、对延迟不敏感、想控制成本。

### 不推荐
- 不要试图开新账户直接调 music-3.0 —— 国内新用户已被官方关闭入口。
- 不要用 `music-3.0-free` / `music-2.6-free`，已下线。

---

## 四、参考链接

| 用途 | URL |
|---|---|
| 国内 API 主域 | `https://api.minimaxi.com` |
| 国内开放平台首页 | `https://platform.minimax.cn/` |
| 国内 Music 文档 | `https://platform.minimax.cn/docs/api-reference/music-generation` |
| 国内按量计费定价 | `https://platform.minimax.cn/docs/guides/pricing-paygo` |
| 国内定价总览 | `https://platform.minimax.cn/docs/pricing/overview` |
| 国内 M Plan 页 | `https://www.minimax.cn/m-plan` |
| 国内 M Plan FAQ | `https://platform.minimax.cn/docs/m-plan/faq` |
| 海螺 AI（C 端） | `https://hailuoai.com/` |
| 海螺 AI 付费服务协议 | `https://hailuoai.com/doc/zh/payment-policy.html` |
| 开源权重 | `https://huggingface.co/MiniMaxAI/MiniMax-Music3` |
| 第三方深度评测 | `https://guancyxx.cn/blog/minimax-music-3-api-deep-dive` |
| MiniMax 官网 | `https://www.minimax.cn/` |

---

## 五、一句话总结

> **国内开放平台的 Music 3.0 已对新用户关闭 API 入口**（2026-08-20 起），历史付费用户可继续按 **¥1.0/首** 调 `https://api.minimaxi.com/v1/music_generation`。新用户想用 Music 3.0 能力，最干净的两条路是 **开海螺 AI 会员（C 端，按月付费含积分）** 或 **自部署开源权重**。M Plan（Go/Explore/Build）是 token 积分池套餐，Music 3.0 在里面按刊例价从积分池扣费，可作为 API 调用的备选方案。
