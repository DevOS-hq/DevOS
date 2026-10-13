"""Shared checks for the project and action scenarios.

run.py skips this module (its name starts with "_"). Each scenario imports it
after putting this folder on sys.path. Every check raises AssertionError
through asserts.fail.

The `state-repo` start is the fixture committed once on `main`, so a skill run
that works adds exactly one commit on top: `commit_count == 2`, and HEAD~1 is
the fixture as it started.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _initcheck  # noqa: E402
import asserts  # noqa: E402

# The fixture's commit plus the one the skill makes.
EXPECTED_COMMITS = 2

# AC12: writing loaded, FORMAT.md read, check.py run; and the commit subject rule.
loaded_and_checked = _initcheck.loaded_and_checked
subject_follows_writing = _initcheck.subject_follows_writing


# --- pure text helpers ----------------------------------------------------------


def heading_level(line):
    """The level of a markdown heading line (`## To do` is 2), or 0."""
    match = re.match(r"^(#{1,6})[ \t]+\S", line)
    return len(match.group(1)) if match else 0


def section(text, heading):
    """Lines under `heading` (a full heading line such as "## To do"), up to the
    next heading of the same or a higher level. Fails when the heading is not
    there exactly once."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.rstrip() == heading]
    if len(starts) != 1:
        asserts.fail("expected the heading {!r} once, found it {} times in:\n{}".format(
            heading, len(starts), text))
    level = heading_level(heading)
    out = []
    for line in lines[starts[0] + 1:]:
        found = heading_level(line)
        if found and found <= level:
            break
        out.append(line)
    return out


def items(lines):
    """Top-level list items (lines starting with `- `), trailing spaces dropped."""
    return [line.rstrip() for line in lines if line.startswith("- ")]


def nonblank(text):
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def field(lines, label):
    """A field's value per FORMAT.md: the text after `- **<label>:**` plus every
    indented line under it, joined by newlines. None when the label is absent."""
    prefix = "- **{}:**".format(label)
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            value = [line[len(prefix):].strip()]
            for more in lines[index + 1:]:
                if more.startswith((" ", "\t")) and more.strip():
                    value.append(more.strip())
                else:
                    break
            return "\n".join(v for v in value if v)
    return None


def fields_under_title(text):
    """Lines after the `#` title and before the first `##` heading."""
    out = []
    for line in text.splitlines()[1:]:
        if heading_level(line):
            break
        out.append(line)
    return out


def double_blank(text):
    """1-based line number of the first blank line that follows a blank line, or 0."""
    previous = False
    for number, line in enumerate(text.split("\n")[:-1], 1):
        blank = not line.strip()
        if blank and previous:
            return number
        previous = blank
    return 0


def diff_lines(diff):
    """(added, deleted) line lists from `git diff -U0` output, hunks only."""
    added, deleted = [], []
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif line.startswith("diff --git"):
            in_hunk = False
        elif in_hunk and line.startswith("+"):
            added.append(line[1:])
        elif in_hunk and line.startswith("-"):
            deleted.append(line[1:])
    return added, deleted


# --- run checks -----------------------------------------------------------------


def commit_date(run, rev="HEAD"):
    """The committer date of `rev` as YYYY-MM-DD (asserts.commit_date)."""
    return str(asserts.commit_date(run, rev=rev)).strip()


def old_text(run, rel):
    """`rel` as the fixture commit (HEAD~1) holds it."""
    return asserts.git(run, "show", "HEAD~1:" + rel) + "\n"


def changes(run, rel):
    """(added, deleted) line lists of `rel` in the skill's commit."""
    return diff_lines(asserts.git(run, "diff", "-U0", "--no-color", "HEAD~1", "HEAD", "--", rel))


def numstat(run, rel):
    """(added, deleted) line counts of `rel` from `git diff --numstat HEAD~1 HEAD`."""
    out = asserts.git(run, "diff", "--numstat", "HEAD~1", "HEAD", "--", rel).split()
    if len(out) < 3:
        asserts.fail("git diff --numstat shows no change to {}".format(rel))
    return int(out[0]), int(out[1])


def one_new_commit(run, files, branch="main"):
    """D14: one commit on top of the fixture's, holding exactly `files`, a clean
    tree, check.py exit 0 and a commit subject that follows writing."""
    if asserts.branch(run) != branch:
        asserts.fail("expected branch {}, found {}".format(branch, asserts.branch(run)))
    count = asserts.commit_count(run)
    if count != EXPECTED_COMMITS:
        asserts.fail("expected {} commits (the fixture's plus one), found {}: {}".format(
            EXPECTED_COMMITS, count, asserts.commit_messages(run)))
    found = asserts.commit_files(run)
    if found != set(files):
        asserts.fail("the commit holds {}, expected {}".format(sorted(found), sorted(files)))
    if asserts.status(run):
        asserts.fail("git status is not clean: {}".format(asserts.status(run)))
    asserts.check_exit(run, 0)
    subject_follows_writing(run)


def clean_layout(run, rel):
    """D10: no two blank lines in a row, and exactly one trailing newline."""
    text = asserts.file_text(run, rel)
    number = double_blank(text)
    if number:
        asserts.fail("{} has two blank lines in a row at line {}:\n{}".format(rel, number, text))
    if not text.endswith("\n") or text.endswith("\n\n"):
        asserts.fail("{} must end with exactly one newline: {!r}".format(rel, text[-20:]))


def last_item(run, rel, heading):
    """The last action line under `heading` in `rel`, or None when the section is empty."""
    found = items(section(asserts.file_text(run, rel), heading))
    return found[-1] if found else None


def expect_last_item(run, rel, heading, expected):
    found = last_item(run, rel, heading)
    if found != expected:
        asserts.fail("the last item under {!r} in {} is {!r}, expected {!r}.\n{}".format(
            heading, rel, found, expected, asserts.file_text(run, rel)))


def scaffold_lines(*to_do):
    """Non-blank lines of an actions.md scaffold, with `to_do` items under `## To do`."""
    return ["# Actions", "## In progress", "## To do"] + list(to_do) + ["## Done"]


def expect_nonblank(run, rel, expected):
    found = nonblank(asserts.file_text(run, rel))
    if found != list(expected):
        asserts.fail("{} holds {!r}, expected {!r}".format(rel, found, list(expected)))


def requirement(text, name):
    """The lines of the `### <name>` requirement block, which must sit under `## Requirements`."""
    lines = section(text, "## Requirements")
    starts = [i for i, line in enumerate(lines) if line.rstrip() == "### " + name]
    if len(starts) != 1:
        asserts.fail("expected `### {}` once under ## Requirements, found {}:\n{}".format(
            name, len(starts), text))
    out = []
    for line in lines[starts[0] + 1:]:
        if heading_level(line):
            break
        out.append(line)
    return out


def expect_requirement(text, name, kind, stakeholders, description):
    """The requirement has Type `kind`, Stakeholders naming each of `stakeholders`,
    and a Description matching every regex in `description` (case-insensitive)."""
    block = requirement(text, name)
    found_type = field(block, "Type")
    if found_type != kind:
        asserts.fail("requirement {!r} has Type {!r}, expected {!r}".format(name, found_type, kind))
    found = field(block, "Stakeholders") or ""
    missing = [s for s in stakeholders if s.lower() not in found.lower()]
    if missing:
        asserts.fail("requirement {!r} Stakeholders {!r} lack {}".format(name, found, missing))
    found = field(block, "Description") or ""
    missing = [p for p in description if not re.search(p, found, re.I)]
    if missing:
        asserts.fail("requirement {!r} Description {!r} lacks {}".format(name, found, missing))
