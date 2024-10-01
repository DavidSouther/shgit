#!/usr/bin/env python3

from shgit import git

if __name__ == "__main__":
    git.check = False
    git.log = True
    git.status()
    # out = git.init(capture_output=True)
    # print(out)
    # git.log("-h")
    git.add(".")
    # git.commit(message="Sh util that uses __getattr__ to choose a bin and **kwargs for flags")
    # git.commit('--amend', message="Sh util that uses __getattr__ to choose a bin and **kwargs for flags")
    git.commit(message="Allow nested arg calls, like git.remote.add.origin(url)")
    git.remote('-v')
    # git.remote.add.origin("git@github.com:DavidSouther/shgit.git")
    # git.push("-u", "origin", "main")
    git.push()
