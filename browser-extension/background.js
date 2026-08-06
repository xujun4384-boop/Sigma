// Sigma Browser Controller - Background Service Worker
// 负责通过 WebSocket 与 Sigma 通信，并把命令转发给当前标签页的 Content Script

const DEFAULT_WS_URL = 'ws://127.0.0.1:8765/ws/browser';
const SITE_MEMORY_KEY = 'sigma_site_memory_v1';
const SITE_MEMORY_MAX_DOMAINS = 80;
const SITE_MEMORY_MAX_ENTRIES_PER_DOMAIN = 30;
const SITE_MEMORY_MAX_ENTRY_CHARS = 4000;
let ws = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let isConnected = false;
let cachedLLMConfigs = [];  // 缓存最后从 WebSocket 收到的 LLM 配置
let activeTabId = null;
let lastSigmaStatus = 'disconnected';
let connectInFlight = false;
let connectionSeq = 0;
let manualCloseSeqs = new Set();
const debuggerTabs = new Set();
const axRefStores = new Map();

// ═══════════════════════════════════════════════
// 持久化日志：content.js 发来的操作日志存这里，跨页面导航不丢失
// ═══════════════════════════════════════════════
const _persistentLogs = [];
const MAX_PERSISTENT_LOGS = 500;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'bridge_log' && msg.entry) {
    _persistentLogs.push(msg.entry);
    if (_persistentLogs.length > MAX_PERSISTENT_LOGS) _persistentLogs.shift();
  }
  if (msg.type === 'request_screenshot') {
    const format = msg.format === 'png' ? 'png' : 'jpeg';
    const quality = Math.max(20, Math.min(Number(msg.quality) || 50, 90));
    chrome.tabs.captureVisibleTab(null, { format, quality }).then(dataUrl => {
      sendResponse({ screenshot: dataUrl });
    }).catch(() => sendResponse({ screenshot: '' }));
    return true; // 保持通道开放等待异步返回
  }
  // Panel 请求缓存配置
  if (msg.type === 'get_llm_configs') {
    sendResponse({ configs: cachedLLMConfigs });
    return false;
  }
  // 不 return true，让其他 listener 也能处理
});

const NETWORK_BRIDGE_LLM_KEY = 'sigma-panel-selected-llm-config';
let currentNetworkBridgeLLM = null;

const AX_INTERACTIVE_ROLES = new Set([
  'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
  'listbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option',
  'searchbox', 'slider', 'spinbutton', 'switch', 'tab', 'treeitem'
]);

function isRestrictedBrowserUrl(url) {
  const text = String(url || '').toLowerCase();
  return !text || text.startsWith('chrome://') || text.startsWith('edge://') || text.startsWith('chrome-extension://') || text.startsWith('about:') || text.startsWith('devtools://');
}

function clearDebuggerTabState(tabId) {
  if (!tabId) return;
  debuggerTabs.delete(tabId);
  axRefStores.delete(tabId);
}

async function getTargetTab(params = {}) {
  const tabId = params.tabId || (await getActiveTabId());
  const tab = await chrome.tabs.get(tabId);
  if (!tab?.id) throw new Error('没有找到目标标签页');
  if (isRestrictedBrowserUrl(tab.url)) {
    throw new Error(`当前页面不支持 CDP 控制: ${tab.url || 'unknown'}`);
  }
  return tab;
}

async function ensureDebuggerAttached(tabId) {
  if (debuggerTabs.has(tabId)) return;
  try {
    await chrome.debugger.attach({ tabId }, '1.3');
    debuggerTabs.add(tabId);
  } catch (err) {
    const message = String(err?.message || err || '');
    if (/already attached/i.test(message) && !/Another debugger/i.test(message)) {
      debuggerTabs.add(tabId);
      return;
    }
    throw new Error(`CDP 调试会话连接失败: ${message}`);
  }
}

async function detachDebugger(tabId) {
  if (!debuggerTabs.has(tabId)) return;
  try {
    await chrome.debugger.detach({ tabId });
  } catch (e) {
    // 调试会话可能已被浏览器或用户断开
  } finally {
    clearDebuggerTabState(tabId);
  }
}

async function sendCdp(tabId, method, params = {}) {
  await ensureDebuggerAttached(tabId);
  return await chrome.debugger.sendCommand({ tabId }, method, params);
}

function getAxValue(node, key) {
  const prop = (node.properties || []).find((item) => item.name === key);
  const value = prop?.value?.value;
  return value === undefined || value === null ? '' : String(value);
}

function getAxText(value) {
  const raw = value?.value ?? value;
  return raw === undefined || raw === null ? '' : String(raw).replace(/\s+/g, ' ').trim();
}

function getAxStore(tabId) {
  let store = axRefStores.get(tabId);
  if (!store) {
    store = { nextId: 1, refs: new Map() };
    axRefStores.set(tabId, store);
  }
  return store;
}

function registerAxNode(tabId, node) {
  const store = getAxStore(tabId);
  const ref = `@ax${store.nextId++}`;
  const item = {
    ref,
    nodeId: node.nodeId,
    backendDOMNodeId: node.backendDOMNodeId,
    role: getAxText(node.role),
    name: getAxText(node.name),
    value: getAxText(node.value),
    description: getAxText(node.description),
  };
  store.refs.set(ref, item);
  return item;
}

