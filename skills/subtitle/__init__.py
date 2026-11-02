"""
subtitle skill - 字幕组（按旁白字级时间戳生成"一行一次、底部锚定"的字幕）

从 produce 的字幕逻辑解耦并重做而来。核心目标（针对旧字幕的三个问题）：
  1. 位置：字幕锚定画面底部（ASS Alignment=2 + 按视频高度计算的 MarginV），不再"中间靠下"。
  2. 单行：一条字幕只显示一行（ASS WrapStyle=2 禁止换行）。断行规则=句末标点必断、
     句内标点在整行够长时才断、末尾防孤字；避免出现"1~2 字自成一行"或数量词被拆开。
  3. 同步：每行的起止时间直接取自旁白的字级时间戳（+ 段偏移），与旁白读速一致。

产出：字幕条目 [[text,start,end],...] + 可选写入 .ass / .srt。
其中 **.ass 自带 PlayRes 与完整样式**（底部/字号/描边），合成部门只需直接烧该 .ass，
即可得到正确的底部单行字幕——位置问题在字幕组这一层根治，不依赖合成再传样式。

时间来源：narration 部门输出的 segments（每段含 text/offset/duration/words）。
"""
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult

# 断句标点（按字符类别分类，通用规则、非关键词匹配）：
#   句末标点 = 强边界，遇之必断；句内标点 = 弱边界，整行已够长才断（避免 3~5 字的碎行）
_PUNCT_HARD = set("。！？；…!?;")
_PUNCT_SOFT = set("，、,：:")

_MIN_LINE = 6   # 行长不足此值时，不在"句内标点"处断行（防碎行）
_MIN_TAIL = 3   # 除首行外任何一行不足此值时，从上一行回填（防孤字/寡行）


def _plen(buf: list) -> int:
    """一行的字数（字级 token 的字符数之和）。"""
    return sum(len(str(x.get("word", ""))) for x in buf)


def _chunk_words(words: list, max_chars: int) -> list:
    """把字级 words 切成字幕行。

    规则：①句末标点必断；②句内标点仅在整行已达 _MIN_LINE 时断，否则继续攒到
    max_chars；③收尾补一道"孤字护栏"，把过短的尾部行用上一行的字回填。
    （这样既保留按标点断句的语义，又不会出现"1~2 个字自成一行"或"数量词被拆开"。）
    """
    lines: list = []
    buf: list = []
    n = 0

    def flush():
        nonlocal buf, n
        if buf:
            lines.append(buf)
        buf, n = [], 0

    for w in words:
        t = str(w.get("word", ""))
        if not t:
            continue
        if buf and n + len(t) > max_chars:
            flush()
        buf.append(w); n += len(t)
        if t[-1] in _PUNCT_HARD:
            flush()
        elif t[-1] in _PUNCT_SOFT and n >= _MIN_LINE:
            flush()
    flush()

    # 孤字护栏：从第二行起，任何一行不足 _MIN_TAIL 字，就把上一行末尾的字挪下来补齐
    i = 1
    while i < len(lines):
        while _plen(lines[i]) < _MIN_TAIL and len(lines[i - 1]) > 1:
            lines[i].insert(0, lines[i - 1].pop())
        if not lines[i - 1]:
            lines.pop(i - 1)
            i -= 1
        i += 1
    return lines


def _lines_from_segment(seg: dict, max_chars: int) -> list:
    """把一段旁白转成若干字幕行 [[text,start,end],...]（全局时间轴）。"""
    words = seg.get("words") or []
    offset = float(seg.get("offset", 0) or 0)
    out = []
    if words:
        for buf in _chunk_words(words, max_chars):
            start = offset + float(buf[0].get("startTime", 0.0))
            end = offset + float(buf[-1].get("endTime", 0.0))
            text = "".join(str(w.get("word", "")) for w in buf).strip()
            if text:
                out.append([text, start, end])
    else:
        # 无字级时间戳时的回退：按字数均分段时长
        text = str(seg.get("text", "")).strip()
        dur = float(seg.get("duration", 0) or 0)
        if text and dur > 0:
            chunks = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
            total_len = sum(len(c) for c in chunks) or 1
            t = offset
            for c in chunks:
                d = dur * len(c) / total_len
                out.append([c, t, t + d]); t += d
    return out


def _build_entries(segments: list, max_chars: int, min_duration: float) -> list:
    entries = []
    for seg in segments:
        if isinstance(seg, dict):
            entries.extend(_lines_from_segment(seg, max_chars))
    entries.sort(key=lambda e: e[1])
    # 单行最短停留：不足则顺延结束时间，但不与下一行重叠
    for i, e in enumerate(entries):
        if e[2] - e[1] < min_duration:
            target = e[1] + min_duration
            if i + 1 < len(entries):
                target = min(target, entries[i + 1][1])
            e[2] = max(e[2], target)
    return entries


