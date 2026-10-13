"""`create-project` writes project.md and an empty actions.md, commits and pushes.

Start: the fixture as a state repo, with a bare repo next to it (setup) as
`origin` and `main` pushed to it. Prompt: create a project with a name,
priority, stakeholders and one requirement. Check (AC6, AC12): one new commit
holding exactly the project's project.md and actions.md; project.md holds the
title, fields and the requirement; actions.md is the empty scaffold; check.py
passes; the tree is clean; banned.py passes on project.md; the remote's `main`
equals local HEAD; writing loaded, FORMAT.md read, check.py run.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _statecheck as common  # noqa: E402
import asserts  # noqa: E402
import runners  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `create-project` skill to create a project named Billing Alerts, "
    "priority P2, stakeholders Finance team and Support team. "
    "Give it one requirement, Overdue invoice email: a need, stakeholders Finance team, "
    "description: Customers get an email when an invoice is three days overdue."
)

SLUG = "billing-alerts"
PROJECT = "projects/{}/project.md".format(SLUG)
ACTIONS = "projects/{}/actions.md".format(SLUG)


def setup(repo, tmp):
    remote = os.path.join(tmp, "remote.git")
    runners.git(tmp, "init", "-q", "--bare", "-b", "main", remote)
    runners.git(repo, "remote", "add", "origin", remote)
    runners.git(repo, "push", "-q", "-u", "origin", "main")
    return {"remote": remote}


def check_state(run):
    common.one_new_commit(run, {PROJECT, ACTIONS})
    text = asserts.file_text(run, PROJECT)
    asserts.file_contains(run, PROJECT, r"\A# Billing Alerts[ \t]*\n")
    asserts.file_contains(run, PROJECT, r"^# ", count=1)
    top = common.fields_under_title(text)
    if common.field(top, "Priority") != "P2":
        asserts.fail("Priority is {!r}, expected P2".format(common.field(top, "Priority")))
    stakeholders = (common.field(top, "Stakeholders") or "").lower()
    for name in ("finance team", "support team"):
        if name not in stakeholders:
            asserts.fail("project Stakeholders {!r} lack {!r}".format(stakeholders, name))
    common.expect_requirement(
        text, "Overdue invoice email", "need", ["Finance team"],
        [r"\bemail\b", r"\boverdue\b", r"\binvoice\b"],
    )
    common.expect_nonblank(run, ACTIONS, common.scaffold_lines())
    common.clean_layout(run, ACTIONS)
    asserts.banned_clean(run, [PROJECT])
    url = run.subs["remote"]
    local = asserts.head(run)
    try:
        pushed = runners.git(url, "rev-parse", "--verify", "-q", "refs/heads/main", env=run.env).strip()
    except subprocess.CalledProcessError:
        asserts.fail("the remote at {} has no main branch".format(url))
    if pushed != local:
        asserts.fail("the remote's main is {}, local HEAD is {}; the push never landed".format(pushed, local))


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
