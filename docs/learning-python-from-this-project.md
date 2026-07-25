# Learning Python From This Project

This is a from-day-1 walkthrough of the `backend/` code in this repo. Every
concept is introduced the moment it first shows up in the real files — not in
abstract order — so you can always point at a line of your own code and say
"that's the thing that does X, and here's why it's written that way."

Goal: after reading this, you should be able to answer **"why did we write it
like that?"** for every line in `backend/app/`.

How to use it: read top to bottom once, then keep it as a reference. Each
section quotes the real file and line, so you can jump back to the source.

---

## Table of Contents

0. [The cast of tools, and why each one is here](#0-the-cast-of-tools-and-why-each-one-is-here)
1. [Modules, packages, and imports](#1-modules-packages-and-imports)
2. [Variables, types, and type hints](#2-variables-types-and-type-hints)
3. [Functions, arguments, and `return`](#3-functions-arguments-and-return)
4. [Classes and objects](#4-classes-and-objects)
5. [Decorators](#5-decorators)
6. [SQLAlchemy models, line by line](#6-sqlalchemy-models-line-by-line)
7. [Pydantic schemas, line by line](#7-pydantic-schemas-line-by-line)
8. [FastAPI routes, line by line](#8-fastapi-routes-line-by-line)
9. [Dependency injection with `Depends`](#9-dependency-injection-with-depends)
10. [The database session lifecycle](#10-the-database-session-lifecycle)
11. [Settings and environment variables](#11-settings-and-environment-variables)
12. [Alembic migrations](#12-alembic-migrations)
13. [The seed script](#13-the-seed-script)
14. [Tracing one request start to finish](#14-tracing-one-request-start-to-finish)
15. [Why FAQ — quick answers to "why not just..."](#15-why-faq)
16. [Glossary](#16-glossary)

---

## 0. The cast of tools, and why each one is here

| Tool | What it is | Why it's in this project |
|---|---|---|
| **Python** | The language | Readable, huge ecosystem, good for a learning project that still needs to be a real backend |
| **FastAPI** | Web framework | Turns Python functions into HTTP endpoints; generates OpenAPI docs for free; plays natively with type hints |
| **SQLAlchemy** | ORM (Object-Relational Mapper) | Lets you write Python classes that map to database tables, instead of hand-writing SQL strings everywhere |
| **Pydantic** | Data validation library | Validates and shapes data crossing a boundary (HTTP request in, HTTP response out) — FastAPI is built on top of it |
| **Alembic** | Migration tool | Tracks *changes* to your database schema over time as versioned, runnable scripts |
| **PostgreSQL (via Neon)** | The actual database | A real relational database with constraints, foreign keys, and transactions — not just a file on disk |

**Why an ORM instead of raw SQL?** You *could* write
`cursor.execute("SELECT * FROM cards WHERE game = %s", (game,))` everywhere.
SQLAlchemy exists so that (a) you write Python, not string-concatenated SQL,
which avoids a whole category of bugs (and SQL-injection risk) and (b) the
same `Card` class describes the table *and* gives you an object with
`.name`, `.rarity`, etc. in Python.

**Why Pydantic on top of SQLAlchemy, instead of returning ORM objects
directly?** Covered in depth in [§7](#7-pydantic-schemas-line-by-line) — short
version: the database shape and the "what the API promises to return" shape
are different concerns, and conflating them bites you later.

---

## 1. Modules, packages, and imports

A **module** is just a `.py` file. A **package** is a folder containing an
`__init__.py` file, which makes Python treat the folder as an importable unit.

```
backend/app/
├── __init__.py        <- makes `app` a package
├── main.py
├── api/
│   ├── __init__.py
│   ├── cards.py
│   └── collection.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   └── database.py
├── models/
│   ├── __init__.py
│   ├── base.py
│   └── models.py
└── schemas/
    ├── card.py
    └── collection.py
```

> **Aside — a typo that used to live here:** `backend/app/__init__.py` was
> previously misspelled `__intit__.py` (missing the `e`). Because it was
> empty and Python still found `app/` importable (likely via **namespace
> packages**, where Python 3.3+ can treat any folder as a package even
> without `__init__.py` at all), nothing broke — but it wasn't doing what
> it was meant to do. Fixed by renaming it. Worth knowing this class of bug
> exists: a misspelled special filename can silently do nothing instead of
> erroring.

### The import statement

```python
from app.api.cards import router as cards_router
```

Reading this left to right:

- `app.api.cards` is a **dotted path** to a module — Python walks
  `app/` → `api/` → `cards.py`.
- `import router` pulls the name `router` (defined in `cards.py` as
  `router = APIRouter(...)`) into this file's namespace.
- `as cards_router` **renames it on import**. Why rename? Because
  `main.py` imports a `router` from *two* different files
  (`cards.py` and `collection.py`) — without renaming, the second import
  would silently overwrite the first name.

```python
# backend/app/main.py
from app.api.cards import router as cards_router
from app.api.collection import router as collection_router
```

**Why absolute imports (`app.api.cards`) instead of relative (`.cards`)?**
Absolute imports read the same no matter which file you're standing in, and
they're what FastAPI's own docs recommend for exactly this app-package
layout. It also means the string `app.main:app` (used to launch the server)
lines up with the real file path.

### `__init__.py` as a "re-export hub"

```python
# backend/app/models/__init__.py
from app.models.base import Base
from app.models.models import User, Card, Price, CollectionItem

__all__ = ["Base", "User", "Card", "Price", "CollectionItem"]
```

This file does no real work — it just re-exports names. Why? So that other
files can write:

```python
from app.models import Card, CollectionItem, User
```

instead of having to remember that `Card` actually lives in
`app.models.models` (a file whose name is a little redundant with its
folder — `models/models.py` — a common pattern once a package needs an
`__init__.py` anyway).

`__all__` is a convention: it tells `from app.models import *` (a wildcard
import) exactly which names to bring in. It's mostly documentation here —
nothing in this repo does a wildcard import — but it's cheap and standard.

---

## 2. Variables, types, and type hints

Python doesn't *require* you to declare a variable's type — but this
codebase adds type hints everywhere, because FastAPI and Pydantic read them
at runtime to validate data. A type hint here isn't just a comment for
humans; it changes program behavior.

```python
# backend/app/schemas/card.py
id: uuid.UUID
name: str
set_name: str | None
rarity: str | None
current_price_usd: Decimal | None
current_price_updated_at: datetime | None
```

- `str` — plain text.
- `uuid.UUID` — not a plain string; a real UUID *object*. Pydantic will
  reject a value that isn't a valid UUID shape, and SQLAlchemy stores it as
  a native `UUID` column type (see §6).
- `str | None` — **union type**: this value is either a `str` or Python's
  `None`. The `|` syntax (instead of the older `typing.Optional[str]`) is
  Python 3.10+ shorthand meaning "one of these types." Every `| None` field
  here maps to a database column that's `nullable=True` — the type hint and
  the database constraint tell the same story from two sides.
- `Decimal` — **why not `float` for money?** See [§15](#15-why-faq).
- `datetime` — Python's built-in date+time object, not a string. Pydantic
  will parse an ISO date string into a real `datetime` automatically.
- `list[CardResponse]` (in `CardListResponse`) — a list where every element
  is typed as a `CardResponse`. Generic collection typing: `list[X]`, not
  just `list`.

### f-strings

```python
# backend/scripts/seed_cards.py
print(f"✓ Seed complete: {created}, created, {skipped} skipped")
```

`f"..."` is an **f-string** (formatted string literal). Anything inside
`{ }` is evaluated as a Python expression and inserted into the string.
It's the modern replacement for `"...".format(...)` or `%`-formatting —
easier to read because the variable sits right where it's used.

---

## 3. Functions, arguments, and `return`

```python
# backend/app/api/cards.py
def search_cards(
    q: str | None = Query(default=None, description="Search by card name"),
    game: str | None = Query(default=None, description="Filter: pokemon or one_piece"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
```

- `def name(...):` defines a function. Each parameter can have a type hint
  (`q: str | None`) and a **default value** (`= Query(default=None, ...)`).
  A parameter with a default becomes optional to the caller.
- `q: str | None = Query(...)` — `Query(...)` isn't the default value in the
  simple sense; it's FastAPI's way of saying "this parameter comes from the
  URL's query string (`?q=charizard`), and here's its validation rule."
  `ge=1, le=100` on `limit` means "greater-or-equal 1, less-or-equal 100" —
  FastAPI enforces that automatically and returns a 422 error if violated,
  before your function body ever runs.
- Parameters are **keyword arguments with defaults**, so callers (in this
  case, FastAPI itself, based on the incoming HTTP request) can supply any
  subset of them.

### `return`

```python
return CardListResponse(items=cards, total=total, limit=limit, offset=offset)
```

`return` hands a value back to whoever called the function. Here it's
constructing a Pydantic model instance and returning *that* — FastAPI then
knows (from the route's `response_model=CardListResponse`) how to serialize
it to JSON.

---

## 4. Classes and objects

```python
# backend/app/models/base.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass
```

- `class Base(DeclarativeBase):` — defines a new class named `Base` that
  **inherits from** `DeclarativeBase` (a class SQLAlchemy provides). Every
  model in this app (`User`, `Card`, `Price`, `CollectionItem`) will in turn
  inherit from *this* `Base`, which is how SQLAlchemy discovers "these are
  all my tables."
- `"""Base class for all SQLAlchemy models"""` — a **docstring**. Not a
  comment (`#`); it's a string literal that Python attaches to the class as
  `Base.__doc__`, readable by tools and other developers.
- `pass` — a no-op statement meaning "this block is intentionally empty."
  Python requires *something* inside an indented block; `pass` is that
  placeholder.

**Why does `Base` exist as its own tiny file (`base.py`)** instead of being
defined inside `models.py`? To avoid a **circular import**: every model
needs to import `Base`, and if `Base` lived in the same file as the models,
that's fine — but splitting it out is a common pattern so that other things
(like Alembic's `env.py`, not shown here but standard in this setup) can
import just `Base` without pulling in every model class too.

### A real model

```python
# backend/app/models/models.py
class Card(Base):
    __tablename__ = "cards"
```

`Card(Base)` — inherits from `Base`, so SQLAlchemy now knows `Card` is a
table definition, not just a regular Python class. `__tablename__` is a
**class attribute** (a variable that belongs to the class itself, shared by
all instances) that SQLAlchemy specifically looks for to name the SQL
table.

---

## 5. Decorators

```python
# backend/app/main.py
@app.get("/")
def root():
    return {"message": "TCG Tracker API is running"}
```

The `@` syntax is a **decorator** — it wraps the function immediately below
it, replacing it with (usually) a version that does extra work around the
original. `@app.get("/")` doesn't change what `root()` returns; it
*registers* `root` with FastAPI's router as "the function to call when an
HTTP GET request comes in for path `/`." Without the decorator, `root` would
just be an ordinary function that nothing ever calls.

Same pattern, on a router instead of the whole app:

```python
# backend/app/api/cards.py
@router.get("", response_model=CardListResponse)
def search_cards(...):
```

`router` here is an `APIRouter`, a mini version of `app` scoped to one
feature area (cards). `main.py` later attaches it with
`app.include_router(cards_router)` — so the final URL becomes
`/api/cards` (see the `prefix="/api/cards"` when `router` was created) plus
whatever path the decorator specifies (`""` = the router's own base path).

**Why split routes into per-feature routers (`cards.py`, `collection.py`)
instead of one giant `main.py`?** So each file stays focused on one concern,
and `main.py` stays a short "assemble the app" file. This mirrors the same
motivation as splitting `models.py` from `base.py` — one responsibility per
file.

---

## 6. SQLAlchemy models, line by line

```python
# backend/app/models/models.py
class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="collection_items_quantity_check"),
        UniqueConstraint("user_id", "card_id", name="uix_user_card"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    condition: Mapped[str | None] = mapped_column(String(50))
    added_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="collection_items")
    card: Mapped["Card"] = relationship(back_populates="collection_items")
```

Piece by piece:

- **`__table_args__`** — a tuple of extra table-level rules that don't
  belong to a single column. `CheckConstraint("quantity > 0", ...)` is
  enforced *by Postgres itself* — even if a bug in Python code tried to
  insert `quantity=0`, the database would refuse it. This is deliberate
  defense in depth: don't only trust application code to enforce business
  rules.
- **`UniqueConstraint("user_id", "card_id", ...)`** — no two rows can have
  the same `(user_id, card_id)` pair. This is *why* `add_to_collection` in
  `collection.py` can safely "add or bump quantity": the database itself
  guarantees one row per user-per-card, so the ORM query for "does this
  user already own this card" is guaranteed to find at most one match.
- **`Mapped[uuid.UUID]`** — `Mapped[...]` is SQLAlchemy 2.0's typed way of
  saying "this attribute, once loaded, will behave as this Python type."
  It's what lets your editor/type-checker know `some_item.quantity` is an
  `int`.
- **`mapped_column(...)`** — the actual column definition: its SQL type
  (`UUID(as_uuid=True)`, `Integer`, `String(50)`), whether it's a
  `primary_key`, a `default` (computed in *Python*, e.g. `uuid.uuid4` — a
  reference to the function itself, called fresh for each new row) versus
  `server_default` (computed by *Postgres*, e.g. `func.now()`), and
  `nullable=False` (this column is required).

  **Why `default=uuid.uuid4` for IDs instead of an auto-incrementing
  integer?** See [§15](#15-why-faq).

- **`ForeignKey("users.id", ondelete="CASCADE")`** — `user_id` must match an
  existing row's `id` in the `users` table. `ondelete="CASCADE"` tells
  Postgres: if that user is ever deleted, automatically delete their
  collection items too, rather than leaving orphaned rows or blocking the
  delete.
- **`index=True`** — builds a database index on this column, because the
  app frequently filters by `user_id` (`WHERE user_id = ...` in
  `get_collection`) — an index makes that lookup fast instead of scanning
  every row.
- **`relationship(back_populates="collection_items")`** — this is
  ORM-level, not a real database column. It tells SQLAlchemy: "when I load
  a `CollectionItem`, let me also reach `.user` and `.card` as Python
  objects (not just raw foreign-key IDs), and keep both sides in sync."
  `back_populates` names the matching relationship on the *other* class
  (`User.collection_items`, `Card.collection_items`) so SQLAlchemy knows
  they describe the same link from two directions.
- **`cascade="all, delete-orphan"`** (on `User.collection_items`) — if a
  `User` Python object is deleted through the ORM, delete its
  `CollectionItem` objects too. This is the **ORM-level** mirror of the
  **database-level** `ondelete="CASCADE"` above — belt and suspenders,
  because the ORM cascade only fires if you delete through SQLAlchemy,
  while the database constraint fires no matter what deletes the row.

---

## 7. Pydantic schemas, line by line

```python
# backend/app/schemas/card.py
class CardResponse(BaseModel):
    """SHape of a card return by the API."""   # <- typo in the docstring, harmless

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    ...
```

- **`class CardResponse(BaseModel)`** — inherits from Pydantic's
  `BaseModel`, which is what gives it automatic validation, parsing, and
  JSON (de)serialization based on the type hints below it.
- **`model_config = ConfigDict(from_attributes=True)`** — by default,
  Pydantic expects to build a model from a `dict`-like object
  (`CardResponse(**{"id": ..., "name": ...})`). But `cards.py` returns raw
  SQLAlchemy `Card` objects, not dicts. `from_attributes=True` tells
  Pydantic "also accept an object and read its *attributes*
  (`obj.id`, `obj.name`, ...) instead of dict keys." This is the bridge
  that lets FastAPI's `response_model=CardResponse` take an ORM object
  straight from the database query and turn it into the right JSON shape.

**Why does `CardResponse` duplicate fields that already exist on the
`Card` SQLAlchemy model?** This is one of the most important "why"s in the
whole codebase:

1. **Different job.** `Card` describes *what's stored in Postgres*.
   `CardResponse` describes *what the API promises callers it will return*.
   Those can and will diverge — e.g. you might add an internal column
   (`vendor_notes`) to `Card` that should never be exposed over the API;
   `CardResponse` simply won't list it, so it can't leak.
2. **Validation direction.** `Card` validates nothing on its own — it just
   reflects the database schema. `CollectionItemCreate` (below) validates
   *incoming* data before it ever touches the database.
3. **Decoupling.** If you rename a database column, you change one model
   and one schema deliberately — you're not fighting an ORM class that's
   also trying to be a wire format.

```python
# backend/app/schemas/collection.py
class CollectionItemCreate(BaseModel):
    """Shape of the requst body when adding a card to the collection"""

    card_id: uuid.UUID
    quantity: int = Field(default=1, ge=1, le=9999)
    condition: str | None = None
```

- **`Field(default=1, ge=1, le=9999)`** — like `Query(...)` in §3, but for a
  request *body* field instead of a query-string parameter. `ge`/`le` are
  short for "greater-or-equal" / "less-or-equal" — Pydantic rejects
  `quantity=0` or `quantity=10000` automatically, with a 422 response,
  before `add_to_collection`'s body ever runs. Compare this to the
  database-level `CheckConstraint("quantity > 0", ...)` in §6: the Pydantic
  check runs first and gives a friendlier error message; the database
  check is the last line of defense if something bypassed the API layer
  entirely (a script, a different service, a bug).

```python
class CollectionItemResponse(BaseModel):
    ...
    card: CardResponse
```

A Pydantic model can **nest another Pydantic model** as a field type. This
is what makes the collection endpoint return each item *with its card's
full details embedded*, instead of just a bare `card_id` the frontend would
have to look up separately.

---

## 8. FastAPI routes, line by line

```python
# backend/app/api/collection.py
router = APIRouter(prefix="/api/collection", tags=["collection"])
```

- **`prefix="/api/collection"`** — every route defined on this router is
  automatically mounted under this path, so `@router.get("")` really means
  `GET /api/collection`, and `@router.post("/items")` really means
  `POST /api/collection/items`. You don't repeat the prefix on every route.
- **`tags=["collection"]`** — purely for the auto-generated API docs
  (`/docs`) — groups these routes together visually. No effect on routing.

```python
@router.get("", response_model=CollectionResponse)
def get_collection(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
```

- **`response_model=CollectionResponse`** — tells FastAPI (and its
  generated docs) exactly what shape this endpoint promises to return.
  FastAPI will also *filter* the actual return value through this schema —
  if `get_collection` accidentally returned extra fields, they'd be
  silently dropped, not leaked.
- Two `Depends(...)` parameters — see §9, this is the mechanism doing real
  work here.

```python
@router.post("/items", response_model=CollectionItemResponse, status_code=201)
def add_to_collection(
    payload: CollectionItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
```

- **`payload: CollectionItemCreate`** — because this type is a Pydantic
  `BaseModel` (not a `Query`/`Depends`/primitive), FastAPI knows to read it
  from the **request body** as JSON and validate it against
  `CollectionItemCreate`'s rules before `add_to_collection` runs.
- **`status_code=201`** — HTTP 201 means "Created." Overriding the default
  (200) documents intent: this endpoint's success case is "a new thing now
  exists," which is the correct status per HTTP conventions.

```python
@router.delete("/items/{item_id}", status_code=204)
def remove_from_collection(
    item_id: uuid.UUID,
    ...
):
```

- **`{item_id}`** in the path is a **path parameter**. FastAPI extracts
  whatever's in that URL segment and, because the function parameter
  `item_id: uuid.UUID` is typed, automatically parses and validates it as a
  UUID — a malformed UUID in the URL gets rejected with a 422 before
  `remove_from_collection` runs.
- **`status_code=204`** — "No Content." Convention for a successful delete
  that has nothing to return.

```python
raise HTTPException(status_code=404, detail="Card not found")
```

**`raise`** stops normal execution and throws an exception. FastAPI has a
built-in handler for `HTTPException` specifically: it catches it and turns
it into a proper HTTP error response (status code + JSON body
`{"detail": "..."}`) instead of crashing the whole request with a 500.

---

## 9. Dependency injection with `Depends`

```python
def get_db():
    """FastAPI dependency that provides a database session per request."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

```python
def get_current_user(db: Session = Depends(get_db)) -> User:
    """TEMPORARY: fetch-or-create a dev user. Replaced by Clerk auth later."""
    user = db.scalar(select(User).where(User.clerk_user_id == TEMP_CLERK_ID))
    if user is None:
        user = User(clerk_user_id=TEMP_CLERK_ID, email="dev@tcgtracker.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
```

**What `Depends` actually does:** when FastAPI sees a route parameter like
`db: Session = Depends(get_db)`, it doesn't call `get_db` itself in your
code — *FastAPI* calls it, before your route function runs, and passes the
result in as that parameter's value. This is **dependency injection**: your
route function declares what it needs ("a database session"), and something
else is responsible for constructing it.

**Why not just call `SessionLocal()` directly inside each route?** Because
then every route would duplicate the open/close logic, and — more
importantly — nobody would be reminded to *close* the session if an
exception happened partway through. `Depends` centralizes that lifecycle in
one place (`get_db`) and FastAPI guarantees it runs for every request that
declares it.

**Why can `get_current_user` itself use `Depends(get_db)`?** Dependencies
can depend on other dependencies — FastAPI resolves the whole chain. So
`get_current_user` gets handed a working `db` session without needing to
know *how* one gets created.

**Why is this `yield` instead of `return` in `get_db`?** Covered in §10.

---

## 10. The database session lifecycle

```python
# backend/app/core/database.py
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- **`engine`** — represents the connection *machinery* to the database
  (connection pool, dialect, etc.). Created once, at import time, and
  reused for the life of the process. `pool_pre_ping=True` makes
  SQLAlchemy test each pooled connection with a cheap ping before reusing
  it — cloud Postgres providers (like Neon) can silently drop idle
  connections, so without this you'd occasionally get a confusing "server
  closed the connection" error on an old, stale connection.
- **`sessionmaker(...)`** — not a session itself, but a *factory* for
  creating sessions. `SessionLocal()` (calling it) produces one new
  `Session` object. `autocommit=False` / `autoflush=False` mean: nothing
  is written to the database until code explicitly calls `db.commit()` —
  you stay in control of transaction boundaries rather than SQLAlchemy
  guessing when to flush.
- **`yield` instead of `return`** — this is what makes `get_db` a
  **generator function**, and it's the specific shape FastAPI's dependency
  system expects for "setup, hand over a value, then guaranteed
  teardown." Execution pauses at `yield db`, FastAPI runs your whole route
  using that `db`, and *then* control returns to `get_db` to run whatever
  comes after `yield` — here, the `finally: db.close()`. Because it's a
  `try/finally`, the session gets closed even if the route raised an
  exception — you don't leak an open database connection every time
  something goes wrong.

**Why one session per request instead of one global session reused
everywhere?** SQLAlchemy sessions aren't safe to share across concurrent
requests, and a session accumulates identity-map state over time. A fresh
session per request is simple, correct, and matches how a web server
actually works (many requests, potentially concurrent).

---

## 11. Settings and environment variables

```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    DATABASE_URL: str
    ENVIRONMENT: str = "development"

settings = Settings()
```

- **`BaseSettings`** — a Pydantic class specialized for reading config from
  environment variables (and, per `env_file=".env"`, from a local `.env`
  file too). It matches each class attribute (`DATABASE_URL`) to an
  environment variable of the same name.
- **Why `DATABASE_URL: str` has no default, but `ENVIRONMENT` does** — a
  field with no default is **required**: if `DATABASE_URL` isn't set
  anywhere, `Settings()` raises an error immediately at startup, which is
  exactly what you want (fail loud and immediately, not with a confusing
  error the first time a route touches the database). `ENVIRONMENT`
  defaults to `"development"` because it's fine for that one to have a
  sane fallback.
- **`extra="ignore"`** — if the `.env` file has *other* variables this
  class doesn't declare, don't error out; just ignore them.
- **`settings = Settings()`** — this line runs once, when this module is
  first imported, and creates the one shared instance every other file
  imports (`from app.core.config import settings`).

**Why keep secrets like `DATABASE_URL` in an untracked `.env` file instead
of hardcoding them in `config.py`?** So the connection string (which
contains a password) never gets committed to git, and so the same code can
point at a different database in different environments (local dev vs.
production) just by swapping the `.env` file — zero code changes.

---

## 12. Alembic migrations

```python
# backend/alembic/versions/7a4e076c1b36_create_initial_tables.py
def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('cards',
        sa.Column('id', sa.UUID(), nullable=False),
        ...
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('prices')
    ...
```

**The problem Alembic solves:** your SQLAlchemy model classes describe what
the database *should* look like, but changing a Python class doesn't
change the actual live database — someone has to run `ALTER TABLE`
statements against it. Alembic auto-generates those statements by diffing
your models against the current database state, and saves each diff as a
timestamped, revision-numbered Python file like this one.

- **`upgrade()`** — the SQL-equivalent operations (via `op.create_table`,
  `op.create_index`, etc. — SQLAlchemy's schema-operation API, not raw SQL
  strings) to move the database *forward* to this revision.
- **`downgrade()`** — the exact inverse, to roll back to the previous
  revision if needed. Notice it undoes things in **reverse order** from
  `upgrade` (drop `prices` before dropping `cards`, since `prices` has a
  foreign key *into* `cards` — you can't drop a table something still
  references).
- **`revision` / `down_revision`** — each migration file has a unique ID
  and points at the ID of the migration before it, forming a linked chain.
  This is how Alembic knows the *order* to apply migrations in, even if
  multiple developers create migration files independently.

**Why keep this as versioned files instead of just running
`CREATE TABLE` once by hand?** Multiple environments (your machine, a
teammate's machine, production) need to reach the *same* schema, in the
*same* order, reproducibly — and you need a way to roll back a bad schema
change. A migration history is a changelog for your database structure.

---

## 13. The seed script

```python
# backend/scripts/seed_cards.py
def main() -> None:
    db = SessionLocal()
    created, skipped = 0, 0

    try:
        for card_data in SEED_CARDS:
            exists = db.scalar(
                select(Card).where(Card.external_id == card_data["external_id"])
            )
            if exists is not None:
                skipped += 1
                continue

            card = Card(
                **card_data,
                current_price_updated_at=datetime.now(timezone.utc),
            )
            db.add(card)
            created += 1

        db.commit()
        print(f"✓ Seed complete: {created}, created, {skipped} skipped")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

- **`created, skipped = 0, 0`** — **tuple unpacking**: the right side
  `0, 0` is a two-element tuple; Python assigns the first element to
  `created` and the second to `skipped` in one line.
- **`for card_data in SEED_CARDS:`** — `SEED_CARDS` is a plain Python
  `list` of `dict`s defined above this function. A `for` loop over a list
  gives you each element (each `dict`) in turn.
- **`db.scalar(select(Card).where(...))`** — SQLAlchemy's modern
  query style: `select(Card)` builds a `SELECT` statement targeting the
  `Card` table, `.where(...)` adds a `WHERE` clause, and `db.scalar(...)`
  runs it and returns a single value (here, either a `Card` object or
  `None`) rather than a list of rows.
- **Why check for an existing row before inserting (`if exists is not
  None: skipped += 1; continue`)?** This makes the script **idempotent** —
  safe to run more than once without creating duplicate cards. Re-running
  a seed script is common (after a fresh clone, after a database reset),
  so this guard matters.
- **`continue`** — skips the rest of *this loop iteration* and jumps to the
  next item in `SEED_CARDS`, without running the insert code below it.
- **`Card(**card_data, current_price_updated_at=...)`** — `**card_data`
  **unpacks a dict into keyword arguments**. Since `card_data` is e.g.
  `{"external_id": "seed-pkm-001", "name": "Charizard ex", ...}`, this line
  is equivalent to writing
  `Card(external_id="seed-pkm-001", name="Charizard ex", ..., current_price_updated_at=...)`
  by hand — but works for every dict in the list without repeating each
  field name.
- **`db.add(card)`** then **`db.commit()`** *outside* the loop — every new
  `Card` is staged in the session first, and only written to the database
  once, in a single transaction, after the whole loop finishes. If
  anything failed partway through, nothing would have been committed yet.
- **`except Exception: db.rollback(); raise`** — if anything above throws,
  undo any partial staged changes (`rollback`), then **`raise`** with no
  argument, which re-throws the *same* exception instead of swallowing it.
  This keeps the script from silently succeeding when something actually
  went wrong, while still guaranteeing cleanup.
- **`finally: db.close()`** — runs no matter what (success, handled
  failure, or re-raised failure) — the session's connection always gets
  released.
- **`Decimal("312.50")`** — string-constructed, not `Decimal(312.50)`. See
  [§15](#15-why-faq) for why money is `Decimal` at all; the *string*
  constructor specifically avoids ever passing through an imprecise
  `float` on the way to becoming a `Decimal`.

---

## 14. Tracing one request start to finish

Put it all together: what actually happens when a client calls
`POST /api/collection/items` with `{"card_id": "...", "quantity": 2}`?

1. **Uvicorn** (the ASGI server, not shown above but what actually runs
   `app.main:app`) receives the raw HTTP request and hands it to FastAPI.
2. FastAPI matches the path + method against the routes registered via
   `app.include_router(collection_router)` → finds
   `add_to_collection` in `collection.py`.
3. FastAPI sees `payload: CollectionItemCreate` and parses the JSON body
   into that Pydantic model — validating `card_id` is a real UUID and
   `quantity` is between 1 and 9999 (§7). Fails here → 422 response,
   your function never runs.
4. FastAPI resolves `db: Session = Depends(get_db)` — calls `get_db()`,
   gets a session via `yield` (§9, §10).
5. FastAPI resolves `user: User = Depends(get_current_user)` — which
   itself depends on `db`, so FastAPI reuses the *same* session instance
   from step 4, then queries or creates the dev user.
6. Your function body runs: looks up the `Card` by `payload.card_id`
   (404 via `HTTPException` if missing — §8), checks for an existing
   `CollectionItem` for this `(user, card)` pair, either bumps `quantity`
   or creates a new row, `db.commit()`s.
7. FastAPI takes whatever your function returned (a `CollectionItem` ORM
   object) and filters it through `response_model=CollectionItemResponse`
   — using `from_attributes=True` (§7) to read `.id`, `.quantity`, `.card`,
   etc. off the ORM object — and serializes that to JSON.
8. The `finally: db.close()` inside `get_db` runs, releasing the session,
   *after* the response has been built.

Every section above is one link in this chain.

---

## 15. Why FAQ

**Why `Decimal` instead of `float` for prices?**
`float` is binary floating point — it cannot represent most decimal
fractions exactly (`0.1 + 0.2 != 0.3` in binary float math). For money,
that's not a rounding curiosity, it's a correctness bug waiting to compound
across thousands of rows. `Decimal` represents base-10 numbers exactly, at
the cost of being slightly slower — a trade this app happily makes.

**Why UUIDs for primary keys instead of auto-incrementing integers?**
An integer ID leaks information (row count, insertion order) and collides
if you ever merge data from two databases (two different "row 5"s). A
UUID, generated in Python via `uuid.uuid4` *before* the row is even
inserted, is globally unique, safe to expose in a public API URL, and lets
the app assign an ID without a round trip to the database first.

**Why do database-level constraints (`CheckConstraint`,
`UniqueConstraint`) exist when Pydantic already validates the input?**
Defense in depth. Pydantic validation only runs for requests that go
*through the API*. A future script, a different service, a manual database
edit, or a bug in the Python code could all bypass it — the database
constraint is the one guarantee that can never be skipped, because
Postgres itself enforces it.

**Why separate Pydantic schemas from SQLAlchemy models at all** (asked
again here because it's the single most "why is this project structured
like this" question)? Covered fully in §7 — short version: one describes
storage, the other describes the API contract, and they're allowed to
diverge on purpose.

**Why does `get_current_user` exist as a fake/temporary thing
(`TEMP_CLERK_ID = "dev_temp_user"`)?** Real user authentication (via
Clerk, per the `clerk_user_id` column already on `User`) isn't wired up
yet. Rather than block all collection features on finishing auth first,
the project stubs it with "always fetch-or-create one dev user" — visible,
explicit, and clearly labeled `TEMPORARY` in the docstring — so real auth
can drop in later by replacing just this one function.

**Why `selectinload(CollectionItem.card)` in `get_collection`?**

```python
items = db.scalars(
    select(CollectionItem)
    .where(CollectionItem.user_id == user.id)
    .options(selectinload(CollectionItem.card))
    ...
).all()
```

Without it, accessing `item.card` for each item would trigger a *separate*
database query per item the first time it's touched (the "N+1 query"
problem — 1 query for the items, then N more, one per item, for their
cards). `selectinload` tells SQLAlchemy to fetch all the related `Card`
rows in one extra query up front, regardless of how many items there are.

**Why `sum(...)` with a generator expression for `total_value`?**

```python
total_value = sum(
    (item.card.current_price_usd or Decimal("0")) * item.quantity
    for item in items
)
```

`(x for x in items)` (no square brackets) is a **generator expression** —
like a list comprehension, but it produces values lazily one at a time
instead of building a whole list in memory first. For summing, that's
strictly better: `sum()` only ever needs one value at a time, so there's no
reason to materialize an intermediate list.
`item.card.current_price_usd or Decimal("0")` handles the case where a
card has no price yet (`current_price_usd` is `None`) — `None or
Decimal("0")` evaluates to `Decimal("0")`, because `or` returns its first
"truthy" operand, and `None` is falsy.

---

## 16. Glossary

- **Module** — a single `.py` file.
- **Package** — a folder of modules, importable as a unit because of an
  `__init__.py`.
- **Type hint** — `name: Type` annotation. Not enforced by plain Python by
  itself, but read and enforced at runtime by Pydantic/FastAPI here.
- **Decorator** (`@thing`) — wraps the function below it; used here to
  register HTTP routes.
- **ORM** (Object-Relational Mapper) — maps Python classes to database
  tables (SQLAlchemy).
- **Migration** — a versioned, runnable script that changes a database
  schema from one state to the next (Alembic).
- **Dependency injection** — a function declares what it needs as a
  parameter; the framework supplies it (`Depends`).
- **Generator function** — a function using `yield` instead of (only)
  `return`; pauses and resumes rather than running start-to-finish in one
  go.
- **Idempotent** — running an operation multiple times has the same effect
  as running it once (the seed script's "skip if it already exists"
  check).
- **N+1 query problem** — accidentally issuing one query per row in a
  result set instead of one batched query; solved here with
  `selectinload`.
- **Docstring** — a string literal as the first statement in a
  module/class/function, attached as its `__doc__`; documentation, not a
  comment.

---

*This file was generated from the actual code in `backend/` as of the
Phase 9 commit. If the code changes, re-generate or update this doc so it
doesn't go stale — a teaching doc that lies about the code is worse than
none.*
