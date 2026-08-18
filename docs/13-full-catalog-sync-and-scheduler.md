# Chapter 13: Full-Catalog Sync, Discovery, and the Scheduler

> **Phase**: 10 (final leg) — sub-phase 1: full-catalog backfill; sub-phase 2: APScheduler
> **Goal**: Stop hardcoding set lists. Sync *everything* (198 Pokémon expansions, 21 One Piece sets, 28 structure decks, ~940 promos ≈ 25,000+ cards), then put price refreshes on autopilot with tiered scheduled jobs.
> **Time investment**: Two long sessions, including one multi-hour unattended backfill run.

---

## The concept

Everything before this phase synced *specific, hand-picked sets*. This phase made two jumps:

1. **Discovery over hardcoding.** Instead of `sync_set(db, "sv3pt5")` with IDs we typed in, the sync modules now *ask each API what exists* (`list_expansions()`, `list_set_ids()`, `list_deck_ids()`) and sync all of it. New sets appear in the catalog automatically the day the API adds them — no code change ever needed.
2. **Scheduled autonomy.** An APScheduler instance lives inside the FastAPI process and runs three recurring jobs. Nobody types `python -m scripts...` at 3am; the system feeds itself.

```
                     ┌──────────────────────────────┐
                     │   FastAPI process (Uvicorn)   │
                     │                              │
   HTTP requests ───▶│  routers (cards, collection) │
                     │                              │
                     │  BackgroundScheduler         │
                     │   ├─ one_piece_nightly 3:00  │──▶ sync_all_sets()
                     │   ├─ pokemon_recent    3:30* │──▶ sync_recent_expansions()
                     │   └─ pokemon_full_sweep Sun 4│──▶ sync_all_expansions()
                     └──────────────────────────────┘
                              (* every 2 days)
```

---

## Part 1: Discovery functions

### Probe before you code (again)

The phase-10 lesson "never write sync code against a response shape you haven't seen" got applied — and paid off immediately, four separate times:

- Scrydex's expansions envelope uses `total_count` (snake_case), not `totalCount`.
- Scrydex includes digital-only sets (`is_online_only: true`) that have no physical prices — filtered out to save credits.
- optcgapi's documented promo endpoint (`/api/allPromoCards/`) **404s**; the real one is `/api/allPromos/`, found by brute-force probing candidate paths and reading status codes.
- optcgapi's promo cards **reuse base-card image IDs** — an identity landmine (Part 4) that would have silently corrupted prices.

### The Pokémon discovery function

```python
def list_expansions() -> list[dict]:
    expansions: list[dict] = []
    page = 1
    with httpx.Client(...) as client:
        while True:
            response = client.get("/en/expansions", params={"page": page, "pageSize": PAGE_SIZE})
            ...
            expansions.extend(data)
            total_count = payload.get("total_count") or 0
            if not data or len(expansions) >= total_count:
                break
            page += 1
    return [e for e in expansions if not e.get("is_online_only")]
```

Key points:

- **Returns whole dicts, not just IDs** — the scheduler needs `release_date` for tiering and `total` for cost estimates. Return what callers will need, once.
- `/en/` in the path scopes to English — the listing endpoint mixes languages without it.
- **Two stop conditions** (`not data or len(...) >= total_count`): the count-bound is primary; the empty-page check is insurance against a wrong/huge `total_count` causing an infinite loop.
- `extend` vs `append`: `extend` adds each element (flat list); `append` would nest whole pages. Apex: `addAll()` vs `add()`.
- The final line is a **list comprehension with a filter** — the idiomatic "keep only the elements where..." construct.

The One Piece equivalents (`list_set_ids`, `list_deck_ids`) are single-request and return bare ID strings — nothing else is needed per set on a free API. Return the simplest thing each caller actually uses.

**Access-style rule reaffirmed**: `s["set_id"]` (hard crash if missing) for data the sync *requires*; `.get()` for optional data. A loud `KeyError` naming the field beats a silent parade of `None`s. This rule caught `d["deck_id"]` (wrong key — the real field is `structure_deck_id`) before it shipped.

