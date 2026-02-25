/**
 * S27: 前端 UX 增强 — 会话重命名 + 代码块复制 + 主题切换
 * 独立文件，不修改 console.js（规则 03 行数限制）
 */

// === 1. 代码块一键复制 ===
function addCopyButtons() {
    document.querySelectorAll('#messages pre code').forEach(block => {
        if (block.parentElement.querySelector('.copy-btn')) return;
        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.textContent = '复制';
        btn.addEventListener('click', () => {
            navigator.clipboard.writeText(block.textContent).then(() => {
                btn.textContent = '✅ 已复制';
                setTimeout(() => btn.textContent = '复制', 1500);
            });
        });
        block.parentElement.style.position = 'relative';
        block.parentElement.appendChild(btn);
    });
}

// 监听消息区变化，自动添加复制按钮
const msgObserver = new MutationObserver(() => addCopyButtons());
const messagesContainer = document.getElementById('messages');
if (messagesContainer) msgObserver.observe(messagesContainer, { childList: true, subtree: true });

// === 2. 会话重命名（双击标题编辑） ===
document.addEventListener('dblclick', (e) => {
    const titleEl = e.target.closest('.session-item .title');
    if (!titleEl) return;
    const item = titleEl.closest('.session-item');
    const sid = item?.dataset?.sid;
    if (!sid || sid === 'default') return;

    const oldTitle = titleEl.textContent;
    const input = document.createElement('input');
    input.type = 'text';
    input.value = oldTitle;
    input.className = 'rename-input';
    input.style.cssText = 'width:100%;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--accent);padding:2px 4px;font-size:12px;';
    titleEl.replaceWith(input);
    input.focus();
    input.select();

    const save = async () => {
        const newTitle = input.value.trim() || oldTitle;
        const span = document.createElement('span');
        span.className = 'title';
        span.textContent = newTitle;
        input.replaceWith(span);
        if (newTitle !== oldTitle) {
            try {
                await fetch(`/api/sessions/${sid}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle })
                });
            } catch (err) { console.error('重命名失败:', err); }
        }
    };
    input.addEventListener('blur', save);
    input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') save(); if (ev.key === 'Escape') { input.value = oldTitle; save(); } });
});

// === 3. 主题切换（亮色/暗色） ===
const themeKey = 'lucidmind-theme';
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(themeKey, theme);
}
function toggleTheme() {
    const current = localStorage.getItem(themeKey) || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}
// 初始化主题
applyTheme(localStorage.getItem(themeKey) || 'dark');

// 添加主题切换按钮到活动栏
const activityBar = document.querySelector('.activity-bar');
if (activityBar) {
    const themeBtn = document.createElement('div');
    themeBtn.className = 'activity-item';
    themeBtn.innerHTML = '🌓';
    themeBtn.title = '切换主题';
    themeBtn.style.cssText = 'cursor:pointer;margin-top:auto;padding:12px;text-align:center;font-size:18px;';
    themeBtn.addEventListener('click', toggleTheme);
    activityBar.appendChild(themeBtn);
}

// === 4. 消息复制按钮 ===
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('msg-copy-btn')) {
        const msg = e.target.closest('.message');
        if (msg) {
            navigator.clipboard.writeText(msg.textContent.replace('复制', '').trim()).then(() => {
                e.target.textContent = '✅';
                setTimeout(() => e.target.textContent = '📋', 1500);
            });
        }
    }
});

// 为每条助手消息添加复制按钮
const msgCopyObserver = new MutationObserver((muts) => {
    for (const m of muts) for (const n of m.addedNodes) {
        if (n.classList && n.classList.contains('message') && n.classList.contains('assistant') && !n.classList.contains('typing-indicator')) {
            if (!n.querySelector('.msg-copy-btn')) {
                const btn = document.createElement('span');
                btn.className = 'msg-copy-btn';
                btn.textContent = '📋';
                btn.title = '复制消息';
                n.style.position = 'relative';
                n.appendChild(btn);
            }
        }
    }
});
if (messagesContainer) msgCopyObserver.observe(messagesContainer, { childList: true });

// === 4. 页面刷新后加载聊天历史 ===
async function loadChatHistory() {
    const sid = localStorage.getItem('lucid_session') || 'default';
    const msgEl = document.getElementById('messages');
    if (!msgEl) return;
    try {
        const res = await fetch(`${location.origin}/api/sessions/${sid}/history`);
        const data = await res.json();
        if (!data.messages || data.messages.length === 0) return;
        // 只在消息区为空时加载（避免重复）
        if (msgEl.querySelectorAll('.message').length > 0) return;
        for (const msg of data.messages) {
            const role = msg.role || 'system';
            if (role === 'system') continue;
            const div = document.createElement('div');
            div.className = `message ${role === 'assistant' ? 'assistant' : 'user'}`;
            if (role === 'assistant' && typeof marked !== 'undefined') {
                div.innerHTML = marked.parse(msg.content || '');
            } else {
                div.textContent = msg.content || '';
            }
            msgEl.appendChild(div);
        }
        msgEl.scrollTop = msgEl.scrollHeight;
    } catch (e) { console.warn('Load history failed:', e); }
}
// 页面加载后延迟加载历史（等 WebSocket 连接后）
setTimeout(loadChatHistory, 1000);
