import os
import re
import subprocess
import time
from ast import literal_eval
from pathlib import Path
import json
import logging
import sys
from functools import lru_cache, partial
from typing import Dict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.models.openai import OpenAIChatModel
from .grid_creator import get_column_words
from .grid_creator import generate_grids

load_dotenv()

# Let LLM_* env vars override the standard OPENAI_* ones for local models
_llm_base = os.getenv("LLM_BASE_URL")
_llm_key = os.getenv("LLM_API_KEY")
if _llm_base:
    os.environ["OPENAI_BASE_URL"] = _llm_base
if _llm_key:
    os.environ["OPENAI_API_KEY"] = _llm_key

logger = logging.getLogger(__name__)

# Clue providers: "openai" (pydantic-ai, the default) or "opencode" (opencode CLI).
DEFAULT_CLUE_PROVIDER = "openai"
DEFAULT_OPENCODE_MODEL = "opencode-go/deepseek-v4-pro"
DEFAULT_OPENCODE_TIMEOUT = 900

CLUE_INSTRUCTIONS = (
    "You are a crossword clue generator. Given a list of words, generate "
    "creative and challenging clues for each word. "
    "Ensure the clues are concise and suitable for a crossword puzzle. "
    "Given words are all real english words. Do not try to correct or change them.\n\n"
    "Clues should not use the word itself or any part of the word in the clue. "
    "You MUST output a JSON object with a top-level key 'clues'. "
    "It must be a dictionary mapping words to clues. "
    "Output JSON only. DO NOT include ```json``` markdown formatting. "
    "example: "
    '{"clues": {"apple": "A fruit that keeps the doctor away", "python": "A programming language named after a comedy group"}}'
)


class ClueOutput(BaseModel):
    clues: Dict[str, str] = Field(..., description="A dictionary mapping words to their clues.")


class ClueGenerationError(RuntimeError):
    """Raised when a clue provider cannot produce usable clues."""


def clue_provider() -> str:
    """Selected clue backend, from CLUE_PROVIDER (defaults to "openai")."""
    return os.getenv("CLUE_PROVIDER", DEFAULT_CLUE_PROVIDER).strip().lower()


def opencode_model() -> str:
    """Model passed to `opencode run --model`, from OPENCODE_MODEL."""
    return os.getenv("OPENCODE_MODEL", DEFAULT_OPENCODE_MODEL).strip()


def opencode_timeout() -> int:
    """Seconds to wait for one `opencode run` call, from OPENCODE_TIMEOUT."""
    return int(os.getenv("OPENCODE_TIMEOUT", str(DEFAULT_OPENCODE_TIMEOUT)))


@lru_cache(maxsize=1)
def openai_agent() -> Agent:
    """Build the pydantic-ai agent lazily so the opencode path needs no API key."""
    return Agent(
        model=OpenAIChatModel(
            model_name=os.getenv("LLM_MODEL_NAME", "gpt-4.1"),
        ),
        system_prompt=CLUE_INSTRUCTIONS,
        output_type=str,
    )


# Grid path
GRID_FILEPATH = Path(__file__).parent / "crossword_grids.txt"
CROSSWORDS_FILEPATH = Path(__file__).parent / "crossword.json"


def read_last_grid():
    # Read last generated grid from file
    with open(GRID_FILEPATH, "r") as f:
        lines = f.readlines()
        last_grid_str = lines[-1].strip()
        last_grid = literal_eval(last_grid_str)
    column_words = get_column_words(last_grid)
    return last_grid + column_words


def stream_generate_crosswords():
    with open(GRID_FILEPATH, "r") as gf:
        total = sum(1 for _ in gf)

    if total == 0:
        print("No grids found in crossword_grids.txt")
        return

    t0 = time.time()
    # Write next to the target and rename at the end so a failed run never
    # leaves a truncated crossword.json behind.
    tmp_filepath = CROSSWORDS_FILEPATH.with_name(CROSSWORDS_FILEPATH.name + ".tmp")
    try:
        with open(GRID_FILEPATH, "r") as gf, open(tmp_filepath, "w") as cf:
            cf.write("{\n")
            for i, line in enumerate(gf):
                grid = literal_eval(line.strip())
                words = grid + get_column_words(grid)
                clues = generate_clues(words)
                inner = json.dumps({"clues": clues, "grid": grid}, indent=4)
                cf.write(f'    "crossword_{i}": {inner.replace("\n", "\n    ")}')
                if i < total - 1:
                    cf.write(",")
                cf.write("\n")
                cf.flush()
                elapsed = time.time() - t0
                eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0
                print(f"  Clues {i + 1}/{total} — {elapsed:.1f}s elapsed, ~{eta:.0f}s remaining", flush=True)
            cf.write("}\n")
        tmp_filepath.replace(CROSSWORDS_FILEPATH)
    except BaseException:
        tmp_filepath.unlink(missing_ok=True)
        raise
    print(f"Clues done: {total}/{total} in {time.time() - t0:.1f}s")