function resolveAxRef(tabId, ref) {
  const item = axRefStores.get(tabId)?.refs.get(ref);
  if (!item) throw new Error(`未知或已失效的 AX 引用: ${ref}，请重新 ax_snapshot`);
  if (!item.backendDOMNodeId) throw new Error(`AX 引用缺少 backendDOMNodeId: ${ref}`);
  return item;
}

function formatAxNodeLine(item) {
  const parts = [item.ref, item.role || 'node'];
  if (item.name) parts.push(`"${item.name.slice(0, 120)}"`);
  if (item.value) parts.push(`value="${item.value.slice(0, 80)}"`);
  if (item.description) parts.push(`desc="${item.description.slice(0, 80)}"`);
  return parts.join(' ');
}


// 读取用户配置的 WebSocket 地址（如未配置则使用默认）
async function getWsUrl() {
  try {
    const cfg = await chrome.storage.local.get('sigmaWsUrl');
    return cfg.sigmaWsUrl || DEFAULT_WS_URL;
  } catch (e) {
    return DEFAULT_WS_URL;
  }
}

function setConnectionStatus(connected) {
  isConnected = connected;
  try {
    chrome.runtime.sendMessage({ type: 'connection_status', connected }).catch(() => {});
  } catch (e) {
    // popup / side panel 可能未打开
  }
}

// 用 canvas 生成动态图标：连接成功显示绿色圆点，断开显示灰色圆点
function updateIcon(connected) {
  try {
    const size = 128;
    const canvas = new OffscreenCanvas(size, size);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // 背景圆
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 4, 0, Math.PI * 2);
    ctx.fillStyle = connected ? '#22c55e' : '#6b7280';
    ctx.fill();

    // 内部高光
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 14, 0, Math.PI * 2);
    ctx.fillStyle = connected ? '#4ade80' : '#9ca3af';
    ctx.fill();

    const imageData = ctx.getImageData(0, 0, size, size);
    chrome.action.setIcon({ imageData });
  } catch (e) {
    console.warn('[Sigma BG] 设置图标失败:', e);
  }
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      stopHeartbeat();
      setConnectionStatus(false);
      scheduleReconnect('heartbeat_socket_not_open');
      return;
    }
    try {
      ws.send(JSON.stringify({ id: `hb-${Date.now()}`, action: 'heartbeat', params: { ts: Date.now() } }));
    } catch (e) {
      console.warn('[Sigma BG] heartbeat 发送失败:', e);
      stopHeartbeat();
      setConnectionStatus(false);
      scheduleReconnect('heartbeat_send_failed');
    }
  }, 10000);
}

async function updateActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    activeTabId = tab?.id ?? null;
    return activeTabId;
  } catch (e) {
    return null;
  }
}

function normalizeSiteMemoryUrl(value) {
  if (!value || typeof value !== 'string') return null;
  try {
    return new URL(value);
  } catch (e) {
    return null;
  }
}

function normalizeSiteMemoryDomain(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return '';
  const parsed = normalizeSiteMemoryUrl(text.includes('://') ? text : `https://${text}`);
  const host = (parsed?.hostname || text).replace(/^www\./, '');
  return host.replace(/[^a-z0-9.-]/g, '').slice(0, 120);
}

async function getCurrentTabForSiteMemory(params = {}) {
  if (params.url) {
    const parsed = normalizeSiteMemoryUrl(params.url);
    return { url: params.url, host: parsed?.hostname || '', title: '' };
  }
  const tabId = params.tabId || (await getActiveTabId());
  const tab = await chrome.tabs.get(tabId);
  return { url: tab?.url || '', host: normalizeSiteMemoryUrl(tab?.url)?.hostname || '', title: tab?.title || '' };
}

async function readSiteMemoryStore() {
  const data = await chrome.storage.local.get(SITE_MEMORY_KEY);
  const store = data?.[SITE_MEMORY_KEY];
  if (store && store.version === 1 && store.domains && typeof store.domains === 'object') {
    return store;
  }
  return { version: 1, domains: {} };
}

async function writeSiteMemoryStore(store) {
  await chrome.storage.local.set({ [SITE_MEMORY_KEY]: store });
}

function trimSiteMemoryStore(store) {
  const domains = Object.values(store.domains || {})
    .sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')))
    .slice(0, SITE_MEMORY_MAX_DOMAINS);
  store.domains = {};
  for (const domainMemory of domains) {
    const domain = normalizeSiteMemoryDomain(domainMemory.domain);
    if (!domain) continue;
    const entries = Array.isArray(domainMemory.entries) ? domainMemory.entries : [];
    domainMemory.domain = domain;
    domainMemory.entries = entries
      .sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')))
      .slice(0, SITE_MEMORY_MAX_ENTRIES_PER_DOMAIN);
    store.domains[domain] = domainMemory;
  }
  return store;
}

