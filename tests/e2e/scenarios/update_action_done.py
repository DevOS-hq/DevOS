"""`update-action` moves an action to `## Done` and stamps the done date.

Start: the fixture as a state repo; checkout-revamp's only in-progress action
is `Build the guest payment form · P0 · added 2026-09-28`. Prompt: mark it
done. Check (AC10, AC12): one new commit holding only that actions.md;
`## In progress` is empty; the last item under `## Done` is the line plus
` · done <commit date>`; counting non-blank lines, the diff deletes only the
old line and adds only the new one; no two blank lines in a row; check.py
passes; writing loaded, FORMAT.md read, check.py run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `update-action` skill to mark the action Build the guest payment form "
    "in the checkout-revamp project as done."
)

ACTIONS = "projects/checkout-revamp/actions.md"
OLD = "- Build the guest payment form · P0 · added 2026-09-28"


def check_state(run):
    common.one_new_commit(run, {ACTIONS})
    if OLD not in common.old_text(run, ACTIONS).splitlines():
        asserts.fail("the fixture changed: {!r} is not in {}".format(OLD, ACTIONS))
    new = "{} · done {}".format(OLD, common.commit_date(run))
    left = common.items(common.section(asserts.file_text(run, ACTIONS), "## In progress"))
    if left:
        asserts.fail("## In progress still holds {}".format(left))
    common.expect_last_item(run, ACTIONS, "## Done", new)
    added, deleted = common.changes(run, ACTIONS)
    added = [line.rstrip() for line in added if line.strip()]
    deleted = [line.rstrip() for line in deleted if line.strip()]
    if (added, deleted) != ([new], [OLD]):
        asserts.fail("non-blank diff lines: added {}, deleted {}; expected added [{!r}], deleted [{!r}]".format(
            added, deleted, new, OLD))
    common.clean_layout(run, ACTIONS)


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
