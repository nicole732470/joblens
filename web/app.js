const $ = (id) => document.getElementById(id);

function apiBase() {
  return ($("apiUrl").value || "").replace(/\/$/, "");
}

$("analyze").addEventListener("click", async () => {
  const btn = $("analyze");
  const status = $("status");
  const result = $("result");
  const jd = $("jd").value.trim();
  if (jd.length < 40) {
    status.textContent = "Paste a longer job description first.";
    return;
  }
  btn.disabled = true;
  status.textContent = "Analyzing…";
  result.textContent = "";
  const t0 = performance.now();
  try {
    const body = {
      jd_text: jd,
      company: $("company").value.trim() || null,
      title: $("title").value.trim() || null,
    };
    const resume = $("resume").value.trim();
    if (resume) body.resume_text = resume;

    const resp = await fetch(`${apiBase()}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await resp.text();
    if (!resp.ok) throw new Error(`${resp.status}: ${text}`);
    const data = JSON.parse(text);
    const sec = ((performance.now() - t0) / 1000).toFixed(1);
    const verdict = data.recommendation?.verdict || data.recommendation?.label || "—";
    status.textContent = `Done in ${sec}s · Verdict: ${verdict}`;
    result.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    status.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});