function sanitizeSiteMemoryEntry(entry) {
  const source = entry && typeof entry === 'object' ? entry : {};
  const now = new Date().toISOString();
  const safe = {
    id: String(source.id || `mem-${Date.now()}`).slice(0, 120),
    scope: source.scope && typeof source.scope === 'object' ? source.scope : {},
    taskPattern: String(source.taskPattern || '').slice(0, 300),
    lesson: String(source.lesson || '').slice(0, 1000),
    successSignals: Array.isArray(source.successSignals) ? source.successSignals.map((v) => String(v).slice(0, 240)).slice(0, 8) : [],
    preferredCommands: Array.isArray(source.preferredCommands) ? source.preferredCommands.slice(0, 8) : [],
    preferredActions: Array.isArray(source.preferredActions) ? source.preferredActions.slice(0, 8) : [],
    avoid: Array.isArray(source.avoid) ? source.avoid.map((v) => String(v).slice(0, 240)).slice(0, 8) : [],
    failures: Array.isArray(source.failures) ? source.failures.slice(0, 8) : [],
    confidence: Math.max(0, Math.min(Number(source.confidence) || 0.5, 1)),
    hits: Math.max(0, Number(source.hits) || 0),
    failuresCount: Math.max(0, Number(source.failuresCount) || 0),
    createdAt: source.createdAt || now,
    updatedAt: source.updatedAt || now,
  };
  const serialized = JSON.stringify(safe);
  if (serialized.length <= SITE_MEMORY_MAX_ENTRY_CHARS) return safe;
  safe.preferredCommands = [];
  safe.preferredActions = [];
  safe.failures = [];
  safe.lesson = safe.lesson.slice(0, 600);
  return safe;
}

async function handleSiteMemoryCommand(action, params = {}) {
  const tabInfo = await getCurrentTabForSiteMemory(params).catch(() => ({ url: params.url || '', host: '', title: '' }));
  const domain = normalizeSiteMemoryDomain(params.domain || tabInfo.host || tabInfo.url);
  if (!domain && action !== 'site_memory_list') {
    return { success: false, error: '无法确定站点域名，不能读写站点记忆' };
  }

  const store = await readSiteMemoryStore();
  if (action === 'site_memory_get') {
    const domainMemory = store.domains[domain] || { domain, entries: [] };
    return { success: true, data: { domain, url: tabInfo.url, title: tabInfo.title, memory: domainMemory } };
  }

  if (action === 'site_memory_list') {
    return { success: true, data: { domains: Object.values(store.domains || {}) } };
  }

  if (action === 'site_memory_clear') {
    if (domain && store.domains[domain]) {
      delete store.domains[domain];
    } else if (params.all === true) {
      store.domains = {};
    }
    await writeSiteMemoryStore(store);
    return { success: true, data: { cleared: params.all === true ? 'all' : domain } };
  }

  if (action === 'site_memory_put') {
    const now = new Date().toISOString();
    const existing = store.domains[domain] || { domain, entries: [], createdAt: now };
    const incoming = Array.isArray(params.entries) ? params.entries : [params.entry || params.memory].filter(Boolean);
    const entriesById = new Map((existing.entries || []).map((entry) => [String(entry.id || ''), entry]));
    for (const rawEntry of incoming) {
      const safeEntry = sanitizeSiteMemoryEntry(rawEntry);
      entriesById.set(safeEntry.id, safeEntry);
    }
    existing.domain = domain;
    existing.updatedAt = now;
    existing.entries = Array.from(entriesById.values());
    store.domains[domain] = existing;
    await writeSiteMemoryStore(trimSiteMemoryStore(store));
    return { success: true, data: { domain, saved: incoming.length, memory: store.domains[domain] } };
  }

  return { success: false, error: `未知站点记忆动作: ${action}` };
}

async function sendStatusToTab(tabId, state) {
  if (!tabId) return;
  try {
    await ensureContentScriptInjected(tabId);
    await chrome.tabs.sendMessage(tabId, { action: 'sigma_status', params: { state } });
  } catch (e) {
    // 标签页可能已关闭或不支持 content script
  }
}

async function broadcastSigmaStatus(state) {
  console.log('[Sigma BG] 广播状态:', state, '当前标签页:', activeTabId);
  lastSigmaStatus = state;

  // 扩展图标角标
  try {
    if (state === 'connected' || state === 'idle') {
      chrome.action.setBadgeText({ text: 'READY' });
      chrome.action.setBadgeBackgroundColor({ color: '#22c55e' });
      chrome.action.setTitle({ title: 'Sigma Browser Controller - Ready' });
    } else if (state === 'working') {
      chrome.action.setBadgeText({ text: 'AI' });
      chrome.action.setBadgeBackgroundColor({ color: '#f59e0b' });
      chrome.action.setTitle({ title: 'Sigma Browser Controller - AI Working' });
    } else {
      chrome.action.setBadgeText({ text: '' });
      chrome.action.setTitle({ title: 'Sigma Browser Controller' });
    }
  } catch (e) {
    // 忽略角标设置失败
  }

  if (state === 'disconnected') {
    // 断开时清理所有标签页上的状态浮层
    try {
      const tabs = await chrome.tabs.query({});
      for (const tab of tabs) {
        sendStatusToTab(tab.id, 'disconnected').catch(() => {});
      }
    } catch (e) {}
    activeTabId = null;
    return;
  }

  const targetId = activeTabId || (await updateActiveTab());
  if (targetId) {
    sendStatusToTab(targetId, state);
  }
}

