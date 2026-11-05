"""Print the next monthly release version, or nothing for an already released HEAD."""

import argparse
from datetime import date, datetime, timezone
import re
import subprocess


def release_tag(tag: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v([0-9]{4})\.([1-9]|1[0-2])\.(0|[1-9][0-9]*)", tag)
    return tuple(map(int, match.groups())) if match and int(match[1]) > 0 else None


def next_version(today: date) -> str | None:
    def tags(*args: str) -> list[str]:
        return subprocess.run(
            ["git", "tag", *args], check=True, capture_output=True, text=True,
        ).stdout.splitlines()

    if any(release_tag(tag) is not None for tag in tags("--points-at", "HEAD")):
        return None
    versions = (release_tag(tag) for tag in tags())
    increments = [
        version[2] for version in versions
        if version is not None and version[:2] == (today.year, today.month)
    ]
    return f"{today.year:04d}.{today.month}.{max(increments, default=-1) + 1}"


def main() -> None:
    def parse_date(value: str) -> date:
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                raise ValueError
            return date.fromisoformat(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("expected a valid YYYY-MM-DD date") from error

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=parse_date, default=datetime.now(timezone.utc).date())
    args = parser.parse_args()
    try:
        version = next_version(args.date)
    except (subprocess.CalledProcessError, OSError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        parser.exit(1, f"git failed: {detail}\n")
    if version is not None:
        print(version)


if __name__ == "__main__":
    main()
