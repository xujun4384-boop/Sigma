# music_generate - 音乐组（AI 音乐生成）

**文本描述 → 音乐 mp3（纯音乐 / 自定义歌词 / 自动写词）。** 是「声音部门」的配乐来源，默认产出纯音乐，用作视频背景音乐（BGM）。

## 摘要
输入一段风格描述 → 生成音乐 mp3 → 返回 `output_path` 与实测时长，供「合成部门」铺底混音或直接交付。

## 三种创作模式（互斥，按参数自动判定）
| 模式 | 触发参数 | 说明 |
|---|---|---|
| **纯音乐**（默认） | `instrumental=true` | 无人声器乐，视频配乐首选；`lyrics` 会被忽略 |
| **自定义歌词** | `instrumental=false` + `lyrics` | 用你给的词演唱，建议带 `[Verse]/[Chorus]/[Bridge]` 结构标签 |
| **自动写词** | `instrumental=false` + `auto_lyrics=true` | 由模型按 `prompt` 主题自动写词并演唱 |

> 非纯音乐模式下，既没给 `lyrics` 也没开 `auto_lyrics` 会直接报错——请显式选定模式。

## 职责边界
- **本组只产音乐**：不做配乐铺轨、不做音量闪避、不做混音（这些属于合成部门）。
- 用于视频时，通常 `instrumental=true`，把 `output_path` 交给合成部门当 BGM。

## 参数
- `prompt`（string，必填）：风格/情绪/场景/乐器/BPM 的自然语言描述。写风格与用途，不要写歌词。
  纯音乐模式下**只需写乐器与情绪**（如「合成器铺底，弦乐主旋律，鼓组四四拍，90BPM」），
  不要写「无人声/纯音乐/别唱」——器乐约束由工具统一加，见下。
- `output_path`（string，必填）：输出 mp3 路径；相对路径自动放 `video_work/<project>/music/`。
- `project`（string，可选）：项目名，与视频工具保持一致。
- `instrumental`（boolean，可选，默认 true）：是否纯音乐。
- `lyrics`（string，可选）：自定义歌词，用 `[Verse]/[Chorus]` 等结构标签分段。
- `auto_lyrics`（boolean，可选，默认 false）：无歌词时是否自动写词。
- `format`（string，可选，默认 mp3）：输出音频格式。

## 纯音乐是怎么保证的（实测踩过的坑）
音乐模型对「无人声」「别唱」这类**否定句不敏感**；提示词里反复出现"人声/演唱/vocal"
反而可能把它当成素材线索，产出带哼唱或和声的版本。

所以 `instrumental=true` 时有**两道保险**，调用方不用自己写：
1. **接口层**：同时发 `is_instrumental=true` + `lyrics=""` + `lyrics_optimizer=false`
   （只发开关时，经代理转发有概率被丢字段，模型会回落到歌曲模式）。
2. **提示词层**：工具把任意描述包成器乐外壳——
   `纯器乐配乐，全部声部由乐器演奏。风格与情绪：<你的描述>。编曲：合成器铺底，弦乐与钢琴承担主旋律，鼓组与打击乐提供节奏。只做器乐，不安排主唱或合唱声部。`

如果加了之后**仍然出现人声**，说明服务端没有识别 `is_instrumental`（模型或代理层忽略了它），
这时改提示词收效有限，应该：换用直接支持纯器乐的模型/直连厂商端点，或改用现成曲库。
接口返回的 `extra_info` 会一并回传，可据此判断服务端有没有记录纯音乐标记。

## 输出
```
{
  "output_path": ".../video_work/<project>/music/bgm.mp3",
  "duration": 92.4,        // 秒
  "size_bytes": 2958421,
  "model": "minimax-music-v3.0",
  "provider": "tencent_tokenhub",
  "instrumental": true
}
```

## 与其它部门的关系
- 上游：导演给定配乐需求（题材/情绪/节奏）。
- 下游：**合成部门**（`compose_video`）用 `bgm` 参数铺底，自动循环铺满全片并与旁白混音。
- 依赖：音乐生成 API Key（见下）。

## 依赖
- 音乐生成 API Key：Settings → Skill Keys → 音乐生成（`musicGenApiKey`）。
- provider 可选「腾讯云 TokenHub」（默认，模型 `minimax-music-v3.0`）或「MiniMax 开放平台」。
- Key 获取：腾讯云 TokenHub 控制台（`console.cloud.tencent.com/tokenhub/apikey`），
  并需在「在线推理-语音模型」处开通对应模型后付费。

# ═══ 参数详情 ═══

# ── music_generate ──
# 文本描述 → 音乐 mp3。
#
# 参数:
#   prompt (string, 必填) 风格/情绪/场景/乐器/BPM 描述，如 "轻快的电子配乐，科技感，无人声"
#   output_path (string, 必填) 输出 mp3 路径（相对路径放 video_work/<project>/music/ 下）
#   project (string, 可选) 项目名，与视频工具保持一致
#   instrumental (boolean, 可选, 默认 true) 是否纯音乐
#   lyrics (string, 可选) 自定义歌词（带 [Verse]/[Chorus] 结构标签）
#   auto_lyrics (boolean, 可选, 默认 false) 自动写词
#   format (string, 可选, 默认 mp3) 输出格式
#
# 输出:
#   output_path: mp3 绝对路径
#   duration: 音乐时长（秒）
#   size_bytes: 文件字节数
#   model / provider: 实际使用的模型与 provider