async function connect(force = false) {
  if (ws && ws.readyState === WebSocket.OPEN && !force) {
    console.log('[Sigma BG] WebSocket 已连接，跳过重复 connect', { connectionId: ws.__sigmaConnectionId });
    setConnectionStatus(true);
    return;
  }

  if (ws && ws.readyState === WebSocket.CONNECTING && !force) {
    console.log('[Sigma BG] WebSocket 正在连接，跳过重复 connect', { connectionId: ws.__sigmaConnectionId });
    return;
  }

  if (connectInFlight && !force) {
    console.log('[Sigma BG] connect 已在进行中，跳过重复 connect');
    return;
  }

  connectInFlight = true;

  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  if (ws) {
    try {
      manualCloseSeqs.add(ws.__sigmaConnectionId);
      ws.close(1000, force ? 'manual reconnect' : 'replace stale socket');
    } catch (e) {}
    ws = null;
  }

  const url = await getWsUrl();
  const connectionId = ++connectionSeq;
  console.log('[Sigma BG] 连接 WebSocket:', url, { connectionId, force });

  try {
    ws = new WebSocket(url);
    ws.__sigmaConnectionId = connectionId;
  } catch (e) {
    console.error('[Sigma BG] 创建 WebSocket 失败:', e, { connectionId });
    connectInFlight = false;
    scheduleReconnect('create_failed');
    return;
  }

  ws.onopen = () => {
    connectInFlight = false;
    console.log('[Sigma BG] WebSocket 已连接', { connectionId });
    setConnectionStatus(true);
    startHeartbeat();
    updateActiveTab().then(() => broadcastSigmaStatus('connected'));
  };

  ws.onmessage = async (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.error('[Sigma BG] 收到非法 JSON:', event.data, { connectionId });
      return;
    }

    // LLM 配置推送：转发给 side panel
    if (msg.type === 'llm_configs') {
      console.log('[Sigma BG] 收到 LLM 配置:', msg.configs?.length, '个');
      cachedLLMConfigs = msg.configs || [];
      chrome.runtime.sendMessage({ type: 'llm_configs', configs: msg.configs }).catch(() => {});
      return;
    }

    console.log('[Sigma BG] 收到命令:', msg.action, msg, { connectionId });
    const result = await handleCommand(msg);
    if (ws && ws.__sigmaConnectionId === connectionId && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ id: msg.id, ...result }));
    }
  };

  ws.onclose = (event) => {
    const wasManual = manualCloseSeqs.delete(connectionId);
    connectInFlight = false;
    console.log('[Sigma BG] WebSocket 已断开', event.code, event.reason, { connectionId, wasManual });
    if (ws && ws.__sigmaConnectionId === connectionId) {
      ws = null;
    }
    if (wasManual) return;
    stopHeartbeat();
    setConnectionStatus(false);
    broadcastSigmaStatus('disconnected');
    scheduleReconnect(`close:${event.code || 'unknown'}`);
  };

  ws.onerror = (e) => {
    console.error('[Sigma BG] WebSocket 错误:', e, { connectionId });
    setConnectionStatus(false);
  };
}

function scheduleReconnect(reason = 'unspecified') {
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log('[Sigma BG] 连接正常，跳过重连调度', { reason, connectionId: ws.__sigmaConnectionId });
    return;
  }
  if (ws && ws.readyState === WebSocket.CONNECTING) {
    console.log('[Sigma BG] 正在连接，跳过重连调度', { reason, connectionId: ws.__sigmaConnectionId });
    return;
  }
  if (reconnectTimer) clearTimeout(reconnectTimer);
  console.log('[Sigma BG] 调度 WebSocket 重连', { reason });
  reconnectTimer = setTimeout(() => connect(false), 3000);
  // 使用 alarms API 唤醒 service worker；connect 本身会防重复。
  try {
    chrome.alarms.create('sigma-reconnect', { delayInMinutes: 0.05 });
  } catch (e) {
    // 忽略 alarms 创建失败
  }
}

// 通过 alarms 唤醒 service worker 后重新连接
chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm.name === 'sigma-reconnect') {
    if (!isConnected) {
      connect(false);
    }
  }
});

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getCdpViewport(tabId) {
  const metrics = await sendCdp(tabId, 'Page.getLayoutMetrics').catch(() => null);
  const visual = metrics?.visualViewport || metrics?.layoutViewport || {};
  return {
    width: Math.round(visual.clientWidth || 0),
    height: Math.round(visual.clientHeight || 0),
    scrollX: Math.round(visual.pageX || 0),
    scrollY: Math.round(visual.pageY || 0),
    devicePixelRatio: 1,
  };
}

