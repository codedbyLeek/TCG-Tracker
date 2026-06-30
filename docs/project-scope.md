                                                                                                                                     # TCG Price Tracker - Project Scope

## Project Intent

Build a guided, beginner-friendly Python project that tracks trading card prices over time. The app should feel useful quickly, while leaving room to grow into a more polished tracker with saved collections, price history, alerts, and charts.

The learning goal matters as much as the product goal: the project should be built mostly by Malik, with Codex acting as a guide, reviewer, debugger, and design partner.

## Working Agreement

- Malik writes most of the code.
- Codex scopes features, explains concepts, reviews code, helps debug errors, and gives small implementation prompts.
- Codex can scaffold only when explicitly asked.
- Each build step should produce something visible or testable.
- Prefer small, working slices over large rewrites.

## Product Hypothesis

Collectors want a simple way to watch the market value of cards they care about without manually checking the same sites every day.

The first version should answer:

- What cards am I tracking?
- What is each card currently worth?
- How has the price changed since I started tracking it?
- Which cards need my attention?

## Target User

A TCG collector or reseller who wants a lightweight personal tracker for cards across one or more games, starting with manual or semi-automated price entry before adding richer integrations.

## Initial Game Scope

Pick one game first to keep the data model simple.

Suggested starting options:

- Pokemon TCG
- Magic: The Gathering
- Yu-Gi-Oh!

Recommended first choice: Pokemon TCG, because card names, sets, variants, and market-price APIs are common enough to make examples approachable.

## MVP Features

### 1. Card Watchlist

Users can add a card to track.

Fields:

- Card name
- Game
- Set name
- Card number
- Variant or printing
- Notes

### 2. Current Price

Each tracked card shows a latest price.

MVP approach:

- Start with manually entered prices.
- Store each price with a date.
- Later replace or supplement this with API lookups.

### 3. Price History

Each card has a simple history view.

MVP approach:

- Table of price entries by date.
- Basic high, low, latest, and change since first entry.

### 4. Dashboard

The home screen summarizes tracked cards.

Useful signals:

- Total tracked cards
- Estimated collection/watchlist value
- Biggest gainers
- Biggest drops
- Cards missing recent prices

### 5. Search and Filter

Users can narrow the watchlist.

Filters:

- Game
- Set
- Variant
- Price status

## Not MVP Yet

Avoid these until the manual tracker works:

- Account login
- Payment or monetization
- Multi-user sharing
- Automated scraping
- Complex inventory management
- Predictive pricing
- Mobile app packaging

## Possible Tech Shape

Since this is a Python project, start with one of these paths:

### Option A: Streamlit

Best for fastest visible progress.

Good fit if the priority is learning Python, data handling, and charts.

Likely stack:

- Python
- Streamlit
- SQLite
- pandas
- plotly or altair

### Option B: Flask

Best for learning web app fundamentals.

Good fit if the priority is routes, templates, forms, and backend structure.

Likely stack:

- Python
- Flask
- SQLite
- SQLAlchemy
- Jinja templates

### Option C: FastAPI + Frontend

Best for a more modern full-stack app.

Good fit later, but probably too much for the first learning slice.

Likely stack:

- Python
- FastAPI
- SQLite/PostgreSQL
- React or plain HTML frontend

Recommended path: Streamlit first, then graduate to Flask or FastAPI if the app outgrows it.

## Figma-Ready Screen Map

Use these as top-level frames if designing in Figma.

### Frame 1: Dashboard

Purpose: quick overview of the watchlist.

Sections:

- Header with app name and add-card button
- Summary metrics row
- Watchlist table
- Biggest movers panel
- Cards needing update panel

### Frame 2: Add Card

Purpose: add a card to the tracker.

Fields:

- Game
- Card name
- Set
- Card number
- Variant
- Starting price
- Price date
- Notes

### Frame 3: Card Detail

Purpose: inspect one card.

Sections:

- Card identity block
- Latest price
- Change since first tracked price
- Price history chart
- Price history table
- Add price entry form

### Frame 4: Settings / Data

Purpose: manage local data.

Sections:

- Export CSV
- Import CSV
- Database location
- API key placeholder for future integrations

## First Wireframe

```text
+------------------------------------------------------------------+
| TCG Price Tracker                                      [+ Card]   |
+------------------------------------------------------------------+
| Cards Tracked | Watchlist Value | Biggest Gain | Needs Update     |
|      12       |     $486.20     | Charizard    |      3 cards     |
+------------------------------------------------------------------+
| Search cards...                         Game v   Status v        |
+------------------------------------------------------------------+
| Card              Set              Latest   Change   Last Updated |
| Charizard ex      151              $42.10   +8.2%    Today        |
| Pikachu promo     Black Star       $18.50   -2.1%    3 days ago   |
| Lugia V           Silver Tempest   $7.80    +0.0%    9 days ago   |
+------------------------------------------------------------------+
| Biggest Movers                    | Needs Price Update            |
| Charizard ex +8.2%                | Lugia V - 9 days old          |
| Mewtwo GX +4.4%                   | Umbreon VMAX - 12 days old    |
+------------------------------------------------------------------+
```

## Data Model Draft

### cards

- id
- game
- name
- set_name
- card_number
- variant
- notes
- created_at

### price_entries

- id
- card_id
- price
- currency
- source
- price_date
- created_at

## Guided Build Milestones

### Milestone 1: Project Setup

Goal: run a tiny Python app locally.

Malik builds:

- Create virtual environment
- Install chosen framework
- Run hello-world app

Codex helps:

- Explain each command
- Debug environment issues
- Review folder structure

### Milestone 2: Static Dashboard

Goal: show a dashboard with fake card data.

Malik builds:

- App file
- Sample list of cards
- Basic table
- Summary metrics

Codex helps:

- Explain lists/dicts or dataframe choices
- Review layout

### Milestone 3: Add Cards

Goal: add cards through a form.

Malik builds:

- Form fields
- Validation
- Store data locally

Codex helps:

- Explain state and persistence
- Debug form behavior

### Milestone 4: Save to SQLite

Goal: make tracked cards survive app restarts.

Malik builds:

- Database file
- Table creation
- Insert and read functions

Codex helps:

- Review SQL
- Explain relationships

### Milestone 5: Price History

Goal: add repeated prices per card.

Malik builds:

- Price entry form
- History table
- Basic chart

Codex helps:

- Explain one-to-many data
- Help test edge cases

### Milestone 6: Polish and Export

Goal: make it feel like a real tool.

Malik builds:

- Filters
- CSV export
- Empty states
- Error messages

Codex helps:

- Review UX
- Suggest cleanup

## Next Decision

Choose the first build path:

- Streamlit: fastest and most visual
- Flask: better web fundamentals
- FastAPI + frontend: most advanced

Recommended next step: choose Streamlit and design the Dashboard frame in Figma or a rough sketch before writing code.
