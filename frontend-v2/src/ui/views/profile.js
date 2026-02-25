/**
 * Profile view — 身份文件管理（用户画像 + 大脑个性 + 安全铁律）
 */
import { html, nothing } from "lit";

let _profileContent = "";
let _soulContent = "";
let _coreContent = "";
let _editing = false;
let _saving = false;
let _loaded = false;
let _activeTab = "user"; // user | soul | core

async function _loadAll() {
  try {
    const [userRes, soulRes, coreRes] = await Promise.all([
      fetch("/api/user-profile"),
      fetch("/api/identity/SOUL.md"),
      fetch("/api/identity/CORE.md"),
    ]);
    const userData = await userRes.json();
    const soulData = await soulRes.json();
    const coreData = await coreRes.json();
    _profileContent = userData.content || "";
    _soulContent = soulData.content || "";
    _coreContent = coreData.content || "";
    _loaded = true;
  } catch (e) {
    _profileContent = "加载失败: " + e.message;
    _loaded = true;
  }
}

async function _saveProfile(app) {
  _saving = true;
  app.requestUpdate();
  try {
    const textarea = document.getElementById("profile-editor");
    const content = textarea.value;
    const res = await fetch("/api/user-profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    const data = await res.json();
    if (data.status === "saved") {
      _profileContent = content;
      _editing = false;
    }
  } catch (e) {
    console.error("保存失败:", e);
  }
  _saving = false;
  app.requestUpdate();
}

function _renderMarkdown(text) {
  const lines = text.split("\n");
  return lines.map(line => {
    if (line.startsWith("# ")) return html`<h2 style="margin:16px 0 8px;font-size:18px;color:var(--accent);">${line.slice(2)}</h2>`;
    if (line.startsWith("## ")) return html`<h3 style="margin:12px 0 6px;font-size:15px;color:var(--fg-2);">${line.slice(3)}</h3>`;
    if (line.startsWith("> ")) return html`<div style="padding:4px 12px;margin:4px 0;border-left:3px solid var(--accent);color:var(--fg-3);font-size:13px;font-style:italic;">${line.slice(2)}</div>`;
    if (line.startsWith("- **")) return html`<div style="padding:4px 0 4px 16px;font-size:13px;">• <b>${line.slice(4).replace("**", "")}</b></div>`;
    if (line.startsWith("- ")) return html`<div style="padding:4px 0 4px 16px;font-size:13px;">• ${line.slice(2)}</div>`;
    if (line.startsWith("_") && line.endsWith("_")) return html`<div style="padding:2px 0;font-size:12px;color:var(--fg-3);font-style:italic;">${line.slice(1, -1)}</div>`;
    if (line.trim() === "---") return html`<hr style="border:none;border-top:1px solid var(--border);margin:12px 0;">`;
    if (line.trim() === "") return html`<div style="height:6px;"></div>`;
    return html`<div style="padding:2px 0;font-size:13px;">${line}</div>`;
  });
}

export function renderProfile(app) {
  if (!_loaded) {
    _loadAll().then(() => app.requestUpdate());
    return html`<div class="card"><div class="card-title">加载中...</div></div>`;
  }

  if (_editing) {
    return html`
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>编辑用户画像</span>
          <div style="display:flex;gap:8px;">
            <button class="btn btn--primary" ?disabled=${_saving}
              @click=${() => _saveProfile(app)}>
              ${_saving ? "保存中..." : "保存"}
            </button>
            <button class="btn" @click=${() => { _editing = false; app.requestUpdate(); }}>取消</button>
          </div>
        </div>
        <textarea id="profile-editor"
          style="width:100%;min-height:400px;background:var(--bg-2);color:var(--fg);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:monospace;font-size:13px;line-height:1.6;resize:vertical;"
          .value=${_profileContent}></textarea>
        <div style="margin-top:8px;font-size:12px;color:var(--fg-3);">
          提示：修改后大脑会自动读取新内容，无需重启。用户多次纠正同一问题时，大脑会自动将其追加到此文件。
        </div>
      </div>
    `;
  }

  const tabs = [
    { id: "user", label: "👤 用户画像", badge: "可编辑" },
    { id: "soul", label: "💫 大脑个性", badge: "可演化" },
    { id: "core", label: "🔒 安全铁律", badge: "不可变" },
  ];

  const tabBar = html`
    <div style="display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:8px;">
      ${tabs.map(t => html`
        <button class="btn ${_activeTab === t.id ? 'btn--primary' : ''}"
          style="font-size:13px;padding:6px 14px;position:relative;"
          @click=${() => { _activeTab = t.id; app.requestUpdate(); }}>
          ${t.label}
          <span style="font-size:10px;margin-left:4px;opacity:0.7;">${t.badge}</span>
        </button>
      `)}
    </div>
  `;

  let content;
  if (_activeTab === "user") {
    content = html`
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>用户画像</span>
          <button class="btn btn--primary" @click=${() => { _editing = true; app.requestUpdate(); }}>编辑</button>
        </div>
        <div style="padding:8px 0;">${_renderMarkdown(_profileContent)}</div>
      </div>
    `;
  } else if (_activeTab === "soul") {
    content = html`
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>大脑个性 <span style="font-size:11px;color:var(--fg-3);font-weight:normal;">SOUL.md — 大脑可通过对话自己演化</span></span>
        </div>
        <div style="padding:8px 0;">${_renderMarkdown(_soulContent)}</div>
      </div>
    `;
  } else {
    content = html`
      <div class="card">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>安全铁律 <span style="font-size:11px;color:var(--fg-3);font-weight:normal;">CORE.md — 不可修改</span></span>
          <span style="font-size:11px;padding:2px 8px;background:var(--danger);color:#fff;border-radius:4px;">🔒 只读</span>
        </div>
        <div style="padding:8px 0;">${_renderMarkdown(_coreContent)}</div>
      </div>
    `;
  }

  return html`
    ${tabBar}
    ${content}
    <div class="card" style="margin-top:16px;">
      <div class="card-title">身份文件架构</div>
      <div style="font-size:13px;color:var(--fg-3);line-height:1.6;">
        <p><b>CORE.md</b> — 不可变安全铁律（诚实、安全、思考格式）</p>
        <p><b>SOUL.md</b> — 可演化个性（性格、行为风格，大脑可通过 identity_update 工具自己修改）</p>
        <p><b>USER.md</b> — 用户画像（本页编辑，大脑通过对话学习填充）</p>
        <p><b>BOOTSTRAP.md</b> — 首次引导（完成后自动标记）</p>
        <p style="margin-top:8px;">用户多次纠正同一问题时，大脑会自动将规则追加到用户画像。修改保存后立即生效。</p>
      </div>
    </div>
  `;
}
