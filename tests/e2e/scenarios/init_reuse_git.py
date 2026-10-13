"""`init` in an existing git repo reuses it and commits only its own files.

Start (setup): a git repo on the branch `notes` with one commit that holds
the user's README.md, AGENTS.md and CLAUDE.md, each with the user's text.
On top of that commit, a change to README.md is staged and scratch.txt is
untracked. Prompt: use the DevOS `init` skill here.
Check: exactly one new commit on `notes`, holding exactly the files init added
or changed; the README.md change still staged and out of the commit;
scratch.txt still untracked; the user's text kept at the top of AGENTS.md and
CLAUDE.md; `## DevOS` and `@AGENTS.md` each once; check.py exits 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _initcheck as common  # noqa: E402
import asserts  # noqa: E402
import runners  # noqa: E402

CLIS = ("claude",)
START = "empty"
TIMEOUT = 900
PROMPT = common.PROMPT

BRANCH = "notes"
USER_AGENTS = "# Team notes\n\nRun the linter before you push.\n"
USER_CLAUDE = "# Claude notes\n\nKeep answers short.\n"
README_V1 = "# Notes\n\nMeeting notes and drafts.\n"
README_V2 = README_V1 + "\nDraft for Friday.\n"
SCRATCH = "half an idea\n"


def _write(repo, rel, text):
    with open(os.path.join(repo, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def setup(repo, tmp):
    runners.git(repo, "init", "-q", "-b", BRANCH)
    _write(repo, "README.md", README_V1)
    _write(repo, "AGENTS.md", USER_AGENTS)
    _write(repo, "CLAUDE.md", USER_CLAUDE)
    runners.git(repo, "add", "README.md", "AGENTS.md", "CLAUDE.md")
    runners.git(repo, "commit", "-q", "-m", "Start notes")
    _write(repo, "README.md", README_V2)
    runners.git(repo, "add", "README.md")
    _write(repo, "scratch.txt", SCRATCH)
    return {"head": runners.git(repo, "rev-parse", "HEAD").strip()}


def check(run):
    if asserts.branch(run) != BRANCH:
        asserts.fail("expected branch {}, found {}".format(BRANCH, asserts.branch(run)))
    if asserts.commit_count(run) != 2:
        asserts.fail("expected 2 commits (the user's and init's), found {}: {}".format(
            asserts.commit_count(run), asserts.commit_messages(run)))
    if asserts.git(run, "rev-parse", "HEAD~1") != run.subs["head"]:
        asserts.fail("init's commit does not sit on the user's commit")
    files = asserts.commit_files(run)
    if files != common.FILES:
        asserts.fail("init's commit holds {}, expected {}".format(sorted(files), sorted(common.FILES)))
    if asserts.staged(run) != ["README.md"]:
        asserts.fail("expected only README.md staged, found {}".format(asserts.staged(run)))
    if asserts.git(run, "show", ":README.md") + "\n" != README_V2:
        asserts.fail("the staged README.md lost the user's change")
    if asserts.git(run, "show", "HEAD:README.md") + "\n" != README_V1:
        asserts.fail("init's commit took in the user's staged README.md change")
    if asserts.untracked(run) != ["scratch.txt"]:
        asserts.fail("expected only scratch.txt untracked, found {}".format(asserts.untracked(run)))
    if asserts.file_text(run, "scratch.txt") != SCRATCH:
        asserts.fail("scratch.txt changed")
    if sorted(asserts.status(run)) != ["?? scratch.txt", "M  README.md"]:
        asserts.fail("git status shows more than the user's own changes: {}".format(asserts.status(run)))
    for rel, text in (("AGENTS.md", USER_AGENTS), ("CLAUDE.md", USER_CLAUDE)):
        if not asserts.file_text(run, rel).startswith(text):
            asserts.fail("{} no longer starts with the user's text:\n{}".format(rel, asserts.file_text(run, rel)))
    common.devos_section_once(run)
    common.agents_md_points(run)
    asserts.check_exit(run, 0)
    common.subject_follows_writing(run)
    if asserts.remotes(run):
        asserts.fail("expected no remote, found {}".format(asserts.remotes(run)))
