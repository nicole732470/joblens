/** MV3 background — proxy analyze API (avoids mixed-content blocks on LinkedIn HTTPS). */

const BACKEND_URL = "https://3-128-164-130.sslip.io";
const ANALYZE_TIMEOUT_MS = 120_000;

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
    store.set({ joblens_token: msg.token }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (msg?.type === "JOBLENS_CLEAR_TOKEN") {
    const store = storageLocal();
    if (!store) {
      sendResponse({ ok: false, error: "storage permission missing" });
      return false;
    }
    store.remove("joblens_token", () => sendResponse({ ok: true }));
    return true;
  }
  if (msg?.type === "JOBLENS_ANALYZE" && msg.body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    authHeaders()
      .then((headers) =>
        fetch(`${BACKEND_URL}/analyze`, {
          method: "POST",
          headers,
          body: JSON.stringify(msg.body),
          signal: controller.signal,
        })
      )
      .then(async (resp) => {
        const text = await resp.text();
        if (!resp.ok) {
          sendResponse({ ok: false, status: resp.status, error: text });
          return;
        }
        try {
          sendResponse({ ok: true, data: JSON.parse(text) });
        } catch (e) {
          sendResponse({ ok: false, error: String(e) });
        }
      })
      .catch((err) => sendResponse({ ok: false, error: String(err) }))
      .finally(() => clearTimeout(timer));
    return true;
  }
  return false;
});
