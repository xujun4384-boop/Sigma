"""视觉理解：把屏幕截图交给「主 LLM」识别，返回文字描述。

与 read_image 走同一条「主程序看图」链路（复用主 LLM 的多模态能力），不再依赖
network_bridge 的独立 vision 配置——那条线更慢，且常常没配。
仅在主 LLM 调用失败时，才回退到 network_bridge 的 vision 配置作为兜底。
"""
from __future__ import annotations

from computer_use.manager import computer_use_manager
from skills.image_reader import describe_image_b64


def describe_image(image_b64: str, mime: str, prompt: str, timeout: float = 120.0) -> str:
    """识别屏幕截图，返回文字描述。

    优先使用 Settings 中指定的「读图专用模型」；未配置时用 computer_use 会话同步的主 LLM。
    仅当读图专用模型调用失败时，才回退到 network_bridge 的独立 vision 配置作为兜底。
    """
    cfg = computer_use_manager.get_llm_config() or {}
    try:
        return describe_image_b64(image_b64, mime, prompt, cfg, timeout=timeout)
    except Exception as main_err:
        # 兜底：绕过读图专用模型，改用 network_bridge 配置的视觉模型
        try:
            from network_bridge_manager import bridge_manager

            vcfg = bridge_manager.get_vision_config()
            if vcfg and vcfg.get("apiKey"):
                return describe_image_b64(image_b64, mime, prompt, vcfg,
                                          timeout=timeout, prefer_vision_llm=False)
        except Exception:
            pass
        raise RuntimeError(f"屏幕理解失败（主 LLM）：{main_err}")