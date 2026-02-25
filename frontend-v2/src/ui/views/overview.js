/**
 * Overview view — 系统仪表盘
 * 聚合展示：系统快照 + 大脑 + 插件 + 通道 + MCP + 工具
 */
import { html, nothing } from "lit";
import { icons } from "../icons.js";

let _pluginData = null;
let _channelData = null;
let _mcpData = null;
let _lastDashLoad = 0;

async function _loadDashboardData() {
  try {
    const [p, c, m] = await Promise.all([
      fetch("/api/plugins").then(r => r.json()).catch(() => null),
      fetch("/api/channel/status").then(r => r.json()).catch(() => null),
      fetch("/api/mcp/servers").then(r => r.json()).catch(() => null),
    ]);
    _pluginData = p;
    _channelData = c;
    _mcpData = m;
  } catch (e) { /* ignore */ }
}

export function renderOverview(app) {
  const s = app.status || {};
  const llm = s.llm || {};
  const ports = s.ports || {};
  const tools = s.tools || [];
  const d = app.brainStatus?.daemon || {};
  const awake = app.brainStatus?.awake;
  const q = d.queue || {};

  const portCount = Object.values(ports).filter(Boolean).length;
  const portTotal = Object.keys(ports).length;

  // 异步加载插件/通道/MCP 数据（每次进入概览页都刷新）
  if (!_pluginData || (Date.now() - (_lastDashLoad || 0)) > 30000) {
    _loadDashboardData().then(() => { _lastDashLoad = Date.now(); app.requestUpdate(); });
  }

  const plugins = _pluginData?.plugins || [];
  const pluginLoaded = plugins.filter(p => p.status === "loaded").length;
  const pluginTools = plugins.reduce((s, p) => s + (p.tools ? p.tools.length : 0), 0);
  const channels = _channelData?.channels || [];
  const channelConfigured = channels.filter(c => c.configured).length;
  const mcpServers = _mcpData?.servers || [];
  const mcpConnected = mcpServers.filter(s => s.connected).length;

  return html`
    <!-- 顶部统计 4 列 -->
    <section class="overview-grid-4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
      <div class="card stat-card-lg">
        <div class="stat-label">工具总数</div>
        <div class="stat-value-lg">${tools.length}</div>
        <div class="stat-sub">内置 + 插件 + MCP</div>
      </div>
      <div class="card stat-card-lg">
        <div class="stat-label">插件</div>
        <div class="stat-value-lg">${pluginLoaded}/${plugins.length}</div>
        <div class="stat-sub">${pluginTools} 个插件工具</div>
      </div>
      <div class="card stat-card-lg">
        <div class="stat-label">通道</div>
        <div class="stat-value-lg">${channelConfigured}/${channels.length}</div>
        <div class="stat-sub">${channelConfigured > 0 ? "已配置" : "未配置"}</div>
      </div>
      <div class="card stat-card-lg">
        <div class="stat-label">MCP</div>
        <div class="stat-value-lg">${mcpConnected}/${mcpServers.length}</div>
        <div class="stat-sub">${mcpConnected > 0 ? "已连接" : "未配置"}</div>
      </div>
    </section>

    <!-- 2列网格 -->
    <section class="overview-grid-2" style="margin-top:12px;">
      <div class="card">
        <div class="card-title">系统快照</div>
        <div class="card-sub">当前系统运行状态一览</div>
        <div class="stat-grid" style="margin-top:16px;">
          <div class="stat">
            <div class="stat-label">连接状态</div>
            <div class="stat-value ${app.connected ? 'text-ok' : 'text-danger'}">
              ${app.connected ? "已连接" : "已断开"}
            </div>
          </div>
          <div class="stat">
            <div class="stat-label">语言模型</div>
            <div class="stat-value ${llm.available ? 'text-ok' : 'text-danger'}">
              ${llm.available ? "就绪" : "离线"}
            </div>
            <div class="stat-sub">${llm.model || "--"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">提供商</div>
            <div class="stat-value">${llm.provider || "未知"}</div>
          </div>
          <div class="stat">
            <div class="stat-label">端口状态</div>
            <div class="stat-value ${portCount === portTotal ? 'text-ok' : 'text-warn'}">
              ${portCount}/${portTotal}
            </div>
            <div class="stat-sub">活跃端口</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">大脑守护进程</div>
        <div class="card-sub">OODA 循环状态与任务调度</div>
        <div class="stat-grid" style="margin-top:16px;">
          <div class="stat">
            <div class="stat-label">大脑状态</div>
            <div class="stat-value ${awake ? 'text-ok' : 'text-danger'}">
              ${awake ? "运行中" : "休眠"}
            </div>
            <div class="stat-sub">${d.paused ? "已暂停" : "正常运行"}</div>
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
    </section>

    <!-- 通道状态 -->
    ${channels.length > 0 ? html`
    <div class="card" style="margin-top:12px;">
      <div class="card-title">通道状态</div>
      <div class="card-sub">消息接入通道（Telegram / 飞书 / 企业微信 / 微信）</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-top:12px;">
        ${channels.map(ch => html`
          <div style="padding:12px;background:var(--bg-2);border-radius:8px;display:flex;align-items:center;gap:10px;">
            <span style="width:8px;height:8px;border-radius:50%;background:${ch.configured ? 'var(--green,#22c55e)' : 'var(--fg-3,#888)'}"></span>
            <div>
              <div style="font-size:14px;font-weight:600;color:var(--fg);">${ch.label}</div>
              <div style="font-size:12px;color:var(--fg-3);">${ch.configured ? "已配置" : "未配置"}</div>
            </div>
          </div>
        `)}
      </div>
    </div>
    ` : nothing}

    <!-- 工具列表 -->
    <div class="card" style="margin-top:12px;">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>工具列表 (${tools.length})</span>
        <button class="btn" style="font-size:12px;" @click=${() => { _pluginData = null; app.requestUpdate(); }}>刷新</button>
      </div>
      <div class="card-sub">已注册的工具适配器</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:12px;">
        ${tools.map(t => html`<span class="pill">${t}</span>`)}
      </div>
    </div>

    <!-- 端口详情 -->
    <div class="card" style="margin-top:12px;">
      <div class="card-title">端口状态</div>
      <div class="card-sub">六边形架构核心端口</div>
      <div class="stat-grid" style="margin-top:12px;">
        ${Object.entries(ports).map(([name, ok]) => html`
          <div class="stat">
            <div class="stat-label">${name}</div>
            <div class="stat-value ${ok ? 'text-ok' : 'text-danger'}">${ok ? "✓ 活跃" : "✗ 离线"}</div>
          </div>
        `)}
      </div>
    </div>
  `;
}
