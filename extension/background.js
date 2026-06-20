/** MV3 background — proxy all analyze API calls (same paths as web /api proxy). */

const BACKEND_URL = "https://3-128-164-130.sslip.io";
const API_TIMEOUT_MS = 180_000;

function storageLocal() {
  return chrome.storage?.local ?? null;
}

chrome.runtime.onInstalled.addListener(() => {
  console.info("[JobLens] extension installed/updated");
});

async function authHeaders() {
  const store = storageLocal();
  const headers = { "Content-Type": "application/json" };
  if (!store) return headers;
  const stored = await store.get(["joblens_token"]);
  const token = stored.joblens_token;
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function proxyApi(path, init = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const headers = await authHeaders();
    const resp = await fetch(`${BACKEND_URL}${path}`, {
      method: init.method || "GET",
      headers: { ...headers, ...(init.headers || {}) },
      body: init.body,
      signal: controller.signal,
    });
    const text = await resp.text();
    if (!resp.ok) {
      return { ok: false, status: resp.status, error: text };
    }
    try {
      return { ok: true, data: JSON.parse(text) };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  } catch (err) {
    return { ok: false, error: String(err) };
  } finally {
    clearTimeout(timer);
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "LCA_PING") {
    sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
    return false;
  }
  if (msg?.type === "LCA_GET_RESOURCE_URL" && msg.path) {
    try {
      sendResponse({ ok: true, url: chrome.runtime.getURL(msg.path) });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
    return false;
  }
  if (msg?.type === "JOBLENS_SET_TOKEN" && msg.token) {
    const store = storageLocal();
    if (!store) {
      sendResponse({ ok: false, error: "storage permission missing" });
      return false;
    }
    store.set(
      { joblens_token: msg.token, joblens_email: msg.email || "" },
      () => {
        sendResponse({ ok: true });
      }
    );
    return true;
  }
  if (msg?.type === "JOBLENS_CLEAR_TOKEN") {
    const store = storageLocal();
    if (!store) {
      sendResponse({ ok: false, error: "storage permission missing" });
      return false;
    }
    store.remove(["joblens_token", "joblens_email"], () => sendResponse({ ok: true }));
    return true;
  }
  if (msg?.type === "JOBLENS_API" && msg.path) {
    proxyApi(msg.path, { method: msg.method, body: msg.body, headers: msg.headers }).then(sendResponse);
    return true;
  }
  return false;
});
