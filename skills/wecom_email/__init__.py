"""
企业微信邮箱（腾讯企业邮箱 exmail）收发 Skill。

支持：SMTP 发送邮件、IMAP 接收/读取/搜索/管理邮件、按企业域名推荐客户端配置。
仅依赖 Python 标准库 smtplib + imaplib，无第三方依赖。

凭据通过 Sigma 前端 Settings → Skill Keys 注入，或从 .env 文件读取（CLI 独立运行回退）。
服务器地址提供企业微信邮箱默认值（smtp.exmail.qq.com / imap.exmail.qq.com），
支持信创环境（xc 前缀服务器），可在 Settings 中覆盖。

参考：https://open.work.weixin.qq.com/help2/pc/19886
"""
from __future__ import annotations

import os
from email import encoders
from email.header import Header, decode_header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import getaddresses, parseaddr

import imaplib
import smtplib

from sigma_logger import log
from skills.base import BaseTool, ToolParameter, ToolResult

# 企业微信邮箱默认服务器配置（通用环境，可在 Settings → Skill Keys 中覆盖）
DEFAULT_SMTP_HOST = "smtp.exmail.qq.com"
DEFAULT_SMTP_PORT = 465  # SSL
DEFAULT_IMAP_HOST = "imap.exmail.qq.com"
DEFAULT_IMAP_PORT = 993  # SSL

VALID_ACTIONS = [
    "send",           # 发送邮件
    "list",           # 列出收件箱邮件
    "read",           # 读取单封邮件
    "search",         # 搜索邮件
    "download",       # 下载邮件附件到本地
    "delete",         # 删除邮件
    "mark_read",      # 标记已读
    "mark_unread",    # 标记未读
    "move",           # 移动邮件到文件夹
    "folders",        # 列出文件夹
    "config_advice",  # 根据域名/环境推荐客户端配置
]

# 信创环境服务器映射（通用 → 信创）
XC_HOST_MAP = {
    "smtp.exmail.qq.com": "xcsmtp.exmail.qq.com",
    "imap.exmail.qq.com": "xcimap.exmail.qq.com",
    "pop.exmail.qq.com": "xcpop.exmail.qq.com",
}


