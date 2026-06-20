/**
 * JobLens report UI — single source of truth for extension + web.
 * Same /analyze JSON → same HTML. Sync: ./scripts/sync-shared-ui.sh
 */

const SOFT_REQUIREMENT_RE =
  /\b(leadership|lead\b|collaborat|cross[- ]?functional|teamwork|communicat|stakeholder|mentor|passion|fast[- ]?paced|self[- ]?starter|culture|interpersonal|organiz|detail[- ]?oriented|problem[- ]?solving|work across| agile|ownership|motivated|dynamic|ambitious|innovative mindset|people skills|verbal and written)\b/i;

const VERDICT_LABELS = {
  Apply: { text: "Apply", tone: "apply" },
  "Near apply": { text: "Near apply", tone: "near-apply" },
  Consider: { text: "Consider", tone: "consider" },
  Skip: { text: "Skip", tone: "skip" },
  "Apply with modifications": { text: "Consider", tone: "consider" },
  "Low priority": { text: "Consider", tone: "consider" },
};

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatWage(w) {
  if (!w) return "";
  const n = Number(String(w).replace(/,/g, ""));
  if (Number.isNaN(n) || n <= 0) return "";
  return `$${Math.round(n).toLocaleString()}`;
}

function stripClaimPrefix(claim) {
  return String(claim || "").replace(/^\[(strong|partial|weak|missing)\]\s*/i, "");
}

