/**
 * Project Overview — 项目状态、分析结果、能力矩阵
 */
import { html, nothing } from "lit";
import { renderMarkdown } from "../markdown.js";
import * as api from "../api.js";

let _analysis = null, _specs = null, _specContent = null, _selectedSpec = null;
let _loading = false, _analyzing = false;

async function _loadData(app) {
  if (_loading) return;
  _loading = true;
  try {
    const [specs] = await Promise.all([
      api.fetchAnalysisSpecs().catch(() => ({ specs: [], validated: false })),
    ]);
    _specs = specs;
  } catch (e) { /* ignore */ }
  _loading = false;
  app.requestUpdate();
}

async function _runAnalysis(app) {
  _analyzing = true;
  app.requestUpdate();
  try {
    _analysis = await api.runProjectAnalysis("lucidmind", false);
    await _loadData(app);
  } catch (e) {
    _analysis = { error: e.message };
  }
  _analyzing = false;
  app.requestUpdate();
}

async function _viewSpec(app, name) {
  _selectedSpec = name;
  _specContent = null;
  app.requestUpdate();
  try {
    const data = await api.fetchAnalysisSpec(name);
    _specContent = data.content || "";
  } catch (e) {
    _specContent = `Error: ${e.message}`;
  }
  app.requestUpdate();
}

const STATUS_COLORS = {
  "🟢": "#22c55e", "🟡": "#f59e0b", "🔴": "#ef4444", "⚪": "#6b7280",
};

export function renderProject(app) {
  if (!_specs && !_loading) _loadData(app);

  return html`
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">

      <!-- Analysis Controls -->
      <div class="card" style="grid-column:1/-1;">
        <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;">
          <span>🔍 项目分析</span>
          <button class="btn btn--primary" style="font-size:12px;padding:6px 16px;"
            ?disabled=${_analyzing}
            @click=${() => _runAnalysis(app)}>
            ${_analyzing ? "分析中..." : "运行分析"}
          </button>
        </div>
        ${_analysis && !_analysis.error ? html`
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px;margin-top:12px;">
            ${[
              ["文件", _analysis.stats?.files],
              ["代码行", _analysis.stats?.lines],
              ["类", _analysis.stats?.classes],
              ["函数", _analysis.stats?.functions],
              ["API路由", _analysis.stats?.routes],
              ["问题", _analysis.stats?.questions],
            ].map(([label, val]) => html`
              <div style="text-align:center;padding:12px;background:var(--bg-2);border-radius:8px;">
                <div style="font-size:20px;font-weight:700;color:var(--fg);">${val?.toLocaleString() || 0}</div>
                <div style="font-size:11px;color:var(--fg-3);margin-top:4px;">${label}</div>
              </div>
            `)}
          </div>
          <div style="font-size:11px;color:var(--fg-3);margin-top:8px;">
            阶段: ${_analysis.stages_completed?.join(" → ")} · Commit: ${_analysis.commit}
          </div>
        ` : nothing}
        ${_analysis?.error ? html`<div style="color:#ef4444;font-size:13px;margin-top:8px;">${_analysis.error}</div>` : nothing}
      </div>

      <!-- Specs List -->
      <div class="card">
        <div class="card-title">📄 规格文件</div>
        ${_specs?.specs?.length ? html`
          <div style="display:flex;flex-direction:column;gap:4px;">
            ${_specs.specs.map(s => html`
              <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-radius:6px;cursor:pointer;
                background:${_selectedSpec === s.file ? 'var(--bg-2)' : 'transparent'};"
                @click=${() => _viewSpec(app, s.file)}>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span style="font-size:14px;">${s.status}</span>
                  <span style="font-size:12px;color:var(--fg);">${s.file}</span>
                </div>
                ${s.size ? html`<span style="font-size:10px;color:var(--fg-3);">${(s.size/1024).toFixed(1)}KB</span>` : nothing}
              </div>
            `)}
          </div>
        ` : html`<div style="color:var(--fg-3);font-size:13px;">暂无规格文件。点击"运行分析"生成。</div>`}
      </div>

      <!-- Spec Viewer -->
      <div class="card">
        <div class="card-title">${_selectedSpec ? `📖 ${_selectedSpec}` : "选择规格文件查看"}</div>
        ${_specContent ? html`
          <div style="max-height:500px;overflow-y:auto;font-size:13px;line-height:1.7;">
            ${renderMarkdown(_specContent)}
          </div>
        ` : _selectedSpec ? html`<div style="color:var(--fg-3);font-size:13px;">加载中...</div>` : nothing}
      </div>
    </div>
  `;
}
