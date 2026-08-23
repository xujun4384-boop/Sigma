# baidu_map skill
# ---------------------------------------------------------------------------
# 摘要
# 百度地图 Agent Plan 技能，提供语义化 AI 地点检索、路线规划、地理编码、
# 逆地理编码、天气查询、地图展示能力。统一使用 BAIDU_MAP_AUTH_TOKEN 鉴权。
#
# 使用场景
# - 语义化地点搜索（"找北京可带宠物的咖啡馆"、"评分最高的火锅店"）
# - 路线规划（驾车/步行/骑行/公交，支持沿途搜索 POI）
# - 地址与坐标互转（地理编码/逆地理编码）
# - 天气查询（按城市或坐标）
# - 地图可视化展示（根据 resource_key 生成并打开地图链接）
#
# 包含 6 种工具:
#   baidu_map_place - 语义化 AI 地点检索
#   baidu_map_direction - 语义化 AI 路线规划
#   baidu_map_geocoding - 地理编码（地址 → 坐标）
#   baidu_map_reverse_geocoding - 逆地理编码（坐标 → 地址）
#   baidu_map_weather - 天气查询
#   baidu_map_render - 地图展示
# ---------------------------------------------------------------------------

# ═══ 参数详情 ═══

# ── baidu_map_place ──
# 语义化 AI 地点检索，根据自然语言需求搜索 POI。
#
# 参数:
#   user_raw_request (string, 必填) 用户原始需求，原样完整传入，不可压缩为关键词；
#         保留约束词（如"评分最高""最近""3公里内"）。
#         示例: "帮我找北京可带宠物的咖啡馆"
#   region (string, 必填) 城市或区域限制，例如：北京市、延庆区
#   center (string, 可选) 检索中心点和排序参考点，格式 lat,lng（gcj02）；
#         仅来自用户明确提供或可信来源，禁止推测/编造。
#   sort (string, 可选) 排序方式：distance（距离）或 relevance（相关度，默认）。
#         sort=distance 时 center 必传。
#
# 输出: POI 列表，包含名称、地址、距离、uid；以及 resource_key（可用于地图展示）。

# ── baidu_map_direction ──
# 语义化 AI 路线规划，支持驾车、步行、骑行、公交，可处理沿途搜索。
#
# 参数:
#   user_raw_request (string, 必填) 用户原始需求，包含起点、终点、途经点；
#         保留路线约束词，需推理改写交通方式。
#         示例: "从百度大厦驾车到颐和园，路上顺便买一杯咖啡"
#   location (string, 必填) 用户当前位置坐标，格式 lat,lng（gcj02），
#         至少保留小数点后 6 位。
#   refer_pois (string, 可选) 地点精确映射，用于消歧。
#         格式: 地点名称:uid,纬度,经度;地点名称:uid,纬度,经度
#
# 输出: 路线方案（距离、耗时、步骤）或地点澄清列表。
#       澄清列表需用户选择后，改写 user_raw_request 并传入 refer_pois 重新调用。

# ── baidu_map_geocoding ──
# 地理编码：将完整地址解析为 gcj02 坐标。
#
# 参数:
#   address (string, 必填) 要解析的完整地址，越完整解析越稳定。
#   region (string, 可选) 城市/区域提示，减少歧义。
#
# 输出: 地址对应的 gcj02 坐标（lat,lng）。

# ── baidu_map_reverse_geocoding ──
# 逆地理编码：将 gcj02 坐标转换为语义化地址。
#
# 参数:
#   location (string, 必填) lat,lng 格式坐标（gcj02），至少保留小数点后 6 位。
#
# 输出: 语义化地址。

# ── baidu_map_weather ──
# 天气查询，按行政区划名称或坐标查询。
#
# 参数:
#   region (string, 可选) 行政区划名称，例如：北京市
#   location (string, 可选) lat,lng 格式坐标（gcj02）
#
# 规则: region 与 location 至少传一个。
#
# 输出: 天气信息。

# ── baidu_map_render ──
# 地图展示：根据 resource_key 生成地图链接并打开浏览器。
#
# 参数:
#   resource_key (string, 必填) 地图资源唯一标识，
#         取自 place/direction 接口响应中的 resource_key 字段。
#   open_browser (boolean, 可选) 是否自动打开浏览器，默认 true。
#
# 触发条件: 用户明确表达"在地图上查看""标出来""可视化展示"等意图时使用。
# 不触发: 单纯信息查询（"附近有什么""怎么走"）不触发。

# ═══ 使用流程 ═══

# 1. 地点检索: 直接调用 baidu_map_place，传入完整用户原始需求
# 2. 路线规划:
#    - 先调用 baidu_map_geocoding 获取起点坐标（如用户未提供）
#    - 调用 baidu_map_direction
#    - 若返回澄清列表，向用户展示选项，用户选择后改写请求并传入 refer_pois 重新调用
# 3. 地图展示: place/direction 返回 resource_key 后，用户要求可视化时调用 baidu_map_render
# 4. 天气查询: 直接调用 baidu_map_weather

# ═══ 鉴权配置 ═══
# 需要 BAIDU_MAP_AUTH_TOKEN（Service Key）。
# 申请地址: https://lbs.baidu.com/apiconsole/agentplan
# 配置方式:
#   1. 环境变量: export BAIDU_MAP_AUTH_TOKEN="你的SK"
#   2. 或写入配置文件（由 skill 初始化时传入）
#
# 注意: Token 关联调用次数，请勿随意分享。
