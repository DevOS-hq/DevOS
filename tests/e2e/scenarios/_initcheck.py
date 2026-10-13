"""Shared prompt and checks for the init scenarios.

run.py skips this module (its name starts with "_"). Each init scenario
imports it after putting this folder on sys.path.
"""

import re

import asserts

PROMPT = "Use the DevOS `init` skill to set up a DevOS state repo in this folder."

# Every file init adds to an empty folder, and the only files its commit may hold.
FILES = {".devos", "AGENTS.md", "CLAUDE.md", "projects/.gitkeep", "progress-reports/.gitkeep"}

# The points AGENTS.md must make. Each regex runs on AGENTS.md with wrapped
# lines joined, so one bullet or paragraph is one line.
AGENTS_POINTS = (
    ("calls the folder a DevOS state repo", r"(?i)\bDevOS state repo\b"),
    ("says to change records through the DevOS skills",
     r"(?im)^(?=.*\brecords?\b)(?=.*\bDevOS skills\b).*$"),
    ("says to load `writing` before any prose, commit messages included",
     r"(?im)^(?=.*\bwriting\b)(?=.*\bbefore\b)(?=.*\bcommit messages?\b).*$"),
    ("says to keep FORMAT.md's format on hand edits",
     r"(?im)^(?=.*\bhand\b)(?=.*FORMAT\.md).*$"),
    ("says FORMAT.md sits in the DevOS plugin folder, next to skills/",
     r"(?im)^(?=.*FORMAT\.md)(?=.*\bplugin\b)(?=.*\bskills/).*$"),
    ("says to commit after a hand edit",
     r"(?im)^(?=.*\bcommit\b)(?=.*\bafterwards?\b).*$"),
)

DEVOS_HEADING = r"(?m)^## DevOS[ \t]*$"
CLAUDE_IMPORT = r"(?m)^@AGENTS\.md[ \t]*$"


def unwrapped(text):
    """Join wrapped lines, so each paragraph or list item is one line."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        starts_block = (
            not stripped
            or stripped.startswith(("- ", "* ", "+ ", "#", "```"))
            or re.match(r"^\d+\. ", stripped)
        )
        if out and out[-1].strip() and not starts_block:
            out[-1] = out[-1].rstrip() + " " + stripped
        else:
            out.append(line)
    return "\n".join(out)


def agents_md_points(run):
    text = unwrapped(asserts.file_text(run, "AGENTS.md"))
    missing = [label for label, pattern in AGENTS_POINTS if not re.search(pattern, text)]
    if missing:
        asserts.fail("AGENTS.md never {}. AGENTS.md:\n{}".format("; never ".join(missing), text))


def devos_section_once(run):
    asserts.file_contains(run, "AGENTS.md", DEVOS_HEADING, count=1)
    asserts.file_contains(run, "CLAUDE.md", CLAUDE_IMPORT, count=1)


def subject_follows_writing(run):
    """The commit subject is short and has no closing period (writing's commit rules)."""
    subject = asserts.commit_message(run).splitlines()[0].strip()
    if len(subject) >= 72 or subject.endswith("."):
        asserts.fail("commit subject breaks the writing rules: {!r}".format(subject))


def loaded_and_checked(run):
    """The transcript shows writing loaded, FORMAT.md read and check.py run from the loaded copy."""
    asserts.writing_loaded(run)
    asserts.read_format(run)
    asserts.check_ran(run)


def fresh_commit(run, branch="main"):
    """One commit on `branch` holding exactly FILES, a clean tree and a clean check."""
    if asserts.branch(run) != branch:
        asserts.fail("expected branch {}, found {}".format(branch, asserts.branch(run)))
    if asserts.commit_count(run) != 1:
        asserts.fail("expected 1 commit, found {}: {}".format(
            asserts.commit_count(run), asserts.commit_messages(run)))
    files = asserts.commit_files(run)
    if files != FILES:
        asserts.fail("the commit holds {}, expected {}".format(sorted(files), sorted(FILES)))
    if asserts.status(run):
        asserts.fail("git status is not clean: {}".format(asserts.status(run)))
    asserts.check_exit(run, 0)
    asserts.file_contains(run, "CLAUDE.md", CLAUDE_IMPORT, count=1)
    subject_follows_writing(run)
