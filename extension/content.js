(function () {
  const EXTENSION_VERSION = "2.3.1";
  const BADGE_ID = "lca-sponsor-checker-badge";
  const POSITION_KEY = "lca-badge-position";
  // Backend for the AI Job Intelligence analysis. Override for deployed envs.
  const BACKEND_URL = "http://localhost:8000";
  let lastPageKey = null;
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

  function renderFoot(ctx, parts) {
    const bits = (parts || []).filter(Boolean);
    bits.push(`v${EXTENSION_VERSION}`);
    return `<div class="lca-foot">${bits.map((p) => escapeHtml(p)).join(" · ")}</div>`;
  }

  function renderDisclaimer(text) {
    return renderFoot(null, [`Disclaimer: ${text}`]);
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
        pageKey: jobId
          ? `job:${jobId}:${slug || "unknown"}`
          : slug
            ? `job:unknown:${slug}`
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

  function renderChrome() {
    return `<div class="lca-chrome"><span class="lca-drag-handle" title="Drag to move">⋮⋮</span><span class="lca-brand">Job Check</span><button type="button" class="lca-close" aria-label="Close">×</button></div>`;
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
      if (!e.target.closest(".lca-chrome") || e.target.closest(".lca-close")) return;
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
    if (ctx) wireAnalyzeButton(el, ctx);
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

    const showAlternatives =
      confidence !== "high" && alternatives?.length ? renderAlternatives(alternatives) : "";

    el.className = `lca-badge lca-${meta.status}`;
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-hero lca-hero-${meta.status}">
          <span class="lca-status-dot lca-status-${meta.status === "found" ? "found" : "caution"}"></span>
          <div class="lca-hero-text">
            <div class="lca-title">${meta.title}</div>
            <div class="lca-company">${escapeHtml(employer.name)}</div>
          </div>
        </div>
        ${
          filings > 0
            ? `<div class="lca-stat-row"><span class="lca-stat"><b>${approvedPct}%</b> approved</span><span class="lca-stat">${filings.toLocaleString()} filings</span></div>`
            : ""
        }
        ${
          jobsHtml || location || showAlternatives
            ? `<details class="lca-details">
                 <summary>H-1B details</summary>
                 ${location ? `<div class="lca-meta">${escapeHtml(location)}</div>` : ""}
                 ${jobsHtml ? `<ul class="lca-jobs">${jobsHtml}</ul>` : ""}
                 ${renderNotes(notes)}
                 ${renderWarnings(warnings)}
                 ${showAlternatives}
               </details>`
            : `${renderNotes(notes)}${renderWarnings(warnings)}`
        }
        <div class="lca-action-row">
          <button type="button" class="lca-analyze-btn">Analyze fit</button>
        </div>
        <div class="lca-analyze-result" hidden></div>
        ${renderFoot(ctx, [footLinkedInHint(ctx, employer.name), "Source: U.S. DOL H-1B"])}
      </div>`;
    finishBadge(el, ctx);
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    const companyLine = ctx.displayName
      ? `<div class="lca-company">${escapeHtml(ctx.displayName)}</div>`
      : "";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-hero lca-hero-miss">
          <span class="lca-status-dot lca-status-miss"></span>
          <div class="lca-hero-text">
            <div class="lca-title">No H-1B record</div>
            ${companyLine}
          </div>
        </div>
        <div class="lca-action-row">
          <button type="button" class="lca-analyze-btn">Analyze fit</button>
        </div>
        <div class="lca-analyze-result" hidden></div>
        ${renderDisclaimer("employer may file under a different legal name")}
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
    ];
    for (const sel of selectors) {
      const text = document.querySelector(sel)?.textContent?.trim();
      if (text) return text.replace(/\s+/g, " ");
    }
    return null;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function findJobDetailsRoot() {
    const selectors = [
      ".jobs-search__job-details",
      ".jobs-search__right-rail",
      ".scaffold-layout__detail",
      ".jobs-details",
      "[class*='jobs-details__main-content']",
      "#job-details",
      ".jobs-description",
      "main",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return document.body;
  }

  function scrollJobPanelIntoView(root) {
    root.scrollIntoView({ block: "nearest", behavior: "instant" });
    const scrollables = root.querySelectorAll
      ? root.querySelectorAll("[class*='job-details'], [class*='jobs-description'], [class*='scaffold-layout']")
      : [];
    scrollables.forEach((el) => {
      if (el.scrollHeight > el.clientHeight + 8) {
        el.scrollTop = 0;
      }
    });
  }

  function simulateClick(el) {
    if (!(el instanceof HTMLElement)) return;
    el.click();
    el.dispatchEvent(
      new MouseEvent("click", { bubbles: true, cancelable: true, view: window })
    );
  }

  function clickShowMoreIn(root) {
    let clicked = false;
    const selectors = [
      ".jobs-description__footer-button",
      "[data-tracking-control-name='public_jobs_show-more-html-btn']",
      ".show-more-less-html__button--more",
      ".show-more-less-html__button",
      "button[aria-expanded='false']",
      "button[aria-label*='Show more' i]",
      "button[aria-label*='See more' i]",
      ".jobs-description__footer button",
      ".feed-shared-inline-show-more-text",
      ".jobs-description-content__text button",
    ];
    for (const sel of selectors) {
      root.querySelectorAll(sel).forEach((btn) => {
        simulateClick(btn);
        clicked = true;
      });
    }
    root.querySelectorAll("button, [role='button']").forEach((el) => {
      const label = (el.textContent || "").trim().toLowerCase();
      if (
        label === "show more" ||
        label === "see more" ||
        label === "show all" ||
        label.endsWith("…more") ||
        label.endsWith("...more")
      ) {
        simulateClick(el);
        clicked = true;
      }
    });
    root
      .querySelectorAll(
        ".jobs-description span, .jobs-description-content__text span, #job-details span, .show-more-less-html span"
      )
      .forEach((span) => {
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
    scrollJobPanelIntoView(root);
    for (let i = 0; i < 8; i++) {
      clickShowMoreIn(root);
      clickShowMoreIn(document);
      await sleep(160);
    }
    await sleep(300);
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

  function extractJobDescriptionFromDom() {
    const selectors = [
      ".show-more-less-html__markup",
      "#job-details",
      ".jobs-description__content",
      ".jobs-description-content__text",
      ".jobs-box__html-content",
      "article.jobs-description__container",
      ".core-section-container__content",
      ".description__text",
      ".jobs-description",
      "[class*='jobs-description']",
      "[id*='job-details']",
    ];
    let best = "";
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        const text = normalizeJdText(el.innerText);
        if (text.length > best.length) best = text;
      });
    }
    if (best.length > 40) return best;

    const root = findJobDetailsRoot();
    let largest = "";
    root.querySelectorAll("div, section, article").forEach((el) => {
      if (el.closest(`#${BADGE_ID}`)) return;
      const text = normalizeJdText(el.innerText);
      if (text.length > largest.length && text.length < 50000) largest = text;
    });
    return largest.length > best.length ? largest : best;
  }

  function extractJobDescription() {
    const dom = extractJobDescriptionFromDom();
    if (dom.length > 40) return dom;
    const jsonLd = extractJobDescriptionFromJsonLd();
    return jsonLd.length > dom.length ? jsonLd : dom;
  }

  async function captureJobDescription() {
    let best = "";
    for (let attempt = 0; attempt < 16; attempt++) {
      await expandJobDescription();
      const text = extractJobDescription();
      if (text.length > best.length) best = text;
      if (best.length > 120) break;
      await sleep(220);
    }
    return best;
  }

  async function gatherJobInputs(ctx) {
    const jd_text = await captureJobDescription();
    return {
      company: ctx.displayName || null,
      title: extractJobTitle(),
      jd_text,
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

  function stripClaimPrefix(claim) {
    return String(claim || "").replace(/^\[(strong|partial|weak|missing)\]\s*/i, "");
  }

  function renderBulletedList(items, extraClass, limit = 8) {
    if (!items?.length) return "";
    const slice = items.slice(0, limit);
    const more = items.length > limit ? `<li class="lca-list-more">+${items.length - limit} more</li>` : "";
    return `<ul class="lca-list ${extraClass || ""}">${slice
      .map((c) => `<li>${escapeHtml(stripClaimPrefix(c.claim))}</li>`)
      .join("")}${more}</ul>`;
  }

  function renderPanel(label, body) {
    if (!body) return "";
    return `<div class="lca-panel"><div class="lca-panel-label">${escapeHtml(label)}</div>${body}</div>`;
  }

  function renderResumeFitSection(rf) {
    if (!rf?.available) {
      const reason = rf?.reason || "";
      return reason ? renderPanel("Resume", `<div class="lca-panel-empty">${escapeHtml(reason)}</div>`) : "";
    }
    const fit = partitionResumeFit(rf);
    const matches = [...fit.strong, ...fit.partial];
    const parts = [];
    if (matches.length) {
      parts.push(renderPanel("Matches", renderBulletedList(matches)));
    }
    if (fit.gaps.length) {
      parts.push(renderPanel("Gaps", renderBulletedList(fit.gaps, "lca-list-gap")));
    }
    if (!matches.length && !fit.gaps.length) {
      parts.push(renderPanel("Resume", `<div class="lca-panel-empty">No hard skill requirements to score.</div>`));
    }
    return parts.join("");
  }

  const VERDICT_LABELS = {
    Apply: { text: "Apply", dot: "found" },
    "Apply with modifications": { text: "Consider", dot: "caution" },
    "Low priority": { text: "Later", dot: "caution" },
    Skip: { text: "Skip", dot: "miss" },
  };

  function renderVerdictSection(rec) {
    if (!rec?.available) {
      const reason = rec?.reason || "";
      return reason ? renderPanel("Fit", `<div class="lca-panel-empty">${escapeHtml(reason)}</div>`) : "";
    }
    const meta = VERDICT_LABELS[rec.decision] || { text: rec.decision || "?", dot: "caution" };
    const track =
      rec.track_label && rec.track_priority != null
        ? `${rec.track_label} · P${rec.track_priority}`
        : rec.track_label || "";
    return `
      <div class="lca-panel lca-panel-top">
        <div class="lca-hero">
          <span class="lca-status-dot lca-status-${meta.dot}"></span>
          <div class="lca-hero-text">
            <div class="lca-title">${escapeHtml(meta.text)}</div>
            ${track ? `<div class="lca-company">${escapeHtml(track)}</div>` : ""}
          </div>
        </div>
      </div>`;
  }

  function renderRiskSection(risk) {
    if (!risk?.available || !risk.risks?.length) return "";
    return renderPanel("Risk", renderBulletedList(risk.risks.map((r) => ({ claim: r.claim })), "lca-list-warn", 4));
  }

  function renderJdErrorOnly(jd, received) {
    if (jd?.available) return "";
    const reason = jd?.reason || "";
    const chars = received?.jd_chars;
    const captureHint =
      typeof chars === "number" && chars < 40
        ? `Captured ${chars} chars from page — wait for JD to load, then retry.`
        : "";
    if (!reason && !captureHint) return "";
    return `<div class="lca-block lca-block-muted">${captureHint ? `<div>${escapeHtml(captureHint)}</div>` : ""}${reason ? `<div>${escapeHtml(friendlyParseReason(reason))}</div>` : ""}</div>`;
  }

  function renderAnalysisInline(report) {
    return `<div class="lca-analyze-inner">${renderVerdictSection(report.recommendation)}${renderResumeFitSection(report.resume_fit)}${renderRiskSection(report.risk)}${renderJdErrorOnly(report.jd, report.received)}</div>`;
  }

  function friendlyParseReason(reason) {
    const r = String(reason || "").toLowerCase();
    if (!reason) return "Could not parse this job posting.";
    if (r.includes("no job description")) {
      return "Couldn't read the job description from this page. Make sure a job is selected in the right panel (not just the job list), wait for it to load, then Analyze again.";
    }
    if (r.includes("llm not configured")) {
      return "Backend LLM not configured — set LLM_API_KEY in .env and restart docker.";
    }
    if (r.includes("no json") || r.includes("parse failed")) {
      return "AI parser failed (free model timeout or bad response). Click Analyze again — often works on retry.";
    }
    return reason;
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
        btn.textContent = "Hide fit";
      } else {
        out.setAttribute("hidden", "");
        btn.textContent = "Analyze fit";
      }
      return;
    }

    out.removeAttribute("hidden");
    out.innerHTML = `<div class="lca-loading-row"><span class="lca-spinner"></span> Analyzing…</div>`;
    btn.disabled = true;
    try {
      const inputs = await gatherJobInputs(ctx);
      console.info("[Job Intelligence] captured JD chars:", inputs.jd_text?.length || 0);
      const report = await analyzeWithBackend(inputs);
      out.innerHTML = renderAnalysisInline(report);
      const jdChars = report.received?.jd_chars ?? inputs.jd_text?.length ?? 0;
      if (jdChars >= 40 && report.jd?.available) {
        out.dataset.loaded = "1";
        btn.textContent = "Hide fit";
      } else {
        btn.textContent = "Retry";
      }
    } catch (err) {
      console.error("[Job Intelligence]", err);
      out.innerHTML = renderAnalysisErrorInline(err);
    } finally {
      btn.disabled = false;
    }
  }

  async function run() {
    if (extensionBroken) return;
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
      const hint =
        /extension disconnected|extension was updated|getURL/i.test(String(err.message))
          ? `<div class="lca-hint">${escapeHtml(err.message)}</div>`
          : `<div class="lca-foot">${escapeHtml(err.message)}</div>`;
      el.innerHTML = `
        ${renderChrome()}
        <div class="lca-body">
          <div class="lca-title">H-1B lookup failed</div>
          ${hint}
          <button type="button" class="lca-analyze-btn">Analyze job</button>
          <div class="lca-analyze-result" hidden></div>
        </div>`;
      finishBadge(el, ctx);
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
