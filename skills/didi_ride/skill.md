# didi_ride skill
# ---------------------------------------------------------------------------
# 摘要
# 滴滴出行服务 Skill。通过 DiDi MCP Server + mcporter CLI 提供：
#   - 地址搜索（文本→坐标）
#   - 路线规划（驾车/公交/步行/骑行）
#   - 周边 POI 搜索
#   - 打车价格预估
#   - 实时下单（需要开通免密支付）
#   - 订单查询 / 取消订单 / 司机位置
#   - 生成 App 深度链接（跳转滴滴 App 发单）
#
# ⚠️ 暂未注册到 SkillManager（等移植到 macOS 后由 Javis 自行集成）。
#
# ## 使用场景
# - 打车/叫车："去陆家嘴"、"帮我叫个快车去机场"
# - 查价对比："从国贸到三里屯打车多少钱"
# - 路线规划："从望京到中关村怎么走（公交/驾车/步行/骑行）"
# - 周边搜索："附近有哪些加油站"、"国贸附近有什么好吃的"
# - 订单管理："查询订单"、"取消订单"、"司机到哪了"
# - 预约出行："明天8点去机场"、"15分钟后叫个车"
#
# 触发词：打车、叫车、快车、专车、滴滴、查价格、路线、怎么走、
#          附近、周边、查询订单、取消订单、司机位置、回家、上班
#
# 包含 1 个工具（didi_ride），通过 action 参数区分 13 种操作。
# ---------------------------------------------------------------------------

# ═══ 前置依赖 ═══

1. Node.js >= 18
2. mcporter CLI: npm install -g mcporter
   验证：mcporter --version
3. DiDi MCP Key：访问 https://mcp.didichuxing.com/claw 或用滴滴出行App扫码获取
   凭据由 Settings → Skill Keys 中 didi_mcp_key 自动注入

# ═══ 操作列表 ═══

── 地图类 ──

maps_textsearch (地址搜索)：
  - keywords (string, 必填): 搜索关键词，如"共富二村北大门"
  - city (string, 必填): 城市名，必须完整格式如"上海市"
  - location (string, 可选): 参考位置坐标"经度,纬度"
  输出：匹配的 POI 列表，含名称、坐标、地址

maps_regeocode (坐标转地址)：
  - location (string, 必填): 坐标"经度,纬度"
  输出：对应地址信息

maps_place_around (周边搜索)：
  - keywords (string, 必填): 搜索关键词，如"加油站"、"餐厅"
  - location (string, 必填): 中心坐标"经度,纬度"
  - max_distance (string, 可选): 搜索半径（米）
  输出：周边 POI 列表

maps_direction_driving (驾车路线) / transit (公交) / walking (步行) / bicycling (骑行)：
  - origin (string, 必填): 起点坐标"经度,纬度"
  - destination (string, 必填): 终点坐标"经度,纬度"
  - city (string, transit 必填): 城市名
  输出：路线方案（距离/耗时/途经点）

── 打车类 ──

taxi_estimate (价格预估)：
  - from_lat/from_lng/from_name (string, 必填): 起点坐标和信息
  - to_lat/to_lng/to_name (string, 必填): 终点坐标和信息
  输出：可用车型列表，含 traceId/productCategory/priceText
  ⚠️ 必须记录 traceId，后续下单使用

taxi_create_order (创建订单)：
  - estimate_trace_id (string, 必填): 预估返回的 traceId
  - product_category (string, 必填): 车型代码
    常见：1=快车, 201=特惠快车, 193=轻享, 8=专车, 17=豪华车
  - caller_car_phone (string, 可选): 叫车手机号
  输出：订单信息（orderId/状态）
  ⚠️ 需要开通 DiDi MCP 免密支付才能成功

taxi_query_order (查询订单)：
  - order_id (string, 可选): 订单ID，留空查当前未完成订单
  输出：订单状态码 + 司机信息

  状态码对照：
    0=匹配中, 1=司机已接单, 2=司机已到达,
    4=行程中, 5=已完成, 6/7=已取消

taxi_cancel_order (取消订单)：
  - order_id (string, 必填): 订单ID
  - reason (string, 可选): 取消原因

taxi_get_driver_location (司机位置)：
  - order_id (string, 必填): 订单ID
  输出：司机实时位置坐标

taxi_generate_ride_app_link (生成 App 链接)：
  - from_lat/from_lng/to_lat/to_lng (string, 必填): 起终点坐标
  - product_category (string, 可选): 车型，多车型逗号分隔
  输出：滴滴 App 深度链接，点击跳转 App 完成发单

# ═══ 核心流程 ═══

完整打车流程（6 步）：

1. 地址解析
   didi_ride action=maps_textsearch keywords="共富二村北大门" city="上海市"
   → 获取坐标和详细地址

2. 确认起终点
   多候选时列出选项让用户选择（单结果精确匹配可跳过）

3. 价格预估
   didi_ride action=taxi_estimate from_lat=... from_lng=... to_lat=... to_lng=...
   → 记录 traceId，展示车型和价格

4. 车型选择
   用户在消息中明确指定 → 直接使用
   读取 PREFERENCE.md 场景偏好 → 自动匹配
   都没有 → 询问用户

5. 创建订单
   didi_ride action=taxi_create_order estimate_trace_id=... product_category=1
   → 输出订单号、车型、预估价格、司机信息

6. 跟踪订单
   用户发"查询订单" → didi_ride action=taxi_query_order
   状态变化时更新（匹配中→已接单→已到达→行程中→完成）

# ═══ 偏好设置 ═══

PREFERENCE.md 支持地址别名和车型偏好：
  - 地址别名：设好"家"/"公司"后，说"回家"即可自动解析
  - 场景车型：设好"上班=快车"后，"我要上班"自动选快车
  - 叫车手机号：可选，不设则不传 caller_car_phone

# ═══ 错误处理 ═══

常见错误：
  - "StatusCode=400" → 核对参数名拼写（keywords not keyword）
  - "-32002 鉴权失败" → MCP Key 无效或过期，重新获取
  - "text/plain" → 未开通免密支付，访问 mcp.didichuxing.com 开通
  - "Missing KEY" → DIDI_MCP_KEY 环境变量未设置或未展开
  - "-32021" → estimate_trace_id 过期，重新调用 taxi_estimate

# ═══ 账号权限 ═══

| 操作 | 未开通免密支付 | 已开通免密支付 |
|------|:---:|:---:|
| maps_* 地图搜索 | ✅ | ✅ |
| taxi_estimate 预估 | ✅ | ✅ |
| taxi_create_order 下单 | ❌ | ✅ |
| taxi_query_order 查单 | ✅ | ✅ |
| taxi_cancel_order 取消 | ✅ | ✅ |
| taxi_generate_ride_app_link | ✅ | ✅ |

# ═══ 命令行使用 ═══

```bash
# 地址搜索
python skills/didi_ride/__init__.py maps_textsearch --keywords "陆家嘴" --city "上海市"

# 价格预估
python skills/didi_ride/__init__.py taxi_estimate \
  --from_lat 31.xxx --from_lng 121.xxx --from_name "当前位置" \
  --to_lat 31.yyy --to_lng 121.yyy --to_name "陆家嘴"

# 查询订单
python skills/didi_ride/__init__.py taxi_query_order --order_id "xxx"
```
