/**
 * Config view — 模型管理 + Brain 设置
 *
 * 对标 OpenClaw model-catalog / model-scan / model-selection。
 * 云端和本地模型分离配置，自动扫描硬件推荐最佳本地模型。
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";
import * as api from "../api.js";

let _modelData = null;
let _modelLoading = false;
let _localScan = null;
let _localScanning = false;
let _switchStatus = "";
let _expandedProvider = null;
let _localModelsCollapsed = false;

function _loadModels(app) {
  if (_modelLoading) return;
  _modelLoading = true;
  api.listModels().then(d => {
    _modelData = d;
    _modelLoading = false;
    app.requestUpdate();
  }).catch(() => { _modelLoading = false; });
}

function _scanLocal(app) {
  if (_localScanning) return;
  _localScanning = true;
  _localScan = null;
  app.requestUpdate();
  api.scanLocalModels().then(d => {
    _localScan = d;
    _localScanning = false;
    app.requestUpdate();
  }).catch(() => { _localScanning = false; app.requestUpdate(); });
}

async function _doSwitch(app, provider, model) {
  _switchStatus = `切换到 ${provider}/${model}...`;
  app.requestUpdate();
  try {
    const r = await api.switchModel(provider, model);
    _switchStatus = r.status === "ok" ? `已切换: ${r.provider}/${r.model}` : "切换失败";
    _modelData = null;
    _loadModels(app);
    app._refreshStatus();
  } catch (e) {
    _switchStatus = `错误: ${e.message || e}`;
  }
  app.requestUpdate();
  setTimeout(() => { _switchStatus = ""; app.requestUpdate(); }, 4000);
}

async function _doInstall(app, modelName) {
  _switchStatus = `安装 ${modelName}...（可能需要几分钟）`;
  app.requestUpdate();
  try {
    await api.installLocalModel(modelName);
    _switchStatus = `${modelName} 安装完成`;
    _localScan = null;
    _scanLocal(app);
  } catch (e) {
    _switchStatus = `安装失败: ${e.message || e}`;
  }
  app.requestUpdate();
}

function _renderCloudProviders(app) {
  if (!_modelData) {
    _loadModels(app);
    return html`<p style="color:var(--text-dim);font-size:13px;">加载模型目录...</p>`;
  }
  const providers = _modelData.cloud_providers || [];
  return html`
    <div style="display:flex;flex-direction:column;gap:2px;">
      ${providers.map(p => {
        const isOpen = _expandedProvider === p.id;
        return html`
          <div style="border:1px solid var(--border);border-radius:6px;overflow:hidden;
                       ${p.active ? 'border-color:var(--accent);' : ''}">
            <!-- 折叠头 -->
            <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;cursor:pointer;
                         background:${p.active ? 'rgba(var(--accent-rgb,59,130,246),0.08)' : 'transparent'};"
              @click=${() => { _expandedProvider = isOpen ? null : p.id; app.requestUpdate(); }}>
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:12px;color:var(--text-dim);transition:transform .2s;
                             display:inline-block;transform:rotate(${isOpen ? '90deg' : '0deg'});">&#9654;</span>
                <span style="font-weight:600;font-size:13px;color:var(--text);">${p.name}</span>
                ${p.configured ? html`<span style="color:var(--ok);font-size:10px;font-weight:600;">KEY</span>`
                  : html`<span style="color:var(--text-dim);font-size:10px;">未配置</span>`}
                ${p.active ? html`<span style="background:var(--accent);color:#fff;padding:1px 5px;border-radius:6px;font-size:9px;font-weight:700;">当前</span>` : nothing}
              </div>
              <div style="display:flex;align-items:center;gap:6px;">
                <span style="font-size:10px;color:var(--text-dim);">${(p.models||[]).length} 模型</span>
                <span style="font-size:10px;color:var(--text-dim);">${p.api_type}</span>
              </div>
            </div>
            <!-- 展开内容 -->
            ${isOpen ? html`
              <div style="padding:6px 12px 10px;border-top:1px solid var(--border);display:flex;flex-wrap:wrap;gap:4px;">
                ${(p.models || []).map(m => {
                  const isActive = p.active && p.active_model === m.id;
                  return html`
                    <button class="btn" style="font-size:11px;padding:3px 8px;
                      ${isActive ? 'background:var(--accent);color:#fff;border-color:var(--accent);' : ''}
                      ${!p.configured && p.id !== 'local' ? 'opacity:0.5;cursor:not-allowed;' : ''}"
                      ?disabled=${!p.configured && p.id !== 'local'}
                      @click=${(e) => { e.stopPropagation(); _doSwitch(app, p.id, m.id); }}
                      title="${m.name}${m.context_window ? ` | ctx:${(m.context_window/1000).toFixed(0)}K` : ''}${m.pricing ? ` | $${m.pricing.input}/${m.pricing.output} per M` : ''}${m.reasoning ? ' | reasoning' : ''}">
                      ${m.name}
                      ${m.reasoning ? html`<span style="color:var(--warn);margin-left:2px;">R</span>` : nothing}
                      ${m.pricing ? html`<span style="color:var(--text-dim);margin-left:3px;font-size:10px;">$${m.pricing.input}</span>` : nothing}
                    </button>
                  `;
                })}
              </div>
            ` : nothing}
          </div>
        `;
      })}
    </div>
  `;
}

function _renderLocalModels(app) {
  if (!_localScan && !_localScanning) {
    _scanLocal(app);
  }
  if (_localScanning) {
    return html`<p style="color:var(--text-dim);font-size:13px;">扫描硬件和本地模型...</p>`;
  }
  if (!_localScan) return nothing;

  const hw = _localScan.hardware || {};
  const installed = _localScan.installed_models || [];
  const rec = _localScan.recommended_model || "";
  const recDesc = _localScan.recommended_desc || "";
  const advice = _localScan.advice || [];
  const activeLocal = _localScan.active_model || "";
  const catalog = _localScan.catalog_recommendations || [];

  return html`
    <!-- 硬件信息 -->
    <div style="background:var(--card-bg,var(--bg-secondary,#1e293b));border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:10px;">
      <div style="font-weight:600;font-size:13px;margin-bottom:6px;color:var(--text);">硬件配置</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:12px;color:var(--text);">
        <span><b>CPU:</b> ${hw.cpu || '?'}</span>
        <span><b>核心:</b> ${hw.cpu_cores || '?'}</span>
        <span><b>内存:</b> ${hw.ram_gb || 0}GB (可用 ${hw.ram_free_gb || 0}GB)</span>
        <span><b>GPU:</b> ${hw.gpu || 'None'}</span>
        <span><b>GPU显存:</b> ${hw.gpu_vram_gb || 0}GB</span>
        <span><b>系统:</b> ${hw.os || '?'} ${hw.arch || ''}</span>
      </div>
    </div>

    <!-- 推荐 -->
    <div style="background:var(--card-bg,var(--bg-secondary,#1e293b));border:1px solid var(--accent,#3b82f6)33;border-radius:8px;padding:10px 12px;margin-bottom:10px;">
      <div style="font-weight:600;font-size:13px;color:var(--accent);">推荐模型: ${rec}</div>
      <div style="font-size:12px;color:var(--text-dim);margin-top:2px;">${recDesc}</div>
      ${advice.map(a => html`<div style="font-size:11px;color:var(--text-dim);margin-top:2px;">- ${a}</div>`)}
    </div>

    <!-- 已安装模型 -->
    <div style="margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div>
          <span style="font-weight:600;font-size:13px;color:var(--text);">已安装模型 (${installed.length})</span>
          <span style="font-weight:400;color:var(--text-dim);font-size:11px;margin-left:4px;">
            Ollama ${_localScan.ollama_running ? '运行中' : '未运行'}
          </span>
        </div>
        ${installed.length > 3 ? html`
          <button class="btn" style="font-size:10px;padding:2px 8px;"
            @click=${() => { _localModelsCollapsed = !_localModelsCollapsed; app.requestUpdate(); }}>
            ${_localModelsCollapsed ? `展开 (${installed.length})` : '收起'}
          </button>
        ` : nothing}
      </div>
      ${installed.length === 0 ? html`<p style="color:var(--text-dim);font-size:12px;">未安装任何本地模型</p>` : html`
        <div style="display:flex;flex-direction:column;gap:4px;
                    ${_localModelsCollapsed ? 'max-height:0;overflow:hidden;' : installed.length > 4 ? 'max-height:240px;overflow-y:auto;' : ''}">
          ${installed.map(m => {
            const isActive = m.name === activeLocal;
            return html`
              <div style="display:flex;justify-content:space-between;align-items:center;
                          border:1px solid var(--border);border-radius:6px;padding:6px 10px;
                          ${isActive ? 'border-color:var(--accent);background:rgba(var(--accent-rgb,59,130,246),0.08);' : ''}">
                <div>
                  <span style="font-weight:600;font-size:13px;color:var(--text);">${m.name}</span>
                  <span style="color:var(--text-dim);font-size:11px;margin-left:6px;">${m.size_gb}GB | ${m.params || '?'}</span>
                  ${m.tool_support ? html`<span style="color:var(--ok);font-size:10px;margin-left:4px;">tools</span>` : nothing}
                  ${isActive ? html`<span style="background:var(--accent);color:#fff;padding:1px 5px;border-radius:6px;font-size:10px;font-weight:700;margin-left:4px;">当前</span>` : nothing}
                </div>
                <button class="btn" style="font-size:11px;padding:2px 8px;"
                  @click=${() => _doSwitch(app, "local", m.name)}>
                  ${isActive ? '已选' : '使用'}
                </button>
              </div>
            `;
          })}
        </div>
      `}
    </div>

    <!-- 推荐安装 -->
    <div>
      <div style="font-weight:600;font-size:13px;margin-bottom:6px;">推荐安装</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;">
        ${catalog.filter(c => !installed.some(i => i.name === c.name)).slice(0, 6).map(c => html`
          <button class="btn" style="font-size:11px;padding:3px 8px;"
            title="${c.desc} | VRAM: ${c.vram_gb}GB | 中文: ${(c.chinese * 100).toFixed(0)}%"
            @click=${() => _doInstall(app, c.name)}>
            ${c.name} <span style="color:var(--text-dim);font-size:10px;">${c.params_b}B</span>
          </button>
        `)}
      </div>
    </div>
  `;
}

export function renderConfig(app) {
  return html`
    <!-- 云端模型 -->
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>云端模型 (API)</span>
        <div style="display:flex;gap:6px;align-items:center;">
          ${_switchStatus ? html`<span style="font-size:11px;color:var(--accent);">${_switchStatus}</span>` : nothing}
          <button class="btn" style="font-size:11px;" @click=${() => { _modelData = null; app.requestUpdate(); }}>刷新</button>
        </div>
      </div>
      ${_renderCloudProviders(app)}
      <div style="margin-top:10px;border-top:1px solid var(--border);padding-top:10px;">
        <div style="font-size:12px;font-weight:600;margin-bottom:6px;">验证 API Key</div>
        <div style="display:flex;gap:6px;align-items:center;">
          <select class="form-select" id="cfg-provider" style="flex:0 0 120px;font-size:12px;">
            ${(_modelData?.cloud_providers || []).map(p => html`
              <option value="${p.id}" ?selected=${app.modelInfo?.provider === p.id}>${p.name}</option>
            `)}
          </select>
          <input class="form-input" type="password" id="cfg-apikey" placeholder="sk-..." style="flex:1;font-size:12px;" />
          <button class="btn btn--primary" style="font-size:11px;white-space:nowrap;" @click=${async () => {
            const provider = document.getElementById("cfg-provider").value;
            const apiKey = document.getElementById("cfg-apikey").value;
            const statusEl = document.getElementById("cfg-status");
            statusEl.textContent = "验证中...";
            statusEl.style.color = "var(--warn)";
            try {
              const data = await api.verifyConnection(provider, apiKey);
              if (data.status === "ok") {
                statusEl.textContent = "已连接";
                statusEl.style.color = "var(--ok)";
                _modelData = null; _loadModels(app);
                app._refreshStatus();
              } else {
                statusEl.textContent = "失败";
                statusEl.style.color = "var(--danger)";
              }
            } catch (e) {
              statusEl.textContent = "错误";
              statusEl.style.color = "var(--danger)";
            }
          }}>测试</button>
          <span id="cfg-status" class="mono" style="font-size:11px;min-width:30px;"></span>
        </div>
      </div>
    </div>

    <!-- 本地模型 -->
    <div class="card" style="margin-top:16px">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>本地模型 (Ollama)</span>
        <button class="btn" style="font-size:11px;" @click=${() => { _localScan = null; _localScanning = false; _scanLocal(app); }}>
          重新扫描
        </button>
      </div>
      ${_renderLocalModels(app)}
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
          <option value="30" ?selected=${app.brainStatus?.daemon?.interval === 30}>30秒 (快速)</option>
          <option value="60" ?selected=${!app.brainStatus?.daemon?.interval || app.brainStatus?.daemon?.interval === 60}>60秒 (正常)</option>
          <option value="120" ?selected=${app.brainStatus?.daemon?.interval === 120}>120秒 (慢速)</option>
          <option value="300" ?selected=${app.brainStatus?.daemon?.interval === 300}>300秒 (极慢)</option>
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">自动求助老师</label>
        <select class="form-select" @change=${async (e) => {
          await api.setAutoAsk(e.target.value === "on");
        }}>
          <option value="on" ?selected=${app.brainStatus?.daemon?.auto_ask !== false}>开启</option>
          <option value="off" ?selected=${app.brainStatus?.daemon?.auto_ask === false}>关闭</option>
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
