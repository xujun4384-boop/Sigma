"""
doubao_tts skill - 豆包语音合成大模型 2.0 旁白生成

提供工具:
  doubao_tts - 文本 → 旁白 mp3，并返回字级时间戳，用于对齐视频字幕/分镜。

设计要点:
  - 使用火山引擎语音技术（openspeech）的单向流式合成接口。
  - key 复用前端 SkillKeys 配置（doubaoVoiceApiKey），与 image_generate 同模式。
  - 字级时间戳是「旁白时间与视频内容契合」的关键。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

DEFAULT_SPEAKER = "zh_male_guanggaojieshuo_uranus_bigtts"  # 广告解说 2.0


def _auto_output_path(output_path: str, project: str, cwd: str) -> Path:
    """相对路径自动放入 video_work/<project>/ 下，与视频工具约定一致。"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    if project:
        work_dir = work_dir / project
    return work_dir / p


class DoubaoTTS(BaseTool):
    name = "doubao_tts"
    description = (
        "用豆包语音合成大模型 2.0 生成视频旁白（mp3）。"
        "返回字级时间戳（每个字的起止时间），可用于精确对齐视频字幕和分镜时长。"
        "适合为宣传片、新闻资讯等视频生成高质量旁白配音。"
    )
    parameters = [
        ToolParameter("text", "string", "待合成的旁白文本"),
        ToolParameter("output_path", "string", "输出 mp3 文件路径（相对路径自动放在 video_work/<project>/ 下）"),
        ToolParameter("project", "string", "项目名，与视频工具保持一致", required=False),
        ToolParameter("speaker", "string", "音色ID，默认「广告解说2.0」", required=False, default=DEFAULT_SPEAKER),
        ToolParameter("speech_rate", "integer", "语速 -50~100（100=2倍速，-50=0.5倍速）", required=False, default=0),
        ToolParameter("loudness_rate", "integer", "音量 -50~100", required=False, default=0),
    ]

    def __init__(self, cwd: str = ".", api_key: str = "", **kwargs):
        super().__init__(cwd)
        self.api_key = api_key

    def execute(
        self,
        text: str,
        output_path: str,
        project: str = None,
        speaker: str = DEFAULT_SPEAKER,
        speech_rate: int = 0,
        loudness_rate: int = 0,
        **kwargs,
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail(
                "未配置豆包语音 API Key。请在 Settings → Skill Keys 中配置豆包语音生成 Key。"
            )

        out = _auto_output_path(output_path, project, self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        self._emit_progress(f"正在生成旁白 ({len(text)} 字)...")
        try:
            from .scripts.tts import synthesize
            result = synthesize(
                text=text,
                api_key=self.api_key,
                speaker=speaker,
                output_path=str(out),
                speech_rate=speech_rate,
                loudness_rate=loudness_rate,
            )
        except Exception as e:
            return ToolResult.fail(f"旁白生成失败: {e}")

        import json
        words = result["words"]
        content = (
            f"旁白生成完成: {out.name}\n"
            f"总时长: {result['duration']:.2f} 秒\n"
            f"字级时间戳(用于字幕对齐，按句聚合后传给 video_compose 的 subtitles):\n"
            f"{json.dumps(words, ensure_ascii=False)}"
        )
        return ToolResult.ok(
            content,
            output_path=result["output_path"],
            duration=round(result["duration"], 2),
            words=words,
            word_count=len(words),
            speaker=speaker,
        )


__all__ = ["DoubaoTTS"]
