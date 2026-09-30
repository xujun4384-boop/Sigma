"""opendesign 渲染脚本 - HyperFrames 脚手架 + LLM 写 HTML + npx 渲染

流程：
  1. scaffold_project() 生成 HyperFrames 项目脚手架（meta.json + hyperframes.json）
  2. call_llm_compose() 调 LLM 按 HyperFrames 契约写 index.html
  3. render() 调 npx hyperframes render 输出 mp4
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "hyperframes_composer.md"

_HYPERFRAMES_JSON = {
    "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    "paths": {
        "blocks": "compositions",
        "components": "compositions/components",
        "assets": "assets",
    },
}


def _load_composer_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def scaffold_project(project_dir: Path, name: str) -> None:
    """生成 HyperFrames 项目脚手架：meta.json + hyperframes.json + 空 index.html"""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "assets").mkdir(parents=True, exist_ok=True)

    meta = {
        "id": name,
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    (project_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (project_dir / "hyperframes.json").write_text(
        json.dumps(_HYPERFRAMES_JSON, indent=2), encoding="utf-8"
    )
    # 占位 index.html，稍后由 LLM 覆盖
    (project_dir / "index.html").write_text(
        "<!doctype html><html><body></body></html>", encoding="utf-8"
    )


def strip_markdown_fences(text: str) -> str:
    """去除 LLM 可能包裹的 markdown 代码块标记。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1:]
        if stripped.endswith("```"):
            stripped = stripped[:-3].rstrip()
    return stripped.strip()


def call_llm_text(
    system_prompt: str,
    context: str,
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    max_tokens: int = 32768,
    timeout: int = 180,
) -> str:
    """通用 LLM 调用：返回纯文本，不做格式校验（HTML 生成与 JSON 规划共用）。"""
    import httpx

    base_url = (base_url or "").rstrip("/")
    if not base_url or not api_key or not model:
        raise ValueError("LLM 配置不完整：需要 base_url, api_key, model")

    if protocol == "anthropic":
        api_url = f"{base_url}/v1/messages" if "/v1" not in base_url else f"{base_url}/messages"
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": context}],
            # 写 HTML/脚本属确定性生成任务，关闭深度思考。
            # Kimi K3 等思考型模型默认会先产出大量 thinking tokens 再出正文，
            # 非流式请求会因此长时间无响应触发 read timeout。
            "thinking": {"type": "disabled"},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
        }
    else:
        api_url = (
            f"{base_url}/v1/chat/completions"
            if "/v1" not in base_url
            else f"{base_url}/chat/completions"
        )
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"LLM API 错误 {e.response.status_code}: {e.response.text[:500]}")
    except httpx.RequestError as e:
        raise RuntimeError(f"LLM API 请求失败: {e}")

    if protocol == "anthropic":
        content_blocks = data.get("content", [])
        text = "".join(
            b.get("text", "") for b in content_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        choices = data.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""

    if not text or not text.strip():
        raise RuntimeError("LLM 响应中未找到文本内容")
    return text


def call_llm_compose(
    context: str,
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    max_tokens: int = 32768,
    timeout: int = 600,
) -> str:
    """调 LLM 按 HyperFrames 契约写 index.html，返回纯 HTML 字符串。"""
    text = call_llm_text(
        system_prompt=_load_composer_prompt(),
        context=context,
        base_url=base_url,
        api_key=api_key,
        model=model,
        protocol=protocol,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    html = strip_markdown_fences(text)
    if len(html) < 500 or not html.lower().startswith("<!doctype"):
        preview = " ".join(html[:200].split())
        raise RuntimeError(f"LLM 输出不是有效 HTML（长度 {len(html)}，开头：{preview}）")
    return html


def _find_npx() -> str:
    """定位 npx 可执行文件（Windows 上为 npx.cmd）。"""
    for name in ("npx.cmd", "npx", "npx.exe"):
        p = shutil.which(name)
        if p:
            return p
    return "npx"


def render(project_dir: Path, output_path: Path, fps: int = 30, quality: str = "standard") -> str:
    """调 npx hyperframes render 将项目渲染为 mp4。"""
    npx = _find_npx()
    cmd = [
        npx, "--yes", "hyperframes", "render",
        str(project_dir),
        "-o", str(output_path),
        "-f", str(fps),
        "-q", quality,
        "--format", "mp4",
        "--quiet",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"hyperframes render 失败: {detail[:800]}")

    if not output_path.exists():
        raise RuntimeError("render 完成但未找到输出 mp4")

    return str(output_path)
