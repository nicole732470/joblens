/**
 * LCA employer lookup — loads compressed index and matches LinkedIn slugs/names.
 */
const LcaMatcher = (() => {
  let payload = null;
  let feinMap = null;
  let keyIndex = null;
  let loadPromise = null;

  function normalize(text) {
    return text
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^\w\s-]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b(incorporated|corporation|company|limited|llc|inc|corp|ltd|co|llp|lp|plc|usa|us)\b/g, "")
      .replace(/\s+/g, " ")
      .trim();
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
      const decompressed = await new Response(new Blob([buf]).stream().pipeThrough(ds)).text();
      payload = JSON.parse(decompressed);

      feinMap = Object.fromEntries(payload.employers.map((e) => [e.fein, e]));
      keyIndex = payload.key_index || {};
      return payload;
    })();

    return loadPromise;
  }

  function lookupByFein(fein) {
    return feinMap[fein] || null;
  }

  function lookup(slug, h1Name) {
    if (!payload) return null;

    const overrides = payload.slug_overrides || {};
    const cleanSlug = (slug || "").toLowerCase().replace(/^\/+|\/+$/g, "");

    if (overrides[cleanSlug]) {
      return lookupByFein(overrides[cleanSlug]);
    }

    const candidates = new Set([
      cleanSlug,
      cleanSlug.replace(/-/g, " "),
      normalize(cleanSlug.replace(/-/g, " ")),
    ]);

    if (h1Name) {
      candidates.add(normalize(h1Name));
      candidates.add(normalize(h1Name).replace(/\s+/g, "-"));
    }

    let best = null;
    for (const key of candidates) {
      if (!key) continue;
      const fein = keyIndex[key];
      if (!fein) continue;
      const emp = lookupByFein(fein);
      if (emp && (!best || emp.lca_count > best.lca_count)) best = emp;
    }

    if (best) return best;

    const slugNorm = normalize(cleanSlug.replace(/-/g, " "));
    if (slugNorm.length < 4) return null;

    for (const [key, fein] of Object.entries(keyIndex)) {
      if (key.includes(slugNorm) || slugNorm.includes(key)) {
        const emp = lookupByFein(fein);
        if (emp && (!best || emp.lca_count > best.lca_count)) best = emp;
      }
    }
    return best;
  }

  return { load, lookup };
})();
