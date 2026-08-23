# MiniMax 开放平台 — 账号可用套餐与模型清单

> 信息来源：MiniMax 开放平台控制台（`platform.minimaxi.com`）实际页面状态 + 官方文档站
> 核查时间：2026-08-20

---

## 一、当前账号套餐信息

| 项目 | 内容 |
|---|---|
| 套餐类型 | **Token Plan · TokenPlanMax-月度会员** |
| 订阅状态 | 订阅中 |
| 购买时间 | 2026-08-20 22:53，支付 ¥119.00 |
| 下次续费日 | 2026-09-20 |
| 订单 ID | 2090408772894728306 |
| 档位规格 | Max |
| 积分余额 | 0 积分 |
| 5h 限额 | 已用 2%，40 分钟后重置 |
| 周限额 | 已用 0%，3 天后重置 |
| 视频赠送 | 0 / 3 已用，40 分钟后重置 |
| 近 7 天 / 30 天调用量 | 637.20K |
| 累计调用量 | 279.94K |

**套餐权益范围**：支持 M3 / M2.7 / 图像 / 语音；文本 / 图像 / 语音共享额度；Hailuo2.3 视频 3 条 / 日；月度约 18 亿+ token。

---

## 二、账号下可调用模型清单

依据控制台「请求管理 > 请求限制」表格 + 官方文档站核对。

### 1. 语言模型

| 模型 | RPM | TPM |
|---|---|---|
| M2 / M2.1 / M2.5 / M2.7 / M3 | 20 | 1,000,000 |

### 2. TTS 语音合成

| 模型 | RPM |
|---|---|
| speech-2.6-hd | 10 |
| speech-2.6-turbo | 10 |
| speech-2.8-hd | 10 |
| speech-2.8-turbo | 10 |
| speech-02-hd | 10 |
| speech-02-turbo | 10 |

调用入口：`POST https://api.minimaxi.com/v1/t2a_v2`（同步）/ `v1/t2a_async_v2`（异步）

### 3. 音色设计 / 音色克隆

| 能力 | RPM | 调用入口 |
|---|---|---|
| 音色快速复刻（voice_clone） | 60 | 官方音色复刻接口（`api.minimaxi.com` 域名） |
| 音色设计（voice_design） | 3 | `POST https://api.minimaxi.com/v1/voice_design` |

### 4. 音乐生成 ⚠️ 受限可用

| 模型 | RPM | 状态 |
|---|---|---|
| music-2.0 | 6 | 请求限制表中存在，可调用 |
| music-2.5 | 6 | 请求限制表中存在，可调用 |
| music-2.5+ | 6 | 请求限制表中存在，可调用 |
| music-3.0 | — | 请求限制表中未出现 |
| music-2.6 | — | 请求限制表中未出现 |
| music-cover | — | 请求限制表中未出现 |
| Music-3.0-free / Music-2.6-free / music-cover-free | — | 已停止服务 |

调用入口（理论）：`POST https://api.minimaxi.com/v1/music_generation`

### 5. 图像生成

| 模型 | 备注 |
|---|---|
| image-01 | TokenPlanMax 权益包含，共享文本额度 |
| image-01-live | TokenPlanMax 权益包含，共享文本额度 |

### 6. 视频生成

| 模型 | RPM | 并发 |
|---|---|---|
| Hailuo 系列（含 Hailuo2.3） | 5 | 29 |
| MiniMax-H3 | 300 | — |

调用入口：`POST https://api.minimaxi.com/v1/video_generation`

---

## 三、音乐生成（Music）受限说明

官方文档原样提示：

> **"自 2026 年 8 月 20 日起，付费接口（音乐生成、歌词生成）不再面向新用户提供服务，历史付费用户可继续使用现有 API 服务；免费音乐生成接口（Music-3.0-free、Music-2.6-free、music-cover-free）停止服务。**
>
> **如需体验或使用音乐生成能力，可前往 MiniMax Audio，或使用已发布在 Hugging Face 和 魔搭 ModelScope 的 MiniMax Music 3 开源模型。"**

**当前账号判定**：
- 账号在 2026-08-20 22:53 购买了 TokenPlanMax，属于当日付费用户 → 可能属于"历史付费用户"范畴
- music-2.0 / 2.5 / 2.5+ 在请求限制表中仍可见（RM=6），属于"现有 API 服务"
- music-3.0 / 2.6 / cover 在请求限制表中未出现，主推模型实际能否调用存疑

**建议**：如需确认 music-3.0 实际可用性，建议用一个测试请求调用 `v1/music_generation` 并观察返回码（403 / 模型不存在 / 额度不足等）。

---

## 四、可用性总览

| 能力 | 是否可用 | 依据 |
|---|---|---|
| 语言模型（M2/M2.1/M2.5/M2.7/M3） | ✅ 可用 | 请求限制表列出 |
| TTS 语音合成 | ✅ 可用 | 请求限制表列出 |
| 音色克隆 / 音色设计 | ✅ 可用 | 请求限制表列出 |
| 视频生成（Hailuo / MiniMax-H3） | ✅ 可用 | 请求限制表 + 套餐含视频赠送 |
| 图像生成 | ✅ 可用 | 套餐权益内，共享文本额度 |
| 音乐生成 | ⚠️ 受限可用 | 仅历史付费用户可继续使用现有 API；music-2.x 可调，music-3.x 存疑 |

---

## 五、备注

- 控制台直接 URL 刷新访问 `/console/plan` 时偶现"Token Plan 未订阅"字样，但通过侧边栏点击或访问 `/console/usage` 均显示"订阅中"——以"订阅中"为准，属页面缓存问题。
- 控制台中尝试访问 `/console/models`、`/console/playground`、`/console/model-center` 等路径均返回 404，当前版本没有独立的"模型广场"入口。
