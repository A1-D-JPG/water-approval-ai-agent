const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";
const SESSION_KEY = "waterApprovalUser";

export function getSession() {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    clearSession();
    return null;
  }
}

export function saveSession(user) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

function authHeaders(extra = {}) {
  const user = getSession();
  return user ? { ...extra, "X-User-Id": String(user.id), "X-Role": user.role } : extra;
}

async function handle(response) {
  if (!response.ok) {
    const text = await response.text();
    try {
      const body = JSON.parse(text);
      throw new Error(body.message || body.error || body.detail || `请求失败：${response.status}`);
    } catch (e) {
      if (e instanceof SyntaxError) throw new Error(text || `请求失败：${response.status}`);
      throw e;
    }
  }
  return response.status === 204 ? null : response.json();
}

export async function registerUser(payload) {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return handle(response);
}

export async function loginUser(payload) {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return handle(response);
}

export async function fetchApplications(filters = {}) {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.keyword) params.set("keyword", filters.keyword);
  const query = params.toString() ? `?${params}` : "";
  const response = await fetch(`${API_BASE_URL}/api/list${query}`, {
    method: "GET",
    mode: "cors",
    headers: authHeaders()
  });
  return handle(response);
}

export async function submitApplication(payload) {
  const formData = new FormData();
  ["applicantName", "idNumber", "projectName", "waterLocation", "waterUse", "industryCategory", "contactPhone", "submitMode"].forEach((key) => {
    formData.append(key, payload[key] || "");
  });
  payload.files.forEach((file) => formData.append("files", file));
  const response = await fetch(`${API_BASE_URL}/api/submit`, {
    method: "POST",
    mode: "cors",
    headers: authHeaders(),
    body: formData
  });
  return handle(response);
}

export async function reviewApplication(id) {
  const response = await fetch(`${API_BASE_URL}/api/review/${id}`, {
    method: "POST",
    mode: "cors",
    headers: authHeaders()
  });
  return handle(response);
}

export async function queryKnowledge(payload) {
  const response = await fetch(`${API_BASE_URL}/api/rag/query`, {
    method: "POST",
    mode: "cors",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload)
  });
  return handle(response);
}

export async function withdrawApplication(id) {
  const response = await fetch(`${API_BASE_URL}/api/withdraw/${id}`, {
    method: "POST",
    mode: "cors",
    headers: authHeaders()
  });
  return handle(response);
}

export async function fetchStats() {
  const response = await fetch(`${API_BASE_URL}/api/stats`, { headers: authHeaders() });
  return handle(response);
}

export async function fetchHealth() {
  const response = await fetch(`${API_BASE_URL}/api/system/health`, { headers: authHeaders() });
  return handle(response);
}

export async function fetchUsers() {
  const response = await fetch(`${API_BASE_URL}/api/auth/admin/users`, { headers: authHeaders() });
  return handle(response);
}

export async function createUserByAdmin(payload) {
  const response = await fetch(`${API_BASE_URL}/api/auth/admin/users`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload)
  });
  return handle(response);
}

export async function activateUser(id) {
  const response = await fetch(`${API_BASE_URL}/api/auth/admin/users/${id}/activate`, {
    method: "POST",
    headers: authHeaders()
  });
  return handle(response);
}

export async function updateUserRole(id, role) {
  const response = await fetch(`${API_BASE_URL}/api/auth/admin/users/${id}/role`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ role })
  });
  return handle(response);
}

export function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

export function statusText(status) {
  return {
    DRAFT: "草稿",
    PENDING: "待审核",
    APPROVED: "通过",
    REJECTED: "不通过",
    NEED_MANUAL_REVIEW: "人工复核",
    WITHDRAWN: "已撤回"
  }[status] || status || "-";
}

export function roleText(role) {
  return { APPLICANT: "申请人", REVIEWER: "审核员", ADMIN: "管理员" }[role] || role || "-";
}

export function parseReviewResult(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}
