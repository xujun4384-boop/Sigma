"""
百度地图 Agent Plan Skill
提供语义化 AI 地点检索、路线规划、地理编码、逆地理编码、天气查询、地图展示能力。
统一使用 BAIDU_MAP_AUTH_TOKEN 鉴权，Base URL: https://api.map.baidu.com/
"""
import json
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import sys
from skills.base import BaseTool, ToolParameter, ToolResult


BASE_URL = "https://api.map.baidu.com"
TOKEN_HINT = (
    "未配置 BAIDU_MAP_AUTH_TOKEN。"
    "请前往 https://lbs.baidu.com/apiconsole/agentplan 申请，"
    "然后在环境变量或配置文件中设置。"
)


def _get_token() -> str:
    """从环境变量读取 token，子类可通过实例属性覆盖。"""
    import os
    return os.environ.get("BAIDU_MAP_AUTH_TOKEN", "")


def _request(endpoint: str, params: dict, token: str) -> ToolResult:
    """统一 GET 请求，带 Authorization Header。"""
    if not token:
        return ToolResult.fail(TOKEN_HINT)

    url = f"{BASE_URL}{endpoint}"
    query = urllib.parse.urlencode(params, safe="")
    full_url = f"{url}?{query}"

    req = urllib.request.Request(
        full_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return ToolResult.fail(f"百度地图 API 错误 HTTP {e.code}: {detail}")
    except Exception as e:
        return ToolResult.fail(f"请求异常: {e}")

    return ToolResult.ok(json.dumps(data, ensure_ascii=False, indent=2), raw=data)


def _format_poi_list(items: list) -> str:
    """格式化 POI 列表为可读文本。"""
    if not items:
        return "未找到相关地点。"
    lines = []
    for idx, item in enumerate(items, 1):
        name = item.get("name", "未知")
        addr = item.get("address", "")
        dist = item.get("distance", "")
        uid = item.get("uid", "")
        line = f"[{idx}] {name}"
        if addr:
            line += f" | {addr}"
        if dist:
            line += f" | 距离 {dist}m"
        if uid:
            line += f" | uid: {uid}"
        lines.append(line)
    return "\n".join(lines)


class _BaiduMapBase(BaseTool):
    """百度地图工具基类，统一处理 token。"""

    def __init__(self, cwd: str = ".", auth_token: str = ""):
        super().__init__(cwd)
        self._auth_token = auth_token or _get_token()

    @property
    def token(self) -> str:
        return self._auth_token


class BaiduMapPlaceTool(_BaiduMapBase):
    """语义化 AI 地点检索"""

    name = "baidu_map_place"
    description = (
        "语义化 AI 地点检索。根据用户自然语言需求搜索 POI，"
        "支持约束词（如「评分最高」「最近」「3公里内」）。"
        "返回 POI 列表，包含名称、地址、距离、uid 等。"
    )
    parameters = [
        ToolParameter(
            "user_raw_request", "string",
            "用户原始需求，原样完整传入，不可压缩为关键词；保留约束词",
            required=True,
        ),
        ToolParameter(
            "region", "string",
            "城市或区域限制，例如：北京市、延庆区",
            required=True,
        ),
        ToolParameter(
            "center", "string",
            "检索中心点和排序参考点，格式 lat,lng（gcj02），仅来自用户明确提供或可信来源",
            required=False,
        ),
        ToolParameter(
            "sort", "string",
            "排序方式：distance（距离）或 relevance（相关度，默认）",
            required=False,
            enum=["distance", "relevance"],
            default="relevance",
        ),
    ]

    def execute(self, user_raw_request: str, region: str,
                center: str = "", sort: str = "relevance", **kwargs) -> ToolResult:
        params = {
            "user_raw_request": user_raw_request,
            "region": region,
            "sort": sort,
        }
        if center:
            params["center"] = center

        result = _request("/agent_plan/v1/place", params, self.token)
        if not result.success:
            return result

        data = result.details.get("raw", {})
        pois = data.get("result", {}).get("pois", [])
        formatted = _format_poi_list(pois)
        resource_key = data.get("result", {}).get("resource_key", "")
        if resource_key:
            formatted += f"\n\nresource_key: {resource_key}（可用于地图展示）"
        return ToolResult.ok(formatted, raw=data, resource_key=resource_key)


class BaiduMapDirectionTool(_BaiduMapBase):
    """语义化 AI 路线规划"""

    name = "baidu_map_direction"
    description = (
        "语义化 AI 路线规划。支持驾车、步行、骑行、公交四种方式，"
        "可处理沿途搜索 POI（如「路上买杯咖啡」）。"
        "返回完整路线方案或地点澄清列表。"
    )
    parameters = [
        ToolParameter(
            "user_raw_request", "string",
            "用户原始需求，包含起点、终点、途经点；保留路线约束词，需推理改写交通方式",
            required=True,
        ),
        ToolParameter(
            "location", "string",
            "用户当前位置坐标，格式 lat,lng（gcj02），至少保留小数点后 6 位",
            required=True,
        ),
        ToolParameter(
            "refer_pois", "string",
            "地点精确映射，用于消歧，格式：地点名称:uid,纬度,经度;地点名称:uid,纬度,经度",
            required=False,
        ),
    ]

    def execute(self, user_raw_request: str, location: str,
                refer_pois: str = "", **kwargs) -> ToolResult:
        params = {
            "user_raw_request": user_raw_request,
            "location": location,
        }
        if refer_pois:
            params["refer_pois"] = refer_pois

        result = _request("/agent_plan/v1/direction", params, self.token)
        if not result.success:
            return result

        data = result.details.get("raw", {})
        answer_type = data.get("result", {}).get("answer_type", "")
        resource_key = data.get("result", {}).get("resource_key", "")

        if answer_type == "gptmodel_navigate":
            routes = data.get("result", {}).get("routes", [])
            lines = ["路线规划结果："]
            for idx, route in enumerate(routes, 1):
                dist = route.get("distance", "")
                dur = route.get("duration", "")
                lines.append(f"方案[{idx}] 距离: {dist}m | 耗时: {dur}秒")
                steps = route.get("steps", [])
                for s_idx, step in enumerate(steps[:5], 1):  # 最多显示5步
                    ins = step.get("instruction", "")
                    lines.append(f"  {s_idx}. {ins}")
                if len(steps) > 5:
                    lines.append(f"  ... 共 {len(steps)} 步")
            if resource_key:
                lines.append(f"\nresource_key: {resource_key}（可用于地图展示）")
            return ToolResult.ok("\n".join(lines), raw=data, resource_key=resource_key)

        elif answer_type in ("gptmodel_poi_clarify", "gptmodel_onway_search_clarify"):
            pois = data.get("result", {}).get("pois", [])
            lines = ["需要您确认具体地点："]
            for idx, poi in enumerate(pois, 1):
                name = poi.get("name", "未知")
                addr = poi.get("address", "")
                uid = poi.get("uid", "")
                lat = poi.get("location", {}).get("lat", "")
                lng = poi.get("location", {}).get("lng", "")
                lines.append(f"[{idx}] {name} | {addr} | uid:{uid} | 坐标:{lat},{lng}")
            lines.append("\n请回复序号选择，我将重新规划路线。")
            return ToolResult.ok("\n".join(lines), raw=data, answer_type=answer_type)

        return ToolResult.ok(json.dumps(data, ensure_ascii=False, indent=2), raw=data)


class BaiduMapGeocodingTool(_BaiduMapBase):
    """地理编码：地址 → 坐标"""

    name = "baidu_map_geocoding"
    description = "将完整地址解析为 gcj02 坐标。"
    parameters = [
        ToolParameter("address", "string", "要解析的完整地址", required=True),
        ToolParameter("region", "string", "城市/区域提示（减少歧义）", required=False),
    ]

    def execute(self, address: str, region: str = "", **kwargs) -> ToolResult:
        params = {"address": address}
        if region:
            params["region"] = region

        result = _request("/agent_plan/v1/geocoding", params, self.token)
        if not result.success:
            return result

        data = result.details.get("raw", {})
        loc = data.get("result", {}).get("location", {})
        lat = loc.get("lat", "")
        lng = loc.get("lng", "")
        formatted = f"地址: {address}\n坐标: {lat},{lng} (gcj02)"
        return ToolResult.ok(formatted, raw=data, lat=lat, lng=lng)


class BaiduMapReverseGeocodingTool(_BaiduMapBase):
    """逆地理编码：坐标 → 地址"""

    name = "baidu_map_reverse_geocoding"
    description = "将 gcj02 坐标转换为语义化地址。"
    parameters = [
        ToolParameter(
            "location", "string",
            "lat,lng 格式坐标（gcj02），至少保留小数点后 6 位",
            required=True,
        ),
    ]

    def execute(self, location: str, **kwargs) -> ToolResult:
        params = {"location": location}
        result = _request("/agent_plan/v1/reverse_geocoding", params, self.token)
        if not result.success:
            return result

        data = result.details.get("raw", {})
        addr = data.get("result", {}).get("formatted_address", "")
        return ToolResult.ok(f"坐标 {location} 对应地址: {addr}", raw=data)


class BaiduMapWeatherTool(_BaiduMapBase):
    """天气查询"""

    name = "baidu_map_weather"
    description = "按行政区划名称或坐标查询天气。"
    parameters = [
        ToolParameter("region", "string", "行政区划名称，例如：北京市", required=False),
        ToolParameter(
            "location", "string",
            "lat,lng 格式坐标（gcj02），与 region 至少传一个",
            required=False,
        ),
    ]

    def execute(self, region: str = "", location: str = "", **kwargs) -> ToolResult:
        if not region and not location:
            return ToolResult.fail("region 与 location 至少传一个")

        params = {}
        if region:
            params["region"] = region
        if location:
            params["location"] = location

        result = _request("/agent_plan/v1/weather", params, self.token)
        if not result.success:
            return result

        data = result.details.get("raw", {})
        weather = data.get("result", {})
        lines = ["天气信息："]
        for k, v in weather.items():
            if v:
                lines.append(f"  {k}: {v}")
        return ToolResult.ok("\n".join(lines), raw=data)


class BaiduMapRenderTool(_BaiduMapBase):
    """地图展示：生成并打开地图链接"""

    name = "baidu_map_render"
    description = (
        "根据 place/direction 接口返回的 resource_key 生成地图展示链接，"
        "并自动打开浏览器。仅在用户明确表达「在地图上查看」等可视化意图时使用。"
    )
    parameters = [
        ToolParameter(
            "resource_key", "string",
            "地图资源唯一标识，取自 place/direction 接口响应中的 resource_key 字段",
            required=True,
        ),
        ToolParameter(
            "open_browser", "boolean",
            "是否自动打开浏览器，默认 true",
            required=False,
            default=True,
        ),
    ]

    def execute(self, resource_key: str, open_browser: bool = True, **kwargs) -> ToolResult:
        url = f"https://lbs.baidu.com/mapstatic/agentui_resource.html?resource_key={resource_key}"

        if open_browser:
            try:
                if sys.platform == "darwin":
                    subprocess.run(["open", url], check=False)
                elif sys.platform == "linux":
                    subprocess.run(["xdg-open", url], check=False)
                else:  # Windows
                    subprocess.run(["start", "", url], shell=True, check=False)
            except Exception:
                pass  # 打开浏览器失败不影响返回链接

        return ToolResult.ok(f"地图展示链接: {url}", url=url, resource_key=resource_key)
