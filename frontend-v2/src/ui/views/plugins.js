/**
 * Plugins view — 插件管理界面（含热加载 + PluginHub）
 */
import { html, nothing } from "lit";

let _plugins = [];
let _loaded = false;
let _toggling = null;
let _reloading = false;
let _reloadMsg = "";
let _hubResults = null;
let _hubSearching = false;
let _hubInstalling = null;
let _hubMsg = "";

async function _searchHub(app) {
  const input = document.getElementById("hub-search-input");
  const q = input?.value?.trim();
  if (!q) return;
  _hubSearching = true;
  _hubResults = null;
  _hubMsg = "";
  app.requestUpdate();
  try {
    const res = await fetch(`/api/plugins/hub/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    _hubResults = data.results || [];
  } catch (e) {
    _hubMsg = `搜索失败: ${e.message}`;
  }
  _hubSearching = false;
  app.requestUpdate();
}

async function _installHub(app, name) {
  _hubInstalling = name;
  _hubMsg = "";
  app.requestUpdate();
  try {
    const res = await fetch("/api/plugins/hub/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (data.status === "ok" || data.status === "installed") {
      _hubMsg = `✅ 插件 ${name} 安装成功！请点击「热加载」激活。`;
      _loaded = false;
    } else {
      _hubMsg = `❌ 安装失败: ${data.message || data.error || "未知错误"}`;
    }
  } catch (e) {
    _hubMsg = `❌ 安装异常: ${e.message}`;
  }
  _hubInstalling = null;
  app.requestUpdate();
  setTimeout(() => { _hubMsg = ""; app.requestUpdate(); }, 6000);
}

async function _loadPlugins() {
  try {
    const res = await fetch("/api/plugins");
    const data = await res.json();
    _plugins = data.plugins || [];
    _loaded = true;
  } catch (e) {
    console.error("加载插件列表失败:", e);
  }
}

async function _togglePlugin(app, name, enabled) {
  _toggling = name;
  app.requestUpdate();
  try {
    await fetch(`/api/plugins/${name}/toggle`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    await _loadPlugins();
  } catch (e) {
    console.error("切换插件失败:", e);
  }
  _toggling = null;
  app.requestUpdate();
}

async function _hotReload(app) {
  _reloading = true;
  _reloadMsg = "";
  app.requestUpdate();
  try {
    const res = await fetch("/api/plugins/reload", { method: "POST" });
    const data = await res.json();
    _reloadMsg = `✅ 加载 ${data.plugins} 个插件, ${data.tools} 个工具`;
    await _loadPlugins();
  } catch (e) {
    _reloadMsg = `❌ 热加载失败: ${e.message}`;
  }
  _reloading = false;
  app.requestUpdate();
  setTimeout(() => { _reloadMsg = ""; app.requestUpdate(); }, 4000);
}

function _statusBadge(status) {
  const colors = {
    loaded: "var(--green, #22c55e)",
    disabled: "var(--fg-3, #888)",
    platform_skip: "var(--yellow, #eab308)",
  };
  const labels = {
    loaded: "运行中",
    disabled: "已禁用",
    platform_skip: "平台不匹配",
  };
  const color = colors[status] || "var(--fg-3)";
  const label = labels[status] || status;
  return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:${color}22;color:${color};font-weight:600;">${label}</span>`;
}

function _renderPluginCard(app, plugin) {
  const isToggling = _toggling === plugin.name;
  return html`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--border);">
      <div style="flex:1;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:15px;font-weight:600;color:var(--fg);">${plugin.name}</span>
          <span style="font-size:11px;color:var(--fg-3);">v${plugin.version}</span>
          ${_statusBadge(plugin.status)}
          ${plugin.legacy ? html`<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--fg-3)22;color:var(--fg-3);">旧格式</span>` : nothing}
        </div>
        <div style="font-size:13px;color:var(--fg-2);margin-top:4px;">${plugin.description}</div>
        <div style="font-size:12px;color:var(--fg-3);margin-top:4px;">
          工具: ${plugin.tools.length > 0 ? plugin.tools.join(", ") : "无"}
          ${plugin.platform.length > 0 ? html` · 平台: ${plugin.platform.join(", ")}` : nothing}
        </div>
      </div>
      <div>
        ${plugin.legacy ? nothing : html`
          <button class="btn ${plugin.enabled ? '' : 'btn--primary'}" 
            ?disabled=${isToggling}
            @click=${() => _togglePlugin(app, plugin.name, !plugin.enabled)}
            style="min-width:64px;">
            ${isToggling ? "..." : (plugin.enabled ? "禁用" : "启用")}
          </button>
        `}
      </div>
    </div>
  `;
}

export function renderPlugins(app) {
  if (!_loaded) {
    _loadPlugins().then(() => app.requestUpdate());
    return html`<div class="card"><div class="card-title">加载中...</div></div>`;
  }

  const loaded = _plugins.filter(p => p.status === "loaded");
  const disabled = _plugins.filter(p => p.status === "disabled");
  const totalTools = _plugins.reduce((s, p) => s + (p.tools ? p.tools.length : 0), 0);

  return html`
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>插件管理</span>
        <div style="display:flex;gap:8px;">
          <button class="btn btn--primary" ?disabled=${_reloading}
            @click=${() => _hotReload(app)}
            style="font-size:12px;">
            ${_reloading ? "加载中..." : "🔄 热加载"}
          </button>
          <button class="btn" @click=${() => { _loaded = false; app.requestUpdate(); }}
            style="font-size:12px;">刷新</button>
        </div>
      </div>
      ${_reloadMsg ? html`<div style="padding:8px 12px;margin:8px 0;border-radius:6px;background:var(--bg-2);font-size:13px;color:var(--fg-2);">${_reloadMsg}</div>` : nothing}
      <div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap;">
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${loaded.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">运行中</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--fg-3);">${disabled.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">已禁用</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${totalTools}</div>
          <div style="font-size:12px;color:var(--fg-3);">工具总数</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--fg-3);">${_plugins.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">总计</div>
        </div>
      </div>
      ${_plugins.map(p => _renderPluginCard(app, p))}
    </div>
    <div class="card" style="margin-top:16px;">
      <div class="card-title">PluginHub 搜索安装</div>
      <div style="display:flex;gap:8px;margin:12px 0;">
        <input type="text" placeholder="搜索插件 (如 weather, notes...)" id="hub-search-input"
          style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);color:var(--fg);font-size:13px;"
          @keydown=${(e) => { if (e.key === 'Enter') _searchHub(app); }}>
        <button class="btn btn--primary" @click=${() => _searchHub(app)}
          ?disabled=${_hubSearching} style="font-size:13px;">
          ${_hubSearching ? "搜索中..." : "🔍 搜索"}
        </button>
      </div>
      ${_hubResults !== null ? html`
        ${_hubResults.length === 0 ? html`
          <div style="padding:16px;text-align:center;color:var(--fg-3);font-size:13px;">未找到匹配的插件</div>
        ` : _hubResults.map(r => html`
          <div style="display:flex;align-items:center;justify-content:space-between;padding:12px;background:var(--bg-2);border-radius:8px;margin-bottom:8px;">
            <div style="flex:1;">
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-size:14px;font-weight:600;color:var(--fg);">${r.name}</span>
                <span style="font-size:11px;color:var(--fg-3);">v${r.version || '?'}</span>
              </div>
              <div style="font-size:12px;color:var(--fg-2);margin-top:4px;">${r.description || ''}</div>
            </div>
            <button class="btn btn--primary" style="font-size:12px;min-width:60px;"
              ?disabled=${_hubInstalling === r.name}
              @click=${() => _installHub(app, r.name)}>
              ${_hubInstalling === r.name ? "安装中..." : "安装"}
            </button>
          </div>
        `)}
      ` : nothing}
      ${_hubMsg ? html`<div style="padding:8px 12px;margin:8px 0;border-radius:6px;background:var(--bg-2);font-size:13px;color:var(--fg-2);">${_hubMsg}</div>` : nothing}
    </div>

    <div class="card" style="margin-top:16px;">
      <div class="card-title">开发插件</div>
      <div style="font-size:13px;color:var(--fg-3);line-height:1.8;">
        <p>在 <code>skills/</code> 目录下创建子目录，包含 <code>manifest.json</code> 和 <code>main.py</code>：</p>
        <pre style="background:var(--bg-2);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:8px 0;">skills/my_plugin/
  manifest.json   # 名称、版本、工具声明
  main.py         # 导出 XxxAdapter 类</pre>
        <p>添加新插件后点击「热加载」按钮即可立即使用，无需重启服务器。</p>
      </div>
    </div>
  `;
}
