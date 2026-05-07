/**
 * Managed Tasks — 任务状态机视图
 * States: draft → planned → approved → running → verifying → done/failed
 */
import { html, nothing } from "lit";
import * as api from "../api.js";

let _tasks = [], _selectedTask = null, _loading = false;
let _newTitle = "", _newGoal = "";
let _statusFilter = "";

const STATUS_ICON = {
  draft: "📝", planned: "📋", approved: "✅", running: "🔄",
  blocked: "🚫", verifying: "🔍", done: "✔️", failed: "❌",
};
const STATUS_COLOR = {
  draft: "#6b7280", planned: "#3b82f6", approved: "#8b5cf6", running: "#f59e0b",
  blocked: "#ef4444", verifying: "#06b6d4", done: "#22c55e", failed: "#ef4444",
};

async function _load(app) {
  if (_loading) return;
  _loading = true;
  try {
    const data = await api.fetchManagedTasks(_statusFilter);
    _tasks = data.tasks || [];
  } catch (e) { _tasks = []; }
  _loading = false;
  app.requestUpdate();
}

async function _create(app) {
  if (!_newTitle.trim() || !_newGoal.trim()) return;
  try {
    await api.createManagedTask(_newTitle, _newGoal);
    _newTitle = ""; _newGoal = "";
    await _load(app);
  } catch (e) { /* ignore */ }
}

async function _transition(app, taskId, status) {
  try {
    _selectedTask = await api.transitionTask(taskId, status, "from UI");
    await _load(app);
  } catch (e) { alert(e.message); }
}

async function _plan(app, taskId) {
  try {
    _selectedTask = await api.generateTaskPlan(taskId);
    await _load(app);
  } catch (e) { alert(e.message); }
}

async function _select(app, taskId) {
  try {
    _selectedTask = await api.fetchManagedTask(taskId);
  } catch (e) { _selectedTask = null; }
  app.requestUpdate();
}

function _nextActions(status) {
  const map = {
    draft: ["planned"], planned: ["approved"], approved: ["running"],
    running: ["verifying", "blocked"], blocked: ["running"],
    verifying: ["done", "running"], failed: ["draft"],
  };
  return map[status] || [];
}

