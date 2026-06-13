# LCA Sponsor Checker

Cross-reference LinkedIn company pages against U.S. Department of Labor (DOL) H-1B Labor Condition Application (LCA) disclosure data — fully offline, no backend.

LinkedIn exposes a **URL slug** and a **display name**. DOL records use **legal entity names** and **FEINs**. There is no shared identifier between the two systems, so matching is an **entity resolution** problem solved with a conservative lookup pipeline and human-verifiable signals on the badge.

**Data:** DOL LCA Disclosure · FY2026 Q2 · 785,687 H-1B filings · 69,250 employers (by FEIN)  
**Extension:** Chrome Manifest V3 · index v1.1 · extension v1.5.1

---

## Quick start

### Use the extension (pre-built index included)

The repo ships `chrome-extension/data/employers.json.gz`. You only need Chrome — no Python, no server.

```bash
git clone https://github.com/nicole732470/lca-linkedin-checker.git
cd lca-linkedin-checker
```

1. Open `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select the `chrome-extension/` folder
4. Visit any [LinkedIn company page](https://www.linkedin.com/company/) or job posting

A badge appears in the corner: **green** = confident LCA match, **yellow** = verify manually, **red** = no match in the index.

### Rebuild the index from DOL data (optional)

Download the latest [LCA Disclosure Data](https://www.dol.gov/agencies/eta/foreign-labor/performance) Excel file from DOL and place it in the repo root (default expected name: `LCA_Dislclosure_Data_FY2026_Q2.xlsx`). Then:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python3 convert_to_sqlite.py       # Excel → lca_fy2026_q2.db (~1 min)
python3 export_employer_index.py   # SQLite → chrome-extension/data/employers.json.gz
```

Reload the extension on `chrome://extensions` after re-exporting.

**Test a slug without re-exporting** (uses existing `employers.json` if present):

```bash
python3 export_employer_index.py --test microsoft
python3 export_employer_index.py --test eversana
```

### Add a manual slug override

When LinkedIn’s slug does not map cleanly to a legal name, edit `slug_overrides.json`, then re-run `export_employer_index.py`:

```json
{
  "your-linkedin-slug": "XX-XXXXXXX"
}
```

FEIN comes from the DOL file or your local SQLite DB (`SELECT DISTINCT EMPLOYER_FEIN, EMPLOYER_NAME FROM lca_cases WHERE …`).

---

## End-to-end data flow

```mermaid
flowchart LR
  subgraph offline["Offline pipeline (Python)"]
    XLSX["DOL LCA Excel\n~440 MB"]
    SQLITE["SQLite\nlca_cases · ~786K rows"]
    INDEX["employers.json.gz\n~6.4 MB · 69K employers"]
    XLSX -->|"convert_to_sqlite.py\npython-calamine"| SQLITE
    SQLITE -->|"export_employer_index.py\nSQL aggregation + key_index"| INDEX
    OVERRIDES["slug_overrides.json"] --> INDEX
  end

  subgraph browser["Browser runtime (Chrome MV3)"]
    LI["linkedin.com/company/{slug}\nor job posting"]
    DOM["content.js\nextract slug + page name"]
    MATCH["matcher.js\nlookup cascade"]
    UI["Badge overlay\nconfidence · industry · alternatives"]
    INDEX --> MATCH
    LI --> DOM --> MATCH --> UI
    STORAGE[("chrome.storage.local\nlearned slugs")] <--> MATCH
  end
```

Raw `.xlsx` and `.db` files are gitignored (too large). The extension ships only the compressed index.

---

## Company identification workflow

On each LinkedIn company or job page, the extension extracts a **slug** (from the URL or company link) and optionally a **display name** (from the page heading or job card). Those inputs feed a fixed-order resolver — **first hit wins**; later stages run only when earlier ones miss.

**Lookup cascade** (left → right):

```mermaid
flowchart LR
  IN["slug + page name"] --> S1["① Cache"]
  S1 --> S2["② Override"]
  S2 --> S3["③ Learned"]
  S3 --> S4["④ Exact key"]
  S4 --> S5["⑤ Fuzzy ≥70"]
  S5 --> S6["⑥ Not found"]

  S1 -.->|hit| BADGE(["Badge UI"])
  S2 -.->|hit| BADGE
  S3 -.->|hit| BADGE
  S4 -.->|hit| SCORE
  S5 -.->|hit| SCORE
  S6 --> BADGE
```

