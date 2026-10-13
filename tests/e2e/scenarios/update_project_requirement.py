"""`update-project` adds a requirement in place, changing no other line.

Start: the fixture as a state repo. checkout-revamp's project.md has the
requirements Guest checkout and Saved cards, then `## Notes`. Prompt: add a
requirement to checkout-revamp. Check (AC7, AC12): one new commit holding only
that project.md; the diff deletes no line; the new `###` block sits inside
`## Requirements`, after the Saved cards block and before `## Notes`, with the
given type, stakeholders and description; check.py passes; writing loaded,
FORMAT.md read, check.py run.
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
    "Use the DevOS `update-project` skill to add a requirement to the checkout-revamp "
    "project: Order tracking, a want, stakeholders Support team, "
    "description: Shoppers can see where their order is from the confirmation email."
)

PROJECT = "projects/checkout-revamp/project.md"
NAME = "Order tracking"
# The last line of the Saved cards block in the fixture.
SAVED_CARDS_END = "- **Description:** Returning shoppers can pay with a card saved on an earlier order."


def check_state(run):
    common.one_new_commit(run, {PROJECT})
    added, deleted = common.numstat(run, PROJECT)
    if deleted or not added:
        asserts.fail("the commit adds {} and deletes {} lines of {}; expected additions only".format(
            added, deleted, PROJECT))
    old = common.old_text(run, PROJECT).splitlines()
    if old.count(SAVED_CARDS_END) != 1:
        asserts.fail("the fixture changed: {!r} is not in {} once".format(SAVED_CARDS_END, PROJECT))
    text = asserts.file_text(run, PROJECT)
    lines = [line.rstrip() for line in text.splitlines()]
    new = [i for i, line in enumerate(lines) if line == "### " + NAME]
    if len(new) != 1:
        asserts.fail("expected `### {}` once in {}:\n{}".format(NAME, PROJECT, text))
    requirements = lines.index("## Requirements")
    saved_end = lines.index(SAVED_CARDS_END)
    notes = lines.index("## Notes")
    if not requirements < saved_end < new[0] < notes:
        asserts.fail("`### {}` is at line {}; expected after the Saved cards block (line {}) "
                     "and before ## Notes (line {}):\n{}".format(
                         NAME, new[0] + 1, saved_end + 1, notes + 1, text))
    common.expect_requirement(
        text, NAME, "want", ["Support team"], [r"\border\b", r"\bemail\b"],
    )


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
