# LCA Sponsor Checker

A local-first system that cross-references LinkedIn company pages against U.S. Department of Labor (DOL) H-1B Labor Condition Application (LCA) disclosure data. The project combines an offline data pipeline with a Chrome extension that performs in-browser entity matching — no backend server, no cloud dependency.

---

## Repository Layout

```
.
├── convert_to_sqlite.py          # Ingestion: Excel → SQLite
├── export_employer_index.py      # Index builder: SQLite → compressed JSON
├── slug_overrides.json           # Curated LinkedIn slug → FEIN mappings
├── requirements.txt
├── data/                         # Derived datasets (job distribution, Chicago sponsors)
├── docs/                         # H-1B distribution summaries and metro sponsor lists
├── chrome-extension/             # Chrome Manifest V3 extension
│   ├── manifest.json
│   ├── content.js                # DOM injection + SPA navigation handling
│   ├── styles.css
│   ├── lib/matcher.js            # Client-side lookup engine
│   └── data/employers.json.gz    # Pre-built employer index (~7 MB)
└── README.md
```

Raw source files (440 MB `.xlsx`, 940 MB `.db`) are excluded from version control due to size.

---

## System Architecture

The system is split into two decoupled layers: an **offline data pipeline** (Python) and a **client-side lookup runtime** (Chrome extension). They communicate only through a versioned, compressed JSON artifact.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OFFLINE DATA PIPELINE                        │
│                                                                     │
│  DOL LCA Excel (.xlsx)                                              │
│       │  python-calamine (Rust-backed reader)                       │
│       ▼                                                             │
│  SQLite (lca_cases table, ~807K rows, indexed)                      │
│       │  SQL aggregation + entity resolution by FEIN              │
│       ▼                                                             │
│  employers.json.gz (~7 MB, 74K employers, 173K search keys)         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ bundled into extension
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     CLIENT RUNTIME (Chrome MV3)                     │
│                                                                     │
│  linkedin.com/company/{slug}                                        │
│       │  content.js extracts slug from URL                          │
│       ▼                                                             │
│  matcher.js loads index + learned slugs (chrome.storage.local)      │
│       │  session cache → overrides → learned → exact → fuzzy        │
│       ▼                                                             │
│  Badge UI (confidence, warnings, match method, FEIN)                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Data Ingestion (Excel → SQLite)

### Problem

DOL publishes LCA data as flat Excel files. The FY2026 Q2 file is ~440 MB on disk, ~807K rows × 98 columns, with ~1.9M shared strings and ~2.6 GB of decompressed XML internally. Standard Python readers (`openpyxl`, `pandas` default engine) take 5–15 minutes; the dataset is too large for in-browser or in-memory analytics without preprocessing.

### Design

| Decision | Rationale |
|----------|-----------|
| **python-calamine** over openpyxl | Rust bindings via PyO3; reads 807K rows in ~47 s vs. minutes. Read-only path is sufficient — no write-back needed. |
| **SQLite** over Parquet/CSV | Random lookups by `EMPLOYER_NAME`, `EMPLOYER_FEIN`, `JOB_TITLE` during exploration; SQL aggregation for index export; single-file portability. |
| **Batch insert (10K rows)** | Reduces transaction overhead; total write ~21 s for 807K rows. |
| **Post-load indexing** | 13 indexes on high-cardinality filter columns (`EMPLOYER_FEIN`, `CASE_STATUS`, `VISA_CLASS`, etc.); built after bulk insert to avoid per-row index maintenance cost (~6 s). |
| **WAL journal mode** | Faster concurrent reads during export while ingestion completes. |
| **TEXT columns throughout** | LCA fields mix formats (dates as strings, empty wage fields, OES year strings in wage-level columns); schema-on-read avoids silent type coercion errors. |

### Schema

One fact table `lca_cases` (98 columns, one row per LCA filing) plus pre-aggregated summary tables and metadata. Employers are deduplicated at query time by **FEIN** (Federal Employer Identification Number): 85,847 distinct `EMPLOYER_NAME` values collapse to **74,732** legal entities — ~9,264 FEINs map to multiple name variants (subsidiaries, DBA names, typos).

---

## Layer 2: Index Export (SQLite → Compressed JSON)

### Problem

A Chrome extension cannot read a 940 MB SQLite file from disk. The browser sandbox permits only packaged extension resources or network requests. The lookup surface needed at runtime is not 807K LCA rows — it is **"does this LinkedIn company correspond to any LCA-filing entity, and what are the headline stats?"**

### Design

The export step performs **server-side aggregation** (in Python/SQL) and ships a **read-optimized denormalized index** to the client.

