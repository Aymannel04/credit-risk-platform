"""No key, token or private key may ever be written in the repository or in the results (the API key of the writer lives in an environment variable)."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".venv", "data", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".dagster_home", ".dagster"}
TEXT = {".py", ".md", ".yaml", ".yml", ".json", ".ps1", ".txt", ".toml", ".csv", ".cfg", ".ini", ".env", ".sh"}
PATTERNS = {
    "NVIDIA API key": re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    "AWS access key id": re.compile(r"A(?:KIA|SIA|ROA)[A-Z0-9]{16}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "bearer token with a value": re.compile(r"Bearer\s+(?!\{|\$|<|test-key|stand-in)[A-Za-z0-9_\-\.]{30,}"),
}


def _files():
    for folder, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]  # never even enter .venv, data, .git
        for name in names:
            path = Path(folder) / name
            if path.suffix.lower() in TEXT and path.stat().st_size < 3_000_000:
                yield path


def test_no_secret_looking_value_is_written_in_any_text_file_of_the_repository():
    found = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                found.append((str(path.relative_to(ROOT)), name))
    assert found == [], found


def test_the_scan_really_looks_at_files():
    names = {p.name for p in _files()}
    assert {"memo_policy.yaml", "validator.py", "agent_eval_seeded.json", "decision-log.md"} <= names
    assert PATTERNS["NVIDIA API key"].search("x nvapi-" + "A" * 30), "the pattern must match a key-shaped value"
    assert not PATTERNS["NVIDIA API key"].search("the variable NVIDIA_API_KEY and the word nvapi alone")


def test_the_env_files_and_keys_are_ignored_by_git():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore and "credentials" in ignore
