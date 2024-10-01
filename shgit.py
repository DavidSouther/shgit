from pathlib import Path
from subprocess import run
from typing import Optional


def make_long_flags(flags: dict[str, str]) -> list[str]:
    return [f"--{key}={val}" for key, val in flags.items()]


class Sh:
    def __init__(self,
                 prefix: Optional[str | list[str]] = None,
                 check=True,
                 cwd: str | bytes | Path = Path("."),
                 log=False):
        if prefix is None:
            self.prefix = []
        elif isinstance(prefix, str):
            self.prefix = [prefix]
        else:
            self.prefix = prefix
        self.check = check
        self.cwd: str | bytes | Path = cwd
        self.log = log

    def __call__(self,
                 *args: str,
                 capture_output=False,
                 check=None,
                 cwd: Optional[str | bytes | Path] = None,
                 **kwargs: str):
        check = check or self.check
        cwd = cwd or self.cwd
        long_args = make_long_flags(kwargs)
        cmd: list[str] = [*self.prefix, *args, *long_args]
        if self.log:
            print(cmd)
        return run(cmd,
                   capture_output=capture_output,
                   check=check,
                   shell=False,
                   cwd=cwd)

    def __getattr__(self, name: str):
        return Sh([*self.prefix, name], self.check, self.cwd, self.log)


sh = Sh()
git = Sh('git')
