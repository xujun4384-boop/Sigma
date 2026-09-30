# gmail skill
# Gmail 邮箱收发工具。通过 SMTP 发送邮件，通过 IMAP 接收/读取/搜索邮件并管理邮件。
# 仅依赖 Python 标准库，无需额外依赖。
# 凭据默认由 Sigma 前端 Settings → Skill Keys 注入；仅独立 CLI 运行时才使用 .env。
#
# 使用场景
# - 代用户发送 Gmail 邮件（支持纯文本/HTML 正文、抄送、密送、附件）
# - 读取收件箱、Sent Mail、Trash、自定义标签中的邮件列表与单封邮件详情
# - 按条件搜索邮件（支持标准 IMAP 与 Gmail 特有的 X-GM-RAW 全文搜索语法）
# - 删除、标记已读/未读、移动邮件到文件夹（Gmail 中等同于添加/移除标签）、查看文件夹列表
#
# 包含 1 种工具:
#   gmail - Gmail 邮箱收发与管理
# ---------------------------------------------------------------------------

# ═══ 前置条件 ═══

1. 已在 Google 账号开启「两步验证」
2. 已生成「应用专用密码」（App Password，16 位），并填入 Sigma 设置 → Skill Keys → Gmail：
   - 邮箱地址（完整 Gmail 地址，如 yourname@gmail.com）
   - 应用专用密码
   - SMTP 服务器（默认 smtp.gmail.com）、SMTP 端口（默认 465）
   - IMAP 服务器（默认 imap.gmail.com）、IMAP 端口（默认 993）
3. Gmail IMAP 默认启用，无需手动开启
4. ⚠️ Gmail 服务器在国外，国内网络需要代理才能访问

# ═══ 操作参数 ═══

── action (必填) ──
操作类型，可选值：
  - send        : 发送邮件
  - list        : 列出指定文件夹/标签的邮件列表
  - read        : 读取单封邮件详情
  - search      : 按条件搜索邮件
  - download    : 下载邮件附件到本地项目目录
  - delete      : 删除邮件（默认移到 [Gmail]/Trash）
  - mark_read   : 标记为已读
  - mark_unread : 标记为未读
  - move        : 移动邮件到文件夹/标签
  - folders     : 列出邮箱文件夹/标签

── 发送邮件参数 (send) ──
  - to (string, 必填): 收件人，多个地址用逗号或分号分隔
  - subject (string, 必填): 主题
  - body (string): 纯文本正文（与 html 至少提供一个）
  - html (string): HTML 正文
  - cc (string): 抄送
  - bcc (string): 密送
  - attachments (array): 附件本地文件路径列表

── 读取/搜索参数 ──
  - folder (string, 默认 INBOX): 邮箱文件夹/标签。Gmail 常用值:
      INBOX, [Gmail]/Sent Mail, [Gmail]/Trash, [Gmail]/Spam, [Gmail]/Starred, [Gmail]/Drafts
  - limit (integer, 默认 20): 返回数量上限（list/search）
  - offset (integer, 默认 0): 分页偏移（list）
  - mail_id (string): 邮件 UID（read/download/delete/mark_read/mark_unread/move 必填）
  - query (string): 搜索条件（search 必填），支持两种语法：
      1) 标准 IMAP: 'SUBJECT "报告"' / 'UNSEEN' / 'FROM "xxx@gmail.com"'
      2) Gmail 特有 X-GM-RAW: 'X-GM-RAW "has:attachment is:unread"' / 'X-GM-RAW "from:someone@gmail.com newer_than:7d"'
  - target_folder (string): 移动目标文件夹/标签（move 必填）
  - attachment_name (string): 要下载的附件文件名（download 时使用），留空则下载全部附件

# ═══ 使用说明 ═══

发送邮件示例（LLM 调用参数）：
  action=send, to="user@gmail.com", subject="会议通知", body="明天上午 10 点开会"

读取收件箱列表：
  action=list, folder="INBOX", limit=20

读取单封邮件：
  action=read, folder="INBOX", mail_id="1234"

搜索未读邮件（标准 IMAP）：
  action=search, folder="INBOX", query="UNSEEN"

搜索近 7 天带附件的未读邮件（Gmail 特有语法）：
  action=search, folder="INBOX", query='X-GM-RAW "has:attachment is:unread newer_than:7d"'

下载邮件全部附件：
  action=download, folder="INBOX", mail_id="1234"

下载指定附件：
  action=download, folder="INBOX", mail_id="1234", attachment_name="报告.pdf"

查看所有标签：
  action=folders

# ═══ 命令行使用 ═══

```bash
# 发送邮件
python -m skills.gmail send --to user@gmail.com --subject "测试" --body "你好"

# 查看收件箱
python -m skills.gmail list --folder INBOX --limit 20

# 读取邮件
python -m skills.gmail read --mail-id 1234

# Gmail 全文搜索
python -m skills.gmail search --query 'X-GM-RAW "has:attachment newer_than:7d"'

# 下载附件
python -m skills.gmail download --mail-id 1234
python -m skills.gmail download --mail-id 1234 --attachment-name "报告.pdf"
```

# ═══ 重要规则 ═══

1. **必须使用应用专用密码，不是 Gmail 登录密码**。生成路径：Google 账号 → 安全性 → 两步验证 → 应用专用密码
2. 发送使用 SMTP SSL（默认端口 465），接收使用 IMAP SSL（默认端口 993）
3. 邮件 UID 在文件夹内唯一，读取/删除/标记/移动均使用 UID
4. **删除邮件默认移动到 [Gmail]/Trash**（30 天后自动清空），而不是立即永久删除
5. Gmail 的"文件夹"实际是标签（Label），同一封邮件可同时属于多个标签
6. 移动邮件到文件夹相当于给邮件添加标签
7. **附件下载**：读取邮件后，使用 action=download 可将附件保存到当前项目目录的 downloads/gmail/<邮件UID>/ 下。可指定 attachment_name 下载单个附件，或留空下载全部
8. Gmail 服务器在国外，国内需要代理才能访问
