(function () {
  const BADGE_ID = "lca-sponsor-checker-badge";
  let lastSlug = null;

  function extractSlug() {
    const m = window.location.pathname.match(/^\/company\/([^/?#]+)/i);
    return m ? decodeURIComponent(m[1]).toLowerCase() : null;
  }

  function extractH1Name() {
    const selectors = [
      "h1.org-top-card-summary__title",
      "h1[data-anonymize='company-name']",
      ".org-top-card-summary-info-list__title h1",
      "main h1",
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el?.textContent?.trim()) return el.textContent.trim();
    }
    return null;
  }

  function formatWage(w) {
    if (!w) return "";
    const n = Number(String(w).replace(/,/g, ""));
    if (Number.isNaN(n) || n <= 0) return "";
    return `$${Math.round(n).toLocaleString()}`;
  }

  function renderBadge(employer, slug, h1) {
    let el = document.getElementById(BADGE_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = BADGE_ID;
      document.body.appendChild(el);
    }

    const certifiedPct =
      employer.lca_count > 0
        ? Math.round((employer.certified_count / employer.lca_count) * 100)
        : 0;

    const jobsHtml = (employer.top_jobs || [])
      .slice(0, 3)
      .map((j) => {
        const wage = formatWage(j.wage_from);
        const level = j.level && !String(j.level).includes("/") ? ` · ${j.level}` : "";
        return `<li>${j.title}${level}${wage ? ` · ${wage}` : ""}</li>`;
      })
      .join("");

    const altNames =
      employer.names.length > 1
        ? `<div class="lca-muted">Also: ${employer.names.slice(1, 3).join("; ")}</div>`
        : "";

    el.className = "lca-badge lca-found";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-title">✅ LCA 数据库命中</div>
      <div class="lca-company">${employer.name}</div>
      ${altNames}
      <div class="lca-stats">
        <span>${employer.lca_count.toLocaleString()} LCA</span>
        <span>${employer.h1b_count.toLocaleString()} H-1B</span>
        <span>${certifiedPct}% Certified</span>
      </div>
      <div class="lca-meta">${employer.city || ""}${employer.city && employer.state ? ", " : ""}${employer.state || ""}</div>
      ${jobsHtml ? `<ul class="lca-jobs">${jobsHtml}</ul>` : ""}
      <div class="lca-foot">slug: ${slug}${h1 ? ` · page: ${h1}` : ""}</div>
    `;

    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
  }

  function renderMiss(slug, h1) {
    let el = document.getElementById(BADGE_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = BADGE_ID;
      document.body.appendChild(el);
    }
    el.className = "lca-badge lca-miss";
    el.innerHTML = `
      <button class="lca-close" aria-label="Close">×</button>
      <div class="lca-title">❌ 未在 LCA 数据库中找到</div>
      <div class="lca-meta">slug: <code>${slug}</code>${h1 ? `<br>page: ${h1}` : ""}</div>
      <div class="lca-foot">可能未 sponsor H-1B，或公司法定名与 LinkedIn 不一致</div>
    `;
    el.querySelector(".lca-close").addEventListener("click", () => el.remove());
  }

  async function run() {
    const slug = extractSlug();
    if (!slug || slug === lastSlug) return;
    lastSlug = slug;

    try {
      await LcaMatcher.load();
      const h1 = extractH1Name();
      const hit = LcaMatcher.lookup(slug, h1);
      if (hit) renderBadge(hit, slug, h1);
      else renderMiss(slug, h1);
    } catch (err) {
      console.error("[LCA Sponsor Checker]", err);
    }
  }

  run();

  // LinkedIn is SPA — re-check on navigation
  const obs = new MutationObserver(() => {
    const slug = extractSlug();
    if (slug && slug !== lastSlug) run();
  });
  obs.observe(document.body, { childList: true, subtree: true });

  window.addEventListener("popstate", () => {
    lastSlug = null;
    run();
  });
})();
