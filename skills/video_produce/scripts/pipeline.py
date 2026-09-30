"""video_produce 流水线核心

5 个固定 stage，顺序执行（有 1 才有 2），每个 stage 失败重试 6 次，超过熔断。
流程顺序由本文件写死，LLM 不能跳步/乱序，只能决定每个 stage 的「内容」。

  narration  旁白生成   scenes.narration → mp3 + 权威时长 + 字级时间戳
  storyboard 画面规划   design LLM 决定图需求清单（要不要图、要什么图）
  images     配图       image_generate 按图需求生成图
  video      画面生成   opendesign 写 HTML + hyperframes 渲染（时长=旁白时长）
  compose    合成       video_compose 叠加旁白 + 字幕
"""
import json
from datetime import datetime
from pathlib import Path

# 每个 stage 的整体重试上限（含其内部子任务的重试）。
# 画面生成等 stage 内部已对每段独立重试，这里只需兜底一次，避免「段内 6 次 × 段数 × stage 6 次」的重试风暴。
MAX_RETRY = 3

# 单段画面生成的最大旁白时长（秒），超过则拆成多段生成，避免单片 HTML 过长卡住 LLM
MAX_SEGMENT_DURATION = 25

# 同时写 HTML 的段数上限：写 HTML 依赖单个 LLM 接口，并发过高容易限流/互相拖慢。
# 实测（Kimi K3）并发写多段几乎必然超时，串行反而最稳，先设为 1。
LLM_CONCURRENCY = 1

STAGES = ["script", "narration", "storyboard", "images", "video", "compose"]

STAGE_LABELS = {
    "script": "脚本设计",
    "narration": "旁白生成",
    "storyboard": "画面规划",
    "images": "配图",
    "video": "画面生成",
    "compose": "合成",
}

# Stage 0 脚本设计的 system prompt（让 design LLM 根据需求设计脚本）
_SCRIPT_PROMPT = """你是一位视频脚本设计师。根据用户需求，设计一个完整的视频脚本。

只输出 JSON，不要输出解释或 markdown：
{"title": "视频标题", "style_prompt": "视觉风格描述", "scenes": [{"narration": "第1镜旁白文案", "visual": "第1镜画面描述"}]}

要求：
- 旁白文案口语化、适合朗读，每镜一句话
- 画面描述具体，便于后续设计 HTML 动画
- 场景数量适中（3~8 个）
- 不要定总时长（时长由旁白实际读速决定）
- 前3秒要有钩子抓住注意力，脚本三段式：钩子 → 正文 → 收尾
"""


# Stage 2 画面规划的 system prompt（让 design LLM 决定图需求）
_STORYBOARD_PROMPT = """你是一位视频画面设计师。根据给定的视频脚本，规划画面方案，并决定需要哪些配图。

只输出 JSON，不要输出解释或 markdown：
{"images": [{"prompt": "图片生成提示词", "scene_index": 0, "purpose": "用途"}]}

规则：
- 如果画面用纯 CSS/文字排版就能表达（标题、卡片、图标、图表），images 返回空数组 []
- 只有画面确实需要配图（产品图、实景图、背景图、人物图等）时才生成图
- 每张图都要有明确用途，scene_index 对应分镜下标（从 0 开始）
- 图片数量尽量克制，能少则少
"""


class PipelineAbortError(Exception):
    """某 stage 重试 6 次仍失败，熔断。"""

    def __init__(self, stage: str, error: Exception, artifacts: dict):
        self.stage = stage
        self.error = error
        self.artifacts = artifacts
        super().__init__(f"阶段「{STAGE_LABELS[stage]}」重试 {MAX_RETRY} 次仍失败: {error}")


def _load_state(state_file: Path) -> dict | None:
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError):
        return None


