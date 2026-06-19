/** MV3 background — health check + resource URL helper for content scripts. */

chrome.runtime.onInstalled.addListener(() => {
  console.info("[LCA Sponsor Checker] extension installed/updated");
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
  return false;
});
