from pathlib import Path
import subprocess
import sys

import pytest


ALLOCATOR = Path(__file__).resolve().parents[1] / ".github/scripts/release.py"


@pytest.fixture
def repository(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "--initial-branch=main")
    git("config", "user.name", "Release CLI test")
    git("config", "user.email", "release-test@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("config", "tag.gpgsign", "false")
    git("commit", "--allow-empty", "-m", "Initial commit")
    return tmp_path, git


def allocate(repository, date="2026-11-05"):
    path, _ = repository
    return subprocess.run(
        [sys.executable, str(ALLOCATOR), "--date", date],
        cwd=path, capture_output=True, text=True,
    )


def test_noncanonical_tags_neither_skip_head_nor_consume_increments(repository):
    _, git = repository
    for tag in (
        "v2026.0.99", "v2026.13.99", "v2026.011.99", "v2026.11.01",
        "v02026.11.99", "v0000.11.99", "v2026.11.-1", "v2026.11.999rc1",
    ):
        git("tag", tag)

    result = allocate(repository)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "2026.11.0\n"


def test_annotated_release_tag_on_head_skips_even_in_another_month(repository):
    _, git = repository
    git("tag", "-a", "v2026.10.9", "-m", "Previous release")

    result = allocate(repository)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_invalid_date_exits_with_clear_diagnostic(repository):
    result = allocate(repository, "2026-02-30")

    assert result.returncode != 0
    assert "--date" in result.stderr
    assert result.stdout == ""


def test_git_failure_exits_with_clear_diagnostic(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ALLOCATOR), "--date", "2026-11-05"],
        cwd=tmp_path, capture_output=True, text=True,
    )

    assert result.returncode != 0
    assert "git failed:" in result.stderr
    assert result.stdout == ""
