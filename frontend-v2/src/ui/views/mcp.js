/**
 * MCP view — MCP Server 管理界面
 */
import { html, nothing } from "lit";

let _servers = null;
let _mcpTools = null;
let _adding = false;
let _discovering = false;
let _discoverMsg = "";
let _addForm = { name: "", transport: "stdio", command: "", args: "", url: "" };

async function _loadMcp() {
  try {
    const [s, t] = await Promise.all([
      fetch("/api/mcp/servers").then(r => r.json()),
      fetch("/api/mcp/tools").then(r => r.json()),
    ]);
    _servers = s.servers || [];
    _mcpTools = t.tools || [];
  } catch (e) {
    console.error("加载MCP数据失败:", e);
  }
}

async function _discover(app) {
  _discovering = true;
  _discoverMsg = "";
  app.requestUpdate();
  try {
    const res = await fetch("/api/mcp/discover", { method: "POST" });
    const data = await res.json();
    _discoverMsg = `发现 ${data.tools_discovered} 个工具`;
    _servers = null;
    _mcpTools = null;
  } catch (e) {
    _discoverMsg = `发现失败: ${e.message}`;
  }
  _discovering = false;
  app.requestUpdate();
  setTimeout(() => { _discoverMsg = ""; app.requestUpdate(); }, 4000);
}

