# -*- coding: utf-8 -*-
"""生成带人声的歌曲，并检查原始响应里是否含任何时间戳（用于歌词对轴）。

key 只留在进程内存，不打印、不落盘。
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]          # .../skills/lyric_mv/scripts -> 仓库根
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from read_keys import load_config                                  # noqa: E402
from skills.music_generate.scripts import music as M               # noqa: E402

DEFAULT_PROMPT = ("轻快诙谐的中文说唱流行歌，节奏明快、律动稳定、鼓点清晰干脆，"
                  "打工人无奈吐槽的情绪，黑色幽默，男声演唱")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lyrics", default="lyrics.txt")
    ap.add_argument("--out", default="song_raw.mp3")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--check-timing", action="store_true",
                    help="打印原始响应结构，确认有没有时间戳字段")
    args = ap.parse_args()

    cfg = load_config()
    sk = cfg.get("skillKeys") or {}
    key = (sk.get("musicGenApiKey") or "").strip()
    if not key:
        print("FAIL: musicGenApiKey 未配置")
        return 1

    lyrics = (HERE.parent / args.lyrics).read_text(encoding="utf-8").strip()
    prov = M.resolve_provider(sk.get("musicGenProvider", ""))
    model = M.resolve_model(prov, sk.get("musicGenModel", ""))
    endpoint = M.resolve_endpoint(prov, sk.get("musicGenBaseUrl", ""))

    payload = M.build_payload(
        prompt=args.prompt, lyrics=lyrics, instrumental=False, auto_lyrics=False,
        model=model, output_format="url", audio_format="mp3",
        sample_rate=M.DEFAULT_SAMPLE_RATE, bitrate=M.DEFAULT_BITRATE,
    )
    n_lines = len([l for l in lyrics.splitlines() if l.strip() and not l.strip().startswith("[")])
    print(f"请求带人声歌曲（{prov} / {model}）... 歌词 {n_lines} 行")

    data = M._post_json(endpoint, key, payload, 900)

    if args.check_timing:
        def shape(o, d=0):
            if isinstance(o, dict):
                return {k: shape(v, d + 1) for k, v in o.items() if d < 3}
            if isinstance(o, list):
                return [shape(o[0], d + 1)] if o else []
            if isinstance(o, str):
                return f"<str len={len(o)}>" if len(o) > 60 else o
            return o
        print("\n—— 原始响应结构（确认有无时间戳）——")
        print(json.dumps(shape(data), ensure_ascii=False, indent=2))

    blob = M._decode_audio(M._extract_audio(data), 900)
    out = HERE.parent / args.out
    out.write_bytes(blob)

    extra = data.get("extra_info") or {}
    print(f"\nOK  文件={out.name}  大小={len(blob) / 1048576:.2f}MB  "
          f"music_duration={extra.get('music_duration')}ms  "
          f"extra_keys={sorted(extra.keys())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
