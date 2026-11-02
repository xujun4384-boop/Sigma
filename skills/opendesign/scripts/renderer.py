"""opendesign 渲染脚本 - HyperFrames 脚手架 + LLM 写 HTML + npx 渲染

流程：
  1. scaffold_project() 生成 HyperFrames 项目脚手架（meta.json + hyperframes.json）
  2. call_llm_compose() 调 LLM 按 HyperFrames 契约写 index.html
  3. render() 调 npx hyperframes render 输出 mp4
"""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from cancellation import ToolCancelledError, raise_if_cancelled
except Exception:  # 脱离主程序单独运行时（脚本调试），降级为无取消能力
    class ToolCancelledError(Exception):
        pass

    def raise_if_cancelled():
        return None

try:
    from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
except Exception:  # 子进程/脚本调试时项目根可能不在 sys.path，兜底保持同一水位
    LONG_OUTPUT_MAX_TOKENS = 128_000
    LONG_OUTPUT_TOKEN_FALLBACKS = (96_000, 64_000, 32_000)

# 流式接收时进度回调的最小间隔（秒）：既能让前端看到 "还在写"，又不至于刷屏
_PROGRESS_INTERVAL_S = 5.0

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "hyperframes_composer.md"

# 内置的第三方脚本（离线渲染用）：渲染机连不上 CDN 时，用这些本地副本替代外链。
VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"

# 动效原语清单（外置文档）：与提示词正文解耦，改这里不用动提示词。
# 提示词负责"框架契约"，清单负责"能做什么、怎么写"；两者在调用点拼装成系统提示词。
CAPABILITIES_DIR = Path(__file__).resolve().parent.parent / "capabilities"

# 匹配 <script ... src="..."> 的 src 属性值
_SCRIPT_SRC_RE = re.compile(r'(<script\b[^>]*\bsrc\s*=\s*["\'])([^"\']+)(["\'])', re.IGNORECASE)
# 判定"外链"：以 http(s):// 或 // 开头
_EXTERNAL_URL_RE = re.compile(r'^(https?:)?//', re.IGNORECASE)

_HYPERFRAMES_JSON = {
    "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
    "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    "paths": {
        "blocks": "compositions",
        "components": "compositions/components",
        "assets": "assets",
    },
}


def _library_text() -> str:
    """从 vendor/ 实际落盘的脚本导出「本地可用库」清单。

    清单从目录派生而非手写：新增/移除内置脚本时提示词自动跟着变，
    模型也就不会写出"引用一个不存在的外链库"这种必崩的代码。
    """
    if not VENDOR_DIR.exists():
        return ""
    names = sorted(p.name for p in VENDOR_DIR.glob("*.js"))
    if not names:
        return ""
    lines = ["## 本地可用库", "",
             "下面这些脚本已随项目落盘，**用相对路径引本地文件，不要写 CDN 外链**（渲染机可能无外网）：", ""]
    lines += [f'- `{n}` → `<script src="{n}"></script>`' for n in names]
    return "\n".join(lines)


def _capability_text() -> str:
    """动效原语清单正文（capabilities/*.md 按文件名排序拼接：C 开头在前、T 开头在后）。"""
    if not CAPABILITIES_DIR.exists():
        return ""
    chunks = []
    for p in sorted(CAPABILITIES_DIR.glob("*.md")):
        try:
            chunks.append(p.read_text(encoding="utf-8").strip())
        except OSError:
            continue
    return "\n\n---\n\n".join(c for c in chunks if c)


def _load_composer_prompt() -> str:
    """系统提示词 = 框架契约 + 本地库清单 + 动效原语清单。三段各自独立维护。"""
    parts = [PROMPT_PATH.read_text(encoding="utf-8").strip()]
    for extra in (_library_text(), _capability_text()):
        if extra:
            parts.append(extra)
    return "\n\n---\n\n".join(parts) + "\n"


def _copy_vendored(project_dir: Path) -> None:
    """把内置第三方脚本复制进项目目录，供 HTML 以相对路径离线引用（避免依赖 CDN）。"""
    if not VENDOR_DIR.exists():
        return
    for src in VENDOR_DIR.glob("*.js"):
        try:
            shutil.copyfile(src, project_dir / src.name)
        except OSError:
            pass


