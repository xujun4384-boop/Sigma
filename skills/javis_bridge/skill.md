# javis_bridge skill
# 与另一台电脑上的 Javis 智能体跨机沟通：带上下文发起完整咨询（自动多轮、6/12 轮上限、[[END]] 双向中止），也支持单条消息、沟通记录与文件收发。
# 使用场景：用户让你咨询/求助 Javis、把任务转交给它、查看它是否回复、把本地文件发给它，或取回它发来的文件。
# 包含工具: javis_bridge
# ---------------------------------------------------------------------------

# ═══ 核心规则 ═══

1. 需要向 Javis 提问、求助或确认信息时，优先用 action="consult"：把问题放进 content，
   把当前任务目标、已完成步骤、关键数据放进 context。工具会在内部完成整场多轮对话，
   结束后把结果返回，你再带着结果继续原任务。
2. consult 已内置轮次控制：收到第 6 条 Javis 消息开始收尾提示，第 12 条强制追加 [[END]] 并结束；
   不要用 send 手动续聊，也不要自己编造 Javis 的回复。
3. 凡是涉及 Javis 的操作，可先调用 action="status" 确认中转服务器可达、Javis 是否在线。
   如果返回错误（未配置地址/密钥、连接失败等），如实把错误告诉用户并给出配置位置，
   绝不能假装已经联系上 Javis。
4. 单次发消息用 action="send"，默认不要传 wait：发送后立即返回，之后再调用 action="poll" 取回复。
5. 取新消息用 action="poll"。默认 mark_read=true，会推进本地游标，避免重复读取。
6. 收到的消息、回复、附件都必须来自工具返回的真实数据；转述时区分是谁说的（from 字段）。
   正文里的 [[END]] 已由工具剥离，不要把它展示给用户。
7. 发文件：把本地文件路径放进 send 的 attachments；也可以先 action="upload" 拿 file_id。
8. 收文件：从 poll/history 返回的 attachments 中拿 file_id，调用 action="download"。
   默认保存到 .sigma2.0/javis_inbox；把返回的 saved_to 路径告诉用户，方便后续上岛暂存。
9. action="history" 只读取最近消息，不推进游标，适合回顾双方沟通内容。
10. 用户要求中止对话时调用 action="end"，会发送 [[END]] 收线；单文件上限 200MB，不接受目录。
11. 不要向用户输出访问密钥；配置项在「设置 → 技能 API 配置 → Javis 桥接」。

# ═══ 动作与参数 ═══

── consult（带上下文咨询 Javis，推荐）──
向 Javis 发起一次完整咨询：工具内部用 Sigma 当前主模型逐条生成回复，自动多轮对话，
直到收到/发出 [[END]]、达到 12 轮硬上限、180 秒无新消息或用户中止。
参数: content（必填，初始问题）、
      context（强烈建议，当前任务目标/已完成步骤/关键数据）、
      peer（可选，默认 javis）、
      idle_timeout（可选，默认 180 秒，范围 30-600）

返回: status、rounds、final_answer、transcript、errors。
status 取值: javis（对方结束）/ sigma（本机结束）/ round_limit（12 轮上限）/
             idle_timeout（无消息超时）/ cancelled（用户中止）/ llm_error / send_error。

轮次规则: 收到第 6 条 Javis 消息起进入收尾提示；第 12 条无论模型输出什么都强制追加 [[END]]。
中止规则: 收到带 [[END]] 的消息立即收线且不再回复；本机发出 [[END]] 后不再等待回复。
退出时除“对方先发 [[END]]”外，工具会尽量补发 [[END]] 收线。

── status（连接与在线状态）──
检查中转服务健康度、Javis 是否在线、本机游标位置。
参数: peer（可选，默认 javis）

── send（发送消息）──
把文本和/或附件发送给 Javis。
参数: content（文本，与 attachments 至少一项）、
      attachments（可选，本地文件路径数组）、
      peer（可选）、
      wait（可选，默认 0；仅用户明确要当场等回复时传 5-10 秒，对端离线会自动跳过等待）

返回: sent、message_id、delivered、attachments；等待时额外返回 replies 与 local_cursor。

── poll（拉取新消息）──
按本地游标拉取 Javis 发来的新消息，默认消费游标。
参数: peer（可选）、limit（默认 20，最大 100）、wait（可选，长轮询秒数）、mark_read（默认 true）

返回: count、messages、local_cursor；无新消息时带 hint 提示稍后再查。

── history（查看历史）──
读取与 Javis 的最近沟通记录，不改变游标。
参数: peer（可选）、limit（默认 20，最大 100）

── upload（上传文件）──
只上传文件并拿到 file_id，便于之后附带发送。
参数: file_paths（必填，本地文件路径数组）、peer（可选）

── download（下载附件）──
把 Javis 发来的附件下载到本地。
参数: file_id（必填，来自 messages 的 attachments）、save_dir（可选，默认 .sigma2.0/javis_inbox）

── end（中止对话）──
向 Javis 发送 [[END]]，结束当前对话。
参数: content（可选，附在中止信号前的结束语）、peer（可选）

# ═══ 典型流程 ═══

场景一：用户让你问 Javis 一件事 / 需要 Javis 协助完成任务
1) status 确认在线
2) consult(content="要问的问题…", context="当前任务目标、已完成步骤、关键数据…")
3) 工具返回后，把 final_answer 与 transcript 合并进当前任务，继续干活

场景一补充：只需发一条消息、不需要多轮问答时才用 send + poll

场景二：用户让你把文件发给 Javis
1) send(content="说明…", attachments=["D:/path/a.pdf"])   （文件会先上传再随消息发送）
2) 需要立即确认时再 poll 看对方回执

场景三：查看 Javis 发了什么
1) poll() 取新消息
2) 有附件则 download(file_id=…)，并告知保存路径

# ═══ 通信协议（中转服务器，供后续 Javis 端实现）═══

基础地址: {javisBridgeUrl}/api/javis
鉴权头: X-Bridge-Key: {共享密钥}，X-Agent-Id: {本机身份}

- GET  /health（服务根路径，运维探活用，无需鉴权）与 GET /api/javis/health（客户端用，需鉴权）
  返回 {"ok": true, "service": "javis-bridge", "version": "..."}
- GET  /peers
  返回 {"peers": [{"id": "Sigma", "online": true, "last_seen": 1700000000}]}
- POST /messages
  请求 {"to": "javis", "from": "Sigma", "content": "...", "kind": "text|file|mixed",
        "attachments": [{"file_id": "...", "name": "...", "size": 123}],
        "client_msg_id": "...", "created_at": 1700000000}
  返回 {"id": 42, "delivered": true, "created_at": 1700000000}
- GET  /messages?peer=javis&after=41&limit=20&wait=30
  返回 {"cursor": 43, "messages": [{"id": 43, "from": "javis", "to": "Sigma",
        "kind": "text", "content": "...", "attachments": [], "created_at": 1700000000}]}
  消息 id 必须单调递增；wait>0 时为长轮询，超时无新消息则返回空 messages。
- GET  /history?peer=javis&limit=20
  返回 {"messages": [...]}（最近 N 条，按时间升序）
- POST /files?to=javis（请求体为文件原始字节流）
  请求头: X-File-Name（UTF-8 文件名经 URL 编码）、Content-Type、Content-Length
  返回 {"file_id": "...", "name": "...", "size": 123}
- GET  /files/{file_id}
  返回文件二进制流，建议带 Content-Disposition: filename="..."
  文件在服务器暂存，供接收方下载后由灵动岛进入暂存区。
