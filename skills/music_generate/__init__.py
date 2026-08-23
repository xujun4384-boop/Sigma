"""MiniMax 音乐生成 Skill。"""
import base64
import json
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from skills.base import BaseTool, ToolParameter, ToolResult

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "music-3.0"


class MusicGenerateTool(BaseTool):
    name = "generate_music"
    description = "根据音乐风格提示词和可选歌词调用 MiniMax 音乐生成服务，保存生成的音频到本地。"
    parameters = [
        ToolParameter("prompt", "string", "音乐风格、情绪、乐器与场景描述", required=False, default=""),
        ToolParameter("lyrics", "string", "歌词；纯音乐时留空", required=False, default=""),
        ToolParameter("is_instrumental", "boolean", "是否生成纯音乐；纯音乐不需要歌词", required=False, default=False),
        ToolParameter("model", "string", "MiniMax 音乐模型名；默认使用设置中的模型", required=False, default=""),
    ]

    def __init__(self, cwd: str = ".", api_key: str = "", base_url: str = "", default_model: str = ""):
        super().__init__(cwd)
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.default_model = default_model or DEFAULT_MODEL

    def execute(
        self,
        prompt: str = "",
        lyrics: str = "",
        is_instrumental: bool = False,
        model: str = "",
    ) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail("未配置 MiniMax 音乐生成 API Key，请在 Skill Keys 中配置。")
        if not prompt and (is_instrumental or not lyrics):
            return ToolResult.fail("纯音乐需要提供 prompt；歌曲需要至少提供歌词或 prompt。")

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "is_instrumental": is_instrumental,
        }
        if prompt:
            payload["prompt"] = prompt
        if lyrics:
            payload["lyrics"] = lyrics

        request = urllib.request.Request(
            f"{self.base_url}/music_generation",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
                message = detail.get("base_resp", {}).get("status_msg") or detail.get("message") or str(detail)
            except Exception:
                message = error.reason
            return ToolResult.fail(f"MiniMax 音乐生成请求失败（HTTP {error.code}）：{message}")
        except Exception as error:
            return ToolResult.fail(f"MiniMax 音乐生成请求失败：{error}")

        base_resp = result.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            return ToolResult.fail(base_resp.get("status_msg") or f"MiniMax 返回错误：{base_resp}")

        audio = self._find_audio(result)
        if not audio:
            return ToolResult.fail("MiniMax 未返回可识别的音频数据。", response=result)

        output_dir = Path(self.cwd) / "generated_music"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"music_{uuid.uuid4().hex[:12]}.mp3"
        output_path = output_dir / filename
        try:
            self._save_audio(audio, output_path)
        except Exception as error:
            return ToolResult.fail(f"音频保存失败：{error}", response=result)

        return ToolResult.ok(
            f"音乐已生成：{output_path}",
            filename=filename,
            filepath=str(output_path.resolve()),
            model=payload["model"],
        )

    @staticmethod
    def _find_audio(data: Any) -> str | None:
        if isinstance(data, dict):
            for key in ("audio", "audio_url", "audio_base64", "url", "file_url"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value
            for value in data.values():
                found = MusicGenerateTool._find_audio(value)
                if found:
                    return found
        elif isinstance(data, list):
            for value in data:
                found = MusicGenerateTool._find_audio(value)
                if found:
                    return found
        return None

    @staticmethod
    def _save_audio(audio: str, output_path: Path) -> None:
        if audio.startswith(("https://", "http://")):
            with urllib.request.urlopen(audio, timeout=120) as response:
                output_path.write_bytes(response.read())
            return
        encoded = audio.split(",", 1)[-1] if audio.startswith("data:") else audio
        try:
            output_path.write_bytes(bytes.fromhex(encoded))
        except ValueError:
            output_path.write_bytes(base64.b64decode(encoded))
