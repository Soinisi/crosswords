import os
import time
from ast import literal_eval
from pathlib import Path
import json
import logging
import sys
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

model = OpenAIChatModel(
    model_name=os.getenv("LLM_MODEL_NAME", "gpt-4.1"),
)


class ClueOutput(BaseModel):
    clues: Dict[str, str] = Field(..., description="A dictionary mapping words to their clues.")


agent = Agent(
    model=model,
    system_prompt=(
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
    ),
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
    with open(GRID_FILEPATH, "r") as gf, open(CROSSWORDS_FILEPATH, "w") as cf:
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
    print(f"Clues done: {total}/{total} in {time.time() - t0:.1f}s")


RETRIES = 3


def generate_clues(crossword_words):
    logger.debug("Generating clues for words: %s", crossword_words)
    prompt = f"Generate clues for the following words: {crossword_words}"
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            result = agent.run_sync(prompt)
            clues = ClueOutput.model_validate_json(result.output).clues
            logger.debug("Generated clues: %s", clues)
            return clues
        except (ValidationError, ModelAPIError) as e:
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
