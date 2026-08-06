"""
deep_research skill - 多维度并行深度调研

纯编排型 skill（无独立工具），告诉 LLM 如何使用现有工具
(sub_agent + web_search + write + read) 完成系统性能深度调研。
"""
from skills.base import BaseTool, ToolParameter, ToolResult


class DeepResearchTool(BaseTool):
    name = "deep_research"
    description = (
        "多维度并行深度调研工作流。拆解主题为≥6个研究维度，每个维度派一个子Agent并行搜索"
        "（每个≥10次独立web_search），交叉验证后提取洞察，生成结构化调研报告。"
        "适用于行业分析、竞争格局、技术趋势等需要全面了解的场景。"
        "调用此工具获取完整的五步调研流水线指南。"
    )
    parameters = [
        ToolParameter("topic", "string", "调研主题"),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, topic: str, **kwargs) -> ToolResult:
        # 返回工作流指南，让 LLM 自行执行各步骤
        guide = (
            f'调研主题: {topic}\n\n'
            '## 五步流水线\n\n'
            '### Step 1: 维度拆解\n'
            f'将"{topic}"拆解为至少6个研究维度，从技术/市场/政策/竞争/用户/供应链等不同角度切入。'
            '每个维度给出核心搜索词。\n\n'
            '### Step 2: 并行搜索 (sub_agent)\n'
            '对每个维度创建一个子Agent任务，prompt要求:\n'
            '- 使用 web_search 进行至少10次独立搜索\n'
            '- 每条发现标注来源URL和日期\n'
            '- 记录相互矛盾的数据\n'
            '- 结果保存到 research/dim{NN}_{维度名}.md\n\n'
            '调用示例:\n'
            'sub_agent(tasks=[\n'
            '  {{"type": "explore", "description": "维度1: 市场份额", "prompt": "..."}},\n'
            '  {{"type": "explore", "description": "维度2: 技术路线", "prompt": "..."}},\n'
            '  ...\n'
            '])\n\n'
            '### Step 3: 交叉验证\n'
            '读取所有 dim*.md 文件，按四类归档:\n'
            '- 高置信度: ≥2个维度独立确认\n'
            '- 中置信度: 1个权威来源\n'
            '- 低置信度: 来源薄弱\n'
            '- 冲突: 不同维度报告矛盾数据 → 重点标注，不掩盖\n'
            '保存到 research/cross_verification.md\n\n'
            '### Step 4: 洞察提取\n'
            '从跨维度对比中提取≥5个深层洞察。每条需说明: 模式→支撑证据→逻辑链条→影响。'
            '保存到 research/insights.md\n\n'
            '### Step 5: 生成报告\n'
            '汇总所有材料，生成结构化报告 research/report.md:\n'
            '- 摘要(300-500字) → 核心发现 → 深度分析 → 争议与不确定性\n'
            '- 关键洞察 → 局限性与后续方向 → 来源列表\n\n'
            '## 原则\n'
            '- 不搜索不发言: 每条声明必须有来源\n'
            '- 矛盾是信号: 不选边站，两方都记录\n'
            '- 优先权威来源: 政府 > 学术 > 主流财经媒体 > 行业报告 > 企业公告\n'
        )
        return ToolResult.ok(guide, topic=topic)
