/**
 * Token Dashboard — 实时 token 使用量看板
 *
 * 功能：
 * - 实时 token 消耗统计（今日/本小时/总量）
 * - 24小时趋势图（ASCII柱状图）
 * - 模型分布（各模型 token 占比）
 * - 最近调用记录
 * - 预算配置（上限/阈值/自动切换）
 */
import { html, nothing } from "lit";
import * as api from "../api.js";

let _tokenData = null;
let _tokenLoading = false;
let _refreshTimer = null;
let _configEditing = false;

function _loadTokenData(app) {
  if (_tokenLoading) return;
  _tokenLoading = true;
  api.getTokenStats().then(d => {
    _tokenData = d;
    _tokenLoading = false;
    app.requestUpdate();
  }).catch(() => { _tokenLoading = false; });
}

function _startAutoRefresh(app) {
  if (_refreshTimer) return;
  _refreshTimer = setInterval(() => _loadTokenData(app), 5000);
}

function _stopAutoRefresh() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

function _formatTokens(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function _renderStatCards(data) {
  const cards = [
    { label: "今日消耗", value: _formatTokens(data.today_tokens), sub: "tokens", color: "var(--accent)" },
    { label: "本小时", value: _formatTokens(data.this_hour_tokens), sub: "tokens", color: "var(--ok)" },
    { label: "总调用", value: String(data.total_calls), sub: "次", color: "var(--warn)" },
    { label: "均值/次", value: _formatTokens(data.avg_tokens_per_call), sub: "tok/call", color: "var(--danger,#ef4444)" },
  ];
  return html`
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
      ${cards.map(c => html`
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center;">
          <div style="font-size:11px;color:var(--fg-3);text-transform:uppercase;letter-spacing:0.5px;">${c.label}</div>
          <div style="font-size:28px;font-weight:800;color:${c.color};margin:6px 0 2px;">${c.value}</div>
          <div style="font-size:11px;color:var(--fg-3);">${c.sub}</div>
        </div>
      `)}
    </div>
  `;
}

function _renderBudgetBar(data) {
  const cfg = data.config || {};
  if (!cfg.budget_enabled) return nothing;
  const pct = Math.min(data.budget_used_pct, 100);
  const color = pct >= 95 ? "var(--danger,#ef4444)" : pct >= 80 ? "var(--warn,#f59e0b)" : "var(--ok,#22c55e)";
  return html`
    <div style="margin-bottom:16px;background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-weight:700;font-size:14px;color:var(--fg);">📊 Token 预算</span>
        <span style="font-size:12px;color:${color};font-weight:700;">${pct.toFixed(1)}% 已用</span>
      </div>
      <div style="height:12px;background:var(--bg-3,#334155);border-radius:6px;overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:6px;transition:width 0.5s;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:var(--fg-3);">
        <span>${_formatTokens(data.today_tokens)} / ${_formatTokens(cfg.max_tokens_per_day)}</span>
        <span>⚠️ ${cfg.warn_threshold_pct}% | 🔄 ${cfg.auto_switch_threshold_pct}%</span>
      </div>
    </div>
  `;
}

function _renderHourlyChart(data) {
  const trend = data.hourly_trend || [];
  if (!trend.length) return nothing;
  const max = Math.max(...trend.map(t => t.tokens), 1);
  return html`
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">📈 24小时趋势</div>
      <div style="display:flex;align-items:flex-end;gap:2px;height:100px;padding:8px 0;">
        ${trend.map(t => {
          const h = Math.max((t.tokens / max) * 80, 2);
          const isNow = trend.indexOf(t) === trend.length - 1;
          return html`
            <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;">
              <div style="font-size:9px;color:var(--fg-3);">${t.tokens > 0 ? _formatTokens(t.tokens) : ''}</div>
              <div style="width:100%;height:${h}px;background:${isNow ? 'var(--accent)' : 'var(--accent)44'};border-radius:3px 3px 0 0;min-width:8px;" title="${t.hour}: ${_formatTokens(t.tokens)}"></div>
              <div style="font-size:8px;color:var(--fg-3);${trend.indexOf(t) % 3 === 0 ? '' : 'visibility:hidden;'}">${t.hour?.split(':')[0]}</div>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}

function _renderDailyChart(data) {
  const trend = data.daily_trend || [];
  if (!trend.length) return nothing;
  const max = Math.max(...trend.map(t => t.tokens), 1);
  return html`
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">📅 7天趋势</div>
      <div style="display:flex;align-items:flex-end;gap:6px;height:80px;padding:8px 0;">
        ${trend.map(t => {
          const h = Math.max((t.tokens / max) * 60, 2);
          return html`
            <div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;">
              <div style="font-size:10px;color:var(--fg-3);font-weight:600;">${_formatTokens(t.tokens)}</div>
              <div style="width:100%;height:${h}px;background:var(--ok,#22c55e)55;border-radius:4px 4px 0 0;min-width:20px;" title="${t.date}: ${_formatTokens(t.tokens)}"></div>
              <div style="font-size:10px;color:var(--fg-3);">${t.date?.slice(5)}</div>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}

function _renderModelBreakdown(data) {
  const models = data.model_breakdown || [];
  if (!models.length) return nothing;
  const total = models.reduce((s, m) => s + m.total_tokens, 0) || 1;
  const colors = ["var(--accent)", "var(--ok)", "var(--warn)", "var(--danger,#ef4444)", "#a855f7", "#ec4899"];
  return html`
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">🔧 模型分布</div>
      <!-- 比例条 -->
      <div style="display:flex;height:16px;border-radius:8px;overflow:hidden;margin-bottom:12px;">
        ${models.map((m, i) => html`
          <div style="width:${(m.total_tokens / total * 100).toFixed(1)}%;background:${colors[i % colors.length]};" title="${m.model}: ${_formatTokens(m.total_tokens)}"></div>
        `)}
      </div>
      <!-- 详情表 -->
      <div style="display:flex;flex-direction:column;gap:6px;">
        ${models.map((m, i) => html`
          <div style="display:flex;align-items:center;gap:8px;font-size:12px;">
            <span style="width:8px;height:8px;border-radius:50%;background:${colors[i % colors.length]};flex-shrink:0;"></span>
            <span style="font-weight:600;color:var(--fg);min-width:140px;">${m.model}</span>
            <span style="color:var(--fg-3);min-width:80px;">${_formatTokens(m.total_tokens)}</span>
            <span style="color:var(--fg-3);min-width:60px;">${m.call_count}次</span>
            <span style="color:var(--fg-3);font-size:11px;">avg: ${_formatTokens(m.avg_prompt)}p + ${_formatTokens(m.avg_completion)}c</span>
            <span style="color:var(--fg-3);font-size:11px;margin-left:auto;">${(m.total_tokens / total * 100).toFixed(1)}%</span>
          </div>
        `)}
      </div>
    </div>
  `;
}

function _renderRecentCalls(data) {
  const calls = data.recent_calls || [];
  if (!calls.length) return nothing;
  return html`
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">🕐 最近调用 (${calls.length})</div>
      <div style="max-height:200px;overflow-y:auto;">
        ${calls.map(c => {
          const dt = new Date(c.timestamp * 1000);
          const time = dt.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
          return html`
            <div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);font-size:11px;">
              <span style="color:var(--fg-3);min-width:60px;">${time}</span>
              <span style="font-weight:600;color:var(--fg);min-width:120px;">${c.model}</span>
              <span style="color:var(--accent);min-width:50px;">${_formatTokens(c.prompt_tokens)}p</span>
              <span style="color:var(--ok);min-width:50px;">${_formatTokens(c.completion_tokens)}c</span>
              <span style="color:var(--fg-3);">${_formatTokens(c.total_tokens)} total</span>
            </div>
          `;
        })}
      </div>
    </div>
  `;
}

