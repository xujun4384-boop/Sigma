"""
news_parser - 新闻脚本提炼模块

使用 LLM（Anthropic Messages 协议）将新闻原文提炼为竖屏短视频结构化脚本。
"""
import json
import re


# ─── Prompt 模板 ───

NEWS_PARSE_SYSTEM_PROMPT = (
    "你是一位资深短视频编导。请根据用户提供的【新闻内容】，提炼出适合竖屏短视频脚本的结构化数据。\n\n"
    "要求：\n"
    "1. 大标题（title）：10-18个字，抓人眼球，口语化\n"
    "2. 副标题（subtitle）：一句话金句，点出核心观点或警示，不超过20个字\n"
    "3. 场景分镜（scenes）：把新闻内容拆成 4-6 个场景，每个场景：\n"
    "   - text：一段口播/字幕文案，信息密度高、节奏紧凑、口语化。总字数约 60-120 字。\n"
    "   - duration：该场景时长（秒），推荐 4-6 秒，总时长控制在 18-24 秒\n"
    "   - transition：该场景进入时的图片切换动画效果，从以下选项中根据内容风格选择：\n"
    "     · fade —— 柔和淡入淡出，适合平缓叙述、过渡性内容\n"
    "     · slide_left —— 从右往左滑入，适合递进、时间线推进的内容\n"
    "     · slide_right —— 从左往右滑入，适合回顾、倒叙内容\n"
    "     · slide_up —— 从下往上滑入，适合揭示、揭秘类内容\n"
    "     · zoom_in —— 从中心放大进入，适合强调、震撼、高潮内容\n"
    "     · none —— 无动画硬切，适合快速切换、对比强烈的场景\n"
    "   第一个场景的 transition 固定为 none。\n\n"
    "请严格只返回如下 JSON 格式，不要添加任何解释或 markdown 标记：\n"
    '{"title": "...", "subtitle": "...", "scenes": [{"text": "...", "duration": 5.0, "transition": "slide_left"}]}'
)

# ─── 可用转场动画列表 ───

AVAILABLE_TRANSITIONS = ["fade", "slide_left", "slide_right", "slide_up", "zoom_in", "none"]

# ─── 转场动画中文说明，用于 LLM 选择 ───

TRANSITION_DESCRIPTIONS = {
    "fade": "柔和淡入淡出，适合平缓叙述、过渡性内容",
    "slide_left": "从右往左滑入，适合递进、时间线推进的内容",
    "slide_right": "从左往右滑入，适合回顾、倒叙内容",
    "slide_up": "从下往上滑入，适合揭示、揭秘类内容",
    "zoom_in": "从中心放大进入，适合强调、震撼、高潮内容",
    "none": "无动画硬切，适合快速切换、对比强烈的场景",
}


# ─── 解析函数 ───

def _strip_markdown_json(text: str) -> str:
    """去除 Markdown 代码块标记，提取纯 JSON 文本。"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行 ```
        if len(lines) > 1:
            lines = lines[1:]
        else:
            lines = []
        # 去掉末行 ```
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _regex_fallback(text: str) -> dict:
    """
    正则兜底：当 JSON 解析失败时，尝试用正则从 LLM 响应中提取字段。
    通用方法，不做关键词硬匹配。
    """
    result = {"title": "", "subtitle": "", "scenes": []}

    # 提取 title
    title_patterns = [
        r'"title"\s*:\s*"([^"]*)"',
        r'"标题"\s*:\s*"([^"]*)"',
        r'["\']title["\']\s*:\s*["\']([^"\']*)["\']',
    ]
    for pat in title_patterns:
        m = re.search(pat, text)
        if m:
            result["title"] = m.group(1).strip()
            break

    # 提取 subtitle
    sub_patterns = [
        r'"subtitle"\s*:\s*"([^"]*)"',
        r'"副标题"\s*:\s*"([^"]*)"',
        r'["\']subtitle["\']\s*:\s*["\']([^"\']*)["\']',
    ]
    for pat in sub_patterns:
        m = re.search(pat, text)
        if m:
            result["subtitle"] = m.group(1).strip()
            break

    # 提取 scenes 数组: 匹配整个 scenes 数组
    scenes_match = re.search(
        r'"scenes"\s*:\s*(\[[^\]]*\])',
        text, re.DOTALL,
    )
    if scenes_match:
        try:
            result["scenes"] = json.loads(scenes_match.group(1))
        except json.JSONDecodeError:
            # 逐场景提取
            scene_blocks = re.finditer(
                r'\{\s*"text"\s*:\s*"([^"]*)"\s*,\s*"duration"\s*:\s*([\d.]+)\s*\}',
                text,
            )
            for match in scene_blocks:
                result["scenes"].append({
                    "text": match.group(1),
                    "duration": float(match.group(2)),
                })

    return result


def parse_news_script(raw_response: str) -> dict:
    """
    解析 LLM 响应为结构化脚本。

    容错策略:
      1. 去除 Markdown 代码块标记
      2. JSON 解析
      3. 正则兜底提取

    返回:
        {"title": str, "subtitle": str, "scenes": [{"text": str, "duration": float}]}
    """
    text = _strip_markdown_json(raw_response)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 JSON 对象边界
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
        "subtitle": str(data.get("subtitle", "")).strip(),
        "scenes": [],
    }

    raw_scenes = data.get("scenes", [])
    if isinstance(raw_scenes, list):
        for i, s in enumerate(raw_scenes):
            if isinstance(s, dict):
                transition = s.get("transition", "none")
                if transition not in AVAILABLE_TRANSITIONS:
                    transition = "none"
                # 第一个场景强制 none
                if i == 0:
                    transition = "none"
                result["scenes"].append({
                    "text": str(s.get("text", "")).strip(),
                    "duration": float(s.get("duration", 5)),
                    "transition": transition,
                })

    # 如果没有有效场景，创建一个默认场景
    if not result["scenes"]:
        result["scenes"] = [{"text": raw_response[:200], "duration": 10}]

    return result


# ─── LLM 调用 ───

def call_llm_parse_news(
    news_content: str,
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int = 8192,
    timeout: int = 120,
) -> dict:
    """
    调用 LLM（Anthropic Messages 协议）解析新闻内容为结构化脚本。

    参数:
        news_content: 新闻原文
        base_url: API base URL
        api_key: API key
        model: 模型名称
        max_tokens: 最大输出 tokens
        timeout: 请求超时（秒）

    返回:
        {"title": str, "subtitle": str, "scenes": [{"text": str, "duration": float}]}
    """
    import httpx

    if not base_url or not api_key or not model:
        raise ValueError("LLM 配置不完整: 需要 base_url, api_key, model")

    # 构建 Anthropic Messages API URL
    if "/v1" not in base_url:
        api_url = f"{base_url.rstrip('/')}/v1/messages"
    else:
        api_url = f"{base_url.rstrip('/')}/messages"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": NEWS_PARSE_SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": news_content},
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

    return parse_news_script(response_text)
