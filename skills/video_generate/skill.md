# video_generate skill
# ---------------------------------------------------------------------------
# 摘要
# 视频生成工具集。支持三种创作模式：预置模板、sandbox 自定义动画、多场景拼接合成。
# LLM 分析用户需求后，可选择模板快速生成或通过 sandbox 编写定制 HTML Canvas 动画。
# 多个场景可通过 sub_agent 并行录制，最后 video_compose 统一合成。
#
## 使用场景
# - 产品宣传视频制作
# - 数据报告动画展示
# - 品牌介绍动画
# - 教育培训内容视频化
# - 将文档/PPT 内容转化为视频
#
# 包含 3 种工具:
#   video_scene   - 单个场景录制（模板 or 自定义HTML → mp4）
#   video_tts     - 文本语音合成（text → mp3）
#   video_compose - 多场景拼接合成（video+audio+bgm+subtitle → mp4）
# ---------------------------------------------------------------------------

# ═══ 推荐工作流 ═══

# 快速模式（模板）:
#   1. 分析用户需求 → 确定项目名（如 "sigma_intro"）
#   2. video_scene(project="sigma_intro", template="particle_brand", params={...}, output_path="scene1.mp4")
#   3. video_tts(project="sigma_intro", text="...", output_path="vo.mp3")
#   4. video_compose(project="sigma_intro", scene_videos=["scene1.mp4"], scene_audios=["vo.mp3"], output_path="final.mp4")

# 创意模式（sandbox 自定义）⭐ 推荐:
#   1. 分析内容 → 项目名 → 确定视觉风格和动画构思
#   2. sandbox_run → write() 编写自定义 HTML Canvas 动画到 video_work/<项目名>/
#   3. video_scene(project="...", html_path="video_work/<项目名>/scene1.html", output_path="scene1.mp4")
#   4. video_tts(project="...", text="旁白文字", output_path="vo_01.mp3")
#   5. 重复 2-4 生成所有场景
#   6. video_compose(project="...", scene_videos=[...], scene_audios=[...], output_path="final.mp4")

# 并行模式（sub_agent 加速）:
#   1. 主 Agent 分析内容 → 项目名 → 生成分场景脚本
#   2. sub_agent(tasks=[
#        { type:"coder", description:"场景1录制", prompt:"... project='xxx' ..." },
#        { type:"coder", description:"场景2录制", prompt:"... project='xxx' ..." },
#        { type:"coder", description:"语音生成", prompt:"... project='xxx' ..." },
#      ])
#   3. 主 Agent: video_compose(project="xxx", ...) 最终合成

# ═══ HTML 动画规范（sandbox 自定义模式） ═══

# 自定义 HTML 必须满足以下接口:
#
# ```html
# <!DOCTYPE html>
# <html>
# <body>
# <canvas id="c"></canvas>
# <script>
# const W = 1920, H = 1080;
# const canvas = document.getElementById("c");
# canvas.width = W; canvas.height = H;
# const ctx = canvas.getContext("2d");
#
# let frame = 0;
# function draw() {
#   const progress = frame / (DURATION_SECONDS * 30);  // 0~1
#   // ... 你的动画逻辑 ...
#   frame++;
#   if (frame < DURATION_SECONDS * 30) requestAnimationFrame(draw);
# }
#
# // ⚠️ 必须暴露这两个接口
# window.CURRENT_FRAME = 0;
# window.updateAnimation = draw;
#
# draw();
# </script>
# </body>
# </html>
# ```

# ═══ 预置模板列表 ═══

# particle_brand  - 粒子汇聚 + 打字机品牌动画
#   参数: BRAND_NAME, SUBTITLE, TAGLINE, PRIMARY_COLOR, BG_COLOR,
#         PARTICLE_COUNT(200-2000), REVEAL_STYLE(typewriter/fade_in),
#         GLOW_INTENSITY(0-1), TITLE_SIZE

# data_counter    - 数字滚动 + 数据统计动画
#   参数: TITLE_TEXT, SUBTITLE, ACCENT_COLOR, STATS_JSON([{key,label,value},...])

# ═══ 输出目录约定 ═══

# 所有工具支持 project 参数，LLM 应根据内容分析为视频项目取名。
# 例如：project="vibe_coding_intro" 会产生:
#   video_work/
#   └── vibe_coding_intro/
#       ├── scene1.html     # sandbox 生成的动画
#       ├── scene1.mp4      # 录制结果
#       ├── vo_01.mp3       # 旁白
#       └── final.mp4       # 最终视频

# ⚠️ 重要规则:
# 1. 同一个视频的所有工具调用 MUST 使用相同的 project 名称
# 2. video_scene/video_tts 返回的 output_path 是绝对路径，后续调用直接使用
# 3. 自定义 HTML 也请写入 video_work/<项目名>/ 目录内

# ═══ 依赖要求 ═══

# 首次使用需安装:
#   pip install playwright moviepy edge-tts numpy
#   playwright install chromium
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── video_scene ──
# 录制单个视频场景。支持模板模式和自定义HTML模式。
#
# 参数:
#   output_path (string, 必填) 输出 mp4 文件路径
#   template (string, 可选) 模板名: particle_brand / data_counter
#   html_path (string, 可选) 自定义 HTML 文件路径（sandbox 创作）
#   params (object, 可选) 模板参数 JSON
#   duration (integer, 可选, 默认10) 录制时长（秒）
#   fps (integer, 可选, 默认30) 帧率
#   width (integer, 可选, 默认1920) 视频宽度
#   height (integer, 可选, 默认1080) 视频高度

# ── video_tts ──
# 文本转语音。使用微软 Edge TTS，免费。
#
# 参数:
#   text (string, 必填) 合成文本
#   output_path (string, 必填) 输出 mp3 路径
#   voice (string, 可选, 默认yunxi) 音色: xiaoxiao/xiaoyi(女) / yunxi/yunjian(男)

# ── video_compose ──
# 多场景拼接合成，叠加音频、BGM、字幕。
#
# 参数:
#   output_path (string, 必填) 最终输出 mp4 路径
#   scene_videos (array, 必填) 场景视频路径列表
#   scene_audios (array, 可选) 旁白音频路径列表（空字符串=无旁白）
#   subtitles (array, 可选) [[text, start_sec, end_sec], ...]
#   bgm_enabled (boolean, 可选, 默认true) 是否生成背景音乐
#   bgm_volume (number, 可选, 默认0.18) BGM音量
#   width (integer, 可选, 默认1920)
#   height (integer, 可选, 默认1080)
#   fps (integer, 可选, 默认30)
# ---------------------------------------------------------------------------
