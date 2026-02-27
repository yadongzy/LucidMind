/**
 * LucidMind Control UI — 主应用组件
 * 对标 OpenClaw 的 Lit Web Component 架构
 */
import { LitElement, html, nothing } from "lit";
import { icons } from "./icons.js";
import { GatewayClient } from "./gateway.js";
import { renderMarkdown } from "./markdown.js";
import * as api from "./api.js";
import { renderChat } from "./views/chat.js";
import { renderOverview } from "./views/overview.js";
import { renderSessions } from "./views/sessions.js";
import { renderConfig } from "./views/config.js";
import { renderBrain, renderMemory, renderTasks } from "./views/brain.js";
import { renderTasksPage } from "./views/scheduler.js";
import { renderProfile } from "./views/profile.js";
import { renderPlugins } from "./views/plugins.js";
import { renderMcp } from "./views/mcp.js";
import { renderChannels } from "./views/channels.js";
import { renderDiagnostics } from "./views/diagnostics.js";
import { installTestProbe } from "./test-probe.js";

const TAB_GROUPS = [
  { label: "对话", tabs: ["chat"] },
  { label: "控制台", tabs: ["overview", "sessions", "tasks"] },
  { label: "大脑", tabs: ["brain", "memory"] },
  { label: "连接", tabs: ["channels", "mcp"] },
  { label: "设置", tabs: ["plugins", "profile", "config", "diagnostics"] },
];

const TAB_ICONS = {
  chat: "chat",
  overview: "overview",
  sessions: "sessions",
  tasks: "tasks",
  brain: "brain",
  memory: "memory",
  channels: "chat",
  mcp: "debug",
  plugins: "zap",
  profile: "user",
  config: "settings",
  diagnostics: "debug",
};

const TAB_TITLES = {
  chat: "对话",
  overview: "系统概览",
  sessions: "会话管理",
  tasks: "任务看板",
  brain: "大脑状态",
  memory: "记忆与学习",
  channels: "消息通道",
  mcp: "MCP 管理",
  plugins: "插件管理",
  profile: "用户画像",
  config: "系统配置",
  diagnostics: "系统诊断",
};

const TAB_SUBS = {
  chat: "与 LucidMind 对话",
  overview: "系统健康状态一览",
  sessions: "管理对话会话",
  tasks: "异步任务与定时任务",
  brain: "目标、思考、行动",
  memory: "对话记忆、经验库、学习进度",
  channels: "Telegram / 飞书 / 企微 / 微信",
  mcp: "连接外部 MCP Server 获取工具",
  plugins: "安装、启用、管理扩展插件",
  profile: "偏好、规则、个性化配置",
  config: "模型、API密钥、大脑设置",
  diagnostics: "工具调用、MCP请求、性能分析、实时日志",
};

class LucidMindApp extends LitElement {
  static properties = {
    tab: { state: true },
    connected: { state: true },
    navCollapsed: { state: true },
    // Chat state
    messages: { state: true },
    chatDraft: { state: true },
    streamingText: { state: true },
    isStreaming: { state: true },
    currentThinking: { state: true },
    showThinking: { state: true },
    pendingConfirm: { state: true },
    // Data
    status: { state: true },
    sessions: { state: true },
    currentSession: { state: true },
    brainStatus: { state: true },
    eventLog: { state: true },
    // Config
    modelInfo: { state: true },
    // Theme
    theme: { state: true },
    // Heartbeat
    heartbeat: { state: true },
    // Queue
    chatQueue: { state: true },
    // Security
    pendingApproval: { state: true },
  };

  // Disable shadow DOM — use global CSS like OpenClaw
  createRenderRoot() {
    return this;
  }

