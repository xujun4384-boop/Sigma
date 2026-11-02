# -*- coding: utf-8 -*-
"""lyric_mv —— 歌词 MV 制作技能

把一首歌做成「卡点逐字歌词」的 MV 动画视频。
支持两种音源：技能生成歌曲 / 用户指定音乐文件；卡点链路完全相同（都由音频实测）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from skills.base import BaseTool, ToolParameter, ToolResult
from .type_styles import ids as type_style_ids

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = HERE / "scripts"
PIPELINE = SCRIPTS / "pipeline.py"


class LyricMvTool(BaseTool):
    name = "lyric_mv"
    description = (
        "把一首歌做成卡点逐字歌词的 MV 动画视频（带音乐成品 mp4）。\n"
        "1. 只给 lyrics：本技能生成歌曲（音乐+人声），再测拍、对齐逐字、渲染。\n"
        "2. 给 audio（用户自己的音乐文件）+ lyrics：直接为这首歌做动画，卡点效果一致。\n"
        "3. 给 audio、不给 lyrics：自动转写人声当歌词（可能有错字）。\n"
        "4. 只给 audio 且是纯器乐：画面按拍与段落走，无歌词层。\n"
        "5. 画面不指定任何预设画风：由画面作者自己决定怎么画（可用 Remotion 的完整能力），"
        "引擎只负责时间轴、歌词层与渲染。\n"
        "brief 用来提编排要求（题材、情绪、开场形式、禁止项），优先级最高。\n"
        "模式 mode：auto（默认，LLM 判断）/ narrative 叙事（整片讲一个故事）/ "
        "performance 表演（舞台与歌词）/ typographic 文字（文字即画面，自动关闭独立歌词层）。\n"
        "叙事型分三步：stage=pitch 出 2~3 个故事方向 → ask_user → "
        "stage=treatment + story_choice 出故事蓝图与镜头表 → ask_user 确认 → "
        "stage=produce 生成视觉圣经、镜头与成片。\n"
        "可选 with_images=true：按段落生成 AI 氛围底图（只做背景层，主体仍由 canvas 画）；"
        "需要已配置图片生成 Key，默认关闭。\n"
        "重要：画面代码由 pipeline 内的 LLM 带着编导方案/视觉圣经/逐镜上下文生成；"
        "失败时不要把 parts/*.tsx 改成手写代码，用同一个 out_dir 重跑或按 run.log 调整参数，"
        "避免上下文丢失、前后画面接不上。\n"
        "断点续跑：用同一个 out_dir 再调一次就是续跑，已完成阶段与已通过的镜头都会复用"
        "（状态在 mv_state.json，逐镜通过记录在 art/shots/），不需要预先检查或另起目录。"
        "要强制重画某一段传 force（如 force='scenes'），只影响点名的那一段。\n"
        "个别镜头最终画不出来不会阻塞整片：会记入 missing-shots.json，该处留兜底黑场。\n"
        "产物：<out_dir>/mv.mp4，以及 timeline.json / plan.json / story.json / "
        "parts/*.tsx（镜头源码）/ render-plan.json / run.log。"
    )
    parameters = [
        ToolParameter("lyrics", "string",
                      "歌词全文（含 [Verse]/[Chorus] 等结构标签）。不传则视为纯器乐", required=False),
        ToolParameter("audio", "string",
                      "用户指定的音乐文件路径（mp3/wav/m4a/flac）。不传则由本技能生成歌曲", required=False),
        ToolParameter("brief", "string",
                      "编排要求：风格、开场形式、标题位置、情绪、禁止项等。优先级高于模型自主选择", required=False),
        ToolParameter("out_dir", "string", "产物目录，默认 cwd/lyric_mv_out", required=False),
        ToolParameter("t0", "number",
                      "首句人声起始秒数（人工锚点）。ASR 定错首句时用它兜底", required=False),
        ToolParameter("synth_prompt", "string",
                      "生成歌曲时的音乐风格提示（仅在未给 audio 时生效）", required=False),
        ToolParameter("mode", "string",
                      "MV 模式：auto（默认，由 LLM 判断）/ narrative 叙事（整片讲一个故事）/ "
                      "performance 表演（舞台与歌词）/ typographic 文字（文字即画面）",
                      required=False, default="auto",
                      enum=["auto", "narrative", "performance", "typographic"]),
        ToolParameter("engine", "string",
                      "渲染引擎：remotion（默认，共享 Remotion 运行时，画面表现力最强）/ "
                      "canvas（旧逐帧引擎，保留兜底）",
                      required=False, default="remotion", enum=["remotion", "canvas"]),
        ToolParameter("stage", "string",
                      "叙事型阶段：auto 按 story.json 状态推进 / pitch 故事方向 / "
                      "treatment 故事蓝图 / produce 产出。其他模式忽略",
                      required=False, default="auto",
                      enum=["auto", "pitch", "treatment", "produce"]),
        ToolParameter("story_choice", "string",
                      "叙事型：从 pitch 进入 treatment 时指定候选方向 id",
                      required=False),
        ToolParameter("revise", "boolean",
                      "叙事型：用户说换一批/不满意时传 true，强制重新生成故事方向或蓝图；"
                      "同时把修改意见写进 brief",
                      required=False, default=False),
        ToolParameter("type_style", "string",
                      "文字类：强制字效风格；不传由 LLM 选",
                      required=False, default="", enum=[""] + type_style_ids()),
        ToolParameter("with_images", "boolean",
                      "是否按段落生成 AI 氛围底图（背景层，主体仍由 canvas 画）。默认 false；"
                      "需要已配置图片生成 Key",
                      required=False, default=False),
        ToolParameter("max_images", "integer",
                      "最多生成几张段落底图，默认 6", required=False, default=6),
        ToolParameter("force", "string",
                      "强制重跑某几段（逗号分隔）：plan / story / bible / scenes / render。"
                      "只影响点名的那几段，其余产物照常复用；不传＝全部按签名续跑",
                      required=False, default=""),
    ]

    def __init__(self, cwd: str = ".", llm_config: dict = None,
                 image_config: dict = None, **kwargs):
        super().__init__(cwd)
        # 编导与画面要 LLM 现场创作：复用主 LLM 配置（由 server.py 注入），
        # 不自己去读前端存储——那种做法格式一变就废。
        self.llm_config = llm_config or {}
        # 可选 AI 插画层：图片生成配置同样由外部注入
        self.image_config = image_config or {}

    def execute(self, lyrics: str = "", audio: str = "", brief: str = "",
                out_dir: str = "", t0: float = None,
                synth_prompt: str = "",
                mode: str = "auto", stage: str = "auto", story_choice: str = "",
                revise: bool = False, type_style: str = "",
                with_images: bool = False,
                max_images: int = 6, engine: str = "remotion", force: str = "", **kw) -> ToolResult:
        work = self._resolve_path(out_dir) if out_dir else (Path(self.cwd) / "lyric_mv_out")
        work.mkdir(parents=True, exist_ok=True)

        lyrics_file = ""
        if lyrics and lyrics.strip():
            lyrics_file = str(work / "lyrics.txt")
            Path(lyrics_file).write_text(lyrics, encoding="utf-8")

        cmd = [sys.executable, str(PIPELINE), "--work", str(work), "--run",
               "--engine", engine or "remotion"]
        if lyrics_file:
            cmd += ["--lyrics", lyrics_file]
        if audio:
            cmd += ["--audio", audio]
        if brief:
            cmd += ["--brief", brief]
        if t0 is not None:
            cmd += ["--t0", str(t0)]
        if synth_prompt:
            cmd += ["--synth-prompt", synth_prompt]
        if mode and mode != "auto":
            cmd += ["--mode", mode]
        if stage and stage != "auto":
            cmd += ["--stage", stage]
        if story_choice:
            cmd += ["--story-choice", story_choice]
        if revise:
            cmd += ["--revise"]
        if type_style:
            cmd += ["--type-style", type_style]
        if with_images:
            cmd += ["--with-images", "--max-images", str(max(0, int(max_images or 0)))]
        if force:
            cmd += ["--force", force]

        # LLM 配置走环境变量传子进程：不进 argv（进程列表可见）、不进日志。
        env = dict(os.environ)
        cfg = self.llm_config or {}
        if cfg.get("api_key") and cfg.get("base_url") and cfg.get("model"):
            env["LYRIC_MV_LLM"] = json.dumps({
                "api_key": cfg.get("api_key"), "base_url": cfg.get("base_url"),
                "model": cfg.get("model"), "protocol": cfg.get("protocol", "anthropic"),
                "provider": cfg.get("provider"), "thinking": cfg.get("thinking"),
            }, ensure_ascii=False)
        else:
            return ToolResult.fail(
                "主 LLM 配置不完整（需要 base_url / api_key / model），"
                "lyric_mv 的编导与画面需要调用 LLM 现场创作，无法继续。")

        # 图片生成配置同样走环境变量；没配 Key 时 pipeline 会自动退回纯 canvas
        if with_images:
            img = self.image_config or {}
            if img.get("api_key"):
                env["LYRIC_MV_IMAGE"] = json.dumps({
                    "provider": img.get("provider", "ark"),
                    "api_key": img.get("api_key"),
                    "base_url": img.get("base_url", ""),
                    "model": img.get("model", ""),
                }, ensure_ascii=False)

        # 流式读取：pipeline 每推进一步就上报一次，前端能看到"跑到哪了"，
        # 不再是盲盒（整条链 30 分钟量级，不给进度根本没法判断是在跑还是卡死）。
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                cwd=str(SCRIPTS), env=env)
        except OSError as e:
            return ToolResult.fail(f"无法启动制作流程：{e}")

        lines = []
        try:
            for raw in proc.stdout:
                ln = raw.rstrip()
                if not ln.strip():
                    continue
                lines.append(ln)
                self._emit_progress(ln)
                if self.is_cancelled():
                    proc.kill()
                    return ToolResult.fail("已取消，制作中止（已完成的部分保留，"
                                           "重跑会从断点继续）。")
            proc.wait(timeout=600)
        finally:
            if proc.poll() is None:
                proc.kill()
        rc = proc.returncode
        out = "\n".join(lines)
        mv = work / "mv.mp4"
        log_path = work / "run.log"
        err_path = work / "last_error.json"

        def _tail(path, n=1200):
            try:
                return Path(path).read_text(encoding="utf-8")[-n:]
            except Exception:
                return "（读不到）"

        # 模式判断需要用户确认：pipeline 已停下，这不是失败
        mode_choices = []
        for ln in lines:
            if ln.startswith("MODE_CHOICES="):
                try:
                    mode_choices = json.loads(ln.split("=", 1)[1])
                except Exception:
                    mode_choices = []
        if mode_choices:
            opts = "\n".join(
                f"- {c.get('label')}（{c.get('id')}）：{c.get('why') or '—'}"
                for c in mode_choices)
            return ToolResult.ok(
                f"这首歌需要先确认 MV 模式（自动判断存在两种以上合理选择）：\n{opts}\n\n"
                f"请**立刻调用 ask_user** 让用户选择，不要替用户决定：\n"
                f"问题：「这支 MV 用哪种模式？」\n\n"
                f"用户选完后，带 mode=<对应 id> 用同一个 out_dir 重跑 lyric_mv"
                f"（audio/lyrics/brief 保持不变）。三种模式的区别：\n"
                f"- narrative：整片讲一个完整故事，歌词层照常显示\n"
                f"- performance：舞台/表演者 + 歌词逐句推进\n"
                f"- typographic：文字就是画面，没有独立字幕层\n\n"
                f"完整日志：{log_path}")

        # 叙事型：故事方向 / 故事蓝图需要用户确认
        story_pitch, story_treatment = None, None
        for ln in lines:
            if ln.startswith("STORY_PITCH="):
                try:
                    story_pitch = json.loads(ln.split("=", 1)[1])
                except Exception:
                    story_pitch = None
            elif ln.startswith("STORY_TREATMENT="):
                try:
                    story_treatment = json.loads(ln.split("=", 1)[1])
                except Exception:
                    story_treatment = None

        if story_pitch:
            cands = story_pitch.get("candidates") or []
            opts = "\n".join(
                f"- {c.get('id')}｜{c.get('logline') or ''}\n"
                f"  主角：{c.get('protagonist') or '—'}｜世界：{c.get('world') or '—'}\n"
                f"  三幕：{c.get('threeAct') or '—'}"
                for c in cands)
            rec = story_pitch.get("recommend") or ""
            return ToolResult.ok(
                f"叙事型：先确认故事方向。\n{opts}\n\n"
                f"推荐：{rec}（{story_pitch.get('why') or '—'}）\n\n"
                f"请**立刻调用 ask_user** 让用户选择，不要替用户决定：\n"
                f"问题：「这个故事方向可以吗？也可以换一个。」\n\n"
                f"用户选完后，带 mode=narrative, stage=treatment, story_choice=<id> "
                f"用同一个 out_dir 重跑 lyric_mv（audio/lyrics/brief 不变）。\n"
                f"如果用户对这批方向都不满意，带 mode=narrative, stage=pitch, revise=true，"
                f"并把修改意见写进 brief，重新出 2~3 个方向。\n"
                f"完整日志：{log_path}")

        if story_treatment:
            shots = story_treatment.get("shots") or []
            acts = story_treatment.get("acts") or []
            act_text = "\n".join(
                f"- {a.get('name', '')}：{a.get('summary', '')}" for a in acts) or "—"
            shot_text = "\n".join(
                f"- {s.get('id')}｜{s.get('start')}~{s.get('end')}s｜"
                f"{s.get('size') or ''}｜{s.get('action') or ''}"
                for s in shots[:10])
            more = f"\n…另有 {len(shots) - 10} 个镜头" if len(shots) > 10 else ""
            return ToolResult.ok(
                f"叙事型：故事蓝图已生成，等用户确认。\n"
                f"标题：{story_treatment.get('title') or '—'}\n"
                f"故事：{story_treatment.get('logline') or '—'}\n"
                f"主角：{story_treatment.get('protagonist') or '—'}\n"
                f"场景：{'、'.join(story_treatment.get('locations') or []) or '—'}\n"
                f"幕：\n{act_text}\n"
                f"镜头（共 {len(shots)} 个）：\n{shot_text}{more}\n\n"
                f"请**立刻调用 ask_user** 让用户确认或提出修改，不要替用户决定：\n"
                f"问题：「这个故事蓝图可以开始制作吗？」\n\n"
                f"用户确认后，带 mode=narrative, stage=produce 用同一个 out_dir 重跑 lyric_mv；"
                f"要改故事就带 stage=treatment、revise=true，并把修改意见写进 brief。\n"
                f"完整日志：{log_path}")

        # 文字类：2~4 种字效样片，等用户选 type_style
        type_html, type_choices = "", []
        for ln in lines:
            if ln.startswith("TYPE_SAMPLE_HTML="):
                type_html = ln.split("=", 1)[1].strip()
            elif ln.startswith("TYPE_SAMPLE_CHOICES="):
                try:
                    type_choices = json.loads(ln.split("=", 1)[1])
                except Exception:
                    type_choices = []
        if type_html and type_choices:
            opts = "\n".join(f"- {c.get('label')}（{c.get('id')}）" for c in type_choices)
            return ToolResult.ok(
                f"文字类字效样片已生成：{type_html}\n"
                f"（Sigma 的 HTML 面板会自动打开这个文件；视频已内嵌，可直接播放对比）\n\n"
                f"请**立刻调用 ask_user** 让用户选字效，不要替用户决定：\n"
                f"问题：「文字类用哪种字效？」\n{opts}\n\n"
                f"用户选完后，带 mode=typographic, type_style=<对应 id> "
                f"用同一个 out_dir 重跑 lyric_mv（audio/lyrics/brief 保持与本次相同）。\n"
                f"完整日志：{log_path}")

        missing_p = work / "missing-shots.json"
        if rc != 0 or not mv.exists():
            hint = (f"\n\n【断点】重跑同一个 out_dir 会从断点继续：已完成的阶段和已通过的镜头都会复用，"
                    f"不需要清理目录或另起 out_dir。")
            if missing_p.exists():
                hint += f"\n【缺镜】有镜头最终没画出来，见 {missing_p}；补跑只会重画缺失的那几镜。"
            return ToolResult.fail(
                f"MV 制作失败。\n"
                f"【先看】{err_path}\n{_tail(err_path, 600)}\n\n"
                f"【完整日志】{log_path}\n{_tail(log_path, 2500)}\n\n"
                f"【排错提示】每次模型调用的原始输出与元信息在 {work / 'llm'} 目录："
                f"*-prompt.txt 是提问，*-t1-meta.txt 是 stop_reason/思考 token，"
                f"*-t1-truncated.txt 表示这次输出被截断（需要精简或提高输出预算）。"
                + hint)
        extra = ""
        if missing_p.exists():
            extra = f"\n注意：{missing_p.read_text(encoding='utf-8').strip()} 这几镜没画出来，成片里是黑场。"
        return ToolResult.ok(
            f"MV 已生成：{mv}\n"
            f"（大小 {mv.stat().st_size / 1048576:.1f} MB）{extra}\n"
            f"可二次修改的产物：timeline.json / plan.json / story.json / parts/*.tsx —— "
            f"改完用同一个 out_dir 重跑，只会重做受影响的部分，其余复用。\n"
            f"完整日志：{log_path}\n\n{out[-1200:]}")


__all__ = ["LyricMvTool"]
