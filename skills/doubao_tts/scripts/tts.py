"""doubao_tts - 豆包语音合成大模型调用封装

使用单向流式 HTTP 接口：一次性输入文本，流式返回 base64 音频片段，
最后一个包携带字级时间戳（sentence.words）。用于生成视频旁白并精确对齐字幕/分镜。
音色与资源 ID（模型代次）必须匹配，resource_id 由调用方按音色解析后传入。
"""
import base64
import json
import uuid
from pathlib import Path

import httpx

from ..voices import DEFAULT_RESOURCE_ID, RESOURCE_TTS_1_0

API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
# 流式接口的成功码（非流式文档示例为 0，实际流式返回 20000000）
_OK_CODES = {0, 20000000}


def synthesize(
    text: str,
    api_key: str,
    speaker: str,
    output_path: str,
    resource_id: str = DEFAULT_RESOURCE_ID,
    speech_rate: int = 0,
    loudness_rate: int = 0,
    audio_format: str = "mp3",
    sample_rate: int = 24000,
    timeout: int = 120,
) -> dict:
    """合成语音并保存到 output_path。

    resource_id: 音色所属模型代次的资源 ID，默认 2.0。

    返回:
        {
            "output_path": str,
            "words": [{"word": str, "startTime": float, "endTime": float, "confidence": float}],
            "duration": float,   # 总时长（最后一个字的 endTime）
            "audio_bytes": int,  # 音频字节数
        }
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text 不能为空")
    if not api_key:
        raise ValueError("缺少豆包语音 API Key")
    if not speaker:
        raise ValueError("缺少音色 speaker")

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    audio_params = {
        "format": audio_format,
        "sample_rate": sample_rate,
        "enable_subtitle": True,
    }
    if resource_id == RESOURCE_TTS_1_0:
        # 1.0 音色需显式开启字级时间戳（2.0 默认返回）
        audio_params["enable_timestamp"] = True
    if speech_rate:
        audio_params["speech_rate"] = speech_rate
    if loudness_rate:
        audio_params["loudness_rate"] = loudness_rate

    body = {
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": audio_params,
        }
    }

    try:
        resp = httpx.post(API_URL, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"豆包 TTS HTTP 错误 {e.response.status_code}: {e.response.text[:300]}")
    except httpx.RequestError as e:
        raise RuntimeError(f"豆包 TTS 请求失败: {e}")

    # 解析流式 NDJSON：多个 JSON 对象，每行一个
    chunks = []
    words = []
    code = None
    message = ""

    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("data"):
            chunks.append(base64.b64decode(obj["data"]))
        sentence = obj.get("sentence")
        # 流式接口对每个分句返回一条 sentence.words，必须累积（不能覆盖，否则只剩最后一句）
        if isinstance(sentence, dict) and sentence.get("words"):
            words.extend(sentence["words"])
        if obj.get("code") is not None:
            code = obj["code"]
        if obj.get("message"):
            message = obj["message"]

    if not chunks:
        raise RuntimeError(f"豆包 TTS 未返回音频（code={code}, message={message}）")

    audio = b"".join(chunks)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)

    duration = words[-1].get("endTime", 0.0) if words else 0.0

    return {
        "output_path": str(out.resolve()),
        "words": words,
        "duration": duration,
        "audio_bytes": len(audio),
    }
