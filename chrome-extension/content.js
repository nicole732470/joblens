(function () {
  const BADGE_ID = "lca-sponsor-checker-badge";
  const RABBIT_ICON = chrome.runtime.getURL("icons/rabbit.png");
  let lastPageKey = null;

  const CONFIDENCE_META = {
    high: {
      label: "Likely same legal employer in DOL data",
      badgeClass: "lca-found",
      emoji: "✅",
    },
    medium: {
      label: "Possible match — verify manually",
      badgeClass: "lca-caution",
      emoji: "⚠️",
    },
    low: {
      label: "Possible match — verify manually",
      badgeClass: "lca-caution",
      emoji: "⚠️",
    },
  };

  function sourceLabel(ctx) {
    if (ctx.source === "job page") {
      return `Detected from job posting · slug: <code>${escapeHtml(ctx.slug || "")}</code>`;
    }
    if (ctx.source === "company page") {
      return `Detected from company page · slug: <code>${escapeHtml(ctx.slug || "")}</code>`;
    }
    return "";
  }

  function industryLine(employer) {
    if (!employer.naics_sector && !employer.naics_code) return "";
    const parts = [];
    if (employer.naics_sector) parts.push(employer.naics_sector);
    if (employer.naics_code) parts.push(`NAICS ${employer.naics_code}`);
    return `<div class="lca-industry"><span class="lca-label">Industry</span> ${escapeHtml(parts.join(" · "))}</div>`;
  }

  function renderAlternatives(alternatives) {
    if (!alternatives?.length) return "";
    const items = alternatives
      .map(({ employer }) => {
        const loc = [employer.city, employer.state].filter(Boolean).join(", ");
        const industry = employer.naics_sector || "";
        const meta = [loc, industry, `${employer.lca_count} LCA`].filter(Boolean).join(" · ");
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

    const certifiedPct =
      employer.lca_count > 0
        ? Math.round((employer.certified_count / employer.lca_count) * 100)
        : 0;

    const jobsHtml = (employer.top_jobs || [])
      .slice(0, 3)
      .map((j) => {
        const wage = formatWage(j.wage_from);
        const level = j.level && !String(j.level).includes("/") ? ` · ${j.level}` : "";
        return `<li>${escapeHtml(j.title)}${level}${wage ? ` · ${wage}` : ""}</li>`;
      })
      .join("");

    const altNames =
      employer.names.length > 1
        ? `<div class="lca-muted">Also filed as: ${escapeHtml(employer.names.slice(1, 3).join("; "))}</div>`
        : "";

    const location = [employer.city, employer.state].filter(Boolean).join(", ");

    const linkedInLine = ctx.displayName
      ? `<div class="lca-compare"><span class="lca-label">LinkedIn</span> ${escapeHtml(ctx.displayName)}</div>`
      : "";

    const showAlternatives =
      confidence !== "high" && alternatives?.length ? renderAlternatives(alternatives) : "";

    el.className = `lca-badge ${meta.badgeClass}`;
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <img class="lca-mascot" src="${RABBIT_ICON}" alt="Bunny mascot" />
        <div>
          <div class="lca-title">${meta.emoji} Found in LCA database</div>
          <div class="lca-confidence lca-confidence-${confidence}">${meta.label}</div>
        </div>
      </div>
      <div class="lca-company">${escapeHtml(employer.name)}</div>
      ${linkedInLine}
      ${industryLine(employer)}
      ${altNames}
      <div class="lca-stats">
        <span>${employer.lca_count.toLocaleString()} LCA</span>
        <span>${employer.h1b_count.toLocaleString()} H-1B</span>
        <span>${certifiedPct}% Certified</span>
      </div>
      ${location ? `<div class="lca-meta">${escapeHtml(location)} · FEIN ${escapeHtml(employer.fein)}</div>` : `<div class="lca-meta">FEIN ${escapeHtml(employer.fein)}</div>`}
      ${jobsHtml ? `<ul class="lca-jobs">${jobsHtml}</ul>` : ""}
      ${renderNotes(notes)}
      ${renderWarnings(warnings)}
      ${showAlternatives}
      <div class="lca-foot">${sourceLabel(ctx)}</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
  }

  function renderMiss(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <img class="lca-mascot" src="${RABBIT_ICON}" alt="Bunny mascot" />
        <div>
          <div class="lca-title">❌ Not found in LCA database</div>
          <div class="lca-confidence">No confident match</div>
        </div>
      </div>
      <div class="lca-meta">
        ${ctx.displayName ? `<div class="lca-compare"><span class="lca-label">LinkedIn</span> ${escapeHtml(ctx.displayName)}</div>` : ""}
        ${ctx.slug ? `<div><span class="lca-label">Slug</span> <code>${escapeHtml(ctx.slug)}</code></div>` : "Could not detect company on this page yet."}
      </div>
      <ul class="lca-warnings">
        <li>May not sponsor H-1B, file under a different legal name, or use a parent company.</li>
        <li>No meaningful token overlap with DOL legal names on file.</li>
      </ul>
      <div class="lca-foot">Absence here is not proof of no sponsorship.</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
  }

  function renderLoading() {
    const el = ensureBadge();
    el.className = "lca-badge lca-loading";
    el.innerHTML = `
      <div class="lca-header">
        <img class="lca-mascot lca-mascot-bounce" src="${RABBIT_ICON}" alt="Bunny mascot" />
        <div class="lca-title">Checking LCA records…</div>
      </div>
    `;
  }

  function renderWaiting(ctx) {
    const el = ensureBadge();
    el.className = "lca-badge lca-waiting";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-header">
        <img class="lca-mascot" src="${RABBIT_ICON}" alt="Bunny mascot" />
        <div class="lca-title">Waiting for job details…</div>
      </div>
      <div class="lca-foot">Open a job posting to detect the employer.</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
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
          <img class="lca-mascot" src="${RABBIT_ICON}" alt="Bunny mascot" />
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
