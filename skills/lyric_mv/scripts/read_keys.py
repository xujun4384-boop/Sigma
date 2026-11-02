# -*- coding: utf-8 -*-
"""从 Electron 的 localStorage(leveldb) 里取 Sigma 的 Skill Keys（只报告是否配置，不打印明文）。

用于本地实测：把 key 读进进程内存后直接调用，避免落盘/打印。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEVELDB = ROOT / ".electron-user-data" / "Local Storage" / "leveldb"


def _raw() -> bytes:
    if not LEVELDB.exists():
        return b""
    parts = []
    for f in sorted(LEVELDB.glob("*")):
        if f.suffix in (".log", ".ldb", ".sst"):
            parts.append(f.read_bytes())
    return b"".join(parts)


def _candidates():
    """leveldb 里同一个 key 可能有新旧多份快照，按出现顺序全部产出。"""
    data = _raw()
    for enc in ("utf-16-le", "utf-8"):
        text = data.decode(enc, "ignore")
        idx = text.find("sigma_kimi_config")
        while idx != -1:
            yield text[idx:idx + 60000]
            idx = text.find("sigma_kimi_config", idx + 1)


def load_config() -> dict:
    for chunk in _candidates():
        # value 是 JSON 字符串；用括号配对截出第一个完整对象
        start = chunk.find("{")
        if start == -1:
            continue
        depth, end = 0, -1
        for i, ch in enumerate(chunk[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end == -1:
            continue
        try:
            cfg = json.loads(chunk[start:end])
        except json.JSONDecodeError:
            continue
        if isinstance(cfg, dict) and cfg.get("skillKeys"):
            return cfg
    return {}


if __name__ == "__main__":
    cfg = load_config()
    sk = cfg.get("skillKeys") or {}
    if not sk:
        print("未取到 skillKeys（可能 Sigma 未在此工作目录运行过）")
        sys.exit(1)
    for k in sorted(sk):
        v = str(sk[k])
        low = k.lower()
        if "key" in low or "secret" in low or "token" in low:
            print(f"  {k} = {'SET(len=%d)' % len(v) if v else 'EMPTY'}")
        else:
            print(f"  {k} = {v}")
