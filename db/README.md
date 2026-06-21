# Database schema

`schema.sql` defines the H-1B/LCA company data tables used by JobLens and the
future JobPush workflow. It is safe to re-run and is applied during EC2
redeploy.

## Core H-1B / company tables

| Table | Role |
|-------|------|
| `lca_cases` | Full cleaned Excel data. One row per H-1B/LCA filing. |
| `companies` | FEIN-deduped legal employer entities. Existing sponsorship lookup stays here. |
| `company_aliases` | Alternate names / DBA / spelling variants for a FEIN. |
| `company_search_keys` | Normalized resolver keys used by the backend to match a company name to FEIN. |
| `company_groups` | Optional brand/group/family layer for parent brands, university systems, hospital systems, etc. |
| `company_group_companies` | Many-to-many mapping between `company_groups` and FEIN entities in `companies`. |
| `company_websites` | Website/career URLs. A URL can attach to a FEIN, a company group, or both. |

## Mapping model

The schema intentionally separates legal entities, brands/groups, and websites:

```text
lca_cases.employer_fein -> companies.fein
companies.fein -> company_aliases.fein
companies.fein -> company_search_keys.fein
company_groups <-> companies via company_group_companies
company_websites -> companies.fein and/or company_groups.company_group_id
```

This avoids assuming one-to-one mappings. In real LCA data:

- one FEIN can have many employer names or DBA values;
- many FEINs can belong to one brand/group;
- one website/careers page can represent a broader group instead of one FEIN.

## Runtime vs seed data

The extension and API do not read `data/h1b/employers.json.gz` at runtime.
Runtime lookup goes through RDS Postgres.

For full JobPush-ready data refreshes, use:

```bash
DATABASE_URL="postgresql://..." \
  python3 data-pipeline/load_lca_excel_to_postgres.py
```

The legacy lightweight loader remains:

```bash
DATABASE_URL="postgresql://..." \
  python3 data-pipeline/load_to_postgres.py
```

See `docs/DATABASE.md` for the broader persisted-data overview.