async function handleAxSnapshot(params = {}) {
  const tab = await getTargetTab(params);
  await sendCdp(tab.id, 'Accessibility.enable').catch(() => {});
  const result = await sendCdp(tab.id, 'Accessibility.getFullAXTree');
  const store = { nextId: 1, refs: new Map() };
  axRefStores.set(tab.id, store);

  const nodes = [];
  for (const node of result.nodes || []) {
    const role = getAxText(node.role);
    const name = getAxText(node.name);
    const value = getAxText(node.value);
    const ignored = Boolean(node.ignored);
    const disabled = getAxValue(node, 'disabled') === 'true';
    const focusable = getAxValue(node, 'focusable') === 'true';
    const editable = getAxValue(node, 'editable');
    const hasUsefulText = Boolean(name || value || getAxText(node.description));
    const isInteractive = AX_INTERACTIVE_ROLES.has(role) || focusable || Boolean(editable);
    if (ignored || !node.backendDOMNodeId || (!isInteractive && !hasUsefulText)) continue;
    const item = registerAxNode(tab.id, node);
    item.disabled = disabled;
    item.focusable = focusable;
    if (editable) item.editable = editable;
    nodes.push(item);
    if (nodes.length >= 350) break;
  }

  const compactNodes = nodes.slice(0, Math.max(1, Math.min(Number(params.limit) || 120, 350)));
  return {
    success: true,
    data: {
      source: 'cdp_ax',
      url: tab.url || '',
      title: tab.title || '',
      tree: compactNodes.map(formatAxNodeLine).join('\n'),
      nodes: compactNodes,
      refCount: nodes.length,
      tabId: tab.id,
    }
  };
}

async function handleCdpScreenshot(params = {}) {
  const tab = await getTargetTab(params);
  const format = params.format === 'jpeg' ? 'jpeg' : 'png';
  const options = { format };
  if (format === 'jpeg') options.quality = Math.max(20, Math.min(Number(params.quality) || 80, 90));
  const result = await sendCdp(tab.id, 'Page.captureScreenshot', options);
  const viewport = await getCdpViewport(tab.id);
  return {
    success: true,
    data: {
      source: 'cdp_page_capture',
      screenshot: `data:image/${format};base64,${result.data}`,
      mimeType: `image/${format}`,
      tabId: tab.id,
      viewport: { ...viewport, url: tab.url || '', title: tab.title || '' },
    }
  };
}

async function getCdpObjectIdForTarget(tabId, params = {}) {
  if (params.ref) {
    const item = resolveAxRef(tabId, params.ref);
    const resolved = await sendCdp(tabId, 'DOM.resolveNode', { backendNodeId: item.backendDOMNodeId });
    if (!resolved.object?.objectId) throw new Error(`无法解析 AX 引用: ${params.ref}`);
    return { objectId: resolved.object.objectId, meta: item };
  }
  if (params.selector) {
    const evaluated = await sendCdp(tabId, 'Runtime.evaluate', {
      expression: `document.querySelector(${JSON.stringify(params.selector)})`,
      returnByValue: false,
    });
    if (evaluated.exceptionDetails) throw new Error(evaluated.exceptionDetails.text || 'selector evaluate failed');
    if (!evaluated.result?.objectId || evaluated.result.subtype === 'null') throw new Error(`未找到元素: ${params.selector}`);
    return { objectId: evaluated.result.objectId, meta: { selector: params.selector } };
  }
  throw new Error('请提供 ref 或 selector');
}

async function getCdpElementCenter(tabId, objectId) {
  await sendCdp(tabId, 'Runtime.callFunctionOn', {
    objectId,
    functionDeclaration: `function() { this.scrollIntoView({ block: 'center', inline: 'center' }); }`,
  }).catch(() => {});
  const box = await sendCdp(tabId, 'DOM.getBoxModel', { objectId });
  const content = box.model?.content || box.model?.border;
  if (!content || content.length < 8) throw new Error('元素没有可点击布局盒');
  const x = (content[0] + content[2] + content[4] + content[6]) / 4;
  const y = (content[1] + content[3] + content[5] + content[7]) / 4;
  return { x, y };
}

async function handleCdpClick(params = {}) {
  const tab = await getTargetTab(params);
  let x = Number(params.x);
  let y = Number(params.y);
  let target = null;
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    target = await getCdpObjectIdForTarget(tab.id, params);
    // scrollIntoViewIfNeeded 后元素位置可能变化，必须重新取坐标
    await sendCdp(tab.id, 'Runtime.callFunctionOn', {
      objectId: target.objectId,
      functionDeclaration: `function() {
        if (typeof this.scrollIntoViewIfNeeded === 'function') {
          this.scrollIntoViewIfNeeded(true);
        } else {
          this.scrollIntoView({ block: 'center', inline: 'center' });
        }
        const r = this.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }`,
      returnByValue: true,
    }).catch(() => {});
    await new Promise(resolve => setTimeout(resolve, 60));
    if (target?.objectId) {
      const updatedCenter = await getCdpElementCenter(tab.id, target.objectId);
      if (updatedCenter) {
        x = updatedCenter.x;
        y = updatedCenter.y;
      }
    }
  }
  const urlBefore = tab.url;
  await sendCdp(tab.id, 'Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none', buttons: 0 });
  await sendCdp(tab.id, 'Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', buttons: 1, clickCount: 1 });
  await sendCdp(tab.id, 'Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', buttons: 0, clickCount: 1 });
  return {
    success: true,
    data: {
      source: 'cdp_input',
      clicked: true,
      x: Math.round(x),
      y: Math.round(y),
      tabId: tab.id,
      target: target?.meta || null,
      urlBefore,
      navigationDetected: false, // CDP 层无法即时感知，由后续 snapshot/list_tabs 检测
    }
  };
}

