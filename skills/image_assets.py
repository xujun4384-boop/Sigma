# -*- coding: utf-8 -*-
"""渲染引擎内部按需生图的共享原语。

和「上游先配好图、引擎再引用」不是一回事：这里不做批量配图规划，
只提供引擎在**写画面的同一轮推理里**声明素材之后所需的最小执行能力 ——
把一条画面描述变成一张落在项目 assets/ 下的本地图片。

谁来声明、声明几张、叫什么名字，由各引擎自己决定：
  - opendesign：LLM 在 index.html 里用 data-gen 属性就地声明（图与动效同一次产出）
  - styled    ：LLM 在 scenes.js 里用 MV.assets 声明，draw() 里用 e.drawImg 取用

硬约束：渲染机无外网，所以这里只返回本地路径，绝不返回 URL；
生成失败一律返回 (None, 原因)，不抛异常 —— 引擎按「这张没有」继续渲染。
"""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from sigma_logger import log

# 用途 → 输出尺寸。ARK 要宽×高，MiniMax 要比例串，由 api_size() 按 provider 适配。
ASPECTS = {
    "16:9": (2048, 1152),
    "4:3": (1536, 1152),
    "3:4": (1152, 1536),
    "1:1": (1024, 1024),
    "9:16": (1152, 2048),
    "3:2": (1536, 1024),
    "2:3": (1024, 1536),
}
DEFAULT_ASPECT = "16:9"

# 生图接口没有独立的 negative prompt 参数，负向约束只能写进 prompt 正文。
# 这是全片统一的素材基调：插画/抽象，不出文字，不出可辨识真人。
NEGATIVE = ("no text, no letters, no words, no watermark, no logo, no UI, "
            "no realistic human face, no identifiable real person")

_ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def normalize_aspect(value, default: str = DEFAULT_ASPECT) -> str:
    """把 "16:9" / "16x9" / "2048x1152" / "16*9" 统一成 ASPECTS 里的比例档位。"""
    raw = str(value or "").strip().lower().replace("×", "x").replace("*", "x").replace(" ", "")
    if not raw:
        return default
    if raw in ASPECTS:
        return raw
    if "x" in raw:
        try:
            w, h = (float(x) for x in raw.split("x")[:2])
        except (TypeError, ValueError):
            return default
        if w > 0 and h > 0:
            ratio = w / h
            return min(ASPECTS, key=lambda k: abs(ASPECTS[k][0] / ASPECTS[k][1] - ratio))
    return default


def api_size(aspect, provider: str = "") -> str:
    """按 provider 给出它认识的尺寸参数值。"""
    a = normalize_aspect(aspect)
    if (provider or "").strip().lower() == "minimax":
        return a
    w, h = ASPECTS[a]
    return f"{w}x{h}"


def slug(text, limit: int = 32) -> str:
    """只保留 [a-z0-9-]；中文/空格会被剥掉（file:// 下非 ASCII 文件名有编码风险）。"""
    s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return s[:limit].strip("-")


def asset_filename(hint: str, seed: str, ext: str = ".png") -> str:
    """稳定文件名：hint 提供可读性，seed 的短哈希保证同一描述复用、不同描述不撞名。"""
    digest = hashlib.sha1(str(seed or hint or "").encode("utf-8")).hexdigest()[:8]
    s = slug(hint)
    return f"{s}_{digest}{ext}" if s else f"img_{digest}{ext}"


def safe_name(name: str) -> str:
    """收敛成 assets/ 下的单层文件名：去掉目录、非法字符，缺扩展名补 .png。"""
    base = Path(str(name or "").replace("\\", "/")).name
    base = re.sub(r"\s+", "-", base)
    base = _ILLEGAL.sub("-", base).strip(" .-")
    if not base:
        return ""
    if "." not in base:
        base = base + ".png"
    return base


def build_prompt(prompt: str, style_prefix: str = "") -> str:
    """风格前缀 + 画面描述 + 统一负向约束。风格前缀保证同片多张图是一套的。"""
    body = "; ".join(p.strip().rstrip(".;") for p in (style_prefix, prompt) if p and p.strip())
    return f"{body}. Illustration or abstract artwork, {NEGATIVE}."


def generate(skill_manager, prompt: str, save_dir, filename: str,
             aspect: str = DEFAULT_ASPECT, style_prefix: str = "",
             progress=None) -> tuple[Path | None, str, bool]:
    """生成一张图并落盘为 save_dir/filename。返回 (本地路径, 错误, 是否新生成)。

    同名文件已存在且非空时直接复用 —— 自愈重试会重新扫一遍 HTML，
    同一批图不会重复调用接口。
    """
    dst = Path(save_dir) / safe_name(filename)
    if not dst.name:
        return None, "文件名为空", False
    if dst.is_file() and dst.stat().st_size > 0:
        return dst, "", False
    if skill_manager is None:
        return None, "未注入 skill_manager", False

    provider = getattr(skill_manager, "image_gen_provider", "") or ""
    if progress:
        progress(f"生图 {dst.name}（{normalize_aspect(aspect)}）…")

    # 生图接口有概率性失败（超时/限流/瞬时 5xx），同一 prompt 先静默重试一次；
    # 还失败才把原始报错交给引擎，由它带进 LLM 的修补上下文。
    last_err = "生图失败"
    for attempt in (1, 2):
        try:
            result = skill_manager.dispatch(
                "generate_image",
                prompt=build_prompt(prompt, style_prefix),
                save_dir=str(dst.parent),
                size=api_size(aspect, provider),
                watermark=False,
            )
        except Exception as e:                   # 生图失败不能把整段渲染打崩
            last_err = f"{type(e).__name__}: {e}"
        else:
            if not getattr(result, "success", False):
                last_err = str(getattr(result, "content", "") or "生图失败")
            else:
                produced = str((getattr(result, "details", {}) or {}).get("filepath") or "")
                src = Path(produced)
                if not produced or not src.is_file():
                    last_err = "生图返回的本地路径无效"
                else:
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        if src.resolve() != dst.resolve():
                            if dst.exists():
                                dst.unlink()
                            src.replace(dst)
                    except OSError as e:
                        last_err = f"落盘失败：{e}"
                    else:
                        return dst, "", True
        if attempt == 1:
            if progress:
                progress(f"生图 {dst.name} 失败，重试一次：{last_err[:80]}")
            time.sleep(1.2)

    log.warning(f"[image_assets] 生图失败 {dst.name}: {last_err[:300]}")
    return None, last_err, False
