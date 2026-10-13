"""`write-progress-report` drafts a cross-project report for a given frame.

Start: the fixture as a state repo. Prompt: write a progress report for
2026-10-01 to 2026-10-08. Check (AC12, AC13): one new commit holding only
`progress-reports/<commit date>.md`; Share date is the commit date and Time
frame `2026-10-01 to 2026-10-08`; the `##` sections are exactly Checkout
Revamp and Search Latency (no Invoice Export); each has an Impact summary and
a non-empty `### Progress`; every progress IN marker sits in its project's
section; no OUT marker anywhere; check.py passes; the tree is clean; the
commit subject follows writing; writing loaded, FORMAT.md read, check.py and
window.py run; the judge passes the report (best of two).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _reportcheck as report  # noqa: E402
import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
PROMPT = (
    "Use the DevOS `write-progress-report` skill to write a progress report for the time frame "
    "{} to {}.".format(report.PROGRESS_START, report.PROGRESS_END)
)


def report_rel(run):
    return report.progress_rel(common.commit_date(run))


def check_state(run):
    date = common.commit_date(run)
    rel = report.progress_rel(date)
    common.one_new_commit(run, {rel})
    report.progress_report(asserts.file_text(run, rel), date)


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
    report.window_ran(run)
    asserts.judge_pass(run, report_rel(run), tries=2)
