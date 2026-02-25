/**
 * Tasks View — 任务看板（整合任务队列 + 定时任务，tab切换）
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";
import * as api from "../api.js";

let _cronJobs = [];
let _dispatcherData = { tasks: [], total: 0, shown: 0 };
let _loading = false;
let _lastRefresh = 0;
let _activeTab = "cron";
let _queueFilter = "all";
let _taskUpdateApp = null;
let _showNewTask = false;
let _creating = false;
let _expandedTaskId = null;

async function _createTask(app) {
  const input = document.getElementById("new-task-content");
  const priSel = document.getElementById("new-task-priority");
  const content = input?.value?.trim();
  if (!content) return;
  _creating = true;
  app.requestUpdate();
  try {
    const res = await fetch("/api/dispatcher/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, priority: priSel?.value || "P2" }),
    });
    const data = await res.json();
    if (data.status === "created") {
      input.value = "";
      _showNewTask = false;
      await _refresh();
    }
  } catch (e) { console.error("创建任务失败:", e); }
  _creating = false;
  app.requestUpdate();
}

async function _createNewItem(app) {
  const typeEl = document.getElementById("new-task-type");
  const jobType = typeEl?.value || "task";

  if (jobType === "cron") {
    const descEl = document.getElementById("new-task-content");
    const exprEl = document.getElementById("new-cron-expr");
    const cmdEl = document.getElementById("new-cron-command");
    const desc = descEl?.value?.trim();
    const expr = exprEl?.value?.trim();
    const cmd = cmdEl?.value?.trim();
    if (!desc || !expr || !cmd) { alert("请填写完整：描述、cron表达式、执行指令"); return; }
    _creating = true;
    app.requestUpdate();
    try {
      const res = await fetch("/api/cron", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: desc, schedule: expr, command: cmd, job_type: "cron" }),
      });
      if (res.ok) {
        descEl.value = ""; cmdEl.value = "";
        _showNewTask = false;
        await _refresh();
      } else {
        const err = await res.json();
        alert("创建失败: " + (err.detail || JSON.stringify(err)));
      }
    } catch (e) { console.error("创建定时日程失败:", e); alert("创建失败: " + e.message); }
    _creating = false;
    app.requestUpdate();
  } else {
    await _createTask(app);
  }
}

// 监听 WebSocket 推送的任务变更事件，自动刷新
window.addEventListener("lucid-task-updated", () => {
  _refresh().then(() => { if (_taskUpdateApp) _taskUpdateApp.requestUpdate(); });
});

// 倒计时心跳：每秒刷新提醒倒计时
let _countdownTimer = null;
function _startCountdown(app) {
  if (_countdownTimer) return;
  _countdownTimer = setInterval(() => {
    const atJobs = _cronJobs.filter(j => j.type === 'at' && j.enabled);
    if (atJobs.length === 0) {
      clearInterval(_countdownTimer);
      _countdownTimer = null;
      return;
    }
    // 检查是否有到期的提醒
    const now = Date.now();
    const expired = atJobs.some(j => j.trigger_at && new Date(j.trigger_at).getTime() <= now);
    if (expired) {
      // 提醒到期 → 刷新数据 + 自动切换到任务队列Tab
      _activeTab = 'queue';
      _refresh().then(() => { if (_taskUpdateApp) _taskUpdateApp.requestUpdate(); });
    } else if (_taskUpdateApp) {
      _taskUpdateApp.requestUpdate(); // 刷新倒计时显示
    }
  }, 1000);
}

function _formatCountdownReminder(triggerAt) {
  if (!triggerAt) return '—';
  const diff = Math.max(0, Math.floor((new Date(triggerAt).getTime() - Date.now()) / 1000));
  if (diff <= 0) return '即将触发...';
  const d = Math.floor(diff / 86400);
  const h = Math.floor((diff % 86400) / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  if (d > 0) return `${d}天${h}小时${m}分`;
  if (h > 0) return `${h}小时${m.toString().padStart(2,'0')}分`;
  if (m > 0) return `${m}分${s.toString().padStart(2,'0')}秒`;
  return `${s}秒`;
}

async function _refresh() {
  if (_loading) return;
  _loading = true;
  try {
    const [cronData, dispData] = await Promise.all([
      api.fetchCron(),
      fetch("/api/dispatcher/tasks").then(r => r.ok ? r.json() : { tasks: [], total: 0 }).catch(() => ({ tasks: [], total: 0 })),
    ]);
    _cronJobs = cronData?.jobs || [];
    _dispatcherData = dispData || { tasks: [], total: 0, shown: 0 };
    _lastRefresh = Date.now();
  } catch (e) {
    console.error("任务数据加载失败:", e);
  } finally {
    _loading = false;
  }
}

function _formatTime(ts) {
  if (!ts) return "—";
  const d = typeof ts === "number"
    ? new Date(ts > 1e12 ? ts : ts * 1000)
    : new Date(ts);
  if (isNaN(d.getTime())) return String(ts).substring(0, 19);
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function _formatCountdown(job) {
  const sched = job.schedule || "";
  const interval = job.interval_seconds;
  const lastRun = job.last_run;
  const created = job.created || job.created_at;
  if (interval && interval > 0) {
    const base = lastRun || (typeof created === "number" ? created : new Date(created).getTime() / 1000);
    if (!base) return "—";
    const nextRun = base + interval;
    const diff = nextRun - Date.now() / 1000;
    if (diff <= 0) return "即将执行";
    if (diff < 60) return `${Math.round(diff)}秒后`;
    if (diff < 3600) return `${Math.round(diff / 60)}分钟后`;
    if (diff < 86400) return `${Math.round(diff / 3600)}小时后`;
    return `${Math.round(diff / 86400)}天后`;
  }
  const schedMap = { hourly: 3600, daily: 86400, weekly: 604800, monthly: 2592000 };
  const sec = schedMap[sched.toLowerCase()];
  if (sec) {
    const base = lastRun || (typeof created === "number" ? created : new Date(created).getTime() / 1000);
    if (!base) return sched;
    const nextRun = base + sec;
    const diff = nextRun - Date.now() / 1000;
    if (diff <= 0) return "即将执行";
    if (diff < 60) return `${Math.round(diff)}秒后`;
    if (diff < 3600) return `${Math.round(diff / 60)}分钟后`;
    if (diff < 86400) return `${Math.round(diff / 3600)}小时后`;
    return `${Math.round(diff / 86400)}天后`;
  }
  if (sched.includes("minute")) return sched;
  return sched || "—";
}

function _formatNextRun(job) {
  // For cron type: compute next run from cron expression
  if (job.type === 'cron' && job.schedule) {
    // Simple: parse "M H * * *" to show today/tomorrow HH:MM
    const parts = (job.schedule || '').split(/\s+/);
    if (parts.length >= 2) {
      const minute = parseInt(parts[0], 10);
      const hour = parseInt(parts[1], 10);
      if (!isNaN(hour) && !isNaN(minute)) {
        const now = new Date();
        const next = new Date(now);
        next.setHours(hour, minute, 0, 0);
        if (next <= now) next.setDate(next.getDate() + 1);
        const isToday = next.toDateString() === now.toDateString();
        const timeStr = next.toLocaleTimeString("zh-CN", {hour:"2-digit", minute:"2-digit"});
        return isToday ? `今天 ${timeStr}` : `明天 ${timeStr}`;
      }
    }
    return job.schedule;
  }
  // For every type: use existing countdown
  return _formatCountdown(job);
}

function _scheduleLabel(job) {
  const sched = job.schedule || "";
  const interval = job.interval_seconds;
  if (job.type === "cron" && sched) {
    // 常见 cron 表达式中文翻译
    const cronMap = {
      "0 8 * * *": "每天 08:00", "0 9 * * *": "每天 09:00", "0 12 * * *": "每天 12:00",
      "0 18 * * *": "每天 18:00", "0 22 * * *": "每天 22:00",
      "0 8 * * 1-5": "工作日 08:00", "0 8 * * 1": "每周一 08:00",
    };
    return cronMap[sched] || `cron: ${sched}`;
  }
  if (interval) {
    if (interval < 60) return `每${interval}秒`;
    if (interval < 3600) return `每${Math.round(interval / 60)}分钟`;
    if (interval < 86400) return `每${Math.round(interval / 3600)}小时`;
    return `每${Math.round(interval / 86400)}天`;
  }
  const map = { hourly: "每小时", daily: "每天", weekly: "每周", monthly: "每月" };
  return map[sched.toLowerCase()] || sched || "—";
}

function _statusBadge(status) {
  const map = {
    pending: { cls: "badge--muted", text: "等待中" },
    running: { cls: "badge--info", text: "运行中" },
    done: { cls: "badge--ok", text: "已完成" },
    failed: { cls: "badge--err", text: "失败" },
    ready: { cls: "badge--muted", text: "就绪" },
    blocked: { cls: "badge--warn", text: "阻塞" },
    escalated: { cls: "badge--err", text: "已上报" },
    completed: { cls: "badge--ok", text: "已完成" },
  };
  const m = map[status] || { cls: "badge--muted", text: status };
  return html`<span class="sched-badge ${m.cls}">${m.text}</span>`;
}

function _priorityBadge(p) {
  const map = { P0: "badge--err", P1: "badge--warn", P2: "badge--info", P3: "badge--muted", L0: "badge--err", L1: "badge--warn", L2: "badge--info", L3: "badge--muted" };
  return html`<span class="sched-badge ${map[p] || 'badge--muted'}">${p}</span>`;
}

async function _deleteTask(taskId, app) {
  if (!confirm("确定删除此任务？")) return;
  try {
    await fetch(`/api/dispatcher/tasks/${taskId}`, { method: "DELETE" });
    await _refresh();
    app.requestUpdate();
  } catch (e) {
    console.error("删除失败:", e);
  }
}

async function _deleteCronJob(jobId, app) {
  if (!confirm("确定删除此定时任务？")) return;
  try {
    await fetch(`/api/cron/${jobId}`, { method: "DELETE" });
    await _refresh();
    app.requestUpdate();
  } catch (e) {
    console.error("删除失败:", e);
  }
}

function _renderQueueTab(app) {
  let tasks = _dispatcherData.tasks || [];
  if (_queueFilter === "active") {
    tasks = tasks.filter(t => ["ready", "running", "blocked"].includes(t.status));
  } else if (_queueFilter === "done") {
    tasks = tasks.filter(t => ["completed", "failed", "escalated"].includes(t.status));
  }
  const activeCount = (_dispatcherData.tasks || []).filter(t => ["ready", "running", "blocked"].includes(t.status)).length;

  return html`
    <div class="sched-filter-bar">
      <button class="sched-filter ${_queueFilter === 'all' ? 'sched-filter--active' : ''}"
        @click=${() => { _queueFilter = 'all'; app.requestUpdate(); }}>全部 (${_dispatcherData.shown || 0})</button>
      <button class="sched-filter ${_queueFilter === 'active' ? 'sched-filter--active' : ''}"
        @click=${() => { _queueFilter = 'active'; app.requestUpdate(); }}>活跃 (${activeCount})</button>
      <button class="sched-filter ${_queueFilter === 'done' ? 'sched-filter--active' : ''}"
        @click=${() => { _queueFilter = 'done'; app.requestUpdate(); }}>已完成</button>
      <span class="text-muted" style="margin-left:auto;font-size:11px;">总计 ${_dispatcherData.total} 条</span>
    </div>
    ${tasks.length === 0 ? html`
      <p class="text-muted" style="padding:24px;text-align:center;">暂无任务</p>
    ` : html`
      <div class="sched-table">
        <div class="sched-row sched-header">
          <span class="sched-col sched-col--id">ID</span>
          <span class="sched-col sched-col--name">内容</span>
          <span class="sched-col sched-col--pri">优先级</span>
          <span class="sched-col sched-col--status">状态</span>
          <span class="sched-col sched-col--src">来源</span>
          <span class="sched-col sched-col--time">创建时间</span>
          <span class="sched-col sched-col--act">操作</span>
        </div>
        ${tasks.map(t => html`
          <div class="sched-row" style="cursor:pointer;" @click=${(e) => {
            if (e.target.closest('button')) return;
            _expandedTaskId = _expandedTaskId === t.id ? null : t.id;
            app.requestUpdate();
          }}>
            <span class="sched-col sched-col--id mono">${t.id || "—"}</span>
            <span class="sched-col sched-col--name" title="${t.content || ''}">${(t.content || "—").substring(0, 80)}</span>
            <span class="sched-col sched-col--pri">${_priorityBadge(t.priority)}</span>
            <span class="sched-col sched-col--status">${_statusBadge(t.status)}</span>
            <span class="sched-col sched-col--src">${t.source || "—"}</span>
            <span class="sched-col sched-col--time">${_formatTime(t.created_at)}</span>
            <span class="sched-col sched-col--act">
              <button class="btn btn--sm btn--icon btn--danger" title="删除"
                @click=${() => _deleteTask(t.id, app)}>${icons.trash}</button>
            </span>
          </div>
          ${_expandedTaskId === t.id ? html`
            <div style="padding:12px 16px;background:var(--bg-2);border-bottom:1px solid var(--border);font-size:12px;line-height:1.7;">
              <div style="display:grid;grid-template-columns:80px 1fr;gap:4px 12px;">
                <span style="color:var(--fg-3);font-weight:600;">完整内容</span>
                <span style="white-space:pre-wrap;word-break:break-all;">${t.content || "—"}</span>
                <span style="color:var(--fg-3);font-weight:600;">任务类型</span>
                <span>${t.type || "task"}</span>
                <span style="color:var(--fg-3);font-weight:600;">创建时间</span>
                <span>${_formatTime(t.created_at)}</span>
                ${t.running_at ? html`
                  <span style="color:var(--fg-3);font-weight:600;">开始执行</span>
                  <span>${_formatTime(t.running_at)}</span>
                ` : nothing}
                ${t.completed_at ? html`
                  <span style="color:var(--fg-3);font-weight:600;">完成时间</span>
                  <span>${_formatTime(t.completed_at)}</span>
                ` : nothing}
                ${t.last_error ? html`
                  <span style="color:var(--danger,#ef4444);font-weight:600;">错误信息</span>
                  <span style="color:var(--danger,#ef4444);">${t.last_error}</span>
                ` : nothing}
                <span style="color:var(--fg-3);font-weight:600;">重试次数</span>
                <span>${t.retries || 0} / ${t.max_retries || 3}</span>
                ${t.parent_id ? html`
                  <span style="color:var(--fg-3);font-weight:600;">父任务</span>
                  <span class="mono">${t.parent_id}</span>
                ` : nothing}
              </div>
            </div>
          ` : nothing}
        `)}
      </div>
    `}
  `;
}

function _renderCronTab(app) {
  return html`
    ${(() => {
      const atJobs = _cronJobs.filter(j => j.type === 'at' && j.enabled);
      const everyJobs = _cronJobs.filter(j => j.type !== 'at' || !j.enabled || j.status === 'fired');
      const firedJobs = _cronJobs.filter(j => j.type === 'at' && j.status === 'fired');
      if (atJobs.length > 0) _startCountdown(app);
      return html`
        ${atJobs.length > 0 ? html`
          <div style="margin-bottom:16px;">
            <div style="font-size:13px;font-weight:600;color:var(--fg);margin-bottom:8px;padding:0 4px;">⏰ 待触发提醒 (${atJobs.length})</div>
            ${atJobs.map(j => {
              const countdown = _formatCountdownReminder(j.trigger_at);
              const isUrgent = j.trigger_at && (new Date(j.trigger_at).getTime() - Date.now()) < 10000;
              return html`
                <div style="padding:10px 14px;background:var(--bg-2);border-radius:8px;margin-bottom:8px;display:flex;align-items:center;gap:12px;
                  ${isUrgent ? 'border:1px solid var(--accent);' : ''}">
                  <span style="font-size:20px;">⏰</span>
                  <div style="flex:1;">
                    <div style="font-size:13px;font-weight:500;color:var(--fg);">${j.command || j.description || '—'}</div>
                    <div style="font-size:11px;color:var(--fg-3);margin-top:2px;">
                      触发: ${j.trigger_at ? new Date(j.trigger_at).toLocaleTimeString("zh-CN", {hour:"2-digit",minute:"2-digit",second:"2-digit"}) : "—"}
                      · ID: ${j.id || ''}
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <div style="font-size:18px;font-weight:700;font-family:monospace;color:${isUrgent ? 'var(--danger,#ef4444)' : 'var(--accent)'};
                      ${isUrgent ? 'animation:pulse 1s infinite;' : ''}">
                      ${countdown}
                    </div>
                    <div style="font-size:10px;color:var(--fg-3);margin-top:2px;">倒计时</div>
                  </div>
                  <button class="btn btn--sm btn--icon btn--danger" title="删除" style="margin-left:8px;"
                    @click=${() => _deleteCronJob(j.id, app)}>${icons.trash}</button>
                </div>`;
            })}
          </div>
        ` : nothing}
        ${firedJobs.length > 0 ? html`
          <div style="margin-bottom:16px;">
            <div style="font-size:13px;font-weight:600;color:var(--fg-3);margin-bottom:8px;padding:0 4px;">✅ 已触发 (${firedJobs.length})</div>
            ${firedJobs.slice(-3).map(j => html`
              <div style="padding:8px 14px;background:var(--bg-2);border-radius:8px;margin-bottom:6px;display:flex;align-items:center;gap:10px;opacity:0.6;">
                <span>✅</span>
                <span style="font-size:12px;flex:1;">${j.command || j.description || '—'}</span>
                <span style="font-size:11px;color:var(--fg-3);">${j.last_run ? _formatTime(j.last_run) : ''}</span>
                <button class="btn btn--sm btn--icon btn--danger" title="删除" style="opacity:1;"
                  @click=${() => _deleteCronJob(j.id, app)}>${icons.trash}</button>
              </div>
            `)}
          </div>
        ` : nothing}
        ${everyJobs.filter(j => j.type !== 'at').length === 0 && atJobs.length === 0 && firedJobs.length === 0 ? html`
          <p class="text-muted" style="padding:24px;text-align:center;">暂无定时任务</p>
        ` : nothing}
      `;
    })()}
    ${(() => {
      const schedJobs = _cronJobs.filter(j => j.type !== 'at');
      if (schedJobs.length === 0) return nothing;
      return html`
        <div style="margin-bottom:16px;">
          <div style="font-size:13px;font-weight:600;color:var(--fg);margin-bottom:8px;padding:0 4px;">📅 定时日程 (${schedJobs.length})</div>
          ${schedJobs.map(job => html`
            <div style="padding:12px 14px;background:var(--bg-2);border-radius:8px;margin-bottom:8px;">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                <span style="font-size:18px;">${job.type === 'cron' ? '🗓️' : '🔄'}</span>
                <div style="flex:1;">
                  <div style="font-size:13px;font-weight:600;color:var(--fg);">${job.name || job.description || '未命名'}</div>
                  <div style="font-size:11px;color:var(--fg-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:500px;"
                    title="${job.command || ''}">${job.command || '—'}</div>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                  ${job.enabled !== false
                    ? html`<span class="sched-badge badge--ok" style="font-size:10px;">启用</span>`
                    : html`<span class="sched-badge badge--muted" style="font-size:10px;">禁用</span>`}
                  <button class="btn btn--sm btn--icon btn--danger" title="删除"
                    @click=${() => _deleteCronJob(job.id, app)}>${icons.trash}</button>
                </div>
              </div>
              <div style="display:flex;gap:16px;font-size:11px;color:var(--fg-3);padding-left:28px;flex-wrap:wrap;">
                <span>📋 <b style="color:var(--fg);">${_scheduleLabel(job)}</b></span>
                <span>▶ 已执行 <b style="color:var(--fg);">${job.run_count || 0}</b> 次</span>
                <span>⏱ 上次: <b style="color:var(--fg);">${job.last_run ? _formatTime(job.last_run) : '未运行'}</b></span>
                <span style="margin-left:auto;">下次: <b style="color:var(--accent);">${_formatNextRun(job)}</b></span>
              </div>
              ${(job.runs && job.runs.length > 0) ? html`
                <details style="margin-top:8px;padding-left:28px;">
                  <summary style="font-size:11px;color:var(--fg-3);cursor:pointer;user-select:none;">📜 执行记录 (${job.runs.length})</summary>
                  <div style="margin-top:6px;max-height:200px;overflow-y:auto;">
                    ${job.runs.slice().reverse().map(r => html`
                      <div style="padding:6px 10px;background:var(--bg);border-radius:6px;margin-bottom:4px;font-size:11px;">
                        <div style="display:flex;gap:8px;align-items:center;margin-bottom:3px;">
                          <span>${r.status === 'ok' ? '✅' : '❌'}</span>
                          <span style="color:var(--fg-3);">${r.ts ? new Date(r.ts * 1000).toLocaleString("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}) : '—'}</span>
                          ${r.tools && r.tools.length > 0 ? html`<span style="color:var(--accent);font-size:10px;">🔧 ${r.tools.length}个工具</span>` : nothing}
                        </div>
                        <div style="color:var(--fg);white-space:pre-wrap;word-break:break-word;max-height:80px;overflow:hidden;">${(r.result || '').substring(0, 200)}</div>
                      </div>
                    `)}
                  </div>
                </details>
              ` : nothing}
            </div>
          `)}
        </div>
      `;
    })()}
  `;
}

export function renderTasksPage(app) {
  _taskUpdateApp = app;
  if (_lastRefresh === 0) {
    _lastRefresh = -1;
    _refresh().then(() => app.requestUpdate());
  }

  const activeCount = (_dispatcherData.tasks || []).filter(t => ["ready", "running", "blocked"].includes(t.status)).length;
  const atJobCount = _cronJobs.filter(j => j.type === 'at' && j.enabled).length;
  const cronCount = _cronJobs.filter(j => j.type !== 'at').length + atJobCount;
  const tabs = [
    { key: "cron", label: "定时任务", icon: icons.clock, count: cronCount },
    { key: "queue", label: "任务队列", icon: icons.tasks, count: activeCount },
  ];

  return html`
    <div class="sched-page">
      <div class="sched-tabs">
        ${tabs.map(t => html`
          <button class="sched-tab ${_activeTab === t.key ? 'sched-tab--active' : ''}"
            @click=${() => { _activeTab = t.key; app.requestUpdate(); }}>
            <span class="sched-tab__icon">${t.icon}</span>
            <span>${t.label}</span>
            ${t.count > 0 ? html`<span class="sched-tab__count">${t.count}</span>` : nothing}
          </button>
        `)}
        <div class="sched-tabs__spacer"></div>
        <button class="btn btn--sm btn--primary" style="font-size:11px;padding:4px 10px;"
          @click=${() => { _showNewTask = !_showNewTask; app.requestUpdate(); }}>
          ＋ 新建任务
        </button>
        <button class="btn btn--sm" @click=${async () => { await _refresh(); app.requestUpdate(); }}>
          ${icons.refresh}
        </button>
        <span class="text-muted" style="font-size:11px;">
          ${_lastRefresh ? new Date(_lastRefresh).toLocaleTimeString() : "..."}
        </span>
      </div>
      ${_showNewTask ? html`
        <div style="padding:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;margin:8px 0;">
          <div style="display:flex;gap:8px;margin-bottom:10px;">
            <select id="new-task-type" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:12px;min-width:120px;"
              @change=${() => app.requestUpdate()}>
              <option value="task">一次性任务</option>
              <option value="cron">定时日程（cron）</option>
            </select>
            <input type="text" id="new-task-content" style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;"
              placeholder="${document.getElementById('new-task-type')?.value === 'cron' ? '任务描述，如：每日早报' : '输入任务内容...'}"
              @keydown=${(e) => { if (e.key === 'Enter') _createNewItem(app); }}>
          </div>
          ${document.getElementById('new-task-type')?.value === 'cron' ? html`
            <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;">
              <select id="new-cron-preset" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:12px;"
                @change=${(e) => { const expr = document.getElementById('new-cron-expr'); if (expr && e.target.value) expr.value = e.target.value; }}>
                <option value="">选择预设...</option>
                <option value="0 8 * * *">每天 08:00</option>
                <option value="0 9 * * *">每天 09:00</option>
                <option value="0 12 * * *">每天 12:00</option>
                <option value="0 18 * * *">每天 18:00</option>
                <option value="0 22 * * *">每天 22:00</option>
                <option value="0 8 * * 1-5">工作日 08:00</option>
                <option value="0 */2 * * *">每2小时</option>
                <option value="0 8 * * 1">每周一 08:00</option>
              </select>
              <input type="text" id="new-cron-expr" placeholder="cron表达式 (分 时 日 月 周)" value="0 8 * * *"
                style="width:200px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:12px;font-family:monospace;">
              <span style="font-size:11px;color:var(--fg-3);">如: 0 8 * * * = 每天8点</span>
            </div>
            <div style="display:flex;gap:8px;margin-bottom:10px;">
              <textarea id="new-cron-command" placeholder="要执行的指令，如：搜索今天最新的时事新闻和小红书热门话题，整理后告诉我" rows="2"
                style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;resize:vertical;font-family:inherit;"></textarea>
            </div>
          ` : html`
            <div style="display:flex;gap:8px;margin-bottom:10px;">
              <select id="new-task-priority" style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:12px;">
                <option value="P0">P0 (紧急)</option>
                <option value="P1">P1 (高)</option>
                <option value="P2" selected>P2 (普通)</option>
                <option value="P3">P3 (低)</option>
              </select>
            </div>
          `}
          <div style="display:flex;gap:8px;justify-content:flex-end;">
            <button class="btn" style="font-size:12px;"
              @click=${() => { _showNewTask = false; app.requestUpdate(); }}>取消</button>
            <button class="btn btn--primary" style="font-size:12px;" ?disabled=${_creating}
              @click=${() => _createNewItem(app)}>${_creating ? "创建中..." : "创建"}</button>
          </div>
        </div>
      ` : nothing}
      <div class="card" style="margin-top:0;border-top-left-radius:0;border-top-right-radius:0;">
        ${_activeTab === "cron" ? _renderCronTab(app) : nothing}
        ${_activeTab === "queue" ? _renderQueueTab(app) : nothing}
      </div>
    </div>
  `;
}
