(function () {
  const BADGE_ID = "joblens-panel";
  const POSITION_KEY = "joblens-panel-position";
  // Production API on EC2 (elastic IP). Use localhost for local dev.
  const BACKEND_URL = "https://3-128-164-130.sslip.io";
  // Official web app (Lovable production URL)
  const WEB_APP_URL = "https://job-lens-main.lovable.app";
  const WEB_LOGIN_URL = `${WEB_APP_URL}?from=extension`;
  const WEB_SIGNUP_URL = `${WEB_APP_URL}?from=extension&panel=register`;
  const WEB_PROFILE_URL = `${WEB_APP_URL}?from=extension&panel=profile`;
  let extensionBroken = false;
  let extensionStale = false;

  function extensionRuntime() {
    try {
      const rt = globalThis.chrome?.runtime ?? globalThis.browser?.runtime ?? null;
      if (rt?.id) void rt.id;
      return rt;
    } catch (_) {
      return null;
    }
  }

  function extensionVersion() {
    try {
      return extensionRuntime()?.getManifest?.()?.version || "?";
    } catch (_) {
      return "?";
    }
  }

  function isExtensionContextError(err) {
    const msg = String(err?.message || err || "");
    return /extension context invalidated|extension was updated|receiving end does not exist|message port closed|could not establish connection/i.test(
      msg
    );
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

  /** Extension was reloaded while this tab stayed open — APIs dead but page may still work via fetch. */
  function markExtensionStale() {
    if (extensionBroken || extensionStale) return;
    extensionStale = true;
    console.warn(
      "[JobLens] Extension was reloaded — refresh this LinkedIn tab (F5) for full plugin features."
    );
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
  const AC = globalThis.JobLensAnalyzeClient;
  if (!RV || !AC) {
    showExtensionBrokenBanner();
    console.error(
      "[JobLens] Shared UI failed to load (report-view or analyze-client). " +
        "Reload the extension at chrome://extensions, then refresh this LinkedIn tab."
    );
    return;
  }

  const SOFT_REQUIREMENT_RE =
    /\b(leadership|lead\b|collaborat|cross[- ]?functional|teamwork|communicat|stakeholder|mentor|passion|fast[- ]?paced|self[- ]?starter|culture|interpersonal|organiz|detail[- ]?oriented|problem[- ]?solving|work across| agile|ownership|motivated|dynamic|ambitious|innovative mindset|people skills|verbal and written)\b/i;

  let lastFingerprint = null;

  function renderFoot(parts) {
    const meta = (parts || []).map((p) => escapeHtml(p)).filter(Boolean);
    const metaHtml = meta.length ? `<span class="lca-foot-meta">${meta.join(" · ")}</span>` : "";
    const site = WEB_APP_URL
      ? `<span class="lca-foot-site">${brandLogoHtml(14)}<a href="${escapeHtml(WEB_APP_URL)}" target="_blank" rel="noopener">${escapeHtml(WEB_APP_URL)}</a></span>`
      : "";
    const ver = `<span class="lca-foot-ver">v${extensionVersion()}</span>`;
    return `<div class="lca-foot">${metaHtml}${site}${ver}</div>`;
  }

  async function readAuthState() {
    try {
      const store = chrome.storage?.local;
      if (!store?.get) return { signedIn: false, email: null };
      const data = await new Promise((resolve) =>
        store.get(["joblens_token", "joblens_email"], resolve)
      );
      return {
        signedIn: Boolean(data?.joblens_token),
        email: data?.joblens_email || null,
      };
    } catch (_) {
      return { signedIn: false, email: null };
    }
  }

  function renderAuthBanner(auth) {
    if (auth.signedIn) {
      const who = auth.email ? escapeHtml(auth.email) : "signed in";
      return `<div class="lca-auth-strip lca-auth-strip--ok">
        <span class="lca-auth-strip-text">${who}</span>
        <span class="lca-auth-strip-links">
          <a href="${escapeHtml(WEB_PROFILE_URL)}" target="_blank" rel="noopener">Profile</a>
        </span>
      </div>`;
    }
    return `<div class="lca-auth-strip">
      <span class="lca-auth-strip-text">Not signed in — default profile</span>
      <span class="lca-auth-strip-links">
        <a href="${escapeHtml(WEB_LOGIN_URL)}" target="_blank" rel="noopener">Log in</a>
        <span class="lca-auth-sep" aria-hidden="true">·</span>
        <a href="${escapeHtml(WEB_SIGNUP_URL)}" target="_blank" rel="noopener">Sign up</a>
      </span>
    </div>`;
  }

  async function refreshAuthBanner() {
    const badge = document.getElementById(BADGE_ID);
    if (!badge) return;
    const auth = await readAuthState();
    const slot = badge.querySelector(".lca-auth-slot");
    if (slot) slot.innerHTML = renderAuthBanner(auth);
    const foot = badge.querySelector(".lca-foot");
    if (foot) foot.outerHTML = renderFoot([]);
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

  function brandLogoHtml(size = 18) {
    const s = Number(size) || 18;
    return `<svg class="lca-logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="${s}" height="${s}" fill="none" aria-hidden="true"><circle cx="13.5" cy="13.5" r="8.5" stroke="#c4654a" stroke-width="2.4"/><circle cx="13.5" cy="13.5" r="3.2" fill="#4a6741"/><path d="M19.8 19.8L27 27" stroke="#c4654a" stroke-width="2.4" stroke-linecap="round"/></svg>`;
  }

  function renderChrome(showRetry = true) {
    const retryBtn = showRetry
      ? `<button type="button" class="lca-refresh-btn" title="Re-run analysis for this job">Retry</button>`
      : "";
    return `<div class="lca-chrome"><span class="lca-drag-handle" title="Drag to move">⋮⋮</span><span class="lca-brand-wrap">${brandLogoHtml(18)}<span class="lca-brand">JobLens</span></span><div class="lca-chrome-actions">${retryBtn}<button type="button" class="lca-close" aria-label="Hide panel" title="Hide panel">&#x2715;</button></div></div>`;
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

  function initPanelChrome(el) {
    initDrag(el);
    const close = el.querySelector(".lca-close");
    if (close) close.addEventListener("click", () => el.remove());
    wireRefreshButton(el);
  }

  function renderPanelShell(auth) {
    const el = ensureBadge();
    el.className = "lca-badge lca-active";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-scroll">
          <div class="lca-analyze-result"></div>
        </div>
        <div class="lca-panel-bottom">
          <div class="lca-auth-slot">${renderAuthBanner(auth)}</div>
          ${renderFoot([])}
        </div>
      </div>`;
    initPanelChrome(el);
    return el;
  }

  function renderLoadingInline(message) {
    return `<div class="lca-analyze-inner"><div class="lca-loading-row"><span class="lca-spinner"></span> ${escapeHtml(message)}</div></div>`;
  }
  function wireRefreshButton(el) {
    const btn = el.querySelector(".lca-refresh-btn");
    if (!btn || btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      lastFingerprint = null;
      const out = el.querySelector(".lca-analyze-result");
      if (out) out.dataset.analyzedFor = "";
      await run({ force: true });
    });
  }

  function showCompanyPageFitHint(out) {
    if (!out) return;
    out.innerHTML = `<div class="lca-section-card lca-section-card--fit">${renderCompanyPageAnalyzeHint()}</div>`;
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
    initPanelChrome(el);
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
    return `<p class="lca-hint">Open a <strong>job posting</strong> (Jobs tab or search) for visa + role fit analysis.</p>`;
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

  /** Passive read: Voyager API (full JD) + JSON-LD + DOM — never click Show more. */
  async function captureJobDescription() {
    if (isCompanyProfilePage()) return "";

    const jobId = extractJobId();
    const candidates = [];

    if (jobId) {
      candidates.push(await fetchJobDescriptionFromApi(jobId));
    }
    candidates.push(extractJobDescriptionFromJsonLd());
    candidates.push(extractJobDescriptionFromDom());

    let best = "";
    for (const text of candidates) {
      const t = text || "";
      if (t.length > best.length) best = t;
    }

    if (best.length < 200) {
      const retry = extractFromJobPanelHeuristic();
      if (retry.length > best.length) best = retry;
    }

    // LinkedIn often hydrates late — retry Voyager once before giving up.
    if (jobId && best.length < 300) {
      await sleep(900);
      const apiRetry = await fetchJobDescriptionFromApi(jobId);
      if (apiRetry.length > best.length) best = apiRetry;
    }

    console.info("[JobLens] JD capture:", best.length, "chars", jobId ? `(job ${jobId})` : "(no job id)");
    return best;
  }

  function extractCompanyLogoUrl() {
    const selectors = [
      ".job-details-jobs-unified-top-card__company-logo img",
      ".jobs-unified-top-card__company-logo img",
      ".job-details-jobs-unified-top-card__company-logo a img",
      "a[data-tracking-control-name='public_jobs_topcard-org-name'] img",
      "a[href*='/company/'] img[src*='licdn.com']",
    ];
    const panel = findActiveJobPanel();
    for (const scope of [panel, document]) {
      if (!scope) continue;
      for (const sel of selectors) {
        const img = scope.querySelector?.(sel) || (scope === document ? document.querySelector(sel) : null);
        if (img?.src && !/ghost|placeholder|data:image|profile-display/i.test(img.src)) {
          return img.src;
        }
      }
    }
    return null;
  }

  function extractCompanyFromJsonLd() {
    for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const parsed = JSON.parse(script.textContent || "");
        const items = Array.isArray(parsed) ? parsed : [parsed];
        for (const item of items) {
          if (!item) continue;
          const org = item.hiringOrganization || item.employer;
          const name =
            (typeof org === "string" ? org : org?.name) ||
            item.organization?.name ||
            null;
          const cleaned = cleanDisplayName(name);
          if (cleaned) return cleaned;
        }
      } catch (_) {
        /* ignore */
      }
    }
    return null;
  }

  function extractCompanyFromPageMeta() {
    const sources = [
      document.querySelector('meta[property="og:title"]')?.content,
      document.title,
    ].filter(Boolean);
    for (const raw of sources) {
      const bit = String(raw).split("|")[0].trim();
      if (typeof RV.parseLinkedInStyleTitle !== "function") continue;
      const parsed = RV.parseLinkedInStyleTitle(bit, null, null);
      if (parsed.company) return parsed.company;
    }
    return null;
  }

  function pageTitleForParse() {
    return (
      document.querySelector('meta[property="og:title"]')?.content?.split("|")[0]?.trim() ||
      document.title?.split("|")[0]?.trim() ||
      null
    );
  }

  function resolvedCompanyForInputs(ctx, inputs) {
    const parse = RV.parseLinkedInStyleTitle;
    const parsed =
      typeof parse === "function"
        ? parse(inputs?.title, inputs?.company || ctx?.displayName, inputs?.job_location)
        : {};
    return parsed.company || inputs?.company || ctx?.displayName || null;
  }

  async function gatherJobInputs(ctx) {
    const jd_text = await captureJobDescription();
    const probe = probeJdOnPage();
    const panel = findActiveJobPanel();
    const domCompany =
      extractCompanyNameFromDom(false, panel) || extractCompanyNameFromDom(false, null);
    const jsonLdCompany = extractCompanyFromJsonLd();
    const metaCompany = extractCompanyFromPageMeta();
    const rawTitle = extractJobTitle() || pageTitleForParse();
    const job_location = extractJobLocation();
    let company = domCompany || jsonLdCompany || metaCompany || ctx.displayName || null;
    let title = rawTitle;
    let location = job_location;
    if (typeof RV.parseLinkedInStyleTitle === "function") {
      const parsed = RV.parseLinkedInStyleTitle(rawTitle, company, job_location);
      company = parsed.company || company;
      title = parsed.title || title;
      location = parsed.jobLocation || location;
    }
    return {
      company,
      title,
      job_location: location,
      jd_text,
      job_url: window.location.href,
      captureProbe: probe,
      company_logo_url: extractCompanyLogoUrl(),
    };
  }

  async function analyzeAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    try {
      const store = chrome.storage?.local;
      if (!store?.get) return headers;
      const data = await new Promise((resolve) => store.get(["joblens_token"], resolve));
      if (data?.joblens_token) headers.Authorization = `Bearer ${data.joblens_token}`;
    } catch (_) {
      /* ignore */
    }
    return headers;
  }

  async function extensionApiJson(path, init = {}) {
    const rt = extensionRuntime();
    if (rt?.sendMessage && !extensionBroken) {
      const viaBackground = await new Promise((resolve) => {
        try {
          rt.sendMessage(
            {
              type: "JOBLENS_API",
              path,
              method: init.method || "GET",
              body: init.body,
            },
            (resp) => {
              const err = rt.lastError;
              if (err) {
                resolve({ ok: false, error: err.message });
                return;
              }
              resolve(resp || { ok: false, error: "no response" });
            }
          );
        } catch (e) {
          resolve({ ok: false, error: e.message || String(e) });
        }
      });

      if (viaBackground?.ok) return viaBackground.data;

      const contextDead =
        viaBackground?.error && isExtensionContextError({ message: viaBackground.error });
      if (contextDead) markExtensionStale();

      if (viaBackground?.error && !contextDead) {
        if (viaBackground.status) {
          throw new Error(
            `Backend responded ${viaBackground.status}${viaBackground.error ? ` — ${viaBackground.error}` : ""}`
          );
        }
        throw new TypeError(viaBackground.error);
      }
    }

    const resp = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      headers: { ...(await analyzeAuthHeaders()), ...(init.headers || {}) },
    });
    const text = await resp.text();
    if (!resp.ok) {
      throw new Error(
        text.trim().length > 200 ? `Backend responded ${resp.status}` : text.trim() || `HTTP ${resp.status}`
      );
    }
    try {
      return JSON.parse(text);
    } catch (_) {
      return text;
    }
  }

  async function runUnifiedAnalyze(inputs, onProgress) {
    const body = AC.buildAnalyzeBody(inputs);
    return AC.runAnalyzeAsync(BACKEND_URL, body, {
      fetchJson: extensionApiJson,
      onProgress,
    });
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
    return `<p class="lca-err-mini">Couldn't read job description${probeBit}. Wait a moment and Retry.</p>`;
  }

  function shortJdError(chars, jd) {
    if (typeof chars === "number" && chars < 40) {
      return "Job description not loaded yet — wait a moment, then Retry.";
    }
    const reason = jd?.reason || "";
    if (!reason) return "Could not parse job requirements — Retry in a moment.";
    const r = reason.toLowerCase();
    if (r.includes("no job description")) return "No job text sent to server.";
    if (r.includes("llm not configured")) return "Server LLM not configured.";
    if (r.includes("parse failed")) return "Server parse failed — Retry.";
    if (r.includes("no requirements extracted")) {
      return "Could not read job requirements from this posting — Retry.";
    }
    if (r.includes("does not look like a job")) {
      return "Server rejected job text — Retry; if it persists, tell us the job URL.";
    }
    return reason.length > 72 ? `${reason.slice(0, 70)}…` : reason;
  }

  function reportRenderOptions(inputs, ctx) {
    const panel = findActiveJobPanel();
    const domCo =
      extractCompanyNameFromDom(false, panel) || extractCompanyNameFromDom(false, null);
    return {
      company: inputs?.company || domCo || ctx?.displayName || null,
      title: inputs?.title || null,
      jobLocation: inputs?.job_location || null,
      companyLogoUrl: inputs?.company_logo_url || extractCompanyLogoUrl() || null,
    };
  }

  function enrichReport(report, inputs) {
    const parse = RV.parseLinkedInStyleTitle;
    const parsed =
      typeof parse === "function"
        ? parse(
            inputs?.title || report.received?.title,
            inputs?.company || report.received?.company,
            inputs?.job_location || report.received?.job_location
          )
        : {};
    return {
      ...report,
      received: {
        ...(report.received || {}),
        title:
          parsed.title ||
          inputs?.title ||
          report.received?.title ||
          extractJobTitle() ||
          null,
        company:
          parsed.company ||
          inputs?.company ||
          report.received?.company ||
          extractCompanyNameFromDom(false, findActiveJobPanel()) ||
          extractCompanyNameFromDom(false, null) ||
          null,
        job_location:
          parsed.jobLocation ||
          inputs?.job_location ||
          report.received?.job_location ||
          extractJobLocation() ||
          null,
        company_logo_url:
          inputs?.company_logo_url || report.received?.company_logo_url || extractCompanyLogoUrl() || null,
      },
    };
  }

  function renderFitPendingBlock(message) {
    return `<div class="lca-section-card lca-section-card--fit lca-fit-pending">
      <div class="lca-section-label lca-section-label--pillar">Role fit</div>
      <div class="lca-loading-row"><span class="lca-spinner"></span> ${escapeHtml(message)}</div>
    </div>`;
  }

  function renderProgressiveReport(headH1bHtml, fitMessage) {
    const fitBlock = renderFitPendingBlock(fitMessage);
    const trimmed = String(headH1bHtml || "").trim();
    const inner = trimmed.replace(/^<div class="jl-report-results">/, "").replace(/<\/div>\s*$/, "");
    return `<div class="jl-report-results">${inner}${fitBlock}</div>`;
  }

  async function lookupSponsorshipQuick(inputs, ctx) {
    const company = resolvedCompanyForInputs(ctx, inputs);
    if (!company) {
      return { matched: false, reason: "no company name provided" };
    }
    try {
      return await extensionApiJson("/sponsorship/lookup", {
        method: "POST",
        body: JSON.stringify({
          company,
          title: inputs?.title || null,
          job_location: inputs?.job_location || null,
        }),
      });
    } catch (err) {
      return {
        matched: false,
        reason: `H-1B lookup failed: ${err?.message || "network error"}`,
      };
    }
  }

  function renderHeadAndH1b(inputs, ctx, sponsorship) {
    const enriched = enrichReport({ sponsorship, received: {} }, inputs);
    return RV.renderUnifiedReport(enriched, {
      sections: ["head", "h1b"],
      ...reportRenderOptions(inputs, ctx),
    });
  }

  function renderFullReport(report, captureProbe, inputs, ctx) {
    const chars = report.received?.jd_chars ?? 0;
    const jd = report.jd;

    if (!jd?.available && chars < 40) {
      return `<div class="lca-analyze-inner">${renderCaptureMeta(chars, captureProbe)}<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p></div>`;
    }

    const enriched = enrichReport(report, inputs);
    const errLine = !jd?.available ? `<p class="lca-err-mini">${escapeHtml(shortJdError(chars, jd))}</p>` : "";
    return `<div class="lca-analyze-inner lca-fadein">${errLine}${RV.renderUnifiedReport(enriched, reportRenderOptions(inputs, ctx))}</div>`;
  }

  function renderAnalysisErrorInline(err) {
    const msg = err?.message || String(err);
    const isAbort = /abort/i.test(msg);
    const isNetwork = err instanceof TypeError || /Failed to fetch/i.test(msg);
    const isStale = isExtensionContextError(err);
    const isServer = /Backend responded 5\d\d/i.test(msg);
    return `<div class="lca-analyze-inner lca-analyze-err">${
      isStale
        ? "JobLens was just reloaded in the background — <strong>refresh this LinkedIn tab (F5)</strong>, then click Retry."
        : isServer
        ? "Our analysis server hit an error (500) — this is on our side, not LinkedIn. Wait a minute and click <strong>Retry</strong>. If it keeps failing, tell us which job URL."
        : isAbort
        ? "Analysis timed out — the server may be busy. Click <strong>Retry</strong>."
        : isNetwork
        ? `Can't reach the analysis server. Check your network, then Retry.`
        : escapeHtml(msg)
    }</div>`;
  }

  let analysisSeq = 0;

  async function runFullAnalysis(out, ctx) {
    if (!out) return;
    const seq = ++analysisSeq;
    const stillCurrent = () => seq === analysisSeq;

    const fresh = extractPageContext();
    if (fresh.pageKey) ctx = fresh;
    if (!canRunFitAnalysis(ctx)) {
      showCompanyPageFitHint(out);
      return;
    }

    out.innerHTML = renderLoadingInline("Starting analysis…");

    try {
      let inputs = await gatherJobInputs(ctx);
      let jdWait = 0;
      while ((inputs.jd_text || "").length < 40 && jdWait < 10) {
        if (!stillCurrent()) return;
        out.innerHTML = renderLoadingInline("Loading job description…");
        await sleep(900);
        inputs = await gatherJobInputs(ctx);
        jdWait += 1;
      }

      if (!stillCurrent()) return;

      if ((inputs.jd_text || "").length < 40) {
        out.innerHTML = `<div class="lca-analyze-inner">${renderCaptureMeta(inputs.jd_text?.length || 0, inputs.captureProbe)}<p class="lca-err-mini">Job description not loaded yet — wait a moment, then click <strong>Retry</strong>.</p></div>`;
        out.dataset.analyzedFor = "";
        return;
      }

      out.innerHTML = renderLoadingInline("Checking visa sponsorship…");
      const sponsorship = await lookupSponsorshipQuick(inputs, ctx);
      if (!stillCurrent()) return;

      const headH1b = renderHeadAndH1b(inputs, ctx, sponsorship);
      let fitMessage = "Analyzing role & resume match… usually 30–60s";
      out.innerHTML = `<div class="lca-analyze-inner">${renderProgressiveReport(headH1b, fitMessage)}</div>`;

      const report = await runUnifiedAnalyze(inputs, (job) => {
        if (!stillCurrent()) return;
        fitMessage = job?.message || "Analyzing role & resume match… usually 30–60s";
        out.innerHTML = `<div class="lca-analyze-inner">${renderProgressiveReport(headH1b, fitMessage)}</div>`;
      });
      if (!stillCurrent()) return;

      window.__jobLensLastReport = report;
      console.debug("[JobLens] explain:", report.explain);
      out.innerHTML = renderFullReport(report, inputs.captureProbe, inputs, ctx);
      if (extensionStale) {
        out.innerHTML =
          `<p class="lca-err-mini">Extension was reloaded — refresh this tab (F5) before the next job.</p>` +
          out.innerHTML;
      }
      RV.wireMetricTips(document.getElementById(BADGE_ID));
    } catch (err) {
      if (!stillCurrent()) return;
      if (isExtensionContextError(err)) markExtensionStale();
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

    const el = renderPanelShell(await readAuthState());
    const out = el.querySelector(".lca-analyze-result");
    if (!canRunFitAnalysis(ctx)) {
      showCompanyPageFitHint(out);
      return;
    }
    await runFullAnalysis(out, ctx);
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

  try {
    chrome.storage?.onChanged?.addListener((changes, area) => {
      if (area !== "local" || (!changes.joblens_token && !changes.joblens_email)) return;
      refreshAuthBanner();
      // Web login synced token → re-analyze current job with user profile (no manual Retry).
      if (changes.joblens_token?.newValue && document.getElementById(BADGE_ID)) {
        lastFingerprint = null;
        run({ force: true });
      }
    });
  } catch (_) {
    /* ignore */
  }
  window.addEventListener("focus", () => refreshAuthBanner());

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
