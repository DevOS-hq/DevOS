"""Shared checks for the spec scenarios (phase 05).

run.py skips this module (its name starts with "_"). Each scenario imports it
after putting this folder on sys.path. Every check raises AssertionError
through asserts.fail.

A spec is model-written prose, so content is checked with marker regexes
(case-insensitive) scoped by section, as phase 04 did (spec D10). Brief links
and spec anchors come from the plugin's own scripts/check.py (`Doc`,
`anchor_slug`, `LINK_RE`), so the scenario and the checker can never disagree
on what an anchor is.

The pure functions take file text, so they run offline on hand-made outcomes
as well as on a live run's files.
"""

import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _statecheck  # noqa: E402
import asserts  # noqa: E402

section = _statecheck.section
items = _statecheck.items

CHECK_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "scripts", "check.py")


def _load_check():
    spec = importlib.util.spec_from_file_location("devos_check_for_speccheck", CHECK_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_py = _load_check()

BRIEF_SECTIONS = ("The problem", "The goal", "The plan", "Not doing", "Still open")
SPEC_SECTIONS = ("Summary", "Goals", "Non-goals", "Milestones", "Risks", "Open questions")
DATE_RE = re.compile(r"\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")


# --- pure text helpers ----------------------------------------------------------


def hits(pattern, text):
    return re.search(pattern, text, re.I) is not None


def section_text(text, name):
    """The text under `## <name>`, up to the next `##` heading (fails when the heading
    is not there exactly once)."""
    return "\n".join(section(text, "## " + name))


def anchors(spec_text):
    """Every anchor spec.md's headings produce, numbered repeats included (check.py's Doc)."""
    return check_py.Doc(spec_text).anchors()


def brief_items(brief_text, name):
    """(text, link targets) of each top-level list item under the brief's `## <name>`.
    `text` is the item's first line after the marker; the targets come from that
    line and the indented lines under it, as check.py reads them."""
    doc = check_py.Doc(brief_text)
    found = [h for h in doc.headings if h.level == 2 and h.text == name]
    if len(found) != 1:
        asserts.fail("expected the heading `## {}` once in the brief, found it {} times:\n{}".format(
            name, len(found), brief_text))
    heading = found[0]
    out = []
    for item in doc.items(heading.idx + 1, doc.end_of_section(heading)):
        read = [line.strip() for line in item.read if line.strip()]
        targets = [target for _, target in check_py.LINK_RE.findall(" ".join([item.text] + read))]
        out.append((item.text, targets))
    return out


def is_none(text, targets):
    return text.strip() == "None" and not targets


def dates(text):
    return DATE_RE.findall(text)


# --- checks ---------------------------------------------------------------------


def brief_links(brief_text, spec_text):
    """AC10: every brief item other than `- None` links to `spec.md#<anchor>` with an
    anchor spec.md has; every Still open item links to `spec.md#open-questions`."""
    known = anchors(spec_text)
    for name in BRIEF_SECTIONS:
        for text, targets in brief_items(brief_text, name):
            if is_none(text, targets):
                continue
            spec_targets = [t for t in targets if t.startswith("spec.md#")]
            if not spec_targets:
                asserts.fail("the brief's {!r} item {!r} links to no spec.md#<anchor>".format(name, text))
            for target in spec_targets:
                if target[len("spec.md#"):] not in known:
                    asserts.fail("the brief's {!r} item {!r} links to {}, which matches no heading "
                                 "in spec.md (anchors: {})".format(name, text, target, sorted(known)))
            if name == "Still open" and "spec.md#open-questions" not in spec_targets:
                asserts.fail("the brief's Still open item {!r} does not link to "
                             "spec.md#open-questions: {}".format(text, spec_targets))


def marker_in(text, where, pattern, label):
    """`pattern` matches the text of `where` (a description such as "spec.md ## Risks")."""
    if not hits(pattern, text):
        asserts.fail("the {} marker /{}/ is missing from {}:\n{}".format(label, pattern, where, text))


def marker_not_in(text, where, pattern, label):
    if hits(pattern, text):
        asserts.fail("the {} marker /{}/ appears in {}:\n{}".format(label, pattern, where, text))


def dates_from(spec_text, source_text):
    """AC11: every YYYY-MM-DD in spec.md occurs in the user's words."""
    stray = [d for d in dates(spec_text) if d not in source_text]
    if stray:
        asserts.fail("spec.md holds the date(s) {}, which the answers never gave".format(stray))
