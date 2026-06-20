(function () {
  const EXTENSION_VERSION = chrome.runtime.getManifest().version;
  const BADGE_ID = "joblens-panel";
  const POSITION_KEY = "joblens-panel-position";
  // Production API on EC2 (elastic IP). Use localhost for local dev.
  const BACKEND_URL = "https://3-128-164-130.sslip.io";
  // Lovable web app — set after Publish (vision-job-glow). Empty = no footer link.
  const WEB_APP_URL = "https://vision-job-glow.lovable.app";
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
      "JobLens extension disconnected — open chrome://extensions, reload it, then refresh this page (F5).";
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
      "[JobLens] Extension APIs unavailable (chrome.runtime.getURL missing). " +
        "Reload the extension at chrome://extensions, then refresh this LinkedIn tab."
    );
    return;
  }

  const RV = globalThis.JobLensReportView;
  if (!RV) {
    console.error("[JobLens] lib/report-view.js not loaded — reload extension at chrome://extensions");
    return;
  }

  const CONFIDENCE_META = {
    high: { title: "H-1B sponsor", status: "found" },
    medium: { title: "Possible sponsor", status: "caution" },
    low: { title: "Possible sponsor", status: "caution" },
  };

  /** One sponsor label for the pill — filing volume can upgrade medium → sponsor. */
  function resolveSponsorMeta(confidence, employer) {
    const filings = Number(employer?.lca_count) || 0;
    const certified = Number(employer?.certified_count) || 0;
    const approval = filings > 0 ? certified / filings : 0;
    if (confidence === "high" || (filings >= 100 && approval >= 0.8)) {
      return { title: "H-1B sponsor", status: "found" };
    }
    if (filings >= 25 && approval >= 0.7) {
      return { title: "Likely H-1B sponsor", status: "ok" };
    }
    return CONFIDENCE_META[confidence] || CONFIDENCE_META.medium;
  }

  const SOFT_REQUIREMENT_RE =
    /\b(leadership|lead\b|collaborat|cross[- ]?functional|teamwork|communicat|stakeholder|mentor|passion|fast[- ]?paced|self[- ]?starter|culture|interpersonal|organiz|detail[- ]?oriented|problem[- ]?solving|work across| agile|ownership|motivated|dynamic|ambitious|innovative mindset|people skills|verbal and written)\b/i;

  let lastFingerprint = null;

  function renderFoot(parts) {
    const bits = (parts || []).map((p) => escapeHtml(p)).filter(Boolean);
    if (WEB_APP_URL) {
      bits.push(`<a href="${escapeHtml(WEB_APP_URL)}" target="_blank" rel="noopener">Open web</a>`);
    }
    bits.push(`v${EXTENSION_VERSION}`);
    return `<div class="lca-foot">${bits.join(" · ")}</div>`;
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

  function renderCompanyLine(name, legalName) {
    if (!name && !legalName) return "";
    const logoUrl = extractCompanyLogoUrl();
    const logo = logoUrl
      ? `<img class="lca-co-logo" src="${escapeHtml(logoUrl)}" alt="" width="20" height="20" />`
      : "";
    const primary = name || legalName || "";
    const sub =
      legalName && name && legalName.toLowerCase() !== name.toLowerCase()
        ? `<span class="lca-legal-name">DOL: ${escapeHtml(legalName)}</span>`
        : "";
    return `<div class="lca-company-line">${logo}<div class="lca-company-text"><span class="lca-company">${escapeHtml(primary)}</span>${sub}</div></div>`;
  }

  function renderJobTitleLine(title) {
    if (!title) return "";
    return `<div class="lca-job-title">${escapeHtml(title)}</div>`;
  }

  function renderHeadBlock(pillHtml, displayName, legalName, jobTitle) {
    const titleLine = jobTitle ? renderJobTitleLine(jobTitle) : "";
    return `<div class="lca-section-card lca-section-card--company"><div class="lca-head-block">${renderCompanyLine(displayName, legalName)}${pillHtml ? `<div class="lca-head-pill">${pillHtml}</div>` : ""}</div>${titleLine}</div>`;
  }

  function statusPill(text, tone) {
    return RV.statusPill(text, tone);
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
    return [ctx.pageKey || "", ctx.slug || "", jobId].join("|");
  }

  function navigationKey() {
    const params = new URLSearchParams(window.location.search);
    const qJob = params.get("currentJobId") || "";
    const pathJob = (window.location.pathname.match(/\/jobs\/view\/(\d+)/i) || [])[1] || "";
    return `${window.location.pathname}|${qJob || pathJob}`;
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

  function extractCompanySlugFromLinks(root) {
    const scope = root || document;
    const preferred = scope.querySelector?.(
      'a[data-tracking-control-name="public_jobs_topcard-org-name"]'
    );
    if (preferred && !isInsideBadge(preferred)) {
      const slug = slugFromCompanyHref(preferred.href);
      if (slug && slug !== "linkedin" && slug !== "learning") {
        return {
          slug,
          name: resolveDisplayName(preferred.textContent?.trim(), slug),
        };
      }
    }

    const links = scope.querySelectorAll?.('a[href*="/company/"]') || [];
    for (const link of links) {
      if (isInsideBadge(link)) continue;
      const slug = slugFromCompanyHref(link.href);
      if (!slug || slug === "linkedin" || slug === "learning") continue;
      const name = resolveDisplayName(link.textContent?.trim(), slug);
      if (name) return { slug, name };
    }
    for (const link of links) {
      if (isInsideBadge(link)) continue;
      const slug = slugFromCompanyHref(link.href);
      if (!slug || slug === "linkedin" || slug === "learning") continue;
      return { slug, name: titleFromSlug(slug) };
    }
    return { slug: null, name: null };
  }

  /** Right-hand job panel for currentJobId — not the first /company/ link on the page. */
  function findActiveJobPanel() {
    const jobId = extractJobId();
    if (jobId) {
      for (const sel of [`[data-job-id="${jobId}"]`, `[data-current-job-id="${jobId}"]`]) {
        for (const el of document.querySelectorAll(sel)) {
          if (isInsideBadge(el)) continue;
          const panel =
            el.closest(".jobs-search__job-details") ||
            el.closest(".jobs-search__right-rail") ||
            el.closest(".scaffold-layout__detail") ||
            el.closest(".job-details-jobs-unified-top-card") ||
            el.closest("[class*='job-details-jobs-unified-top-card']");
          if (panel && !isInsideBadge(panel)) return panel;
        }
      }
      const rail = document.querySelector(".jobs-search__job-details, .jobs-search__right-rail");
      if (rail && !isInsideBadge(rail)) {
        if (
          rail.querySelector(
            ".job-details-jobs-unified-top-card, .jobs-unified-top-card, .job-details-jobs-unified-top-card__job-title"
          )
        ) {
          return rail;
        }
      }
    }
    const topCard = document.querySelector(".job-details-jobs-unified-top-card, .jobs-unified-top-card");
    if (topCard && !isInsideBadge(topCard)) {
      return topCard.closest(".jobs-search__job-details") || topCard;
    }
    return findJobDetailsRoot();
  }

  function extractCompanyNameFromDom(isCompanyPage, root) {
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
    const scopes = root ? [root] : [document];
    for (const scope of scopes) {
      for (const sel of selectors) {
        const el = scope.querySelector?.(sel) || (scope === document ? document.querySelector(sel) : null);
        const text = el?.textContent?.trim();
        const cleaned = cleanDisplayName(text);
        if (cleaned) return cleaned;
      }
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
      const panel = findActiveJobPanel();
      const fromLinks = extractCompanySlugFromLinks(panel);
      const domName = extractCompanyNameFromDom(false, panel);
      const displayName =
        domName ||
        fromLinks.name ||
        resolveDisplayName(extractCompanyNameFromDom(false, null), fromLinks.slug);
      const slug = fromLinks.slug;
      const nameKey = (displayName || "unknown").toLowerCase().slice(0, 40);
      return {
        slug,
        displayName,
        jobId,
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
    return RV.escapeHtml(s);
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

  function renderChrome(showRetry = true) {
    const retryBtn = showRetry
      ? `<button type="button" class="lca-refresh-btn" title="Re-run H-1B + fit analysis for this job">Retry</button>`
      : "";
    return `<div class="lca-chrome"><span class="lca-drag-handle" title="Drag to move">⋮⋮</span><span class="lca-brand">JobLens</span>${retryBtn}<button type="button" class="lca-close" aria-label="Close panel">×</button></div>`;
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
    RV.wireMetricTips(el);
    if (ctx) runAutoAnalyze(el, ctx);
  }

  function wireRefreshButton(el) {
    const btn = el.querySelector(".lca-refresh-btn");
    if (!btn || btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      lastFingerprint = null;
      if (typeof LcaMatcher.clearCache === "function") LcaMatcher.clearCache();
      const out = el.querySelector(".lca-analyze-result");
      if (out) out.dataset.analyzedFor = "";
      await run({ force: true });
    });
  }

  function showCompanyPageFitHint(out) {
    if (!out) return;
    out.innerHTML = `<div class="lca-section-card lca-section-card--fit">${renderCompanyPageAnalyzeHint()}</div>`;
  }

  async function runAutoAnalyze(el, ctx) {
    const out = el.querySelector(".lca-analyze-result");
    if (!out) return;
    if (!canRunFitAnalysis(ctx)) {
      showCompanyPageFitHint(out);
      return;
    }
    await runAnalysis(out, ctx);
  }

  function renderH1bSummary(employer, currentJobTitle) {
    const filings = Number(employer.lca_count) || 0;
    if (filings <= 0) return "";
    return RV.renderH1bBlock(
      {
        filings,
        certified: employer.certified_count,
        top_jobs: employer.top_jobs,
      },
      currentJobTitle
    );
  }

  function renderBadge(result, ctx) {
    const { employer, confidence } = result;
    const meta = resolveSponsorMeta(confidence, employer);
    const el = ensureBadge();
    const displayName = ctx.displayName || employer.name;
    const jobTitle = extractJobTitle();

    el.className = `lca-badge lca-${meta.status}`;
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        ${renderHeadBlock(statusPill(meta.title, meta.status === "found" || meta.status === "ok" ? "ok" : "caution"), displayName, employer.name, jobTitle)}
        ${renderH1bSummary(employer, jobTitle)}
        <div class="lca-analyze-result" data-section="fit"></div>
        ${renderFoot(["Source: U.S. DOL H-1B"])}
      </div>`;
    finishBadge(el, ctx);
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        ${renderHeadBlock(statusPill("No H-1B record", "neutral"), ctx.displayName || "", null, extractJobTitle())}
        <div class="lca-analyze-result"></div>
        ${renderFoot(["May file under a different legal name"])}
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

  function isCompanyProfilePage() {
    return Boolean(window.location.pathname.match(/^\/company\/[^/?#]+/i)) &&
      !window.location.pathname.includes("/jobs");
  }

  function canRunFitAnalysis(ctx) {
    if (ctx?.source === "company page" || isCompanyProfilePage()) return false;
    return Boolean(ctx?.pageKey) && (ctx?.jobId || /\/jobs\//i.test(window.location.pathname));
  }

  function renderCompanyPageAnalyzeHint() {
    return `<p class="lca-hint">Open a <strong>job posting</strong> (Jobs tab or search) to see Apply / Skip fit. H-1B lookup above still works on this page.</p>`;
  }

  function extractJobTitle() {
    const selectors = [
      ".job-details-jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title",
      ".job-details-jobs-unified-top-card__job-title h1",
      ".job-details-jobs-unified-top-card__job-title a",
      "h1.jobs-unified-top-card__job-title",
      ".jobs-unified-top-card__job-title h1",
      ".jobs-unified-top-card__job-title a",
      ".top-card-layout__title",
      ".jobs-details-top-card__job-title",
      "[data-test-job-title]",
      "h1.t-24",
      "main h1",
    ];
    const panel = findActiveJobPanel();
    for (const scope of [panel, document]) {
      if (!scope) continue;
      for (const sel of selectors) {
        const text = scope.querySelector?.(sel)?.textContent?.trim();
        if (text) return text.replace(/\s+/g, " ");
      }
    }
    const og = document.querySelector('meta[property="og:title"]')?.content;
    if (og) {
      const bit = og.split("|")[0].trim();
      if (bit.length >= 6) return bit;
    }
    return null;
  }

  /** LinkedIn shows city/state under the job title — not always in the title string. */
  function normalizeJobLocation(raw) {
    if (!raw) return null;
    const s = String(raw).replace(/\s+/g, " ").trim();
    if (!s) return null;
    const segments = s.split(/\s*[·•|]\s*/).map((x) => x.trim()).filter(Boolean);
    const candidates = segments.length ? segments : [s];
    for (const part of candidates) {
      const m = part.match(/^([A-Za-z][A-Za-z .'-]*,\s*[A-Z]{2})\b/);
      if (m) return m[1].trim();
      if (/^[A-Za-z][A-Za-z .'-]*,\s*[A-Za-z][A-Za-z .'-]+$/.test(part) && part.length <= 64) {
        return part;
      }
    }
    return s.length <= 80 ? s : null;
  }

  function extractJobLocationFromJsonLd() {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const parsed = JSON.parse(script.textContent || "");
        const items = Array.isArray(parsed) ? parsed : [parsed];
        for (const item of items) {
          if (!item || (item["@type"] !== "JobPosting" && !item.jobLocation)) continue;
          const jl = item.jobLocation;
          const addr = jl?.address || jl;
          const city = addr?.addressLocality || (typeof jl === "string" ? jl : jl?.name);
          const region = addr?.addressRegion;
          if (city && region) return normalizeJobLocation(`${city}, ${region}`);
          if (city) return normalizeJobLocation(city);
        }
      } catch (_) {
        /* ignore */
      }
    }
    return null;
  }

  function extractJobLocation() {
    const fromJson = extractJobLocationFromJsonLd();
    if (fromJson) return fromJson;

    const selectors = [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".job-details-jobs-unified-top-card__primary-description",
      ".jobs-unified-top-card__primary-description",
      ".jobs-unified-top-card__bullet",
      ".job-details-jobs-unified-top-card__bullet",
      ".jobs-unified-top-card__subtitle-primary-grouping",
      ".job-details-jobs-unified-top-card__subtitle-primary-grouping",
      ".jobs-unified-top-card__workplace-type",
      ".job-details-jobs-unified-top-card__workplace-type",
      "[data-test-job-location]",
      ".top-card-layout__entity-info .t-black--light",
    ];
    const panel = findActiveJobPanel();
    for (const scope of [panel, document]) {
      if (!scope) continue;
      for (const sel of selectors) {
        const nodes = scope.querySelectorAll?.(sel);
        if (!nodes?.length) continue;
        for (const node of nodes) {
          const text = node.textContent?.replace(/\s+/g, " ").trim();
          if (!text || text.length < 3 || text.length > 120) continue;
          if (/^\d+\s+(follower|employee)/i.test(text)) continue;
          if (/^posted\s/i.test(text)) continue;
          const norm = normalizeJobLocation(text);
          if (norm) return norm;
        }
      }
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
    if (isCompanyProfilePage()) return "";

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

  /** Never click LinkedIn UI — passive read + Voyager API only. */
  async function captureJobDescription() {
    if (isCompanyProfilePage()) return "";

    let best = extractJobDescription();
    if (best.length < 200) {
      const retry = extractFromJobPanelHeuristic();
      if (retry.length > best.length) best = retry;
    }

    const jobId = extractJobId();
    if (jobId && best.length < 400) {
      const apiText = await fetchJobDescriptionFromApi(jobId);
      if (apiText.length > best.length) best = apiText;
    }

    console.info("[JobLens] JD capture:", best.length, "chars (passive)");
    return best;
  }

  async function gatherJobInputs(ctx) {
    const jd_text = await captureJobDescription();
    const probe = probeJdOnPage();
    const linkedin = extractLinkedInCompanySignals();
    return {
      company: ctx.displayName || null,
      title: extractJobTitle(),
      job_location: extractJobLocation(),
      jd_text,
      job_url: window.location.href,
      captureProbe: probe,
      linkedin_followers: linkedin.followers,
      alumni_hints: linkedin.alumni_hints,
    };
  }

  function parseFollowerCount(raw) {
    const s = String(raw || "").replace(/,/g, "").trim();
    const m = s.match(/^([\d.]+)\s*([KMB])?$/i);
    if (!m) return null;
    let n = parseFloat(m[1]);
    if (Number.isNaN(n)) return null;
    const u = (m[2] || "").toUpperCase();
    if (u === "K") n *= 1000;
    else if (u === "M") n *= 1_000_000;
    else if (u === "B") n *= 1_000_000_000;
    return Math.round(n);
  }

  /** Read follower / alumni lines from the open LinkedIn page (no backend crawl). */
  function extractLinkedInCompanySignals() {
    const root = findActiveJobPanel() ||
      document.querySelector(
        ".jobs-unified-top-card, .job-details-jobs-unified-top-card, .org-top-card"
      ) ||
      document.body;
    const text = root.innerText || "";

    let followers = null;
    const fm = text.match(/([\d,.]+[KMB]?)\s+followers?\b/i);
    if (fm) followers = parseFollowerCount(fm[1]);

    const alumni_hints = [];
    const re = /([\d,.]+)\s+([^\n·|]{3,80}?)\s+alumni\s+work\s+here/gi;
    let m;
    while ((m = re.exec(text)) !== null) {
      alumni_hints.push(`${m[1].trim()} ${m[2].trim()} alumni`.replace(/\s+/g, " "));
    }
    if (/people from your (?:school|network)/i.test(text)) {
      alumni_hints.push("people from your school");
    }

    return { followers, alumni_hints: [...new Set(alumni_hints)].slice(0, 5) };
  }

  async function analyzeWithBackend(inputs) {
    const body = {
      jd_text: inputs.jd_text || "",
      company: inputs.company,
      title: inputs.title,
      job_location: inputs.job_location || null,
      job_url: inputs.job_url,
      linkedin_followers: inputs.linkedin_followers ?? null,
      alumni_hints: inputs.alumni_hints || [],
    };
    const viaBackground = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "JOBLENS_ANALYZE", body }, (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        resolve(resp || { ok: false, error: "no response" });
      });
    });
    if (viaBackground.ok && viaBackground.data) return viaBackground.data;
    if (viaBackground.status) {
      throw new Error(`Backend responded ${viaBackground.status}${viaBackground.error ? ` — ${viaBackground.error}` : ""}`);
    }
    if (viaBackground.error) throw new TypeError(viaBackground.error);

    // Fallback: direct fetch (local dev)
    const resp = await fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
      return `Expand the job description on LinkedIn (click Show more), wait a moment, then Retry.`;
    }
    const reason = jd?.reason || "";
    if (!reason) return "Could not parse job requirements — expand the JD and Retry.";
    const r = reason.toLowerCase();
    if (r.includes("no job description")) return "No job text sent to server.";
    if (r.includes("llm not configured")) return "Server LLM not configured.";
    if (r.includes("parse failed")) return "Server parse failed — Retry.";
    if (r.includes("no requirements extracted")) {
      return "Could not read job requirements — open the full posting, expand description, Retry.";
    }
    return reason.length > 72 ? `${reason.slice(0, 70)}…` : reason;
  }

  function enrichReport(report, inputs) {
    return {
      ...report,
      received: {
        ...(report.received || {}),
        title: inputs?.title || report.received?.title || extractJobTitle() || null,
        company: inputs?.company || report.received?.company || null,
        job_location: inputs?.job_location || report.received?.job_location || extractJobLocation() || null,
      },
    };
  }

  function renderAnalysisInline(report, captureProbe, inputs) {
    const chars = report.received?.jd_chars ?? 0;
    const jd = report.jd;

    if (!jd?.available && chars < 40) {
      return `<div class="lca-analyze-inner">${renderCaptureMeta(chars, captureProbe)}<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p></div>`;
    }

    const enriched = enrichReport(report, inputs);
    const errLine = !jd?.available ? `<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p>` : "";
    const fitBlock = RV.renderUnifiedReport(enriched, { sections: ["fit", "risk"] });
    return `<div class="lca-analyze-inner">${errLine}${fitBlock}</div>`;
  }

  function renderAnalysisErrorInline(err) {
    const msg = err?.message || String(err);
    const isAbort = /abort/i.test(msg);
    const isNetwork = err instanceof TypeError || /Failed to fetch/i.test(msg);
    return `<div class="lca-analyze-inner lca-analyze-err">${
      isAbort
        ? "Analysis timed out after 2 minutes — the server may be busy. Click <strong>Retry</strong>."
        : isNetwork
        ? `Can't reach the analysis server at <code>${escapeHtml(BACKEND_URL)}</code>. Reload the extension at chrome://extensions, then Retry.`
        : escapeHtml(msg)
    }</div>`;
  }

  let analysisSeq = 0;

  async function runAnalysis(out, ctx) {
    if (!out) return;
    const seq = ++analysisSeq;
    const stillCurrent = () => seq === analysisSeq;

    const fresh = extractPageContext();
    if (fresh.pageKey) ctx = fresh;
    if (!canRunFitAnalysis(ctx)) {
      showCompanyPageFitHint(out);
      return;
    }

    out.innerHTML = `<div class="lca-section-card lca-section-card--fit"><div class="lca-section-label">Fit analysis</div><div class="lca-loading-row"><span class="lca-spinner"></span> Analyzing fit… usually 30–60s</div></div>`;

    try {
      let inputs = await gatherJobInputs(ctx);
      let jdWait = 0;
      while ((inputs.jd_text || "").length < 80 && jdWait < 6) {
        if (!stillCurrent()) return;
        out.innerHTML = `<div class="lca-section-card lca-section-card--fit"><div class="lca-section-label">Fit analysis</div><div class="lca-loading-row"><span class="lca-spinner"></span> Loading job description…</div></div>`;
        await sleep(900);
        inputs = await gatherJobInputs(ctx);
        jdWait += 1;
      }

      if (!stillCurrent()) return;

      if ((inputs.jd_text || "").length < 80) {
        out.innerHTML = `<div class="lca-analyze-inner">${renderCaptureMeta(inputs.jd_text?.length || 0, inputs.captureProbe)}<p class="lca-err-mini">Job description not loaded yet — expand it on LinkedIn, wait a moment, then click <strong>Retry</strong>.</p></div>`;
        out.dataset.analyzedFor = "";
        return;
      }

      const report = await analyzeWithBackend(inputs);
      if (!stillCurrent()) return;

      window.__jobLensLastReport = report;
      console.debug("[JobLens] explain:", report.explain);
      out.innerHTML = renderAnalysisInline(report, inputs.captureProbe, inputs);
      RV.wireMetricTips(document.getElementById(BADGE_ID));
    } catch (err) {
      if (!stillCurrent()) return;
      console.error("[JobLens]", err);
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
      console.error("[JobLens]", err);
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
          <button type="button" class="lca-refresh-btn">Retry</button>
          <div class="lca-analyze-result"></div>
        </div>`;
      finishBadge(el, ctx);
    }
  }

  let lastNavKey = navigationKey();

  function onNavigate() {
    const key = navigationKey();
    if (key === lastNavKey) return;
    lastNavKey = key;
    lastFingerprint = null;
    scheduleRun();
  }

  run();

  let debounceTimer = null;
  function scheduleRun() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(run, 1200);
  }

  window.addEventListener("popstate", onNavigate);
  // LinkedIn calls replaceState constantly — do NOT hook pushState/replaceState.
  setInterval(() => {
    const key = navigationKey();
    if (key !== lastNavKey) onNavigate();
  }, 1500);
})();