  constructor() {
    super();
    this.tab = "chat";
    this.connected = false;
    this.navCollapsed = false;
    this.messages = [];
    this.chatDraft = "";
    this.streamingText = "";
    this.isStreaming = false;
    this.currentThinking = null;
    this.showThinking = localStorage.getItem("lucid_thinking") !== "false";
    this.pendingConfirm = false;
    this.status = null;
    this.sessions = [];
    this.currentSession = localStorage.getItem("lucid_session") || "default";
    this.brainStatus = null;
    this.eventLog = [];
    this.modelInfo = { model: "--", provider: "unknown" };
    this.heartbeat = { alive: false, latency: null, lastTs: null };
    this.theme = localStorage.getItem("lucid_theme") || "dark";
    document.documentElement.setAttribute("data-theme", this.theme);

    this.chatQueue = [];
    this.pendingApproval = null;
    this.gateway = new GatewayClient();
    this._setupGateway();
  }

  connectedCallback() {
    super.connectedCallback();
    this.gateway.connect();
    this._loadInitialData();
    this._statusInterval = setInterval(() => this._refreshStatus(), 30000);
    this._brainInterval = setInterval(() => this._refreshBrain(), 15000);
    installTestProbe(this);
    // 请求浏览器通知权限（用于 Cron 任务结果推送）
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
    // 文件路径链接点击 → 复制到剪贴板
    this.addEventListener("click", (e) => {
      const link = e.target.closest(".file-link");
      if (link) {
        e.preventDefault();
        const path = link.dataset.path;
        if (path) {
          navigator.clipboard.writeText(path).then(() => {
            const orig = link.textContent;
            link.textContent = "✅ 已复制!";
            link.classList.add("file-link--copied");
            setTimeout(() => { link.textContent = orig; link.classList.remove("file-link--copied"); }, 1500);
          }).catch(() => {
            prompt("复制路径:", path);
          });
        }
      }
    });
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.gateway.disconnect();
    clearInterval(this._statusInterval);
    clearInterval(this._brainInterval);
  }

  _log(type, msg) {
    const time = new Date().toLocaleTimeString();
    this.eventLog = [{ time, type, msg }, ...this.eventLog].slice(0, 200);
  }

