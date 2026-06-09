# Chicago Metro H-1B Sponsors (FY2026 Q2)

Companies with H-1B LCA filings where the **worksite** is in the Chicago metropolitan area.

## Geographic Scope

Counties included (Chicago-Naperville-Elgin MSA core):

| County | H-1B LCA Filings |
|--------|----------------:|
| Cook | 9,708 |
| DuPage | 2,066 |
| Lake | 1,917 |
| Will | 381 |
| Kane | 219 |
| McHenry | 52 |

**Totals (all visa types):** 14,555 LCA filings · 3,807 unique employers (by FEIN)

| Visa Class | Filings |
|------------|--------:|
| H-1B | 14,343 |
| E-3 Australian | 160 |
| H-1B1 Chile | 26 |
| H-1B1 Singapore | 26 |

**H-1B only:** 3,730 unique employers (aggregated summary)

> Excludes downstate Illinois worksites (e.g., Bloomington, Peoria, Champaign).  
> 3,730 is **not** every company in Chicagoland — only employers that filed at least one H-1B LCA with a worksite in these six counties during FY2026 Q2.

## Data Files

| File | Rows | Description |
|------|-----:|-------------|
| [`data/chicago_metro_lca_full.csv`](../data/chicago_metro_lca_full.csv) | **14,555** | **Full LCA records, all 98 DOL columns** (one row per filing) |
| [`data/chicago_metro_companies.csv`](../data/chicago_metro_companies.csv) | 3,730 | H-1B employer summary (aggregated by FEIN) |

Regenerate: `python export_chicago_metro.py`

---

## Top 50 Employers by LCA Count

| # | Employer | LCA |
|--:|----------|----:|
| 1 | Ernst & Young U.S. LLP | 558 |
| 2 | Cognizant Technology Solutions US Corp | 449 |
| 3 | Tata Consultancy Services Limited | 310 |
| 4 | DFS Corporate Services LLC | 255 |
| 5 | Northwestern University | 254 |
| 6 | The University of Chicago | 245 |
| 7 | Grandison Management, Inc. | 224 |
| 8 | Medline Industries, LP | 215 |
| 9 | Capgemini America Inc | 192 |
| 10 | Deloitte Consulting LLP | 159 |
| 11 | Fermi Forward Discovery Group, LLC | 133 |
| 12 | Discover Products Inc | 120 |
| 13 | IBM Corporation | 108 |
| 14 | Infosys Limited | 106 |
| 15 | UChicago Argonne LLC | 98 |
| 16 | Accenture LLP | 97 |
| 17 | AbbVie Inc. | 96 |
| 18 | JPMorgan Chase & Co. | 95 |
| 19 | Google LLC | 87 |
| 20 | University of Illinois Chicago | 81 |
| 21 | Bitwise Inc. | 75 |
| 22 | The Northern Trust Company | 75 |
| 23 | PricewaterhouseCoopers Advisory Services LLC | 66 |
| 24 | Boston Consulting Group, Inc. | 65 |
| 25 | Deloitte Tax LLP | 62 |
| 26 | Cook County Health | 55 |
| 27 | Amazon.com Services LLC | 52 |
| 28 | Rush University Medical Center | 46 |
| 29 | Motorola Solutions, Inc. | 43 |
| 30 | Tech Mahindra (Americas), Inc | 43 |
| 31 | Compunnel Software Group, Inc | 42 |
| 32 | Wipro Limited | 41 |
| 33 | ZS Associates Inc. | 41 |
| 34 | Caterpillar Inc. | 40 |
| 35 | Zurich American Insurance Company | 40 |
| 36 | Deloitte & Touche LLP | 40 |
| 37 | Skilltune Technologies Inc | 38 |
| 38 | Chicago Mercantile Exchange Inc. | 38 |
| 39 | PayPal, Inc. | 37 |
| 40 | Expedia, Inc. | 36 |
| 41 | HCL America Inc | 34 |
| 42 | Caremark LLC | 32 |
| 43 | Microsoft Corporation | 32 |
| 44 | Chicago Public Schools | 32 |
| 45 | Northwestern Memorial HealthCare | 32 |
| 46 | Amazon Web Services, Inc. | 32 |
| 47 | SLK America Inc | 30 |
| 48 | Abbott Laboratories | 30 |
| 49 | TheMathCompany, Inc. | 30 |
| 50 | Egen Solutions LLC | 29 |

See CSV for certified counts, worksite cities, and all 3,730 employers.

---

## Industry Mix in Chicago Metro

Compared to national H-1B distribution, Chicago metro skews toward:

- **Consulting / IT services** (EY, Cognizant, TCS, Infosys, Accenture, Capgemini)
- **Universities & research** (Northwestern, UChicago, UIC, Argonne, Fermilab)
- **Healthcare / pharma** (AbbVie, Medline)
- **Finance** (Discover, Northern Trust, JPMorgan, CME)
- **Corporate HQs** (McDonald's, Walgreens, United, Allstate, Caterpillar, Motorola)

---

## Notes

- List is based on **worksite location**, not employer headquarters.
- A company may appear because it has employees working in Chicagoland, even if HQ is elsewhere.
- `lca_count` is number of LCA filings, not number of workers hired.
