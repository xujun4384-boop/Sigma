# project_memory skill
# ---------------------------------------------------------------------------
# 摘要
# 项目记忆 + Network Bridge 记忆管理。
#
## 存储结构

# 项目记忆（source="project"）存储在 {working_dir}/.sigma2.0/memory/：
#   - project_overview.md: 全局目录扫描结果，记录所有文件的用途推测
#   - task_history.md: 按日期分组的任务完成记录
#
# Network Bridge 记忆（source="sigma"）存储在 Sigma 本体的 .sigma/memory/：
#   - network_bridge_overview.md: 浏览器自动化常访问站点 + 跨站点经验
#   - network_bridge_history.md: 浏览器任务历史记录
#
## ⚠️ 重要提示
# - 每次新对话开始时，必须先调用 memory_read 了解上下文
# - 项目编码任务: memory_read(source="project") 读项目记忆
# - 浏览器自动化任务: memory_read(source="sigma") 读 Network Bridge 记忆
# - 有实质性进展后用 memory_record 追加简短记录（分别指定对应的 source）
#
## 使用场景
# - 对话开始时，调用 memory_read 加载相关记忆
# - 当你需要了解项目结构或浏览器自动化历史时
# - 有实质性任务完成后，追加记录
# - 确认新信息后，更新概览中的标注
#
# 包含 4 种工具:
#   project_scan - 全局目录扫描（通常由系统自动触发）
#   memory_read  - 读取记忆（对话开始时必调，参数 source 选 project/sigma）
#   memory_record - 追加任务记录（参数 source 选 project/sigma）
#   memory_update - 更新概览条目（参数 source 选 project/sigma）
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── project_scan ──
# 扫描项目目录结构，列出所有文件和子目录。
# 仅基于文件名和路径，不读取文件内容。
# 所有文件初始标注为 [待判断]。
# 通常由系统在首次使用时自动触发，无需手动调用。
#
# 参数:
#   working_dir (string, 必填) 项目工作目录的绝对路径
#
# 输出:
#   content: 扫描概要 + 文件总数
#   extras: file_count, overview_path

# ── memory_read ──
# 读取记忆的概览和历史记录。
# ⚠️ 对话开始时必调！
# 参数 source 决定读取哪个记忆:
#   - source="project" (默认): 读取项目记忆（project_overview.md + task_history.md）
#   - source="sigma": 读取 Network Bridge 记忆（network_bridge_overview.md + network_bridge_history.md）
#     source="sigma" 时 working_dir 参数被忽略，可传入任意字符串如 "."。
#
# 参数:
#   working_dir (string, 必填) 项目工作目录的绝对路径。source="sigma" 时传 "." 即可。
#   source (string, 可选, 默认 "project") 记忆来源
#
# 输出:
#   content: 两份记忆文件的合并内容

# ── memory_record ──
# 追加一条任务记录。只在有实质性任务进展时调用，闲聊、问候等无需记录。
# 记录会自动按日期分组。
#
# 参数:
#   working_dir (string, 必填) 项目工作目录的绝对路径。source="sigma" 时传 "." 即可。
#   summary (string, 必填) 任务简述，一句话
#   files (string, 可选) 涉及的关键文件/站点，逗号分隔
#   source (string, 可选, 默认 "project") 记忆来源
#
# 输出:
#   content: 写入确认

# ── memory_update ──
# 更新概览中某个条目的标注。
# 当你确认了新信息后调用。
#
# 参数:
#   working_dir (string, 必填) 项目工作目录的绝对路径。source="sigma" 时传 "." 即可。
#   entry (string, 必填) 概览中的条目名称
#   purpose (string, 必填) 用途描述
#   source (string, 可选, 默认 "project") 记忆来源
#
# 输出:
#   content: 更新确认
# ---------------------------------------------------------------------------
