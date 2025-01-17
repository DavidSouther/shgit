from pathlib import Path
from typing import Callable

RewriteAction = Callable[[str], tuple[bool, str]]


def rewrite(path: Path, act: RewriteAction, reraise=False) -> int:
    try:
        with open(path) as file:
            content = file.read()
        (replace, content) = act(content)
        if replace:
            with open(path, "w") as file:
                file.write(content)
            return 1

    except Exception as e:
        if reraise:
            raise
        else:
            print(f"Failed to modify {path} ({e})")
    return 0


def rewrite_walk(
    d,
    act: RewriteAction,
    reraise=False,
    filter: Callable[[Path], bool] = lambda p: False,
):
    d = Path(d)
    count = 0
    for root, dirs, files in d.walk():
        for name in files:
            path = root / name
            if not filter(path):
                count += rewrite(path, act, reraise)
        for name in dirs:
            path = root / name
            if not filter(path):
                count += rewrite_walk(path, act, reraise, filter)
    return count
