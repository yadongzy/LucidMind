/**
 * Memory Files view — Markdown 记忆文件管理
 * 对接 /api/memory/files/* API 端点
 * GAP-3 前端集成: 让用户查看/编辑/搜索记忆文件
 */
import { html, nothing } from "lit";

let _files = null, _filesLoading = false, _filesTs = 0;
let _activeFile = null, _fileContent = "", _fileEditing = false, _fileDirty = false;
let _searchQuery = "", _searchResults = null;

async function _fetchFiles(app) {
  _filesLoading = true;
  try {
    const r = await fetch("/api/memory/files").then(r => r.json());
    _files = r.files || [];
    _filesTs = Date.now();
  } catch (e) {
    _files = [];
    console.error("加载记忆文件失败:", e);
  }
  _filesLoading = false;
  if (app) app.requestUpdate();
}

async function _loadFile(filename, app) {
  try {
    const r = await fetch(`/api/memory/files/${encodeURIComponent(filename)}`).then(r => r.json());
    _activeFile = filename;
    _fileContent = r.content || "";
    _fileEditing = false;
    _fileDirty = false;
  } catch (e) {
    console.error("读取文件失败:", e);
  }
  if (app) app.requestUpdate();
}

async function _saveFile(app) {
  if (!_activeFile || !_fileDirty) return;
  try {
    await fetch(`/api/memory/files/${encodeURIComponent(_activeFile)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: _fileContent }),
    });
    _fileDirty = false;
    _fileEditing = false;
    _fetchFiles(app);
  } catch (e) {
    console.error("保存失败:", e);
    alert("保存失败: " + e.message);
  }
  if (app) app.requestUpdate();
}

async function _deleteFile(filename, app) {
  if (!confirm(`确定删除 ${filename}？此操作不可撤销。`)) return;
  try {
    await fetch(`/api/memory/files/${encodeURIComponent(filename)}`, { method: "DELETE" });
    if (_activeFile === filename) {
      _activeFile = null;
      _fileContent = "";
    }
    _fetchFiles(app);
  } catch (e) {
    console.error("删除失败:", e);
  }
}

async function _searchFiles(app) {
  if (!_searchQuery.trim()) { _searchResults = null; if (app) app.requestUpdate(); return; }
  try {
    const r = await fetch("/api/memory/files/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: _searchQuery, limit: 10 }),
    }).then(r => r.json());
    _searchResults = r.results || [];
  } catch (e) {
    _searchResults = [];
    console.error("搜索失败:", e);
  }
  if (app) app.requestUpdate();
}

async function _indexFiles(app) {
  try {
    const r = await fetch("/api/memory/files/index", { method: "POST" }).then(r => r.json());
    alert(`索引完成: ${r.indexed} 条已索引, ${r.skipped} 条跳过`);
  } catch (e) {
    console.error("索引失败:", e);
    alert("索引失败: " + e.message);
  }
}

export function renderMemoryFiles(app) {
  if (!_files || Date.now() - _filesTs > 60000) {
    if (!_filesLoading) _fetchFiles(app);
  }

  return html`
    <!-- 搜索栏 -->
    <div style="display:flex;gap:8px;margin-bottom:12px;align-items:center;">
      <input type="text" placeholder="搜索记忆文件..." .value=${_searchQuery}
        @input=${(e) => { _searchQuery = e.target.value; }}
        @keydown=${(e) => { if (e.key === "Enter") _searchFiles(app); }}
        style="flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);color:var(--fg);font-size:13px;">
      <button class="btn" style="font-size:12px;" @click=${() => _searchFiles(app)}>🔍 搜索</button>
      <button class="btn" style="font-size:12px;" @click=${() => _fetchFiles(app)}>刷新</button>
      <button class="btn" style="font-size:12px;" @click=${() => _indexFiles(app)}
        title="将 Markdown 文件索引到 MemoryStore">📥 重建索引</button>
    </div>

    <!-- 搜索结果 -->
    ${_searchResults ? html`
      <div style="margin-bottom:12px;padding:10px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border);">
        <div style="font-weight:600;font-size:13px;margin-bottom:8px;">搜索结果 (${_searchResults.length})</div>
        ${_searchResults.length === 0 ? html`<p style="color:var(--fg-3);font-size:12px;">无匹配结果</p>` : nothing}
        ${_searchResults.map(r => html`
          <div style="padding:6px 0;border-bottom:1px solid var(--border);cursor:pointer;font-size:12px;"
            @click=${() => _loadFile(r.file, app)}>
            <div style="display:flex;justify-content:space-between;">
              <span style="color:var(--accent);font-weight:600;">${r.file}</span>
              <span style="opacity:0.5;">匹配度: ${(r.score * 100).toFixed(0)}%</span>
            </div>
            <div style="opacity:0.7;margin-top:2px;">${r.title}</div>
            <div style="opacity:0.5;margin-top:2px;white-space:pre-wrap;">${(r.snippet || "").slice(0, 150)}</div>
          </div>
        `)}
        <button class="btn" style="font-size:11px;margin-top:6px;" @click=${() => { _searchResults = null; app.requestUpdate(); }}>关闭搜索结果</button>
      </div>
    ` : nothing}

    <div style="display:flex;gap:12px;">
      <!-- 文件列表（左侧） -->
      <div style="min-width:200px;max-width:240px;">
        <div style="font-weight:600;font-size:13px;margin-bottom:8px;">
          记忆文件 (${_files ? _files.length : 0})
        </div>
        ${_filesLoading ? html`<p style="font-size:12px;color:var(--fg-3);">加载中...</p>` : nothing}
        <div style="max-height:400px;overflow-y:auto;">
          ${(_files || []).map(f => html`
            <div style="padding:6px 8px;border-radius:6px;cursor:pointer;font-size:12px;display:flex;justify-content:space-between;align-items:center;
              ${_activeFile === f.name ? 'background:var(--accent);color:#fff;' : 'hover:background:var(--bg-2);'}"
              @click=${() => _loadFile(f.name, app)}>
              <div>
                <div style="font-weight:500;">${f.is_evergreen ? '📌 ' : '📄 '}${f.name}</div>
                <div style="opacity:0.6;font-size:11px;">${(f.size / 1024).toFixed(1)}KB</div>
              </div>
              ${!f.is_evergreen ? html`
                <button class="btn btn--sm" style="font-size:10px;padding:0 4px;${_activeFile === f.name ? 'color:#fff;' : 'color:var(--danger,#ef4444);'}"
                  @click=${(e) => { e.stopPropagation(); _deleteFile(f.name, app); }}
                  title="删除">✕</button>
              ` : nothing}
            </div>
          `)}
        </div>
      </div>

      <!-- 文件内容（右侧） -->
      <div style="flex:1;min-width:0;">
        ${_activeFile ? html`
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <span style="font-weight:600;font-size:13px;">${_activeFile}${_fileDirty ? ' *' : ''}</span>
            <div style="display:flex;gap:6px;">
              ${_fileEditing ? html`
                <button class="btn btn--primary" style="font-size:12px;" @click=${() => _saveFile(app)}>💾 保存</button>
                <button class="btn" style="font-size:12px;" @click=${() => { _fileEditing = false; _loadFile(_activeFile, app); }}>取消</button>
              ` : html`
                <button class="btn" style="font-size:12px;" @click=${() => { _fileEditing = true; app.requestUpdate(); }}>✏️ 编辑</button>
              `}
            </div>
          </div>
          ${_fileEditing ? html`
            <textarea style="width:100%;min-height:350px;padding:10px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);color:var(--fg);font-family:monospace;font-size:13px;resize:vertical;line-height:1.5;"
              .value=${_fileContent}
              @input=${(e) => { _fileContent = e.target.value; _fileDirty = true; }}></textarea>
          ` : html`
            <div style="padding:12px;background:var(--bg-2);border-radius:8px;border:1px solid var(--border);max-height:400px;overflow-y:auto;font-size:13px;line-height:1.6;white-space:pre-wrap;font-family:monospace;">
              ${_fileContent || '(空文件)'}
            </div>
          `}
        ` : html`
          <div style="padding:40px;text-align:center;color:var(--fg-3);font-size:13px;">
            ← 选择一个记忆文件查看内容
          </div>
        `}
      </div>
    </div>
  `;
}
