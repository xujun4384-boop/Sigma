"""
image_provider - 场景图片智能提供模块

策略层级（从快到慢、从省到费）:
  1. 图片池匹配 —— 扫描 images/ 下已有图片，按关键词匹配复用
  2. AI 生成 —— 调用 generate_image 工具

图片命名: {index:02d}_{描述关键词}.jpg，便于人工和 LLM 识别图片内容。

决策逻辑:
  - auto: 自动使用 AI 生成
  - generate: AI 生成
"""
import os
import re
import shutil
from pathlib import Path


# ─── 通用中文实体模式检测 ───

_ENTITY_PATTERNS = [
    r'(?:[\u4e00-\u9fff]{1,4})(?:公司|集团|企业|银行|基金|证券|保险|医院|学校|大学|政府|部门|委员会|协会|组织)',
    r'(?:[\u4e00-\u9fff]{1,3})(?:省|市|县|区|镇|乡|村|国|洲)',
    r'(?:[\u4e00-\u9fff]{1,4})(?:先生|女士|教授|博士|总理|主席|总统|部长|局长|市长|院长)',
    r'(?:\d{2,4}年\d{1,2}月\d{1,2}日?)',
    r'(?:\d+(?:\.\d+)?(?:亿|万|千|百)?(?:元|美元|欧元|日元|英镑|人民币))',
    r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)*',
]

DEFAULT_IMAGE_STYLE = "现代科技新闻插画风格，高清，适合竖屏视频背景"

# 关键词匹配阈值：中文字符交集比例
_MIN_MATCH_RATIO = 0.3


# ─── 文件名提取 ───

