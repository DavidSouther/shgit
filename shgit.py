from pathlib import Path
from subprocess import run
from typing import Optional


def make_long_flags(flags: dict[str, str]) -> list[str]:
    return [f"--{key}={val}" for key, val in flags.items()]


type StrOrBytesPath = str | bytes | Path


class Sh:
    def __init__(self, prefix=None):
        self.prefix = prefix
        self.check = True
        self.cwd: StrOrBytesPath = Path('.')
        self.log = False

    def __getattr__(self, name):
        def sh_call(
                *args,
                capture_output=False,
                check=self.check,
                cwd: Optional[StrOrBytesPath] = self.cwd,
                **kwargs: str
        ):
            long_args = make_long_flags(kwargs)
            cmd = [name, *args, *long_args]
            if self.prefix:
                cmd = [self.prefix] + cmd
            if self.log:
                print(cmd)
            return run(cmd,
                       capture_output=capture_output,
                       check=check,
                       shell=False,
                       cwd=cwd)

        return sh_call


sh = Sh()
git = Sh('git')
