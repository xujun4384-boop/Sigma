"""
风鸟（Fengniao / Riskbird）企业查询 Skill。
提供中国企业工商信息、股东、高管、对外投资、变更记录、
以及风险数据（被执行、失信、限高、经营异常、严重违法、行政处罚）查询。
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from skills.base import BaseTool, ToolParameter, ToolResult


FENGNIAO_BASE_URL = "https://m.riskbird.com/prod-qbb-api"

TOOL_DEFS = {
    "biz_fuzzy_search": {
        "endpoint": "/skills/searchHint",
        "method": "GET",
    },
    "biz_basic_info": {
        "endpoint": "/skills/dataDimension?version=B1",
        "method": "GET",
    },
    "biz_shareholders": {
        "endpoint": "/skills/dataDimension?version=B2",
        "method": "GET",
    },
    "biz_executives": {
        "endpoint": "/skills/dataDimension?version=B3",
        "method": "GET",
    },
    "biz_investments": {
        "endpoint": "/skills/dataDimension?version=B4",
        "method": "GET",
    },
    "biz_changes": {
        "endpoint": "/skills/dataDimension?version=B5",
        "method": "GET",
    },
    "risk_executed": {
        "endpoint": "/skills/dataDimension?version=C2",
        "method": "GET",
    },
    "risk_dishonest": {
        "endpoint": "/skills/dataDimension?version=C3",
        "method": "GET",
    },
    "risk_limit_consumption": {
        "endpoint": "/skills/dataDimension?version=C4",
        "method": "GET",
    },
    "risk_abnormal_operation": {
        "endpoint": "/skills/dataDimension?version=D1",
        "method": "GET",
    },
    "risk_serious_illegal": {
        "endpoint": "/skills/dataDimension?version=D2",
        "method": "GET",
    },
    "risk_admin_penalty": {
        "endpoint": "/skills/dataDimension?version=D11",
        "method": "GET",
    },
}


class _FengniaoClient:
    """风鸟 API HTTP 客户端。"""

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def _call(self, tool_id: str, **params) -> dict:
        if not self._api_key:
            return {"code": 9999, "msg": "API Key 未配置"}

        tool = TOOL_DEFS.get(tool_id)
        if not tool:
            return {"code": 8888, "msg": f"未知工具: {tool_id}"}

        url = FENGNIAO_BASE_URL + tool["endpoint"]
        query_params = {"apikey": self._api_key}
        for k, v in params.items():
            if v is not None and v != "":
                query_params[k] = str(v)

        full_url = url + "&" + urllib.parse.urlencode(query_params) if "?" in url else url + "?" + urllib.parse.urlencode(query_params)

        try:
            req = urllib.request.Request(full_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
                return json.loads(body)
            except Exception:
                return {"code": e.code, "msg": f"HTTP {e.code}"}
        except Exception as e:
            return {"code": -1, "msg": str(e)}


def _format_response(data: dict) -> str:
    """将 API 响应格式化为可读文本。"""
    code = data.get("code")
    msg = data.get("msg", "")
    result = data.get("data", data)

    if code is not None and code != 20000 and code != 0:
        # 没有数据或错误
        if code == 20000 or (isinstance(result, list) and len(result) == 0):
            return "未查询到相关记录。"
        return f"查询失败 (code={code}): {msg}"

    if isinstance(result, dict):
        # 单条记录，格式化键值对
        lines = []
        for k, v in result.items():
            if v is not None and v != "":
                lines.append(f"{k}: {v}")
        return "\n".join(lines) if lines else "查询成功，但无详细数据返回。"

    if isinstance(result, list):
        if len(result) == 0:
            return "未查询到相关记录。"
        lines = []
        for idx, item in enumerate(result):
            if isinstance(item, dict):
                fields = []
                for k, v in item.items():
                    if v is not None and v != "":
                        fields.append(f"{k}: {v}")
                if fields:
                    lines.append(f"[{idx+1}] " + " | ".join(fields))
            else:
                lines.append(f"[{idx+1}] {item}")
        return "\n".join(lines)

    return str(result)


# ── 12 个工具类 ──


class FengniaoFuzzySearch(BaseTool):
    name = "fengniao_search"
    description = "企业模糊搜索：根据企业名称关键词（中文）搜索企业，返回企业全称、entid（内部ID）和经营状态。必须先调此工具获取 entid，才能查询其他维度。"
    parameters = [
        ToolParameter("key", "string", "搜索关键词，必须是中文，如企业简称或全称。例如：腾讯、阿里巴巴、华为", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, key: str, **kwargs) -> ToolResult:
        if not key.strip():
            return ToolResult.fail("请提供企业搜索关键词")
        data = self._client._call("biz_fuzzy_search", key=key.strip())
        return ToolResult.ok(_format_response(data))


class FengniaoBasicInfo(BaseTool):
    name = "fengniao_basic_info"
    description = "查询企业工商基本信息：注册资本、法定代表人、成立日期、注册地址、经营范围、经营状态、行业分类、统一社会信用代码、官网、电话、邮箱等。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取。注意：不要展示给用户", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("biz_basic_info", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoShareholders(BaseTool):
    name = "fengniao_shareholders"
    description = "查询企业股东信息：股东名单、持股比例、认缴出资额、股东类型（自然人/法人）、认缴日期、出资方式。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("biz_shareholders", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoExecutives(BaseTool):
    name = "fengniao_executives"
    description = "查询企业高级职员：董事、监事、高管及法定代表人，包含姓名、职务（可多职务）、持股比例。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("biz_executives", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoInvestments(BaseTool):
    name = "fengniao_investments"
    description = "查询企业对外投资：被投公司列表，包含持股比例、被投企业经营状态、成立日期、注册资本、法定代表人。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("biz_investments", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoChanges(BaseTool):
    name = "fengniao_changes"
    description = "查询企业工商变更记录：变更日期、变更事项（法人变更/地址变更/注册资本变更等）、变更前后内容。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("biz_changes", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoExecuted(BaseTool):
    name = "fengniao_executed"
    description = "查询企业被执行人记录：法院强制执行信息，包含案号、执行法院、立案时间、执行标的金额、案件状态。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_executed", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoDishonest(BaseTool):
    name = "fengniao_dishonest"
    description = "查询企业失信被执行人（老赖）记录：失信行为类型、履行情况、列入日期、执行法院。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_dishonest", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoLimitConsumption(BaseTool):
    name = "fengniao_limit_consumption"
    description = "查询企业限制高消费记录：案号、限制法院、立案日期、申请人列表、关联法定代表人。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_limit_consumption", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoAbnormalOperation(BaseTool):
    name = "fengniao_abnormal_operation"
    description = "查询企业经营异常记录：列入原因、列入日期、列入机关、移出原因、移出日期。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_abnormal_operation", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoSeriousIllegal(BaseTool):
    name = "fengniao_serious_illegal"
    description = "查询企业严重违法记录：被列入严重违法失信名单的记录，包含列入原因、列入日期、移出情况。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_serious_illegal", entid=entid)
        return ToolResult.ok(_format_response(data))


class FengniaoAdminPenalty(BaseTool):
    name = "fengniao_admin_penalty"
    description = "查询企业行政处罚记录：处罚机关、处罚日期、违法事实、处罚金额、处罚依据。"
    parameters = [
        ToolParameter("entid", "string", "企业唯一标识，通过 fengniao_search 获取", required=True),
    ]

    def __init__(self, cwd: str = ".", api_key: str = ""):
        super().__init__(cwd)
        self._client = _FengniaoClient(api_key)

    def execute(self, entid: str, **kwargs) -> ToolResult:
        data = self._client._call("risk_admin_penalty", entid=entid)
        return ToolResult.ok(_format_response(data))
