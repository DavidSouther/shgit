from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess, TimeoutExpired
import sys
from typing import Union

import pytest
from structlog.testing import capture_logs

from shgit import (
    FalseRunner,
    RunnableCallbackCompleted,
    Sh,
    TrueRunner,
    clone,
    git,
    make_runner,
    sh,
    simple_runner_wrapper,
    with_exit_code,
)


def test_shell_call():
    run = sh["/usr/bin/env"].which("which")
    assert run.returncode == 0
    assert run.stdout.strip().endswith("/bin/which")


def echo(args: list[str], cwd: Path, input: Union[str, None]):
    return RunnableCallbackCompleted(returncode=0, stdout="\n".join(args), stderr="")


def cat(args: list[str], cwd: Path, input: Union[str, None]):
    return RunnableCallbackCompleted(returncode=0, stdout=input or "", stderr="")


def test_fake_shell():
    run = Sh(runner=make_runner(echo))("Hello")
    assert run.returncode == 0
    assert run.stdout == "Hello"


def test_shell_or():
    run_echo = Sh(runner=make_runner(echo))
    run_cat = Sh(runner=make_runner(cat))
    run = run_echo("Hello", "world") | run_cat()
    assert run.returncode == 0
    assert run.stdout == "Hello\nworld"


def test_real_subprocess(tmp_path):
    command = Sh(sys.executable, cwd=tmp_path)
    run = command("-c", "import os, sys; print(os.getcwd()); print('error', file=sys.stderr)")
    assert run.stdout.strip() == str(tmp_path)
    assert run.stderr == "error\n"
    assert run.returncode == 0
    assert run() == run.stdout


def test_runner_receives_options_and_runs_only_once(tmp_path):
    calls = []

    def runner(args, capture_output, check, cwd, input):
        calls.append((args, capture_output, check, cwd, input))
        return CompletedProcess(args, 0, stdout="out", stderr="err")

    shell = Sh("tool", runner=runner, check=False, capture_output=False)
    run = shell.remote["show-all"]("some value", cwd=tmp_path, capture_output=True, verbose="yes")
    assert calls == []
    assert run.stdout == "out"
    assert run.stderr == "err"
    assert run.returncode == 0
    assert run() == "out"
    assert calls == [(["tool", "remote", "show-all", "some value", "--verbose=yes"], True, False, tmp_path, None)]
    assert run.command == "tool remote show-all 'some value' --verbose=yes"


@pytest.mark.parametrize("default, override, raises", [(True, None, True), (True, False, False), (False, None, False), (False, True, True)])
def test_check_override(default, override, raises):
    command = Sh(sys.executable, check=default)
    run = command("-c", "raise SystemExit(7)", check=override)
    if raises:
        with pytest.raises(CalledProcessError) as error:
            _ = run.returncode
        assert error.value.returncode == 7
    else:
        assert run.returncode == 7


@pytest.mark.parametrize("capture_output", [True, False])
def test_make_runner_capture_and_check(tmp_path, capture_output):
    seen = []

    def callback(args, cwd, input):
        seen.append((args, cwd, input))
        return RunnableCallbackCompleted(3, "out", "err")

    runner = make_runner(callback)
    result = runner(["test"], capture_output, False, tmp_path, "piped")
    assert seen == [(["test"], tmp_path, "piped")]
    assert result.returncode == 3
    assert result.stdout == ("out" if capture_output else None)
    assert result.stderr == ("err" if capture_output else None)
    with pytest.raises(CalledProcessError):
        runner(["test"], capture_output, True, tmp_path, None)


@pytest.mark.parametrize("runner, code", [(TrueRunner, 0), (FalseRunner, 1), (with_exit_code(9), 9)])
def test_exit_code_runners(runner, code):
    # Fixed exit-code runners return a result even when check is enabled.
    assert Sh(runner=runner)().returncode == code


def test_simple_runner_wrapper():
    seen = []

    def callback(args):
        seen.append(args)
        return CompletedProcess(args, 2, stdout="out", stderr="err")

    run = Sh("tool", runner=simple_runner_wrapper(callback))("arg")
    assert run.stdout == "out"
    assert run.stderr == "err"
    assert run.returncode == 2
    assert seen == [["tool", "arg"]]


