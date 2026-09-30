"""
image_to_image skill - AI 图片生成（图生图 / 多图融合）

与 image_generate 共用 image_gen 的 key 通道（ImageGen Provider/BaseURL/Model/API Key）。
底层调用根据 provider 自动适配:
  - ark (火山引擎 Seedream): POST /v1/images/generations，image 字段传 URL 或 Base64 数组
  - minimax: POST /v1/image_generation，使用 subject_reference 字段（仅支持单图，超出自动取首张）

输入图片支持三种形式:
  - 本地文件路径（绝对路径或相对 cwd）
  - http(s) URL（直接透传）
  - data:image/...;base64,...（去掉前缀后作为纯 base64 透传）

不识别的输入会被忽略并提示用户。
"""
from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from sigma_logger import log
from skills.base import BaseTool, ToolParameter, ToolResult

DEFAULT_PROVIDER = "ark"
DEFAULT_MODEL = "doubao-seedream-4-5-251128"
DEFAULT_MINIMAX_MODEL = "image-01"
DEFAULT_SIZE = "2K"
# 参考图压缩到最长边 1024，避免 payload 过大
_REFERENCE_MAX_EDGE = 1024
# 单张参考图压缩质量
_REFERENCE_JPEG_QUALITY = 85
# ARK 多图上限（参考 Seedream 4.5/4.0 文档：最多 14 张）
_ARK_MAX_REFERENCE_IMAGES = 14


