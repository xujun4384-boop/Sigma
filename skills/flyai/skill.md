# flyai skill
# ---------------------------------------------------------------------------
# 摘要
# 飞猪 AI 开放平台（FlyAI / Fliggy MCP）旅行搜索 Skill。通过调用本地 flyai-cli（Node.js）
# 接入飞猪全品类旅行生态，提供酒店、机票、火车票、景点门票、度假套餐、POI 以及万豪酒店/套餐的
# 结构化搜索能力。结果包含可预订链接，可直接用于行程规划、差旅比价、出行推荐等场景。
#
# ## 使用场景
# - 机票/火车票查询与比价
# - 酒店搜索（按城市、入住日期、星级、POI、价格筛选）
# - 景点门票、周边一日游、当地体验搜索
# - 自然语言旅行需求（关键词/AI 语义搜索）
# - 万豪集团酒店及套餐商品搜索
# - 行程规划与差旅推荐
#
# 包含 8 种工具:
#   flyai_keyword_search - 关键词搜索，覆盖全品类旅行
#   flyai_ai_search - AI 语义搜索，理解复杂旅行意图
#   flyai_search_flight - 结构化机票搜索
#   flyai_search_train - 结构化火车票搜索
#   flyai_search_hotel - 酒店搜索
#   flyai_search_poi - 景点/POI 搜索
#   flyai_search_marriott_hotel - 万豪酒店搜索
#   flyai_search_marriott_package - 万豪套餐搜索
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── flyai_keyword_search ──
# 自然语言关键词搜索，覆盖酒店、机票、景点、度假等全品类旅行商品。
#
# 参数:
#   query (string, 必填) 搜索关键词，例如："杭州3日游"、"上海到东京机票"、"三亚五星级酒店"
#
# 输出: 匹配商品列表，通常包含标题、图片、价格、链接、标签等。

# ── flyai_ai_search ──
# AI 语义搜索，理解复杂旅行意图，例如预算、时间、偏好等多条件自然语言查询。
#
# 参数:
#   query (string, 必填) 自然语言查询，例如：
#       "五一去杭州3天，人均2000，住西湖附近"
#
# 输出: 结构化旅行推荐结果，通常包含商品标题、图片、价格、可预订链接。

# ── flyai_search_flight ──
# 结构化机票搜索，支持单程/往返、直飞/中转、舱位、价格、排序筛选。
#
# 参数:
#   origin (string, 必填) 出发地城市名，例如：上海、北京
#   destination (string, 必填) 目的地城市名，例如：东京、三亚
#   dep_date (string, 必填) 出发日期，格式 YYYY-MM-DD
#   back_date (string, 可选) 回程日期，格式 YYYY-MM-DD
#   journey_type (string, 可选) 1=直达，2=中转
#   seat_class_name (string, 可选) 舱位等级：economy, business, first，可多选逗号分隔
#   max_price (integer, 可选) 最高价格（人民币）
#   sort_type (string, 可选) 排序：1=价格从高到低 2=智能推荐 3=价格从低到高
#           4=耗时最短 5=耗时最长 6=出发早 7=出发晚 8=直飞优先
#
# 输出: 航班列表，通常包含航班号、起降时间、价格、航司、时长、链接等。

# ── flyai_search_train ──
# 结构化火车票搜索，支持日期、车次类型、座位等级、排序。
#
# 参数:
#   origin (string, 必填) 出发地城市名或车站名，例如：北京、上海虹桥
#   destination (string, 必填) 目的地城市名或车站名，例如：上海、杭州东
#   dep_date (string, 必填) 出发日期，格式 YYYY-MM-DD
#   journey_type (string, 可选) 1=直达，2=中转
#   seat_class_name (string, 可选) 座位等级，例如：second class, first class, business class
#   sort_type (string, 可选) 排序：1=价格从高到低 2=智能推荐 3=价格从低到高
#           4=耗时最短 5=耗时最长 6=出发早 7=出发晚 8=直达优先
#
# 输出: 车次列表，通常包含车次号、出发/到达时间、历时、座位价格、链接等。

# ── flyai_search_hotel ──
# 酒店搜索，支持目的地、入住/离店日期、POI、星级、价格、排序。
#
# 参数:
#   dest_name (string, 必填) 目的地城市名，例如：杭州、三亚
#   check_in_date (string, 必填) 入住日期，格式 YYYY-MM-DD
#   check_out_date (string, 必填) 离店日期，格式 YYYY-MM-DD
#   poi_name (string, 可选) POI 名称，例如：西湖、外滩
#   hotel_stars (string, 可选) 酒店星级，可多选逗号分隔，例如：4,5
#   max_price (integer, 可选) 最高价格（人民币）
#   sort (string, 可选) 排序，例如：rate_desc（评分从高到低）、price_asc（价格从低到高）
#
# 输出: 酒店列表，通常包含酒店名称、星级、价格、地址、链接等。

# ── flyai_search_poi ──
# 景点/POI 搜索，支持城市、分类、等级、关键词。
#
# 参数:
#   city_name (string, 必填) 城市名，例如：西安、北京
#   category (string, 可选) 分类，例如：历史古迹、地标建筑、山湖田园
#   poi_level (string, 可选) 景点等级，例如：5（5A景区）
#   keyword (string, 可选) 关键词，例如：西湖
#
# 输出: 景点/POI 列表，通常包含名称、等级、地址、链接等。

# ── flyai_search_marriott_hotel ──
# 万豪集团酒店搜索。
#
# 参数:
#   dest_name (string, 必填) 目的地城市名，例如：上海、北京
#   check_in_date (string, 必填) 入住日期，格式 YYYY-MM-DD
#   check_out_date (string, 必填) 离店日期，格式 YYYY-MM-DD
#   hotel_brands (string, 可选) 品牌，可多选逗号分隔，例如：JW Marriott,Sheraton
#
# 输出: 万豪酒店列表，通常包含品牌、酒店名称、价格、链接等。

# ── flyai_search_marriott_package ──
# 万豪集团酒店套餐商品搜索。
#
# 参数:
#   keyword (string, 必填) 搜索关键词，例如：上海、JW Marriott
#   sort_type (string, 可选) 排序，例如：price_asc（价格从低到高）
#
# 输出: 万豪套餐商品列表，通常包含标题、价格、链接等。

# ═══ 使用流程 ═══

# 1. 根据用户需求选择最合适的工具
#    - 模糊/自然语言需求：优先使用 flyai_keyword_search 或 flyai_ai_search
#    - 明确机票/火车票需求：使用 flyai_search_flight / flyai_search_train
#    - 酒店需求：使用 flyai_search_hotel
#    - 景点需求：使用 flyai_search_poi
#    - 万豪特定需求：使用 search_marriott_hotel / search_marriott_package
# 2. 输出中如有 jumpUrl 或链接，可直接展示给用户作为预订入口
# 3. 搜索日期请使用未来日期，格式统一为 YYYY-MM-DD

# ═══ 前置依赖 ═══
# 1. 安装 flyai-cli: npm i -g @fly-ai/flyai-cli
# 2. 在 Settings → Skill Keys → 旅行搜索（飞猪/FlyAI）中配置 sk- 开头的 API Key。
#    API Key 从 https://flyai.open.fliggy.com/console 获取。
