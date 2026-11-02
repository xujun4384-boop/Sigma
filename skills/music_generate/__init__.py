"""
music_generate skill - 音乐组（AI 音乐生成）

提供工具:
  music_generate - 文本描述 → 音乐 mp3（纯音乐 / 自定义歌词 / 自动写词）。

设计要点:
  - provider 可切换（腾讯云 TokenHub / MiniMax 开放平台），端点信息集中在
    scripts/music.py 的 PROVIDER_SPECS 里登记，调用逻辑不因厂商而分叉。
  - key 复用前端 SkillKeys 配置（musicGenApiKey），与 image_generate / doubao_tts 同模式。
  - 产物默认落 video_work/<project>/music/，与视频部门目录约定一致。
"""
import os
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult


def _auto_output_path(output_path: str, project: str, cwd: str) -> Path:
    """相对路径自动放入 video_work/<project>/music/ 下，与视频工具约定一致。"""
    p = Path(output_path)
    if p.is_absolute():
        return p
    base = Path(cwd) if cwd else Path(os.getcwd())
    work_dir = base / "video_work"
    if project:
        work_dir = work_dir / project
    return work_dir / "music" / p


class MusicGenerateTool(BaseTool):
    name = "music_generate"
    description = (
        "音乐组：根据文本描述生成音乐（mp3）。支持三种模式——纯音乐（默认，适合做视频配乐/BGM）、"
        "自定义歌词演唱、按主题自动写词演唱。返回音频路径与时长。"
    )
    parameters = [
        ToolParameter("prompt", "string", "音乐描述：风格 / 情绪 / 场景 / 乐器 / BPM（如“轻快的电子配乐，适合科技讲解，无鼓点干扰人声”）"),
        ToolParameter("output_path", "string", "输出 mp3 文件路径（相对路径自动放在 video_work/<project>/music/ 下）"),
        ToolParameter("project", "string", "项目名，与视频工具保持一致", required=False),
        ToolParameter("instrumental", "boolean", "是否纯音乐（无人声），默认 true；做视频配乐一般用 true", required=False, default=True),
        ToolParameter("lyrics", "string", "自定义歌词；建议用 [Verse]/[Chorus]/[Bridge] 等结构标签分段。instrumental=true 时忽略", required=False),
        ToolParameter("auto_lyrics", "boolean", "没有歌词时是否让模型按 prompt 主题自动写词（仅非纯音乐模式生效）", required=False, default=False),
        ToolParameter("format", "string", "输出音频格式，默认 mp3", required=False, default="mp3"),
    ]

    def __init__(self, cwd: str = ".", api_key: str = "", base_url: str = "",
                 default_model: str = "", provider: str = "", **kwargs):
        super().__init__(cwd)
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.provider = provider

    def execute(self, prompt: str, output_path: str, project: str = None,
                instrumental: bool = True, lyrics: str = None,
                auto_lyrics: bool = False, format: str = "mp3",
                **kwargs) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail(
                "未配置音乐生成 API Key。请在 Settings → Skill Keys → 音乐生成 中配置。"
            )

        from .scripts.music import generate, provider_label, resolve_provider

        out = _auto_output_path(output_path, project or "", self.cwd)
        out.parent.mkdir(parents=True, exist_ok=True)

        mode = "纯音乐" if instrumental else ("自定义歌词" if (lyrics or "").strip() else "自动写词")
        self._emit_progress(f"正在生成音乐（{mode}）：{prompt[:40]}{'...' if len(prompt) > 40 else ''}")

        try:
            result = generate(
                api_key=self.api_key,
                output_path=str(out),
                prompt=prompt,
                provider=self.provider,
                base_url=self.base_url,
                model=self.default_model,
                lyrics=lyrics or "",
                instrumental=bool(instrumental),
                auto_lyrics=bool(auto_lyrics),
                audio_format=format or "mp3",
            )
        except Exception as e:
            return ToolResult.fail(f"音乐生成失败: {e}")

        self._emit_progress("音乐生成完成")
        size_mb = result["size_bytes"] / 1024 / 1024
        content = (
            f"音乐生成完成: {Path(result['output_path']).name}\n"
            f"时长: {result['duration']} 秒｜大小: {size_mb:.2f} MB｜模式: {mode}\n"
            f"provider: {provider_label(resolve_provider(self.provider))}｜模型: {result['model']}\n"
            f"文件路径: {result['output_path']}"
        )
        return ToolResult.ok(
            content,
            output_path=result["output_path"],
            duration=result["duration"],
            size_bytes=result["size_bytes"],
            model=result["model"],
            provider=result["provider"],
            instrumental=bool(instrumental),
        )


__all__ = ["MusicGenerateTool"]
