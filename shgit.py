from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from subprocess import CompletedProcess, run
from typing import Callable, Optional, Protocol, Union

from structlog.stdlib import BoundLogger, get_logger

logger = get_logger(__name__)


def make_long_flags(flags: dict[str, str]) -> list[str]:
    return [f"--{key}={val}" for key, val in flags.items()]


class Runnable(Protocol):
    def __call__(
        self,
        args: list[str],
        capture_output: bool,
        check: bool,
        cwd: Path,
        input: Optional[str],
    ) -> CompletedProcess[str]:
        pass


def subprocess_runner(
    args: list[str],
    capture_output: bool,
    check: bool,
    cwd: Path,
    input: Optional[str],
) -> CompletedProcess[str]:
    return run(
        args,
        capture_output=capture_output,
        check=check,
        cwd=cwd,
        input=input,
        shell=False,
        encoding="utf-8",
    )


@dataclass
class RunnableCallbackCompleted:
    returncode: int
    stdout: Optional[str]
    stderr: Optional[str]


class RunnableCallback(Protocol):
    def __call__(
        self, args: list[str], cwd: Path, input: Optional[str]
    ) -> RunnableCallbackCompleted:
        pass


def make_runner(cb: RunnableCallback) -> Runnable:
    def runner(
        args: list[str],
        capture_output: bool,
        check: bool,
        cwd: Path,
        input: Optional[str],
    ) -> CompletedProcess:
        output = cb(args, cwd, input)
        if capture_output:
            completed = CompletedProcess(
                args, output.returncode, stdout=output.stdout, stderr=output.stderr
            )
        else:
            completed = CompletedProcess(args, output.returncode)
        if check:
            completed.check_returncode()
        return completed

    return runner


def with_exit_code(code: int) -> Runnable:
    def runner(
        args: list[str],
        capture_output: bool,
        check: bool,
        cwd: Path,
        input: Optional[str],
    ) -> CompletedProcess:
        return CompletedProcess(args, returncode=code)

    return runner


def simple_runner_wrapper(cb: Callable[[list[str]], CompletedProcess[str]]) -> Runnable:
    def runner(
        args: list[str],
        capture_output: bool,
        check: bool,
        cwd: Path,
        input: Optional[str],
    ) -> CompletedProcess:
        return cb(args)

    return runner


TrueRunner: Runnable = with_exit_code(0)
FalseRunner: Runnable = with_exit_code(1)


class Sh:
    def __init__(
        self,
        args: Union[str, list[str], None] = None,
        check=True,
        capture_output=True,
        cwd: Union[str, bytes, Path] = Path("."),
        log=False,
        runner: Runnable = subprocess_runner,
    ):
        if args is None:
            self.args = []
        elif isinstance(args, str):
            self.args = [args]
        else:
            self.args = args
        self.check = check
        self.capture_output = capture_output
        self.cwd: Union[str, bytes, Path] = cwd
        self.log = log
        self.runner = runner

    def __call__(
        self,
        *args: str,
        capture_output=False,
        check=None,
        cwd: Union[str, bytes, Path, None] = None,
        **kwargs: str,
    ):
        if check is None:
            check = self.check
        cwd = cwd or self.cwd
        capture_output = capture_output or self.capture_output
        long_args = make_long_flags(kwargs)
        cmd: list[str] = [*self.args, *args, *long_args]
        run = Run(cmd, check, cwd, capture_output, self.runner)
        if self.log:
            logger.info(run.command)
        return run

    def __getattr__(self, arg: str):
        return Sh(
            [*self.args, arg], self.check, self.capture_output, self.cwd, self.log, self.runner
        )

    def __getitem__(self, arg: str):
        return Sh(
            [*self.args, arg], self.check, self.capture_output, self.cwd, self.log, self.runner
        )


def clone(
    sh: Sh,
    check: Optional[bool] = None,
    capture_output: Optional[bool] = None,
    cwd: Optional[Union[str, bytes, Path]] = None,
    log: Optional[bool] = None,
    runner: Optional[Runnable] = None,
) -> Sh:
    return Sh(
        sh.args,
        check=check or sh.check,
        capture_output=capture_output or sh.capture_output,
        cwd=cwd or sh.cwd,
        log=log or sh.log,
        runner=runner or sh.runner,
    )


class Run:
    def __init__(self, args, check, cwd, capture_output, runner: Runnable):
        self.args = args
        self.check = check
        self.cwd = cwd
        self.capture_output = capture_output
        self.pipe: Optional[str] = None
        self.completed: Optional[CompletedProcess[str]] = None
        self.runner: Runnable = runner
        self.command = " ".join(quote(arg) for arg in args)

    @property
    def stdout(self):
        completed = self._run()
        return completed.stdout

    @property
    def stderr(self):
        completed = self._run()
        return completed.stderr

    @property
    def returncode(self):
        completed = self._run()
        return completed.returncode

    def check_returncode(
        self, event: Optional[str] = None, logger: BoundLogger = logger, reraise=True
    ) -> "Run":
        event = event or self.command
        self.check = False
        try:
            self._run()
            assert self.completed is not None
            self.completed.check_returncode()
        except Exception as e:
            logger.warning(
                event or "Command returned failure",
                cwd=self.cwd,
                command=self.command,
                stdout=self.stdout,
                stderr=self.stderr,
            )
            if reraise:
                raise e
        return self

    def _run(self) -> CompletedProcess[str]:
        if self.completed is None:
            self.completed = self.runner(
                self.args,
                capture_output=self.capture_output,
                check=self.check,
                cwd=self.cwd,
                input=self.pipe,
            )
        return self.completed

    def __or__(self, other):
        self.capture_output = True
        completed = self._run()
        other.pipe = completed.stdout
        other._run()
        return other

    def __call__(self) -> str:
        return self.stdout


# Pre-configured shell instances for common tools
sh = Sh()
git = Sh("git")
