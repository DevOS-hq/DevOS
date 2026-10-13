"""`write-status-report` asks for a start date when there is no earlier report.

Start: the fixture as a state repo; search-latency has no status report.
Prompt: write a status report for Search Latency, no frame, one turn.
Check (AC11): turn 1 changed nothing (HEAD and status as before), and its
reply asks for a start date or a time frame.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asserts  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
PROMPT = "Use the DevOS `write-status-report` skill to write a status report for the Search Latency project."

ASKS_FOR_START = re.compile(
    r"start(ing)?\s+date|time\s*-?\s*frame|\bframe\b|date\s+range|"
    r"(which|what)\s+date|since\s+when|from\s+when|when\s+should\s+(it|the\s+report)\s+start",
    re.I,
)


def check_state(run):
    if len(run.turns) != 1:
        asserts.fail("expected 1 turn, found {}".format(len(run.turns)))
    asserts.turn_unchanged(run, 1)
    reply = run.turns[0].text or ""
    if not ASKS_FOR_START.search(reply):
        asserts.fail("turn 1's reply never asks for a start date or time frame: {!r}".format(reply))


def check(run):
    check_state(run)
