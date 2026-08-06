"""
滴滴出行 Skill（DiDi Ride Skill）。

通过 DiDi MCP Server + mcporter CLI 提供：
  - 地址搜索 / 路线规划 / 周边搜索
  - 打车价格预估 / 实时下单 / 订单查询 / 取消订单

前置依赖：
  1. Node.js >= 18
  2. mcporter: npm install -g mcporter
  3. DiDi MCP Key（从 https://mcp.didichuxing.com/claw 获取）
     凭据由 Sigma Settings → Skill Keys 中 didi_mcp_key 注入

⚠️ 暂未注册到 SkillManager（等移植到 macOS 后由 Javis 自行集成）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from skills.base import BaseTool, ToolParameter, ToolResult

# ── 常量 ──────────────────────────────────────────────────────────────

MCP_BASE_URL = "https://mcp.didichuxing.com/mcp-servers"

# 全部可用工具
VALID_ACTIONS = [
    # 地图
    "maps_textsearch",
    "maps_regeocode",
    "maps_place_around",
    "maps_direction_driving",
    "maps_direction_transit",
    "maps_direction_walking",
    "maps_direction_bicycling",
    # 打车
    "taxi_estimate",
    "taxi_create_order",
    "taxi_query_order",
    "taxi_cancel_order",
    "taxi_get_driver_location",
    "taxi_generate_ride_app_link",
]

# 偏好文件路径（相对 skill 目录）
PREFERENCE_FILE = Path(__file__).parent / "PREFERENCE.md"


# ── mcporter 查找 ─────────────────────────────────────────────────────

def _find_mcporter() -> str | None:
    """查找 mcporter CLI 可执行文件路径。"""
    # 1. PATH 中查找
    exe = shutil.which("mcporter") or shutil.which("mcporter.cmd")
    if exe:
        return exe
    # 2. npm 全局安装路径
    try:
        prefix = subprocess.check_output(
            ["npm", "prefix", "-g"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        for name in ("mcporter.cmd", "mcporter"):
            candidate = os.path.join(prefix, name)
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass
    # 3. 常见默认路径
    candidates = [
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm", "mcporter.cmd"),
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm", "mcporter"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


# ── PREFERENCE.md 工具 ─────────────────────────────────────────────────

def _read_preference() -> dict[str, Any]:
    """读取偏好文件，返回结构化数据。"""
    pref: dict[str, Any] = {"aliases": {}, "scenarios": {}, "defaults": {}}
    if not PREFERENCE_FILE.exists():
        return pref

    content = PREFERENCE_FILE.read_text(encoding="utf-8")
    current_section = ""

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if line.startswith("|") and "----" not in line and current_section == "地址别名":
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4 and parts[1]:
                pref["aliases"][parts[0]] = {
                    "name": parts[1], "lng": parts[2], "lat": parts[3], "city": parts[4] if len(parts) > 4 else "",
                }
        elif line.startswith("|") and "----" not in line and "场景车型偏好" in current_section:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 3 and parts[1]:
                pref["scenarios"][parts[0]] = {"vehicle": parts[1], "code": parts[2]}
        elif line.startswith("|") and "----" not in line and "默认偏好" in current_section:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 2:
                pref["defaults"][parts[0]] = parts[1]
    return pref


# ═══════════════════════════════════════════════════════════════════════════════
# DiDi Ride Tool
# ═══════════════════════════════════════════════════════════════════════════════

class DiDiRideTool(BaseTool):
    name = "didi_ride"
    description = (
        "滴滴出行服务。支持：地址搜索、路线规划（驾车/公交/步行/骑行）、周边POI搜索、"
        "打车价格预估、实时下单、订单查询、取消订单。\n"
        "凭据已由 Settings → Skill Keys 中 didi_mcp_key 自动注入。\n"
        "前置：需要安装 mcporter CLI（npm install -g mcporter）并配置 DiDi MCP Key。"
    )
    parameters = [
        ToolParameter(
            "action", "string",
            f"操作类型: {' / '.join(VALID_ACTIONS)}",
            required=True, enum=VALID_ACTIONS,
        ),
        # ── maps_textsearch ──
        ToolParameter("keywords", "string", "搜索关键词（maps_textsearch 必填）", required=False),
        ToolParameter("city", "string", "城市名，必须完整格式如'北京市'", required=False),
        ToolParameter("location", "string", "参考位置坐标，格式'经度,纬度'（maps_textsearch 可选）", required=False),
        # ── maps_place_around ──
        ToolParameter("max_distance", "string", "搜索半径（米）", required=False),
        # ── maps_direction_* ──
        ToolParameter("origin", "string", "起点坐标，格式'经度,纬度'（路线规划必填）", required=False),
        ToolParameter("destination", "string", "终点坐标，格式'经度,纬度'（路线规划必填）", required=False),
        ToolParameter("need_geo", "boolean", "是否返回途经点序列（路线规划可选）", required=False),
        # ── taxi_estimate ──
        ToolParameter("from_lat", "string", "出发纬度（taxi_estimate 必填）", required=False),
        ToolParameter("from_lng", "string", "出发经度（taxi_estimate 必填）", required=False),
        ToolParameter("from_name", "string", "出发地名（taxi_estimate 必填）", required=False),
        ToolParameter("to_lat", "string", "目的纬度（taxi_estimate 必填）", required=False),
        ToolParameter("to_lng", "string", "目的经度（taxi_estimate 必填）", required=False),
        ToolParameter("to_name", "string", "目的地名（taxi_estimate 必填）", required=False),
        # ── taxi_create_order ──
        ToolParameter("estimate_trace_id", "string", "预估 traceId（taxi_create_order 必填）", required=False),
        ToolParameter("product_category", "string", "车型代码，如 '1'=快车 '8'=专车（taxi_create_order 必填）", required=False),
        ToolParameter("caller_car_phone", "string", "叫车手机号（可选，不传则使用默认）", required=False),
        # ── taxi_query_order / taxi_cancel_order / taxi_get_driver_location ──
        ToolParameter("order_id", "string", "订单ID（查询/取消/司机位置 时使用）", required=False),
        ToolParameter("reason", "string", "取消原因（taxi_cancel_order 可选）", required=False),
        # ── taxi_generate_ride_app_link ──
        ToolParameter("product_category_for_link", "string", "车型（生成App链接时可选，多车型逗号分隔）", required=False),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._api_key = api_key
        self._mcp_url = ""

    def _ensure_mcp_url(self) -> str | None:
        """构建 MCP URL，返回错误信息或 None（成功）。"""
        if not self._api_key:
            return (
                "未配置 DiDi MCP Key。请在 Settings → Skill Keys 中填写 didi_mcp_key。\n"
                "获取方式：访问 https://mcp.didichuxing.com/claw 或用滴滴出行App扫码获取。"
            )
        self._mcp_url = f"{MCP_BASE_URL}?key={self._api_key}"
        return None

    def _ensure_mcporter(self) -> str | None:
        """检查 mcporter 是否可用，返回错误信息或 None。"""
        cli = _find_mcporter()
        if not cli:
            return (
                "未找到 mcporter CLI。请先安装：npm install -g mcporter\n"
                "验证安装：mcporter --version"
            )
        return None

    def _call_mcp(self, tool_name: str, args: dict) -> ToolResult:
        """通过 mcporter 调用 DiDi MCP 工具。"""
        mcporter_err = self._ensure_mcporter()
        if mcporter_err:
            return ToolResult.fail(mcporter_err)

        url_err = self._ensure_mcp_url()
        if url_err:
            return ToolResult.fail(url_err)

        args_json = json.dumps({k: str(v) if v is not None else "" for k, v in args.items() if v is not None},
                               ensure_ascii=False)

        cmd = ["mcporter", "call", self._mcp_url, tool_name, "--args", args_json]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail("调用 DiDi MCP 超时（60秒）")
        except FileNotFoundError:
            return ToolResult.fail(
                "未找到 mcporter CLI。请先安装：npm install -g mcporter\n"
                "验证安装：mcporter --version"
            )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            err = stderr or stdout or f"退出码 {result.returncode}"
            # 关键错误识别
            if "StatusCode=400" in err:
                err += "\n提示：通常是参数名拼写错误或必填参数缺失，请核对参数名。"
            elif "-32002" in err:
                err += "\n提示：DiDi MCP Key 鉴权失败，请检查或重新获取。"
            elif "免密支付" in err or "text/plain" in err:
                err += "\n提示：可能未开通 DiDi MCP 免密支付，请到 https://mcp.didichuxing.com 开通。"
            return ToolResult.fail(err)

        # 尝试解析 JSON
        try:
            data = json.loads(stdout)
            # MCP 响应结构：通常含 content[].text 或 structuredContent
            text = ""
            structured = None
            if isinstance(data, dict):
                # 提取 content[].text
                content = data.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text += item.get("text", "") + "\n"
                # 提取 structuredContent
                if "structuredContent" in data and data["structuredContent"] is not None:
                    structured = data["structuredContent"]
            elif isinstance(data, list):
                text = json.dumps(data, ensure_ascii=False, indent=2)

            if structured:
                text = json.dumps(structured, ensure_ascii=False, indent=2) + "\n\n" + text

            return ToolResult.ok(
                (text or stdout)[:8000],
                structured=structured,
                raw=data if isinstance(data, dict) else None,
            )
        except json.JSONDecodeError:
            return ToolResult.ok(stdout[:8000])

    # ─── 主入口 ───

    def execute(
        self,
        action: str,
        # maps
        keywords: str = "", city: str = "", location: str = "",
        origin: str = "", destination: str = "", need_geo: bool = True,
        max_distance: str = "",
        # taxi
        from_lat: str = "", from_lng: str = "", from_name: str = "",
        to_lat: str = "", to_lng: str = "", to_name: str = "",
        estimate_trace_id: str = "", product_category: str = "",
        caller_car_phone: str = "",
        order_id: str = "", reason: str = "",
        product_category_for_link: str = "",
        **kwargs,
    ) -> ToolResult:
        if action not in VALID_ACTIONS:
            return ToolResult.fail(f"不支持的操作: {action}，支持: {', '.join(VALID_ACTIONS)}")

        # 根据 action 构建参数
        args: dict[str, str] = {}
        if action == "maps_textsearch":
            if not keywords or not city:
                return ToolResult.fail("maps_textsearch 需要 keywords 和 city 参数")
            args = {"keywords": keywords, "city": city}
            if location:
                args["location"] = location

        elif action == "maps_regeocode":
            if not location:
                return ToolResult.fail("maps_regeocode 需要 location 参数")
            args = {"location": location}

        elif action == "maps_place_around":
            if not keywords or not location:
                return ToolResult.fail("maps_place_around 需要 keywords 和 location 参数")
            args = {"keywords": keywords, "location": location}
            if max_distance:
                args["max_distance"] = max_distance

        elif action.startswith("maps_direction_"):
            if not origin or not destination:
                return ToolResult.fail(f"{action} 需要 origin 和 destination 参数")
            args = {"origin": origin, "destination": destination}
            if action not in ("maps_direction_transit",):
                args["need_geo"] = "true" if need_geo else "false"
            if action == "maps_direction_transit":
                if not city:
                    return ToolResult.fail("maps_direction_transit 需要 city 参数")
                args["city"] = city

        elif action == "taxi_estimate":
            if not all([from_lat, from_lng, from_name, to_lat, to_lng, to_name]):
                return ToolResult.fail("taxi_estimate 需要 from_lat/from_lng/from_name/to_lat/to_lng/to_name 六个参数")
            args = {
                "from_lat": from_lat, "from_lng": from_lng, "from_name": from_name,
                "to_lat": to_lat, "to_lng": to_lng, "to_name": to_name,
            }

        elif action == "taxi_create_order":
            if not estimate_trace_id or not product_category:
                return ToolResult.fail("taxi_create_order 需要 estimate_trace_id 和 product_category 参数")
            args = {"estimate_trace_id": estimate_trace_id, "product_category": product_category}
            if caller_car_phone:
                args["caller_car_phone"] = caller_car_phone

        elif action in ("taxi_query_order", "taxi_cancel_order", "taxi_get_driver_location"):
            args = {"order_id": order_id} if order_id else {}
            if action == "taxi_cancel_order" and reason:
                args["reason"] = reason

        elif action == "taxi_generate_ride_app_link":
            if not all([from_lat, from_lng, to_lat, to_lng]):
                return ToolResult.fail("taxi_generate_ride_app_link 需要 from_lat/from_lng/to_lat/to_lng 参数")
            args = {"from_lat": from_lat, "from_lng": from_lng, "to_lat": to_lng, "to_lng": to_lng}
            if product_category_for_link:
                args["product_category"] = product_category_for_link

        return self._call_mcp(action, args)


# ─── 命令行入口 ───

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="滴滴出行 Skill")
    sub = parser.add_subparsers(dest="action", required=True)

    p_text = sub.add_parser("maps_textsearch", help="地址搜索")
    p_text.add_argument("--keywords", required=True)
    p_text.add_argument("--city", required=True)
    p_text.add_argument("--location", default="")

    p_geo = sub.add_parser("maps_regeocode", help="坐标转地址")
    p_geo.add_argument("--location", required=True)

    p_around = sub.add_parser("maps_place_around", help="周边搜索")
    p_around.add_argument("--keywords", required=True)
    p_around.add_argument("--location", required=True)
    p_around.add_argument("--max_distance", default="")

    for d in ("driving", "transit", "walking", "bicycling"):
        p_d = sub.add_parser(f"maps_direction_{d}", help=f"{d} 路线规划")
        p_d.add_argument("--origin", required=True)
        p_d.add_argument("--destination", required=True)
        if d == "transit":
            p_d.add_argument("--city", required=True)

    p_est = sub.add_parser("taxi_estimate", help="价格预估")
    p_est.add_argument("--from_lat", required=True)
    p_est.add_argument("--from_lng", required=True)
    p_est.add_argument("--from_name", required=True)
    p_est.add_argument("--to_lat", required=True)
    p_est.add_argument("--to_lng", required=True)
    p_est.add_argument("--to_name", required=True)

    p_order = sub.add_parser("taxi_create_order", help="创建订单")
    p_order.add_argument("--estimate_trace_id", required=True)
    p_order.add_argument("--product_category", required=True)
    p_order.add_argument("--caller_car_phone", default="")

    p_query = sub.add_parser("taxi_query_order", help="查询订单")
    p_query.add_argument("--order_id", default="")

    p_cancel = sub.add_parser("taxi_cancel_order", help="取消订单")
    p_cancel.add_argument("--order_id", required=True)
    p_cancel.add_argument("--reason", default="")

    p_driver = sub.add_parser("taxi_get_driver_location", help="司机位置")
    p_driver.add_argument("--order_id", required=True)

    p_link = sub.add_parser("taxi_generate_ride_app_link", help="生成App链接")
    p_link.add_argument("--from_lat", required=True)
    p_link.add_argument("--from_lng", required=True)
    p_link.add_argument("--to_lat", required=True)
    p_link.add_argument("--to_lng", required=True)
    p_link.add_argument("--product_category", default="")

    args_ns = parser.parse_args()

    tool = DiDiRideTool(api_key=os.environ.get("DIDI_MCP_KEY", ""))
    kwargs = {k: v for k, v in vars(args_ns).items() if v is not None and k != "action"}
    result = tool.execute(**kwargs)
    print(result.content)
