/**
 * LucidMind IDE Console
 */

// === DOM Elements ===
const activityItems = document.querySelectorAll('.activity-item[data-tab]');
const sidebarViews = document.querySelectorAll('.sidebar-view');
const messagesEl = document.getElementById('messages');
const inputForm = document.getElementById('input-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusIndicator = document.getElementById('status-indicator');
const modelBadge = document.getElementById('model-badge');
const thinkingToggle = document.getElementById('thinking-toggle');
const devToggleBtn = document.getElementById('dev-toggle-btn');
const rightPanel = document.getElementById('right-panel');
const miniLog = document.getElementById('mini-log');

// Config Elements
const modelSelect = document.getElementById('model-select');
const apiKeyInput = document.getElementById('api-key-input');
const testConnBtn = document.getElementById('test-conn-btn');
const connStatus = document.getElementById('conn-status');

// Memory Elements
const refreshMemoryBtn = document.getElementById('refresh-memory-btn');
const memoryList = document.getElementById('memory-list');
const lessonsList = document.getElementById('lessons-list');
const lessonCount = document.getElementById('lesson-count');

// S49: Auth Guard — 未登录跳转登录页
const authToken = localStorage.getItem('lucidmind_token');
if (!authToken) { window.location.href = '/login'; }
// S51: 解析JWT显示用户名 + 过期检测
try { const p = JSON.parse(atob(authToken.split('.')[1])); document.getElementById('user-badge').textContent = p.user_id || '--'; if (p.exp && p.exp * 1000 < Date.now()) { localStorage.removeItem('lucidmind_token'); window.location.href = '/login'; } } catch(e) {}
document.getElementById('logout-btn').addEventListener('click', () => { localStorage.removeItem('lucidmind_token'); window.location.href = '/login'; });

// State
let ws = null;
let heartbeatTimer = null;
let heartbeatTimeout = null;
let messageQueue = [];
let isProcessing = false;
let currentThinkingBox = null;
let streamingMsgEl = null;
let streamingBuffer = '';
let welcomeRemoved = false;
let currentSessionId = localStorage.getItem('lucid_session') || 'default';
let thinkingVisible = localStorage.getItem('lucid_thinking') !== 'false';
let devPanelVisible = localStorage.getItem('lucid_dev_panel') !== 'false';

// === Layout Logic ===

// Activity Bar Switching
activityItems.forEach(item => {
    item.addEventListener('click', () => {
        // Remove active class from all items
        activityItems.forEach(i => i.classList.remove('active'));
        // Add active class to clicked
        item.classList.add('active');
        
        // Switch Sidebar View
        const targetViewId = `view-${item.dataset.tab}`;
        sidebarViews.forEach(view => {
            if (view.id === targetViewId) {
                view.classList.remove('hidden');
            } else {
                view.classList.add('hidden');
            }
        });
    });
});

// Dev Panel Toggle
function updateDevPanel() {
    if (devPanelVisible) {
        rightPanel.classList.remove('collapsed');
        devToggleBtn.classList.add('active');
    } else {
        rightPanel.classList.add('collapsed');
        devToggleBtn.classList.remove('active');
    }
}

devToggleBtn.addEventListener('click', () => {
    devPanelVisible = !devPanelVisible;
    localStorage.setItem('lucid_dev_panel', devPanelVisible);
    updateDevPanel();
});
updateDevPanel();

// Thinking Toggle
function updateThinkingVisibility() { thinkingToggle.classList.toggle('on', thinkingVisible); document.querySelectorAll('.thinking-box').forEach(box => { box.style.display = thinkingVisible ? 'block' : 'none'; }); }
let allExpanded = true;
document.getElementById('expand-all-thinking')?.addEventListener('click', () => { allExpanded = !allExpanded; document.querySelectorAll('.thinking-box').forEach(b => { allExpanded ? b.classList.remove('collapsed') : b.classList.add('collapsed'); }); });
thinkingToggle.addEventListener('click', () => { thinkingVisible = !thinkingVisible; localStorage.setItem('lucid_thinking', thinkingVisible); updateThinkingVisibility(); });
updateThinkingVisibility();

// === Chat Logic ===

function logEvent(type, msg) {
    const time = new Date().toLocaleTimeString();
    const line = document.createElement('div');
    line.style.borderBottom = '1px solid #333';
    line.style.padding = '2px 0';
    line.innerHTML = `<span style="color:#569cd6">[${time}]</span> <span style="color:#dcdcaa">${type}</span> ${msg}`;
    miniLog.prepend(line);
}

function scrollToBottom() {
    // messagesEl.parentElement is #chat-container
    const container = document.getElementById('chat-container');
    container.scrollTop = container.scrollHeight;
}

function removeWelcome() {
    if (!welcomeRemoved) {
        const welcome = document.querySelector('.welcome-msg');
        if (welcome) welcome.remove();
        welcomeRemoved = true;
    }
}

function addMessage(text, role) {
    removeWelcome();
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (role === 'assistant' && typeof marked !== 'undefined') {
        div.innerHTML = marked.parse(text);
    } else {
        div.textContent = text;
    }
    messagesEl.appendChild(div);
    scrollToBottom();
    logEvent('chat', `${role}: ${text.substring(0, 20)}...`);
}

function showThinking(text) {
    removeWelcome();
    const box = document.createElement('div');
    box.className = 'thinking-box';
    if (!thinkingVisible) box.style.display = 'none';
    
    box.innerHTML = `
        <div class="thinking-header">
            <span>⚡ Thinking Process</span>
        </div>
        <div class="thinking-body">${text}</div>
    `;
    
    // Toggle collapse
    box.querySelector('.thinking-header').addEventListener('click', () => {
        box.classList.toggle('collapsed');
    });

    messagesEl.appendChild(box);
    currentThinkingBox = box;
    scrollToBottom();
    logEvent('think', 'Started thinking...');
}

function showToolUse(toolName, args) {
    const card = document.createElement('div');
    card.className = 'tool-card';
    card.innerHTML = `<div>> Tool: <strong>${toolName}</strong></div><div style="color:#858585">${args}</div>`;
    messagesEl.appendChild(card);
    scrollToBottom();
    logEvent('tool', `Call: ${toolName}`);
}

function showToolResult(result) {
    const card = document.createElement('div');
    card.className = 'tool-card';
    card.style.borderLeft = '2px solid #89d185';
    card.innerHTML = `<div>< Result:</div><div style="color:#cccccc">${result}</div>`;
    messagesEl.appendChild(card);
    scrollToBottom();
    logEvent('tool', 'Result received');
}

// === WebSocket ===

function setOnline(isOnline) {
    if (isOnline) {
        statusIndicator.className = 'status-pill online';
        statusIndicator.textContent = 'ONLINE';
    } else {
        statusIndicator.className = 'status-pill offline';
        statusIndicator.textContent = 'OFFLINE';
    }
}

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws?token=${encodeURIComponent(authToken || '')}`);

    ws.onopen = () => {
        setOnline(true);
        logEvent('sys', 'WebSocket Connected');
        isProcessing = false; // S59: 新连接重置处理状态
        processQueue(); // S59: 处理排队中的消息
        fetchStatus();
        startHeartbeat();
    };

    ws.onclose = () => {
        setOnline(false);
        stopHeartbeat();
        logEvent('sys', 'WebSocket Disconnected');
        // S59: 断线时清理状态，让重连后能继续处理
        document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
        isProcessing = false;
        setTimeout(connect, 3000);
    };

    ws.onmessage = (evt) => {
        const data = JSON.parse(evt.data);
        
        switch (data.type) {
            case 'thinking':
                document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
                showThinking(data.data);
                break;
            case 'plan_confirm': {
                const cb = document.getElementById('brain-confirm-bar');
                if (cb) { cb.classList.remove('hidden'); const t = document.getElementById('brain-confirm-text'); if (t) t.textContent = '大脑自检完成，等待确认执行'; }
                break; }
            case 'tool_call':
                showToolUse('Command', data.data);
                break;
            case 'tool_result':
                showToolResult(data.data);
                break;
            case 'response_start':
                document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
                if (currentThinkingBox) { currentThinkingBox.classList.add('done'); currentThinkingBox = null; }
                removeWelcome();
                streamingBuffer = '';
                streamingMsgEl = document.createElement('div');
                streamingMsgEl.className = 'message assistant streaming';
                messagesEl.appendChild(streamingMsgEl);
                scrollToBottom();
                logEvent('stream', 'Streaming started');
                break;
            case 'response_delta':
                if (streamingMsgEl && data.data) {
                    streamingBuffer += data.data;
                    streamingMsgEl.textContent = streamingBuffer;
                    scrollToBottom();
                }
                break;
            case 'response_end':
                if (streamingMsgEl && streamingBuffer) {
                    if (typeof marked !== 'undefined') {
                        streamingMsgEl.innerHTML = marked.parse(streamingBuffer);
                    }
                    streamingMsgEl.classList.remove('streaming');
                    logEvent('stream', 'Streaming complete');
                }
                streamingMsgEl = null;
                streamingBuffer = '';
                break;
            case 'response':
                document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
                if (currentThinkingBox) { currentThinkingBox.classList.add('done'); currentThinkingBox = null; }
                addMessage(data.data, 'assistant');
                break;
            case 'error':
                document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
                if (currentThinkingBox) { currentThinkingBox.classList.add('done'); currentThinkingBox = null; }
                addMessage(`Error: ${data.data}`, 'error');
                isProcessing = false;
                processQueue();
                userInput.disabled = false;
                sendBtn.disabled = false;
                break;
            case 'pong':
                clearTimeout(heartbeatTimeout);
                break;
            case 'complete':
                document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
                isProcessing = false;
                processQueue();
                userInput.disabled = false;
                sendBtn.disabled = false;
                userInput.focus();
                break;
        }
    };
}

function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
            heartbeatTimeout = setTimeout(() => {
                logEvent('warn', 'Heartbeat timeout, reconnecting...');
                ws.close();
            }, 60000);
        }
    }, 30000);
}

function stopHeartbeat() {
    clearInterval(heartbeatTimer);
    clearTimeout(heartbeatTimeout);
}

function enqueueMessage(msg) {
    messageQueue.push(msg);
    processQueue();
}

function processQueue() {
    if (isProcessing || messageQueue.length === 0) return;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    isProcessing = true;
    const msg = messageQueue.shift();
    ws.send(JSON.stringify(msg));
}

// === API & Config ===

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        document.getElementById('dev-llm-status').textContent = 
            data.llm.available ? 'Ready' : 'Not Connected';
            
        document.getElementById('dev-tool-status').textContent = 
            `${data.tools.length} Tools Loaded`;
            
        document.getElementById('dev-tool-list').textContent = 
            data.tools.join(', ');
            
        document.getElementById('dev-memory-status').textContent = 
            data.ports.memory ? 'Active' : 'Inactive';
        document.getElementById('dev-learning-status').textContent = 
            data.ports.learning ? 'Active' : 'Inactive';
        // Update header model badge
        modelBadge.textContent = data.llm.model || '--';
        modelBadge.title = `Provider: ${data.llm.provider || 'unknown'}`;
            
    } catch (e) {
        console.error(e);
    }
}

// Config Test Button
testConnBtn.addEventListener('click', async () => {
    const provider = modelSelect.value, apiKey = apiKeyInput.value.trim();
    if (!apiKey && provider !== 'local') { connStatus.textContent = 'Key Required ❌'; connStatus.style.color = '#f48771'; return; }
    connStatus.textContent = 'Verifying...'; connStatus.style.color = '#cca700'; testConnBtn.disabled = true;
    try {
        const res = await fetch('/api/verify', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({provider, api_key: apiKey}) });
        const data = await res.json();
        if (data.status === 'ok') { connStatus.textContent = 'Connected ✅'; connStatus.style.color = '#89d185'; logEvent('conf', `Switched to ${provider}`); fetchStatus(); }
        else { connStatus.textContent = 'Failed ❌'; connStatus.style.color = '#f48771'; }
    } catch (e) { connStatus.textContent = 'Error ❌'; connStatus.style.color = '#f48771'; }
    finally { testConnBtn.disabled = false; }
});

// File Upload
const fileUpload = document.getElementById('file-upload');
const uploadBtn = document.getElementById('upload-btn');
uploadBtn.addEventListener('click', () => fileUpload.click());
fileUpload.addEventListener('change', async () => {
    for (const file of fileUpload.files) {
        const form = new FormData();
        form.append('file', file);
        try {
            const res = await fetch('/api/upload', { method: 'POST', body: form });
            const data = await res.json();
            if (res.ok) {
                addMessage(`📎 已上传: ${data.filename} (${(data.size/1024).toFixed(1)}KB)`, 'user');
                enqueueMessage({ type: 'chat', message: `我上传了文件 ${data.filename}，路径是 ${data.path}，请分析这个文件。` });
                logEvent('sys', `Upload: ${data.filename}`);
            } else {
                addMessage(`上传失败: ${data.detail || '未知错误'}`, 'error');
            }
        } catch (e) { addMessage(`上传错误: ${e.message}`, 'error'); }
    }
    fileUpload.value = '';
});

// Input Handling — S59: 排队模式，AI回复期间仍可输入
inputForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = userInput.value.trim();
    if (!text) return;
    addMessage(text, 'user');
    enqueueMessage({ type: 'chat', message: text, session_id: currentSessionId });
    userInput.value = '';
    if (!isProcessing) {
        // S23: typing 指示（仅首条消息）
        const typing = document.createElement('div'); typing.className = 'message assistant typing-indicator'; typing.innerHTML = '<span>●</span><span>●</span><span>●</span>';
        messagesEl.appendChild(typing); scrollToBottom();
    }
    userInput.focus();
});

// === Memory & Lessons Visualization ===

async function fetchMemory() {
    try {
        const res = await fetch(`/api/memory/${currentSessionId}`);
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
            memoryList.innerHTML = data.messages.slice(-10).map(m => 
                `<div class="memory-item ${m.role}"><span class="role">${m.role === 'user' ? '🧑' : '🤖'}</span> ${(m.content || '').substring(0, 80)}${(m.content || '').length > 80 ? '...' : ''}</div>`
            ).join('');
        } else {
            memoryList.innerHTML = '<div class="memory-empty">无记忆</div>';
        }
    } catch (e) {
        memoryList.innerHTML = '<div class="memory-empty">加载失败</div>';
    }
}

async function fetchLessons() {
    try {
        const res = await fetch('/api/lessons');
        const data = await res.json();
        lessonCount.textContent = data.count || 0;
        if (data.lessons && data.lessons.length > 0) {
            lessonsList.innerHTML = data.lessons.map(l => 
                `<div class="memory-item lesson"><div class="lesson-trigger">触发: ${(l.trigger || '').substring(0, 60)}</div><div class="lesson-text">教训: ${(l.lesson || '').substring(0, 80)}</div><div class="lesson-meta">效果: ${l.effectiveness != null ? (l.effectiveness * 100).toFixed(0) + '%' : '未验证'} | 应用: ${l.applied_count || 0}次</div></div>`
            ).join('');
        } else {
            lessonsList.innerHTML = '<div class="memory-empty">无经验</div>';
        }
    } catch (e) {
        lessonsList.innerHTML = '<div class="memory-empty">加载失败</div>';
    }
}

refreshMemoryBtn.addEventListener('click', () => {
    fetchMemory();
    fetchLessons();
    logEvent('mem', 'Refreshed memory & lessons');
});

// === S18: Multi-Session ===
const sessionListEl = document.getElementById('session-list');
const newSessionBtn = document.getElementById('new-session-btn');

async function fetchSessions() {
    try {
        const res = await fetch('/api/sessions');
        const data = await res.json();
        sessionListEl.innerHTML = data.sessions.map(s =>
            `<div class="session-item${s.id === currentSessionId ? ' active' : ''}" data-sid="${s.id}"><span class="icon">💬</span><span class="title">${s.title}</span><span class="time">${s.message_count || 0}条</span>${s.id !== 'default' ? '<span class="del-btn" title="删除">×</span>' : ''}</div>`
        ).join('');
        sessionListEl.querySelectorAll('.session-item').forEach(el => {
            el.addEventListener('click', (e) => { if (!e.target.classList.contains('del-btn')) switchSession(el.dataset.sid); });
        });
        sessionListEl.querySelectorAll('.del-btn').forEach(btn => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); deleteSession(btn.closest('.session-item').dataset.sid); });
        });
    } catch (e) { console.error('fetchSessions:', e); }
}

function switchSession(sid) {
    if (sid === currentSessionId) return;
    currentSessionId = sid;
    localStorage.setItem('lucid_session', sid);
    messagesEl.innerHTML = '';
    welcomeRemoved = false;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'switch_session', session_id: sid }));
    fetchSessions();
    logEvent('session', `Switched to ${sid}`);
}

async function deleteSession(sid) {
    if (!confirm(`删除会话 ${sid}？`)) return;
    await fetch(`/api/sessions/${sid}`, { method: 'DELETE' });
    if (currentSessionId === sid) switchSession('default');
    fetchSessions();
}

newSessionBtn.addEventListener('click', async () => {
    const res = await fetch('/api/sessions', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
    const data = await res.json();
    switchSession(data.session.id);
});

if (typeof marked !== 'undefined' && typeof hljs !== 'undefined') { marked.setOptions({ highlight: (code, lang) => { try { return lang ? hljs.highlight(code, {language: lang}).value : hljs.highlightAuto(code).value; } catch(e) { return code; } } }); }
connect(); fetchSessions(); setInterval(fetchStatus, 30000);
