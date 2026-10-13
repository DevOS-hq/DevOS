"""`init` with a remote URL pushes the first commit to it.

Start: an empty folder, plus a bare git repo next to it (setup) whose path is
the URL. Prompt: use the DevOS `init` skill here, with that URL as the remote.
Check: the state repo as in init_empty, `origin` set to the URL, the bare
repo's `main` equal to the local HEAD, and `main` tracking `origin/main`.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _initcheck as common  # noqa: E402
import asserts  # noqa: E402
import runners  # noqa: E402

CLIS = ("claude",)
START = "empty"
TIMEOUT = 900
PROMPT = common.PROMPT[:-1] + ", with {remote} as its remote."


def setup(repo, tmp):
    remote = os.path.join(tmp, "remote.git")
    runners.git(tmp, "init", "-q", "--bare", "-b", "main", remote)
    return {"remote": remote}


def check(run):
    url = run.subs["remote"]
    common.fresh_commit(run, "main")
    if asserts.remotes(run) != {"origin": url}:
        asserts.fail("expected origin = {}, found {}".format(url, asserts.remotes(run)))
    local = asserts.head(run)
    try:
        pushed = runners.git(url, "rev-parse", "--verify", "-q", "refs/heads/main", env=run.env).strip()
    except subprocess.CalledProcessError:
        asserts.fail("the remote at {} has no main branch; the push never landed".format(url))
    if pushed != local:
        asserts.fail("the remote's main is {}, local HEAD is {}".format(pushed, local))
    upstream = run.git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    if upstream != "origin/main":
        asserts.fail("main tracks {!r}, expected origin/main".format(upstream))
    common.agents_md_points(run)
    common.loaded_and_checked(run)
