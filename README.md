# MiniWöördi - Crossword Puzzle Generator

Generates crossword grids from a 91K-word dictionary, produces AI-powered clues, and serves a mobile-first static crossword app.

## Setup

```bash
# Python generation dependencies
pip install -r requirements.txt

# Static site dev server
npm install
```

Create `.env` in the repo root. Use either remote OpenAI or a local llamafile.

```bash
# Remote OpenAI
OPENAI_API_KEY=your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
```

The `.env` file is loaded from the current working directory by `load_dotenv()` in `crossword_creator.py`.

### opencode CLI (no API key)

Clues can instead be generated through the `opencode` CLI, which reuses your existing
opencode login and model account. No `OPENAI_API_KEY` is needed:

```bash
CLUE_PROVIDER=opencode
# optional, this is the default:
OPENCODE_MODEL=opencode-go/deepseek-v4-pro
```

`CLUE_PROVIDER` defaults to `openai`, so the pydantic-ai/OpenAI path above stays the
default and is unaffected. The opencode path runs
`opencode run --model "$OPENCODE_MODEL" "<prompt>"` as your normal user, inheriting your
opencode authentication, and parses the model's JSON output into the same
`{"clues": {word: clue}}` shape the OpenAI path produces.

`OPENCODE_TIMEOUT` (seconds, default `900`) bounds a single `opencode run` call. The
`LLM_*`/`OPENAI_*` settings are ignored when `CLUE_PROVIDER=opencode`, so no OpenAI key is
needed on that path.

### Local Model

Start a llamafile in a separate terminal:

```bash
/home/simo/projects/ai/llm_models/Qwen3.5-4B-Q5_K_S.llamafile
```

Then set:

```bash
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=not-needed
LLM_MODEL_NAME=local
```

Unset all `LLM_*` vars to use the OpenAI cloud defaults.

## Quick Start

```bash
# Run the static crossword UI locally with Node/Vite
npm run dev
```

Open the local URL printed by Vite. The static app loads `crossword_creator/site/crossword.json`.

## Generate Crosswords

```bash
# Generate 1 grid + AI clues and write crossword_creator/crossword.json
python -m crossword_creator.crossword_creator prod

# Generate 30 crosswords at once
python -m crossword_creator.crossword_creator prod 30

# Same with debug logging
python -m crossword_creator.crossword_creator --verbose

# Generate clues through the opencode CLI instead of the OpenAI API
CLUE_PROVIDER=opencode python -m crossword_creator.crossword_creator prod
```

To generate raw grids interactively:

```bash
python -m crossword_creator.grid_creator
```

Generated grids are appended to `crossword_creator/crossword_grids.txt`.

## Local Data Copy

The UI reads `crossword_creator/site/crossword.json`. After generating new data, copy it into the site folder for local preview:

```bash
cp crossword_creator/crossword.json crossword_creator/site/crossword.json
```

Netlify runs the same copy command during deployment.

## Deploy To Netlify

The production frontend is a static HTML page that loads `crossword.json` and picks today's crossword in the browser.

```bash
# 1. Generate crosswords locally, for example 30 days worth
python -m crossword_creator.crossword_creator prod 30

# 2. Commit and push. Netlify auto-deploys on push.
#    The build step in netlify.toml copies crossword.json into site/.
git add crossword_creator/crossword.json
git commit -m "30 new crosswords"
git push
```

Netlify config:

```toml
[build]
  publish = "crossword_creator/site"
  command = "cp crossword_creator/crossword.json crossword_creator/site/crossword.json"
```

## Daily Rotation

`site/index.html` picks a crossword by local calendar day, so the puzzle changes at midnight in the visitor's local timezone.

It rotates among committed `crossword_*` entries in `crossword.json`. Netlify does not generate new crosswords on a schedule; new puzzles are added when regenerated and deployed.

## Architecture

```text
          wl.txt
             |
     grid_creator.py         backtracking NumPy solver
             |
     crossword_grids.txt     raw grids, Python repr format
             |
   crossword_creator.py      clues: pydantic-ai or opencode CLI
             |
       crossword.json        generated grids + clues
             |
       site/index.html       static mobile-first app
             |
          Netlify            static hosting
```

Python is used only for crossword generation. The user-facing app is static HTML/CSS/JS and is run locally with Node/Vite.

## Files

| File | Purpose |
|---|---|
| `crossword_creator/crossword.json` | Generated crossword data. Source copied into the static site at deploy time. |
| `crossword_creator/site/index.html` | Static crossword app. Mobile-first UI and local-midnight daily selection. |
| `crossword_creator/site/crossword.json` | Runtime data file for local/static serving. Copied from `crossword_creator/crossword.json`. |
| `crossword_creator/crossword_arc.json` | Archive of older crosswords. Not read at runtime. |
| `crossword_creator/crossword_grids.txt` | Raw grids output by the solver, one `list[str]` per line. |
| `crossword_creator/wl.txt` | Word dictionary used by the solver. |
| `tests/` | Pytest suite; clue-provider tests mock the opencode subprocess. |
| `requirements-dev.txt` | Generation deps plus `pytest`. |
| `package.json` | Node/Vite local static-site workflow. |
| `netlify.toml` | Netlify static deploy config. |

## Dependencies

Python:

| Dependency | Purpose |
|---|---|
| `pydantic-ai-slim[openai]` | AI agent for clue generation (`CLUE_PROVIDER=openai`). |
| `numpy` | Fast array-based word matching in the grid solver. |
| `python-dotenv` | Loads `.env`. |

Install `requirements-dev.txt` (which includes `requirements.txt` plus `pytest`) to run the
tests.

Node:

| Dependency | Purpose |
|---|---|
| `vite` | Local static-site dev server. |

## Clue Providers

| Env var | Default | Purpose |
|---|---|---|
| `CLUE_PROVIDER` | `openai` | `openai` uses pydantic-ai; `opencode` shells out to the opencode CLI. |
| `OPENCODE_MODEL` | `opencode-go/deepseek-v4-pro` | Model for `opencode run --model`. |
| `OPENCODE_TIMEOUT` | `900` | Seconds allowed for one `opencode run` call. |

The opencode path needs no API key: it runs as the current user and inherits the normal
opencode authentication. Both providers produce the same `{"clues": {word: clue}}` data, so
`crossword.json` is identical in shape either way.

## Model

OpenAI path (`CLUE_PROVIDER=openai`, the default):

| Env var | Default | Purpose |
|---|---|---|
| `LLM_MODEL_NAME` | `gpt-4.1` | Model name sent to the endpoint. |
| `LLM_BASE_URL` | `OPENAI_BASE_URL` | API base URL. |
| `LLM_API_KEY` | `OPENAI_API_KEY` | API key. |

Set `LLM_*` vars to override for local models. Unset them to use the OpenAI cloud defaults.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The clue-provider tests mock the opencode subprocess, so they need neither a live
`opencode` login nor an OpenAI key.