export function renderManagedTasks(app) {
  if (!_tasks.length && !_loading) _load(app);

  return html`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">

      <!-- Task List -->
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>📋 任务列表 (${_tasks.length})</span>
          <select style="font-size:11px;padding:4px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg-2);color:var(--fg);"
            @change=${(e) => { _statusFilter = e.target.value; _load(app); }}>
            <option value="">全部状态</option>
            ${Object.keys(STATUS_ICON).map(s => html`<option value="${s}" ?selected=${_statusFilter === s}>${STATUS_ICON[s]} ${s}</option>`)}
          </select>
        </div>
        ${_tasks.length ? html`
          <div style="max-height:400px;overflow-y:auto;">
            ${_tasks.map(t => html`
              <div style="padding:8px;border-radius:6px;margin-bottom:4px;cursor:pointer;
                background:${_selectedTask?.id === t.id ? 'var(--bg-2)' : 'transparent'};border-left:3px solid ${STATUS_COLOR[t.status] || '#6b7280'};"
                @click=${() => _select(app, t.id)}>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <span style="font-size:13px;font-weight:600;color:var(--fg);">${t.title}</span>
                  <span style="font-size:11px;padding:2px 6px;border-radius:4px;background:${STATUS_COLOR[t.status]}22;color:${STATUS_COLOR[t.status]};">${STATUS_ICON[t.status]} ${t.status}</span>
                </div>
                <div style="font-size:11px;color:var(--fg-3);margin-top:2px;">${t.id}</div>
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">${_loading ? "加载中..." : "暂无任务"}</div>`}

        <!-- Create Task -->
        <div style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px;">
          <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:6px;">新建任务</div>
          <input type="text" placeholder="任务标题" style="width:100%;padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg-2);color:var(--fg);font-size:12px;margin-bottom:4px;box-sizing:border-box;"
            .value=${_newTitle} @input=${(e) => { _newTitle = e.target.value; }}>
          <input type="text" placeholder="任务目标" style="width:100%;padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg-2);color:var(--fg);font-size:12px;margin-bottom:6px;box-sizing:border-box;"
            .value=${_newGoal} @input=${(e) => { _newGoal = e.target.value; }}>
          <button class="btn btn--primary" style="font-size:12px;padding:6px 16px;width:100%;" @click=${() => _create(app)}>创建</button>
        </div>
      </div>

      <!-- Task Detail -->
      <div class="card">
        ${_selectedTask ? html`
          <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
            <span>${STATUS_ICON[_selectedTask.status]} ${_selectedTask.title}</span>
            <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:${STATUS_COLOR[_selectedTask.status]}22;color:${STATUS_COLOR[_selectedTask.status]};font-weight:600;">${_selectedTask.status}</span>
          </div>
          <div style="font-size:13px;color:var(--fg-2);line-height:1.8;margin-top:8px;">
            <div><strong>ID:</strong> <code>${_selectedTask.id}</code></div>
            <div><strong>目标:</strong> ${_selectedTask.goal}</div>
            <div><strong>项目:</strong> ${_selectedTask.project_id}</div>
            <div><strong>创建:</strong> ${_selectedTask.created_at ? new Date(_selectedTask.created_at).toLocaleString() : "N/A"}</div>
            ${_selectedTask.verification_cmd ? html`<div><strong>验证:</strong> <code>${_selectedTask.verification_cmd}</code></div>` : nothing}
            ${_selectedTask.rollback_strategy ? html`<div><strong>回滚:</strong> ${_selectedTask.rollback_strategy}</div>` : nothing}
          </div>

          ${_selectedTask.plan?.length ? html`
            <div style="margin-top:12px;">
              <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:4px;">计划</div>
              ${_selectedTask.plan.map(p => html`<div style="font-size:12px;color:var(--fg-2);padding:2px 0;">• ${p}</div>`)}
            </div>
          ` : nothing}

          ${_selectedTask.scope?.length ? html`
            <div style="margin-top:8px;">
              <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:4px;">范围</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;">
                ${_selectedTask.scope.map(s => html`<code style="background:var(--bg-2);padding:2px 6px;border-radius:4px;font-size:11px;">${s}</code>`)}
              </div>
            </div>
          ` : nothing}

          ${_selectedTask.risks?.length ? html`
            <div style="margin-top:8px;">
              <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:4px;">风险</div>
              ${_selectedTask.risks.map(r => html`<div style="font-size:12px;color:#f59e0b;padding:2px 0;">⚠️ ${r}</div>`)}
            </div>
          ` : nothing}

          ${_selectedTask.history?.length ? html`
            <div style="margin-top:12px;">
              <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:4px;">状态历史</div>
              ${_selectedTask.history.map(h => html`
                <div style="font-size:11px;color:var(--fg-3);padding:2px 0;">
                  ${h.from} → ${h.to} <span style="color:var(--fg-4);">(${h.reason || ""})</span>
                  <span style="float:right;">${h.at ? new Date(h.at).toLocaleTimeString() : ""}</span>
                </div>
              `)}
            </div>
          ` : nothing}

          <!-- Actions -->
          <div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">
            ${_selectedTask.status === "draft" ? html`
              <button class="btn btn--primary" style="font-size:12px;padding:6px 16px;" @click=${() => _plan(app, _selectedTask.id)}>生成计划</button>
            ` : nothing}
            ${_nextActions(_selectedTask.status).map(s => html`
              <button class="btn" style="font-size:12px;padding:6px 16px;border:1px solid ${STATUS_COLOR[s]};color:${STATUS_COLOR[s]};"
                @click=${() => _transition(app, _selectedTask.id, s)}>${STATUS_ICON[s]} → ${s}</button>
            `)}
          </div>
        ` : html`
          <div class="card-title">任务详情</div>
          <div style="color:var(--fg-3);font-size:13px;padding:20px 0;text-align:center;">选择左侧任务查看详情</div>
        `}
      </div>
    </div>
  `;
}
