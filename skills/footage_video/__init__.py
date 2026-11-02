# -*- coding: utf-8 -*-
"""footage_video - 用户自备素材引擎（导演组内部）

把用户自己放在项目文件夹里的视频（常见是 10 秒 mp4）**直接**用作某一段画面：
  - 输入不限容器（mp4/mov/mkv/webm/avi…），输出**统一转成 mp4**；
  - 只做规格统一（等比缩放/补边或裁切、统一 fps 与像素格式），画布默认 1920×1080，不重绘、不改内容；
  - 段长 = 素材原长（可用 clip_seconds 截取前 N 秒），不做补帧拉伸；
  - 原声默认保留（单独抽出音频轨交给导演做该段音频；有旁白时旁白优先）；
  - 标题/蒙版包装由导演用 title_overlay 叠加，本工具只管底片。

与 cinematic 的区别：画面不是 AI 生成，也不需要 API 额度；
是否启用**只能由用户主动提供素材并指定**，不做任何自动挑选。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

FITS = ("contain", "cover")


class FootageVideoTool(BaseTool):
    name = "footage_video"
    description = (
        "用户自备素材引擎：把用户提供的本地视频（如 10 秒 mp4）直接作为一段画面。"
        "非 mp4 素材会自动转成 mp4；画面统一到目标画布（默认 1920×1080），"
        "只做 contain 补边 / cover 裁切与可选截取，不重绘不改内容；"
        "默认保留素材原声并单独输出音频轨。是否使用只能由用户主动指定素材，不做自动选择。"
    )
    parameters = [
        ToolParameter("input_path", "string",
                      "用户提供的视频文件路径（相对项目目录或绝对路径；mp4/mov/mkv/webm 等均可）"),
        ToolParameter("output_path", "string", "输出 mp4 路径（非 .mp4 后缀会自动改为 .mp4）"),
        ToolParameter("width", "integer", "目标画布宽", required=False, default=1920),
        ToolParameter("height", "integer", "目标画布高", required=False, default=1080),
        ToolParameter("fps", "integer", "目标帧率", required=False, default=30),
        ToolParameter("fit", "string", "画布适配：contain=完整保留并补黑边（默认）；cover=等比裁切铺满",
                      required=False, default="contain", enum=list(FITS)),
        ToolParameter("clip_seconds", "number", "只取素材前 N 秒（0/缺省=整段原长）",
                      required=False, default=0),
        ToolParameter("keep_audio", "boolean", "是否保留素材原声（默认 true；该段有旁白时旁白优先）",
                      required=False, default=True),
    ]

    def __init__(self, cwd: str = ".", **kwargs):
        super().__init__(cwd)

    def execute(self, input_path: str, output_path: str, width: int = 1920,
                height: int = 1080, fps: int = 30, fit: str = "contain",
                clip_seconds: float = 0, keep_audio: bool = True,
                **kwargs) -> ToolResult:
        src = self._resolve_path(input_path)
        if not src.exists() or src.stat().st_size <= 0:
            return ToolResult.fail(
                f"找不到用户提供的视频素材：{input_path}（已按项目目录解析为 {src}）。"
                f"请把素材放到项目文件夹，或在蓝图里写对路径。"
            )
        fit = str(fit or "contain").strip().lower()
        if fit not in FITS:
            return ToolResult.fail(f"fit={fit!r} 不认识，只能是 {' / '.join(FITS)}")
        # 上游蓝图可能把布尔写成字符串（"false"），在边界处归一，避免 bool("false") == True。
        if isinstance(keep_audio, str):
            keep_audio = keep_audio.strip().lower() not in ("0", "false", "no", "none", "")
        try:
            clip = float(clip_seconds or 0)
        except (TypeError, ValueError):
            return ToolResult.fail(f"clip_seconds 需为秒数，收到: {clip_seconds}")
        clip = max(0.0, clip)

        out = self._resolve_path(output_path)
        self._emit_progress(f"使用用户素材：{src.name}（{fit}）...")
        try:
            from .scripts.render import render_footage
            res = render_footage(
                str(src), str(out), W=int(width or 1920), H=int(height or 1080),
                fps=int(fps or 30), fit=fit, target=clip, keep_audio=bool(keep_audio),
            )
        except Exception as e:
            return ToolResult.fail(f"用户素材处理失败：{e}")

        note = (f"用户素材已就位：{Path(res['output_path']).name} "
                f"（{res['duration']}s / {res['width']}x{res['height']} / {res['fit']}）")
        if res.get("converted_to_mp4"):
            note += "\n格式：非 mp4 素材，已转成 mp4（H.264）"
        if res["has_source_audio"]:
            note += "\n原声：" + ("已保留（独立音频轨）" if res["audio_path"] else "已按要求丢弃")
        else:
            note += "\n原声：素材本身无音轨"
        return ToolResult.ok(
            note,
            output_path=res["output_path"],
            duration=res["duration"],
            source_duration=res["source_duration"],
            width=res["width"],
            height=res["height"],
            fps=res["fps"],
            fit=res["fit"],
            clipped=res["clipped"],
            converted_to_mp4=res.get("converted_to_mp4"),
            has_source_audio=res["has_source_audio"],
            audio_path=res["audio_path"],
            deliverable=True,
        )


__all__ = ["FootageVideoTool"]
