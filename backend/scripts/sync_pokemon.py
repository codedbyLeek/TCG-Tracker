"""CLI entry point: sync Pokemon cards and prices into the database.

Usage:
    python -m scripts.sync_pokemon <set_id>   # one expansion
    python -m scripts.sync_pokemon all        # every English physical expansion

Examples:
    python -m scripts.sync_pokemon sv3pt5
    python -m scripts.sync_pokemon all
"""

import logging
import sys

from app.core.database import SessionLocal
from app.sync.pokemon import sync_all_expansions, sync_set


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage: python -m scripts.sync_pokemon <set_id|all>")
        sys.exit(1)

    target = sys.argv[1]

    db = SessionLocal()
    try:
        if target == "all":
            summary = sync_all_expansions(db)
            print(
                f"Done: {summary['sets_attempted']} expansions attempted, "
                f"{summary['sets_failed']} failed, "
                f"{summary['created']} created, {summary['updated']} updated"
            )
            for expansion_id, error in summary["failures"]:
                print(f"  FAILED {expansion_id}: {error}")
        else:
            created, updated = sync_set(db, target)
            print(f"Done: {created} created, {updated} updated")
    finally:
        db.close()


if __name__ == "__main__":
    main()