  _setupGateway() {
    this.gateway.on("connected", () => {
      this.connected = true;
      this._log("sys", "WebSocket Connected");
      this._refreshStatus();
    });

    this.gateway.on("disconnected", () => {
      this.connected = false;
      this.heartbeat = { alive: false, latency: null, lastTs: null };
      this._log("sys", "WebSocket Disconnected");
    });

    this.gateway.on("pong", (info) => {
      this.heartbeat = { alive: true, latency: info.latency, lastTs: info.ts };
    });

    this.gateway.on("queue_changed", () => {
      this.chatQueue = this.gateway.getQueue();
    });

    this.gateway.on("queue_sent", (info) => {
      this.messages = [...this.messages, { role: "user", content: info.text, timestamp: Date.now() }];
    });

    this.gateway.on("message", (data) => {
      switch (data.type) {
        case "thinking":
          if (!this.gateway.isProcessing) break;
          this.currentThinking = data.data;
          this.messages = [...this.messages, { role: "thinking", content: data.data, timestamp: Date.now() }];
          this._log("think", "Thinking...");
          break;

        case "tool_call":
          if (!this.gateway.isProcessing) break;
          this.messages = [...this.messages, { role: "tool_call", content: data.data, timestamp: Date.now() }];
          this._log("tool", `Call: ${data.data}`);
          break;

        case "tool_result":
          if (!this.gateway.isProcessing) break;
          this.messages = [...this.messages, { role: "tool_result", content: data.data, timestamp: Date.now() }];
          this._log("tool", "Result received");
          break;

        case "response_start":
          this.isStreaming = true;
          this.streamingText = "";
          this.currentThinking = null;
          this._log("stream", "Streaming started");
          break;

        case "response_delta":
          if (data.data) {
            this.streamingText += data.data;
          }
          break;

        case "response_end":
          if (this.streamingText) {
            this.messages = [...this.messages, { role: "assistant", content: this.streamingText, timestamp: Date.now() }];
          }
          this.isStreaming = false;
          this.streamingText = "";
          this._log("stream", "Streaming complete");
          break;

        case "response":
          this.currentThinking = null;
          this.messages = [...this.messages, { role: "assistant", content: data.data, timestamp: Date.now() }];
          this._log("chat", `assistant: ${(data.data || "").substring(0, 30)}...`);
          break;

        case "error":
          this.currentThinking = null;
          this.isStreaming = false;
          this.messages = [...this.messages, { role: "error", content: data.data, timestamp: Date.now() }];
          this._log("error", data.data);
          break;

        case "plan_confirm":
          this.pendingConfirm = true;
          this._log("brain", "Plan confirmation requested");
          break;

        case "tool_approval_request":
          this.pendingApproval = data;
          this._log("security", `\u5de5\u5177\u5ba1\u6279: ${data.tool_name} (${data.level})`);
          break;

        case "task_updated": {
          const evt = data.event || "updated";
          const t = data.task || {};
          this._log("task", `${evt}: ${t.content || t.id || ""}`);
          // 触发任务看板数据刷新（通过自定义事件）
          window.dispatchEvent(new CustomEvent("lucid-task-updated", { detail: data }));
          break;
        }

        case "cron_updated": {
          const cronEvt = data.event || "updated";
          const cronJob = data.job || {};
          this._log("info", `⏰ 定时任务${cronEvt === 'created' ? '已创建' : cronEvt === 'fired' ? '已触发' : cronEvt}: ${cronJob.description || cronJob.command || ""}`);
          window.dispatchEvent(new CustomEvent("lucid-task-updated", { detail: data }));
          break;
        }

        case "task_result": {
          const tr = data.data || {};
          const taskName = tr.job_name || "任务";
          const taskContent = tr.content || "";
          const taskId = tr.task_id || "";
          if (taskContent) {
            this.messages = [...this.messages, {
              role: "assistant",
              content: `📋 **[任务完成]** ${taskName.substring(0, 40)}\n\n${taskContent}`,
              timestamp: Date.now(),
              isTask: true,
              taskId,
            }];
            this._log("task", `任务结果: ${taskName.substring(0, 30)}`);
          }
          window.dispatchEvent(new CustomEvent("lucid-task-updated", { detail: data }));
          break;
        }

        case "task_live": {
          const liveEvt = data.event || "";
          const liveData = data.data || "";
          const liveTaskName = data.task_name || "";
          if (liveEvt === "tool_call" && liveData) {
            this.messages = [...this.messages, {
              role: "tool_call",
              content: liveData,
              timestamp: Date.now(),
              isTask: true,
              taskId: data.task_id,
            }];
          } else if (liveEvt === "tool_result" && liveData) {
            this.messages = [...this.messages, {
              role: "tool_result",
              content: liveData,
              timestamp: Date.now(),
              isTask: true,
              taskId: data.task_id,
            }];
          }
          this._log("task", `${liveEvt}: ${liveTaskName.substring(0, 30)}`);
          break;
        }

        case "cron_result": {
          const cr = data.data || {};
          const jobName = cr.job_name || "定时任务";
          const content = cr.content || "";
          if (content) {
            this.messages = [...this.messages, {
              role: "assistant",
              content: `📅 **[${jobName}]**\n\n${content}`,
              timestamp: Date.now(),
              isCron: true,
            }];
            this._log("cron", `结果: ${jobName}`);
          }
          // 浏览器通知
          if (Notification.permission === "granted") {
            new Notification(`📅 ${jobName}`, {
              body: content.substring(0, 120),
              icon: "/assets/icon.png",
            });
          }
          window.dispatchEvent(new CustomEvent("lucid-task-updated", { detail: data }));
          break;
        }

        case "info":
          this._log("info", data.data || "");
          break;

        case "complete":
          this._log("sys", "Processing complete");
          break;
      }
    });
  }

  async _loadInitialData() {
    await Promise.all([
      this._refreshStatus(),
      this._refreshSessions(),
      this._refreshBrain(),
      this._loadHistory(),
    ]);
  }

  async _refreshStatus() {
    try {
      this.status = await api.fetchStatus();
      this.modelInfo = {
        model: this.status?.llm?.model || "--",
        provider: this.status?.llm?.provider || "unknown",
      };
    } catch (e) { /* ignore */ }
  }