function isSoftRequirement(claim) {
  return SOFT_REQUIREMENT_RE.test(stripClaimPrefix(claim?.claim || claim || ""));
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

function resolveFitRatio(rec, rf) {
  if (rec?.fit_ratio != null) return rec.fit_ratio;
  if (!rf?.available) return null;
  const buckets = hardRequirementFit(rf);
  if (!buckets) return null;
  const strong = buckets.strong.length;
  const partial = buckets.partial.length;
  const weak = buckets.weak.length;
  const gaps = buckets.gaps.length;
  const denom = strong + partial + weak + gaps;
  if (!denom) return null;
  return (strong + partial * 0.5 + weak * 0.25) / denom;
}

function buildVerdictNote(rec) {
  if (!rec?.available) return "";
  const summary = (rec.summary || "").trim();
  if (summary && summary.toLowerCase() !== "not a strong fit") return summary;
  if (rec.track_label) {
    const pri = rec.track_priority != null ? ` · P${rec.track_priority}` : "";
    return `${rec.track_label}${pri}`;
  }
  if (rec.reasoning) {
    const first = rec.reasoning.split(/(?<=[.!?])\s+/)[0];
    if (first && first.length > 10) return first.slice(0, 120);
  }
  return "";
}

function titlesRoughlyMatch(a, b) {
  const strip = (t) =>
    String(t || "")
      .toLowerCase()
      .replace(/\([^)]*\)/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  const na = strip(a);
  const nb = strip(b);
  if (!na || !nb) return false;
  if (na === nb) return true;
  if (na.length >= 12 && nb.length >= 12 && (na.includes(nb) || nb.includes(na))) return true;
  return false;
}

function statusPill(text, tone) {
  return `<span class="lca-pill lca-pill-${tone}">${escapeHtml(text)}</span>`;
}

function renderMetricTip(title, rows) {
  if (!rows?.length) return "";
  const body = rows
    .map(
      (r) =>
        `<div class="lca-tip-row"><span class="lca-tip-k">${escapeHtml(r.k)}</span><span class="lca-tip-v">${escapeHtml(r.v)}</span></div>`
    )
    .join("");
  return `<div class="lca-metric-tip" role="tooltip"><div class="lca-tip-title">${escapeHtml(title)}</div>${body}</div>`;
}

function renderMetricGrid(cells) {
  if (!cells.length) return "";
  const cols = cells.length > 4 ? 3 : Math.min(cells.length, 3);
  return `<div class="lca-metrics" style="grid-template-columns:repeat(${cols},1fr)">${cells
    .map((c) => {
      const tip = c.tip ? renderMetricTip(c.tipTitle || c.lbl, c.tip) : "";
      return `<div class="lca-metric${tip ? " lca-has-tip" : ""}" tabindex="0">${tip}<span class="lca-metric-val">${escapeHtml(c.val)}</span><span class="lca-metric-lbl">${escapeHtml(c.lbl)}</span></div>`;
    })
    .join("")}</div>`;
}

function buildMetricCells(rec, co, explain, rf) {
  const cells = [];
  const roleTip = [
    { k: "Track", v: rec.track_label || "—" },
    { k: "Priority", v: rec.track_priority != null ? `P${rec.track_priority}` : "—" },
  ];
  if (rec.track_similarity != null) {
    roleTip.push({ k: "Title match", v: `${Math.round(rec.track_similarity * 100)}%` });
  }
  if (explain?.role?.adjustments?.length) {
    roleTip.push({ k: "Adjustments", v: explain.role.adjustments.join("; ") });
  }
  cells.push({
    val: rec.track_priority != null ? `P${rec.track_priority}` : "—",
    lbl: "Role",
    tipTitle: "Role fit",
    tip: roleTip,
  });

  const fitRatio = resolveFitRatio(rec, rf);
  if (fitRatio != null) {
    const buckets = rf?.available ? hardRequirementFit(rf) : null;
    const strong = buckets?.strong.length ?? 0;
    const partial = buckets?.partial.length ?? 0;
    const weak = buckets?.weak.length ?? 0;
    const gaps = buckets?.gaps.length ?? 0;
    const resumeTip = [
      { k: "Fit", v: `${Math.round(fitRatio * 100)}%` },
      {
        k: "Method",
        v: rf?.match_method === "llm" ? "LLM + RAG" : rf?.match_method === "vector" ? "Vector" : "—",
      },
      { k: "Counts", v: `S${strong} · P${partial}${weak ? ` · W${weak}` : ""} · G${gaps}` },
    ];
    cells.push({
      val: `${Math.round(fitRatio * 100)}%`,
      lbl: "Resume",
      tipTitle: "Resume vs JD",
      tip: resumeTip,
    });
  }

  cells.push({
    val: rec.location_tier != null ? `P${rec.location_tier}` : "—",
    lbl: "Location",
    tipTitle: "Location",
    tip: [{ k: "Tier", v: rec.location_label || "—" }],
  });

  if (co?.company_tier != null) {
    const bd = explain?.company?.breakdown || co.score_breakdown || {};
    const coTip = [{ k: "Tier", v: co.company_label || `P${co.company_tier}` }];
    if (bd.reason === "dealbreaker") {
      coTip.push({ k: "Reason", v: bd.hit || co.dealbreaker_hits?.[0] || "dealbreaker" });
    } else if (bd.combined != null) {
      coTip.push({ k: "Score", v: `${Math.round(bd.combined * 100)}%` });
      if (bd.preference != null) coTip.push({ k: "Preferences", v: `${Math.round(bd.preference * 100)}%` });
      if (bd.industry != null) coTip.push({ k: "Industry", v: `${Math.round(bd.industry * 100)}%` });
      coTip.push({ k: "Bands", v: "≥52% P1 · ≥38% P2 · else P3" });
    }
    cells.push({
      val: `P${co.company_tier}`,
      lbl: "Company",
      tipTitle: "Company fit",
      tip: coTip,
    });
  }

  const pref = rec.preferences_matched ?? 0;
  const prefHits = rec.preference_hits?.length ? rec.preference_hits : explain?.company?.preference_hits || [];
  const prefTip = [{ k: "Matched", v: `${pref} / ${rec.preferences_total ?? 0}` }];
  if (prefHits.length) {
    prefHits.slice(0, 4).forEach((h, i) => prefTip.push({ k: `Hit ${i + 1}`, v: h }));
  } else {
    prefTip.push({ k: "Note", v: "No preference phrases matched in JD" });
  }
  cells.push({ val: String(pref), lbl: "Preferences", tipTitle: "Preferences", tip: prefTip });

  const deal = rec.dealbreakers_matched ?? 0;
  const flagHits = rec.dealbreaker_hits?.length ? rec.dealbreaker_hits : explain?.flags?.hits || [];
  const flagTip = [{ k: "Matched", v: `${deal} / ${rec.dealbreakers_total ?? 0}` }];
  if (flagHits.length) {
    flagHits.slice(0, 4).forEach((h, i) => flagTip.push({ k: `Flag ${i + 1}`, v: h }));
  } else {
    flagTip.push({ k: "Note", v: "No dealbreakers matched" });
  }
  cells.push({ val: String(deal), lbl: "Dealbreakers", tipTitle: "Dealbreakers", tip: flagTip });

  return cells;
}

function renderMetricsGrid(rec, co, explain, rf) {
  return renderMetricGrid(buildMetricCells(rec, co, explain, rf));
}

function renderCompanySignals(co) {
  if (!co?.available) return "";
  const rows = [];
  if (co.linkedin_followers != null) {
    rows.push({ label: "Followers", value: co.linkedin_followers.toLocaleString() });
  }
  for (const s of co.alumni_hits || []) {
    rows.push({ label: "Alumni", value: `${s} on LinkedIn` });
  }
  if (co.industry_label) {
    rows.push({ label: "Industry", value: co.industry_label });
  }
  for (const p of (co.preference_hits || []).slice(0, 2)) {
    rows.push({ label: "Preference", value: p });
  }
  if (!rows.length) return "";
  return `<div class="lca-signal-lines">${rows
    .map(
      (r) =>
        `<div class="lca-signal-row"><span class="lca-signal-lbl">${escapeHtml(r.label)}</span><span class="lca-signal-val">${escapeHtml(r.value)}</span></div>`
    )
    .join("")}</div>`;
}

function hasFitSignals(rec) {
  if (!rec) return false;
  if (rec.available) return true;
  return (
    rec.location_tier != null ||
    (rec.location_label && rec.location_label !== "—") ||
    rec.track_priority != null ||
    rec.fit_ratio != null ||
    (rec.preferences_total != null && rec.preferences_total > 0)
  );
}

function sponsorHeadPillFromApi(sp) {
  if (!sp?.matched) return statusPill("No H-1B record", "neutral");
  const n = sp.total_lca_count || 0;
  if (n > 0) return statusPill(`H-1B sponsor · ${n} LCAs`, "ok");
  return statusPill("H-1B sponsor", "ok");
}

function renderCompanyHeadBlock(displayName, legalName, jobTitle, pillHtml, jobLocation) {
  const primary = displayName || legalName || "";
  const sub =
    legalName && displayName && legalName.toLowerCase() !== displayName.toLowerCase()
      ? `<span class="lca-legal-name">DOL: ${escapeHtml(legalName)}</span>`
      : "";
  const companyLine = primary
    ? `<div class="lca-company-line"><div class="lca-company-text"><span class="lca-company">${escapeHtml(primary)}</span>${sub}</div></div>`
    : "";
  const titleLine = jobTitle ? `<div class="lca-job-title">${escapeHtml(jobTitle)}</div>` : "";
  const locLine =
    jobLocation && jobLocation.trim()
      ? `<div class="lca-job-location">${escapeHtml(jobLocation.trim())}</div>`
      : "";
  const pillBlock = pillHtml ? `<div class="lca-head-pill">${pillHtml}</div>` : "";
  return `<div class="lca-section-card lca-section-card--company"><div class="lca-head-block">${companyLine}${pillBlock}</div>${titleLine}${locLine}</div>`;
}

function renderAnalysisBlock(rec, rf, co, explain) {
  if (!hasFitSignals(rec) && !co?.available) return "";

  const meta = rec?.available
    ? VERDICT_LABELS[rec.decision] || { text: rec.decision || "?", tone: "consider" }
    : { text: "Fit unavailable", tone: "neutral" };
  const note = rec?.available ? buildVerdictNote(rec) : (rec?.reason || "");

  const metrics =
    rec && hasFitSignals(rec)
      ? `<div class="lca-metrics-wrap">${renderMetricsGrid(rec, co, explain, rf)}</div>`
      : "";

  const verdictCard = rec?.available
    ? `<div class="lca-verdict-card lca-verdict-card--${meta.tone}">
        <div class="lca-verdict-row">
          ${statusPill(meta.text, meta.tone)}
          ${note ? `<span class="lca-verdict-note">${escapeHtml(note)}</span>` : ""}
        </div>
      </div>`
    : note
      ? `<p class="lca-h1b-subline">${escapeHtml(note)}</p>`
      : "";

  return `
    <div class="lca-section-card lca-section-card--fit lca-analysis lca-fadein">
      <div class="lca-section-label">Fit analysis</div>
      ${verdictCard}
      ${metrics}
      ${renderCompanySignals(co)}
    </div>`;
}

function renderRiskSection(risk) {
  if (!risk?.available || !risk.risks?.length) return "";
  const top = risk.risks[0];
  const claim = top.claim || "";
  const truncated = claim.length > 56 ? `${claim.slice(0, 55)}…` : claim;
  const more = risk.risks.length > 1 ? ` · +${risk.risks.length - 1}` : "";
  return `<p class="lca-risk-line">⚠ ${escapeHtml(truncated)}${more ? `<span class="lca-risk-more">${escapeHtml(more)}</span>` : ""}</p>`;
}

function renderResumeClaimList(items, emptyLabel) {
  const rows = (items || [])
    .map((c) => {
      const text = stripClaimPrefix(c?.claim || c);
      return text ? `<li>${escapeHtml(text)}</li>` : "";
    })
    .filter(Boolean)
    .join("");
  if (!rows) return `<p class="lca-resume-empty">${escapeHtml(emptyLabel)}</p>`;
  return `<ul class="lca-resume-list">${rows}</ul>`;
}

/** Your resume snapshot + requirement-level match for this posting. */
function renderResumeDetailSection(rf, received) {
  const hasResume = Boolean(received?.has_resume);
  const summary = (received?.resume_summary || "").trim();
  if (!hasResume && !rf?.available) return "";

  const blocks = [];
  if (hasResume) {
    const body = summary
      ? `<p class="lca-resume-summary">${escapeHtml(summary)}</p>`
      : `<p class="lca-resume-summary">${Number(received?.resume_chars || 0).toLocaleString()} characters on file.</p>`;
    blocks.push(`
      <div class="lca-section-card lca-section-card--resume lca-resume-you">
        <div class="lca-section-label">Your resume</div>
        ${body}
      </div>`);
  }

  if (rf?.available) {
    const strong = rf.strong_matches || [];
    const partial = rf.partial_matches || [];
    const missing = rf.missing || [];
    blocks.push(`
      <div class="lca-section-card lca-section-card--resume lca-resume-role">
        <div class="lca-section-label">Resume vs this role</div>
        <div class="lca-resume-cols">
          <div class="lca-resume-col">
            <div class="lca-resume-col-hd">Strong (${strong.length})</div>
            ${renderResumeClaimList(strong, "No strong overlaps.")}
          </div>
          <div class="lca-resume-col">
            <div class="lca-resume-col-hd">Partial (${partial.length})</div>
            ${renderResumeClaimList(partial, "No partial overlaps.")}
          </div>
          <div class="lca-resume-col">
            <div class="lca-resume-col-hd">Gaps (${missing.length})</div>
            ${renderResumeClaimList(missing, "No major gaps flagged.")}
          </div>
        </div>
      </div>`);
  } else if (hasResume && rf?.reason) {
    blocks.push(`<p class="lca-h1b-subline">${escapeHtml(rf.reason)}</p>`);
  }

  return blocks.join("");
}

/** H-1B block — works with extension employer object or API sponsorship. */
function renderH1bBlock(data, currentJobTitle = null) {
  const filings = Number(data.filings ?? data.lca_count ?? data.total_lca_count) || 0;
  if (filings <= 0 && !data.showWhenEmpty) return "";

  const certified = Number(data.certified ?? data.certified_count) || 0;
  const approvedPct = filings > 0 ? Math.round((certified / filings) * 100) : 0;
  const topJobs = data.topJobs || data.top_jobs || data.sponsored_titles || [];

  const grid =
    filings > 0
      ? renderMetricGrid([
          {
            val: `${approvedPct}%`,
            lbl: "Approved",
            tipTitle: "LCA approval rate",
            tip: [{ k: "Certified", v: `${certified} of ${filings}` }],
          },
          {
            val: filings.toLocaleString(),
            lbl: "Filings",
            tipTitle: "H-1B filings",
            tip: [{ k: "Total LCAs", v: filings.toLocaleString() }],
          },
        ])
      : "";

  const jobRows = topJobs
    .slice(0, 2)
    .filter((j) => !titlesRoughlyMatch(j.title || j, currentJobTitle))
    .map((j) => {
      const title = typeof j === "string" ? j : j.title;
      const wage = formatWage(j.wage_from);
      const titleHtml = escapeHtml(title);
      const wageHtml = wage ? `<span class="lca-h1b-wage">${escapeHtml(wage)}</span>` : "";
      return `<div class="lca-h1b-role" title="${titleHtml}${wage ? ` · ${escapeHtml(wage)}` : ""}">${titleHtml}${wageHtml}</div>`;
    });

  const rolesBlock = jobRows.length ? `<div class="lca-h1b-roles">${jobRows.join("")}</div>` : "";
  const headerPill = data.pillHtml || "";
  const subline = data.subline
    ? `<p class="lca-h1b-subline">${escapeHtml(data.subline)}</p>`
    : "";

  return `<div class="lca-section-card lca-section-card--h1b"><div class="lca-section-label">H-1B sponsorship</div>${headerPill}${subline}${grid}${rolesBlock}</div>`;
}

function renderSponsorshipFromApi(sp, currentJobTitle = null) {
  if (!sp) return "";
  if (!sp.matched) {
    return renderH1bBlock({
      filings: 0,
      showWhenEmpty: true,
      pillHtml: statusPill("No H-1B record", "neutral"),
      subline: sp.reason || "Not in DOL database",
    });
  }
  const name = sp.company?.name;
  return renderH1bBlock(
    {
      filings: sp.total_lca_count,
      certified: sp.certified_count,
      sponsored_titles: sp.sponsored_titles,
      pillHtml: statusPill(
        sp.total_lca_count > 0 ? `H-1B sponsor · ${sp.total_lca_count} LCAs` : "H-1B sponsor",
        "ok"
      ),
      subline: name || undefined,
    },
    currentJobTitle
  );
}

/** Web + extension: unified layout (company → H-1B → fit). */
function renderUnifiedReport(report, options = {}) {
  const sections = options.sections || ["head", "h1b", "fit", "resume_detail", "risk"];
  const title = options.title || report.received?.title || null;
  const jobLocation = options.jobLocation || report.received?.job_location || null;
  const company =
    options.company || report.received?.company || report.sponsorship?.company?.name || "";
  const legal =
    report.sponsorship?.company?.name && report.sponsorship.company.name !== company
      ? report.sponsorship.company.name
      : null;
  const pill = options.headPillHtml || sponsorHeadPillFromApi(report.sponsorship);

  const parts = ['<div class="jl-report-results">'];

  if (sections.includes("head") && (company || title || pill || jobLocation)) {
    parts.push(renderCompanyHeadBlock(company, legal, title, pill, jobLocation));
  }

  if (sections.includes("h1b")) {
    if (options.localH1bHtml) {
      parts.push(options.localH1bHtml);
    } else if (report.sponsorship?.matched && (report.sponsorship.total_lca_count || 0) > 0) {
      parts.push(
        renderH1bBlock(
          {
            filings: report.sponsorship.total_lca_count,
            certified: report.sponsorship.certified_count,
            sponsored_titles: report.sponsorship.sponsored_titles,
          },
          title
        )
      );
    } else if (report.sponsorship && !report.sponsorship.matched) {
      parts.push(
        renderH1bBlock({
          filings: 0,
          showWhenEmpty: true,
          subline: report.sponsorship.reason || "Not in DOL database",
        })
      );
    }
  }

  if (sections.includes("fit")) {
    parts.push(
      renderAnalysisBlock(report.recommendation, report.resume_fit, report.company, report.explain)
    );
  }
  if (sections.includes("resume_detail")) {
    parts.push(renderResumeDetailSection(report.resume_fit, report.received));
  }
  if (sections.includes("risk")) {
    parts.push(renderRiskSection(report.risk));
  }
  parts.push("</div>");
  return parts.filter(Boolean).join("");
}

/** @deprecated use renderUnifiedReport */
function renderReportResults(report, options = {}) {
  return renderUnifiedReport(report, options);
}

function tipMountRoot() {
  return document.getElementById("joblens-panel") || document.querySelector(".jl-report-shell") || document.body;
}

function applyTipSurface(tip) {
  tip.style.background = "#fdfaf3";
  tip.style.color = "#2a2418";
  tip.style.border = "1px solid rgba(42, 36, 24, 0.12)";
  tip.style.boxShadow = "0 12px 32px -10px rgba(15, 15, 15, 0.22)";
  tip.style.opacity = "1";
}

function wireMetricTips(root) {
  if (!root || typeof document === "undefined") return;

  const host = tipMountRoot();
  host.querySelectorAll(":scope > .lca-metric-tip").forEach((t) => t.remove());
  document.querySelectorAll("body > .lca-metric-tip").forEach((t) => t.remove());

  root.querySelectorAll(".lca-metric.lca-has-tip").forEach((cell) => {
    if (cell.dataset.tipWired === "1") return;
    cell.dataset.tipWired = "1";

    const show = () => {
      let tip =
        host.querySelector(`.lca-metric-tip[data-jl-cell-id="${cell.dataset.jlTipId}"]`) ||
        cell.querySelector(".lca-metric-tip");
      if (!tip) return;

      const mount = tipMountRoot();
      if (tip.parentElement !== mount) {
        mount.appendChild(tip);
      }

      tip.classList.add("lca-tip-visible");
      applyTipSurface(tip);
      tip.style.display = "block";
      tip.style.visibility = "hidden";
      tip.style.position = "fixed";
      tip.style.transform = "none";
      tip.style.right = "auto";
      tip.style.bottom = "auto";
      tip.style.zIndex = "100000";
      tip.style.maxWidth = `${Math.min(280, window.innerWidth - 16)}px`;
      tip.style.pointerEvents = "none";

      const cellRect = cell.getBoundingClientRect();
      const tipRect = tip.getBoundingClientRect();
      let left = cellRect.left + cellRect.width / 2 - tipRect.width / 2;
      let top = cellRect.bottom + 8;

      const panel = document.getElementById("joblens-panel");
      const bounds = panel ? panel.getBoundingClientRect() : null;
      const pad = 8;
      const maxW = bounds ? bounds.width - pad * 2 : window.innerWidth - 16;
      tip.style.maxWidth = `${Math.max(120, Math.min(280, maxW))}px`;

      const tipRect2 = tip.getBoundingClientRect();
      left = cellRect.left + cellRect.width / 2 - tipRect2.width / 2;

      if (bounds) {
        left = Math.max(bounds.left + pad, Math.min(left, bounds.right - tipRect2.width - pad));
        if (top + tipRect2.height > bounds.bottom - pad) {
          top = cellRect.top - tipRect2.height - 8;
        }
        top = Math.max(bounds.top + pad, Math.min(top, bounds.bottom - tipRect2.height - pad));
      } else {
        left = Math.max(pad, Math.min(left, window.innerWidth - tipRect2.width - pad));
        if (top + tipRect2.height > window.innerHeight - pad) {
          top = cellRect.top - tipRect2.height - 8;
        }
        top = Math.max(pad, Math.min(top, window.innerHeight - tipRect2.height - pad));
      }

      tip.style.left = `${Math.round(left)}px`;
      tip.style.top = `${Math.round(top)}px`;
      tip.style.visibility = "visible";
    };

    const hide = () => {
      const mount = tipMountRoot();
      const tip =
        mount.querySelector(`.lca-metric-tip[data-jl-cell-id="${cell.dataset.jlTipId}"]`) ||
        cell.querySelector(".lca-metric-tip");
      if (!tip) return;
      tip.classList.remove("lca-tip-visible");
      tip.style.display = "none";
      tip.style.visibility = "";
      tip.style.left = "";
      tip.style.top = "";
      if (cell.isConnected && tip.parentElement === mount) {
        cell.insertBefore(tip, cell.firstChild);
      }
    };

    if (!cell.dataset.jlTipId) {
      cell.dataset.jlTipId = `jl-tip-${Math.random().toString(36).slice(2, 9)}`;
    }
    const tipEl = cell.querySelector(".lca-metric-tip");
    if (tipEl) tipEl.dataset.jlCellId = cell.dataset.jlTipId;

    cell.addEventListener("mouseenter", show);
    cell.addEventListener("focus", show);
    cell.addEventListener("mouseleave", hide);
    cell.addEventListener("blur", hide);
  });
}

// Extension content scripts (no bundler): attach to global.
const JobLensReportView = {
  escapeHtml,
  formatWage,
  buildVerdictNote,
  titlesRoughlyMatch,
  statusPill,
  renderMetricGrid,
  buildMetricCells,
  renderMetricsGrid,
  renderCompanySignals,
  renderAnalysisBlock,
  renderResumeDetailSection,
  renderRiskSection,
  renderH1bBlock,
  renderSponsorshipFromApi,
  renderUnifiedReport,
  renderReportResults,
  renderCompanyHeadBlock,
  sponsorHeadPillFromApi,
  wireMetricTips,
  hardRequirementFit,
  resolveFitRatio,
};

if (typeof globalThis !== "undefined") {
  globalThis.JobLensReportView = JobLensReportView;
}

export {
  escapeHtml,
  formatWage,
  buildVerdictNote,
  titlesRoughlyMatch,
  statusPill,
  renderMetricGrid,
  buildMetricCells,
  renderMetricsGrid,
  renderCompanySignals,
  renderAnalysisBlock,
  renderResumeDetailSection,
  renderRiskSection,
  renderH1bBlock,
  renderSponsorshipFromApi,
  renderUnifiedReport,
  renderReportResults,
  renderCompanyHeadBlock,
  sponsorHeadPillFromApi,
  wireMetricTips,
  hardRequirementFit,
  resolveFitRatio,
  JobLensReportView,
};
