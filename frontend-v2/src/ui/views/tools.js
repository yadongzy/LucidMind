/**
 * Tools & Executors — 工具安全配置、审批历史、执行器状态
 */
import { html, nothing } from "lit";
import * as api from "../api.js";

let _toolConfig = null, _executors = null, _loading = false;

async function _load(app) {
  if (_loading) return;
  _loading = true;
  try {
    const [tc, ex] = await Promise.all([
      api.fetchToolSafetyConfig().catch(() => null),
      api.fetchExecutors().catch(() => ({ executors: [] })),
    ]);
    _toolConfig = tc;
    _executors = ex;
  } catch (e) { /* ignore */ }
  _loading = false;
  app.requestUpdate();
}

const LEVEL_STYLE = {
  dangerous: { bg: "#ef444422", color: "#ef4444", icon: "🔴" },
  sensitive: { bg: "#f59e0b22", color: "#f59e0b", icon: "🟡" },
  safe: { bg: "#22c55e22", color: "#22c55e", icon: "🟢" },
};

export function renderTools(app) {
  if (!_toolConfig && !_loading) _load(app);

  return html`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">

      <!-- Tool Safety Config -->
      <div class="card">
        <div class="card-title">🛡️ 工具安全配置</div>
        ${_toolConfig ? html`
          <div style="font-size:13px;color:var(--fg-2);line-height:1.8;">
            <div><strong>启用:</strong> ${_toolConfig.enabled ? "✅ 是" : "❌ 否"}</div>
            <div><strong>超时策略:</strong> ${_toolConfig.fail_closed ? "🔒 拒绝" : "🔓 放行"}</div>
          </div>

          <div style="margin-top:12px;">
            <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:6px;">
              🔴 危险工具 (${_toolConfig.dangerous_tools?.length || 0})
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">
              ${(_toolConfig.dangerous_tools || []).map(t => html`
                <code style="background:#ef444422;color:#ef4444;padding:2px 6px;border-radius:4px;font-size:11px;">${t}</code>
              `)}
            </div>
          </div>

          <div style="margin-top:12px;">
            <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:6px;">
              🟡 敏感工具 (${_toolConfig.sensitive_tools?.length || 0})
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">
              ${(_toolConfig.sensitive_tools || []).map(t => html`
                <code style="background:#f59e0b22;color:#f59e0b;padding:2px 6px;border-radius:4px;font-size:11px;">${t}</code>
              `)}
            </div>
          </div>

          <div style="margin-top:12px;">
            <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:6px;">
              🟢 白名单 (${_toolConfig.custom_safe?.length || 0})
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">
              ${(_toolConfig.custom_safe || []).map(t => html`
                <code style="background:#22c55e22;color:#22c55e;padding:2px 6px;border-radius:4px;font-size:11px;">${t}</code>
              `)}
            </div>
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">${_loading ? "加载中..." : "无法获取安全配置"}</div>`}
      </div>

      <!-- Executors -->
      <div class="card">
        <div class="card-title">⚡ 执行器</div>
        ${_executors?.executors?.length ? html`
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${_executors.executors.map(ex => html`
              <div style="padding:12px;background:var(--bg-2);border-radius:8px;display:flex;align-items:center;gap:12px;">
                <div style="width:40px;height:40px;border-radius:8px;background:var(--bg);display:flex;align-items:center;justify-content:center;font-size:20px;">
                  ${ex.name === "codex" ? "🤖" : ex.name === "local" ? "💻" : "⚡"}
                </div>
                <div>
                  <div style="font-size:14px;font-weight:600;color:var(--fg);">${ex.name}</div>
                  <div style="font-size:11px;color:var(--fg-3);">
                    ${ex.name === "codex" ? "Codex CLI — 代码修复/审查/解释" :
                      ex.name === "local" ? "本地工具 — Shell 命令/脚本" :
                      "外部执行器"}
                  </div>
                </div>
                <div style="margin-left:auto;">
                  <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#22c55e;"></span>
                </div>
              </div>
            `)}
          </div>
        ` : html`
          <div style="color:var(--fg-3);font-size:13px;">
            ${_loading ? "加载中..." : "未注册执行器。可用: Codex CLI, Local Tool"}
          </div>
        `}

        <div style="margin-top:16px;padding:12px;background:var(--bg-2);border-radius:8px;">
          <div style="font-size:12px;font-weight:600;color:var(--fg);margin-bottom:6px;">执行器路由策略</div>
          <div style="font-size:11px;color:var(--fg-3);line-height:1.6;">
            <div>• coding task (fix/patch/review) → <strong>Codex CLI</strong></div>
            <div>• local automation (script/shell) → <strong>Local Tool</strong></div>
            <div>• browser task → <strong>Browser Tool</strong> (planned)</div>
            <div>• fallback → <strong>Brain 内部执行</strong></div>
          </div>
        </div>
      </div>
    </div>
  `;
}
