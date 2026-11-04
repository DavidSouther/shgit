from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from subprocess import CompletedProcess, run
from typing import Any, Callable, Mapping, Optional, Protocol, Union

from structlog.stdlib import BoundLogger, get_logger

logger = get_logger(__name__)


def render_flag(key: str, value: Any) -> list[str]:
    """Render one option the way most CLIs accept it.

    `None` and `False` omit the option; `True` is a bare switch. A list repeats the
    option, and a mapping repeats it as `KEY=VALUE` (docker's `--env`, `--label`).
    A one-letter key is a short option with its value as a separate argument; a longer
    key is `--key=value`, with `_` written as `-`.
    """
    if value is None or value is False:
        return []
    short = len(key) == 1
    flag = f"-{key}" if short else f"--{key.replace('_', '-')}"
    if value is True:
        return [flag]
    if isinstance(value, Mapping):
        values = [f"{name}={val}" for name, val in value.items()]
    elif isinstance(value, (list, tuple)):
        values = [str(val) for val in value]
    else:
        values = [str(value)]
    rendered: list[str] = []
    for val in values:
        rendered += [flag, val] if short else [f"{flag}={val}"]
    return rendered


def make_flags(flags: Mapping[str, Any]) -> list[str]:
    return [arg for key, value in flags.items() for arg in render_flag(key, value)]


make_long_flags = make_flags


class Runnable(Protocol):
    def __call__(
        self,
        args: list[str],
        capture_output: bool,
        check: bool,
        cwd: Path,
        input: Optional[str],
        timeout: Optional[float] = None,
    ) -> CompletedProcess[str]:
        pass


def subprocess_runner(
    args: list[str],
    capture_output: bool,
    check: bool,
    cwd: Path,
    input: Optional[str],
    timeout: Optional[float] = None,
) -> CompletedProcess[str]:
    return run(
        args,
        capture_output=capture_output,
        check=check,
        cwd=cwd,
        input=input,
        timeout=timeout,
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
        timeout: Optional[float] = None,
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
        timeout: Optional[float] = None,
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
        timeout: Optional[float] = None,
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
        timeout: Optional[float] = None,
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
        self.timeout = timeout

    def __call__(
        self,
        *args: str,
        capture_output=False,
        check=None,
        cwd: Union[str, bytes, Path, None] = None,
        timeout: Optional[float] = None,
        input: Optional[str] = None,
        **kwargs: Any,
    ):
        if check is None:
            check = self.check
        if timeout is None:
            timeout = self.timeout
        cwd = cwd or self.cwd
        capture_output = capture_output or self.capture_output
        cmd: list[str] = [*self.args, *args, *make_flags(kwargs)]
        run = Run(cmd, check, cwd, capture_output, self.runner, timeout)
        run.pipe = input
        if self.log:
            logger.info(run.command)
        return run

    def _with(self, *args: str) -> "Sh":
        return Sh(
            [*self.args, *args],
            self.check,
            self.capture_output,
            self.cwd,
            self.log,
            self.runner,
            self.timeout,
        )

    def __getattr__(self, arg: str):
        return self._with(arg)

    def __getitem__(self, arg: Union[str, Mapping[str, Any]]):
        """Append a name, or a mapping of options, at this position in the command."""
        if isinstance(arg, Mapping):
            return self._with(*make_flags(arg))
        return self._with(arg)


def clone(
    sh: Sh,
    check: Optional[bool] = None,
    capture_output: Optional[bool] = None,
    cwd: Optional[Union[str, bytes, Path]] = None,
    log: Optional[bool] = None,
    runner: Optional[Runnable] = None,
    timeout: Optional[float] = None,
) -> Sh:
    return Sh(
        sh.args,
        check=check or sh.check,
        capture_output=capture_output or sh.capture_output,
        cwd=cwd or sh.cwd,
        log=log or sh.log,
        runner=runner or sh.runner,
        timeout=sh.timeout if timeout is None else timeout,
    )


class Run:
    def __init__(
        self,
        args,
        check,
        cwd,
        capture_output,
        runner: Runnable,
        timeout: Optional[float] = None,
    ):
        self.args = args
        self.check = check
        self.cwd = cwd
        self.capture_output = capture_output
        self.pipe: Optional[str] = None
        self.completed: Optional[CompletedProcess[str]] = None
        self.runner: Runnable = runner
        self.timeout = timeout
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
                stdout=self.completed.stdout if self.completed else None,
                stderr=self.completed.stderr if self.completed else None,
            )
            if reraise:
                raise e
        return self

    def _run(self) -> CompletedProcess[str]:
        if self.completed is None:
            # Only pass a timeout when one is set, so runners that predate it keep working.
            options = {} if self.timeout is None else {"timeout": self.timeout}
            self.completed = self.runner(
                self.args,
                capture_output=self.capture_output,
                check=self.check,
                cwd=self.cwd,
                input=self.pipe,
                **options,
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
