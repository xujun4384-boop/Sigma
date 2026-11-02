"""
豆包语音合成音色注册表（单一数据源）

- 后端工具（doubao_tts / video_produce）与前端 Settings 均以此为准，
  前端通过 GET /api/doubao-voices 读取，避免前后端各写一份导致不一致。
- label 为面向用户的中文名称，不外露 zh_ 开头的音色 ID。
- resource_id 标记音色所属代次（1.0 / 2.0）：官方规定音色与资源 ID 必须同代次，
  1.0 音色只能配 seed-tts-1.0，2.0 音色只能配 seed-tts-2.0，混用会鉴权失败。
- 新增音色只需在 VOICES 追加一条（含所属 resource_id），前后端自动生效。
"""

# 资源 ID（请求头 X-Api-Resource-Id）：豆包语音合成模型代次标识
RESOURCE_TTS_1_0 = "seed-tts-1.0"
RESOURCE_TTS_2_0 = "seed-tts-2.0"

# 音色注册表：id 为豆包音色 ID，label 为前端展示用中文名，resource_id 为所属代次资源
VOICES: list[dict] = [
    {"id": "zh_male_guanggaojieshuo_uranus_bigtts", "label": "广告解说 2.0", "resource_id": RESOURCE_TTS_2_0},
    {"id": "zh_female_mizai_uranus_bigtts", "label": "黑猫侦探社咪仔 2.0", "resource_id": RESOURCE_TTS_2_0},
    {"id": "zh_male_dayi_uranus_bigtts", "label": "大壹 2.0", "resource_id": RESOURCE_TTS_2_0},
    {"id": "zh_male_guozhoudege_moon_bigtts", "label": "广州德哥", "resource_id": RESOURCE_TTS_1_0},
]

# 内置默认音色（广告解说 2.0）与默认资源代次
DEFAULT_VOICE_ID = "zh_male_guanggaojieshuo_uranus_bigtts"
DEFAULT_RESOURCE_ID = RESOURCE_TTS_2_0


def resolve_voice(*candidates: str) -> str:
    """
    按优先级（调用方显式传入 > Settings 配置 > 内置默认）返回第一个非空音色。

    音色 ID 是自由字符串（豆包 2.0 无枚举限制），此处不做白名单校验，
    以便用户/调用方使用未登记的自定义音色。
    """
    for c in candidates:
        v = (c or "").strip()
        if v:
            return v
    return DEFAULT_VOICE_ID


def resolve_resource(voice_id: str) -> str:
    """
    返回音色对应的资源 ID（X-Api-Resource-Id），保证音色与模型代次匹配。

    未登记的音色（用户自定义 / 复刻音色）回落默认资源。
    """
    for v in VOICES:
        if v["id"] == voice_id:
            return v.get("resource_id") or DEFAULT_RESOURCE_ID
    return DEFAULT_RESOURCE_ID


def list_voices() -> list[dict]:
    """返回音色列表副本，供 API 输出。"""
    return [dict(v) for v in VOICES]