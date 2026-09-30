"""
Network Bridge Skill – 操控用户真实浏览器。

支持批量操作：LLM 一次给出多步计划，skill 内部顺序执行，
完成后汇总结果。单步失败即停止剩余步骤。
"""
from __future__ import annotations

import json
from typing import Any

import requests

from skills.base import BaseTool, ToolParameter, ToolResult
from skills.network_bridge.logger import (
    info, warn, error as log_error, debug,
    action_start, action_result, click_detail, content_logs,
)

SIGMA_BRIDGE_URL = "http://127.0.0.1:8765/api/network-bridge"

# 支持的浏览器操作列表（供 LLM 参考）
SUPPORTED_ACTIONS = [
    "navigate",           # 打开 URL
    "snapshot",           # 获取页面 DOM 结构化快照（含语义属性锚点: id/aria-label/name/data-testid/placeholder）
    "ax_snapshot",        # 获取 CDP 无障碍结构
    "find_element",       # 按语义属性在当前 DOM 中实时查找元素（不依赖 @e 编号，解决弹窗/SPA 导致编号漂移）
    "smart_click",        # 按语义属性查找元素并点击（推荐代替 click + @e 的组合）
    "click",              # 点击元素
    "force_click",        # 强制点击（多策略兜底）
    "targeted_click",     # 按语义精准点击
    "inspect_click_target", # 侦察点击目标
    "click_xy",           # 按坐标点击
    "cdp_click",          # CDP 真实鼠标点击
    "fill",               # 输入文本
    "cdp_type",           # CDP 真实文本输入
    "scroll_to",          # 滚动到元素或坐标
    "hover",              # 悬停元素
    "keypress",           # 按键
    "cdp_keypress",       # CDP 真实按键
    "select",             # 下拉框选择
    "evaluate",           # 执行 JavaScript
    "inject_evaluate",    # 主世界执行 JavaScript
    "highlight",          # 高亮元素
    "clear_highlight",    # 清除高亮
    "screenshot",         # 截图
    "cdp_screenshot",     # CDP 截图
    "get_page_text",      # 读取页面文本
    "get_page_html",      # 读取页面 HTML
    "get_page_title",     # 读取页面标题
    "query_selector",     # CSS 选择器查询
    "wait",               # 等待
    "list_tabs",          # 列出标签页
    "new_tab",            # 新建标签页
    "activate_tab",       # 切换标签页
    "close_tab",          # 关闭标签页
    "get_bookmarks",      # 查询收藏夹
    "site_memory_get",    # 读取站点记忆
    "site_memory_put",    # 保存站点记忆
    "start_recording",    # 开始录制操作
    "stop_recording",     # 停止录制操作
    "inspect_all_elements", # 全页面元素扫描
    "clear_inspect",      # 清除元素选框
    "analyze_screenshot", # 截图并使用 vision 模型分析
]


