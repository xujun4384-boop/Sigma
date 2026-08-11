"""
微信公众平台草稿管理 Skill。

支持：Access Token 管理、草稿增删改查、图片素材上传、一键存草稿。
凭据通过 Sigma 前端 Settings → Skill Keys 中配置，或从 .env 文件读取。

⚠️ 2025年7月起，发布接口（freepublish/submit）仅企业已认证(蓝V)账号可用。
   个人号/未认证企业号只能存草稿，发布需在后台手动操作。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import argparse
from pathlib import Path
from typing import Any

import re
import requests
from dotenv import load_dotenv
from sigma_logger import log

from skills.base import BaseTool, ToolParameter, ToolResult

WECHAT_API_BASE = "https://api.weixin.qq.com"

# ── wenyan-cli Markdown 转 HTML ────────────────────────────────────────

WENYAN_THEMES = [
    "default", "orangeheart", "rainbow", "lapis",
    "pie", "maize", "purple", "phycat",
]

WENYAN_HIGHLIGHT_THEMES = [
    "atom-one-dark", "atom-one-light", "dracula", "github-dark",
    "github", "monokai", "solarized-dark", "solarized-light", "xcode",
]


def _find_wenyan_cli() -> str | None:
    """查找 wenyan-cli 可执行文件路径。"""
    # 1. 检查常见 npm 全局路径（跨平台）
    npm_global_dirs = []
    try:
        prefix = subprocess.check_output(
            ["npm", "prefix", "-g"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if prefix:
            npm_global_dirs.append(prefix)
    except Exception:
        pass
    # 补充常见默认路径
    npm_global_dirs.extend([
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm"),  # Windows
        "/usr/local/lib/node_modules",  # macOS / Linux
        "/usr/lib/node_modules",
    ])
    for dir_path in npm_global_dirs:
        for name in ("wenyan.cmd", "wenyan"):
            candidate = os.path.join(dir_path, name)
            if os.path.exists(candidate):
                return candidate
    # 2. 回退：在 PATH 中查找
    for name in ("wenyan.cmd", "wenyan"):
        found = shutil.which(name)
        if found:
            return found
    return None


# Token 缓存文件
TOKEN_CACHE_FILE = Path(__file__).parent / ".token_cache.json"

# 有效操作列表
VALID_ACTIONS = [
    "get_token",
    "add_draft",
    "update_draft",
    "get_draft",
    "delete_draft",
    "list_drafts",
    "count_drafts",
    "upload_image",
    "upload_material",
    "push_draft",    # 一键存草稿（封面图 + 创建草稿，不发布）
    "publish",       # 发布草稿（⚠️ 仅企业认证号可用）
]


class WeChatPublisherTool(BaseTool):
    name = "wechat_publish"
    description = (
        "微信公众平台草稿管理工具。支持 Access Token 管理、草稿增删改查、"
        "图片素材上传、一键存草稿。凭据已由 Sigma 前端 Settings → Skill Keys 自动注入，"
        "不得读取 .env、不得要求用户配置 .env、不得导航浏览器到微信公众平台获取凭据。\n"
        "调用失败时应基于工具返回的错误说明原因；如使用中转地址，优先检查中转服务响应。\n"
        "⚠️ 发布接口仅企业已认证(蓝V)账号可用，个人号只能存草稿后人工发布。"
    )

    parameters = [
        ToolParameter(
            "action",
            "string",
            "操作类型: get_token / add_draft / update_draft / get_draft / delete_draft / "
            "list_drafts / count_drafts / upload_image / upload_material / push_draft / publish",
            required=True,
            enum=VALID_ACTIONS,
        ),
        ToolParameter(
            "articles",
            "array",
            "草稿文章数组（add_draft/update_draft 时使用），每项包含 title/content/thumb_media_id 等字段",
            required=False,
        ),
        ToolParameter(
            "media_id",
            "string",
            "草稿 media_id（get_draft/delete_draft/publish/update_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "index",
            "integer",
            "要修改的文章在草稿中的索引（update_draft 时使用，从0开始）",
            required=False,
        ),
        ToolParameter(
            "file_path",
            "string",
            "本地文件路径（upload_image/upload_material 时使用）",
            required=False,
        ),
        ToolParameter(
            "type",
            "string",
            "素材类型（upload_material 时使用，默认 image）",
            required=False,
            default="image",
        ),
        ToolParameter(
            "offset",
            "integer",
            "分页偏移（list_drafts 时使用）",
            required=False,
            default=0,
        ),
        ToolParameter(
            "count",
            "integer",
            "每页数量（list_drafts 时使用）",
            required=False,
            default=20,
        ),
        ToolParameter(
            "title",
            "string",
            "文章标题（push_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "content",
            "string",
            "文章正文（push_draft 时使用，HTML 格式）",
            required=False,
        ),
        ToolParameter(
            "cover_image",
            "string",
            "封面图本地路径（push_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "author",
            "string",
            "作者（push_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "digest",
            "string",
            "摘要（push_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "content_source_url",
            "string",
            "原文链接（push_draft 时使用）",
            required=False,
        ),
        ToolParameter(
            "style",
            "string",
            "排版样式: wechat 为应用微信专业排版, 留空不处理",
            required=False,
            default="",
        ),
        ToolParameter(
            "markdown",
            "string",
            "文章正文的 Markdown 格式内容（推荐）。提供此参数时，"
            "工具会自动调用 wenyan-cli 将 Markdown 转换为微信公众号兼容的 HTML，"
            "支持多主题和代码高亮。与 content 二选一。",
            required=False,
        ),
        ToolParameter(
            "theme",
            "string",
            f"wenyan 渲染主题（仅 markdown 模式有效）: {', '.join(WENYAN_THEMES)}",
            required=False,
            default="lapis",
        ),
        ToolParameter(
            "highlight",
            "string",
            "wenyan 代码高亮主题（仅 markdown 模式有效），默认 solarized-light",
            required=False,
            default="solarized-light",
        ),
        ToolParameter(
            "mac_style",
            "boolean",
            "是否使用 Mac 风格代码块（仅 markdown 模式有效）",
            required=False,
            default=True,
        ),
        ToolParameter(
            "footnote",
            "boolean",
            "是否将链接转为脚注（仅 markdown 模式有效）",
            required=False,
            default=True,
        ),
    ]

    def __init__(self, cwd: str = ".", appid: str | None = None, appsecret: str | None = None,
                 relay_url: str = "", relay_key: str = ""):
        super().__init__(cwd)
        # None 表示未从 SkillManager 传入（独立 CLI 运行），空字符串表示 SkillManager 传了但为空
        self._from_skill_manager = appid is not None and appsecret is not None
        self._appid: str = appid or ""
        self._appsecret: str = appsecret or ""
        self._relay_url: str = relay_url.rstrip("/") if relay_url else ""
        self._relay_key: str = relay_key
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        # 只有独立 CLI 运行时（未从 SkillManager 传入）才回退到 .env
        if not self._from_skill_manager:
            self._load_from_env()
        self._load_token_cache()

    def _load_from_env(self):
        """从 .env 文件加载配置（作为 CLI 独立运行时的回退方式）。"""
        env_path = self._resolve_path(".env")
        if env_path.exists():
            load_dotenv(env_path)
        self._appid = os.getenv("WECHAT_APPID", "")
        self._appsecret = os.getenv("WECHAT_APPSECRET", "")

    def _load_token_cache(self):
        """从缓存文件恢复 access_token。"""
        if TOKEN_CACHE_FILE.exists():
            try:
                data = json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
                expires = data.get("expires_at", 0)
                if time.time() < expires - 300:
                    self._access_token = data.get("access_token", "")
                    self._token_expires_at = expires
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_token_cache(self):
        """保存 access_token 到缓存文件。"""
        TOKEN_CACHE_FILE.write_text(
            json.dumps({
                "access_token": self._access_token,
                "expires_at": self._token_expires_at,
            }, ensure_ascii=False),
            encoding="utf-8",
        )

    def _ensure_config(self) -> str | None:
        if not self._appid or not self._appsecret:
            source = ".env 文件 (WECHAT_APPID / WECHAT_APPSECRET)" if not self._from_skill_manager else "Settings → Skill Keys"
            log.warning(
                f"[WeChatPublisher] 密钥未配置 (来源: {source}) | "
                f"appid={'***' if self._appid else '(空)'} "
                f"appsecret={'***' if self._appsecret else '(空)'} "
                f"relay_url={self._relay_url or '(空)'} relay_key={'***' if self._relay_key else '(空)'}"
            )
            return (
                "未配置微信公众号凭据。请在 Sigma 设置 → Skill Keys 中填写 AppID 和 AppSecret，"
                "或在项目 .env 文件中设置 WECHAT_APPID 和 WECHAT_APPSECRET"
            )
        return None

    def _get_access_token(self) -> tuple[str | None, str | None]:
        if self._access_token and time.time() < self._token_expires_at - 300:
            return self._access_token, None

        config_err = self._ensure_config()
        if config_err:
            return None, config_err

        url = f"{WECHAT_API_BASE}/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self._appid,
            "secret": self._appsecret,
        }
        try:
            if self._relay_url:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                data = self._relay_request("GET", full_url)
            else:
                resp = requests.get(url, params=params, timeout=30)
                data = resp.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 7200)
                self._save_token_cache()
                return self._access_token, None
            if data.get("success") is False and data.get("error"):
                return None, f"获取 Access Token 失败: {data['error']}"
            else:
                errcode = data.get("errcode", -1)
                errmsg = data.get("errmsg", "未知错误")
                return None, f"获取 Access Token 失败: [{errcode}] {errmsg}"
        except requests.RequestException as e:
            return None, f"网络请求失败: {e}"

    def _relay_request(self, method: str, target_url: str,
                       body: bytes = b"", content_type: str = "application/json") -> dict:
        """通过中转服务器发起请求（解决 IP 白名单问题）。"""
        headers = {
            "X-Relay-Key": self._relay_key,
            "X-Target-URL": target_url,
            "X-Target-Method": method,
            "Content-Type": content_type,
        }
        try:
            resp = requests.post(
                f"{self._relay_url}/relay",
                data=body,
                headers=headers,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return {"success": False, "error": f"中转服务返回了非 JSON 数据: {type(data).__name__}"}
            if "errcode" in data:
                log.info(
                    f"[WeChatPublisher] 中转响应 | status={resp.status_code} "
                    f"errcode={data.get('errcode')} errmsg={data.get('errmsg', '未知错误')}"
                )
            return data
        except requests.RequestException as e:
            return {"success": False, "error": f"中转请求失败: {e}"}
        except ValueError:
            return {"success": False, "error": f"中转服务返回非 JSON 响应 (HTTP {resp.status_code})"}

    def _build_file_body(self, params: dict, filename: str, file_bytes: bytes,
                          content_type: str = "image/jpeg") -> tuple[bytes, str]:
        """构建 multipart/form-data 请求体，用于通过 relay 上传文件。"""
        import uuid
        boundary = f"----WeChatPub{uuid.uuid4().hex[:12]}"
        parts = []

        for key, value in params.items():
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            parts.append(f"{value}\r\n".encode())

        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(file_bytes)
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())

        body = b"".join(parts)
        ct = f"multipart/form-data; boundary={boundary}"
        return body, ct

    def _api_get(self, path: str, params: dict | None = None) -> dict:
        token, err = self._get_access_token()
        if err:
            return {"success": False, "error": err}
        params = params or {}
        params["access_token"] = token
        target_url = f"{WECHAT_API_BASE}{path}"

        if self._relay_url:
            # 通过中转服务器
            from urllib.parse import urlencode
            full_url = f"{target_url}?{urlencode(params)}"
            return self._relay_request("GET", full_url)
        else:
            try:
                resp = requests.get(target_url, params=params, timeout=30)
                return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    def _api_post(self, path: str, data: dict | None = None, files: dict | None = None) -> dict:
        token, err = self._get_access_token()
        if err:
            return {"success": False, "error": err}
        params = {"access_token": token}
        target_url = f"{WECHAT_API_BASE}{path}"

        if self._relay_url:
            # 通过中转服务器：access_token 需要拼在 URL 上（中继转发原始 body）
            from urllib.parse import urlencode
            target_url = f"{target_url}?{urlencode(params)}"
            if files:
                file_key = list(files.keys())[0]
                file_tuple = files[file_key]  # (filename, file_obj, content_type)
                filename = file_tuple[0]
                file_obj = file_tuple[1]
                file_bytes = file_obj.read()
                file_obj.seek(0)  # 重置以便后续可能复用
                mime = file_tuple[2] if len(file_tuple) > 2 else "image/jpeg"
                body, ct = self._build_file_body(params, filename, file_bytes, mime)
                return self._relay_request("POST", target_url, body, ct)
            else:
                body = json.dumps(data, ensure_ascii=False).encode() if data else b""
                return self._relay_request("POST", target_url, body, "application/json")
        else:
            # 直连微信 API
            try:
                if files:
                    resp = requests.post(target_url, params=params, files=files, timeout=60)
                else:
                    resp = requests.post(target_url, params=params, json=data, timeout=30)
                return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    # ─── 各项操作实现 ───

    def _handle_get_token(self) -> ToolResult:
        token, err = self._get_access_token()
        if err:
            return ToolResult.fail(err)
        remaining = max(0, int(self._token_expires_at - time.time()))
        return ToolResult.ok(
            f"Access Token: {token[:20]}...\n"
            f"有效期剩余: {remaining} 秒 ({remaining // 60} 分钟)\n"
            f"过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self._token_expires_at))}"
        )

    def _handle_add_draft(self, articles: list) -> ToolResult:
        if not articles:
            return ToolResult.fail("缺少 articles 参数")
        result = self._api_post("/cgi-bin/draft/add", {"articles": articles})
        if "media_id" in result:
            return ToolResult.ok(f"草稿创建成功\nmedia_id: {result['media_id']}")
        return ToolResult.fail(f"创建草稿失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_update_draft(self, media_id: str, index: int, article: dict) -> ToolResult:
        if not media_id:
            return ToolResult.fail("缺少 media_id 参数")
        if index is None:
            return ToolResult.fail("缺少 index 参数")
        if not article:
            return ToolResult.fail("缺少 articles 参数")
        result = self._api_post("/cgi-bin/draft/update", {
            "media_id": media_id,
            "index": index,
            "articles": article,
        })
        if result.get("errcode", 0) == 0:
            return ToolResult.ok("草稿修改成功")
        return ToolResult.fail(f"修改草稿失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_get_draft(self, media_id: str) -> ToolResult:
        if not media_id:
            return ToolResult.fail("缺少 media_id 参数")
        result = self._api_post("/cgi-bin/draft/get", {"media_id": media_id})
        if "news_item" in result:
            return ToolResult.ok(json.dumps(result, ensure_ascii=False, indent=2))
        return ToolResult.fail(f"获取草稿失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_delete_draft(self, media_id: str) -> ToolResult:
        if not media_id:
            return ToolResult.fail("缺少 media_id 参数")
        result = self._api_post("/cgi-bin/draft/delete", {"media_id": media_id})
        if result.get("errcode", 0) == 0:
            return ToolResult.ok(f"草稿 {media_id} 已删除")
        return ToolResult.fail(f"删除草稿失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_list_drafts(self, offset: int = 0, count: int = 20) -> ToolResult:
        result = self._api_post("/cgi-bin/draft/batchget", {
            "offset": offset,
            "count": count,
            "no_content": 1,
        })
        if "item" in result:
            total = result.get("total_count", 0)
            items = result["item"]
            output = [f"草稿总数: {total}, 当前页: {len(items)} 条\n"]
            for item in items:
                mid = item.get("media_id", "")
                update_time = item.get("update_time", 0)
                ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(update_time))
                content = item.get("content", {})
                news = content.get("news_item", [])
                title = news[0].get("title", "无标题") if news else "无标题"
                output.append(f"  [{mid}] {title} (更新: {ts})")
            return ToolResult.ok("\n".join(output))
        return ToolResult.fail(f"获取草稿列表失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_count_drafts(self) -> ToolResult:
        result = self._api_get("/cgi-bin/draft/count")
        if "total_count" in result:
            return ToolResult.ok(f"草稿总数: {result['total_count']}")
        return ToolResult.fail(f"获取草稿总数失败: {json.dumps(result, ensure_ascii=False)}")

    def _handle_upload_image(self, file_path: str) -> ToolResult:
        """上传图片到微信图床（用于文章内容插图），返回 URL。"""
        if not file_path:
            return ToolResult.fail("缺少 file_path 参数")
        fp = self._resolve_path(file_path)
        if not fp.exists():
            return ToolResult.fail(f"文件不存在: {file_path}")
        try:
            with open(fp, "rb") as f:
                result = self._api_post(
                    "/cgi-bin/media/uploadimg",
                    files={"media": (fp.name, f, "image/*")},
                )
            if "url" in result:
                return ToolResult.ok(f"图片上传成功\nURL: {result['url']}")
            return ToolResult.fail(f"上传失败: {json.dumps(result, ensure_ascii=False)}")
        except Exception as e:
            return ToolResult.fail(f"上传异常: {e}")

    def _handle_upload_material(self, file_path: str, material_type: str = "image") -> ToolResult:
        """上传永久素材（用于封面图），返回 media_id。"""
        if not file_path:
            return ToolResult.fail("缺少 file_path 参数")
        fp = self._resolve_path(file_path)
        if not fp.exists():
            return ToolResult.fail(f"文件不存在: {file_path}")
        # 将 type 参数通过 _api_post 的额外 query params 传递
        try:
            with open(fp, "rb") as f:
                # 先获取 token，手动构建带 type 的 URL
                token, err = self._get_access_token()
                if err:
                    return ToolResult.fail(err)
                from urllib.parse import urlencode
                target_url = f"{WECHAT_API_BASE}/cgi-bin/material/add_material?{urlencode({'access_token': token, 'type': material_type})}"
                if self._relay_url:
                    body, ct = self._build_file_body(
                        {"access_token": token, "type": material_type},
                        fp.name, f.read(), "image/jpeg"
                    )
                    result = self._relay_request("POST", target_url, body, ct)
                else:
                    f.seek(0)
                    resp = requests.post(target_url, files={"media": (fp.name, f)}, timeout=60)
                    result = resp.json()
            if "media_id" in result:
                url = result.get("url", "")
                return ToolResult.ok(
                    f"素材上传成功\nmedia_id: {result['media_id']}\nURL: {url}"
                )
            return ToolResult.fail(f"上传失败: {json.dumps(result, ensure_ascii=False)}")
        except Exception as e:
            return ToolResult.fail(f"上传异常: {e}")

    def _apply_wechat_style(self, content: str) -> str:
        """对 HTML 内容应用微信公众平台兼容的专业排版样式。
        使用内联 style 属性（公众号编辑器仅支持内联样式）。"""
        # 如果内容没有 HTML 标签，用 <p> 包裹
        stripped = content.strip()
        if not re.search(r'<\w+[^>]*>', stripped):
            content = f"<p>{stripped}</p>"

        # 定义微信兼容的内联样式映射
        styles = {
            "h1": "font-size:22px;font-weight:700;color:#000;text-align:center;"
                  "margin:24px 0 16px 0;line-height:1.4;letter-spacing:1px;",
            "h2": "font-size:18px;font-weight:700;color:#1a1a1a;"
                  "margin:20px 0 12px 0;line-height:1.5;padding-left:12px;"
                  "border-left:3px solid #607B8B;",
            "h3": "font-size:16px;font-weight:600;color:#333;"
                  "margin:16px 0 8px 0;line-height:1.5;",
            "h4": "font-size:15px;font-weight:600;color:#555;"
                  "margin:12px 0 6px 0;line-height:1.5;",
            "p": "font-size:15px;color:#3f3f3f;line-height:1.75;"
                 "margin:0 0 12px 0;text-align:justify;letter-spacing:0.5px;",
            "blockquote": "font-size:14px;color:#666;line-height:1.7;"
                          "margin:12px 0;padding:10px 16px;"
                          "background-color:#f5f7fa;border-left:3px solid #607B8B;",
            "ul": "font-size:15px;color:#3f3f3f;line-height:1.75;"
                  "margin:8px 0 12px 0;padding-left:24px;",
            "ol": "font-size:15px;color:#3f3f3f;line-height:1.75;"
                  "margin:8px 0 12px 0;padding-left:24px;",
            "li": "margin-bottom:6px;",
            "img": "max-width:100%;height:auto;display:block;"
                   "margin:16px auto;border-radius:4px;",
            "a": "color:#607B8B;text-decoration:none;",
            "strong": "color:#1a1a1a;",
            "code": "font-family:Consolas,Monaco,monospace;font-size:13px;"
                    "background-color:#f0f0f0;padding:2px 6px;border-radius:3px;",
            "pre": "font-size:13px;line-height:1.5;background-color:#2d2d2d;"
                   "color:#f8f8f2;padding:16px;border-radius:6px;overflow-x:auto;"
                   "margin:12px 0;",
            "hr": "border:none;border-top:1px solid #e0e0e0;margin:24px 0;",
        }

        for tag, style in styles.items():
            # 匹配不含 style 属性的标签，添加样式
            pattern = re.compile(
                rf'(<{tag})(\s(?:(?!style=)[^>])*)?(>)',
                re.IGNORECASE,
            )
            def make_repl(s):
                return lambda m: f'{m.group(1)} style="{s}"{m.group(2) or ""}{m.group(3)}'
            content = pattern.sub(make_repl(style), content)

        # 添加文章整体容器样式
        if not content.strip().startswith('<div style="'):
            content = (
                '<div style="max-width:677px;margin:0 auto;padding:16px 8px;'
                'font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\','
                '\'Hiragino Sans GB\',\'Microsoft YaHei\',sans-serif;">'
                + content + '</div>'
            )

        return content

    def _render_markdown_via_wenyan(
        self, markdown: str, theme: str = "lapis",
        highlight: str = "solarized-light", mac_style: bool = True,
        footnote: bool = True,
    ) -> tuple[str | None, str | None]:
        """通过 wenyan-cli 将 Markdown 转换为微信公众号兼容 HTML。

        返回 (html, error)。成功时 html 为转换结果，error 为 None。
        """
        cli = _find_wenyan_cli()
        if not cli:
            return None, (
                "未找到 wenyan-cli。请先安装: npm install -g @wenyan-md/cli\n"
                "如果已安装但仍报错，请确保 Node.js >= 14 且 npm 全局 bin 目录在 PATH 中"
            )

        # 将 markdown 写入临时文件（wenyan render 支持 stdin，但 Windows 上管道不稳定）
        tmp_dir = tempfile.mkdtemp(prefix="sigma_wenyan_")
        md_file = os.path.join(tmp_dir, "article.md")
        try:
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown)

            cmd = [cli, "render", "-f", md_file]
            if theme and theme in WENYAN_THEMES:
                cmd.extend(["-t", theme])
            if highlight and highlight in WENYAN_HIGHLIGHT_THEMES:
                cmd.extend(["-h", highlight])
            if not mac_style:
                cmd.append("--no-mac-style")
            if not footnote:
                cmd.append("--no-footnote")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                shell=False,
            )

            if result.returncode != 0:
                return None, f"wenyan render 失败: {result.stderr[:500] or result.stdout[:500]}"

            html = result.stdout.strip()
            if not html:
                return None, "wenyan render 返回了空内容"

            return html, None

        except subprocess.TimeoutExpired:
            return None, "wenyan render 超时（120秒）"
        except FileNotFoundError:
            return None, "未找到 wenyan-cli 可执行文件"
        except Exception as e:
            return None, f"wenyan render 异常: {e}"
        finally:
            import shutil as _shutil
            try:
                _shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

    def _replace_inline_images(self, content: str) -> tuple[str, list[str]]:
        """检测正文中的本地图片路径，上传到微信图床并替换为微信 URL。
        返回 (替换后的 content, 上传日志列表)。"""
        import re
        logs = []
        # 匹配 <img> 标签中指向本地文件的 src (不以 http/https/data 开头)
        img_pattern = re.compile(r'<img\s+[^>]*src="(?!https?://|data:)([^"]+)"[^>]*>', re.IGNORECASE)

        def upload_and_replace(match):
            local_path = match.group(1)
            fp = self._resolve_path(local_path)
            if fp.exists():
                result = self._handle_upload_image(str(fp))
                if result.success:
                    # 从返回内容中提取 URL
                    for line in result.content.split("\n"):
                        if line.startswith("URL:"):
                            wx_url = line.split(":", 1)[1].strip()
                            logs.append(f"[OK] {fp.name} → {wx_url[:50]}...")
                            return match.group(0).replace(local_path, wx_url)
                logs.append(f"[FAIL] {fp.name}")
            return match.group(0)  # 文件不存在则保留原样

        new_content = img_pattern.sub(upload_and_replace, content)
        return new_content, logs

    def _handle_push_draft(
        self,
        title: str,
        content: str = "",
        cover_image: str = "",
        author: str = "",
        digest: str = "",
        content_source_url: str = "",
        style: str = "",
        markdown: str = "",
        theme: str = "lapis",
        highlight: str = "solarized-light",
        mac_style: bool = True,
        footnote: bool = True,
    ) -> ToolResult:
        """一键存草稿: Markdown 渲染（可选）→ 排版 → 上传封面图 → 上传正文插图 → 创建草稿。"""
        if not title:
            return ToolResult.fail("缺少 title 参数")

        steps = []

        # 步骤0: 如果提供了 markdown，用 wenyan-cli 渲染为 HTML
        if markdown:
            if content:
                steps.append("[INFO] 同时收到了 markdown 和 content，优先使用 markdown")
            print(f"[push_draft] 步骤0: 用 wenyan-cli 将 Markdown 转换为 HTML（主题: {theme}，代码高亮: {highlight}）...")
            html, err = self._render_markdown_via_wenyan(
                markdown, theme=theme, highlight=highlight,
                mac_style=mac_style, footnote=footnote,
            )
            if err:
                steps.append(f"[FAIL] Markdown 转 HTML 失败: {err}")
                # 降级：尝试用内置 wechat 排版处理原始 markdown
                steps.append("[INFO] 降级为内置排版模式（效果可能不如 wenyan）")
                content = markdown
            else:
                content = html
                steps.append(f"[OK] Markdown 转换完成（主题: {theme}，代码高亮: {highlight}）")

        if not content:
            return ToolResult.fail("缺少 content 参数（或 markdown 参数）")
        if not cover_image:
            return ToolResult.fail("缺少 cover_image 参数（封面图路径）")

        # 步骤1: 上传封面图
        print("[push_draft] 步骤1/3: 上传封面图...")
        result = self._handle_upload_material(cover_image)
        if not result.success:
            return ToolResult.fail(f"上传封面图失败: {result.content}")
        cover_lines = result.content
        thumb_media_id = ""
        for line in cover_lines.split("\n"):
            if line.startswith("media_id:"):
                thumb_media_id = line.split(":", 1)[1].strip()
                break
        if not thumb_media_id:
            return ToolResult.fail("未能从上传结果中提取封面图 media_id")
        steps.append(f"[OK] 封面图上传成功: {thumb_media_id}")

        # 步骤2: 检测并上传正文中的本地图片
        print("[push_draft] 步骤2/4: 上传正文插图...")
        content, img_logs = self._replace_inline_images(content)
        if img_logs:
            steps.append(f"[OK] 正文插图: {len(img_logs)} 张")
            steps.extend(img_logs)
        else:
            steps.append("[INFO] 正文中未检测到本地图片")

        # 步骤3: 应用微信排版（可选）
        if style == "wechat":
            print("[push_draft] 步骤3/4: 应用微信排版...")
            content = self._apply_wechat_style(content)
            steps.append("[OK] 已应用微信专业排版")
        else:
            print("[push_draft] 步骤3/4: 跳过排版")

        # 步骤4: 创建草稿
        print("[push_draft] 步骤4/4: 创建草稿...")
        article = {
            "title": title,
            "content": content,
            "thumb_media_id": thumb_media_id,
        }
        if author:
            article["author"] = author
        if digest:
            article["digest"] = digest
        if content_source_url:
            article["content_source_url"] = content_source_url

        result = self._handle_add_draft([article])
        if not result.success:
            return ToolResult.fail(f"创建草稿失败: {result.content}")
        steps.append(f"[OK] {result.content}")

        steps.append("\n⚠️ 草稿已存入草稿箱，请登录公众号后台手动点击「发布」。")
        return ToolResult.ok("\n".join(steps))

    def _handle_publish(self, media_id: str) -> ToolResult:
        """发布草稿（⚠️ 仅企业已认证(蓝V)账号可用，个人号会返回 api unauthorized）。"""
        if not media_id:
            return ToolResult.fail("缺少 media_id 参数")
        result = self._api_post("/cgi-bin/freepublish/submit", {"media_id": media_id})
        if "publish_id" in result:
            return ToolResult.ok(
                f"发布成功\npublish_id: {result['publish_id']}\n"
                f"msg_data_id: {result.get('msg_data_id', 'N/A')}"
            )
        errcode = result.get("errcode", -1)
        errmsg = result.get("errmsg", "未知错误")
        hint = ""
        if errcode == 48001:
            hint = "\n⚠️ 当前账号无发布权限。个人号/未认证企业号无法调用发布接口，请登录后台手动发布。"
        return ToolResult.fail(f"发布失败: [{errcode}] {errmsg}{hint}")

    # ─── 主入口 ───

    def execute(
        self,
        action: str,
        articles: list | None = None,
        media_id: str = "",
        index: int = 0,
        file_path: str = "",
        type: str = "image",
        offset: int = 0,
        count: int = 20,
        title: str = "",
        content: str = "",
        cover_image: str = "",
        author: str = "",
        digest: str = "",
        content_source_url: str = "",
        style: str = "",
        markdown: str = "",
        theme: str = "lapis",
        highlight: str = "solarized-light",
        mac_style: bool = True,
        footnote: bool = True,
        **kwargs,
    ) -> ToolResult:
        if action not in VALID_ACTIONS:
            return ToolResult.fail(f"不支持的操作: {action}，支持: {', '.join(VALID_ACTIONS)}")

        article = articles[0] if articles else {}

        action_handlers = {
            "get_token": lambda: self._handle_get_token(),
            "add_draft": lambda: self._handle_add_draft(articles or []),
            "update_draft": lambda: self._handle_update_draft(media_id, index, article),
            "get_draft": lambda: self._handle_get_draft(media_id),
            "delete_draft": lambda: self._handle_delete_draft(media_id),
            "list_drafts": lambda: self._handle_list_drafts(offset, count),
            "count_drafts": lambda: self._handle_count_drafts(),
            "upload_image": lambda: self._handle_upload_image(file_path),
            "upload_material": lambda: self._handle_upload_material(file_path, type),
            "push_draft": lambda: self._handle_push_draft(
                title, content, cover_image, author, digest, content_source_url, style,
                markdown=markdown, theme=theme, highlight=highlight,
                mac_style=mac_style, footnote=footnote,
            ),
            "publish": lambda: self._handle_publish(media_id),
        }

        handler = action_handlers.get(action)
        if handler is None:
            return ToolResult.fail(f"未知操作: {action}")
        return handler()


skill = WeChatPublisherTool()


# ═══ 命令行入口 ═══

def _parse_args():
    parser = argparse.ArgumentParser(
        description="微信公众平台草稿管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python -m skills.wechat_publisher get_token
  python -m skills.wechat_publisher list_drafts
  python -m skills.wechat_publisher push_draft --title "标题" --content "<p>正文</p>" --cover ./cover.jpg
        """,
    )
    parser.add_argument("action", nargs="?", choices=VALID_ACTIONS,
                        help="操作类型")
    parser.add_argument("--media_id", help="草稿 media_id")
    parser.add_argument("--file_path", help="文件路径")
    parser.add_argument("--title", help="文章标题")
    parser.add_argument("--content", help="文章正文（HTML 格式）")
    parser.add_argument("--cover_image", help="封面图路径")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--digest", default="", help="摘要")
    parser.add_argument("--content_source_url", default="", help="原文链接")
    parser.add_argument("--markdown", default="", help="文章正文 Markdown（与 content 二选一）")
    parser.add_argument("--theme", default="lapis", help=f"wenyan 主题: {', '.join(WENYAN_THEMES)}")
    parser.add_argument("--highlight", default="solarized-light", help="代码高亮主题")
    parser.add_argument("--no-mac-style", action="store_true", help="禁用 Mac 风格代码块")
    parser.add_argument("--no-footnote", action="store_true", help="禁用链接转脚注")
    parser.add_argument("--offset", type=int, default=0, help="分页偏移")
    parser.add_argument("--count", type=int, default=20, help="每页数量")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if not args.action:
        print("微信公众平台草稿管理工具")
        print("=" * 40)
        tool = WeChatPublisherTool()
        result = tool._handle_get_token()
        print(result.content)
    else:
        tool = WeChatPublisherTool()
        kwargs = {
            "action": args.action,
        }
        if args.media_id:
            kwargs["media_id"] = args.media_id
        if args.file_path:
            kwargs["file_path"] = args.file_path
        if args.title:
            kwargs["title"] = args.title
        if args.content:
            kwargs["content"] = args.content
        if args.cover_image:
            kwargs["cover_image"] = args.cover_image
        if args.author:
            kwargs["author"] = args.author
        if args.digest:
            kwargs["digest"] = args.digest
        if args.content_source_url:
            kwargs["content_source_url"] = args.content_source_url
        if args.markdown:
            kwargs["markdown"] = args.markdown
        if args.theme:
            kwargs["theme"] = args.theme
        if args.highlight:
            kwargs["highlight"] = args.highlight
        kwargs["mac_style"] = not args.no_mac_style
        kwargs["footnote"] = not args.no_footnote
        if args.offset:
            kwargs["offset"] = args.offset
        if args.count:
            kwargs["count"] = args.count

        result = tool.execute(**kwargs)
        if result.success:
            print(result.content)
        else:
            print(f"错误: {result.content}")