def localize_scripts(html: str, project_dir: Path) -> str:
    """把 HTML 里指向外部 CDN 的 <script src> 改写为项目内的本地同名文件。

    仅当项目目录里确实存在同名文件时才改写（即"内置脚本已落盘"），
    避免误改其他外链；已是相对/绝对本地路径的引用保持不动。
    """
    def _repl(m: "re.Match") -> str:
        prefix, url, suffix = m.group(1), m.group(2), m.group(3)
        if not _EXTERNAL_URL_RE.match(url):
            return m.group(0)                      # 本地引用，保持原样
        name = url.split("?", 1)[0].split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if name and (project_dir / name).exists():
            return f"{prefix}{name}{suffix}"       # 命中内置副本 → 改本地
        return m.group(0)

    return _SCRIPT_SRC_RE.sub(_repl, html)


def scaffold_project(project_dir: Path, name: str) -> None:
    """生成 HyperFrames 项目脚手架：meta.json + hyperframes.json + 空 index.html"""
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "assets").mkdir(parents=True, exist_ok=True)
    # 内置第三方脚本落盘：让 HTML 可以用 <script src="gsap.min.js"> 离线引用
    _copy_vendored(project_dir)

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


def _apply_thinking(payload: dict, model: str, protocol: str,
                    provider: str = None, thinking: str = None) -> None:
    """按 provider + protocol + thinking 模式注入思考参数。

    统一复用 context_manager 的注册表（与主对话链路同一套规则），**不在调用点写死**：
    某些模型对思考模式有硬性要求（如要求 adaptive、不允许关闭），写死任一取值都会
    在换模型时被服务端以 4xx 拒绝。
    """
    try:
        from context_manager import apply_model_specific_params
    except Exception:
        return
    apply_model_specific_params(payload, model, protocol, {
        "provider": provider or "generic",
        "thinking": thinking or "adaptive",
    })


def _read_stream_text(resp, protocol: str, on_progress=None, on_meta=None) -> str:
    """读取 SSE 流并拼出纯文本；顺带回调进度（已输出字数、已耗时）与元信息。

    只取正文：Anthropic 的 text_delta / OpenAI 的 delta.content；
    思考过程、ping、usage 等事件忽略，但都算"服务端仍在响应"，不会触发停滞超时。

    on_meta 会收到 {stop_reason, usage}：**必须记录下来**，否则"模型正常写完"
    与"撞上 max_tokens 被截断"在调用方看来一模一样（实测踩过：
    kimi-for-coding 的思考 token 也算在 max_tokens 里，思考一长正文就被腰斩）。
    """
    import time

    parts: list[str] = []
    chars = 0
    started = time.monotonic()
    last_report = started
    meta = {"stop_reason": None, "usage": {}}

    for line in resp.iter_lines():
        raise_if_cancelled()
        if not line:
            continue
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        if not data:
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue

        if protocol == "anthropic":
            typ = obj.get("type")
            if typ == "error":
                err = obj.get("error") or {}
                raise RuntimeError(f"LLM 流式返回错误: {err.get('message') or err}")
            if typ == "message_start":
                msg = obj.get("message") or {}
                meta["usage"].update(msg.get("usage") or {})
            elif typ == "message_delta":
                sr = (obj.get("delta") or {}).get("stop_reason")
                if sr:
                    meta["stop_reason"] = sr
                meta["usage"].update(obj.get("usage") or {})
            elif typ == "content_block_delta":
                delta = obj.get("delta") or {}
                if delta.get("type") == "text_delta":
                    piece = delta.get("text") or ""
                    if piece:
                        parts.append(piece)
                        chars += len(piece)
        else:
            if obj.get("usage"):
                meta["usage"].update(obj["usage"])
            for choice in (obj.get("choices") or []):
                fr = (choice or {}).get("finish_reason")
                if fr:
                    meta["stop_reason"] = fr
                delta = (choice or {}).get("delta") or {}
                piece = delta.get("content")
                if piece:
                    parts.append(piece)
                    chars += len(piece)

        now = time.monotonic()
        if on_progress and now - last_report >= _PROGRESS_INTERVAL_S:
            last_report = now
            try:
                on_progress(chars, now - started)
            except Exception:
                pass

    if on_progress:
        try:
            on_progress(chars, time.monotonic() - started)
        except Exception:
            pass
    if on_meta:
        try:
            on_meta(meta)
        except Exception:
            pass
    return "".join(parts)


