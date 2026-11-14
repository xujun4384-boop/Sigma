"""网页取景合成：LLM 写「浏览器 + 标注 + 批注」HTML → 几何闸门 → 交给 HyperFrames 闸门与渲染。"""
from __future__ import annotations

import json
from pathlib import Path

from .common import load_prompt


def composer_system_prompt() -> str:
    """合成契约 + 本地库清单（gsap 等），保证模型只引用项目里真实存在的脚本。"""
    from skills.opendesign.scripts.renderer import _library_text

    prompt = load_prompt("webpage_composer")
    lib = _library_text()
    return prompt + ("\n\n---\n\n" + lib if lib else "")


def compose_context(scene: dict) -> str:
    return (
        "【scene】\n```json\n"
        + json.dumps(scene, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        "按契约输出完整 index.html。只输出 HTML，不要解释。"
    )


def compose_html(cfg: dict, scene: dict, on_progress=None) -> str:
    from skills.opendesign.scripts.renderer import (
        _call_with_token_fallback, call_llm_text,
        LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
    )

    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            system_prompt=composer_system_prompt(),
            context=compose_context(scene),
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
            protocol=cfg.get("protocol", "anthropic"),
            provider=cfg.get("provider"),
            thinking=cfg.get("thinking"),
            max_tokens=budget,
            on_progress=on_progress,
        ),
        max_tokens=LONG_OUTPUT_MAX_TOKENS,
        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    return _strip_fences(raw)


def _strip_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "html":
            s = s[4:]
        s = s.lstrip()
    start = s.lower().find("<!doctype")
    if start > 0:
        s = s[start:]
    return s.strip()


# 运行时几何检查：页面带尺寸正确，标注是它的直接子元素且用页面坐标。
_JS_CHECK_GEOMETRY = r"""
(spec) => {
  const out = [];
  const stage = document.querySelector('#page-stage');
  if (!stage) return ['缺少 #page-stage（页面带容器）'];
  const st = getComputedStyle(stage);
  if (!['relative', 'absolute', 'fixed'].includes(st.position)) {
    out.push('#page-stage 必须是定位元素（position:relative/absolute），否则标注坐标没有参照');
  }
  if (Math.abs(stage.offsetWidth - spec.stage.width) > 2 ||
      Math.abs(stage.offsetHeight - spec.stage.height) > 2) {
    out.push(`#page-stage 尺寸应为 ${spec.stage.width}×${spec.stage.height}，实际 ${stage.offsetWidth}×${stage.offsetHeight}`);
  }
  for (const m of spec.marks) {
    const el = stage.querySelector(`[data-mark="${m.id}"]`);
    if (!el) { out.push(`缺少 data-mark="${m.id}" 的标注元素`); continue; }
    if (el.parentElement !== stage) {
      out.push(`data-mark="${m.id}" 必须是 #page-stage 的直接子元素（要跟着页面一起滚动）`);
      continue;
    }
    const pos = getComputedStyle(el).position;
    if (pos !== 'absolute') {
      out.push(`data-mark="${m.id}" 必须是 position:absolute，实际 ${pos}`);
    }
    const diffs = [];
    const checks = [
      ['left', el.offsetLeft, m.rect[0]],
      ['top', el.offsetTop, m.rect[1]],
      ['width', el.offsetWidth, m.rect[2]],
      ['height', el.offsetHeight, m.rect[3]],
    ];
    for (const [name, got, want] of checks) {
      if (Math.abs(got - want) > 2) diffs.push(`${name} 期望 ${want} 实际 ${got}`);
    }
    if (diffs.length) {
      out.push(`data-mark="${m.id}" 几何不符：${diffs.join('；')}（修法：把它改成 `
        + `style="position:absolute;left:${m.rect[0]}px;top:${m.rect[1]}px;`
        + `width:${m.rect[2]}px;height:${m.rect[3]}px"）`);
    }
  }
  return out;
}
"""


