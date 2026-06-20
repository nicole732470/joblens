/** Sync web login token → extension (visit JobLens web while signed in). */
(function () {
  const token = localStorage.getItem("joblens_token");
  if (!token) return;
  try {
    chrome.runtime.sendMessage({ type: "JOBLENS_SET_TOKEN", token });
  } catch (_) {
    /* not in extension context */
  }
})();
