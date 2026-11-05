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

## Placing options

A command is built from segments. Attribute and bracket access add to the command and return another `Sh`; only the final call returns a `Run`. Positional arguments are passed through unchanged. A mapping in brackets adds options at that position, which matters for tools that take some options before the subcommand, some after it, and some after `--` for the program they launch:

```python
docker = Sh("docker")
docker.run[{"detach": True, "name": "db", "env": {"POSTGRES_HOST_AUTH_METHOD": "trust"}}](
    "postgres:16", "--", "-c", "fsync=off"
)
# docker run --detach --name=db --env=POSTGRES_HOST_AUTH_METHOD=trust postgres:16 -- -c fsync=off
git[{"C": "/repo"}].commit[{"m": "message"}]()
# git -C /repo commit -m message
```

Options render as follows:

| Value | Rendered |
| --- | --- |
| `"x"`, `5432` | `--key=x`, `--key=5432` |
| `True` | `--key` |
| `False`, `None` | omitted |
| `["a", "b"]` | `--key=a --key=b` |
| `{"A": "1"}` | `--key=A=1` |
| one-letter key | `-k value` (`-k` alone for `True`) |

`_` in a key is written as `-`; use a mapping literal for any other spelling. Keyword arguments to a call use the same rendering, placed after the positional arguments, so use them only for options that belong at the end. `input=` passes text to the command's stdin.

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
* `timeout`: seconds a command may run before `subprocess.TimeoutExpired` is raised, or `None` for no limit; defaults to `None`. A call's `timeout=` overrides it. A command that times out is not cached, so reading the `Run` again runs it again. `check_returncode` logs a timeout like any other failure.
* `runner`: the callable that executes the command; defaults to `subprocess_runner`. Attribute and bracket access preserve it and the other settings.

`Run.command` contains the shell-quoted command for display. Commands execute without a shell. `Run.check_returncode(event=None, logger=..., reraise=True)` executes with automatic checking disabled, checks the result, and logs a warning with the command, working directory, stdout, and stderr on failure. It raises by default; use `reraise=False` to log without raising. It returns the `Run`, and accepts a custom structlog-compatible logger and event message.

## Cloning and test runners

Use `clone(shell, check=..., capture_output=..., cwd=..., log=..., runner=..., timeout=...)` to create another wrapper with the same arguments and selected settings replaced:

```python
from shgit import clone, git

other_checkout = clone(git, cwd="/path/to/checkout")
```

Clone settings use `override or original`: a false value does not replace a true setting. Construct a new `Sh` when you need to disable such a setting. `timeout` is the exception: any value other than `None` replaces the original, though `None` cannot clear it.

Inject a `Runnable` to execute without launching subprocesses. It receives `args`, `capture_output`, `check`, `cwd`, and `input`, plus `timeout` when one is set, and returns a `subprocess.CompletedProcess`. A runner that never receives a timeout need not accept the parameter; the built-in fake runners accept it and ignore it. `make_runner` adapts a `RunnableCallback` that accepts `(args, cwd, input)` and returns `RunnableCallbackCompleted(returncode, stdout, stderr)`; the adapter handles capture and return-code checking.

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

CI runs the tests and builds wheel and source distributions on pushes and pull requests, using Python 3.11 and 3.15. To build locally:

```sh
python -m build
```

## Nightly releases

The nightly workflow checks `main` daily at 06:17 UTC and can also be run manually from `main`. It publishes only when the selected commit has no valid release tag, even across month boundaries. Versions use UTC `Year.Month.Increment`: `2026.11.0`, `2026.11.1`, then `2026.12.0`. Months are unpadded, increments start at zero, and each month's next increment follows its greatest existing release tag. Tags use a `v` prefix; malformed tags are ignored.

Release runs are serialized. Tests, wheel/sdist builds, and distribution-version checks must pass before creating the tag and GitHub prerelease with both downloadable assets. Nothing is published to PyPI. Ordinary builds infer a version from Git with setuptools-scm; release builds set `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SHGIT` to the allocated version.

If publication stops after GitHub creates a release, inspect that release before retrying. To repair missing assets, check out its exact commit, rebuild with the same version override, and use `gh release upload v<version> dist/*.whl dist/*.tar.gz --clobber`. If the release remains a draft, finish it with `gh release edit v<version> --draft=false --prerelease --latest=false`. A commit already bearing a valid release tag is skipped by later nightly runs.

## Signed commits

Local development uses Git's SSH commit signing with an existing SSH key. Keep the private key outside the repository, register the public key as a GitHub signing key, and configure `gpg.format=ssh`, `user.signingkey`, and `commit.gpgsign=true`. Local verification also needs `gpg.ssh.allowedSignersFile` containing the author identity and public key; check a signed commit with `git verify-commit HEAD`. Nightly releases create no source commits and need no signing key or signing secret in Actions.
