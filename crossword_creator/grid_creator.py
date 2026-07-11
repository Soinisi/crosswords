from pathlib import Path
from functools import lru_cache
import logging
import sys
import time
import numpy as np


# This files path
WORD_LIST_FILEPATH = Path(__file__).parent / "wl.txt"
GRID_FILEPATH = Path(__file__).parent / "crossword_grids.txt"
logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Load dictionary into NumPy
# ------------------------------------------------------------
@lru_cache(maxsize=None)
def load_words_by_length(path_str):
    buckets = {}
    with open(path_str, "r", encoding="utf-8") as f:
        for line in f:
            word = line.strip().lower()
            if not word:
                continue
            buckets.setdefault(len(word), []).append(word)

    return {length: np.array(words, dtype=f"<U{length}") for length, words in buckets.items()}


def load_words_numpy(length, path):
    words_by_length = load_words_by_length(str(path))
    words = words_by_length.get(length)
    if words is None or words.size == 0:
        raise ValueError(f"No words of length {length} found in {path}")

    matrix = np.array([list(w) for w in words], dtype="<U1")
    return words, matrix


def build_next_letter_index(words):
    word_length = len(words[0])
    index = [dict() for _ in range(word_length)]

    for word in words.tolist():
        prefix = ""
        for k, letter in enumerate(word):
            bucket = index[k].get(prefix)
            if bucket is None:
                bucket = set()
                index[k][prefix] = bucket
            bucket.add(letter)
            prefix += letter

    compact = []
    for level in index:
        compact.append({prefix: np.array(sorted(letters), dtype="<U1") for prefix, letters in level.items()})

    return compact


def build_position_letter_masks(matrix):
    _, word_length = matrix.shape
    masks = [dict() for _ in range(word_length)]

    for c in range(word_length):
        column = matrix[:, c]
        for letter in np.unique(column):
            masks[c][letter] = column == letter

    return masks


@lru_cache(maxsize=None)
def prepare_length_data(length, path_str):
    words, matrix = load_words_numpy(length, Path(path_str))
    next_letter_index = build_next_letter_index(words)
    position_letter_masks = build_position_letter_masks(matrix)
    return words, matrix, next_letter_index, position_letter_masks


