"""`init` turns an empty folder into a state repo, on all three CLIs.

Start: an empty folder. Prompt: use the DevOS `init` skill here.
Check: a git repo on `main` holding exactly .devos, AGENTS.md, CLAUDE.md,
projects/.gitkeep and progress-reports/.gitkeep, in one commit that holds
exactly those files; a clean `git status`; check.py exits 0; no remote.
AGENTS.md makes every point the state repo needs, and CLAUDE.md imports it.
The transcript shows the loaded copy's `writing` skill used, its FORMAT.md
read and its scripts/check.py run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _initcheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude", "codex", "cursor")
START = "empty"
TIMEOUT = 900
PROMPT = common.PROMPT


def check(run):
    common.fresh_commit(run, "main")
    if set(asserts.tree(run)) != common.FILES:
        asserts.fail("the folder holds {}, expected {}".format(asserts.tree(run), sorted(common.FILES)))
    if asserts.remotes(run):
        asserts.fail("expected no remote, found {}".format(asserts.remotes(run)))
    common.agents_md_points(run)
    common.loaded_and_checked(run)