async function focusCdpTarget(tabId, params = {}) {
  if (!params.ref && !params.selector) return null;
  const target = await getCdpObjectIdForTarget(tabId, params);
  const result = await sendCdp(tabId, 'Runtime.callFunctionOn', {
    objectId: target.objectId,
    functionDeclaration: `function() { this.scrollIntoView({ block: 'center', inline: 'center' }); if (typeof this.focus === 'function') this.focus(); return { tag: this.tagName, text: (this.innerText || this.textContent || '').slice(0, 100) }; }`,
    returnByValue: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'focus failed');
  return { ...target.meta, focused: result.result?.value || null };
}

async function handleCdpType(params = {}) {
  const text = params.text ?? params.value;
  if (typeof text !== 'string') throw new Error('cdp_type 需要 text 字符串');
  const tab = await getTargetTab(params);
  const target = await focusCdpTarget(tab.id, params);
  await sendCdp(tab.id, 'Input.insertText', { text });
  return {
    success: true,
    data: {
      source: 'cdp_input',
      typed: true,
      length: text.length,
      tabId: tab.id,
      target,
    }
  };
}

const CDP_KEY_SPECS = {
  enter: { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' },
  return: { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' },
  tab: { key: 'Tab', code: 'Tab', windowsVirtualKeyCode: 9 },
  escape: { key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 },
  esc: { key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 },
  backspace: { key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 },
  delete: { key: 'Delete', code: 'Delete', windowsVirtualKeyCode: 46 },
  arrowup: { key: 'ArrowUp', code: 'ArrowUp', windowsVirtualKeyCode: 38 },
  arrowdown: { key: 'ArrowDown', code: 'ArrowDown', windowsVirtualKeyCode: 40 },
  arrowleft: { key: 'ArrowLeft', code: 'ArrowLeft', windowsVirtualKeyCode: 37 },
  arrowright: { key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 },
};

function cdpKeySpec(key) {
  const text = String(key || '').trim();
  if (!text) throw new Error('cdp_keypress 需要 key');
  const spec = CDP_KEY_SPECS[text.toLowerCase()];
  if (spec) return spec;
  if (/^[a-z]$/i.test(text)) {
    const upper = text.toUpperCase();
    return { key: text.toLowerCase(), code: `Key${upper}`, windowsVirtualKeyCode: upper.charCodeAt(0), text: text.toLowerCase() };
  }
  if (/^[0-9]$/.test(text)) return { key: text, code: `Digit${text}`, windowsVirtualKeyCode: text.charCodeAt(0), text };
  throw new Error(`不支持的 cdp_keypress key: ${key}`);
}

async function handleCdpKeypress(params = {}) {
  const tab = await getTargetTab(params);
  await focusCdpTarget(tab.id, params);
  const repeat = Math.max(1, Math.min(Number(params.repeat) || 1, 50));
  const spec = cdpKeySpec(params.key || params.keys);
  for (let i = 0; i < repeat; i++) {
    const textPayload = spec.text && spec.key.length === 1 ? { text: spec.text } : {};
    await sendCdp(tab.id, 'Input.dispatchKeyEvent', { type: 'keyDown', key: spec.key, code: spec.code, windowsVirtualKeyCode: spec.windowsVirtualKeyCode, ...textPayload });
    await sendCdp(tab.id, 'Input.dispatchKeyEvent', { type: 'keyUp', key: spec.key, code: spec.code, windowsVirtualKeyCode: spec.windowsVirtualKeyCode });
  }
  return {
    success: true,
    data: {
      source: 'cdp_input',
      keypressed: true,
      key: spec.key,
      dispatched: repeat,
      tabId: tab.id,
    }
  };
}

async function handleGetBookmarks(params = {}) {
  try {
    const keyword = (params.keyword || params.query || '').toLowerCase().trim();
    const maxResults = Math.max(1, Math.min(Number(params.limit) || 20, 100));

    // 获取完整书签树
    const tree = await chrome.bookmarks.getTree();

    // 递归扁平化书签，只保留有 URL 的叶子节点
    const flat = [];
    function walk(nodes, parentTitle = '') {
      for (const node of nodes) {
        if (node.url) {
          flat.push({
            id: node.id,
            title: node.title || '',
            url: node.url,
            parentTitle: parentTitle || '',
            dateAdded: node.dateAdded,
          });
        }
        if (node.children) {
          walk(node.children, node.title || parentTitle);
        }
      }
    }
    walk(tree);

    // 按关键词过滤
    let results = flat;
    if (keyword) {
      results = results.filter((bm) => {
        return (
          bm.title.toLowerCase().includes(keyword) ||
          bm.url.toLowerCase().includes(keyword) ||
          bm.parentTitle.toLowerCase().includes(keyword)
        );
      });
    }

    // 截断
    const total = results.length;
    results = results.slice(0, maxResults);

    return {
      success: true,
      data: {
        keyword: keyword || null,
        total,
        count: results.length,
        results: results.map((bm) => ({
          title: bm.title,
          url: bm.url,
          folder: bm.parentTitle || '根目录',
        })),
      }
    };
  } catch (e) {
    return { success: false, error: `无法读取收藏夹: ${e.message}` };
  }
}

// ═══════════════════════════════════════════════════════════════
// 命令处理入口（纯浏览器执行器，LLM 回路已迁移到 Python 后端）
// ═══════════════════════════════════════════════════════════════

async function handleCommand(msg) {
  const { action, params = {}, id } = msg;
  const cmdId = id || 'no-id';
  console.log(`[handleCommand] 收到命令 id=${cmdId}, action=${action}, params_keys=${Object.keys(params || {})}`);
  const shouldShowWorking = action !== 'sigma_status' && action !== 'heartbeat';
  const startedAt = Date.now();
  try {
    if (shouldShowWorking) {
      await broadcastSigmaStatus('working');
    }

    // 状态通知：由 Sigma 主程序发来，转发到当前标签页
    if (action === 'sigma_status') {
      console.log('[Sigma BG] 收到状态通知:', params.state);
      await broadcastSigmaStatus(params.state || 'connected');
      return { success: true, data: { state: lastSigmaStatus } };
    }

    // 浏览器级命令（不需要 Content Script）
    if (action === 'get_tabs' || action === 'list_tabs') {
      const tabs = await chrome.tabs.query({});
      return {
        success: true,
        data: tabs.map((t) => ({ id: t.id, tabId: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId }))
      };
    }

    if (action === 'get_bridge_logs') {
      const limit = Math.min(params.limit || 100, MAX_PERSISTENT_LOGS);
      const logs = _persistentLogs.slice(-limit);
      return {
        success: true,
        data: { logs, total: _persistentLogs.length },
      };
    }

    if (action === 'activate_tab') {
      await chrome.tabs.update(params.tabId, { active: true });
      return { success: true, data: { activated: params.tabId } };
    }

    if (action === 'navigate') {
      const tabId = params.tabId || (await getActiveTabId());
      await chrome.tabs.update(tabId, { url: params.url });
      activeTabId = tabId; // 锁定导航后的 tab，防止多标签页下后续操作漂移
      return { success: true, data: { navigated: params.url, tabId } };
    }

    if (action === 'new_tab') {
      const tab = await chrome.tabs.create({
        url: params.url || 'about:blank',
        active: params.active !== false
      });
      if (params.active !== false) activeTabId = tab.id; // 新前台 tab 成为当前目标
      return { success: true, data: { tabId: tab.id, url: tab.url } };
    }

    if (action === 'close_tab') {
      await chrome.tabs.remove(params.tabId);
      return { success: true, data: { closed: params.tabId } };
    }

    if (action === 'screenshot') {
      const tabId = params.tabId || (await getActiveTabId());
      await ensureContentScriptInjected(tabId);
      const viewport = await chrome.tabs.sendMessage(tabId, { action: 'viewport', params: {} }).catch(() => null);
      const format = params.format === 'png' ? 'png' : 'jpeg';
      const quality = Math.max(20, Math.min(Number(params.quality) || 65, 90));
      const captureOptions = format === 'jpeg' ? { format, quality } : { format };
      const dataUrl = await chrome.tabs.captureVisibleTab(null, captureOptions);
      return {
        success: true,
        data: {
          screenshot: dataUrl,
          mimeType: format === 'jpeg' ? 'image/jpeg' : 'image/png',
          compressed: format === 'jpeg',
          tabId,
          viewport
        }
      };
    }

    if (action === 'wait') {
      const ms = Math.max(0, Math.min(Number(params.duration) || 1000, 60000));
      await wait(ms);
      return { success: true, data: { waited: ms } };
    }

    if (action === 'site_memory_get' || action === 'site_memory_put' || action === 'site_memory_list' || action === 'site_memory_clear') {
      return await handleSiteMemoryCommand(action, params);
    }

    if (action === 'get_bookmarks') {
      return await handleGetBookmarks(params);
    }

    if (action === 'ax_snapshot') {
      return await handleAxSnapshot(params);
    }

    if (action === 'cdp_screenshot') {
      return await handleCdpScreenshot(params);
    }

    if (action === 'cdp_click') {
      return await handleCdpClick(params);
    }

    if (action === 'cdp_type') {
      return await handleCdpType(params);
    }

    if (action === 'cdp_keypress') {
      return await handleCdpKeypress(params);
    }

    // 默认：把命令发给当前激活标签页的 Content Script 执行
    const tabId = params.tabId || (await getActiveTabId());
    await ensureContentScriptInjected(tabId);
    const response = await chrome.tabs.sendMessage(tabId, { action, params });
    return { success: true, data: response };
  } catch (err) {
    console.error('[Sigma BG] 命令执行失败:', action, err);
    return { success: false, error: err.message };
  } finally {
    console.log(`[handleCommand] 命令处理结束 id=${cmdId}, action=${action}, 耗时=${Date.now() - startedAt}ms`);
    if (shouldShowWorking) {
      const elapsed = Date.now() - startedAt;
      if (elapsed < 350) {
        await wait(350 - elapsed);
      }
      await broadcastSigmaStatus('idle');
    }
  }
}

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('没有找到当前激活的标签页');
  return tab.id;
}

async function ensureContentScriptInjected(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { action: 'ping' });
  } catch (e) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content.js']
    });
  }
}

