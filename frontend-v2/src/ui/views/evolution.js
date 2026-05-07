/**
 * Evolution Dashboard — 进化看板
 * 健康趋势、度量、进化日志、Git Hooks
 */
import { html, nothing } from "lit";
import * as api from "../api.js";

let _metrics = null, _log = null, _health = null, _targets = null;
let _loading = false, _healing = false;

async function _load(app) {
  if (_loading) return;
  _loading = true;
  try {
    const [metrics, log, health, targets] = await Promise.all([
      api.fetchEvolutionMetrics().catch(() => null),
      api.fetchEvolutionLog().catch(() => ({ beads: [], stats: {} })),
      api.fetchHealthCheck().catch(() => null),
      api.fetchEvolutionTargets().catch(() => null),
    ]);
    _metrics = metrics;
    _log = log;
    _health = health;
    _targets = targets;
  } catch (e) { /* ignore */ }
  _loading = false;
  app.requestUpdate();
}

async function _triggerHeal(app) {
  _healing = true;
  app.requestUpdate();
  try {
    const result = await api.triggerHeal();
    _health = { score: result.final_score, healthy: result.final_score >= 80 };
    await _load(app);
  } catch (e) { /* ignore */ }
  _healing = false;
  app.requestUpdate();
}

async function _installHooks(app) {
  try {
    await api.installGitHooks();
    alert("Git Hooks 安装成功！");
  } catch (e) { alert(`安装失败: ${e.message}`); }
}

const OUTCOME_STYLE = {
  success: { color: "#22c55e", icon: "✅" },
  failure: { color: "#ef4444", icon: "❌" },
  rollback: { color: "#f59e0b", icon: "🔄" },
  noop: { color: "#6b7280", icon: "⏭️" },
  pending: { color: "#3b82f6", icon: "⏳" },
};

export function renderEvolution(app) {
  if (!_metrics && !_loading) _load(app);

  return html`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">

      <!-- Health Status -->
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>💊 代码健康</span>
          <button class="btn btn--primary" style="font-size:12px;padding:6px 16px;"
            ?disabled=${_healing}
            @click=${() => _triggerHeal(app)}>
            ${_healing ? "自愈中..." : "触发自愈"}
          </button>
        </div>
        ${_health ? html`
          <div style="display:flex;align-items:center;gap:16px;margin-top:12px;">
            <div style="width:80px;height:80px;border-radius:50%;display:flex;align-items:center;justify-content:center;
              background:${_health.score >= 80 ? '#22c55e22' : _health.score >= 60 ? '#f59e0b22' : '#ef444422'};
              border:3px solid ${_health.score >= 80 ? '#22c55e' : _health.score >= 60 ? '#f59e0b' : '#ef4444'};">
              <span style="font-size:24px;font-weight:700;color:${_health.score >= 80 ? '#22c55e' : _health.score >= 60 ? '#f59e0b' : '#ef4444'};">${_health.score}</span>
            </div>
            <div>
              <div style="font-size:14px;font-weight:600;color:var(--fg);">${_health.healthy ? "✅ 健康" : "⚠️ 需要修复"}</div>
              <div style="font-size:12px;color:var(--fg-3);margin-top:4px;">问题数: ${_health.issues_count || 0}</div>
            </div>
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">${_loading ? "加载中..." : "点击检查健康状态"}</div>`}
      </div>

      <!-- Targets -->
      <div class="card">
        <div class="card-title">🎯 进化目标</div>
        ${_targets?.targets ? html`
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
            ${Object.entries(_targets.targets).map(([key, t]) => html`
              <div style="display:flex;align-items:center;justify-content:space-between;padding:8px;background:var(--bg-2);border-radius:6px;">
                <div>
                  <div style="font-size:12px;font-weight:600;color:var(--fg);">${key.replace(/_/g, " ")}</div>
                  <div style="font-size:11px;color:var(--fg-3);">目标: ${t.target}</div>
                </div>
                <div style="text-align:right;">
                  <span style="font-size:14px;font-weight:700;color:${t.met ? '#22c55e' : '#f59e0b'};">${typeof t.current === 'number' ? t.current.toFixed(2) : t.current}</span>
                  <div style="font-size:10px;color:${t.met ? '#22c55e' : '#f59e0b'};">${t.met ? "✅ 达标" : "🟡 未达"}</div>
                </div>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">加载中...</div>`}
      </div>

      <!-- Metrics Summary -->
      <div class="card" style="grid-column:1/-1;">
        <div class="card-title">📊 进化度量 (${_metrics?.period_days || 30} 天)</div>
        ${_metrics ? html`
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;margin-top:12px;">
            ${[
              ["总次数", _metrics.total_heals],
              ["成功", _metrics.successful_heals],
              ["失败", _metrics.failed_heals],
              ["回滚", _metrics.rollbacks],
              ["成功率", (_metrics.success_rate * 100).toFixed(0) + "%"],
              ["周频率", _metrics.weekly_frequency],
              ["均耗时", (_metrics.avg_duration_ms / 1000).toFixed(1) + "s"],
              ["修复文件", _metrics.files_healed_total],
            ].map(([label, val]) => html`
              <div style="text-align:center;padding:10px;background:var(--bg-2);border-radius:8px;">
                <div style="font-size:18px;font-weight:700;color:var(--fg);">${val}</div>
                <div style="font-size:10px;color:var(--fg-3);margin-top:2px;">${label}</div>
              </div>
            `)}
          </div>
        ` : nothing}
      </div>

      <!-- Evolution Log -->
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>📜 进化日志</span>
          <span style="font-size:11px;color:var(--fg-3);">${_log?.beads?.length || 0} 条</span>
        </div>
        ${_log?.beads?.length ? html`
          <div style="max-height:300px;overflow-y:auto;">
            ${_log.beads.slice(0, 15).map(b => html`
              <div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <span style="font-weight:600;color:var(--fg);">${(OUTCOME_STYLE[b.outcome] || OUTCOME_STYLE.pending).icon} ${b.id}</span>
                  <span style="font-size:10px;color:var(--fg-3);">${b.timestamp?.slice(0, 16)}</span>
                </div>
                <div style="color:var(--fg-2);margin-top:2px;">${b.action?.slice(0, 60)}</div>
                <div style="font-size:10px;color:var(--fg-3);margin-top:1px;">${b.trigger} · ${b.executor} · ${b.notes || ""}</div>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">暂无进化记录</div>`}
      </div>

      <!-- Git Hooks -->
      <div class="card">
        <div class="card-title">🪝 Git Hooks</div>
        <div style="font-size:13px;color:var(--fg-2);line-height:1.8;margin-top:8px;">
          <div><strong>pre-commit:</strong> 提交前快速体检，分数 &lt;60 阻止提交</div>
          <div><strong>post-merge:</strong> 合并后自动修复引入的问题</div>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px;">
          <button class="btn btn--primary" style="font-size:12px;padding:6px 16px;" @click=${() => _installHooks(app)}>安装 Hooks</button>
          <button class="btn" style="font-size:12px;padding:6px 16px;border:1px solid var(--border);color:var(--fg-3);" @click=${() => api.uninstallGitHooks().then(() => alert("已卸载"))}>卸载</button>
        </div>
      </div>
    </div>
  `;
}
