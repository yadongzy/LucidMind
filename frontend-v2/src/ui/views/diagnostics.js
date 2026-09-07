/**
 * Diagnostics view — 系统诊断面板（事件查询 + 摘要统计 + 时间线）
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";

let _summary = null;
let _events = null;
let _timeline = null;
let _loading = false;
let _lastRefresh = 0;
let _activeTab = "summary";
let _diagRunning = false;
let _diagResult = null;
let _filterCategory = "";
let _filterStatus = "";
let _filterMinutes = 60;
let _expandedIdx = null;

async function _refresh() {
  if (_loading) return;
  _loading = true;
  try {
    const [sumRes, evtRes, tlRes] = await Promise.all([
      fetch("/api/diagnostics/summary?hours=24").then(r => r.ok ? r.json() : {}),
      fetch(`/api/diagnostics?minutes=${_filterMinutes}&limit=100${_filterCategory ? '&category=' + _filterCategory : ''}${_filterStatus ? '&status=' + _filterStatus : ''}`).then(r => r.ok ? r.json() : { events: [] }),
      fetch(`/api/diagnostics/timeline?minutes=${_filterMinutes}`).then(r => r.ok ? r.json() : { buckets: [] }),
    ]);
    _summary = sumRes;
    _events = evtRes.events || [];
    _timeline = tlRes.buckets || [];
    _lastRefresh = Date.now();
  } catch (e) {
    console.error("诊断数据加载失败:", e);
  } finally {
    _loading = false;
  }
}

function _formatTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function _formatDuration(ms) {
  if (ms < 1) return "<1ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function _statusColor(status) {
  const map = {
    success: "var(--green, #22c55e)",
    failure: "var(--danger, #ef4444)",
    error: "var(--danger, #ef4444)",
    timeout: "var(--warn, #f59e0b)",
    blocked: "var(--warn, #f59e0b)",
    skipped: "var(--fg-3, #888)",
  };
  return map[status] || "var(--fg-3)";
}

function _statusIcon(status) {
  const map = { success: "✅", failure: "❌", error: "❌", timeout: "⏱", blocked: "🔒", skipped: "⏭" };
  return map[status] || "●";
}

function _categoryLabel(cat) {
  const map = {
    tool_call: "工具调用",
    plugin_load: "插件加载",
    mcp_request: "MCP请求",
    security_check: "安全检查",
    brain_process: "大脑处理",
    api_request: "API请求",
  };
  return map[cat] || cat;
}

function _renderSummaryTab() {
  if (!_summary || !_summary.categories) {
    return html`<p class="text-muted" style="padding:24px;text-align:center;">暂无诊断数据</p>`;
  }
  const cats = _summary.categories;
  const catKeys = Object.keys(cats);
  if (catKeys.length === 0) {
    return html`<p class="text-muted" style="padding:24px;text-align:center;">暂无诊断数据</p>`;
  }

  const totalEvents = _summary.total || 0;
  const totalSuccess = catKeys.reduce((s, k) => s + (cats[k].success || 0), 0);
  const totalFailure = catKeys.reduce((s, k) => s + (cats[k].failure || 0), 0);
  const overallRate = totalEvents > 0 ? (totalSuccess / totalEvents * 100).toFixed(1) : "—";

  return html`
    <!-- 总览卡片 -->
    <div class="card-grid" style="margin-bottom:16px;">
      <div class="stat">
        <div class="stat-label">总事件数</div>
        <div class="stat-value">${totalEvents}</div>
        <div class="stat-sub">过去24小时</div>
      </div>
      <div class="stat">
        <div class="stat-label">成功率</div>
        <div class="stat-value" style="color:${parseFloat(overallRate) >= 90 ? 'var(--green,#22c55e)' : parseFloat(overallRate) >= 70 ? 'var(--warn,#f59e0b)' : 'var(--danger,#ef4444)'};">${overallRate}%</div>
        <div class="stat-sub">${totalSuccess} 成功 / ${totalFailure} 失败</div>
      </div>
      <div class="stat">
        <div class="stat-label">类别数</div>
        <div class="stat-value">${catKeys.length}</div>
      </div>
    </div>

    <!-- 各类别详情 -->
    ${catKeys.map(cat => {
      const c = cats[cat];
      const rate = c.total > 0 ? (c.success / c.total * 100).toFixed(1) : "0";
      const rateColor = parseFloat(rate) >= 90 ? 'var(--green,#22c55e)' : parseFloat(rate) >= 70 ? 'var(--warn,#f59e0b)' : 'var(--danger,#ef4444)';
      return html`
        <div style="padding:14px 16px;background:var(--bg-2);border-radius:8px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
            <span style="font-size:14px;font-weight:600;color:var(--fg);">${_categoryLabel(cat)}</span>
            <span style="font-size:13px;font-weight:700;color:${rateColor};">${rate}%</span>
          </div>
          <div style="display:flex;gap:16px;font-size:12px;color:var(--fg-3);flex-wrap:wrap;">
            <span>📊 总计 <b style="color:var(--fg);">${c.total}</b></span>
            <span>✅ 成功 <b style="color:var(--green,#22c55e);">${c.success}</b></span>
            <span>❌ 失败 <b style="color:var(--danger,#ef4444);">${c.failure}</b></span>
            <span>⏱ 平均 <b style="color:var(--fg);">${_formatDuration(c.avg_duration_ms)}</b></span>
            <span>P50 <b style="color:var(--fg);">${_formatDuration(c.p50_duration_ms)}</b></span>
            <span>P95 <b style="color:var(--fg);">${_formatDuration(c.p95_duration_ms)}</b></span>
          </div>
          <!-- 成功率进度条 -->
          <div style="margin-top:8px;height:4px;background:var(--border);border-radius:2px;overflow:hidden;">
            <div style="height:100%;width:${rate}%;background:${rateColor};border-radius:2px;transition:width 0.3s;"></div>
          </div>
        </div>`;
    })}
  `;
}

function _renderTimelineTab() {
  if (!_timeline || _timeline.length === 0) {
    return html`<p class="text-muted" style="padding:24px;text-align:center;">暂无时间线数据</p>`;
  }

  const maxTotal = Math.max(..._timeline.map(b => b.total), 1);

  return html`
    <div style="padding:8px 0;">
      <div style="font-size:12px;color:var(--fg-3);margin-bottom:12px;">
        最近 ${_filterMinutes} 分钟 · 每分钟聚合 · 共 ${_timeline.length} 个数据点
      </div>
      <div style="display:flex;align-items:flex-end;gap:2px;height:120px;padding:0 4px;">
        ${_timeline.map(b => {
          const h = Math.max(4, (b.total / maxTotal) * 100);
          const failH = b.total > 0 ? (b.failure / b.total) * h : 0;
          const succH = h - failH;
          const time = _formatTs(b.timestamp);
          return html`
            <div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%;min-width:3px;max-width:12px;" title="${time}: ${b.total}事件 (${b.success}成功, ${b.failure}失败)">
              ${failH > 0 ? html`<div style="height:${failH}%;background:var(--danger,#ef4444);border-radius:2px 2px 0 0;min-height:2px;"></div>` : nothing}
              <div style="height:${succH}%;background:var(--green,#22c55e);border-radius:${failH > 0 ? '0' : '2px 2px'} 0 0;min-height:2px;"></div>
            </div>`;
        })}
      </div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--fg-3);margin-top:4px;padding:0 4px;">
        <span>${_timeline.length > 0 ? _formatTs(_timeline[0].timestamp) : ''}</span>
        <span>
          <span style="display:inline-block;width:8px;height:8px;background:var(--green,#22c55e);border-radius:2px;margin-right:2px;"></span>成功
          <span style="display:inline-block;width:8px;height:8px;background:var(--danger,#ef4444);border-radius:2px;margin:0 2px 0 8px;"></span>失败
        </span>
        <span>${_timeline.length > 0 ? _formatTs(_timeline[_timeline.length - 1].timestamp) : ''}</span>
      </div>
    </div>
  `;
}

function _renderEventsTab(app) {
  if (!_events || _events.length === 0) {
    return html`<p class="text-muted" style="padding:24px;text-align:center;">暂无事件记录</p>`;
  }

  const categories = [...new Set(_events.map(e => e.category))];

  return html`
    <!-- 过滤器 -->
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
      <select style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-2);color:var(--fg);font-size:12px;"
        @change=${(e) => { _filterCategory = e.target.value; _events = null; _refresh().then(() => app.requestUpdate()); }}>
        <option value="">全部类别</option>
        ${categories.map(c => html`<option value="${c}" ?selected=${_filterCategory === c}>${_categoryLabel(c)}</option>`)}
      </select>
      <select style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-2);color:var(--fg);font-size:12px;"
        @change=${(e) => { _filterStatus = e.target.value; _events = null; _refresh().then(() => app.requestUpdate()); }}>
        <option value="">全部状态</option>
        <option value="success" ?selected=${_filterStatus === "success"}>成功</option>
        <option value="failure" ?selected=${_filterStatus === "failure"}>失败</option>
        <option value="timeout" ?selected=${_filterStatus === "timeout"}>超时</option>
        <option value="blocked" ?selected=${_filterStatus === "blocked"}>拦截</option>
      </select>
      <select style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-2);color:var(--fg);font-size:12px;"
        @change=${(e) => { _filterMinutes = parseInt(e.target.value); _events = null; _refresh().then(() => app.requestUpdate()); }}>
        <option value="15" ?selected=${_filterMinutes === 15}>15分钟</option>
        <option value="60" ?selected=${_filterMinutes === 60}>1小时</option>
        <option value="360" ?selected=${_filterMinutes === 360}>6小时</option>
        <option value="1440" ?selected=${_filterMinutes === 1440}>24小时</option>
      </select>
      <span class="text-muted" style="font-size:11px;margin-left:auto;">${_events.length} 条记录</span>
    </div>

    <!-- 事件列表 -->
    <div style="max-height:500px;overflow-y:auto;">
      ${_events.slice().reverse().map((e, i) => html`
        <div style="padding:8px 12px;background:var(--bg-2);border-radius:6px;margin-bottom:4px;cursor:pointer;border-left:3px solid ${_statusColor(e.status)};"
          @click=${() => { _expandedIdx = _expandedIdx === i ? null : i; app.requestUpdate(); }}>
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:12px;">${_statusIcon(e.status)}</span>
            <span style="font-size:12px;font-weight:600;color:var(--fg);min-width:70px;">${_categoryLabel(e.category)}</span>
            <span style="font-size:12px;color:var(--fg-2);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${e.action}${e.input_summary ? ` · ${e.input_summary.substring(0, 60)}` : ''}
            </span>
            <span style="font-size:11px;color:var(--fg-3);font-family:monospace;white-space:nowrap;">${_formatDuration(e.duration_ms)}</span>
            <span style="font-size:11px;color:var(--fg-3);font-family:monospace;white-space:nowrap;">${_formatTs(e.timestamp)}</span>
          </div>
          ${_expandedIdx === i ? html`
            <div style="margin-top:8px;padding:8px 10px;background:var(--bg);border-radius:4px;font-size:12px;line-height:1.7;">
              <div style="display:grid;grid-template-columns:80px 1fr;gap:4px 12px;">
                <span style="color:var(--fg-3);font-weight:600;">类别</span>
                <span>${e.category}</span>
                <span style="color:var(--fg-3);font-weight:600;">操作</span>
                <span>${e.action}</span>
                <span style="color:var(--fg-3);font-weight:600;">状态</span>
                <span style="color:${_statusColor(e.status)};">${e.status}</span>
                <span style="color:var(--fg-3);font-weight:600;">耗时</span>
                <span>${_formatDuration(e.duration_ms)}</span>
                <span style="color:var(--fg-3);font-weight:600;">级别</span>
                <span>${e.level || 'info'}</span>
                ${e.input_summary ? html`
                  <span style="color:var(--fg-3);font-weight:600;">输入</span>
                  <span style="word-break:break-all;">${e.input_summary}</span>
                ` : nothing}
                ${e.output_summary ? html`
                  <span style="color:var(--fg-3);font-weight:600;">输出</span>
                  <span style="word-break:break-all;">${e.output_summary}</span>
                ` : nothing}
                ${e.error ? html`
                  <span style="color:var(--danger,#ef4444);font-weight:600;">错误</span>
                  <span style="color:var(--danger,#ef4444);word-break:break-all;">${e.error}</span>
                ` : nothing}
                ${e.metadata && Object.keys(e.metadata).length > 0 ? html`
                  <span style="color:var(--fg-3);font-weight:600;">元数据</span>
                  <span style="font-family:monospace;font-size:11px;word-break:break-all;">${JSON.stringify(e.metadata)}</span>
                ` : nothing}
              </div>
            </div>
          ` : nothing}
        </div>
      `)}
    </div>
  `;
}

export function renderDiagnostics(app) {
  if (!_summary && !_loading) {
    _refresh().then(() => app.requestUpdate());
    return html`<div class="card"><div class="card-title">加载诊断数据...</div></div>`;
  }

  const tabs = [
    { key: "summary", label: "摘要统计", icon: "📊" },
    { key: "timeline", label: "时间线", icon: "📈" },
    { key: "events", label: "事件列表", icon: "📋" },
    { key: "realtime", label: "实时日志", icon: "📡" },
  ];

  return html`
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>系统诊断</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <button class="btn btn--primary" style="font-size:12px;" ?disabled=${_diagRunning}
            @click=${async () => {
              _diagRunning = true; _diagResult = null; app.requestUpdate();
              try {
                const r = await fetch('/api/diagnostics/run', { method: 'POST' }).then(r => r.json());
                _diagResult = r;
              } catch (e) { _diagResult = { status: 'error', message: e.message }; }
              _diagRunning = false;
              _summary = null; _events = null; _timeline = null;
              await _refresh();
              app.requestUpdate();
            }}>
            ${_diagRunning ? '诊断中...' : '🩺 运行诊断'}
          </button>
          <button class="btn" style="font-size:12px;" @click=${() => { _summary = null; _events = null; _timeline = null; _refresh().then(() => app.requestUpdate()); }}>
            ${icons.refresh} 刷新
          </button>
          <span class="text-muted" style="font-size:11px;">
            ${_lastRefresh ? new Date(_lastRefresh).toLocaleTimeString() : "..."}
          </span>
        </div>
      </div>

      <!-- 诊断结果 -->
      ${_diagResult ? html`
        <div style="margin:12px 0;padding:10px 14px;border-radius:8px;font-size:13px;
          background:${_diagResult.status === 'ok' && _diagResult.count === 0 ? 'var(--green,#22c55e)11' : _diagResult.status === 'ok' ? 'var(--warn,#f59e0b)11' : 'var(--danger,#ef4444)11'};
          border:1px solid ${_diagResult.status === 'ok' && _diagResult.count === 0 ? 'var(--green,#22c55e)33' : _diagResult.status === 'ok' ? 'var(--warn,#f59e0b)33' : 'var(--danger,#ef4444)33'};">
          ${_diagResult.status === 'ok'
            ? (_diagResult.count === 0
              ? html`<span style="color:var(--green,#22c55e);font-weight:600;">✅ 系统诊断通过，未发现问题</span>`
              : html`<div><span style="color:var(--warn,#f59e0b);font-weight:600;">⚠️ 发现 ${_diagResult.count} 个问题：</span>
                  ${(_diagResult.issues || []).map(iss => html`<div style="margin:4px 0 0 16px;font-size:12px;">• ${iss.description || JSON.stringify(iss)}</div>`)}</div>`)
            : html`<span style="color:var(--danger,#ef4444);">❌ 诊断失败: ${_diagResult.message || '未知错误'}</span>`}
          <button class="btn btn--sm" style="font-size:10px;margin-left:8px;float:right;" @click=${() => { _diagResult = null; app.requestUpdate(); }}>✕</button>
        </div>
      ` : nothing}

      <!-- Tab 切换 -->
      <div style="display:flex;gap:4px;margin:12px 0;border-bottom:1px solid var(--border);padding-bottom:8px;">
        ${tabs.map(t => html`
          <button class="btn ${_activeTab === t.key ? 'btn--primary' : ''}"
            style="font-size:12px;padding:5px 12px;"
            @click=${() => { _activeTab = t.key; app.requestUpdate(); }}>
            ${t.icon} ${t.label}
          </button>
        `)}
      </div>

      <!-- 内容区 -->
      ${_activeTab === "summary" ? _renderSummaryTab() : nothing}
      ${_activeTab === "timeline" ? _renderTimelineTab() : nothing}
      ${_activeTab === "events" ? _renderEventsTab(app) : nothing}
      ${_activeTab === "realtime" ? _renderRealtimeTab(app) : nothing}
    </div>
  `;
}

function _renderRealtimeTab(app) {
  const logs = app.eventLog || [];
  if (logs.length === 0) {
    return html`<p class="text-muted" style="padding:24px;text-align:center;">暂无实时事件</p>`;
  }
  return html`
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="text-muted" style="font-size:11px;">${logs.length} 条实时事件（本次会话）</span>
      <button class="btn btn--sm" style="font-size:11px;" @click=${() => { app.eventLog = []; app.requestUpdate(); }}>清空</button>
    </div>
    <div style="max-height:500px;overflow-y:auto;font-family:var(--mono);font-size:12px;">
      <table class="data-table">
        <thead><tr><th style="width:80px">时间</th><th style="width:70px">类型</th><th>内容</th></tr></thead>
        <tbody>
          ${logs.slice().reverse().map(e => html`
            <tr>
              <td style="color:var(--accent)">${e.time}</td>
              <td style="color:var(--warn)">${e.type}</td>
              <td>${e.msg}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  `;
}
