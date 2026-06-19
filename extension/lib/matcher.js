/**
 * LCA employer lookup — evidence-first entity resolution on meaningful token overlap.
 *
 * lookup() returns:
 *   { employer, confidence, rank_score, method, matchedOn, warnings[], notes[], alternatives[] } | null
 *
 * confidence: entity-resolution confidence (high / medium / low) — drives badge color.
 * rank_score: internal candidate sort key only — not confidence, not probability.
 */
const LcaMatcher = (() => {
  const SESSION_CACHE = new Map();

  const LEGAL_SUFFIXES = new Set([
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corporation",
    "corp",
    "company",
    "co",
    "llp",
    "lp",
    "plc",
  ]);

  const WEAK_CORPORATE_WORDS = new Set([
    "group",
    "holdings",
    "services",
    "solutions",
    "systems",
    "technologies",
    "international",
    "usa",
    "us",
    "america",
  ]);

  const NOISE_WORDS = new Set([...LEGAL_SUFFIXES, ...WEAK_CORPORATE_WORDS]);

  const GENERIC_TOKENS = new Set([
    "american",
    "global",
    "international",
    "group",
    "services",
    "service",
    "solutions",
    "technology",
    "technologies",
    "systems",
    "management",
    "consulting",
    "partners",
    "partner",
    "capital",
    "holdings",
    "labs",
    "health",
    "care",
    "university",
    "hiring",
    "staffing",
    "industries",
    "industry",
    "enterprises",
    "enterprise",
    "associates",
    "resources",
    "digital",
    "software",
    "companies",
    "gamma",
    "united",
    "national",
    "advanced",
    "north",
    "south",
    "east",
    "west",
    "central",
    "community",
    "first",
    "general",
    "professional",
    "business",
    "world",
    "city",
    "state",
    "pacific",
    "atlantic",
    "prime",
    "blue",
    "green",
    "red",
    "new",
    "best",
    "all",
    "one",
  ]);

  let payload = null;
  let feinMap = null;
  let keyIndex = null;
  let employerProfiles = null;
  let tokenIndex = null;
  let loadPromise = null;

  /** Capture at script load while extension context is still valid. */
  const EXT_RUNTIME = (() => {
    try {
      const rt = globalThis.chrome?.runtime ?? globalThis.browser?.runtime;
      if (rt?.getURL && rt?.id) return rt;
    } catch (_) {
      /* extension context invalidated */
    }
    return null;
  })();

  async function extensionResourceUrlAsync(path) {
    if (EXT_RUNTIME?.getURL) {
      try {
        void EXT_RUNTIME.id;
        return EXT_RUNTIME.getURL(path);
      } catch (_) {
        /* try background */
      }
    }
    const rt = globalThis.chrome?.runtime ?? globalThis.browser?.runtime;
    if (!rt?.sendMessage) {
      throw new Error(
        "Extension disconnected — open chrome://extensions, click Reload on Job Check, then refresh this LinkedIn tab (F5)."
      );
    }
    return new Promise((resolve, reject) => {
      rt.sendMessage({ type: "LCA_GET_RESOURCE_URL", path }, (resp) => {
        const err = rt.lastError;
        if (err) {
          reject(
            new Error(
              `${err.message} — reload the extension at chrome://extensions, then refresh this tab (F5).`
            )
          );
          return;
        }
        if (resp?.ok && resp.url) {
          resolve(resp.url);
          return;
        }
        reject(new Error(resp?.error || "Could not resolve extension resource URL."));
      });
    });
  }

  function tokenizeRaw(text) {
    return String(text)
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^\w\s-]/g, " ")
      .replace(/-/g, " ")
      .split(/\s+/)
      .filter(Boolean);
  }

  function stripNoiseTokens(tokens) {
    const out = [];
    for (let i = 0; i < tokens.length; i += 1) {
      if (tokens[i] === "north" && tokens[i + 1] === "america") {
        i += 1;
        continue;
      }
      if (!NOISE_WORDS.has(tokens[i])) out.push(tokens[i]);
    }
    return out;
  }

  function meaningfulTokens(text) {
    const seen = new Set();
    const out = [];
    for (const token of stripNoiseTokens(tokenizeRaw(text))) {
      if (token.length < 3 || GENERIC_TOKENS.has(token) || seen.has(token)) continue;
      seen.add(token);
      out.push(token);
    }
    return out;
  }

  function coreNormalize(text) {
    return meaningfulTokens(text).join(" ");
  }

  function normalize(text) {
    return coreNormalize(text);
  }

  function shortLabel(text, max = 48) {
    if (!text) return "";
    const one = String(text).replace(/\s+/g, " ").trim();
    if (one.length <= max) return one;
    return `${one.slice(0, max).replace(/\s+\S*$/, "").trim()}…`;
  }

  function cacheKey(slug, pageName) {
    return `${slug}|${coreNormalize(pageName || "")}`;
  }

  function buildEmployerProfile(employer) {
    const tokenSet = new Set();
    const cores = new Set();
    const sources = [employer.name, ...(employer.names || []), ...(employer.search_keys || [])];

    for (const raw of sources) {
      const tokens = meaningfulTokens(raw);
      tokens.forEach((t) => tokenSet.add(t));
      const core = coreNormalize(raw);
      if (core) cores.add(core);
    }

    return {
      employer,
      tokens: tokenSet,
      cores,
      primaryCore: coreNormalize(employer.name),
    };
  }

  function buildIndexes() {
    employerProfiles = new Map();
    tokenIndex = new Map();

    for (const employer of payload.employers) {
      const profile = buildEmployerProfile(employer);
      employerProfiles.set(employer.fein, profile);
      for (const token of profile.tokens) {
        if (!tokenIndex.has(token)) tokenIndex.set(token, new Set());
        tokenIndex.get(token).add(employer.fein);
      }
    }
  }

  function linkedInTokenSet(slug, pageName) {
    const pageTokens = pageName ? meaningfulTokens(pageName) : [];
    const slugTokens = slug ? meaningfulTokens(slug.replace(/-/g, " ")) : [];

    if (pageTokens.length > 0) {
      const tokens = new Set(pageTokens);
      for (const slugToken of slugTokens) {
        if (tokens.has(slugToken)) continue;
        const dominated = [...tokens].some(
          (pageToken) =>
            slugToken.includes(pageToken) ||
            pageToken.includes(slugToken) ||
            slugToken.startsWith(pageToken) ||
            pageToken.startsWith(slugToken)
        );
        if (!dominated) tokens.add(slugToken);
      }
      return tokens;
    }

    return new Set(slugTokens);
  }

  function linkedInCore(slug, pageName) {
    const pageCore = pageName ? coreNormalize(pageName) : "";
    const slugCore = slug ? coreNormalize(slug.replace(/-/g, " ")) : "";
    if (pageCore && (!slugCore || pageCore.length >= slugCore.length)) return pageCore;
    return slugCore;
  }

  function slugTokenSet(slug) {
    return slug ? new Set(meaningfulTokens(slug.replace(/-/g, " "))) : new Set();
  }

  function pageTokenSet(pageName) {
    return pageName ? new Set(meaningfulTokens(pageName)) : new Set();
  }

  function slugDisplayDisagree(slug, pageName) {
    const slugTokens = slugTokenSet(slug);
    const pageTokens = pageTokenSet(pageName);
    if (!slugTokens.size || !pageTokens.size) return false;
    if (slugTokens.size !== pageTokens.size) return true;
    for (const token of slugTokens) {
      if (!pageTokens.has(token)) return true;
    }
    return false;
  }

  function isDisplayNameSubset(pageName, legalName) {
    const pageTokens = meaningfulTokens(pageName);
    const legalTokenSet = new Set(meaningfulTokens(legalName));
    if (!pageTokens.length) return false;
    if (pageTokens.length >= meaningfulTokens(legalName).length) return false;
    return pageTokens.every((token) => legalTokenSet.has(token));
  }

  function intersectSets(a, b) {
    const out = new Set();
    for (const item of a) if (b.has(item)) out.add(item);
    return out;
  }

  function ambiguityCount(linkedInTokens) {
    if (!linkedInTokens.size) return Number.POSITIVE_INFINITY;
    let feins = null;
    for (const token of linkedInTokens) {
      const hits = tokenIndex.get(token);
      if (!hits || !hits.size) return Number.POSITIVE_INFINITY;
      if (feins === null) feins = new Set(hits);
      else feins = intersectSets(feins, hits);
    }
    return feins ? feins.size : Number.POSITIVE_INFINITY;
  }

  function computeSignals(linkedInTokens, linkedInCoreName, profile) {
    const shared = intersectSets(linkedInTokens, profile.tokens);
    const linkedInCount = linkedInTokens.size;
    const dolCount = profile.tokens.size;

    const exactCoreMatch =
      Boolean(linkedInCoreName) &&
      (linkedInCoreName === profile.primaryCore || profile.cores.has(linkedInCoreName));

    const subsetMatch =
      linkedInCount > 0 && [...linkedInTokens].every((t) => profile.tokens.has(t));

    const extraDolTokens = [...profile.tokens].filter((t) => !linkedInTokens.has(t));

    return {
      shared_count: shared.size,
      linkedIn_count: linkedInCount,
      dol_count: dolCount,
      token_overlap_ratio: linkedInCount ? shared.size / linkedInCount : 0,
      reverse_overlap_ratio: dolCount ? shared.size / dolCount : 0,
      exact_core_match: exactCoreMatch,
      subset_match: subsetMatch,
      single_token_match: linkedInCount === 1,
      extra_dol_tokens: extraDolTokens,
    };
  }

  function computeRankScore(signals, ambiguity) {
    return (
      (signals.exact_core_match ? 1_000_000 : 0) +
      signals.shared_count * 10_000 +
      Math.round(signals.token_overlap_ratio * 1_000) -
      ambiguity * 100
    );
  }

  function compareCandidates(a, b) {
    const sa = a.signals;
    const sb = b.signals;
    if (sa.exact_core_match !== sb.exact_core_match) {
      return Number(sb.exact_core_match) - Number(sa.exact_core_match);
    }
    if (sa.shared_count !== sb.shared_count) return sb.shared_count - sa.shared_count;
    if (sa.token_overlap_ratio !== sb.token_overlap_ratio) {
      return sb.token_overlap_ratio - sa.token_overlap_ratio;
    }
    if (a.ambiguity_count !== b.ambiguity_count) return a.ambiguity_count - b.ambiguity_count;
    return b.profile.employer.lca_count - a.profile.employer.lca_count;
  }

  function isCloseAlternative(top, other) {
    if (other.profile.employer.fein === top.profile.employer.fein) return false;
    const ts = top.signals;
    const os = other.signals;
    if (os.shared_count === 0) return false;
    if (ts.exact_core_match && os.exact_core_match) return true;
    if (Math.abs(ts.token_overlap_ratio - os.token_overlap_ratio) <= 0.15) return true;
    if (ts.shared_count > 0 && os.shared_count >= ts.shared_count - 1) return true;
    return false;
  }

  function displayOverlap(pageName, legalName) {
    if (!pageName || !legalName) return 1;
    const pageTokens = new Set(meaningfulTokens(pageName));
    const legalTokens = new Set(meaningfulTokens(legalName));
    if (!pageTokens.size || !legalTokens.size) return 0;
    const shared = intersectSets(pageTokens, legalTokens);
    return shared.size / Math.max(pageTokens.size, legalTokens.size);
  }

  function passesMinimumEvidence(signals) {
    if (signals.shared_count === 0) return false;
    if (signals.exact_core_match) return true;
    if (signals.subset_match) return true;
    if (signals.token_overlap_ratio >= 0.5 && signals.shared_count >= 2) return true;
    if (signals.single_token_match && signals.shared_count === 1) return true;
    return false;
  }

  function isFuzzyEvidence(signals) {
    return (
      !signals.exact_core_match &&
      !(signals.subset_match && signals.token_overlap_ratio >= 1)
    );
  }

  function assignConfidence(signals, ambiguity, closeAlternatives, context) {
    if (!passesMinimumEvidence(signals)) return null;

    const {
      exact_core_match,
      subset_match,
      single_token_match,
      token_overlap_ratio,
      shared_count,
      linkedIn_count,
      extra_dol_tokens,
    } = signals;

    const { slugDisplayDisagree: slugPageDisagree, fuzzyOnly } = context;
    const competing = ambiguity > 1 || closeAlternatives.length > 0;
    const weakOverlap = token_overlap_ratio < 0.5;
    const partialMultiToken = linkedIn_count >= 2 && shared_count < linkedIn_count;
    const extraDolMeaningful = extra_dol_tokens.length > 0;

    if (exact_core_match && !competing) return "high";
    if (subset_match && linkedIn_count >= 2 && token_overlap_ratio >= 1 && !competing) {
      return "high";
    }

    if (fuzzyOnly) return "low";
    if (single_token_match && competing) return "low";
    if (single_token_match && !exact_core_match) return "low";
    if (weakOverlap) return "low";
    if (partialMultiToken) return "low";

    if (subset_match && linkedIn_count >= 2 && extraDolMeaningful) return "medium";
    if (competing) return "medium";
    if (slugPageDisagree) return "medium";
    if (closeAlternatives.length > 0) return "medium";
    if (exact_core_match) return "medium";

    if (single_token_match) return "low";

    return "medium";
  }

  function collectKeyCandidates(cleanSlug, pageName) {
    const feins = new Set();
    const keys = new Set();

    const addKey = (key) => {
      if (!key) return;
      keys.add(key);
    };

    addKey(cleanSlug);
    addKey(cleanSlug.replace(/-/g, " "));
    addKey(coreNormalize(cleanSlug.replace(/-/g, " ")));
    addKey(coreNormalize(cleanSlug.replace(/-/g, " ")).replace(/\s+/g, "-"));

    if (pageName) {
      addKey(coreNormalize(pageName));
      addKey(coreNormalize(pageName).replace(/\s+/g, "-"));
    }

    for (const key of keys) {
      const fein = keyIndex[key];
      if (fein) feins.add(fein);
    }
    return feins;
  }

  function collectTokenCandidates(linkedInTokens) {
    const feins = new Set();
    for (const token of linkedInTokens) {
      const hits = tokenIndex.get(token);
      if (hits) hits.forEach((fein) => feins.add(fein));
    }
    return feins;
  }

  function resolveMethod(signals, fromKeyIndex) {
    if (signals.exact_core_match) return "core_exact";
    if (signals.subset_match && signals.token_overlap_ratio >= 1) return "core_subset";
    if (fromKeyIndex) return "key_overlap";
    return "token_overlap";
  }

  function buildWarnings(signals, confidence, pageName, employer, ambiguity, closeAlternatives, method, slugPageDisagree) {
    const warnings = [];

    if (signals.single_token_match) {
      warnings.push("Matched on a single distinctive word — verify the legal entity.");
    }
    if (ambiguity > 1) {
      warnings.push(`Multiple employers (${ambiguity}) share these name tokens.`);
    }
    if (closeAlternatives.length > 0 && confidence !== "high") {
      warnings.push("Other similar employers exist — see alternatives below.");
    }
    if (slugPageDisagree) {
      warnings.push("LinkedIn slug and display name disagree — match uses both inputs.");
    }
    if (pageName) {
      const overlap = displayOverlap(pageName, employer.name);
      if (overlap < 0.34) {
        warnings.push(
          `LinkedIn shows "${shortLabel(pageName)}" but LCA lists "${employer.name}".`
        );
      }
    }
    if (signals.extra_dol_tokens.length > 0 && signals.reverse_overlap_ratio < 0.8) {
      warnings.push("DOL legal name includes extra words not seen on LinkedIn.");
    }
    if (method === "token_overlap" || method === "key_overlap") {
      warnings.push("Partial token overlap only — confirm legal name and industry.");
    }
    if (employer.lca_count <= 2) {
      warnings.push("Very few LCA filings — weak sponsorship signal.");
    }

    return warnings;
  }

  function buildNotes(pageName, employer) {
    const notes = [];
    if (pageName && isDisplayNameSubset(pageName, employer.name)) {
      notes.push(
        `LinkedIn display name "${shortLabel(pageName)}" is a subset of DOL legal name "${employer.name}".`
      );
    }
    return notes;
  }

  function buildResult(top, pageName, cleanSlug, allRanked, matchedOn) {
    const { profile, signals, ambiguity_count: ambiguity } = top;
    const closeAlternatives = allRanked.slice(1).filter((c) => isCloseAlternative(top, c));
    const slugPageDisagree = slugDisplayDisagree(cleanSlug, pageName);
    const method = resolveMethod(signals, matchedOn.startsWith("key:"));
    const fuzzyOnly = isFuzzyEvidence(signals);

    const confidence = assignConfidence(signals, ambiguity, closeAlternatives, {
      slugDisplayDisagree: slugPageDisagree,
      fuzzyOnly,
    });
    if (!confidence) return null;

    const rank_score = computeRankScore(signals, ambiguity);
    const warnings = buildWarnings(
      signals,
      confidence,
      pageName,
      profile.employer,
      ambiguity,
      closeAlternatives,
      method,
      slugPageDisagree
    );
    const notes = buildNotes(pageName, profile.employer);

    const alternatives = allRanked
      .slice(1, 4)
      .filter((c) => c.signals.shared_count > 0)
      .map((c) => ({
        employer: c.profile.employer,
        confidence: assignConfidence(c.signals, c.ambiguity_count, [], {
          slugDisplayDisagree: slugPageDisagree,
          fuzzyOnly: isFuzzyEvidence(c.signals),
        }),
      }))
      .filter((a) => a.confidence);

    return {
      employer: profile.employer,
      confidence,
      rank_score,
      method,
      matchedOn: matchedOn.replace(/^key:/, ""),
      warnings,
      notes,
      alternatives,
    };
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

  async function load() {
    if (payload) return payload;
    if (loadPromise) return loadPromise;

    loadPromise = (async () => {
      const url = await extensionResourceUrlAsync("data/employers.json.gz");
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
      buildIndexes();
      return payload;
    })();

    return loadPromise;
  }

  function lookupByFein(fein) {
    return feinMap[fein] || null;
  }

  function resolveMatch(cleanSlug, pageName) {
    const linkedInTokens = linkedInTokenSet(cleanSlug, pageName);
    const linkedInCoreName = linkedInCore(cleanSlug, pageName);

    if (!linkedInTokens.size) return null;

    const candidateFeins = collectTokenCandidates(linkedInTokens);
    collectKeyCandidates(cleanSlug, pageName).forEach((fein) => candidateFeins.add(fein));

    const globalAmbiguity = ambiguityCount(linkedInTokens);
    const ranked = [];

    for (const fein of candidateFeins) {
      const profile = employerProfiles.get(fein);
      if (!profile) continue;
      const signals = computeSignals(linkedInTokens, linkedInCoreName, profile);
      if (!passesMinimumEvidence(signals)) continue;
      ranked.push({
        profile,
        signals,
        ambiguity_count: globalAmbiguity,
        rank_score: computeRankScore(signals, globalAmbiguity),
      });
    }

    if (!ranked.length) return null;

    ranked.sort(compareCandidates);
    const top = ranked[0];

    let matchedOn = [...linkedInTokens].sort().join(" + ");
    const keyHits = collectKeyCandidates(cleanSlug, pageName);
    if (keyHits.has(top.profile.employer.fein)) {
      matchedOn = `key:${matchedOn}`;
    }

    return buildResult(top, pageName, cleanSlug, ranked, matchedOn);
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

    const result = resolveMatch(cleanSlug, pageName);
    SESSION_CACHE.set(key, result);
    return result;
  }

  function nameOverlap(pageName, legalName) {
    return displayOverlap(pageName, legalName);
  }

  function clearCache() {
    SESSION_CACHE.clear();
  }

  return {
    load,
    lookup,
    clearCache,
    lookupByFein,
    normalize,
    nameOverlap,
    meaningfulTokens,
    coreNormalize,
    isDisplayNameSubset,
    slugDisplayDisagree,
  };
})();
