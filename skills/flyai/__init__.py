"""
飞猪 AI 开放平台（FlyAI / Fliggy MCP）旅行搜索 Skill。
通过调用本地 flyai-cli（Node.js）子进程，提供酒店、机票、火车票、
景点 POI、关键词/语义搜索以及万豪酒店/套餐查询能力。
"""

import json
import os
import shutil
import subprocess
import sys
from skills.base import BaseTool, ToolParameter, ToolResult


def _find_flyai_cli() -> str:
    """定位 flyai CLI 可执行文件路径。"""
    # 1. PATH 中查找
    exe = shutil.which("flyai") or shutil.which("flyai.cmd")
    if exe:
        return exe

    # 2. Windows 常见全局 npm 安装路径
    appdata = os.environ.get("APPDATA", "")
    candidate = os.path.join(appdata, "npm", "flyai.cmd")
    if os.path.exists(candidate):
        return candidate

    # 3. npm prefix
    try:
        prefix = subprocess.check_output(["npm", "prefix", "-g"], text=True, stderr=subprocess.DEVNULL).strip()
        for name in ("flyai.cmd", "flyai"):
            candidate = os.path.join(prefix, name)
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass

    return "flyai"


def _format_value(v: Any) -> str:
    """将参数值安全转换为命令行字符串。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _format_response(data: dict) -> str:
    """将 flyai-cli 返回的 JSON 格式化为可读文本。"""
    status = data.get("status")
    message = data.get("message", "")
    result = data.get("data")

    if status != 0:
        return f"查询失败 (status={status}): {message}"

    if result is None:
        return "查询成功，但无数据返回。"

    if isinstance(result, dict):
        lines = []
        for k, v in result.items():
            if v is None:
                continue
            if isinstance(v, list):
                lines.append(f"{k}:")
                lines.append(_format_list(v))
            elif isinstance(v, dict):
                lines.append(f"{k}:")
                for kk, vv in v.items():
                    if vv is not None and vv != "":
                        lines.append(f"  {kk}: {vv}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else "查询成功，但无详细数据返回。"

    if isinstance(result, list):
        return _format_list(result)

    return str(result)


def _format_list(items: list) -> str:
    """将列表格式化为可读文本。"""
    if len(items) == 0:
        return "未查询到相关记录。"
    lines = []
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            fields = []
            for k, v in item.items():
                if v is None or v == "":
                    continue
                if isinstance(v, (dict, list)):
                    continue
                fields.append(f"{k}: {v}")
            if fields:
                lines.append(f"[{idx+1}] " + " | ".join(fields))
        else:
            lines.append(f"[{idx+1}] {item}")
    return "\n".join(lines) if lines else "未查询到相关记录。"


class _FlyAIBase(BaseTool):
    """FlyAI 工具基类，统一处理 API Key 和 CLI 调用。"""

    command: str = ""
    api_key_param: bool = True

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._api_key = api_key

    def _call(self, args: dict) -> ToolResult:
        if self.api_key_param and not self._api_key:
            return ToolResult.fail("FLYAI_API_KEY 未配置")

        # 设置环境变量（CLI 优先读取 FLYAI_API_KEY）
        env = os.environ.copy()
        if self._api_key:
            env["FLYAI_API_KEY"] = self._api_key

        cli = _find_flyai_cli()
        cmd = [cli, self.command]
        for k, v in args.items():
            if v is None or v == "":
                continue
            # CLI 使用 kebab-case 参数名，例如 dep_date -> dep-date
            cli_arg = k.replace("_", "-")
            cmd.append(f"--{cli_arg}")
            cmd.append(_format_value(v))

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
                env=env,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail("调用 flyai-cli 超时（60秒）")
        except FileNotFoundError:
            return ToolResult.fail(
                f"未找到 flyai-cli 可执行文件: {cli}。请先运行: npm i -g @fly-ai/flyai-cli"
            )
        except Exception as e:
            return ToolResult.fail(f"调用 flyai-cli 失败: {e}")

        # 提取 stdout 中的 JSON
        first_json = None
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and line.startswith("{") and line.endswith("}"):
                try:
                    first_json = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if first_json is not None:
            return ToolResult.ok(_format_response(first_json))

        err_text = result.stderr.strip() or result.stdout.strip()
        return ToolResult.fail(err_text or "flyai-cli 无输出")


class FlyAIKeywordSearch(_FlyAIBase):
    name = "flyai_keyword_search"
    description = "飞猪关键词搜索：覆盖酒店、机票、景点、度假等全品类旅行商品，适合明确的旅行需求。"
    parameters = [
        ToolParameter("query", "string", "搜索关键词，例如：杭州3日游、上海到东京机票、三亚五星级酒店", required=True),
    ]

    command = "keyword-search"

    def execute(self, query: str, **kwargs) -> ToolResult:
        return self._call({"query": query})


class FlyAIAISearch(_FlyAIBase):
    name = "flyai_ai_search"
    description = "飞猪 AI 语义搜索：理解复杂旅行意图，例如预算、时间、偏好等多条件自然语言查询。"
    parameters = [
        ToolParameter("query", "string", "自然语言查询，例如：五一去杭州3天，人均2000，住西湖附近", required=True),
    ]

    command = "ai-search"

    def execute(self, query: str, **kwargs) -> ToolResult:
        return self._call({"query": query})


class FlyAISearchFlight(_FlyAIBase):
    name = "flyai_search_flight"
    description = "飞猪机票搜索：查询国内/国际航班，支持单程、往返、直飞/中转筛选、价格排序。"
    parameters = [
        ToolParameter("origin", "string", "出发地城市名，例如：上海、北京", required=True),
        ToolParameter("destination", "string", "目的地城市名，例如：东京、三亚", required=True),
        ToolParameter("dep_date", "string", "出发日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("back_date", "string", "回程日期，格式 YYYY-MM-DD（往返时填写）", required=False),
        ToolParameter("journey_type", "string", "1=直达，2=中转", required=False, enum=["1", "2"]),
        ToolParameter("seat_class_name", "string", "舱位等级：economy, business, first，可多选逗号分隔", required=False),
        ToolParameter("max_price", "integer", "最高价格（人民币）", required=False),
        ToolParameter("sort_type", "string", "排序：1=价格从高到低 2=智能推荐 3=价格从低到高 4=耗时最短 5=耗时最长 6=出发早 7=出发晚 8=直飞优先", required=False, enum=["1", "2", "3", "4", "5", "6", "7", "8"]),
    ]

    command = "search-flight"

    def execute(self, origin: str, destination: str, dep_date: str, **kwargs) -> ToolResult:
        args = {"origin": origin, "destination": destination, "dep_date": dep_date}
        for k in ("back_date", "journey_type", "seat_class_name", "max_price", "sort_type"):
            if kwargs.get(k) not in (None, ""):
                args[k] = kwargs[k]
        return self._call(args)


class FlyAISearchTrain(_FlyAIBase):
    name = "flyai_search_train"
    description = "飞猪火车票搜索：查询国内火车票，支持日期、车次类型、座位等级、排序。"
    parameters = [
        ToolParameter("origin", "string", "出发地城市名或车站名，例如：北京、上海虹桥", required=True),
        ToolParameter("destination", "string", "目的地城市名或车站名，例如：上海、杭州东", required=True),
        ToolParameter("dep_date", "string", "出发日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("journey_type", "string", "1=直达，2=中转", required=False, enum=["1", "2"]),
        ToolParameter("seat_class_name", "string", "座位等级，例如：second class, first class, business class", required=False),
        ToolParameter("sort_type", "string", "排序：1=价格从高到低 2=智能推荐 3=价格从低到高 4=耗时最短 5=耗时最长 6=出发早 7=出发晚 8=直达优先", required=False, enum=["1", "2", "3", "4", "5", "6", "7", "8"]),
    ]

    command = "search-train"

    def execute(self, origin: str, destination: str, dep_date: str, **kwargs) -> ToolResult:
        args = {"origin": origin, "destination": destination, "dep_date": dep_date}
        for k in ("journey_type", "seat_class_name", "sort_type"):
            if kwargs.get(k) not in (None, ""):
                args[k] = kwargs[k]
        return self._call(args)


class FlyAISearchHotel(_FlyAIBase):
    name = "flyai_search_hotel"
    description = "飞猪酒店搜索：按目的地、入住/离店日期、POI、星级、价格、排序查询酒店。"
    parameters = [
        ToolParameter("dest_name", "string", "目的地城市名，例如：杭州、三亚", required=True),
        ToolParameter("check_in_date", "string", "入住日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("check_out_date", "string", "离店日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("poi_name", "string", "POI 名称，例如：西湖、外滩", required=False),
        ToolParameter("hotel_stars", "string", "酒店星级，可多选逗号分隔，例如：4,5", required=False),
        ToolParameter("max_price", "integer", "最高价格（人民币）", required=False),
        ToolParameter("sort", "string", "排序，例如：rate_desc（评分从高到低）、price_asc（价格从低到高）", required=False),
    ]

    command = "search-hotel"

    def execute(self, dest_name: str, check_in_date: str, check_out_date: str, **kwargs) -> ToolResult:
        args = {
            "dest_name": dest_name,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
        }
        for k in ("poi_name", "hotel_stars", "max_price", "sort"):
            if kwargs.get(k) not in (None, ""):
                args[k] = kwargs[k]
        return self._call(args)


class FlyAISearchPOI(_FlyAIBase):
    name = "flyai_search_poi"
    description = "飞猪景点/POI 搜索：按城市、分类、等级、关键词查询景点门票、一日游等。"
    parameters = [
        ToolParameter("city_name", "string", "城市名，例如：西安、北京", required=True),
        ToolParameter("category", "string", "分类，例如：历史古迹、地标建筑、山湖田园", required=False),
        ToolParameter("poi_level", "string", "景点等级，例如：5（5A景区）", required=False),
        ToolParameter("keyword", "string", "关键词，例如：西湖", required=False),
    ]

    command = "search-poi"

    def execute(self, city_name: str, **kwargs) -> ToolResult:
        args = {"city_name": city_name}
        for k in ("category", "poi_level", "keyword"):
            if kwargs.get(k) not in (None, ""):
                args[k] = kwargs[k]
        return self._call(args)


class FlyAISearchMarriottHotel(_FlyAIBase):
    name = "flyai_search_marriott_hotel"
    description = "飞猪万豪酒店搜索：查询万豪集团旗下的酒店，支持目的地、品牌、入住/离店日期。"
    parameters = [
        ToolParameter("dest_name", "string", "目的地城市名，例如：上海、北京", required=True),
        ToolParameter("check_in_date", "string", "入住日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("check_out_date", "string", "离店日期，格式 YYYY-MM-DD", required=True),
        ToolParameter("hotel_brands", "string", "品牌，可多选逗号分隔，例如：JW Marriott,Sheraton", required=False),
    ]

    command = "search-marriott-hotel"

    def execute(self, dest_name: str, check_in_date: str, check_out_date: str, **kwargs) -> ToolResult:
        args = {
            "dest_name": dest_name,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
        }
        if kwargs.get("hotel_brands") not in (None, ""):
            args["hotel_brands"] = kwargs["hotel_brands"]
        return self._call(args)


class FlyAISearchMarriottPackage(_FlyAIBase):
    name = "flyai_search_marriott_package"
    description = "飞猪万豪酒店套餐搜索：查询万豪集团旗下的酒店套餐商品，支持关键词和排序。"
    parameters = [
        ToolParameter("keyword", "string", "搜索关键词，例如：上海、JW Marriott", required=True),
        ToolParameter("sort_type", "string", "排序，例如：price_asc（价格从低到高）", required=False),
    ]

    command = "search-marriott-package"

    def execute(self, keyword: str, **kwargs) -> ToolResult:
        args = {"keyword": keyword}
        if kwargs.get("sort_type") not in (None, ""):
            args["sort_type"] = kwargs["sort_type"]
        return self._call(args)
