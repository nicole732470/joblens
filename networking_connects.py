#!/usr/bin/env python3
"""Track LinkedIn connect / networking outreach by employer FEIN."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONNECTS_PATH = BASE_DIR / "data" / "networking_connects.csv"
COMPANIES_PATH = BASE_DIR / "data" / "cook_county_companies.csv"

FIELDNAMES = ["fein", "employer_name", "status", "sent_date", "notes"]


def load_connects() -> dict[str, dict[str, str]]:
    if not CONNECTS_PATH.exists():
        return {}
    with CONNECTS_PATH.open(newline="", encoding="utf-8") as f:
        return {row["fein"]: row for row in csv.DictReader(f)}


def save_connects(rows: dict[str, dict[str, str]]) -> None:
    CONNECTS_PATH.parent.mkdir(exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r.get("sent_date", ""), r["fein"]), reverse=True)
    with CONNECTS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(ordered)


def log_connect(
    fein: str,
    employer_name: str,
    *,
    status: str = "sent",
    sent_date: str | None = None,
    notes: str = "",
) -> dict[str, str]:
    rows = load_connects()
    row = {
        "fein": fein.strip(),
        "employer_name": employer_name.strip(),
        "status": status.strip(),
        "sent_date": sent_date or date.today().isoformat(),
        "notes": notes.strip(),
    }
    rows[row["fein"]] = row
    save_connects(rows)
    return row


def connect_status_map() -> dict[str, str]:
    return {fein: row["status"] for fein, row in load_connects().items()}


def merge_into_companies_csv(companies_path: Path = COMPANIES_PATH) -> int:
    """Add/update connect_status column in cook_county_companies.csv from networking log."""
    if not companies_path.exists():
        return 0
    status_by_fein = connect_status_map()
    rows: list[dict[str, str]] = []
    with companies_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = [c for c in (reader.fieldnames or []) if c != "connect_status"]
        if "connect_status" not in fieldnames:
            fieldnames.append("connect_status")
        for row in reader:
            row["connect_status"] = status_by_fein.get(row["fein"], "")
            rows.append(row)
    with companies_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return sum(1 for r in rows if r.get("connect_status"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Log LinkedIn connect outreach by FEIN")
    sub = parser.add_subparsers(dest="cmd", required=True)

    add_p = sub.add_parser("add", help="Mark a company as connect sent")
    add_p.add_argument("fein", help="Employer FEIN, e.g. 20-2079434")
    add_p.add_argument("employer_name", help="Employer name")
    add_p.add_argument("--status", default="sent", help="sent / accepted / follow_up")
    add_p.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    add_p.add_argument("--notes", default="", help="Optional note")

    sub.add_parser("list", help="Show all logged connects")
    sub.add_parser("sync", help="Refresh connect_status column in cook_county_companies.csv")

    args = parser.parse_args()

    if args.cmd == "add":
        row = log_connect(
            args.fein,
            args.employer_name,
            status=args.status,
            sent_date=args.date or None,
            notes=args.notes,
        )
        marked = merge_into_companies_csv()
        print(f"Logged {row['employer_name']} ({row['fein']}) → {row['status']} on {row['sent_date']}")
        print(f"Updated cook_county_companies.csv — {marked} row(s) with connect_status")

    elif args.cmd == "list":
        rows = load_connects()
        if not rows:
            print("No connects logged yet.")
            return
        for row in sorted(rows.values(), key=lambda r: r["sent_date"], reverse=True):
            note = f" — {row['notes']}" if row.get("notes") else ""
            print(f"{row['sent_date']}  {row['status']:10}  {row['fein']}  {row['employer_name']}{note}")

    elif args.cmd == "sync":
        marked = merge_into_companies_csv()
        print(f"Synced connect_status into cook_county_companies.csv — {marked} marked")


if __name__ == "__main__":
    main()
