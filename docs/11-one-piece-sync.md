# Phase 10, Part 2: One Piece Sync (optcgapi.com)

## Context

With the Pokémon sync working end-to-end against Scrydex, the second half of Phase 10 was syncing One Piece card data. Unlike Pokémon, this provider was already decided back in initial planning (`optcgapi.com`, locked in the original tech-stack table) — so this leg was less about choosing a provider and more about understanding a genuinely different API shape, and catching bugs by careful reading before ever running the code.

## What got built

- `app/sync/one_piece.py` — a single-request sync against optcgapi.com's `/sets/{set_id}/` endpoint. No pagination loop, no auth headers, no nested price-variant filtering — the simplest of the three sync modules so far, because the API itself is the simplest.
- `scripts/sync_one_piece.py` — CLI entry point, same shape as the Pokémon one (`sys.argv` parsing, `logging.basicConfig`, `SessionLocal`/`try`/`finally`).
- Verified 154 real cards synced for set `OP-01`, with correct handling of "variant" prints (parallels, box toppers) as distinct rows.
- Cleaned up the 5 leftover One Piece seed cards from Phase 9, same procedure as the Pokémon side.

## Key architectural decisions

**No pagination needed at all.** optcgapi.com's `/sets/{set_id}/` endpoint returns the *entire* set as one flat JSON array in a single response — no `data`/`totalCount` envelope, no page parameter. This is a direct consequence of the provider, not a design choice on our end: Scrydex and pokemontcg.io both cap page size and require looping; optcgapi.com just doesn't. Worth remembering as a general lesson — always check what a new API actually does before assuming a pattern (like pagination) from a previous integration will carry over.

**No authentication.** optcgapi.com's docs are explicit: GET-only, no API key required, open to anyone (with a polite request not to hammer it, since it's a single hobbyist's VPS). One fewer failure mode than the Scrydex integration, which requires two header values and fails loudly at startup if either is missing.

**Variant identity: `external_id = card_image_id`, not `card_set_id`.** This was the central design decision of the whole sync. optcgapi.com returns a base print and every parallel/box-topper print of a card as *separate top-level objects* in the response array, sharing the same `card_set_id` (e.g. both Zoro prints are `OP01-001`) but differing in `card_image_id` (`OP01-001` vs `OP01-001_p1`) and — critically — market price (`$5.81` vs `$568.01` for the same card). Keying `external_id` off `card_set_id` instead would have silently collapsed these into one row, with whichever variant processed last overwriting the other's price. Using `card_image_id` keeps each print as its own row; `card_set_id` is instead stored in `card_number`, since it's still useful as the human-readable print identifier shared across a card's variants.

**No price-selection logic needed.** Compare this to Scrydex, where a single card had a nested `variants[].prices[]` structure requiring a two-phase filter-then-choose function to pick "the" price. Here, `market_price` sits flat on every object, and the "choosing between variants" problem doesn't exist in the sync code at all — it's already been solved by the API returning each variant as a fully independent object. The lesson generalizes: how much "selection" logic a sync module needs is entirely a function of how the source API structures ambiguity, not something to design defensively in advance.

## Error catalog

| # | Symptom | Root cause | Fix | Lesson |
|---|---|---|---|---|
| 1 | (Caught in review, before running) `NameError: name 'externail_id' is not defined` — would have occurred | Typo: `external_id` (defined) vs `externail_id` (used in the `select().where()` call) — two letters transposed | Corrected to `external_id` | A variable name typo is invisible to the eye at a glance but fatal at runtime — Python has no compile-time check that would catch it before that exact line executes. Read variable names character-by-character when something "looks right" but the bug persists. |
| 2 | (Caught in review, before running) `SyntaxError: invalid syntax` — would have occurred | Missing comma between `game="one_piece"` and `image_url=api_card.get("card_image"),` inside the `Card(...)` constructor call | Added the missing comma | A missing comma between keyword arguments is a *syntax* error, not a *runtime* error — it fails to parse before any code runs at all, unlike a `NameError`, which only surfaces once execution reaches that line. Different bug categories fail at different times. |
| 3 | `sys.srgv[1]` typo in `scripts/sync_one_piece.py` (caught in review) | Same category as bug #1 — `sys.argv` misspelled as `sys.srgv`; `sys` module genuinely has no such attribute | Corrected to `sys.argv[1]` | Same lesson as #1, in a second file — this kind of adjacent-key/transposed-letter typo is common enough to specifically watch for during any code review pass. |
| 4 | Pylance import warnings reappeared for `httpx`/`sqlalchemy` in a fresh editor session, despite having been fixed earlier in the project | VS Code's interpreter selection reverted to the global Homebrew Python (visible in the status bar: `Python 3.14.6 (homebrew)`) rather than `backend/.venv` — possibly from opening a new window/session | Reselected `backend/.venv`'s interpreter via the status bar picker, same manual "Enter interpreter path" → reveal hidden files → browse to `.venv/bin/python` procedure as before | Interpreter selection is a per-VS-Code-window setting, not something that necessarily persists reliably across sessions. The fix procedure from earlier in the project is worth having memorized, since it's likely to recur. |
| 5 | Training doc file existed on disk but was `0` bytes with no `.md` extension, sitting in `docs/` instead of the suggested `docs/training/` | The initial file download/save didn't fully complete — an empty placeholder was created without the real content ever landing in it. Separately, `docs/training/` was a guessed convention that didn't match the project's actual structure (other docs sit directly in `docs/`). | Regenerated the file content, saved directly to `docs/` matching the existing convention (`project-scope.md`, `learning-python-from-this-project.md`), and verified with `ls -la` that the real byte count was non-zero before trusting it | Don't assume a save succeeded — check the actual file (size, extension, location) on disk. Also: match a project's *actual* existing conventions rather than guessing a "more organized" structure that isn't really there. |

## New concepts covered this session

- **API shape varies by provider, not by "how sync modules generally work."** Three real integrations now (pokemontcg.io, Scrydex, optcgapi.com) have had three different pagination strategies (empty-array sentinel, `totalCount`-bounded, none at all) and three different price-data shapes (flat, deeply nested, flat-but-duplicated-per-variant). Each required reading real API responses before writing code, not assuming a previous pattern would transfer.
- **Syntax errors vs. runtime errors, concretely.** A missing comma breaks parsing before anything runs; a misspelled variable name only breaks execution once that specific line is reached. Both are typos, but they fail at different times and produce different error types (`SyntaxError` vs `NameError`).
- **`ON DELETE RESTRICT`** (recapped from the Pokémon-side cleanup, applied again here) — same procedure needed for the One Piece seed cards, confirming the pattern generalizes across game types since both use the same `cards`/`prices`/`collection_items` schema.

## Where Phase 10 stands now

- ✅ Pokémon sync (Scrydex) — done, verified, seed data cleaned up
- ✅ One Piece sync (optcgapi.com) — done, verified, seed data cleaned up
- ⏳ Not yet started: Cloudflare R2 image migration, APScheduler nightly job