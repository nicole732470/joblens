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
│  matcher.js loads + decompresses index (DecompressionStream)          │
│       │  multi-stage entity resolution                              │
│       ▼                                                             │
│  Badge UI injected into page (LCA count, H-1B count, top roles)     │
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
| `content.js` | Runs on `linkedin.com/company/*`; extracts slug from URL; handles LinkedIn SPA navigation via `MutationObserver` + `popstate` |
| `lib/matcher.js` | Singleton lookup engine; lazy-loads and caches decompressed index |
| `styles.css` | Fixed-position badge overlay (z-index 99999) |
| `data/employers.json.gz` | Web-accessible resource declared in `manifest.json` |

No background service worker, no `host_permissions` beyond LinkedIn, no network calls — fully offline after install.

### Entity Resolution Pipeline

Matching LinkedIn identity to LCA identity is an **entity resolution** problem, not exact string equality:

```
Input:  linkedin.com/company/dun-bradstreet
LCA:    "Dun & Bradstreet, Inc."  (FEIN 22-3582360)

LinkedIn slug ≠ legal name ≠ DBA ≠ subsidiary name
```

The matcher applies a **cascading resolution strategy**:

```
1. Slug override table     slug_overrides["dun-bradstreet"] → FEIN → employer record
2. Exact key index lookup  normalize(slug) → key_index → feinMap
3. H1 fallback             read page <h1> company name, repeat step 2
4. Substring fuzzy match   bidirectional contains on normalized tokens;
                           tie-break by highest lca_count
```

This is intentionally conservative: false positives (wrong company) are reduced by preferring high-volume filers; false negatives (company not found) occur when slug and legal name diverge with no override entry.

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
