# wechat_publisher skill
# 微信公众平台草稿管理工具。管理 Access Token、创建/修改/查询草稿、上传图片素材。
# 凭据默认由 Sigma 前端 Settings → Skill Keys 注入；仅独立 CLI 运行时才使用 .env。
## 使用场景
# - 需要在微信公众号后台自动创建、修改或查询草稿
# - 需要上传图片素材到微信公众号（内容图片或封面图）
# - 需要管理微信公众号的 Access Token
# ⚠️ 重要限制（2025年7月起）：
# 微信公众平台自 2025年7月起收回发布接口权限：
# - 个人主体账号、企业主体未认证账号：只能通过 API 存入草稿箱，无法自动发布
# - 企业主体已微信认证（蓝V）账号：可以使用 freepublish/submit 接口发布
# 本 Skill 默认聚焦「自动写稿进草稿箱 + 人工确认发布」的工作流。
# 发布操作需在公众号后台手动点击，或用浏览器自动化（Puppeteer/Playwright）模拟操作。
# 前置条件：
# 1. 已注册微信公众号（个人订阅号即可创建草稿，推荐企业认证号发布）
# 2. 已在公众号后台获取 AppID 和 AppSecret
# 3. 已将服务器 IP 加入公众号后台的 IP 白名单
# 4. 在项目 .env 文件中配置 WECHAT_APPID 和 WECHAT_APPSECRET
# 包含工具: wechat_publish
# ---------------------------------------------------------------------------

# ═══ 核心设计 ═══

wechat_publish 封装微信公众号常用 API，核心流程：上传封面图 → 新建草稿 → 人工发布。

所有账号（含个人号、测试号）均可使用草稿创建和素材上传接口。
发布（freepublish/submit）仅企业认证号可用，不在本 Skill 默认流程中。

Token 自动管理：首次调用时自动获取 access_token（有效期 7200 秒），
过期后自动刷新，无需手动管理。

# ═══ 操作参数 ═══

── action (必填) ──
操作类型，可选值：
  - get_token      : 获取当前有效的 Access Token
  - add_draft      : 新建草稿
  - update_draft   : 修改已有草稿
  - get_draft      : 获取草稿详情
  - delete_draft   : 删除草稿
  - list_drafts    : 获取草稿列表
  - count_drafts   : 获取草稿总数
  - upload_image   : 上传图片（用于文章内容插图，返回 URL）
  - upload_material: 上传永久素材（用于封面图等，返回 media_id）
  - push_draft     : 一键存草稿：上传封面图 → 创建草稿（发布需人工确认）
  - publish        : 发布草稿为正式文章（⚠️ 仅企业认证号可用）

── 草稿操作参数 ──

add_draft / update_draft 需要的 articles 字段（JSON 数组）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 标题（不超过64字） |
| content | string | 是 | 正文 HTML 内容 |
| author | string | 否 | 作者 |
| digest | string | 否 | 摘要 |
| content_source_url | string | 否 | 原文链接 |
| thumb_media_id | string | 是 | 封面图素材 media_id |
| need_open_comment | int | 否 | 是否开启评论（0/1） |
| only_fans_can_comment | int | 否 | 是否仅粉丝可评论（0/1） |
| show_cover_pic | int | 否 | 是否显示封面（0/1） |

update_draft 额外参数：
  - media_id (string, 必填): 要修改的草稿 media_id
  - index (int, 必填): 要修改的文章在草稿中的位置（从0开始）

get_draft / delete_draft / publish 参数：
  - media_id (string, 必填): 草稿 media_id

list_drafts 参数：
  - offset (int, 默认 0): 分页偏移
  - count (int, 默认 20): 每页数量

── 素材上传参数 ──

upload_image（上传内容图片，返回 URL）：
  - file_path (string, 必填): 本地图片文件路径

upload_material（上传永久素材，返回 media_id）：
  - file_path (string, 必填): 本地文件路径
  - type (string, 默认 "image"): 素材类型（image/voice/video/thumb）

# ═══ 一键存草稿参数 ═══

push_draft 有两种内容模式（二选一）：

**Markdown 模式（推荐）：**
  - markdown (string, 可选): 文章正文的 Markdown 格式内容。工具会自动调用 wenyan-cli
    将 Markdown 转换为微信公众号兼容的 HTML，支持多主题和代码高亮。
    与 content 二选一。
  - theme (string, 默认 "lapis"): wenyan 渲染主题
    可选: default, orangeheart, rainbow, lapis, pie, maize, purple, phycat
  - highlight (string, 默认 "solarized-light"): 代码高亮主题
    可选: atom-one-dark, atom-one-light, dracula, github-dark, github,
    monokai, solarized-dark, solarized-light, xcode
  - mac_style (boolean, 默认 true): 是否使用 Mac 风格代码块（红黄绿三色圆点）
  - footnote (boolean, 默认 true): 是否将链接转为脚注

