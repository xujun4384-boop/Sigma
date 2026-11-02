"""
ark_video_client - 火山方舟（豆包 Seedance）视频生成客户端

封装方舟的视频生成任务接口，与 hailuo_client 保持同构，供
video_cinematic_generate 按用户在 Settings 中选择的服务商切换：
  POST /contents/generations/tasks       创建任务
  GET  /contents/generations/tasks/{id}  查询任务
"""
import time
from pathlib import Path

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedance-1-0-pro-250528"

# Hailuo 的档位 → Seedance 的档位（director 传的是 768P / 1080P，这里只做档位名换算）
_RESOLUTION_MAP = {
    "768P": "720p",
    "720P": "720p",
    "1080P": "1080p",
    "480P": "480p",
}


class ArkVideoClient:
    """火山方舟视频生成客户端（Seedance 系列）"""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL, timeout: int = 60):
        if not api_key:
            raise ValueError("火山方舟 API Key 不能为空")
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_task(self, prompt: str, duration: int = 6, resolution: str = "768P",
                    ratio: str = "16:9", watermark: bool = False,
                    camera_fixed: bool = False) -> str:
        """创建文生视频任务，返回任务 ID。"""
        import httpx

        if not prompt or not prompt.strip():
            raise ValueError("prompt 不能为空")

        payload = {
            "model": self.model,
            "content": [{"type": "text", "text": prompt.strip()}],
            "resolution": _RESOLUTION_MAP.get(str(resolution).upper(), str(resolution).lower()),
            "ratio": ratio,
            "duration": int(duration),
            "camera_fixed": bool(camera_fixed),
            "watermark": bool(watermark),
        }
        url = f"{self.base_url}/contents/generations/tasks"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"火山方舟 API 返回错误 {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            raise RuntimeError(f"火山方舟 API 请求失败: {e}")

        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            raise RuntimeError(f"火山方舟未返回任务 ID: {data}")
        return str(task_id)

    def query_task(self, task_id: str) -> dict:
        """查询任务状态，返回原始 dict（含 status / content）。"""
        import httpx

        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"火山方舟查询接口返回错误 {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            raise RuntimeError(f"火山方舟查询接口请求失败: {e}")

    def wait_for_completion(self, task_id: str, poll_interval: int = 10,
                            max_wait: int = 1800, progress_callback=None) -> dict:
        """轮询直到任务结束；成功返回任务详情，失败/取消抛异常。"""
        waited = 0
        while waited < max_wait:
            task = self.query_task(task_id)
            status = str(task.get("status", "")).lower()
            if progress_callback:
                try:
                    progress_callback(status or "unknown", waited)
                except Exception:
                    pass
            if status in ("succeeded", "success"):
                return task
            if status in ("failed", "cancelled", "canceled", "expired"):
                err = task.get("error") or {}
                raise RuntimeError(
                    f"任务 {task_id} 生成失败（{status}）: {err.get('message') or err or '未知原因'}")
            time.sleep(poll_interval)
            waited += poll_interval
        raise TimeoutError(f"任务 {task_id} 等待超时（{max_wait}秒）")

    def download_video(self, video_url: str, output_path: str) -> str:
        """下载生成的视频到本地。"""
        import httpx

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=300, follow_redirects=True) as client:
                with client.stream("GET", video_url) as resp:
                    resp.raise_for_status()
                    with open(out, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"视频下载失败 {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            raise RuntimeError(f"视频下载请求失败: {e}")
        return str(out.resolve())


def generate_cinematic_video(prompt: str, output_path: str, api_key: str,
                             duration: int = 6, resolution: str = "768P",
                             base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                             poll_interval: int = 10, max_wait: int = 1800,
                             progress_callback=None) -> dict:
    """一站式生成：提交任务 → 轮询 → 下载。返回结构与 hailuo_client 对齐。"""
    client = ArkVideoClient(api_key=api_key, base_url=base_url, model=model)
    task_id = client.create_task(prompt=prompt, duration=duration, resolution=resolution)
    if progress_callback:
        try:
            progress_callback("submitted", 0)
        except Exception:
            pass

    task = client.wait_for_completion(
        task_id=task_id, poll_interval=poll_interval, max_wait=max_wait,
        progress_callback=progress_callback,
    )
    content = task.get("content") or {}
    video_url = content.get("video_url") or task.get("video_url") or ""
    if not video_url:
        raise RuntimeError(f"任务完成但未返回 video_url: {task}")

    local_path = client.download_video(video_url, output_path)
    return {
        "task_id": task_id,
        "status": "succeeded",
        "output_path": local_path,
        "video_url": video_url,
        "duration": duration,
        "resolution": resolution,
        "video_width": task.get("video_width", 0),
        "video_height": task.get("video_height", 0),
    }


__all__ = ["ArkVideoClient", "generate_cinematic_video", "DEFAULT_BASE_URL", "DEFAULT_MODEL"]
