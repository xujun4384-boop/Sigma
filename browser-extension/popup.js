const dot = document.getElementById('dot');
const statusText = document.getElementById('statusText');
const logEl = document.getElementById('log');

function setConnected(connected) {
  dot.classList.toggle('connected', connected);
  statusText.textContent = connected ? '已连接到 Sigma' : '未连接';
}

function appendLog(text) {
  logEl.textContent += text + '\n';
  logEl.scrollTop = logEl.scrollHeight;
}

async function refreshStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ type: 'get_status' });
    setConnected(status.connected);
    appendLog(`状态: ${status.connected ? '已连接' : '未连接'}`);
  } catch (e) {
    setConnected(false);
    appendLog(`获取状态失败: ${e.message}`);
  }
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'connection_status') {
    setConnected(msg.connected);
  }
});

document.getElementById('btnReconnect').addEventListener('click', async () => {
  appendLog('正在重新连接...');
  try {
    await chrome.runtime.sendMessage({ type: 'reconnect' });
    appendLog('已发送重新连接请求');
  } catch (e) {
    appendLog(`重新连接失败: ${e.message}`);
  }
  setTimeout(refreshStatus, 1500);
});

document.getElementById('btnTest').addEventListener('click', async () => {
  appendLog('请使用 Sigma WebSocket 服务器发送命令测试');
});

refreshStatus();
