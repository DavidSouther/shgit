"Shell" / "Git" is a fluent wrapper around shell & git commands.

Create a shell wrapper with `Sh()`. Build commands with attribute access, positional arguments, and keyword flags. The `sh` and `git` presets provide `Sh()` and `Sh("git")`.

```python
from shgit import Sh, git, sh

listing = sh.ls("-la").stdout
contents = Sh("cat")("README.md")()
status = git.status("--short").stdout
# Brackets support command names that aren't Python identifiers.
pick = git["cherry-pick"]("abc123", check=False)
code = pick.returncode
```

Calls return a lazy `Run`. Reading `stdout`, `stderr`, or `returncode`, or calling the result, executes the command once and caches its result. Calling a `Run` returns its stdout. Use `|` to pass one command's captured stdout to the next command's stdin:

```python
result = sh.printf("hello\nworld\n") | sh.grep("world")
assert result.stdout == "world\n"
```

## Properties

`Sh` wraps `subprocess.run` with these settings:

* `args`: the executable and accumulated arguments, as a `list[str]`.
* `check`: whether the subprocess runner raises for a nonzero exit status; defaults to `True`. A call's `check=None` inherits this setting; `check=False` or `check=True` overrides it.
* `capture_output`: whether to capture stdout and stderr; defaults to `True`. When disabled, output goes to the parent process and the result's stdout and stderr are `None`. The call-level value is combined with the instance setting using `or`, so disable capture on the instance when needed.
* `cwd`: the working directory, as a `str`, `bytes`, or `Path`; defaults to `Path(".")`. Calls can override it.
* `log`: when `True`, logs the shell-quoted command through structlog when the `Run` is created; defaults to `False`.
* `runner`: the callable that executes the command; defaults to `subprocess_runner`. Attribute and bracket access preserve it and the other settings.

`Run.command` contains the shell-quoted command for display. Commands execute without a shell. `Run.check_returncode(event=None, logger=..., reraise=True)` executes with automatic checking disabled, checks the result, and logs a warning with the command, working directory, stdout, and stderr on failure. It raises by default; use `reraise=False` to log without raising. It returns the `Run`, and accepts a custom structlog-compatible logger and event message.

## Cloning and test runners

Use `clone(shell, check=..., capture_output=..., cwd=..., log=..., runner=...)` to create another wrapper with the same arguments and selected settings replaced:

```python
from shgit import clone, git

other_checkout = clone(git, cwd="/path/to/checkout")
```

Clone settings use `override or original`: a false value does not replace a true setting. Construct a new `Sh` when you need to disable such a setting.

Inject a `Runnable` to execute without launching subprocesses. It receives `args`, `capture_output`, `check`, `cwd`, and `input`, and returns a `subprocess.CompletedProcess`. `make_runner` adapts a `RunnableCallback` that accepts `(args, cwd, input)` and returns `RunnableCallbackCompleted(returncode, stdout, stderr)`; the adapter handles capture and return-code checking.

```python
from shgit import RunnableCallbackCompleted, Sh, make_runner


def echo(args, cwd, input):
    return RunnableCallbackCompleted(0, "\n".join(args), "")


fake = Sh(runner=make_runner(echo))
assert fake("hello", "world")() == "hello\nworld"
```

`with_exit_code(code)` creates a runner with a fixed exit status; `TrueRunner` and `FalseRunner` use zero and one. These runners do not capture output or raise automatically. `simple_runner_wrapper(callback)` adapts a callback taking only the argument list and returning a `CompletedProcess`; it delegates all behavior to that callback.

## Tests

See [tests/test_shgit.py](./tests/test_shgit.py) for executable examples and tests. Install the test dependencies and run them with:

```sh
python -m pip install -e '.[test]'
python -m pytest
```