// 监听来自 popup / side panel 的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'get_status' || request.type === 'get_connection_status') {
    if (!isConnected) {
      connect(false);
    }
    sendResponse({ connected: isConnected, wsUrl: DEFAULT_WS_URL });
    return false;
  }
  if (request.type === 'reconnect') {
    connect(true);
    sendResponse({ ok: true });
    return false;
  }

  // ===== 录制消息 =====
  if (request.type === 'start_recording') {
    recordingActive = true;
    recordedSteps = [];
    console.log('[Sigma BG] 录制已启动');
    sendResponse({ success: true, recording: true });
    return false;
  }
  if (request.type === 'stop_recording') {
    recordingActive = false;
    const steps = [...recordedSteps];
    recordedSteps = [];
    console.log('[Sigma BG] 录制已停止，共', steps.length, '步');
    sendResponse({ success: true, steps, count: steps.length });
    return false;
  }
  if (request.type === 'record_step') {
    if (recordingActive && request.step) {
      recordedSteps.push(request.step);
      console.log('[Sigma BG] 录制步骤:', request.step.description, '(总计', recordedSteps.length, '步)');
    }
    sendResponse({ ok: true });
    return false;
  }
  if (request.type === 'get_recording_status') {
    sendResponse({ recording: recordingActive, stepCount: recordedSteps.length });
    return false;
  }
  if (request.type === 'networkbridge_selected_llm') {
    currentNetworkBridgeLLM = request.config || null;
    console.log('[Sigma BG] NetworkBridge LLM 已更新:', currentNetworkBridgeLLM?.name || 'null');
    chrome.storage.local.set({
      [NETWORK_BRIDGE_LLM_KEY]: currentNetworkBridgeLLM || null,
      'sigma-panel-selected-llm': request.name || '',
    }).catch(() => {});
    sendResponse({ success: true });
    return false;
  }

  return false;
});