def geometry_issues(project_dir: Path, scene: dict) -> list[str]:
    """用无头浏览器实测标注几何；返回空列表表示通过。"""
    from playwright.sync_api import sync_playwright

    html_path = (project_dir / "index.html").resolve()
    if not html_path.is_file():
        return ["index.html 不存在"]
    canvas = scene.get("canvas") or {}
    page = scene.get("page") or {}
    spec = {
        "stage": {
            "width": int(page.get("width") or 0),
            "height": int(page.get("height") or 0),
        },
        "marks": [
            {"id": m["id"], "rect": m["mark"]["rect"]}
            for m in scene.get("notes") or []
        ],
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page_obj = browser.new_page(
            viewport={
                "width": int(canvas.get("width") or 1920),
                "height": int(canvas.get("height") or 1080),
            }
        )
        try:
            page_obj.goto(html_path.as_uri(), wait_until="load", timeout=30000)
            page_obj.wait_for_timeout(500)
            return page_obj.evaluate(_JS_CHECK_GEOMETRY, spec) or []
        except Exception as e:
            return [f"几何检查执行失败：{e}"]
        finally:
            try:
                browser.close()
            except Exception:
                pass


def asset_issues(project_dir: Path, scene: dict) -> list[str]:
    """确认 HTML 引用的页面带截图真实存在（避免破图被视觉复审误判成设计问题）。"""
    issues = []
    src = (scene.get("page") or {}).get("src")
    if src and not (project_dir / src).is_file():
        issues.append(f"页面截图缺失：{src}")
    return issues


_REPAIR_SYSTEM = """你是 HyperFrames「网页取景」合成的代码修复器。下面给你当前完整的 index.html 与具体错误。
只输出 JSON 修改清单，不要解释、不要 markdown、不要输出整份文件。

### 输出格式（严格）
{"edits":[{"find":"原文中逐字复制的一段唯一代码","replace":"修正后的代码"}]}

### 必须遵守
- 根元素：<div id="root" data-composition-id="root" ...>，CSS 必须有明确宽高与 overflow:hidden。
- 浏览器视口容器（如 #page-viewport）与 #page-stage 都必须 overflow:hidden。
- 时间轴：先 window.__timelines = window.__timelines || {}，再 window.__timelines["root"] = gsap.timeline({paused:true})。
- #page-stage 只放页面带截图；宽高必须等于 page 尺寸，不能被修改；滚动只对它做 translateY。
- 每个 data-mark 必须是 #page-stage 的直接子元素、position:absolute，
  left/top/width/height 必须与下方给出的 mark.rect 逐像素一致（页面坐标）；装饰只能放进它的子元素。
- 禁止 Math.random() / Date.now() / performance.now() / fetch() / repeat:-1 / CSS @keyframes。
- 只用本地 gsap.min.js 与 assets/ 下的截图，不留任何外链。

### 修复规则
1. 最小修改：只改与报错直接相关的标签/样式/脚本，不要重排版面。
2. find 必须从当前文件里逐字复制，且在全文只出现一次；太短容易重复，请带足够上下文。
3. replace 保留原逻辑，只改必要部分；删除时 replace 用空字符串。
4. 最多 8 处编辑；不要输出整份文件。"""


def repair_webpage(current_html: str, errs: list, kind: str, cfg: dict, scene: dict,
                   on_progress=None) -> tuple:
    """网页取景专用的最小 diff 修补（不复用 opendesign 的提示词，避免底部安全区等规则串味）。"""
    from skills.opendesign.scripts.gate import _apply_edits
    from skills.opendesign.scripts.renderer import (
        _call_with_token_fallback, call_llm_text,
        LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    from .common import extract_json

    marks = [
        {
            "id": n["id"],
            "rect": n["mark"]["rect"],
            "lines": n["mark"]["lines"],
            "scroll_y": n.get("scroll_y"),
        }
        for n in scene.get("notes") or []
    ]
    ctx = (
        "【当前 index.html】\n```html\n" + current_html + "\n```\n\n"
        "【本次错误】\n" + "\n".join(f"- {e}" for e in (errs or [])[:6]) + "\n\n"
        "【标注规格（必须逐像素一致）】\n"
        + json.dumps(marks, ensure_ascii=False, indent=2) + "\n\n"
        "只输出 JSON 修改清单。"
    )
    raw = _call_with_token_fallback(
        lambda budget: call_llm_text(
            system_prompt=_REPAIR_SYSTEM,
            context=ctx,
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
            protocol=cfg.get("protocol", "anthropic"),
            provider=cfg.get("provider"),
            thinking="disabled",
            max_tokens=budget,
            on_progress=on_progress,
        ),
        max_tokens=LONG_OUTPUT_MAX_TOKENS,
        fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
    )
    data = extract_json(raw)
    return _apply_edits(current_html, data.get("edits"))


__all__ = ["compose_html", "geometry_issues", "asset_issues", "repair_webpage"]
