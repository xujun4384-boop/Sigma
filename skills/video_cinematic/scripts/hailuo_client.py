"""
hailuo_client - MiniMax-Hailuo-2.3 视频生成客户端

封装 MiniMax-Hailuo-2.3 文生视频(t2v) API 调用（/v1/video_generation）。
适用于 Token Plan 订阅 Key 或按量计费 API Key；额度按实际生成扣减。
"""
import time
from pathlib import Path
from typing import Optional


class HailuoClient:
    """MiniMax-Hailuo-2.3 视频生成客户端"""

    BASE_URL = "https://api.minimaxi.com"
    MODEL = "MiniMax-Hailuo-2.3"

    def __init__(self, api_key: str, timeout: int = 60):
        """
        初始化客户端。

        参数:
            api_key: MiniMax Token Plan API Key 或按量计费 API Key
            timeout: HTTP 请求超时（秒）
        """
        if not api_key:
            raise ValueError("MiniMax API Key 不能为空")
        self.api_key = api_key
        self.timeout = timeout

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_video_generation(
        self,
        prompt: str,
        duration: int = 6,
        resolution: str = "768P",
        prompt_optimizer: bool = True,
        fast_pretreatment: bool = False,
        callback_url: Optional[str] = None,
        aigc_watermark: bool = False,
    ) -> str:
        """
        创建文生视频任务（t2v）。

        参数:
            prompt: 视频生成提示词（建议英文，支持 [运镜指令] 语法）
            duration: 视频时长（秒），Hailuo-2.3 支持 6 或 10
            resolution: 分辨率，768P 或 1080P（1080P 仅支持 6s）
            prompt_optimizer: 是否自动优化 prompt，默认 true
            fast_pretreatment: 是否缩短 prompt 优化耗时，默认 false
            callback_url: 任务状态变更回调地址（可选）
            aigc_watermark: 是否添加 AIGC 标识水印

        返回:
            task_id: MiniMax 任务 ID
        """
        import httpx

        # 参数校验
        if not prompt or not prompt.strip():
            raise ValueError("prompt 不能为空")
        if duration not in (6, 10):
            raise ValueError(f"Hailuo-2.3 duration 只支持 6 或 10 秒，当前值: {duration}")
        if resolution not in ("768P", "1080P"):
            raise ValueError(f"resolution 必须是 768P 或 1080P，当前值: {resolution}")
        if resolution == "1080P" and duration != 6:
            raise ValueError("1080P 分辨率仅支持 6 秒时长，请调整 duration 或改用 768P")

        payload = {
            "model": self.MODEL,
            "prompt": prompt.strip(),
            "duration": duration,
            "resolution": resolution,
            "prompt_optimizer": prompt_optimizer,
            "fast_pretreatment": fast_pretreatment,
            "aigc_watermark": aigc_watermark,
        }
        if callback_url:
            payload["callback_url"] = callback_url

        url = f"{self.BASE_URL}/v1/video_generation"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"MiniMax API 返回错误 {e.response.status_code}: {e.response.text[:500]}"
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"MiniMax API 请求失败: {e}")

        # 检查业务状态码
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "未知错误")
            raise RuntimeError(f"MiniMax API 业务错误 [{status_code}]: {status_msg}")

        task_id = data.get("task_id")
        if not task_id:
            raise RuntimeError(f"MiniMax API 未返回 task_id: {data}")

        return str(task_id)

    def query_task(self, task_id: str) -> dict:
        """
        查询视频生成任务状态。

        参数:
            task_id: 任务 ID

        返回:
            任务详情 dict，包含 status / file_id / video_width / video_height 等
        """
        import httpx

        url = f"{self.BASE_URL}/v1/query/video_generation"
        params = {"task_id": task_id}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"MiniMax 查询接口返回错误 {e.response.status_code}: {e.response.text[:500]}"
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"MiniMax 查询接口请求失败: {e}")

        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "未知错误")
            raise RuntimeError(f"MiniMax 查询业务错误 [{status_code}]: {status_msg}")

        return data

    def retrieve_file(self, file_id: str) -> str:
        """
        根据 file_id 获取视频下载地址。

        参数:
            file_id: 任务成功时返回的文件 ID

        返回:
            download_url: 视频下载地址（有效期 1 小时）
        """
        import httpx

        url = f"{self.BASE_URL}/v1/files/retrieve"
        params = {"file_id": file_id}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"MiniMax 文件检索返回错误 {e.response.status_code}: {e.response.text[:500]}"
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"MiniMax 文件检索请求失败: {e}")

        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", -1)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "未知错误")
            raise RuntimeError(f"MiniMax 文件检索业务错误 [{status_code}]: {status_msg}")

        file_info = data.get("file", {})
        download_url = file_info.get("download_url")
        if not download_url:
            raise RuntimeError(f"MiniMax 未返回下载地址: {data}")

        return download_url

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 10,
        max_wait: int = 1800,
        progress_callback=None,
    ) -> dict:
        """
        轮询等待任务完成。

        参数:
            task_id: 任务 ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）
            progress_callback: 进度回调函数 fn(status, elapsed)

        返回:
            任务详情 dict（status == "Success"）

        异常:
            RuntimeError: 任务失败
            TimeoutError: 超过最大等待时间
        """
        waited = 0
        while waited < max_wait:
            task = self.query_task(task_id)
            status = task.get("status", "unknown")

            if progress_callback:
                try:
                    progress_callback(status, waited)
                except Exception:
                    pass

            if status == "Success":
                return task
            if status == "Fail":
                raise RuntimeError(f"任务 {task_id} 生成失败")

            time.sleep(poll_interval)
            waited += poll_interval

        raise TimeoutError(f"任务 {task_id} 等待超时（{max_wait}秒）")

    def download_video(self, video_url: str, output_path: str) -> str:
        """
        下载生成的视频到本地。

        参数:
            video_url: MiniMax CDN 视频地址
            output_path: 本地保存路径

        返回:
            本地文件路径
        """
        import httpx

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        try:
            with httpx.Client(timeout=300) as client:
                with client.stream("GET", video_url) as response:
                    response.raise_for_status()
                    with open(out, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=8192):
                            f.write(chunk)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"视频下载失败 {e.response.status_code}: {e.response.text[:500]}"
            )
        except httpx.RequestError as e:
            raise RuntimeError(f"视频下载请求失败: {e}")

        return str(out.resolve())


