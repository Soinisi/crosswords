# AGENTS.md

## Setup

- Copy `.env` from the repo root and fill in `OPENAI_API_KEY` + `OPENAI_BASE_URL` for remote OpenAI, or `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL_NAME` for a local llamafile.
- `pip install -r requirements.txt` installs Python generation dependencies.
- `pip install -r requirements-dev.txt` adds `pytest` for the test suite.
- `npm install` installs the Node/Vite static-site dev server.
- The Python generator reads `.env` from the cwd via `load_dotenv()` in `crossword_creator.py`.

## Package Structure

- Single flat Python package: `crossword_creator/`. All modules are siblings. No `setup.py`/`pyproject.toml`.
- Python is generation-only. The user-facing app is static HTML/CSS/JS in `crossword_creator/site/index.html`.
- Entrypoints: `crossword_creator.py` (grid+clue pipeline), `grid_creator.py` (interactive grid generator), `npm run dev` (local UI server).

## Commands

```bash
# Local static UI server (Node/Vite)
npm run dev

# Generate grid + AI clues and write crossword.json
python -m crossword_creator.crossword_creator prod

# Generate N crosswords at once (with progress + ETA)
python -m crossword_creator.crossword_creator prod 10

# Same with debug logging
python -m crossword_creator.crossword_creator --verbose

# Interactive grid generation (prompts for dimensions)
python -m crossword_creator.grid_creator

# Run the Python tests (clue-provider tests mock the opencode subprocess)
python -m pytest

# Copy generated data into the static site for local preview
cp crossword_creator/crossword.json crossword_creator/site/crossword.json
```

## Data Flow

1. `wl.txt` - 91K-line word dictionary (all-caps; used as-is).
2. `grid_creator.py` - backtracking solver with NumPy. Writes raw grids to `crossword_grids.txt` (one `list[str]` per line, Python repr format).
3. `crossword_creator.py` - reads `crossword_grids.txt`, calls an OpenAI-compatible API for clues via `pydantic-ai` by default, or the opencode CLI when `CLUE_PROVIDER=opencode`, and writes `crossword.json`.
4. Netlify build - copies `crossword_creator/crossword.json` to `crossword_creator/site/crossword.json`.
5. `site/index.html` - standalone static app. Fetches `crossword.json`, picks today's crossword by visitor-local date, and changes puzzle at local midnight.

## Key Files

| File | Role |
|---|---|
| `crossword.json` | Generated crossword data. Source copied into the static site at deploy time. |
| `crossword_arc.json` | Archive of older crosswords. Never read at runtime. |
| `crossword_grids.txt` | Raw generated grids (Python list reprs). Append-only from grid generator. |
| `site/index.html` | Single UI source of truth. Static mobile-first crossword app. |
| `site/crossword.json` | Runtime data file for static serving. Copied from `crossword.json`. |
| `package.json` | Node/Vite local static-site workflow. |
| `netlify.toml` | Netlify deploy config. Publish dir = `crossword_creator/site`. Build command = `cp crossword_creator/crossword.json crossword_creator/site/crossword.json`. |
