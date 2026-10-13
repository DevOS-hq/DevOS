"""`add-action` asks for a missing priority before it writes anything.

Start: the fixture as a state repo; search-latency has no actions.md. Turn 1
names an action for search-latency with no priority; the scripted answer gives
P1. Check (AC9, AC12): turn 1 changed nothing (HEAD and status as before) and
its reply mentions priority; then one new commit holding only
search-latency's actions.md, which is the scaffold with the action under
`## To do` at P1 and the commit date; check.py passes; the tree is clean;
writing loaded, FORMAT.md read, check.py run.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `add-action` skill to add the action Profile the slow search queries "
    "to the search-latency project."
)
ANSWERS = ("P1",)

ACTIONS = "projects/search-latency/actions.md"


def check_state(run):
    if len(run.turns) != 1 + len(ANSWERS):
        asserts.fail("expected {} turns, found {}".format(1 + len(ANSWERS), len(run.turns)))
    asserts.turn_unchanged(run, 1)
    first = run.turns[0].text or ""
    if not re.search(r"(?i)\bpriorit", first):
        asserts.fail("turn 1's reply never asks for the priority: {!r}".format(first))
    common.one_new_commit(run, {ACTIONS})
    line = "- Profile the slow search queries · P1 · added {}".format(common.commit_date(run))
    common.expect_nonblank(run, ACTIONS, common.scaffold_lines(line))
    common.clean_layout(run, ACTIONS)


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
