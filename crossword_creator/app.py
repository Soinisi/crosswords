from pathlib import Path
import sys
import json
from flask import Flask, render_template_string
from crossword_creator.crossword_creator import create_cword_prod_pipe

if sys.argv[-1] == "prod":
    print("Generating crossword and clues for production...")
    create_cword_prod_pipe()

app = Flask(__name__)
# ------------------------------------------------------
# Your JSON crossword data (grid + clues)
# ------------------------------------------------------
CROSSWORD_JSON_PATH = Path(__file__).parent / "crossword.json"
with open(CROSSWORD_JSON_PATH, "r") as f:
    DATA = json.load(f)


crossword_index = max(
    (int(key.split("_")[-1])
     for key in DATA.keys()
     if key.startswith("crossword_") and not key.startswith("used_")),
    default=-1
)
if crossword_index == -1:
    print("No available crosswords. Generating a fresh one...")
    create_cword_prod_pipe()
    with open(CROSSWORD_JSON_PATH, "r") as f:
        DATA = json.load(f)
    crossword_index = max(
        int(key.split("_")[-1])
        for key in DATA.keys()
        if key.startswith("crossword_") and not key.startswith("used_")
    )

CROSSW_INDEX = f"crossword_{crossword_index}"

CLUE_MAP = DATA[CROSSW_INDEX]["clues"]
GRID = DATA[CROSSW_INDEX]["grid"]

DATA[f"used_{CROSSW_INDEX}"] = DATA.pop(CROSSW_INDEX)
with open(CROSSWORD_JSON_PATH, "w") as f:
    json.dump(DATA, f, indent=4)

ROWS = len(GRID)
COLS = max(len(r) for r in GRID)

# ------------------------------------------------------
# Extract Across words (directly from grid rows)
# ------------------------------------------------------
ACROSS = []
for r, row in enumerate(GRID):
    word = row
    clue = CLUE_MAP.get(word)
    ACROSS.append((r, 0, word, clue))

# ------------------------------------------------------
# Extract Down words (column scanning)
# ------------------------------------------------------
DOWN = []
for c in range(COLS):
    letters = []
    for r in range(ROWS):
        if c < len(GRID[r]):
            letters.append(GRID[r][c])
        else:
            letters.append("#")

    word = "".join(letters).replace("#", "")
    if word in CLUE_MAP:
        start_r = next(i for i, ch in enumerate(letters) if ch != "#")
        DOWN.append((start_r, c, word, CLUE_MAP[word]))

# ------------------------------------------------------
# Crossword numbering (safe for uneven rows)
# ------------------------------------------------------
numbers = [[None for _ in range(COLS)] for _ in range(ROWS)]
num = 1

for r in range(ROWS):
    for c in range(COLS):

        # Skip if this row doesn't have this column
        if c >= len(GRID[r]):
            continue

        if GRID[r][c] == "#":
            continue

        # Across start
        start_across = c == 0 or c - 1 >= len(GRID[r]) or GRID[r][c - 1] == "#"

        # Down start
        start_down = r == 0 or c >= len(GRID[r - 1]) or GRID[r - 1][c] == "#"

        if start_across or start_down:
            numbers[r][c] = num
            num += 1

