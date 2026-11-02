# -*- coding: utf-8 -*-
"""文字类 MV 的字效风格库（只给 lyric_mv 的 typographic 模式用）。

和插画风格库（skills/style_lib.py）分开：
  - 插画风格规定“画面怎么画”（线条/质感/人物）；
  - 字效风格规定“文字怎么排、怎么动”（字体/字重/字距/版式/节奏）。

这里只放结构性规则，不放任何题材内容；具体写什么字由歌词和 LLM 决定。
字体优先使用系统本地字体，离线渲染不依赖联网字体。
"""

TYPES = {
    "brutalist": {
        "label": "粗野主义",
        "use_for": ["口号", "态度表达", "说唱", "强节奏", "社会议题"],
        "avoid_for": ["温柔抒情", "古风", "童趣"],
        "font": '"Arial Black", "Microsoft YaHei", "PingFang SC", sans-serif',
        "weight": 900,
        "tracking": -0.02,
        "leading": 0.92,
        "align": "left",
        "palette": "黑底白字 + 1 个高饱和强调色（正红/亮黄）；最多 3 色",
        "background": "纯色或大色块；可加粗网格、分割线、编号",
        "layout": "超大字号占满画面，允许出框与裁切；一行只放 2~6 个字；主字与辅助字用同一套字重，靠大小拉开层级",
        "motion": "硬切、弹入、遮罩擦除；按拍做 8%~15% 缩放冲击；位移取整、不要柔和缓动",
        "texture": "无渐变；可有扫描线/网点，但不得影响文字可读",
        "forbidden": ["整帧亮度闪烁", "多种花哨字体混用", "小字堆信息", "文字被背景吞掉"],
        "emphasis": {
            "scale": 1.36, "fill": "accent", "block": "", "weight": 900,
            "glow": 0.0, "underline": False,
            "text": "重点片段字号 ×1.36、换成强调色、字重加到最大；其余字保持基准字号与颜色",
        },
    },
    "editorial": {
        "label": "杂志排版",
        "use_for": ["叙事民谣", "都市情绪", "独白", "文艺", "慢歌"],
        "avoid_for": ["硬核说唱", "强节奏舞曲", "儿童"],
        "font": '"Georgia", "SimSun", "Songti SC", serif',
        "weight": 600,
        "tracking": 0.02,
        "leading": 1.18,
        "align": "left",
        "palette": "纸白/米色底 + 墨黑正文 + 1 个低饱和强调色（赭石/墨绿）",
        "background": "大留白 + 细分割线 + 小号页码/栏目名",
        "layout": "网格排版：标题大、正文小；允许竖排/横排混用；每屏留 30% 以上空白；一行 6~12 字",
        "motion": "文字逐行滑入、遮罩揭示、字距缓慢收紧；动作幅度小，靠版式推进",
        "texture": "纸纹颗粒；不要发光",
        "forbidden": ["满屏大字", "霓虹色", "文字压住分割线", "长段落不换行"],
        "emphasis": {
            "scale": 1.24, "fill": "accent", "block": "", "weight": 600,
            "glow": 0.0, "underline": True,
            "text": "重点片段字号 ×1.24、换成强调色并加细下划线；正文保持墨黑与基准字号",
        },
    },
    "neon": {
        "label": "霓虹字",
        "use_for": ["电子", "夜场", "赛博", "强节奏", "恋爱"],
        "avoid_for": ["古风", "纪实", "安静叙事"],
        "font": '"Impact", "Microsoft YaHei", "PingFang SC", sans-serif',
        "weight": 900,
        "tracking": 0.0,
        "leading": 1.0,
        "align": "center",
        "palette": "深蓝/黑底 + 青色/洋红霓虹 + 少量白",
        "background": "暗底 + 极淡网格/光晕；不要大面积渐变",
        "layout": "居中堆叠 1~3 行；主字大、辅字小；字距紧；可做空心字/描边字",
        "motion": "按拍做 4%~10% 呼吸缩放、色相在青/洋红间切换；逐字点亮；不要整屏闪烁",
        "texture": "轻微辉光（shadowBlur ≤ 字号的 0.25）；不要脏噪点",
        "forbidden": ["整帧亮度脉动", "白字压亮底", "超过 3 种霓虹色", "文字糊成一团"],
        "emphasis": {
            "scale": 1.30, "fill": "accent", "block": "", "weight": 900,
            "glow": 0.22, "underline": False,
            "text": "重点片段字号 ×1.30、用霓虹强调色并加辉光（模糊 ≤ 字号的 0.22）；其余字保持白/浅色",
        },
    },
    "handwritten": {
        "label": "手写手账",
        "use_for": ["童趣", "日记", "校园", "温柔叙事", "民谣"],
        "avoid_for": ["硬核说唱", "赛博", "严肃议题"],
        "font": '"KaiTi", "STKaiti", "Kaiti SC", cursive',
        "weight": 400,
        "tracking": 0.01,
        "leading": 1.12,
        "align": "left",
        "palette": "纸白/浅杏底 + 墨蓝/墨黑字 + 1 个手账色（砖红/草绿）",
        "background": "纸纹 + 胶带/便签/箭头等简单标记，不能抢字",
        "layout": "像手账：主句斜着写、辅句小字标注；允许下划线、圈重点；一行 4~10 字",
        "motion": "笔迹逐字出现（用遮罩/擦除模拟书写）、纸张轻漂、贴纸弹入",
        "texture": "纸纹、铅笔排线；不要发光",
        "forbidden": ["整帧闪烁", "机械等宽排版", "过多贴纸遮挡文字"],
        "emphasis": {
            "scale": 1.28, "fill": "accent", "block": "", "weight": 400,
            "glow": 0.0, "underline": True,
            "text": "重点片段字号 ×1.28、换成手账强调色并画一道手写下划线；其余字保持墨色",
        },
    },
    "pixel": {
        "label": "像素字",
        "use_for": ["游戏", "怀旧", "8-bit", "强节奏", "轻快"],
        "avoid_for": ["细腻抒情", "古风", "写实"],
        "font": '"Consolas", "Courier New", monospace',
        "weight": 700,
        "tracking": 0.04,
        "leading": 1.0,
        "align": "center",
        "palette": "深蓝/紫底 + 亮青/洋红/黄，最多 16 色",
        "background": "纯色 + 像素网格/HUD 边框；不要渐变",
        "layout": "像游戏 UI：主字居中、辅字做 HUD；所有位置对齐 4px 网格；一行 4~10 字",
        "motion": "按 8~12fps 步进；位移取整像素；逐字弹出/打字机；不要平滑缓动",
        "texture": "抖动（dither）/扫描线，但不能影响字",
        "forbidden": ["平滑渐变", "抗锯齿柔边", "超过 16 色", "整帧闪烁"],
        "emphasis": {
            "scale": 1.20, "fill": "accent", "block": "", "weight": 700,
            "glow": 0.0, "underline": False,
            "text": "重点片段字号 ×1.20、换成像素亮色，并沿 4px 网格对齐；其余字保持同色系暗一档",
        },
    },
    "kinetic": {
        "label": "动态字",
        "use_for": ["青春摇滚", "流行", "强卡点", "恋爱", "现场感"],
        "avoid_for": ["安静独白", "古风", "慢歌"],
        "font": '"Arial Black", "Microsoft YaHei", "PingFang SC", sans-serif',
        "weight": 900,
        "tracking": -0.01,
        "leading": 0.96,
        "align": "center",
        "palette": "高对比双色（深底亮字或亮底深字）+ 1 个强调色",
        "background": "纯色/几何色块/速度线，随拍变化但不抢字",
        "layout": "词组级排版：一句拆成 2~4 个词组，按拍换行/换位；允许斜排、错位、出框",
        "motion": "词组按拍弹入、位移、旋转 ±6°、缩放 90%~115%；转场由文字动作带出",
        "texture": "无纹理或极轻速度线",
        "forbidden": ["整帧亮度闪烁", "所有字同时动", "文字重叠不可读", "慢速缓动"],
        "emphasis": {
            "scale": 1.38, "fill": "bg", "block": "accent", "weight": 900,
            "glow": 0.0, "underline": False,
            "text": "重点片段字号 ×1.38，压在强调色色块上、字用背景色反白；其余字保持浅色无块",
        },
    },
}


