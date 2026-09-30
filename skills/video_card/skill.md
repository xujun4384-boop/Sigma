# video_card - 竖版卡片短视频（统一入口）

**竖版卡片短视频（9:16 无声）。** 顶部标题/副标题 + 中部素材卡片 + 底部打字机字幕，统一替代原 video_auto / video_custom / video_overlay 三个入口。

## 摘要
做新闻/资讯/产品/教程等**竖版卡片短视频**的唯一入口。接收内容或素材，产出无声 MP4（无旁白无 BGM）。

## 使用场景
- 竖版短视频、卡片式信息流视频（抖音/视频号/快手等 9:16）
- 新闻资讯、产品展示、活动回顾、教程演示等

## 与其它视频入口的区别（主 LLM 据此精确选择）
- **video_card** —— 竖版卡片短视频，**无声**，中部是图片或视频。素材可 AI 自动配图，也可用户手动提供。
- **video_produce** —— **完整流水线**：脚本设计+旁白(Doubao TTS)+画面生成+字幕合成，**带旁白**的成片。需求很自由、要配音选它。
- **video_cinematic** —— **电影级 AI 生视频**：纯 prompt 生图生视频，不走代码/卡片布局，风格化艺术短片。

## 关键参数
- `asset_source`: `auto`（AI 自动配图 + 自动提炼脚本）/ `user`（手动提供素材路径）
- `material_type`: `image`（静态图片）/ `video`（视频素材，可 `keep_audio` 保留音轨）
- 提供素材（user）时用 `scenes`：每项 `{text, duration, transition, image|media}`；提供原文（auto）时用 `news_content`。

## 说明
本入口为薄路由，按 `asset_source` / `material_type` 委托给内部工具执行，不重写渲染。