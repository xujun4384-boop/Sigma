"""
storyboard_designer - 电影分镜脚本设计模块

使用 LLM 将用户意图拆解为结构化电影分镜，支持 Anthropic / OpenAI 双协议。
"""
import json
import re


# ─── Prompt 模板 ───

CINEMATIC_STORYBOARD_PROMPT = """你是一位资深电影导演和分镜师。请根据用户的视频意图，设计一份专业的电影分镜脚本。

## 输出要求

请严格只返回如下 JSON 格式，不要添加任何解释或 markdown 标记：
{
  "title": "视频标题（中文，10字以内）",
  "logline": "一句话剧情概括（中文，20字以内）",
  "scenes": [
    {
      "scene_id": 1,
      "prompt": "详细英文提示词，必须包含：主体(subject)、动作(action)、环境(environment)、镜头(camera)、光影(lighting)、氛围(mood)。支持使用 [运镜指令] 语法，如 [推进], [拉远], [左摇], [上升], [跟随], [固定] 等",
      "prompt_zh": "中文分镜说明（给用户的通俗解释）",
      "duration": 10,
      "camera": "镜头运动描述（如 slow push in, aerial tracking, static wide shot）",
      "mood": "情绪/氛围关键词（如 epic, melancholic, tense, serene）",
      "lighting": "光影描述（如 golden hour, neon noir, soft diffused）"
    }
  ],
  "total_duration": 30,
  "style_notes": "整体视觉风格说明（中文）"
}

## 分镜设计原则

1. **时长分配**：单镜可选 6 秒或 10 秒（Hailuo-2.3 768P 单镜最长 10 秒）。额度按实际生成扣减，10 秒约为 6 秒的两倍；按叙事需要选择时长，不必为“用满额度”硬拉 10 秒。如需更长剧情，拆成多个分镜。
2. **镜头语言**：合理运用远景(establishing)、中景(medium)、特写(close-up)、航拍(aerial)等
3. **节奏控制**：快慢结合，有起承转合，高潮镜头适当延长
4. **光影统一**：全片保持统一的光影风格和色调
5. **运镜指令**：Hailuo-2.3 支持 [指令] 语法，可在 prompt 中嵌入精确镜头控制：
   - 左右移: [左移], [右移]
   - 左右摇: [左摇], [右摇]
   - 推拉: [推进], [拉远]
   - 升降: [上升], [下降]
   - 上下摇: [上摇], [下摇]
   - 变焦: [变焦推近], [变焦拉远]
   - 其他: [晃动], [跟随], [固定]
   - 组合运镜: 同一组 [] 内多个指令同时生效，如 [左摇,上升]，建议不超过 3 个
   - 顺序运镜: prompt 中前后出现的指令依次生效，如 "...[推进], 然后...[拉远]"

## 提示词撰写规范

每个 prompt 必须是英文，包含以下要素：
- 主体（谁/什么）
- 动作（在做什么）
- 环境（在哪里，什么氛围）
- 镜头（怎么拍，可嵌入 [运镜指令]）
- 光影（什么光线）
- 情绪（什么感觉）

示例：
"Cinematic wide shot, a lone astronaut standing on the edge of a massive crater, [slow push in] as they raise their helmet visor to reveal a determined expression, golden hour sunlight casting long shadows across the lunar surface, dust particles floating in the low gravity, epic atmosphere, photorealistic, 8K quality"
"""


# ─── 解析函数 ───

