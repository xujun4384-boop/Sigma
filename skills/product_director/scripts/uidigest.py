# -*- coding: utf-8 -*-
"""前端 UI 提取器：把真实前端工程抽成"可复现的规格"，供 product_director 作画时照抄。

不是把源码塞进提示词（会淹掉上下文），而是产出三样东西：
  1. `ui-tokens.css`  —— 原样照抄设计变量（颜色/圆角/字体…），画面里必须用 var(--x)
  2. `ui-digest.md`   —— ≤5k 字的规格摘要：配色、字号阶梯、布局骨架、关键组件样式
  3. `assets/`        —— 真实 logo / 图标 / 图片（限量拷贝），画面直接引用，不重画

支持 web 前端（css + tsx/jsx/vue/html）。原生桌面/手机 App 没有前端代码时，只能走截图路线。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", ".next", ".nuxt", "coverage",
              "__pycache__", ".cache", "release", "target"}
_TEXT_EXT = {".css", ".scss", ".less", ".tsx", ".jsx", ".vue", ".html", ".htm"}
_ASSET_EXT = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
_KEY_PROPS = ("display", "position", "width", "height", "background", "background-color", "color",
              "border", "border-radius", "font-size", "font-weight", "padding", "gap",
              "grid-template-columns", "box-shadow", "backdrop-filter", "flex-direction")

_TAG_RE = re.compile(
    r"<(div|aside|main|section|nav|header|footer)\b([^>]*)>|</(div|aside|main|section|nav|header|footer)>",
    re.I)
_CLASS_RE = re.compile(r"className\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|\{`([^`]+)`\}|\{\"([^\"]+)\"\})")


def _iter_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            yield root
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part.lower() in _SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in _TEXT_EXT | _ASSET_EXT:
                yield p


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _parse_vars(css_texts: list[str]) -> dict:
    """只取第一次出现的变量定义：深色主题通常在 :root 里排在前面。"""
    out = {}
    for text in css_texts:
        for name, value in re.findall(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;{}]+);", text):
            out.setdefault(name.strip(), " ".join(value.split()))
    return out


def _parse_rules(css_texts: list[str]) -> dict:
    """朴素规则表：选择器 → 声明字典。只留单一 class 选择器（含 :hover 归并到基类）。"""
    rules = {}
    for text in css_texts:
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text):
            decls = {}
            for item in body.split(";"):
                if ":" not in item:
                    continue
                k, v = item.split(":", 1)
                k, v = k.strip().lower(), v.strip()
                if k and v and not v.startswith("var(--x"):
                    decls[k] = v
            for sel in selector.split(","):
                sel = sel.strip()
                base = re.match(r"^\.([a-zA-Z][\w-]*)(?::{1,2}[\w-]+)?$", sel)
                if not base:
                    continue
                name = "." + base.group(1)
                rules.setdefault(name, {}).update(decls)
    return rules


_STRUCT_TAGS = {"div", "aside", "main", "section", "nav", "header", "footer"}


def _scan_tags(text: str):
    """逐标签扫描 JSX/HTML：忽略引号与 `{}` 里的 `>`，返回 (kind, tag, body, selfclose)。"""
    i, n = 0, len(text)
    while i < n:
        j = text.find("<", i)
        if j < 0:
            return
        if text.startswith("</", j):
            k = text.find(">", j)
            if k < 0:
                return
            yield "close", text[j + 2:k].strip().lower(), "", False
            i = k + 1
            continue
        k, quote, brace = j + 1, "", 0
        while k < n:
            ch = text[k]
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'`":
                quote = ch
            elif ch == "{":
                brace += 1
            elif ch == "}":
                brace = max(0, brace - 1)
            elif ch == ">" and brace == 0:
                break
            k += 1
        body = text[j + 1:k]
        m = re.match(r"\s*([A-Za-z][\w.-]*)", body)
        yield "open", (m.group(1).lower() if m else ""), body, body.rstrip().endswith("/")
        i = k + 1


def _class_of(body: str) -> str:
    m = _CLASS_RE.search(body or "")
    if not m:
        return ""
    raw = next((g for g in m.groups() if g), "")
    raw = re.sub(r"\$\{[^}]*\}", "", raw).strip()
    return raw.split()[0] if raw else ""


def _jsx_skeleton(code_files: list[tuple[Path, str]], rules: dict, max_depth: int = 4) -> list[str]:
    """从组件文件里抽最外层的标签/类名嵌套，作为布局骨架。"""
    if not code_files:
        return []
    src = next(((p, t) for p, t in code_files if p.name.lower() in
                ("app.tsx", "app.jsx", "app.vue", "index.tsx", "index.jsx")), None)
    if src is None:
        src = max(code_files, key=lambda pt: pt[1].count("className"))

    lines, stack = [], []
    for kind, tag, body, selfclose in _scan_tags(src[1]):
        if kind == "close":
            if tag in _STRUCT_TAGS and stack:
                stack.pop()
            continue
        if tag not in _STRUCT_TAGS:
            continue
        name = _class_of(body)
        if len(stack) < max_depth and name:
            props = rules.get("." + name, {})
            extra = "  ".join(f"{k}:{props[k]}" for k in _KEY_PROPS if k in props)[:110]
            lines.append("  " * len(stack) + f"<{tag} class=.{name}>" + (f"   {extra}" if extra else ""))
        if not selfclose:
            stack.append(tag)
    return lines[:24]


def _component_roots(code_files: list[tuple[Path, str]], rules: dict,
                     preferred: set | None = None, limit: int = 10) -> list[str]:
    """每个组件文件的根元素 class + 关键样式：比 tag 树更可靠地说明"这一栏是什么"。"""
    ordered = sorted(code_files, key=lambda pt: 0 if (preferred and pt[0].stem in preferred) else 1)
    out = []
    for p, text in ordered:
        body = re.sub(r"<[^>]*\.map\([^)]*\)[^>]*>", "", text)
        for kind, tag, attrs, selfclose in _scan_tags(body):
            if kind != "open" or tag not in _STRUCT_TAGS:
                continue
            name = _class_of(attrs)
            if not name or len(name) < 3:
                continue
            props = rules.get("." + name)
            if not props:
                continue
            keys = [k for k in _KEY_PROPS if k in props]
            style = "; ".join(f"{k}:{props[k]}" for k in keys)[:140]
            out.append(f"{p.stem} → .{name} {{ {style} }}")
            break
        if len(out) >= limit:
            break
    return out


def _imports(text: str) -> set:
    names = set()
    for m in re.finditer(r"import\s+([A-Z][\w]*)[^\n]*from\s+['\"]([^'\"]+)['\"]", text):
        names.add(m.group(1))
    return names


def _panel_children(app_text: str) -> dict:
    """每个容器 class 里挂的是哪个组件（.panel-left → ChatPanel 这种），这是最容易搞反的信息。"""
    out, stack = {}, []
    if not app_text:
        return out
    for kind, tag, body, selfclose in _scan_tags(app_text):
        raw = re.match(r"\s*([A-Za-z][\w.-]*)", body or "")
        name = raw.group(1) if raw else ""
        if kind == "close":
            if stack:
                stack.pop()
            continue
        if name[:1].isupper():          # 自定义组件
            if stack and stack[-1] and re.search(r"panel|sidebar|workspace", stack[-1]) \
                    and stack[-1] not in out:
                out[stack[-1]] = name
            continue
        if tag not in _STRUCT_TAGS:
            continue
        if not selfclose:
            stack.append(_class_of(body))
    return out


def _shell_order(code_files: list[tuple[Path, str]], rules: dict) -> list[str]:
    """入口文件里 panel-* 容器出现的顺序，就是真实的左右结构。"""
    src = next(((p, t) for p, t in code_files if p.name.lower() in
                ("app.tsx", "app.jsx", "app.vue", "index.tsx", "index.jsx")), None)
    if not src:
        return []
    children = _panel_children(src[1])
    order, seen = [], set()
    for kind, tag, body, _ in _scan_tags(src[1]):
        if kind != "open" or tag not in _STRUCT_TAGS:
            continue
        name = _class_of(body)
        if not name or name in seen or not re.search(r"panel|sidebar|main|layout|workspace", name):
            continue
        seen.add(name)
        props = rules.get("." + name, {})
        keys = [k for k in _KEY_PROPS if k in props]
        style = "; ".join(f"{k}:{props[k]}" for k in keys)[:140]
        inline = re.search(r"style=\{\{([^}]*)\}\}", body)
        if inline:
            style += "  ← 内联: " + " ".join(inline.group(1).split())[:80]
        child = children.get(name)
        order.append(f".{name} {{ {style} }}" + (f"  ← 里面是 {child}" if child else ""))
    return order[:8]


def _pick_tokens(tokens: dict, limit: int = 40) -> dict:
    """优先保留颜色类变量，其余按出现顺序补齐。"""
    colorish = {k: v for k, v in tokens.items()
                if re.search(r"#[0-9a-fA-F]{3,8}|rgba?\(|hsl\(", v)}
    rest = {k: v for k, v in tokens.items() if k not in colorish}
    out = dict(list(colorish.items())[:limit])
    for k, v in list(rest.items())[: max(0, limit - len(out))]:
        out[k] = v
    return out


def _component_table(rules: dict, limit: int = 14) -> list[str]:
    scored = []
    for name, props in rules.items():
        hit = [k for k in _KEY_PROPS if k in props]
        if len(hit) >= 2:
            scored.append((len(hit), name, props))
    scored.sort(key=lambda x: -x[0])
    lines = []
    for _, name, props in scored[:limit]:
        body = "; ".join(f"{k}:{props[k]}" for k in _KEY_PROPS if k in props)
        lines.append(f"{name} {{ {body[:220]} }}")
    return lines


def _scale(rules: dict, prop: str, limit: int = 12) -> list[str]:
    vals = []
    for props in rules.values():
        v = props.get(prop)
        if v and v not in vals:
            vals.append(v)
    return vals[:limit]


def build(roots: list[Path], out_dir: Path, max_files: int = 600,
          max_assets: int = 24, max_asset_bytes: int = 500_000) -> dict:
    """抽取规格并落盘。返回 {digest, tokens_css, assets, files, tokens, components}。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = list(_iter_files(roots))[:max_files]
    css_files = [p for p in files if p.suffix.lower() in {".css", ".scss", ".less"}]
    code_files = [(p, _read(p)) for p in files if p.suffix.lower() in {".tsx", ".jsx", ".vue", ".html", ".htm"}]
    asset_files = [p for p in files if p.suffix.lower() in _ASSET_EXT]

    css_texts = [_read(p) for p in css_files]
    tokens = _pick_tokens(_parse_vars(css_texts))
    rules = _parse_rules(css_texts)
    skeleton = _jsx_skeleton(code_files, rules)
    shell = _shell_order(code_files, rules)
    app_text = next((t for p, t in code_files if p.name.lower() in
                     ("app.tsx", "app.jsx", "app.vue", "index.tsx", "index.jsx")), "")
    comp_roots = _component_roots(code_files, rules, _imports(app_text))

    # 1) 原样 token 表
    token_lines = [":root {"]
    token_lines += [f"  {k}: {v};" for k, v in tokens.items()]
    token_lines.append("}")
    tokens_css = "\n".join(token_lines) + "\n"

    # 2) 真实资源
    assets_dir = out_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir, ignore_errors=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in asset_files[:max_assets]:
        try:
            if p.stat().st_size > max_asset_bytes:
                continue
            dst = assets_dir / p.name
            shutil.copy2(p, dst)
            copied.append(dst.name)
        except OSError:
            continue

    # 3) 规格摘要
    sources = "、".join(f"{p.name}" for p in roots[:4])
    md = [
        "# UI 规格（从真实前端工程抽取，必须照此还原）",
        f"源：{sources}；扫描 {len(files)} 个文件"
        f"（CSS {len(css_files)} / 组件 {len(code_files)} / 资源 {len(asset_files)}）",
        "",
        "## 1. 设计变量（界面颜色/圆角/字号一律用 var(--x)，不要自创品牌色）",
        "```css",
        tokens_css.strip(),
        "```",
        "",
        "## 2. 布局骨架（真实组件的嵌套与栏宽，按这个搭窗口）",
        "### 2.1 容器顺序（从左到右；「里面是 X」就是该栏真正承载的组件）",
        "注意：`← 内联` 表示宽度由运行时 state 决定，还原时取常见值（侧栏 320–380px，中栏自适应）。",
        "```css",
    ]
    md += shell or ["（没有识别到 panel/layout 容器）"]
    md += ["```", "### 2.2 组件根节点样式", "```css"]
    md += comp_roots or ["（没有识别到组件根节点）"]
    md += ["```", "### 2.3 标签嵌套（深度 ≤4）", "```"]
    md += skeleton or ["（没有从组件里抽到带 class 的骨架，参考 2.1/2.2）"]
    md += ["```", "", "## 3. 关键组件样式（可直接照抄）", "```css"]
    md += _component_table(rules) or ["（没有可用的组件规则）"]
    md += ["```", "", "## 4. 字号 / 圆角 / 间距阶梯"]
    md += [
        "- font-size: " + ", ".join(_scale(rules, "font-size")),
        "- border-radius: " + ", ".join(_scale(rules, "border-radius")),
        "- padding: " + ", ".join(_scale(rules, "padding")),
        "- gap: " + ", ".join(_scale(rules, "gap")),
    ]
    if copied:
        md += ["", "## 5. 真实资源（放进 assets/ 直接引用，不要重画）",
               "、".join(copied[:max_assets])]
    digest = "\n".join(md)
    (out_dir / "ui-digest.md").write_text(digest, encoding="utf-8")
    (out_dir / "ui-tokens.css").write_text(tokens_css, encoding="utf-8")

    return {
        "digest": digest,
        "tokens_css": tokens_css,
        "assets_dir": str(assets_dir) if copied else "",
        "assets": copied,
        "files": len(files),
        "tokens": len(tokens),
        "components": len(rules),
        "skeleton": skeleton,
    }


if __name__ == "__main__":  # python uidigest.py <dir> [<dir>…]
    import sys
    src = [Path(p) for p in sys.argv[1:]] or [Path.cwd()]
    info = build(src, Path.cwd() / "ui_digest")
    print(f"files={info['files']} tokens={info['tokens']} components={info['components']}")
    print(info["digest"][:1500])

