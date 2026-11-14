"""webpage 技能内部共用：提示词加载、LLM JSON 调用与轻量解析。"""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    """读取 prompts/<name>.md；缺失直接报错，避免静默退化成空提示词。"""
    path = PROMPT_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip()


def extract_json(text: str) -> dict:
    """从模型输出里取出第一个完整 JSON 对象（容忍 ```json 包裹与前后废话）。"""
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end <= start:
        return {}
    chunk = s[start:end + 1]
    for candidate in (chunk, chunk.replace("\n", " ")):
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def call_json(cfg: dict, system: str, context: str, *, max_tokens: int = 6000,
              timeout: int = 150, on_progress=None) -> dict:
    """调用主 LLM 并解析 JSON；解析失败返回空字典，由调用方决定重试。

    思考型模型会先把 token 花在思考上，较小的 max_tokens 很容易被截断
    （stop_reason=length，usage 为空），导致取景失败、整段降级。
    因此解析失败但确有输出时，自动加预算重试一次。
    """
    from skills.opendesign.scripts.renderer import call_llm_text

    start = max(400, int(max_tokens or 0))
    budgets = [start]
    bigger = min(max(start * 4, 6000), 16000)
    if bigger > start:
        budgets.append(bigger)

    for budget in budgets:
        raw = call_llm_text(
            system_prompt=system,
            context=context,
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
            protocol=cfg.get("protocol", "anthropic"),
            max_tokens=budget,
            timeout=timeout,
            attempts=1,
            provider=cfg.get("provider"),
            thinking="disabled",
            on_progress=on_progress,
        )
        data = extract_json(raw)
        if data:
            return data
        # 没有任何输出：说明是硬失败，加预算也没用，直接返回空
        if not str(raw or "").strip():
            return {}
    return {}


def normalized(text: str) -> str:
    """与前端定位脚本一致的空白折叠（仅此一项，不做任何语义改写）。"""
    return " ".join(str(text or "").split())


__all__ = ["load_prompt", "extract_json", "call_json", "normalized"]