| Field per employer | Purpose |
|--------------------|---------|
| `fein` | Stable primary key for legal entity |
| `name` / `names[]` | Primary and alias employer names from LCA filings |
| `search_keys[]` | Precomputed normalized lookup tokens |
| `lca_count`, `h1b_count`, `certified_count` | Headline sponsorship signals |
| `top_jobs[]` | Top 3 `(title, wage_level, wage_from)` by filing frequency |
| `key_index` | Inverted map: `normalized_key → fein` for O(1) client lookup |
| `slug_overrides` | Curated `linkedin_slug → fein` for known mismatches |

**Top-jobs aggregation** uses a single SQL window-function query (`ROW_NUMBER() OVER (PARTITION BY EMPLOYER_FEIN ...)`) rather than 74K per-FEIN queries — export completes in ~7 s instead of 10+ minutes.

**Compression:** raw JSON ~36 MB → gzip ~7 MB. Loaded once per session via `fetch()` + native `DecompressionStream` (no third-party library).

### Search Key Generation

Each employer name is normalized (lowercase, strip legal suffixes like LLC/Inc/Corp, replace `&` → `and`, remove punctuation) and expanded into multiple keys:

- Full normalized name: `"google llc"` → `"google"`
- Slug form: `"Google LLC"` → `"google-llc"`
- First token (≥3 chars): `"Google LLC"` → `"google"`

When multiple employers share a key (e.g., `"meta"` matching both Meta Platforms and unrelated `"META IT CORP"`), the export resolves collisions by keeping the employer with the **highest `lca_count`** — a frequency-based disambiguation heuristic.

---

## Layer 3: Chrome Extension (Client Runtime)

### Manifest V3 Structure

| Component | Role |
|-----------|------|
| `content.js` | Runs on LinkedIn company/job pages; extracts slug; handles SPA navigation |
| `lib/matcher.js` | Lookup engine with session cache + learned slug persistence |
| `styles.css` | Fixed-position badge overlay with confidence color coding |
| `data/employers.json.gz` | Web-accessible compressed employer index |
| `chrome.storage.local` | Device-local learned slug → FEIN mappings (not in git) |

Requires `storage` permission for learned slug persistence only. No network calls — fully offline after install.

### Lookup Cascade

Each page view resolves a company through a fixed-order pipeline. Earlier stages are cheaper and more reliable; later stages are fallbacks.

```
1. Session cache          slug + page name seen earlier this browser session?
2. Manual overrides       slug_overrides.json curated mappings
3. Learned slugs          chrome.storage.local entries from past high-confidence hits
4. Exact key index        normalize(slug / page name) → key_index → FEIN
5. Whole-word fuzzy       all slug tokens must match as complete words in employer name
6. Not found              no result ≥ confidence threshold
```

After stage 4 or 5 produces a **high-confidence exact match**, the slug may be written to `learned_slugs` (stage 3 on future visits). Fuzzy matches and low-confidence hits are never learned.

### Session Cache

An in-memory `Map` keyed by `slug|normalized_page_name` stores both hits and misses for the current browser session.

| Property | Detail |
|----------|--------|
| Scope | Current tab session only; cleared when the extension reloads |
| Stores | Full match results and `null` (not-found) |
| Purpose | Avoid repeated fuzzy scans when LinkedIn SPA navigation or DOM mutations re-trigger lookup for the same company |
| Cost | O(1) hash lookup vs. O(74K) fuzzy scoring |

Typical win: navigating between a job posting and a company page for the same employer, or LinkedIn re-rendering the page several times without a URL change.

### Learned Slug Memory

High-confidence exact matches are persisted to `chrome.storage.local` under `learned_slugs`:

```json
{
  "typeface": {
    "fein": "88-2469676",
    "employer_name": "Typeface Inc.",
    "learned_at": "2026-06-08T...",
    "method": "exact_key",
    "score": 95
  }
}
```

**Write criteria (all must pass):**

| Rule | Reason |
|------|--------|
| `confidence === "high"` | No medium/low results stored |
| Method is `exact_key` or `exact_page_name` | Fuzzy guesses are never learned |
| LinkedIn name overlap ≥ 34% with LCA legal name | Prevents learning mismatched pairs |
| No "looks different" warning | Name disagreement blocks persistence |

**Why this improves accuracy:** fuzzy matching is heuristic and can false-positive (e.g., `coppersmith` once matched `rsm` via substring). Learned slugs convert a verified slug into an O(1) exact lookup on subsequent visits — the same path `google` uses on first load.

**Why this improves speed:** learned hits skip the O(74K) fuzzy scan entirely, even across browser sessions (unlike session cache).

Manual overrides in `slug_overrides.json` take precedence and ship with the extension. Learned slugs are device-local corrections discovered during normal use.

### Match Verification on the Badge

The badge surfaces enough signal to judge correctness without external tools:

