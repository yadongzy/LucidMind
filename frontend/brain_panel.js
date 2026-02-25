/**
 * S38: 大脑状态面板 — 目标/思考/灵魂进化/行动日志可视化
 * 独立文件，不修改 console.js（行数限制）
 */
(function() {
  'use strict';

  const BASE = window.location.origin;
  let panelVisible = false;
  let refreshTimer = null;

  // 创建大脑面板按钮（Activity Bar）
  function initBrainButton() {
    const bar = document.getElementById('activity-bar');
    if (!bar) return;
    const btn = document.createElement('div');
    btn.className = 'activity-item';
    btn.title = '大脑状态 (Brain)';
    btn.innerHTML = '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>';
    const spacer = bar.querySelector('.activity-spacer');
    if (spacer) bar.insertBefore(btn, spacer);
    else bar.appendChild(btn);
    btn.addEventListener('click', togglePanel);
  }

  // 创建面板 DOM
  function createPanel() {
    const panel = document.createElement('div');
    panel.id = 'brain-panel';
    panel.style.cssText = 'display:none;position:fixed;right:0;top:0;width:360px;height:100vh;background:var(--bg-secondary,#1e1e1e);border-left:1px solid var(--border,#333);z-index:1000;overflow-y:auto;padding:16px;font-size:13px;color:var(--text,#ccc);';
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;color:var(--accent,#007acc);">🧠 大脑状态</h3>
        <span id="brain-panel-close" style="cursor:pointer;font-size:18px;">✕</span>
      </div>
      <div id="brain-awake-status" style="margin-bottom:12px;padding:8px;border-radius:4px;background:var(--bg-tertiary,#252526);"></div>
      <h4 style="color:var(--accent,#007acc);margin:12px 0 6px;">🎯 目标</h4>
      <div id="brain-goals" style="margin-bottom:12px;"></div>
      <h4 style="color:var(--accent,#007acc);margin:12px 0 6px;">💭 后台思考</h4>
      <div id="brain-thoughts" style="margin-bottom:12px;"></div>
      <h4 style="color:var(--accent,#007acc);margin:12px 0 6px;">⚡ 自主行动</h4>
      <div id="brain-actions" style="margin-bottom:12px;"></div>
      <h4 style="color:var(--accent,#007acc);margin:12px 0 6px;">🧬 灵魂进化</h4>
      <div id="brain-soul" style="margin-bottom:12px;"></div>
    `;
    document.body.appendChild(panel);
    document.getElementById('brain-panel-close').addEventListener('click', togglePanel);
    return panel;
  }

  function togglePanel() {
    let panel = document.getElementById('brain-panel');
    if (!panel) panel = createPanel();
    panelVisible = !panelVisible;
    panel.style.display = panelVisible ? 'block' : 'none';
    if (panelVisible) {
      refreshPanel();
      refreshTimer = setInterval(refreshPanel, 15000);
    } else if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  async function refreshPanel() {
    try {
      const [statusRes, goalsRes, thoughtsRes, soulRes] = await Promise.all([
        fetch(`${BASE}/api/brain/status`).then(r => r.json()),
        fetch(`${BASE}/api/brain/goals`).then(r => r.json()),
        fetch(`${BASE}/api/brain/thoughts`).then(r => r.json()),
        fetch(`${BASE}/api/brain/soul/history`).then(r => r.json()),
      ]);

      // 状态
      const awakeEl = document.getElementById('brain-awake-status');
      if (awakeEl) {
        const awake = statusRes.awake;
        const daemon = statusRes.daemon || {};
        awakeEl.innerHTML = `
          <div>状态: ${awake ? '🟢 醒来' : '🔴 休眠'}</div>
          <div>Daemon: ${daemon.running ? '运行中' : '停止'}</div>
          <div>思考次数: ${daemon.thought_count || 0} | 行动次数: ${daemon.action_count || 0}</div>
          <div>目标: ${statusRes.goals?.active || 0} 活跃 / ${statusRes.goals?.total || 0} 总计</div>
          <div>灵魂进化: ${statusRes.soul_evolutions || 0} 次</div>
        `;
      }

      // 目标
      const goalsEl = document.getElementById('brain-goals');
      if (goalsEl) {
        const goals = goalsRes.goals || [];
        goalsEl.innerHTML = goals.slice(0, 6).map(g => {
          const icon = g.type === 'long_term' ? '🎯' : '📌';
          const status = g.status === 'completed' ? '✅' : '🔄';
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border,#333);">${icon} ${status} <span style="color:#ddd;">${g.content}</span></div>`;
        }).join('') || '<div style="color:#666;">暂无目标</div>';
      }

      // 思考
      const thoughtsEl = document.getElementById('brain-thoughts');
      if (thoughtsEl) {
        const thoughts = thoughtsRes.thoughts || [];
        thoughtsEl.innerHTML = thoughts.slice(-5).reverse().map(t => {
          const items = (t.thoughts || []).join('; ');
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border,#333);"><span style="color:#666;font-size:11px;">${t.time || ''}</span><br>${items}</div>`;
        }).join('') || '<div style="color:#666;">暂无思考记录</div>';
      }

      // 行动
      const actionsEl = document.getElementById('brain-actions');
      if (actionsEl) {
        const daemon = statusRes.daemon || {};
        const actions = daemon.recent_actions || [];
        actionsEl.innerHTML = actions.slice(-5).reverse().map(a => {
          const items = (a.actions || []).join('; ');
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border,#333);"><span style="color:#666;font-size:11px;">${a.time || ''}</span><br>${items}</div>`;
        }).join('') || '<div style="color:#666;">暂无自主行动</div>';
      }

      // 灵魂进化
      const soulEl = document.getElementById('brain-soul');
      if (soulEl) {
        const history = soulRes.history || [];
        soulEl.innerHTML = history.slice(-5).reverse().map(h => {
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border,#333);"><span style="color:#666;font-size:11px;">${h.time || ''}</span><br>🧬 ${h.rule || ''}<br><span style="color:#888;font-size:11px;">触发: ${h.trigger || ''}</span></div>`;
        }).join('') || '<div style="color:#666;">灵魂尚未进化</div>';
      }
    } catch (e) {
      console.error('Brain panel refresh error:', e);
    }
  }

  // 暂停/恢复大脑任务
  function initPauseButton() {
    const btn = document.getElementById('pause-brain-btn');
    if (!btn) return;
    let paused = false;
    btn.addEventListener('click', async () => {
      try {
        const action = paused ? 'resume' : 'pause';
        const res = await fetch(`${BASE}/api/brain/${action}`, {method: 'POST'});
        const data = await res.json();
        if (data.status === 'ok') {
          paused = !paused;
          btn.textContent = paused ? '▶' : '⏸';
          btn.title = paused ? '恢复大脑任务' : '暂停大脑任务';
          btn.style.color = paused ? '#f44' : '';
          // 同步设置面板
          const sel = document.getElementById('brain-auto-learning');
          if (sel) sel.value = paused ? 'off' : 'on';
        }
      } catch (e) { console.error('Pause/resume error:', e); }
    });
  }

  // 大脑设置面板
  function initBrainSettings() {
    const panel = document.getElementById('brain-settings');
    const closeBtn = document.getElementById('brain-settings-close');
    if (!panel || !closeBtn) return;

    // 设置按钮（右下角齿轮）
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'brain-settings-toggle';
    toggleBtn.textContent = '⚙ LucidMind Settings';
    const mainArea = document.getElementById('main-area');
    if (mainArea) { mainArea.style.position = 'relative'; mainArea.appendChild(toggleBtn); }

    toggleBtn.addEventListener('click', () => panel.classList.toggle('hidden'));
    closeBtn.addEventListener('click', () => panel.classList.add('hidden'));

    // Auto Learning 开关
    const autoLearn = document.getElementById('brain-auto-learning');
    if (autoLearn) {
      autoLearn.addEventListener('change', async () => {
        const action = autoLearn.value === 'on' ? 'resume' : 'pause';
        try {
          await fetch(`${BASE}/api/brain/${action}`, {method: 'POST'});
          // 同步暂停按钮
          const pauseBtn = document.getElementById('pause-brain-btn');
          if (pauseBtn) {
            pauseBtn.textContent = action === 'pause' ? '▶' : '⏸';
            pauseBtn.style.color = action === 'pause' ? '#f44' : '';
          }
        } catch (e) { console.error('Auto learning toggle error:', e); }
      });
    }

    // Think Interval 设置
    const intervalSel = document.getElementById('brain-think-interval');
    if (intervalSel) {
      intervalSel.addEventListener('change', async () => {
        try {
          await fetch(`${BASE}/api/brain/interval`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({interval: parseInt(intervalSel.value)})
          });
        } catch (e) { console.error('Interval change error:', e); }
      });
    }

    // Auto Ask Teacher 设置
    const autoAsk = document.getElementById('brain-auto-ask');
    if (autoAsk) {
      autoAsk.addEventListener('change', async () => {
        try {
          await fetch(`${BASE}/api/brain/auto-ask`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: autoAsk.value === 'on'})
          });
        } catch (e) { console.error('Auto ask toggle error:', e); }
      });
    }

    // 加载当前状态
    loadBrainSettings();
  }

  async function loadBrainSettings() {
    try {
      const res = await fetch(`${BASE}/api/brain/status`);
      const data = await res.json();
      const d = data.daemon || data;
      const autoLearn = document.getElementById('brain-auto-learning');
      if (autoLearn) autoLearn.value = d.paused ? 'off' : 'on';
      const pauseBtn = document.getElementById('pause-brain-btn');
      if (pauseBtn) {
        pauseBtn.textContent = d.paused ? '▶' : '⏸';
        pauseBtn.style.color = d.paused ? '#f44' : '';
      }
      // 显示/隐藏确认栏
      const bar = document.getElementById('brain-confirm-bar');
      if (bar) {
        if (d.pending_plan && !d.user_confirmed) {
          bar.classList.remove('hidden');
          const txt = document.getElementById('brain-confirm-text');
          if (txt) txt.textContent = `大脑自检完成，等待确认执行`;
        } else {
          bar.classList.add('hidden');
        }
      }
    } catch (e) { /* ignore */ }
  }

  // 确认 & 跳过按钮
  function initConfirmButton() {
    const runBtn = document.getElementById('brain-confirm-btn');
    const skipBtn = document.getElementById('brain-skip-btn');
    const bar = document.getElementById('brain-confirm-bar');
    if (runBtn) {
      runBtn.addEventListener('click', async () => {
        try {
          await fetch(`${BASE}/api/brain/confirm`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
          if (bar) bar.classList.add('hidden');
          runBtn.textContent = '✅ Running';
          setTimeout(() => { runBtn.textContent = '▶ Run'; }, 2000);
        } catch (e) { console.error('Confirm error:', e); }
      });
    }
    if (skipBtn) {
      skipBtn.addEventListener('click', async () => {
        try {
          await fetch(`${BASE}/api/brain/skip`, {method: 'POST'});
          if (bar) bar.classList.add('hidden');
        } catch (e) { console.error('Skip error:', e); }
      });
    }
  }

  // 定期检查是否有待确认计划
  setInterval(loadBrainSettings, 15000);

  // 初始化
  function initAll() { initBrainButton(); initPauseButton(); initBrainSettings(); initConfirmButton(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else { initAll(); }
})();