---

## Part 2: Orchestration — sync_all with failure isolation

### The shape

```python
for set_id, endpoint in targets:
    try:
        created, updated = sync_set(db, set_id, endpoint=endpoint)
    except Exception as exc:
        logger.exception("%s %s failed, continuing", endpoint, set_id)
        db.rollback()
        failures.append((set_id, endpoint, str(exc)))
        continue
    total_created += created
    total_updated += updated
```

- **Broad `except Exception` is correct at a batch boundary** (one bad set must not kill the run) even though it's a smell in inner logic. Same idea as per-record try/catch inside an Apex batch's `execute`.
- **`db.rollback()` is the critical line.** A SQLAlchemy exception mid-transaction poisons the session; every later operation raises `PendingRollbackError` until rollback. Without it, one failure cascades into all subsequent sets failing.
- `logger.exception(...)` = `logger.error` + automatic traceback of the in-flight exception. Only valid inside `except`.
- `continue` skips the counter lines — making the intent explicit.

### The retry pass

One retry, at the **end** of the run, for everything that failed:

- **At the end, not immediately**: transient failures (Neon connection drops, network blips) are time-correlated. Minutes later, conditions have changed.
- **One retry, not a loop**: transient failures heal on attempt two; persistent failures (404s, schema changes) fail every attempt and should surface to a human, not burn credits in a retry loop.
- **Build a new list, swap at the end** (`remaining_failures` → `failures = remaining_failures`): never mutate a list you're iterating.
- The One Piece version keeps `(id, endpoint, error)` **triples internally** (the retry must know *how* to re-attempt — `sets`, `decks`, or the promo dispatch) but returns `(id, error)` **pairs** in the summary, because the CLI and scheduler unpack exactly two. Internal richness, stable external contract.

### The proof it works

The Pokémon backfill (198 expansions) ran clean. The first One Piece full run wasn't so lucky — **OP-12 died mid-set** to a Neon `server closed the connection unexpectedly` — and the machinery did exactly its job: caught it, rolled back, synced the remaining 8 sets, reported the failure with set ID and reason. Recovery was one command (`python -m scripts.sync_one_piece OP-12`): 130 already-committed cards took the update path, 25 got created. Later, the promo `AttributeError` gave the retry pass its first live firing — it re-dispatched correctly, failed again identically (persistent bug, as designed), and reported.

### Why per-card commits didn't fully prevent OP-12

Per-card commits *narrowed* the vulnerable window; they didn't eliminate it. Each new card: checkout connection (pre_ping validates **here**) → slow R2 upload while the transaction idles → INSERT + commit. If Neon kills the connection during the upload, the INSERT hits a corpse. ~1–2 seconds of exposure × 3,000 new cards = one death is about par. Only *new* cards have the window (existing cards skip the upload), so steady-state nightly runs are far safer than backfills. The auto-retry converts the residual risk into a non-event.

---

## Part 3: Idempotency — the property that makes all of this safe

An operation is **idempotent** if running it twice leaves the same end state as running it once (elevator call button, not vending machine coin slot).

Every layer of this system has it, deliberately:

| Layer | Mechanism |
|---|---|
| Card upsert | Look up by `external_id`; update if found, create if not |
| R2 upload | HEAD check — skip if the object already exists |
| Job registration | `replace_existing=True` — reloads replace, never duplicate |
| Alembic | Version table — `upgrade head` twice applies nothing new |

One deliberate impurity: every sync run appends a new `Price` history row. The *catalog state* is idempotent; the *history log* intentionally isn't — "a price observation happened" is itself a fact worth recording. Idempotent state + append-only log is a standard real-world split.

**The payoff chain**: idempotency at the bottom → blind retries are safe → the scheduler can abandon jobs mid-flight at shutdown (`wait=False`) → nobody needs to be awake at 3am. Idempotency at the bottom buys casualness at the top.