def _extract_keyword(text: str, max_len: int = 10) -> str:
    """
    从场景文本中提取简短的描述关键词，用作文件名。
    优先提取中文实体（公司名、人名、地名等），退化为前 max_len 个中文字符。
    """
    if not text:
        return "image"

    # 优先匹配实体模式中的具体指代
    for pattern in _ENTITY_PATTERNS:
        m = re.search(pattern, text)
        if m:
            kw = m.group()
            if len(kw) >= 2:
                return _sanitize_filename(kw[:max_len])

    # 取前 max_len 个有效字符（中文/字母/数字）
    clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text)
    if clean:
        return _sanitize_filename(clean[:max_len])
    return "image"


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符，保留中英文数字和下划线。"""
    return "".join(c if c.isalnum() or '\u4e00' <= c <= '\u9fff' or c in "_-" else "_" for c in name).strip("_") or "image"


# ─── 图片池 ───

def _scan_image_pool(save_dir: str) -> list[dict]:
    """
    扫描图片池目录，返回已存图片的元信息列表。

    返回: [{"keyword": str, "path": str, "stem": str}, ...]
      - keyword: 从文件名提取的描述关键词（去掉序号前缀）
      - path: 文件绝对路径
      - stem: 文件名（不含扩展名）
    """
    pool_dir = Path(save_dir)
    if not pool_dir.exists():
        return []

    entries = []
    for f in sorted(pool_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
            continue
        name = f.stem
        # 去掉序号前缀（如 "00_", "01_", "0_", "1_"）
        keyword = re.sub(r'^\d{1,3}[_\-]', '', name)
        entries.append({
            "keyword": keyword,
            "path": str(f.resolve()),
            "stem": name,
        })
    return entries


def _match_scene_to_pool(
    scene_text: str,
    scene_index: int,
    pool: list[dict],
    used_paths: set,
) -> str | None:
    """
    从图片池中为场景匹配最合适的已有图片。

    匹配策略:
      1. 优先按场景序号精确匹配（文件名以 {index:02d}_ 开头）
      2. 按关键词字符交集匹配（中文字符 2-gram 重叠率）
      3. 阈值以下视为不匹配，返回 None

    参数:
        scene_text: 场景文案
        scene_index: 场景序号
        pool: 图片池列表
        used_paths: 已被选走的图片路径集合

    返回:
        匹配到的图片路径，或 None
    """
    if not pool:
        return None

    scene_keyword = _extract_keyword(scene_text)
    prefix = f"{scene_index:02d}_"

    best_path = None
    best_score = 0.0

    for entry in pool:
        if entry["path"] in used_paths:
            continue

        score = 0.0

        # 策略1: 序号精确匹配
        if entry["stem"].startswith(prefix):
            score = 1.0
        else:
            # 策略2: 关键词字符交集
            pool_keyword = entry["keyword"]
            # 提取 2-gram 字符集
            scene_chars = set(scene_keyword)
            pool_chars = set(pool_keyword)
            if scene_chars and pool_chars:
                intersection = scene_chars & pool_chars
                union = scene_chars | pool_chars
                score = len(intersection) / len(union) if union else 0.0

        if score > best_score:
            best_score = score
            best_path = entry["path"]

    if best_score >= _MIN_MATCH_RATIO and best_path:
        return best_path
    return None


# ─── 主入口 ───

def provide_images_for_scenes(
    scenes: list[dict],
    image_source: str,
    image_style: str,
    work_dir: str,
    project: str,
    skill_manager,
) -> list[str]:
    """
    为每个场景智能准备配图。

    优先级: 图片池匹配 → AI 生成

    参数:
        scenes: [{"text": str, "duration": float}, ...]
        image_source: 图片来源策略（保留参数以兼容旧调用，当前统一使用 AI 生成）
        image_style: AI 生成图片的风格前缀
        work_dir: 工作目录基路径
        project: 项目名（用作子目录）
        skill_manager: SkillManager 实例

    返回:
        图片路径列表，长度与 scenes 一致
    """
    style = image_style or DEFAULT_IMAGE_STYLE
    safe_project = "".join(c if c.isalnum() or c in "._-" else "_" for c in project)[:50] or "video"
    save_dir = str(Path(work_dir) / "video_work" / safe_project / "images")
    Path(save_dir).mkdir(parents=True, exist_ok=True)

    # ── 扫描图片池 ──
    pool = _scan_image_pool(save_dir)
    used_paths: set = set()

    image_paths: list[str] = []

    for i, scene in enumerate(scenes):
        text = scene.get("text", "").strip()
        keyword = _extract_keyword(text)

        # ── 第1步: 尝试从池中匹配 ──
        matched = _match_scene_to_pool(text, i, pool, used_paths)
        if matched:
            used_paths.add(matched)
            image_paths.append(matched)
            continue

        # ── 第2步: AI 生成 ──
        target_name = f"{i:02d}_{keyword}"
        final_path = None

        # AI 生成
        if not final_path:
            gen_prompt = f"{style}，16:9横版构图，画面内容：{text[:120]}"
            try:
                result = skill_manager.dispatch(
                    "generate_image",
                    prompt=gen_prompt,
                    save_dir=save_dir,
                )
                if result.success:
                    raw_path = result.details.get("filepath", "")
                    final_path = _rename_to_descriptive(raw_path, save_dir, target_name)
            except Exception:
                pass

        if final_path:
            image_paths.append(final_path)
            # 同步更新池，避免后续场景重复匹配到同一张未命名的图
            pool.append({
                "keyword": keyword,
                "path": final_path,
                "stem": Path(final_path).stem,
            })
        else:
            image_paths.append("")

    return image_paths


def _rename_to_descriptive(raw_path: str, save_dir: str, target_name: str) -> str:
    """
    将工具生成的图片重命名为描述性名称。

    参数:
        raw_path: 工具返回的原始路径
        save_dir: 目标保存目录
        target_name: 目标文件名（不含扩展名），如 "00_股市下跌"

    返回:
        重命名后的路径
    """
    if not raw_path or not os.path.exists(raw_path):
        return raw_path

    raw = Path(raw_path)
    ext = raw.suffix.lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        ext = '.jpg'

    new_path = Path(save_dir) / f"{target_name}{ext}"

    # 如果目标已存在（如从池中匹配到了同名文件），不覆盖
    if new_path.exists():
        return raw_path

    try:
        shutil.move(str(raw), str(new_path))
        return str(new_path.resolve())
    except (OSError, shutil.Error):
        return raw_path
