/**
 * WebSocket gateway client — 对标 OpenClaw gateway.ts
 * 处理连接、心跳、重连、消息分发
 */

export class GatewayClient {
  constructor() {
    this.ws = null;
    this.heartbeatTimer = null;
    this.heartbeatTimeout = null;
    this.reconnectTimer = null;
    this.connected = false;
    this.messageQueue = [];
    this.isProcessing = false;
    this._listeners = {};
  }

  on(event, fn) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(fn);
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach(fn => fn(data));
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    this.ws = new WebSocket(`${protocol}//${location.host}/ws`);

    this.ws.onopen = () => {
      this.connected = true;
      this.isProcessing = false;
      this._emit("connected");
      this._startHeartbeat();
      this._processQueue();
    };

    this.ws.onclose = () => {
      this.connected = false;
      this._stopHeartbeat();
      this._emit("disconnected");
      this.isProcessing = false;
      this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.ws.onmessage = (evt) => {
      const data = JSON.parse(evt.data);
      if (data.type === "pong") {
        clearTimeout(this.heartbeatTimeout);
        this.lastPongTs = Date.now();
        this.lastPongLatency = data.client_ts ? Math.round(Date.now() - data.client_ts) : null;
        this._emit("pong", { ts: this.lastPongTs, latency: this.lastPongLatency, brain: data.brain, queue: data.queue });
        return;
      }
      if (data.type === "server_ping") {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: "server_pong", ts: data.ts }));
        }
        return;
      }
      if (data.type === "complete") {
        this.isProcessing = false;
        this._processQueue();
      }
      this._emit("message", data);
    };
  }

  disconnect() {
    clearTimeout(this.reconnectTimer);
    this._stopHeartbeat();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  send(msg) {
    this.messageQueue.push(msg);
    this._processQueue();
  }

  sendChat(text, sessionId, attachments) {
    const msg = { type: "chat", message: text, session_id: sessionId };
    if (attachments && attachments.length > 0) msg.attachments = attachments;
    this.send(msg);
  }

  switchSession(sessionId) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "switch_session", session_id: sessionId }));
    }
  }

  abort() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "abort" }));
    }
    this.isProcessing = false;
  }

  _processQueue() {
    if (this.isProcessing || this.messageQueue.length === 0) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.isProcessing = true;
    const msg = this.messageQueue.shift();
    this.ws.send(JSON.stringify(msg));
    if (msg.type === "chat" && (msg.message || (msg.attachments && msg.attachments.length))) {
      this._emit("queue_sent", { text: msg.message, attachments: msg.attachments });
    }
    this._emit("queue_changed");
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping", client_ts: Date.now() }));
        this.heartbeatTimeout = setTimeout(() => {
          this.ws?.close();
        }, 60000);
      }
    }, 30000);
  }

  _stopHeartbeat() {
    clearInterval(this.heartbeatTimer);
    clearTimeout(this.heartbeatTimeout);
  }

  get queueLength() {
    return this.messageQueue.length;
  }

  /** 返回队列中所有待发送的 chat 消息（含原始对象引用）。 */
  getQueue() {
    return this.messageQueue.map((msg, i) => ({
      index: i,
      text: msg.message || "",
      type: msg.type,
      session_id: msg.session_id,
    }));
  }

  /** 编辑队列中指定位置的消息文本。 */
  editQueueItem(index, newText) {
    if (index >= 0 && index < this.messageQueue.length) {
      this.messageQueue[index].message = newText;
      this._emit("queue_changed");
    }
  }

  /** 删除队列中指定位置的消息。 */
  removeQueueItem(index) {
    if (index >= 0 && index < this.messageQueue.length) {
      this.messageQueue.splice(index, 1);
      this._emit("queue_changed");
    }
  }

  /** 强制立即发送队列中下一条消息（跳过 isProcessing 检查）。 */
  forceSendNext() {
    if (this.messageQueue.length === 0) return;
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const msg = this.messageQueue.shift();
    this.isProcessing = true;
    this.ws.send(JSON.stringify(msg));
    if (msg.type === "chat" && msg.message) {
      this._emit("queue_sent", { text: msg.message });
    }
    this._emit("queue_changed");
  }
}