# ------------------------------------------------------------
# Ragged-grid solver with UNIQUE ROWS + UNIQUE COLUMNS
# ------------------------------------------------------------
def solve_ragged(row_lengths, path, max_attempts=1_000_000, num_restarts=4):
    row_lengths = sorted(row_lengths, reverse=True)
    R = len(row_lengths)
    C = max(row_lengths)

    # Column lengths for sorted row lengths (always contiguous from the top)
    col_lengths = np.array([sum(1 for L in row_lengths if L > c) for c in range(C)], dtype=int)
    column_word_lengths = {L for L in col_lengths if L > 1}

    # Load all needed dictionaries
    needed_lengths = set(row_lengths) | column_word_lengths
    dicts = {}
    next_letter_indexes = {}
    position_letter_masks = {}
    for L in needed_lengths:
        words, matrix, next_letter_index, letter_masks = prepare_length_data(L, str(path))
        dicts[L] = (words, matrix)
        next_letter_indexes[L] = next_letter_index
        position_letter_masks[L] = letter_masks

    if num_restarts < 1:
        num_restarts = 1

    per_restart_attempts = max(1, max_attempts // num_restarts)

    def run_single_attempt():
        used_rows = {L: np.zeros(dicts[L][0].shape[0], dtype=bool) for L in set(row_lengths)}
        used_row_words = {}
        used_cols = {L: set() for L in column_word_lengths}
        col_prefixes = ["" for _ in range(C)]
        placed_rows = [""] * R
        steps = 0

        def valid_mask_for_row(L):
            _, matrix = dicts[L]
            valid = ~used_rows[L].copy()

            for c in range(L):
                col_len = col_lengths[c]
                if col_len <= 1:
                    continue

                base = col_prefixes[c]
                next_letters = next_letter_indexes[col_len][len(base)].get(base)
                if next_letters is None:
                    return None

                letter_masks = position_letter_masks[L][c]
                col_valid = np.zeros(matrix.shape[0], dtype=bool)
                for letter in next_letters:
                    letter_mask = letter_masks.get(letter)
                    if letter_mask is not None:
                        col_valid |= letter_mask

                valid &= col_valid
                if not np.any(valid):
                    return None

            return valid

        def backtrack(depth):
            nonlocal steps
            if depth == R:
                return True

            r = depth
            L = row_lengths[r]
            words, matrix = dicts[L]

            valid = valid_mask_for_row(L)
            if valid is None:
                return False

            candidates = np.where(valid)[0]
            if candidates.size == 0:
                return False

            np.random.shuffle(candidates)

            for idx in candidates:
                steps += 1
                if steps > per_restart_attempts:
                    return False

                row_word = words[idx]
                if row_word in used_cols.get(len(row_word), set()):
                    continue

                row_letters = matrix[idx]
                used_rows[L][idx] = True
                used_row_words[row_word] = used_row_words.get(row_word, 0) + 1
                placed_rows[r] = str(row_word)

                touched_prefixes = []
                pending_cols_by_len = {}
                ok = True
                for c in range(L):
                    old_prefix = col_prefixes[c]
                    new_prefix = old_prefix + row_letters[c]
                    col_prefixes[c] = new_prefix
                    touched_prefixes.append((c, old_prefix))

                    col_len = col_lengths[c]
                    if col_len > 1 and len(new_prefix) == col_len:
                        pending_for_len = pending_cols_by_len.setdefault(col_len, set())
                        if new_prefix in used_cols[col_len] or new_prefix in pending_for_len:
                            ok = False
                            break
                        if used_row_words.get(new_prefix, 0) > 0:
                            ok = False
                            break
                        pending_for_len.add(new_prefix)

                if ok:
                    for col_len, words_set in pending_cols_by_len.items():
                        used_cols[col_len].update(words_set)

                    if backtrack(depth + 1):
                        return True

                    for col_len, words_set in pending_cols_by_len.items():
                        used_cols[col_len].difference_update(words_set)

                used_rows[L][idx] = False
                count = used_row_words.get(row_word, 0)
                if count <= 1:
                    used_row_words.pop(row_word, None)
                else:
                    used_row_words[row_word] = count - 1
                for c, old_prefix in touched_prefixes:
                    col_prefixes[c] = old_prefix

            return False

        if backtrack(0):
            return placed_rows
        return None

    for _ in range(num_restarts):
        solution = run_single_attempt()
        if solution is not None:
            return solution

    return None


# ------------------------------------------------------------
# Random interval ragged-grid generator
# ------------------------------------------------------------
def solve_random_interval(row_min, row_max, col_min, col_max, path):
    """
    Generate a ragged grid where each row length is chosen randomly
    between R_min and R_max (inclusive).
    """
    rows_size = np.random.randint(col_min, col_max + 1)
    row_lengths = np.random.randint(row_min, row_max + 1, size=rows_size).tolist()

    logger.debug("Row lengths selected: %s", row_lengths)

    return solve_ragged(row_lengths, path=path)


def get_column_words(grid):
    columns_max = max(len(row) for row in grid)
    col_words = []
    for c in range(columns_max):
        col_word = ""
        for r, _ in enumerate(grid):
            if c < len(grid[r]):
                col_word += grid[r][c]
            else:
                break
        if len(col_word) > 1:
            col_words.append(col_word)
    return col_words


def user_inputs_loop():
    while True:
        row_min = int(input("Enter minimum row length (or '0' to quit): "))
        if row_min == 0:
            break
        row_max = int(input("Enter maximum row length: "))
        col_min = int(input("Enter minimum number of rows: "))
        col_max = int(input("Enter maximum number of rows: "))
        grid = solve_random_interval(row_min, row_max, col_min, col_max, path=WORD_LIST_FILEPATH)
        if grid is not None:
            logger.debug("Solution found:")
            for row in grid:
                logger.debug(row)
            column_words = get_column_words(grid)
            logger.debug("Column words:")
            for col_word in column_words:
                logger.debug(col_word)
            with open(GRID_FILEPATH, "a", encoding="utf-8") as f:
                f.write(str(grid) + "\n")

        else:
            logger.debug("No solution found.")


def generate_grids(row_min, row_max, col_min, col_max, num_grids, write_mode="a"):
    t0 = time.time()
    with open(GRID_FILEPATH, write_mode, encoding="utf-8") as f:
        for i in range(num_grids):
            grid = solve_random_interval(row_min, row_max, col_min, col_max, path=WORD_LIST_FILEPATH)
            if grid is not None:
                logger.debug("Solution found:")
                for row in grid:
                    logger.debug(row)
                column_words = get_column_words(grid)
                logger.debug("Column words:")
                for col_word in column_words:
                    logger.debug(col_word)
                f.write(str(grid) + "\n")
            else:
                logger.debug("No solution found.")
            elapsed = time.time() - t0
            eta = (elapsed / (i + 1)) * (num_grids - i - 1) if i > 0 else 0
            print(f"  Grid {i + 1}/{num_grids} — {elapsed:.1f}s elapsed, ~{eta:.0f}s remaining", flush=True)
    print(f"Grids done: {num_grids}/{num_grids} in {time.time() - t0:.1f}s")


def user_input_generate_grids():
    row_min = int(input("Enter minimum row length: "))
    row_max = int(input("Enter maximum row length: "))
    col_min = int(input("Enter minimum number of rows: "))
    col_max = int(input("Enter maximum number of rows: "))
    num_grids = int(input("Enter number of grids to generate: "))
    generate_grids(row_min, row_max, col_min, col_max, num_grids)


if __name__ == "__main__":
    log_level = logging.DEBUG if "--verbose" in sys.argv[1:] else logging.WARNING
    logging.basicConfig(level=log_level)

    choice = input("Enter '1' for interactive mode or '2' to generate multiple grids: ")
    if choice == "1":
        user_inputs_loop()
    elif choice == "2":
        user_input_generate_grids()
