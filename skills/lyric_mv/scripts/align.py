# -*- coding: utf-8 -*-
"""用 ASR + 已知歌词做「强制对齐」，得到字级时间戳。

思路（KTV 的做法）：
  1. whisper 转写整首歌 -> 字/词级时间戳（识别错字没关系）
  2. 把「已知歌词」当作参考序列，把「识别结果」当作假设序列
  3. 用动态规划做单调对齐（Needleman-Wunsch），靠**顺序**把两边对上
     —— 即使识别错了一半的字，只要顺序对，对齐仍然成立
  4. 每个歌词字拿到时间 -> 每行得到起止时间

运行（需要 3.11 解释器，faster-whisper 装在那里）：
    py -3.11 tools/asr_align.py --song song_child.mp3 --lyrics lyrics_child.txt --out timeline_forced.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")

_cc = None


def norm(s: str) -> str:
    """归一化：转简体 + 只留汉字/字母数字。
    whisper 对普通话常输出**繁体**（點/門/還），不转简体会让匹配率白白掉一截。"""
    global _cc
    s = s or ""
    try:
        if _cc is None:
            from opencc import OpenCC
            _cc = OpenCC("t2s")
        s = _cc.convert(s)
    except Exception:
        pass
    return "".join(CJK.findall(s))


def parse_lyrics(path: Path):
    out, cur = [], "Verse"
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            continue
        m = re.fullmatch(r"[\[［](.+?)[\]］]", s)
        if m:
            cur = m.group(1).strip()
            continue
        if cur.lower() == "intro":
            continue
        out.append((cur, s))
    return out


def _whisper_cls():
    """导入 faster-whisper，失败时给出可直接执行的修复命令。
    venv 放在 %TEMP% 会被系统清理工具删掉包里的 .py，报错是
    `cannot import name 'WhisperModel' from 'faster_whisper' (unknown location)`。"""
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except Exception as e:
        raise SystemExit(
            f"ASR 依赖不可用：{e}\n"
            f"修复：\"{sys.executable}\" -m pip install --force-reinstall "
            f"--no-cache-dir faster-whisper==1.2.1"
        )


def transcribe(song: Path, model_size: str):
    WhisperModel = _whisper_cls()
    print(f"加载 whisper-{model_size}（CPU int8）...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print("转写中（这首歌约 3 分钟，CPU 上要几分钟）...")
    segs, info = model.transcribe(str(song), language="zh", word_timestamps=True,
                                 beam_size=5, vad_filter=False,
                                 condition_on_previous_text=False)
    words = []
    for seg in segs:
        for w in (getattr(seg, "words", None) or []):
            t = norm(w.word)
            if t:
                words.append((t, float(w.start), float(w.end)))
    return words


def transcribe_segments(song: Path, model_size: str):
    """返回 ASR 段落列表（含每段的字级时间），供"无歌词"时自动成词。"""
    WhisperModel = _whisper_cls()
    print(f"加载 whisper-{model_size}（CPU int8）...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print("自动转写中（无歌词，用识别结果当歌词）...")
    segs, _ = model.transcribe(str(song), language="zh", word_timestamps=True,
                               beam_size=5, vad_filter=True,
                               condition_on_previous_text=False)
    out = []
    for s in segs:
        ws = []
        for w in (getattr(s, "words", None) or []):
            t = norm(w.word)
            if t:
                ws.append((t, float(w.start), float(w.end)))
        txt = norm(s.text)
        if txt and ws:
            out.append({"text": txt, "start": float(s.start), "end": float(s.end),
                        "words": ws})
    return out


def align(ref, hyp):
    """单调对齐：ref/hyp 都是 (char, start, end) 或 (char,) 的列表。
    返回 ref 每个字命中的 hyp 索引（或 -1）。"""
    n, m = len(ref), len(hyp)
    NEG = -10 ** 9
    # dp[i][j] = 前 i 个 ref 字与前 j 个 hyp 字的最优得分
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - 2
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - 1
    for i in range(1, n + 1):
        ri = ref[i - 1]
        row, prev = dp[i], dp[i - 1]
        for j in range(1, m + 1):
            same = (ri == hyp[j - 1])
            sub = prev[j - 1] + (3 if same else -1)
            dele = prev[j] - 2
            ins = row[j - 1] - 1
            dp[i][j] = max(sub, dele, ins)
    # 回溯
    i, j = n, m
    pairs = {}
    while i > 0 and j > 0:
        ri = ref[i - 1]
        same = (ri == hyp[j - 1])
        sub = dp[i - 1][j - 1] + (3 if same else -1)
        if dp[i][j] == sub:
            pairs[i - 1] = j - 1
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j] - 2:
            i -= 1
        else:
            j -= 1
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", default="song_child.mp3")
    ap.add_argument("--lyrics", default="lyrics_child.txt")
    ap.add_argument("--out", default="timeline_forced.json")
    ap.add_argument("--model", default="small")
    ap.add_argument("--grid", default="", help="可选：拍网格 json，用于把行首吸附到拍点")
    ap.add_argument("--duration", type=float, default=0.0, help="歌曲总时长（秒）")
    ap.add_argument("--t0", type=float, default=None,
                    help="人工锚点：首句起始秒数。ASR 在伴奏压住人声时可能错，"
                         "用耳朵给一个准数，整条时间轴按差值平移（兜底手段）")
    ap.add_argument("--autocaption", action="store_true",
                    help="无歌词模式：自动转写并把识别结果当歌词（用户自带器乐/纯音乐时用）")
    args = ap.parse_args()

    here = Path(__file__).resolve().parents[1]
    song = Path(args.song)
    if not song.is_absolute():
        song = here / song

    # 拍网格：仅用于把行首吸附到拍点（可由实测的 timeline 或 beat.json 提供）
    offset, beat, dur = 0.0, 0.5, 0.0
    if args.grid:
        g = json.loads(Path(args.grid).read_text(encoding="utf-8"))
        offset, beat = g["offset_seconds"], g["beat_seconds"]
        dur = float(g.get("duration") or 0.0)
    if args.duration:
        dur = args.duration

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = here / out_path

    # ── 无歌词模式：自动转写，把识别结果当歌词 ──
    if args.autocaption:
        segs = transcribe_segments(song, args.model)
        print(f"自动转写得到 {len(segs)} 句")
        out_lines = []
        for i, s in enumerate(segs):
            st = round((round((s["start"] - offset) / beat) * beat + offset), 3)
            chars = [[c, round(tm, 3)] for c, tm, _ in s["words"]]
            out_lines.append({"idx": i, "section": "转写", "text": s["text"],
                              "start": st, "end": round(s["end"], 3),
                              "beat": int(round((st - offset) / beat)),
                              "hit_chars": len(chars), "aligned": True, "chars": chars,
                              "autocaption": True})
        tl = {"bpm": round(60.0 / beat, 3), "beat_seconds": beat,
              "offset_seconds": offset, "duration": round(dur, 3),
              "song": song.name, "mode": "autocaption", "lines": out_lines}
        out_path.write_text(json.dumps(tl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n自动成词 {len(out_lines)} 行（注意：词是 ASR 转写，可能有错字）"
              f"\n写入 {out_path}")
        return 0

    lyrics_path = Path(args.lyrics)
    if not lyrics_path.is_absolute():
        lyrics_path = here / lyrics_path
    lines = parse_lyrics(lyrics_path)

    words = transcribe(song, args.model)
    print(f"识别到 {len(words)} 个字/词")
    if words:
        print("识别样本:", "".join(w[0] for w in words[:60]))

    # ref: 歌词所有字（保留 -> (行号, 行内位置) 的映射）
    ref, where = [], []
    for li, (sec, text) in enumerate(lines):
        for ch in norm(text):
            ref.append(ch)
            where.append(li)
    hyp = [w[0] for w in words]

    pairs = align(ref, hyp)
    hit = len(pairs)
    print(f"歌词 {len(ref)} 字，对齐命中 {hit} 字（{hit / max(1, len(ref)):.0%}）")

    # ---- 逐字时间 ----
    # 关键：**行内**插值并夹在本行 [start,end] 内。
    # 若在整首歌的序列上插值，漏字会把隔壁行的时间串过来（实测"我"被插到上一行位置）。
    # 另外**不**把逐字时间吸附到拍点——那会让每个字机械地隔一拍，失去 MTV 的呼吸感。
    line_idx = {}
    for i, li in enumerate(where):
        line_idx.setdefault(li, []).append(i)

    # 每个歌词字的原始（命中）时间；未命中为 None
    ctime = [None] * len(ref)
    for i, j in pairs.items():
        ctime[i] = words[j][1]

    def line_char_times(li, st, en):
        idxs = line_idx.get(li, [])
        raw = [ctime[i] for i in idxs]
        # 行首/行尾补齐
        anchors = [k for k, v in enumerate(raw) if v is not None]
        if not anchors:
            n = max(1, len(idxs))
            return [st + (en - st) * (k / n) for k in range(len(idxs))]
        for k in range(0, anchors[0]):
            raw[k] = raw[anchors[0]]
        for k in range(anchors[-1] + 1, len(raw)):
            raw[k] = raw[anchors[-1]]
        for a in range(len(anchors) - 1):
            p, q = anchors[a], anchors[a + 1]
            if q - p > 1:
                tp, tq = raw[p], raw[q]
                for k in range(p + 1, q):
                    raw[k] = tp + (tq - tp) * (k - p) / (q - p)
        # 夹在本行区间内 + 单调
        out = []
        for k, v in enumerate(raw):
            v = min(max(v, st), max(st, en - 0.06))
            if out and v <= out[-1]:
                v = out[-1] + 0.05
            out.append(v)
        # 单调修正可能把尾部推出上界（密集字群），整体压回区间并保持单调
        hi = max(st, en - 0.06)
        if out and out[-1] > hi:
            lo, span = out[0], out[-1] - out[0]
            if span <= 1e-6:
                out = [st + (hi - st) * (k / max(1, len(out))) for k in range(len(out))]
            else:
                out = [lo + (hi - lo) * ((v - lo) / span) for v in out]
        return [round(v, 3) for v in out]

    # 每行取命中的最早时间作为行首，并统计命中字数
    per_line = {}
    for i, j in pairs.items():
        li = where[i]
        ch, st, en = words[j]
        if li not in per_line:
            per_line[li] = [st, 0]
        else:
            per_line[li][0] = min(per_line[li][0], st)
        per_line[li][1] += 1

    # 起点：对齐上的用最早命中时间；没对齐的在相邻两行之间按行距插值
    starts = {li: v[0] for li, v in per_line.items()}
    key = sorted(starts)
    for li in range(len(lines)):
        if li in starts:
            continue
        prev = max([k for k in key if k < li], default=None)
        nxt = min([k for k in key if k > li], default=None)
        if prev is not None and nxt is not None:
            starts[li] = starts[prev] + (starts[nxt] - starts[prev]) * ((li - prev) / (nxt - prev))
        elif prev is not None:
            starts[li] = starts[prev] + 3.0
        elif nxt is not None:
            starts[li] = max(0.0, starts[nxt] - 3.0)
        else:
            starts[li] = 0.0

    # 起止：起点吸附到拍点；行尾 = 下一行起点（留一点缝），并设上限，
    # 否则个别错配字的远端时间会把一行拉成十几秒。
    MAXDUR = 6.5
    keys = sorted(starts)
    out_lines = []
    for li in keys:
        sec, text = lines[li]
        st = starts[li]
        st = round((st - offset) / beat) * beat + offset
        nxt = next((k for k in keys if k > li), None)
        en = (starts[nxt] - 0.06) if nxt is not None else (st + max(2.0, 0.30 * len(text)))
        en = min(en, st + MAXDUR)
        out_lines.append({
            "idx": li, "section": sec, "text": text,
            "start": round(st, 3), "end": round(max(en, st + 0.8), 3),
            "beat": int(round((st - offset) / beat)),
            "hit_chars": per_line.get(li, [0, 0])[1],
            "aligned": li in per_line,
            # 逐字时间：[字, 起始秒]，保留原始节奏（不吸拍），用于 MTV 跳字
            "chars": [[c, tm] for c, tm in
                      zip([ref[i] for i in line_idx.get(li, [])],
                          line_char_times(li, st, max(en, st + 0.8)))],
        })

    if args.t0 is not None and out_lines:
        delta = args.t0 - out_lines[0]["start"]
        for l in out_lines:
            l["start"] = round(l["start"] + delta, 3)
            l["end"] = round(l["end"] + delta, 3)
            l["chars"] = [[c, round(tm + delta, 3)] for c, tm in l.get("chars", [])]
        print(f"\n人工锚点：首句按 --t0 平移到 {args.t0}s（整条轴平移 {delta:+.3f}s）")

    tl = {"bpm": round(60.0 / beat, 3), "beat_seconds": beat,
          "offset_seconds": offset, "duration": round(dur, 3),
          "song": song.name, "mode": "asr-forced", "lines": out_lines}
    out_path.write_text(json.dumps(tl, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print("\n—— 对齐结果 ——")
    for l in out_lines:
        tag = "✓" if l["aligned"] else "·"
        print(f" {tag}{l['idx']:>2} [{l['section']:>10}] {l['start']:>7.2f}→{l['end']:>7.2f}s "
              f"({l['hit_chars']:>2}字)  {l['text']}")
    na = sum(1 for l in out_lines if not l["aligned"])
    print(f"\n写入 {args.out}｜未对齐行 {na}/{len(out_lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
