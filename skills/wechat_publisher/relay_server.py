"""
微信公众平台 API 中转服务 (Relay Server)

部署在阿里云服务器上，接收来自本地 Sigma 的微信 API 请求，
以固定 IP (8.159.156.138) 转发给 api.weixin.qq.com，解决 IP 白名单问题。

启动方式:
  python relay_server.py --port 8888 --key YOUR_SHARED_SECRET_KEY

安全: 使用预共享密钥 (X-Relay-Key header) 认证，防止未授权访问。
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Any

import requests


class RelayHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器：认证 → 转发 → 返回"""

    # 由外部设置的共享密钥
    shared_key: str = ""

    def _auth_fail(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "unauthorized"}).encode())

    def _bad_request(self, msg: str):
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

    def _proxy_error(self, msg: str, status: int = 502):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

    def log_message(self, format, *args):
        """简洁日志格式"""
        print(f"[Relay] {args[0]}", flush=True)

    # ─── 请求处理 ───

    def do_POST(self):
        if self.path != "/relay":
            self.send_response(404)
            self.end_headers()
            return

        # 认证
        client_key = self.headers.get("X-Relay-Key", "")
        if client_key != self.shared_key:
            self._auth_fail()
            return

        # 目标 URL
        target_url = self.headers.get("X-Target-URL", "")
        if not target_url:
            self._bad_request("missing X-Target-URL header")
            return

        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # 目标方法 (默认 POST)
        target_method = self.headers.get("X-Target-Method", "POST").upper()

        # 内容类型
        content_type = self.headers.get("X-Content-Type", self.headers.get("Content-Type", "application/json"))

        print(f"[Relay] → {target_method} {target_url[:80]}... (body={len(body)} bytes)", flush=True)

        try:
            headers = {"Content-Type": content_type}

            if target_method == "GET":
                resp = requests.get(target_url, timeout=60)
            elif b"multipart/form-data" in body[:100] or "multipart/form-data" in content_type:
                # 文件上传：直接透传原始 body
                resp = requests.post(target_url, data=body, headers=headers, timeout=120)
            elif body:
                resp = requests.post(target_url, data=body, headers=headers, timeout=60)
            else:
                resp = requests.post(target_url, headers=headers, timeout=60)

            # 返回响应
            self.send_response(resp.status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(resp.content)
            print(f"[Relay] ← {resp.status_code} ({len(resp.content)} bytes)", flush=True)

        except requests.Timeout:
            self._proxy_error("upstream timeout", 504)
        except requests.ConnectionError:
            self._proxy_error("upstream connection failed", 502)
        except Exception as e:
            self._proxy_error(f"proxy error: {e}", 502)

    def do_GET(self):
        """健康检查"""
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "service": "wechat-relay"}).encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="微信 API 中转服务")
    parser.add_argument("--port", type=int, default=8888, help="监听端口 (默认 8888)")
    parser.add_argument("--key", type=str, required=True, help="预共享密钥 (必填)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    args = parser.parse_args()

    if len(args.key) < 8:
        print("错误: 密钥至少 8 个字符")
        sys.exit(1)

    RelayHandler.shared_key = args.key

    server = HTTPServer((args.host, args.port), RelayHandler)
    print(f"[Relay] 微信 API 中转服务已启动")
    print(f"[Relay] 监听: {args.host}:{args.port}")
    print(f"[Relay] 出站 IP: 将作为微信 IP 白名单地址")
    print(f"[Relay] 健康检查: http://{args.host}:{args.port}/health")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Relay] 服务已停止")
        server.server_close()


if __name__ == "__main__":
    main()
