/**
 * LCA employer lookup — loads compressed index and matches LinkedIn slugs/names.
 *
 * lookup() returns:
 *   { employer, confidence, score, method, matchedOn, warnings[], alternatives[], fromCache? } | null
 */
const LcaMatcher = (() => {
  const STORAGE_KEY = "learned_slugs";
  const LEARNABLE_METHODS = new Set(["exact_key", "exact_page_name"]);
  const SESSION_CACHE = new Map();
  const FUZZY_FLOOR = 70;
  const LEGAL_SUFFIXES = [
    " incorporated",
    " corporation",
    " company",
    " limited",
    " llc",
    " inc",
    " corp",
    " ltd",
    " llp",
    " lp",
    " plc",
    " usa",
    " us",
    " co",
  ];
  /** Too common for single-token fuzzy or brand-subset promotion alone. */
  const GENERIC_TOKENS = new Set([
    "hiring",
    "staffing",
    "solutions",
    "services",
    "service",
    "consulting",
    "group",
    "partners",
    "partner",
    "global",
    "international",
    "systems",
    "industries",
    "industry",
    "technologies",
    "technology",
    "holdings",
    "enterprises",
    "enterprise",
    "associates",
    "management",
    "resources",
    "digital",
    "software",
    "company",
    "companies",
  ]);

  let payload = null;
  let feinMap = null;
  let keyIndex = null;
  let learnedSlugs = {};
  let loadPromise = null;

  function stripLegalSuffixes(text) {
    let prev;
    do {
      prev = text;
      for (const suffix of LEGAL_SUFFIXES) {
        if (text.endsWith(suffix)) {
          text = text.slice(0, -suffix.length).trim();
          break;
        }
      }
    } while (text !== prev);
    return text;
  }

  function normalize(text) {
    return stripLegalSuffixes(
      String(text)
        .toLowerCase()
        .replace(/&/g, " and ")
        .replace(/[^\w\s-]/g, " ")
        .replace(/\s+/g, " ")
        .trim()
    );
  }

  /** LinkedIn display names — do not strip legal suffixes (e.g. "A Hiring Company"). */
  function displayTokens(text) {
    return String(text)
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^\w\s-]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .split(" ")
      .filter((t) => t.length >= 2);
  }

  function tokens(text) {
    return normalize(String(text).replace(/-/g, " "))
      .split(" ")
      .filter((t) => t.length >= 2);
  }

  function isDistinctiveToken(token) {
    return token.length >= 4 && !GENERIC_TOKENS.has(token);
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function hasWord(haystack, word) {
    if (!haystack || !word) return false;
    const re = new RegExp(`\\b${escapeRegExp(word)}\\b`, "i");
    return re.test(haystack);
  }

  function nameOverlap(pageName, legalName) {
    const ta = new Set(displayTokens(pageName));
    const tb = new Set(tokens(legalName));
    if (!ta.size || !tb.size) return 0;
    let shared = 0;
    for (const t of ta) if (tb.has(t) && t.length >= 3) shared += 1;
    return shared / Math.max(ta.size, tb.size);
  }

  /** LinkedIn shows a short brand; LCA uses a longer legal name (e.g. EVERSANA → EVERSANA LIFE … LLC). */
  function isBrandSubset(pageName, legalName) {
    const pageTokens = displayTokens(pageName);
    const legalTokenSet = new Set(tokens(legalName));
    if (!pageTokens.length) return false;
    if (pageTokens.length >= tokens(legalName).length) return false;
    if (!pageTokens.every((t) => legalTokenSet.has(t))) return false;
    return pageTokens.some(isDistinctiveToken);
  }

  function cacheKey(slug, pageName) {
    return `${slug}|${normalize(pageName || "")}`;
  }

  function shortLabel(text, max = 48) {
    if (!text) return "";
    const one = String(text).replace(/\s+/g, " ").trim();
    if (one.length <= max) return one;
    return `${one.slice(0, max).replace(/\s+\S*$/, "").trim()}…`;
  }

  function buildResult(employer, score, method, matchedOn, pageName, alternatives = []) {
    const warnings = [];
    const notes = [];
    let confidence = "high";
    const brandSubset = pageName && isBrandSubset(pageName, employer.name);

    if (score < 90 && !brandSubset && method !== "manual_override") confidence = "medium";
    if (score < 75 && !brandSubset && method !== "manual_override") confidence = "low";

    if (method.startsWith("fuzzy_") && !brandSubset) {
      warnings.push("Name-based match — confirm legal name and industry before trusting.");
    }

    if (brandSubset) {
      notes.push(
        `LinkedIn brand "${shortLabel(pageName)}" — H-1B filed under legal entity "${employer.name}".`
      );
      if (confidence === "low" || confidence === "medium") confidence = "high";
    } else if (pageName) {
      const overlap = nameOverlap(pageName, employer.name);
      if (overlap < 0.34) {
        confidence = confidence === "high" ? "medium" : "low";
        warnings.push(
          `LinkedIn shows "${shortLabel(pageName)}" but LCA lists "${employer.name}".`
        );
      }
    }

    if (employer.lca_count <= 2) {
      warnings.push("Very few LCA filings — weak sponsorship signal.");
    }

    if (alternatives.length > 0 && confidence !== "high") {
      warnings.push("Other similar employers exist — see alternatives below.");
    }

    return { employer, confidence, score, method, matchedOn, warnings, notes, alternatives };
  }

  function cloneResult(result, extras = {}) {
    return {
      ...result,
      warnings: [...(result.warnings || [])],
      notes: [...(result.notes || [])],
      alternatives: [...(result.alternatives || [])],
      ...extras,
    };
  }

  async function loadLearnedSlugs() {
    if (!chrome.storage?.local) return;
    const stored = await chrome.storage.local.get(STORAGE_KEY);
    learnedSlugs = stored[STORAGE_KEY] || {};
  }

  async function load() {
    if (payload) return payload;
    if (loadPromise) return loadPromise;

    loadPromise = (async () => {
      const url = chrome.runtime.getURL("data/employers.json.gz");
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`Failed to load employer index: ${resp.status}`);

      const buf = await resp.arrayBuffer();
      const ds = new DecompressionStream("gzip");
      const decompressed = await new Response(
        new Blob([buf]).stream().pipeThrough(ds)
      ).text();
      payload = JSON.parse(decompressed);

      feinMap = Object.fromEntries(payload.employers.map((e) => [e.fein, e]));
      keyIndex = payload.key_index || {};
      await loadLearnedSlugs();
      return payload;
    })();

    return loadPromise;
  }

  function lookupByFein(fein) {
    return feinMap[fein] || null;
  }

  function employerHaystacks(employer) {
    return [
      normalize(employer.name),
      ...(employer.names || []).map(normalize),
      ...(employer.search_keys || []).map(normalize),
    ].filter(Boolean);
  }

  function scoreEmployer(employer, slugTokens, slugNorm) {
    if (slugTokens.length >= 2 && !slugTokens.some(isDistinctiveToken)) {
      return 0;
    }
    if (slugTokens.length === 1 && GENERIC_TOKENS.has(slugTokens[0])) {
      return 0;
    }

    const haystacks = employerHaystacks(employer);

    for (const hay of haystacks) {
      if (hay === slugNorm) return 100;
    }

    if (slugTokens.length >= 2) {
      const tokenHits = slugTokens.map((token) =>
        haystacks.some((hay) => hasWord(hay, token))
      );
      if (tokenHits.length > 0 && tokenHits.every(Boolean)) {
        return 75 + Math.min(slugTokens.length * 5, 20);
      }
    }

    if (slugTokens.length === 1) {
      const t = slugTokens[0];
      if (t.length >= 5) {
        for (const hay of haystacks) {
          if (hay === t || hasWord(hay, t)) return 70;
        }
      }
    }

    return 0;
  }

  function collectFuzzyCandidates(tokenList, norm, excludeFein) {
    const scored = [];
    for (const employer of payload.employers) {
      if (employer.fein === excludeFein) continue;
      const score = scoreEmployer(employer, tokenList, norm);
      if (score >= FUZZY_FLOOR) {
        scored.push({ employer, score });
      }
    }
    scored.sort((a, b) => b.score - a.score || b.employer.lca_count - a.employer.lca_count);
    return scored;
  }

  function tokensDiffer(a, b) {
    if (a.length !== b.length) return true;
    return a.some((t, i) => t !== b[i]);
  }

  /** Try URL tokens first; if no hit, fall back to LinkedIn display-name tokens. */
  function resolveFuzzy(slugTokenList, slugNorm, pageName, excludeFein) {
    let hits = collectFuzzyCandidates(slugTokenList, slugNorm, excludeFein);
    let tokenList = slugTokenList;
    let norm = slugNorm;
    let method;

    if (!hits.length && pageName) {
      const pageTokens = displayTokens(pageName);
      const pageNorm = normalize(pageName);
      if (pageTokens.length && tokensDiffer(pageTokens, slugTokenList)) {
        const pageHits = collectFuzzyCandidates(pageTokens, pageNorm, excludeFein);
        if (pageHits.length) {
          hits = pageHits;
          tokenList = pageTokens;
          norm = pageNorm;
        }
      }
    }

    if (!hits.length) return null;

    const top = hits[0];
    if (top.score < FUZZY_FLOOR) return null;

    if (tokenList === slugTokenList) {
      method = slugTokenList.length === 1 ? "fuzzy_single" : "fuzzy_token";
    } else {
      method = tokenList.length === 1 ? "fuzzy_page_single" : "fuzzy_page_token";
    }

    return {
      top,
      method,
      matchedOn: tokenList.join(" + ") || norm,
      alts: hits.slice(1, 3).map(({ employer, score }) => ({ employer, score })),
    };
  }

  function shouldLearn(result, pageName) {
    if (result.confidence !== "high") return false;
    if (!LEARNABLE_METHODS.has(result.method)) return false;
    if (result.warnings.some((w) => w.includes("LinkedIn shows"))) return false;
    if (pageName && nameOverlap(pageName, result.employer.name) < 0.34) return false;
    return true;
  }

  async function persistLearnedSlug(slug, result) {
    if (!chrome.storage?.local) return;
    learnedSlugs[slug] = {
      fein: result.employer.fein,
      employer_name: result.employer.name,
      learned_at: new Date().toISOString(),
      method: result.method,
      score: result.score,
    };
    await chrome.storage.local.set({ [STORAGE_KEY]: learnedSlugs });
  }

  function resolveLearned(slug, pageName) {
    const entry = learnedSlugs[slug];
    if (!entry?.fein) return null;
    const employer = lookupByFein(entry.fein);
    if (!employer) return null;
    const result = buildResult(employer, 100, "learned_slug", slug, pageName);
    result.warnings.push("Matched from a slug you verified earlier on this device.");
    return result;
  }

  function lookupExact(cleanSlug, slugNorm, slugTokenList, pageName) {
    const overrides = payload.slug_overrides || {};
    if (overrides[cleanSlug]) {
      const employer = lookupByFein(overrides[cleanSlug]);
      if (!employer) return null;
      return buildResult(employer, 100, "manual_override", cleanSlug, pageName);
    }

    const learned = resolveLearned(cleanSlug, pageName);
    if (learned) return learned;

    const candidates = new Map();
    const addCandidate = (key, source) => {
      if (key) candidates.set(key, source);
    };

    addCandidate(cleanSlug, "slug");
    addCandidate(cleanSlug.replace(/-/g, " "), "slug");
    addCandidate(slugNorm, "slug");
    addCandidate(slugNorm.replace(/\s+/g, "-"), "slug");

    if (pageName) {
      addCandidate(normalize(pageName), "page_name");
      addCandidate(normalize(pageName).replace(/\s+/g, "-"), "page_name");
    }

    let best = null;
    let bestKey = null;
    let bestSource = null;

    for (const [key, source] of candidates.entries()) {
      const fein = keyIndex[key];
      if (!fein) continue;
      const emp = lookupByFein(fein);
      if (emp && (!best || emp.lca_count > best.lca_count)) {
        best = emp;
        bestKey = key;
        bestSource = source;
      }
    }

    if (best) {
      const method = bestSource === "page_name" ? "exact_page_name" : "exact_key";
      const alts = collectFuzzyCandidates(slugTokenList, slugNorm, best.fein)
        .slice(0, 2)
        .map(({ employer, score }) => ({ employer, score }));
      return buildResult(best, 95, method, bestKey, pageName, alts);
    }

    const fuzzy = resolveFuzzy(slugTokenList, slugNorm, pageName, null);
    if (!fuzzy) return null;

    return buildResult(
      fuzzy.top.employer,
      fuzzy.top.score,
      fuzzy.method,
      fuzzy.matchedOn,
      pageName,
      fuzzy.alts
    );
  }

  async function lookup(slug, pageName) {
    await load();

    const cleanSlug = (slug || "").toLowerCase().replace(/^\/+|\/+$/g, "");
    if (!cleanSlug) return null;

    const key = cacheKey(cleanSlug, pageName);
    if (SESSION_CACHE.has(key)) {
      const cached = SESSION_CACHE.get(key);
      if (cached === null) return null;
      return cloneResult(cached, { fromCache: true });
    }

    const slugNorm = normalize(cleanSlug.replace(/-/g, " "));
    const slugTokenList = tokens(cleanSlug);
    const result = lookupExact(cleanSlug, slugNorm, slugTokenList, pageName);

    if (result && shouldLearn(result, pageName)) {
      await persistLearnedSlug(cleanSlug, result);
    }

    SESSION_CACHE.set(key, result);
    return result;
  }

  async function clearLearnedSlugs() {
    learnedSlugs = {};
    SESSION_CACHE.clear();
    if (chrome.storage?.local) {
      await chrome.storage.local.remove(STORAGE_KEY);
    }
  }

  async function getLearnedSlugs() {
    await load();
    return { ...learnedSlugs };
  }

  return {
    load,
    lookup,
    normalize,
    nameOverlap,
    clearLearnedSlugs,
    getLearnedSlugs,
  };
})();
