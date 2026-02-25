/**
 * S52-S54: 前端体验升级
 * S52: 对话历史列表增强（预览、时间格式化）
 * S53: 消息搜索 + 对话导出
 * S54: 主题记忆(已在ux_enhance.js) + 移动端适配
 * 独立文件，不修改 console.js（规则 03 行数限制）
 */

// === S52: 对话历史增强 ===
(function initSessionEnhance() {
    const sidebar = document.getElementById('view-chat');
    if (!sidebar) return;

    // 在 session list 上方添加搜索框
    const header = sidebar.querySelector('.sidebar-header');
    if (header && !document.getElementById('session-search')) {
        const searchBox = document.createElement('input');
        searchBox.id = 'session-search';
        searchBox.type = 'text';
        searchBox.placeholder = '搜索会话...';
        searchBox.style.cssText = 'width:100%;padding:4px 8px;margin-top:6px;background:var(--bg-tertiary,#2d2d2d);color:var(--text-primary,#ccc);border:1px solid #444;border-radius:4px;font-size:12px;box-sizing:border-box;';
        header.appendChild(searchBox);

        searchBox.addEventListener('input', () => {
            const q = searchBox.value.toLowerCase();
            document.querySelectorAll('#session-list .session-item').forEach(el => {
                const title = (el.querySelector('.title')?.textContent || '').toLowerCase();
                el.style.display = (!q || title.includes(q)) ? '' : 'none';
            });
        });
    }
})();

