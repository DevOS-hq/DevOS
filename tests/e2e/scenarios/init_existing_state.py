"""`init` in a folder that is already a state repo changes nothing.

Start: the fixture state repo, committed on `main`. Prompt: use the DevOS
`init` skill here. Check: HEAD, the file tree and `git status` are as they
were, and no remote was added.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _initcheck as common  # noqa: E402
import asserts  # noqa: E402
import runners  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 600
PROMPT = common.PROMPT


def _tree(root):
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            out.append(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
    return sorted(out)


def setup(repo, tmp):
    return {"head": runners.git(repo, "rev-parse", "HEAD").strip(), "tree": "\n".join(_tree(repo))}


def check(run):
    if asserts.head(run) != run.subs["head"]:
        asserts.fail("HEAD moved from {} to {}: {}".format(
            run.subs["head"], asserts.head(run), asserts.commit_messages(run)))
    if asserts.branch(run) != "main":
        asserts.fail("the branch changed to {}".format(asserts.branch(run)))
    if asserts.status(run):
        asserts.fail("git status is not clean: {}".format(asserts.status(run)))
    if "\n".join(asserts.tree(run)) != run.subs["tree"]:
        asserts.fail("the file tree changed:\nbefore: {}\nafter:  {}".format(
            run.subs["tree"].split("\n"), asserts.tree(run)))
    if asserts.remotes(run):
        asserts.fail("expected no remote, found {}".format(asserts.remotes(run)))