def _save_state(state_file: Path, completed: set, artifacts: dict):
    state_file.write_text(
        json.dumps(
            {"completed": sorted(completed), "artifacts": artifacts},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def run_pipeline(
    *,
    brief: str,
    script: str = None,
    output_path: str,
    project: str,
    speaker: str,
    skill_manager,
    opendesign_llm_config: dict,
    fps: int,
    width: int,
    height: int,
    progress,
) -> dict:
    """执行流水线：Stage 0 脚本设计（design LLM）→ 确认后 → Stage 1-5 自动执行。"""
    out = Path(output_path)
    work_dir = out.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    state_file = work_dir / f"{out.stem}_state.json"

    # 任务产物根目录：本任务所有中间产物（旁白/配图/每段画面/字幕）统一收纳，
    # 每段一个子文件夹，避免散落在 work_dir 里；最终成品仍写到 output_path。
    parts_root = work_dir / f"{out.stem}_parts"
    (parts_root / "voice").mkdir(parents=True, exist_ok=True)
    (parts_root / "assets").mkdir(parents=True, exist_ok=True)

    # 进度同时落盘到 pipeline.log，便于卡住时查看内部进展（前端流式进度不落日志）
    log_path = work_dir / f"{out.stem}_pipeline.log"
    _orig_progress = progress
    def _progress(msg: str):
        _orig_progress(msg)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%H:%M:%S')} {msg}\n")
        except OSError:
            pass
    progress = _progress

    state = _load_state(state_file)
    completed = set(state.get("completed", [])) if state else set()
    artifacts = state.get("artifacts", {}) if state else {}

    # 二次调用：传入确认后的脚本，覆盖脚本设计完成。
    # 脚本一旦（重新）确认，脚本之后的所有产物都必须基于新脚本重新生成——
    # 旧旁白/画面/字幕时间戳可能来自过期脚本或旧版本代码（如 words 只含末句的 bug），
    # 不能续用。故把 script 之后的阶段全部重置，仅保留新脚本本身。
    if script:
        parsed = _parse_script(script)
        if parsed:
            artifacts["script"] = parsed
            artifacts["script_raw"] = script
            artifacts["title"] = parsed.get("title", "")
            artifacts["style_prompt"] = parsed.get("style_prompt", "")
            artifacts["scenes"] = parsed.get("scenes", [])
            # 仅保留 script 已完成，后续 stage 全部重跑
            completed = {"script"}
            _save_state(state_file, completed, artifacts)

    for stage in STAGES:
        if stage in completed:
            progress(f"⏭ 跳过已完成阶段: {STAGE_LABELS[stage]}")
            continue

        progress(f"▶ 阶段 {STAGE_LABELS[stage]}...")
        last_err = None
        for attempt in range(1, MAX_RETRY + 1):
            try:
                artifacts = _run_stage(
                    stage, brief, out, work_dir, parts_root, project, speaker,
                    skill_manager, opendesign_llm_config,
                    fps, width, height, artifacts, progress,
                )
                completed.add(stage)
                _save_state(state_file, completed, artifacts)
                progress(f"✔ 阶段完成: {STAGE_LABELS[stage]}")
                last_err = None
                break
            except Exception as e:
                last_err = e
                progress(f"✗ 阶段失败({attempt}/{MAX_RETRY}): {STAGE_LABELS[stage]} - {e}")

        if last_err is not None:
            raise PipelineAbortError(stage, last_err, artifacts)

        # 脚本设计完成 → 返回脚本，等用户确认（不继续后续阶段）
        if stage == "script":
            return {"need_confirm": True, "script": artifacts.get("script"), "script_raw": artifacts.get("script_raw")}

    return {"output_path": str(out), "artifacts": artifacts, "duration": artifacts.get("total_duration", 0)}


def _run_stage(stage, brief, out, work_dir, parts_root, project, speaker,
               skill_manager, opendesign_llm_config,
               fps, width, height, artifacts, progress):
    if stage == "script":
        return _stage_script(brief, artifacts, opendesign_llm_config, progress)
    if stage == "narration":
        return _stage_narration(artifacts, parts_root, project, speaker, skill_manager, progress)
    if stage == "storyboard":
        return _stage_storyboard(artifacts, opendesign_llm_config, progress)
    if stage == "images":
        return _stage_images(parts_root, project, artifacts, skill_manager, progress)
    if stage == "video":
        return _stage_video(out, parts_root, project, artifacts, opendesign_llm_config, skill_manager, fps, width, height, progress)
    if stage == "compose":
        return _stage_compose(out, parts_root, project, artifacts, skill_manager, fps, width, height, progress)
    raise ValueError(f"未知阶段: {stage}")


# ── Stage 0: 脚本设计（design LLM） ──

def _stage_script(brief, artifacts, opendesign_llm_config, progress):
    from skills.opendesign.scripts.renderer import call_llm_text

    cfg = opendesign_llm_config
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        raise RuntimeError("design LLM 未配置，无法设计脚本")

    raw = call_llm_text(
        system_prompt=_SCRIPT_PROMPT,
        context=f"用户需求：\n{brief}",
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        protocol=cfg.get("protocol", "anthropic"),
        max_tokens=4096,
    )
    parsed = _parse_script(raw)
    if not parsed or not parsed.get("scenes"):
        raise RuntimeError("脚本设计失败：未能解析出有效脚本")

    artifacts["script"] = parsed
    artifacts["script_raw"] = raw
    artifacts["title"] = parsed.get("title", "")
    artifacts["style_prompt"] = parsed.get("style_prompt", "")
    artifacts["scenes"] = parsed.get("scenes", [])
    return artifacts


def _parse_script(raw: str) -> dict:
    """从 design LLM 输出中解析脚本 {title, style_prompt, scenes}。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return {}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {}
    if not isinstance(data, dict):
        return {}
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        return {}
    return {
        "title": str(data.get("title", "")),
        "style_prompt": str(data.get("style_prompt", "")),
        "scenes": [
            {"narration": str(s.get("narration", "")), "visual": str(s.get("visual", ""))}
            for s in scenes if isinstance(s, dict)
        ],
    }


# ── Stage 1: 旁白生成 ──

def _stage_narration(artifacts, parts_root, project, speaker, skill_manager, progress):
    scenes = artifacts.get("scenes", [])
    voice_dir = Path(parts_root) / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    vo_paths = []
    all_words = []
    total_duration = 0.0

    # 用 ffprobe 探测 mp3 实际时长（含尾部停顿），保证分镜时长/字幕时间轴对齐真实旁白。
    # words 末字 endTime 会少算每句 ~0.3~0.9s 尾音，段级累积会漂移，不能作为权威时长。
    from skills.video_generate.scripts.composer import _probe_duration

    for i, scene in enumerate(scenes):
        narration = (scene.get("narration") or "").strip()
        if not narration:
            continue
        vo_path = str(voice_dir / f"vo_{i}.mp3")
        result = skill_manager.dispatch(
            "doubao_tts", text=narration, output_path=vo_path,
            project=project, speaker=speaker,
        )
        if not result.success:
            raise RuntimeError(f"旁白生成失败(分镜{i}): {result.content}")

        words = result.details.get("words", [])
        out_path = result.details.get("output_path", vo_path)
        # 权威时长 = mp3 实际时长（合成后落盘，探测真实长度）
        try:
            duration = _probe_duration(out_path)
        except Exception:
            duration = result.details.get("duration", 0)
        vo_paths.append(out_path)
        all_words.append({"scene_index": i, "offset": round(total_duration, 3), "words": words})
        total_duration += duration

    artifacts["vo_paths"] = vo_paths
    artifacts["words_by_scene"] = all_words
    artifacts["total_duration"] = round(total_duration, 2)
    return artifacts


# ── Stage 2: 画面规划（design LLM 决定图需求） ──

def _stage_storyboard(artifacts, opendesign_llm_config, progress):
    from skills.opendesign.scripts.renderer import call_llm_text

    cfg = opendesign_llm_config
    if not (cfg.get("base_url") and cfg.get("api_key") and cfg.get("model")):
        raise RuntimeError("design LLM 未配置，无法进行画面规划")

    scenes = artifacts.get("scenes", [])
    title = artifacts.get("title", "")
    style_prompt = artifacts.get("style_prompt", "")

    context = (
        "视频脚本如下，请规划画面方案并决定需要哪些配图。\n\n"
        f"标题：{title or '未命名'}\n"
        f"视觉风格：{style_prompt or '现代简洁'}\n"
        f"旁白总时长：{artifacts.get('total_duration', 0)} 秒\n"
        f"分镜（含旁白文案与画面描述）：\n{json.dumps(scenes, ensure_ascii=False, indent=2)}\n"
    )
    raw = call_llm_text(
        system_prompt=_STORYBOARD_PROMPT,
        context=context,
        base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
        protocol=cfg.get("protocol", "anthropic"),
        max_tokens=4096,
    )
    images = _parse_image_plan(raw)
    artifacts["image_plan"] = images
    return artifacts


def _parse_image_plan(raw: str) -> list:
    """从 design LLM 输出中解析图需求清单，失败返回空列表（不强求配图）。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    images = data.get("images", []) if isinstance(data, dict) else []
    return [img for img in images if isinstance(img, dict) and img.get("prompt")]


# ── Stage 3: 配图 ──

def _stage_images(parts_root, project, artifacts, skill_manager, progress):
    plan = artifacts.get("image_plan", [])
    if not plan:
        artifacts["image_paths"] = []
        return artifacts

    assets_dir = Path(parts_root) / "assets"
    image_paths = []
    for idx, item in enumerate(plan):
        result = skill_manager.dispatch(
            "generate_image",
            prompt=item.get("prompt", ""),
            save_dir=str(assets_dir),
        )
        if not result.success:
            raise RuntimeError(f"配图失败(第{idx}张): {result.content}")
        image_paths.append(result.details.get("filepath", ""))

    artifacts["image_paths"] = image_paths
    artifacts["assets_dir"] = str(assets_dir)
    return artifacts


# ── Stage 4: 画面生成（拆段 + 并行） ──

def _scene_durations(artifacts):
    """返回每个场景的旁白时长列表（秒）。"""
    words_by_scene = artifacts.get("words_by_scene", [])
    total = artifacts.get("total_duration", 0)
    durations = []
    for i, wbs in enumerate(words_by_scene):
        start = wbs.get("offset", 0)
        end = words_by_scene[i + 1].get("offset", 0) if i + 1 < len(words_by_scene) else total
        durations.append(max(round(end - start, 2), 0.5))
    return durations


def _split_segments(artifacts):
    """按场景分组拆段，每段累计旁白时长 ≤ MAX_SEGMENT_DURATION。"""
    scenes = artifacts.get("scenes", [])
    vo_paths = artifacts.get("vo_paths", [])
    durations = _scene_durations(artifacts)

    segments = []
    cur_indices, cur_vos, cur_dur = [], [], 0.0
    start_offset = 0.0

    for i, scene in enumerate(scenes):
        dur = durations[i] if i < len(durations) else 1.0
        if cur_indices and cur_dur + dur > MAX_SEGMENT_DURATION:
            segments.append(_make_segment(len(segments), cur_indices, cur_vos, cur_dur, start_offset, scenes))
            start_offset += cur_dur
            cur_indices, cur_vos, cur_dur = [], [], 0.0
        cur_indices.append(i)
        cur_vos.append(vo_paths[i] if i < len(vo_paths) else "")
        cur_dur += dur

    if cur_indices:
        segments.append(_make_segment(len(segments), cur_indices, cur_vos, cur_dur, start_offset, scenes))

    return segments


def _make_segment(index, indices, vos, duration, start_offset, scenes):
    return {
        "index": index,
        "scene_indices": indices,
        "scenes": [scenes[j] for j in indices],
        "vo_paths": list(vos),
        "duration": round(duration, 2),
        "start_offset": round(start_offset, 2),
    }


def _seg_dir(parts_root, index) -> Path:
    """每段独立文件夹，便于单段交付/重试/检查。"""
    d = Path(parts_root) / f"seg_{index}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _generate_segment(seg, seg_dir, project, artifacts, skill_manager, fps, width, height, progress):
    title = artifacts.get("title", "")
    style_prompt = artifacts.get("style_prompt", "")
    n_scenes = len(seg["scenes"])
    brief = (
        f"标题：{title or '未命名'}\n"
        f"视觉风格：{style_prompt or '现代简洁'}\n"
        f"本段时长：{seg['duration']} 秒，共 {n_scenes} 个场景。\n"
        f"分镜（画面内容 + 旁白文案，画面时长需匹配旁白）：\n"
        f"{json.dumps(seg['scenes'], ensure_ascii=False, indent=2)}\n"
    )
    seg_mp4 = str(seg_dir / "video.mp4")
    progress(f"生成第 {seg['index'] + 1} 段画面（{seg['duration']}s，{n_scenes} 场景）...")
    result = skill_manager.dispatch(
        "opendesign_video",
        brief=brief,
        output_path=seg_mp4,
        project=project,
        duration_s=int(round(seg["duration"])),
        n_scenes=n_scenes,
        style_prompt=style_prompt,
        assets_dir=artifacts.get("assets_dir"),
        fps=fps, width=width, height=height,
    )
    if not result.success:
        raise RuntimeError(f"第 {seg['index'] + 1} 段画面生成失败: {result.content}")
    seg["video"] = result.details.get("output_path", seg_mp4)
    seg["dir"] = str(seg_dir)
    return seg


def _merge_audios(vo_paths, output_path):
    """把多个旁白 mp3 合并成单音频，供一段画面对齐；始终写入 output_path。"""
    valid = [p for p in vo_paths if p and Path(p).exists()]
    if not valid:
        return ""
    if len(valid) == 1:
        import shutil
        shutil.copy2(valid[0], output_path)
        return str(output_path)
    from moviepy import AudioFileClip, concatenate_audioclips
    clips = [AudioFileClip(p) for p in valid]
    merged = concatenate_audioclips(clips)
    merged.write_audiofile(str(output_path), logger=None)
    for c in clips:
        c.close()
    merged.close()
    return str(output_path)


def _stage_video(out, parts_root, project, artifacts, opendesign_llm_config, skill_manager, fps, width, height, progress):
    segments = _split_segments(artifacts)
    n = len(segments)

    if n > 1:
        progress(f"视频较长（{artifacts.get('total_duration', 0)}s），拆成 {n} 段生成（并发 {min(n, LLM_CONCURRENCY)}）...")

    SEG_RETRY = 3  # 单段重试上限：每次 LLM 调用本身就要几分钟，6 次会拖出几十分钟的重试风暴

    def _run_segment_with_retry(seg):
        """逐段独立重试 + 单段级断点续传：已生成且非空的段 video.mp4 直接复用。"""
        seg_dir = _seg_dir(parts_root, seg["index"])
        seg_mp4 = seg_dir / "video.mp4"
        if seg_mp4.exists() and seg_mp4.stat().st_size > 0:
            seg["video"] = str(seg_mp4)
            seg["dir"] = str(seg_dir)
            progress(f"⏭ 第 {seg['index'] + 1} 段已存在，跳过生成")
            return
        last_err = None
        for attempt in range(1, SEG_RETRY + 1):
            try:
                _generate_segment(seg, seg_dir, project, artifacts, skill_manager, fps, width, height, progress)
                return
            except Exception as e:
                last_err = e
                progress(f"✗ 第 {seg['index'] + 1} 段第 {attempt}/{SEG_RETRY} 次失败: {e}")
        seg["_error"] = str(last_err)

    if n == 1:
        _run_segment_with_retry(segments[0])
    else:
        from concurrent.futures import ThreadPoolExecutor
        # pool.map 会等所有任务跑完才返回；每段内部已自行重试，不会提前抛异常导致卡死
        with ThreadPoolExecutor(max_workers=min(n, LLM_CONCURRENCY)) as pool:
            list(pool.map(_run_segment_with_retry, segments))

    failed = [seg for seg in segments if "_error" in seg]
    if failed:
        detail = "；".join(f"第 {s['index'] + 1} 段: {s['_error']}" for s in failed)
        raise RuntimeError(f"画面生成失败 {len(failed)}/{n} 段——{detail}")

    # 每段收尾：该段旁白合并为单音频、该段字幕按相对时间轴导出，均写入段文件夹
    words_by_scene = artifacts.get("words_by_scene", [])
    for seg in segments:
        seg_dir = Path(seg["dir"]) if seg.get("dir") else _seg_dir(parts_root, seg["index"])
        seg["audio"] = _merge_audios(
            seg["vo_paths"],
            seg_dir / "vo.mp3",
        )
        # 该段字幕（相对该段起始，供单段检查/交付）
        seg_subs = _build_seg_subtitles(words_by_scene, seg["scene_indices"], seg.get("start_offset", 0))
        if seg_subs:
            from skills.video_generate.scripts.composer import _write_srt
            _write_srt(seg_subs, str(seg_dir / "subtitles.srt"))
            seg["subtitle_file"] = str(seg_dir / "subtitles.srt")

    artifacts["segments"] = segments
    return artifacts


# ── Stage 5: 合成 ──

def _stage_compose(out, parts_root, project, artifacts, skill_manager, fps, width, height, progress):
    segments = artifacts.get("segments", [])
    subtitles = _build_subtitles(artifacts.get("words_by_scene", []))

    scene_videos = [seg.get("video", "") for seg in segments]
    scene_audios = [seg.get("audio", "") for seg in segments]

    from skills.video_generate.scripts.composer import compose, _write_srt
    progress("正在合成最终视频（拼接各段画面 + 叠加旁白 + 烧录字幕）...")
    compose(
        scene_videos=scene_videos,
        scene_audios=scene_audios,
        subtitles=subtitles,
        output_path=str(out),
        width=width, height=height, fps=fps,
    )

    # 全片 SRT 一并导出（供后期微调/替换使用）
    if subtitles:
        srt_path = out.parent / f"{out.stem}.srt"
        _write_srt(subtitles, str(srt_path))
        artifacts["subtitle_file"] = str(srt_path)

    artifacts["final_video"] = str(out)
    artifacts["parts_root"] = str(parts_root)
    return artifacts


def _build_subtitles(words_by_scene: list) -> list:
    """把字级时间戳聚合成全片字幕 [(text, start, end), ...]（绝对时间轴）。

    按标点分句：句号/问号/叹号/逗号处断句。
    """
    subs = []
    for group in words_by_scene:
        subs.extend(_group_to_subtitles(group, 0.0))
    return subs


def _build_seg_subtitles(words_by_scene: list, scene_indices: list, start_offset: float) -> list:
    """生成某段内的字幕，时间轴相对该段起点（便于单独交付/检查）。"""
    subs = []
    for idx in scene_indices:
        for group in words_by_scene:
            if group.get("scene_index") != idx:
                continue
            subs.extend(_group_to_subtitles(group, -start_offset))
            break
    return subs


def _group_to_subtitles(group: dict, base_shift: float) -> list:
    """把某一分镜的字级时间戳聚合成若干条字幕。

    base_shift: 加在绝对时间上的偏移（全片为 0，段级字幕为 -段起点）。
    """
    subs = []
    offset = group.get("offset", 0.0) + base_shift
    words = group.get("words", [])
    buf = []
    buf_start = None
    for w in words:
        text = w.get("word", "")
        if buf_start is None:
            buf_start = w.get("startTime", 0.0) + offset
        buf.append(text)
        if text and text[-1] in "。！？；，,.;!?":
            subs.append(("".join(buf), round(buf_start, 2), round(w.get("endTime", 0.0) + offset, 2)))
            buf = []
            buf_start = None
    if buf:
        last = words[-1] if words else {}
        subs.append(("".join(buf), round(buf_start if buf_start is not None else 0, 2),
                     round(last.get("endTime", 0.0) + offset, 2)))
    return subs