// === S53: 消息搜索 + 对话导出 ===
(function initMessageTools() {
    const chatContainer = document.getElementById('chat-container');
    const inputArea = document.getElementById('input-area');
    if (!chatContainer || !inputArea) return;

    // 搜索+导出工具栏
    const toolbar = document.createElement('div');
    toolbar.id = 'msg-toolbar';
    toolbar.style.cssText = 'display:flex;gap:4px;padding:2px 12px;background:var(--bg-secondary,#252526);border-top:1px solid #333;align-items:center;';
    toolbar.innerHTML = `
        <input id="msg-search" type="text" placeholder="搜索消息..." style="flex:1;padding:3px 8px;background:var(--bg-tertiary,#2d2d2d);color:var(--text-primary,#ccc);border:1px solid #444;border-radius:3px;font-size:11px;">
        <button id="msg-search-btn" title="搜索" style="background:none;border:none;color:#569cd6;cursor:pointer;font-size:13px;">&#x1F50D;</button>
        <button id="msg-search-clear" title="清除" style="background:none;border:none;color:#858585;cursor:pointer;font-size:11px;display:none;">&#x2715;</button>
        <span style="color:#444">|</span>
        <button id="export-btn" title="导出对话" style="background:none;border:none;color:#89d185;cursor:pointer;font-size:13px;">&#x1F4BE;</button>
    `;
    inputArea.parentNode.insertBefore(toolbar, inputArea);

    const msgSearch = document.getElementById('msg-search');
    const msgSearchBtn = document.getElementById('msg-search-btn');
    const msgSearchClear = document.getElementById('msg-search-clear');
    const exportBtn = document.getElementById('export-btn');
    const messagesEl = document.getElementById('messages');

    // 搜索高亮
    function doSearch() {
        const q = (msgSearch.value || '').trim().toLowerCase();
        // 清除旧高亮
        messagesEl.querySelectorAll('.search-highlight').forEach(el => {
            el.replaceWith(document.createTextNode(el.textContent));
        });
        if (!q) { msgSearchClear.style.display = 'none'; return; }
        msgSearchClear.style.display = '';
        let firstMatch = null;
        messagesEl.querySelectorAll('.message').forEach(msg => {
            highlightText(msg, q);
            if (!firstMatch && msg.querySelector('.search-highlight')) firstMatch = msg;
        });
        if (firstMatch) firstMatch.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function highlightText(node, query) {
        if (node.nodeType === 3) {
            const idx = node.textContent.toLowerCase().indexOf(query);
            if (idx >= 0) {
                const span = document.createElement('span');
                span.className = 'search-highlight';
                span.style.cssText = 'background:#cca700;color:#000;border-radius:2px;padding:0 1px;';
                span.textContent = node.textContent.substring(idx, idx + query.length);
                const after = node.splitText(idx);
                after.textContent = after.textContent.substring(query.length);
                node.parentNode.insertBefore(span, after);
            }
        } else if (node.nodeType === 1 && !node.classList.contains('search-highlight')) {
            Array.from(node.childNodes).forEach(c => highlightText(c, query));
        }
    }

    msgSearchBtn.addEventListener('click', doSearch);
    msgSearch.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
    msgSearchClear.addEventListener('click', () => {
        msgSearch.value = '';
        doSearch();
    });

    // 导出对话为 Markdown
    exportBtn.addEventListener('click', () => {
        const msgs = messagesEl.querySelectorAll('.message');
        if (!msgs.length) return;
        let md = `# LucidMind 对话导出\n\n导出时间: ${new Date().toLocaleString()}\n\n---\n\n`;
        msgs.forEach(msg => {
            const role = msg.classList.contains('user') ? '**用户**' :
                         msg.classList.contains('assistant') ? '**LucidMind**' : '**系统**';
            md += `${role}: ${msg.textContent.trim()}\n\n`;
        });
        const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `lucidmind_chat_${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
    });
})();

// === S54: 移动端适配 ===
(function initMobileAdapt() {
    // 检测移动端
    const isMobile = window.innerWidth < 768;
    if (!isMobile) return;

    const sidebar = document.getElementById('sidebar');
    const rightPanel = document.getElementById('right-panel');
    const activityBar = document.getElementById('activity-bar');

    // 移动端默认隐藏侧边栏和右侧面板
    if (sidebar) sidebar.style.display = 'none';
    if (rightPanel) { rightPanel.classList.add('collapsed'); rightPanel.style.display = 'none'; }

    // 点击 activity bar 切换侧边栏
    if (activityBar) {
        activityBar.querySelectorAll('.activity-item[data-tab]').forEach(item => {
            item.addEventListener('click', () => {
                if (sidebar) {
                    sidebar.style.display = sidebar.style.display === 'none' ? '' : 'none';
                }
            });
        });
    }

    // 添加移动端样式
    const style = document.createElement('style');
    style.textContent = `
        @media (max-width: 768px) {
            #ide-container { grid-template-columns: 40px 1fr !important; }
            #sidebar { position: absolute; left: 40px; top: 0; bottom: 0; z-index: 100; width: 220px; }
            #right-panel { display: none !important; }
            .editor-header { flex-wrap: wrap; }
            .header-actions { gap: 4px; }
            #input-area .input-wrapper { padding: 4px; }
            #user-input { font-size: 14px; }
        }
    `;
    document.head.appendChild(style);
})();

// === S59: 排队状态指示器 ===
(function initQueueIndicator() {
    const inputArea = document.getElementById('input-area');
    if (!inputArea) return;

    const indicator = document.createElement('div');
    indicator.id = 'queue-indicator';
    indicator.style.cssText = 'display:none;padding:2px 12px;background:#264f78;color:#ccc;font-size:11px;text-align:center;';
    inputArea.parentNode.insertBefore(indicator, inputArea);

    // 监听队列变化
    setInterval(() => {
        if (typeof messageQueue !== 'undefined' && messageQueue.length > 0) {
            indicator.textContent = `📋 ${messageQueue.length} 条消息排队中...`;
            indicator.style.display = '';
        } else {
            indicator.style.display = 'none';
        }
    }, 300);
})();

// === S58: Textarea自适应高度 + IME兼容 + Shift+Enter ===
(function initTextareaEnhance() {
    const ta = document.getElementById('user-input');
    if (!ta || ta.tagName !== 'TEXTAREA') return;

    // 自适应高度
    function autoResize() {
        ta.style.height = 'auto';
        ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
    }
    ta.addEventListener('input', autoResize);

    // Enter发送 + Shift+Enter换行 + IME兼容
    ta.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        if (e.isComposing || e.keyCode === 229) return; // IME输入中，不处理
        if (e.shiftKey) return; // Shift+Enter换行
        e.preventDefault();
        document.getElementById('input-form').dispatchEvent(new Event('submit', {cancelable: true}));
    });

    // 发送后重置高度
    document.getElementById('input-form').addEventListener('submit', () => {
        setTimeout(() => { ta.style.height = 'auto'; }, 50);
    });
})();

// === S58: 停止生成按钮 ===
(function initStopButton() {
    const stopBtn = document.getElementById('stop-btn');
    const sendBtn = document.getElementById('send-btn');
    if (!stopBtn) return;

    // 监听消息状态切换停止/发送按钮
    const observer = new MutationObserver(() => {
        const typing = document.querySelector('.typing-indicator');
        const streaming = document.querySelector('.message.streaming');
        if (typing || streaming) {
            stopBtn.style.display = '';
            sendBtn.style.display = 'none';
        } else {
            stopBtn.style.display = 'none';
            sendBtn.style.display = '';
        }
    });
    const msgs = document.getElementById('messages');
    if (msgs) observer.observe(msgs, { childList: true, subtree: true, attributes: true });

    stopBtn.addEventListener('click', () => {
        // 关闭当前WebSocket连接触发重连（中断流式输出）
        if (typeof ws !== 'undefined' && ws && ws.readyState === WebSocket.OPEN) {
            ws.close();
        }
        document.querySelectorAll('.typing-indicator').forEach(e => e.remove());
        const streaming = document.querySelector('.message.streaming');
        if (streaming) streaming.classList.remove('streaming');
        stopBtn.style.display = 'none';
        sendBtn.style.display = '';
    });
})();

// === S58: 新消息提示按钮 ===
(function initNewMessageIndicator() {
    const container = document.getElementById('chat-container');
    if (!container) return;

    const btn = document.createElement('button');
    btn.id = 'new-msg-btn';
    btn.textContent = '↓ 新消息';
    btn.style.cssText = 'display:none;position:absolute;bottom:80px;left:50%;transform:translateX(-50%);background:var(--accent,#0e639c);color:#fff;border:none;padding:6px 16px;border-radius:16px;cursor:pointer;font-size:12px;z-index:50;box-shadow:0 2px 8px rgba(0,0,0,0.3);';
    container.parentElement.style.position = 'relative';
    container.parentElement.appendChild(btn);

    let userNearBottom = true;
    container.addEventListener('scroll', () => {
        const threshold = 100;
        userNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold;
        if (userNearBottom) btn.style.display = 'none';
    });

    const msgObserver = new MutationObserver(() => {
        if (!userNearBottom) btn.style.display = '';
    });
    const msgs = document.getElementById('messages');
    if (msgs) msgObserver.observe(msgs, { childList: true });

    btn.addEventListener('click', () => {
        container.scrollTop = container.scrollHeight;
        btn.style.display = 'none';
    });
})();

// === S58: 图片粘贴上传 ===
(function initPasteUpload() {
    const ta = document.getElementById('user-input');
    if (!ta) return;

    ta.addEventListener('paste', async (e) => {
        const items = e.clipboardData?.items;
        if (!items) return;
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.startsWith('image/')) {
                e.preventDefault();
                const file = items[i].getAsFile();
                if (!file) continue;
                const form = new FormData();
                form.append('file', file, 'paste_' + Date.now() + '.png');
                try {
                    const res = await fetch('/api/upload', { method: 'POST', body: form });
                    const data = await res.json();
                    if (res.ok && typeof addMessage === 'function') {
                        addMessage('📎 粘贴图片: ' + data.filename, 'user');
                        if (typeof enqueueMessage === 'function') {
                            enqueueMessage({ type: 'chat', message: '我粘贴了图片 ' + data.filename + '，路径是 ' + data.path + '，请分析。', session_id: typeof currentSessionId !== 'undefined' ? currentSessionId : 'default' });
                        }
                    }
                } catch (err) { console.error('粘贴上传失败:', err); }
                return;
            }
        }
    });
})();

// === S58: 断线重连醒目提示 ===
(function initReconnectBanner() {
    const header = document.querySelector('.editor-header');
    if (!header) return;

    const banner = document.createElement('div');
    banner.id = 'reconnect-banner';
    banner.style.cssText = 'display:none;position:fixed;top:35px;left:0;right:0;background:#f4877180;color:#fff;text-align:center;padding:4px;font-size:12px;z-index:999;';
    banner.textContent = '⚠ 连接已断开，正在重连...';
    document.body.appendChild(banner);

    const indicator = document.getElementById('status-indicator');
    if (indicator) {
        const obs = new MutationObserver(() => {
            banner.style.display = indicator.classList.contains('offline') ? '' : 'none';
        });
        obs.observe(indicator, { attributes: true, attributeFilter: ['class'] });
    }
})();

// === S59: 拖拽上传 ===
(function initDragDropUpload() {
    const chatContainer = document.getElementById('chat-container');
    if (!chatContainer) return;
    const overlay = document.createElement('div');
    overlay.style.cssText = 'display:none;position:absolute;inset:0;background:rgba(14,99,156,0.3);border:2px dashed var(--accent);z-index:100;pointer-events:none;display:none;align-items:center;justify-content:center;font-size:16px;color:#fff;';
    overlay.textContent = '📎 拖拽文件到此处上传';
    chatContainer.parentElement.appendChild(overlay);
    chatContainer.addEventListener('dragover', (e) => { e.preventDefault(); overlay.style.display = 'flex'; });
    chatContainer.addEventListener('dragleave', () => { overlay.style.display = 'none'; });
    chatContainer.addEventListener('drop', async (e) => {
        e.preventDefault(); overlay.style.display = 'none';
        const files = e.dataTransfer?.files;
        if (!files || !files.length) return;
        for (const file of files) {
            const form = new FormData();
            form.append('file', file);
            try {
                const res = await fetch('/api/upload', { method: 'POST', body: form });
                const data = await res.json();
                if (res.ok && typeof addMessage === 'function') {
                    addMessage('📎 拖拽上传: ' + data.filename + ' (' + (data.size/1024).toFixed(1) + 'KB)', 'user');
                    if (typeof enqueueMessage === 'function') {
                        enqueueMessage({ type: 'chat', message: '我上传了文件 ' + data.filename + '，路径是 ' + data.path + '，请分析。', session_id: typeof currentSessionId !== 'undefined' ? currentSessionId : 'default' });
                    }
                }
            } catch (err) { console.error('拖拽上传失败:', err); }
        }
    });
})();

// === S59: 异步任务面板 ===
(function initTaskPanel() {
    const panel = document.getElementById('right-panel');
    if (!panel) return;
    const section = document.createElement('div');
    section.className = 'status-card';
    section.innerHTML = '<div class="label">ASYNC TASKS</div><div id="task-list" class="value" style="font-size:11px;max-height:120px;overflow-y:auto;">无任务</div>';
    const panelContent = panel.querySelector('.panel-content');
    if (panelContent) panelContent.appendChild(section);
    async function refreshTasks() {
        try {
            const res = await fetch('/api/tasks');
            const data = await res.json();
            const el = document.getElementById('task-list');
            if (!el) return;
            if (!data.tasks || data.tasks.length === 0) { el.textContent = '无任务'; return; }
            el.innerHTML = data.tasks.slice(0, 5).map(t => {
                const st = t.status === 'done' ? '✅' : t.status === 'running' ? '⏳' : t.status === 'failed' ? '❌' : '⏸';
                return '<div style="margin:2px 0">' + st + ' ' + t.description.substring(0, 30) + '</div>';
            }).join('');
        } catch (e) { /* ignore */ }
    }
    refreshTasks();
    setInterval(refreshTasks, 15000);
})();

// === S59: Cron定时任务面板 ===
(function initCronPanel() {
    const panel = document.getElementById('right-panel');
    if (!panel) return;
    const section = document.createElement('div');
    section.className = 'status-card';
    section.innerHTML = '<div class="label">CRON JOBS</div><div id="cron-list" class="value" style="font-size:11px;max-height:100px;overflow-y:auto;">无定时任务</div>';
    const panelContent = panel.querySelector('.panel-content');
    if (panelContent) panelContent.appendChild(section);
    async function refreshCron() {
        try {
            const res = await fetch('/api/cron');
            const data = await res.json();
            const el = document.getElementById('cron-list');
            if (!el) return;
            if (!data.jobs || data.jobs.length === 0) { el.textContent = '无定时任务'; return; }
            el.innerHTML = data.jobs.map(j => {
                const en = j.enabled ? '🟢' : '⚪';
                return '<div style="margin:2px 0">' + en + ' ' + j.description.substring(0, 25) + ' (每' + j.interval_seconds + 's, 已执行' + (j.run_count||0) + '次)</div>';
            }).join('');
        } catch (e) { /* ignore */ }
    }
    refreshCron();
    setInterval(refreshCron, 30000);
})();

// === S59: 对话中文件路径/URL可点击 ===
(function initClickablePaths() {
    const container = document.getElementById('chat-container');
    if (!container) return;
    const processed = new WeakSet();
    const obs = new MutationObserver((mutations) => {
        for (const m of mutations) {
            // 1. 新节点添加
            for (const node of m.addedNodes) {
                if (node.nodeType !== 1) continue;
                if (!node.classList) continue;
                if ((node.classList.contains('assistant') || node.classList.contains('tool-card')) && !node.classList.contains('streaming') && !processed.has(node)) {
                    processed.add(node); linkifyPaths(node);
                }
            }
            // 2. streaming类移除 → Markdown渲染完成 → linkify
            if (m.type === 'attributes' && m.attributeName === 'class' && m.target.classList && m.target.classList.contains('assistant') && !m.target.classList.contains('streaming') && !processed.has(m.target)) {
                processed.add(m.target); linkifyPaths(m.target);
            }
        }
    });
    obs.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });

    const _played = new Set();
    function linkifyPaths(el) {
        let html = el.innerHTML;
        let lastAudio = null; // 只播放最后一个音频
        // 1. /static/... 路径 → 可点击链接
        html = html.replace(
            /(?:\/static\/output\/|\/static\/)[^\s<"']*?\.(mp3|wav|mp4|png|jpg|jpeg|gif|txt|pdf|pptx|xlsx|csv)/gi,
            (match) => {
                const ext = match.split('.').pop().toLowerCase();
                if (['mp3','wav'].includes(ext)) lastAudio = match;
                if (['mp4'].includes(ext))
                    return '<a href="' + match + '" target="_blank" style="color:var(--accent)">' + match + '</a><video controls src="' + match + '" style="display:block;max-width:400px;margin:4px 0"></video>';
                if (['png','jpg','jpeg','gif'].includes(ext))
                    return '<a href="' + match + '" target="_blank"><img src="' + match + '" style="max-width:300px;margin:4px 0;border-radius:4px" /></a>';
                return '<a href="' + match + '" target="_blank" style="color:var(--accent);text-decoration:underline">' + match + '</a>';
            }
        );
        // 2. 纯文件名如 xxx.mp3 (code标签内) → 链接
        html = html.replace(/<code>([^<]+?\.(mp3|wav))<\/code>/gi, (full, fname) => {
            const url = '/static/output/' + fname;
            lastAudio = url;
            return '<a href="' + url + '" target="_blank" style="color:var(--accent)">' + fname + '</a>';
        });
        // 只播放最后一个音频，且不重复
        if (lastAudio && !_played.has(lastAudio)) {
            _played.add(lastAudio);
            try { new Audio(lastAudio).play(); } catch(e) {}
        }
        // 3. 本地路径 (F:\...) → 点击复制
        html = html.replace(
            /([A-Z]:\\[^\s<"']+\.\w{1,5})/gi,
            (m) => '<span style="color:#4ec9b0;cursor:pointer;text-decoration:underline dotted" title="Click to copy" onclick="navigator.clipboard.writeText(\'' + m.replace(/\\/g,'\\\\').replace(/'/g,"\\'") + '\');this.title=\'Copied!\'">' + m + '</span>'
        );
        if (html !== el.innerHTML) el.innerHTML = html;
    }
})();