def _decode_header_value(value: str | None) -> str:
    """解码 RFC 2047 编码的邮件头（处理中文主题/发件人等）。"""
    if not value:
        return ""
    parts = decode_header(value)
    result: list[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            result.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(text)
    return "".join(result)


def _format_address(value: str | None) -> str:
    """解码并格式化地址头，返回 '姓名 <addr>' 或 'addr'。"""
    if not value:
        return ""
    decoded = _decode_header_value(value)
    name, addr = parseaddr(decoded)
    if name and addr:
        return f"{name} <{addr}>"
    return addr or decoded


def _parse_recipients(value: str | None) -> list[str]:
    """解析收件人字符串（支持逗号/分号分隔、'Name <addr>' 格式），返回纯地址列表。"""
    if not value:
        return []
    addrs = [a for _, a in getaddresses([value]) if a]
    return addrs


class WecomEmailTool(BaseTool):
    name = "wecom_email"
    description = (
        "企业微信邮箱（腾讯企业邮箱 exmail）收发工具。支持 SMTP 发送邮件、IMAP 接收/读取/搜索邮件、"
        "以及删除、标记已读/未读、移动邮件等管理操作；还可根据企业邮箱域名/环境（通用或信创）"
        "推荐 POP3/IMAP/SMTP/Exchange 客户端配置。"
        "凭据已由 Sigma 前端 Settings → Skill Keys 自动注入，"
        "不得读取 .env、不得要求用户配置 .env。"
        "发送邮件需管理员/成员开启 SMTP 服务；读取邮件需开启 IMAP 服务；"
        "若开启安全登录，密码处需使用客户端授权码。"
    )

    parameters = [
        ToolParameter(
            "action",
            "string",
            "操作类型: send / list / read / search / delete / mark_read / mark_unread / move / folders / config_advice",
            required=True,
            enum=VALID_ACTIONS,
        ),
        ToolParameter("to", "string", "收件人地址（send 时使用），多个地址用逗号或分号分隔", required=False),
        ToolParameter("subject", "string", "邮件主题（send 时使用）", required=False),
        ToolParameter("body", "string", "纯文本正文（send 时使用）", required=False),
        ToolParameter("html", "string", "HTML 正文（send 时使用，与 body 可同时提供）", required=False),
        ToolParameter("cc", "string", "抄送地址（send 时使用），多个地址用逗号或分号分隔", required=False),
        ToolParameter("bcc", "string", "密送地址（send 时使用），多个地址用逗号或分号分隔", required=False),
        ToolParameter("attachments", "array", "附件本地文件路径列表（send 时使用）", required=False),
        ToolParameter("folder", "string", "邮箱文件夹（list/read/search 时使用），默认 INBOX", required=False, default="INBOX"),
        ToolParameter("limit", "integer", "返回邮件数量上限（list/search 时使用），默认 20", required=False, default=20),
        ToolParameter("offset", "integer", "分页偏移（list 时使用），默认 0", required=False, default=0),
        ToolParameter("mail_id", "string", "邮件 UID（read/download/delete/mark_read/mark_unread/move 时使用）", required=False),
        ToolParameter("query", "string", "IMAP 搜索条件（search 时使用），如 'SUBJECT \"报告\"' / 'UNSEEN' / 'FROM \"xxx@company.com\"'", required=False),
        ToolParameter("target_folder", "string", "目标文件夹（move 时使用）", required=False),
        ToolParameter("attachment_name", "string", "要下载的附件文件名（download 时使用），留空则下载全部附件", required=False),
        ToolParameter("domain", "string", "企业邮箱域名（config_advice 时使用），如 company.com；留空则使用当前账号域名", required=False),
        ToolParameter("env_type", "string", "环境类型（config_advice 时使用）: general（通用） / xc（信创），默认 general", required=False, default="general", enum=["general", "xc"]),
    ]

    def __init__(
        self,
        cwd: str = ".",
        address: str | None = None,
        auth_code: str | None = None,
        smtp_host: str | None = None,
        smtp_port: str | None = None,
        imap_host: str | None = None,
        imap_port: str | None = None,
    ):
        super().__init__(cwd)
        # None 表示未从 SkillManager 传入（独立 CLI 运行）
        self._from_skill_manager = address is not None
        self._address: str = address or ""
        self._auth_code: str = auth_code or ""
        self._smtp_host: str = smtp_host or DEFAULT_SMTP_HOST
        self._smtp_port: int = self._to_int(smtp_port, DEFAULT_SMTP_PORT)
        self._imap_host: str = imap_host or DEFAULT_IMAP_HOST
        self._imap_port: int = self._to_int(imap_port, DEFAULT_IMAP_PORT)
        # 只有独立 CLI 运行时才回退到 .env
        if not self._from_skill_manager:
            self._load_from_env()

    @staticmethod
    def _to_int(value: str | None, default: int) -> int:
        if value in (None, ""):
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _load_from_env(self):
        """从 .env 文件加载配置（作为 CLI 独立运行时的回退方式）。"""
        try:
            from dotenv import load_dotenv
            env_path = self._resolve_path(".env")
            if env_path.exists():
                load_dotenv(env_path)
        except Exception:
            pass
        self._address = os.getenv("WECOM_EMAIL_ADDRESS", "")
        self._auth_code = os.getenv("WECOM_EMAIL_AUTH_CODE", "")
        self._smtp_host = os.getenv("WECOM_EMAIL_SMTP_HOST", DEFAULT_SMTP_HOST)
        self._smtp_port = self._to_int(os.getenv("WECOM_EMAIL_SMTP_PORT"), DEFAULT_SMTP_PORT)
        self._imap_host = os.getenv("WECOM_EMAIL_IMAP_HOST", DEFAULT_IMAP_HOST)
        self._imap_port = self._to_int(os.getenv("WECOM_EMAIL_IMAP_PORT"), DEFAULT_IMAP_PORT)

    def _ensure_config(self) -> str | None:
        if not self._address or not self._auth_code:
            source = ".env (WECOM_EMAIL_ADDRESS / WECOM_EMAIL_AUTH_CODE)" if not self._from_skill_manager else "Settings → Skill Keys"
            return (
                "未配置企业微信邮箱凭据。请在 Sigma 设置 → Skill Keys 中填写邮箱地址和授权码"
                f"（当前来源: {source}）。"
                "需管理员在企业微信管理端开启 POP/SMTP 或 IMAP/SMTP 服务，"
                "成员在网页版企业邮箱 → 设置 → 收发信设置 中开启服务；"
                "若开启安全登录，授权码在网页版企业邮箱 → 设置 → 邮箱绑定 中生成。"
            )
        return None

    # ─── SMTP 发送 ───

    def _send(self, to: str, subject: str, body: str, html: str,
              cc: str, bcc: str, attachments: list | None) -> ToolResult:
        config_err = self._ensure_config()
        if config_err:
            return ToolResult.fail(config_err)
        if not to:
            return ToolResult.fail("缺少收件人参数 to")
        if not subject:
            return ToolResult.fail("缺少主题参数 subject")
        if not body and not html:
            return ToolResult.fail("缺少正文参数 body 或 html")

        recipients = _parse_recipients(to)
        recipients += _parse_recipients(cc)
        recipients += _parse_recipients(bcc)
        if not recipients:
            return ToolResult.fail("无法从 to/cc/bcc 中解析出有效收件地址")

        # 构建邮件
        if html:
            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body or "", "plain", "utf-8"))
            alt.attach(MIMEText(html, "html", "utf-8"))
            msg: MIMEMultipart = MIMEMultipart()
            msg.attach(alt)
        else:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body, "plain", "utf-8"))

        msg["From"] = self._address
        msg["To"] = to
        msg["Subject"] = Header(subject, "utf-8")
        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc

        attachment_errors: list[str] = []
        for path in attachments or []:
            err = self._add_attachment(msg, path)
            if err:
                attachment_errors.append(err)

        try:
            with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=60) as server:
                server.login(self._address, self._auth_code)
                server.sendmail(self._address, recipients, msg.as_string())
        except smtplib.SMTPAuthenticationError as e:
            return ToolResult.fail(
                f"SMTP 认证失败（请检查邮箱地址和授权码；若开启安全登录需使用客户端授权码）: {e}"
            )
        except (smtplib.SMTPException, OSError) as e:
            return ToolResult.fail(f"SMTP 发送失败: {e}")

        parts = [f"邮件已发送", f"收件人: {', '.join(recipients)}", f"主题: {subject}"]
        if attachment_errors:
            parts.append("附件警告:\n  - " + "\n  - ".join(attachment_errors))
        return ToolResult.ok("\n".join(parts))

    def _add_attachment(self, msg: MIMEMultipart, file_path: str) -> str | None:
        """添加附件，返回错误信息（成功返回 None）。"""
        fp = self._resolve_path(file_path)
        if not fp.exists():
            return f"附件不存在: {file_path}"
        if fp.is_dir():
            return f"附件是目录而非文件: {file_path}"
        try:
            part = MIMEBase("application", "octet-stream")
            with open(fp, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", "attachment",
                filename=("utf-8", "", fp.name),
            )
            msg.attach(part)
            return None
        except OSError as e:
            return f"附件读取失败 {file_path}: {e}"

    # ─── IMAP 连接 ───

    def _imap_connect(self, folder: str):
        """建立 IMAP 连接并选中文件夹，返回 (imap, error)。"""
        config_err = self._ensure_config()
        if config_err:
            return None, config_err
        try:
            imap = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
        except (imaplib.IMAP4.error, OSError) as e:
            log.warning(f"[WecomEmail] IMAP 连接失败 host={self._imap_host}:{self._imap_port} | {e}")
            return None, f"IMAP 连接失败（请确认已开启 IMAP 服务）: {e}"
        try:
            login_typ, login_data = imap.login(self._address, self._auth_code)
            log.info(
                f"[WecomEmail] IMAP 登录 | account={'***' if self._address else '(空)'} "
                f"typ={login_typ} data={login_data!r}"
            )
        except imaplib.IMAP4.error as e:
            log.warning(f"[WecomEmail] IMAP 登录失败 account={'***' if self._address else '(空)'} | {e}")
            try:
                imap.logout()
            except Exception:
                pass
            return None, f"IMAP 登录失败（请检查邮箱地址和授权码，并确认已开启 IMAP 服务）: {e}"
        typ, data = imap.select(folder, readonly=False)
        if typ != "OK":
            log.warning(f"[WecomEmail] IMAP 打开文件夹失败 folder={folder} typ={typ} data={data!r}")
            try:
                imap.logout()
            except Exception:
                pass
            err_text = data[0].decode(errors="replace") if data and data[0] else str(data)
            return None, f"无法打开文件夹: {folder}（服务器返回: {err_text}）"
        return imap, None

    @staticmethod
    def _uid_bytes(uid: str) -> bytes:
        return uid.encode("ascii", "ignore")

    def _fetch_raw(self, imap, uid: str, parts: str) -> bytes | None:
        """按 UID 抓取指定部分，返回原始字节；失败返回 None。"""
        typ, data = imap.uid("fetch", self._uid_bytes(uid), parts)
        if typ != "OK" or not data:
            return None
        for item in data:
            if isinstance(item, tuple):
                return item[1]
        return None

    def _parse_message(self, raw: bytes):
        """解析完整邮件，返回 dict（subject/from/to/date/body/attachments）。"""
        from email import message_from_bytes
        msg = message_from_bytes(raw)
        return {
            "subject": _decode_header_value(msg.get("Subject")),
            "from": _format_address(msg.get("From")),
            "to": _format_address(msg.get("To")),
            "date": msg.get("Date", ""),
            "body": self._extract_body(msg),
            "attachments": self._extract_attachments(msg),
        }

    def _extract_body(self, msg) -> str:
        if msg.is_multipart():
            text_parts = []
            html_parts = []
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    text_parts.append(part)
                elif ctype == "text/html":
                    html_parts.append(part)
            for part in text_parts or html_parts:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
            return ""
        payload = msg.get_payload(decode=True)
        if payload is None:
            return msg.get_payload() or ""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")

    def _extract_attachments(self, msg) -> list[str]:
        attachments: list[str] = []
        for part in msg.walk():
            if part.get_content_disposition() == "attachment" or part.get_filename():
                name = _decode_header_value(part.get_filename())
                attachments.append(name or "未命名附件")
        return attachments

    # ─── IMAP 各操作 ───

    def _handle_list(self, folder: str, limit: int, offset: int) -> ToolResult:
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            typ, data = imap.uid("search", None, "ALL")
            if typ != "OK":
                return ToolResult.fail(f"搜索邮件失败: {data}")
            uids = data[0].split()
            total = len(uids)
            uids = list(reversed(uids))[offset:offset + limit]
            lines = [f"文件夹 {folder} 共 {total} 封邮件，当前显示 {len(uids)} 封\n"]
            for uid in uids:
                header_raw = self._fetch_raw(imap, uid.decode(), "(BODY.PEEK[HEADER])")
                if not header_raw:
                    continue
                from email import message_from_bytes
                head = message_from_bytes(header_raw)
                subject = _decode_header_value(head.get("Subject")) or "(无主题)"
                sender = _format_address(head.get("From"))
                date = head.get("Date", "")
                lines.append(f"[{uid.decode()}] {subject} | 来自: {sender} | {date}")
            return ToolResult.ok("\n".join(lines))
        finally:
            self._logout(imap)

    def _handle_read(self, folder: str, mail_id: str) -> ToolResult:
        if not mail_id:
            return ToolResult.fail("缺少邮件 UID 参数 mail_id")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            raw = self._fetch_raw(imap, mail_id, "(RFC822)")
            if not raw:
                return ToolResult.fail(f"未找到邮件: {mail_id}")
            info = self._parse_message(raw)
            lines = [
                f"主题: {info['subject']}",
                f"发件人: {info['from']}",
                f"收件人: {info['to']}",
                f"日期: {info['date']}",
            ]
            if info["attachments"]:
                lines.append(f"附件: {', '.join(info['attachments'])}")
                lines.append("提示: 使用 action=download 可将附件下载到本地项目目录")
            lines.append("\n正文:\n" + (info["body"] or "(无正文)"))
            return ToolResult.ok("\n".join(lines))
        finally:
            self._logout(imap)

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，移除 Windows/macOS/Linux 不允许的字符，并处理换行/回车。"""
        cleaned = filename.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        illegal_chars = '<>:"/\\|?*'
        for ch in illegal_chars:
            cleaned = cleaned.replace(ch, "_")
        cleaned = cleaned.strip(" .")
        if not cleaned:
            cleaned = "未命名附件"
        return cleaned

    def _handle_download(self, folder: str, mail_id: str, attachment_name: str) -> ToolResult:
        """下载邮件附件到当前工作目录的 downloads/wecom_email/<uid>/ 下。"""
        if not mail_id:
            return ToolResult.fail("缺少邮件 UID 参数 mail_id")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            raw = self._fetch_raw(imap, mail_id, "(RFC822)")
            if not raw:
                return ToolResult.fail(f"未找到邮件: {mail_id}")
            from email import message_from_bytes
            msg = message_from_bytes(raw)

            from pathlib import Path
            save_dir = Path(self.cwd) / "downloads" / "wecom_email" / mail_id
            save_dir.mkdir(parents=True, exist_ok=True)

            downloaded: list[str] = []
            skipped: list[str] = []
            errors: list[str] = []
            for part in msg.walk():
                if part.get_content_disposition() != "attachment" and not part.get_filename():
                    continue
                raw_filename = _decode_header_value(part.get_filename()) or "未命名附件"
                filename = self._sanitize_filename(raw_filename)
                if attachment_name and raw_filename != attachment_name and filename != attachment_name:
                    skipped.append(raw_filename)
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    skipped.append(f"{raw_filename} (无法解码)")
                    continue
                try:
                    save_path = save_dir / filename
                    with open(save_path, "wb") as f:
                        f.write(payload)
                    downloaded.append(f"{raw_filename} -> {save_path}")
                except OSError as e:
                    errors.append(f"{raw_filename} (保存失败: {e})")

            if not downloaded and not errors:
                if attachment_name:
                    return ToolResult.fail(f"未找到附件: {attachment_name}，可用附件: {', '.join(skipped)}")
                return ToolResult.ok("该邮件没有附件")

            result = f"已下载 {len(downloaded)} 个附件到 {save_dir}"
            if downloaded:
                result += "\n" + "\n".join(downloaded)
            if errors:
                result += f"\n失败 {len(errors)} 个:\n" + "\n".join(errors)
            if skipped and attachment_name:
                result += f"\n跳过: {', '.join(skipped)}"
            return ToolResult.ok(result)
        finally:
            self._logout(imap)

    def _handle_search(self, folder: str, query: str, limit: int) -> ToolResult:
        if not query:
            return ToolResult.fail("缺少搜索条件参数 query")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            typ, data = imap.uid("search", None, query)
            if typ != "OK":
                return ToolResult.fail(f"搜索失败: {data}")
            uids = data[0].split()
            uids = list(reversed(uids))[:limit]
            if not uids:
                return ToolResult.ok(f"未找到匹配的邮件（条件: {query}）")
            lines = [f"找到 {len(uids)} 封匹配邮件\n"]
            for uid in uids:
                header_raw = self._fetch_raw(imap, uid.decode(), "(BODY.PEEK[HEADER])")
                if not header_raw:
                    continue
                from email import message_from_bytes
                head = message_from_bytes(header_raw)
                subject = _decode_header_value(head.get("Subject")) or "(无主题)"
                sender = _format_address(head.get("From"))
                date = head.get("Date", "")
                lines.append(f"[{uid.decode()}] {subject} | 来自: {sender} | {date}")
            return ToolResult.ok("\n".join(lines))
        finally:
            self._logout(imap)

    def _handle_delete(self, folder: str, mail_id: str) -> ToolResult:
        if not mail_id:
            return ToolResult.fail("缺少邮件 UID 参数 mail_id")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            typ, _ = imap.uid("store", self._uid_bytes(mail_id), "+FLAGS", "\\Deleted")
            if typ != "OK":
                return ToolResult.fail(f"删除失败: {mail_id}")
            imap.expunge()
            return ToolResult.ok(f"邮件 {mail_id} 已删除")
        finally:
            self._logout(imap)

    def _handle_mark(self, folder: str, mail_id: str, read: bool) -> ToolResult:
        if not mail_id:
            return ToolResult.fail("缺少邮件 UID 参数 mail_id")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            flag = "+FLAGS" if read else "-FLAGS"
            typ, _ = imap.uid("store", self._uid_bytes(mail_id), flag, "\\Seen")
            if typ != "OK":
                return ToolResult.fail(f"标记操作失败: {mail_id}")
            state = "已读" if read else "未读"
            return ToolResult.ok(f"邮件 {mail_id} 已标记为{state}")
        finally:
            self._logout(imap)

    def _handle_move(self, folder: str, mail_id: str, target_folder: str) -> ToolResult:
        if not mail_id:
            return ToolResult.fail("缺少邮件 UID 参数 mail_id")
        if not target_folder:
            return ToolResult.fail("缺少目标文件夹参数 target_folder")
        imap, err = self._imap_connect(folder)
        if err:
            return ToolResult.fail(err)
        try:
            typ, _ = imap.uid("copy", self._uid_bytes(mail_id), target_folder)
            if typ != "OK":
                return ToolResult.fail(f"移动失败（复制到 {target_folder} 出错）: {mail_id}")
            imap.uid("store", self._uid_bytes(mail_id), "+FLAGS", "\\Deleted")
            imap.expunge()
            return ToolResult.ok(f"邮件 {mail_id} 已移动到 {target_folder}")
        finally:
            self._logout(imap)

    def _handle_folders(self) -> ToolResult:
        imap, err = self._imap_connect("INBOX")
        if err:
            return ToolResult.fail(err)
        try:
            typ, data = imap.list()
            if typ != "OK":
                return ToolResult.fail(f"获取文件夹列表失败: {data}")
            folders: list[str] = []
            for item in data:
                if isinstance(item, bytes):
                    line = item.decode("utf-8", errors="replace")
                    parts = line.split('"')
                    if parts:
                        name = parts[-1].strip()
                        if name:
                            folders.append(name)
            if not folders:
                return ToolResult.ok("未获取到文件夹")
            return ToolResult.ok("邮箱文件夹:\n  " + "\n  ".join(folders))
        finally:
            self._logout(imap)

    # ─── 配置推荐 ───

    def _handle_config_advice(self, domain: str, env_type: str) -> ToolResult:
        """根据企业邮箱域名与环境类型，推荐客户端配置。"""
        if not domain:
            if self._address and "@" in self._address:
                domain = self._address.split("@", 1)[1]
            else:
                return ToolResult.fail("缺少域名参数 domain（或先在 Skill Keys 中配置邮箱地址）")

        xc = env_type == "xc"
        smtp_host = XC_HOST_MAP["smtp.exmail.qq.com"] if xc else DEFAULT_SMTP_HOST
        imap_host = XC_HOST_MAP["imap.exmail.qq.com"] if xc else DEFAULT_IMAP_HOST
        pop_host = XC_HOST_MAP["pop.exmail.qq.com"] if xc else "pop.exmail.qq.com"
        env_label = "信创环境" if xc else "通用环境"

        lines = [
            f"企业微信邮箱客户端配置推荐（{env_label}）",
            f"域名: {domain}",
            "",
            "【开启服务】",
            "  管理员: 企业微信管理端 → 协作 → 邮件 → 安全管理 → 客户端访问权限 → 开启 POP/SMTP 或 IMAP/SMTP 服务范围",
            "  成员: 网页版企业邮箱 → 设置 → 收发信设置 → 开启服务",
            "",
            "【IMAP/SMTP（推荐）】",
            f"  接收服务器: {imap_host} | 端口: 993 | 加密: SSL",
            f"  发送服务器: {smtp_host} | 端口: 465 | 加密: SSL",
            "",
            "【POP3/SMTP】",
            f"  接收服务器: {pop_host} | 端口: 995 | 加密: SSL",
            f"  发送服务器: {smtp_host} | 端口: 465 | 加密: SSL",
        ]
        if not xc:
            lines += [
                "",
                "【Exchange】",
                "  服务器: ex.exmail.qq.com | 端口: 443 | 加密: SSL",
                "  注意: 信创邮箱不支持 Exchange 协议",
            ]
        lines += [
            "",
            "【认证】",
            "  用户名: 完整企业邮箱地址（如 name@" + domain + "）",
            "  密码: 企业邮箱密码；若开启安全登录，需使用「客户端授权码」",
            "  授权码生成: 网页版企业邮箱 → 设置 → 邮箱绑定 → 生成客户端专用密码",
        ]
        return ToolResult.ok("\n".join(lines))

    @staticmethod
    def _logout(imap):
        try:
            imap.logout()
        except Exception:
            pass

    # ─── 主入口 ───

    def execute(
        self,
        action: str,
        to: str = "",
        subject: str = "",
        body: str = "",
        html: str = "",
        cc: str = "",
        bcc: str = "",
        attachments: list | None = None,
        folder: str = "INBOX",
        limit: int = 20,
        offset: int = 0,
        mail_id: str = "",
        query: str = "",
        target_folder: str = "",
        domain: str = "",
        env_type: str = "general",
        attachment_name: str = "",
        **kwargs,
    ) -> ToolResult:
        if action not in VALID_ACTIONS:
            return ToolResult.fail(f"不支持的操作: {action}，支持: {', '.join(VALID_ACTIONS)}")

        handlers = {
            "send": lambda: self._send(to, subject, body, html, cc, bcc, attachments),
            "list": lambda: self._handle_list(folder, limit, offset),
            "read": lambda: self._handle_read(folder, mail_id),
            "search": lambda: self._handle_search(folder, query, limit),
            "download": lambda: self._handle_download(folder, mail_id, attachment_name),
            "delete": lambda: self._handle_delete(folder, mail_id),
            "mark_read": lambda: self._handle_mark(folder, mail_id, True),
            "mark_unread": lambda: self._handle_mark(folder, mail_id, False),
            "move": lambda: self._handle_move(folder, mail_id, target_folder),
            "folders": lambda: self._handle_folders(),
            "config_advice": lambda: self._handle_config_advice(domain, env_type),
        }
        return handlers[action]()


skill = WecomEmailTool()


# ═══ 命令行入口（便于独立测试凭据） ═══

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="企业微信邮箱收发工具（CLI 测试）")
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS, help="操作类型")
    parser.add_argument("--to", help="收件人")
    parser.add_argument("--subject", help="主题")
    parser.add_argument("--body", help="纯文本正文")
    parser.add_argument("--html", help="HTML 正文")
    parser.add_argument("--cc", help="抄送")
    parser.add_argument("--bcc", help="密送")
    parser.add_argument("--attachments", help="附件路径，多个用逗号分隔")
    parser.add_argument("--folder", default="INBOX", help="文件夹，默认 INBOX")
    parser.add_argument("--limit", type=int, default=20, help="数量上限")
    parser.add_argument("--offset", type=int, default=0, help="分页偏移")
    parser.add_argument("--mail-id", dest="mail_id", help="邮件 UID")
    parser.add_argument("--query", help="IMAP 搜索条件")
    parser.add_argument("--target-folder", dest="target_folder", help="移动目标文件夹")
    parser.add_argument("--attachment-name", dest="attachment_name", help="要下载的附件名（download 时使用）")
    parser.add_argument("--domain", help="企业邮箱域名")
    parser.add_argument("--env-type", dest="env_type", default="general", choices=["general", "xc"], help="环境类型")
    args = parser.parse_args()

    tool = WecomEmailTool()
    if not args.action:
        print("用法: python -m skills.wecom_email <action> [选项]")
        print("可用操作:", ", ".join(VALID_ACTIONS))
        sys.exit(0)

    result = tool.execute(
        action=args.action,
        to=args.to or "",
        subject=args.subject or "",
        body=args.body or "",
        html=args.html or "",
        cc=args.cc or "",
        bcc=args.bcc or "",
        attachments=[p.strip() for p in args.attachments.split(",") if p.strip()] if args.attachments else None,
        folder=args.folder,
        limit=args.limit,
        offset=args.offset,
        mail_id=args.mail_id or "",
        query=args.query or "",
        target_folder=args.target_folder or "",
        attachment_name=args.attachment_name or "",
        domain=args.domain or "",
        env_type=args.env_type,
    )
    print(result.content)
    sys.exit(0 if result.success else 1)
