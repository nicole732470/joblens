(function () {
  const BADGE_ID = "lca-sponsor-checker-badge";
  // Backend for the AI Job Intelligence analysis. Override for deployed envs.
  const BACKEND_URL = "http://localhost:8000";
  let lastPageKey = null;

  const CONFIDENCE_META = {
    high: { title: "H-1B sponsor", sub: "Strong match", status: "found", icon: "✓" },
    medium: { title: "Possible H-1B sponsor", sub: "Verify — uncertain match", status: "caution", icon: "?" },
    low: { title: "Possible H-1B sponsor", sub: "Verify — uncertain match", status: "caution", icon: "?" },
  };

  function sourceLabel(ctx) {
    if (ctx.source === "job page") return "Detected on this job posting";
    if (ctx.source === "company page") return "Detected on this company page";
    return "";
  }

  function renderAlternatives(alternatives) {
    if (!alternatives?.length) return "";
    const items = alternatives
      .map(({ employer }) => {
        const loc = [employer.city, employer.state].filter(Boolean).join(", ");
        const meta = [loc, `${Number(employer.lca_count).toLocaleString()} filings`]
          .filter(Boolean)
          .join(" · ");
        return `<li><b>${escapeHtml(employer.name)}</b>${meta ? `<br><span class="lca-alt-meta">${escapeHtml(meta)}</span>` : ""}</li>`;
      })
      .join("");
    return `
      <div class="lca-alternatives">
        <div class="lca-label">Other possible matches</div>
        <ul>${items}</ul>
      </div>`;
  }

  function extractJobId() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get("currentJobId");
    if (fromQuery) return fromQuery;
    const m = window.location.pathname.match(/\/jobs\/view\/(\d+)/i);
    return m ? m[1] : null;
  }

  function slugFromCompanyHref(href) {
    const m = href.match(/\/company\/([^/?#]+)/i);
    return m ? decodeURIComponent(m[1]).toLowerCase() : null;
  }

  function cleanDisplayName(raw) {
    if (!raw) return null;
    let text = raw.replace(/\s+/g, " ").trim();
    if (!text) return null;

    const stopPatterns = [
      /\bFollow\b/i,
      /\bfollowers\b/i,
      /\bpeople from your school\b/i,
      /\bwere hired here\b/i,
      /\bSee all\b/i,
      /\bFor decades,/i,
      /\bWith Ansys now part of/i,
      /\bSoftware Development(?=[A-Z])/i,
      /[a-z]([A-Z][a-z]+,\s*[A-Z]{2})\b/,
    ];
    for (const re of stopPatterns) {
      const m = text.match(re);
      if (m && m.index > 0) {
        text = text.slice(0, m.index).trim();
      }
    }

    text = text.replace(/\s+(Software Development|Information Technology|IT Services).*$/i, "");

    const words = text.split(" ").filter(Boolean);
    if (words.length >= 2 && words[0].toLowerCase() === words[1].toLowerCase()) {
      text = words[0];
    }

    if (text.length > 60) {
      text = text.slice(0, 60).replace(/\s+\S*$/, "").trim();
    }

    return text.length > 1 ? text : null;
  }

  function titleFromSlug(slug) {
    if (!slug) return null;
    return slug
      .split("-")
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  function resolveDisplayName(raw, slug) {
    return cleanDisplayName(raw) || titleFromSlug(slug);
  }

  function extractCompanySlugFromLinks() {
    const links = document.querySelectorAll('a[href*="/company/"]');
    for (const link of links) {
      const slug = slugFromCompanyHref(link.href);
      if (!slug || slug === "linkedin" || slug === "learning") continue;
      const name = resolveDisplayName(link.textContent?.trim(), slug);
      if (name) return { slug, name };
    }
    for (const link of links) {
      const slug = slugFromCompanyHref(link.href);
      if (!slug || slug === "linkedin" || slug === "learning") continue;
      return { slug, name: titleFromSlug(slug) };
    }
    return { slug: null, name: null };
  }

  function extractCompanyNameFromDom(isCompanyPage) {
    const companySelectors = [
      "h1.org-top-card-summary__title",
      "h1[data-anonymize='company-name']",
      ".org-top-card-summary-info-list__title h1",
      ".org-top-card-primary-content h1",
    ];
    const jobSelectors = [
      ".job-details-jobs-unified-top-card__company-name",
      ".jobs-unified-top-card__company-name",
      ".jobs-details-top-card__company-url",
      ".job-details-jobs-unified-top-card__primary-description-container a",
      "a[data-tracking-control-name='public_jobs_topcard-org-name']",
    ];
    const selectors = isCompanyPage
      ? companySelectors
      : [...jobSelectors, ".artdeco-entity-lockup__subtitle"];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      const text = el?.textContent?.trim();
      const cleaned = cleanDisplayName(text);
      if (cleaned) return cleaned;
    }
    return null;
  }

  function extractPageContext() {
    const companyPath = window.location.pathname.match(/^\/company\/([^/?#]+)/i);
    if (companyPath) {
      const slug = decodeURIComponent(companyPath[1]).toLowerCase();
      return {
        slug,
        displayName: resolveDisplayName(extractCompanyNameFromDom(true), slug),
        pageKey: `company:${slug}`,
        source: "company page",
      };
    }

    if (window.location.pathname.includes("/jobs")) {
      const jobId = extractJobId();
      const fromLinks = extractCompanySlugFromLinks();
      const displayName =
        fromLinks.name || resolveDisplayName(extractCompanyNameFromDom(false), fromLinks.slug);
      const slug = fromLinks.slug;
      return {
        slug,
        displayName,
        pageKey: slug ? `job:${jobId || "unknown"}:${slug}` : null,
        source: "job page",
      };
    }

    return { slug: null, displayName: null, pageKey: null, source: null };
  }

  function formatWage(w) {
    if (!w) return "";
    const n = Number(String(w).replace(/,/g, ""));
    if (Number.isNaN(n) || n <= 0) return "";
    return `$${Math.round(n).toLocaleString()}`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureBadge() {
    let el = document.getElementById(BADGE_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = BADGE_ID;
      document.body.appendChild(el);
    }
    return el;
  }

  function renderWarnings(warnings) {
    if (!warnings?.length) return "";
    return `<ul class="lca-warnings">${warnings
      .map((w) => `<li>${escapeHtml(w)}</li>`)
      .join("")}</ul>`;
  }

  function renderNotes(notes) {
    if (!notes?.length) return "";
    return `<ul class="lca-notes">${notes
      .map((n) => `<li>${escapeHtml(n)}</li>`)
      .join("")}</ul>`;
  }

  function renderBadge(result, ctx) {
    const { employer, confidence, warnings, notes, alternatives } = result;
    const meta = CONFIDENCE_META[confidence] || CONFIDENCE_META.medium;
    const el = ensureBadge();

    const filings = Number(employer.lca_count) || 0;
    const approvedPct =
      filings > 0 ? Math.round((employer.certified_count / filings) * 100) : 0;

    const jobsHtml = (employer.top_jobs || [])
      .slice(0, 3)
      .map((j) => {
        const wage = formatWage(j.wage_from);
        const level = j.level && !String(j.level).includes("/") ? ` · ${j.level}` : "";
        return `<li>${escapeHtml(j.title)}${level}${wage ? ` · ${wage}` : ""}</li>`;
      })
      .join("");

    const location = [employer.city, employer.state].filter(Boolean).join(", ");

    const linkedInLine =
      ctx.displayName && ctx.displayName.toLowerCase() !== (employer.name || "").toLowerCase()
        ? `<div class="lca-compare">LinkedIn shows <b>${escapeHtml(ctx.displayName)}</b></div>`
        : "";

    const showAlternatives =
      confidence !== "high" && alternatives?.length ? renderAlternatives(alternatives) : "";

    el.className = `lca-badge lca-${meta.status}`;
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <span class="lca-icon lca-icon-${meta.status}">${meta.icon}</span>
        <div>
          <div class="lca-title">${meta.title}</div>
          <div class="lca-sub">${meta.sub}</div>
        </div>
      </div>
      <div class="lca-company">${escapeHtml(employer.name)}</div>
      ${linkedInLine}
      ${
        filings > 0
          ? `<div class="lca-rate"><b>${approvedPct}% approved</b><span class="lca-rate-sub"> · ${filings.toLocaleString()} visa filings</span></div>`
          : ""
      }
      ${location ? `<div class="lca-meta">${escapeHtml(location)}</div>` : ""}
      ${jobsHtml ? `<div class="lca-jobs-label">Top sponsored roles</div><ul class="lca-jobs">${jobsHtml}</ul>` : ""}
      ${renderNotes(notes)}
      ${renderWarnings(warnings)}
      ${showAlternatives}
      <button class="lca-analyze-btn">Analyze this job ▾</button>
      <div class="lca-analyze-result" hidden></div>
      <div class="lca-foot">${sourceLabel(ctx)} · Source: U.S. DOL H-1B data</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
    wireAnalyzeButton(el, ctx);
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <span class="lca-icon lca-icon-miss">–</span>
        <div>
          <div class="lca-title">No sponsorship record found</div>
          <div class="lca-sub">Not in U.S. H-1B visa data</div>
        </div>
      </div>
      ${
        ctx.displayName
          ? `<div class="lca-compare">LinkedIn shows <b>${escapeHtml(ctx.displayName)}</b></div>`
          : `<div class="lca-meta">Couldn't detect the company on this page yet.</div>`
      }
      <ul class="lca-warnings">
        <li>They may not sponsor, file under a different legal name, or use a parent company.</li>
      </ul>
      <button class="lca-analyze-btn">Analyze this job ▾</button>
      <div class="lca-analyze-result" hidden></div>
      <div class="lca-foot">Not finding a record isn't proof they don't sponsor.</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
    wireAnalyzeButton(el, ctx);
  }

  function renderLoading() {
    const el = ensureBadge();
    el.className = "lca-badge lca-loading";
    el.innerHTML = `
      <div class="lca-header">
        <span class="lca-spinner"></span>
        <div class="lca-title">Checking sponsorship records…</div>
      </div>
    `;
  }

  function renderWaiting(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-waiting";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <div class="lca-title">Waiting for job details…</div>
      </div>
      <div class="lca-foot">Open a job posting to detect the employer.</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
  }

  // ---- AI Job Intelligence (backend) ----

  function extractJobTitle() {
    const selectors = [
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".job-details-jobs-unified-top-card__job-title h1",
      "h1.jobs-unified-top-card__job-title",
      ".top-card-layout__title",
    ];
    for (const sel of selectors) {
      const text = document.querySelector(sel)?.textContent?.trim();
      if (text) return text.replace(/\s+/g, " ");
    }
    return null;
  }

  function extractJobDescription() {
    const selectors = [
      "#job-details",
      ".jobs-description__content",
      ".jobs-description-content__text",
      ".jobs-box__html-content",
      ".jobs-description",
      ".show-more-less-html__markup",
    ];
    for (const sel of selectors) {
      const text = document.querySelector(sel)?.innerText?.trim();
      if (text && text.length > 40) return text.replace(/\s+\n/g, "\n");
    }
    return "";
  }

  function gatherJobInputs(ctx) {
    return {
      company: ctx.displayName || null,
      title: extractJobTitle(),
      jd_text: extractJobDescription(),
      job_url: window.location.href,
    };
  }

  async function analyzeWithBackend(inputs) {
    const resp = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jd_text: inputs.jd_text || "",
        company: inputs.company,
        title: inputs.title,
        job_url: inputs.job_url,
      }),
    });
    if (!resp.ok) {
      let detail = "";
      try {
        detail = JSON.stringify(await resp.json());
      } catch (_) {
        /* ignore */
      }
      throw new Error(`Backend responded ${resp.status}${detail ? ` — ${detail}` : ""}`);
    }
    return resp.json();
  }

  function likelihoodClass(likelihood) {
    const v = String(likelihood || "").toLowerCase();
    if (v === "high") return "lca-odds-high";
    if (v === "medium") return "lca-odds-medium";
    if (v === "low") return "lca-odds-low";
    return "lca-odds-unknown";
  }

  const REQ_CATEGORY_LABELS = {
    required_skill: "Required",
    preferred_skill: "Preferred",
    experience: "Experience",
    education: "Education",
    responsibility: "Responsibility",
    location: "Location",
    visa: "Visa",
    risk_keyword: "Risk",
    other: "Other",
  };

  function renderJdSection(jd) {
    if (!jd || !jd.available) {
      const reason = jd?.reason || "";
      return reason
        ? `<div class="lca-coming"><div class="lca-label">Job parsing</div><div class="lca-hint">${escapeHtml(reason)}</div></div>`
        : "";
    }
    const meta = [jd.seniority, jd.location].filter(Boolean).join(" · ");
    const reqs = (jd.requirements || [])
      .slice(0, 12)
      .map((r) => {
        const tag = REQ_CATEGORY_LABELS[r.category] || "Other";
        return `<li><span class="lca-req-tag">${escapeHtml(tag)}</span> ${escapeHtml(r.text)}</li>`;
      })
      .join("");
    const visa = (jd.visa_language || [])
      .map((v) => `<li>${escapeHtml(v)}</li>`)
      .join("");
    return `
      <div class="lca-coming">
        <div class="lca-label">Job requirements</div>
        ${meta ? `<div class="lca-hint">${escapeHtml(meta)}</div>` : ""}
        ${reqs ? `<ul class="lca-reqs">${reqs}</ul>` : `<div class="lca-hint">No explicit requirements extracted.</div>`}
        ${visa ? `<div class="lca-label" style="margin-top:6px">Visa language</div><ul class="lca-notes">${visa}</ul>` : ""}
      </div>`;
  }

  function renderAnalysisInline(report) {
    const sp = report.sponsorship || {};
    const likelihood = sp.sponsorship_likelihood || "Unknown";
    const pending = report.pending || [];
    const labels = {
      jd_parsing: "Job description parsing",
      resume_fit: "Resume fit vs. your profile",
      risk: "Risk signals",
      recommendation: "Apply / skip recommendation",
    };
    const pendingHtml = pending.length
      ? `<div class="lca-coming">
           <div class="lca-label">Coming soon</div>
           <ul class="lca-notes">${pending.map((p) => `<li>${escapeHtml(labels[p] || p)}</li>`).join("")}</ul>
         </div>`
      : "";
    return `
      <div class="lca-analyze-inner">
        <div class="lca-ai-head">Job Intelligence <span class="lca-beta">beta</span></div>
        <div class="lca-kv">
          <span class="lca-label">Sponsorship odds</span>
          <b class="${likelihoodClass(likelihood)}">${escapeHtml(String(likelihood))}</b>
        </div>
        ${
          likelihood === "Unknown"
            ? `<div class="lca-hint">A transparent likelihood score is still being built.</div>`
            : ""
        }
        ${renderJdSection(report.jd)}
        ${pendingHtml}
      </div>`;
  }

  function renderAnalysisErrorInline(err) {
    const isNetwork = err instanceof TypeError || /Failed to fetch/i.test(err.message);
    return `<div class="lca-analyze-inner lca-analyze-err">${
      isNetwork
        ? `Can't reach the analysis server. Start it with <code>docker compose up -d</code>, then retry.`
        : escapeHtml(err.message)
    }</div>`;
  }

  function wireAnalyzeButton(el, ctx) {
    const btn = el.querySelector(".lca-analyze-btn");
    const out = el.querySelector(".lca-analyze-result");
    if (!btn || !out) return;
    btn.addEventListener("click", () => onAnalyzeClick(btn, out, ctx));
  }

  async function onAnalyzeClick(btn, out, ctx) {
    // Already loaded once → just toggle visibility.
    if (out.dataset.loaded === "1") {
      if (out.hasAttribute("hidden")) {
        out.removeAttribute("hidden");
        btn.textContent = "Hide analysis ▴";
      } else {
        out.setAttribute("hidden", "");
        btn.textContent = "Analyze this job ▾";
      }
      return;
    }

    out.removeAttribute("hidden");
    out.innerHTML = `<div class="lca-loading-row"><span class="lca-spinner"></span> Analyzing…</div>`;
    btn.disabled = true;
    try {
      const report = await analyzeWithBackend(gatherJobInputs(ctx));
      out.innerHTML = renderAnalysisInline(report);
      out.dataset.loaded = "1";
      btn.textContent = "Hide analysis ▴";
    } catch (err) {
      console.error("[Job Intelligence]", err);
      out.innerHTML = renderAnalysisErrorInline(err);
    } finally {
      btn.disabled = false;
    }
  }

  async function run() {
    const ctx = extractPageContext();
    const onJobs = window.location.pathname.includes("/jobs");
    const onCompany = window.location.pathname.includes("/company/");

    if (!onJobs && !onCompany) {
      document.getElementById(BADGE_ID)?.remove();
      lastPageKey = null;
      return;
    }

    if (!ctx.pageKey) {
      if (onJobs) renderWaiting(ctx);
      return;
    }

    if (ctx.pageKey === lastPageKey) return;
    lastPageKey = ctx.pageKey;

    renderLoading();

    try {
      await LcaMatcher.load();
      const result = await LcaMatcher.lookup(ctx.slug, ctx.displayName);
      if (result) renderBadge(result, ctx);
      else renderMiss(ctx);
    } catch (err) {
      console.error("[LCA Sponsor Checker]", err);
      const el = ensureBadge();
      el.className = "lca-badge lca-miss";
      el.innerHTML = `
        <div class="lca-header">
          <span class="lca-icon lca-icon-miss">!</span>
          <div class="lca-title">Lookup failed</div>
        </div>
        <div class="lca-foot">${escapeHtml(err.message)}</div>
      `;
    }
  }

  function onNavigate() {
    lastPageKey = null;
    scheduleRun();
  }

  run();

  let debounceTimer = null;
  function scheduleRun() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(run, 350);
  }

  const wrapHistory = (fn) =>
    function (...args) {
      fn.apply(this, args);
      onNavigate();
    };
  history.pushState = wrapHistory(history.pushState);
  history.replaceState = wrapHistory(history.replaceState);

  let lastHref = location.href;
  setInterval(() => {
    if (location.href !== lastHref) {
      lastHref = location.href;
      onNavigate();
    }
  }, 600);

  const obs = new MutationObserver(scheduleRun);
  obs.observe(document.body, { childList: true, subtree: true });

  window.addEventListener("popstate", onNavigate);
})();