---

## Part 4: The promo identity trap

optcgapi's `/allPromos/` returns card objects whose `card_image_id` **is the base card's ID** (a Premium Collection "Gum-Gum Lightning" reports `OP09-077` — same as the main-set card already in the DB, at 5× the price). The Phase 10b decision (`external_id = card_image_id`) was verified against the *sets* endpoint, where it uniquely identifies prints; the *promos* endpoint silently violates that assumption.

Unfixed consequence: the upsert finds the main-set row, takes the update path, and **overwrites the regular card's price with the promo price** — no error anywhere, prices whiplashing between syncs. Caught only because the probe output was read closely.

Fix: promos derive `external_id` from the image **filename** (unique per print, by necessity) with a `promo_` prefix so no collision is possible:

```python
filename = image_url.rsplit("/", 1)[-1].removesuffix(".jpg")
external_id = f"promo_{filename}"
```

- `rsplit("/", 1)[-1]` — split from the right at most once, take the last piece: the filename. Works even with no `/` present.
- `.removesuffix(".jpg")` — strips the extension *only if present*. (Not `.rstrip(".jpg")`, which strips **characters** and mangles names ending in j/p/g — a classic trap.)

**Lesson**: an identity scheme verified against one endpoint is not verified against a *family* of endpoints. Assumptions travel poorly; re-check them at every new data source.

---

## Part 5: The shared upsert — extracting `_upsert_card`

With promos needing the same card-processing loop as sets/decks but a different ID, the loop was extracted:

```python
def _upsert_card(db, api_card, external_id, now) -> bool:
    """Upsert one card and its price row, committing. Returns True if created."""
```

- **The one thing that varies (`external_id`) became the one parameter the caller controls.** That's what a good extraction looks like: shared logic inside, variation at the boundary.
- Returns `bool` instead of mutating counters — a deep helper shouldn't know the caller's bookkeeping. `created = card is None` is captured *before* the create path assigns a new object to `card`.
- `sync_set` collapsed to fetch-plus-loop and gained `endpoint: str = "sets"` — the default keeps every existing caller working (backwards-compatible extension); decks are `sync_set(db, "ST-01", endpoint="decks")` since the two endpoint families return identical card shapes.
- **When to extract**: at the *second* real use case, not speculatively before it, and not never. This phase hit that threshold twice (`_sync_expansions` for the two Pokémon entry points, `_upsert_card` for the three One Piece card sources).

---

## Part 6: Credit budgeting and tiered scheduling

Scrydex bills per request; the plan allows **5,000 credits/month**. That constraint *designed the schedule*:

| Job | Trigger | Cost/run | Cost/month |
|---|---|---|---|
| One Piece full (sets+decks+promos) | Nightly 3:00 | free API | 0 |
| Pokémon recent (last 90 days) | Every 2 days, 3:30 | ~6 req | ~100 |
| Pokémon full sweep | Sundays 4:00 | ~260–300 req | ~1,200 |

- "Recent" is a **date filter** (`release_date >= now - 90 days`), not a hardcoded top-N — it tracks release droughts and bursts automatically. (Observed live: Ascended Heroes aged out of the window mid-phase.)
- Estimated request cost is computed up front with **ceiling division**: `(total + PAGE_SIZE - 1) // PAGE_SIZE` — the `(n + d - 1) // d` idiom for "how many buckets of size d for n items". Boundary-check it: 207→3, 200→2, 1→1, 0→0.
- `CronTrigger(day="*/2")` is day-of-*month* stepping — at 31-day month boundaries the 31st and 1st run back-to-back. Accepted: the flaw is bounded (~10 extra credits) and predictable, unlike `IntervalTrigger(days=2)` which resets its clock on every redeploy. Knowing *why* you chose an imperfect option is the skill.

---

## Part 7: Uvicorn, lifespan, and the in-process scheduler

