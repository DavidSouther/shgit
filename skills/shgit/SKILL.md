---
name: shgit
description: Use when writing or reviewing Python that runs external commands (git, docker, aws, psql, make) through the shgit library, especially when a helper function wraps every call or the code reads like subprocess.run with different spelling.
---

# shgit

shgit builds a command from segments and runs it lazily. Its value is that the command's shape, its working directory, its tolerance for failure, and its test double all live on the object, so call sites stay one line each. Code that routes every call through a helper has bypassed that.

Written against shgit `main` on 2026-11-04. The property list is in the README; this file covers habits.

## The model

- `Sh` is a reusable command prefix with settings: `check` (default `True`), `capture_output` (default `True`), `cwd`, `timeout`, `log`, `runner`.
- Attribute access, brackets, and calls extend the command. Only the final `(...)` call returns a `Run`.
- A `Run` is lazy. Reading `.stdout`, `.stderr`, `.returncode`, or calling it (which returns stdout) executes once and caches.
- With `check=True` a failure is a `subprocess.CalledProcessError` raised on that first read, not at the call.

```python
from shgit import Sh

echo = Sh("echo")
run = echo("hello")      # nothing has run
print(run().strip())     # runs now; prints hello
print(run.returncode)    # cached; prints 0
```

## Bind once, build in order

Create one `Sh` per tool at module level. Add subcommands by attribute, names that are not identifiers by brackets, values by arguments.

```python
from shgit import Sh

git = Sh("git")
cherry = git["cherry-pick"]("abc123", check=False)   # git cherry-pick abc123
```

**Brackets for any name that is also a setting.** `args`, `check`, `capture_output`, `cwd`, `log`, `runner`, `timeout` are `Sh` fields, so `git.log` is `False`, not a subcommand. Write `git["log"]`.

**Place options with a mapping in brackets.** Some tools take options before the subcommand, some between subcommand and argument, some after `--` for the program they launch. A mapping adds its options at that position:

```python
from shgit import Sh

docker = Sh("docker")
run = docker.run[{"detach": True, "name": "db", "env": {"MODE": "test"}}](
    "postgres:16", "--", "-c", "fsync=off"
)
assert run.args == [
    "docker", "run", "--detach", "--name=db", "--env=MODE=test",
    "postgres:16", "--", "-c", "fsync=off",
]
git = Sh("git")
assert git[{"C": "/repo"}].commit[{"m": "msg"}]().args == ["git", "-C", "/repo", "commit", "-m", "msg"]
```

Values render as: `True` a bare switch; `False` and `None` omitted; a list repeated; a mapping repeated as `KEY=VALUE`; a one-letter key as `-k value`; `_` in a key as `-`. Arguments after `--` belong to the launched program; pass them as plain strings.

**Keyword arguments in the final call use the same rendering but always land after the positional arguments.** `docker.run("img", name="x")` is `docker run img --name=x`, which hands `--name=x` to the container. Use a bracket mapping before the positional arguments instead.

## Handle failure where it is known

Leave `check=True`. The code that issued the command knows what its failure means, so translate it there:

```python
from subprocess import CalledProcessError

from shgit import Sh

class DeployError(Exception):
    pass

def release_listing(path):
    try:
        return Sh("ls")(path).stdout
    except CalledProcessError as error:
        raise DeployError(f"cannot list {path}: {error.stderr.strip()}") from error

try:
    release_listing("/no/such/dir")
except DeployError as error:
    print(error)
```

Use the narrowest tool for the outcome:

| Situation | Use |
| --- | --- |
| A nonzero exit is the expected answer (readiness probe, `grep`) | `check=False` on that call, then read `returncode` |
| Run now, fail loudly, record the command, cwd, stdout, stderr | `run.check_returncode(event="what was attempted")` |
| Same, but only log | `run.check_returncode(reraise=False)` |
| A command that must not hang | `timeout=` (see below); expiry raises `TimeoutExpired` |

```python
from shgit import Sh

ready = Sh("grep")("-q", "ready", "/dev/null", check=False).returncode == 0
assert ready is False
```

Do not write one `execute(run)` that catches and re-raises for every call. It discards the call's context (which command, what it meant), and each call site then reads as `execute(...)`, not as the command.

## Settings belong on the shell

- `cwd` and `timeout` are settings. Derive a variant instead of passing them to each call: `repo = clone(git, cwd=path)`.
- A call-level `capture_output=False` cannot override an instance that captures; the two combine with `or`. Build the instance without capture to stream output: `Sh("make", capture_output=False)`.
- `clone` combines settings with `or` too, so a false override does not replace a true setting, except `timeout`, where any value other than `None` replaces it.
- `timeout=` accepts a number of seconds on the instance or the call. A timed-out `Run` caches nothing and runs again when read again.

```python
from shgit import Sh, clone

slow = Sh("sleep", timeout=0.1)
patient = clone(slow, timeout=5)
assert slow.timeout == 0.1 and patient.timeout == 5
```

## Output and stdin

- Read output with `.stdout` (or call the `Run`); add `.strip()` where a single line is expected.
- `input=` on the call sends text to stdin.
- `a | b` runs both commands at the `|` and passes `a`'s stdout to `b`'s stdin. A failure in either raises there.

```python
from shgit import sh

assert (sh.printf("a\nb\n") | sh.grep("b")).stdout == "b\n"
assert sh.cat(input="piped\n")() == "piped\n"
```

## Test with a runner

Inject a `runner`; do not patch `subprocess`. Pick by failure style:

| Runner | Behavior |
| --- | --- |
| `make_runner(callback)` | callback receives `(args, cwd, input)` and returns `RunnableCallbackCompleted(returncode, stdout, stderr)`; honors `check`, so a nonzero code raises `CalledProcessError` |
| `TrueRunner`, `FalseRunner`, `with_exit_code(n)` | return that exit code and never raise, even with `check=True` |

Use `make_runner` to exercise a failure handler, and assert on the arguments the callback saw.

```python
from subprocess import CalledProcessError

from shgit import RunnableCallbackCompleted, Sh, make_runner

seen = []

def callback(args, cwd, input):
    seen.append(args)
    return RunnableCallbackCompleted(returncode=3, stdout="", stderr="boom")

tool = Sh("tool", runner=make_runner(callback))
try:
    tool.deploy[{"env": "prod"}]("v1")()
except CalledProcessError as error:
    assert error.returncode == 3
assert seen == [["tool", "deploy", "--env=prod", "v1"]]
```

Code that takes a `Sh` parameter (default the real one) can be tested without a subprocess.

## Not `subprocess.run`

| Reaching for | shgit already has |
| --- | --- |
| `subprocess.run([...], check=True)` | the default; the error arrives on first read |
| `capture_output=True, text=True` | the default; `.stdout` is `str` |
| `cwd=` on every call | `clone(shell, cwd=...)` |
| `timeout=` on every call | `Sh(..., timeout=...)` |
| `input=` | `input=` on the call, or `a | b` |
| `shell=True` and quoting | none needed; commands run without a shell; `|` pipes |
| a `run()` / `execute()` wrapper | a module-level `Sh`; missing behavior is a setting, a segment, or a runner |
| `mock.patch("subprocess.run")` | an injected `runner` |
| building flag lists by hand | bracket mappings |