| UI element | Meaning |
|------------|---------|
| **Green badge** | High confidence — safe to trust initially |
| **Yellow badge** | Medium/low confidence or name mismatch — verify manually |
| **Red badge** | Not found — no confident match in index |
| **LinkedIn vs LCA legal name** | Side-by-side comparison; unrelated names indicate a false positive |
| **Match method** | `Exact slug` > `Learned slug` > `Fuzzy` in reliability |
| **Score / 100** | ≥90 high · 60–89 medium · fuzzy floor is 60 |
| **Warnings list** | Explicit reasons to distrust the result |
| **FEIN** | Cross-check against DOL disclosure or local SQLite |

**False positive signals:** yellow badge, fuzzy method, LinkedIn name ≠ LCA legal name, implausible employer for the industry (e.g., a furniture company resolving to an accounting firm).

**False negative signals:** red badge on a company known to sponsor — likely slug/legal-name mismatch; add a manual override or wait for a learned mapping after verifying FEIN.

### Entity Resolution Pipeline

Matching LinkedIn identity to LCA identity is an **entity resolution** problem, not exact string equality:

```
Input:  linkedin.com/company/dun-bradstreet
LCA:    "Dun & Bradstreet, Inc."  (FEIN 22-3582360)

LinkedIn slug ≠ legal name ≠ DBA ≠ subsidiary name
```

The matcher applies a **cascading resolution strategy** (see Lookup Cascade above). Whole-word token matching replaced naive substring matching after a documented false positive where `coppersmith` contained the character sequence `rsm`, incorrectly resolving to RSM US LLP.

```
1. Session cache hit       return immediately
2. slug_overrides          manual curated slug → FEIN
3. learned_slugs           device-local verified slug → FEIN
4. Exact key index         normalize(slug / h1) → key_index
5. Whole-word fuzzy        every slug token must appear as a complete word
6. Not found
```

This is intentionally conservative: false positives are reduced by preferring exact paths and never learning fuzzy results; false negatives occur when slug and legal name diverge with no override or learned entry.

---

## Key Design Trade-offs (Interview Talking Points)

### Why not query SQLite from the extension?

Browser extensions cannot access the local filesystem. Options considered:

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Localhost FastAPI | Full SQL, always fresh | Must run server; friction for daily use | Rejected for v1 |
| Cloud DB (Supabase) | Accessible anywhere | Upload PII-adjacent data; latency; cost | Rejected |
| **Bundled JSON index** | Zero ops, offline, instant | Stale until re-export; ~7 MB install size | **Chosen** |

### Why deduplicate by FEIN, not employer name?

Same company appears under multiple names (`Google LLC`, `Google Public Sector LLC`, `Meta Platforms, Inc.` vs `Meta Platforms, Inc.` with trailing period). FEIN is the legal entity identifier; name is a display attribute. Aggregation by FEIN prevents splitting stats across aliases.

### Why precompute `key_index` instead of scanning 74K records client-side?

74K linear scans per page load would work (~1–5 ms in JS) but 173K key lookups with hash-map access is O(1) per candidate and simpler to reason about. The inverted index is built once at export time; the client only reads.

### Why not ship all 807K LCA rows?

Full row set is ~36 MB+ JSON, mostly redundant for the UX question ("does this company sponsor?"). The aggregated index answers the question in <50 KB per lookup result. Raw rows remain in local SQLite for ad-hoc SQL analysis outside the extension.

### LinkedIn as a single-page application (SPA)

LinkedIn does not trigger full page reloads on in-app navigation. `content.js` uses a `MutationObserver` on `document.body` and resets state on `popstate` to re-run matching when the URL slug changes — otherwise the badge would show stale results from the previous company.

---

## Data Provenance

| Attribute | Value |
|-----------|-------|
| Source | DOL Office of Foreign Labor Certification — LCA Disclosure Data |
| Period | FY2026 Q2 |
| Raw filings | 806,939 LCA records |
| Unique employers (FEIN) | 74,732 |
| Unique employer names | 85,847 |
| Index search keys | 173,406 |

LCA filings represent employer **attestations** of intent to employ H-1B workers at a stated wage — not confirmed hires, not H-1B lottery outcomes. A company with LCA records has historically engaged the sponsorship process; absence of records does not prove non-sponsorship (may file under a parent entity or PEO).

---

## Technology Stack

| Layer | Technology | Why |
|-------|------------|-----|
| Excel ingestion | python-calamine | Rust performance for large xlsx |
| Storage | SQLite 3 | Embedded, indexed, zero-config |
| Index serialization | JSON + gzip | Browser-native decompression; git-friendly size |
| Extension | Chrome Manifest V3 | Content scripts, no persistent background page |
| Matching | Custom normalizer + inverted index | Domain-specific entity resolution without ML overhead |

---

## License

MIT — DOL public data subject to federal open-data terms.
