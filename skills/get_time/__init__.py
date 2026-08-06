"""
get_current_time skill - 获取当前时间

提供给 LLM 准确的时间感知能力，避免 LLM 使用训练截止时间。
"""
import time
from datetime import datetime
from datetime import timezone as timezone_module

from skills.base import BaseTool, ToolParameter, ToolResult


class GetCurrentTimeTool(BaseTool):
    name = "get_current_time"
    description = (
        "获取当前准确时间。每次进行需要时间上下文的任务前都应调用此工具，"
        "因为 LLM 的训练截止时间远早于实际当前时间。"
        "支持本地时间、UTC 时间和自定义时区。"
    )
    parameters = [
        ToolParameter("format", "string", "时间格式化字符串（Python strftime 格式），默认 '%Y-%m-%d %H:%M:%S'", required=False, default="%Y-%m-%d %H:%M:%S"),
        ToolParameter("timezone", "string", "时区: local / utc / IANA 名称（如 Asia/Shanghai），默认 local", required=False, default="local"),
        ToolParameter("return_timestamp", "boolean", "是否返回 Unix 时间戳，默认 false", required=False, default=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, format: str = "%Y-%m-%d %H:%M:%S",
                timezone: str = "local", return_timestamp: bool = False, **kwargs) -> ToolResult:
        try:
            tz_name = timezone.lower().strip()
            if tz_name == "utc":
                dt = datetime.now(timezone_module.utc)
                actual_tz = "UTC"
            elif tz_name == "local":
                dt = datetime.now()
                actual_tz = "local"
            else:
                try:
                    from zoneinfo import ZoneInfo
                    dt = datetime.now(ZoneInfo(timezone))
                    actual_tz = timezone
                except Exception:
                    dt = datetime.now()
                    actual_tz = "local"

            extra = dict(timezone=actual_tz, iso=dt.isoformat())
            if return_timestamp:
                extra["timestamp"] = time.time()

            return ToolResult.ok(dt.strftime(format), **extra)
        except Exception as e:
            return ToolResult.fail(f"获取时间失败: {e}")
