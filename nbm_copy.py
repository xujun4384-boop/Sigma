"""
Network Bridge Manager – WebSocket 桥接层。

负责维护与浏览器扩展的 WebSocket 连接，将来自 skill 的命令转发给扩展，
并将扩展的响应返回。同时缓存主程序用过的 LLM 配置，扩展连接时自动推送。

通信协议（与浏览器扩展对齐）：
  服务端 → 扩展: {"id": str, "action": str, "params": dict}
  扩展 → 服务端: {"id": str, "success": bool, "data": dict}
  扩展 → 服务端（心跳）: {"id": "hb-...", "action": "heartbeat", "params": {"ts": int}}
  服务端 → 扩展（LLM 配置推送）: {"type": "llm_configs", "configs": [...]}
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from sigma_logger import log


class NetworkBridgeManager:
    """单例管理器，持有与浏览器扩展的唯一 WebSocket 连接。"""

    def __init__(self):
        self._ws: WebSocket | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._counter = 0
        self._connected_at: float = 0.0
        # LLM 配置缓存: name -> {baseUrl, apiKey, model, protocol}
        self._llm_configs: dict[str, dict] = {}
        # 当前主程序/扩展面板选择的配置名
        self._active_config_name: str | None = None
        # Vision 配置缓存: {apiKey, model, baseUrl}
        self._vision_config: dict | None = None
        # 最大工具调用轮次（默认 10，由主程序 Settings 面板同步）
        self._max_iterations: int = 10

    # ── LLM 配置管理 ──

    def register_llm_config(self, name: str, base_url: str, api_key: str, model: str, protocol: str = "anthropic", active: bool = False):
        """注册一个 LLM 配置（通常来自主程序的 chat 请求）。"""
        if not name or not api_key:
            return
        self._llm_configs[name] = {
            "name": name,
            "baseUrl": base_url,
            "apiKey": api_key,
            "model": model,
            "protocol": protocol,
        }
        if active:
            self._active_config_name = name
        elif self._active_config_name is None:
            # 首次注册时默认设为 active
            self._active_config_name = name
        log.info(f"[Bridge] LLM 配置已缓存: {name} ({model}, protocol={protocol}, active={self._active_config_name == name})")

    def set_active_config_name(self, name: str):
        """设置当前使用的 LLM 配置名（来自扩展面板选择或主程序切换）。"""
        if name and name in self._llm_configs:
            self._active_config_name = name
            print(f"[Bridge] 激活 LLM 配置: {name}")

    def get_llm_config(self, name: str) -> dict | None:
        """获取指定名称的 LLM 配置（含完整 apiKey）。"""
        return self._llm_configs.get(name)

    def get_active_llm_config(self) -> dict | None:
        """获取当前激活的 LLM 配置，若无则取第一个可用配置。"""
        if self._active_config_name:
            cfg = self._llm_configs.get(self._active_config_name)
            if cfg:
                return cfg
        if self._llm_configs:
            return next(iter(self._llm_configs.values()))
        return None

    def get_llm_config_list(self) -> list[dict]:
        """获取 LLM 配置列表（含完整 apiKey 和 protocol，仅供本地扩展使用）。"""
        return [
            {
                "name": cfg["name"],
                "model": cfg["model"],
                "baseUrl": cfg["baseUrl"],
                "apiKey": cfg["apiKey"],
                "protocol": cfg.get("protocol", "anthropic"),
            }
            for cfg in self._llm_configs.values()
        ]

    # ── Vision 配置管理 ──

    def register_vision_config(self, api_key: str, model: str, base_url: str):
        """注册视觉模型配置（来自主程序 Settings）。"""
        if not api_key or not model or not base_url:
            self._vision_config = None
            return
        self._vision_config = {
            "apiKey": api_key,
            "model": model,
            "baseUrl": base_url,
        }
        print(f"[Bridge] Vision 配置已缓存: {model}")

    def get_vision_config(self) -> dict | None:
        """获取视觉模型配置（含完整 apiKey）。"""
        return self._vision_config

    # ── 最大工具调用轮次 ──

    def set_max_iterations(self, n: int):
        """设置最大工具调用轮次（来自主程序 Settings 面板）。"""
        if n > 0:
            self._max_iterations = n

    def get_max_iterations(self) -> int:
        """获取最大工具调用轮次。"""
        return self._max_iterations

    async def _push_llm_configs(self):
        """向扩展推送当前可用的 LLM 配置列表。"""
        if self._ws is None:
            return
        configs = self.get_llm_config_list()
        if not configs:
            return
        try:
            await self._ws.send_text(json.dumps({
                "type": "llm_configs",
                "configs": configs,
            }, ensure_ascii=False))
            log.info(f"[Bridge] 已推送 {len(configs)} 个 LLM 配置到扩展")
        except Exception as e:
            log.warning(f"[Bridge] 推送 LLM 配置失败: {e}")

    # ── WebSocket 生命周期 ──

    async def handle_connection(self, websocket: WebSocket):
        """FastAPI WebSocket 端点入口。"""
        await websocket.accept()
        # 断开旧连接（扩展端只能有一个连接）
        if self._ws is not None:
            try:
                await self._ws.close(code=1000, reason="new connection")
            except Exception:
                pass
        self._ws = websocket
        self._connected_at = time.time()
        print(f"[Bridge] 浏览器扩展已连接")

        # 连接成功后推送 LLM 配置
        await self._push_llm_configs()

        try:
            while True:
                raw = await websocket.receive_text()
                print(f"[Bridge] WebSocket 收到原始消息: {raw[:200]}")
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    print("[Bridge] WebSocket 收到非法 JSON，忽略")
                    continue

                msg_id = msg.get("id", "")
                msg_action = msg.get("action", "")
                # 心跳消息：直接忽略
                if msg_action == "heartbeat":
                    continue

                # LLM 配置更新：来自扩展的面板选择了新配置
                if msg.get("type") == "set_llm_config":
                    cfg_name = msg.get("configName", "")
                    self.set_active_config_name(cfg_name)
                    continue

                # 命令响应：匹配 pending 请求
                if msg_id and msg_id in self._pending:
                    print(f"[Bridge] WebSocket 匹配到 pending 响应 id={msg_id}, action={msg_action}")
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        future.set_result(msg)
                else:
                    print(f"[Bridge] WebSocket 收到未匹配消息 id={msg_id}, action={msg_action}, pending_keys={list(self._pending.keys())}")
        except WebSocketDisconnect:
            print(f"[Bridge] 浏览器扩展已断开")
        except Exception as e:
            print(f"[Bridge] WebSocket 异常: {e}")
        finally:
            self._ws = None
            self._connected_at = 0.0
            # 清理所有未完成的请求
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(ConnectionError("浏览器扩展已断开"))
            self._pending.clear()

    # ── 命令转发 ──

    async def send_command(self, action: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        """向浏览器扩展发送命令并等待响应。"""
        log.info(f"[Bridge] send_command: action={action}, timeout={timeout}, ws_connected={self._ws is not None}")
        if self._ws is None:
            log.warning("[Bridge] send_command: 扩展未连接")
            raise ConnectionError("浏览器扩展未连接")

        self._counter += 1
        msg_id = f"cmd-{self._counter}"
        future: asyncio.Future = asyncio.Future()
        self._pending[msg_id] = future

        payload = {
            "id": msg_id,
            "action": action,
            "params": params or {},
        }
        print(f"[Bridge] send_command: 发送 payload id={msg_id}, action={action}")
        try:
            await self._ws.send_text(json.dumps(payload, ensure_ascii=False))
        except Exception as e:
            self._pending.pop(msg_id, None)
            print(f"[Bridge] send_command: 发送失败 {e}")
            raise ConnectionError(f"向扩展发送命令失败: {e}")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            print(f"[Bridge] send_command: 收到响应 id={msg_id}, success={result.get('success')}, has_error={bool(result.get('error'))}")
            return result
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            print(f"[Bridge] send_command: 等待响应超时 ({timeout}s): {action}")
            raise TimeoutError(f"浏览器操作超时 ({timeout}s): {action}")

    async def send_delegate(self, task: str, timeout: float = 300.0) -> dict:
        """向浏览器扩展发送委托任务，由扩展端 LLM 自主完成并返回结果。

        Args:
            task: 任务描述，由扩展端 LLM 自主规划执行
            timeout: 超时秒数，默认 300 秒（5 分钟）

        Returns:
            扩展返回的结果字典: {"success": bool, "answer": str, "summary": str, ...}
        """
        cfg = self.get_active_llm_config()
        if not cfg:
            log.warning("[Bridge] send_delegate: 没有可用 LLM 配置")
            return {"success": False, "error": "没有可用的 LLM 配置，请先在主程序发送一条消息或同步配置"}

        params = {
            "task": task,
            "llm_config": {
                "baseUrl": cfg["baseUrl"],
                "apiKey": cfg["apiKey"],
                "model": cfg["model"],
                "protocol": cfg.get("protocol", "anthropic"),
            },
        }
        log.info(f"[Bridge] send_delegate: task={task[:80]}..., timeout={timeout}")
        log.info(f"[Bridge] send_delegate: 使用配置 name={cfg['name']}, model={cfg['model']}, protocol={cfg.get('protocol', 'anthropic')}, baseUrl={cfg['baseUrl']}, apiKey_prefix={cfg['apiKey'][:8] if cfg['apiKey'] else '(empty)'}...")

        return await self.send_command("delegate", params, timeout=timeout)

    @property
    def is_connected(self) -> bool:
        return self._ws is not None


# 全局单例
bridge_manager = NetworkBridgeManager()