class NetworkBridgeTool(BaseTool):
    name = "network_bridge"
    description = (
        "操控用户真实浏览器。通过 actions 数组逐步骤操作浏览器，每批操作后自动截图。\n"
        "一步失败则停止剩余步骤，适合需要精细控制的场景。3-5 步一批为宜。\n\n"
        "重要——操作动态网页（含弹窗/广告/SPA重渲染）时:\n"
        "- 先 snapshot 获取元素列表（每个元素带有语义属性锚点: id/aria-label/name/data-testid/placeholder）\n"
        "- 使用 smart_click 按语义属性点击（不依赖 @e 编号，不会因弹窗导致点错按钮）\n"
        "- 或先用 find_element 查找元素确认后再操作\n\n"
        "smart_click 接受参数: text / id / ariaLabel / name / testid / placeholder / tag\n"
        "示例: {\"action\":\"smart_click\",\"text\":\"登录\",\"id\":\"login-btn\"}\n"
        "find_element 参数相同，返回匹配元素的详细信息。"
    )

    parameters = [
        ToolParameter(
            "actions",
            "array",
            "浏览器操作序列。每步含 action 和对应参数。\n"
            "示例: [{\"action\":\"navigate\",\"url\":\"https://ctrip.com\"},{\"action\":\"snapshot\"}]",
            required=True,
        ),
        ToolParameter("session", "string", "会话标识", required=False, default="default"),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)
        self._last_snapshot_id = 0
        self._last_content_log_count = 0

    def execute(self, actions: list, session: str = "default", **kwargs) -> ToolResult:
        """执行浏览器操作序列。一步失败则停止剩余步骤。"""
        info(f"execute: actions_count={len(actions) if actions else 0}")

        status = self._check_status()
        print(f"[NetworkBridge] 状态: running={status.get('running')}, ext={status.get('extension_connected')}")
        if not status.get("running"):
            return ToolResult.fail("Sigma 后端未就绪")
        if not status.get("extension_connected"):
            return ToolResult.fail("浏览器扩展未连接")

        if not actions:
            return ToolResult.fail("请提供 actions 参数")

        info(f"手动模式: {len(actions)} 步")
        results = []
        stopped_early = False

        for i, step in enumerate(actions):
            if not isinstance(step, dict) or "action" not in step:
                results.append({"index": i, "success": False, "error": f"步骤 {i} 缺少 'action'"})
                stopped_early = True
                break
            action = step["action"]
            params = {k: v for k, v in step.items() if k != "action"}
            result = self._execute_single(action, params)
            result["index"] = i
            results.append(result)
            if not result.get("success"):
                stopped_early = True
                break

        # 仅在所有操作结束后同步一次 content 日志（非阻塞，失败不影响结果）
        try:
            self._sync_content_logs()
        except Exception:
            pass

        # 只在 LLM 没有 snapshot 时自动追加
        has_snapshot = any(
            isinstance(s, dict) and s.get("action") in ("snapshot", "ax_snapshot", "screenshot", "cdp_screenshot", "get_page_text", "analyze_screenshot")
            for s in actions
        )
        if not has_snapshot:
            final_result = self._execute_single("snapshot", {})
            if final_result.get("success"):
                results.append({"index": len(results), "action": "snapshot", "success": True,
                              "data": final_result.get("data", {})})

        content = json.dumps({
            "total": len(actions), "completed": len([r for r in results if r.get("success")]),
            "stopped_early": stopped_early, "results": results,
        }, ensure_ascii=False, indent=2)
        all_ok = not stopped_early and len(results) >= len(actions)
        return ToolResult.ok(content) if all_ok else ToolResult.fail(content)

    def _execute_single(self, action: str, params: dict) -> dict:
        """执行单步浏览器操作，返回 {"success": bool, "action": str, ...}"""
        action_start(action, params)

        # 独立的截图分析 action，不转发给扩展
        if action == "analyze_screenshot":
            result = self._handle_analyze_screenshot(params)
            action_result(action, result.get("success", False))
            return result

        # 别名处理
        resolved_action, resolved_params = self._resolve_action(action, params)

        payload = {
            "action": resolved_action,
            "args": resolved_params,
        }

        try:
            resp = requests.post(
                f"{SIGMA_BRIDGE_URL}/command",
                json=payload,
                timeout=60,
            )
            try:
                result = resp.json()
            except json.JSONDecodeError:
                log_error(f"非 JSON 响应: HTTP {resp.status_code}, body={resp.text[:300]}")
                action_result(action, False, f"HTTP {resp.status_code} non-JSON")
                return {
                    "action": action,
                    "success": False,
                    "error": f"非 JSON 响应: HTTP {resp.status_code}",
                    "body": resp.text[:500],
                }

            if resp.status_code >= 400:
                err = result.get("error", f"HTTP {resp.status_code}")
                log_error(f"HTTP {resp.status_code}: {err[:200]}")
                action_result(action, False, f"HTTP {resp.status_code}")
                return {
                    "action": action,
                    "success": False,
                    "error": err,
                    "response": result,
                }

            # 扩展返回格式: {"success": bool, "data": {...}} 或 {"success": bool, "error": "..."}
            success = result.get("success", False)
            output = {
                "action": action,
                "success": success,
            }
            if success:
                output["data"] = result.get("data", result)
                # 追踪 snapshot id，供后续 click 自动附加
                if action in ("snapshot", "ax_snapshot"):
                    sid = output["data"].get("snapshotId") if isinstance(output["data"], dict) else None
                    if sid is not None:
                        self._last_snapshot_id = sid
                        debug(f"更新 snapshotId: {sid}")
                # 截图后自动调用 vision 分析
                if action in ("screenshot", "cdp_screenshot") and params.get("analyze"):
                    analysis = self._analyze_screenshot_from_result(
                        output["data"], params.get("prompt")
                    )
                    # 移除原始 base64，只保留分析结果
                    output["data"].pop("screenshot", None)
                    if analysis.get("success"):
                        output["data"]["analysis"] = analysis.get("analysis", "")
                    else:
                        output["data"]["analysis_error"] = analysis.get("error", "")

                # 对点击操作记录详细日志
                if action in ("click", "force_click", "js_click", "targeted_click", "cdp_click", "click_xy"):
                    data = output.get("data", {})
                    if isinstance(data, dict):
                        click_detail(
                            action=action,
                            selector=params.get("selector", params.get("ref", "")),
                            stability=data.get("stability"),
                            navigation_detected=data.get("navigationDetected"),
                            url_before=data.get("urlBefore", ""),
                            url_after=data.get("urlAfter", ""),
                        )
                        if not data.get("clicked") and data.get("needsSnapshot"):
                            warn(f"点击需要重新snapshot: reason={data.get('reason')} message={data.get('message', '')[:100]}")

                action_result(action, True)
            else:
                err = result.get("error", "未知错误")
                log_error(f"{action} 失败: {err[:300]}")
                output["error"] = err
                action_result(action, False, err[:100])
            return output

        except requests.Timeout:
            log_error(f"{action} 超时")
            action_result(action, False, "timeout")
            return {"action": action, "success": False, "error": f"操作超时: {action}"}
        except requests.ConnectionError:
            log_error(f"{action} 无法连接后端")
            action_result(action, False, "connection_error")
            return {"action": action, "success": False, "error": "无法连接 Sigma 后端"}
        except Exception as e:
            log_error(f"{action} 异常: {type(e).__name__}: {e}")
            action_result(action, False, f"{type(e).__name__}")
            return {"action": action, "success": False, "error": str(e)}

    def _sync_content_logs(self):
        """从 content.js 拉取日志并追加到 Python 日志文件"""
        try:
            result = self._execute_single_raw("get_bridge_logs", {"limit": 100})
            debug(f"_sync_content_logs raw result: success={result.get('success')}, keys={list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
            if not result.get("success"):
                debug(f"_sync_content_logs failed: {result.get('error', 'unknown')[:200]}")
                return
            data = result.get("data", {})
            if not isinstance(data, dict):
                debug(f"_sync_content_logs data is not dict: {type(data).__name__}")
                return
            all_logs = data.get("logs", [])
            total = data.get("total", 0)
            debug(f"_sync_content_logs: total={total}, last_synced={self._last_content_log_count}")
            if total <= self._last_content_log_count:
                return  # 无新日志
            new_logs = all_logs[-(total - self._last_content_log_count):]
            if new_logs:
                content_logs(new_logs)
                info(f"已同步 {len(new_logs)} 条 content 日志 (total={total})")
            self._last_content_log_count = total
        except Exception as e:
            debug(f"_sync_content_logs exception: {type(e).__name__}: {e}")

    def _execute_single_raw(self, action: str, params: dict) -> dict:
        """执行单步但不记录 action_start/result（内部使用）"""
        resolved_action, resolved_params = self._resolve_action(action, params)
        try:
            resp = requests.post(
                f"{SIGMA_BRIDGE_URL}/command",
                json={"action": resolved_action, "args": resolved_params},
                timeout=10,
            )
            return resp.json()
        except Exception:
            return {"success": False}

    def _take_screenshot(self) -> str:
        """对当前页面截图（低质量JPEG压缩），返回 markdown 图片引用格式"""
        try:
            result = self._execute_single_raw("screenshot", {"format": "jpeg", "quality": 40})
            if not result.get("success"):
                debug(f"_take_screenshot failed: {result.get('error', 'unknown')[:100]}")
                return ""
            data = result.get("data", {})
            screenshot_b64 = data.get("screenshot", "")
            if not screenshot_b64:
                return ""
            # 限制大小：超过100KB截断
            if len(screenshot_b64) > 100000:
                debug(f"_take_screenshot truncated from {len(screenshot_b64)} to 100000 bytes")
                screenshot_b64 = screenshot_b64[:100000]
            mime = data.get("mimeType", "image/jpeg")
            return f"\n\n## 当前页面截图\n![screenshot](data:{mime};base64,{screenshot_b64})\n"
        except Exception as e:
            debug(f"_take_screenshot exception: {e}")
            return ""

    def _resolve_action(self, action: str, params: dict) -> tuple[str, dict]:
        """处理操作别名和参数兼容。"""
        params = dict(params)

        # open_url → navigate
        if action == "open_url":
            action = "navigate"

        # navigate 时 url 参数兼容
        if action == "navigate":
            if "url" not in params and "query" in params:
                params["url"] = params.pop("query")
            # 导航后旧 snapshotId 失效，需要重新 snapshot
            self._last_snapshot_id = 0

        # fill 时 value 兼容 text
        if action in ("fill", "input"):
            if "text" in params and "value" not in params:
                params["value"] = params.pop("text")

        # click 时 @e ref 用 selector 传递（扩展 content script 接收 selector 参数）
        if action in ("click", "force_click", "fill", "scroll_to", "hover", "select"):
            if "ref" in params and "selector" not in params:
                params["selector"] = params.pop("ref")

        # 对 @e ref 点击自动附加快照 id，用于跨代际校验
        if action in ("click", "force_click") and self._last_snapshot_id > 0:
            selector = params.get("selector", "")
            if isinstance(selector, str) and selector.startswith("@e"):
                params.setdefault("snapshotId", self._last_snapshot_id)

        # js_click → force_click
        if action == "js_click":
            action = "force_click"

        # screenshot/cdp_screenshot 的 analyze/prompt 是 skill 层参数，不传给扩展
        if action in ("screenshot", "cdp_screenshot"):
            params.pop("analyze", None)
            params.pop("prompt", None)

        # get_bookmarks keyword 兼容 query
        if action == "get_bookmarks":
            if "keyword" in params and "query" not in params:
                params["query"] = params.pop("keyword")

        return action, params

    def _check_status(self) -> dict:
        """检查 Sigma 后端和浏览器扩展状态。"""
        try:
            resp = requests.get(f"{SIGMA_BRIDGE_URL}/status", timeout=5)
            data = resp.json()
            print(f"[NetworkBridge] /status: running={data.get('running')}, extension_connected={data.get('extension_connected')}")
            return data
        except Exception as e:
            print(f"[NetworkBridge] /status 异常: {e}")
            return {"running": False, "extension_connected": False, "error": str(e)}

    # ─── Vision 截图分析 ───

    def _handle_analyze_screenshot(self, params: dict) -> dict:
        """截图并返回文件路径，由主 LLM 通过 batch_read 读取。"""
        source = params.get("source", "visible")  # visible | full
        screenshot_action = "screenshot" if source == "visible" else "cdp_screenshot"
        # 透传 format/quality 等截图参数
        screenshot_params = {
            k: v for k, v in params.items()
            if k not in ("action", "source", "prompt", "analyze")
        }
        screenshot_result = self._execute_single(screenshot_action, screenshot_params)
        if not screenshot_result.get("success"):
            return {
                "action": "analyze_screenshot",
                "success": False,
                "error": screenshot_result.get("error", "截图失败"),
            }

        data = screenshot_result.get("data", {})
        screenshot_path = data.get("path", "")

        if not screenshot_path:
            return {
                "action": "analyze_screenshot",
                "success": False,
                "error": "截图结果中没有文件路径",
            }

        # 返回文件路径，由主 LLM 通过 batch_read 读取
        return {
            "action": "analyze_screenshot",
            "success": True,
            "data": {
                "analysis": f"[截图已完成，文件路径: {screenshot_path}。可使用 batch_read 读取]",
                "screenshot_path": screenshot_path,
            },
        }


skill = NetworkBridgeTool()
