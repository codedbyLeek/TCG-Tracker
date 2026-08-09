# Phase 10, Part 3: Cloudflare R2 Image Migration

## Context

With both syncs pulling real card data and prices, every `Card.image_url` still pointed at a third-party CDN — `images.scrydex.com` for Pokémon, `optcgapi.com/media/static/...` for One Piece. That's a real dependency risk: your app's images are only as reliable as two other companies' servers staying up, a risk made concrete earlier this same project when pokemontcg.io quietly died mid-build. This phase moved every card image into your own Cloudflare R2 bucket, and wired the sync modules so future cards migrate automatically at creation time — no more manual backfills needed going forward.

## What got built

- **Cloudflare R2 setup**: bucket created, an API token scoped to *just* that bucket (not account-wide admin), S3-compatible credentials saved to `.env`, and public read access enabled via a free `r2.dev` development URL (explicitly not production-grade per Cloudflare's own docs — a real custom domain is a future to-do before this app has real users).
- **`app/core/storage.py`**: an idempotent `upload_image_to_r2()` helper. Downloads an image from its source CDN, uploads it to R2 via `boto3` (AWS's S3 SDK, pointed at Cloudflare's endpoint instead of Amazon's, since R2 is deliberately S3-protocol-compatible), and returns the new public URL. Detects the real file extension from the response's `Content-Type` header rather than assuming `.jpg` — Pokémon images turned out to be `.png`, which would have silently mislabeled every file if guessed from a small sample instead of checked.
- **`scripts/backfill_r2_images.py`**: a one-off migration for the 361 cards that existed before this work, looping over every `Card` row and calling the upload helper, skipping anything already migrated (by URL prefix) or lacking an image entirely.
- **Both sync modules updated**: `upload_image_to_r2()` now runs automatically inside the `if card is None:` (creation) branch of both `pokemon.py` and `one_piece.py`, wrapped in a `try/except` that falls back to the original source URL and logs a warning rather than failing the whole sync if one image's upload has a bad moment.

## Key architectural decisions

**Backfill once, then hook into the go-forward creation path — not one or the other.** A pure backfill only fixes cards that already exist; every future sync would keep creating new cards with external CDN URLs, silently re-introducing the exact dependency being migrated away from. Wiring upload only into the sync path, with no backfill, would leave the 361 pre-existing cards stuck on external URLs forever. Both were needed — this is the standard "backfill + go-forward hook" pattern for this class of data migration.

**Upload failures are non-fatal to the sync.** Given price data is the actual product and images are an enhancement, a flaky R2 upload for one card shouldn't be able to crash an otherwise-successful sync of hundreds of cards' prices. The `try/except` around the upload call, with a fallback to the original source URL, means a bad network moment costs you one temporarily-external-hosted image, not the whole run.

**Extension detection from `Content-Type`, not assumed from a URL pattern.** A quick check of two sample URLs suggested `.jpg` everywhere; a proper `HEAD` request revealed Pokémon images are actually served as `.png`. Assuming from a small sample would have produced files with the wrong extension relative to their actual content — probably still displaying fine in most browsers (which mostly sniff content anyway), but wrong and confusing on inspection, and a bad habit to reinforce.

## The Neon connection-timeout bug — a real system design lesson

This is the most valuable lesson from this leg of the project, and worth understanding at the architecture level, not just as "here's the fix."

**The symptom:** the `sv2` Pokémon sync crashed partway through, at card 242 of ~279, with `psycopg.OperationalError: server closed the connection unexpectedly` — a database error, even though the actual work happening around it (image downloads and uploads) had nothing to do with the database at all.

**Why it happened:** `app/core/database.py` already had `pool_pre_ping=True` set — SQLAlchemy's standard defense against a cloud Postgres provider silently killing an idle connection. But `pool_pre_ping` only re-validates a connection at the moment it's **checked out from the pool**. Before this phase, each sync's database work happened in a tight, fast burst — query, insert, query, insert — so the single session used for the whole run stayed genuinely active the entire time. Adding a `HEAD` + `GET` + `PUT` to R2 *per card, before the database is touched again* introduced real wall-clock gaps — seconds of pure network I/O with the database connection sitting completely idle — repeated hundreds of times. Since the sync design held one single session open, uninterrupted, from the first card to a single `db.commit()` at the very end, that connection was *never* returned to the pool and re-acquired mid-run. `pool_pre_ping`'s protection simply never got a chance to trigger — it was the same live, aging connection the whole time, and Neon's own server-side idle-connection policy eventually terminated it out from under the session.

**The fix:** move `db.commit()` from once-at-the-end to once-per-card, inside the loop. This has two effects, one obvious and one less obvious. The obvious one: less work lost if a future run does crash partway through, since already-committed cards stay committed. The less obvious, more important one: each `commit()` returns the connection to SQLAlchemy's pool, and the *next* card's work triggers a fresh checkout — which is exactly the moment `pool_pre_ping` actually runs its validation. Committing frequently isn't just about transaction safety; it's what makes an existing safety mechanism (`pool_pre_ping`) actually able to do its job at all.

**The general lesson**, worth remembering well past this specific bug: a connection pool's retry/validation logic can only protect you at the boundaries where connections are checked in and checked out. A long-lived session that never returns its connection to the pool is invisible to that protection, no matter how correctly the pool itself is configured. Any time a database session's lifetime is about to grow — mixing in slow external I/O, background jobs, batch scripts — it's worth asking specifically: *how often does this session actually return its connection to the pool?* Not just "is `pool_pre_ping` set."

## Error catalog

| # | Symptom | Root cause | Fix | Lesson |
|---|---|---|---|---|
| 1 | Backfill script run with `python scripts.backfill_r2_images` (no `-m`) failed: `No such file or directory` | Missing the `-m` flag — without it, Python treats the argument as a literal file path, not a dotted module path, and `scripts.backfill_r2_images` (with dots) isn't a real filename | Ran `python -m scripts.backfill_r2_images` | `-m` tells Python to resolve dots as package/folder separators and locate a module; omitting it makes Python search for a literal file with that exact (usually nonexistent) name. |
| 2 | `git commit`/`git add` for the config change appeared to succeed but `git show --stat HEAD` showed only `requirements.txt`, not `config.py` | `config.py`'s edits were real and saved to disk, but simply never got staged in that particular `git add` call — likely an easy-to-miss path issue in a multi-file command | Ran `git status` to confirm the file was genuinely modified-but-unstaged (not lost), then staged and committed it separately | A commit "succeeding" only proves *something* was committed, not that *everything intended* was. `git show --stat HEAD` after every commit is a cheap, worthwhile habit — this session caught the same class of silent gap twice. |
| 3 | `requirements.txt` `grep` reported "Binary file (standard input) matches" | The file was still UTF-16/CRLF-encoded, inherited from the original Windows setup; appending UTF-8 bytes to it (via `pip freeze >>`) produced a file with two mixed encodings, which `grep` correctly flagged as binary-looking | Regenerated the file entirely fresh with `pip freeze > requirements.txt` (overwrite, not append), producing clean UTF-8 | A stale, wrong file encoding from a cross-platform project handoff can sit undetected for a long time — it only surfaces the first time a Unix tool tries to append to or parse it. `file <filename>` is the fast way to check actual encoding when something behaves strangely. |
| 4 | `sv2` Pokémon sync crashed at card 242/279 with `psycopg.OperationalError: server closed the connection unexpectedly` | A single long-lived database session held one connection open across a multi-minute sync with real network-I/O gaps (image uploads) between database touches; Neon's server-side idle-connection policy killed the connection, and `pool_pre_ping` never got a chance to catch it since the connection was never returned to the pool mid-run | Moved `db.commit()` from once-at-the-end to once-per-card in both sync modules, so the connection cycles through the pool regularly | `pool_pre_ping` (or any pool-level retry logic) only protects connections at checkout time. A session that holds one connection continuously through a long, I/O-heavy operation is invisible to that protection no matter how it's configured. |

## New concepts covered this session

- **S3-compatible storage**: `boto3` (AWS's SDK) works against any service speaking the same protocol via `endpoint_url` — this is Cloudflare's deliberate design choice to make R2 a drop-in replacement for S3-based tooling.
- **`HEAD` requests** for cheap metadata checks (`Content-Type`) without downloading a full response body — used both to detect image file type and to check R2 object existence before re-uploading.
- **`try`/`except` used for expected, not just erroneous, control flow** — `_object_exists()` deliberately catches a "not found" `ClientError` as a normal, anticipated outcome, re-raising anything else.
- **Deliberately broad `except Exception:`** in both the backfill script and the sync modules' image-upload path — a conscious tradeoff (silently catching real bugs alongside network flakiness) accepted specifically because a long batch job finishing with a clear failure count is more valuable than one bad row killing hundreds of good ones.
- **`continue`** in a `for` loop — skip the rest of the current iteration's body and move to the next item, used in the backfill script's skip conditions.
- **Connection pool checkout/checkin as the actual unit `pool_pre_ping` protects** — not "is this setting on," but "how often does my session actually cycle through the pool."
- **File encoding diagnosis**: `file <name>` reveals actual byte-level encoding (UTF-8 vs UTF-16, LF vs CRLF) when a file behaves unexpectedly with standard Unix tools.

## Where Phase 10 stands now

- ✅ Pokémon sync (Scrydex), verified, seed data cleaned up
- ✅ One Piece sync (optcgapi.com), verified, seed data cleaned up
- ✅ Cloudflare R2 image migration — all 486 Pokémon cards and 154 One Piece cards hosted on R2, both sync modules auto-migrating new cards going forward
- ⏳ Not yet started: APScheduler nightly job