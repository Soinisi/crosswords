# MiniWöördi — Crossword Puzzle Generator

Generates crossword grids from a 91K-word dictionary, produces AI-powered clues via OpenAI, and serves an interactive web puzzle with a timer and win celebration.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt python-dotenv
```

Create `.env` in the repo root. Use **either** remote OpenAI **or** a local llamafile (see below).

```bash
# Remote OpenAI (cloud)
echo 'OPENAI_API_KEY=your-key-here' > .env
echo 'OPENAI_BASE_URL=https://api.openai.com/v1' >> .env
```

The `.env` is loaded at import time from the current working directory (repo root) by `load_dotenv()` in `crossword_creator.py`.

### Remote OpenAI (cloud)
Set `OPENAI_API_KEY` and optionally `OPENAI_BASE_URL` in `.env`. The default model is `gpt-4.1`.

### Local model (offline testing)
Start a llamafile in a separate terminal:
```bash
/home/simo/projects/ai/llm_models/Qwen3.5-4B-Q5_K_S.llamafile
```
Then in `.env`:
```bash
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=not-needed
LLM_MODEL_NAME=local
```
The llamafile serves an OpenAI-compatible HTTP API on `localhost:8080` — no API key required. Omit all `LLM_*` vars to use remote OpenAI as before.

## Quick start

```bash
# Dev server with auto-reload (debug mode)
python -m crossword_creator.app

# Then open http://127.0.0.1:5000/minicrossword
```

## Deploy to Netlify

The production frontend is a static HTML page that loads `crossword.json` and picks today's crossword based on the date (Wordle-style — same puzzle for all users each day).

```bash
# 1. Generate crosswords (e.g. 30 days worth)
python -m crossword_creator.crossword_creator prod 30

# 2. Build the static site
python -m crossword_creator.app build

# 3. Deploy
netlify deploy --prod
```

The site folder (`crossword_creator/site/`) contains:
- `index.html` — standalone crossword player (date-based selection, all interactive features)
- `crossword.json` — pre-generated crossword data

## Commands

### Web server

| Command | Description |
|---|---|
| `python -m crossword_creator.app` | Flask dev server (debug=True, reload on change, localhost only) |
| `python -m crossword_creator.app prod` | Generate a fresh crossword, then serve via waitress on `0.0.0.0:5000` |
| `python -m crossword_creator.app build` | Copy `crossword.json` into `site/` for static deployment |

### Generating crosswords (no web server)

| Command | Description |
|---|---|
| `python -m crossword_creator.crossword_creator prod` | Generate 1 grid + AI clues and write `crossword.json` |
| `python -m crossword_creator.crossword_creator prod 30` | Generate 30 crosswords at once (with progress + ETA) |
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
     crossword_creator.py    ← LLM via pydantic-ai (OpenAI / local llamafile)
              │
        crossword.json       ← grids + clues
           /       \
          /         \
      app.py       site/index.html
   (Flask dev)    (static, Netlify)

```

**Crossword selection**: The static site uses the current date (`days since epoch % total`) to pick a crossword — every user gets the same puzzle each day. The Flask dev server uses sequential one-time consumption (renames `crossword_N` → `used_crossword_N`).

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

| Env var | Default | Purpose |
|---|---|---|
| `LLM_MODEL_NAME` | `gpt-4.1` | Model name sent to the endpoint |
| `LLM_BASE_URL` | `OPENAI_BASE_URL` | API base URL |
| `LLM_API_KEY` | `OPENAI_API_KEY` | API key |

Set `LLM_*` vars to override for local models. Unset them to use the OpenAI cloud defaults.
