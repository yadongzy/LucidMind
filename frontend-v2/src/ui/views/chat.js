/**
 * Chat view — 聊天主界面
 * 对标 OpenClaw: 消息分组 + 头像 + 时间戳 + 会话选择器 + 思考开关
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";
import { renderMarkdown } from "../markdown.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";

function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 150) + "px";
}

// 快捷指令
const SLASH_COMMANDS = [
  { cmd: "/天气", desc: "查询天气", template: "今天{city}的天气怎么样？", placeholder: "城市名" },
  { cmd: "/新闻", desc: "今日新闻", template: "帮我搜索今天的热点新闻" },
  { cmd: "/翻译", desc: "翻译文本", template: "请翻译以下内容：{text}", placeholder: "要翻译的文本" },
  { cmd: "/总结", desc: "总结对话", template: "请总结我们刚才的对话内容" },
  { cmd: "/搜索", desc: "联网搜索", template: "帮我联网搜索：{query}", placeholder: "搜索内容" },
  { cmd: "/代码", desc: "写代码", template: "请帮我写一段{lang}代码：{desc}", placeholder: "语言 描述" },
  { cmd: "/提醒", desc: "设置提醒", template: "{time}提醒我{task}", placeholder: "时间 事项" },
  { cmd: "/清空", desc: "清空对话", template: "__CLEAR__" },
];

function _getSlashMatches(text) {
  if (!text) return [];
  // 支持半角 / 和全角 ／
  let q = text.replace(/^／/, "/");
  if (!q.startsWith("/")) return [];
  if (q === "/") return SLASH_COMMANDS; // 只输入 / 显示全部
  const keyword = q.slice(1);
  return SLASH_COMMANDS.filter(c => c.cmd.includes(keyword) || c.desc.includes(keyword));
}

function _applySlashCmd(cmd, app) {
  if (cmd.template === "__CLEAR__") {
    app.messages = []; app.chatDraft = ""; app._slashOpen = false; app.requestUpdate();
    return;
  }
  app._slashOpen = false;
  if (cmd.placeholder) {
    const val = prompt(cmd.placeholder + ":");
    if (!val) { app.chatDraft = ""; app.requestUpdate(); return; }
    // 依次填充模板中的占位符
    let t = cmd.template;
    const placeholders = t.match(/\{[^}]+\}/g) || [];
    const parts = val.split(/\s+/);
    placeholders.forEach((ph, i) => {
      t = t.replace(ph, parts[i] || (i === 0 ? val : ""));
    });
    app.chatDraft = t;
    app.requestUpdate();
    // 有占位符的也自动发送
    setTimeout(() => app._sendChat(), 100);
  } else {
    app.chatDraft = cmd.template;
    app.requestUpdate();
    setTimeout(() => app._sendChat(), 100);
  }
}

function _exportChat(messages) {
  let md = `# LucidMind 对话记录\n> 导出时间: ${new Date().toLocaleString()}\n\n---\n\n`;
  for (const m of messages) {
    if (m.role === "user") md += `## 🧑 用户\n${m.content}\n\n`;
    else if (m.role === "assistant") md += `## 🤖 LucidMind\n${m.content}\n\n`;
    else if (m.role === "tool_call") md += `> 🔧 工具调用: ${m.content}\n\n`;
    else if (m.role === "tool_result") md += `> 📋 工具结果: ${(m.content || "").slice(0, 200)}\n\n`;
  }
  const blob = new Blob([md], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `lucidmind-chat-${new Date().toISOString().slice(0,10)}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function groupMessages(messages, showThinking) {
  const groups = [];
  let current = null;

  for (const msg of messages) {
    if (msg.role === "thinking" && !showThinking) continue;

    const groupRole = (msg.role === "user") ? "user"
      : (msg.role === "assistant" || msg.role === "thinking" || msg.role === "tool_call" || msg.role === "tool_result") ? "assistant"
      : "system";

    if (!current || current.role !== groupRole) {
      if (current) groups.push(current);
      current = { role: groupRole, messages: [msg], timestamp: msg.timestamp || null };
    } else {
      current.messages.push(msg);
    }
  }
  if (current) groups.push(current);
  return groups;
}

function renderAvatar(role) {
  if (role === "user") {
    return html`<div class="chat-avatar user">U</div>`;
  }
  if (role === "assistant") {
    return html`<div class="chat-avatar assistant">L</div>`;
  }
  return html`<div class="chat-avatar other">?</div>`;
}

const COLLAPSE_THRESHOLD = 500;

const NSFW_PATTERNS = [
  /黄播/i, /黄色/i, /色情/i, /淫/i, /裸/i, /成人/i,
  /约炮/i, /一夜情/i, /性爱/i, /做爱/i, /口交/i, /肛交/i,
  /AV\b/i, /porn/i, /nsfw/i, /xxx/i, /sex/i,
  /赌博/i, /博彩/i, /六合彩/i, /时时彩/i,
  /吃瓜.*爆料/i, /猛料/i, /黑料/i, /反差/i,
  /魅魔/i, /6P/i, /群P/i, /偷拍/i, /偷偷拔套/i,
];

function containsNSFW(text) {
  if (!text) return false;
  let matchCount = 0;
  for (const p of NSFW_PATTERNS) {
    if (p.test(text)) matchCount++;
    if (matchCount >= 2) return true;
  }
  return false;
}

function renderCollapsibleBubble(content, isMarkdown) {
  const text = content || "";
  const isLong = text.length > COLLAPSE_THRESHOLD;
  const isNSFW = containsNSFW(text);

  if (isNSFW) {
    return html`
      <div class="chat-bubble chat-bubble--filtered fade-in">
        <div class="chat-filter-notice">
          <span>⚠️ 内容已过滤</span>
          <span class="chat-filter-reason">检测到不适当内容</span>
        </div>
        <details class="chat-filter-details">
          <summary>查看原始内容</summary>
          <div class="chat-filter-content">
            ${isMarkdown ? unsafeHTML(renderMarkdown(text)) : text}
          </div>
        </details>
      </div>
    `;
  }

  if (isLong) {
    const preview = text.substring(0, COLLAPSE_THRESHOLD);
    return html`
      <div class="chat-bubble chat-bubble--long fade-in">
        <div class="chat-bubble__preview">
          ${isMarkdown ? unsafeHTML(renderMarkdown(preview + "...")) : (preview + "...")}
        </div>
        <details class="chat-bubble__expand">
          <summary>展开全部 (${text.length} 字符)</summary>
          <div class="chat-bubble__full">
            ${isMarkdown ? unsafeHTML(renderMarkdown(text)) : text}
          </div>
        </details>
      </div>
    `;
  }

  return html`<div class="chat-bubble fade-in">${isMarkdown ? unsafeHTML(renderMarkdown(text)) : text}</div>`;
}

function renderBubble(msg) {
  if (msg.role === "user") {
    return renderCollapsibleBubble(msg.content, false);
  }
  if (msg.role === "assistant") {
    return renderCollapsibleBubble(msg.content, true);
  }
  if (msg.role === "thinking") {
    return html`
      <div class="chat-tool-card" @click=${(e) => e.currentTarget.classList.toggle("chat-tool-card--collapsed")}>
        <div class="chat-tool-card__header">
          <div class="chat-tool-card__title">
            <span class="chat-tool-card__icon">⚡</span>
            <span>思考过程</span>
          </div>
        </div>
        <div class="chat-tool-card__body">${msg.content}</div>
      </div>
    `;
  }
  if (msg.role === "tool_call") {
    const toolName = (msg.content || "").split("(")[0] || "tool";
    return html`
      <details class="chat-tool-card chat-tool-card--collapsed">
        <summary class="chat-tool-card__header">
          <span class="chat-tool-card__icon">⚙️</span>
          <span style="font-size:12px;color:var(--fg-3);">调用 <b style="color:var(--fg);">${toolName}</b></span>
        </summary>
        <div class="chat-tool-card__body" style="font-size:11px;word-break:break-all;">${msg.content}</div>
      </details>
    `;
  }
  if (msg.role === "tool_result") {
    const preview = (msg.content || "").substring(0, 80);
    return html`
      <details class="chat-tool-card chat-tool-card--result chat-tool-card--collapsed">
        <summary class="chat-tool-card__header">
          <span class="chat-tool-card__icon">✅</span>
          <span style="font-size:12px;color:var(--fg-3);">结果: ${preview}${(msg.content || "").length > 80 ? '...' : ''}</span>
        </summary>
        <div class="chat-tool-card__body" style="font-size:11px;">${msg.content}</div>
      </details>
    `;
  }
  if (msg.role === "error") {
    return html`<div class="chat-bubble chat-bubble--error fade-in">错误: ${msg.content}</div>`;
  }
  return nothing;
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    const thread = document.getElementById("chat-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  });
}

let _scrollListenerEl = null;
function _attachScrollListener() {
  requestAnimationFrame(() => {
    const thread = document.getElementById("chat-thread");
    const btn = document.getElementById("chat-scroll-btn");
    if (!thread || !btn) return;
    if (_scrollListenerEl === thread) return;
    _scrollListenerEl = thread;
    thread.addEventListener("scroll", () => {
      const distFromBottom = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
      btn.classList.toggle("visible", distFromBottom > 150);
    });
  });
}

export function renderChat(app) {
  const isBusy = app.isStreaming || app.gateway.isProcessing;
  const searchQ = (app._chatSearch || '').toLowerCase();
  const filteredMsgs = searchQ
    ? app.messages.filter(m => (m.content || '').toLowerCase().includes(searchQ))
    : app.messages;
  const groups = groupMessages(filteredMsgs, app.showThinking);

  // 自动滚动：新消息、流式输出、或刚切换到对话页面时
  if (app._prevMsgCount !== app.messages.length || app.isStreaming || app._chatJustOpened) {
    app._prevMsgCount = app.messages.length;
    app._chatJustOpened = false;
    scrollToBottom();
  }
  _attachScrollListener();

  return html`
    <section class="chat">
      <!-- Chat Controls — 对标 OpenClaw chat-controls -->
      <div class="chat-controls">
        <div class="chat-controls__left">
          <label class="chat-controls__session">
            <select .value=${app.currentSession} ?disabled=${!app.connected}
              @change=${(e) => app._switchSession(e.target.value)}>
              ${app.sessions.map(s => html`
                <option value=${s.id} ?selected=${s.id === app.currentSession}>
                  ${s.title || s.id}
                </option>
              `)}
            </select>
          </label>
          <button class="btn btn--sm btn--icon" title="新建会话"
            @click=${() => app._newSession()} ?disabled=${!app.connected}>
            ${icons.plus}
          </button>
          <button class="btn btn--sm btn--icon" title="清除当前对话"
            @click=${async () => { if(confirm('清除当前对话内容？')) { app.messages = []; await fetch('/api/sessions/' + app.currentSession + '/history', {method:'DELETE'}); app._log('chat', 'Cleared'); } }}>
            ${icons.trash}
          </button>
          <button class="btn btn--sm btn--icon" title="刷新对话"
            @click=${async (e) => {
              const btn = e.currentTarget;
              btn.classList.add('spinning');
              await app._loadHistory();
              setTimeout(() => btn.classList.remove('spinning'), 600);
            }} ?disabled=${!app.connected}>
            ${icons.refresh}
          </button>
          <span class="chat-controls__separator">|</span>
          <button class="btn btn--sm btn--icon ${app.showThinking ? 'active' : ''}"
            title="${app.showThinking ? '隐藏思考过程' : '显示思考过程'}"
            @click=${() => {
              app.showThinking = !app.showThinking;
              localStorage.setItem("lucid_thinking", app.showThinking);
            }}>
            ${icons.brain}
          </button>
        </div>
        <div class="chat-controls__right" style="display:flex;align-items:center;gap:4px;">
          <input type="text" placeholder="🔍 搜索对话..." .value=${app._chatSearch || ''}
            @input=${(e) => { app._chatSearch = e.target.value; app.requestUpdate(); }}
            style="padding:3px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-2);color:var(--fg);font-size:11px;width:140px;">
          ${app._chatSearch ? html`<button class="btn btn--sm btn--icon" title="清除搜索"
            @click=${() => { app._chatSearch = ''; app.requestUpdate(); }}
            style="font-size:10px;">✕</button>` : nothing}
          <button class="btn btn--sm btn--icon" title="导出对话为 Markdown"
            @click=${() => _exportChat(app.messages)}
            style="font-size:12px;">📥</button>
        </div>
      </div>

      <!-- Messages Thread -->
      <div class="chat-thread" id="chat-thread">
        ${groups.length === 0 && !app.isStreaming ? html`
          <div class="chat-empty">
            <div class="chat-empty__icon">🧠</div>
            <div class="chat-empty__title">LucidMind</div>
            <div class="chat-empty__sub">开始对话吧</div>
          </div>
        ` : nothing}

        ${groups.map(group => html`
          <div class="chat-group ${group.role}">
            ${renderAvatar(group.role)}
            <div class="chat-group-messages">
              ${group.messages.map(msg => renderBubble(msg))}
              <div class="chat-group-footer">
                <span class="chat-sender-name">${group.role === "user" ? "你" : "LucidMind"}</span>
                ${group.timestamp ? html`<span class="chat-group-timestamp">${new Date(group.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>` : nothing}
              </div>
            </div>
          </div>
        `)}

        ${app.isStreaming && app.streamingText ? html`
          <div class="chat-group assistant">
            ${renderAvatar("assistant")}
            <div class="chat-group-messages">
              <div class="chat-bubble streaming fade-in">${unsafeHTML(renderMarkdown(app.streamingText))}</div>
              <div class="chat-group-footer">
                <span class="chat-sender-name">LucidMind</span>
                <span class="chat-group-timestamp">${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
              </div>
            </div>
          </div>
        ` : nothing}

        ${isBusy && !app.isStreaming ? html`
          <div class="chat-group assistant">
            ${renderAvatar("assistant")}
            <div class="chat-group-messages">
              <div class="chat-bubble chat-reading-indicator">
                <span class="chat-reading-indicator__dots">
                  <span></span><span></span><span></span>
                </span>
              </div>
            </div>
          </div>
        ` : nothing}
      </div>

      <!-- Scroll to bottom button -->
      <button class="chat-scroll-bottom" id="chat-scroll-btn"
        @click=${() => {
          const thread = document.getElementById("chat-thread");
          if (thread) thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
        }}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>

      <!-- Queue panel — 对标 Cascade 排队机制: 可编辑、可删除、可强行发送 -->
      ${app.chatQueue.length > 0 ? html`
        <div class="chat-queue-panel">
          <div class="chat-queue-panel__header">
            <span>${app.chatQueue.length} message${app.chatQueue.length > 1 ? 's' : ''} queued</span>
          </div>
          ${app.chatQueue.map(item => html`
            <div class="chat-queue-item">
              <span class="chat-queue-item__icon">💬</span>
              <span class="chat-queue-item__text">${item.text.length > 60 ? item.text.substring(0, 60) + '…' : item.text}</span>
              <div class="chat-queue-item__actions">
                <button class="chat-queue-btn" title="编辑"
                  @click=${() => {
                    const newText = prompt("编辑消息:", item.text);
                    if (newText !== null && newText.trim()) {
                      app.gateway.editQueueItem(item.index, newText.trim());
                      app.chatQueue = app.gateway.getQueue();
                    }
                  }}>✏️</button>
                <button class="chat-queue-btn" title="删除"
                  @click=${() => {
                    app.gateway.removeQueueItem(item.index);
                    app.chatQueue = app.gateway.getQueue();
                  }}>🗑️</button>
                <button class="chat-queue-btn chat-queue-btn--send" title="强行发送"
                  @click=${() => {
                    app.gateway.forceSendNext();
                    app.chatQueue = app.gateway.getQueue();
                  }}>⚡</button>
              </div>
            </div>
          `)}
        </div>
      ` : nothing}

      <!-- Compose — 对标 OpenClaw chat-compose -->
      <div class="chat-compose">
        <div class="chat-compose__row">
          <button class="btn btn--icon" title="上传文件"
            @click=${() => {
              const input = document.createElement("input");
              input.type = "file";
              input.onchange = () => {
                for (const file of input.files) app._uploadFile(file);
              };
              input.click();
            }}>
            ${icons.upload}
          </button>
          <textarea class="chat-compose__textarea"
            placeholder="消息... (Enter发送, Shift+Enter换行, / 快捷指令)"
            .value=${app.chatDraft}
            @input=${(e) => { app.chatDraft = e.target.value; app._slashOpen = _getSlashMatches(e.target.value).length > 0; autoResize(e.target); app.requestUpdate(); }}
            @keydown=${(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
                e.preventDefault();
                const matches = _getSlashMatches(app.chatDraft);
                if (matches.length === 1) {
                  _applySlashCmd(matches[0], app);
                  app._slashOpen = false;
                  e.target.style.height = "auto";
                  return;
                }
                app._slashOpen = false;
                app._sendChat();
                e.target.style.height = "auto";
              }
            }}
            @paste=${(e) => {
              const items = e.clipboardData?.items;
              if (!items) return;
              for (let i = 0; i < items.length; i++) {
                if (items[i].type.startsWith("image/")) {
                  e.preventDefault();
                  const file = items[i].getAsFile();
                  if (file) app._uploadFile(file);
                  return;
                }
              }
            }}
            rows="1"
          ></textarea>
          ${app._slashOpen ? html`
            <div style="position:absolute;bottom:100%;left:0;right:0;background:var(--bg-elevated,var(--card));border:1px solid var(--border);border-radius:8px;box-shadow:0 -4px 16px rgba(0,0,0,.15);max-height:280px;overflow-y:auto;z-index:100;margin-bottom:4px;">
              <div style="padding:6px 12px;font-size:11px;color:var(--fg-3);border-bottom:1px solid var(--border);font-weight:600;">快捷指令</div>
              ${_getSlashMatches(app.chatDraft).map(c => html`
                <div style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:12px;font-size:13px;transition:background .1s;"
                  @mousedown=${(e) => { e.preventDefault(); _applySlashCmd(c, app); }}
                  @mouseenter=${(e) => e.currentTarget.style.background='var(--bg-2)'}
                  @mouseleave=${(e) => e.currentTarget.style.background='transparent'}>
                  <span style="font-weight:700;color:var(--accent);min-width:55px;font-family:monospace;">${c.cmd}</span>
                  <span style="color:var(--fg-2);">${c.desc}</span>
                  ${c.placeholder ? html`<span style="color:var(--fg-3);font-size:11px;margin-left:auto;">${c.placeholder}</span>` : nothing}
                </div>
              `)}
            </div>
          ` : nothing}
          <button class="btn btn--compose ${isBusy ? 'btn--danger' : 'btn--primary'}"
            ?disabled=${!isBusy && (!app.connected || !app.chatDraft.trim())}
            @click=${isBusy ? () => app._abortChat() : () => app._sendChat()}
            title="${isBusy ? '停止生成' : '发送 (Enter)'}">
            ${isBusy ? icons.stop : icons.send}
          </button>
        </div>
      </div>
    </section>
  `;
}
