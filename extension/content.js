(function () {
  const BADGE_ID = "lca-sponsor-checker-badge";
  const POSITION_KEY = "lca-badge-position";
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
    const chrome = el.querySelector(".lca-chrome");
    if (!chrome) return;
    el.dataset.dragWired = "1";

    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    const onMove = (e) => {
      if (!dragging) return;
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const x = Math.max(8, Math.min(window.innerWidth - w - 8, e.clientX - offsetX));
      const y = Math.max(8, Math.min(window.innerHeight - h - 8, e.clientY - offsetY));
      el.style.left = `${x}px`;
      el.style.top = `${y}px`;
      el.style.right = "auto";
    };

    const onUp = () => {
      if (!dragging) return;
      dragging = false;
      el.classList.remove("lca-dragging");
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      const rect = el.getBoundingClientRect();
      localStorage.setItem(POSITION_KEY, JSON.stringify({ x: rect.left, y: rect.top }));
    };

    chrome.addEventListener("mousedown", (e) => {
      if (e.target.closest(".lca-close")) return;
      e.preventDefault();
      dragging = true;
      el.classList.add("lca-dragging");
      const rect = el.getBoundingClientRect();
      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;
      el.style.right = "auto";
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
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

    const linkedInLine =
      ctx.displayName && ctx.displayName.toLowerCase() !== (employer.name || "").toLowerCase()
        ? `<div class="lca-compare">LinkedIn shows <b>${escapeHtml(ctx.displayName)}</b></div>`
        : "";

    const showAlternatives =
      confidence !== "high" && alternatives?.length ? renderAlternatives(alternatives) : "";

    el.className = `lca-badge lca-${meta.status}`;
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-row">
          <span class="lca-status-dot lca-status-${meta.status === "found" ? "found" : "caution"}"></span>
          <div>
            <div class="lca-title">${meta.title}</div>
            <div class="lca-sub">${escapeHtml(employer.name)}${meta.sub ? ` · ${meta.sub}` : ""}</div>
          </div>
        </div>
        ${linkedInLine}
        ${
          filings > 0
            ? `<div class="lca-sponsor-summary"><b>${approvedPct}%</b> visa approvals · ${filings.toLocaleString()} filings</div>`
            : ""
        }
        ${
          jobsHtml || location || showAlternatives
            ? `<details class="lca-details">
                 <summary>More H-1B details</summary>
                 ${location ? `<div class="lca-meta">${escapeHtml(location)}</div>` : ""}
                 ${jobsHtml ? `<div class="lca-jobs-label">Top sponsored roles</div><ul class="lca-jobs">${jobsHtml}</ul>` : ""}
                 ${renderNotes(notes)}
                 ${renderWarnings(warnings)}
                 ${showAlternatives}
               </details>`
            : `${renderNotes(notes)}${renderWarnings(warnings)}`
        }
        <button type="button" class="lca-analyze-btn">Analyze job</button>
        <div class="lca-analyze-result" hidden></div>
        <div class="lca-foot">${sourceLabel(ctx)} · U.S. DOL H-1B data</div>
      </div>`;
    finishBadge(el, ctx);
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      ${renderChrome()}
      <div class="lca-body">
        <div class="lca-row">
          <span class="lca-status-dot lca-status-miss"></span>
          <div>
            <div class="lca-title">No H-1B record</div>
            <div class="lca-sub">Not in U.S. visa sponsorship data</div>
          </div>
        </div>
        ${
          ctx.displayName
            ? `<div class="lca-compare">LinkedIn: <b>${escapeHtml(ctx.displayName)}</b></div>`
            : `<div class="lca-hint">Couldn't detect the company on this page yet.</div>`
        }
        <div class="lca-hint">May file under another legal name — not proof they don't sponsor.</div>
        <button type="button" class="lca-analyze-btn">Analyze job</button>
        <div class="lca-analyze-result" hidden></div>
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

  function renderFitList(items, cssClass, emptyLabel) {
    if (!items?.length) {
      return emptyLabel ? `<div class="lca-hint">${escapeHtml(emptyLabel)}</div>` : "";
    }
    return `<ul class="lca-fit-list">${items
      .slice(0, 8)
      .map(
        (c) =>
          `<li class="${cssClass}"><span class="lca-fit-dot"></span>${escapeHtml(stripClaimPrefix(c.claim))}</li>`
      )
      .join("")}${items.length > 8 ? `<li class="lca-hint">+${items.length - 8} more</li>` : ""}</ul>`;
  }

  function renderResumeFitSection(rf) {
    if (!rf?.available) {
      const reason = rf?.reason || "";
      return reason
        ? `<div class="lca-section"><div class="lca-label">Resume match</div><div class="lca-hint">${escapeHtml(reason)}</div></div>`
        : "";
    }
    const strong = rf.strong_matches?.length || 0;
    const partial = rf.partial_matches?.length || 0;
    const missing = rf.missing?.length || 0;
    const summary = `${strong} strong · ${partial} partial · ${missing} gap${missing === 1 ? "" : "s"}`;
    return `
      <div class="lca-section">
        <div class="lca-label">Resume match</div>
        <div class="lca-hint">${escapeHtml(summary)}</div>
        ${renderFitList(rf.strong_matches, "lca-fit-strong", "")}
        ${renderFitList(rf.partial_matches, "lca-fit-partial", "")}
        ${missing ? `<div class="lca-label" style="margin-top:6px">Gaps</div>${renderFitList(rf.missing, "lca-fit-missing", "")}` : ""}
      </div>`;
  }

  const RECOMMENDATION_LABELS = {
    Apply: { text: "Apply", cls: "lca-rec-apply" },
    "Apply with modifications": { text: "Apply (tweak resume)", cls: "lca-rec-modify" },
    "Low priority": { text: "Low priority", cls: "lca-rec-low" },
    Skip: { text: "Skip", cls: "lca-rec-skip" },
  };

  function renderRecommendationSection(rec) {
    if (!rec?.available) {
      const reason = rec?.reason || "";
      return reason
        ? `<div class="lca-section"><div class="lca-label">Recommendation</div><div class="lca-hint">${escapeHtml(reason)}</div></div>`
        : "";
    }
    const meta = RECOMMENDATION_LABELS[rec.decision] || {
      text: rec.decision || "Unknown",
      cls: "lca-rec-low",
    };
    return `
      <div class="lca-section">
        <div class="lca-label">Recommendation</div>
        <div class="lca-rec ${meta.cls}">${escapeHtml(meta.text)}</div>
        ${
          rec.track_priority != null
            ? `<div class="lca-hint">Track: ${escapeHtml(rec.track_label || rec.track_id || "")} · priority ${rec.track_priority}${
                rec.track_similarity != null ? ` · ${Math.round(rec.track_similarity * 100)}% title match` : ""
              }${rec.fit_ratio != null ? ` · ${Math.round(rec.fit_ratio * 100)}% resume fit` : ""}</div>`
            : ""
        }
        ${rec.reasoning ? `<div class="lca-hint">${escapeHtml(rec.reasoning)}</div>` : ""}
      </div>`;
  }

  function renderRiskSection(risk) {
    if (!risk?.available || !risk.risks?.length) return "";
    const items = risk.risks
      .slice(0, 4)
      .map((r) => `<li>${escapeHtml(r.claim)}</li>`)
      .join("");
    return `
      <div class="lca-section">
        <div class="lca-label">Risk signals</div>
        <ul class="lca-notes lca-risk-list">${items}</ul>
      </div>`;
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

  function renderJdSection(jd, received) {
    if (!jd || !jd.available) {
      const reason = jd?.reason || "";
      const chars = received?.jd_chars;
      const captureHint =
        typeof chars === "number" && chars < 40
          ? `<div class="lca-hint">Page capture: ${chars} characters — LinkedIn may not have loaded the job text yet. Wait a second, then click Analyze again.</div>`
          : "";
      return reason || captureHint
        ? `<div class="lca-section"><div class="lca-label">Job parsing failed</div>${captureHint}<div class="lca-hint">${escapeHtml(friendlyParseReason(reason))}</div></div>`
        : captureHint;
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
      <div class="lca-section">
        <div class="lca-label">Job requirements</div>
        ${meta ? `<div class="lca-hint">${escapeHtml(meta)}</div>` : ""}
        ${reqs ? `<ul class="lca-reqs">${reqs}</ul>` : `<div class="lca-hint">No explicit requirements extracted.</div>`}
        ${visa ? `<div class="lca-label" style="margin-top:6px">Visa language</div><ul class="lca-notes">${visa}</ul>` : ""}
      </div>`;
  }

  function renderAnalysisInline(report) {
    const pending = report.pending || [];
    const labels = {
      jd_parsing: "Job description parsing",
      resume_fit: "Resume matching",
      recommendation: "Apply recommendation",
    };
    const pendingHtml = pending.length
      ? `<div class="lca-section"><div class="lca-label">Still processing</div><ul class="lca-notes">${pending.map((p) => `<li>${escapeHtml(labels[p] || p)}</li>`).join("")}</ul></div>`
      : "";
    return `
      <div class="lca-analyze-inner">
        ${renderRecommendationSection(report.recommendation)}
        ${renderResumeFitSection(report.resume_fit)}
        ${renderRiskSection(report.risk)}
        ${renderJdSection(report.jd, report.received)}
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
        btn.textContent = "Hide analysis";
      } else {
        out.setAttribute("hidden", "");
        btn.textContent = "Analyze job";
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
        btn.textContent = "Hide analysis";
      } else {
        btn.textContent = "Retry analyze";
      }
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
        ${renderChrome()}
        <div class="lca-body">
          <div class="lca-title">Lookup failed</div>
          <div class="lca-foot">${escapeHtml(err.message)}</div>
        </div>`;
      finishBadge(el, null);
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