# 样片预览用的结构化参数（只影响 10 秒字效样片，不影响全片排版方案）。
# 全片仍由 LLM 按上面的规则生成；这里只保证 2~4 个候选在画面上有真实差异。
_PREVIEWS = {
    "brutalist": {
        "bg": "#111318", "fg": "#F4EFE4", "accent": "#E9A63B", "dark": True,
        "align": "left", "rows": 1, "chorus_rows": 2, "block": "",
        "accent_every": 4, "rise": 26, "leading": 1.08,
    },
    "editorial": {
        "bg": "#EFE7D8", "fg": "#171512", "accent": "#C8452D", "dark": False,
        "align": "left", "rows": 2, "chorus_rows": 2, "block": "",
        "accent_every": 0, "rise": 18, "leading": 1.18,
    },
    "neon": {
        "bg": "#07121F", "fg": "#EAF7FF", "accent": "#00E5FF", "dark": True,
        "align": "center", "rows": 2, "chorus_rows": 2, "block": "",
        "accent_every": 3, "rise": 16, "leading": 1.06,
    },
    "handwritten": {
        "bg": "#F7F1E3", "fg": "#2B2B2B", "accent": "#C8452D", "dark": False,
        "align": "left", "rows": 2, "chorus_rows": 2, "block": "",
        "accent_every": 0, "rise": 22, "leading": 1.16,
    },
    "pixel": {
        "bg": "#160F2E", "fg": "#F4EFE4", "accent": "#00E5A8", "dark": True,
        "align": "center", "rows": 2, "chorus_rows": 2, "block": "",
        "accent_every": 2, "rise": 12, "leading": 1.05,
    },
    "kinetic": {
        "bg": "#141210", "fg": "#F4EFE4", "accent": "#FF4D3D", "dark": True,
        "align": "center", "rows": 2, "chorus_rows": 2, "block": "#F2C14E",
        "accent_every": 0, "rise": 20, "leading": 1.05,
    },
}

for _tid, _p in _PREVIEWS.items():
    TYPES[_tid]["preview"] = _p


def ids():
    return list(TYPES)


def get(type_id):
    return TYPES.get(str(type_id or "").strip())


def label(type_id):
    t = get(type_id)
    return t["label"] if t else str(type_id or "")


def menu():
    """给 LLM 的候选菜单：只列 id / 名称 / 适合 / 不适合。"""
    lines = []
    for tid, t in TYPES.items():
        lines.append(
            f"- {tid}（{t['label']}）：适合 {'、'.join(t['use_for'])}；"
            f"不适合 {'、'.join(t['avoid_for'])}"
        )
    return "\n".join(lines)


def prompt(type_id):
    """把一种字效风格展开成可直接照做的排版规格。"""
    t = get(type_id)
    if not t:
        return ""
    return f"""### 字效风格：{t['label']}（{type_id}）
字体：{t['font']}（系统本地字体，不联网）
字重：{t['weight']}｜字距：{t['tracking']}em｜行距：{t['leading']}
配色：{t['palette']}
背景：{t['background']}
排版：{t['layout']}
运动：{t['motion']}
质感：{t['texture']}
重点处理：{t['emphasis']['text']}
禁止：{"；".join(t['forbidden'])}"""