  async _refreshSessions() {
    try {
      const data = await api.fetchSessions();
      this.sessions = data.sessions || [];
    } catch (e) { /* ignore */ }
  }

  async _refreshBrain() {
    try {
      this.brainStatus = await api.fetchBrainStatus();
      const d = this.brainStatus?.daemon || {};
      if (d.pending_plan && !d.user_confirmed) {
        this.pendingConfirm = true;
      }
    } catch (e) { /* ignore */ }
  }

  async _loadHistory() {
    try {
      const data = await api.fetchHistory(this.currentSession);
      if (data.messages) {
        this.messages = data.messages
          .filter(m => m.role !== "system")
          .map(m => ({ role: m.role || "user", content: m.content || "", timestamp: m.timestamp ? m.timestamp * 1000 : null }));
        this._log("sys", `Loaded ${this.messages.length} messages`);
      }
    } catch (e) {
      this._log("error", `History load failed: ${e.message}`);
    }
  }

  // === Actions ===

  _sendChat() {
    const text = this.chatDraft.trim();
    if (!text) return;
    const willQueue = this.gateway.isProcessing;
    this.gateway.sendChat(text, this.currentSession);
    this.chatDraft = "";
    this.chatQueue = this.gateway.getQueue();
    this._log("chat", `user: ${text.substring(0, 30)}${willQueue ? ' [queued]' : ''}`);
  }

  _switchSession(sid) {
    if (sid === this.currentSession) return;
    this.currentSession = sid;
    localStorage.setItem("lucid_session", sid);
    this.messages = [];
    this.isStreaming = false;
    this.streamingText = "";
    this.currentThinking = null;
    this.gateway.isProcessing = false;
    this.gateway.switchSession(sid);
    this._refreshSessions();
    this._loadHistory();
    this._log("session", `Switched to ${sid}`);
  }

  async _newSession() {
    try {
      const data = await api.createSession();
      this._switchSession(data.session.id);
    } catch (e) { /* ignore */ }
  }

  async _deleteSession(sid) {
    if (!confirm(`删除会话 ${sid}？`)) return;
    await api.deleteSession(sid);
    if (this.currentSession === sid) this._switchSession("default");
    this._refreshSessions();
  }

  async _confirmPlan() {
    await api.confirmPlan();
    this.pendingConfirm = false;
    this._log("brain", "Plan confirmed");
  }

  async _skipPlan() {
    await api.skipPlan();
    this.pendingConfirm = false;
    this._log("brain", "Plan skipped");
  }

  _abortChat() {
    this.gateway.abort();
    this.isStreaming = false;
    this.streamingText = "";
    this.currentThinking = null;
    this._log("sys", "Chat aborted");
  }

  async _uploadFile(file) {
    try {
      const data = await api.uploadFile(file);
      this.messages = [...this.messages, { role: "user", content: `📎 已上传: ${data.filename} (${(data.size / 1024).toFixed(1)}KB)` }];
      this.gateway.sendChat(`我上传了文件 ${data.filename}，路径是 ${data.path}，请分析这个文件。`, this.currentSession);
      this._log("sys", `Upload: ${data.filename}`);
    } catch (e) {
      this.messages = [...this.messages, { role: "error", content: `上传失败: ${e.message}` }];
    }
  }

  _setTab(tab) {
    if (tab === "chat") this._chatJustOpened = true;
    this.tab = tab;
  }

  // === Render ===

