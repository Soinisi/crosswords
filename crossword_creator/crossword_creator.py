from ast import literal_eval
from pathlib import Path
import json
import logging
import sys
from typing import Dict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from grid_creator import get_column_words
from grid_creator import generate_grids

load_dotenv()

logger = logging.getLogger(__name__)

model = OpenAIChatModel(
    model_name="gpt-4.1",
)


class ClueOutput(BaseModel):
    clues: Dict[str, str] = Field(..., description="A dictionary mapping words to their clues.")


crossword_clues_instructions = (
    "You are a crossword clue generator for crossword puzzle. you create clues from given words. "
    "Given a list of words, generate creative and challenging clues for each word. "
    "Ensure the clues are concise and suitable for a crossword puzzle."
    "Given words are all real english words. Do not try to correct or change them."
)

agent = Agent(
    model=model,
    instructions=crossword_clues_instructions,
    system_prompt=(
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


def read_all_grids():
    # Read all generated grids from file
    with open(GRID_FILEPATH, "r") as f:
        lines = f.readlines()
        grids = [literal_eval(line.strip()) for line in lines]
    return grids


def generate_all_crosswords(grids):
    words_grids = [(grid + get_column_words(grid), grid) for grid in grids]
    return [(generate_clues(wg[0]), wg[1]) for wg in words_grids]


def generate_clues(crossword_words):
    logger.debug("Generating clues for words: %s", crossword_words)
    result = agent.run_sync(f"Generate clues for the following words: {crossword_words}")
    clues = ClueOutput.model_validate_json(result.output).clues

    logger.debug("Generated clues: %s", clues)
    return clues


def write_crosswords_to_json(crosswords):
    clues_combined = {}
    for i, cw in enumerate(crosswords):
        clues_combined[f"crossword_{i}"] = {"clues": cw[0], "grid": cw[1]}
    with open(CROSSWORDS_FILEPATH, "w") as f:
        json.dump(clues_combined, f, indent=4)


def create_cword_prod_pipe():
    generate_grids(row_min=6, row_max=8, col_min=4, col_max=5, num_grids=1, write_mode="w")
    grid = read_all_grids()
    crossword = generate_all_crosswords(grid)
    write_crosswords_to_json(crossword)


if __name__ == "__main__":
    log_level = logging.DEBUG if "--verbose" in sys.argv[1:] else logging.WARNING
    logging.basicConfig(level=log_level)

    if len(sys.argv) > 1 and sys.argv[1] == "prod":
        generate_grids(row_min=6, row_max=8, col_min=4, col_max=5, num_grids=1, write_mode="w")
    grids = read_all_grids()
    crosswords = generate_all_crosswords(grids)
    write_crosswords_to_json(crosswords)
