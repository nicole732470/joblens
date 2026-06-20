#!/usr/bin/env python3
"""Sync owner test account profile + resume from evals/golden_set (extension parity)."""

from __future__ import annotations

import sys

from app.user_store import sync_owner_from_golden


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        out = sync_owner_from_golden(email)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