RETRIES = 3

RETRYABLE_CLUE_ERRORS = (ValidationError, ModelAPIError, ClueGenerationError)


def build_opencode_prompt(crossword_words) -> str:
    return (
        f"{CLUE_INSTRUCTIONS}\n\n"
        f"Generate clues for the following words: {list(crossword_words)}\n\n"
        "Respond with the JSON object only. No markdown, no code fences, no commentary."
    )


def parse_clues(output: str) -> Dict[str, str]:
    """Pull the {'clues': {word: clue}} payload out of raw provider output."""
    decoder = json.JSONDecoder()
    payloads = []
    for match in re.finditer(r"\{", output):
        try:
            candidate, _ = decoder.raw_decode(output, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("clues"), dict):
            payloads.append(candidate)
    if not payloads:
        raise ClueGenerationError(
            "Clue output contained no JSON object with a 'clues' mapping"
        )
    return ClueOutput.model_validate(payloads[-1]).clues


def generate_clues_openai(prompt: str) -> Dict[str, str]:
    result = openai_agent().run_sync(prompt)
    return ClueOutput.model_validate_json(result.output).clues


def generate_clues_opencode(crossword_words) -> Dict[str, str]:
    model = opencode_model()
    command = ["opencode", "run", "--model", model, build_opencode_prompt(crossword_words)]
    logger.debug("Running opencode clue generation with model %s", model)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=opencode_timeout(),
            check=False,
        )
    except FileNotFoundError as e:
        raise ClueGenerationError(
            "opencode CLI not found on PATH; install opencode or set CLUE_PROVIDER=openai"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ClueGenerationError(
            f"opencode CLI timed out after {opencode_timeout()}s"
        ) from e
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        raise ClueGenerationError(
            f"opencode CLI exited with status {completed.returncode}: {stderr[-1000:]}"
        )
    return parse_clues(completed.stdout or "")


def generate_clues(crossword_words):
    provider = clue_provider()
    logger.debug("Generating clues via %s for words: %s", provider, crossword_words)
    prompt = f"Generate clues for the following words: {crossword_words}"
    if provider == "openai":
        fetch_clues = partial(generate_clues_openai, prompt)
    elif provider == "opencode":
        fetch_clues = partial(generate_clues_opencode, crossword_words)
    else:
        raise ValueError(
            f"Unknown CLUE_PROVIDER={provider!r}; expected 'openai' or 'opencode'"
        )
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            clues = fetch_clues()
            logger.debug("Generated clues: %s", clues)
            return clues
        except RETRYABLE_CLUE_ERRORS as e:
            last_error = e
            if attempt < RETRIES:
                delay = 2**attempt
                print(f"  Retry {attempt}/{RETRIES} — {type(e).__name__}: {e} — waiting {delay}s", flush=True)
                time.sleep(delay)
    raise last_error


def create_cword_prod_pipe(num_grids=1):
    print(f"Phase 1/2: Generating {num_grids} grid(s)...")
    generate_grids(row_min=6, row_max=8, col_min=4, col_max=5, num_grids=num_grids, write_mode="w")
    print(f"\nPhase 2/2: Generating clues...")
    stream_generate_crosswords()


if __name__ == "__main__":
    log_level = logging.DEBUG if "--verbose" in sys.argv[1:] else logging.WARNING
    logging.basicConfig(level=log_level)

    t_total = time.time()
    if len(sys.argv) > 1 and sys.argv[1] == "prod":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        generate_grids(row_min=6, row_max=8, col_min=4, col_max=5, num_grids=count, write_mode="w")
    stream_generate_crosswords()
    print(f"\nDone. in {time.time() - t_total:.1f}s total")
