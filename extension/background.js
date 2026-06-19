/** MV3 background — proxy analyze API (avoids mixed-content blocks on LinkedIn HTTPS). */

const BACKEND_URL = "http://3.128.164.130:8000";

chrome.runtime.onInstalled.addListener(() => {
  console.info("[JobLens] extension installed/updated");
});

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
  if (msg?.type === "JOBLENS_ANALYZE" && msg.body) {
    fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(msg.body),
    })
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
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // async sendResponse
  }
  return false;
});