# ------------------------------------------------------
# HTML template
# ------------------------------------------------------
TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Interactive Crossword Puzzle</title>
<style>
    :root {
        --cell-size: 65px;
    }

    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }

    body {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
        padding: 40px 20px;
        display: flex;
        justify-content: center;
        align-items: flex-start;
    }

    .container {
        max-width: 1200px;
        width: 100%;
        background: white;
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        overflow: hidden;
    }

    header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 22px;
        text-align: center;
    }

    header h1 {
        font-size: 2.2em;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.2);
    }

    .timer {
        font-size: 1.3em;
        font-weight: 600;
        margin-top: 10px;
        color: rgba(255, 255, 255, 0.9);
    }

    .content {
        display: flex;
        flex-wrap: wrap;
        padding: 40px;
        gap: 40px;
        justify-content: flex-start;
        align-items: flex-start;
    }

    .grid-container {
        flex: 1;
        min-width: 400px;
        display: flex;
        justify-content: center;
    }

    #grid {
        display: grid;
        gap: 0;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
        border: 3px solid #333;
        background: #333;
    }

    .cell {
        width: var(--cell-size);
        height: var(--cell-size);
        background: white;
        border: 1px solid #666;
        position: relative;
        transition: all 0.2s ease;
    }

    .cell:hover {
        background: #f0f0f0;
    }

    .cell input {
        width: 100%;
        height: 100%;
        border: none;
        text-align: center;
        font-size: 30px;
        font-weight: 600;
        text-transform: uppercase;
        background: transparent;
        outline: none;
        cursor: pointer;
        color: #333;
        transition: all 0.2s ease;
    }

    .cell input:focus {
        background: #e3f2fd;
        box-shadow: inset 0 0 0 2px #2196F3;
    }

    .number {
        position: absolute;
        top: 2px;
        left: 3px;
        font-size: 14px;
        font-weight: 600;
        color: #666;
        pointer-events: none;
        z-index: 1;
    }

    .correct {
        background: #c8e6c9 !important;
        animation: correctPulse 0.5s ease;
    }

    .incorrect {
        background: #ffcdd2 !important;
        animation: shake 0.5s ease;
    }

    @keyframes correctPulse {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.05); }
    }

    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-5px); }
        75% { transform: translateX(5px); }
    }

    .clues-container {
        flex: 1;
        min-width: 0;
    }

    #clues {
        display: flex;
        flex-direction: column;
        gap: 30px;
    }

    .clue-section h2 {
        color: #667eea;
        font-size: 1.6em;
        margin-bottom: 15px;
        padding-bottom: 10px;
        border-bottom: 3px solid #667eea;
    }

    #clues ul {
        list-style: none;
        padding: 0;
    }

    #clues li {
        padding: 9px 12px;
        margin-bottom: 8px;
        background: #f8f9fa;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        font-size: 0.98em;
        line-height: 1.5;
        overflow-wrap: anywhere;
        word-break: break-word;
        transition: all 0.2s ease;
        cursor: pointer;
    }

    #clues li:hover {
        background: #e3f2fd;
        transform: translateX(5px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
    }

    .clue-section:nth-child(2) h2 {
        color: #764ba2;
        border-bottom-color: #764ba2;
    }

    .clue-section:nth-child(2) li {
        border-left-color: #764ba2;
    }

    @media (max-width: 768px) {
        :root {
            --cell-size: 35px;
        }

        body {
            padding: 20px 10px;
        }

        header h1 {
            font-size: 1.65em;
        }

        .content {
            padding: 20px;
            flex-direction: column;
        }

        .clues-container,
        .grid-container {
            min-width: 100%;
            width: 100%;
        }

        .cell {
            width: 35px;
            height: 35px;
        }

        .cell input {
            font-size: 16px;
        }

        .number {
            font-size: 11px;
        }

        .clue-section h2 {
            font-size: 1.4em;
            margin-bottom: 12px;
            padding-bottom: 8px;
        }

        #clues li {
            padding: 8px 10px;
            font-size: 0.93em;
        }
    }

    @keyframes pop-in {
        0% { transform: translate(-50%, -50%) scale(0.7); opacity: 0; }
        80% { transform: translate(-50%, -50%) scale(1.1); opacity: 1; }
        100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
    }

    </style>
</head>
<body>

<div class="container">
    <header>
        <h1>🧩 MiniWöördi</h1>
        <div class="timer" id="timer">Time: 00:00</div>
    </header>

    <div class="content">
        <div class="clues-container">
            <div id="clues">
                <div class="clue-section">
                    <h2>➡️ Across</h2>
                    <ul id="across"></ul>
                </div>
                <div class="clue-section">
                    <h2>⬇️ Down</h2>
                    <ul id="down"></ul>
                </div>
            </div>
        </div>
        <div class="grid-container">
            <div id="grid"></div>
        </div>
    </div>
