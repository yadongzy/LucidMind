/**
 * Project Brain Cockpit — 项目大脑驾驶舱
 * Panels: Project State, Reports Browser, Governance, Memory Candidates
 */
import { html, nothing } from "lit";
import { renderMarkdown } from "../markdown.js";
import * as api from "../api.js";

// === Cache ===
let _projectState = null, _reports = null, _governance = null, _memory = null;
let _selectedReport = null, _selectedReportData = null;
let _loading = false, _lastFetch = 0;
let _govFiles = "", _govActions = "", _govResult = null;

async function _fetchAll() {
  if (_loading || Date.now() - _lastFetch < 5000) return;
  _loading = true;
  try {
    const [state, reports, gov, mem] = await Promise.all([
      api.fetchProjectState().catch(() => null),
      api.fetchProjectReports().catch(() => []),
      api.fetchGovernanceDecisions().catch(() => []),
      api.fetchMemoryCandidates().catch(() => ({ candidates: [], total: 0 })),
    ]);
    _projectState = state;
    _reports = reports;
    _governance = gov;
    _memory = mem;
    _lastFetch = Date.now();
  } catch (e) { /* ignore */ }
  _loading = false;
}

async function _selectReport(app, taskId) {
  _selectedReport = taskId;
  _selectedReportData = null;
  app.requestUpdate();
  try {
    _selectedReportData = await api.fetchProjectReport("lucidmind", taskId);
  } catch (e) {
    _selectedReportData = { markdown: `Error loading report: ${e.message}` };
  }
  app.requestUpdate();
}

async function _runGovernanceCheck(app) {
  const files = _govFiles.split(",").map(s => s.trim()).filter(Boolean);
  const actions = _govActions.split(",").map(s => s.trim()).filter(Boolean);
  try {
    _govResult = await api.postGovernanceReview("lucidmind", files, actions);
  } catch (e) {
    _govResult = { error: e.message };
  }
  app.requestUpdate();
}

