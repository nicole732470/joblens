#!/usr/bin/env python3
"""Track LinkedIn connect / networking outreach by employer FEIN."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONNECTS_PATH = DATA_DIR / "networking_connects.csv"
ALL_EMPLOYERS_PATH = DATA_DIR / "all_employers.csv"
COOK_COUNTY_PATH = DATA_DIR / "cook_county_companies.csv"

CONNECT_FIELDNAMES = ["fein", "employer_name", "status", "sent_date", "notes"]

# Tables that receive connect_status / connect_sent_date / connect_notes on sync.
SYNC_TARGETS = (ALL_EMPLOYERS_PATH, COOK_COUNTY_PATH)


def load_connects() -> dict[str, dict[str, str]]:
    if not CONNECTS_PATH.exists():
        return {}
    with CONNECTS_PATH.open(newline="", encoding="utf-8") as f:
        return {row["fein"]: row for row in csv.DictReader(f)}


def save_connects(rows: dict[str, dict[str, str]]) -> None:
    CONNECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r.get("sent_date", ""), r["fein"]), reverse=True)
    with CONNECTS_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONNECT_FIELDNAMES)
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


def sync_connect_columns(csv_path: Path) -> int:
    """Merge networking log into connect_* columns; drop legacy website column if present."""
    if not csv_path.exists():
        return 0

    connects = load_connects()
    drop_cols = {"website", "connect_status", "connect_sent_date", "connect_notes"}
    rows: list[dict[str, str]] = []

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        base_fields = [c for c in (reader.fieldnames or []) if c not in drop_cols]
        fieldnames = base_fields + ["connect_status", "connect_sent_date", "connect_notes"]
        for row in reader:
            fein = row["fein"]
            conn = connects.get(fein, {})
            out = {k: row[k] for k in base_fields if k in row}
            out["connect_status"] = conn.get("status", "")
            out["connect_sent_date"] = conn.get("sent_date", "")
            out["connect_notes"] = conn.get("notes", "")
            rows.append(out)

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return sum(1 for r in rows if r.get("connect_status"))


def sync_all_tables() -> dict[str, int]:
    return {path.name: sync_connect_columns(path) for path in SYNC_TARGETS}


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
    sub.add_parser("sync", help="Refresh connect columns in all employer CSVs")

    args = parser.parse_args()

    if args.cmd == "add":
        row = log_connect(
            args.fein,
            args.employer_name,
            status=args.status,
            sent_date=args.date or None,
            notes=args.notes,
        )
        counts = sync_all_tables()
        print(f"Logged {row['employer_name']} ({row['fein']}) → {row['status']} on {row['sent_date']}")
        for name, n in counts.items():
            if Path(name).exists() or name in {p.name for p in SYNC_TARGETS}:
                print(f"  Updated {name} — {n} row(s) with connect_status")

    elif args.cmd == "list":
        rows = load_connects()
        if not rows:
            print("No connects logged yet.")
            return
        for row in sorted(rows.values(), key=lambda r: r["sent_date"], reverse=True):
            note = f" — {row['notes']}" if row.get("notes") else ""
            print(f"{row['sent_date']}  {row['status']:10}  {row['fein']}  {row['employer_name']}{note}")

    elif args.cmd == "sync":
        counts = sync_all_tables()
        for name, n in counts.items():
            print(f"Synced {name} — {n} marked")


if __name__ == "__main__":
    main()
