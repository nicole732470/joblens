# H-1B employer index

`employers.json.gz` is the legacy committed seed input for
`data-pipeline/load_to_postgres.py`. It is generated from the local DOL/LCA
pipeline by `export_employer_index.py`.

The Chrome extension does not load this file at runtime. Production H-1B
lookups use the Postgres tables seeded from it.

For new JobPush-ready data work, the preferred path is the cleaned canonical
Excel workbook:

```text
/Users/nicole/Desktop/APPLY/jobpush/LCA_H1B_FY2025_FY2026_Q2.xlsx
  -> data-pipeline/load_lca_excel_to_postgres.py
  -> RDS Postgres
```

That loader writes the full filing-level table (`lca_cases`) and derives the
existing sponsorship lookup tables (`companies`, `company_aliases`,
`company_search_keys`) from the same source. The JSON file remains useful for
quick rebuilds or rollback of the old FEIN-level sponsorship index, but it is
not the runtime database.

See [`docs/DATABASE.md`](../../docs/DATABASE.md) for the current table
relationships and mapping rules.
