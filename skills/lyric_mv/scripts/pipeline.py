# -*- coding: utf-8 -*-
"""lyric_mv 流水线：编排 + 闸门 + 断点续做

    音源准备 -> 拍网格 -> 逐字对齐 -> 编导(LLM/plan.json) -> 画面(LLM/scenes.js)
    -> 渲染前闸门 -> 逐帧渲染 -> 出片验收

每段记录「输入签名 + 产物存在 + 验收通过」，三者齐备才跳过。任何一段失败只重跑那一段。
"""
import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = SKILL.parents[1]
ENGINE = SKILL / "engine" / "stage.html"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(ROOT))

import type_styles  # noqa: E402  （文字类 MV 的字效风格库）
import remotion_artist  # noqa: E402  （开放模式：定妆 + 自动分镜）

# 渲染引擎开关：canvas = 旧的逐帧 canvas 引擎；remotion = 共享 Remotion 运行时
TSX_ENGINE = os.environ.get("LYRIC_MV_ENGINE", "canvas").strip().lower() == "remotion"
RUNTIME_RENDER = SKILL.parent / "remotion_runtime" / "scripts" / "render_mv.py"

def _asr_venv_root() -> Path:
    """ASR venv 目录。优先 %LOCALAPPDATA%，不要放 %TEMP%：
    系统清理工具会按 .py 后缀把 %TEMP% 里装的包清成空壳，
    import 时报 `cannot import name 'X' from 'Y' (unknown location)`。
    已经装在 %TEMP% 的继续用，只是不再往那儿新建。"""
    la = os.environ.get("LOCALAPPDATA")
    if la:
        p = Path(la) / "sigma_asr_venv"
        if (p / "Scripts" / "python.exe").exists():
            return p
    tmp = Path(os.environ.get("TEMP", "/tmp")) / "sigma_asr_venv"
    if (tmp / "Scripts" / "python.exe").exists():
        return tmp
    return (Path(la) / "sigma_asr_venv") if la else tmp


VENV_ROOT = _asr_venv_root()
VENV_PY = VENV_ROOT / "Scripts" / "python.exe"
DEFAULT_MODEL = "medium"


def log(m):
    line = f"[{datetime.now():%H:%M:%S}] {m}"
    print(line, flush=True)
    if _LOG_FH:
        _LOG_FH.write(line + "\n")
        _LOG_FH.flush()
        # 任何以 ❌ 开头的消息自动落成结构化错误，供排错时精确定位
        if m.startswith("❌"):
            try:
                (_LOGDIR / "last_error.json").write_text(json.dumps({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "message": m,
                    "log": str(_LOGDIR / "run.log"),
                    "how_to_debug": (
                        "1) 先看本文件 message；2) 到 run.log 搜同一时间戳看上下文"
                        "（每个子进程的完整 stdout/stderr 都在里面）；"
                        "3) 若失败在「编导/画面」段，去 llm/ 目录看模型每一次的原始输出；"
                        "4) 若失败在闸门，run.log 里能看到逐条被拦的原因。"),
                }, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
    return line


_LOG_FH = None
_LOGDIR = Path(".")


def open_log(w: Path):
    """把日志同时写到 <work>/run.log，长跑/子进程输出都能事后回看。"""
    global _LOG_FH, _LOGDIR
    _LOGDIR = Path(w)
    _LOG_FH = open(_LOGDIR / "run.log", "a", encoding="utf-8")
    _LOG_FH.write(f"\n===== 运行开始 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    _LOG_FH.flush()
    # 清掉上一次留下的错误文件：否则重跑时它还挂在那儿，会被误读成"这次又失败了"
    try:
        stale = _LOGDIR / "last_error.json"
        if stale.exists():
            stale.unlink()
    except Exception:
        pass
    return _LOGDIR / "run.log"


def dump(name: str, text: str) -> str:
    """把 LLM 原始输出存档：模型写的代码出问题时，必须能读到它到底写了什么。"""
    if not _LOG_FH:
        return ""
    d = _LOGDIR / "llm"
    d.mkdir(exist_ok=True)
    p = d / f"{name}.txt"
    p.write_text(text or "", encoding="utf-8")
    log(f"  原始输出存档 → llm/{p.name}")
    return str(p)


def sh(cmd, stream=False, **kw):
    """外部命令统一入口。Windows 上命令不存在时 subprocess 抛 FileNotFoundError
    而不是返回非零码——环境自检必须能"报告缺失"，不能自己崩。

    stream=True：子进程每输出一行就实时转发到日志/前端（长任务用，
    否则用户只能对着"逐帧渲染中..."干等十几分钟，完全不知道跑到哪）。"""
    args = [str(c) for c in cmd]
    if not stream:
        try:
            r = subprocess.run(args, capture_output=True, text=True, **kw)
        except FileNotFoundError:
            class R:
                returncode, stdout, stderr = 127, "", f"找不到可执行文件：{cmd[0]}"
            r = R()
        if _LOG_FH:
            _LOG_FH.write(f"\n$ {' '.join(args)}\n[exit={r.returncode}]\n")
            if r.stdout:
                _LOG_FH.write("--- stdout ---\n" + r.stdout[-12000:] + "\n")
            if r.stderr:
                _LOG_FH.write("--- stderr ---\n" + r.stderr[-12000:] + "\n")
            _LOG_FH.flush()
        return r

    buf = []
    # 子进程输出统一按 utf-8 读：否则 Windows 控制台代码页会把中文进度解成乱码
    env = kw.pop("env", None)
    if env is None:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace",
                             bufsize=1, env=env, **kw)
    except FileNotFoundError:
        class R2:
            returncode, stdout, stderr = 127, "", f"找不到可执行文件：{cmd[0]}"
        _LOG_FH and _LOG_FH.write(f"\n$ {' '.join(args)}\n[exit=127] 找不到可执行文件\n")
        _LOG_FH and _LOG_FH.flush()
        return R2()
    except Exception as e:
        # 起不来也要返回一个"失败结果"，不能让整个 pipeline 带着 traceback 死掉
        msg = f"启动失败：{type(e).__name__}: {e}"
        log(f"❌ {msg}")
        class R3:
            returncode, stdout, stderr = 1, "", msg
        return R3()
    assert p.stdout is not None
    read_err = ""
    try:
        for line in p.stdout:
            line = line.rstrip()
            if not line:
                continue
            buf.append(line)
            log(line)                     # 实时上报（前端能立刻看到进度）
    except Exception as e:
        read_err = f"读取子进程输出异常：{type(e).__name__}: {e}"
        log(f"⚠ {read_err}")
    try:
        p.wait(timeout=30)
    except Exception:
        p.kill()
        try:
            p.wait(timeout=10)
        except Exception:
            pass

    class RS:
        pass
    r = RS()
    r.returncode = p.returncode if p.returncode is not None else 1
    r.stdout = "\n".join(buf)
    r.stderr = read_err
    if _LOG_FH:
        _LOG_FH.write(f"\n$ {' '.join(args)}\n[exit={r.returncode}]\n--- streamed ---\n"
                      + "\n".join(buf[-400:]) + ("\n" + read_err if read_err else "") + "\n")
        _LOG_FH.flush()
    return r


def sha(*parts):
    h = hashlib.sha1()
    for p in parts:
        if isinstance(p, Path):
            p = p.read_bytes() if p.exists() else b"<missing>"
        h.update(str(p).encode("utf-8", "ignore"))
    return h.hexdigest()[:12]


# ───────────────────────── 状态 ─────────────────────────

def load_state(w):
    f = w / "mv_state.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            pass
    return {"stages": {}}


def save_state(w, st):
    (w / "mv_state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2),
                                     encoding="utf-8")


def ok_cached(st, name, sig):
    s = st["stages"].get(name)
    return bool(s and s.get("ok") and s.get("sig") == sig
                and all(Path(a).exists() for a in s.get("artifacts", [])))


def mark(st, name, ok, sig, arts, note=""):
    st["stages"][name] = {"ok": ok, "sig": sig, "artifacts": [str(a) for a in arts],
                          "note": note, "at": datetime.now().strftime("%m-%d %H:%M")}


def _stage_reason(st, name, sig, *arts):
    """这一段为什么没命中缓存——「为什么又重跑」不能只能靠猜。"""
    old = (st.get("stages") or {}).get(name)
    if not old or not old.get("ok"):
        return "没有成功记录"
    if old.get("sig") != sig:
        return "输入变了（签名不一致）"
    if any(not Path(a).exists() for a in arts):
        return "产物缺失"
    return "被强制重跑"


# ───────────────────────── 各段 ─────────────────────────

ASR_PKGS = ("faster_whisper", "tqdm", "ctranslate2", "huggingface_hub",
            "tokenizers", "onnxruntime", "av", "numpy")
# faster-whisper 1.2.1 用 av.open(metadata_errors=...) 解码音频；av 19 删掉了这个参数。
# 两个版本必须一起钉住，否则自愈重装会把 av 又升回 19。
ASR_PINS = ("faster-whisper==1.2.1", "av==16.0.1")


def _asr_probe() -> list[str]:
    """ASR venv 是否真的可用。返回不可用的原因列表（空 = 可用）。

    只检查 python.exe 或包目录是不够的，两种坏法都要挡住：
    1) venv 在 %TEMP%，系统清理工具按 .py 后缀删掉纯 Python 文件，只留 .pyd/__pycache__，
       import 时报 `cannot import name 'X' from 'Y' (unknown location)`；
    2) 包都在，但 av 版本和 faster-whisper 的调用签名不兼容（av 19 去掉了 metadata_errors），
       会一直到转写时才炸。这里用一段真实 wav 走一遍 av.open，提前发现。
    """
    if not VENV_PY.exists():
        return list(ASR_PKGS)

    code = (
        "import importlib.util as u, json, os, tempfile, wave\n"
        f"names = {list(ASR_PKGS)!r}\n"
        "bad = []\n"
        "for n in names:\n"
        "    try:\n"
        "        s = u.find_spec(n)\n"
        "        if s is None or s.loader is None:\n"
        "            bad.append(n)\n"
        "    except Exception:\n"
        "        bad.append(n)\n"
        "if not bad:\n"
        "    try:\n"
        "        import av\n"
        "        p = os.path.join(tempfile.gettempdir(), '_asr_probe.wav')\n"
        "        with wave.open(p, 'wb') as f:\n"
        "            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)\n"
        "            f.writeframes(b'\\x00\\x00' * 1600)\n"
        "        with av.open(p, mode='r', metadata_errors='ignore'):\n"
        "            pass\n"
        "        os.remove(p)\n"
        "    except Exception:\n"
        "        bad.append('av:incompatible')\n"
        "print(json.dumps(bad))\n"
    )
    r = sh([str(VENV_PY), "-c", code], timeout=180)
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return list(ASR_PKGS)


def _asr_repair() -> tuple[bool, str]:
    if not VENV_PY.exists():
        log(f"ASR venv 不存在 → 新建到 {VENV_ROOT}")
        r = sh([sys.executable, "-m", "venv", str(VENV_ROOT)], stream=True, timeout=900)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "")[-400:]
    log("ASR 依赖不完整 → 按钉住的版本重装（faster-whisper 1.2.1 + av 16.0.1）…")
    r = sh([str(VENV_PY), "-m", "pip", "install", "--no-cache-dir",
            "-i", "https://pypi.tuna.tsinghua.edu.cn/simple", *ASR_PINS],
           stream=True, timeout=2400)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "")[-400:]
    return True, ""


def st_env(w, st):
    info, bad = [], []
    for name, cmd in (("ffmpeg", ["ffmpeg", "-version"]), ("node", ["node", "-v"])):
        r = sh(cmd)
        (info if r.returncode == 0 else bad).append(name)
    try:
        import playwright  # noqa
        info.append("playwright")
    except Exception:
        bad.append("playwright")

    broken = _asr_probe()
    if broken:
        ok_r, why = _asr_repair()
        broken = _asr_probe()
        if broken:
            log(f"❌ ASR 不可用：{', '.join(broken)}")
            if why:
                log(f"   重装失败：{why.splitlines()[-1][:200] if why.strip() else '未知原因'}")
            log(f"   手动修复：\"{VENV_PY}\" -m pip install --no-cache-dir "
                f"-i https://pypi.tuna.tsinghua.edu.cn/simple {' '.join(ASR_PINS)}")
    has_tl = (w / "timeline.json").exists()
    asr_ok = not broken or has_tl
    (info if asr_ok else bad).append("asr-venv")

    log(f"环境自检 OK: {', '.join(info)}" + (f"｜缺失: {', '.join(bad)}" if bad else ""))
    if not asr_ok:
        return False, ("ASR 依赖缺失：" + ", ".join(broken)
                       + "（逐字对齐无法进行。修好后重跑即可，已完成的音源/拍网格会复用）")
    return ("playwright" not in bad), "; ".join(bad)


