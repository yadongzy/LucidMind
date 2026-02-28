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
let _trustChanging = null;
let _mcpWrapping = null;

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

async function _changeTrust(app, name, level) {
  _trustChanging = name;
  app.requestUpdate();
  try {
    const res = await fetch(`/api/plugins/${name}/trust`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trust_level: level }),
    });
    const data = await res.json();
    if (data.status === "ok") {
      _loaded = false;
    }
  } catch (e) {
    console.error("信任等级变更失败:", e);
  }
  _trustChanging = null;
  app.requestUpdate();
}

async function _wrapMcp(app, name) {
  _mcpWrapping = name;
  app.requestUpdate();
  try {
    const res = await fetch(`/api/plugins/${name}/mcp-wrap`, { method: "POST" });
    const data = await res.json();
    if (data.status === "ok") {
      _reloadMsg = `\u2705 ${name} \u5df2\u5c01\u88c5\u4e3a MCP Server`;
    } else {
      _reloadMsg = `\u274c MCP \u5c01\u88c5\u5931\u8d25: ${data.detail || ""}`;
    }
  } catch (e) {
    _reloadMsg = `\u274c MCP \u5c01\u88c5\u5f02\u5e38: ${e.message}`;
  }
  _mcpWrapping = null;
  app.requestUpdate();
  setTimeout(() => { _reloadMsg = ""; app.requestUpdate(); }, 4000);
}

function _trustBadge(trustLevel) {
  if (trustLevel === "sandboxed") {
    return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#f59e0b22;color:#f59e0b;font-weight:600;" title="\u5b50\u8fdb\u7a0b\u9694\u79bb\u6267\u884c\uff0c\u9996\u6b21\u4f7f\u7528\u9700\u786e\u8ba4">\ud83d\udd12 \u6c99\u7bb1</span>`;
  }
  return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#22c55e22;color:#22c55e;font-weight:600;" title="\u8fdb\u7a0b\u5185\u6267\u884c\uff0c\u5df2\u5ba1\u6838">\u26a1 \u5df2\u4fe1\u4efb</span>`;
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

function _kindBadge(kind) {
  if (!kind || kind === "code") {
    return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#3b82f622;color:#3b82f6;font-weight:600;" title="代码执行型技能">⚡ 代码</span>`;
  }
  if (kind === "prompt") {
    return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#8b5cf622;color:#8b5cf6;font-weight:600;" title="知识文档型技能（SKILL.md）">📄 知识</span>`;
  }
  if (kind === "hybrid") {
    return html`<span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#06b6d422;color:#06b6d4;font-weight:600;" title="代码+知识混合型技能">🔀 混合</span>`;
  }
  return nothing;
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
          ${_kindBadge(plugin.kind)}
          ${plugin.trust_level ? _trustBadge(plugin.trust_level) : nothing}
          ${plugin.legacy ? html`<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--fg-3)22;color:var(--fg-3);">旧格式</span>` : nothing}
        </div>
        <div style="font-size:13px;color:var(--fg-2);margin-top:4px;">${plugin.description}</div>
        <div style="font-size:12px;color:var(--fg-3);margin-top:4px;">
          ${plugin.kind === 'prompt' ? html`知识: ${plugin.prompt_tokens || 0} 字符` : html`工具: ${plugin.tools && plugin.tools.length > 0 ? plugin.tools.join(", ") : "无"}`}
          ${plugin.platform && plugin.platform.length > 0 ? html` · 平台: ${plugin.platform.join(", ")}` : nothing}
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;">
        ${plugin.trust_level === "sandboxed" && !plugin.legacy ? html`
          <button class="btn" style="font-size:11px;min-width:70px;"
            ?disabled=${_trustChanging === plugin.name}
            @click=${() => _changeTrust(app, plugin.name, "audited")}
            title="\u5347\u7ea7\u4e3a\u8fdb\u7a0b\u5185\u6267\u884c\uff08\u5df2\u5ba1\u6838\uff09">
            ${_trustChanging === plugin.name ? "..." : "\u2b06 \u4fe1\u4efb"}
          </button>
        ` : nothing}
        ${!plugin.legacy && plugin.status === "loaded" ? html`
          <button class="btn" style="font-size:11px;min-width:50px;"
            ?disabled=${_mcpWrapping === plugin.name}
            @click=${() => _wrapMcp(app, plugin.name)}
            title="\u5c01\u88c5\u4e3a MCP Server">
            ${_mcpWrapping === plugin.name ? "..." : "MCP"}
          </button>
        ` : nothing}
        ${plugin.legacy ? nothing : html`
          <button class="btn ${plugin.enabled ? '' : 'btn--primary'}" 
            ?disabled=${isToggling}
            @click=${() => _togglePlugin(app, plugin.name, !plugin.enabled)}
            style="min-width:64px;">
            ${isToggling ? "..." : (plugin.enabled ? "\u7981\u7528" : "\u542f\u7528")}
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
  const promptSkills = _plugins.filter(p => p.kind === "prompt" && p.status === "loaded");
  const hybridSkills = _plugins.filter(p => p.kind === "hybrid" && p.status === "loaded");

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
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:#8b5cf6;">${promptSkills.length + hybridSkills.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">知识技能</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:#f59e0b;">${_plugins.filter(p => p.trust_level === 'sandboxed').length}</div>
          <div style="font-size:12px;color:var(--fg-3);">沙箱隔离</div>
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
        <p>在 <code>skills/</code> 目录下创建子目录，支持三种技能形态：</p>
        <pre style="background:var(--bg-2);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:8px 0;">⚡ 代码技能 (kind: "code", 默认)
skills/my_tool/
  manifest.json   # 名称、版本、工具声明
  main.py         # 导出 XxxAdapter 类

📄 知识技能 (kind: "prompt")
skills/my_guide/
  manifest.json   # kind: "prompt"
  SKILL.md        # 知识文档，注入 LLM 上下文

🔀 混合技能 (kind: "hybrid")
skills/my_hybrid/
  manifest.json   # kind: "hybrid"
  main.py + SKILL.md</pre>
        <p>添加新插件后点击「热加载」按钮即可立即使用，无需重启服务器。</p>
      </div>
    </div>
  `;
}
