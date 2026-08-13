"""京东云 Anthropic Messages API 兼容性诊断脚本。

示例：
    python diagnose_jdcloud_messages.py --api-key "pk-..." --model "Claude-Opus-5-hq"

脚本依次验证基础非流式请求、system 字段、tools 字段和 SSE 流式响应，
不修改 Sigma 的任何运行逻辑。
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://modelservice.jdcloud.com/anthropic"


def print_result(name: str, response: httpx.Response) -> None:
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    print(f"HTTP {response.status_code}")
    print(f"Content-Type: {response.headers.get('content-type', '(missing)')}")
    print(response.text[:2000])


def run_non_stream_case(
    client: httpx.Client,
    name: str,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> bool:
    try:
        response = client.post(url, headers=headers, json=payload)
        print_result(name, response)
        return response.status_code == 200
    except httpx.HTTPError as error:
        print(f"\n{'=' * 72}\n{name}\n{'=' * 72}\n请求异常: {type(error).__name__}: {error}")
        return False


def run_stream_case(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> bool:
    name = "4. 流式请求（stream=true）"
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    try:
        with client.stream("POST", url, headers=headers, json=payload) as response:
            print(f"HTTP {response.status_code}")
            print(f"Content-Type: {response.headers.get('content-type', '(missing)')}")
            if response.status_code != 200:
                print(response.read().decode("utf-8", errors="replace")[:2000])
                return False

            received = False
            for line in response.iter_lines():
                if line:
                    received = True
                    print(line[:2000])
                if line == "data: [DONE]":
                    break
            if not received:
                print("未收到任何流式事件")
            return received
    except httpx.HTTPError as error:
        print(f"请求异常: {type(error).__name__}: {error}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="京东云 Anthropic Messages API 兼容性诊断")
    parser.add_argument("--api-key", required=True, help="京东云 API Key")
    parser.add_argument("--model", required=True, help="京东云模型名称，例如 Claude-Opus-5-hq")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"默认：{DEFAULT_BASE_URL}")
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/v1/messages"
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }
    base_payload: dict[str, Any] = {
        "model": args.model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": "请只回复：基础调用成功"}],
    }

    print(f"目标 URL: {url}")
    print(f"模型: {args.model}")
    print("认证密钥已传入（不会输出）。")

    with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
        results = {
            "基础非流式": run_non_stream_case(
                client=client,
                name="1. 基础非流式请求（与京东云示例一致）",
                url=url,
                headers=headers,
                payload=base_payload,
            ),
        }

        system_payload = {
            **base_payload,
            "system": "你是一个简洁的助手。",
        }
        results["system"] = run_non_stream_case(
            client, "2. 非流式请求 + system", url, headers, system_payload
        )

        tools_payload = {
            **system_payload,
            "tools": [{
                "name": "get_status",
                "description": "返回当前状态。",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            }],
        }
        results["tools"] = run_non_stream_case(
            client, "3. 非流式请求 + system + tools", url, headers, tools_payload
        )

        stream_payload = {
            **base_payload,
            "stream": True,
        }
        results["stream"] = run_stream_case(client, url, headers, stream_payload)

    print(f"\n{'=' * 72}\n诊断汇总\n{'=' * 72}")
    for case, passed in results.items():
        print(f"{'通过' if passed else '失败'}  {case}")


if __name__ == "__main__":
    main()