def st_audio(w, st, audio, lyrics, synth_prompt, brief):
    """音源准备：接纳用户文件（任意格式→wav）或调用 music_generate 生成歌曲。"""
    dst = w / "song.wav"
    if dst.exists() and ok_cached(st, "audio", sha(Path(audio) if audio else synth_prompt,
                                                   lyrics.read_bytes() if lyrics else "")):
        log("音源复用：song.wav")
        return True, "复用"
    if audio:
        src = Path(audio)
        if not src.exists():
            return False, f"用户指定的音乐不存在：{src}"
        # 用户可能直接把工作目录里的 song.wav 当输入传进来：
        # ffmpeg 不允许输入输出同一个文件，这种情况直接复用。
        try:
            same = src.resolve() == dst.resolve()
        except OSError:
            same = False
        if same:
            log("输入音频就是工作目录的 song.wav，跳过转码")
            return True, f"用户文件 {src.name}"
        r = sh(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn",
                "-ac", "2", "-ar", "44100", dst])
        if r.returncode != 0 or not dst.exists():
            return False, f"音频转码失败（可能是格式不支持）：{r.stderr[-200:]}"
        log(f"接纳用户音乐 {src.name} → song.wav")
        return True, f"用户文件 {src.name}"
    # 生成歌曲
    if not lyrics:
        return False, "既没给 audio 也没给 lyrics，无法生成歌曲"
    r = sh([sys.executable, str(HERE / "gen_music.py"),
            "--lyrics", lyrics, "--out", w / "song.mp3", "--prompt", synth_prompt])
    mp3 = w / "song.mp3"
    if not mp3.exists():
        return False, f"歌曲生成失败：{(r.stdout or r.stderr)[-300:]}"
    sh(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-vn", "-ac", "2", "-ar", "44100", dst])
    log(f"生成歌曲完成：{dst.stat().st_size / 1048576:.2f} MB")
    return True, "技能生成"


def st_grid(w, st, song):
    g = w / "grid.json"
    sig = sha(song)
    if ok_cached(st, "grid", sig):
        log("拍网格复用")
        return True, "复用"
    import beat as B
    x = B.decode(song)
    env = B.onset_envelope(x)
    bpm, phase, _ = B.coarse_grid(env)
    bpm, phase = B.fine_grid(env, bpm, phase)
    beat = 60.0 / bpm
    offset = B.refine_phase(env, B.ENV_FPS * 60.0 / bpm, phase) / B.ENV_FPS
    dur = len(x) / B.SR
    g.write_text(json.dumps({"bpm": round(bpm, 3), "beat_seconds": round(beat, 6),
                             "offset_seconds": round(offset, 6),
                             "duration": round(dur, 3)}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    log(f"拍网格：BPM {bpm:.2f}｜每拍 {beat:.4f}s｜相位 {offset:.3f}s｜时长 {dur:.2f}s")
    return True, f"BPM {bpm:.1f}"


def st_align(w, st, song, lyrics, grid, t0, model, autocaption=False):
    """逐字对齐。有歌词 → 歌词先验强制对齐；无歌词 → 自动转写当歌词。"""
    tl_path = w / "timeline.json"
    sig = sha(song, lyrics.read_bytes() if lyrics else "", str(t0), model, str(autocaption))
    if ok_cached(st, "align", sig):
        tl = json.loads(tl_path.read_text(encoding="utf-8"))
        log(f"时间轴复用：{len(tl['lines'])} 行")
        return True, f"{len(tl['lines'])} 行", tl
    if not VENV_PY.exists():
        return False, f"ASR venv 缺失：{VENV_PY}", None
    env = dict(os.environ, HF_ENDPOINT="https://hf-mirror.com",
               HF_HUB_DISABLE_XET="1", HF_HUB_DISABLE_SYMLINKS_WARNING="1")
    cmd = [VENV_PY, str(HERE / "align.py"), "--song", song,
           "--out", tl_path, "--model", model, "--grid", grid]
    if lyrics:
        cmd += ["--lyrics", lyrics]
    else:
        cmd += ["--autocaption"]
    if t0 is not None:
        cmd += ["--t0", str(t0)]
    log(f"ASR 对齐（whisper-{model}，CPU）...")
    r = sh(cmd, env=env)
    for ln in (r.stdout or "")[-1200:].splitlines():
        if any(k in ln for k in ("命中", "未对齐", "写入", "识别到", "自动转写")):
            log("  " + ln.strip())
    if not tl_path.exists():
        return False, (r.stderr or r.stdout)[-400:], None
    tl = json.loads(tl_path.read_text(encoding="utf-8"))
    n = len(tl["lines"])
    miss = sum(1 for L in tl["lines"] for c in (L.get("chars") or [])
               if not (L["start"] - 1e-6 <= c[1] <= L["end"] + 1e-6))
    una = sum(1 for L in tl["lines"] if not L.get("aligned", True))
    log(f"时间轴：{n} 行｜未对齐 {una}｜首句 {tl['lines'][0]['start'] if n else '-'}s｜逐字越界 {miss}")
    if miss:
        return False, f"{miss} 个逐字时间越出本行区间（删 timeline.json 重算）", None
    if n and una > max(2, n * 0.1):
        return False, f"未对齐行过多 {una}/{n}：换更大模型或给 --t0", None
    return True, f"{n} 行", tl


# ───────────────────── 编导 / 画面（LLM） ─────────────────────

LYRIC_STYLES = ["band", "shrink", "bounce", "vertical", "bottom", "walk", "brush"]

# ───────────────────── 模式判断（叙事 / 表演 / 文字） ─────────────────────

MODES = ["narrative", "performance", "typographic"]
MODE_LABELS = {"narrative": "叙事型", "performance": "表演型", "typographic": "文字类"}
MODE_ASK_THRESHOLD = float(os.environ.get("LYRIC_MV_MODE_THRESHOLD", "0.7"))

MODE_SCENE_RULES = {
    "performance": (
        "本片是**表演型**：整片发生在同一个舞台/主场景里。\n"
        "- 每句画面都必须沿用视觉圣经里的固定舞台、固定背景、固定光位和同一个表演者/主体；\n"
        "- 只允许机位、景别、灯光、道具和动作变化，禁止换场景、换主体、换服装、换画风；\n"
        "- 歌词是表演者正在唱的内容，不是分镜脚本：不要为贴合某一句歌词换一个完全不同的世界；\n"
        "- 相邻句的变化要有连续性（同一空间里的移动/推拉/光影变化），不要每句重新起构图。"
    ),
    "narrative": (
        "本片是**叙事型**：画面服务故事节拍，歌词是画外音。\n"
        "- 不要逐句解释歌词；镜头可以覆盖多句，按故事推进切；\n"
        "- 同一角色/场景/服装必须跨镜头保持一致。"
    ),
    "typographic": (
        "本片是**文字类**：文字就是画面主体，没有独立字幕层。\n"
        "- 用歌词的逐字时间驱动排版与字效，不要画与文字无关的插画主体；\n"
        "- 文字必须清晰可读，并避开底部/边缘安全区。"
    ),
}

_MODE_SYS = """你是 MV 导演。先判断这首歌应该做成哪一种 MV，只输出 JSON。

三种模式：
- narrative（叙事型）：整片讲一个完整故事，故事由你和用户一起拟定，不被歌词逐句约束；
  歌词层照常显示。适合有明确主题/时代/人物关系的歌（主旋律、古风叙事、人生故事等）。
- performance（表演型）：没有完整故事，靠舞台、表演者、情绪与段落推进；歌词层照常显示。
  适合态度表达、吐槽、乐队/舞台感、群像。
- typographic（文字类）：文字本身就是画面主体，按拍与逐字时间做排版和字效；
  没有独立字幕层。适合节奏强、短句多、口号/说唱/青春摇滚。

判断依据：歌词的叙事密度与意象、brief 的意图、BPM 与段落结构、歌曲时长。
不要按关键词机械判断，要看整首歌的表达方式。

只输出：
{
 "mode": "narrative|performance|typographic",
 "confidence": 0.0,
 "reason": "一句话说明为什么",
 "alternatives": [{"mode": "...", "why": "..."}],
 "ask_user": false,
 "conflict": false
}

规则：
1. 没有歌词时不能选 typographic。
2. 两种模式都说得通、或 brief 与歌词指向不同模式时，conflict=true 且 ask_user=true。
3. confidence < 0.7 时 ask_user=true。
4. 只输出 JSON。
"""


def _mode_signals(tl, bpm):
    sections = []
    for L in tl.get("lines") or []:
        name = str(L.get("section") or "").strip()
        if name and name not in sections:
            sections.append(name)
    return {
        "bpm": bpm,
        "duration": tl.get("duration"),
        "section_count": len(sections),
        "sections": sections,
    }


def st_mode(w, st, tl, brief, cfg, lyrics_text="", bpm=None,
            forced_mode="", force=False):
    """判断 MV 模式，写 mode.json。

    forced_mode 非空时按用户指定，不再调用 LLM；否则由 LLM 综合歌词/brief/BPM 判断。
    ask_user=true 时由主流程打印 MODE_CHOICES 并停下，等用户选完带 --mode 重跑。
    """
    sig = sha(lyrics_text or "", brief or "", str(bpm), str(tl.get("duration")),
              ",".join(_mode_signals(tl, bpm)["sections"]))
    p = w / "mode.json"
    if p.exists() and not force and not forced_mode:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        if old.get("sig") == sig and old.get("mode") in MODES:
            log(f"模式复用：{MODE_LABELS.get(old['mode'])}（{old.get('reason') or ''}）")
            return True, "复用", old

    sig_info = _mode_signals(tl, bpm)
    signals = dict(sig_info, lyrics_present=bool((lyrics_text or "").strip()),
                   brief=str(brief or "")[:200])

    if forced_mode:
        if forced_mode not in MODES:
            return False, f"未知模式 {forced_mode!r}，可选 {' / '.join(MODES)}", None
        if forced_mode == "typographic" and not (lyrics_text or "").strip():
            return False, "文字类模式需要歌词；当前没有歌词", None
        doc = {
            "version": 1, "mode": forced_mode, "confidence": 1.0,
            "reason": "用户指定", "alternatives": [], "ask_user": False,
            "conflict": False, "decided_by": "user", "sig": sig, "signals": signals,
            # 歌词层：叙事/表演都保留完整歌词层；文字类由画面自己写字，没有独立字幕层
            "lyrics_layer": "none" if forced_mode == "typographic" else "full",
        }
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"模式（用户指定）：{MODE_LABELS[forced_mode]}")
        return True, "用户指定", doc

    ctx = (
        f"歌曲：时长 {tl.get('duration')}s，BPM {bpm}，"
        f"段落 {sig_info['sections'] or '未标注'}，共 {len(tl.get('lines') or [])} 行歌词。\n\n"
        f"用户要求（优先级最高）：\n{brief or '（无额外要求）'}\n\n"
    )
    if (lyrics_text or "").strip():
        ctx += "歌词（用于判断表达方式，不需要逐句分析）：\n" + lyrics_text[:4000]
    else:
        ctx += "本片没有歌词（纯器乐）：不能选 typographic。\n"

    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"mode-prompt-{k}", c2)
            raw = _llm(_MODE_SYS, c2, cfg, meta_label=f"mode-{k}")
            dump(f"mode-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"模式判断 第{k}次 ✗ {errs[0]}")
            continue

        errs = []
        mode = str(doc.get("mode") or "").strip()
        if mode not in MODES:
            errs.append(f"mode 必须是 {' / '.join(MODES)} 之一，收到 {mode!r}")
        if mode == "typographic" and not (lyrics_text or "").strip():
            errs.append("没有歌词，不能选 typographic")
        try:
            conf = float(doc.get("confidence"))
        except (TypeError, ValueError):
            conf = 0.0
            errs.append("confidence 必须是 0~1 的数字")
        if not str(doc.get("reason") or "").strip():
            errs.append("缺 reason")
        alts = []
        for a in (doc.get("alternatives") or []):
            if not isinstance(a, dict):
                continue
            am = str(a.get("mode") or "").strip()
            if am in MODES and am != mode and all(x["mode"] != am for x in alts):
                alts.append({"mode": am, "why": str(a.get("why") or "")[:120]})
        if errs:
            log(f"模式判断 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        ask = bool(doc.get("ask_user") or doc.get("conflict") or conf < MODE_ASK_THRESHOLD)
        out = {
            "version": 1, "mode": mode, "confidence": round(conf, 2),
            "reason": str(doc.get("reason") or "")[:300],
            "alternatives": alts[:2], "ask_user": ask,
            "conflict": bool(doc.get("conflict")),
            "decided_by": "auto", "sig": sig, "signals": signals,
            # 歌词层：叙事/表演都保留完整歌词层；文字类没有独立字幕层
            "lyrics_layer": "none" if mode == "typographic" else "full",
        }
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"模式判断：{MODE_LABELS[mode]}（置信度 {out['confidence']}）"
            f"｜{out['reason']}" + ("｜需要用户确认" if ask else ""))
        return True, "自动", out

    # 判断连续失败：按当前行为（表演型）继续，不拦片
    out = {
        "version": 1, "mode": "performance", "confidence": 0.0,
        "reason": "模式判断失败，按表演型继续", "alternatives": [],
        "ask_user": False, "conflict": False, "decided_by": "auto",
        "sig": sig, "signals": signals, "lyrics_layer": "full",
    }
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log("⚠ 模式判断失败，按表演型继续")
    return True, "回退", out



# ───────────────────── 文字类：字效方案 ─────────────────────

TYPE_PLAN_VERSION = 1

_TYPE_PLAN_SYS = """你是 MV 字体设计师。整片是**文字类 MV**：文字就是画面主体，没有独立字幕层。
读歌词、编导方案与用户要求，选一种字效风格，并定下全片排版系统。只输出 JSON。

候选字效风格：
{TYPE_MENU}

输出：
{
 "typeStyle": "brutalist",
 "typography": {"weight": 900, "tracking": -0.02, "leading": 0.92, "align": "left"},
 "palette": {"bg": "#111111", "fg": "#F4EFE4", "accent": "#E9A63B"},
 "sections": [{"name": "Verse 1", "energy": "low|mid|high", "layout": "这一段的排版", "emphasis": "重点词怎么处理"}],
 "rules": ["全片都要遵守的排版/运动规则"]
}

规则：
1. typeStyle 必须是候选之一；字体由风格库决定，不要自己指定字体文件。
2. sections 必须覆盖编导方案里的每个段落，顺序一致。
3. 配色必须保证文字高对比；不要依赖渐变。
4. 运动按拍，但禁止整帧亮度脉动。
5. 只输出 JSON。
"""


def _type_sections(plan):
    return [str(s.get("name") or "").strip() for s in (plan.get("sections") or [])
            if str(s.get("name") or "").strip()]


# ── 逐句重点标注：让每句有主次，而不是整句同一个字号 ──
# 只由 LLM 按语义挑片段；这里不做任何关键词表或词频打分。

TYPE_EMPHASIS_VERSION = 1

_TYPE_EMPHASIS_SYS = """你是文字类 MV 的重点标注师。整片文字就是画面主体，没有独立字幕层。
任务：逐句挑出**值得放大的连续片段**，让排版有主次，而不是整句一样大。
输出 JSON：
{
 "lines": [{"idx": 12, "picks": ["好不好"], "why": "反问落点"}],
 "summary": "一句话说明全片重点策略"
}

规则：
1. picks 必须逐字出现在该行 text 里，是**连续子串**，原样复制；不许改写、不许跨行。
2. 每行 0~2 个片段，每个 1~8 字；不要标整行，不要标标点。
3. 判断依据是语义重心：转折、结论、反问、称呼、动作结果、具体物象、情绪落点。
   不要按词性机械挑，也不要每行都挑开头第一个词。
4. 密度：主歌每 2~3 行标 1 处；副歌每 1~2 行标 1 处；纯重复/语气行可以 0 处。
   全片至少 1 处，但总处数不得超过行数的 1.2 倍。
5. 同一段不要反复标同一个词，除非它是全曲 hook。
6. idx 用给定行号，不要自己重排。
7. 只输出 JSON。
"""


def _type_emphasis_map(w):
    """读 type-emphasis.json → {行 idx: [片段...]}；没有或损坏时返回空表。"""
    try:
        doc = json.loads((w / "type-emphasis.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for e in (doc.get("lines") or []):
        if not isinstance(e, dict):
            continue
        idx = e.get("idx")
        picks = [str(x).strip() for x in (e.get("picks") or []) if str(x).strip()]
        if isinstance(idx, int) and picks:
            out[idx] = picks[:2]
    return out


def _type_emphasis_text(w):
    """把逐句重点渲染成注入画面提示词的短文本。"""
    try:
        tp = json.loads((w / "type-plan.json").read_text(encoding="utf-8"))
        style = type_styles.get(tp.get("typeStyle")) or {}
        treat = (style.get("emphasis") or {}).get("text") or ""
    except Exception:
        treat = ""
    try:
        doc = json.loads((w / "type-emphasis.json").read_text(encoding="utf-8"))
    except Exception:
        doc = {}
    rows = [e for e in (doc.get("lines") or [])
            if isinstance(e, dict) and e.get("picks")]
    if not rows:
        return ("（本片没有预标注重点：你按语义自行给每句挑 1~2 处连续片段做重点，"
                "其余字保持基准字号/颜色。）"
                + (f"\n重点处理：{treat}" if treat else ""))
    L = ["每句只重点处理这些片段，其余字保持基准："]
    for e in rows:
        pos = e.get("pos")
        pos = pos if isinstance(pos, int) else e.get("idx")
        L.append(f"- 第 {pos} 行「{e.get('text', '')}」→「{('」「'.join(e['picks']))}」"
                 + (f"（{e.get('why')}）" if e.get("why") else ""))
    if treat:
        L.append("重点处理：" + treat)
    return "\n".join(L)


def st_type_emphasis(w, tl, plan, brief, cfg, force=False):
    """生成逐句重点标注 type-emphasis.json。失败不拦片，画面提示词会要求模型自行判断。"""
    p = w / "type-emphasis.json"
    lines = [L for L in (tl.get("lines") or []) if isinstance(L.get("text"), str) and L["text"]]
    if not lines:
        return False, "没有歌词行"
    need = _type_sections(plan)
    sig = sha(brief or "", "\n".join(need),
              "\n".join(f"{L.get('idx')}:{L['text']}" for L in lines))
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            if (int(old.get("_v") or 0) >= TYPE_EMPHASIS_VERSION
                    and old.get("_sig") == sig):
                n = sum(len(e.get("picks") or []) for e in (old.get("lines") or [])
                        if isinstance(e, dict))
                log(f"重点标注复用：{n} 处")
                return True, "复用"
        except Exception:
            pass

    listing = []
    for pos, L in enumerate(lines):
        idx = L.get("idx")
        idx = idx if isinstance(idx, int) else pos
        listing.append(f"idx={idx}｜[{L.get('section') or ''}] {L['text']}")
    ctx = (
        f"用户要求（最高优先级）：\n{brief or '（无额外要求）'}\n\n"
        f"歌曲：{tl.get('duration')}s，BPM {tl.get('bpm')}，段落 {need}\n\n"
        "编导方案（段落情绪）：\n" + json.dumps(plan.get("sections") or [], ensure_ascii=False)
        + "\n\n歌词逐行：\n" + "\n".join(listing)
    )
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"type-emphasis-prompt-{k}", c2)
            raw = _llm(_TYPE_EMPHASIS_SYS, c2, cfg, meta_label=f"type-emphasis-{k}")
            dump(f"type-emphasis-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"重点标注 第{k}次 ✗ {errs[0]}")
            continue

        by_idx = {}
        for pos, L in enumerate(lines):
            idx = L.get("idx")
            idx = idx if isinstance(idx, int) else pos
            by_idx[idx] = (pos, L["text"])
        bad, got = [], {}
        for e in (doc.get("lines") or []):
            if not isinstance(e, dict):
                continue
            try:
                idx = int(e.get("idx"))
            except (TypeError, ValueError):
                bad.append(f"idx 不是整数：{e.get('idx')!r}")
                continue
            hit = by_idx.get(idx)
            if not hit:
                bad.append(f"idx {idx} 不在歌词里")
                continue
            pos, text = hit
            picks, seen = [], set()
            for x in (e.get("picks") or []):
                s = str(x).strip()
                if not s or s in seen:
                    continue
                if s not in text:
                    bad.append(f"第 {idx} 行的「{s}」不是原文连续子串")
                    continue
                if s == text:
                    bad.append(f"第 {idx} 行不能整行标注")
                    continue
                if len(s) > 8:
                    bad.append(f"第 {idx} 行的「{s}」超过 8 字")
                    continue
                seen.add(s)
                picks.append(s)
                if len(picks) >= 2:
                    break
            if picks:
                got[idx] = {"idx": idx, "pos": pos, "text": text,
                            "picks": picks, "why": str(e.get("why") or "").strip()}
        total = sum(len(x["picks"]) for x in got.values())
        if bad:
            errs = bad[:6]
            log(f"重点标注 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue
        if total < 1:
            errs = ["至少标 1 处重点"]
            log(f"重点标注 第{k}次 ✗ {errs[0]}")
            continue
        if total > max(1, int(len(lines) * 1.2)):
            errs = [f"标了 {total} 处，超过行数的 1.2 倍（{int(len(lines) * 1.2)}）"]
            log(f"重点标注 第{k}次 ✗ {errs[0]}")
            continue

        rows = [got[k2] for k2 in sorted(got)]
        out = {"_v": TYPE_EMPHASIS_VERSION, "_sig": sig,
               "summary": str(doc.get("summary") or ""), "lines": rows}
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"重点标注：{len(rows)} 句 / {total} 处")
        return True, f"{len(rows)} 句 / {total} 处"
    log("⚠ 重点标注 3 次未通过，画面由模型按句自行判断")
    return False, "标注未通过"


def _type_plan_text(w):
    """把 type-plan.json 渲染成注入画面提示词的短文本。"""
    try:
        tp = json.loads((w / "type-plan.json").read_text(encoding="utf-8"))
    except Exception:
        return "（字效方案缺失：用大号高对比文字，逐字出现。）"
    if not isinstance(tp, dict):
        return "（字效方案格式无效：用大号高对比文字，逐字出现。）"
    tid = tp.get("typeStyle")
    typo = tp.get("typography") or {}
    pal = tp.get("palette") or {}
    L = [type_styles.prompt(tid) or f"字效风格：{tid}",
         f"最终字体：{typo.get('font', '')}｜字重 {typo.get('weight', 900)}｜"
         f"字距 {typo.get('tracking', 0)}em｜行距 {typo.get('leading', 1.0)}｜"
         f"对齐 {typo.get('align', 'center')}",
         f"配色：bg {pal.get('bg', '#111111')} / fg {pal.get('fg', '#F4EFE4')} / "
         f"accent {pal.get('accent', '#E9A63B')}"]
    for s in (tp.get("sections") or []):
        L.append(f"- 段落「{s.get('name', '')}」：energy {s.get('energy', 'mid')}；"
                 f"layout {s.get('layout', '')}；emphasis {s.get('emphasis', '')}")
    if tp.get("rules"):
        L.append("全片规则：" + "；".join(str(x) for x in tp["rules"]))
    return "\n".join(L)


def _apply_type_plan(w, plan, tp):
    """把字效方案落到 plan.json：关闭歌词层与 chrome，记录 typePlan。"""
    if not isinstance(tp, dict):
        return
    plan["plain"] = True
    plan["typeStyle"] = tp.get("typeStyle")
    plan["typePlan"] = tp
    plan["lyrics_layer"] = "none"
    plan["chrome"] = {"section": "hide", "progress": "hide"}
    (w / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def st_typeplan(w, tl, plan, brief, cfg, force=False, forced_style=""):
    """生成文字类的字效方案 type-plan.json，并写入 plan.plain。
    forced_style 给定时按用户指定的字效风格，不再让 LLM 选。"""
    p = w / "type-plan.json"
    need = _type_sections(plan)
    if forced_style and not type_styles.get(forced_style):
        return False, f"未知字效风格 {forced_style!r}；可选 {' / '.join(type_styles.ids())}"
    lyrics_text = ""
    try:
        lf = w / "lyrics.txt"
        if lf.exists():
            lyrics_text = lf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        lyrics_text = ""
    sig = sha(brief or "", "\n".join(need), lyrics_text[:2000], forced_style)
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        if (int(old.get("_v") or 0) >= TYPE_PLAN_VERSION
                and (old.get("_sections") or []) == need
                and (old.get("_sig") or "") == sig):
            _apply_type_plan(w, plan, old)
            log(f"字效方案复用：{type_styles.label(old.get('typeStyle'))}")
            return True, "复用"

    ctx = (
        f"用户要求（最高优先级）：\n{brief or '（无额外要求）'}\n\n"
        f"歌曲：{tl.get('duration')}s，BPM {tl.get('bpm')}，段落 {need}\n\n"
        "编导方案：\n" + json.dumps(plan, ensure_ascii=False) + "\n\n"
        "歌词：\n" + (lyrics_text[:4000] or "（无歌词）")
    )
    if forced_style:
        ctx += (f"\n\n用户指定字效风格：{forced_style}"
                f"（{type_styles.label(forced_style)}）。typeStyle 必须填它。")
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"typeplan-prompt-{k}", c2)
            raw = _llm(_TYPE_PLAN_SYS.replace("{TYPE_MENU}", type_styles.menu()),
                       c2, cfg, meta_label=f"typeplan-{k}")
            dump(f"typeplan-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"字效 第{k}次 ✗ {errs[0]}")
            continue

        errs = []
        tid = forced_style or str(doc.get("typeStyle") or "").strip()
        style = type_styles.get(tid)
        if not style:
            errs.append(f"typeStyle 必须是 {' / '.join(type_styles.ids())} 之一，收到 {tid!r}")
        raw_sections = doc.get("sections")
        raw_sections = raw_sections if isinstance(raw_sections, list) else []
        have = {str(s.get("name") or "").strip() for s in raw_sections if isinstance(s, dict)}
        if set(need) - have:
            errs.append(f"sections 缺少段落：{sorted(set(need) - have)}")
        pal = doc.get("palette")
        pal = pal if isinstance(pal, dict) else {}
        if not str(pal.get("bg") or "").strip() or not str(pal.get("fg") or "").strip():
            errs.append("palette 必须给 bg / fg")
        if errs:
            log(f"字效 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        got = doc.get("typography")
        got = got if isinstance(got, dict) else {}
        typo = {
            "font": style["font"],
            "weight": got.get("weight", style["weight"]),
            "tracking": got.get("tracking", style["tracking"]),
            "leading": got.get("leading", style["leading"]),
            "align": got.get("align", style["align"]),
        }
        secs = []
        for name in need:
            hit = next((s for s in raw_sections
                        if isinstance(s, dict) and str(s.get("name") or "").strip() == name), {})
            secs.append({
                "name": name,
                "energy": str(hit.get("energy") or "mid"),
                "layout": str(hit.get("layout") or ""),
                "emphasis": str(hit.get("emphasis") or ""),
            })
        raw_rules = doc.get("rules")
        raw_rules = raw_rules if isinstance(raw_rules, list) else []
        tp = {
            "version": 1, "typeStyle": tid,
            "typography": typo,
            "palette": {"bg": pal.get("bg"), "fg": pal.get("fg"),
                        "accent": pal.get("accent", "")},
            "sections": secs,
            "rules": [str(x) for x in raw_rules if str(x).strip()],
            "_v": TYPE_PLAN_VERSION, "_sections": need, "_sig": sig,
        }
        p.write_text(json.dumps(tp, ensure_ascii=False, indent=2), encoding="utf-8")
        _apply_type_plan(w, plan, tp)
        log(f"字效方案完成（第 {k} 次）：{style['label']}")
        return True, f"第{k}次"

    return False, f"3 次不通过：{errs[:3]}"


_PLAN_SYS = """你是 MV 编导。读歌词与用户要求，产出编排方案 plan.json（只输出 JSON）。
{
 "title": "歌名", "subtitle": "副标题或署名",
 "opening": { "form": "标题先出|画面先出|黑场切入|直接入唱", "titleAt": "居中|左上|右下|底部",
              "note": "开场怎么演" },
 "palette": { "base": "#141A2E", "accent": "#E9A63B", "mood": "一句话" },
 "sections": [ { "name": "段落名(与歌词标签一致)", "theme": "视觉母题", "motion": "推进|静止|漂移" } ],
 "interludes": [ { "afterLine": 11, "idea": "这段间奏讲什么" } ],
 "ending": { "form": "标题回扣|定格|字幕|渐黑", "credit": "署名" },
 "lyricStyle": "band",
 "lyricStyles": {
   "Verse 1": {"style": "bottom", "karaoke": false},
   "Chorus":  {"style": "bounce", "karaoke": true}
 },
 "chrome": { "section": "zh", "sectionAt": "top-left", "progress": "top" }
}

**本片不指定任何画风**：不要写 visualStyle，也不要把画面往某种既有插画范式上套。
画面怎么画由画面作者自己判断，你只负责故事、段落、配色母题、开场与收尾。

歌词呈现 —— 两件事都由你按这首歌决定，**不要全片一个样**：

1. `style`：这一段的字幕放哪、什么形态
  band     居中横幅，整句可见、逐字变金    跟唱友好，最稳
  shrink   逐字"缩着蹦出"                  走心，情绪往里收
  bounce   逐字从上方落下                  轻快，少年感
  vertical 右侧竖排、楷书、逐字淡入        国风、古意、安静
  bottom   贴底居中、逐字蹦出              大场面，把天地全让出来
  walk     小球踩字往前走，压到的字回弹    童趣、轻松
  brush    左侧竖两排、行楷、落笔墨晕      书法、怀旧、思亲

2. `karaoke`：要不要 KTV 逐字高亮
  true  = 逐字点亮（适合慢歌、长音、需要跟唱）
  false = 整句一起出现、不做逐字（适合**语速快、句子长、逐字根本来不及读**的歌）
  判断依据看**字/秒**：一句的字数 ÷ 时长，≥3 字/秒基本就该用 false；
  整首歌语速都快时，可以直接给 `"lyricKaraoke": false` 当全局默认，个别慢段再覆盖。

`lyricStyles` 的键用歌词里的段落标签（可写 "Verse 1"，引擎会退到 "Verse" 匹配）。
不填也不会崩：引擎会按段落轮换版式、并按字/秒自动决定是否逐字 —— 但那样是通用策略，
不如你按歌性判断得准。

**选完版式，画面主体必须避开它占的位置**（引擎通过 e.lyricBox 给出矩形 x0,y0,x1,y1）：
  band / shrink / bounce / walk → 顶部横条（y 96~206，walk 到 52）
  vertical                      → 右侧一列（x 1080~1280）
  bottom                        → 底部横条（y 546~664）
  brush                         → 左侧两列（x 80~340）
人脸、手、关键道具、标题都不要压进这块；背景渐变可以铺满。

画面框 chrome —— 这些是"画框"，不是主角，可关可挪：
  section    en（Verse/Chorus）| zh（主歌/副歌）| hide
  sectionAt  top-left | top-right | bottom-left | bottom-right
  progress   top | bottom | hide

要求：
1. sections 必须覆盖歌词里出现的**每一个**段落标签，顺序一致。
2. interludes 必须覆盖下面列出的**每一处**空档（用 afterLine 指"接在第几句之后"，0 基）。
3. 用户要求（brief）里明确说的，优先级高于你自己的想法，冲突以 brief 为准。
4. 歌词是别人的心声/叙事时，编排要服务于"讲清楚这件事"，不要堆特效。
5. lyricStyle 与 chrome 必须贴这首歌的气质，**不许永远用 band + top-left + top**：
   国风/思念/怀旧考虑 brush 或 vertical；轻快/童声考虑 bounce 或 walk；大场面/山河/登高考虑 bottom；
   中文歌词优先 section:"zh"。不同作品之间要避免版式雷同。
6. 画面主体按上面「必须避开」的位置来构图：选 bottom 就把主体放中上部；选 vertical 就避开右侧；
   选 brush 就避开左侧；选 band 系列就把主体放在 y>206 以下。
"""

# 视觉圣经版本：新增字段（如 character 一致性档案）时自增，旧缓存自动重建。
BIBLE_VERSION = 3

# 截图自查闭环：低分帧回灌重写，最多重写几个批次（成本上限）
REVIEW_SCORE_FLOOR = int(os.environ.get("LYRIC_MV_REVIEW_FLOOR", "4"))
REVIEW_REPAIR_MAX_BATCHES = int(os.environ.get("LYRIC_MV_REVIEW_MAX_BATCHES", "1"))

# 视觉圣经：在动笔写任何一帧之前，先把「整片长什么样」钉死。
# 为什么必须单独生成：画面是按 6 句一批分工写的，各批互相看不见；
# 只给同一份 plan，八批会各自解读，最终像八支不同的片子。
# 把角色、配色弧线、母题、构图、运动规则显式写出来，每批照抄执行，才有整片感。
_BIBLE_SYS = """你是这支 MV 的美术总监。编导方案已经定了「每段讲什么」，你要在画面代码动笔之前，
先把「全片视觉圣经」定下来：后面每一句画面都照它写，所以它必须是**能直接照着画的具体规定**，
不是形容词堆砌。

只输出一个 JSON 对象（不要 markdown 围栏、不要解释）：
{
 "protagonist": "整片不变的视觉主体：优先考虑一件物件、一个场景或一种光影结构，也可以是一个/一组人物；写清它长什么样、什么颜色、占据画面多大",
 "character": {"applies": true, "who": "如果片中有固定人物：是谁/什么身份", "hair": "固定的发型与发色", "cloth": "固定的服装与配色", "colors": ["#RRGGBB", "#RRGGBB"], "scale": "人物高度约占画面的比例"},
 "cast": [{"role": "friend-a", "name": "配角名", "hair": "发型", "outfit": "服装", "colors": ["#RRGGBB"], "note": "与主角的区分点"}],
 "stage": {"location": "整片固定的舞台/主场景（一场戏只在一个世界里）", "background": ["固定背景元素"], "light": "固定光位与色调", "camera": "默认机位与轴线"},
 "continuity": ["整片只允许哪些变化（机位/景别/灯光/道具/动作）", "明确禁止的变化（换场景/换主体/换服装等）"],
 "paletteArc": [{"section": "段落名", "colors": ["#RRGGBB", "#RRGGBB"], "mood": "一句话情绪"}],
 "motifs": ["贯穿全片的 2~3 个视觉母题/符号（同一物件反复出现在不同段落）"],
 "composition": "构图规则：镜头远近怎么推进、主体偏左/中/右、留白比例、如何避开歌词占用的位置",
 "motion": "运动规则：每个镜头必须有什么在动、转场怎么由动作带出来、哪些运动会破坏观感",
 "forbidden": ["明确禁止的做法"]
}

硬性要求：
1. paletteArc 必须覆盖下面列出的**每一个段落**，顺序与歌曲一致；颜色要在段落之间承接推进，不是每段换一套。
2. protagonist 要能落到 canvas 上：写清形状、颜色、比例，能直接用形状工具画出来；
   不要写「唯美」「电影感」「氛围感」这类无法执行的说法。
   画面里画不画人由内容决定；如果要画，尽量贴近所选风格的画法；
   这一风格不适合正面人物时，就用背影、远景或只画物件。
3. **character 是主角的一致性档案**：片中如果出现主角（哪怕是背影），必须把发型、服装、主色、
   身高比例钉死，后面每一批都照这套画，不许换发色/换衣服；片中不需要固定人物时 applies=false，
   其余字段留空字符串即可。
   **配角写进 cast**：每个配角给 role（小写英文/连字符，如 friend-a）、name、发型、服装、主色
   和「与主角的区分点」；数量按内容定、最多 4 个，没有配角就给空数组。
4. motifs 必须是具体物件（伞、扁担、一盏灯……），不能是抽象概念。
5. **stage / continuity 是表演型的硬约束**：整片只能发生在同一个舞台/主场景里；
   后续每句画面只允许机位、景别、灯光、道具和动作变化，不许换场景、换主体、换服装。
   stage 要写成能直接照着画的具体规定（地点、背景元素、光位、轴线）。
6. 不靠照片；不要用文字当字幕/对白。短标题、标签、数字、关键词可以写（≤12 字），
   但不要重复歌词原文、不要长段落。hanzi 允许汉字本身作为画面主体。
7. 只输出 JSON。
"""

_SCENES_SYS = """你是 MV 美术指导兼动画师。你要为一首歌的每一句歌词写画面代码。
引擎已经把时间、拍点、歌词、KTV 跳字、安全区都做好了——**你只管画**。

输出一个 JS 文件（只要代码，不要 markdown 围栏、不要解释）：

MV.scenes = [ { bg:"#141A2E", draw(e){ ... } }, ... ];   // 每句一条，条数必须等于歌词行数
MV.intro = [ { bars:2, bg:"#0E1428", draw(e){...} }, ... ];
MV.interludes = [ { afterLine:11, cards:[ { bars:4, bg:"#1D2540", draw(e){...} } ] } ];
MV.outro = [ { bars:3, bg:"#0E1428", draw(e){...} } ];
MV.filler = { bg:"#101828", draw(e){...} };

### 可用 API（下面这段是**从引擎运行时实时导出**的，随引擎自动更新）
**只有列出的成员存在，没列出的就是不存在 —— 不要猜、不要自己造名字。**
{API}

### 本次模式
{MODE_RULE}

### 铁律（违反会被闸门拦下）
1. draw 必须是 e.t 的**纯函数**。禁止 Math.random / Date.now / performance.now /
   setTimeout / requestAnimationFrame / 任何跨帧累积的外部变量。
   要随机用 e.rnd(seed)。
2. **不要画歌词/字幕原文**（不要重复本句歌词，也不要做字幕）。y∈[96,206] 的歌词带由引擎负责。
   短标题、标签、数字、关键词可以写（用 e.drawText，≤12 字），按风格里的「文字」规则；
   不要写长段落，也不要把文字放进歌词带。hanzi 可以把与主题相关的**单字**作为画面主体，但不要放歌词原文。
3. **绝不做整帧亮度脉动**（全画面忽明忽暗＝闪，观感极差）。
   节拍只能用位移/缩放/旋转/形变表达，用 e.pulse / e.strong 驱动这些。
4. 每句画面要**具体对应这句歌词的意思**，用具象的物/场景，不要泛泛堆色块。
5. 相邻句不要长得一样；段落之间要有视觉递进。
6. MV.scenes 条数必须严格等于歌词行数。
7. **每个镜头都要有看得见的运动**（0.5 秒内至少满足一条）：主体移动 ≥ 画面宽度的 1.5%（约 20px）、
   缩放变化 ≥ 8%、透明度变化 ≥ 15%，或一组元素整体位移 ≥ 20px。
   只加几根细线、亚像素推拉**不算**——它们看起来和静止没区别。
8. 相邻两句的转场要**由画面里的动作带出来**（物件落下、光带扫过、镜头下坠/推近），
   不要靠整帧淡入淡出糊过去。
9. `e.W` / `e.H` / `e.t` / `e.i` / `e.P` 这些是**属性**，直接写 `e.W`；
   写成 `e.W()` 会报 "e.W is not a function" 并整批退回重写。

### 可用 AI 底图（可选）
{IMAGES}

### 人物（可选）
{STYLE}

画面主体由这句歌词的内容决定：可以是一件物件、一个场景、一束光，也可以是一个人。
需要人时用 `e.actor(...)` 最稳（pose / phase / hug 控制动作）；不需要人时不要硬加。
同一句里不要让同一个人跳变位置。
"""


# 思考档位默认跟随调用方配置，**不再强制关闭**：
# 有些模型（如 Kimi K3.1）根本关不掉思考，强行注入 off 无效；统一按"正常思考"处理，
# 把余量放在停滞超时（600s）与输出预算（整体 128k，思考 token 也在里面）上。
# 想在本技能内单独关闭思考：设环境变量 LYRIC_MV_THINKING=disabled 即可。
THINKING_MODE = os.environ.get("LYRIC_MV_THINKING", "")

# 输出预算：**思考 token 也算在 max_tokens 里**，实际思考量常超过正文；
# 统一按整体给足（见 context_manager.LONG_OUTPUT_MAX_TOKENS），
# 通道上限更低时，服务端拒绝会自动沿 OUT_TOKEN_FALLBACKS 降档。
try:
    from context_manager import LONG_OUTPUT_MAX_TOKENS, LONG_OUTPUT_TOKEN_FALLBACKS
except Exception:
    LONG_OUTPUT_MAX_TOKENS = 128_000
    LONG_OUTPUT_TOKEN_FALLBACKS = (96_000, 64_000, 32_000)
MAX_OUT_TOKENS = int(os.environ.get("LYRIC_MV_MAX_TOKENS", str(LONG_OUTPUT_MAX_TOKENS)))
OUT_TOKEN_FALLBACKS = LONG_OUTPUT_TOKEN_FALLBACKS


def _llm(system, ctx, cfg, meta_label=""):
    """单次调用。
    timeout=600：这是"停滞超时"（连续这么久没有任何数据才判失败）。长思考模型思考期间
    可能长时间不吐正文，给足余量；真正卡死由用户取消兜底。
    attempts=1：重试统一交给上层 _ask（它知道错在哪、且只重来这一小段），
    两层都重试会叠成很长的等待。

    meta_label 给了就把 {stop_reason, usage} 落到 llm/<label>-meta.txt；
    一旦 stop_reason=max_tokens 就**明确报"输出被截断"**，而不是伪装成语法错误
    ——曾经的故障就是被截断后 node --check 报语法错，看起来像模型不会写。"""
    from skills.opendesign.scripts.renderer import call_llm_text
    meta = {}

    def on_meta(m):
        meta.clear()
        meta.update(m or {})
        if meta_label:
            dump(f"{meta_label}-meta", json.dumps(meta, ensure_ascii=False))

    def _call(mt):
        return call_llm_text(
            system_prompt=system, context=ctx,
            base_url=cfg["base_url"], api_key=cfg["api_key"],
            model=cfg["model"], protocol=cfg.get("protocol", "anthropic"),
            provider=cfg.get("provider"), thinking=cfg.get("thinking") or THINKING_MODE,
            max_tokens=mt, timeout=600, attempts=1, on_meta=on_meta)

    # 先按预算上限要；通道不接受这个 max_tokens 才逐档下调。
    # 注意：「输出被截断」是模型真把预算用完了，降档只会更糟，必须直接报错。
    caps = [MAX_OUT_TOKENS] + [c for c in OUT_TOKEN_FALLBACKS if c < MAX_OUT_TOKENS]
    for i, mt in enumerate(caps):
        try:
            txt = _call(mt)
            break
        except RuntimeError as e:
            msg = str(e)
            if "输出被截断" in msg or "max_tokens" not in msg or i == len(caps) - 1:
                raise
            log(f"  max_tokens={mt} 被服务端拒绝，降到 {caps[i + 1]}")
    sr = str(meta.get("stop_reason") or "")
    usage = meta.get("usage") or {}
    # 各家把「思考 token」放在不同字段里；都读一遍。
    # DeepSeek 的 Anthropic 端点只返回 output_tokens，不单列思考 → 用正文反推一个近似值，
    # 否则日志会一直显示"没有思考"，误导判断。
    think = ((usage.get("output_tokens_details") or {}).get("thinking_tokens")
             or (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
             or usage.get("reasoning_tokens"))
    if think is None and usage.get("output_tokens"):
        body = sum(1 for ch in txt if "\u4e00" <= ch <= "\u9fff")
        body += (len(txt) - body) / 3.6
        gap = int(usage["output_tokens"] - body)
        if gap > 500:
            think = f"≈{gap}"
    if sr in ("max_tokens", "length"):
        if meta_label:
            dump(f"{meta_label}-truncated", txt)
        raise RuntimeError(
            f"输出被截断（stop_reason={sr}；正文 {len(txt)} 字，"
            f"思考 {think if think is not None else '?'} tokens，"
            f"总输出 {usage.get('output_tokens')}）—— 提高 LYRIC_MV_MAX_TOKENS 或拆小批次")
    if usage.get("output_tokens"):
        log(f"  tokens：输入 {usage.get('input_tokens')}｜输出 {usage.get('output_tokens')}"
            + (f"（其中思考 {think}）" if think else ""))
    return txt


def _llm_cfg():
    """LLM 配置：优先用框架注入的（环境变量，不进 argv/日志）。
    找不到才回落到本地读配置——那只在命令行直接跑时有用，Sigma 内应始终由框架注入。"""
    raw = os.environ.get("LYRIC_MV_LLM")
    if raw:
        try:
            c = json.loads(raw)
            if c.get("api_key") and c.get("base_url") and c.get("model"):
                return c
            log("框架注入的 LLM 配置不完整（缺 base_url/api_key/model）")
        except Exception as e:
            log(f"框架注入的 LLM 配置解析失败：{e}")
    try:
        from read_keys import load_config
        sk = load_config().get("skillKeys") or {}
        if sk.get("opendesignLlmApiKey"):
            return {"api_key": sk["opendesignLlmApiKey"],
                    "base_url": sk.get("opendesignLlmBaseUrl", ""),
                    "model": sk.get("opendesignLlmModel", ""),
                    "protocol": sk.get("opendesignLlmProtocol", "anthropic")}
    except Exception:
        pass
    return None


def _json_of(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except Exception:
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            return json.loads(raw[i:j + 1])
    raise ValueError("不是合法 JSON")


def _js_of(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    return raw.strip()


def gaps_of(tl, bar_sec, min_bars=2):
    out, lines = [], tl["lines"]
    for i in range(len(lines) - 1):
        g = lines[i + 1]["start"] - lines[i]["end"]
        if g > min_bars * bar_sec:
            out.append((i, round(g, 2)))
    return out


def _card_times(tl, gaps):
    """片头/间奏/尾奏/短空档各取代表时刻，用来校验卡片代码在引擎里跑不跑得起来。
    卡片没有"行号"可依，只能按引擎调度它的时段反推：
      片头 = 第一句之前；间奏 = 长空档中点；短空档 = 用 filler 兜底的中点；
      尾奏 = 末句之后。"""
    lines, dur = tl["lines"], tl["duration"]
    bar = 4 * (tl.get("beat_seconds") or 0.5)
    ts = []
    if lines and lines[0]["start"] > 1.0:
        ts.append(round(lines[0]["start"] * 0.5, 3))
    for i, _g in gaps:
        ts.append(round((lines[i]["end"] + lines[i + 1]["start"]) / 2, 3))
    # 短空档（≤2 小节）没有间奏卡，靠 filler 兜底；这里必须一起抽查，
    # 否则卡片代码“通过”了，短空档那几秒却是一片死画面。
    for i in range(len(lines) - 1):
        g = lines[i + 1]["start"] - lines[i]["end"]
        if 0.2 < g <= 2 * bar:
            ts.append(round((lines[i]["end"] + lines[i + 1]["start"]) / 2, 3))
    if lines and dur > lines[-1]["end"] + 1.0:
        ts.append(round((lines[-1]["end"] + dur) / 2, 3))
    seen, out = set(), []
    for t in ts:
        r = round(t, 3)
        if 0 <= r < dur and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _ctx_common(tl, brief):
    bar = 4 * tl["beat_seconds"]
    gaps = gaps_of(tl, bar)
    return (f"用户要求（最高优先级）：\n{brief or '（未特别指定，你自行判断）'}\n\n"
            f"歌曲：{tl['duration']:.1f}s｜BPM {tl['bpm']:.1f}｜每拍 {tl['beat_seconds']:.4f}s｜"
            f"每小节 {bar:.3f}s\n首句在 {tl['lines'][0]['start']:.2f}s｜"
            f"末句结束于 {tl['lines'][-1]['end']:.2f}s\n\n"
            + "歌词（第 i 行对应 MV.scenes[i]，i 从 0 起）：\n"
            + "\n".join(f"{i}: [{L['section']}] {L['text']}  ({L['start']:.1f}~{L['end']:.1f}s)"
                        for i, L in enumerate(tl["lines"]))
            + "\n\n必须用间奏卡覆盖的空档（afterLine 0 基）：\n"
            + ("\n".join(f"  afterLine={i}（第 {i} 句之后，空 {g}s）" for i, g in gaps)
               if gaps else "  （无）")), gaps


def _api_spec_text(w):
    """导出「引擎实际可用的 API 清单」供提示词注入。
    带缓存：引擎文件没变就复用，省一次浏览器启动。
    导出失败不致命（模型只能靠铁律盲写），但会写进 run.log 便于排查。"""
    cache = w / "api-spec.txt"
    try:
        # 导出器自己改了也要失效：只比引擎 mtime 的话，改了格式会一直用旧清单
        spec_src = HERE / "api_spec.py"
        fresh = (cache.exists()
                 and cache.stat().st_mtime >= ENGINE.stat().st_mtime
                 and cache.stat().st_mtime >= spec_src.stat().st_mtime)
    except OSError:
        fresh = False
    if fresh:
        return cache.read_text(encoding="utf-8")
    # 走 --out 写文件而不是抓 stdout：Windows 子进程 stdout 用的是本地编码，
    # 而这份清单里全是中文，走管道容易被解成乱码。写文件则两边都是 utf-8。
    sh([sys.executable, str(HERE / "api_spec.py"), "--engine", str(ENGINE),
        "--out", str(cache)], cwd=HERE)
    if not cache.exists():
        log("⚠ API 清单导出失败，本次提示词不含清单")
        return ""
    txt = cache.read_text(encoding="utf-8").strip()
    if not txt:
        log("⚠ API 清单为空，本次提示词不含清单")
        return ""
    log(f"API 清单已从引擎导出（{len(txt)} 字符）→ {cache.name}")
    return txt


def st_plan(w, st, tl, brief, cfg, force=False, mode="performance"):
    p = w / "plan.json"
    if p.exists() and not force:
        doc = json.loads(p.read_text(encoding="utf-8"))
        old_mode = doc.get("_mode") or "performance"
        if doc.get("visualStyle"):
            log("旧编导方案带有画风字段（已下线）：重新生成")
        elif old_mode != mode:
            log(f"编导方案的模式是 {old_mode}，与 {mode} 不同：重新生成")
        else:
            log("编导方案复用：plan.json")
            return True, "复用", doc
    ctx, gaps = _ctx_common(tl, brief)
    ctx += ("\n\n【不指定画风】不要写 visualStyle，也不要把画面往某种既有插画范式上套；"
            "画法由画面作者自己判断。")
    if mode == "typographic":
        ctx += ("\n\n本片是**文字类 MV**：sections 的 theme 写这一段的情绪与排版意图，"
                "不要写具体插画主体；lyricStyle 仍填一个值但不会被使用（没有独立歌词层）。")
    elif mode == "narrative":
        ctx += ("\n\n本片是**叙事型 MV**：sections 的 theme 写故事段落与情绪，不是歌词逐句画面；"
                "lyricStyle 仍要选一个适合的版式（歌词层照常显示，构图会避开歌词区）。")
    sys_prompt = _PLAN_SYS
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"plan-prompt-{k}", c2)
            raw = _llm(sys_prompt, c2, cfg, meta_label=f"plan-{k}")
            dump(f"plan-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"编导 第{k}次 ✗ {errs[0]}（原始输出见 llm/plan-raw-{k}.txt）")
            continue
        errs = []
        for key in ("title", "opening", "palette", "sections", "ending"):
            if key not in doc:
                errs.append(f"缺字段 {key}")
        doc.pop("visualStyle", None)
        ls = (doc.get("lyricStyle") or "").strip()
        if ls not in LYRIC_STYLES:
            errs.append(f"lyricStyle 必须是 {' / '.join(LYRIC_STYLES)} 之一，收到 {ls!r}")
        secs_needed = {L["section"] for L in tl["lines"] if L.get("section")}
        secs_have = {s.get("name") for s in (doc.get("sections") or [])}
        if secs_needed - secs_have:
            errs.append(f"sections 缺少段落：{sorted(secs_needed - secs_have)}")
        have = {i.get("afterLine") for i in (doc.get("interludes") or [])}
        if {i for i, _ in gaps} - have:
            errs.append(f"interludes 缺少空档：{sorted({i for i, _ in gaps} - have)}")
        if not errs:
            doc["_mode"] = mode
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"编导方案完成（第 {k} 次）")
            return True, f"第{k}次", doc
        log(f"编导 第{k}次 ✗ {'；'.join(errs[:3])}")
    return False, f"3 次不通过：{errs[:3]}", None


def st_bible(w, tl, plan, brief, cfg, force=False, mode="performance"):
    """生成全片视觉圣经 visual-bible.json（角色/舞台/连续性/配色弧线/母题）。
    非致命：失败只降级为「只按编导方案画」，不拦片。"""
    p = w / "visual-bible.json"
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        keep = ((old.get("_mode") or "performance") == mode
                and int(old.get("_v") or 0) >= BIBLE_VERSION)
        if old.get("_style"):
            keep = False   # 旧圣经带着画风规定，必须重建
        if keep:
            log("视觉圣经复用：visual-bible.json")
            return True, "复用"
        log(f"视觉圣经需要重建（模式 {old.get('_mode') or '无'} / 版本 {old.get('_v') or 0}"
            f" → {mode} / v{BIBLE_VERSION}）")
    ctx, _ = _ctx_common(tl, brief)
    ctx += "\n\n编导方案（视觉圣经必须能落实它）：\n" + json.dumps(plan, ensure_ascii=False)
    ctx += ("\n\n【不做画风预设】只写**故事事实**：角色是谁、什么造型特征、穿什么、"
            "在什么地点、什么时间与光线、镜头之间哪些必须保持一致。"
            "不要规定笔触、材质、画风名（绘本/皮影/水墨…），画法留给画面作者判断。")
    need = [s.get("name") for s in (plan.get("sections") or []) if s.get("name")]
    if need:
        ctx += "\n\npaletteArc 必须覆盖这些段落（顺序一致）：" + "、".join(need)
    if mode == "performance":
        ctx += ("\n\n本片是**表演型**：必须给出固定的 stage（地点/背景/光位/轴线）与 continuity"
                "（允许变什么、禁止变什么）。整片只在一个舞台里完成，靠机位、景别、灯光、道具和动作变化推进。")
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"bible-prompt-{k}", c2)
            raw = _llm(_BIBLE_SYS, c2, cfg, meta_label=f"bible-{k}")
            dump(f"bible-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"美术 第{k}次 ✗ {errs[0]}")
            continue
        errs = []
        if not str(doc.get("protagonist") or "").strip():
            errs.append("缺 protagonist")
        have = {a.get("section") for a in (doc.get("paletteArc") or [])}
        if set(need) - have:
            errs.append(f"paletteArc 缺少段落：{sorted(set(need) - have)}")
        for key in ("composition", "motion"):
            if not str(doc.get(key) or "").strip():
                errs.append(f"缺 {key}")
        if not isinstance(doc.get("motifs"), list) or not doc["motifs"]:
            errs.append("motifs 必须是非空数组")
        if mode == "performance":
            stage = doc.get("stage")
            if not isinstance(stage, dict) or not str(stage.get("location") or "").strip():
                errs.append("表演型缺 stage.location（整片固定舞台）")
            cont = doc.get("continuity")
            if not isinstance(cont, list) or not cont:
                errs.append("表演型缺 continuity（允许/禁止哪些变化）")
        if not errs:
            doc["_style"] = ""
            doc["_mode"] = mode
            doc["_v"] = BIBLE_VERSION
            p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"视觉圣经完成（第 {k} 次）：{str(doc.get('protagonist'))[:36]}")
            return True, f"第{k}次"
        log(f"美术 第{k}次 ✗ {'；'.join(errs[:3])}")
    return False, f"3 次不通过：{errs[:3]}"


SHOTLIST_VERSION = 1

_SHOTLIST_SYS = """你是 MV 的分镜导演。读歌词时间轴、编导方案、视觉圣经和用户要求，
把整首歌切成一串可拍的镜头，给画面作者逐镜的指令。
只输出 JSON：
{
 "shots": [
   {"start": 0.0, "end": 6.5, "section": "Verse 1",
    "size": "景别（大全景/全景/中景/近景/特写/空镜）",
    "camera": "机位与运动（固定/推/拉/横移/摇/俯拍/仰拍/手持/跟拍）",
    "subject": "这一镜的主体（谁/什么东西/哪处环境）",
    "action": "画面里发生什么（具体的动作或光影变化）",
    "cast": ["这一镜出场的角色 key（角色表里的 role，空镜可为空数组）"],
    "change": "与上一镜的差别（第一镜写「开场」）"}
 ]
}

硬性要求：
1. shots 从 0 连续铺满到 {DURATION}s，首尾相接，不留空档、不重叠；每镜 3~12 秒。
2. 按段落与情绪切，不按歌词句机械切；一个镜头可以跨多句。
3. 相邻两镜至少在景别 / 机位 / 主体 / 动作里换一项；禁止连续两镜同景别、同主体、同构图。
4. 允许纯环境空镜（size=空镜，subject 写环境，cast 为空）：不要每镜都摆全员合影。
5. 主体写清是谁；配角按视觉圣经的固定造型，不要把主角复制成多个人。
6. 严格服从视觉圣经的世界、角色、服装与连续性；但机位、景别、主体可以大胆变化。
7. cast 只能填角色表里存在的 role，不要自造角色；不在这一镜的人不要写进 cast。
8. 只输出 JSON。
"""


def _character_file(w) -> Path | None:
    """整组角色文件的来源：环境变量（事务注入）优先，其次 out_dir 里的 art 目录。"""
    env = os.environ.get("LYRIC_MV_CHARACTER", "").strip()
    if env:
        p = Path(env)
        candidates = [p.parent / "characters.json", p]
    else:
        candidates = [w / "art" / "characters.json", w / "art" / "character.json",
                      w / "characters.json", w / "character.json"]
    return next((p for p in candidates if p.exists()), None)


def _cast_roles(w) -> list[dict]:
    """项目里已确认的角色表：[{role, name}]。没有定妆文件就返回空（镜头表不写 cast）。"""
    p = _character_file(w)
    if p:
        try:
            doc = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            doc = None
        if isinstance(doc, dict) and isinstance(doc.get("characters"), list):
            out = []
            for c in doc["characters"]:
                if not isinstance(c, dict):
                    continue
                spec = c.get("spec") if isinstance(c.get("spec"), dict) else c
                role = str(c.get("role") or "").strip()
                if role:
                    out.append({"role": role, "name": str(spec.get("name") or role)})
            if out:
                return out
        if isinstance(doc, dict) and isinstance(doc.get("proportions"), dict):
            return [{"role": "hero", "name": str(doc.get("name") or "主角")}]
    return []


def st_shotlist(w, tl, plan, brief, cfg, force=False):
    """performance 模式的逐镜镜头表：景别/机位/主体/动作/与上一镜的差异。

    非致命：生成失败就退回「按段落自动分镜」，不拦片；成功时画面作者每镜都会
    拿到具体镜头要求，并对上一镜的构图做出变化。
    """
    p = w / "shots.json"
    dur = float(tl.get("duration") or 0)
    cast_file = _character_file(w)
    sig = sha(w / "timeline.json", w / "plan.json", w / "visual-bible.json", brief or "",
              cast_file if cast_file else "")
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            old = {}
        if int(old.get("_v") or 0) >= SHOTLIST_VERSION and old.get("_sig") == sig:
            log(f"镜头表复用：{len(old.get('shots') or [])} 镜")
            return True, "复用"

    ctx, _ = _ctx_common(tl, brief)
    ctx += "\n\n编导方案：\n" + json.dumps(plan, ensure_ascii=False)[:4000]
    bt = _bible_text(w)
    if bt:
        ctx += "\n\n视觉圣经（世界/角色/连续性必须遵守）：\n" + bt[:3000]
    roles = _cast_roles(w)
    if roles:
        ctx += ("\n\n可用角色（每镜的 cast 只能填这些 role，不要自造角色）：\n"
                + "\n".join(f"- {r['role']}：{r['name']}" for r in roles))
    ctx += f"\n\n歌长 {dur:.2f}s：镜头必须从 0 连续铺到 {dur:.2f}s。"

    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"shotlist-prompt-{k}", c2)
            raw = _llm(_SHOTLIST_SYS.replace("{DURATION}", f"{dur:.2f}"), c2, cfg,
                       meta_label=f"shotlist-{k}")
            dump(f"shotlist-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"镜头表 第{k}次 ✗ {errs[0]}")
            continue

        raw_shots = doc.get("shots") if isinstance(doc, dict) else None
        clean = []
        for s in (raw_shots if isinstance(raw_shots, list) else []):
            if not isinstance(s, dict):
                continue
            try:
                a, b = float(s.get("start")), float(s.get("end"))
            except (TypeError, ValueError):
                continue
            clean.append({
                "start": round(a, 3), "end": round(b, 3),
                "section": str(s.get("section") or "").strip(),
                "size": str(s.get("size") or "").strip(),
                "camera": str(s.get("camera") or "").strip(),
                "subject": str(s.get("subject") or "").strip(),
                "action": str(s.get("action") or "").strip(),
                "change": str(s.get("change") or "").strip(),
                "cast": [str(x).strip() for x in (s.get("cast") or [])
                         if isinstance(x, (str, int)) and str(x).strip()]
                        if isinstance(s.get("cast"), list) else [],
            })
        if not isinstance(raw_shots, list):
            errs = ["缺 shots 数组"]
        elif len(clean) != len(raw_shots):
            errs = ["有镜头缺 start/end 或不是对象"]
        else:
            errs = []
            if not (8 <= len(clean) <= 28):
                errs.append(f"镜头数 {len(clean)} 不在 8~28 之间")
        if not errs:
            for i, s in enumerate(clean):
                span = s["end"] - s["start"]
                if span < 3.0:
                    errs.append(f"第 {i + 1} 镜只有 {span:.1f}s，太短（≥3s）")
                elif span > 12.0:
                    errs.append(f"第 {i + 1} 镜有 {span:.1f}s，太长（≤12s）")
                for key, label in (("size", "景别"), ("camera", "机位"),
                                   ("subject", "主体"), ("action", "动作")):
                    if not s[key]:
                        errs.append(f"第 {i + 1} 镜缺{label}")
                if i > 0 and not s["change"]:
                    errs.append(f"第 {i + 1} 镜缺「与上一镜的差别」")
                if roles:
                    known = {r["role"] for r in roles}
                    unknown = [c for c in s["cast"] if c not in known]
                    if unknown:
                        errs.append(f"第 {i + 1} 镜 cast 里有不存在的角色 {unknown}"
                                    f"（可用：{sorted(known)}）")
            errs.extend(_shot_coverage_errors(clean, dur))
        if errs:
            errs = errs[:8]
            log(f"镜头表 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        clean.sort(key=lambda s: s["start"])
        p.write_text(json.dumps({
            "_v": SHOTLIST_VERSION, "_sig": sig, "_mode": "performance", "shots": clean,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"镜头表完成（第 {k} 次）：{len(clean)} 镜")
        return True, f"{len(clean)} 镜"
    return False, ("；".join(errs[:3]) if errs else "未生成")


def _bible_text(w):
    """把 visual-bible.json 渲染成注入每批提示词的短文本。"""
    f = w / "visual-bible.json"
    if not f.exists():
        return ""
    try:
        b = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return ""
    L = [f"主角（整片不变）：{b.get('protagonist', '')}"]
    ch = b.get("character") or {}
    if isinstance(ch, dict) and ch.get("applies"):
        fixed = [str(ch.get(k) or "").strip() for k in ("who", "hair", "cloth", "scale")]
        fixed = [x for x in fixed if x]
        colors = [str(x) for x in (ch.get("colors") or []) if str(x).strip()]
        if fixed or colors:
            L.append("角色固定档案（同一角色所有批次必须一致，不许换发色/服装/主色）："
                     + "；".join(fixed + (["主色 " + " ".join(colors)] if colors else [])))
    stage = b.get("stage") or {}
    if isinstance(stage, dict) and str(stage.get("location") or "").strip():
        parts = [f"地点 {stage.get('location')}"]
        bg = [str(x).strip() for x in (stage.get("background") or []) if str(x).strip()]
        if bg:
            parts.append("背景 " + "、".join(bg))
        for key, label in (("light", "光"), ("camera", "机位")):
            if str(stage.get(key) or "").strip():
                parts.append(f"{label} {stage[key]}")
        L.append("固定舞台（整片不许换场）：" + "；".join(parts))
    cont = b.get("continuity")
    if isinstance(cont, list) and cont:
        L.append("连续性规则（每句都必须遵守）：" + "；".join(str(x) for x in cont if str(x).strip()))
    cast = b.get("cast")
    if isinstance(cast, list) and cast:
        rows = []
        for c in cast:
            if isinstance(c, dict):
                name = str(c.get("name") or "").strip()
                look = str(c.get("look") or "").strip()
                if not look:
                    look = "；".join(x for x in (
                        str(c.get("hair") or "").strip(),
                        str(c.get("outfit") or "").strip()) if x)
                colors = " ".join(str(x) for x in (c.get("colors") or []) if str(x).strip())
                note = str(c.get("note") or "").strip()
                if name or look:
                    rows.append(f"{name}（{look}" + (f"，{colors}" if colors else "")
                                + (f"；{note}" if note else "") + "）")
            elif str(c).strip():
                rows.append(str(c))
        if rows:
            L.append("固定配角（跨镜头一致）：" + "；".join(rows))
    locs = b.get("locations")
    if isinstance(locs, list) and locs:
        rows = []
        for x in locs:
            if isinstance(x, dict):
                name = str(x.get("name") or "").strip()
                look = str(x.get("look") or "").strip()
                light = str(x.get("light") or "").strip()
                props = "、".join(str(p) for p in (x.get("props") or []) if str(p).strip())
                if name or look:
                    rows.append(f"{name}（{look}；光 {light}" + (f"；道具 {props}" if props else "") + "）")
            elif str(x).strip():
                rows.append(str(x))
        if rows:
            L.append("固定场景（跨镜头一致）：" + "；".join(rows))
    arc = b.get("paletteArc") or []
    if arc:
        L.append("配色弧线（按段落承接，不许每段换一套）：")
        for x in arc:
            L.append(f"  {x.get('section', '')}：{' '.join(x.get('colors') or [])} — {x.get('mood', '')}")
    if b.get("motifs"):
        L.append("贯穿母题（每个段落至少出现一次，形式可变）：" + "；".join(b["motifs"]))
    if b.get("composition"):
        L.append("构图规则：" + str(b["composition"]))
    if b.get("motion"):
        L.append("运动规则：" + str(b["motion"]))
    if b.get("forbidden"):
        L.append("禁止：" + "；".join(b["forbidden"]))
    return "\n".join(L)


# ───────────────────── 叙事型：故事方向 / 蓝图 / 镜头表 ─────────────────────

STORY_VERSION = 1
STORY_SHOTS_PER_CALL = 3

_STORY_PITCH_SYS = """你是 MV 故事导演。读歌曲主题、歌词、编导方案和用户要求，提出 2~3 个完全不同的故事方向。
只输出 JSON：
{
 "candidates": [
   {"id": "a", "logline": "一句话故事", "tone": "情绪基调",
    "protagonist": "谁", "world": "时代/地点",
    "threeAct": "起：...；承：...；转：...；合：..."}
 ],
 "recommend": "a",
 "why": "为什么推荐它"
}

规则：
1. 只给 2~3 个，方向之间必须有真实差异（时代/人物/冲突/结构至少一项不同）。
2. 故事必须扣住歌曲主题与情绪，不要逐句解释歌词。
3. 控制在 1 个主角、2~4 个场景，能用手绘/图形画出来。
4. 不写与歌曲主题冲突的内容；brief 的优先级最高。
5. 只输出 JSON。
"""

_STORY_TREATMENT_SYS = """你是 MV 故事导演。把选定的故事方向扩写成可执行的故事蓝图。
只输出 JSON：
{
 "title": "故事标题",
 "logline": "一句话故事",
 "protagonist": "主角（外形/身份/目标）",
 "cast": ["配角1（外形/作用）"],
 "locations": ["场景1（外观/光）"],
 "acts": [{"name": "起", "sections": ["Verse 1"], "summary": "这一段发生什么"}],
 "beats": [{"id": "b1", "section": "Verse 1", "emotion": "情绪", "story": "故事动作", "anchor": false}],
 "shots": [
   {"id": "s1", "start": 0.0, "end": 8.5, "size": "wide|medium|close|empty",
    "camera": "push|pan|static|handheld", "cast": ["protagonist"],
    "location": "场景", "action": "画面里发生什么", "transition": "cut|match-cut|dissolve"}
 ]
}

硬性要求：
1. shots 必须从 0 连续铺满到 {DURATION}s，不能有空档/重叠；每个镜头 2~8 秒。
2. 镜头按故事节拍切，不按歌词句切；一个镜头可以跨多句歌词。
3. 3~5 个 anchor 镜头放在副歌/情绪高点，但不要逐句解释歌词。
4. 1 个主角、1~2 个配角、2~4 个场景；同一角色同一套服装。
5. 每个镜头写清景别、机位、角色、地点、动作；不要写抽象形容词。
6. 只输出 JSON。
"""

_STORY_BIBLE_SYS = """你是这支叙事 MV 的美术总监。故事蓝图已确认，现在定下全片视觉圣经。
只输出 JSON：
{
 "protagonist": "主角固定外形/服装/主色/比例",
 "character": {"applies": true, "who": "主角", "hair": "固定发型/发色", "cloth": "固定服装/配色",
               "colors": ["#RRGGBB"], "scale": "人物高度约占画面比例"},
 "cast": [{"name": "配角名", "look": "固定外形/服装", "colors": ["#RRGGBB"]}],
 "locations": [{"name": "场景名", "look": "外观/材质", "light": "光位/色调", "props": ["固定道具"]}],
 "paletteArc": [{"section": "段落名", "colors": ["#RRGGBB"], "mood": "情绪"}],
 "motifs": ["贯穿母题的物件"],
 "composition": "构图/镜头语言规则",
 "motion": "运动规则",
 "continuity": ["跨镜头必须保持什么"],
 "forbidden": ["禁止什么"]
}

规则：
1. paletteArc 覆盖每个段落，顺序一致。
2. 主角/配角/场景必须能落到 canvas 上，写清形状、颜色、比例。
3. 同一角色跨镜头不许换发色/服装/主色；同一场景不许换光位。
4. 不靠照片；不要写文字字幕。
5. 只输出 JSON。
"""

_STORY_SCENES_SYS = """你是 MV 分镜动画师。整片按**故事镜头**切，不按歌词句切。
歌词由引擎自动叠加；你只画镜头里的世界与动作。

输出一个 JS 文件（只要代码，不要 markdown 围栏、不要解释）：

MV.shots = [
  { start: 0.0, end: 8.5, bg: "#141A2E", camera(e){ ... }, draw(e){ ... } },
  ...
];

### 可用 API（运行时实时导出，未列出的不存在）
{API}

### 故事与镜头表
{STORY}

### 视觉圣经（全片统一）
{BIBLE}

### 铁律（违反会被闸门拦下）
1. draw 必须是 e.t 的**纯函数**：禁止 Math.random / Date.now / performance.now /
   setTimeout / requestAnimationFrame / 任何跨帧累积的外部变量。要随机用 e.rnd(seed)。
2. 每个 shot 的 start/end 必须与镜头表**完全一致**，不要改时间。
3. 镜头内动画用 `e.shotU`（0~1）、`e.shotT`（镜头内秒数）、`e.shotDur` 驱动；
   不要用 `e.i` / `e.line` 做分镜（那是歌词层）。
4. 角色/服装/场景/道具严格按视觉圣经，跨镜头保持一致；同一角色不许换脸/换衣服。
5. **不要画歌词/字幕**；顶部歌词带和底部安全区由引擎负责。构图避开 `e.lyricBox`。
6. 每个镜头都要有**看得见的运动**：主体位移/缩放/形变/光影漂移；
   0.5 秒内至少满足一条：位移 ≥ 画面宽 1.5%、缩放 ≥ 8%、透明度 ≥ 15%。
7. **禁止整帧亮度脉动**；节拍用位移/缩放/形变表达。
8. 镜头之间要有叙事推进（前→后变化），不要重复同一个构图；转场由画面动作带出。
9. 只画与故事相关的内容，不要为了贴合某一句歌词突然换世界。
10. MV.shots 条数必须严格等于镜头表条数。
"""

_STORY_BATCH_SYS = _STORY_SCENES_SYS + """
**本次只写指定的那几个镜头**：第一行先写一句摘要注释（供下一批衔接），
然后紧接着写恰好一行的代码：
/* 摘要：一句话说这批镜头讲了什么 */
MV.shotsPart = [ { start:..., end:..., draw(e){...} }, ... ];
条数必须等于本批镜头数，start/end 必须与镜头表一致。不要写 MV.shots，不要写其他字段。
"""


def _story_doc(w):
    try:
        d = json.loads((w / "story.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _shot_coverage_errors(shots, duration):
    """故事镜头覆盖度：从 0 连续铺满到 duration，不能空档/重叠。"""
    errs, clean = [], []
    for i, s in enumerate(shots or []):
        try:
            a, b = float(s.get("start")), float(s.get("end"))
        except (TypeError, ValueError):
            errs.append(f"第 {i + 1} 个镜头 start/end 不是数字")
            continue
        clean.append((a, b, i))
    if not clean:
        return errs or ["shots 为空"]
    clean.sort()
    if clean[0][0] > 0.05:
        errs.append(f"shots 从 {clean[0][0]:.2f}s 开始，没有覆盖片头 0s")
    prev = 0.0
    for a, b, i in clean:
        if b <= a:
            errs.append(f"第 {i + 1} 个镜头 start >= end")
            continue
        if a - prev > 0.05:
            errs.append(f"第 {i + 1} 个镜头与上一个之间有空档 {prev:.2f}→{a:.2f}s")
        elif prev - a > 0.05:
            errs.append(f"第 {i + 1} 个镜头与上一个重叠 {a:.2f}→{prev:.2f}s")
        prev = max(prev, b)
    if duration and abs(prev - duration) > 0.1:
        errs.append(f"shots 结束于 {prev:.2f}s，但歌曲时长 {duration:.2f}s")
    return errs


def _story_lyrics(w):
    try:
        f = w / "lyrics.txt"
        return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else ""
    except OSError:
        return ""


def st_story_pitch(w, tl, plan, brief, cfg, force=False):
    """生成 2~3 个故事方向，写 story.json（status=pitch）。"""
    p = w / "story.json"
    lyrics = _story_lyrics(w)
    sig = sha(brief or "", lyrics[:2000], ",".join(_type_sections(plan)))
    old = _story_doc(w)
    if p.exists() and not force and int(old.get("_v") or 0) >= STORY_VERSION \
            and old.get("_sig") == sig and old.get("status") in ("pitch", "treatment", "approved"):
        log("故事方向复用：story.json")
        return True, "复用", old

    ctx = (
        f"用户要求（最高优先级）：\n{brief or '（无额外要求）'}\n\n"
        f"歌曲：{tl.get('duration')}s，BPM {tl.get('bpm')}，段落 "
        f"{_type_sections(plan) or '未标注'}\n\n"
        "编导方案：\n" + json.dumps(plan, ensure_ascii=False) + "\n\n"
        "歌词：\n" + (lyrics[:4000] or "（无歌词）")
    )
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"story-pitch-prompt-{k}", c2)
            raw = _llm(_STORY_PITCH_SYS, c2, cfg, meta_label=f"story-pitch-{k}")
            dump(f"story-pitch-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"故事方向 第{k}次 ✗ {errs[0]}")
            continue

        errs = []
        cands = doc.get("candidates") if isinstance(doc.get("candidates"), list) else []
        cands = [c for c in cands if isinstance(c, dict) and str(c.get("id") or "").strip()]
        ids = [str(c.get("id")).strip() for c in cands]
        if not (2 <= len(cands) <= 3):
            errs.append(f"candidates 必须是 2~3 个，收到 {len(cands)}")
        if len(set(ids)) != len(ids):
            errs.append("candidates 的 id 必须唯一")
        for c in cands:
            for key in ("logline", "protagonist", "world"):
                if not str(c.get(key) or "").strip():
                    errs.append(f"候选 {c.get('id')} 缺 {key}")
        rec = str(doc.get("recommend") or "").strip()
        if rec and rec not in ids:
            errs.append(f"recommend={rec!r} 不在 candidates 里")
        if errs:
            log(f"故事方向 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        out = {
            "_v": STORY_VERSION, "status": "pitch", "candidates": cands[:3],
            "recommend": rec or ids[0], "why": str(doc.get("why") or "")[:300],
            "_sig": sig,
        }
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"故事方向完成（第 {k} 次）：{len(cands)} 个候选")
        return True, f"第{k}次", out
    return False, f"3 次不通过：{errs[:3]}", None


def st_story_treatment(w, tl, plan, brief, cfg, choice="", force=False):
    """把选中的故事方向扩写成蓝图与镜头表，写 story.json（status=treatment）。"""
    p = w / "story.json"
    doc = _story_doc(w)
    cands = doc.get("candidates") or []
    if not cands:
        return False, "没有故事方向，请先跑 stage=pitch", None
    pick = str(choice or doc.get("recommend") or cands[0].get("id")).strip()
    selected = next((c for c in cands if str(c.get("id")).strip() == pick), None)
    if not selected:
        return False, f"story_choice={pick!r} 不在候选里", None
    lyrics = _story_lyrics(w)
    sig = sha(pick, json.dumps(selected, ensure_ascii=False, sort_keys=True),
              brief or "", lyrics[:2000], ",".join(_type_sections(plan)))
    if (doc.get("status") in ("treatment", "approved") and doc.get("choice") == pick
            and doc.get("_sig") == sig and not force):
        log("故事蓝图复用：story.json")
        return True, "复用", doc

    dur = float(tl.get("duration") or 0)
    sys_prompt = _STORY_TREATMENT_SYS.replace("{DURATION}", f"{dur:.2f}")
    ctx = (
        f"用户要求（最高优先级）：\n{brief or '（无额外要求）'}\n\n"
        f"已选故事方向：\n" + json.dumps(selected, ensure_ascii=False, indent=2) + "\n\n"
        f"歌曲：{dur:.2f}s，BPM {tl.get('bpm')}，段落 {_type_sections(plan)}\n\n"
        "编导方案：\n" + json.dumps(plan, ensure_ascii=False) + "\n\n"
        "歌词：\n" + (lyrics[:4000] or "（无歌词）")
    )
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"story-treatment-prompt-{k}", c2)
            raw = _llm(sys_prompt, c2, cfg, meta_label=f"story-treatment-{k}")
            dump(f"story-treatment-raw-{k}", raw)
            body = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"故事蓝图 第{k}次 ✗ {errs[0]}")
            continue

        errs = []
        shots = body.get("shots") if isinstance(body.get("shots"), list) else []
        shots = [s for s in shots if isinstance(s, dict)]
        raw_cast = body.get("cast") if isinstance(body.get("cast"), list) else []
        raw_locs = body.get("locations") if isinstance(body.get("locations"), list) else []
        if not str(body.get("protagonist") or "").strip():
            errs.append("缺 protagonist")
        if not shots:
            errs.append("缺 shots")
        errs.extend(_shot_coverage_errors(shots, dur))
        for i, s in enumerate(shots):
            try:
                a, b = float(s.get("start")), float(s.get("end"))
                if b - a < 1.0 or b - a > 12.0:
                    errs.append(f"第 {i + 1} 个镜头时长 {b - a:.1f}s，需在 1~12s")
            except (TypeError, ValueError):
                pass
        if not raw_locs:
            errs.append("缺 locations")
        if errs:
            log(f"故事蓝图 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        shots.sort(key=lambda s: float(s.get("start") or 0))
        out = dict(doc)
        out.update({
            "_v": STORY_VERSION, "status": "treatment", "choice": pick,
            "direction": selected,
            "title": str(body.get("title") or selected.get("logline") or "未命名故事"),
            "logline": str(body.get("logline") or selected.get("logline") or ""),
            "protagonist": str(body.get("protagonist") or ""),
            "cast": [str(x) for x in raw_cast if str(x).strip()],
            "locations": [str(x) for x in raw_locs if str(x).strip()],
            "acts": [x for x in (body.get("acts") or []) if isinstance(x, dict)],
            "beats": [x for x in (body.get("beats") or []) if isinstance(x, dict)],
            "shots": shots,
            "_sig": sig,
        })
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"故事蓝图完成（第 {k} 次）：{len(shots)} 个镜头")
        return True, f"第{k}次", out
    return False, f"3 次不通过：{errs[:3]}", None


def st_story_bible(w, tl, plan, story, cfg, force=False):
    """生成叙事型视觉圣经（角色/配角/场景/连续性/配色/母题）。"""
    p = w / "visual-bible.json"
    pick = str(story.get("choice") or "")
    story_sig = sha(json.dumps(story, ensure_ascii=False, sort_keys=True))
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            old = {}
        if (old.get("_mode") == "narrative" and old.get("_story") == pick
                and old.get("_story_sig") == story_sig
                and not old.get("_style")
                and int(old.get("_v") or 0) >= BIBLE_VERSION):
            log("叙事视觉圣经复用：visual-bible.json")
            return True, "复用"

    ctx = (
        "故事蓝图（必须落实）：\n" + json.dumps(story, ensure_ascii=False, indent=2) + "\n\n"
        f"全片时长 {tl.get('duration')}s，BPM {tl.get('bpm')}\n\n"
        "【不做画风预设】只写故事事实：角色造型特征、场景、时间与光线、"
        "跨镜头必须一致的元素。不要规定笔触/材质/画风名。\n"
    )
    need = _type_sections(plan)
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"story-bible-prompt-{k}", c2)
            raw = _llm(_STORY_BIBLE_SYS, c2, cfg, meta_label=f"story-bible-{k}")
            dump(f"story-bible-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"叙事圣经 第{k}次 ✗ {errs[0]}")
            continue

        errs = []
        if not str(doc.get("protagonist") or "").strip():
            errs.append("缺 protagonist")
        arc = doc.get("paletteArc") if isinstance(doc.get("paletteArc"), list) else []
        have = {str(a.get("section") or "").strip() for a in arc if isinstance(a, dict)}
        if set(need) - have:
            errs.append(f"paletteArc 缺少段落：{sorted(set(need) - have)}")
        if not isinstance(doc.get("motifs"), list) or not doc["motifs"]:
            errs.append("motifs 必须是非空数组")
        if not str(doc.get("composition") or "").strip() or not str(doc.get("motion") or "").strip():
            errs.append("缺 composition / motion")
        locs = doc.get("locations") if isinstance(doc.get("locations"), list) else []
        if not locs:
            errs.append("缺 locations")
        if errs:
            log(f"叙事圣经 第{k}次 ✗ {'；'.join(errs[:3])}")
            continue

        doc["_style"] = ""
        doc["_mode"] = "narrative"
        doc["_story"] = pick
        doc["_story_sig"] = story_sig
        doc["_v"] = BIBLE_VERSION
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"叙事视觉圣经完成（第 {k} 次）")
        return True, f"第{k}次"
    return False, f"3 次不通过：{errs[:3]}"


def _story_prompt_text(story):
    L = [f"故事：{story.get('title') or ''}｜{story.get('logline') or ''}",
         f"主角：{story.get('protagonist') or ''}"]
    if story.get("cast"):
        L.append("配角：" + "；".join(str(x) for x in story["cast"]))
    if story.get("locations"):
        L.append("场景：" + "；".join(str(x) for x in story["locations"]))
    L.append("镜头表：")
    for s in story.get("shots") or []:
        L.append(
            f"- {s.get('id')}｜{float(s.get('start', 0)):.2f}~{float(s.get('end', 0)):.2f}s｜"
            f"{s.get('size', '')}｜{s.get('camera', '')}｜{s.get('location', '')}｜"
            f"{s.get('action', '')}｜{s.get('transition', '')}"
        )
    return "\n".join(L)


def _story_batch_text(shots, idxs):
    rows = []
    for i in idxs:
        s = shots[i]
        rows.append(
            f"- 镜头 {i + 1}（id={s.get('id')}）：{float(s.get('start', 0)):.2f}~"
            f"{float(s.get('end', 0)):.2f}s｜景别 {s.get('size', '')}｜机位 {s.get('camera', '')}｜"
            f"地点 {s.get('location', '')}｜角色 {', '.join(s.get('cast') or [])}｜"
            f"动作 {s.get('action', '')}｜转场 {s.get('transition', '')}"
        )
    return "\n".join(rows)


def st_story_scenes(w, st, tl, plan, story, cfg, force=False,
                    only_batches=None, review_notes=None):
    """生成叙事型的 MV.shots（按故事镜头分批），过闸门后写 scenes.js。
    only_batches 给定时只重写这些批次（1 基），其余批次复用。"""
    p = w / "scenes.js"
    sig = sha(w / "story.json", w / "visual-bible.json", w / "plan.json", "narrative")
    marker = w / "scenes.story.txt"
    same = marker.exists() and marker.read_text(encoding="utf-8").strip() == sig
    if p.exists() and same and not force and not only_batches:
        log("叙事画面复用：scenes.js")
        return True, "复用", p

    shots = story.get("shots") or []
    if not shots:
        return False, "故事蓝图没有镜头表", None
    parts = w / "parts"
    parts.mkdir(exist_ok=True)
    # 故事/圣经/编导变了：旧镜头批必须作废，否则会拿上一版镜头拼进新故事
    if not same and not force and not only_batches:
        for f in parts.glob("shots-b*.js"):
            f.unlink(missing_ok=True)
    if only_batches:
        for bi in only_batches:
            (parts / f"shots-b{bi}.js").unlink(missing_ok=True)
    api = _api_spec_text(w)
    bible = _bible_text(w)
    story_text = _story_prompt_text(story)
    fallback_api = "（清单导出失败：只用 e.sh / e.drawText / e.bg / e.rnd / e.screen / e.layer）"
    sys_base = (_STORY_BATCH_SYS.replace("{API}", api or fallback_api)
                .replace("{STORY}", story_text)
                .replace("{BIBLE}", bible))

    batches = [list(range(i, min(i + STORY_SHOTS_PER_CALL, len(shots))))
               for i in range(0, len(shots), STORY_SHOTS_PER_CALL)]
    for bi, idxs in enumerate(batches, 1):
        if only_batches is not None and bi not in only_batches:
            continue
        fp = parts / f"shots-b{bi}.js"
        if fp.exists() and not force and not only_batches:
            log(f"  镜头批 {bi}/{len(batches)} 复用")
            continue
        ctx = (f"本批只写镜头 " + "、".join(str(i + 1) for i in idxs) +
               f"（共 {len(idxs)} 个），start/end 必须与镜头表一致：\n" +
               _story_batch_text(shots, idxs))
        if bi > 1:
            ctx += "\n\n上一批镜头结束时的画面状态请自然承接，不要重新起世界。"
        if review_notes and bi in review_notes:
            ctx += ("\n\n上一版这几帧被指出问题，针对性修正（不要改 start/end）：\n"
                    + "\n".join(review_notes[bi]))
        times = ",".join(f"{(float(shots[i].get('start', 0)) + float(shots[i].get('end', 0))) / 2:.3f}"
                         for i in idxs)
        rt = {"total": len(shots), "kind": "shots", "times": times}
        log(f"  镜头批 {bi}/{len(batches)} 生成中...")
        js = _ask(f"shots-b{bi}", sys_base, ctx, cfg, w, rt=rt, tries=3)
        if js is None:
            return False, f"镜头批 {bi} 未通过", None
        fp.write_text(js, encoding="utf-8")

    def assemble():
        pieces = []
        for b in range(1, len(batches) + 1):
            pieces.append((parts / f"shots-b{b}.js").read_text(encoding="utf-8")
                          .replace("MV.shotsPart", f"_s{b}"))
        return "\n".join(pieces) + "\nMV.shots = [" + \
            ",".join(f"..._s{b}" for b in range(1, len(batches) + 1)) + "];\n"

    try_js = w / "_shots_try.js"
    gate_plan = w / "_plan_gate.json"

    def gate_all(js):
        try_js.write_text(js, encoding="utf-8")
        gp = dict(plan)
        gp["_story_ranges"] = [[float(s.get("start", 0)), float(s.get("end", 0))]
                               for s in shots]
        gate_plan.write_text(json.dumps(gp, ensure_ascii=False, indent=2), encoding="utf-8")
        r = None
        out = ""
        try:
            r = sh([sys.executable, str(HERE / "render.py"), "--engine", str(ENGINE),
                    "--timeline", w / "timeline.json", "--plan", gate_plan,
                    "--scenes", try_js, "--gate-only"], cwd=HERE, stream=True)
            out = (r.stdout or "") + (r.stderr or "")
        finally:
            try_js.unlink(missing_ok=True)
            gate_plan.unlink(missing_ok=True)
        return (r.returncode == 0 if r is not None else False), out

    out_text = ""
    for rnd in range(2):
        assembled = assemble()
        ok, out_text = gate_all(assembled)
        if ok:
            p.write_text(assembled, encoding="utf-8")
            marker.write_text(sig, encoding="utf-8")
            log(f"  叙事镜头已组装：{len(shots)} 个 → {p.name}")
            return True, f"{len(batches)}批", p
        # 按报错时刻定位镜头批次，重写最多两批
        bad = []
        for t in _gate_bad_times(out_text):
            idx = next((i for i, s in enumerate(shots)
                        if float(s.get("start", 0)) <= t <= float(s.get("end", 0))), None)
            if idx is not None:
                bi = idx // STORY_SHOTS_PER_CALL
                if bi not in bad:
                    bad.append(bi)
        if not bad:
            break
        errs = [l.strip(" -") for l in out_text.splitlines() if l.strip().startswith("-")]
        for bi in bad[:2]:
            (parts / f"shots-b{bi + 1}.js").unlink(missing_ok=True)
            ctx = (f"上次闸门报错：{'；'.join(errs[:2])}\n"
                   f"只重写镜头 " + "、".join(str(i + 1) for i in batches[bi]) +
                   "，start/end 不变：\n" + _story_batch_text(shots, batches[bi]))
            times = ",".join(
                f"{(float(shots[i].get('start', 0)) + float(shots[i].get('end', 0))) / 2:.3f}"
                for i in batches[bi])
            js = _ask(f"shots-b{bi+1}", sys_base, ctx, cfg, w,
                      rt={"total": len(shots), "kind": "shots", "times": times}, tries=2)
            if js is None:
                return False, f"镜头批 {bi + 1} 修复失败", None
            (parts / f"shots-b{bi + 1}.js").write_text(js, encoding="utf-8")
    return False, "镜头闸门未通过：" + (out_text[-300:] or ""), None


# ───────────────────── 可选：段落氛围底图（AI 插画层） ─────────────────────

def _image_cfg():
    """图片生成配置由工具通过环境变量传入（不进 argv、不进日志）。"""
    raw = os.environ.get("LYRIC_MV_IMAGE", "")
    if not raw:
        return None
    try:
        cfg = json.loads(raw)
    except Exception:
        return None
    if not isinstance(cfg, dict) or not str(cfg.get("api_key") or "").strip():
        return None
    return cfg


def _bible_doc(w):
    try:
        return json.loads((w / "visual-bible.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _section_order(tl):
    """按歌词出现顺序列出段落名（用于给每段配一张底图）。"""
    names = []
    for L in tl.get("lines") or []:
        name = str(L.get("section") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _image_style_prefix(style_id=None):
    """生图用的美术方向：不再从风格库派生，交给视觉圣经。"""
    return ""


def ensure_section_images(w, tl, plan, max_images):
    """按段落生成氛围底图，写入 plan['assets'] 与 plan['imageSections']。

    返回可用 key 列表；未配置图片 Key / 生成失败都只是跳过，不影响成片。
    """
    cfg = _image_cfg()
    if not cfg:
        log("⚠ 未配置图片生成 Key：跳过 AI 底图，画面全部用 canvas 绘制")
        return []

    from skills import image_assets
    from skills.image_generate import ImageGenerateTool

    vs = ""   # 不再有预设画风
    names = _section_order(tl)
    limit = max(0, int(max_images or 0))
    names = names[:limit]
    if not names:
        return []

    themes = {str(s.get("name") or "").strip(): str(s.get("theme") or "")
              for s in (plan.get("sections") or [])}
    bible = _bible_doc(w)
    moods = {str(a.get("section") or "").strip(): str(a.get("mood") or "")
             for a in (bible.get("paletteArc") or [])}
    protagonist = str(bible.get("protagonist") or "").strip()
    motifs = "；".join(str(x).strip() for x in (bible.get("motifs") or []) if str(x).strip())
    ch = bible.get("character") or {}
    character = ""
    if isinstance(ch, dict) and ch.get("applies"):
        character = "；".join(
            str(ch.get(k) or "").strip() for k in ("who", "hair", "cloth", "scale")
            if str(ch.get(k) or "").strip())

    prefix = _image_style_prefix()
    canvas = tl.get("canvas") or {}
    aspect = image_assets.normalize_aspect(
        f"{canvas.get('width', 1280)}x{canvas.get('height', 720)}")
    assets_dir = w / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # 风格/段落变了或图片数量变了：旧底图全部作废，避免串风格
    old_sections = [str(x.get("section") or "") for x in (plan.get("imageSections") or [])]
    if (plan.get("imageStyle") or "") != vs or old_sections != names:
        for old in assets_dir.glob("sec_*"):
            try:
                old.unlink()
            except OSError:
                pass
        plan.pop("assets", None)
        plan.pop("imageSections", None)

    tool = ImageGenerateTool(
        cwd=str(ROOT),
        api_key=str(cfg.get("api_key") or ""),
        base_url=str(cfg.get("base_url") or ""),
        default_model=str(cfg.get("model") or ""),
        provider=str(cfg.get("provider") or "ark"),
    )
    assets, sections = {}, []
    for i, name in enumerate(names):
        key = f"sec_{i}"
        existing = next(iter(assets_dir.glob(f"{key}.*")), None)
        if existing and existing.stat().st_size > 0:
            assets[key] = str(existing.resolve())
            sections.append({"key": key, "section": name, "theme": themes.get(name, "")})
            log(f"  · 段落底图复用：{key}（{name}）")
            continue

        prompt = (
            f"为本片段落「{name}」画一张氛围底图。"
            f"段落主题：{themes.get(name) or '按歌词情绪'}；情绪：{moods.get(name) or ''}。"
            f"视觉主体（全片一致）：{protagonist}。贯穿母题：{motifs}。"
            + (f"固定角色（发型/服装/比例必须一致）：{character}。" if character else "")
            + "这是背景/氛围层：不要出现文字、字幕、UI、logo、可辨识真人正脸；"
              "主体偏一侧，画面中部与四周留给前景图形与歌词安全区，边缘可虚化。"
        )
        log(f"  · 生成段落底图 {key}（{name}）...")
        res = tool.execute(
            prompt=image_assets.build_prompt(prompt, prefix),
            save_dir=str(assets_dir),
            size=image_assets.api_size(aspect, cfg.get("provider", "")),
            watermark=False,
        )
        if not getattr(res, "success", False):
            log(f"  ⚠ {key} 生成失败，跳过：{str(getattr(res, 'content', ''))[:120]}")
            continue
        src = Path(str((getattr(res, "details", {}) or {}).get("filepath") or ""))
        if not src.is_file():
            log(f"  ⚠ {key} 返回的图片路径无效，跳过")
            continue
        dst = assets_dir / f"{key}{src.suffix.lower() or '.png'}"
        try:
            if dst.exists():
                dst.unlink()
            src.replace(dst)
        except OSError as e:
            log(f"  ⚠ {key} 落盘失败，跳过：{e}")
            continue
        assets[key] = str(dst.resolve())
        sections.append({"key": key, "section": name, "theme": themes.get(name, "")})
        log(f"  ✓ 段落底图 {key} → {dst.name}")

    # 无论成功几张都写回：避免旧 plan 里残留已失效的 assets 路径
    plan["assets"] = assets
    plan["imageSections"] = sections
    plan["imageStyle"] = vs
    (w / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return sorted(assets)


def _scene_image_block(plan):
    """把可用底图 key 写进画面提示词，让 LLM 知道能用哪些、怎么用。"""
    assets = plan.get("assets") or {}
    rows = []
    for item in (plan.get("imageSections") or []):
        key = str(item.get("key") or "")
        if key and key in assets:
            theme = str(item.get("theme") or "").strip()
            rows.append(f"- 段落「{item.get('section')}」→ `e.drawImg(\"{key}\", ...)`"
                        + (f"（{theme}）" if theme else ""))
    if not rows:
        return "（本片未启用 AI 底图：画面全部用 canvas 图形绘制。）"
    return (
        "本片为每个段落准备了氛围底图，只能当**背景/氛围层**：\n"
        + "\n".join(rows) + "\n"
        "- 用法：`e.drawImg(\"sec_0\", x, y, w, h, {mode:\"cover\", alpha:0.5~0.9})`；"
        "图片必须参与运动（视差/横移/缩放），禁止整段钉死。\n"
        "- 叙事主体仍必须用 canvas 图形 / e.actor 画，底图不能替代主体；\n"
        "- 只使用本句所属段落对应的那张；未列出的 key 不存在。"
    )


# ───────────────────── 截图自查 → 有界重写闭环 ─────────────────────

def _line_at_time(tl, t):
    lines = tl.get("lines") or []
    if not lines or t is None:
        return None
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    for i, L in enumerate(lines):
        if float(L.get("start", 0)) <= t <= float(L.get("end", 0)):
            return i
    mids = [(float(L.get("start", 0)) + float(L.get("end", 0))) / 2 for L in lines]
    return min(range(len(lines)), key=lambda i: abs(mids[i] - t))


def review_notes_by_line(w, tl):
    """把 review.json 里低分帧的问题映射到歌词行号，供按批重写。"""
    f = w / "review.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    notes = {}
    for row in (doc.get("frames") or []):
        score = row.get("score")
        if not isinstance(score, (int, float)) or score > REVIEW_SCORE_FLOOR:
            continue
        issue = [str(x).strip() for x in (row.get("issues") or []) if str(x).strip()]
        fix = str(row.get("fix") or "").strip()
        if not issue and not fix:
            continue
        idx = _line_at_time(tl, row.get("t"))
        if idx is None:
            continue
        notes.setdefault(idx, [])
        notes[idx].extend(issue[:2] + ([fix] if fix else []))
    return {i: list(dict.fromkeys(v))[:3] for i, v in notes.items()}


def review_notes_by_shot(w):
    """把 review.json 里低分帧的问题映射到故事镜头批，供按批重写。"""
    f = w / "review.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}
    shots = _story_doc(w).get("shots") or []
    if not shots:
        return {}
    notes = {}
    for row in (doc.get("frames") or []):
        score = row.get("score")
        if not isinstance(score, (int, float)) or score > REVIEW_SCORE_FLOOR:
            continue
        issue = [str(x).strip() for x in (row.get("issues") or []) if str(x).strip()]
        fix = str(row.get("fix") or "").strip()
        if not issue and not fix:
            continue
        t = row.get("t")
        if not isinstance(t, (int, float)):
            continue
        idx = next((i for i, s in enumerate(shots)
                    if float(s.get("start", 0)) <= t <= float(s.get("end", 0))), None)
        if idx is None:
            continue
        bi = idx // STORY_SHOTS_PER_CALL
        notes.setdefault(bi, [])
        notes[bi].extend([f"第 {idx + 1} 个镜头"] + issue[:2] + ([fix] if fix else []))
    return {b: list(dict.fromkeys(v))[:4] for b, v in notes.items()}


def _type_sections_from_lines(lines):
    out, seen = [], set()
    for L in lines:
        name = str(L.get("section") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def st_type_shortlist(w, tl, plan, brief, cfg, force=False):
    """让 LLM 从 6 种字效里筛 2~4 个候选，供字效样片使用。"""
    p = w / "type-shortlist.json"
    lyrics = _story_lyrics(w)
    sig = sha(brief or "", lyrics[:2000], ",".join(_type_sections(plan)),
              str(tl.get("duration")))
    if p.exists() and not force:
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            picks = [x for x in (old.get("styles") or [])
                     if isinstance(x, dict) and type_styles.get(x.get("id"))]
            if old.get("_sig") == sig and 2 <= len(picks) <= 4:
                log("字效候选复用：" + "、".join(str(x["id"]) for x in picks))
                return picks
        except Exception:
            pass
    ctx = _ctx_common(tl, brief)[0]
    sysp = _TYPE_SHORTLIST_SYS.replace("{TYPE_MENU}", type_styles.menu())
    errs = []
    for k in (1, 2, 3):
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            raw = _llm(sysp, c2, cfg, meta_label=f"type-shortlist-{k}")
            dump(f"type-shortlist-raw-{k}", raw)
            doc = _json_of(raw)
        except Exception as e:
            errs = [f"JSON 解析失败：{e}"]
            log(f"字效筛选 第{k}次 ✗ {errs[0]}")
            continue
        picks, seen = [], set()
        for x in (doc.get("styles") or []):
            if not isinstance(x, dict):
                continue
            tid = str(x.get("id") or "").strip()
            if type_styles.get(tid) and tid not in seen:
                seen.add(tid)
                picks.append({"id": tid, "why": str(x.get("why") or "").strip()})
        if len(picks) > 4:
            picks = picks[:4]
        if len(picks) < 2:
            errs = [f"只给了 {len(picks)} 个，必须 2~4 个"]
            log(f"字效筛选 第{k}次 ✗ {errs[0]}")
            continue
        (w / "type-shortlist.json").write_text(json.dumps(
            {"_sig": sig, "styles": picks, "summary": str(doc.get("summary") or "")},
            ensure_ascii=False, indent=2), encoding="utf-8")
        log("字效候选：" + "、".join(f"{x['id']}（{x['why'][:18]}）" for x in picks))
        return picks
    fallback = [{"id": i, "why": "（筛选失败，默认候选）"} for i in type_styles.ids()[:3]]
    log("⚠ 字效筛选 3 次未通过，回落为默认 3 种")
    return fallback


def _type_sample_plan(mini, title):
    return {
        "title": title or "字效样片", "subtitle": "",
        "lyricStyle": "band",
        "plain": True, "lyrics_layer": "none",
        "chrome": {"section": "hide", "progress": "hide"},
        "sections": [{"name": s} for s in _type_sections_from_lines(mini["lines"])],
    }


def _type_emph_ranges(text, picks):
    """把重点片段（原文子串）换算成字符区间，重叠的合并。"""
    spans = []
    for pick in (picks or []):
        s = str(pick or "").strip()
        if not s:
            continue
        start = text.find(s)
        if start >= 0:
            spans.append([start, start + len(s)])
    spans.sort()
    out = []
    for a, b in spans:
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _type_role_color(role, bg, fg, accent):
    return {"bg": bg, "fg": fg, "accent": accent}.get(str(role or "").strip(), "")


def _type_preview_scenes(mini, tid, emph=None):
    t = type_styles.get(tid) or {}
    pv = t.get("preview") or {}
    ek = t.get("emphasis") or {}
    bg = pv.get("bg", "#111318")
    fg = pv.get("fg", "#F4EFE4")
    accent = pv.get("accent", "#E9A63B")
    dark = bool(pv.get("dark", True))
    align = pv.get("align", "center")
    rows = int(pv.get("rows", 2))
    chorus_rows = int(pv.get("chorus_rows", rows))
    block = pv.get("block", "")
    every = int(pv.get("accent_every", 0))
    rise = float(pv.get("rise", 22))
    lead = float(pv.get("leading", 1.1))
    font = t.get("font") or '"Microsoft YaHei","PingFang SC",sans-serif'
    weight = int(t.get("weight", 900))
    out = [_TYPE_PREVIEW_JS, "MV.scenes = ["]
    for idx, L in enumerate(mini["lines"]):
        sec = str(L.get("section") or "")
        r = chorus_rows if "Chorus" in sec else rows
        b = block if ("Chorus" in sec and block) else ""
        text = str(L.get("text") or "")
        picks = (emph or {}).get(L.get("idx")) or []
        emp_js = []
        for a, bb in _type_emph_ranges(text, picks):
            emp_js.append({
                "a": a, "b": bb,
                "scale": float(ek.get("scale") or 1.0),
                "fill": _type_role_color(ek.get("fill"), bg, fg, accent),
                "block": _type_role_color(ek.get("block"), bg, fg, accent),
                "weight": int(ek.get("weight") or weight),
                "glow": float(ek.get("glow") or 0.0),
                "underline": bool(ek.get("underline")),
            })
        out.append(
            f'  {{ bg: {json.dumps(bg)}, draw(e) {{ '
            f'tBg(e, {json.dumps(accent)}, {str(dark).lower()}, {json.dumps(f"{idx+1:02d}")}); '
            f'tType(e, {json.dumps(text, ensure_ascii=False)}, {{ '
            f'align: {json.dumps(align)}, rows: {r}, block: {json.dumps(b) if b else "null"}, '
            f'fill: {json.dumps(fg)}, accent: {json.dumps(accent)}, '
            f'accentEvery: {every}, rise: {rise}, leading: {lead}, '
            f'emph: {json.dumps(emp_js, ensure_ascii=False)}, '
            f'font: {json.dumps(font)}, weight: {weight} }}); }} }},'
        )
    out.append("];")
    out.append(
        f'MV.filler = {{ bg: {json.dumps(bg)}, '
        f'draw(e) {{ tBg(e, {json.dumps(accent)}, {str(dark).lower()}, ""); }} }};'
    )
    return "\n".join(out)


def _type_samples_html(items, start, end, mini):
    win = f"{start:.1f}s – {end:.1f}s"
    cards = []
    for it in items:
        t = type_styles.get(it["sid"]) or {}
        if not it.get("b64"):
            body = f'<div class="fail">这一版没跑出来：{it.get("note", "")}</div>'
        else:
            body = (f'<video src="data:video/mp4;base64,{it["b64"]}" '
                    f'autoplay muted loop playsinline controls></video>')
        cards.append(f"""
  <div class="card" data-id="{it['sid']}">
    <div class="cap"><b>{t.get('label', it['sid'])}</b><span>{it['sid']}</span></div>
    {body}
    <div class="meta">
      {f'<p class="why"><i>为什么给它</i>{it["why"]}</p>' if it.get("why") else ''}
      <p><i>适合</i>{'、'.join(t.get('use_for') or [])}</p>
      <p><i>不适合</i>{'、'.join(t.get('avoid_for') or [])}</p>
    </div>
    <button onclick="pick('{it['sid']}','{t.get('label', it['sid'])}')">选这个字效</button>
  </div>""")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>字效样片 · {win}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:24px; background:#0d1117; color:#e6edf3;
         font:14px/1.6 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }}
  h1 {{ font-size:18px; margin:0 0 4px; }}
  .sub {{ color:#8b949e; margin:0 0 18px; font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:10px;
           padding:12px; transition:border-color .15s; }}
  .card.on {{ border-color:#e9a63b; box-shadow:0 0 0 1px #e9a63b inset; }}
  .cap {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }}
  .cap b {{ font-size:16px; }}
  .cap span {{ color:#8b949e; font-size:12px; }}
  video {{ width:100%; aspect-ratio:16/9; background:#000; border-radius:6px; display:block; }}
  .meta p {{ margin:6px 0 0; font-size:12px; color:#b8c4d0; }}
  .meta i {{ font-style:normal; color:#6e7681; margin-right:6px; }}
  .meta .why {{ color:#e9c98a; }}
  button {{ margin-top:10px; width:100%; padding:8px; border-radius:6px; cursor:pointer;
            border:1px solid #30363d; background:#21262d; color:#e6edf3; font-size:13px; }}
  button:hover {{ border-color:#e9a63b; color:#e9a63b; }}
  .fail {{ aspect-ratio:16/9; display:flex; align-items:center; justify-content:center;
           background:#1a1f27; border-radius:6px; color:#f0883e; font-size:12px; padding:12px; }}
  #picked {{ margin:0 0 14px; padding:10px 12px; border-radius:8px; display:none;
             background:#1f2a1f; border:1px solid #3fb950; color:#7ee787; }}
</style></head><body>
<h1>同一段歌词 · {len(items)} 种字效</h1>
<p class="sub">{mini.get('bpm', 0):.0f} BPM｜样片区间 {win}｜文字即画面，无独立歌词层</p>
<div id="picked"></div>
<div class="grid">{''.join(cards)}</div>
<script>
function pick(id, label) {{
  document.querySelectorAll('.card').forEach(c => c.classList.toggle('on', c.dataset.id === id));
  const box = document.getElementById('picked');
  box.style.display = 'block';
  box.textContent = '已选：' + label + '。回到对话里说「用' + label + '字效」。';
}}
</script></body></html>"""


def st_type_samples(w, tl, plan, brief, cfg, song, fps, force=False, html_dir=None):
    """文字类：先筛 2~4 种字效，各渲 10 秒样片，再生成对比页。
    返回 (ok, note, html_path, shown_ids)。"""
    root = w / "type-samples"
    root.mkdir(exist_ok=True)
    picks = st_type_shortlist(w, tl, plan, brief, cfg, force)
    if not picks:
        return False, "没有可用的字效候选", None, []
    start, end, idxs = _sample_window(tl)
    if not idxs:
        return False, "没找到可用的歌词窗口", None, []
    log(f"字效样片窗口 {start:.1f}~{end:.1f}s｜第 {idxs[0]}~{idxs[-1]} 句，"
        f"渲染 {len(picks)} 种字效")
    mini = _slice_timeline(tl, start, end, "clip.wav", keep=idxs)
    emph = _type_emphasis_map(w)
    if emph:
        log(f"样片重点标注：{sum(len(v) for v in emph.values())} 处")
    clip = root / "clip.wav"
    if force or not clip.exists():
        r = sh(["ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
                "-i", str(song), "-ac", "1", "-ar", "44100", str(clip)])
        if not clip.exists():
            return False, f"切样片音频失败：{(r.stderr or '')[-200:]}", None, []
    (root / "timeline.json").write_text(
        json.dumps(mini, ensure_ascii=False, indent=2), encoding="utf-8")

    items = []
    for pick in picks:
        tid = str(pick.get("id") or "").strip()
        if not type_styles.get(tid):
            continue
        sub = root / tid
        sub.mkdir(exist_ok=True)
        (sub / "timeline.json").write_text(
            json.dumps(mini, ensure_ascii=False, indent=2), encoding="utf-8")
        (sub / "plan.json").write_text(
            json.dumps(_type_sample_plan(mini, type_styles.label(tid)),
                       ensure_ascii=False, indent=2), encoding="utf-8")
        js = _type_preview_scenes(mini, tid, emph)
        old_js = ""
        try:
            old_js = (sub / "scenes.js").read_text(encoding="utf-8")
        except OSError:
            pass
        changed = old_js != js
        (sub / "scenes.js").write_text(js, encoding="utf-8")
        label = type_styles.label(tid)
        mp4 = sub / "sample.mp4"
        if mp4.exists() and not force and not changed:
            log(f"  字效样片 {label} 复用")
        else:
            log(f"  字效样片 {label} 渲染中...")
            r = sh([sys.executable, str(HERE / "render.py"),
                    "--engine", str(ENGINE),
                    "--timeline", str(sub / "timeline.json"),
                    "--plan", str(sub / "plan.json"),
                    "--scenes", str(sub / "scenes.js"),
                    "--audio", str(clip), "--out", str(mp4),
                    "--fps", str(fps)], cwd=HERE, stream=True)
            if r.returncode != 0 or not mp4.exists():
                items.append({"sid": tid, "why": pick.get("why", ""),
                              "note": "渲染/闸门未通过"})
                continue
        web = sub / "web.mp4"
        if force or not web.exists():
            if not _web_mp4(mp4, web):
                web = mp4
        try:
            b64 = base64.b64encode(web.read_bytes()).decode("ascii")
        except Exception as e:
            items.append({"sid": tid, "why": pick.get("why", ""),
                          "note": f"读取视频失败：{e}"})
            continue
        items.append({"sid": tid, "why": pick.get("why", ""), "b64": b64})
        log(f"  字效样片 {label} 完成（{mp4.stat().st_size / 1048576:.1f} MB）")

    shown = [i["sid"] for i in items if i.get("b64")]
    if not shown:
        return False, "候选字效都没有跑出样片", None, []
    html = _type_samples_html(items, start, end, mini)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = Path(html_dir) if html_dir else w
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"type-samples-{stamp}-{sha(str(start), str(end), *shown)}.html"
    p.write_text(html, encoding="utf-8")
    log(f"字效对比页已生成：{p}")
    return True, f"{len(shown)}/{len(items)} 版可用", p, shown


# ───────────────────── 截图自查（视觉模型回看） ─────────────────────

_REVIEW_PROMPT = """这是一支歌词 MV 的一帧截图（画面里的歌词与顶部标签是引擎自动加的，不用评价）。
请只做美术审查，直接指出问题，不要客套：
1) 主体是否一眼可辨，还是只剩色块/空景？
2) 构图是否空旷、主体是否被歌词带压住？
3) 元素是否互相遮挡、比例是否明显失真？
4) 有没有明显瑕疵（文字乱码、重复图案、硬边、颜色过曝）？
只输出 JSON：{"score": 0-10, "issues": ["最多 3 条具体问题"], "fix": "一句可执行的修改建议"}
没有问题就 issues 为空、score 给 8~10。"""

_REVIEW_MODE_RULES = {
    "performance": (
        "\n这是表演型 MV：额外检查舞台/背景/光位/表演者是否前后一致；"
        "突然换场景、换主体或换服装属于严重问题，写进 issues。"
    ),
    "narrative": (
        "\n这是叙事型 MV：额外检查角色/服装/场景是否跨镜头一致，故事是否看得懂。"
    ),
    "typographic": (
        "\n这是文字类 MV：额外检查文字是否清晰可读、是否超出画面或被遮挡、"
        "阅读速度是否跟得上演唱；重复叠字、字挤成一团、文字被背景吞掉属于严重问题。"
    ),
}


def _review_times(w, tl, n=8, mode="performance"):
    if mode == "narrative":
        story = _story_doc(w)
        shots = story.get("shots") or []
        if shots:
            step = max(1, len(shots) // n)
            return [round((float(s.get("start", 0)) + float(s.get("end", 0))) / 2, 3)
                    for s in shots[::step]][:n]
    lines = tl.get("lines") or []
    if not lines:
        return []
    step = max(1, len(lines) // n)
    return [round((L["start"] + L["end"]) / 2, 3) for L in lines[::step]][:n]


def _frame_b64(p, max_side=1024):
    """压成 JPEG 再送视觉接口：整幅 PNG 一张 1~2MB，直接 base64 容易超限。"""
    try:
        from PIL import Image
        im = Image.open(p)
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=82)
        return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"
    except Exception:
        return base64.b64encode(Path(p).read_bytes()).decode("ascii"), "image/png"


def st_review(w, tl, plan, cfg, scenes_js, n=8, tag="review", mode="performance"):
    """截图自查：抽帧 → 视觉模型审 → <tag>.json。
    非致命：模型不支持看图 / 接口失败，都只记一笔并跳过。"""
    out_dir = w / "review"
    times = _review_times(w, tl, n, mode=mode)
    if not times:
        return False, "无歌词"
    log(f"  抽 {len(times)} 帧...")
    r = sh([sys.executable, str(HERE / "render.py"), "--engine", str(ENGINE),
            "--timeline", str(w / "timeline.json"), "--plan", str(w / "plan.json"),
            "--scenes", str(scenes_js), "--shots", ",".join(f"{t:.3f}" for t in times),
            "--shots-out", str(out_dir)], cwd=HERE)
    frames = sorted(out_dir.glob("f_*.png"))
    if r.returncode != 0 or not frames:
        return False, "抽帧失败"
    try:
        from skills.image_reader import describe_image_b64
    except Exception as e:
        return False, f"看图模块不可用：{e}"
    rows = []
    review_prompt = _REVIEW_PROMPT + _REVIEW_MODE_RULES.get(mode, "")
    for i, f in enumerate(frames):
        b64, mime = _frame_b64(f)
        try:
            txt = describe_image_b64(b64, mime, review_prompt, cfg, timeout=90)
        except Exception as e:
            log(f"  自查跳过：视觉接口不可用（{type(e).__name__}）")
            return False, "模型不支持看图"
        try:
            doc = _json_of(txt)
            if not isinstance(doc, dict):
                doc = {"score": None, "issues": [], "fix": "", "raw": txt[:300]}
        except Exception:
            doc = {"score": None, "issues": [], "fix": "", "raw": txt[:300]}
        doc["t"] = times[i] if i < len(times) else None
        rows.append(doc)
    scores = [d["score"] for d in rows if isinstance(d.get("score"), (int, float))]
    mean = round(sum(scores) / len(scores), 1) if scores else None
    (w / f"{tag}.json").write_text(json.dumps(
        {"model": cfg.get("model", ""), "mean": mean, "frames": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [d for d in rows if isinstance(d.get("score"), (int, float)) and d["score"] <= REVIEW_SCORE_FLOOR]
    log(f"自查完成：平均 {mean} 分｜明显问题 {len(bad)} 帧 → {tag}.json")
    if bad:
        log("  最需要改：" + "；".join(str(x) for x in (bad[0].get("issues") or [])[:2]))
    return True, f"平均 {mean}"


def _ask(label, sys_prompt, ctx, cfg, w, tries=3, rt=None, deadline=None):
    """要模型写**一小段** JS：语法自检 +（可选）运行时抽查，把具体错误回灌重试。
    —— 分段调用的核心：每次只写几句，任何一处不合格只重来这一小段。
    rt 给出时还会把这一批**装进引擎真跑一遍**：
    「语法对」不等于「跑得起来」—— 模型最常见的错是猜了不存在的 API
    （如 e.sh.drawText）或算出 NaN，这两种 node --check 完全查不出来，
    只有让引擎真跑才暴露。放在这里抓，就只需重写这一小批；
    拖到最后整片闸门才抓，8 批都白跑了。
    deadline（time.monotonic 值）给出时，到点不再开新的重试，避免长时间退不出来。"""
    errs = []
    for k in range(1, tries + 1):
        if deadline is not None and time.monotonic() > deadline:
            errs = ["已到画面修复时间预算，停止重试"]
            log(f"  {label} ✗ {errs[0]}")
            break
        c2 = ctx + ("\n\n上次被拒，只修这些问题：\n" + "\n".join(errs) if errs else "")
        try:
            dump(f"{label}-prompt-{k}", c2)
            raw = _llm(sys_prompt, c2, cfg, meta_label=f"{label}-{k}")
            dump(f"{label}-raw-{k}", raw)
            js = _js_of(raw)
        except Exception as e:
            errs = [f"调用失败：{e}"]
            log(f"  {label} 第{k}次 ✗ {errs[0]}")
            continue
        tmp = w / f"_syn_{label}.js"
        tmp.write_text(js, encoding="utf-8")
        r = sh(["node", "--check", tmp])
        tmp.unlink(missing_ok=True)
        if r.returncode != 0:
            errs = [f"JS 语法错误：{(r.stderr or r.stdout)[-300:]}"]
            log(f"  {label} 第{k}次 ✗ 语法错（原文见 llm/{label}-raw-{k}.txt）")
            continue
        if rt:
            err = _runtime_check(js, label, w, rt)
            if err:
                errs = [f"运行时报错：{err}"]
                log(f"  {label} 第{k}次 ✗ 运行时：{err[:150]}")
                continue
        return js
    return None


def _runtime_check(js, label, w, rt):
    """把这一批片段装进「长度正确、只有本批有内容」的 MV.scenes，用引擎抽查本批时刻。
    返回引擎真实抛出的错误（无错返回 None）。
    其余位置填 null —— 引擎只画 typeof draw==='function' 的节点，会安全跳过，
    于是抽查到的每一帧画的都是本批画面，不会串到别批去。"""
    tmp = w / f"_rt_{label}.js"
    total = rt["total"]
    kind = rt.get("kind")
    key = ("MV.cardsPart" if kind == "cards"
           else "MV.shotsPart" if kind == "shots" else "MV.scenesPart")
    if key not in js:
        # 不拦的话，下面的包装会把模型写的东西整个盖掉，
        # 于是"什么都没测到"却报通过 —— 比报错更危险。
        return f"没找到 {key}：本段必须写成 {key} = [...]; 这一种形式"
    if kind == "shots":
        # 单批只覆盖一段时间；用空镜头补齐前后，让覆盖度校验只针对整片时生效
        wrap = (js.replace("MV.shotsPart", "MV._sp")
                + "\nconst _sp = (MV._sp || []).slice().sort((a,b)=>a.start-b.start);"
                  "\nconst _dur = (window.TL && TL.duration) || 0;"
                  "\nMV.shots = [];"
                  "\nif (_sp.length) {"
                  "\n  const _a = _sp[0].start, _b = _sp[_sp.length-1].end;"
                  "\n  if (_a > 0.001) MV.shots.push({start:0, end:_a, bg:'#000', draw(){}});"
                  "\n  MV.shots.push(..._sp);"
                  "\n  if (_b < _dur - 0.001) MV.shots.push({start:_b, end:_dur, bg:'#000', draw(){}});"
                  "\n}\n")
    elif kind == "cards":
        wrap = (js.replace("MV.cardsPart", "MV._cp")
                + f"\nMV.intro = (MV._cp || {{}}).intro || [];"
                  f"\nMV.interludes = (MV._cp || {{}}).interludes || [];"
                  f"\nMV.outro = (MV._cp || {{}}).outro || [];"
                  f"\nMV.filler = (MV._cp || {{}}).filler || null;"
                  f"\nMV.scenes = new Array({total}).fill(null);\n")
    else:
        wrap = (js.replace("MV.scenesPart", "MV._part")
                + f"\nMV.scenes = new Array({total}).fill(null);"
                  f"\n(MV._part || []).forEach((s, k) => {{ MV.scenes[{rt['start']} + k] = s; }});\n")
    tmp.write_text(wrap, encoding="utf-8")
    try:
        r = sh([sys.executable, str(HERE / "render.py"),
                "--engine", str(ENGINE),
                "--timeline", str(w / "timeline.json"),
                "--plan", str(w / "plan.json"),
                "--scenes", str(tmp), "--gate-only",
                "--times", rt["times"]], cwd=HERE)
    finally:
        tmp.unlink(missing_ok=True)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    if r.returncode == 0:
        return None
    bad = [l.strip(" -") for l in out.splitlines() if l.strip().startswith("-")]
    return "；".join(bad[:2]) or out[-200:]


SCENES_PER_CALL = 6      # 每次写 6 句。40+ 句一次写完＝单点 10 分钟长调用，
                         # 且一处不合格整批重来；分段后每段 1~2 分钟，失败只重那段。
# 整体闸门失败后的修复预算：有上限地重写出错的那一批/卡片，避免无限循环。
# 三个都能用环境变量调：轮数、整段总时长、最多调用次数。
SCENES_REPAIR_ROUNDS = int(os.environ.get("LYRIC_MV_REPAIR_ROUNDS", "3"))
SCENES_BUDGET_SEC = int(os.environ.get("LYRIC_MV_SCENES_BUDGET", "1800"))
SCENES_MAX_ASKS = int(os.environ.get("LYRIC_MV_SCENES_MAX_ASKS", "24"))

_TYPE_SCENES_SYS = """你是 MV 字体设计师兼动画师。整片是**文字类 MV**：文字就是画面主体，没有独立字幕层。
引擎已经把时间、拍点、逐字时间都做好了——你只管把这一句歌词排成画面。

输出一个 JS 文件（只要代码，不要 markdown 围栏、不要解释）：

MV.scenes = [ { bg:"#111111", draw(e){ ... } }, ... ];   // 每句一条，条数必须等于歌词行数
MV.intro = [ { bars:2, bg:"#111111", draw(e){...} }, ... ];
MV.interludes = [ { afterLine:11, cards:[ { bars:4, bg:"#111111", draw(e){...} } ] } ];
MV.outro = [ { bars:3, bg:"#111111", draw(e){...} } ];
MV.filler = { bg:"#111111", draw(e){...} };

### 可用 API（下面是**从引擎运行时实时导出**的，未列出的就是不存在）
{API}

### 逐字时间（重要）
- `e.line.text`：本句歌词原文；`e.chars`：`[[字, 开始秒], ...]`；
  `e.sung`：当前已唱到第几个字（-1 = 还没开口）。
- 用 `e.chars[j][1]` 或 `e.sung` 决定每个字何时出现/变色/位移；未唱到的字不要提前显示。
- 宽度用 `e.measure(str, size, weight, font)`；`e.drawText` 传 `maxW` 可自动缩字号防出框。

### 字效方案（全片统一，优先级仅次于用户要求）
{TYPE_PLAN}

### 铁律（违反会被闸门拦下）
1. draw 必须是 e.t 的**纯函数**：禁止 Math.random / Date.now / performance.now /
   setTimeout / requestAnimationFrame / 任何跨帧累积的外部变量。要随机用 e.rnd(seed)。
2. **文字就是主体**：每句至少有一处大号主字；不要画人物、风景、插画主体；
   允许色块、线条、网格、HUD 作为排版支撑。
3. **可读性**：主字与背景高对比（深底浅字/浅底深字），不重叠、不被遮挡；
   四周留 6% 安全边距；长句自动换行或缩字号，禁止挤出画面。
4. **逐字驱动**：字的出现、变色、位移必须跟 e.chars / e.sung 对齐；不要所有字同时出现。
5. **每个镜头都要有可见运动**：文字按拍做位移/缩放/字重/遮罩变化；
   0.5 秒内至少满足一条：位移 ≥ 画面宽 1.5%、缩放 ≥ 8%、透明度 ≥ 15%。
6. **禁止整帧亮度脉动**：全画面忽明忽暗＝闪；节拍用文字动作表达。
7. 相邻句不要长得一样；按段落 energy 递进；同一段内保持同一套排版语言。
8. 不要写歌词之外的旁白/字幕；标题/标签可用 ≤8 字。
9. 不要使用 e.lyricBox / e.lyricBand（没有歌词层）；屏幕空间就是全部可用空间。
10. MV.scenes 条数必须严格等于歌词行数。
11. **主次**：每句只把 1~2 个连续片段做成「点睛」（更大字号 + 强调色/更重字重/色块），
    其余字保持基准字号与颜色；重点要落在语义重心（转折、结论、反问、称呼、动作结果），
    禁止整句一起放大，也禁止每句都用同一套强调方式。
"""

_TYPE_BATCH_SYS = _TYPE_SCENES_SYS + """
### 本片逐句重点
{EMPHASIS}

**本次只写指定的那几句**：第一行先写一句摘要注释（供下一批衔接），
然后紧接着写恰好一行的代码：
/* 摘要：一句话说这批文字排成了什么样 */
MV.scenesPart = [ { draw(e){...} }, ... ];
条数必须等于"本批句数"，顺序与给定的句号一致。不要写 MV.scenes，不要写其他字段。
"""

_TYPE_CARD_SYS = _TYPE_SCENES_SYS + """
**本次只写卡片**（片头 / 间奏 / 尾奏 / 短空档兜底），输出恰好一行：
MV.cardsPart = { intro:[...], interludes:[...], outro:[...], filler:{ bg, draw(e) } };
卡片不承担歌词：只写标题、署名、关键词或单字排版；每张卡给 bars（占几小节）+ draw(e)。
长间奏拆成 3~5 张卡，每张 2~4 小节，连续铺满空档，每张要有开始→结束的变化。
filler 负责短于 2 小节的空档：必须有缓慢的文字/光线运动，不能是纯色。
不要写 MV.scenes。
"""


_BATCH_SYS = _SCENES_SYS + """
**本次只写指定的那几句**：第一行先写一句摘要注释（供下一批衔接），
然后紧接着写恰好一行的代码：
/* 摘要：一句话说这批画面画了什么 */
MV.scenesPart = [ { draw(e){...} }, ... ];
条数必须等于"本批句数"，顺序与给定的句号一致。不要写 MV.scenes，不要写其他字段。
"""

_SUM_RE = re.compile(r"/\*\s*摘要[：:]\s*(.*?)\s*\*/|//\s*摘要[：:]\s*([^\n]+)", re.S)


def _batch_summary(fp):
    """取某批的画面摘要：优先读旁挂文件，没有就从代码里的摘要注释提取。
    摘要只用于「下一批接着画」，缺失不致命（老产物没有这个注释）。"""
    s = fp.with_suffix(".summary.txt")
    if s.exists():
        return s.read_text(encoding="utf-8").strip()
    if not fp.exists():
        return ""
    m = _SUM_RE.search(fp.read_text(encoding="utf-8"))
    if not m:
        return ""
    txt = (m.group(1) or m.group(2) or "").strip()
    if not txt:
        return ""
    s.write_text(txt, encoding="utf-8")
    return txt

_CARD_SYS = _SCENES_SYS + """
**本次只写卡片**（片头 / 间奏 / 尾奏 / 短空档兜底），输出恰好一行：
MV.cardsPart = { intro:[...], interludes:[...], outro:[...], filler:{ bg, draw(e) } };
每张卡给 bars（占几小节）+ draw(e)。interludes 用 afterLine 指向"接在第几句之后"。
filler 负责**短于 2 小节的歌词空档**：必须有画面（缓慢漂移的光斑/粒子/光影），
不能是纯色、不能什么都不画，否则短空档那几秒会变成一片死画面。

长间奏不能糊：
- 空档 > 8 小节时，必须拆成 **3~5 张卡**，每张 2~4 小节，连续铺满整个空档；
- 每张卡都要有「开始状态 → 结束状态」的变化（位置/尺度/显隐/时间推进/场景切换），
  不能只让一个小道具在固定舞台上平移；
- 这段间奏的叙事要接住编导方案里对应的 idea，并接上前后两句的画面，让故事继续走。
不要写 MV.scenes。
"""


def _gate_bad_times(out):
    """从闸门输出里提取失败时刻（只看错误行，不看“运动偏弱”这类提示）。"""
    ts = []
    for line in (out or "").splitlines():
        if not line.strip().startswith("-"):
            continue
        for m in re.finditer(r"t=([0-9]+(?:\.[0-9]+)?)", line):
            try:
                t = float(m.group(1))
            except ValueError:
                continue
            if t not in ts:
                ts.append(t)
    return ts


def _part_of_time(t, tl, per):
    """把失败时刻映射到「某一批」或「卡片」。"""
    for i, L in enumerate(tl.get("lines") or []):
        if L["start"] - 0.05 <= t <= L["end"] + 0.45:
            return "batch", i // per
    return "cards", None


def st_scenes(w, st, tl, plan, brief, cfg, force=False,
              only_batches=None, review_notes=None, mode="performance"):
    """分两段要画面：① 正片按批（每批 SCENES_PER_CALL 句）② 卡片（片头/间奏/尾奏）。
    各段独立缓存到 parts/，重跑只补缺的那一段。换视觉风格时全部重写。

    only_batches：只重写这些批次（1-based），其余批次与卡片复用——
                  用于截图自查后的有界修复，避免整片重写。
    review_notes：{行号: [问题...]}，重写对应批次时把自查问题回灌给模型。

    整体闸门失败后不再直接放弃：按失败时刻定位到具体批次/卡片，有上限地重写，
    再重新组装过闸门。轮数、总时长、最多调用次数都有上限，避免退不出来。"""
    p = w / "scenes.js"
    # 画面签名要包含模式、字效方案与底图 key：任一变化都必须重写画面
    asset_sig = ",".join(sorted((plan.get("assets") or {}).keys()))
    type_sig = sha(w / "type-plan.json") if (w / "type-plan.json").exists() else ""
    emph_sig = sha(w / "type-emphasis.json") if (w / "type-emphasis.json").exists() else ""
    scene_sig = (f"mode:{mode}"
                 + (f"|type:{type_sig}" if type_sig else "")
                 + (f"|emph:{emph_sig}" if emph_sig else "")
                 + (f"|img:{asset_sig}" if asset_sig else ""))
    marker = w / "scenes.style.txt"
    same = marker.exists() and marker.read_text(encoding="utf-8").strip() == scene_sig
    only_batches = set(only_batches or ())
    if not same:
        if p.exists() and marker.exists():
            log(f"画面签名变化（{marker.read_text(encoding='utf-8').strip()} → {scene_sig}）：重写全部画面")
        force = True
    if p.exists() and not force and not only_batches:
        log("画面代码复用：scenes.js")
        return True, "复用", p

    parts = w / "parts"
    parts.mkdir(exist_ok=True)
    lines = tl["lines"]
    n = len(lines)
    ctx0, gaps = _ctx_common(tl, brief)
    ctx0 += "\n\n编导方案（必须落实）：\n" + json.dumps(plan, ensure_ascii=False)
    bible = "" if mode == "typographic" else _bible_text(w)
    if bible:
        ctx0 += ("\n\n【视觉圣经 · 全片统一，优先级仅次于用户要求】\n" + bible
                 + "\n每一句都要遵守；与前一批衔接，但不要重复它的构图。")
    # API 清单：从引擎运行时导出后填进提示词，提示词与引擎永不漂移
    api = _api_spec_text(w)
    if mode == "typographic":
        type_block = _type_plan_text(w)
        fallback_api = ("（清单导出失败：只用 e.drawText / e.measure / e.bg / "
                        "e.sh 的 rect/circle/line / e.rnd，其余一律不要用）")
        bs = _TYPE_BATCH_SYS.replace("{API}", api or fallback_api).replace(
            "{TYPE_PLAN}", type_block).replace("{EMPHASIS}", _type_emphasis_text(w))
        cs = _TYPE_CARD_SYS.replace("{API}", api or fallback_api).replace(
            "{TYPE_PLAN}", type_block)
    else:
        style_block = "（本片不预设画风：按视觉圣经与这一句的内容自己决定画法）"
        bs = _BATCH_SYS.replace("{API}", api) if api else _BATCH_SYS.replace(
            "{API}", "（清单导出失败：只用手边这几个—— e.sh 的 rect/circle/ring/tri/line/speckle、"
                     "e.drawText/e.drawParagraph/e.measure/e.bg/e.rnd，其余一律不要用）")
        cs = _CARD_SYS.replace("{API}", api) if api else _CARD_SYS.replace("{API}", "（同正片，保守作画）")
        bs = bs.replace("{STYLE}", style_block)
        cs = cs.replace("{STYLE}", style_block)
        image_block = _scene_image_block(plan)
        bs = bs.replace("{IMAGES}", image_block)
        cs = cs.replace("{IMAGES}", image_block)
        mode_rule = MODE_SCENE_RULES.get(mode, MODE_SCENE_RULES["performance"])
        bs = bs.replace("{MODE_RULE}", mode_rule)
        cs = cs.replace("{MODE_RULE}", mode_rule)

    batches = [list(range(i, min(i + SCENES_PER_CALL, n))) for i in range(0, n, SCENES_PER_CALL)]
    log(f"正片 {n} 句，分 {len(batches)} 批（每批 ≤{SCENES_PER_CALL} 句）")
    log(f"画面修复预算：{SCENES_REPAIR_ROUNDS} 轮 / {SCENES_BUDGET_SEC}s / {SCENES_MAX_ASKS} 次调用")

    deadline = time.monotonic() + SCENES_BUDGET_SEC
    asks = 0
    budget_hit = False

    def affordable():
        nonlocal budget_hit
        if time.monotonic() > deadline:
            budget_hit = True
            log(f"  ✗ 画面修复超过时间预算（{SCENES_BUDGET_SEC}s）")
            return False
        if asks >= SCENES_MAX_ASKS:
            budget_hit = True
            log(f"  ✗ 画面修复调用次数超过上限（{SCENES_MAX_ASKS} 次）")
            return False
        return True

    def gen_batch(bi, idxs, tries=3):
        nonlocal asks
        if not affordable():
            return False
        fp = parts / f"scenes-b{bi}.js"
        lo, hi = max(0, idxs[0] - 1), min(n - 1, idxs[-1] + 1)
        ctx = (ctx0 + f"\n\n【本批】只写第 {idxs[0]}~{idxs[-1]} 句，共 {len(idxs)} 条。\n"
               + "".join(f"  {i}: [{lines[i]['section']}] {lines[i]['text']}"
                         f"  ({lines[i]['start']:.1f}~{lines[i]['end']:.1f}s)"
                         + ("   ← 只作上下文参考，不要为它写画面\n"
                            if i not in idxs else "\n")
                         for i in range(lo, hi + 1)))
        if bi > 1:
            prev = _batch_summary(parts / f"scenes-b{bi - 1}.js")
            if prev:
                ctx += "\n上一批画了什么（保持同一套视觉语言与情绪递进，不要重复构图）：\n  " + prev
        if review_notes:
            mine = [f"  第 {i} 句：{'；'.join(review_notes[i])}"
                    for i in idxs if i in review_notes]
            if mine:
                ctx += ("\n\n【截图自查发现的问题 · 只修这些句】\n" + "\n".join(mine) +
                        "\n重写时：主体要一眼可辨（不要只剩色块/空景）、不要被歌词带压住、"
                        "不要元素互相遮挡或比例失真；其余句保持原视觉语言，不要改风格。")
        rt = {"total": n, "start": idxs[0],
              "times": ",".join(f"{(lines[k]['start'] + lines[k]['end']) / 2:.3f}" for k in idxs)}
        asks += 1
        log(f"  第 {bi}/{len(batches)} 批（第 {idxs[0]}~{idxs[-1]} 句）生成中...")
        js = _ask(f"b{bi}", bs, ctx, cfg, w, rt=rt, tries=tries, deadline=deadline)
        if js is None:
            return False
        fp.write_text(js, encoding="utf-8")
        _batch_summary(fp)
        return True

    def gen_cards(tries=3):
        nonlocal asks
        if not affordable():
            return False
        bar = 4 * (tl.get("beat_seconds") or 0.5)
        short = [(i, round(lines[i + 1]["start"] - lines[i]["end"], 2))
                 for i in range(len(lines) - 1)
                 if 0.2 < lines[i + 1]["start"] - lines[i]["end"] <= 2 * bar]
        ideas = {x.get("afterLine"): str(x.get("idea") or "")
                 for x in (plan.get("interludes") or []) if x.get("afterLine") is not None}
        gap_desc = "，".join(
            f"afterLine={i}（{g}s ≈ {max(2, round(g / bar))} 小节；"
            f"{ideas.get(i, '按前后画面自然延续')[:70]}）"
            for i, g in gaps) if gaps else "无"
        ctxc = (ctx0 + f"\n\n需要 cards：intro 覆盖 0~{lines[0]['start']:.1f}s；"
                f"outro 覆盖 {lines[-1]['end']:.1f}s~{tl['duration']:.1f}s；"
                f"interludes 必须各有一条对应下面每个长空档。\n长空档：{gap_desc}"
                + "\n短空档（≤2 小节，没有间奏卡，由 filler 兜底）："
                + ("，".join(f"afterLine={i}（{g}s）" for i, g in short) if short else "无"))
        last_sum = _batch_summary(parts / f"scenes-b{len(batches)}.js")
        if last_sum:
            ctxc += "\n全片最后一批画了什么（片尾要接得上）：\n  " + last_sum
        cts = _card_times(tl, gaps)
        asks += 1
        log("  卡片（片头/间奏/尾奏 + filler）生成中...")
        js = _ask("cards", cs, ctxc, cfg, w,
                  rt={"total": n, "start": 0, "kind": "cards",
                      "times": ",".join(f"{t:.3f}" for t in cts)} if cts else None,
                  tries=tries, deadline=deadline)
        if js is None:
            return False
        (parts / "cards.js").write_text(js, encoding="utf-8")
        return True

    for bi, idxs in enumerate(batches, 1):
        fp = parts / f"scenes-b{bi}.js"
        if fp.exists() and not force and bi not in only_batches:
            _batch_summary(fp)          # 顺手补摘要，供下一批衔接
            log(f"  第 {bi}/{len(batches)} 批 复用")
            continue
        if not gen_batch(bi, idxs):
            why = "（画面修复预算用完，可用 LYRIC_MV_SCENES_BUDGET / LYRIC_MV_SCENES_MAX_ASKS 调大）" \
                if budget_hit else f"（见 llm/b{bi}-raw-*.txt）"
            return False, f"正片第 {bi} 批 3 次未通过{why}", None

    # 卡片（片头/间奏/尾奏/短空档 filler）：独立一次小调用
    fcard = parts / "cards.js"
    if fcard.exists() and not force:
        try:
            old_card = fcard.read_text(encoding="utf-8")
        except Exception:
            old_card = ""
        if "filler" not in old_card:
            log("  旧卡片代码缺 filler（短空档会空帧）：只重写卡片")
            fcard.unlink()
    if not fcard.exists() or force:
        if not gen_cards():
            why = "（画面修复预算用完）" if budget_hit else "（见 llm/cards-raw-*.txt）"
            return False, f"卡片 3 次未通过{why}", None
    else:
        log("  卡片 复用")

    def assemble():
        pieces = []
        for b in range(1, len(batches) + 1):
            pieces.append((parts / f"scenes-b{b}.js").read_text(encoding="utf-8")
                          .replace("MV.scenesPart", f"_part{b}"))
        return ("\n".join(pieces) + "\n" + fcard.read_text(encoding="utf-8") + "\n"
                "MV.scenes = [" + ",".join(f"..._part{b}" for b in range(1, len(batches) + 1)) + "];\n"
                "if (MV.cardsPart) { MV.intro = MV.cardsPart.intro || [];\n"
                "  MV.interludes = MV.cardsPart.interludes || [];\n"
                "  MV.outro = MV.cardsPart.outro || [];\n"
                "  MV.filler = MV.cardsPart.filler || null; }\n")

    try_js = w / "_scenes_try.js"

    def gate_all(js):
        try_js.write_text(js, encoding="utf-8")
        r = sh([sys.executable, str(HERE / "render.py"), "--engine", ENGINE,
                "--timeline", w / "timeline.json", "--plan", w / "plan.json",
                "--scenes", try_js, "--gate-only"], cwd=HERE, stream=True)
        out = (r.stdout or "") + (r.stderr or "")
        try_js.unlink(missing_ok=True)
        return r.returncode == 0, out

    repairs = 0
    last_errs = []
    for rnd in range(SCENES_REPAIR_ROUNDS + 1):
        assembled = assemble()
        ok, out = gate_all(assembled)
        if ok:
            p.write_text(assembled, encoding="utf-8")
            marker.write_text(scene_sig, encoding="utf-8")
            log(f"  已组装 {n} 条正片 + 卡片 → {p.name}")
            note = [l for l in out.strip().splitlines() if l.strip()]
            log("画面代码通过闸门｜" + (note[0].strip() if note else ""))
            extra = f"｜修复 {repairs} 处" if repairs else ""
            return True, f"{len(batches)}批+卡片{extra}", p

        dump(f"scenes-gate-r{rnd}", out)
        last_errs = [l.strip(" -") for l in out.splitlines() if l.strip().startswith("-")]
        if rnd >= SCENES_REPAIR_ROUNDS:
            return False, ("整体闸门未通过（已自动修复 %d 处仍未过）：" % repairs
                           + "；".join(last_errs[:3])
                           + f"（逐条见 llm/scenes-gate-r{rnd}.txt）"), None
        if time.monotonic() > deadline:
            return False, ("画面修复超过时间预算（%ds）：" % SCENES_BUDGET_SEC
                           + "；".join(last_errs[:2])), None

        todo = []
        for t in _gate_bad_times(out):
            kind, bi = _part_of_time(t, tl, SCENES_PER_CALL)
            key = "cards" if kind == "cards" else bi
            if key not in todo:
                todo.append(key)
        if not todo:
            return False, ("整体闸门未通过，且无法从错误里定位到具体批次："
                           + "；".join(last_errs[:3])), None

        log("  整体闸门未通过，进入第 %d 轮修复：%s" % (
            rnd + 1, "、".join("卡片" if k == "cards" else f"第{k + 1}批" for k in todo[:2])))
        for key in todo[:2]:
            repairs += 1
            if key == "cards":
                fcard.unlink(missing_ok=True)
                if not gen_cards(tries=2):
                    return False, "卡片修复失败（见 llm/cards-raw-*.txt）", None
            else:
                (parts / f"scenes-b{key + 1}.js").unlink(missing_ok=True)
                if not gen_batch(key + 1, batches[key], tries=2):
                    return False, f"正片第 {key + 1} 批修复失败（见 llm/b{key + 1}-raw-*.txt）", None

    return False, "整体闸门未通过：" + "；".join(last_errs[:3]), None


def st_render(w, st, tl, plan, scenes, song, fps):
    out = w / "mv.mp4"
    sig = sha((w / "timeline.json"), (w / "plan.json"), scenes, song)
    if ok_cached(st, "render", sig) and out.exists():
        log("成片复用")
        return True, "复用", out
    log("逐帧渲染中...")
    last = ""
    for attempt in (1, 2):
        if attempt > 1:
            log("  渲染失败，重试一次（已完成的帧块会复用）...")
        r = sh([sys.executable, str(HERE / "render.py"), "--engine", ENGINE,
                "--timeline", w / "timeline.json", "--plan", w / "plan.json",
                "--scenes", scenes, "--audio", song, "--out", out, "--fps", fps],
               cwd=HERE, stream=True)
        if r.returncode == 0 and out.exists():
            return True, f"{out.stat().st_size / 1048576:.1f} MB", out
        last = (r.stdout or r.stderr or "")[-400:]
        log(f"  渲染第 {attempt} 次失败：{last[-200:]}")
    return False, last, None


def st_render_tsx(w, st, tl, plan, song, fps, force=False):
    """Remotion 引擎的渲染段：bundle → renderMedia → 混音。"""
    out = w / "mv.mp4"
    sig = sha((w / "timeline.json"), (w / "render-plan.json"), song, (w / "look.json"))
    if not force and ok_cached(st, "render", sig) and out.exists():
        log("成片复用")
        return True, "复用", out
    log("Remotion 渲染中（bundle + 逐帧 + 混音）...")
    r = sh([sys.executable, str(RUNTIME_RENDER), str(w), "--fps", str(fps)],
           cwd=RUNTIME_RENDER.parent, stream=True)
    if r.returncode == 0 and out.exists():
        return True, f"{out.stat().st_size / 1048576:.1f} MB", out
    # stream=True 时 stderr 被并进 stdout，真正的报错在 stdout 尾部
    tail = (r.stdout or r.stderr or "").strip()
    return False, (f"退出码 {r.returncode}：" + tail[-600:]) if tail else f"退出码 {r.returncode}，无输出", None


def write_render_plan(w, tl, plan, story, mode):
    """渲染用的 plan：在编导方案上补「时间 → 组件 id」的映射。
    单独落文件，避免改动 plan.json 让画面签名漂移。"""
    rp = json.loads(json.dumps(plan, ensure_ascii=False))
    man_p = w / "parts" / "registry.json"
    manifest = json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else {}
    shots = sorted((v for v in manifest.values() if str(v.get("key", "")).startswith("shot-")),
                   key=lambda v: float(v.get("start") or 0))
    if shots:
        # 画面作者自己分了镜（一镜可跨多句）：用绝对时间覆盖
        rp["shots"] = [{"start": float(v["start"]), "end": float(v["end"]), "scene": v["key"]}
                       for v in shots]
        rp.pop("scenes", None)
    elif mode == "narrative":
        shots = (story or {}).get("shots") or []
        rp["shots"] = [
            {"start": float(s.get("start", 0)), "end": float(s.get("end", 0)), "scene": f"shot-{i + 1}"}
            for i, s in enumerate(shots)
        ]
    else:
        rp["scenes"] = [f"line-{i}" for i in range(len(tl.get("lines") or []))]
        rp.setdefault("filler", "default.filler")
    rp.setdefault("lyricStyle", "band")

    # 歌词呈现兜底：编导没指定的部分，按段落「字/秒」自动决定
    #   - 版式：横向安全版式轮换（长句不会溢出）；vertical/walk/brush 留给编导显式指定
    #   - karaoke：字/秒 >= 2.6 视为语速快、逐字来不及读 → 整句一起出现
    FAQ = 2.6
    rates: dict[str, tuple[int, float]] = {}
    order: list[str] = []
    for ln in (tl.get("lines") or []):
        s = str(ln.get("section") or "").strip()
        if not s:
            continue
        if s not in rates:
            rates[s] = (0, 0.0)
            order.append(s)
        chars, dur = rates[s]
        rates[s] = (chars + len(str(ln.get("text") or "")),
                    dur + max(0.1, float(ln.get("end", 0)) - float(ln.get("start", 0))))

    styles = rp.get("lyricStyles") or {}
    if not isinstance(styles, dict):
        styles = {}
    rotation = ["band", "bottom", "shrink", "bounce"]
    base = rp.get("lyricStyle")
    start = rotation.index(base) if base in rotation else 0
    for i, name in enumerate(order):
        cfg = styles.get(name)
        if isinstance(cfg, str):
            cfg = {"style": cfg}
        elif not isinstance(cfg, dict):
            cfg = None
        if cfg is None:
            cfg = {"style": rotation[(start + i) % len(rotation)]}
        if "karaoke" not in cfg and rp.get("lyricKaraoke") is None:
            chars, dur = rates[name]
            rate = chars / dur if dur > 0 else 0.0
            cfg["karaoke"] = rate < FAQ
        styles[name] = cfg
    if styles:
        rp["lyricStyles"] = styles
    p = w / "render-plan.json"
    p.write_text(json.dumps(rp, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def st_accept(st, out):
    r = sh([sys.executable, str(HERE / "flicker.py"), out])
    txt = r.stdout or ""
    p99, big = None, None
    for ln in txt.splitlines():
        pr = ln.split()
        if len(pr) >= 2 and pr[0] == "p99":
            p99 = float(pr[-1])
        if "跳变 >8" in ln:
            big = ln.strip()
    log("验收：" + (big or "（无指标）"))
    if p99 is None:
        return False, "验收指标缺失"
    if p99 > 8:
        return False, f"帧间亮度跳变 p99={p99} 过大 → 画面里有整帧亮度脉动（闪），需改成位移表达"
    return True, txt.strip().replace("\n", " | ")


LABEL = {"env": "环境自检", "audio": "音源准备", "grid": "拍网格", "align": "逐字对齐",
         "mode": "模式判断", "plan": "编导编排", "typeplan": "字效方案",
         "shotlist": "镜头表",
         "scenes": "画面代码", "render": "逐帧渲染", "accept": "出片验收"}
STEP = {"env": "⓪", "audio": "①", "grid": "②", "align": "③", "mode": "③·4",
        "plan": "④", "typeplan": "④·5T", "shotlist": "④·6", "scenes": "⑤",
        "render": "⑥", "accept": "⑦"}


def hdr(name):
    """阶段抬头。编号在这里发（pipeline 才知道当前在哪段），
    前端/工具只做转发，不必靠猜关键词。"""
    log(f"{STEP[name]} {LABEL[name]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="工作目录（产物落这里）")
    ap.add_argument("--brief", default="", help="用户要求，优先级最高")
    ap.add_argument("--audio", default="", help="用户指定的音乐文件（不传则生成）")
    ap.add_argument("--lyrics", default="", help="歌词文件（不传视为器乐/纯音乐）")
    ap.add_argument("--synth-prompt", default="真诚的中文流行歌，钢琴与弦乐，节奏舒缓但鼓点清晰，"
                                              "情绪真挚，清澈嗓音")
    ap.add_argument("--t0", type=float, default=None)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--mode", default="auto", choices=["auto"] + MODES,
                    help="MV 模式：auto（LLM 判断）/ narrative 叙事 / performance 表演 / typographic 文字")
    ap.add_argument("--stage", default="auto", choices=["auto", "pitch", "treatment", "produce"],
                    help="叙事型阶段：auto / pitch 故事方向 / treatment 故事蓝图 / produce 产出")
    ap.add_argument("--story-choice", default="",
                    help="叙事型：从 pitch 进入 treatment 时指定候选方向 id")
    ap.add_argument("--revise", action="store_true",
                    help="叙事型：强制重新生成故事方向/蓝图（用户说换一批时用）")
    ap.add_argument("--type-style", default="", choices=[""] + type_styles.ids(),
                    help="文字类：强制字效风格；不传则由 LLM 选")
    ap.add_argument("--force", default="", help="强制重跑某段（逗号分隔）")
    ap.add_argument("--stop-after", default="",
                    help="跑完这一段就停下（用于分段验收/调试），取值同段名："
                         "env/audio/grid/align/plan/scenes/render/accept")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--no-review", action="store_true", help="跳过截图自查")
    ap.add_argument("--no-review-repair", action="store_true",
                    help="自查只出报告，不把低分帧回灌重写")
    ap.add_argument("--with-images", action="store_true",
                    help="为每个段落生成一张 AI 氛围底图（需要配置图片生成 Key）")
    ap.add_argument("--max-images", type=int, default=6,
                    help="最多生成几张段落底图，默认 6")
    ap.add_argument("--look", default="",
                    help='渲染外观 JSON（自由配置），例如 {"pixel":{"block":4,"colors":24}}；'
                         "不传则沿用 out_dir 里已有的 look.json")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--engine", default=os.environ.get("LYRIC_MV_ENGINE", "canvas"),
                    choices=["canvas", "remotion"],
                    help="渲染引擎：canvas=旧逐帧引擎；remotion=共享 Remotion 运行时")
    args = ap.parse_args()

    global TSX_ENGINE
    TSX_ENGINE = args.engine == "remotion"

    # 入口统一解析成绝对路径：各阶段是以子进程调用的，相对路径会被子脚本按自身目录解析
    # （踩过：--lyrics 传相对路径，结果变成 skills/lyric_mv/kinetic_demo/...）
    w = Path(args.work).resolve()
    w.mkdir(parents=True, exist_ok=True)
    open_log(w)

    # 渲染外观（像素化等）：显式传入优先，其次用外部注入的环境变量；都没有就沿用已有配置
    raw_look = (args.look or os.environ.get("LYRIC_MV_LOOK", "")).strip()
    if raw_look:
        try:
            look_doc = json.loads(raw_look)
        except Exception as e:
            log(f"❌ look 不是合法 JSON：{e}")
            return 1
        if not isinstance(look_doc, dict):
            log("❌ look 必须是 JSON 对象")
            return 1
        (w / "look.json").write_text(json.dumps(look_doc, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    st = load_state(w)
    fset = {x for x in args.force.split(",") if x}
    stop = args.stop_after.strip()
    if stop and stop not in LABEL:
        log(f"❌ --stop-after 取值必须是 {list(LABEL)} 之一")
        return 1
    if args.status:
        print(f"工作目录 {w}：")
        for k in LABEL:
            s = st["stages"].get(k)
            print(f"  {LABEL[k]:<10} " + ("✅ " + (s["note"] or "") if s and s["ok"]
                                          else ("❌ " + (s["note"] if s else "未跑"))))
        return 0
    if not args.run:
        print(__doc__)
        return 0

    lyrics = Path(args.lyrics).resolve() if args.lyrics else None
    audio_in = str(Path(args.audio).resolve()) if args.audio else ""
    if lyrics and not lyrics.exists():
        log(f"❌ 歌词文件不存在：{lyrics}")
        return 1

    def cached(name, sig, *extra):
        return name not in fset and ok_cached(st, name, sig)

    def halt(name):
        """到了 --stop-after 指定的段就停，供分段验收"""
        if stop and stop == name:
            log(f"—— 已到 --stop-after={stop}，停止 ——")
            return True
        return False

    # 0 环境
    hdr("env")
    ok, note = st_env(w, st)
    mark(st, "env", ok, "v1", [], note)
    save_state(w, st)
    if not ok:
        log(f"❌ 环境缺依赖：{note}")
        return 1
    if halt("env"): return 0

    # 1 音源
    hdr("audio")
    sig_a = sha(Path(audio_in) if audio_in else args.synth_prompt,
                lyrics.read_bytes() if lyrics else "")
    if cached("audio", sig_a):
        log("跳过 音源准备")
    else:
        log(f"  音源重跑：{_stage_reason(st, 'audio', sig_a, w / 'song.wav')}")
        ok, note = st_audio(w, st, audio_in, lyrics, args.synth_prompt, args.brief)
        mark(st, "audio", ok, sig_a, [w / "song.wav"], note)
        save_state(w, st)
        if not ok:
            log(f"❌ 音源：{note}")
            return 1
        if halt("audio"): return 0
    song = w / "song.wav"

    # 2 拍网格
    hdr("grid")
    if cached("grid", sha(song)):
        log("跳过 拍网格")
    else:
        log(f"  拍网格重跑：{_stage_reason(st, 'grid', sha(song), w / 'grid.json')}")
        ok, note = st_grid(w, st, song)
        mark(st, "grid", ok, sha(song), [w / "grid.json"], note)
        save_state(w, st)
        if not ok:
            return 1
        if halt("grid"): return 0
    grid = w / "grid.json"

    # 3 逐字对齐
    hdr("align")
    sig_l = sha(song, lyrics.read_bytes() if lyrics else "", str(args.t0), args.model)
    old_align = (st.get("stages") or {}).get("align") or {}
    # 「歌和歌词都没变」就复用已有时间轴：t0/ASR 模型这类参数变化不该把几十分钟的对齐推倒重来。
    same_src = (old_align.get("song") == sha(song)
                and old_align.get("lyrics") == (sha(lyrics) if lyrics else ""))
    if (not cached("align", sig_l)) and same_src and old_align.get("ok") \
            and (w / "timeline.json").exists() and "align" not in fset:
        log("复用已有时间轴（歌曲和歌词都没变；重对齐请显式 force=align）")
    elif cached("align", sig_l) and (w / "timeline.json").exists():
        log("跳过 逐字对齐")
    else:
        log(f"  逐字对齐重跑：{_stage_reason(st, 'align', sig_l, w / 'timeline.json')}")
        ok, note, _ = st_align(w, st, song, lyrics, grid, args.t0, args.model)
        mark(st, "align", ok, sig_l, [w / "timeline.json"], note)
        st["stages"]["align"]["song"] = sha(song)
        st["stages"]["align"]["lyrics"] = sha(lyrics) if lyrics else ""
        save_state(w, st)
        if not ok:
            log(f"❌ 逐字对齐：{note}")
            return 1
    if halt("align"): return 0
    tl = json.loads((w / "timeline.json").read_text(encoding="utf-8"))

    cfg = _llm_cfg()
    if not cfg:
        log("❌ 没有可用的 LLM 配置，无法生成编导与画面")
        return 1

    try:
        bpm = json.loads(grid.read_text(encoding="utf-8")).get("bpm")
    except Exception:
        bpm = None

    # 3·4 模式判断：叙事 / 表演 / 文字
    hdr("mode")
    lyrics_text = ""
    if lyrics and lyrics.exists():
        try:
            lyrics_text = lyrics.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            lyrics_text = ""
    forced_mode = "" if args.mode == "auto" else args.mode
    ok, note, mode_doc = st_mode(
        w, st, tl, args.brief, cfg,
        lyrics_text=lyrics_text, bpm=bpm,
        forced_mode=forced_mode, force=("mode" in fset))
    if not ok:
        log(f"❌ 模式判断：{note}")
        return 1
    mark(st, "mode", True, str(mode_doc.get("sig") or ""), [w / "mode.json"], note)
    save_state(w, st)
    if halt("mode"):
        return 0

    # 低把握：停下让用户选模式（由主 LLM 调 ask_user）
    if mode_doc.get("ask_user") and not forced_mode:
        choices = [{
            "id": mode_doc["mode"],
            "label": MODE_LABELS.get(mode_doc["mode"], mode_doc["mode"]),
            "why": mode_doc.get("reason") or "",
        }]
        for a in (mode_doc.get("alternatives") or []):
            if a.get("mode") in MODES and all(c["id"] != a["mode"] for c in choices):
                choices.append({
                    "id": a["mode"],
                    "label": MODE_LABELS.get(a["mode"], a["mode"]),
                    "why": a.get("why") or "",
                })
        for m in MODES:
            if all(c["id"] != m for c in choices):
                choices.append({"id": m, "label": MODE_LABELS[m], "why": "备选"})
        print("MODE_CHOICES=" + json.dumps(choices[:3], ensure_ascii=False), flush=True)
        log("模式判断需要用户确认：已停下，等用户选择后带 --mode 重跑")
        return 0

    mode = mode_doc.get("mode")
    if mode == "narrative":
        log("模式：叙事型（故事驱动，歌词层照常显示）")
    elif mode == "typographic":
        log("模式：文字类（文字即画面，关闭独立歌词层）")

    # 4 编导
    hdr("plan")
    sig_plan = "v3:" + mode
    if cached("plan", sig_plan) and (w / "plan.json").exists():
        log("跳过 编导编排")
        plan = json.loads((w / "plan.json").read_text(encoding="utf-8"))
    else:
        ok, note, plan = st_plan(w, st, tl, args.brief, cfg, force="plan" in fset, mode=mode)
        mark(st, "plan", ok, sig_plan, [w / "plan.json"], note)
        save_state(w, st)
        if not ok:
            log(f"❌ 编导：{note}")
            return 1
    if halt("plan"): return 0

    if mode == "narrative":
        stage = (args.stage or "auto").strip().lower()
        story = _story_doc(w)
        status = story.get("status")
        rev = bool(args.revise) or ("story" in fset)
        if stage == "treatment" or (stage == "auto" and args.story_choice):
            ok, note, story = st_story_treatment(
                w, tl, plan, args.brief, cfg,
                choice=args.story_choice, force=rev)
            if not ok:
                log(f"❌ 故事蓝图：{note}")
                return 1
            payload = {
                "status": story.get("status"),
                "choice": story.get("choice"),
                "title": story.get("title"),
                "logline": story.get("logline"),
                "protagonist": story.get("protagonist"),
                "cast": story.get("cast") or [],
                "locations": story.get("locations") or [],
                "acts": story.get("acts") or [],
                "shot_count": len(story.get("shots") or []),
                "shots": [{"id": s.get("id"), "start": s.get("start"), "end": s.get("end"),
                           "size": s.get("size"), "action": s.get("action")}
                          for s in (story.get("shots") or [])],
            }
            print("STORY_TREATMENT=" + json.dumps(payload, ensure_ascii=False), flush=True)
            log("故事蓝图已生成：等用户确认后带 --stage produce 重跑")
            return 0
        if stage == "pitch" or (stage == "auto" and status not in ("treatment", "approved")):
            ok, note, story = st_story_pitch(
                w, tl, plan, args.brief, cfg, force=rev)
            if not ok:
                log(f"❌ 故事方向：{note}")
                return 1
            payload = {
                "recommend": story.get("recommend"),
                "why": story.get("why") or "",
                "candidates": [
                    {"id": c.get("id"), "logline": c.get("logline"),
                     "tone": c.get("tone"), "protagonist": c.get("protagonist"),
                     "world": c.get("world"), "threeAct": c.get("threeAct")}
                    for c in (story.get("candidates") or [])
                ],
            }
            print("STORY_PITCH=" + json.dumps(payload, ensure_ascii=False), flush=True)
            log("故事方向已生成：等用户选择后带 --stage treatment --story-choice <id> 重跑")
            return 0
        if stage not in ("auto", "produce"):
            log(f"❌ 未知 stage={stage!r}；可用 auto / pitch / treatment / produce")
            return 1
        if status not in ("treatment", "approved"):
            log("❌ 还没有确认的故事蓝图；请先跑 stage=treatment")
            return 1
        ok, note = st_story_bible(w, tl, plan, story, cfg, force="bible" in fset)
        if not ok:
            log(f"❌ 叙事视觉圣经：{note}")
            return 1
        log(f"叙事视觉圣经完成：{note}")

    if mode == "typographic":
        # 逐句重点：先定"每句点哪几个字"，样片和全片共用，保证主次一致。
        ok_e, note_e = st_type_emphasis(w, tl, plan, args.brief, cfg,
                                       force=("type-emphasis" in fset))
        log(f"重点标注：{note_e}" if ok_e else f"⚠ 重点标注未生成（{note_e}），画面按句自行判断")

        # 用户没指定字效、且要样片：先出 2~4 种 10 秒样片让用户选
        if not args.type_style and args.samples:
            log("③·5T 字效样片（2~4 种 × 10 秒）")
            ok_s, note_s, html, shown = st_type_samples(
                w, tl, plan, args.brief, cfg, song, args.fps,
                force=("type-samples" in fset), html_dir=args.samples_html_dir)
            if ok_s and html:
                print("TYPE_SAMPLE_HTML=" + str(html), flush=True)
                print("TYPE_SAMPLE_CHOICES=" + json.dumps(
                    [{"id": i, "label": type_styles.label(i)} for i in shown],
                    ensure_ascii=False), flush=True)
                log("字效样片已生成：等用户选择后带 --type-style <id> 重跑")
                return 0
            log(f"⚠ 字效样片未生成（{note_s}），改为自动选风格")

        # 文字类：不生成插画视觉圣经，也不生成氛围底图；先定字效方案
        log("④· 字效方案（文字类）")
        ok, note = st_typeplan(w, tl, plan, args.brief, cfg,
                               force="typeplan" in fset, forced_style=args.type_style)
        if not ok:
            log(f"❌ 字效方案：{note}")
            return 1
        log(f"字效方案：{note}")
        mark(st, "typeplan", True, sha(w / "type-plan.json"), [w / "type-plan.json"], note)
        save_state(w, st)
        if halt("typeplan"):
            return 0
    elif mode == "performance":
        # 4·5 视觉圣经：先把全片统一的美术规则定下来，再让各批照着画。
        # 非致命——失败只降级，不拦片；重跑时若文件在就复用。
        log("④· 视觉圣经（全片美术规则）")
        ok, note = st_bible(w, tl, plan, args.brief, cfg, force="bible" in fset, mode=mode)
        if not ok:
            log(f"⚠ 视觉圣经未生成（{note}），画面只按编导方案画")

        # 4·6 镜头表：每一镜的景别/机位/主体/动作/与上一镜的差异。
        # 没有它时画面作者只能按段落自由发挥，同段落的多镜会收敛成同一张构图。
        log("④·6 镜头表（逐镜导演指令）")
        ok_sl, note_sl = st_shotlist(w, tl, plan, args.brief, cfg, force="shotlist" in fset)
        if ok_sl:
            log(f"镜头表：{note_sl}")
        else:
            log(f"⚠ 镜头表未生成（{note_sl}），退回按段落自动分镜")
        if halt("shotlist"):
            return 0

        # 4·7 可选：段落氛围底图（AI 插画层）。未配置 Key 或生成失败都只跳过，不拦片。
        if args.with_images:
            log("④· 段落底图（可选 AI 插画层）")
            keys = ensure_section_images(w, tl, plan, args.max_images)
            if keys:
                log(f"可用底图：{' / '.join(keys)}")
            else:
                log("⚠ 没有可用底图，画面按纯 canvas 绘制")

    # 5 画面
    hdr("scenes")
    art = w / ("scenes.tsx" if TSX_ENGINE else "scenes.js")
    if mode == "narrative":
        sig_scenes = "v5:narrative:" + sha(
            w / "story.json", w / "visual-bible.json", w / "plan.json")
    else:
        asset_keys = ",".join(sorted((plan.get("assets") or {}).keys()))
        type_sig = sha(w / "type-plan.json") if (w / "type-plan.json").exists() else ""
        emph_sig = sha(w / "type-emphasis.json") if (w / "type-emphasis.json").exists() else ""
        shot_sig = sha(w / "shots.json") if (w / "shots.json").exists() else ""
        sig_scenes = ("v7:mode:" + mode
                      + (f"|type:{type_sig}" if type_sig else "")
                      + (f"|emph:{emph_sig}" if emph_sig else "")
                      + (f"|shots:{shot_sig}" if shot_sig else "")
                      + (f"|img:{asset_keys}" if asset_keys else ""))
    if TSX_ENGINE:
        sig_scenes += "|engine:remotion"
    # 有缺镜时不能算「画面完成」：否则重跑会直接跳到渲染，缺的那几镜永远是黑场。
    # 重跑画面段是安全的——已有镜头按代码哈希复用，只会补画缺的那几镜。
    has_missing = (w / "missing-shots.json").exists()
    if cached("scenes", sig_scenes) and art.exists() and not has_missing:
        log("跳过 画面代码")
        scenes = art
    else:
        if has_missing:
            log("上次有镜头没画出来，重跑画面段补画（已通过的镜头会复用）")
        if TSX_ENGINE:
            # 开放模式：镜头表（performance）→ 定妆（硬闸门）→ 并行拍镜 → 闸门
            shot_list = []
            if mode == "performance" and (w / "shots.json").exists():
                try:
                    shot_list = json.loads(
                        (w / "shots.json").read_text(encoding="utf-8-sig")).get("shots") or []
                except Exception:
                    shot_list = []
            ok, note, scenes = remotion_artist.generate(
                w, tl, plan, args.brief, cfg, _llm, dump, mode=mode,
                story=story if mode == "narrative" else None,
                shots=shot_list, force="scenes" in fset)
        elif mode == "narrative":
            ok, note, scenes = st_story_scenes(
                w, st, tl, plan, story, cfg, force="scenes" in fset)
        else:
            ok, note, scenes = st_scenes(w, st, tl, plan, args.brief, cfg,
                                         force="scenes" in fset, mode=mode)
        mark(st, "scenes", ok, sig_scenes, [art], note)
        save_state(w, st)
        if not ok:
            log(f"❌ 画面代码：{note}")
            return 1
    if TSX_ENGINE:
        write_render_plan(w, tl, plan, story if mode == "narrative" else None, mode)
    if halt("scenes"): return 0

    # 5·5 截图自查：让视觉模型回看几帧，出 review.json（非致命，不支持看图就跳过）
    if TSX_ENGINE:
        log("⑤· 截图自查：Remotion 引擎暂未接入（闸门已含运行时与确定性校验）")
    elif not args.no_review:
        log("⑤· 截图自查")
        okr, noter = st_review(w, tl, plan, cfg, scenes, mode=mode)
        if not okr:
            log(f"截图自查跳过（{noter}）")
        elif mode == "narrative" and not args.no_review_repair:
            notes0 = review_notes_by_shot(w)
            if not notes0:
                log("自查未发现需要修复的低分帧")
            elif not (w / "parts").exists():
                log("缺少 parts/（画面来自旧产物），跳过自查修复")
            else:
                notes = {b + 1: v for b, v in notes0.items()}
                batches = sorted(notes)[:REVIEW_REPAIR_MAX_BATCHES]
                log(f"自查反馈：{len(notes0)} 个镜头批待修 → 只重写第 {batches} 批")
                backup = w / "_review_backup"
                shutil.rmtree(backup, ignore_errors=True)
                shutil.copytree(w / "parts", backup / "parts")
                shutil.copy2(scenes, backup / "scenes.js")
                ok2, note2, scenes2 = st_story_scenes(
                    w, st, tl, plan, story, cfg,
                    only_batches=set(batches), review_notes=notes)
                if ok2:
                    scenes = scenes2
                    log(f"自查修复完成：{note2}，复核中...")
                    okr2, noter2 = st_review(w, tl, plan, cfg, scenes, n=4,
                                              tag="review-after", mode=mode)
                    log(f"复核{'完成' if okr2 else '跳过'}：{noter2}")
                    if okr2 and (w / "review-after.json").exists():
                        # 复核结果作为下一轮的基线，避免每次重跑都按旧低分再修一遍
                        shutil.copy2(w / "review-after.json", w / "review.json")
                else:
                    shutil.rmtree(w / "parts", ignore_errors=True)
                    shutil.copytree(backup / "parts", w / "parts")
                    shutil.copy2(backup / "scenes.js", scenes)
                    log(f"自查修复未通过（{note2}），已还原原画面")
                shutil.rmtree(backup, ignore_errors=True)
        elif mode == "narrative":
            log("叙事型自查只出报告（已关闭自查修复）")
        elif not args.no_review_repair:
            # 自查闭环：低分帧的问题回灌到对应批次，只重写这几批并重新过闸。
            notes = review_notes_by_line(w, tl)
            if not notes:
                log("自查未发现需要修复的低分帧")
            elif not (w / "parts").exists():
                log("缺少 parts/（画面来自旧产物），跳过自查修复")
            else:
                batches = sorted({i // SCENES_PER_CALL + 1 for i in notes})[:REVIEW_REPAIR_MAX_BATCHES]
                log(f"自查反馈：{len(notes)} 句待修 → 只重写第 {batches} 批")
                backup = w / "_review_backup"
                shutil.rmtree(backup, ignore_errors=True)
                shutil.copytree(w / "parts", backup / "parts")
                shutil.copy2(scenes, backup / "scenes.js")
                ok2, note2, scenes2 = st_scenes(
                    w, st, tl, plan, args.brief, cfg,
                    only_batches=set(batches), review_notes=notes, mode=mode)
                if ok2:
                    scenes = scenes2
                    log(f"自查修复完成：{note2}，复核中...")
                    okr2, noter2 = st_review(w, tl, plan, cfg, scenes, n=4,
                                              tag="review-after", mode=mode)
                    log(f"复核{'完成' if okr2 else '跳过'}：{noter2}")
                else:
                    shutil.rmtree(w / "parts", ignore_errors=True)
                    shutil.copytree(backup / "parts", w / "parts")
                    shutil.copy2(backup / "scenes.js", scenes)
                    log(f"自查修复未通过（{note2}），已还原原画面")
                shutil.rmtree(backup, ignore_errors=True)

    # 6 渲染
    hdr("render")
    plan_used = w / ("render-plan.json" if TSX_ENGINE else "plan.json")
    sig_render = sha((w / "timeline.json"), plan_used, scenes, song, (w / "look.json"))
    if cached("render", sig_render) and (w / "mv.mp4").exists():
        log("跳过 逐帧渲染")
        out = w / "mv.mp4"
    else:
        if TSX_ENGINE:
            ok, note, out = st_render_tsx(w, st, tl, plan, song, args.fps,
                                          force="render" in fset)
        else:
            ok, note, out = st_render(w, st, tl, plan, scenes, song, args.fps)
        mark(st, "render", ok, sig_render, [out] if out else [], note)
        save_state(w, st)
        if not ok:
            log(f"❌ 渲染：{note}")
            return 1

    # 6b 片尾：按字效风格生成「Sigma 制作」动画并追加（幂等，失败不影响成片）
    try:
        from skills.compose_video.scripts.sigma_outro import append_outro, recipe_for_lyric
        style_id = args.type_style or str((plan or {}).get("typeStyle") or "")
        recipe = recipe_for_lyric(style_id)
        out = Path(append_outro(str(out), recipe))
        log(f"片尾已追加：{recipe}（{out.name}）")
    except Exception as e:
        log(f"片尾生成失败（不影响成片）：{e}")
    if halt("render"): return 0

    # 7 验收
    hdr("accept")
    ok, note = st_accept(st, out)
    mark(st, "accept", ok, sha(out), [out], note)
    save_state(w, st)
    log(("✅ 验收通过：" if ok else "❌ 验收失败：") + note)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        # 未捕获异常必须落 last_error.json：否则上游只能看到"MV 制作失败 / 读不到"，
        # 完全无法定位是哪一步崩的（之前渲染段整段就是被这个吞掉的）。
        import traceback
        tb = traceback.format_exc()
        try:
            d = globals().get("_LOGDIR")
            if d:
                # 先 log（它会把 last_error 写成一句泛泛的话），再写带 traceback 的版本，
                # 顺序反过来就会被覆盖 —— 之前就是这样把真正的报错弄丢的。
                log("❌ 未捕获异常，详情见 last_error.json 的 traceback")
                (d / "last_error.json").write_text(json.dumps({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "message": "❌ pipeline 崩溃（未捕获异常，不是模型问题）：\n" + tb[-3000:],
                    "log": str(d / "run.log"),
                    "how_to_debug": "先看 message 里的 traceback；若在渲染段，"
                                    "可直接手动跑 remotion_runtime/scripts/render_mv.py 复现。",
                }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        raise
