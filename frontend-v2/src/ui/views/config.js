/**
 * Config view — 模型配置 + Brain 设置
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";
import * as api from "../api.js";

export function renderConfig(app) {
  return html`
    <div class="card">
      <div class="card-title">模型配置</div>
      <div class="form-group">
        <label class="form-label">提供商</label>
        <select class="form-select" id="cfg-provider">
          <option value="deepseek" ?selected=${app.modelInfo?.provider === "deepseek"}>DeepSeek</option>
          <option value="minimax" ?selected=${app.modelInfo?.provider === "minimax"}>MiniMax</option>
          <option value="local" ?selected=${app.modelInfo?.provider === "local"}>Local (Ollama)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">API 密钥</label>
        <input class="form-input" type="password" id="cfg-apikey" placeholder="sk-..." />
      </div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button class="btn btn--primary" id="cfg-test-btn" @click=${async () => {
          const provider = document.getElementById("cfg-provider").value;
          const apiKey = document.getElementById("cfg-apikey").value;
          const statusEl = document.getElementById("cfg-status");
          statusEl.textContent = "验证中...";
          statusEl.style.color = "var(--warn)";
          try {
            const data = await api.verifyConnection(provider, apiKey);
            if (data.status === "ok") {
              statusEl.textContent = "已连接 \u2705";
              statusEl.style.color = "var(--ok)";
              app._refreshStatus();
            } else {
              statusEl.textContent = "失败 \u274c";
              statusEl.style.color = "var(--danger)";
            }
          } catch (e) {
            statusEl.textContent = "错误 \u274c";
            statusEl.style.color = "var(--danger)";
          }
}}>测试并应用</button>
        <span id="cfg-status" class="mono" style="font-size:12px;"></span>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-title">大脑设置</div>
      <div class="form-group">
        <label class="form-label">自动执行 (Auto Execution)</label>
        <div class="form-hint">开启后大脑自动执行任务，关闭则等待用户确认</div>
        <select class="form-select" @change=${async (e) => {
          const action = e.target.value === "on" ? "resume" : "pause";
          if (action === "resume") await api.resumeBrain();
          else await api.pauseBrain();
          app._refreshBrain();
        }}>
          <option value="on" ?selected=${!app.brainStatus?.daemon?.paused}>开启 (自动)</option>
          <option value="off" ?selected=${app.brainStatus?.daemon?.paused}>关闭 (手动确认)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">思考间隔</label>
        <select class="form-select" @change=${async (e) => {
          await api.setBrainInterval(parseInt(e.target.value));
        }}>
          <option value="30">30秒 (快速)</option>
          <option value="60" selected>60秒 (正常)</option>
          <option value="120">120秒 (慢速)</option>
          <option value="300">300秒 (极慢)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">自动求助老师</label>
        <select class="form-select" @change=${async (e) => {
          await api.setAutoAsk(e.target.value === "on");
        }}>
          <option value="on">开启</option>
          <option value="off">关闭</option>
        </select>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-title">显示设置</div>
      <div class="form-group">
        <label class="form-label">显示思考过程</label>
        <select class="form-select" @change=${(e) => {
          app.showThinking = e.target.value === "on";
          localStorage.setItem("lucid_thinking", app.showThinking);
        }}>
          <option value="on" ?selected=${app.showThinking}>开启</option>
          <option value="off" ?selected=${!app.showThinking}>关闭</option>
        </select>
      </div>
    </div>

    <div class="card" style="margin-top:16px">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>安全设置</span>
        <button class="btn" style="font-size:12px;" @click=${() => { _secData = null; app.requestUpdate(); }}>刷新</button>
      </div>
      ${_secData === null ? _loadSecurityConfig(app) || html`<p>加载中...</p>` : html`
        <div class="form-group">
          <label class="form-label">工具安全审批</label>
          <div class="form-hint">开启后，危险工具执行前需要用户确认</div>
          <select class="form-select" @change=${async (e) => {
            const enabled = e.target.value === "on";
            await fetch('/api/security/toggle', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ enabled }),
            });
            _secData = null; app.requestUpdate();
          }}>
            <option value="on" ?selected=${_secData?.enabled}>开启</option>
            <option value="off" ?selected=${!_secData?.enabled}>关闭</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">危险工具 (${(_secData?.dangerous_tools || []).length})</label>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
            ${(_secData?.dangerous_tools || []).map(t => html`
              <span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:var(--danger,#ef4444)22;color:var(--danger,#ef4444);border-radius:10px;font-size:11px;font-weight:600;">
                ${t}
              </span>
            `)}
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">敏感工具 (${(_secData?.sensitive_tools || []).length})</label>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
            ${(_secData?.sensitive_tools || []).map(t => html`
              <span style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;background:var(--warn,#f59e0b)22;color:var(--warn,#f59e0b);border-radius:10px;font-size:11px;font-weight:600;">
                ${t}
              </span>
            `)}
          </div>
        </div>
      `}
    </div>
  `;
}

let _secData = null;
function _loadSecurityConfig(app) {
  fetch('/api/security/config').then(r => r.json()).then(d => {
    _secData = d;
    app.requestUpdate();
  }).catch(() => { _secData = { enabled: false, dangerous_tools: [], sensitive_tools: [] }; app.requestUpdate(); });
  return null;
}