// === Main Render ===
export function renderCockpit(app) {
  if (!_projectState && !_loading) {
    _fetchAll().then(() => app.requestUpdate());
  }

  return html`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <!-- Project State -->
      <div class="card">
        <div class="card-title">项目状态</div>
        ${_projectState ? html`
          <div style="font-size:13px;color:var(--fg-2);line-height:1.8;">
            <div><strong>项目:</strong> ${_projectState.project_name}</div>
            <div><strong>语言:</strong> ${(_projectState.languages || []).join(", ")}</div>
            <div><strong>框架:</strong> ${(_projectState.frameworks || []).join(", ")}</div>
            <div><strong>Git:</strong> ${_projectState.git_branch || "N/A"} @ ${_projectState.git_commit || "N/A"}</div>
            <div><strong>更新:</strong> ${_projectState.updated_at ? new Date(_projectState.updated_at).toLocaleString() : "N/A"}</div>
            <div style="margin-top:8px;"><strong>核心文件:</strong></div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
              ${(_projectState.core_files || []).map(f => html`<code style="background:var(--bg-2);padding:2px 6px;border-radius:4px;font-size:11px;">${f}</code>`)}
            </div>
            <div style="margin-top:8px;"><strong>能力状态:</strong></div>
            ${Object.entries(_projectState.capability_status || {}).map(([k, v]) => html`
              <div style="display:inline-block;margin:2px 4px;">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${v === 'stable' ? '#22c55e' : v === 'beta' ? '#f59e0b' : v === 'experimental' ? '#3b82f6' : '#6b7280'};margin-right:4px;"></span>
                <span style="font-size:11px;">${k}: ${v}</span>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">${_loading ? "加载中..." : "未找到项目状态。运行 index_project_state.py 生成。"}</div>`}
      </div>

      <!-- Reports Browser -->
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>任务报告</span>
          <span style="font-size:11px;color:var(--fg-3);">${(_reports || []).length} 份</span>
        </div>
        ${(_reports || []).length ? html`
          <div style="max-height:200px;overflow-y:auto;">
            ${_reports.map(r => html`
              <div style="padding:6px 8px;cursor:pointer;border-radius:6px;font-size:12px;margin-bottom:2px;
                background:${_selectedReport === r.task_id ? 'var(--bg-2)' : 'transparent'};"
                @click=${() => _selectReport(app, r.task_id)}>
                <div style="font-weight:600;color:var(--fg);">${r.task_id}</div>
                <div style="color:var(--fg-3);font-size:11px;">${(r.size_bytes / 1024).toFixed(1)} KB</div>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">暂无报告</div>`}
      </div>

      <!-- Report Detail -->
      ${_selectedReport ? html`
        <div class="card" style="grid-column:1/-1;">
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
            <span>报告: ${_selectedReport}</span>
            <button class="btn" style="font-size:11px;padding:4px 10px;" @click=${() => { _selectedReport = null; _selectedReportData = null; app.requestUpdate(); }}>关闭</button>
          </div>
          <div style="max-height:400px;overflow-y:auto;font-size:13px;line-height:1.7;">
            ${_selectedReportData ? renderMarkdown(_selectedReportData.markdown || "") : html`<span style="color:var(--fg-3);">加载中...</span>`}
          </div>
        </div>
      ` : nothing}

      <!-- Governance Check -->
      <div class="card">
        <div class="card-title">治理审查</div>
        <div style="font-size:12px;color:var(--fg-3);margin-bottom:8px;">输入文件/操作，检查是否需要确认</div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          <input type="text" placeholder="文件 (逗号分隔，如 brain.py, api/main.py)"
            style="padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg-2);color:var(--fg);font-size:12px;"
            .value=${_govFiles} @input=${(e) => { _govFiles = e.target.value; }}>
          <input type="text" placeholder="操作 (逗号分隔，如 git push, delete)"
            style="padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg-2);color:var(--fg);font-size:12px;"
            .value=${_govActions} @input=${(e) => { _govActions = e.target.value; }}>
          <button class="btn btn--primary" style="align-self:flex-end;font-size:12px;padding:6px 16px;" @click=${() => _runGovernanceCheck(app)}>检查</button>
        </div>
        ${_govResult ? html`
          <div style="margin-top:10px;padding:10px;border-radius:6px;background:${_govResult.approved ? 'rgba(34,197,94,.1)' : 'rgba(239,68,68,.1)'};border:1px solid ${_govResult.approved ? '#22c55e' : '#ef4444'};">
            <div style="font-weight:600;font-size:13px;color:${_govResult.approved ? '#22c55e' : '#ef4444'};">${_govResult.approved ? '✅ 已批准' : '❌ 需要确认'}</div>
            <div style="font-size:12px;color:var(--fg-2);margin-top:4px;">
              <div>风险: ${_govResult.risk_level || "N/A"}</div>
              ${(_govResult.protected_files || []).length ? html`<div>保护文件: ${_govResult.protected_files.join(", ")}</div>` : nothing}
              ${(_govResult.dangerous_actions || []).length ? html`<div>危险操作: ${_govResult.dangerous_actions.join(", ")}</div>` : nothing}
              ${(_govResult.reasons || []).map(r => html`<div style="color:var(--fg-3);font-size:11px;">• ${r}</div>`)}
            </div>
          </div>
        ` : nothing}
      </div>

      <!-- Memory Candidates -->
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>项目记忆</span>
          <span style="font-size:11px;color:var(--fg-3);">${_memory?.total || 0} 条</span>
        </div>
        ${(_memory?.candidates || []).length ? html`
          <div style="max-height:250px;overflow-y:auto;">
            ${_memory.candidates.slice(0, 50).map(c => html`
              <div style="padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <code style="background:var(--bg-2);padding:1px 6px;border-radius:4px;font-size:10px;">${c.collection}</code>
                  <span style="font-size:10px;color:var(--fg-3);">#${c.memory_id}</span>
                </div>
                <div style="color:var(--fg-2);margin-top:3px;line-height:1.5;">${c.content}</div>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">暂无记忆候选</div>`}
      </div>

      <!-- Governance Decision Log -->
      <div class="card" style="grid-column:1/-1;">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>治理决策日志</span>
          <span style="font-size:11px;color:var(--fg-3);">${(_governance || []).length} 条</span>
        </div>
        ${(_governance || []).length ? html`
          <div style="overflow-x:auto;">
            <table style="width:100%;font-size:12px;border-collapse:collapse;">
              <thead>
                <tr style="border-bottom:1px solid var(--border);color:var(--fg-3);">
                  <th style="text-align:left;padding:6px 8px;">任务</th>
                  <th style="text-align:left;padding:6px 8px;">操作</th>
                  <th style="text-align:center;padding:6px 8px;">结果</th>
                  <th style="text-align:left;padding:6px 8px;">风险</th>
                  <th style="text-align:left;padding:6px 8px;">时间</th>
                </tr>
              </thead>
              <tbody>
                ${_governance.slice(-20).reverse().map(d => html`
                  <tr style="border-bottom:1px solid var(--border);">
                    <td style="padding:6px 8px;color:var(--fg);">${d.task_id}</td>
                    <td style="padding:6px 8px;color:var(--fg-2);">${d.action}</td>
                    <td style="padding:6px 8px;text-align:center;">
                      <span style="color:${d.approved ? '#22c55e' : '#ef4444'};">${d.approved ? '✅' : '❌'}</span>
                    </td>
                    <td style="padding:6px 8px;"><span style="color:${d.risk_level === 'high' ? '#ef4444' : '#f59e0b'};">${d.risk_level}</span></td>
                    <td style="padding:6px 8px;color:var(--fg-3);font-size:11px;">${d.created_at ? new Date(d.created_at).toLocaleString() : ""}</td>
                  </tr>
                `)}
              </tbody>
            </table>
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">暂无治理决策记录</div>`}
      </div>
    </div>
  `;
}
