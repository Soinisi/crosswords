# MiniWöördi — Crossword Puzzle Generator

Generates crossword grids from a 91K-word dictionary, produces AI-powered clues via OpenAI, and serves an interactive web puzzle with a timer and win celebration.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt python-dotenv

# 2. Create .env in the repo root
echo 'OPENAI_API_KEY=your-key-here' > .env
echo 'OPENAI_BASE_URL=https://api.openai.com/v1' >> .env
```

The `.env` is loaded at import time from the current working directory (repo root) by `load_dotenv()` in `crossword_creator.py`.

## Quick start

```bash
# Dev server with auto-reload (debug mode)
python -m crossword_creator.app

# Then open http://127.0.0.1:5000/minicrossword
```

## Commands

### Web server

| Command | Description |
|---|---|
| `python -m crossword_creator.app` | Flask dev server (debug=True, reload on change, localhost only) |
| `python -m crossword_creator.app prod` | Generate a fresh crossword, then serve via waitress on `0.0.0.0:5000` |

### Generating crosswords (no web server)

| Command | Description |
|---|---|
| `python -m crossword_creator.crossword_creator prod` | Generate grid + AI clues and write `crossword.json` |
| `python -m crossword_creator.crossword_creator --verbose` | Same with debug-level logging |

### Interactive grid generation

```bash
python -m crossword_creator.grid_creator
# Prompts for row length range, column count range, and number of grids.
# Generated grids are appended to crossword_grids.txt.
```

## Architecture

```
           wl.txt
              │
      grid_creator.py        ← backtracking NumPy solver
              │
      crossword_grids.txt    ← raw grids (Python repr format)
              │
     crossword_creator.py    ← OpenAI gpt-4.1 via pydantic-ai
              │
        crossword.json       ← grids + clues
              │
           app.py            ← Flask + HTML crossword
              │
     http://host/minicrossword
```

## Files

| File | Purpose |
|---|---|
| `crossword.json` | **Active** crossword data. Mutated by `app.py` on startup — the served crossword key is renamed from `crossword_N` to `used_crossword_N` so no puzzle repeats. |
| `crossword_arc.json` | Archive of previously served crosswords. Never read at runtime — manual backup store. |
| `crossword_grids.txt` | Raw grids output by the solver, one `list[str]` per line. Append-only from `grid_creator.py`. |
| `wl.txt` | 91,733-line word dictionary. All-caps proper nouns + common words. Used as-is by the solver. |

## Dependencies

- `flask` — web server
- `waitress` — production WSGI server (used in `prod` mode)
- `pydantic-ai-slim[openai]` — AI agent for clue generation
- `numpy` — fast array-based word matching in the grid solver
- `python-dotenv` — loads `.env` (not in `requirements.txt`, install manually)

## Model

Clue generation uses `gpt-4.1` via `pydantic-ai`. To change the model, edit `crossword_creator.py:19`.
