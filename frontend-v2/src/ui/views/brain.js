/**
 * Brain/Memory/Tasks/Learning tab renders
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";

// === 大脑状态页 ===
let _goals = null, _thoughts = null, _brainLoading = false, _brainDetailTs = 0;

async function _fetchBrainDetails() {
  _brainLoading = true;
  try {
    const [g, t] = await Promise.all([
      fetch('/api/brain/goals').then(r => r.json()).catch(() => ({})),
      fetch('/api/brain/thoughts').then(r => r.json()).catch(() => ({})),
    ]);
    _goals = g;
    _thoughts = t;
    _brainDetailTs = Date.now();
  } catch (e) { /* ignore */ }
  _brainLoading = false;
}

async function _brainAction(action, app) {
  try {
    await fetch(`/api/brain/${action}`, { method: "POST" });
    await app._refreshBrain();
    app.requestUpdate();
  } catch (e) { console.error(`Brain ${action} failed:`, e); }
}

export function renderBrain(app) {
  const d = app.brainStatus?.daemon || {};
  const awake = app.brainStatus?.awake;
  const q = d.queue || {};

  if ((!_goals || Date.now() - _brainDetailTs > 15000) && !_brainLoading) {
    _fetchBrainDetails().then(() => app.requestUpdate());
  }

  const goalsList = _goals?.goals || _goals?.active_goals || [];
  const thoughtsList = _thoughts?.thoughts || _thoughts?.recent || [];

  return html`
    <!-- 控制区 -->
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>大脑控制</span>
        <div style="display:flex;gap:8px;">
          <button class="btn" @click=${() => { _goals = null; _thoughts = null; _fetchBrainDetails().then(() => app.requestUpdate()); app._refreshBrain(); }}
            style="font-size:12px;">${icons.refresh} 刷新</button>
        </div>
      </div>
      <div class="card-grid" style="margin-top:12px;">
        <div class="stat">
          <div class="stat-label">状态</div>
          <div class="stat-value">${awake ? "🟢 运行中" : "🔴 休眠"}</div>
          <div style="margin-top:8px;">
            ${awake
              ? html`<button class="btn btn--sm" style="font-size:11px;" @click=${() => _brainAction('sleep', app)}>💤 休眠</button>`
              : html`<button class="btn btn--sm btn--primary" style="font-size:11px;" @click=${() => _brainAction('awaken', app)}>⚡ 唤醒</button>`}
          </div>
        </div>
        <div class="stat">
          <div class="stat-label">守护进程</div>
          <div class="stat-value">${d.paused ? "⏸ 已暂停" : (d.running ? "▶ 运行" : "⏹ 停止")}</div>
          <div style="margin-top:8px;">
            ${d.paused
              ? html`<button class="btn btn--sm btn--primary" style="font-size:11px;" @click=${() => _brainAction('resume', app)}>▶ 恢复</button>`
              : html`<button class="btn btn--sm" style="font-size:11px;" @click=${() => _brainAction('pause', app)}>⏸ 暂停</button>`}
          </div>
        </div>
        <div class="stat">
          <div class="stat-label">思考次数</div>
          <div class="stat-value">${d.thought_count || 0}</div>
        </div>
        <div class="stat">
          <div class="stat-label">行动次数</div>
          <div class="stat-value">${d.action_count || 0}</div>
        </div>
        <div class="stat">
          <div class="stat-label">任务队列</div>
          <div class="stat-value">${q.total || 0}</div>
          <div class="stat-sub">${q.running || 0} 执行中</div>
        </div>
      </div>
    </div>

    <!-- 自检状态 -->
    ${d.boot_diag ? html`
      <div class="card" style="margin-top:12px;">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>🩺 今日自检</span>
          <span style="font-size:11px;color:var(--fg-3);">${d.boot_diag.time ? new Date(d.boot_diag.time).toLocaleString("zh-CN") : ""}</span>
        </div>
        <div class="card-grid" style="margin-top:8px;">
          <div class="stat">
            <div class="stat-label">总体健康</div>
            <div class="stat-value">${d.boot_diag.healthy ? "✅ 正常" : "⚠️ 异常"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">LLM</div>
            <div class="stat-value">${d.boot_diag.llm ? "✅" : "❌"} ${d.boot_diag.model || "?"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">工具/记忆/学习</div>
            <div class="stat-value">${d.boot_diag.tools ? "✅" : "❌"} / ${d.boot_diag.memory ? "✅" : "❌"} / ${d.boot_diag.learning ? "✅" : "❌"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">内存 / 磁盘</div>
            <div class="stat-value">${d.boot_diag.mem_percent || 0}% / ${d.boot_diag.disk_free_gb || 0}GB</div>
          </div>
        </div>
        ${(d.boot_diag.resource_alerts || []).length > 0 ? html`
          <div style="margin-top:8px;padding:8px 12px;background:var(--danger,#ef4444)11;border-radius:6px;color:var(--danger,#ef4444);font-size:12px;">
            ${d.boot_diag.resource_alerts.map(a => html`<div>⚠️ ${a}</div>`)}
          </div>
        ` : nothing}
        <div style="margin-top:8px;font-size:12px;color:var(--fg-3);">
          当前目标: ${d.boot_diag.goals || "无"}
        </div>
      </div>
    ` : nothing}

    <!-- 大脑目标 -->
    <div class="card" style="margin-top:12px;">
      <div class="card-title">大脑目标</div>
      <div style="margin-top:12px;">
        ${Array.isArray(goalsList) && goalsList.length > 0
          ? goalsList.map(g => {
              const content = g.content || g.description || g.goal || (typeof g === 'string' ? g : '');
              const status = g.status || '';
              const progress = Array.isArray(g.progress) ? g.progress : [];
              const lastNote = progress.length > 0 ? progress[progress.length - 1] : null;
              return html`
                <div style="padding:10px 14px;background:var(--bg-2);border-radius:8px;margin-bottom:8px;font-size:13px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:600;color:var(--fg);">${content.substring(0, 80)}</span>
                    <span style="font-size:11px;padding:2px 8px;border-radius:10px;
                      background:${status === 'active' ? 'var(--green,#22c55e)22' : 'var(--fg-3)22'};
                      color:${status === 'active' ? 'var(--green,#22c55e)' : 'var(--fg-3)'};">
                      ${status === 'active' ? '活跃' : status || '—'}
                    </span>
                  </div>
                  ${lastNote ? html`
                    <div style="margin-top:6px;font-size:11px;color:var(--fg-3);">
                      最近进展: ${(lastNote.note || '').substring(0, 60)}
                      ${lastNote.time ? html` · ${new Date(lastNote.time).toLocaleDateString("zh-CN")}` : nothing}
                    </div>
                  ` : nothing}
                </div>`;
            })
          : html`<p class="text-muted" style="padding:12px;">暂无目标</p>`}
      </div>
    </div>

    <!-- 最近思考 -->
    <div class="card" style="margin-top:12px;">
      <div class="card-title">最近思考</div>
      <div style="max-height:300px;overflow-y:auto;margin-top:12px;">
        ${Array.isArray(thoughtsList) && thoughtsList.length > 0
          ? thoughtsList.slice(-10).reverse().map(t => {
              const items = Array.isArray(t.thoughts) ? t.thoughts : (typeof t === 'string' ? [t] : []);
              const time = t.time || '';
              const ms = t.ms || 0;
              return html`
                <div style="padding:8px 14px;background:var(--bg-2);border-radius:8px;margin-bottom:6px;display:flex;align-items:center;gap:10px;">
                  <span style="font-size:11px;color:var(--fg-3);min-width:52px;font-family:monospace;">${time}</span>
                  <div style="display:flex;flex-wrap:wrap;gap:6px;flex:1;">
                    ${items.map(s => html`<span style="font-size:12px;">${s}</span>`)}
                  </div>
                  <span style="font-size:10px;color:var(--fg-3);white-space:nowrap;">${ms}ms</span>
                </div>`;
            })
          : html`<p class="text-muted" style="padding:12px;">暂无思考数据</p>`}
      </div>
    </div>
  `;
}

// === 记忆页面 ===
let _memData = null, _memLoading = false, _memSid = null, _memTs = 0;
async function _fetchMemory(sid) {
  _memLoading = true;
  _memSid = sid;
  try {
    const [memR, lesR] = await Promise.all([
      fetch(`/api/memory/${sid}`).then(r => r.json()),
      fetch('/api/lessons').then(r => r.json()),
    ]);
    _memData = { messages: memR.messages || [], lessons: lesR.lessons || [], count: lesR.count || 0, sid };
    _memTs = Date.now();
  } catch(e) { _memData = { messages: [], lessons: [], count: 0, error: e.message, sid }; }
  _memLoading = false;
}
export function renderMemory(app) {
  const sid = app ? app.currentSession : 'default';
  if (!_memData || _memSid !== sid || Date.now() - _memTs > 30000) {
    if (!_memLoading) _fetchMemory(sid).then(() => app && app.requestUpdate());
    return html`<div class="card"><p>加载中...</p></div>`;
  }
  const msgs = _memData.messages.slice(-20);
  const srcs = {};
  _memData.lessons.forEach(l => { const s = l.source || '?'; srcs[s] = (srcs[s]||0)+1; });
  return html`
    <div class="card-grid">
      <div class="stat"><div class="stat-label">会话消息</div><div class="stat-value">${_memData.messages.length}</div>
        <div class="stat-sub">会话: ${sid}</div></div>
      <div class="stat"><div class="stat-label">经验总数</div><div class="stat-value">${_memData.count}</div></div>
      <div class="stat"><div class="stat-label">经验来源</div><div class="stat-value">${Object.keys(srcs).length}类</div>
        <div class="stat-sub">${Object.entries(srcs).map(([k,v])=>`${k}:${v}`).join(' ')}</div></div>
    </div>
    <div class="card" style="margin-top:1rem">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>最近对话记忆 (${sid})</span>
        <button class="btn" style="font-size:12px;" @click=${()=>{_memData=null;_fetchMemory(sid).then(()=>app&&app.requestUpdate());}}>刷新</button>
      </div>
      <div style="max-height:400px;overflow-y:auto;font-size:0.85rem">
        ${msgs.map((m, i) => html`
          <div style="padding:4px 0;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:flex-start;">
            <span style="color:var(--accent);min-width:50px;font-weight:600">${m.role}</span>
            <span style="opacity:0.8;flex:1;">${(m.content||'').slice(0,200)}</span>
            <button class="btn btn--sm" style="font-size:10px;padding:1px 6px;color:var(--danger,#ef4444);flex-shrink:0;"
              @click=${async () => {
                if (!confirm('删除此条记忆？')) return;
                const realIdx = _memData.messages.length - msgs.length + i;
                try {
                  await fetch('/api/memory/' + sid + '/' + realIdx, { method: 'DELETE' });
                  _memData = null; _fetchMemory(sid).then(() => app && app.requestUpdate());
                } catch(e) { console.error('删除记忆失败:', e); }
              }}
              title="删除此条记忆">✕</button>
          </div>
        `)}
      </div>
    </div>
  `;
}

export function renderTasks() {
  return html`<div class="card"><div class="card-title">任务看板</div><p class="text-muted">请使用「任务」Tab查看完整任务看板</p></div>`;
}

// === 学习页面 ===
let _learnData = null, _learnLoading = false, _learnTs = 0;
let _learnFilter = "";
async function _fetchLearning() {
  _learnLoading = true;
  try {
    const r = await fetch('/api/lessons').then(r => r.json());
    _learnData = r;
    _learnTs = Date.now();
  } catch(e) { _learnData = { lessons: [], count: 0, error: e.message }; }
  _learnLoading = false;
}
async function _deleteLesson(index, app) {
  try {
    await fetch(`/api/lessons/${index}`, { method: "DELETE" });
    _learnData = null;
    _fetchLearning().then(() => app.requestUpdate());
  } catch (e) { console.error("删除经验失败:", e); }
}
export function renderLearning(app) {
  if ((!_learnData || Date.now() - _learnTs > 30000) && !_learnLoading) { _fetchLearning().then(() => app && app.requestUpdate()); }
  if (!_learnData) return html`<div class="card"><p>加载中...</p></div>`;
  let lessons = _learnData.lessons || [];
  const tiers = {}, srcs = {};
  let effSum = 0, effCount = 0;
  lessons.forEach(l => {
    tiers[l.tier||'?'] = (tiers[l.tier||'?']||0)+1;
    srcs[l.source||'?'] = (srcs[l.source||'?']||0)+1;
    if (l.effectiveness != null) { effSum += l.effectiveness; effCount++; }
  });
  const avgEff = effCount > 0 ? (effSum/effCount).toFixed(2) : 'N/A';
  if (_learnFilter) {
    const q = _learnFilter.toLowerCase();
    lessons = lessons.filter(l =>
      (l.trigger || '').toLowerCase().includes(q) ||
      (l.lesson || '').toLowerCase().includes(q) ||
      (l.source || '').toLowerCase().includes(q));
  }
  return html`
    <div class="card-grid">
      <div class="stat"><div class="stat-label">经验总数</div><div class="stat-value">${_learnData.lessons?.length || 0}</div></div>
      <div class="stat"><div class="stat-label">有效性均值</div><div class="stat-value">${avgEff}</div></div>
      <div class="stat"><div class="stat-label">分层</div><div class="stat-value">${Object.keys(tiers).length}层</div>
        <div class="stat-sub">${Object.entries(tiers).map(([k,v])=>`${k}:${v}`).join(' ')}</div></div>
      <div class="stat"><div class="stat-label">来源</div><div class="stat-value">${Object.keys(srcs).length}类</div>
        <div class="stat-sub">${Object.entries(srcs).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([k,v])=>`${k}:${v}`).join(' ')}</div></div>
    </div>
    <div class="card" style="margin-top:1rem">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>经验列表 (${lessons.length})</span>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="text" placeholder="搜索经验..." .value=${_learnFilter}
            @input=${(e) => { _learnFilter = e.target.value; app && app.requestUpdate(); }}
            style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-2);color:var(--fg);font-size:12px;width:150px;">
          <button class="btn" style="font-size:12px;" @click=${()=>{_learnData=null;_fetchLearning().then(()=>app&&app.requestUpdate());}}>刷新</button>
        </div>
      </div>
      <div style="max-height:500px;overflow-y:auto;font-size:0.85rem">
        ${lessons.slice(0,50).map((l, i) => html`
          <div style="padding:6px 0;border-bottom:1px solid var(--border)">
            <div style="display:flex;gap:8px;align-items:center;justify-content:space-between;">
              <div style="display:flex;gap:8px;align-items:center;">
                <span style="background:var(--accent);color:#fff;padding:1px 6px;border-radius:4px;font-size:0.75rem">${l.tier||'?'}</span>
                <span style="opacity:0.5;font-size:0.75rem">${l.source||'?'}</span>
                <span style="opacity:0.5;font-size:0.75rem">eff:${l.effectiveness != null ? l.effectiveness.toFixed(2) : '?'}</span>
              </div>
              <button class="btn btn--sm" style="font-size:10px;padding:1px 6px;color:var(--danger,#ef4444);"
                @click=${() => { if(confirm('删除此条经验？')) _deleteLesson(l._index != null ? l._index : i, app); }}
                title="删除此经验">✕</button>
            </div>
            <div style="margin-top:2px"><strong>${(l.trigger||'').slice(0,80)}</strong></div>
            <div style="opacity:0.7">${(l.lesson||'').slice(0,150)}</div>
          </div>
        `)}
      </div>
    </div>
  `;
}
