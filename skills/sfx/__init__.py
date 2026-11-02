"""
sfx skill - 音效组（程序合成，不依赖外部素材）

导演组用它给画面加短音效（哔 / duang / whoosh / 盖章 / 金币 等），
与 BGM 无关：BGM 是铺满全片的音乐床，sfx 是带时间点的一次性事件。
"""
from __future__ import annotations

import json
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


class SfxTool(BaseTool):
    name = "sfx"
    description = (
        "音效组：按配方 id 程序合成短音效（wav），不需要 API Key、不依赖外部素材。"
        "先看目录（action='list' 或 skill.md）选 recipe，再用 recipe + 可选 params 生成。"
        "常用：mg.blip / mg.whoosh / cartoon.duang / cartoon.boing / paper.stamp / "
        "pixel.coin / tech.scan / tech.glitch / cinematic.impact / cinematic.riser。"
    )
    parameters = [
        ToolParameter("action", "string", "generate=生成音效；list=查看配方目录", required=False,
                      enum=["generate", "list"], default="generate"),
        ToolParameter("recipe", "string",
                      "配方 id（如 cartoon.duang）。generate 时必填；留空且 action=generate 时返回目录。",
                      required=False),
        ToolParameter("output_path", "string",
                      "输出 wav 路径。留空则落到 video_work/<project>/sfx/ 下（按配方+参数命名）。",
                      required=False),
        ToolParameter("project", "string", "项目名，决定默认产物目录", required=False),
        ToolParameter("params", "object",
                      "可调参数：pitch（半音 -12~12）、brightness（-1~1，负=更暗）、seed（轻微变化）。",
                      required=False),
        ToolParameter("seed", "integer", "变化种子；相同配方+种子输出完全一致。", required=False),
    ]

    def __init__(self, cwd: str = ".", **kwargs):
        super().__init__(cwd)

    @staticmethod
    def _safe(text: str) -> str:
        import re
        s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(text or "").strip())
        return s.strip("._")[:64] or "sfx"

    @staticmethod
    def _hash(obj) -> str:
        import hashlib
        raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:10]

    def execute(self, action: str = "generate", recipe: str = "", output_path: str = "",
                project: str = "", params=None, seed: int = None, **kwargs) -> ToolResult:
        from .scripts import synth

        if str(action or "").lower() == "list" or not str(recipe or "").strip():
            rows = ["可用音效配方（按风格家族）：", ""]
            rows.append(synth.catalog_menu())
            rows += ["", "生成示例：sfx(recipe=\"cartoon.duang\")；调参：params={\"pitch\": -2, \"brightness\": 0.2}"]
            return ToolResult.ok("\n".join(rows), recipes=synth.catalog())

        rid = str(recipe).strip()
        rec = synth.get_recipe(rid)
        if not rec:
            return ToolResult.fail(
                f"未知音效配方: {rid}。可用配方见 action='list'。"
            )

        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}
        params = dict(params or {})
        if seed is not None and "seed" not in params:
            params["seed"] = seed

        if output_path:
            out = self._resolve_path(output_path)
        else:
            proj = self._safe(project or "sfx")
            key = self._hash({"recipe": rid, "params": params})
            out = Path(self.cwd) / "video_work" / proj / "sfx" / f"{self._safe(rid)}_{key}.wav"

        self._emit_progress(f"合成音效：{rid}（{rec['title']}）...")
        try:
            audio = synth.render(rid, params)
            synth.write_wav(str(out), audio)
        except Exception as e:
            return ToolResult.fail(f"音效合成失败（{rid}）: {e}")

        dur = round(len(audio) / synth.SAMPLE_RATE, 3)
        return ToolResult.ok(
            f"音效已生成：{rec['title']}（{rid}）\n"
            f"路径：{out}\n时长：{dur}s｜家族：{synth.FAMILIES.get(rec['family'], {}).get('name', rec['family'])}",
            output_path=str(out),
            recipe=rid,
            duration=dur,
            family=rec["family"],
            params=params,
        )


__all__ = ["SfxTool"]
