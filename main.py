from shgit import git
from pathlib import Path

if __name__ == "__main__":
    git.check = False
    git.log = True
    git.status()
    # out = git.init(capture_output=True)
    # print(out)
    # git.log("-h")
    git.add(".")
    # git.commit(message="Sh util that uses __getattr__ to choose a bin and **kwargs for flags")
    git.commit('--amend', message="Sh util that uses __getattr__ to choose a bin and **kwargs for flags")