### Uvicorn in one paragraph

FastAPI's `app` is just an object — nothing in it opens ports or parses HTTP bytes. **Uvicorn is the server**: it listens on the socket, parses requests, and calls the app through the **ASGI** contract (which is why servers and frameworks are swappable). `uvicorn app.main:app` = "import module `app.main`, use its variable `app`." In Salesforce terms: Uvicorn is the piece of the platform's invisible infrastructure you now operate yourself.

### The lifespan pattern

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    register_jobs()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)
```

- Everything **before `yield`** runs once at startup; the function *pauses at `yield`* for the server's whole lifetime; everything **after** runs at shutdown. (`yield` makes it a generator — a function that can pause and resume. Closest Apex analogy: a try/finally where the framework owns the middle.)
- `wait=False` abandons in-flight jobs at shutdown — safe *only because the jobs are idempotent*. A sync-layer design decision paying rent in the infrastructure layer.
- `logging.basicConfig` lives here because Uvicorn only configures *its own* loggers; without this line, all `logger.info` calls in app code are silently dropped (Phase-10 error #6, recurring under a new entry point).

### Scheduler design decisions

- **`BackgroundScheduler`** — jobs run on their own thread pool, so a 40-minute sync never blocks API requests. (`BlockingScheduler` would freeze the app; `AsyncIOScheduler` would stall the event loop, since the sync functions are blocking code.)
- **Module-level singleton by import** — Python caches modules, so every `from app.core.scheduler import scheduler` gets the same object. Same mechanism as `settings` and `SessionLocal`.
- **`register_jobs()` is a function, not module-level calls** — import should be side-effect-free; the *app* decides when jobs attach.
- **`timezone="America/New_York"`** (IANA name, not "EST") — carries the DST rules, so 3:00 AM stays 3:00 AM local year-round. Verified in logs by the `-04:00` offset.
- **`max_instances=1`** — a still-running job skips its next trigger instead of stacking; the skipped work self-heals next trigger (idempotency again).
- **Each job run creates and closes its own `SessionLocal()`** — sessions aren't thread-safe and jobs run on scheduler threads. `_run_job` is to the scheduler what `main()` is to a CLI script: the entry point that owns session lifecycle.
- **In-process scheduling (option 1) vs a worker process (option 2)**: chosen because the jobs are I/O-bound, traffic is one user, and Railway bills per service. The sync functions don't know where they're called from, so graduating to a worker later is cheap. Corollary: **the schedule is only as alive as the process hosting it** — a laptop dev server firing real jobs is a feature and a hazard (a 4am full sweep nearly double-ran during testing).

### The heartbeat method

New infrastructure was proven with a trivial `heartbeat` job on `CronTrigger(minute="*")` — no DB, no HTTP, just a log line — before any real job was attached. Prove the infrastructure fires in isolation from everything else that could fail; then swap in the real work.

---

## Error catalog

| # | Symptom | Root cause | Fix | Lesson |
|---|---|---|---|---|
| 1 | R2 uploads happened but DB stored source-CDN URLs (both sync modules) | `image_url` variable carefully computed, then the `Card(...)` constructor re-called the extraction function instead of using the variable — assigned-but-never-read | `image_url=image_url` in the constructor | Compute-then-discard is a silent bug class. If a variable is assigned and never read, something is wrong. (Left side of `kwarg=expr` is the parameter name; right side is your local value.) |
| 2 | One Piece still committed once at end of run | The per-card-commit lesson from Phase 10c was applied to Pokémon but not back-ported | Moved `db.commit()` inside the card loop | When a lesson changes a pattern, sweep *all* implementations of the pattern, not just the file that taught it. |
| 3 | `SyntaxError` — `db.commit()` landed *inside* `db.add(...)`'s parentheses | Statement pasted mid-argument-list; unclosed `(` puts Python in expression mode | Moved the commit after the closed call | Bracket errors surface at parse time, sometimes a line *after* the real mistake. On a `SyntaxError` near brackets, look upward for an unclosed `(`. |
| 4 | Latent `NameError: set_id` in the single-set CLI path | Variable renamed to `target` at top; one branch still used the old name — and the `for set_id, ...` loop elsewhere in scope hid it from the linter | Passed `target` | Python doesn't check name existence until the line runs; loop variables aren't block-scoped. Partial renames compile fine and detonate later. |
| 5 | `total_craeted += created` | Transposed-letter typo; `+=` reads the name first → `NameError` on first *success* — outside the try/except, so it would kill the whole batch loop | Fixed spelling | `x += y` requires `x` to exist. A typo'd accumulator defeats the error isolation it sits next to. |
| 6 | `"set_attempted"` (singular) summary key | Key renamed during transcription; consumer reads `sets_attempted` → `KeyError` *after* an entire multi-hour sync succeeds | Restored plural | Summary dicts are contracts. Uniform keys across modules exist so shared consumers (CLI, scheduler) never need to care which module produced them. |
| 7 | `NameError: _sync_expansion... Did you mean: '_sync_expansions'?` | Helper renamed, call sites not — third partial rename of the phase | Renamed call sites | Use F2 (Rename Symbol) for renames — Pylance rewrites all references atomically. Manual rename → `Cmd+F` the old spelling before moving on. |
| 8 | Fixed code regressed on disk; retry edit vanished | Edits landed in an unsaved buffer / stale copy; file reverted to last-committed state | Re-applied; verified with `git diff` | `git --no-pager diff <file>` answers "what does my working file actually differ from the last commit?" definitively when memory and editor disagree. |
| 9 | `pokemon_recent` defined twice — first ran the *One Piece* sync | `def` is just assignment; the second binding silently replaces the first. No warning, no error | Deleted the wrong one | Duplicate `def`s are legal Python. Which one survives is purely textual order — this class of bug is invisible to the runtime. |
| 10 | `NameError: asynccontextmanager` at Uvicorn boot | `from contextlib import asynccontextmanager` missing | Added the import | Even stdlib names bind nothing until imported. In a boot traceback, scan for the first frame in *your* code; everything above is the framework delivering the crash. |
| 11 | Scheduler heartbeat invisible under Uvicorn | Root logger unconfigured; Uvicorn only configures its own loggers | `logging.basicConfig(level=logging.INFO)` in lifespan startup | Every new *entry point* (CLI, server, worker) needs its own logging config. Phase-10 error #6, new costume. |
| 12 | Committed doc showed as `deleted` + a new extensionless untracked file | `.md` extension accidentally removed in a rename; git compares snapshots and saw delete + unknown file | `mv` to restore the extension | Git doesn't watch renames happen. A delete/untracked pair with near-identical names = a rename gone wrong. |
| 13 | Phase 10c doc was never in the repo at all | Written to disk, never `git add`ed | Committed it (as its own commit) | "File exists locally" and "file is in version control" are different facts. `git status` untracked list is worth actually reading. |
| 14 | `git show --stat` swallowed by a help screen | Output paged through `less`; `h` opened its help | `q` to quit; `git --no-pager show --stat` for short outputs | Git pipes long output through `less`. Space = page, `q` = quit. `--no-pager` goes before the subcommand. |
| 15 | Bizarre VS Code error: "Extension for backend/.venv/bin/python is not installed" | `settings.json` had `python-envs.defaultEnvManager` (expects a manager *ID*) set to a file *path* — the extension treated the path as an extension identifier | Replaced with `python.defaultInterpreterPath: ${workspaceFolder}/backend/.venv/bin/python` | Wrong setting key + wrong value type fails silently in JSON settings, then surfaces as a nonsense error elsewhere. The leanest settings file that does the job is the correct one. |
| 16 | `curl: command not found` — seconds after curl worked | `echo $PATH` → `allPromoCard`. PATH had been *replaced* by a loop-candidate string; in zsh, lowercase `path` is an array **tied to** `PATH`, so a mangled `path=...` assignment nukes command lookup | Fresh terminal (env damage is session-local) | Builtins keep working when PATH breaks (that's the tell). Never use `path` as a shell loop variable in zsh. |
| 17 | Documented promo endpoint 404s | Docs/server drift on a hobbyist API | Probed candidate paths in a loop reading only status codes; found `/allPromos/` | When docs and server disagree, the server wins. A status-code probe loop (`curl -s -o /dev/null -w "%{http_code}"`) is the cheapest way to search for the truth. |
| 18 | (Caught in probe review) promos reuse base-card `card_image_id` | Endpoint family violates the identity assumption verified on the sets endpoint | Filename-derived `promo_`-prefixed `external_id` | Would have silently overwritten main-set prices with promo prices — no error, just corrupt data flip-flopping nightly. The scariest bug class is the one that never raises. |
| 19 | `AttributeError: 'NoneType' object has no attribute 'rsplit'` in promo sync | A promo has `"card_image": null` — key *present* with null value, so `.get("card_image", "")` returned `None`, sailing past the default | `api_card.get("card_image") or ""` | `.get(key, default)` only defaults on **absent** keys. Present-but-null needs the `or` coalesce. Third-party JSON mixes the two freely. |
| 20 | (Caught in review) `sync_promos` indented inside the targets loop | One indentation level too deep — promos would sync once *per target* (49 full promo runs per night) | Dedented one level | Indentation IS structure. The wrongly-nested version raises no error ever — it's just 49× wasteful against a hobbyist's VPS. |
| 21 | (Caught in review) `logger.exception("Set %s failed...", endpoint, set_id)` ×3 | Placeholder count ≠ argument count | Matched counts (`"%s %s ..."`) | Logging swallows its own formatting errors into `--- Logging error ---` noise — the message is lost exactly when it's needed most. Count placeholders against args. |
| 22 | OP-12 sync died mid-set: `psycopg.OperationalError: server closed the connection unexpectedly` | Neon killed a connection during the R2-upload window between pre_ping and INSERT (see Part 2) | Re-ran the set (idempotent); later, auto-retry automates this | Transient infra failure across thousands of dice rolls is *normal*, not a bug. Design for re-runnability instead of trying to prevent every death. |

**Meta-pattern of the phase**: almost every self-inflicted bug was *transcription drift* — partial renames, transposed letters, dropped imports, wrong indentation depth — not logic errors. The structure was always right. Defenses that earned their keep: review-before-run, F2 renames, `Cmd+F` for old spellings, `git diff` as ground truth, and copy-pasting intricate given code while reserving hand-typing for logic being composed.

---

## Key takeaways

1. **Discovery over hardcoding.** Asking the API what exists makes the system self-maintaining — new sets, release droughts, and bursts are all handled by the same code, forever.
2. **Probe every new endpoint, even on a known API.** Four probe-caught surprises this phase, including one (promo IDs) that would have silently corrupted data.
3. **Failure isolation + rollback + one deferred retry** turns "3am job failed" into "log line about a set that healed itself." `db.rollback()` in the except block is what keeps one failure from cascading.
4. **Idempotency is the foundation everything else stands on** — blind retries, abandoned shutdowns, skipped triggers, and one-command recovery are all downstream of upsert-by-external-id.
5. **Constraints design systems.** The 5,000-credit budget produced the tiered schedule; the schedule produced the date-filtered "recent" function. Good architecture is often just arithmetic done early.
6. **Extract shared logic at the second use case.** `_sync_expansions` and `_upsert_card` both appeared exactly when duplication became real, parameterizing exactly what varies.
7. **The scheduler lives and dies with its process.** In-process scheduling is the right start; know its one big rule before pointing a laptop dev server at production data.
8. **Contracts at boundaries stay stable while internals get richer** — triple-element failures inside, pair-element summaries outside; the CLI and scheduler never knew anything changed.