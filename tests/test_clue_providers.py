import json
from types import SimpleNamespace

import pytest

from crossword_creator import crossword_creator as cc

CLUES_JSON = '{"clues": {"APPLE": "A fruit that keeps the doctor away", "OCEAN": "Vast body of salt water"}}'


@pytest.fixture
def sleeper(monkeypatch):
    """Record retry sleeps instead of waiting for them."""
    delays = []
    monkeypatch.setattr(cc.time, "sleep", delays.append)
    return delays


def fake_completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.fixture
def opencode_run(monkeypatch):
    """Replace subprocess.run and hand back the recorded calls."""
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return fake_completed(stdout=CLUES_JSON)

    monkeypatch.setattr(cc.subprocess, "run", run)
    return calls


def test_default_provider_is_openai(monkeypatch):
    monkeypatch.delenv("CLUE_PROVIDER", raising=False)
    assert cc.clue_provider() == "openai"


def test_provider_selector_is_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv("CLUE_PROVIDER", " OpenCode ")
    assert cc.clue_provider() == "opencode"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("CLUE_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="CLUE_PROVIDER"):
        cc.generate_clues(["APPLE"])


def test_openai_provider_routes_to_pydantic_agent(monkeypatch):
    monkeypatch.delenv("CLUE_PROVIDER", raising=False)
    monkeypatch.setattr(
        cc, "generate_clues_openai", lambda prompt: {"APPLE": "clue for apple"}
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("opencode CLI must not run for CLUE_PROVIDER=openai")

    monkeypatch.setattr(cc.subprocess, "run", unexpected)
    assert cc.generate_clues(["APPLE"]) == {"APPLE": "clue for apple"}


def test_opencode_provider_routes_to_cli(monkeypatch, opencode_run):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.setattr(
        cc,
        "openai_agent",
        lambda: pytest.fail("pydantic-ai agent must not be built for the opencode path"),
    )

    clues = cc.generate_clues(["APPLE", "OCEAN"])

    assert clues == {
        "APPLE": "A fruit that keeps the doctor away",
        "OCEAN": "Vast body of salt water",
    }
    (command, kwargs), = opencode_run
    assert command[:4] == [
        "opencode",
        "run",
        "--model",
        "opencode-go/deepseek-v4-pro",
    ]
    prompt = command[4]
    assert "APPLE" in prompt and "OCEAN" in prompt
    # The CLI must inherit the user's environment (and so their auth).
    assert "env" not in kwargs


def test_opencode_model_env_override(monkeypatch, opencode_run):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    monkeypatch.setenv("OPENCODE_MODEL", "custom/model#variant")

    cc.generate_clues(["APPLE"])

    assert opencode_run[0][0][2:4] == ["--model", "custom/model#variant"]


def test_opencode_output_is_parsed_from_noisy_text():
    output = (
        "Sure, here are the clues.\n"
        "```json\n" + CLUES_JSON + "\n```\n"
        "Let me know if you want them harder."
    )
    assert cc.parse_clues(output, ["APPLE", "OCEAN"]) == {
        "APPLE": "A fruit that keeps the doctor away",
        "OCEAN": "Vast body of salt water",
    }


def test_opencode_echoed_example_does_not_override_requested_clues():
    example = '{"clues": {"apple": "A fruit", "python": "A snake"}}'
    output = f"{CLUES_JSON}\nFor example: {example}"

    assert cc.parse_clues(output, ["APPLE", "OCEAN"]) == {
        "APPLE": "A fruit that keeps the doctor away",
        "OCEAN": "Vast body of salt water",
    }


def test_opencode_incomplete_clue_set_raises():
    output = '{"clues": {"APPLE": "A fruit", "OCEAN": "Vast body of salt water"}}'

    with pytest.raises(cc.ClueGenerationError, match="clues"):
        cc.parse_clues(output, ["APPLE", "OCEAN", "RIVER"])


def test_opencode_clue_keys_are_canonicalized_to_requested_words():
    output = '{"clues": {"EXPLORED": "Travelled through unknown land"}}'

    assert cc.parse_clues(output, ["explored"]) == {
        "explored": "Travelled through unknown land"
    }


def test_opencode_invalid_candidate_does_not_hide_later_valid_clues():
    output = (
        '{"clues": {"APPLE": null}}\n'
        '{"clues": {"APPLE": "A fruit that keeps the doctor away", '
        '"OCEAN": "Vast body of salt water"}}'
    )

    assert cc.parse_clues(output, ["APPLE", "OCEAN"]) == {
        "APPLE": "A fruit that keeps the doctor away",
        "OCEAN": "Vast body of salt water",
    }


def test_opencode_output_without_requested_words_raises():
    output = '{"clues": {"apple": "A fruit", "python": "A snake"}}'

    with pytest.raises(cc.ClueGenerationError, match="clues"):
        cc.parse_clues(output, ["RIVER", "STONE"])


def test_opencode_output_without_clues_payload_raises():
    with pytest.raises(cc.ClueGenerationError, match="clues"):
        cc.parse_clues("I could not do that.", ["APPLE"])


def test_opencode_nonzero_exit_raises_clear_error(monkeypatch, sleeper):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        lambda *args, **kwargs: fake_completed(stderr="boom", returncode=2),
    )

    with pytest.raises(cc.ClueGenerationError, match="status 2"):
        cc.generate_clues(["APPLE"])
    assert sleeper == []


def test_opencode_missing_cli_raises_clear_error(monkeypatch, sleeper):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")

    def missing(*args, **kwargs):
        raise FileNotFoundError("opencode")

    monkeypatch.setattr(cc.subprocess, "run", missing)

    with pytest.raises(cc.ClueGenerationError, match="not found on PATH"):
        cc.generate_clues(["APPLE"])
    assert sleeper == []


def test_opencode_retries_after_unparseable_output(monkeypatch, sleeper):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    outputs = [fake_completed(stdout="nope"), fake_completed(stdout=CLUES_JSON)]

    def run(*args, **kwargs):
        return outputs.pop(0)

    monkeypatch.setattr(cc.subprocess, "run", run)

    assert cc.generate_clues(["APPLE", "OCEAN"])["APPLE"]
    assert sleeper == [2]


def test_crossword_json_shape_written_via_opencode(monkeypatch, tmp_path, opencode_run):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    grid_file = tmp_path / "grids.txt"
    grid_file.write_text('["APPLE", "OCEAN"]\n')
    crossword_file = tmp_path / "crossword.json"
    monkeypatch.setattr(cc, "GRID_FILEPATH", grid_file)
    monkeypatch.setattr(cc, "CROSSWORDS_FILEPATH", crossword_file)
    monkeypatch.setattr(cc, "get_column_words", lambda grid: [])

    cc.stream_generate_crosswords()

    written = json.loads(crossword_file.read_text())
    assert list(written) == ["crossword_0"]
    assert written["crossword_0"]["grid"] == ["APPLE", "OCEAN"]
    assert written["crossword_0"]["clues"] == {
        "APPLE": "A fruit that keeps the doctor away",
        "OCEAN": "Vast body of salt water",
    }
    assert not (tmp_path / "crossword.json.tmp").exists()


def test_failed_crossword_json_write_leaves_no_file(monkeypatch, tmp_path, sleeper):
    monkeypatch.setenv("CLUE_PROVIDER", "opencode")
    grid_file = tmp_path / "grids.txt"
    grid_file.write_text('["APP", "OCE"]\n')
    crossword_file = tmp_path / "crossword.json"
    monkeypatch.setattr(cc, "GRID_FILEPATH", grid_file)
    monkeypatch.setattr(cc, "CROSSWORDS_FILEPATH", crossword_file)
    monkeypatch.setattr(cc, "get_column_words", lambda grid: [])
    monkeypatch.setattr(
        cc.subprocess, "run", lambda *a, **k: fake_completed(returncode=1)
    )

    with pytest.raises(cc.ClueGenerationError):
        cc.stream_generate_crosswords()

    assert not crossword_file.exists()
    assert not (tmp_path / "crossword.json.tmp").exists()
