"""
文件系统监听器

使用 watchdog 监听工作目录中的文件变化，当 .xlsx/.docx/.md 文件被外部编辑时，
自动生成 diff 并通过回调推送给前端。
"""
import os
import asyncio
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from file_diff_tracker import file_diff_tracker, _diff_has_changes
from sigma_logger import log

# 所有可追踪的文件后缀（变更时弹出标签页）
TRACKABLE_SUFFIXES = {
    # 文档
    ".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".csv",
    # 代码
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".less",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".swift",
    # 数据/配置
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg", ".env", ".properties",
    # 脚本
    ".sql", ".sh", ".bat", ".ps1", ".log",
}
# 支持结构化 diff 的类型
TEXT_DIFFABLE_SUFFIXES = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".scss", ".less",
    ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php", ".swift",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".ini", ".cfg",
    ".sql", ".sh", ".bat", ".ps1", ".log", ".txt", ".csv",
}
DIFFABLE_SUFFIXES = {".xlsx", ".docx", ".md"} | TEXT_DIFFABLE_SUFFIXES
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".sigma", ".sigma2.0"}


class FileWatcher:
    """文件监听器，集成到 asyncio 事件循环中"""

    def __init__(self, watch_dir: str):
        self.watch_dir = Path(watch_dir).resolve()
        self._listeners: list = []  # [(queue, loop)]
        self._observer: Observer | None = None
        self._debounce_lock = threading.Lock()
        # 防抖：mtime -> asyncio task handle
        self._pending: dict[str, asyncio.Task] = {}
        self._debounce_sec = 1.0
        # 初始化快照：扫描所有可追踪文件
        self._scan_and_snapshot()

    # ─── 内部：扫描并初始化快照 ───

    def _scan_and_snapshot(self):
        if not self.watch_dir.exists():
            return
        for fpath in self.watch_dir.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in TRACKABLE_SUFFIXES:
                continue
            if any(d in fpath.parts for d in EXCLUDE_DIRS):
                continue
            try:
                file_diff_tracker.snapshot_file(str(fpath.resolve()))
            except Exception:
                continue

    # ─── 订阅者管理 ───

    def subscribe(self, queue: asyncio.Queue):
        """订阅文件变更事件，返回取消订阅的回调"""
        loop = asyncio.get_running_loop()
        entry = (queue, loop)
        self._listeners.append(entry)
        # 首次订阅时启动 observer
        self._ensure_observer_running()

        def unsubscribe():
            if entry in self._listeners:
                self._listeners.remove(entry)
            if not self._listeners and self._observer:
                self._observer.stop()
                self._observer.join(timeout=3)
                self._observer = None

        return unsubscribe

    def _ensure_observer_running(self):
        if self._observer is not None:
            return
        if not self.watch_dir.exists():
            return
        self._observer = Observer()
        self._observer.schedule(_WatcherHandler(self), str(self.watch_dir), recursive=True)
        self._observer.start()
        log.info(f"[FileWatcher] 已启动: {self.watch_dir}")

    # ─── 文件变更处理 ───

    def on_file_changed(self, file_path: str):
        path_str = str(Path(file_path).resolve())
        suffix = Path(file_path).suffix.lower()
        if suffix not in TRACKABLE_SUFFIXES:
            return
        if any(d in Path(file_path).parts for d in EXCLUDE_DIRS):
            return

        # 防抖：取消之前的定时任务，重新排程
        with self._debounce_lock:
            if path_str in self._pending:
                self._pending[path_str].cancel()
            # 在任意一个订阅者的 event loop 上调度
            if not self._listeners:
                return
            loop = self._listeners[0][1]
            self._pending[path_str] = loop.call_later(
                self._debounce_sec,
                lambda: asyncio.ensure_future(self._check_and_push(path_str), loop=loop),
            )

    async def _check_and_push(self, path_str: str):
        with self._debounce_lock:
            self._pending.pop(path_str, None)
        try:
            suffix = Path(path_str).suffix.lower()
            file_type = {
                ".xlsx": "xlsx", ".docx": "docx", ".pptx": "pptx", ".pdf": "pdf",
                ".md": "markdown", ".py": "python", ".js": "javascript",
                ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
                ".html": "html", ".css": "css", ".json": "json",
                ".yaml": "yaml", ".yml": "yaml", ".xml": "xml",
            }.get(suffix, suffix.lstrip("."))
            file_name = os.path.basename(path_str)

            # 推送修改开始（总是发送，确保前端弹出标签页）
            for queue, loop in self._listeners:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "file_modification_start", "file_path": path_str, "file_name": file_name, "file_type": file_type},
                )

            # 尝试生成结构化 diff（仅支持 .xlsx/.docx/.md）
            if suffix in DIFFABLE_SUFFIXES:
                diff = file_diff_tracker.get_diff(path_str)
                if diff is not None and _diff_has_changes(diff):
                    for queue, loop in self._listeners:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            {"type": "file_diff_update", "file_path": path_str, "file_name": file_name, "file_type": file_type, "diff_data": diff},
                        )

            # 推送修改完成
            for queue, loop in self._listeners:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "file_modification_complete", "file_path": path_str, "file_name": file_name, "file_type": file_type},
                )

            # 更新快照为当前状态
            file_diff_tracker.snapshot_file(path_str)
            log.info(f"[FileWatcher] 文件变更: {file_name} ({file_type})")
        except Exception as e:
            log.warning(f"[FileWatcher] diff 失败: {path_str}, {e}")


class _WatcherHandler(FileSystemEventHandler):
    """watchdog 事件处理器，将文件系统事件转发给 FileWatcher"""

    def __init__(self, watcher: FileWatcher):
        self._watcher = watcher

    def on_modified(self, event):
        if not event.is_directory:
            self._watcher.on_file_changed(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._watcher.on_file_changed(event.src_path)


# ── 全局实例（按 watch_dir 缓存） ──

_watchers: dict[str, FileWatcher] = {}


def get_watcher(watch_dir: str) -> FileWatcher:
    """获取或创建指定目录的 FileWatcher"""
    key = str(Path(watch_dir).resolve())
    if key not in _watchers:
        _watchers[key] = FileWatcher(watch_dir)
    return _watchers[key]