# ─── 样式 ───

def _ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600); sec -= h * 3600
    m = int(sec // 60); sec -= m * 60
    s = int(sec); cs = int(round((sec - s) * 100))
    if cs == 100:
        s += 1; cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _srt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600); sec -= h * 3600
    m = int(sec // 60); sec -= m * 60
    s = int(sec); ms = int(round((sec - s) * 1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_escape(text: str) -> str:
    # ASS 用 {} 包裹覆盖标签，正文里的花括号需替换，避免被当标签解析
    return text.replace("{", "（").replace("}", "）").replace("\n", " ")


def _write_ass(entries: list, path: Path, width: int, height: int,
               font: str, font_size: int, margin_v: int) -> None:
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 2\n"            # 2 = 不自动换行，保证单行
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,2,1,2,60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for text, start, end in entries:
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{_ass_escape(text)}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def _write_srt(entries: list, path: Path) -> None:
    blocks = []
    for i, (text, start, end) in enumerate(entries, 1):
        blocks.append(f"{i}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")


class SubtitleTool(BaseTool):
    name = "subtitle"
    description = (
        "字幕组：根据旁白的字级时间戳生成字幕条目与字幕文件。特性："
        "①底部锚定（不再中间靠下）；②一次只显示一行（按标点/字数切分，禁止换行）；"
        "③时间轴直接取自旁白字级时间戳，与旁白读速一致。"
        "产出 .ass（自带 PlayRes 与样式，合成直接烧即可）与 .srt。"
        "输入用 narration 部门输出的 segments。"
    )
    parameters = [
        ToolParameter("segments", "array", "旁白分段（narration 的 segments 输出，每段含 text/offset/duration/words）"),
        ToolParameter("output_path", "string", "输出 .ass 路径（同目录同名 .srt 一并产出）；省略则只返回条目", required=False),
        ToolParameter("max_chars", "integer", "单行最大字数，默认 16", required=False, default=16),
        ToolParameter("min_duration", "number", "单行最短停留秒数，默认 0.8", required=False, default=0.8),
        ToolParameter("width", "integer", "视频宽（PlayResX），默认 1920", required=False, default=1920),
        ToolParameter("height", "integer", "视频高（PlayResY），默认 1080", required=False, default=1080),
        ToolParameter("font_size", "integer", "字号(px)，默认按高度 4.8%", required=False),
        ToolParameter("margin_v", "integer", "底部安全距离(px)，默认按高度 6%", required=False),
        ToolParameter("font", "string", "字体名，默认 Microsoft YaHei", required=False, default="Microsoft YaHei"),
    ]

    def __init__(self, cwd: str = ".", **kwargs):
        super().__init__(cwd)

    def execute(self, segments, output_path: str = None, max_chars: int = 16,
                min_duration: float = 0.8, width: int = 1920, height: int = 1080,
                font_size: int = None, margin_v: int = None,
                font: str = "Microsoft YaHei", **kwargs) -> ToolResult:
        if not segments or not isinstance(segments, list):
            return ToolResult.fail("segments 不能为空（应为 narration 的 segments 数组）")
        entries = _build_entries(segments, int(max_chars), float(min_duration))
        if not entries:
            return ToolResult.fail("未生成任何字幕条目（segments 中缺少 words/text）")

        font_size = int(font_size) if font_size else round(height * 0.048)
        margin_v = int(margin_v) if margin_v else round(height * 0.06)

        ass_path = srt_path = ""
        if output_path:
            out = self._resolve_path(output_path)
            ass_path = str(out.with_suffix(".ass"))
            srt_path = str(out.with_suffix(".srt"))
            _write_ass(entries, Path(ass_path), width, height, font, font_size, margin_v)
            _write_srt(entries, Path(srt_path))

        preview = "\n".join(f"  {round(s,2)}-{round(e,2)}  {t}" for t, s, e in entries[:6])
        return ToolResult.ok(
            f"字幕生成完成：{len(entries)} 行（单行/底部锚定）\n{preview}"
            + ("\n..." if len(entries) > 6 else ""),
            entries=entries,
            count=len(entries),
            ass_path=ass_path,
            srt_path=srt_path,
            style={
                "alignment": "bottom-center",
                "font_size": font_size,
                "margin_v": margin_v,
                "wrap": False,
                "font": font,
                "play_res": f"{width}x{height}",
            },
        )


__all__ = ["SubtitleTool"]
