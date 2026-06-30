# TCG Tracker

A multi-user web app for tracking prices of Pokémon and One Piece trading cards.
Users can search a catalog, build personal collections, and see total collection value.

## Tech Stack

- **Backend**: FastAPI (Python 3.12), SQLAlchemy 2.0, Alembic, APScheduler
- **Frontend**: Next.js, Tailwind CSS, shadcn/ui
- **Database**: PostgreSQL (Neon) — SQLite locally
- **Storage**: Cloudflare R2 for card images
- **Auth**: Clerk
- **Hosting**: Railway (backend) + Vercel (frontend)

## Project Structure

```
tcg-tracker/
├── backend/    FastAPI API + sync jobs
├── frontend/   Next.js web app
└── docs/       Architecture diagrams, ER diagram, user flows
```

## Local Development

See `backend/README.md` and `frontend/README.md` for setup instructions.

## Status

🚧 In development — v1 in progress.