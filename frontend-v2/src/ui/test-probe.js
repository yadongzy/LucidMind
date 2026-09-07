/**
 * LucidMind 前端测试探针
 * 暴露 window.__LUCID_TEST__ 供大脑通过 API 调用验证页面状态
 * 不影响正常功能，仅在开发模式下激活
 */

export function installTestProbe(app) {
  if (window.__LUCID_TEST__) return;

  window.__LUCID_TEST__ = {
    /**
     * 获取完整页面状态快照
     */
    getSnapshot() {
      return {
        timestamp: Date.now(),
        tab: app.tab,
        connected: app.connected,
        heartbeat: { ...app.heartbeat },
        model: { ...app.modelInfo },
        theme: app.theme,
        messages: app.messages.length,
        sessions: app.sessions.length,
        currentSession: app.currentSession,
        isStreaming: app.isStreaming,
        pendingConfirm: app.pendingConfirm,
        showThinking: app.showThinking,
        eventLogCount: app.eventLog.length,
        brainAwake: app.brainStatus?.awake ?? null,
        daemonRunning: app.brainStatus?.daemon?.running ?? null,
      };
    },

    /**
     * 检查所有关键 DOM 元素是否存在
     */
    checkElements() {
      const checks = {
        // Topbar
        topbar: !!document.querySelector(".topbar"),
        statusPill: !!document.querySelector(".pill .statusDot"),
        modelSelect: !!document.querySelector(".model-select"),
        heartbeatPulse: !!document.querySelector(".heartbeat-pulse"),
        themeToggle: !!document.querySelector(".theme-toggle"),
        // Navigation
        nav: !!document.querySelector(".nav"),
        navItems: document.querySelectorAll(".nav-item").length,
        // Chat (only if on chat tab)
        chatControls: !!document.querySelector(".chat-controls"),
        sessionSelect: !!document.querySelector(".chat-controls__session select"),
        refreshBtn: !!document.querySelector(".chat-controls .btn--icon"),
        thinkingToggle: !!document.querySelector(".chat-controls .btn--icon:last-child"),
        chatThread: !!document.querySelector(".chat-thread"),
        chatCompose: !!document.querySelector(".chat-compose"),
        textarea: !!document.querySelector(".chat-compose__textarea"),
        uploadBtn: !!document.querySelector(".chat-compose .btn--icon"),
        sendBtn: !!document.querySelector(".chat-compose__actions .btn--primary"),
        actionBtn: !!document.querySelector(".chat-compose__actions .btn:first-child"),
        // Confirm bar (conditional)
        confirmBar: !!document.querySelector(".confirm-bar"),
        // Queue indicator (conditional)
        queueIndicator: !!document.querySelector(".chat-queue-indicator"),
      };
      checks._allCorePresent =
        checks.topbar && checks.statusPill && checks.modelSelect &&
        checks.themeToggle && checks.nav;
      if (app.tab === "chat") {
        checks._chatReady =
          checks.chatControls && checks.sessionSelect &&
          checks.chatThread && checks.chatCompose &&
          checks.textarea && checks.sendBtn;
      }
      return checks;
    },

    /**
     * 检查按钮的 disabled 状态
     */
    checkButtonStates() {
      const results = {};
      const sendBtn = document.querySelector(".chat-compose__actions .btn--primary");
      const actionBtn = document.querySelector(".chat-compose__actions .btn:first-child");
      const sessionSelect = document.querySelector(".chat-controls__session select");
      const refreshBtn = document.querySelector(".chat-controls .btn--icon");

      if (sendBtn) {
        results.sendBtn = {
          exists: true,
          disabled: sendBtn.disabled,
          text: sendBtn.textContent.trim(),
        };
      }
      if (actionBtn) {
        results.actionBtn = {
          exists: true,
          disabled: actionBtn.disabled,
          text: actionBtn.textContent.trim(),
        };
      }
      if (sessionSelect) {
        results.sessionSelect = {
          exists: true,
          disabled: sessionSelect.disabled,
          value: sessionSelect.value,
          optionCount: sessionSelect.options.length,
        };
      }
      if (refreshBtn) {
        results.refreshBtn = {
          exists: true,
          disabled: refreshBtn.disabled,
        };
      }
      return results;
    },

    /**
     * 检查 WebSocket 连接和心跳
     */
    checkConnection() {
      return {
        wsConnected: app.connected,
        gatewayState: app.gateway?.ws?.readyState ?? -1,
        heartbeat: {
          alive: app.heartbeat.alive,
          latency: app.heartbeat.latency,
          lastTs: app.heartbeat.lastTs,
          secondsAgo: app.heartbeat.lastTs
            ? Math.round((Date.now() - app.heartbeat.lastTs) / 1000)
            : null,
        },
        isProcessing: app.gateway?.isProcessing ?? false,
        queueLength: app.gateway?.queueLength ?? 0,
      };
    },

    /**
     * 检查模型状态
     */
    checkModel() {
      return {
        model: app.modelInfo.model,
        provider: app.modelInfo.provider,
        available: app.status?.llm?.available ?? null,
        selectValue: document.querySelector(".model-select")?.value ?? null,
        statusDotOk: !!document.querySelector(".pill--model .statusDot.ok"),
      };
    },

    /**
     * 检查消息渲染
     */
    checkMessages() {
      const groups = document.querySelectorAll(".chat-group");
      const bubbles = document.querySelectorAll(".chat-bubble");
      const toolCards = document.querySelectorAll(".chat-tool-card");
      const readingIndicator = document.querySelector(".chat-reading-indicator");
      const streamingBubble = document.querySelector(".chat-bubble.streaming");
      const emptyState = document.querySelector(".chat-empty");

      return {
        totalMessages: app.messages.length,
        renderedGroups: groups.length,
        renderedBubbles: bubbles.length,
        renderedToolCards: toolCards.length,
        hasReadingIndicator: !!readingIndicator,
        hasStreamingBubble: !!streamingBubble,
        hasEmptyState: !!emptyState,
        isStreaming: app.isStreaming,
        streamingTextLength: app.streamingText?.length ?? 0,
      };
    },

    /**
     * 检查概览页数据（需切换到 overview tab）
     */
    checkOverview() {
      if (app.tab !== "overview") {
        return { error: "当前不在概览页，请先切换到 overview tab" };
      }
      const cards = document.querySelectorAll(".card");
      const statValues = document.querySelectorAll(".stat-value-lg");
      return {
        cardCount: cards.length,
        statValueCount: statValues.length,
        status: app.status,
        brainStatus: app.brainStatus,
      };
    },

    /**
     * 运行全部检查，返回综合报告
     */
    runAll() {
      const report = {
        timestamp: new Date().toISOString(),
        snapshot: this.getSnapshot(),
        elements: this.checkElements(),
        buttons: this.checkButtonStates(),
        connection: this.checkConnection(),
        model: this.checkModel(),
        messages: this.checkMessages(),
      };

      // 计算通过/失败
      const issues = [];
      if (!report.snapshot.connected) issues.push("WebSocket 未连接");
      if (!report.connection.heartbeat.alive) issues.push("心跳未响应");
      if (!report.elements._allCorePresent) issues.push("核心 DOM 元素缺失");
      if (report.snapshot.tab === "chat" && !report.elements._chatReady) {
        issues.push("对话页 DOM 元素不完整");
      }
      if (report.model.available === false) issues.push("模型不可用");

      report.summary = {
        totalChecks: 5,
        passed: 5 - issues.length,
        failed: issues.length,
        issues,
        verdict: issues.length === 0 ? "ALL_PASS" : "HAS_ISSUES",
      };

      return report;
    },
  };

  console.log("[TestProbe] __LUCID_TEST__ 已安装");
}
