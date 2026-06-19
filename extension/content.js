(function () {
  const EXTENSION_VERSION = "2.7.9";
  const BADGE_ID = "lca-sponsor-checker-badge";
  const POSITION_KEY = "lca-badge-position";
  // Backend for the AI Job Intelligence analysis. Override for deployed envs.
  const BACKEND_URL = "http://localhost:8000";
  let extensionBroken = false;

  function extensionRuntime() {
    try {
      return globalThis.chrome?.runtime ?? globalThis.browser?.runtime ?? null;
    } catch (_) {
      return null;
    }
  }

  function showExtensionBrokenBanner() {
    if (document.getElementById(`${BADGE_ID}-broken`)) return;
    extensionBroken = true;
    const el = document.createElement("div");
    el.id = `${BADGE_ID}-broken`;
    el.textContent =
      "Job Check extension disconnected — open chrome://extensions, reload it, then refresh this page (F5).";
    el.style.cssText =
      "position:fixed;bottom:16px;right:16px;z-index:2147483647;max-width:320px;padding:12px 14px;" +
      "background:#fff5f5;border:1px solid #fca5a5;border-radius:8px;font:13px/1.4 system-ui,sans-serif;" +
      "color:#991b1b;box-shadow:0 4px 16px rgba(0,0,0,.12);";
    document.body.appendChild(el);
  }

  const runtime = extensionRuntime();
  if (!runtime?.getURL || !runtime?.id) {
    showExtensionBrokenBanner();
    console.error(
      "[LCA Sponsor Checker] Extension APIs unavailable (chrome.runtime.getURL missing). " +
        "Reload the extension at chrome://extensions, then refresh this LinkedIn tab."
    );
    return;
  }

  const CONFIDENCE_META = {
    high: { title: "H-1B sponsor", status: "found" },
    medium: { title: "Possible sponsor", status: "caution" },
    low: { title: "Possible sponsor", status: "caution" },
  };

  const SOFT_REQUIREMENT_RE =
    /\b(leadership|lead\b|collaborat|cross[- ]?functional|teamwork|communicat|stakeholder|mentor|passion|fast[- ]?paced|self[- ]?starter|culture|interpersonal|organiz|detail[- ]?oriented|problem[- ]?solving|work across| agile|ownership|motivated|dynamic|ambitious|innovative mindset|people skills|verbal and written)\b/i;

  let lastFingerprint = null;

  function renderFoot(ctx, parts) {
    const bits = (parts || []).filter(Boolean);
    bits.push(`v${EXTENSION_VERSION}`);
    return `<div class="lca-foot">${bits.map((p) => escapeHtml(p)).join(" · ")}</div>`;
  }

  function footLinkedInHint(ctx, legalName) {
    if (!ctx.displayName) return null;
    if (legalName && ctx.displayName.toLowerCase() === legalName.toLowerCase()) return null;
    return `LinkedIn: ${ctx.displayName}`;
  }

  function isSoftRequirement(claim) {
    return SOFT_REQUIREMENT_RE.test(stripClaimPrefix(claim?.claim || ""));
  }

  function partitionResumeFit(rf) {
    const buckets = { strong: [], partial: [], gaps: [], soft: 0 };
    for (const c of rf.strong_matches || []) {
      (isSoftRequirement(c) ? buckets.soft++ : buckets.strong.push(c));
    }
    for (const c of rf.partial_matches || []) {
      (isSoftRequirement(c) ? buckets.soft++ : buckets.partial.push(c));
    }
    for (const c of rf.missing || []) {
      (isSoftRequirement(c) ? buckets.soft++ : buckets.gaps.push(c));
    }
    return buckets;
  }

  function simplifyReasoning(text) {
    return String(text || "")
      .replace(/\s*\(vector fit ratio \d+%\)/gi, "")
      .replace(/\s*\(fit ratio \d+%\)/gi, "")
      .replace(/vector fit ratio \d+%/gi, "")
      .replace(/fit ratio \d+%/gi, "")
      .replace(/vector overlap/gi, "resume overlap")
      .replace(/across \d+ JD requirements/gi, "")
      .replace(/\s{2,}/g, " ")
      .trim();
  }

  function hardRequirementFit(rf) {
    if (!rf?.available) return null;
    const strong = [];
    const partial = [];
    const weak = [];
    const gaps = [];
    for (const c of rf.strong_matches || []) {
      if (isSoftRequirement(c)) continue;
      strong.push(c);
    }
    for (const c of rf.partial_matches || []) {
      if (isSoftRequirement(c)) continue;
      partial.push(c);
    }
    for (const c of rf.missing || []) {
      if (isSoftRequirement(c)) continue;
      if (/^\[weak\]/i.test(c.claim || "")) weak.push(c);
      else gaps.push(c);
    }
    return { strong, partial, weak, gaps };
  }

  function truncateText(text, max = 40) {
    const s = String(text || "").trim();
    if (s.length <= max) return s;
    return `${s.slice(0, max - 1)}…`;
  }

  function extractCompanyLogoUrl() {
    const selectors = [
      ".job-details-jobs-unified-top-card__company-logo img",
      ".jobs-unified-top-card__company-logo img",
      ".job-details-jobs-unified-top-card__company-logo a img",
      ".jobs-unified-top-card__content--main-company img",
      "a[data-tracking-control-name='public_jobs_topcard-org-image'] img",
      "a[href*='/company/'] img[src*='licdn.com']",
      "img[class*='CompanyLogo']",
      ".artdeco-entity-lockup__image img",
    ];
    for (const sel of selectors) {
      const img = document.querySelector(sel);
      if (img?.src && !/ghost|placeholder|data:image|profile-display/i.test(img.src)) {
        return img.src;
      }
    }
    return null;
  }

  function renderCompanyLine(name) {
    if (!name) return "";
    const logoUrl = extractCompanyLogoUrl();
    const logo = logoUrl
      ? `<img class="lca-co-logo" src="${escapeHtml(logoUrl)}" alt="" width="20" height="20" />`
      : "";
    return `<div class="lca-company-line">${logo}<span class="lca-company">${escapeHtml(name)}</span></div>`;
  }

  function renderHeadBlock(pillHtml, companyName) {
    return `<div class="lca-head-block">${companyName ? renderCompanyLine(companyName) : ""}${pillHtml}</div>`;
  }

  function statusPill(text, tone) {
    return `<span class="lca-pill lca-pill-${tone}">${escapeHtml(text)}</span>`;
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
    if (m) return m[1];
    for (const sel of [
      ".jobs-search__job-details [data-job-id]",
      ".job-details-jobs-unified-top-card[data-job-id]",
      "[data-current-job-id]",
    ]) {
      const el = document.querySelector(sel);
      const raw = el?.getAttribute("data-job-id") || el?.getAttribute("data-current-job-id");
      if (raw) {
        const digits = raw.replace(/\D/g, "");
        if (digits.length >= 6) return digits;
      }
    }
    return null;
  }

  function contextFingerprint(ctx) {
    const jobId = extractJobId() || "";
    const title = (extractJobTitle() || "").slice(0, 100).toLowerCase();
    return [
      ctx.pageKey || "",
      ctx.slug || "",
      (ctx.displayName || "").toLowerCase(),
      jobId,
      title,
    ].join("|");
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
      const nameKey = (displayName || "unknown").toLowerCase().slice(0, 40);
      return {
        slug,
        displayName,
        pageKey: jobId
          ? `job:${jobId}:${slug || "unknown"}:${nameKey}`
          : slug || displayName
            ? `job:unknown:${slug || "unknown"}:${nameKey}`
            : null,
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
      applySavedPosition(el);
    }
    return el;
  }

  function applySavedPosition(el) {
    try {
      const raw = localStorage.getItem(POSITION_KEY);
      if (!raw) return;
      const { x, y } = JSON.parse(raw);
      if (typeof x === "number" && typeof y === "number") {
        el.style.left = `${x}px`;
        el.style.top = `${y}px`;
        el.style.right = "auto";
      }
    } catch (_) {
      /* ignore */
    }
  }

  function renderChrome(showRefresh = true) {
    const logo = runtime.getURL("icons/rabbit.png");
    const refreshBtn = showRefresh
      ? `<button type="button" class="lca-refresh-btn" title="Reload for this job">Refresh</button>`
      : "";
    return `<div class="lca-chrome"><span class="lca-drag-handle" title="Drag to move">⋮⋮</span><img class="lca-logo" src="${logo}" alt="" width="18" height="18" /><span class="lca-brand">Hop</span>${refreshBtn}<button type="button" class="lca-close" aria-label="Close">×</button></div>`;
  }

  function initDrag(el) {
    if (el.dataset.dragWired === "1") return;
    el.dataset.dragWired = "1";

    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;
    let pointerId = null;

    const onMove = (e) => {
      if (!dragging || e.pointerId !== pointerId) return;
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const x = Math.max(8, Math.min(window.innerWidth - w - 8, e.clientX - offsetX));
      const y = Math.max(8, Math.min(window.innerHeight - h - 8, e.clientY - offsetY));
      el.style.left = `${x}px`;
      el.style.top = `${y}px`;
      el.style.right = "auto";
    };

    const onUp = (e) => {
      if (!dragging || (e.pointerId != null && e.pointerId !== pointerId)) return;
      dragging = false;
      pointerId = null;
      el.classList.remove("lca-dragging");
      el.releasePointerCapture?.(e.pointerId);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      const rect = el.getBoundingClientRect();
      localStorage.setItem(POSITION_KEY, JSON.stringify({ x: rect.left, y: rect.top }));
    };

    el.addEventListener("pointerdown", (e) => {
      if (!e.target.closest(".lca-chrome") || e.target.closest(".lca-close") || e.target.closest(".lca-refresh-btn")) return;
      e.preventDefault();
      dragging = true;
      pointerId = e.pointerId;
      el.classList.add("lca-dragging");
      el.setPointerCapture?.(e.pointerId);
      const rect = el.getBoundingClientRect();
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      el.style.right = "auto";
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
    });
  }

  function finishBadge(el, ctx) {
    initDrag(el);
    const close = el.querySelector(".lca-close");
    if (close) close.addEventListener("click", () => el.remove());
    wireRefreshButton(el);
    if (ctx) runAutoAnalyze(el, ctx);
  }

  function wireRefreshButton(el) {
    const btn = el.querySelector(".lca-refresh-btn");
    if (!btn || btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      lastFingerprint = null;
      const out = el.querySelector(".lca-analyze-result");
      if (out) out.dataset.analyzedFor = "";
      run({ force: true });
    });
  }

  async function runAutoAnalyze(el, ctx) {
    const out = el.querySelector(".lca-analyze-result");
    if (!out || !ctx?.pageKey) return;
    const fp = contextFingerprint(ctx);
    if (out.dataset.analyzedFor === fp) return;
    out.dataset.analyzedFor = fp;
    await runAnalysis(out, ctx);
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

  function renderMetricGrid(cells) {
    if (!cells.length) return "";
    const cols = Math.min(cells.length, 5);
    return `<div class="lca-metrics" style="grid-template-columns:repeat(${cols},1fr)">${cells
      .map(
        (c) =>
          `<div class="lca-metric" title="${escapeHtml(c.hint || c.lbl || "")}"><span class="lca-metric-val">${escapeHtml(c.val)}</span><span class="lca-metric-lbl">${escapeHtml(c.lbl)}</span></div>`
      )
      .join("")}</div>`;
  }

  function renderH1bSummary(employer) {
    const filings = Number(employer.lca_count) || 0;
    if (filings <= 0) return "";

    const approvedPct = Math.round((employer.certified_count / filings) * 100);
    const grid = renderMetricGrid([
      { val: `${approvedPct}%`, lbl: "Approved", hint: "Certified LCA share" },
      { val: filings.toLocaleString(), lbl: "Filings", hint: "Total H-1B filings on record" },
    ]);

    const jobRows = (employer.top_jobs || []).slice(0, 2).map((j) => {
      const wage = formatWage(j.wage_from);
      const title = escapeHtml(j.title);
      const wageHtml = wage ? `<span class="lca-h1b-wage">${escapeHtml(wage)}</span>` : "";
      return `<div class="lca-h1b-role" title="${escapeHtml(j.title)}${wage ? ` · ${wage}` : ""}">${title}${wageHtml}</div>`;
    });

    if (!jobRows.length) return grid;
    return `${grid}<div class="lca-h1b-roles">${jobRows.join("")}</div>`;
  }

  function buildVerdictNote(rec) {
    if (!rec?.available) return "";
    if (rec.summary) return rec.summary;
    const decision = rec.decision || "";
    if (decision === "Skip") return "Not a strong fit";
    if (rec.track_label) return rec.track_label;
    return "";
  }

  function renderBadge(result, ctx) {
    const { employer, confidence } = result;
    const meta = CONFIDENCE_META[confidence] || CONFIDENCE_META.medium;
    const el = ensureBadge();

    el.className = `lca-badge lca-${meta.status}`;
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        ${renderHeadBlock(statusPill(meta.title, meta.status === "found" ? "ok" : "caution"), employer.name)}
        ${renderH1bSummary(employer)}
        <div class="lca-analyze-result"></div>
        ${renderFoot(ctx, [footLinkedInHint(ctx, employer.name), "Source: U.S. DOL H-1B"])}
      </div>`;
    finishBadge(el, ctx);
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        ${renderHeadBlock(statusPill("No H-1B record", "neutral"), ctx.displayName || "")}
        <div class="lca-analyze-result"></div>
        ${renderFoot(ctx, [
          "Disclaimer: employer may file under a different legal name",
        ])}
      </div>`;
    finishBadge(el, ctx);
  }

  function renderLoading() {
    const el = ensureBadge();
    el.className = "lca-badge lca-loading";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-loading-row"><span class="lca-spinner"></span> Checking H-1B records…</div>
      </div>`;
    finishBadge(el, null);
  }

  function renderWaiting(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-waiting";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-title">Waiting for job details…</div>
        <div class="lca-hint">Open a job posting to detect the employer.</div>
      </div>`;
    finishBadge(el, null);
  }

  // ---- AI Job Intelligence (backend) ----

  function extractJobTitle() {
    const selectors = [
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".job-details-jobs-unified-top-card__job-title h1",
      "h1.jobs-unified-top-card__job-title",
      ".top-card-layout__title",
      ".jobs-details-top-card__job-title",
      "h1.t-24",
    ];
    for (const sel of selectors) {
      const text = document.querySelector(sel)?.textContent?.trim();
      if (text) return text.replace(/\s+/g, " ");
    }
    const og = document.querySelector('meta[property="og:title"]')?.content;
    if (og) {
      const bit = og.split("|")[0].trim();
      if (bit.length >= 6) return bit;
    }
    return null;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function linkedInCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta?.content) return meta.content;
    const match = document.cookie.match(/JSESSIONID="([^"]+)"/);
    return match ? match[1] : "";
  }

  function isInsideBadge(el) {
    return Boolean(el?.closest?.(`#${BADGE_ID}`));
  }

  function pickDescriptionFromVoyagerPayload(json) {
    const tryText = (obj) => {
      if (!obj) return "";
      if (typeof obj === "string") return stripHtml(obj);
      if (typeof obj.text === "string") return normalizeJdText(obj.text);
      if (typeof obj.description === "string") return stripHtml(obj.description);
      return "";
    };

    let best = tryText(json?.data?.description);
    if (best.length > 40) return best;

    const included = json?.included || json?.data?.included;
    if (Array.isArray(included)) {
      for (const item of included) {
        const t = tryText(item?.description) || tryText(item?.message) || tryText(item);
        if (t.length > best.length) best = t;
      }
    }

    const walk = (obj, depth) => {
      if (!obj || depth > 10 || typeof obj !== "object") return "";
      if (obj.description) {
        const t = tryText(obj.description);
        if (t.length > 40) return t;
      }
      for (const val of Object.values(obj)) {
        if (val && typeof val === "object") {
          const t = walk(val, depth + 1);
          if (t.length > 40) return t;
        }
      }
      return "";
    };
    const walked = walk(json?.data, 0);
    return walked.length > best.length ? walked : best;
  }

  async function fetchJobDescriptionFromApi(jobId) {
    const csrf = linkedInCsrfToken();
    if (!csrf || !jobId) return "";

    const headers = {
      accept: "application/vnd.linkedin.normalized+json+2.1",
      "csrf-token": csrf,
      "x-restli-protocol-version": "2.0.0",
    };
    const urls = [
      `https://www.linkedin.com/voyager/api/jobs/jobPostings/${jobId}?decorationId=com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65`,
      `https://www.linkedin.com/voyager/api/jobs/jobPostings/${jobId}?decorationId=com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-67`,
      `https://www.linkedin.com/voyager/api/jobs/jobPostings/urn:li:fs_jobPosting:${jobId}`,
    ];

    for (const url of urls) {
      try {
        const resp = await fetch(url, { credentials: "include", headers });
        if (!resp.ok) continue;
        const json = await resp.json();
        const text = pickDescriptionFromVoyagerPayload(json);
        if (text.length > 40) return text;
      } catch (_) {
        /* try next URL */
      }
    }
    return "";
  }

  function expandAllShowMoreOnPage() {
    let clicked = false;
    document.querySelectorAll("button, span, a").forEach((el) => {
      if (isInsideBadge(el)) return;
      const t = (el.textContent || "").trim().toLowerCase();
      if (t !== "show more" && t !== "…more" && t !== "...more" && t !== "see more") return;
      if (!el.closest("main, [class*='job'], [class*='jobs'], section, article")) return;
      simulateClick(el);
      clicked = true;
    });
    return clicked;
  }

  function extractJobDescriptionByMetadataAnchor() {
    const anchorTexts = new Set(["Seniority level", "Employment type", "Job function", "Industries"]);
    let best = "";

    document.querySelectorAll("h3, h4, span, dt, strong").forEach((el) => {
      if (isInsideBadge(el)) return;
      if (el.children.length > 1) return;
      const txt = (el.textContent || "").trim();
      if (!anchorTexts.has(txt)) return;

      let node = el.closest("ul, ol, section, div");
      for (let hop = 0; hop < 6 && node; hop++) {
        let prev = node.previousElementSibling;
        for (let i = 0; i < 4 && prev; i++) {
          const t = elementPlainText(prev);
          if (t.length > best.length && t.length > 120 && !/Similar jobs|People also viewed/i.test(t)) {
            best = t;
          }
          prev = prev.previousElementSibling;
        }
        node = node.parentElement;
      }
    });
    return best.replace(/\bShow more\b|\bShow less\b/gi, "").trim();
  }

  function extractFromShowMoreContainer() {
    let best = "";
    document.querySelectorAll('[class*="show-more-less"], [class*="description"]').forEach((el) => {
      if (isInsideBadge(el)) return;
      const t = elementPlainText(el);
      if (t.length > best.length && t.length > 80) best = t;
    });

    document.querySelectorAll("button, span").forEach((el) => {
      if (isInsideBadge(el)) return;
      const t = (el.textContent || "").trim().toLowerCase();
      if (t !== "show more" && t !== "…more" && t !== "...more") return;
      const host = el.closest('[class*="description"], [class*="show-more"], section, article, div');
      if (!host) return;
      const text = elementPlainText(host).replace(/\bShow more\b|\bShow less\b/gi, "").trim();
      if (text.length > best.length) best = text;
    });
    return best;
  }

  function findJobDetailsRoot() {
    const selectors = [
      "#job-details",
      ".show-more-less-html",
      "[class*='show-more-less-html']",
      ".jobs-description",
      ".jobs-description__content",
      ".jobs-description-content__text",
      ".jobs-search__job-details",
      ".jobs-search__right-rail",
      ".scaffold-layout__detail",
      "[class*='jobs-details__main-content']",
      "[class*='job-details-jobs-unified-top-card']",
      ".jobs-details",
      "main",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && !el.closest(`#${BADGE_ID}`)) return el;
    }
    const titleEl = document.querySelector(
      ".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1.t-24, .top-card-layout__title"
    );
    if (titleEl) {
      const panel = titleEl.closest(
        ".scaffold-layout__detail, .jobs-search__job-details, [class*='job-details'], .jobs-search__right-rail"
      );
      if (panel && !panel.closest(`#${BADGE_ID}`)) return panel;
    }
    return null;
  }

  function jdExpandScope(root) {
    if (!root) return null;
    if (root.matches?.(".show-more-less-html, #job-details, .jobs-description, .jobs-description__content")) {
      return root;
    }
    return (
      root.querySelector(".show-more-less-html") ||
      root.querySelector("#job-details") ||
      root.querySelector(".jobs-description") ||
      root.querySelector(".jobs-description__content") ||
      null
    );
  }

  function scrollJobPanelIntoView(root) {
    if (!root) return;
    root.scrollIntoView({ block: "nearest", behavior: "instant" });
  }

  function simulateClick(el) {
    if (!(el instanceof HTMLElement)) return;
    el.click();
  }

  function clickShowMoreIn(root) {
    const scope = jdExpandScope(root);
    if (!scope) return false;
    let clicked = false;
    const selectors = [
      ".jobs-description__footer-button",
      "[data-tracking-control-name='public_jobs_show-more-html-btn']",
      ".show-more-less-html__button--more",
      ".show-more-less-html__button",
      "button.show-more-less-html__button--more",
    ];
    for (const sel of selectors) {
      scope.querySelectorAll(sel).forEach((btn) => {
        simulateClick(btn);
        clicked = true;
      });
    }
    scope.querySelectorAll(".show-more-less-html span").forEach((span) => {
      const t = (span.textContent || "").trim().toLowerCase();
      if (span.children.length === 0 && (t === "more" || t === "…more" || t === "...more")) {
        simulateClick(span.parentElement || span);
        clicked = true;
      }
    });
    return clicked;
  }

  /** Expand LinkedIn's collapsed JD ("Show more") before we scrape text. */
  async function expandJobDescription() {
    const root = findJobDetailsRoot();
    if (root) {
      scrollJobPanelIntoView(root);
      for (let i = 0; i < 6; i++) {
        clickShowMoreIn(root);
        await sleep(160);
      }
    } else {
      for (let i = 0; i < 4; i++) {
        expandAllShowMoreOnPage();
        await sleep(160);
      }
    }
    await sleep(250);
  }

  function stripHtml(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return (tmp.innerText || tmp.textContent || "").replace(/\s+\n/g, "\n").trim();
  }

  function extractJobDescriptionFromJsonLd() {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const raw = JSON.parse(script.textContent || "");
        const nodes = Array.isArray(raw) ? raw : raw["@graph"] ? raw["@graph"] : [raw];
        for (const node of nodes) {
          const type = node?.["@type"];
          const isJob =
            type === "JobPosting" || (Array.isArray(type) && type.includes("JobPosting"));
          if (isJob && node.description) {
            const text = typeof node.description === "string" ? stripHtml(node.description) : "";
            if (text.length > 40) return text;
          }
        }
      } catch (_) {
        /* ignore malformed JSON-LD */
      }
    }
    return "";
  }

  function normalizeJdText(text) {
    return String(text || "")
      .replace(/\u00a0/g, " ")
      .replace(/\s+\n/g, "\n")
      .trim();
  }

  function elementPlainText(el) {
    if (!el) return "";
    return normalizeJdText(el.textContent || el.innerText || "");
  }

  function extractFromJobPanelHeuristic() {
    const titleEl = document.querySelector(
      ".job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1.t-24, .top-card-layout__title, .job-details-jobs-unified-top-card__job-title h1"
    );
    const panel =
      titleEl?.closest(
        ".scaffold-layout__detail, .jobs-search__job-details, .jobs-search__right-rail, [class*='job-details']"
      ) || findJobDetailsRoot();
    if (!panel || panel.closest(`#${BADGE_ID}`)) return "";

    const markup =
      panel.querySelector(".show-more-less-html__markup") ||
      panel.querySelector(".show-more-less-html");
    if (markup) {
      const t = elementPlainText(markup);
      if (t.length > 40) return t;
    }

    const jdHost =
      panel.querySelector("#job-details") ||
      panel.querySelector(".jobs-description") ||
      panel.querySelector("[class*='jobs-description']");
    if (jdHost) {
      const t = elementPlainText(jdHost);
      if (t.length > 40) return t;
    }

    const lines = [];
    panel.querySelectorAll("p, li").forEach((el) => {
      if (el.closest(`#${BADGE_ID}`)) return;
      const t = (el.textContent || "").trim();
      if (t.length >= 24 && t.length < 600) lines.push(t);
    });
    if (lines.length) return normalizeJdText(lines.join("\n"));
    return "";
  }

  function extractJobDescriptionFromDom() {
    const selectors = [
      ".show-more-less-html__markup",
      "[class*='show-more-less-html__markup']",
      ".show-more-less-html",
      "[class*='show-more-less-html']",
      "#job-details",
      ".jobs-description__content",
      ".jobs-description-content__text",
      ".jobs-description-content__text--stretch",
      ".jobs-box__html-content",
      "article.jobs-description__container",
      ".core-section-container__content",
      ".description__text",
      ".jobs-description",
      "[class*='jobs-description-content']",
      "[class*='jobs-description']",
      "[id*='job-details']",
      "[class*='about-the-job']",
    ];
    let best = "";
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        if (isInsideBadge(el)) return;
        const text = elementPlainText(el);
        if (text.length > best.length) best = text;
      });
    }

    for (const fn of [
      extractFromShowMoreContainer,
      extractJobDescriptionByMetadataAnchor,
      extractFromJobPanelHeuristic,
    ]) {
      const t = fn();
      if (t.length > best.length) best = t;
    }

    const root = findJobDetailsRoot();
    if (root && best.length < 120) {
      let largest = "";
      root.querySelectorAll("div, section, article").forEach((el) => {
        if (isInsideBadge(el)) return;
        const text = elementPlainText(el);
        if (text.length > largest.length && text.length < 50000) largest = text;
      });
      if (largest.length > best.length) best = largest;
    }
    return best.replace(/\bShow more\b|\bShow less\b/gi, "").trim();
  }

  function extractJobDescription() {
    const jsonLd = extractJobDescriptionFromJsonLd();
    const dom = extractJobDescriptionFromDom();
    return dom.length >= jsonLd.length ? dom : jsonLd;
  }

  async function captureJobDescription() {
    const isDirectJobView = /\/jobs\/view\/\d+/i.test(window.location.pathname);
    const maxAttempts = isDirectJobView ? 28 : 20;
    let best = "";
    let source = "dom";

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      await expandJobDescription();
      const text = extractJobDescription();
      if (text.length > best.length) best = text;
      if (best.length > 120) break;
      await sleep(isDirectJobView ? 350 : 280);
    }

    if (best.length < 40) {
      const retry = extractFromJobPanelHeuristic();
      if (retry.length > best.length) best = retry;
    }

    if (best.length < 40) {
      const jobId = extractJobId();
      if (jobId) {
        const apiText = await fetchJobDescriptionFromApi(jobId);
        if (apiText.length > best.length) {
          best = apiText;
          source = "api";
        }
      }
    }

    console.info("[Hop] JD capture:", best.length, "chars via", source);
    return best;
  }

  async function gatherJobInputs(ctx) {
    const jd_text = await captureJobDescription();
    const probe = probeJdOnPage();
    return {
      company: ctx.displayName || null,
      title: extractJobTitle(),
      jd_text,
      job_url: window.location.href,
      captureProbe: probe,
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

  function stripClaimPrefix(claim) {
    return String(claim || "").replace(/^\[(strong|partial|weak|missing)\]\s*/i, "");
  }

  function isSkillEvidence(claim) {
    const t = stripClaimPrefix(claim || "").trim();
    if (t.length < 10) return false;
    const lower = t.toLowerCase();
    if (/^(in person|in-person|on-?site|hybrid|remote only|must be located|based in)/i.test(lower)) {
      return false;
    }
    if (/^[A-Za-z .'-]+,\s*[A-Z]{2}\b/.test(t) && t.length < 64) return false;
    if (/^(san francisco|palo alto|new york|chicago|seattle|austin|boston)/i.test(lower) && t.length < 48) {
      return false;
    }
    return true;
  }

  function renderMetricsGrid(rec) {
    const cells = [];

    cells.push({
      val: rec.track_priority != null ? `P${rec.track_priority}` : "—",
      lbl: "Role",
      hint:
        rec.track_label ||
        (rec.track_priority != null ? `Priority ${rec.track_priority} track` : "No track match"),
    });

    if (rec.fit_ratio != null) {
      cells.push({
        val: `${Math.round(rec.fit_ratio * 100)}%`,
        lbl: "Resume",
        hint: "Parsed JD requirements vs your resume",
      });
    }

    cells.push({
      val: rec.location_tier != null ? `P${rec.location_tier}` : "—",
      lbl: "Location",
      hint: rec.location_label || "Location tier",
    });

    const pref = rec.preferences_matched ?? 0;
    cells.push({
      val: String(pref),
      lbl: "Prefs",
      hint:
        (rec.preferences_total ?? 0) > 0
          ? `${pref} of ${rec.preferences_total} preference(s) matched`
          : "No preferences configured",
    });

    const deal = rec.dealbreakers_matched ?? 0;
    cells.push({
      val: String(deal),
      lbl: "Flags",
      hint:
        (rec.dealbreakers_total ?? 0) > 0
          ? `${deal} dealbreaker(s) matched in JD`
          : "No dealbreakers configured",
    });

    return renderMetricGrid(cells);
  }

  function renderEvidenceLine(rf) {
    const buckets = rf?.available ? hardRequirementFit(rf) : null;
    if (!buckets) return "";
    const pick = (list) => list.find((c) => isSkillEvidence(c.claim));
    const topStrong = pick(buckets.strong);
    const topPartial = pick(buckets.partial);
    const topGap = pick(buckets.gaps);
    if (!topStrong && !topPartial && !topGap) return "";
    const bits = [];
    if (topStrong) {
      bits.push(
        `<span class="lca-ev lca-ev-match" title="${escapeHtml(stripClaimPrefix(topStrong.claim))}">${escapeHtml(truncateText(stripClaimPrefix(topStrong.claim), 36))}</span>`
      );
    } else if (topPartial) {
      bits.push(
        `<span class="lca-ev lca-ev-match" title="${escapeHtml(stripClaimPrefix(topPartial.claim))}">${escapeHtml(truncateText(stripClaimPrefix(topPartial.claim), 36))}</span>`
      );
    }
    if (topGap) {
      bits.push(
        `<span class="lca-ev lca-ev-gap" title="${escapeHtml(stripClaimPrefix(topGap.claim))}">${escapeHtml(truncateText(stripClaimPrefix(topGap.claim), 36))}</span>`
      );
    }
    return `<div class="lca-evidence">${bits.join("")}</div>`;
  }

  const VERDICT_LABELS = {
    Apply: { text: "Apply", tone: "apply" },
    Consider: { text: "Consider", tone: "consider" },
    Skip: { text: "Skip", tone: "skip" },
    // legacy API strings (cached responses)
    "Apply with modifications": { text: "Consider", tone: "consider" },
    "Low priority": { text: "Consider", tone: "consider" },
  };

  function renderAnalysisBlock(rec, rf) {
    if (!rec?.available && !rf?.available) return "";
    if (!rec?.available) return "";

    const meta = VERDICT_LABELS[rec.decision] || { text: rec.decision || "?", tone: "later" };
    const note = buildVerdictNote(rec);

    return `
      <div class="lca-analysis">
        <div class="lca-verdict-row">
          ${statusPill(meta.text, meta.tone)}
          ${note ? `<span class="lca-verdict-note">${escapeHtml(note)}</span>` : ""}
        </div>
        ${renderMetricsGrid(rec)}
        ${renderEvidenceLine(rf)}
      </div>`;
  }

  function renderRiskSection(risk) {
    if (!risk?.available || !risk.risks?.length) return "";
    const top = risk.risks[0];
    const more = risk.risks.length > 1 ? ` · +${risk.risks.length - 1}` : "";
    return `<p class="lca-risk-line">⚠ ${escapeHtml(truncateText(top.claim, 56))}${more ? `<span class="lca-risk-more">${escapeHtml(more)}</span>` : ""}</p>`;
  }

  function probeJdOnPage() {
    const jobDetails = document.querySelector("#job-details");
    const markup =
      document.querySelector(".show-more-less-html__markup") ||
      document.querySelector('[class*="show-more-less-html__markup"]');
    const showMoreLess = document.querySelector('[class*="show-more-less"]');
    return {
      jobDetails: jobDetails ? normalizeJdText(jobDetails.textContent).length : 0,
      markup: markup ? normalizeJdText(markup.textContent).length : 0,
      showMoreLess: showMoreLess ? elementPlainText(showMoreLess).length : 0,
      metaAnchor: extractJobDescriptionByMetadataAnchor().length,
      jsonLd: extractJobDescriptionFromJsonLd().length,
    };
  }

  function renderCaptureMeta(captured, probe) {
    const n = captured || 0;
    if (n >= 40) return "";
    const probeBit = probe
      ? ` (debug: legacy ${probe.jobDetails}/${probe.markup}, alt ${probe.showMoreLess}/${probe.metaAnchor})`
      : "";
    return `<p class="lca-err-mini">Couldn't read job description${probeBit}. Expand on LinkedIn, wait, Retry.</p>`;
  }

  function shortJdError(chars, jd) {
    if (typeof chars === "number" && chars < 40) {
      return `Expand the description on LinkedIn, wait a moment, then Retry.`;
    }
    const reason = jd?.reason || "";
    if (!reason) return "";
    const r = reason.toLowerCase();
    if (r.includes("no job description")) return "No job text sent to server.";
    if (r.includes("llm not configured")) return "Server LLM not configured.";
    if (r.includes("parse failed")) return "Server parse failed — Retry.";
    return reason.length > 72 ? `${reason.slice(0, 70)}…` : reason;
  }

  function renderAnalysisInline(report, captureProbe) {
    const chars = report.received?.jd_chars ?? 0;
    const jd = report.jd;
    const rec = report.recommendation;
    const rf = report.resume_fit;

    if (!jd?.available && chars < 40) {
      return `<div class="lca-analyze-inner">${renderCaptureMeta(chars, captureProbe)}<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p></div>`;
    }

    const errLine = !jd?.available ? `<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p>` : "";
    return `<div class="lca-analyze-inner">${errLine}${renderAnalysisBlock(rec, rf)}${renderRiskSection(report.risk)}</div>`;
  }

  function renderAnalysisErrorInline(err) {
    const isNetwork = err instanceof TypeError || /Failed to fetch/i.test(err.message);
    return `<div class="lca-analyze-inner lca-analyze-err">${
      isNetwork
        ? `Can't reach the analysis server. Start it with <code>docker compose up -d</code>, then retry.`
        : escapeHtml(err.message)
    }</div>`;
  }

  async function runAnalysis(out, ctx) {
    if (!out) return;
    out.innerHTML = `<div class="lca-loading-row"><span class="lca-spinner"></span> Checking fit…</div>`;
    try {
      const inputs = await gatherJobInputs(ctx);
      const report = await analyzeWithBackend(inputs);
      out.innerHTML = renderAnalysisInline(report, inputs.captureProbe);
    } catch (err) {
      console.error("[Job Intelligence]", err);
      out.innerHTML = renderAnalysisErrorInline(err);
      out.dataset.analyzedFor = "";
    }
  }

  async function run(options = {}) {
    if (extensionBroken) return;
    const ctx = extractPageContext();
    const onJobs = window.location.pathname.includes("/jobs");
    const onCompany = window.location.pathname.includes("/company/");

    if (!onJobs && !onCompany) {
      document.getElementById(BADGE_ID)?.remove();
      lastFingerprint = null;
      return;
    }

    if (!ctx.pageKey) {
      if (onJobs) renderWaiting(ctx);
      return;
    }

    const fp = contextFingerprint(ctx);
    if (!options.force && fp === lastFingerprint) return;
    lastFingerprint = fp;

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
      const hint =
        /extension disconnected|extension was updated|getURL/i.test(String(err.message))
          ? `<div class="lca-hint">${escapeHtml(err.message)}</div>`
          : `<div class="lca-foot">${escapeHtml(err.message)}</div>`;
      el.innerHTML = `
        ${renderChrome()}
        <div class="lca-body">
          <div class="lca-title">H-1B lookup failed</div>
          ${hint}
          <button type="button" class="lca-refresh-btn">Refresh</button>
          <div class="lca-analyze-result"></div>
        </div>`;
      finishBadge(el, ctx);
    }
  }

  function onNavigate() {
    lastFingerprint = null;
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
  }, 400);

  const obs = new MutationObserver(scheduleRun);
  obs.observe(document.body, { childList: true, subtree: true });

  window.addEventListener("popstate", onNavigate);
})();
