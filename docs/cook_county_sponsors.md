# Cook County H-1B Sponsors (FY2026 Q2)

Companies with H-1B LCA filings where the **worksite** is in **Cook County, Illinois** (Chicago and immediate suburbs within the county).

## Geographic Scope

| Scope | H-1B LCA Filings | Unique Employers |
|-------|------------------:|-----------------:|
| **Cook County only** | **9,708** | **2,635** |

> Excludes DuPage, Lake, Will, Kane, McHenry and all non-IL worksites.  
> 2,635 is **not** every company in Cook County — only employers that filed at least one H-1B LCA with a Cook County worksite during FY2026 Q2.

## Data Files

| File | Rows | Description |
|------|-----:|-------------|
| [`data/cook_county_lca_full.csv`](../data/cook_county_lca_full.csv) | **9,708** | **Full LCA records, all 98 DOL columns** (one row per filing) |
| [`data/cook_county_companies.csv`](../data/cook_county_companies.csv) | 2,635 | Employer summary (aggregated by FEIN) |

Regenerate: `python export_cook_county.py`

---

## Top 50 Employers by LCA Count

| # | Employer | LCA |
|--:|----------|----:|
| 1 | Ernst & Young U.S. LLP | 517 |
| 2 | Northwestern University | 254 |
| 3 | The University of Chicago | 245 |
| 4 | Cognizant Technology Solutions US Corp | 198 |
| 5 | Tata Consultancy Services Limited | 161 |
| 6 | Grandison Management, Inc. | 154 |
| 7 | Deloitte Consulting LLP | 144 |
| 8 | Capgemini America Inc | 131 |
| 9 | Medline Industries, LP | 124 |
| 10 | JPMorgan Chase & Co. | 95 |
| 11 | Google LLC | 86 |
| 12 | University of Illinois Chicago | 81 |
| 13 | Accenture LLP | 75 |
| 14 | Bitwise Inc. | 74 |
| 15 | PricewaterhouseCoopers Advisory Services LLC | 66 |
| 16 | Boston Consulting Group, Inc. | 65 |
| 17 | Infosys Limited | 64 |
| 18 | Deloitte Tax LLP | 59 |
| 19 | Cook County Health | 55 |
| 20 | IBM Corporation | 51 |
| 21 | Rush University Medical Center | 46 |
| 22 | The Northern Trust Company | 46 |
| 23 | Amazon.com Services LLC | 41 |
| 24 | ZS Associates Inc. | 41 |
| 25 | Caterpillar Inc. | 39 |
| 26 | Zurich American Insurance Company | 39 |
| 27 | Chicago Mercantile Exchange Inc. | 38 |
| 28 | PayPal, Inc. | 37 |
| 29 | Deloitte & Touche LLP | 37 |
| 30 | Expedia, Inc. | 36 |
| 31 | Motorola Solutions, Inc. | 36 |
| 32 | Chicago Public Schools | 32 |
| 33 | SLK America Inc | 30 |
| 34 | Wipro Limited | 30 |
| 35 | TheMathCompany, Inc. | 30 |
| 36 | Compunnel Software Group, Inc | 29 |
| 37 | The Options Clearing Corporation | 29 |
| 38 | Loyola University Chicago | 29 |
| 39 | Resilience Healthcare Chicago Graduate Education Foundation | 28 |
| 40 | Tempus AI | 28 |
| 41 | Neosis IT Solutions LLC | 28 |
| 42 | Hexaware Technologies, Inc. | 27 |
| 43 | Amazon Web Services, Inc. | 27 |
| 44 | TransUnion LLC | 26 |
| 45 | Health Care Service Corporation | 26 |
| 46 | Akuna Capital, LLC | 26 |
| 47 | McKinsey & Company, Inc. United States | 26 |
| 48 | Microsoft Corporation | 25 |
| 49 | Northwestern Memorial HealthCare | 25 |
| 50 | University of Chicago Medical Center | 24 |

See CSV for certified counts, worksite cities, and all 2,635 employers.

---

## Industry Mix in Cook County

Compared to national H-1B distribution, Cook County skews toward:

- **Consulting / IT services** (EY, Cognizant, TCS, Infosys, Accenture, Capgemini)
- **Universities & healthcare** (Northwestern, UChicago, UIC, Rush, Loyola)
- **Finance / trading** (JPMorgan, Northern Trust, CME, Akuna, OCC)
- **Tech & corporate HQs** (Google, Amazon, Motorola, Caterpillar, PayPal, Expedia)

---

## Notes

- List is based on **worksite location** (`WORKSITE_COUNTY = COOK`), not employer headquarters.
- Dataset is **H-1B only** (E-3 / H-1B1 excluded).
- `lca_count` is number of LCA filings, not number of workers hired.
