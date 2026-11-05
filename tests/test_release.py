from email import message_from_bytes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile


def test_nightly_versions_and_distributions_follow_release_history(tmp_path):
    """Changed main commits get monthly CalVer artifacts; released commits skip."""
    project = tmp_path / "project"
    shutil.copytree(
        Path(__file__).resolve().parents[1],
        project,
        ignore=shutil.ignore_patterns(
            ".git", ".ailly", ".venv", ".pytest_cache", "__pycache__",
            "build", "dist", "*.egg-info",
        ),
    )

    def run(*args, env=None):
        result = subprocess.run(
            args, cwd=project, env=env, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    def allocate(date):
        return run(sys.executable, ".github/scripts/release.py", "--date", date)

    run("git", "init", "--initial-branch=main")
    run("git", "config", "user.name", "Release acceptance test")
    run("git", "config", "user.email", "release-test@example.invalid")
    run("git", "config", "commit.gpgsign", "false")
    run("git", "config", "tag.gpgsign", "false")
    run("git", "add", ".")
    run("git", "commit", "-m", "Initial package")
    for tag in ("unrelated", "v2026.10.99", "v2026.11.999rc1", "v2026.11.999-extra"):
        run("git", "tag", tag)
    run("git", "commit", "--allow-empty", "-m", "Changed main after October release")

    assert allocate("2026-11-05") == "2026.11.0"
    run("git", "tag", "v2026.11.0")
    assert allocate("2026-11-06") == ""

    # History order and lexical tag order must not determine the next increment.
    for tag in ("v2026.11.9", "v2026.11.2"):
        run("git", "tag", tag)
    run("git", "commit", "--allow-empty", "-m", "Changed main")
    version = allocate("2026-11-07")
    assert version == "2026.11.10"
    build_env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SHGIT": version}
    run(sys.executable, "-m", "build", "--no-isolation", env=build_env)

    wheels = list((project / "dist").glob("*.whl"))
    sdists = list((project / "dist").glob("*.tar.gz"))
    assert len(wheels) == len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        metadata = next(name for name in wheel.namelist() if name.endswith(".dist-info/METADATA"))
        assert message_from_bytes(wheel.read(metadata))["Version"] == version
        assert {"shgit/__init__.py", "shgit/py.typed", "walk.py"} <= set(wheel.namelist())
    with tarfile.open(sdists[0]) as sdist:
        metadata = next(member for member in sdist.getmembers() if member.name.endswith("/PKG-INFO"))
        assert message_from_bytes(sdist.extractfile(metadata).read())["Version"] == version

    run("git", "tag", f"v{version}")
    assert allocate("2026-12-01") == ""
    run("git", "commit", "--allow-empty", "-m", "Changed main next month")
    assert allocate("2026-12-01") == "2026.12.0"
