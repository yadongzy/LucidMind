/**
 * Logs view — 实时事件日志
 */
import { html } from "lit";
import { icons } from "../icons.js";

export function renderLogs(app) {
  return html`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <div class="card-title" style="margin-bottom:0">事件日志 (${app.eventLog.length})</div>
        <button class="btn" @click=${() => { app.eventLog = []; }}>清空</button>
      </div>

      <div style="max-height:600px;overflow-y:auto;font-family:var(--mono);font-size:12px;">
        ${app.eventLog.length === 0 ? html`<div class="text-muted">暂无事件</div>` : html`
          <table class="data-table">
            <thead>
              <tr>
                <th style="width:80px">时间</th>
                <th style="width:70px">类型</th>
                <th>内容</th>
              </tr>
            </thead>
            <tbody>
              ${app.eventLog.map(e => html`
                <tr>
                  <td style="color:var(--accent)">${e.time}</td>
                  <td style="color:var(--warn)">${e.type}</td>
                  <td>${e.msg}</td>
                </tr>
              `)}
            </tbody>
          </table>
        `}
      </div>
    </div>
  `;
}