</div>

<script>
const GRID = {{ grid|tojson }};
const NUMBERS = {{ numbers|tojson }};
const ACROSS = {{ across|tojson }};
const DOWN = {{ down|tojson }};

const ROWS = GRID.length;
const COLS = Math.max(...GRID.map(r => r.length));

// Timer variables
let timerStarted = false;
let startTime = null;
let timerInterval = null;

function startTimer() {
    if (timerStarted) return;

    timerStarted = true;
    startTime = Date.now();

    timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const seconds = (elapsed % 60).toString().padStart(2, '0');
        document.getElementById('timer').textContent = `Time: ${minutes}:${seconds}`;
    }, 1000);
}

function stopTimer() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
}

function handleArrowKeys(e) {
    const r = parseInt(e.target.dataset.row);
    const c = parseInt(e.target.dataset.col);

    let nextR = r, nextC = c;

    switch (e.key) {
        case "ArrowUp":
            nextR = r > 0 ? r - 1 : r;
            break;
        case "ArrowDown":
            nextR = r < ROWS - 1 ? r + 1 : r;
            break;
        case "ArrowLeft":
            nextC = c > 0 ? c - 1 : c;
            break;
        case "ArrowRight":
            nextC = c < GRID[nextR].length - 1 ? c + 1 : c;
            break;
        default:
            return;
    }

    if (
        nextR >= 0 &&
        nextR < ROWS &&
        nextC >= 0 &&
        nextC < GRID[nextR].length &&
        GRID[nextR][nextC] !== "#"
    ) {
        const nextInput = document.querySelector(
            `input[data-row="${nextR}"][data-col="${nextC}"]`
        );
        if (nextInput) {
            nextInput.focus();
            e.preventDefault();
        }
    }
}

function renderGrid() {
    const container = document.getElementById("grid");
    container.style.gridTemplateColumns = `repeat(${COLS}, var(--cell-size))`;

    for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
            const cell = document.createElement("div");
            cell.className = "cell";

            if (c >= GRID[r].length) {
                cell.style.visibility = "hidden";
            } else {
                const input = document.createElement("input");
                input.maxLength = 1;
                input.dataset.row = r;
                input.dataset.col = c;
                input.addEventListener("input", checkLetter);
                input.addEventListener("keydown", handleCellKeyDown);
                input.addEventListener("keydown", handleArrowKeys);
                cell.appendChild(input);

                if (NUMBERS[r][c]) {
                    const num = document.createElement("div");
                    num.className = "number";
                    num.textContent = NUMBERS[r][c];
                    cell.appendChild(num);
                }
            }

            container.appendChild(cell);
        }
    }
}
function handleCellKeyDown(e) {
    // Only handle single letter keys (A-Z)
    if (e.key.length === 1 && /^[a-zA-Z]$/.test(e.key)) {
        e.preventDefault();

        const input = e.target;
        input.value = e.key.toUpperCase();
        // Manually trigger input event for validation and styling
        checkLetter({ target: input });
    }
}


function checkLetter(e) {
    const input = e.target;
    const r = parseInt(input.dataset.row);
    const c = parseInt(input.dataset.col);
    const val = input.value.toUpperCase();

    if (!timerStarted && val.match(/^[A-Z]$/)) {
        startTimer();
    }

    input.value = val;

    if (!val.match(/^[A-Z]$/)) {
        input.classList.remove("correct", "incorrect");
        return;
    }

    if (val === GRID[r][c].toUpperCase()) {
        input.classList.add("correct");
        input.classList.remove("incorrect");
    } else {
        input.classList.add("incorrect");
        input.classList.remove("correct");
    }
    /*
    const nextCol = c + 1;
    if (nextCol < GRID[r].length) {
        const nextInput = document.querySelector(
            `input[data-row="${r}"][data-col="${nextCol}"]`
        );
        if (nextInput) nextInput.focus();
    }
    */
    // Check for win after every input
    checkWin();
}

