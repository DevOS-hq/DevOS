"""An action skill outside a state repo changes nothing and points to `init`.

Start: an empty folder. Prompt: use `add-action` to add an action. Check
(AC11): no `.git`, `.devos`, `projects/` or any `actions.md` appears, and the
reply names `init`.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asserts  # noqa: E402

CLIS = ("claude",)
START = "empty"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `add-action` skill to add the action Write the launch email "
    "to the checkout-revamp project, priority P2."
)


def check_state(run):
    for rel in (".git", ".devos", "projects"):
        asserts.file_missing(run, rel)
    made = [rel for rel in asserts.tree(run) if rel.split("/")[-1] == "actions.md"]
    if made:
        asserts.fail("the skill wrote {} outside a state repo".format(made))
    # "git init" is not the DevOS skill.
    if not re.search(r"(?<!git )\binit\b", run.text or ""):
        asserts.fail("the reply never names the `init` skill: {!r}".format(run.text))


def check(run):
    check_state(run)
