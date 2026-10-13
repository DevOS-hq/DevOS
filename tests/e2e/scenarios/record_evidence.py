"""`record-evidence` appends one dated evidence item to evidence.md.

Start: the fixture as a state repo. Prompt: record evidence for Checkout
Revamp with a name, an impact, the status `measured` and one link, all given.
Check (AC9, AC13): one new commit holding only checkout-revamp's evidence.md;
the diff deletes 0 lines; the last `##` item is the new one, with Date equal to
the commit date, Impact status `measured`, the given numbers in Impact and the
link in References; check.py passes; the tree is clean; the commit subject
follows writing; writing loaded, FORMAT.md read, check.py run.
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

NAME = "Checkout errors fell after the retry fix"
IMPACT = "Checkout errors fell from 2.1% to 0.4% in the week after the retry fix."
LINK = "https://example.com/dashboards/checkout-errors"

PROMPT = (
    "Use the DevOS `record-evidence` skill to record evidence for the Checkout Revamp project. "
    "Name: {name}. Impact: {impact} Impact status: measured. Reference: {link}"
).format(name=NAME, impact=IMPACT, link=LINK)

EVIDENCE = "projects/checkout-revamp/evidence.md"


def _plain(text):
    return text.strip().rstrip(".").casefold()


def check_state(run):
    common.one_new_commit(run, {EVIDENCE})
    added, deleted = common.numstat(run, EVIDENCE)
    if deleted:
        asserts.fail("the diff deletes {} lines of {}; expected 0".format(deleted, EVIDENCE))
    text = asserts.file_text(run, EVIDENCE)
    found = report.evidence_items(text)
    if not found or _plain(found[-1][0]) != _plain(NAME):
        asserts.fail("the last ## item in {} is {!r}, expected {!r}:\n{}".format(
            EVIDENCE, found[-1][0] if found else None, NAME, text))
    lines = found[-1][1]
    date = common.commit_date(run)
    value = report.field(lines, "Date")
    if value != date:
        asserts.fail("the new item's Date is {!r}, expected {!r} (the commit date)".format(value, date))
    value = report.field(lines, "Impact status")
    if value != "measured":
        asserts.fail("the new item's Impact status is {!r}, expected 'measured'".format(value))
    value = report.field(lines, "Impact") or ""
    if "2.1%" not in value or "0.4%" not in value:
        asserts.fail("the new item's Impact {!r} drops the given numbers 2.1% and 0.4%".format(value))
    value = report.field(lines, "References") or ""
    if LINK not in value:
        asserts.fail("the new item's References {!r} lacks the link {}".format(value, LINK))


def check(run):
    check_state(run)
    common.loaded_and_checked(run)