def generate_cinematic_video(
    prompt: str,
    output_path: str,
    api_key: str,
    duration: int = 6,
    resolution: str = "768P",
    prompt_optimizer: bool = True,
    fast_pretreatment: bool = False,
    poll_interval: int = 10,
    max_wait: int = 1800,
    progress_callback=None,
) -> dict:
    """
    一站式生成电影级视频：提交任务 → 轮询等待 → 下载到本地。

    参数:
        prompt: 视频生成提示词
        output_path: 本地输出路径
        api_key: MiniMax API Key
        duration: 视频时长（秒），6 或 10
        resolution: 分辨率，768P 或 1080P
        prompt_optimizer: 是否自动优化 prompt
        fast_pretreatment: 是否缩短 prompt 优化耗时
        poll_interval: 轮询间隔（秒）
        max_wait: 最大等待时间（秒）
        progress_callback: 进度回调 fn(status, elapsed)

    返回:
        {
            "task_id": str,
            "status": "succeeded",
            "output_path": str,
            "video_url": str,
            "duration": int,
            "resolution": str,
            "video_width": int,
            "video_height": int
        }
    """
    client = HailuoClient(api_key=api_key)

    # 1. 提交任务
    task_id = client.create_video_generation(
        prompt=prompt,
        duration=duration,
        resolution=resolution,
        prompt_optimizer=prompt_optimizer,
        fast_pretreatment=fast_pretreatment,
    )

    if progress_callback:
        try:
            progress_callback("submitted", 0)
        except Exception:
            pass

    # 2. 轮询等待
    task = client.wait_for_completion(
        task_id=task_id,
        poll_interval=poll_interval,
        max_wait=max_wait,
        progress_callback=progress_callback,
    )

    # 3. 获取下载地址
    file_id = task.get("file_id")
    if not file_id:
        raise RuntimeError(f"任务完成但未返回 file_id: {task}")

    video_url = client.retrieve_file(str(file_id))

    # 4. 下载视频
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



