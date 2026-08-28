# wecom_email skill
# 企业微信邮箱（腾讯企业邮箱 exmail）收发工具。通过 SMTP 发送邮件，通过 IMAP 接收/读取/搜索邮件并管理邮件。
# 仅依赖 Python 标准库，无需额外依赖。
# 凭据默认由 Sigma 前端 Settings → Skill Keys 注入；仅独立 CLI 运行时才使用 .env。
#
# 使用场景
# - 代用户发送企业微信邮箱邮件（支持纯文本/HTML 正文、抄送、密送、附件）
# - 读取收件箱邮件列表与单封邮件详情
# - 按条件搜索邮件
# - 删除、标记已读/未读、移动邮件到文件夹、查看文件夹列表
# - 根据企业邮箱域名与环境（通用/信创）推荐客户端配置参数
#
# 包含 1 种工具:
#   wecom_email - 企业微信邮箱收发与管理
# ---------------------------------------------------------------------------

# ═══ 前置条件 ═══

1. 管理员已在企业微信管理端开放对应协议：
   - 企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限 → 开启 POP/SMTP 或 IMAP/SMTP 服务范围
   - 管理后台未设置服务范围时，成员端无法启用对应协议
2. 成员已在网页版企业邮箱开启服务：
   - 网页版登录企业邮箱 → 设置 → 收发信设置 → 开启服务
3. 在 Sigma 设置 → Skill Keys → 企业微信邮箱中填写：
   - 邮箱地址（完整企业邮箱地址，如 name@company.com）
   - 授权码/密码：普通登录用邮箱密码；开启安全登录时需使用「客户端授权码」
     （网页版企业邮箱 → 设置 → 邮箱绑定 → 生成客户端专用密码）
   - SMTP 服务器（默认 smtp.exmail.qq.com）、SMTP 端口（默认 465）
   - IMAP 服务器（默认 imap.exmail.qq.com）、IMAP 端口（默认 993）
4. 信创环境需使用信创专用服务器：
   - SMTP: xcsmtp.exmail.qq.com:465，IMAP: xcimap.exmail.qq.com:993，POP3: xcpop.exmail.qq.com:995
5. 服务器地址可覆盖，因此本 skill 也可适配其他支持 SMTP/IMAP 的邮箱。

# ═══ 操作参数 ═══

── action (必填) ──
操作类型，可选值：
  - send          : 发送邮件
  - list          : 列出指定文件夹的邮件列表
  - read          : 读取单封邮件详情
  - search        : 按条件搜索邮件
  - delete        : 删除邮件
  - mark_read     : 标记为已读
  - mark_unread   : 标记为未读
  - move          : 移动邮件到文件夹
  - folders       : 列出邮箱文件夹
  - config_advice : 根据域名/环境推荐客户端配置

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
  - mail_id (string): 邮件 UID（read/delete/mark_read/mark_unread/move 必填）
  - query (string): IMAP 搜索条件（search 必填），如 'SUBJECT "报告"' / 'UNSEEN' / 'FROM "xxx@company.com"'
  - target_folder (string): 移动目标文件夹（move 必填）

── 配置推荐参数 (config_advice) ──
  - domain (string): 企业邮箱域名，如 company.com；留空则使用当前账号域名
  - env_type (string): general（通用，默认） / xc（信创）

# ═══ 使用说明 ═══

发送邮件示例（LLM 调用参数）：
  action=send, to="user@company.com", subject="会议通知", body="明天上午 10 点开会"

读取收件箱列表：
  action=list, folder="INBOX", limit=20

读取单封邮件：
  action=read, folder="INBOX", mail_id="1234"

搜索未读邮件：
  action=search, folder="INBOX", query="UNSEEN"

获取客户端配置推荐：
  action=config_advice, domain="company.com", env_type="general"

# ═══ 命令行使用 ═══

```bash
# 发送邮件
python -m skills.wecom_email send --to user@company.com --subject "测试" --body "你好"

# 查看收件箱
python -m skills.wecom_email list --folder INBOX --limit 20

# 读取邮件
python -m skills.wecom_email read --mail-id 1234

# 获取配置推荐（信创环境）
python -m skills.wecom_email config_advice --domain company.com --env-type xc
```

# ═══ 重要规则 ═══

1. 授权码不是登录密码；开启安全登录后，第三方客户端必须使用客户端授权码
2. 发送使用 SMTP SSL（默认端口 465），接收使用 IMAP SSL（默认端口 993）
3. 邮件 UID 在文件夹内唯一，读取/删除/标记/移动均使用 UID
4. 删除、移动操作会真实修改邮箱，执行前应向用户确认
5. 管理后台未开放 IMAP/SMTP 或 POP/SMTP 服务范围时，成员端无法启用对应协议
6. 信创邮箱不支持 Exchange 协议；客户端不支持同步邮箱通讯录