  render() {
    const isChat = this.tab === "chat";

    return html`
      <div class="shell ${this.navCollapsed ? "shell--nav-collapsed" : ""}">
        <!-- Topbar -->
        <header class="topbar">
          <div class="topbar-left">
            <button class="nav-toggle" @click=${() => this.navCollapsed = !this.navCollapsed}
              title="${this.navCollapsed ? "Expand sidebar" : "Collapse sidebar"}">
              ${icons.menu}
            </button>
            <div class="brand">
              <div class="brand-icon">🧠</div>
              <div class="brand-text">
                <div class="brand-title">LUCIDMIND</div>
                <div class="brand-sub">控制面板</div>
              </div>
            </div>
          </div>
          <div class="topbar-right">
            <div class="pill" title="${this.heartbeat.alive ? `心跳正常 · ${this.heartbeat.latency != null ? this.heartbeat.latency + 'ms' : ''}` : '等待心跳...'}">
              <span class="statusDot ${this.connected ? "ok" : ""}"></span>
              <span>状态</span>
              <span class="mono">${this.connected ? "正常" : "离线"}</span>
              ${this.connected ? html`<span class="heartbeat-pulse ${this.heartbeat.alive ? 'alive' : ''}">♥</span>` : nothing}
            </div>
            ${this.status?.llm?.local_only ? html`
              <div class="pill pill--warn" title="外部模型冷却中，当前使用本地备用模型，响应可能较慢">
                <span class="statusDot warn"></span>
                <span>备用模型</span>
              </div>
            ` : nothing}
            <div class="pill pill--model" title="当前模型 (点击切换)">
              <span class="statusDot ${this.status?.llm?.available ? 'ok' : ''}"></span>
              <select class="model-select"
                .value=${this.modelInfo.provider}
                @change=${(e) => this._switchModel(e.target.value)}>
                <option value="deepseek" ?selected=${this.modelInfo.provider === 'deepseek'}>DeepSeek</option>
                <option value="minimax" ?selected=${this.modelInfo.provider === 'minimax'}>MiniMax</option>
                <option value="local" ?selected=${this.modelInfo.provider === 'local'}>Local (Ollama)</option>
              </select>
            </div>
            <button class="theme-toggle" @click=${(e) => this._toggleTheme(e)}
              title="${this.theme === 'dark' ? '切换亮色' : '切换暗色'}">
              <div class="theme-toggle__track">
                <span class="theme-toggle__item ${this.theme === 'light' ? 'theme-toggle__item--active' : ''}">
                  ${icons.sun}
                </span>
                <span class="theme-toggle__item ${this.theme === 'dark' ? 'theme-toggle__item--active' : ''}">
                  ${icons.moon}
                </span>
              </div>
            </button>
          </div>
        </header>

        <!-- Nav Sidebar -->
        <aside class="nav ${this.navCollapsed ? "nav--collapsed" : ""}">
          ${TAB_GROUPS.map(group => html`
            <div class="nav-group">
              <div class="nav-label">
                <span class="nav-label__text">${group.label}</span>
              </div>
              <div class="nav-group__items">
                ${group.tabs.map(tab => html`
                  <button class="nav-item ${this.tab === tab ? "nav-item--active" : ""}"
                    @click=${() => this._setTab(tab)}>
                    <span class="nav-item__icon">${icons[TAB_ICONS[tab]] || icons.overview}</span>
                    <span>${TAB_TITLES[tab]}</span>
                  </button>
                `)}
              </div>
            </div>
          `)}
        </aside>

        <!-- Content -->
        <main class="content ${isChat ? "content--chat" : ""}">
          ${isChat ? nothing : html`
            <section class="content-header">
              <div>
                <div class="page-title">${TAB_TITLES[this.tab]}</div>
                <div class="page-sub">${TAB_SUBS[this.tab]}</div>
              </div>
            </section>
          `}

          ${this.tab === "chat" ? renderChat(this) : nothing}
          ${this.tab === "overview" ? renderOverview(this) : nothing}
          ${this.tab === "sessions" ? renderSessions(this) : nothing}
          ${this.tab === "config" ? renderConfig(this) : nothing}
          ${this.tab === "brain" ? renderBrain(this) : nothing}
          ${this.tab === "memory" ? renderMemory(this) : nothing}
          ${this.tab === "tasks" ? renderTasksPage(this) : nothing}
          ${this.tab === "profile" ? renderProfile(this) : nothing}
          ${this.tab === "channels" ? renderChannels(this) : nothing}
          ${this.tab === "mcp" ? renderMcp(this) : nothing}
          ${this.tab === "plugins" ? renderPlugins(this) : nothing}
          ${this.tab === "diagnostics" ? renderDiagnostics(this) : nothing}
        </main>
      </div>

      ${!this.connected ? html`<div class="reconnect-banner">⚠ 连接已断开，正在重连...</div>` : nothing}

      ${this.pendingApproval ? html`
        <div class="modal-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center;">
          <div style="background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:24px;max-width:480px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,.3);">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
              <span style="font-size:28px;">⚠️</span>
              <div>
                <div style="font-size:16px;font-weight:700;color:var(--fg);">工具安全确认</div>
                <div style="font-size:12px;color:var(--fg-3);">该工具被标记为 <strong style="color:${this.pendingApproval.level === 'dangerous' ? '#ef4444' : '#f59e0b'};">${this.pendingApproval.level === 'dangerous' ? '危险' : '敏感'}</strong></div>
              </div>
            </div>
            <div style="padding:12px;background:var(--bg-2);border-radius:8px;margin-bottom:16px;">
              <div style="font-size:14px;font-weight:600;color:var(--fg);font-family:monospace;">${this.pendingApproval.tool_name}</div>
              <div style="font-size:12px;color:var(--fg-3);margin-top:6px;word-break:break-all;">
                ${Object.entries(this.pendingApproval.params || {}).map(([k,v]) => html`<div><strong>${k}:</strong> ${v}</div>`)}
              </div>
            </div>
            <div style="display:flex;gap:10px;justify-content:flex-end;align-items:center;">
              <span style="font-size:11px;color:var(--fg-3);">允许后自动加入白名单，不再弹窗</span>
              <button class="btn btn--primary" @click=${() => this._approvalRespond(true)}>允许执行</button>
            </div>
          </div>
        </div>
      ` : nothing}
    `;
  }

