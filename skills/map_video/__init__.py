# -*- coding: utf-8 -*-
"""map_video - 高德真实地图引擎（导演组内部）

把「真实地图镜头」做成一段 mp4：中国/世界行政区、真实驾车/步行/骑行路线、
地点标注、行程演示。底层是高德 JS API 2.0 + DistrictLayer，Playwright 逐帧截图。

和 styled 的 `visualStyle="map"` 区别：
  - styled map 是**风格化纸地图**（插画/纸纹/虚线），不保证真实地理；
  - 本引擎是**真实地图**（真实省界/国界/道路/路线），用于真实地点与行程。

spec 结构（由导演组设计 LLM 写在面板的 `map` 字段）：
{
  "kind": "route|region|world",
  "title": "...", "subtitle": "...", "kicker": "...",
  "theme": "dark|light",
  "list": true,
  "markers": [{"name": "北京", "sub": "BEIJING", "coord": [116.4074, 39.9042], "side": "left-up"}],
  "route": {"origin": "三里屯", "destination": "国贸", "mode": "driving",
            "origin_name": "...", "destination_name": "..."},
  "region": {"soc": "CHN", "depth": 1, "bounds": [[73.5,3.8],[135.1,53.6]],
             "highlight": ["北京市", "上海市"]},
  "world": {"highlight": ["CHN", "USA"], "center": [104.2, 20]}
}

Key 由前端「设置 → 技能 API 配置 → 高德地图」注入（SkillManager 构造参数）；
环境变量 AMAP_JS_KEY / AMAP_SECURITY_CODE 仅用于命令行调试。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

HERE = Path(__file__).resolve().parent
RENDERER = HERE / "scripts" / "render.py"


class MapVideoTool(BaseTool):
    name = "map_video"
    description = (
        "高德真实地图引擎：真实中国/世界行政区、真实驾车/步行/骑行路线、地点标注与行程演示。"
        "spec.kind = route（两地点路线）/ region（中国或省市行政区）/ world（世界国家）。"
        "与 styled 的 visualStyle=map（风格化纸地图）不同：本引擎用于真实地理与真实行程。"
    )
    parameters = [
        ToolParameter("spec", "object", "地图 spec：kind/title/subtitle/theme/city/markers/route/region/world"),
        ToolParameter("output_path", "string", "输出 mp4 路径"),
        ToolParameter("duration", "number", "时长秒（默认 6）", required=False, default=6),
        ToolParameter("width", "integer", "画布宽，默认 1920", required=False, default=1920),
        ToolParameter("height", "integer", "画布高，默认 1080", required=False, default=1080),
        ToolParameter("fps", "integer", "帧率，默认 30", required=False, default=30),
    ]

    def __init__(self, cwd: str = ".", amap_js_key: str = "",
                 amap_security_code: str = "", **kwargs):
        super().__init__(cwd)
        self.api_key = (amap_js_key or "").strip()
        self.security_code = (amap_security_code or "").strip()

    def _keys(self) -> tuple:
        """Key 只来自前端配置（构造参数）或调试环境变量，不落程序目录。"""
        key = self.api_key or os.environ.get("AMAP_JS_KEY", "").strip()
        code = self.security_code or os.environ.get("AMAP_SECURITY_CODE", "").strip()
        return key, code

    @property
    def available(self) -> bool:
        key, code = self._keys()
        return bool(key and code)

    def execute(self, spec, output_path: str, duration: float = 6,
                width: int = 1920, height: int = 1080, fps: int = 30,
                **kwargs) -> ToolResult:
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except Exception as e:
                return ToolResult.fail(f"map spec 不是有效 JSON：{e}")
        if not isinstance(spec, dict):
            return ToolResult.fail("map spec 必须是对象")

        kind = str(spec.get("kind") or "").strip().lower()
        if kind not in ("route", "region", "world", "flight"):
            return ToolResult.fail("map.kind 只能是 route / region / world / flight")
        if kind == "route":
            r = spec.get("route") or {}
            if not isinstance(r, dict) or not r.get("origin") or not r.get("destination"):
                return ToolResult.fail("route 需要 origin 与 destination（地名或 [经度,纬度]）")
        if kind == "flight":
            f = spec.get("flight") or {}
            if not isinstance(f, dict):
                return ToolResult.fail("flight 必须是对象")
            if not (f.get("from") or spec.get("from")) or not (f.get("to") or spec.get("to")):
                return ToolResult.fail("flight 需要 from 与 to（城市名或 [经度,纬度]）")
        if kind == "region" and not isinstance(spec.get("region") or {}, dict):
            return ToolResult.fail("region 必须是对象")
        if kind == "world" and not isinstance(spec.get("world") or {}, dict):
            return ToolResult.fail("world 必须是对象")

        key, code = self._keys()
        if not key or not code:
            return ToolResult.fail(
                "未配置高德 Key。请在「设置 → 技能 API 配置 → 高德地图」填写"
                " Web端(JS API) Key 和安全密钥 jscode。")

        out = self._resolve_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        secs = max(2.0, min(60.0, float(duration or spec.get("seconds") or 6)))
        W, H, Fps = max(320, int(width or 1920)), max(240, int(height or 1080)), max(12, int(fps or 30))

        fd, spec_path = tempfile.mkstemp(prefix="map_spec_", suffix=".json")
        os.close(fd)
        Path(spec_path).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["AMAP_JS_KEY"] = key
        env["AMAP_SECURITY_CODE"] = code

        self._emit_progress(f"高德地图：{kind}（{secs:g}s，{W}x{H}）生成中...")
        try:
            r = subprocess.run(
                [sys.executable, str(RENDERER), "--spec", spec_path,
                 "--out", str(out), "--seconds", f"{secs:g}", "--fps", str(Fps),
                 "--width", str(W), "--height", str(H)],
                capture_output=True, text=True, timeout=1200, env=env,
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail("高德地图渲染超时（1200s）")
        finally:
            try:
                Path(spec_path).unlink()
            except OSError:
                pass

        if r.returncode != 0 or not out.exists() or out.stat().st_size < 1024:
            tail = (r.stderr or r.stdout or "")[-1600:]
            return ToolResult.fail(f"高德地图渲染失败：\n{tail}")

        real_dur = 0.0
        try:
            from skills.compose_video.scripts.renderer import probe_duration
            real_dur = float(probe_duration(str(out)) or 0.0)
        except Exception:
            pass
        size_mb = round(out.stat().st_size / 1048576, 2)
        self._emit_progress(f"高德地图完成：{kind} / {real_dur or secs:g}s / {size_mb} MB")
        return ToolResult.ok(
            f"高德地图完成：{kind} / {real_dur or secs:g}s / {size_mb} MB\n输出：{out}",
            output_path=str(out.resolve()),
            duration=real_dur or secs,
            kind=kind,
            size_mb=size_mb,
            deliverable=True,
        )


__all__ = ["MapVideoTool"]
