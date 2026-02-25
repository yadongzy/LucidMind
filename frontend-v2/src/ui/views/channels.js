/**
 * Channels view — 多通道管理界面（含一键配置表单）
 */
import { html, nothing } from "lit";

let _channels = null;
let _testResult = {};
let _restarting = {};
let _configOpen = {};    // 展开/收起配置表单
let _configForm = {};    // 表单临时数据
let _configSaving = {};  // 保存中状态
let _configMsg = {};     // 保存结果消息

// ngrok 状态
let _ngrok = null;       // {installed, running, url}
let _ngrokLoading = "";  // "install" | "start" | "stop" | ""
let _ngrokMsg = null;    // {status, message}

async function _loadChannels() {
  try {
    const res = await fetch("/api/channel/status");
    const data = await res.json();
    _channels = data.channels || [];
  } catch (e) {
    console.error("加载通道数据失败:", e);
  }
}

async function _testChannel(name, app) {
  _testResult[name] = { loading: true };
  app.requestUpdate();
  try {
    const res = await fetch(`/api/channel/${name}/test`, { method: "POST" });
    const data = await res.json();
    _testResult[name] = data;
  } catch (e) {
    _testResult[name] = { status: "error", message: e.message };
  }
  app.requestUpdate();
  setTimeout(() => { delete _testResult[name]; app.requestUpdate(); }, 5000);
}

async function _restartChannel(name, app) {
  _restarting[name] = true;
  app.requestUpdate();
  try {
    const res = await fetch(`/api/channel/${name}/restart`, { method: "POST" });
    const data = await res.json();
    _testResult[name] = data;
  } catch (e) {
    _testResult[name] = { status: "error", message: e.message };
  }
  _restarting[name] = false;
  _channels = null;
  await _loadChannels();
  app.requestUpdate();
  setTimeout(() => { delete _testResult[name]; app.requestUpdate(); }, 5000);
}

