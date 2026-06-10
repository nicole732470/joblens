#!/usr/bin/env python3
"""Deprecated wrapper — websites live in cook_county_companies.csv only."""

from cook_county_websites import CSV_PATH, enrich_csv

if __name__ == "__main__":
    filled, total = enrich_csv()
    print(f"Done: {filled}/{total} companies have websites in {CSV_PATH.name}")