def test_clone_preserves_and_overrides_settings(tmp_path):
    original = Sh("tool", check=False, capture_output=False, runner=TrueRunner)
    copied = clone(original)
    assert copied is not original
    assert vars(copied) == vars(original)
    changed = clone(original, check=True, capture_output=True, cwd=tmp_path, log=True, runner=FalseRunner)
    assert changed.args == ["tool"]
    assert changed.check is True
    assert changed.capture_output is True
    assert changed.cwd == tmp_path
    assert changed.log is True
    assert changed.runner is FalseRunner
    assert original.check is False
    assert original.runner is TrueRunner
    nested = changed.remote["show-all"]
    assert nested.args == ["tool", "remote", "show-all"]
    for setting in ("check", "capture_output", "cwd", "log", "runner"):
        assert getattr(nested, setting) == getattr(changed, setting)


def test_boolean_fallbacks_are_preserved():
    original = Sh(log=True, runner=TrueRunner)
    copied = clone(original, check=False, capture_output=False, log=False)
    assert copied.check is True
    assert copied.capture_output is True
    assert copied.log is True
    assert Sh(runner=TrueRunner)(capture_output=False).capture_output is True


def test_command_logging():
    with capture_logs() as events:
        run = Sh("tool", log=True, runner=TrueRunner)("some value")
    assert events == [{"event": "tool 'some value'", "log_level": "info"}]
    assert run.completed is None


@pytest.mark.parametrize("reraise", [True, False])
@pytest.mark.parametrize("event", [None, "command failed"])
def test_check_returncode_logs_failure(reraise, event, tmp_path):
    def callback(args, cwd, input):
        return RunnableCallbackCompleted(5, "out", "err")

    run = Sh("tool", cwd=tmp_path, runner=make_runner(callback))("arg")
    with capture_logs() as events:
        if reraise:
            with pytest.raises(CalledProcessError) as error:
                run.check_returncode(event=event)
            assert error.value.returncode == 5
        else:
            assert run.check_returncode(event=event, reraise=False) is run
    assert events == [{"event": event or "tool arg", "log_level": "warning", "cwd": tmp_path, "command": "tool arg", "stdout": "out", "stderr": "err"}]
    assert run.check is False


def test_check_returncode_custom_logger_and_success():
    class Logger:
        def __init__(self):
            self.events = []

        def warning(self, event, **fields):
            self.events.append((event, fields))

    logger = Logger()
    failed = Sh("tool", runner=FalseRunner)()
    assert failed.check_returncode("failure", logger=logger, reraise=False) is failed
    assert logger.events[0][0] == "failure"
    success = Sh(runner=TrueRunner)()
    assert success.check_returncode(logger=logger) is success
    assert len(logger.events) == 1


def test_generic_presets():
    assert sh.args == []
    assert git.args == ["git"]


SLEEP = "import time; time.sleep(5)"


def test_timeout_raises_for_slow_command():
    run = Sh(sys.executable, timeout=0.2)("-c", SLEEP)
    with pytest.raises(TimeoutExpired):
        _ = run.returncode


def test_call_timeout_overrides_instance_timeout():
    slow = Sh(sys.executable, timeout=30)("-c", SLEEP, timeout=0.2)
    with pytest.raises(TimeoutExpired):
        _ = slow.returncode
    fast = Sh(sys.executable, timeout=0.2)("-c", "pass", timeout=30)
    assert fast.returncode == 0


def test_timeout_passes_through_attribute_and_bracket_access():
    shell = Sh("tool", timeout=3).remote["show-all"]
    assert shell.timeout == 3
    assert shell().timeout == 3


def test_runner_only_receives_timeout_when_set():
    calls = []

    def runner(args, capture_output, check, cwd, input, **options):
        calls.append(options)
        return CompletedProcess(args, 0, stdout="", stderr="")

    Sh("tool", runner=runner)().returncode
    Sh("tool", runner=runner, timeout=4)().returncode
    Sh("tool", runner=runner)(timeout=5).returncode
    assert calls == [{}, {"timeout": 4}, {"timeout": 5}]


def test_clone_timeout():
    original = Sh("tool", timeout=3)
    assert clone(original).timeout == 3
    assert clone(original, timeout=9).timeout == 9
    assert original.timeout == 3


@pytest.mark.parametrize("runner", [TrueRunner, FalseRunner, with_exit_code(2), make_runner(echo)])
def test_builtin_runners_accept_timeout(runner):
    assert Sh(runner=runner, check=False, timeout=1)().returncode in (0, 1, 2)


def test_check_returncode_logs_timeout_without_rerunning():
    calls = []

    def runner(args, capture_output, check, cwd, input, timeout=None):
        calls.append(args)
        raise TimeoutExpired(args, timeout)

    run = Sh("tool", runner=runner, timeout=1)("arg")
    with capture_logs() as events:
        with pytest.raises(TimeoutExpired):
            run.check_returncode()
    assert len(calls) == 1
    assert events[0]["stdout"] is None
    assert events[0]["stderr"] is None