async function _saveConfig(name, app) {
  const form = _configForm[name] || {};
  _configSaving[name] = true;
  _configMsg[name] = null;
  app.requestUpdate();
  try {
    const res = await fetch(`/api/channel/${name}/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await res.json();
    _configMsg[name] = data;
    if (data.status === "ok") {
      _channels = null;
      await _loadChannels();
    }
  } catch (e) {
    _configMsg[name] = { status: "error", message: e.message };
  }
  _configSaving[name] = false;
  app.requestUpdate();
  setTimeout(() => { _configMsg[name] = null; app.requestUpdate(); }, 6000);
}

const _channelMeta = {
  telegram: {
    icon: "🤖",
    fields: [
      { key: "TELEGRAM_BOT_TOKEN", label: "Bot Token", placeholder: "123456:ABC-DEF...", required: true },
      { key: "TELEGRAM_ALLOWED_USERS", label: "允许的用户ID", placeholder: "逗号分隔, 如 123456,789012", required: false },
    ],
    help: "在 Telegram 找 @BotFather → /newbot → 获取 Token",
  },
  feishu: {
    icon: "📱",
    fields: [
      { key: "FEISHU_APP_ID", label: "App ID", placeholder: "cli_xxxxxxxxxx", required: true },
      { key: "FEISHU_APP_SECRET", label: "App Secret", placeholder: "飞书应用密钥", required: true },
    ],
    help: "🚀 长连接模式 — 无需公网域名，无需 ngrok\n1. 飞书开放平台 → 创建企业自建应用\n2. 开启机器人能力\n3. 事件订阅选「使用长连接接收事件」\n4. 添加事件: im.message.receive_v1\n5. 填入 App ID 和 Secret → 保存即可",
  },
  wecom: {
    icon: "💼",
    fields: [
      { key: "WECOM_CORP_ID", label: "Corp ID", placeholder: "企业ID ww_xxx", required: true },
      { key: "WECOM_AGENT_ID", label: "Agent ID", placeholder: "应用ID 1000002", required: true },
      { key: "WECOM_SECRET", label: "Secret", placeholder: "应用密钥", required: true },
      { key: "WECOM_TOKEN", label: "Token", placeholder: "接收消息Token", required: false },
    ],
    help: "企业微信管理后台 → 应用管理 → 自建应用\n回调地址: /api/channel/wecom/webhook",
  },
  wechat: {
    icon: "💬",
    fields: [
      { key: "GEWECHAT_BASE_URL", label: "GeweChat 地址", placeholder: "http://localhost:2531", required: true },
      { key: "GEWECHAT_TOKEN", label: "Token (appId)", placeholder: "登录后获取的appId", required: true },
      { key: "GEWECHAT_CALLBACK_URL", label: "回调地址", placeholder: "http://你的IP:8765/api/channel/wechat/webhook", required: false },
      { key: "WECHAT_ALLOWED_WXIDS", label: "允许的微信ID", placeholder: "wxid_xxx,wxid_yyy", required: false },
    ],
    help: "需 Docker 部署 GeweChat 服务\n⚠ 仅供个人研究使用",
  },
};

const _inputStyle = "width:100%;padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--fg);font-size:12px;font-family:monospace;box-sizing:border-box;";

function _renderConfigForm(name, app) {
  const meta = _channelMeta[name];
  if (!meta) return nothing;
  if (!_configForm[name]) _configForm[name] = {};
  const form = _configForm[name];

  return html`
    <div style="margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
      <div style="font-size:12px;font-weight:600;color:var(--fg-2);margin-bottom:10px;">配置凭据</div>
      ${meta.fields.map(f => html`
        <div style="margin-bottom:8px;">
          <label style="display:block;font-size:11px;color:var(--fg-3);margin-bottom:3px;">
            ${f.label} ${f.required ? html`<span style="color:var(--danger,#ef4444);">*</span>` : nothing}
          </label>
          <input type="${f.key.includes('SECRET') || f.key.includes('TOKEN') ? 'password' : 'text'}"
            style="${_inputStyle}"
            placeholder="${f.placeholder}"
            .value=${form[f.key] || ""}
            @input=${(e) => { form[f.key] = e.target.value; }}>
        </div>
      `)}
      <div style="font-size:11px;color:var(--fg-3);white-space:pre-line;margin-bottom:10px;line-height:1.6;">${meta.help}</div>
      <div style="display:flex;gap:8px;align-items:center;">
        <button class="btn" style="font-size:12px;padding:6px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;"
          @click=${() => _saveConfig(name, app)}
          ?disabled=${_configSaving[name]}>
          ${_configSaving[name] ? "保存中..." : "💾 保存并启用"}
        </button>
        <button class="btn" style="font-size:11px;padding:4px 10px;"
          @click=${() => { _configOpen[name] = false; app.requestUpdate(); }}>取消</button>
      </div>
      ${_configMsg[name] ? html`
        <div style="margin-top:8px;padding:6px 10px;border-radius:4px;font-size:12px;
          background:${_configMsg[name].status === 'ok' ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)'};
          color:${_configMsg[name].status === 'ok' ? 'var(--green,#22c55e)' : 'var(--danger,#ef4444)'};">
          ${_configMsg[name].status === 'ok' ? '✅' : '❌'} ${_configMsg[name].message}
        </div>
      ` : nothing}
    </div>
  `;
}

// ── ngrok 管理函数 ──

async function _loadNgrok(app) {
  try {
    const res = await fetch("/api/channel/ngrok/status");
    _ngrok = await res.json();
  } catch (e) {
    _ngrok = { installed: false, running: false, url: "" };
  }
  app?.requestUpdate();
}

async function _ngrokAction(action, app) {
  _ngrokLoading = action;
  _ngrokMsg = null;
  app.requestUpdate();
  try {
    const res = await fetch(`/api/channel/ngrok/${action}`, { method: "POST" });
    const data = await res.json();
    _ngrokMsg = data;
    if (data.url) _ngrok = { installed: true, running: true, url: data.url };
    else await _loadNgrok(app);
  } catch (e) {
    _ngrokMsg = { status: "error", message: e.message };
  }
  _ngrokLoading = "";
  app.requestUpdate();
  if (_ngrokMsg?.status === "ok") {
    setTimeout(() => { _ngrokMsg = null; app.requestUpdate(); }, 8000);
  }
}

function _copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta);
    ta.select(); document.execCommand("copy");
    document.body.removeChild(ta);
  });
}

function _renderNgrokPanel(app) {
  if (_ngrok === null) {
    _loadNgrok(app);
    return nothing;
  }

  return html`
    <div class="card" style="margin-top:16px;">
      <div class="card-title" style="display:flex;align-items:center;gap:8px;">
        <span>🌐 内网穿透 (ngrok)</span>
        ${_ngrok.running ? html`<span style="font-size:11px;color:var(--green,#22c55e);font-weight:400;">运行中</span>` : nothing}
      </div>
      <div style="font-size:13px;color:var(--fg-3);margin-bottom:12px;">
        飞书、企业微信、微信通道需要公网回调地址。ngrok 可将本地服务暴露到公网。
      </div>

      ${!_ngrok.installed ? html`
        <!-- 未安装 -->
        <div style="padding:16px;background:var(--bg-2);border-radius:8px;">
          <div style="font-size:13px;color:var(--fg);margin-bottom:10px;">ngrok 未安装</div>
          <button class="btn" style="font-size:12px;padding:6px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;"
            @click=${() => _ngrokAction("install", app)}
            ?disabled=${_ngrokLoading === "install"}>
            ${_ngrokLoading === "install" ? "安装中（可能需要1-2分钟）..." : "📦 一键安装 ngrok"}
          </button>
          <div style="font-size:11px;color:var(--fg-3);margin-top:8px;">
            通过 Homebrew 安装。也可手动: <span style="font-family:monospace;">brew install ngrok</span>
          </div>
        </div>
      ` : !_ngrok.running ? html`
        <!-- 已安装未运行 -->
        <div style="padding:16px;background:var(--bg-2);border-radius:8px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="width:8px;height:8px;border-radius:50%;background:var(--fg-3)"></span>
            <span style="font-size:13px;color:var(--fg);">ngrok 已安装，隧道未启动</span>
          </div>
          <!-- Authtoken 配置 -->
          <div style="margin-bottom:12px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;">
            <label style="display:block;font-size:11px;color:var(--fg-3);margin-bottom:4px;">
              Authtoken（首次使用必填，在 <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" style="color:var(--accent);">ngrok.com</a> 获取）
            </label>
            <div style="display:flex;gap:6px;">
              <input type="password" id="ngrok-token-input"
                style="flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);color:var(--fg);font-size:12px;font-family:monospace;"
                placeholder="2xxx...your_authtoken">
              <button class="btn" style="font-size:11px;padding:4px 12px;white-space:nowrap;"
                @click=${async () => {
                  const input = document.getElementById("ngrok-token-input");
                  const token = input?.value?.trim();
                  if (!token) { alert("请输入 authtoken"); return; }
                  _ngrokLoading = "authtoken"; app.requestUpdate();
                  try {
                    const res = await fetch("/api/channel/ngrok/authtoken", {
                      method: "POST", headers: {"Content-Type":"application/json"},
                      body: JSON.stringify({token})
                    });
                    const data = await res.json();
                    _ngrokMsg = data;
                  } catch(e) { _ngrokMsg = {status:"error",message:e.message}; }
                  _ngrokLoading = ""; app.requestUpdate();
                }}
                ?disabled=${_ngrokLoading === "authtoken"}>
                ${_ngrokLoading === "authtoken" ? "配置中..." : "� 保存Token"}
              </button>
            </div>
          </div>
          <button class="btn" style="font-size:12px;padding:6px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;"
            @click=${() => _ngrokAction("start", app)}
            ?disabled=${_ngrokLoading === "start"}>
            ${_ngrokLoading === "start" ? "启动中..." : "🚀 启动内网穿透"}
          </button>
        </div>
      ` : html`
        <!-- 运行中 -->
        <div style="padding:16px;background:var(--bg-2);border-radius:8px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="width:8px;height:8px;border-radius:50%;background:var(--green,#22c55e);animation:pulse 2s infinite;"></span>
            <span style="font-size:13px;font-weight:600;color:var(--green,#22c55e);">隧道运行中</span>
          </div>
          <!-- 公网地址 -->
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <div style="flex:1;padding:8px 12px;background:var(--bg);border:1px solid var(--border);border-radius:6px;font-family:monospace;font-size:13px;color:var(--accent);word-break:break-all;">
              ${_ngrok.url}
            </div>
            <button class="btn" style="font-size:11px;padding:6px 12px;white-space:nowrap;"
              @click=${() => { _copyText(_ngrok.url); }}>
              📋 复制
            </button>
          </div>
          <!-- Webhook 地址 -->
          <div style="font-size:12px;color:var(--fg-3);margin-bottom:10px;">
            <div style="font-weight:600;margin-bottom:4px;">各通道回调地址：</div>
            <div style="background:var(--bg);padding:8px 10px;border-radius:4px;font-family:monospace;font-size:11px;line-height:1.8;">
              <div style="display:flex;align-items:center;gap:6px;">
                <span>飞书:</span>
                <span style="color:var(--accent);flex:1;">${_ngrok.url}/api/channel/feishu/webhook</span>
                <button style="font-size:10px;padding:2px 6px;border:1px solid var(--border);border-radius:3px;background:var(--bg-2);color:var(--fg-3);cursor:pointer;"
                  @click=${() => _copyText(_ngrok.url + "/api/channel/feishu/webhook")}>复制</button>
              </div>
              <div style="display:flex;align-items:center;gap:6px;">
                <span>企微:</span>
                <span style="color:var(--accent);flex:1;">${_ngrok.url}/api/channel/wecom/webhook</span>
                <button style="font-size:10px;padding:2px 6px;border:1px solid var(--border);border-radius:3px;background:var(--bg-2);color:var(--fg-3);cursor:pointer;"
                  @click=${() => _copyText(_ngrok.url + "/api/channel/wecom/webhook")}>复制</button>
              </div>
              <div style="display:flex;align-items:center;gap:6px;">
                <span>微信:</span>
                <span style="color:var(--accent);flex:1;">${_ngrok.url}/api/channel/wechat/webhook</span>
                <button style="font-size:10px;padding:2px 6px;border:1px solid var(--border);border-radius:3px;background:var(--bg-2);color:var(--fg-3);cursor:pointer;"
                  @click=${() => _copyText(_ngrok.url + "/api/channel/wechat/webhook")}>复制</button>
              </div>
            </div>
          </div>
          <button class="btn" style="font-size:11px;padding:4px 12px;color:var(--danger,#ef4444);border-color:var(--danger,#ef4444);"
            @click=${() => _ngrokAction("stop", app)}
            ?disabled=${_ngrokLoading === "stop"}>
            ${_ngrokLoading === "stop" ? "停止中..." : "⏹ 停止隧道"}
          </button>
        </div>
      `}

      ${_ngrokMsg ? html`
        <div style="margin-top:8px;padding:6px 10px;border-radius:4px;font-size:12px;
          background:${_ngrokMsg.status === 'ok' ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)'};
          color:${_ngrokMsg.status === 'ok' ? 'var(--green,#22c55e)' : 'var(--danger,#ef4444)'};">
          ${_ngrokMsg.status === 'ok' ? '✅' : '❌'} ${_ngrokMsg.message}
        </div>
      ` : nothing}
    </div>
  `;
}

export function renderChannels(app) {
  if (_channels === null) {
    _loadChannels().then(() => app.requestUpdate());
    return html`<div class="card"><div class="card-title">加载中...</div></div>`;
  }

  const configured = _channels.filter(c => c.configured).length;

  return html`
    <div class="card">
      <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>消息通道</span>
        <button class="btn" @click=${() => { _channels = null; app.requestUpdate(); }}
          style="font-size:12px;">刷新</button>
      </div>
      <div style="display:flex;gap:12px;margin:12px 0;">
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--accent);">${configured}</div>
          <div style="font-size:12px;color:var(--fg-3);">已配置</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--bg-2);border-radius:8px;min-width:80px;">
          <div style="font-size:24px;font-weight:700;color:var(--fg-3);">${_channels.length}</div>
          <div style="font-size:12px;color:var(--fg-3);">总计</div>
        </div>
      </div>

      ${_channels.map(ch => {
        const meta = _channelMeta[ch.name] || {};
        return html`
          <div style="padding:16px;background:var(--bg-2);border-radius:8px;margin-bottom:12px;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:24px;">${meta.icon || "📡"}</span>
                <div>
                  <div style="font-size:15px;font-weight:600;color:var(--fg);">${ch.label}</div>
                  <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
                    <span style="width:8px;height:8px;border-radius:50%;background:${ch.configured ? 'var(--green,#22c55e)' : 'var(--fg-3,#888)'}"></span>
                    <span style="font-size:12px;color:${ch.configured ? 'var(--green,#22c55e)' : 'var(--fg-3)'};">${ch.configured ? "已配置" : "未配置"}</span>
                    ${ch.running ? html`<span style="font-size:11px;color:var(--accent);margin-left:4px;">运行中</span>` : nothing}
                  </div>
                </div>
              </div>
              <div style="display:flex;gap:6px;">
                <button class="btn" style="font-size:11px;padding:4px 10px;background:var(--accent);color:#fff;border:none;border-radius:4px;"
                  @click=${() => { _configOpen[ch.name] = !_configOpen[ch.name]; app.requestUpdate(); }}>
                  ${_configOpen[ch.name] ? "收起" : "⚙️ 配置"}
                </button>
                <button class="btn" style="font-size:11px;padding:4px 10px;"
                  @click=${() => _testChannel(ch.name, app)}
                  ?disabled=${_testResult[ch.name]?.loading}>
                  ${_testResult[ch.name]?.loading ? "测试中..." : "🔍 测试"}
                </button>
                <button class="btn" style="font-size:11px;padding:4px 10px;"
                  @click=${() => _restartChannel(ch.name, app)}
                  ?disabled=${_restarting[ch.name]}>
                  ${_restarting[ch.name] ? "重启中..." : "🔄 重启"}
                </button>
              </div>
            </div>
            ${_testResult[ch.name] && !_testResult[ch.name].loading ? html`
              <div style="margin-top:8px;padding:6px 10px;border-radius:4px;font-size:12px;
                background:${_testResult[ch.name].status === 'ok' ? 'rgba(34,197,94,.12)' : 'rgba(239,68,68,.12)'};
                color:${_testResult[ch.name].status === 'ok' ? 'var(--green,#22c55e)' : 'var(--danger,#ef4444)'};">
                ${_testResult[ch.name].status === 'ok' ? '✅' : '❌'} ${_testResult[ch.name].message || ''}
              </div>
            ` : nothing}
            ${_configOpen[ch.name] ? _renderConfigForm(ch.name, app) : nothing}
          </div>
        `;
      })}
    </div>

    ${_renderNgrokPanel(app)}
  `;
}
