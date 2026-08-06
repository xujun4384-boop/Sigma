# sandbox skill
# ---------------------------------------------------------------------------
# 摘要
# 安全代码沙箱。当没有对应专用 skill 时，LLM 可自行编写 Python/Bash 脚本在沙箱中执行。
# 基于 AST 静态安全检查 + 受限内建函数 + 预注入辅助函数。
#
## 使用场景
# - 没有专用 skill 但有标准库可完成的任务
# - 需要批量处理文件、数据转换、格式转换等脚本化操作
# - 临时性的计算、分析任务
# - 后期可用于 skill creator 封装成功的脚本为永久 skill
#
# 包含 1 种子操作:
#   sandbox_run - 在沙箱中执行代码
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── sandbox_run ──
# 在安全沙箱中执行 Python/Bash 代码。
#
# 参数:
#   code (string, 必填) 要执行的代码。
#   language (string, 可选, 默认 "python") 语言: python / bash。
#
# Python 沙箱特性:
#   - 允许 import 语句，通过受限 __import__ 控制可导入的模块
#   - 白名单包含全部标准库 + 常用第三方库（openpyxl/pptx/PyPDF2/pandas/numpy 等）
#   - AST 检查仅拦截: eval()/exec()/compile()/open()/input()/breakpoint()
#   - 预注入辅助函数: read(path) / write(path, content) / ls(path)
#   - cwd 变量指向项目根目录
#   - 输出自动截断 (80KB)
#   - 【有状态】同一会话内多次调用共享变量/import/已定义的函数和对象，
#     可以像 REPL 一样分步执行（例如第一次调用 `doc = Document()`，
#     第二次调用直接用 `doc.add_paragraph(...)`，无需重新定义）
#   - 会话按调用线程区分：主对话与每个并行子 Agent 各自独立，互不干扰
#   - 传 reset=true 可清空当前会话已保留的状态，从干净环境重新开始
#   - 会话状态在 30 分钟无调用后自动过期清理
#
# Bash 沙箱特性:
#   - subprocess 执行, 工作目录为项目根目录
#   - 60 秒超时
#   - 捕获 stdout/stderr
#
# 输出: stdout 输出内容。
# ---------------------------------------------------------------------------

# 安全限制
# 1. 允许 import — 但只能导入白名单模块（标准库 + 常用第三方）
# 2. 禁止 eval/exec/compile/open/input/breakpoint
# 3. 文件写入通过 write() 辅助函数（自动创建目录）
