from pathlib import Path
from subprocess import run
from typing import Any, Optional


def make_long_flags(flags: dict[str, str]) -> list[str]:
    return [f"--{key}={val}" for key, val in flags.items()]


class Sh:
    def __init__(self,
                 args: Optional[str | list[str]] = None,
                 check=True,
                 capture_output=False,
                 cwd: str | bytes | Path = Path("."),
                 log=False):
        if args is None:
            self.args = []
        elif isinstance(args, str):
            self.args = [args]
        else:
            self.args = args
        self.check = check
        self.capture_output = capture_output
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
        capture_output = capture_output or self.capture_output
        long_args = make_long_flags(kwargs)
        cmd: list[str] = [*self.args, *args, *long_args]
        if self.log:
            print(cmd)
        return Run(cmd, check, cwd, capture_output)

    def __getattr__(self, arg: str):
        return Sh([*self.args, arg],
                  self.check,
                  self.capture_output,
                  self.cwd,
                  self.log)


class Run():
    def __init__(self, args, check, cwd, capture_output):
        self.args = args
        self.check = check
        self.cwd = cwd
        self.capture_output = capture_output
        self.pipe = None
        self.completed = None

    @property
    def stdout(self):
        self._run()
        return self.completed.stdout

    @property
    def stderr(self):
        self._run()
        return self.completed.stderr
    
    @property
    def returncode(self):
        self._run()
        return self.completed.returncode

    def check_returncode(self):
        self._run()
        return self.completed.check_returncode()

    def _run(self):
        if self.completed is None:
            self.completed = run(
                self.args,
                capture_output=self.capture_output,
                check=self.check,
                shell=False,
                cwd=self.cwd,
                input=self.pipe,
                encoding="utf-8")
    
    def __or__(self, other):
        self.capture_output = True
        self._run()
        other.pipe = self.completed.stdout
        other._run()
        return other


sh = Sh()
git = Sh('git')
