# H-1B employer index

`employers.json.gz` is the committed, reproducible input for
`data-pipeline/load_to_postgres.py`. It is generated from the local DOL/LCA
pipeline by `export_employer_index.py`.

The Chrome extension does not load this file at runtime. Production H-1B
lookups use the Postgres tables seeded from it.
