"""Shared checks for the evidence and report scenarios (phase 04).

run.py skips this module (its name starts with "_"). Each scenario imports it
after putting this folder on sys.path. Every check raises AssertionError
through asserts.fail.

Report items are paraphrased by the model, so the checks match marker regexes
(case-insensitive) scoped by section, never exact lines (spec D12, D13). The
markers are the plan's table, verbatim:

- Status report, checkout-revamp, frame `2026-10-09 to <commit date>`:
  every IN marker in `## Done` and none in `## Pending`; every open-action
  marker in `## Pending` and none in `## Done`; no OUT marker anywhere.
- Progress report, frame `2026-10-01 to 2026-10-08`: `##` sections exactly
  Checkout Revamp and Search Latency; each with an Impact summary and a
  non-empty `### Progress`; every IN marker in its project's section; no OUT
  marker anywhere.

The pure functions take report text and dates, so they run offline on
hand-made outcomes as well as on a live run's file.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _statecheck  # noqa: E402
import asserts  # noqa: E402

section = _statecheck.section
field = _statecheck.field
fields_under_title = _statecheck.fields_under_title
items = _statecheck.items

# --- markers (plan "Markers" table) ---------------------------------------------

STATUS_PROJECT = "checkout-revamp"
STATUS_TITLE = "# Status report: Checkout Revamp"
# The previous status report's date: the default frame's start (D14).
STATUS_PREVIOUS = "2026-10-09"
STATUS_IN = (r"fraud", r"beta")
STATUS_OPEN = (r"payment form", r"rollout plan", r"refund", r"saved.card", r"vault")
STATUS_OUT = (r"scope", r"flow map|mapped", r"support", r"usability|prototype|9 of 10")

PROGRESS_TITLE = "# Progress report"
PROGRESS_START = "2026-10-01"
PROGRESS_END = "2026-10-08"
PROGRESS_IN = {
    "Checkout Revamp": (r"scope", r"usability|prototype|9 of 10"),
    "Search Latency": (r"p95|820|310",),
}
PROGRESS_OUT = (
    r"flow map|mapped", r"support", r"fraud", r"beta", r"region", r"csv|spreadsheet", r"nightly",
)
PROGRESS_SECTIONS = ("Checkout Revamp", "Search Latency")


# --- pure text helpers ----------------------------------------------------------


def hits(pattern, text):
    return re.search(pattern, text, re.I) is not None


def level2_headings(text):
    """Names of the `## ` headings, in file order."""
    return [line[3:].strip() for line in text.splitlines()
            if _statecheck.heading_level(line) == 2]


def header_fields(text, title, share, frame):
    """The title line, then Share date == `share` and Time frame == `frame`."""
    first = text.splitlines()[0].rstrip() if text.strip() else ""
    if first != title:
        asserts.fail("the report's title is {!r}, expected {!r}".format(first, title))
    lines = fields_under_title(text)
    found = field(lines, "Share date")
    if found != share:
        asserts.fail("the Share date is {!r}, expected {!r} (the commit date)".format(found, share))
    found = field(lines, "Time frame")
    if found != frame:
        asserts.fail("the Time frame is {!r}, expected {!r}".format(found, frame))


def no_out_markers(text, out):
    found = [p for p in out if hits(p, text)]
    if found:
        asserts.fail("the report carries out-of-frame items (OUT markers {}):\n{}".format(found, text))


def status_report(text, start, end):
    """D13 and D14 on a status report's text. `end` is the commit date."""
    header_fields(text, STATUS_TITLE, end, "{} to {}".format(start, end))
    done = "\n".join(section(text, "## Done"))
    pending = "\n".join(section(text, "## Pending"))
    missing = [p for p in STATUS_IN if not hits(p, done)]
    if missing:
        asserts.fail("## Done lacks in-frame items (IN markers {}):\n{}".format(missing, text))
    wrong = [p for p in STATUS_IN if hits(p, pending)]
    if wrong:
        asserts.fail("## Pending lists done items (IN markers {}):\n{}".format(wrong, text))
    missing = [p for p in STATUS_OPEN if not hits(p, pending)]
    if missing:
        asserts.fail("## Pending lacks open actions (open markers {}):\n{}".format(missing, text))
    wrong = [p for p in STATUS_OPEN if hits(p, done)]
    if wrong:
        asserts.fail("## Done lists open actions (open markers {}):\n{}".format(wrong, text))
    no_out_markers(text, STATUS_OUT)


def project_block(text, name):
    """(lines before `### Progress`, the `### Progress` lines) of `## <name>`."""
    lines = section(text, "## " + name)
    at = [i for i, line in enumerate(lines) if line.rstrip() == "### Progress"]
    if len(at) != 1:
        asserts.fail("## {} holds `### Progress` {} times, expected once:\n{}".format(
            name, len(at), text))
    head = lines[:at[0]]
    progress = []
    for line in lines[at[0] + 1:]:
        if _statecheck.heading_level(line):
            break
        progress.append(line)
    return head, progress


def progress_report(text, share):
    """AC12 on a progress report's text. `share` is the commit date."""
    header_fields(text, PROGRESS_TITLE, share, "{} to {}".format(PROGRESS_START, PROGRESS_END))
    found = level2_headings(text)
    if sorted(found) != sorted(PROGRESS_SECTIONS):
        asserts.fail("the project sections are {}, expected exactly {}:\n{}".format(
            found, list(PROGRESS_SECTIONS), text))
    for name in PROGRESS_SECTIONS:
        head, progress = project_block(text, name)
        if not (field(head, "Impact summary") or "").strip():
            asserts.fail("## {} has no Impact summary:\n{}".format(name, text))
        listed = [line for line in items(progress) if line.strip().lower() not in ("- none", "- none.")]
        if not listed:
            asserts.fail("## {} has an empty ### Progress:\n{}".format(name, text))
        body = "\n".join(head + progress)
        missing = [p for p in PROGRESS_IN[name] if not hits(p, body)]
        if missing:
            asserts.fail("## {} lacks in-frame items (IN markers {}):\n{}".format(name, missing, text))
    no_out_markers(text, PROGRESS_OUT)


def evidence_items(text):
    """[(heading, lines)] for each `##` item of an evidence file, in order."""
    out = []
    for line in text.splitlines():
        if _statecheck.heading_level(line) == 2:
            out.append((line[3:].strip(), []))
        elif out:
            out[-1][1].append(line)
    return out


# --- run checks -----------------------------------------------------------------


def status_rel(date, project=STATUS_PROJECT):
    return "projects/{}/status-reports/{}.md".format(project, date)


def progress_rel(date):
    return "progress-reports/{}.md".format(date)


def window_ran(run):
    """AC13: the transcript shows the loaded copy's scripts/window.py executed."""
    target = run.plugin_path("scripts/window.py")
    if not run.transcript.ran(target):
        asserts.fail("{} never ran {}. Transcript:\n{}".format(run.cli, target, run.transcript.describe()))