// 全局录制状态（跨标签页持久化）
let recordingActive = false;
let recordedSteps = [];

// 配置 Side Panel：点击扩展图标时自动打开（Chrome / Edge 114+ 推荐方式）
async function setupSidePanel() {
  try {
    if (chrome.sidePanel && chrome.sidePanel.setPanelBehavior) {
      await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
      console.log('[Sigma BG] Side Panel 行为已设置为点击图标打开');
      return;
    }
  } catch (e) {
    console.warn('[Sigma BG] setPanelBehavior 失败，回退到 onClicked:', e);
  }

  if (chrome.sidePanel && chrome.sidePanel.open) {
    chrome.action.onClicked.addListener(async (tab) => {
      try {
        await chrome.sidePanel.open({ windowId: tab.windowId });
      } catch (e2) {
        console.warn('[Sigma BG] 打开 side panel 失败:', e2);
      }
    });
  }
}

setupSidePanel();

// 恢复 NetworkBridge 当前选中的 LLM 配置
(async function restoreNetworkBridgeLLM() {
  try {
    const stored = await chrome.storage.local.get(NETWORK_BRIDGE_LLM_KEY);
    if (stored[NETWORK_BRIDGE_LLM_KEY]) {
      currentNetworkBridgeLLM = stored[NETWORK_BRIDGE_LLM_KEY];
      console.log('[Sigma BG] 已恢复 NetworkBridge LLM:', currentNetworkBridgeLLM.name);
    }
  } catch (e) { /* ignore */ }
})();

// 启动时尝试连接
connect(false);

// 创建周期性 alarm，确保 service worker 会定期检查连接
// Manifest V3 中 service worker 容易被系统挂起，alarm 可以唤醒它
try {
  chrome.alarms.create('sigma-keepalive', { periodInMinutes: 0.5 });
} catch (e) {
  console.error('[Sigma BG] 创建 keepalive alarm 失败:', e);
}

chrome.alarms?.onAlarm?.addListener((alarm) => {
  if (alarm.name === 'sigma-keepalive') {
    console.log('[Sigma BG] keepalive alarm 触发，连接状态:', isConnected);
    if (!isConnected) {
      connect(false);
    }
  }
});

// 跟踪当前激活标签页，让状态浮层跟随当前页面
chrome.tabs.onRemoved.addListener((tabId) => {
  clearDebuggerTabState(tabId);
});

chrome.debugger?.onDetach?.addListener((source) => {
  if (source?.tabId) clearDebuggerTabState(source.tabId);
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  const previousTabId = activeTabId;
  activeTabId = activeInfo.tabId;
  if (previousTabId && previousTabId !== activeTabId && lastSigmaStatus !== 'disconnected') {
    sendStatusToTab(previousTabId, 'disconnected').catch(() => {});
  }
  if (lastSigmaStatus !== 'disconnected') {
    sendStatusToTab(activeTabId, lastSigmaStatus);
  }
});

// 页面刷新后重新显示当前状态
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'loading' || changeInfo.url) {
    axRefStores.delete(tabId);
  }
  if (changeInfo.status === 'complete' && tab.active && tab.id === activeTabId && lastSigmaStatus !== 'disconnected') {
    sendStatusToTab(tabId, lastSigmaStatus);
  }
});
