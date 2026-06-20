/** Sync web login → extension (single auth surface: always use the web app). */
(function () {
  function pushAuthToExtension() {
    const token = localStorage.getItem("joblens_token");
    const email = localStorage.getItem("joblens_email");
    try {
      if (token) {
        chrome.runtime.sendMessage({ type: "JOBLENS_SET_TOKEN", token, email: email || "" });
      } else {
        chrome.runtime.sendMessage({ type: "JOBLENS_CLEAR_TOKEN" });
      }
    } catch (_) {
      /* not in extension context */
    }
  }

  pushAuthToExtension();
  window.addEventListener("joblens-auth-changed", pushAuthToExtension);
  window.addEventListener("storage", (e) => {
    if (e.key === "joblens_token" || e.key === "joblens_email") pushAuthToExtension();
  });
})();
