/**
 * Channels view — 多通道管理界面
 */
import { html, nothing } from "lit";

let _channels = null;
let _testResult = {};
let _restarting = {};

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

const _channelDocs = {
  telegram: {
    icon: "🤖",
    env: ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS (可选)"],
    steps: "1. 在 Telegram 找 @BotFather 创建 Bot\n2. 获取 Bot Token\n3. 设置环境变量后重启服务器",
  },
  feishu: {
    icon: "📱",
    env: ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN (可选)"],
    steps: "1. 在飞书开放平台创建企业自建应用\n2. 开启机器人能力\n3. 设置事件回调地址: /api/channel/feishu/webhook",
  },
  wecom: {
    icon: "💼",
    env: ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET", "WECOM_TOKEN"],
    steps: "1. 在企业微信管理后台创建自建应用\n2. 设置接收消息的回调地址: /api/channel/wecom/webhook\n3. 配置 Token 和 EncodingAESKey",
  },
  wechat: {
    icon: "💬",
    env: ["GEWECHAT_BASE_URL", "GEWECHAT_TOKEN (appId)", "GEWECHAT_CALLBACK_URL"],
    steps: "1. Docker 部署 GeweChat 服务\n2. 扫码登录获取 appId\n3. 设置回调地址: /api/channel/wechat/webhook\n⚠ 仅用于个人研究，请勿商用",
  },
};

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
        const doc = _channelDocs[ch.name] || {};
        return html`
          <div style="padding:16px;background:var(--bg-2);border-radius:8px;margin-bottom:12px;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
              <div style="display:flex;align-items:center;gap:10px;">
                <span style="font-size:24px;">${doc.icon || "📡"}</span>
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
                background:${_testResult[ch.name].status === 'ok' ? 'var(--green,#22c55e)22' : 'var(--danger,#ef4444)22'};
                color:${_testResult[ch.name].status === 'ok' ? 'var(--green,#22c55e)' : 'var(--danger,#ef4444)'};">
                ${_testResult[ch.name].status === 'ok' ? '✅' : '❌'} ${_testResult[ch.name].message || ''}
              </div>
            ` : nothing}
            <div style="margin-top:12px;font-size:12px;color:var(--fg-3);">
              <div style="font-weight:600;margin-bottom:4px;">环境变量：</div>
              ${(doc.env || []).map(e => html`<div style="font-family:monospace;padding:2px 0;">${e}</div>`)}
            </div>
            <div style="margin-top:8px;font-size:12px;color:var(--fg-3);white-space:pre-line;">${doc.steps || ""}</div>
          </div>
        `;
      })}
    </div>

    <div class="card" style="margin-top:16px;">
      <div class="card-title">Webhook 端点</div>
      <div style="font-size:13px;color:var(--fg-3);line-height:1.8;">
        <p>各通道的回调地址（需要公网可达）：</p>
        <div style="background:var(--bg-2);padding:12px;border-radius:6px;font-size:12px;font-family:monospace;margin-top:8px;">
          <div>飞书: POST /api/channel/feishu/webhook</div>
          <div>企微: GET/POST /api/channel/wecom/webhook</div>
          <div>微信: POST /api/channel/wechat/webhook</div>
        </div>
        <p style="margin-top:8px;">Telegram 使用 polling 模式，无需公网地址。</p>
      </div>
    </div>
  `;
}
