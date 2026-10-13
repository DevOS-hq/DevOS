"""`write-status-report` drafts Checkout Revamp's report since its last one.

Start: the fixture as a state repo. checkout-revamp's last status report is
2026-10-09. Prompt: write a status report for Checkout Revamp, no frame.
Check (AC10, AC13, D13, D14): one new commit holding only
`projects/checkout-revamp/status-reports/<commit date>.md`; Share date is the
commit date and Time frame `2026-10-09 to <commit date>`; every status IN
marker in `## Done` and none in `## Pending`; every open-action marker in
`## Pending` and none in `## Done`; no OUT marker anywhere; check.py passes;
the tree is clean; the commit subject follows writing. Every CLI: writing
loaded, FORMAT.md read, check.py and window.py run. Claude only: the judge
passes the report (best of two). Runs on all three CLIs (the smoke test).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _reportcheck as report  # noqa: E402
import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude", "codex", "cursor")
START = "state-repo"
TIMEOUT = 900
PROMPT = "Use the DevOS `write-status-report` skill to write a status report for the Checkout Revamp project."


def report_rel(run):
    return report.status_rel(common.commit_date(run))


def check_state(run):
    date = common.commit_date(run)
    rel = report.status_rel(date)
    common.one_new_commit(run, {rel})
    report.status_report(asserts.file_text(run, rel), report.STATUS_PREVIOUS, date)


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
    report.window_ran(run)
    if run.cli == "claude":
        asserts.judge_pass(run, report_rel(run), tries=2)
