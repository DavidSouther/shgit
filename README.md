"Shell" / "Git" is a fluent wrapper around shell & git commands.

Create a "shell" wrapper with `Sh()`. Call binaries & set flags as property access, and as arguments. `Sh().ls('-la')`, `Sh('cat')('README.md')`. `git = Sh('git'), git.remote.add.origin('git://...')`.

## Properties

An instance of `Sh` has several shell properties, wrapping `subprocess.run` and `popen`.

* `args`: `list[str]` of the main binary and simple string arguments following the binary.
* `check`: `bool` controls whether `popen` raises when the command returns non-zero.
* `capture_output`: `bool` passed to `popen`'s argument of the same name. When True, returns the ExecutionResult; when False, prints the output to stdout/err and returns None. 
* `cwd`: `str | bytes | Path` the current working directory for the command. Defaults to `Path('.')`.
* `log`: `bool` when True, prints the command before running.

## Examples

See [main.py](./main.py) for the example commands that were used to create this repository.