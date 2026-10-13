"""Probe: does each CLI apply the state repo's AGENTS.md in a headless run?

A recorded finding, not a gate. Start: the fixture state repo, with AGENTS.md
replaced by one sentinel rule and CLAUDE.md importing it (`@AGENTS.md`), as
`init` writes it. Prompt: an arithmetic question that needs no file. The
check never fails on the outcome. It prints one line per CLI,

    PROBE agents_md_probe [<cli>]: followed=yes|no read_agents_md=yes|no reply=<tail>

and writes the same line to probe.txt in the run folder (kept with --keep).
`followed` says whether the reply holds the sentinel word. `read_agents_md`
says whether a tool call read AGENTS.md, which tells a CLI that loaded the
file on its own from a model that went looking for it.
"""

import os
import re
import sys

import asserts
import runners

CLIS = ("claude", "codex", "cursor")
START = "state-repo"
TIMEOUT = 300

SENTINEL = "PERSIMMON"
AGENTS = (
    "# Rules for agents\n\n"
    "End every reply with the word {} on a line of its own.\n".format(SENTINEL)
)
PROMPT = "What is 7 times 6? Answer in one short sentence."


def setup(repo, tmp):
    with open(os.path.join(repo, "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write(AGENTS)
    with open(os.path.join(repo, "CLAUDE.md"), "w", encoding="utf-8") as fh:
        fh.write("@AGENTS.md\n")
    runners.git(repo, "add", "AGENTS.md", "CLAUDE.md")
    runners.git(repo, "commit", "-q", "-m", "Plant the AGENTS.md probe rule")
    return None


def outcome(run):
    followed = bool(re.search(r"\b{}\b".format(SENTINEL), run.text or "", re.I))
    read = run.transcript.was_read(asserts.path(run, "AGENTS.md"))
    tail = " ".join((run.text or "").split())[-80:]
    return "PROBE agents_md_probe [{}]: followed={} read_agents_md={} reply={!r}".format(
        run.cli, "yes" if followed else "no", "yes" if read else "no", tail)


def check(run):
    line = outcome(run)
    print(line)
    sys.stdout.flush()
    try:
        with open(os.path.join(run.run_root, "probe.txt"), "w", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
