/**
 * Sessions view — 会话管理
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";

export function renderSessions(app) {
  return html`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <div class="card-title" style="margin-bottom:0">会话列表 (${app.sessions.length})</div>
        <div style="display:flex;gap:8px;">
          <button class="btn" @click=${() => app._refreshSessions()}>${icons.refresh} 刷新</button>
          <button class="btn btn--primary" @click=${() => app._newSession()}>${icons.plus} 新建</button>
        </div>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>标题</th>
            <th>消息数</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${app.sessions.map(s => html`
            <tr>
              <td>
                <span style="cursor:pointer;${s.id === app.currentSession ? "color:var(--accent);font-weight:600;" : ""}"
                  @click=${() => { app._switchSession(s.id); app._setTab("chat"); }}
                  @dblclick=${async (e) => {
                    e.stopPropagation();
                    const newTitle = prompt("重命名会话:", s.title || s.id);
                    if (newTitle !== null && newTitle.trim()) {
                      try {
                        await fetch('/api/sessions/' + s.id + '/title', {
                          method: 'PUT',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ title: newTitle.trim() }),
                        });
                        app._refreshSessions();
                      } catch (err) { console.error("重命名失败:", err); }
                    }
                  }}
                  title="单击切换, 双击重命名">
                  ${s.id === app.currentSession ? "● " : ""}${s.title || s.id}
                </span>
              </td>
              <td class="mono">${s.message_count ?? s.messages ?? 0}</td>
              <td>
                ${s.id !== "default" ? html`
                  <button class="btn btn--danger" style="padding:2px 8px;font-size:11px;"
                    @click=${() => app._deleteSession(s.id)}>删除</button>
                ` : nothing}
              </td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  `;
}
