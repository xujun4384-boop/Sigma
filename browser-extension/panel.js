(function () {
  'use strict';

  console.log('[Sigma Panel] panel.js 加载');

  const API_BASE = 'http://127.0.0.1:8765';
  const SESSION_ID = 'sigma-panel';
  const SELECTED_LLM_KEY = 'sigma-panel-selected-llm';
  const SELECTED_LLM_CONFIG_KEY = 'sigma-panel-selected-llm-config';

  const els = {
    // status
    statusDot: document.getElementById('status-dot'),
    statusLabel: document.getElementById('status-label'),
    connectionBadge: document.getElementById('connection-badge'),
    backendStatus: document.getElementById('backend-status'),
    wsStatus: document.getElementById('ws-status'),
    tabInfo: document.getElementById('tab-info'),
    // llm selector
    llmSelect: document.getElementById('llm-select'),
    // messages
    messages: document.getElementById('messages'),
    // input
    input: document.getElementById('message-input'),
    sendBtn: document.getElementById('send-btn'),
    // toolbar
    btnTest: document.getElementById('btn-test-bridge'),
    inspectBtn: document.getElementById('inspect-btn'),
    stopBtn: document.getElementById('clear-inspect-btn'),
  };

  let isWsConnected = false;
  let isProcessing = false;
  let abortController = null;
  let streamingBubble = null;
  let streamText = '';
  let thinkingBubble = null;
  let thinkingText = '';
  let llmConfigs = [];  // {name, model, baseUrl, apiKey, protocol}

  // ═══ Messages ═══
  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function removeEmptyState() {
    const empty = els.messages.querySelector('.empty-state');
    if (empty) empty.remove();
  }

  function appendMessage(text, cssClass, options = {}) {
    removeEmptyState();
    const div = document.createElement('div');
    div.className = 'message ' + (cssClass || '');
    if (options.html) {
      div.classList.add('markdown');
      div.innerHTML = text;
    } else {
      div.textContent = text;
    }
    els.messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  // ═══ Markdown Renderer ═══
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderInlineMarkdown(text) {
    let html = escapeHtml(text);
    // 行内代码
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    // 粗体
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    // 斜体
    html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
    html = html.replace(/(?<!_)_([^_]+)_(?!_)/g, '<em>$1</em>');
    // 删除线
    html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    // 链接
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    return html;
  }

  function renderMarkdown(text) {
    if (!text) return '';

    // 保护代码块
    const codeBlocks = [];
    text = text.replace(/```([\s\S]*?)```/g, (m, code) => {
      codeBlocks.push(code);
      return '\u0000CODE_BLOCK_' + (codeBlocks.length - 1) + '\u0000';
    });

    // 处理表格（块级，先于其他块级元素）
    const lines = text.split('\n');
    const outLines = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i].trim();
      if (line.startsWith('|') && line.endsWith('|')) {
        const rows = [];
        while (i < lines.length) {
          const trimmed = lines[i].trim();
          if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
            rows.push(trimmed);
            i++;
          } else {
            break;
          }
        }
        let header = [];
        let body = [];
        if (rows.length >= 2 && /^[\s\-:]+$/.test(rows[1].replace(/\|/g, ''))) {
          header = rows[0].slice(1, -1).split('|').map(c => c.trim());
          body = rows.slice(2).map(r => r.slice(1, -1).split('|').map(c => c.trim()));
        } else {
          body = rows.map(r => r.slice(1, -1).split('|').map(c => c.trim()));
        }
        let tableHtml = '<table class="md-table">';
        if (header.length) {
          tableHtml += '<thead><tr>' +
            header.map(h => '<th>' + renderInlineMarkdown(h) + '</th>').join('') +
            '</tr></thead>';
        }
        tableHtml += '<tbody>' +
          body.map(row => '<tr>' +
            row.map(c => '<td>' + renderInlineMarkdown(c) + '</td>').join('') +
          '</tr>').join('') +
          '</tbody>';
        tableHtml += '</table>';
        outLines.push(tableHtml);
      } else {
        outLines.push(lines[i]);
        i++;
      }
    }
    text = outLines.join('\n');

    // 还原代码块
    text = text.replace(/\u0000CODE_BLOCK_(\d+)\u0000/g, (m, idx) => {
      const code = codeBlocks[idx];
      const firstNl = code.indexOf('\n');
      const lang = firstNl >= 0 ? code.slice(0, firstNl).trim() : '';
      const body = firstNl >= 0 ? code.slice(firstNl + 1) : code;
      return '<pre class="md-code-block"><code class="language-' + escapeHtml(lang) + '">' +
        escapeHtml(body) + '</code></pre>';
    });

    // 块级元素处理
    const blocks = text.split(/\n\n+/);
    const result = blocks.map(block => {
      if (block.startsWith('<table') || block.startsWith('<pre')) return block;

      const blockLines = block.split('\n');

      // 标题
      const hMatch = blockLines[0].match(/^(#{1,6})\s+(.*)$/);
      if (hMatch) {
        const level = hMatch[1].length;
        return '<h' + level + '>' + renderInlineMarkdown(hMatch[2]) + '</h' + level + '>';
      }

      // 引用
      if (blockLines[0].startsWith('> ')) {
        const content = blockLines.map(l => l.replace(/^>\s?/, '')).join(' ');
        return '<blockquote>' + renderInlineMarkdown(content) + '</blockquote>';
      }

      // 无序列表
      if (blockLines.every(l => l.match(/^[-*+]\s/))) {
        return '<ul>' + blockLines.map(l =>
          '<li>' + renderInlineMarkdown(l.replace(/^[-*+]\s/, '')) + '</li>'
        ).join('') + '</ul>';
      }

      // 有序列表
      if (blockLines.every(l => l.match(/^\d+\.\s/))) {
        return '<ol>' + blockLines.map(l =>
          '<li>' + renderInlineMarkdown(l.replace(/^\d+\.\s/, '')) + '</li>'
        ).join('') + '</ol>';
      }

      // 普通段落，行内换行保留为 <br>
      return '<p>' + blockLines.map(l => renderInlineMarkdown(l)).join('<br>') + '</p>';
    });

    return result.join('\n');
  }

  // ═══ LLM Config Selector ═══
  function setLLMConfigs(configs) {
    llmConfigs = configs || [];
    els.llmSelect.innerHTML = '';

    if (llmConfigs.length === 0) {
      els.llmSelect.disabled = true;
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '等待主程序同步...';
      els.llmSelect.appendChild(opt);
    } else {
      els.llmSelect.disabled = false;
      llmConfigs.forEach((cfg) => {
        const opt = document.createElement('option');
        opt.value = cfg.name;
        opt.textContent = cfg.name + ' (' + cfg.model + ')';
        els.llmSelect.appendChild(opt);
      });
      restoreSelectedLLM();
      // 缓存配置，以便离线或重试时快速恢复
      try { chrome.storage.local.set({ [SELECTED_LLM_CONFIG_KEY]: llmConfigs }); } catch (_) { /* ignore */ }
    }
    updateInputState();
  }

  async function restoreSelectedLLM() {
    try {
      const stored = await chrome.storage.local.get(SELECTED_LLM_KEY);
      const lastName = stored[SELECTED_LLM_KEY];
      if (lastName && Array.from(els.llmSelect.options).some((o) => o.value === lastName)) {
        els.llmSelect.value = lastName;
      } else if (els.llmSelect.options.length > 0) {
        els.llmSelect.selectedIndex = 0;
      }
    } catch (e) {
      if (els.llmSelect.options.length > 0) {
        els.llmSelect.selectedIndex = 0;
      }
    }

    await persistSelectedLLMConfig();
  }

  function saveSelectedLLM(name) {
    try {
      chrome.storage.local.set({ [SELECTED_LLM_KEY]: name || '' });
    } catch (e) { /* ignore */ }
  }

  function getSelectedConfigName() {
    return els.llmSelect.value || '';
  }

  function getSelectedLLMConfig() {
    const selectedName = getSelectedConfigName();
    return llmConfigs.find((cfg) => cfg.name === selectedName) || null;
  }

  async function persistSelectedLLMConfig(config = getSelectedLLMConfig()) {
    const name = config?.name || getSelectedConfigName() || '';
    try {
      await chrome.storage.local.set({
        [SELECTED_LLM_KEY]: name,
        [SELECTED_LLM_CONFIG_KEY]: config || null,
      });
    } catch (e) { /* ignore */ }

    try {
      await chrome.runtime.sendMessage({
        type: 'networkbridge_selected_llm',
        name,
        config: config || null,
      });
    } catch (e) { /* ignore */ }
  }

  function hasConfigSelected() {
    return llmConfigs.length > 0 && getSelectedConfigName() !== '';
  }

  // ═══ Status ═══
  let _wsEverConnected = false; // 防止 HTTP 轮询覆盖 WebSocket 消息确认的状态

  function updateWsStatus(connected, source) {
    // source === 'message' 表示来自 WebSocket 消息（最高优先级）
    // source === 'http' 表示来自 HTTP checkBackend 轮询
    if (source === 'http' && _wsEverConnected) {
      // HTTP 轮询数据可能过期，如果 WebSocket 曾经连上过就不再降级
      return;
    }
    isWsConnected = connected;
    if (connected) {
      _wsEverConnected = true;
      els.connectionBadge.classList.add('connected');
      els.statusDot.classList.add('connected');
      els.statusLabel.textContent = '已连接';
      els.wsStatus.textContent = '已连接';
      els.wsStatus.className = 'status-value ok';
    } else if (source === 'message') {
      // 仅当 WebSocket 消息明确断连时才降级
      _wsEverConnected = false;
      els.connectionBadge.classList.remove('connected');
      els.statusDot.classList.remove('connected');
      els.statusLabel.textContent = '离线';
      els.wsStatus.textContent = '未连接';
      els.wsStatus.className = 'status-value err';
    }
    // HTTP 返回 disconnected 且从未连上过：正常降级
    if (!connected && source !== 'message') {
      els.connectionBadge.classList.remove('connected');
      els.statusDot.classList.remove('connected');
      els.statusLabel.textContent = '离线';
      els.wsStatus.textContent = '未连接';
      els.wsStatus.className = 'status-value err';
    }
  }

  let _inputStateRetryTimer = null;

  function updateInputState() {
    if (!isWsConnected) {
      els.input.placeholder = 'WebSocket 未连接...';
      els.input.disabled = true;
      els.sendBtn.disabled = true;
      scheduleInputStateRetry();
    } else if (!hasConfigSelected()) {
      els.input.placeholder = '请在主程序发送一条消息以同步 LLM 配置...';
      els.input.disabled = true;
      els.sendBtn.disabled = true;
      scheduleInputStateRetry();
    } else if (isProcessing) {
      els.input.disabled = true;
      els.sendBtn.disabled = false;
      // 处理中不需要重试，等待流程结束
    } else {
      // 一切就绪，清除重试定时器
      if (_inputStateRetryTimer) { clearTimeout(_inputStateRetryTimer); _inputStateRetryTimer = null; }
      els.input.placeholder = '输入任务，例如：打开百度搜索 Python 教程...';
      els.input.disabled = false;
      els.sendBtn.disabled = !els.input.value.trim();
    }
  }

  function scheduleInputStateRetry() {
    if (_inputStateRetryTimer) return; // 已有等待中的重试
    _inputStateRetryTimer = setTimeout(() => {
      _inputStateRetryTimer = null;
      console.log('[Sigma Panel] 输入未就绪，1 秒后重试检查...');
      updateInputState();
    }, 1000);
  }

  async function checkBackend() {
    try {
      const resp = await fetch(API_BASE + '/api/network-bridge/status');
      const data = await resp.json();
      els.backendStatus.textContent = data.running ? '运行中' : '异常';
      els.backendStatus.className = 'status-value ' + (data.running ? 'ok' : 'err');
      updateWsStatus(Boolean(data.extension_connected), 'http');
    } catch (e) {
      els.backendStatus.textContent = '无法连接';
      els.backendStatus.className = 'status-value err';
    }
  }

  async function updateTabInfo() {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        const url = tab.url || '';
        els.tabInfo.textContent = tab.title || url.slice(0, 40) || '-';
        els.tabInfo.title = url;
      }
    } catch (e) { /* ignore */ }
  }

  let _configRetryTimer = null;

  async function fetchLLMConfigs() {
    try {
      const resp = await fetch(API_BASE + '/api/network-bridge/llm-configs');
      const data = await resp.json();
      if (data.configs && data.configs.length > 0) {
        setLLMConfigs(data.configs);
        if (_configRetryTimer) { clearTimeout(_configRetryTimer); _configRetryTimer = null; }
      } else {
        await tryRestoreCachedConfigs();
        scheduleConfigRetry();
      }
    } catch (e) {
      await tryRestoreCachedConfigs();
      scheduleConfigRetry();
    }
  }

  async function tryRestoreCachedConfigs() {
    if (llmConfigs.length > 0) return; // 已有配置，无需恢复
    try {
      const cached = await chrome.storage.local.get(SELECTED_LLM_CONFIG_KEY);
      if (cached[SELECTED_LLM_CONFIG_KEY]?.length > 0) {
        console.log('[Sigma Panel] 使用缓存的 LLM 配置');
        setLLMConfigs(cached[SELECTED_LLM_CONFIG_KEY]);
      }
    } catch (_) { /* ignore */ }
  }

  function scheduleConfigRetry() {
    if (_configRetryTimer) return;
    _configRetryTimer = setTimeout(() => {
      _configRetryTimer = null;
      console.log('[Sigma Panel] 配置为空，5 秒后重试...');
      fetchLLMConfigs();
    }, 5000);
  }

  async function refreshAll() {
    await Promise.all([checkBackend(), updateTabInfo(), fetchLLMConfigs()]);
    updateInputState();
  }

  // ═══ Chat (streaming via fetch) ═══
  function showThinking() {
    removeEmptyState();
    const el = document.getElementById('thinking-indicator');
    if (el) return;
    const div = document.createElement('div');
    div.className = 'thinking-indicator';
    div.id = 'thinking-indicator';
    div.innerHTML = '<span class="spinner"></span>Sigma 思考中...';
    els.messages.appendChild(div);
    scrollToBottom();
  }

  function hideThinking() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
  }

  function ensureThinkingBubble() {
    if (thinkingBubble) return;
    thinkingBubble = appendMessage('思考：', 'info thinking');
  }

  function appendThinkingChunk(text) {
    ensureThinkingBubble();
    thinkingText += text;
    // 合并连续空白，避免逐 token 分行；英文 token 之间通常已有空格
    const normalized = thinkingText.replace(/\s+/g, ' ').trim();
    const display = normalized.slice(0, 400) + (normalized.length > 400 ? '…' : '');
    thinkingBubble.textContent = '思考：' + display;
    scrollToBottom();
  }

  function resetThinking() {
    thinkingBubble = null;
    thinkingText = '';
  }

  function ensureStreamingBubble() {
    if (streamingBubble) return;
    streamingBubble = document.createElement('div');
    streamingBubble.className = 'streaming-bubble';
    els.messages.appendChild(streamingBubble);
    scrollToBottom();
  }

  function appendStreamChunk(text) {
    ensureStreamingBubble();
    streamText += text;
    streamingBubble.innerHTML = escapeHtml(streamText) + '<span class="stream-cursor"></span>';
    scrollToBottom();
  }

  function finalizeStream() {
    if (!streamingBubble) return '';
    streamingBubble.querySelector('.stream-cursor')?.remove();
    const text = streamText;
    streamingBubble.remove();
    streamingBubble = null;
    streamText = '';
    return text;
  }

  function setProcessing(processing) {
    isProcessing = processing;
    els.sendBtn.classList.toggle('stop-mode', processing);
    els.sendBtn.disabled = processing ? false : !els.input.value.trim();
    els.input.disabled = processing || !isWsConnected;
    if (processing) showThinking();
  }

  function finishProcessing() {
    isProcessing = false;
    els.sendBtn.classList.remove('stop-mode');
    abortController = null;
    updateInputState();
  }

  async function stopCurrentTask() {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    if (!isProcessing) return;
    try {
      await fetch(API_BASE + '/api/stop-task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID }),
      });
    } catch (e) { /* ignore */ }
  }

  async function sendMessage() {
    if (isProcessing) {
      await stopCurrentTask();
      return;
    }

    const configName = getSelectedConfigName();
    if (!hasConfigSelected()) {
      appendMessage('请先在主程序发送一条消息以同步 LLM 配置', 'error');
      return;
    }

    const text = els.input.value.trim();
    if (!text || !isWsConnected) return;

    streamingBubble = null;
    streamText = '';
    resetThinking();

    appendMessage(text, 'user');
    els.input.value = '';
    setProcessing(true);

    abortController = new AbortController();

    // 获取当前标签页上下文
    let tabUrl = '';
    let tabTitle = '';
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      tabUrl = tab?.url || '';
      tabTitle = tab?.title || '';
    } catch (e) { /* ignore */ }

    const body = {
      message: text,
      session_id: SESSION_ID,
      // 只传配置名，服务端有完整 apiKey
      configName: configName,
      tabUrl,
      tabTitle,
    };

    try {
      const resp = await fetch(API_BASE + '/api/panel-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: abortController.signal,
      });

      if (!resp.ok) {
        throw new Error('HTTP ' + resp.status + ': ' + (await resp.text()).slice(0, 200));
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              handleStreamEvent(event);
            } catch (e) { /* skip */ }
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        hideThinking();
        resetThinking();
        finalizeStream();
        appendMessage('任务已停止', 'info');
      } else {
        hideThinking();
        resetThinking();
        finalizeStream();
        appendMessage('错误: ' + e.message, 'error');
      }
    } finally {
      finishProcessing();
    }
  }

  function handleStreamEvent(data) {
    const type = data?.type;
    if (!type) return;

    switch (type) {
      case 'started':
        break;

      // LLM 文本/思考流式输出
      case 'text':
        if (data.contentType === 'thinking') {
          appendThinkingChunk(data.content || '');
        } else {
          // 正式回复开始，锁定思考气泡
          if (thinkingBubble) resetThinking();
          appendStreamChunk(data.content || '');
        }
        break;

      case 'tool_start':
        // network_bridge: 显示 task 委托描述或 action 列表
        if (data.tool_name === 'network_bridge') {
          if (data.tool_input?.task) {
            appendMessage('浏览器委托任务: ' + data.tool_input.task, 'info');
          } else if (data.tool_input?.actions) {
            const actions = data.tool_input.actions;
            appendMessage(
              '浏览器操作 (' + actions.length + ' 步):\n' +
              actions.map((a, i) => '  ' + (i + 1) + '. ' + a.action + (a.url ? ' ' + a.url : a.ref ? ' ' + a.ref : '')).join('\n'),
              'info'
            );
          } else {
            appendMessage('调用工具: ' + (data.tool_name || ''), 'info');
          }
        } else {
          appendMessage('调用工具: ' + (data.tool_name || ''), 'info');
        }
        break;

      case 'tool_result':
        // 显示工具执行结果摘要
        if (data.tool_name === 'network_bridge' && data.content) {
          try {
            const parsed = typeof data.content === 'string' ? JSON.parse(data.content) : data.content;
            const done = parsed.completed || 0;
            const total = parsed.total || 0;
            appendMessage('浏览器操作完成: ' + done + '/' + total + (data.success ? '' : ' (部分失败)'), data.success ? 'info' : 'error');
          } catch (e) {
            appendMessage('操作完成' + (data.success ? '' : ' (失败)'), data.success ? 'info' : 'error');
          }
        }
        break;

      case 'thinking':
        break;

      case 'chat_complete':
        hideThinking();
        resetThinking();
        const streamed = finalizeStream();
        if (streamed) {
          const html = renderMarkdown(streamed);
          appendMessage(html, 'assistant', { html: true });
        }
        break;

      case 'error':
      case 'fatal_error':
        hideThinking();
        resetThinking();
        finalizeStream();
        appendMessage(data.message || '未知错误', 'error');
        break;

      case 'todolist_update':
      case 'todolist':
        break;

      case 'compact':
      case 'context_usage':
        break;

      default:
        break;
    }
  }

  // ═══ Bridge Test ═══
  async function testBridge() {
    appendMessage('桥接测试...', 'info');
    els.btnTest.disabled = true;

    try {
      // 1. 检查当前标签页
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('edge://') || tab.url === 'about:blank') {
        appendMessage('当前标签页不支持操作，请先打开一个普通网页（如 baidu.com）', 'error');
        els.btnTest.disabled = false;
        return;
      }

      // 2. 检查后端和扩展连接
      const statusResp = await fetch(API_BASE + '/api/network-bridge/status');
      const status = await statusResp.json();
      if (!status.extension_connected) {
        appendMessage('WebSocket 未连接', 'error');
        els.btnTest.disabled = false;
        await refreshAll();
        return;
      }
      appendMessage('WebSocket 已连接', 'ok');

      // 3. 发送测试命令
      appendMessage('发送 get_page_title...', 'info');
      const cmdResp = await fetch(API_BASE + '/api/network-bridge/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'get_page_title', args: {} }),
      });
      const cmd = await cmdResp.json();

      if (cmd.success) {
        const title = cmd.data?.title || cmd.data?.data?.title || cmd.data?.data?.data?.title || '';
        appendMessage('桥接通过！页面: ' + (title || '(无标题)'), 'ok');
      } else {
        const errMsg = cmd.error || '未知错误';
        appendMessage('命令执行失败: ' + errMsg, 'error');
        if (errMsg.includes('Could not establish') || errMsg.includes('Receiving end')) {
          appendMessage('提示：请刷新当前页面后重试（扩展刚加载，旧页面 content script 未激活）', 'info');
        }
      }
    } catch (e) {
      appendMessage('请求异常: ' + e.message, 'error');
    }

    els.btnTest.disabled = false;
    await refreshAll();
  }

  // ═══ Element Inspect ═══
  async function getActiveTabId() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab?.id;
  }

  async function inspectElements() {
    const tabId = await getActiveTabId();
    if (!tabId) return;
    try {
      await chrome.tabs.sendMessage(tabId, { action: 'inspect_all_elements', params: { maxElements: 200 } });
      els.inspectBtn.style.display = 'none';
      els.stopBtn.style.display = '';
    } catch (e) {
      appendMessage('无法显示选框（刷新页面后重试）', 'error');
    }
  }

  async function clearInspect() {
    const tabId = await getActiveTabId();
    if (!tabId) return;
    try { await chrome.tabs.sendMessage(tabId, { action: 'clear_inspect', params: {} }); } catch (e) {}
    els.inspectBtn.style.display = '';
    els.stopBtn.style.display = 'none';
  }

  // ═══ Events ═══
  function bindEvents() {
    els.sendBtn.addEventListener('click', sendMessage);
    els.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    els.input.addEventListener('input', () => {
      els.sendBtn.disabled = isProcessing ? false : !els.input.value.trim();
    });

    els.llmSelect.addEventListener('change', () => {
      const config = getSelectedLLMConfig();
      saveSelectedLLM(config?.name || els.llmSelect.value);
      persistSelectedLLMConfig(config);
      updateInputState();
    });

    els.btnTest.addEventListener('click', testBridge);
    els.inspectBtn.addEventListener('click', inspectElements);
    els.stopBtn.addEventListener('click', clearInspect);

    chrome.runtime.onMessage.addListener((message) => {
      if (message?.type === 'llm_configs') {
        console.log('[Sigma Panel] 收到 LLM 配置:', message.configs?.length, '个');
        setLLMConfigs(message.configs);
      }
      if (message?.type === 'connection_status') {
        updateWsStatus(Boolean(message.connected), 'message');
        updateInputState();
      }
    });

    chrome.tabs.onActivated?.addListener(() => updateTabInfo());
    chrome.tabs.onUpdated?.addListener((tabId, info) => {
      if (info.status === 'complete' || info.title || info.url) updateTabInfo();
    });
  }

  // ═══ Init ═══
  async function init() {
    bindEvents();
    // 立即从缓存恢复配置，避免等待 HTTP/WebSocket
    await tryRestoreCachedConfigs();
    await requestCachedConfigsFromBG();
    await refreshAll();
    setInterval(refreshAll, 10000);
    console.log('[Sigma Panel] 初始化完成');
  }

  async function requestCachedConfigsFromBG() {
    if (llmConfigs.length > 0) return;
    try {
      const resp = await chrome.runtime.sendMessage({ type: 'get_llm_configs' });
      if (resp?.configs?.length > 0) {
        console.log('[Sigma Panel] 从后台缓存恢复 LLM 配置:', resp.configs.length);
        setLLMConfigs(resp.configs);
      }
    } catch (_) { /* ignore */ }
  }

  init();
})();
