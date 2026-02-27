/**
 * REST API client — 封装所有后端 API 调用
 */

const BASE = "";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || body.message || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function fetchStatus() {
  return request("/api/status");
}

export async function fetchSessions() {
  return request("/api/sessions");
}

export async function createSession() {
  return request("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export async function deleteSession(sid) {
  return request(`/api/sessions/${sid}`, { method: "DELETE" });
}

export async function renameSession(sid, title) {
  return request(`/api/sessions/${sid}/title`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function fetchHistory(sid) {
  return request(`/api/sessions/${sid}/history`);
}

export async function fetchMemory(sid) {
  return request(`/api/memory/${sid}`);
}

export async function fetchLessons() {
  return request("/api/lessons");
}

export async function fetchTasks() {
  return request("/api/dispatcher/tasks");
}

export async function fetchCron() {
  return request("/api/cron");
}

export async function fetchBrainStatus() {
  return request("/api/brain/status");
}

export async function fetchBrainGoals() {
  return request("/api/brain/goals");
}

export async function fetchBrainThoughts() {
  return request("/api/brain/thoughts");
}

export async function fetchSoulHistory() {
  return request("/api/brain/soul/history");
}

export async function confirmPlan() {
  return request("/api/brain/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
}

export async function skipPlan() {
  return request("/api/brain/skip", { method: "POST" });
}

export async function pauseBrain() {
  return request("/api/brain/pause", { method: "POST" });
}

export async function resumeBrain() {
  return request("/api/brain/resume", { method: "POST" });
}

export async function setBrainInterval(interval) {
  return request("/api/brain/interval", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interval }),
  });
}

export async function setAutoAsk(enabled) {
  return request("/api/brain/auto-ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export async function switchProvider(provider) {
  return request("/api/switch-provider", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
}

export async function verifyConnection(provider, apiKey, model) {
  return request("/api/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey, model }),
  });
}

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: form });
  return res.json();
}
