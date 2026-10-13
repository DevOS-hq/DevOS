"""Claude rewrites the sloppy sample with the DevOS `writing` skill.

Start: a folder holding draft.md, a copy of tests/e2e/samples/sloppy.md. The
sample is the update in samples/clean.md with its facts (numbers, owners,
dates) buried in every banned pattern, so a faithful rewrite can be specific.
Prompt: load the `writing` skill and rewrite draft.md into update.md.
Check: the transcript shows `writing` loaded from the plugin copy, draft.md is
unchanged, update.md keeps the draft's key facts, gets no banned.py hits and
passes the LLM judge.
"""

import os
import shutil

import asserts
import runners

CLIS = ("claude",)
START = "empty"
TIMEOUT = 600

DRAFT = "draft.md"
OUTPUT = "update.md"
SAMPLE = os.path.join(runners.PLUGIN_SRC, "tests", "e2e", "samples", "sloppy.md")

PROMPT = (
    "Load the DevOS `writing` skill and follow it. Then rewrite {draft} in this folder "
    "into a new file, {output}, for the same readers. Keep every fact from {draft} and "
    "add none. Leave {draft} unchanged."
).format(draft=DRAFT, output=OUTPUT)

# Facts the draft buries in slop; a faithful rewrite keeps each one. Regexes,
# matched case-insensitively.
FACTS = (r"61\s*%", r"66\s*%", r"Priya", r"webhook", r"fraud model")


def setup(repo, tmp):
    shutil.copyfile(SAMPLE, os.path.join(repo, DRAFT))


def check(run):
    asserts.writing_loaded(run)
    with open(SAMPLE, encoding="utf-8") as fh:
        if asserts.file_text(run, DRAFT) != fh.read():
            asserts.fail("{} changed; the rewrite must leave it as it was".format(DRAFT))
    for fact in FACTS:
        asserts.file_contains(run, OUTPUT, r"(?i)" + fact)
    asserts.banned_clean(run, [OUTPUT])
    asserts.judge_pass(run, OUTPUT)
