"""`add-action` appends one line at the bottom of `## To do`.

Start: the fixture as a state repo. checkout-revamp's `## To do` ends with
`- Add saved-card storage …` and its indented note. Prompt: add an action with
a name, project and priority. Check (AC8, AC12): one new commit holding only
that actions.md; the file is the old one with exactly one line inserted right
after the note `  - Waiting on the card vault contract.`, and that line,
the last item under `## To do`, is `- <name> · <priority> · added <commit
date>`; check.py passes; the tree is clean; writing loaded, FORMAT.md read,
check.py run. Runs on all three CLIs (the smoke test).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude", "codex", "cursor")
START = "state-repo"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `add-action` skill to add the action Load-test the payment API "
    "to the checkout-revamp project, priority P1."
)

ACTIONS = "projects/checkout-revamp/actions.md"
NOTE = "  - Waiting on the card vault contract."


def expected_line(run):
    return "- Load-test the payment API · P1 · added {}".format(common.commit_date(run))


def check_state(run):
    common.one_new_commit(run, {ACTIONS})
    line = expected_line(run)
    common.expect_last_item(run, ACTIONS, "## To do", line)
    old = common.old_text(run, ACTIONS).splitlines()
    if old.count(NOTE) != 1:
        asserts.fail("the fixture changed: {!r} is not in {} once".format(NOTE, ACTIONS))
    at = old.index(NOTE) + 1
    want = old[:at] + [line] + old[at:]
    found = asserts.file_text(run, ACTIONS).splitlines()
    if found != want:
        asserts.fail("{} should be the old file plus one line after {!r}.\nExpected:\n{}\nFound:\n{}".format(
            ACTIONS, NOTE, "\n".join(want), "\n".join(found)))
    added, deleted = common.numstat(run, ACTIONS)
    if (added, deleted) != (1, 0):
        asserts.fail("the diff adds {} and deletes {} lines; expected 1 and 0".format(added, deleted))
    common.clean_layout(run, ACTIONS)


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