**HTML 模式（兼容旧版）：**
  - content (string, 可选): 文章正文的 HTML 格式内容。
    与 markdown 二选一。

**通用参数：**
  - title (string, 必填): 文章标题
  - cover_image (string, 必填): 封面图本地路径
  - author (string, 可选): 作者
  - digest (string, 可选): 摘要
  - content_source_url (string, 可选): 原文链接
  - style (string, 可选): 排版样式，设为 "wechat" 自动应用微信专业排版
    （仅在 HTML 模式或 markdown 降级时生效，wenyan 已自带精美排版）

**前置条件：**
  1. Node.js >= 14（wenyan-cli 依赖）
  2. wenyan-cli 已安装: npm install -g @wenyan-md/cli

正文插图自动上传：如果 content（wenyan 转换后的 HTML）中的 <img> 标签 src
指向本地文件路径（不以 http/https/data 开头），push_draft 会自动上传该图片
到微信图床并替换为微信 URL。

微信排版（style="wechat"）会自动为 HTML 元素添加内联样式：
- 标题 h1-h4：分级字号、颜色、装饰线
- 正文 p：15px #3f3f3f、1.75 行高、两端对齐
- 引用 blockquote：左侧蓝色边框、灰色背景
- 图片 img：自适应宽度、居中、圆角
- 代码 code/pre：等宽字体、暗色背景
- 容器：677px 最大宽度、系统字体栈

# ═══ 账号权限对照 ═══

| 操作 | 个人订阅号 | 企业未认证 | 企业已认证(蓝V) |
|------|:---:|:---:|:---:|
| draft/add (草稿) | ✅ | ✅ | ✅ |
| draft/update | ✅ | ✅ | ✅ |
| media/uploadimg | ✅ | ✅ | ✅ |
| material/add | ✅ | ✅ | ✅ |
| freepublish/submit (发布) | ❌ | ❌ | ✅ |
| mass/sendall (群发) | ❌ | ❌ | ✅ |

# ═══ 凭据配置 ═══

正常运行时，凭据由 Sigma 前端 **Settings → Skill Keys** 自动注入到本技能：
- `wechatAppId` → 微信公众号 AppID
- `wechatAppSecret` → 微信公众号 AppSecret
- `wechatRelayUrl` → 可选的请求中转地址
- `wechatRelayKey` → 可选的请求中转密钥

**不要读取 `.env`，不要通过 bash 检查 `.env`，不要要求用户把 Skill Keys 复制到 `.env`，也不要打开浏览器去微信公众平台获取这些凭据。**

仅当用户直接从命令行运行 `skills/wechat_publisher/__init__.py` 时，才允许使用项目 `.env` 作为 CLI 回退配置：

```
WECHAT_APPID=wx1234567890abcdef
WECHAT_APPSECRET=your_app_secret_here
```

# ═══ 命令行使用 ═══

```bash
# 获取 Token
python skills/wechat_publisher/__init__.py get_token

# 查看草稿列表
python skills/wechat_publisher/__init__.py list_drafts

# 一键存草稿（封面图 → 草稿箱）
python skills/wechat_publisher/__init__.py push_draft \
  --title "文章标题" \
  --content "<p>文章正文</p>" \
  --cover "./cover.jpg" \
  --author "作者名"

# 上传封面图素材
python skills/wechat_publisher/__init__.py upload_material --file_path ./cover.jpg
```

# ═══ 重要规则 ═══

1. Access Token 有效期 7200 秒（2小时），工具内部自动缓存和刷新
2. 上传图片（upload_image）得到的 URL 可直接用于文章 content 的 `<img>` 标签
3. 封面图必须通过 upload_material 上传为永久素材，获取 media_id
4. 草稿存入后可登录公众号后台手动点击发布
5. 发布接口（publish）仅企业认证号可用，个人号/un认证号调用会返回 api unauthorized
6. freepublish/submit 发布的文章不会主动推送给粉丝（与群发不同），但会生成永久链接
7. 如需全自动发布（含个人号），需使用浏览器自动化方案（Playwright/Puppeteer 模拟后台操作）