function renderClues() {
    const acrossList = document.getElementById("across");
    const downList = document.getElementById("down");

    ACROSS.forEach(([r, c, word, clue]) => {
        const num = NUMBERS[r][c];
        const li = document.createElement("li");
        li.textContent = `${num}. ${clue}`;
        acrossList.appendChild(li);
    });

    DOWN.forEach(([r, c, word, clue]) => {
        const num = NUMBERS[r][c];
        const li = document.createElement("li");
        li.textContent = `${num}. ${clue}`;
        downList.appendChild(li);
    });
}

function checkWin() {
    const inputs = document.querySelectorAll('.cell input');
    for (const input of inputs) {
        if (
            input.parentElement.style.visibility !== "hidden" &&
            !input.classList.contains('correct')
        ) {
            return false;
        }
    }
    stopTimer(); // Stop timer when puzzle is solved
    showWinAnimation();
    return true;
}

function showWinAnimation() {
    if (document.getElementById('win-banner')) return; // Prevent duplicates

    // Freeze all inputs
    const inputs = document.querySelectorAll('.cell input');
    inputs.forEach(input => {
        input.disabled = true;
        input.style.cursor = 'not-allowed';
    });

    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');

    // Create WhatsApp share message
    const shareText = `😺 I just solved today's MiniWöördi crossword in ${minutes}:${seconds}! 😺`;
    const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(shareText)}`;

    const banner = document.createElement('div');
    banner.id = 'win-banner';
    banner.innerHTML = `
        <div style="margin-bottom: 20px;">
            🎉 Congratulations! You solved it in ${minutes}:${seconds}! 🎉
        </div>
        <a href="${whatsappUrl}"
           target="_blank"
           style="display: inline-block;
                  background: #25D366;
                  color: white;
                  text-decoration: none;
                  padding: 15px 30px;
                  border-radius: 10px;
                  font-size: 0.7em;
                  font-weight: bold;
                  transition: all 0.3s ease;
                  box-shadow: 0 4px 15px rgba(37, 211, 102, 0.4);"
           onmouseover="this.style.background='#128C7E'; this.style.transform='scale(1.05)'"
           onmouseout="this.style.background='#25D366'; this.style.transform='scale(1)'">
            📱 Share on WhatsApp
        </a>
    `;
    banner.style.position = 'fixed';
    banner.style.top = '50%';
    banner.style.left = '50%';
    banner.style.transform = 'translate(-50%, -50%)';
    banner.style.background = 'rgba(102,126,234,0.98)';
    banner.style.color = 'white';
    banner.style.fontSize = '2.5em';
    banner.style.fontWeight = 'bold';
    banner.style.padding = '40px 60px';
    banner.style.borderRadius = '20px';
    banner.style.boxShadow = '0 8px 32px rgba(0,0,0,0.25)';
    banner.style.zIndex = '9999';
    banner.style.textAlign = 'center';
    banner.style.animation = 'pop-in 0.7s cubic-bezier(.68,-0.55,.27,1.55)';
    document.body.appendChild(banner);
    /*
    // Optional: Remove banner after 8 seconds (increased time for sharing)
    setTimeout(() => {
        banner.style.transition = 'opacity 0.7s';
        banner.style.opacity = '0';
        setTimeout(() => banner.remove(), 700);
    }, 8000);
    */
}

renderGrid();
renderClues();
</script>

</body>
</html>
"""


@app.route("/minicrossword")
def index():
    return render_template_string(TEMPLATE, grid=GRID, numbers=numbers, across=ACROSS, down=DOWN)


if __name__ == "__main__":
    if sys.argv[-1] == "build":
        import shutil
        site_dir = Path(__file__).parent / "site"
        site_dir.mkdir(exist_ok=True)
        shutil.copy(CROSSWORD_JSON_PATH, site_dir / "crossword.json")
        print(f"Site built: {site_dir}/")
    elif sys.argv[-1] == "prod":
        print("Starting production server on http://0.0.0.0:5000")
        from waitress import serve

        serve(app, host="0.0.0.0", port=5000)
    else:
        app.run(debug=True)
