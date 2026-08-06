"""
writing_polish skill - 去AI味润色

纯编排型 skill，返回去 AI 味润色规则指南，LLM 直接在对话中应用。
"""
from skills.base import BaseTool, ToolParameter, ToolResult


class WritingPolishTool(BaseTool):
    name = "writing_polish"
    description = (
        "去 AI 味润色指南。让文字听起来像真人写的而非 AI 生成："
        "去除机器腔、注入人味、让文字有脉搏。适合改写回复、报告、文章等。"
    )
    parameters = [
        ToolParameter("text", "string", "待润色的文本（可选，也可不填直接获取规则指南）", required=False),
    ]

    def __init__(self, cwd: str = "."):
        super().__init__(cwd)

    def execute(self, text: str = "", **kwargs) -> ToolResult:
        guide = (
            "## 去 AI 味润色规则\n\n"
            "### 致命级：绝对不能出现\n"
            "- 知识截止用语：'根据我的知识截止日期'、'截至我所知'\n"
            "- 聊天机器人腔：'希望这对你有帮助！'、'如果你还有其他问题…'\n"
            "- Markdown 泄漏到纯文本中：非必要的加粗和标题\n\n"
            "### 高信号：AI词库替换\n"
            "- 助力→帮助/推动、彰显→体现/表明、赋能→加强/支持、闭环→完整流程\n"
            "- 删除：数字化转型、值得注意的是、综上所述、不难发现\n"
            "- 破折号'——'同篇不超过 1 个\n\n"
            "### 中信号：AI惯用套路\n"
            "- 假引用：'专家认为'、'行业报告显示'→ 要么具名引用，要么删除\n"
            "- 流水连接词：'此外…而且…另外…总之…'→ 砍掉一半\n"
            "- 废话开篇：'在当今快节奏的社会中…'→ 直接说正事\n\n"
            "### 改写原则\n"
            "1. 有态度：喜欢就夸，不喜欢就质疑，模棱两可是AI标志\n"
            "2. 允许粗糙：偶尔跑题、半句话、口语化都是人味\n"
            "3. 具体而非概括：不说'这很令人担忧'，说'这个数据意味着三个月后就会出问题'\n"
            "4. 节奏变化：短句。然后用一个带细节和情绪的长句。再短回来\n"
            "5. 承认复杂性：不确定就说不确定，有矛盾就指出矛盾\n"
            "6. 允许'我'：能用'我觉得'就用，比'综合考虑'更像人\n"
        )
        if text:
            guide = f"对以下文本应用去 AI 味润色规则：\n\n---\n{text}\n---\n\n{guide}"
        return ToolResult.ok(guide)
