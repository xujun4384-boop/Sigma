# -*- coding: utf-8 -*-
"""music_generate 内部实现：按 provider 调用音乐生成 API，落盘为音频文件。

设计要点（通用性）：
  - provider 以「配置表」登记（base_url / 路径 / 默认模型），新增厂商只需加一条登记，
    不做 if/else 分支堆叠，也不做任何名称关键词匹配。
  - 腾讯云 TokenHub 与 MiniMax 开放平台共用同一套请求/响应契约（TokenHub 即 MiniMax 的代理），
    因此 payload 构造与响应解析只有一份实现；两者只是端点与模型名不同。

接口语义（三选一的创作模式，由调用方参数决定）：
  - 纯音乐：is_instrumental=true（无需歌词）
  - 自定义歌词：传 lyrics（可带 [Verse]/[Chorus] 等结构标签）
  - 自动写词：lyrics_optimizer=true + prompt 描述主题
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PROVIDER = "tencent_tokenhub"
DEFAULT_AUDIO_FORMAT = "mp3"
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_BITRATE = 256000

# 纯音乐模式的提示词外壳。
# 为什么要有它：音乐模型对「无人声」这类否定句不敏感，甚至在提示词里出现
# “人声/演唱/vocal” 反而会把它当成素材线索。所以这里改成**先正面声明器乐**、
# 再把编曲落成具体乐器，最后才补一句排除项；并且由工具统一加，不靠上游 LLM 自觉。
INSTRUMENTAL_PREFIX = "纯器乐配乐，全部声部由乐器演奏。"
INSTRUMENTAL_SUFFIX = (
    "编曲：合成器铺底，弦乐与钢琴承担主旋律，鼓组与打击乐提供节奏。"
    "只做器乐，不安排主唱或合唱声部。"
)


def instrumental_prompt(prompt: str) -> str:
    """把任意风格描述包装成「器乐优先」的提示词。

    结构固定：正面声明 → 用户风格 → 具体编曲与排除项。
    这样即使上游只写了一句"史诗感"，产出也不会落到歌曲形态。
    """
    text = (prompt or "").strip().strip("。.;；")
    if not text:
        text = "现代感科技配乐，节奏清晰，适合做视频背景"
    return f"{INSTRUMENTAL_PREFIX}风格与情绪：{text}。{INSTRUMENTAL_SUFFIX}"

# provider → 端点信息与默认模型。新增厂商在此登记即可（无需改动调用逻辑）。
PROVIDER_SPECS = {
    "tencent_tokenhub": {
        "label": "腾讯云 TokenHub",
        "base_url": "https://tokenhub.tencentmaas.com",
        "path": "/v1/wand/minimax-music/generation",
        "default_model": "minimax-music-v3.0",
    },
    "minimax": {
        "label": "MiniMax 开放平台",
        "base_url": "https://api.minimaxi.com",
        "path": "/v1/music_generation",
        "default_model": "music-3.0",
    },
}


def resolve_provider(provider: str) -> str:
    """归一化 provider 名；未知值回落到默认 provider。"""
    name = (provider or "").strip().lower()
    return name if name in PROVIDER_SPECS else DEFAULT_PROVIDER


def provider_label(provider: str) -> str:
    return PROVIDER_SPECS[resolve_provider(provider)]["label"]


def resolve_endpoint(provider: str, base_url: str = "") -> str:
    """base_url 可覆盖默认主机；路径由 provider 决定。"""
    spec = PROVIDER_SPECS[resolve_provider(provider)]
    host = (base_url or "").strip().rstrip("/") or spec["base_url"]
    return f"{host}{spec['path']}"


def resolve_model(provider: str, model: str = "") -> str:
    spec = PROVIDER_SPECS[resolve_provider(provider)]
    return (model or "").strip() or spec["default_model"]


def build_payload(prompt: str, lyrics: str, instrumental: bool, auto_lyrics: bool,
                  model: str, output_format: str, audio_format: str,
                  sample_rate: int, bitrate: int) -> dict:
    """构造请求体。三种创作模式互斥，优先级：纯音乐 > 自定义歌词 > 自动写词。"""
    payload = {
        "model": model,
        "prompt": prompt,
        "output_format": output_format,
        "audio_setting": {
            "sample_rate": int(sample_rate),
            "bitrate": int(bitrate),
            "format": audio_format,
        },
    }
    if instrumental:
        # 三个信号一起给：接口文档说「is_instrumental=true 或 lyrics 为空」都算纯音乐，
        # 只传开关时实测有概率仍出人声（尤其经代理层转发时字段可能被丢），
        # 这里把空歌词和「不要自动写词」也显式写上，避免模型回落到默认的带人声歌曲模式。
        payload["is_instrumental"] = True
        payload["lyrics"] = ""
        payload["lyrics_optimizer"] = False
    else:
        if (lyrics or "").strip():
            payload["lyrics"] = lyrics
        if auto_lyrics:
            payload["lyrics_optimizer"] = True
    return payload


def _post_json(url: str, api_key: str, payload: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
        except Exception:
            detail = {}
        message = (
            (detail.get("base_resp") or {}).get("status_msg")
            or detail.get("message")
            or str(detail)
            or error.reason
        )
        raise RuntimeError(f"HTTP {error.code}: {message}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"网络请求失败: {error.reason}") from error


def _extract_audio(data: dict) -> str:
    base_resp = data.get("base_resp") or {}
    code = base_resp.get("status_code")
    if code not in (None, 0):
        raise RuntimeError(base_resp.get("status_msg") or f"status_code={code}")
    audio = (data.get("data") or {}).get("audio")
    if not audio:
        raise RuntimeError("API 响应中没有音频数据（data.audio 为空）")
    return audio


def _download(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Sigma/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _decode_audio(audio: str, timeout: int) -> bytes:
    """把 data.audio 解成音频字节。

    接口对 output_format 的遵守并不稳定（实测腾讯云 TokenHub 传入 hex 仍返回下载链接），
    因此按**实际返回值**判定：是 http(s) 链接就下载，否则按十六进制解码。
    """
    text = (audio or "").strip()
    if text[:7].lower() == "http://" or text[:8].lower() == "https://":
        return _download(text, timeout)
    return bytes.fromhex(text)


def generate(*, api_key: str, output_path: str, prompt: str,
             provider: str = "", base_url: str = "", model: str = "",
             lyrics: str = "", instrumental: bool = True, auto_lyrics: bool = False,
             output_format: str = "url", audio_format: str = DEFAULT_AUDIO_FORMAT,
             sample_rate: int = DEFAULT_SAMPLE_RATE, bitrate: int = DEFAULT_BITRATE,
             timeout: int = 900) -> dict:
    """调用音乐生成 API 并把音频写入 output_path，返回结果元信息。"""
    if not api_key:
        raise ValueError("缺少音乐生成 API Key")
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("prompt 不能为空")
    if instrumental:
        # 纯音乐模式统一加器乐外壳：不依赖上游怎么写，避免落到歌曲/哼唱形态
        prompt = instrumental_prompt(prompt)
    if not instrumental and not (lyrics or "").strip() and not auto_lyrics:
        raise ValueError(
            "非纯音乐模式需要提供 lyrics（自定义歌词）或开启 auto_lyrics（自动写词）"
        )

    prov = resolve_provider(provider)
    endpoint = resolve_endpoint(prov, base_url)
    mdl = resolve_model(prov, model)

    payload = build_payload(
        prompt=prompt, lyrics=lyrics, instrumental=instrumental,
        auto_lyrics=auto_lyrics, model=mdl, output_format=output_format,
        audio_format=audio_format, sample_rate=sample_rate, bitrate=bitrate,
    )

    data = _post_json(endpoint, api_key, payload, timeout)
    audio = _extract_audio(data)
    audio_bytes = _decode_audio(audio, timeout)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio_bytes)

    extra = data.get("extra_info") or {}
    duration_ms = extra.get("music_duration") or 0
    try:
        duration = round(float(duration_ms) / 1000.0, 3)
    except (TypeError, ValueError):
        duration = 0.0

    return {
        "output_path": str(out.resolve()),
        "duration": duration,
        "size_bytes": len(audio_bytes),
        "model": mdl,
        "provider": prov,
        "provider_label": provider_label(prov),
        "prompt": prompt,
        "extra_info": extra,
    }