Stages ④ and ⑤ run through the **[confidence & scoring](#confidence--scoring)** pipeline before the badge is shown. High-confidence exact hits may be persisted as learned slugs.

### Why this order

| Stage | On hit | Why it runs before the next stage |
|-------|--------|-----------------------------------|
| **① Cache** | Same slug/name this session → return | Avoids repeat work on LinkedIn SPA re-renders |
| **② Override** | High confidence → badge | Curated slug → FEIN (`meta`, `eversana`, …) |
| **③ Learned** | High confidence → badge | Device-local slug verified on a prior visit |
| **④ Exact key** | Score → confidence → badge | O(1) hash lookup on precomputed keys |
| **⑤ Fuzzy** | Score ≥ 70 → confidence → badge | Last resort; whole-word tokens only |
| **⑥ Not found** | Red badge | No match above threshold |

Fuzzy matches are **never learned**. Only high-confidence exact paths with sufficient LinkedIn ↔ LCA name overlap are written to `chrome.storage.local`.

### Search key policy (export time)

Earlier versions generated single-token keys like `gamma` or `american`, causing thousands of collisions. Index v1.2 key policy:

- Multi-word legal names and hyphenated slugs (`ornua-foods-north-america-inc`) always indexed
- Short brand tokens (≥4 chars, e.g. `ornua`, `coforge`) indexed only when **≤5 employers** share that token — avoids `american` / `university` collisions
- Generic words (`gamma`, `hiring`, `global`, …) never indexed as single-token keys

Collisions on the same key resolve to the employer with the **highest `lca_count`**.

---

## Confidence & scoring

This is **not** machine learning and **not** a sponsorship probability. The matcher produces two separate outputs:

| Output | What it measures | Used for |
|--------|------------------|----------|
| **`score`** (0–100) | How closely the **LinkedIn URL tokens** match an employer’s legal names / search keys | Whether fuzzy matching qualifies; ranking alternatives |
| **`confidence`** (`high` / `medium` / `low`) | Whether we trust that employer is the **same entity** LinkedIn is showing | Badge color (green vs yellow) |

**Red (not found)** means `lookup()` returned `null` — no employer reached score ≥ 70 on the fuzzy path, and no exact / override / learned hit.

### Step 1 — Match score (URL vs LCA names)

Only stages **④ exact key** and **⑤ fuzzy** compute a numeric score. Overrides and learned slugs are assigned **100**; exact index hits are assigned **95** before confidence rules run.

**Fuzzy scoring** compares normalized LinkedIn URL tokens against each employer’s legal name, aliases, and precomputed keys. Matching uses **whole words** (`\b token \b`), not arbitrary substrings — so `coppersmith` cannot match `RSM` via an embedded character sequence.

```mermaid
flowchart LR
  T["URL tokens"] --> E{"Exact normalized\nstring match?"}
  E -->|yes| S100["score 100"]
  E -->|no| M{"Every token\nwhole-word hit?"}
  M -->|"2+ tokens"| S75["75 + 5×tokens\ncapped at 95"]
  M -->|"1 token, len ≥ 6"| S70["score 70"]
  M -->|miss| S0["score 0"]
  S0 --> NF["🔴 not found"]
  S70 --> OK{"score ≥ 70?"}
  S75 --> OK
  S100 --> OK
  OK -->|yes| CONF["→ Step 2"]
```

| Fuzzy case | Score | Example |
|------------|-------|---------|
| Normalized URL equals a stored name/key | 100 | rare on fuzzy path; usually caught at exact key |
| All URL tokens appear as whole words (2 tokens) | 85 | `gamma-technologies` → “Gamma Technologies …” |
| All URL tokens (3 tokens) | 90 | |
| All URL tokens (4+ tokens) | 95 | |
| Single token, length ≥ 6, whole-word hit | 70 | minimum to qualify |
| Anything else | 0 → **not found** | bare `gamma` after key tightening |

Candidates with score ≥ **70** are ranked by score, then by `lca_count`. The top hit is returned; runners-up may appear as **alternatives** on yellow badges.

### Step 2 — Confidence (display name vs legal name)

After an employer is selected, `confidence` starts at **high** and is adjusted:

```mermaid
flowchart LR
  IN["score + method"] --> B["Bucket by score\n(not override)"]
  B --> B90["≥90 → high"]
  B --> B75["75–89 → medium"]
  B --> B70["70–74 → low"]
  B90 --> ADJ
  B75 --> ADJ
  B70 --> ADJ["Adjustments"]
  ADJ --> BR{"Brand subset?\npage name ⊂ legal name"}
  BR -->|yes| HI["→ high + note"]
  BR -->|no| OV{"Display-name overlap\n< 34%?"}
  OV -->|yes| DOWN["high→medium\nmedium→low"]
  OV -->|no| KEEP["keep bucket"]
  HI --> OUT
  DOWN --> OUT
  KEEP --> OUT["confidence"]
  OUT --> G{"level?"}
  G -->|high| GREEN["🟢 badge"]
  G -->|medium / low| YELLOW["🟡 badge"]
```

**Score → initial bucket** (skipped for `manual_override`):

| Score | Initial confidence |
|-------|-------------------|
| ≥ 90 | `high` |
| 75 – 89 | `medium` |
| 70 – 74 | `low` |

**Adjustments** (applied in order):

| Rule | Condition | Effect |
|------|-----------|--------|
| **Brand subset** | Every token in the LinkedIn **display name** appears in the LCA **legal name**, and the display name is shorter | Promote `medium` / `low` → `high`; add explanatory note (e.g. `EVERSANA` → `EVERSANA LIFE SCIENCE SERVICES, LLC`) |
| **Name overlap** | Token overlap between display name and legal name &lt; **34%** (tokens length ≥ 3) | `high` → `medium`, or `medium` → `low`; add name-mismatch warning |
| **Fuzzy method** | `fuzzy_token` or `fuzzy_single` | Add “confirm legal name and industry” warning (does not by itself change the bucket) |

**Display-name overlap** is separate from match score:

```
overlap = shared_tokens / max(linkedin_tokens, legal_tokens)
```

Example: LinkedIn shows `Vertex Pharmaceuticals`, LCA lists `Vertex Pharmaceuticals Incorporated` → overlap **100%** → no downgrade. LinkedIn shows `Acme`, LCA lists `Totally Different Industries LLC` → low overlap → downgrade even if the URL matched.

### Badge colors

| Badge | `confidence` | Typical situation |
|-------|--------------|-------------------|
| 🟢 **Green** | `high` | Exact index hit (score 95) with agreeing names; or strong fuzzy (score ≥ 90); or brand subset |
| 🟡 **Yellow** | `medium` or `low` | Fuzzy match at 70–89; or exact hit but display name ≠ legal name; alternatives shown |
| 🔴 **Red** | no result | No match, or fuzzy score &lt; 70 |

### Warnings (do not change the color)

These lines appear on the badge but **do not** switch green ↔ yellow ↔ red:

| Warning | Trigger |
|---------|---------|
| Very few LCA filings | `lca_count ≤ 2` — weak historical signal |
| Other possible matches | Alternatives exist and confidence is not `high` |
| Matched from learned slug | Slug was verified on this device earlier |

### Persistence (learned slugs)

A slug is saved to `chrome.storage.local` only when **all** of the following hold:

- `confidence === high` after adjustments
- Method is `exact_key` or `exact_page_name` (never fuzzy)
- No display-name mismatch warning
- Display-name overlap ≥ **34%**

### What green / yellow do *not* mean

Green or yellow means the **legal entity** appears in LCA disclosure data. It does **not** mean this specific job posting sponsors H-1B — the JD may still exclude internships, entry-level roles, or candidates who need sponsorship.

Implementation: `chrome-extension/lib/matcher.js` — `scoreEmployer()`, `nameOverlap()`, `isBrandSubset()`, `buildResult()`.

---

## Repository layout

```
.
├── convert_to_sqlite.py          # Excel → SQLite ingestion
├── export_employer_index.py      # SQLite → compressed JSON index
├── naics_sectors.py              # NAICS code → sector label
├── slug_overrides.json           # Curated LinkedIn slug → FEIN
├── requirements.txt
├── export_all_employers.py       # National employer CSV (69K, networking columns)
├── export_cook_county.py         # Cook County IL sponsor export
├── networking_connects.py        # Log / sync LinkedIn connect outreach
├── export_distribution.py        # National job/SOC distribution CSVs
├── data/
│   ├── all_employers.csv         # National summary + connect_status
│   ├── cook_county_companies.csv # Cook County subset
│   └── networking_connects.csv   # Connect log (source of truth)
├── docs/                         # Distribution summaries
└── chrome-extension/
    ├── manifest.json
    ├── content.js                # DOM extraction + badge UI
    ├── styles.css
    ├── lib/matcher.js            # Lookup engine
    └── data/employers.json.gz    # Pre-built index (~6.4 MB)
```

---

## Layer 1: Ingestion (Excel → SQLite)

DOL publishes LCA data as flat Excel. The FY2026 Q2 file is ~440 MB, ~807K rows × 98 columns; import filters to **785,687 H-1B** rows only.

| Decision | Rationale |
|----------|-----------|
| **python-calamine** | Rust-backed reader; ~47 s vs minutes with openpyxl |
| **SQLite** | Indexed random lookups; single-file portability for local SQL |
| **Batch insert + post-load indexes** | 13 indexes on filter columns after bulk load |
| **TEXT columns** | Mixed formats in source fields; avoids silent coercion |

Employers deduplicate by **FEIN**: 79,492 distinct names → **69,250** legal entities.

---

## Layer 2: Index export (SQLite → JSON)

The browser cannot read a ~940 MB SQLite file. Export aggregates per FEIN and ships a read-optimized artifact:

| Field | Purpose |
|-------|---------|
| `fein` | Stable legal-entity key |
| `name` / `names[]` | Primary and alias employer names |
| `search_keys[]` | Precomputed lookup tokens (strict policy above) |
| `lca_count`, `h1b_count`, `certified_count` | Headline sponsorship signals |
| `naics_code`, `naics_sector` | Industry context for verification |
| `top_jobs[]` | Top 3 roles by filing frequency |
| `key_index` | Inverted map `normalized_key → fein` |
| `slug_overrides` | Bundled manual slug → FEIN mappings |

Top jobs use one SQL window query (`ROW_NUMBER() OVER (PARTITION BY EMPLOYER_FEIN …)`). Raw JSON ~36 MB compresses to **~6.4 MB gzip** with **124,926** search keys.

---

## Layer 3: Chrome extension

| Component | Role |
|-----------|------|
| `content.js` | Extracts slug/name from company and job pages; `MutationObserver` + `popstate` for LinkedIn SPA navigation |
| `matcher.js` | Loads gzip index; runs lookup cascade; session cache + learned slug persistence |
| `styles.css` | Fixed badge: confidence, legal name, industry, warnings, alternatives |
| `employers.json.gz` | Web-accessible compressed index — no network calls after install |

**Permissions:** `storage` only (learned slugs). No telemetry, no remote API.

### Manual overrides

When slug and legal name diverge with no safe automatic key, add an entry to `slug_overrides.json` and re-export:

```json
{
  "eversana": "39-1821626",
  "meta": "20-1665019",
  "dun-bradstreet": "22-3582360"
}
```

---

## Data provenance

| Attribute | Value |
|-----------|-------|
| Source | DOL Office of Foreign Labor Certification — LCA Disclosure Data |
| Period | FY2026 Q2 |
| H-1B LCA records | 785,687 |
| Unique employers (FEIN) | 69,250 |
| Index search keys | 124,926 |

LCA filings are employer **attestations** of intent to employ H-1B workers — not confirmed hires or lottery outcomes. A company may file under a parent entity, PEO, or a name not visible on LinkedIn.

---

## Technology stack

| Layer | Technology |
|-------|------------|
| Excel ingestion | python-calamine (Rust via PyO3) |
| Storage | SQLite 3 |
| Index | JSON + gzip · browser `DecompressionStream` |
| Extension | Chrome Manifest V3 |
| Matching | Normalizer + inverted index + conservative fuzzy · no ML |

---

## License

MIT — DOL public data subject to federal open-data terms.
