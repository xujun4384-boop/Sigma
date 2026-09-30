# mail_163 skill
# 163 邮箱收发工具。通过 SMTP 发送邮件，通过 IMAP 接收/读取/搜索邮件并管理邮件。
# 仅依赖 Python 标准库，无需额外依赖。
# 凭据默认由 Sigma 前端 Settings → Skill Keys 注入；仅独立 CLI 运行时才使用 .env。
#
# 使用场景
# - 代用户发送邮件（支持纯文本/HTML 正文、抄送、密送、附件）
# - 读取收件箱邮件列表与单封邮件详情
# - 按条件搜索邮件
# - 删除、标记已读/未读、移动邮件到文件夹、查看文件夹列表
#
# 包含 1 种工具:
#   mail_163 - 163 邮箱收发与管理
# ---------------------------------------------------------------------------

# ═══ 前置条件 ═══

1. 163 邮箱已在网页版开启对应服务：
   - 发信：开启 SMTP 服务
   - 收信：开启 IMAP 服务
2. 获取「客户端授权码」（不是登录密码），并在 Sigma 设置 → Skill Keys → 163 邮箱中填写：
   - 邮箱地址
   - 授权码
   - SMTP 服务器（默认 smtp.163.com）、SMTP 端口（默认 465）
   - IMAP 服务器（默认 imap.163.com）、IMAP 端口（默认 993）
3. 服务器地址可覆盖，因此本 skill 也可适配其他支持 SMTP/IMAP 的邮箱。

# ═══ 操作参数 ═══

── action (必填) ──
操作类型，可选值：
  - send        : 发送邮件
  - list        : 列出指定文件夹的邮件列表
  - read        : 读取单封邮件详情
  - search      : 按条件搜索邮件
  - download    : 下载邮件附件到本地项目目录
  - delete      : 删除邮件
  - mark_read   : 标记为已读
  - mark_unread : 标记为未读
  - move        : 移动邮件到文件夹
  - folders     : 列出邮箱文件夹

── 发送邮件参数 (send) ──
  - to (string, 必填): 收件人，多个地址用逗号或分号分隔
  - subject (string, 必填): 主题
  - body (string): 纯文本正文（与 html 至少提供一个）
  - html (string): HTML 正文
  - cc (string): 抄送
  - bcc (string): 密送
  - attachments (array): 附件本地文件路径列表

── 读取/搜索参数 ──
  - folder (string, 默认 INBOX): 邮箱文件夹
  - limit (integer, 默认 20): 返回数量上限（list/search）
  - offset (integer, 默认 0): 分页偏移（list）
  - mail_id (string): 邮件 UID（read/download/delete/mark_read/mark_unread/move 必填）
  - query (string): IMAP 搜索条件（search 必填），如 'SUBJECT "报告"' / 'UNSEEN' / 'FROM "xxx@163.com"'
  - target_folder (string): 移动目标文件夹（move 必填）
  - attachment_name (string): 要下载的附件文件名（download 时使用），留空则下载全部附件

# ═══ 使用说明 ═══

发送邮件示例（LLM 调用参数）：
  action=send, to="user@163.com", subject="会议通知", body="明天上午 10 点开会"

读取收件箱列表：
  action=list, folder="INBOX", limit=20

读取单封邮件：
  action=read, folder="INBOX", mail_id="1234"

搜索未读邮件：
  action=search, folder="INBOX", query="UNSEEN"

下载邮件全部附件：
  action=download, folder="INBOX", mail_id="1234"

下载指定附件：
  action=download, folder="INBOX", mail_id="1234", attachment_name="报告.pdf"

# ═══ 命令行使用 ═══

```bash
# 发送邮件
python -m skills.mail_163 send --to user@163.com --subject "测试" --body "你好"

# 查看收件箱
python -m skills.mail_163 list --folder INBOX --limit 20

# 读取邮件
python -m skills.mail_163 read --mail-id 1234

# 下载附件
python -m skills.mail_163 download --mail-id 1234
python -m skills.mail_163 download --mail-id 1234 --attachment-name "报告.pdf"
```

# ═══ 重要规则 ═══

1. 授权码不是登录密码，需在 163 网页邮箱中开启服务后获取
2. 发送使用 SMTP SSL（默认端口 465），接收使用 IMAP SSL（默认端口 993）
3. 邮件 UID 在文件夹内唯一，读取/删除/标记/移动均使用 UID
4. **附件下载**：读取邮件后，使用 action=download 可将附件保存到当前项目目录的 downloads/mail163/<邮件UID>/ 下。可指定 attachment_name 下载单个附件，或留空下载全部
5. 删除、移动操作会真实修改邮箱，执行前应向用户确认
