/**
 * Shared analyze API client — web + extension use the same async job flow.
 * Sync: ./scripts/sync-shared-ui.sh
 */

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 120;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Same request body shape as vision-job-glow runAnalyzeCore. */
function buildAnalyzeBody(inputs) {
  let company = inputs.company || null;
  let title = inputs.title || null;
  let job_location = inputs.job_location || null;
  const normalize =
    (typeof JobLensReportView !== "undefined" && JobLensReportView.parseLinkedInStyleTitle) ||
    globalThis.JobLensReportView?.parseLinkedInStyleTitle;
  if (typeof normalize === "function") {
    const parsed = normalize(title, company, job_location);
    company = parsed.company || company;
    title = parsed.title || title;
    job_location = parsed.jobLocation || job_location;
  }
  return {
    jd_text: inputs.jd_text || "",
    company,
    title,
    job_url: inputs.job_url || null,
    job_location,
  };
}

/**
 * POST /analyze/async then poll GET /analyze/jobs/{id} until done.
 * @param {string} baseUrl - API root (no trailing slash)
 * @param {object} body - analyze payload
 * @param {{ fetchJson?: Function, onProgress?: Function }} [options]
 */
async function runAnalyzeAsync(baseUrl, body, options = {}) {
  const fetchJson =
    options.fetchJson ||
    (async (path, init) => {
      const res = await fetch(`${baseUrl}${path}`, init);
      const text = await res.text();
      if (!res.ok) {
        throw new Error(
          text.trim().length > 200 ? `Backend responded ${res.status}` : text.trim() || `HTTP ${res.status}`
        );
      }
      try {
        return JSON.parse(text);
      } catch (_) {
        return text;
      }
    });

  const started = await fetchJson("/analyze/async", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const jobId = started?.job_id;
  if (!jobId) throw new Error("Failed to start analysis");

  for (let i = 0; i < MAX_POLLS; i++) {
    await sleep(POLL_INTERVAL_MS);
    const job = await fetchJson(`/analyze/jobs/${jobId}`, { method: "GET" });
    if (typeof options.onProgress === "function") options.onProgress(job);
    if (job?.status === "done" && job.report) return job.report;
    if (job?.status === "error") throw new Error(job.error || "Analysis failed");
  }

  throw new Error("Analysis is taking longer than expected — check back or retry.");
}

const JobLensAnalyzeClient = {
  buildAnalyzeBody,
  runAnalyzeAsync,
  POLL_INTERVAL_MS,
  MAX_POLLS,
  sleep,
};

if (typeof globalThis !== "undefined") {
  globalThis.JobLensAnalyzeClient = JobLensAnalyzeClient;
}

