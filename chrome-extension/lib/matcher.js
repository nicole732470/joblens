/**
 * LCA employer lookup — loads compressed index and matches LinkedIn slugs/names.
 *
 * lookup() returns:
 *   { employer, confidence, score, method, matchedOn, warnings[], fromCache? } | null
 */
const LcaMatcher = (() => {
  const STORAGE_KEY = "learned_slugs";
  const LEARNABLE_METHODS = new Set(["exact_key", "exact_page_name"]);
  const SESSION_CACHE = new Map();

  let payload = null;
  let feinMap = null;
  let keyIndex = null;
  let learnedSlugs = {};
  let loadPromise = null;

  function normalize(text) {
    return text
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^\w\s-]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(
        /\b(incorporated|corporation|company|limited|llc|inc|corp|ltd|co|llp|lp|plc|usa|us)\b/g,
        ""
      )
      .replace(/\s+/g, " ")
      .trim();
  }

  function tokens(text) {
    return normalize(String(text).replace(/-/g, " "))
      .split(" ")
      .filter(Boolean);
  }

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function hasWord(haystack, word) {
    if (!haystack || !word) return false;
    const re = new RegExp(`\\b${escapeRegExp(word)}\\b`, "i");
    return re.test(haystack);
  }

  function nameOverlap(a, b) {
    const ta = new Set(tokens(a));
    const tb = new Set(tokens(b));
    if (!ta.size || !tb.size) return 0;
    let shared = 0;
    for (const t of ta) if (tb.has(t) && t.length >= 3) shared += 1;
    return shared / Math.max(ta.size, tb.size);
  }

  function cacheKey(slug, pageName) {
    return `${slug}|${normalize(pageName || "")}`;
  }

  function buildResult(employer, score, method, matchedOn, pageName) {
    const warnings = [];
    let confidence = "high";

    if (score < 90) confidence = "medium";
    if (score < 70) confidence = "low";

    if (method === "fuzzy_token" || method === "fuzzy_single") {
      warnings.push("Fuzzy match — verify the legal name before trusting this result.");
    }

    if (pageName) {
      const overlap = nameOverlap(pageName, employer.name);
      if (overlap < 0.34) {
        confidence = confidence === "high" ? "medium" : "low";
        warnings.push(
          `LinkedIn name "${pageName}" looks different from LCA name "${employer.name}".`
        );
      }
    }

    if (employer.lca_count <= 2) {
      warnings.push("Very few LCA filings — treat as weak signal.");
    }

    return { employer, confidence, score, method, matchedOn, warnings };
  }

  function cloneResult(result, extras = {}) {
    return {
      ...result,
      warnings: [...(result.warnings || [])],
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
    const haystacks = employerHaystacks(employer);

    for (const hay of haystacks) {
      if (hay === slugNorm) return 100;
    }

    const tokenHits = slugTokens.map((token) =>
      haystacks.some((hay) => hasWord(hay, token))
    );
    if (tokenHits.length > 0 && tokenHits.every(Boolean)) {
      return 70 + slugTokens.length * 10;
    }

    if (slugTokens.length === 1) {
      const t = slugTokens[0];
      if (t.length >= 4) {
        for (const hay of haystacks) {
          if (hay === t || hasWord(hay, t)) return 60;
        }
      }
    }

    return 0;
  }

  function shouldLearn(result, pageName) {
    if (result.confidence !== "high") return false;
    if (!LEARNABLE_METHODS.has(result.method)) return false;
    if (result.warnings.some((w) => w.includes("looks different"))) return false;
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
    result.warnings.push("Matched from a previously verified slug mapping on this device.");
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
      return buildResult(best, 95, method, bestKey, pageName);
    }

    let bestScore = 0;
    let bestEmp = null;
    for (const employer of payload.employers) {
      const score = scoreEmployer(employer, slugTokenList, slugNorm);
      if (score > bestScore) {
        bestScore = score;
        bestEmp = employer;
      } else if (score === bestScore && score > 0 && bestEmp) {
        if (employer.lca_count > bestEmp.lca_count) bestEmp = employer;
      }
    }

    if (bestScore < 60 || !bestEmp) return null;

    const method = slugTokenList.length === 1 ? "fuzzy_single" : "fuzzy_token";
    return buildResult(bestEmp, bestScore, method, slugTokenList.join(" + "), pageName);
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