class ImageToImageTool(BaseTool):
    name = "generate_image_from_images"
    description = (
        "根据参考图片和文本提示词调用 AI 图生图 / 多图融合服务，生成新图片并保存到本地。"
        "支持单图（图生图）和多图（多图融合、风格迁移、主体一致性等）。"
        "输入图片可以是本地文件路径、http(s) URL 或 data URL/base64。"
        "复用 Settings → Skill Keys → ImageGen 中配置的图片生成通道（火山 ARK 或 MiniMax）。"
    )
    parameters = [
        ToolParameter("prompt", "string", "图片生成提示词，描述想要的画面或对参考图的处理方式"),
        ToolParameter("save_dir", "string", "图片保存目录（LLM 应根据项目目标文件夹自行决定）"),
        ToolParameter(
            "images",
            "array",
            "参考图片列表，每项可以是本地文件路径、http(s) URL 或 data:image/...;base64,...，至少 1 项",
        ),
        ToolParameter(
            "size",
            "string",
            "输出尺寸或比例，默认 2K（MiniMax 仅支持比例，如 1:1、16:9）",
            required=False,
            default=DEFAULT_SIZE,
        ),
        ToolParameter(
            "model",
            "string",
            "模型名称，不填则使用 Settings 中配置的模型",
            required=False,
        ),
        ToolParameter(
            "watermark",
            "boolean",
            "是否添加水印，默认 true",
            required=False,
            default=True,
        ),
        ToolParameter(
            "n",
            "integer",
            "生成图片张数（仅 ARK 适用），默认 1；MiniMax 不支持时静默忽略",
            required=False,
            default=1,
        ),
    ]

    def __init__(self, cwd: str = ".", api_key: str = "", base_url: str = "",
                 default_model: str = "", provider: str = DEFAULT_PROVIDER):
        super().__init__(cwd)
        self.api_key = api_key
        self.provider = (provider or DEFAULT_PROVIDER).strip().lower()
        default_base_url = "https://api.minimaxi.com/v1" if self.provider == "minimax" else "https://ark.cn-beijing.volces.com/api/v3"
        self.base_url = (base_url or default_base_url).rstrip("/")
        self.default_model = (default_model or "").strip() or (
            DEFAULT_MINIMAX_MODEL if self.provider == "minimax" else DEFAULT_MODEL
        )

    def execute(self, prompt: str, save_dir: str, images: list,
                size: str = DEFAULT_SIZE, model: str = None,
                watermark: bool = True, n: int = 1, **kwargs) -> ToolResult:
        if not self.api_key:
            return ToolResult.fail(
                "未配置 ImageGen API Key。请在 Settings → Skill Keys 中配置图片生成 Key。"
            )

        model = (model or "").strip() or self.default_model
        prompt = (prompt or "").strip()
        if not prompt:
            return ToolResult.fail("prompt 不能为空")
        if not images or not isinstance(images, list) or len(images) == 0:
            return ToolResult.fail("images 至少包含 1 个参考图片")

        save_dir = (save_dir or "").strip()
        if not save_dir:
            return ToolResult.fail("save_dir 不能为空，LLM 应根据项目目标文件夹自行决定保存位置")
        save_path = self._resolve_path(save_dir)
        try:
            save_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            import traceback
            log.error(f"[generate_image_from_images] mkdir 失败 | save_dir={save_dir} resolved={save_path} error={e}")
            log.error(traceback.format_exc())
            return ToolResult.fail(f"无法创建保存目录 {save_path}: {e}")

        # 1. 解析参考图为统一 data:image/...;base64,... 列表
        self._emit_progress(f"正在加载 {len(images)} 张参考图...")
        try:
            normalized = self._normalize_references(images)
        except ValueError as e:
            return ToolResult.fail(str(e))
        except Exception as e:
            return ToolResult.fail(f"参考图处理失败: {e}")
        if not normalized:
            return ToolResult.fail("所有参考图都无法识别或加载")

        # 2. 调用图像 API
        self._emit_progress(f"正在调用图生图服务: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
        if self.provider == "minimax":
            try:
                image_bytes, content_type = self._generate_minimax(
                    prompt=prompt,
                    model=model,
                    size=size,
                    watermark=watermark,
                    reference=normalized[0],  # MiniMax 当前仅支持单图
                )
            except Exception as e:
                return ToolResult.fail(f"MiniMax 图生图 API 调用失败: {e}")
        else:
            try:
                image_bytes, content_type = self._generate_ark(
                    prompt=prompt,
                    model=model,
                    size=size,
                    watermark=watermark,
                    references=normalized[:_ARK_MAX_REFERENCE_IMAGES],
                    n=max(1, min(int(n or 1), 4)),
                )
            except Exception as e:
                return ToolResult.fail(f"ARK 图生图 API 调用失败: {e}")

        # 3. 保存图片
        ext = ".png" if "png" in content_type else ".jpg"
        filename = f"image_{uuid.uuid4().hex[:12]}{ext}"
        filepath = save_path / filename
        filepath.write_bytes(image_bytes)

        # 4. 获取尺寸
        img_size = "unknown"
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            img_size = f"{img.width}x{img.height}"
        except Exception:
            pass

        if len(normalized) > 1 and self.provider != "minimax":
            note = f"\n注意：MiniMax 图生图仅支持单张参考图，已自动取首张。"
        else:
            note = ""
        return ToolResult.ok(
            f"图片已生成: {filepath}\n"
            f"尺寸: {img_size}\n格式: {content_type}\n"
            f"参考图: {len(normalized)} 张（provider={self.provider}）{note}",
            filename=filename,
            filepath=str(filepath.resolve()),
            size=img_size,
            mime_type=content_type,
            model=model,
            reference_count=len(normalized),
        )

    # ─── 参考图规范化 ───

    def _normalize_references(self, images: list) -> list[str]:
        """
        把任意形式输入归一化为 data:image/<fmt>;base64,<...> 列表，便于跨 provider 复用。
        同时压缩以减小 payload。
        """
        out: list[str] = []
        skipped: list[str] = []
        for idx, raw in enumerate(images):
            if not isinstance(raw, str):
                skipped.append(f"#{idx + 1}(非字符串)")
                continue
            value = raw.strip()
            if not value:
                skipped.append(f"#{idx + 1}(空)")
                continue

            # data URL
            if value.startswith("data:"):
                # data:image/<fmt>;base64,<...> → 直接使用
                if ";base64," in value:
                    out.append(value)
                    continue
                skipped.append(f"#{idx + 1}(仅 base64 的 data URL 不支持)")
                continue

            # http(s) URL → 直接透传（ARK 支持公网 URL）
            if value.startswith(("http://", "https://")):
                out.append(value)
                continue

            # 本地文件
            local_path = self._resolve_path(value)
            if not local_path.exists():
                skipped.append(f"#{idx + 1}(路径不存在: {value})")
                continue
            try:
                data_url = self._encode_local_to_data_url(local_path)
                out.append(data_url)
            except Exception as e:
                log.warning(f"[generate_image_from_images] 编码本地图片失败 | path={value} error={e}")
                skipped.append(f"#{idx + 1}({os.path.basename(str(local_path))})")
                continue

        if skipped:
            log.warning(f"[generate_image_from_images] 跳过 {len(skipped)} 张不可用参考图: {', '.join(skipped)}")
        return out

    def _encode_local_to_data_url(self, path: Path) -> str:
        from PIL import Image
        suffix = path.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}:
            raise ValueError(f"不支持的图片格式: {suffix}")
        img = Image.open(path)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, "white")
            if img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.getchannel("A"))
                img = background
            else:
                img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # 压缩最长边
        if max(img.width, img.height) > _REFERENCE_MAX_EDGE:
            img.thumbnail((_REFERENCE_MAX_EDGE, _REFERENCE_MAX_EDGE), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_REFERENCE_JPEG_QUALITY, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"

    # ─── Provider 实现 ───

    def _generate_ark(self, prompt: str, model: str, size: str, watermark: bool,
                      references: list[str], n: int) -> tuple[bytes, str]:
        """调用火山引擎 ARK /images/generations（图生图）。"""
        payload = {
            "model": model,
            "prompt": prompt,
            "image": references if len(references) > 1 else references[0],
            "response_format": "url",
            "watermark": bool(watermark),
        }
        if n and n > 1:
            payload["sequential_image_generation"] = "auto"
        # ARK 接受像素串或 1K/2K/4K
        payload["size"] = size or DEFAULT_SIZE

        req = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e

        items = data.get("data") or []
        if not items:
            raise RuntimeError(f"API 响应中没有图片数据: {json.dumps(data)[:500]}")
        first = items[0] or {}
        # 优先 url，fallback b64_json
        url = (first.get("url") or "").strip()
        b64 = first.get("b64_json")
        if not url and not b64:
            raise RuntimeError("API 响应中缺少图片 url 或 b64_json")
        if url:
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": "Sigma/1.0"})
                with urllib.request.urlopen(req2, timeout=60) as resp:
                    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    return resp.read(), content_type
            except Exception as e:
                raise RuntimeError(f"图片下载失败: {e}") from e
        return base64.b64decode(b64), "image/jpeg"

    def _generate_minimax(self, prompt: str, model: str, size: str, watermark: bool,
                          reference: str) -> tuple[bytes, str]:
        """调用 MiniMax /v1/image_generation（图生图）。"""
        # MiniMax 当前仅支持单图，使用 subject_reference
        # reference 可能是 http(s) URL 或 data:image/...;base64,... —— 文档中 image_file 都接受
        payload = {
            "model": model,
            "prompt": prompt,
            "subject_reference": [
                {"type": "character", "image_file": reference}
            ],
            "response_format": "url",
            "n": 1,
        }
        # MiniMax 仅接受比例；size 形如 "1:1"/"16:9"/"2K"
        if size in {"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"}:
            payload["aspect_ratio"] = size
        else:
            payload["aspect_ratio"] = "1:1"
        # watermark 参数：MiniMax 通过 aigc_watermark 控制
        payload["aigc_watermark"] = bool(watermark)

        req = urllib.request.Request(
            f"{self.base_url}/image_generation",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.reason}") from e

        # 与 MiniMax 文生图相同的响应结构
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code") not in (None, 0):
            raise RuntimeError(base_resp.get("status_msg") or str(base_resp))
        image_data = data.get("data") or {}

        # URL 或 base64 两种返回方式都支持
        if isinstance(image_data, dict):
            url = (image_data.get("image_url") or image_data.get("url") or "").strip()
            if url:
                try:
                    req2 = urllib.request.Request(url, headers={"User-Agent": "Sigma/1.0"})
                    with urllib.request.urlopen(req2, timeout=60) as resp:
                        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                        return resp.read(), content_type
                except Exception as e:
                    raise RuntimeError(f"图片下载失败: {e}") from e
            encoded = image_data.get("image_base64")
            if isinstance(encoded, list):
                encoded = encoded[0] if encoded else ""
            if encoded:
                return base64.b64decode(encoded), "image/png"
        raise RuntimeError(f"API 响应中没有图片数据: {json.dumps(data)[:500]}")