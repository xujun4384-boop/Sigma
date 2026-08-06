"""
语音合成 - Edge TTS 封装
"""
import edge_tts
import asyncio
import os

VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "xiaochen": "zh-CN-XiaochenNeural",
}


async def generate_async(text: str, output_path: str, voice: str = "yunxi") -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    voice_id = VOICES.get(voice, VOICES["yunxi"])
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(output_path)
    return output_path


def generate(text: str, output_path: str, voice: str = "yunxi") -> str:
    return asyncio.run(generate_async(text, output_path, voice))