function _renderBudgetConfig(app, data) {
  const cfg = data.config || {};
  return html`
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;"
        @click=${() => { _configEditing = !_configEditing; app.requestUpdate(); }}>
        <span>⚙️ 预算配置</span>
        <span style="font-size:12px;color:var(--fg-3);transform:rotate(${_configEditing ? '90deg' : '0deg'});transition:transform .2s;">&#9654;</span>
      </div>
      ${_configEditing ? html`
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">启用预算</label>
            <select class="form-select" id="tc-enabled" style="font-size:12px;">
              <option value="true" ?selected=${cfg.budget_enabled}>启用</option>
              <option value="false" ?selected=${!cfg.budget_enabled}>停用</option>
            </select>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">每日上限</label>
            <input class="form-input" type="number" id="tc-daily" value="${cfg.max_tokens_per_day || 500000}" style="font-size:12px;width:120px;" />
            <span style="font-size:11px;color:var(--fg-3);">tokens</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">每小时上限</label>
            <input class="form-input" type="number" id="tc-hourly" value="${cfg.max_tokens_per_hour || 100000}" style="font-size:12px;width:120px;" />
            <span style="font-size:11px;color:var(--fg-3);">tokens</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">警告阈值</label>
            <input class="form-input" type="number" id="tc-warn" value="${cfg.warn_threshold_pct || 80}" min="10" max="100" step="5" style="font-size:12px;width:80px;" />
            <span style="font-size:11px;color:var(--fg-3);">%</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">自动切换阈值</label>
            <input class="form-input" type="number" id="tc-switch" value="${cfg.auto_switch_threshold_pct || 95}" min="50" max="100" step="5" style="font-size:12px;width:80px;" />
            <span style="font-size:11px;color:var(--fg-3);">% 时自动切换模型</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">切换目标</label>
            <input class="form-input" type="text" id="tc-target" value="${cfg.auto_switch_target || ''}" placeholder="local 或 provider/model" style="font-size:12px;flex:1;" />
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;font-weight:600;min-width:120px;">到限时暂停</label>
            <select class="form-select" id="tc-pause" style="font-size:12px;">
              <option value="true" ?selected=${cfg.pause_at_limit}>暂停（不再调用）</option>
              <option value="false" ?selected=${!cfg.pause_at_limit}>切换模型</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;margin-top:4px;">
            <button class="btn btn--primary" style="font-size:12px;" @click=${async () => {
              const config = {
                budget_enabled: document.getElementById("tc-enabled").value === "true",
                max_tokens_per_day: parseInt(document.getElementById("tc-daily").value) || 500000,
                max_tokens_per_hour: parseInt(document.getElementById("tc-hourly").value) || 100000,
                warn_threshold_pct: parseFloat(document.getElementById("tc-warn").value) || 80,
                auto_switch_threshold_pct: parseFloat(document.getElementById("tc-switch").value) || 95,
                auto_switch_target: document.getElementById("tc-target").value.trim(),
                pause_at_limit: document.getElementById("tc-pause").value === "true",
              };
              await api.updateTokenConfig(config);
              _tokenData = null;
              _loadTokenData(app);
            }}>保存配置</button>
            <button class="btn" style="font-size:12px;" @click=${async () => {
              await api.resetTokenStats();
              _tokenData = null;
              _loadTokenData(app);
            }}>重置今日统计</button>
          </div>
        </div>
      ` : html`
        <div style="font-size:12px;color:var(--fg-3);margin-top:4px;">
          预算: ${cfg.budget_enabled ? '已启用' : '未启用'}
          | 日限: ${_formatTokens(cfg.max_tokens_per_day || 0)}
          | 警告: ${cfg.warn_threshold_pct || 80}%
          | 自动切换: ${cfg.auto_switch_threshold_pct || 95}%
        </div>
      `}
    </div>
  `;
}

export function renderTokens(app) {
  _startAutoRefresh(app);
  if (!_tokenData) {
    _loadTokenData(app);
    return html`<p style="color:var(--fg-3);font-size:13px;">加载 token 统计...</p>`;
  }
  return html`
    ${_renderStatCards(_tokenData)}
    ${_renderBudgetBar(_tokenData)}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div>${_renderHourlyChart(_tokenData)}</div>
      <div>${_renderDailyChart(_tokenData)}</div>
    </div>
    ${_renderModelBreakdown(_tokenData)}
    ${_renderRecentCalls(_tokenData)}
    ${_renderBudgetConfig(app, _tokenData)}
  `;
}
