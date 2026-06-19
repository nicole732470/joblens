const API = import.meta.env.VITE_API_URL || "http://3.128.164.130:8000";

function base() {
  return API.replace(/\/$/, "");
}

function headers(token) {
  const h = { "Content-Type": "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

export async function register(email, password) {
  const res = await fetch(`${base()}/auth/register`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export async function login(email, password) {
  const res = await fetch(`${base()}/auth/login`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export async function getProfile(token) {
  const res = await fetch(`${base()}/me/profile`, { headers: headers(token) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function saveProfile(token, profile) {
  const res = await fetch(`${base()}/me/profile`, {
    method: "PUT",
    headers: headers(token),
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function parseJobUrl(url) {
  const res = await fetch(`${base()}/jobs/parse-url`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ url }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export async function uploadResumePdf(token, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${base()}/resume/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export async function analyzeJob(body, token) {
  const res = await fetch(`${base()}/analyze`, {
    method: "POST",
    headers: headers(token),
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(text || `HTTP ${res.status}`);
  return JSON.parse(text);
}

export { API };
