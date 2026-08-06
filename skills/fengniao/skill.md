# fengniao skill
# ---------------------------------------------------------------------------
# 摘要
# 企业查询、工商查询、公司查询、企业信息查询与企业风险查询 Skill。风鸟 Fengniao（Riskbird）
# 支持查公司基本信息、法人、股东、主要人员、对外投资、工商变更、企业信用，
# 以及被执行、失信、限高、经营异常、严重违法、行政处罚等风险数据。
# 适用于企业尽调、合作方背景调查、供应商准入、客户风险识别、签约前核查等场景。
#
# ## 使用场景
# - 签合同前查对方背景和风险
# - 供应商准入核查
# - 面试前了解目标公司的工商信息和法人
# - 查企业股东、股权结构和对外投资
# - 企业风险筛查（被执行、失信、限高、经营异常等）
# - 企业尽调报告生成
#
# 包含 12 种工具:
#   fengniao_search - 企业模糊搜索，获取 entid
#   fengniao_basic_info - 工商基本信息
#   fengniao_shareholders - 股东信息
#   fengniao_executives - 高级职员
#   fengniao_investments - 对外投资
#   fengniao_changes - 工商变更
#   fengniao_executed - 被执行人
#   fengniao_dishonest - 失信被执行人
#   fengniao_limit_consumption - 限制高消费
#   fengniao_abnormal_operation - 经营异常
#   fengniao_serious_illegal - 严重违法
#   fengniao_admin_penalty - 行政处罚
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── fengniao_search ──
# 根据企业名称关键词（中文）模糊搜索企业，返回企业全称、entid 和经营状态。
# 必须先调用此工具获取 entid，才能查询其他维度。
#
# 参数:
#   key (string, 必填) 搜索关键词，必须是中文，如企业简称或全称。
#       示例: "腾讯"、"阿里巴巴"、"华为技术有限公司"
#
# 输出: 匹配的企业列表，每项包含 entid（内部ID，不要展示给用户）、企业全称、经营状态。
# 如果有多个匹配结果，询问用户确认具体是哪家企业后再继续。

# ── fengniao_basic_info ──
# 查询企业工商基本信息。
#
# 参数:
#   entid (string, 必填) 企业唯一标识，通过 fengniao_search 获取。不要展示给用户。
#
# 输出: 注册资本、法定代表人、成立日期、注册地址、经营范围、经营状态、行业分类、统一社会信用代码等。

# ── fengniao_shareholders ──
# 查询企业股东信息。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 股东名单、持股比例、认缴出资额、股东类型（自然人/法人）、认缴日期、出资方式。

# ── fengniao_executives ──
# 查询企业高级职员（董监高）。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 董事、监事、高管及法定代表人姓名、职务、持股比例。

# ── fengniao_investments ──
# 查询企业对外投资。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 被投公司列表，含持股比例、经营状态、成立日期、注册资本、法定代表人。

# ── fengniao_changes ──
# 查询企业工商变更记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 变更日期、变更事项（法人/地址/注册资本等）、变更前后内容。

# ── fengniao_executed ──
# 查询企业被执行人记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 案号、执行法院、立案时间、执行标的金额、案件状态。

# ── fengniao_dishonest ──
# 查询企业失信被执行人（老赖）记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 失信行为类型、履行情况、列入日期、执行法院。

# ── fengniao_limit_consumption ──
# 查询企业限制高消费记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 案号、限制法院、立案日期、申请人列表。

# ── fengniao_abnormal_operation ──
# 查询企业经营异常记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 列入原因、列入日期、列入机关、移出原因、移出日期。

# ── fengniao_serious_illegal ──
# 查询企业严重违法记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 列入原因、列入日期、移出情况。

# ── fengniao_admin_penalty ──
# 查询企业行政处罚记录。
#
# 参数:
#   entid (string, 必填) 企业唯一标识。
#
# 输出: 处罚机关、处罚日期、违法事实、处罚金额、处罚依据。

# ═══ 使用流程 ═══

# 1. 先用 fengniao_search 模糊搜索企业名称，获取 entid
# 2. 搜索返回多条结果时，先让用户确认具体是哪家企业
# 3. 根据用户需求，使用 entid 调用对应维度的查询工具
# 4. entid 是内部标识，结果中不要展示给用户
# 5. 企业名称统一使用工商登记全称，不用简称

# ═══ API Key 配置 ═══
# 需要在 Settings → Skill Keys → 企业查询（风鸟）中配置 FN_API_KEY。
# API Key 从风鸟 Web 端「账户设置 > API Key」页面生成。