  _toggleTheme(e) {
    this.theme = this.theme === "dark" ? "light" : "dark";
    localStorage.setItem("lucid_theme", this.theme);
    document.documentElement.setAttribute("data-theme", this.theme);
  }

  _approvalRespond(approved) {
    if (!this.pendingApproval) return;
    // 直接发送，不走消息队列（审批响应必须即时到达）
    if (this.gateway.ws && this.gateway.ws.readyState === WebSocket.OPEN) {
      this.gateway.ws.send(JSON.stringify({
        type: "tool_approval_response",
        request_id: this.pendingApproval.request_id,
        approved,
        reason: approved ? "" : "用户拒绝",
      }));
    }
    this._log("security", `${approved ? '✅ 已批准' : '❌ 已拒绝'}: ${this.pendingApproval.tool_name}`);
    this.pendingApproval = null;
  }

  async _switchModel(model) {
    const providerMap = {
      "deepseek-chat": "deepseek",
      "MiniMax-M1": "minimax",
      "minimax": "minimax",
      "qwen2.5:7b": "local",
      "gemma3:4b": "local",
    };
    const provider = providerMap[model] || model;
    this._log("sys", `切换模型: ${provider}...`);
    try {
      const data = await api.switchProvider(provider);
      if (data.status === "ok") {
        this.messages = [...this.messages, {
          role: "assistant",
          content: `✅ 模型已切换为 **${data.model}** (${data.provider})`,
          timestamp: Date.now(),
        }];
        this._log("sys", `✅ 模型切换成功: ${data.model} (${data.provider})`);
      } else {
        this.messages = [...this.messages, {
          role: "assistant",
          content: `❌ 模型切换失败: ${data.detail || "未知错误"}`,
          timestamp: Date.now(),
        }];
        this._log("error", `模型切换失败`);
      }
      await this._refreshStatus();
    } catch (e) {
      this.messages = [...this.messages, {
        role: "assistant",
        content: `❌ 模型切换异常: ${e.message}`,
        timestamp: Date.now(),
      }];
      this._log("error", `模型切换异常: ${e.message}`);
    }
  }

}

customElements.define("lucidmind-app", LucidMindApp);