def call_llm_text(
    system_prompt: str,
    context: str,
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    max_tokens: int = LONG_OUTPUT_MAX_TOKENS,
    timeout: int = 180,
    attempts: int = 2,
    provider: str = None,
    thinking: str = None,
    on_progress=None,
    on_meta=None,
) -> str:
    """通用 LLM 调用：流式接收，返回纯文本，不做格式校验（HTML 生成与 JSON 规划共用）。

    timeout 是「停滞超时」：连续 timeout 秒收不到任何数据才判失败；只要服务端还在持续
    输出（包括思考过程），总生成时长可以超过它。非流式客户端只能拿"总生成时长"当超时，
    正常但较慢的长文会被误杀；反过来为了容错把阈值放大，真卡死时又要干等十几分钟。
    流式还能透出真实进度（on_progress），并让用户取消立即生效。

    provider / thinking 由调用方从各自 LLM 配置透传，思考模式走注册表决定（见 _apply_thinking）。
    """
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
            "stream": True,
        }
        # 思考模式不写死：按调用方透传的 provider/thinking 经注册表注入。
        _apply_thinking(payload, model, protocol, provider, thinking)
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
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    # connect 单独收紧：连不上要立刻失败，而不是等满整个停滞超时
    timeout_cfg = httpx.Timeout(float(timeout), connect=min(10.0, float(timeout)))

    import time

    last_err = None
    text = ""
    meta: dict = {}

    def _keep_meta(m) -> None:
        meta.clear()
        meta.update(m or {})
        if on_meta:
            try:
                on_meta(m)
            except Exception:
                pass

    for attempt in range(1, max(1, attempts) + 1):
        try:
            with httpx.Client(timeout=timeout_cfg) as client:
                with client.stream("POST", api_url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    text = _read_stream_text(resp, protocol, on_progress, _keep_meta)
            last_err = None
            break
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            try:
                detail = e.response.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = str(e)
            last_err = RuntimeError(f"LLM API 错误 {code}: {detail}")
            if 400 <= code < 500:      # 客户端错误（鉴权/参数）不重试
                raise last_err
        except httpx.TimeoutException as e:
            if isinstance(e, httpx.ConnectTimeout):
                last_err = RuntimeError(f"连接 LLM 超时: {e}")
            else:
                last_err = RuntimeError(f"LLM 响应停滞超过 {timeout}s（无新数据），已中断")
        except httpx.RequestError as e:
            last_err = RuntimeError(f"LLM API 请求失败: {e}")
        if attempt < attempts:
            time.sleep(1.5 * attempt)
    if last_err is not None:
        raise last_err

    reason = str(meta.get("stop_reason") or "")
    if not text or not text.strip():
        if reason in ("length", "max_tokens"):
            usage = meta.get("usage") or {}
            raise RuntimeError(
                f"输出被截断：max_tokens={max_tokens} 已耗尽（stop_reason={reason}；usage={usage}）"
            )
        detail = f"（stop_reason={reason}）" if reason else ""
        usage = meta.get("usage") or {}
        if usage:
            detail += f"，usage={usage}"
        raise RuntimeError("LLM 响应中未找到文本内容" + detail)
    if reason in ("length", "max_tokens"):
        raise RuntimeError(
            f"输出被截断：max_tokens={max_tokens} 已耗尽（stop_reason={reason}；"
            f"正文 {len(text)} 字；usage={meta.get('usage') or {}}）"
        )
    return text


def _html_complete(html: str) -> bool:
    """判断 LLM 吐出的 HTML 是否完整、可渲染。

    完整 = 有闭合标签 + 有根合成元素 + 有挂到 window.__timelines 的时间轴注册。
    任一缺失都说明输出被截断（推理型模型偶发命中输出上限），此时不能送渲染。
    """
    low = html.lower()
    return (
        "</html>" in low
        and "</body>" in low
        and "data-composition-id" in low
        and "__timelines" in low
    )


def _max_tokens_rejected(error: Exception) -> bool:
    """仅识别服务端明确拒绝输出预算的错误，避免把其他 4xx 当成可降级。"""
    message = str(error).lower()
    return "max_tokens" in message and any(
        marker in message
        for marker in (
            "too large", "maximum", "max is", "must be less", "exceeds",
            "not supported", "invalid", "must not exceed", "greater than",
        )
    )


def _call_with_token_fallback(call, max_tokens: int, fallbacks: tuple[int, ...]) -> str:
    """预算上限被服务端拒绝时逐档回退；模型实际截断时不降低预算重试。"""
    caps = [max_tokens] + [value for value in fallbacks if value < max_tokens]
    for index, cap in enumerate(caps):
        try:
            return call(cap)
        except RuntimeError as error:
            if not _max_tokens_rejected(error) or index == len(caps) - 1:
                raise
    raise RuntimeError("LLM 输出预算回退失败")


def call_llm_compose(
    context: str,
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "anthropic",
    max_tokens: int = LONG_OUTPUT_MAX_TOKENS,
    timeout: int = 120,
    attempts: int = 2,
    provider: str = None,
    thinking: str = None,
    on_progress=None,
) -> str:
    """调 LLM 按 HyperFrames 契约写 index.html，返回纯 HTML 字符串。

    timeout 为「停滞超时」（秒）：只要模型还在持续输出就不会被打断，真正卡死才快速失败。
    对"输出被截断/无效 HTML"与网络类失败都会重试，最多 attempts 次；每次只发一次请求，
    重试统一在本层控制，避免内外层叠加把等待时间成倍放大。

    完整性校验：输出必须是完整闭合的 HTML；若疑似被截断（缺 </html>/根元素/时间轴），
    自动重写（最多 attempts 次）。仍失败则抛错，交由上层显示为"LLM 编写 HTML 失败"，
    而不是带着残缺 HTML 去渲染、报出"没有注册时间轴"这类误导性错误。
    """
    import time

    system_prompt = _load_composer_prompt()
    last_err: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        ctx = context
        if attempt > 1:
            ctx = (
                context
                + "\n\n⚠️ 上一次输出被截断了（HTML 不完整）。请务必输出**完整闭合**的 HTML："
                "以 </html> 结尾，包含根元素（data-composition-id）与 window.__timelines 注册；"
                "并精简冗余 CSS 以控制长度。"
            )
        try:
            text = _call_with_token_fallback(
                lambda budget: call_llm_text(
                    system_prompt=system_prompt,
                    context=ctx,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    protocol=protocol,
                    max_tokens=budget,
                    timeout=timeout,
                    attempts=1,
                    provider=provider,
                    thinking=thinking,
                    on_progress=on_progress,
                ),
                max_tokens=max_tokens,
                fallbacks=LONG_OUTPUT_TOKEN_FALLBACKS,
            )
        except ToolCancelledError:
            raise
        except Exception as e:
            last_err = e
            if attempt < attempts:
                time.sleep(1.5 * attempt)
            continue
        html = strip_markdown_fences(text)
        if len(html) < 500 or not html.lower().startswith("<!doctype"):
            preview = " ".join(html[:200].split())
            last_err = RuntimeError(f"LLM 输出不是有效 HTML（长度 {len(html)}，开头：{preview}）")
            continue
        if not _html_complete(html):
            last_err = RuntimeError(
                f"LLM 输出的 HTML 不完整（长度 {len(html)}，缺少 </html> / 根元素 / 时间轴），疑似被截断"
            )
            continue
        return html
    raise last_err if last_err is not None else RuntimeError("LLM 未能产出有效 HTML")


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
