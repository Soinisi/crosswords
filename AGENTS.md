# AGENTS.md

## Setup
- Copy `.env` from the repo root and fill in `OPENAI_API_KEY` + `OPENAI_BASE_URL` (remote) or `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL_NAME` (local llamafile).
- `pip install -r requirements.txt` (also needs `python-dotenv`, not listed).
- The app reads `.env` from the cwd (repo root) at import time via `load_dotenv()` in `crossword_creator.py`.

## Package structure
- Single flat package: `crossword_creator/`. All modules are siblings. No `setup.py`/`pyproject.toml`.
- Entrypoints: `app.py` (Flask web server), `crossword_creator.py` (CLI grid+clue pipeline), `grid_creator.py` (interactive grid generator).

## Commands
```bash
# Dev web server (debug=True, Flask reload)
python -m crossword_creator.app

# Production: generate crossword + clues, then serve via waitress on 0.0.0.0:5000
python -m crossword_creator.app prod

# Generate grid + AI clues and write crossword.json (no web server)
python -m crossword_creator.crossword_creator prod

# Generate N crosswords at once (with progress + ETA)
python -m crossword_creator.crossword_creator prod 10

# Same with debug logging
python -m crossword_creator.crossword_creator --verbose

# Interactive grid generation (prompts for dimensions)
python -m crossword_creator.grid_creator
```

## Data flow
1. `wl.txt` — 91K-line word dictionary (all-caps; used as-is).
2. `grid_creator.py` — backtracking solver with NumPy. Writes raw grids to `crossword_grids.txt` (one `list[str]` per line, Python repr format).
3. `crossword_creator.py` — reads `crossword_grids.txt`, calls OpenAI (`gpt-4.1`) for clues via `pydantic-ai`, writes `crossword.json`.
4. `app.py` — reads `crossword.json`, renders interactive HTML crossword, then renames the served key from `crossword_N` to `used_crossword_N` (each crossword served once).
5. `site/index.html` — standalone static page for Netlify. Fetches `crossword.json`, picks today's crossword by date (`daysSinceEpoch % total`). Same crossword for all users each day.

## Key files
| File | Role |
|---|---|
| `crossword.json` | Active crossword data (grids + clues). Mutated by `app.py` on startup. Read by `site/index.html` at runtime. |
| `crossword_arc.json` | Archive of older crosswords. Never read at runtime. |
| `crossword_grids.txt` | Raw generated grids (Python list reprs). Append-only from grid generator. |
| `netlify.toml` | Netlify deploy config. Publish dir = `crossword_creator/site`. Build command = `python -m crossword_creator.app build`. |
| `site/index.html` | Standalone crossword SPA for Netlify. Date-based puzzle selection. |
| `site/crossword.json` | Copy of crossword data for static deployment. Built by `app.py build`. |
