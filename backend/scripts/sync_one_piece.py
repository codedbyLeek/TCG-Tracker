"""CLI entry point: sync on One Piece set's cards and prices into the database.

Usage:
    python -m scripts.sync_one_piece <set_id>

Example:
    python -m scripts.sync_one_piece OP-01
"""


import logging
import sys

from app.core.database import SessionLocal
from app.sync.one_piece import sync_set


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage: python -m scripts.sync_one_piece <set_id>")
        sys.exit(1)

    set_id = sys.argv[1]

    db = SessionLocal()
    try:
        created, updated = sync_set(db, set_id)
        print(f"Done: {created} created, {updated} updated")
    finally:
        db.close()


if __name__ == "__main__":
    main()