async function _addServer(app) {
  const body = {
    name: _addForm.name,
    transport: _addForm.transport,
    enabled: true,
  };
  if (_addForm.transport === "stdio") {
    body.command = _addForm.command;
    body.args = _addForm.args ? _addForm.args.split(" ").filter(Boolean) : [];
  } else {
    body.url = _addForm.url;
  }
  try {
    await fetch("/api/mcp/servers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    _adding = false;
    _servers = null;
    _addForm = { name: "", transport: "stdio", command: "", args: "", url: "" };
  } catch (e) {
    console.error("添加失败:", e);
  }
  app.requestUpdate();
}

async function _removeServer(app, name) {
  try {
    await fetch(`/api/mcp/servers/${name}`, { method: "DELETE" });
    _servers = null;
  } catch (e) {
    console.error("删除失败:", e);
  }
  app.requestUpdate();
}

export function renderMcp(app) {
  if (_servers === null) {
    _loadMcp().then(() => app.requestUpdate());
    return html`<div class="card"><div class="card-title">加载中...</div></div>`;
  }

  return html`
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>MCP Server 管理</span>
        <div style="display:flex;gap:8px;">
          <button class="btn btn--primary" ?disabled=${_discovering}
            @click=${() => _discover(app)} style="font-size:12px;">
            ${_discovering ? "发现中..." : "🔍 发现工具"}
          </button>
          <button class="btn" @click=${() => { _adding = !_adding; app.requestUpdate(); }}
            style="font-size:12px;">
            ${_adding ? "取消" : "➕ 添加"}
          </button>
          <button class="btn" @click=${() => { _servers = null; _mcpTools = null; app.requestUpdate(); }}
            style="font-size:12px;">刷新</button>
        </div>
      </div>
      ${_discoverMsg ? html`<div style="padding:8px 12px;margin:8px 0;border-radius:6px;background:var(--bg-2);font-size:13px;color:var(--fg-2);">${_discoverMsg}</div>` : nothing}

      <!-- 统计 -->
      <div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap;">
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${_servers.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">服务器</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${_servers.filter(s => s.connected).length}</div>
          <div style="font-size:12px;color:var(--fg-3);">已连接</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${(_mcpTools || []).length}</div>
          <div style="font-size:12px;color:var(--fg-3);">MCP工具</div>
        </div>
      </div>

      <!-- 添加表单 -->
      ${_adding ? html`
        <div style="padding:16px;background:var(--bg-2);border-radius:8px;margin:12px 0;">
          <div style="font-size:14px;font-weight:600;margin-bottom:12px;">添加 MCP Server</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <input type="text" placeholder="名称 (如 filesystem)"
              .value=${_addForm.name}
              @input=${(e) => { _addForm.name = e.target.value; }}
              style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;">
            <select .value=${_addForm.transport}
              @change=${(e) => { _addForm.transport = e.target.value; app.requestUpdate(); }}
              style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;">
              <option value="stdio">stdio (子进程)</option>
              <option value="http">http (远程)</option>
            </select>
          </div>
          ${_addForm.transport === "stdio" ? html`
            <div style="display:grid;grid-template-columns:1fr 2fr;gap:8px;margin-top:8px;">
              <input type="text" placeholder="命令 (如 npx)"
                .value=${_addForm.command}
                @input=${(e) => { _addForm.command = e.target.value; }}
                style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;">
              <input type="text" placeholder="参数 (空格分隔)"
                .value=${_addForm.args}
                @input=${(e) => { _addForm.args = e.target.value; }}
                style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;">
            </div>
          ` : html`
            <input type="text" placeholder="URL (如 http://localhost:3001/mcp)"
              .value=${_addForm.url}
              @input=${(e) => { _addForm.url = e.target.value; }}
              style="padding:8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:13px;margin-top:8px;width:100%;box-sizing:border-box;">
          `}
          <button class="btn btn--primary" style="margin-top:10px;font-size:13px;"
            @click=${() => _addServer(app)}>保存</button>
        </div>
      ` : nothing}

      <!-- 服务器列表 -->
      ${_servers.length === 0 ? html`
        <div style="padding:24px;text-align:center;color:var(--fg-3);font-size:14px;">
          <p>暂无 MCP Server 配置</p>
          <p style="font-size:12px;margin-top:8px;">点击「添加」配置 MCP Server，或在 <code>data/mcp_servers.json</code> 中手动配置。</p>
        </div>
      ` : _servers.map(srv => html`
        <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 0;border-bottom:1px solid var(--border);">
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:15px;font-weight:600;color:var(--fg);">${srv.name}</span>
              <span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:${srv.connected ? '#22c55e22' : '#88888822'};color:${srv.connected ? '#22c55e' : '#888'};font-weight:600;">
                ${srv.connected ? "已连接" : "未连接"}
              </span>
              <span style="font-size:11px;color:var(--fg-3);">${srv.transport || "http"}</span>
            </div>
            <div style="font-size:12px;color:var(--fg-3);margin-top:4px;">
              ${srv.transport === "stdio" ? `${srv.command} ${(srv.args || []).join(" ")}` : srv.url || ""}
              ${srv.tool_count > 0 ? ` · ${srv.tool_count} 个工具` : ""}
            </div>
          </div>
          <button class="btn" style="font-size:12px;color:var(--danger,#ef4444);"
            @click=${() => _removeServer(app, srv.name)}>删除</button>
        </div>
      `)}
    </div>

    <!-- MCP 工具列表 -->
    ${(_mcpTools || []).length > 0 ? html`
    <div class="card" style="margin-top:16px;">
      <div class="card-title">MCP 工具 (${_mcpTools.length})</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;">
        ${_mcpTools.map(t => html`
          <span class="pill" title="${t.description}">${t.name}</span>
        `)}
      </div>
    </div>
    ` : nothing}

    <!-- 使用说明 -->
    <div class="card" style="margin-top:16px;">
      <div class="card-title">什么是 MCP?</div>
      <div style="font-size:13px;color:var(--fg-3);line-height:1.8;">
        <p><strong>Model Context Protocol</strong> 是 Claude/Cursor 生态的工具协议标准。</p>
        <p>接入 MCP Server = 瞬间获得数百个现成工具（文件系统、数据库、GitHub、Slack 等）。</p>
        <p style="margin-top:8px;">示例配置（stdio 方式）：</p>
        <pre style="background:var(--bg-2);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:8px 0;">名称: filesystem
命令: npx
参数: -y @modelcontextprotocol/server-filesystem /tmp</pre>
      </div>
    </div>
  `;
}