def _strip_markdown_json(text: str) -> str:
    """去除 Markdown 代码块标记，提取纯 JSON 文本。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) > 1:
            lines = lines[1:]
        else:
            lines = []
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _regex_fallback(text: str) -> dict:
    """
    正则兜底：当 JSON 解析失败时，尝试用正则从 LLM 响应中提取字段。
    """
    result = {"title": "", "logline": "", "scenes": [], "style_notes": ""}

    # 提取 title
    title_patterns = [
        r'"title"\s*:\s*"([^"]*)"',
        r'"标题"\s*:\s*"([^"]*)"',
    ]
    for pat in title_patterns:
        m = re.search(pat, text)
        if m:
            result["title"] = m.group(1).strip()
            break

    # 提取 logline
    logline_patterns = [
        r'"logline"\s*:\s*"([^"]*)"',
        r'"一句话概括"\s*:\s*"([^"]*)"',
    ]
    for pat in logline_patterns:
        m = re.search(pat, text)
        if m:
            result["logline"] = m.group(1).strip()
            break

    # 提取 scenes 数组
    scenes_match = re.search(
        r'"scenes"\s*:\s*(\[[^\]]*\])',
        text, re.DOTALL,
    )
    if scenes_match:
        try:
            result["scenes"] = json.loads(scenes_match.group(1))
        except json.JSONDecodeError:
            pass

    # 提取 style_notes
    style_match = re.search(r'"style_notes"\s*:\s*"([^"]*)"', text)
    if style_match:
        result["style_notes"] = style_match.group(1).strip()

    return result


def parse_storyboard(raw_response: str) -> dict:
    """
    解析 LLM 响应为结构化分镜脚本。

    返回:
        {
            "title": str,
            "logline": str,
            "scenes": [
                {
                    "scene_id": int,
                    "prompt": str,
                    "prompt_zh": str,
                    "duration": int,
                    "camera": str,
                    "mood": str,
                    "lighting": str
                }
            ],
            "total_duration": int,
            "style_notes": str
        }
    """
    text = _strip_markdown_json(raw_response)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = _regex_fallback(text)
        else:
            data = _regex_fallback(text)

    # 标准化输出
    result = {
        "title": str(data.get("title", "")).strip(),
        "logline": str(data.get("logline", "")).strip(),
        "scenes": [],
        "total_duration": int(data.get("total_duration", 0)),
        "style_notes": str(data.get("style_notes", "")).strip(),
    }

    raw_scenes = data.get("scenes", [])
    if isinstance(raw_scenes, list):
        for i, s in enumerate(raw_scenes):
            if isinstance(s, dict):
                duration = s.get("duration", 10)
                # Hailuo-2.3 仅支持 6 秒或 10 秒，赠送额度按条数计算
                # 默认偏向 10 秒以充分利用赠送额度
                duration = int(duration)
                if duration not in (6, 10):
                    duration = 10 if duration >= 8 else 6
                result["scenes"].append({
                    "scene_id": int(s.get("scene_id", i + 1)),
                    "prompt": str(s.get("prompt", "")).strip(),
                    "prompt_zh": str(s.get("prompt_zh", "")).strip(),
                    "duration": duration,
                    "camera": str(s.get("camera", "")).strip(),
                    "mood": str(s.get("mood", "")).strip(),
                    "lighting": str(s.get("lighting", "")).strip(),
                })

    # 自动计算总时长
    if not result["total_duration"] and result["scenes"]:
        result["total_duration"] = sum(s["duration"] for s in result["scenes"])

    # 如果没有有效场景，创建一个默认场景
    if not result["scenes"]:
        result["scenes"] = [{
            "scene_id": 1,
            "prompt": "Cinematic shot, " + raw_response[:300],
            "prompt_zh": "默认场景",
            "duration": 10,
            "camera": "static",
            "mood": "neutral",
            "lighting": "natural",
        }]
        result["total_duration"] = 10

    return result


# ─── LLM 调用 ───

def call_llm_design_storyboard(
    user_intent: str,
    total_duration: int = 15,
    style: str = "cinematic",
    scene_count: int = None,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
    max_tokens: int = 8192,
    timeout: int = 120,
    protocol: str = "anthropic",
) -> dict:
    """
    调用 LLM（支持 Anthropic Messages / OpenAI Chat Completions 双协议）设计电影分镜脚本。

    参数:
        user_intent: 用户视频意图描述
        total_duration: 目标总时长（秒）
        style: 视觉风格参考
        scene_count: 分镜数量（可选）
        base_url: LLM API base URL
        api_key: LLM API key
        model: LLM 模型名称
        max_tokens: 最大输出 tokens
        timeout: 请求超时（秒）
        protocol: "anthropic" 或 "openai"

    返回:
        结构化分镜脚本 dict
    """
    import httpx

    if not base_url or not api_key or not model:
        raise ValueError("LLM 配置不完整: 需要 base_url, api_key, model")

    base_url = base_url.rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # 构建用户消息
    user_msg = f"""用户视频意图：{user_intent}

目标总时长：{total_duration} 秒
视觉风格：{style}
"""
    if scene_count:
        user_msg += f"分镜数量：{scene_count} 个\n"

    if protocol == "openai":
        api_url = f"{base_url}/chat/completions" if "/v1" in base_url else f"{base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": CINEMATIC_STORYBOARD_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        }
    else:
        api_url = f"{base_url}/messages" if "/v1" in base_url else f"{base_url}/v1/messages"
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": CINEMATIC_STORYBOARD_PROMPT,
            "messages": [
                {"role": "user", "content": user_msg},
            ],
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"LLM API 返回错误 {e.response.status_code}: {e.response.text[:500]}")
    except httpx.RequestError as e:
        raise RuntimeError(f"LLM API 请求失败: {e}")

    # 提取响应文本
    if protocol == "openai":
        choices = data.get("choices", [])
        response_text = choices[0].get("message", {}).get("content", "") if choices else ""
    else:
        content_blocks = data.get("content", [])
        response_text = ""
        for block in content_blocks:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    response_text += block.get("text", "")
                elif block.get("type") == "content":
                    response_text += str(block.get("text", ""))

    if not response_text:
        raise RuntimeError(f"LLM 响应中未找到文本内容。响应 keys: {list(data.keys())}")

    return parse_storyboard(response_text)
