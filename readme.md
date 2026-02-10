# Yu-Gi-Oh Probability Calculator

This app is a hands-on toolkit for testing opening hands, handtraps, and decklist variants. It’s built for fast iteration: define your ideal hands, compare variants side-by-side, and run simulations or optimizations without leaving the UI.

## Quick Start

- Install dependencies: `pip install -r requirements.txt`
- Run with `python run.py` (or your venv’s Python).
- Open or create a project file (`.deckdb` recommended, `.json` supported).
- Start with the **Deck** tab, then define **Ideal Hands** and **Handtraps**, and finally run **Simulation** or **Optimize**.

## Core Ideas (Glossary)

- **Deck variant**: A separate decklist you can compare against others.
- **Swap Bench**: A per-variant parking area for cards you don’t want in that decklist right now.
- **Ideal hand**: A named set of requirements that describe a “good opening.”
- **Must (AND)**: All entries must be present in the hand.
- **OR groups**: Each group needs at least one of its options to be present.
- **Hand reference**: An ideal hand can reference another ideal hand (re-using it as a requirement).

## Tabs

### 1) Deck

This is where deck variants live.

- **Variant tabs**: Each tab is a decklist variant. Click the `+` tab to create a new variant.
- **Rename / Delete**: Right-click a variant tab for rename and delete.
- **Add / Update / Remove**: Edit cards in the active variant.
- **Card settings**: Double-click a card (or press the button) to open card settings.
- **Swap Bench**: Move cards between the deck and the bench using the arrow buttons.

### 2) Ideal Hands

Define what counts as a good opening hand.

- **Must cards (AND)**: Required cards or hand references (shown with an arrow).
- **OR groups**: Create groups where at least one option must be satisfied.
- **Hand references**: You can use another ideal hand as a requirement to avoid re-selecting the same cards. This is displayed as `↪ Hxx - Name`.

Naming:
- The app prefixes ideal hands with a card-count estimate (e.g., `2C - ...` or `2-3C - ...`).
- The range reflects possible OR-group sizes and referenced hands.

### 3) Handtraps

Assign handtrap effects per ideal hand.

- Effects are stored per ideal hand.
- Used for stats in Simulation (impact or draw-type traps).

### 4) Optimize

Searches for a better list based on your ideal hands.

- **Pick a variant** to optimize.
- **Min/Max deck size**: Constrains the total deckcount.
- **Per-card limits**: Each card can have a min/max (0–3), plus a lock to freeze it.
- **Deckcount as a variable**: The optimizer can add blanks to reach a higher deckcount, but it will not remove real cards just to create blanks.
- **Tag priorities**: Weight specific tags to bias the search (optional).

Progress and feedback:
- Steps and evaluations are shown live (you see how many candidates are being tested).
- ETA is estimated from recent step times.
- The result summary shows base vs. optimized probability and deck size.
- Optimization state is saved on pause and can be resumed after reloading.

### 5) Simulation

Runs Monte‑Carlo simulations across all variants.

- **Opening probability** per variant (any ideal hand).
- **Per‑ideal‑hand results** in separate tabs for each variant.
- **Handtrap means** and distributions.
- **Base variant**: Right‑click a variant in the results table and set it as the base for deltas.

## Card Settings (Tags + Draw Effects)

Each card can have tags and optional draw effects.

Tags:
- Engine
- Engine requirement
- Endboard piece
- Extender
- Non‑engine

Draw effects:
- **Draw N**: Adds extra draws to the evaluation.
- **Cost mode**: Optional discard/banish costs.
- **Cost cards**: Limit the cost to specific cards.

These settings are considered during simulations and optimization.

## Metrics (RKI / TOE)

Simulation results include two metrics to compare variants at a glance:

- **RKI** (Road‑of‑the‑King‑inspired): A weighted consistency score that rewards strong openings and penalizes bloated hands.
- **TOE** (Theory‑of‑Everything‑inspired): A composite measure combining consistency, resilience, and complexity.

Higher values are better.

## Notes

- All UI labels are in English.
- Bench cards are known to the system with a count of 0, so ideal hands referencing them won’t error.
- JSON files are versioned; old projects are migrated automatically when possible.
- `.deckdb` is the preferred format for faster incremental saves.

---

If you want additional features or a specific workflow, just ask.
