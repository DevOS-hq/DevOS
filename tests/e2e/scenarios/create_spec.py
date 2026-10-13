"""`create-spec` interviews first, shows an outline, then writes the spec.

Start: the fixture as a state repo; search-latency has no specs. Turn 1 names
the skill, the spec Typo-tolerant search and the project. ANSWERS[0] answers
every content slot in one message, one point "I don't know yet"; the rest are
one fallback that fits both a further question round and the outline.
UNTIL_COMMIT stops the answers once a turn commits.

Check (AC8-AC12): turn 1 changed nothing and asked questions; every turn
before the last left HEAD alone; the last turn made the only new commit, not
on turn 2 (no outline turn), and the reply before it names the spec's folder
path (the outline, spec review S1); the commit holds exactly brief.md, spec.md
and appendix.md; check.py passes; the tree is clean; brief links resolve and
Still open links to spec.md#open-questions; each marker sits in its own
section; the unknown point is an open question and nothing else; every date
in spec.md came from the answers; the appendix holds the link. The full check
adds AC13 (judge cold read of the brief, grounded milestones; best of two)
and AC14 (writing loaded, FORMAT.md read, check.py run, commit subject rule).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _speccheck as spec  # noqa: E402
import _statecheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude",)
START = "state-repo"
TIMEOUT = 900
UNTIL_COMMIT = True

PROMPT = (
    "Use the DevOS `create-spec` skill to write a spec called Typo-tolerant search "
    "for the search-latency project."
)

LINK = "https://example.com/dashboards/empty-results"

FALLBACK = (
    "That's everything I know. Treat anything I haven't answered as still open. "
    "If you're showing me an outline, it's right, so go ahead and write the spec."
)

ANSWERS = (
    "Problem: shoppers who mistype a product name get an empty results page. "
    "For example, \"bluetooth headphnes\" returns nothing.\n"
    "Goals: return results for searches with one or two typos, and halve the number of "
    "empty results pages.\n"
    "Not doing: no changes to autocomplete.\n"
    "Milestones: first, edit-distance matching on product titles, target 2026-11-20; "
    "second, a \"did you mean\" banner, with no date yet.\n"
    "Risk: looser matching may show the wrong products for model numbers such as XR-200. "
    "Mitigation: skip matching for queries that contain digits.\n"
    "Unknown: \"I don't know yet whether brand names should be exempt.\"\n"
    "Supporting material: the empty-results dashboard, {}.".format(LINK),
    FALLBACK,
    FALLBACK,
    FALLBACK,
)

# The user's words: the only source of dates and milestones.
SOURCE = "\n\n".join((PROMPT,) + ANSWERS)

FOLDER = "projects/search-latency/specs/typo-tolerant-search"
BRIEF = FOLDER + "/brief.md"
SPEC = FOLDER + "/spec.md"
APPENDIX = FOLDER + "/appendix.md"
FILES = {BRIEF, SPEC, APPENDIX}

# Markers (plan "Scenario content"): case-insensitive, each matching only its
# own answer and none of the files' fixed text (titles, headings, `- None`,
# `Target:`). Widen with a true synonym after a live miss; never drop one.
MILESTONE_MARKERS = (r"edit[- ]?distance", r"did you mean")
RISK_MARKER = r"model numbers?|digits?"
NON_GOAL_MARKER = r"auto-?complete"
UNKNOWN_MARKER = r"brands?"
MARKERS = MILESTONE_MARKERS + (RISK_MARKER, NON_GOAL_MARKER, UNKNOWN_MARKER)

# The turn that delivered ANSWERS[0].
ANSWER_TURN = 2


def rubric(run):
    return os.path.join(run.plugin_dir, "tests", "e2e", "rubrics", "brief-cold-read.md")


def milestones_text(run):
    return "## Milestones\n" + spec.section_text(asserts.file_text(run, SPEC), "Milestones").strip()


def check_turns(run):
    """AC8, AC9: ask first, outline next, then the only commit on the last turn."""
    if not run.turns:
        asserts.fail("the run has no turns")
    asserts.turn_unchanged(run, 1)
    first = run.turns[0].text or ""
    if first.count("?") < 2:
        asserts.fail("turn 1's reply asks fewer than two questions: {!r}".format(first))
    start = run.turns[0].before["head"]
    for turn in run.turns[:-1]:
        if (turn.after or {}).get("head") != start:
            asserts.fail("turn {} of {} changed HEAD; only the last turn may commit".format(
                turn.index, len(run.turns)))
    last = run.turns[-1]
    if (last.after or {}).get("head") == start:
        asserts.fail("no turn made a commit in {} turns".format(len(run.turns)))
    if len(run.turns) <= ANSWER_TURN:
        asserts.fail("the commit came on turn {}, the turn that delivered ANSWERS[0]; "
                     "no outline turn came first".format(len(run.turns)))
    before = run.turns[-2].text or ""
    if FOLDER not in before:
        asserts.fail("turn {}'s reply, before the commit, never names the folder path {}, "
                     "so it was not an outline: {!r}".format(len(run.turns) - 1, FOLDER, before))


def check_content(run):
    """AC10-AC12 on the three written files."""
    spec_text = asserts.file_text(run, SPEC)
    brief_text = asserts.file_text(run, BRIEF)
    spec.brief_links(brief_text, spec_text)
    sections = {name: spec.section_text(spec_text, name) for name in spec.SPEC_SECTIONS}
    for index, marker in enumerate(MILESTONE_MARKERS, 1):
        spec.marker_in(sections["Milestones"], "spec.md ## Milestones", marker, "milestone {}".format(index))
    spec.marker_in(sections["Risks"], "spec.md ## Risks", RISK_MARKER, "risk")
    spec.marker_in(sections["Non-goals"], "spec.md ## Non-goals", NON_GOAL_MARKER, "non-goal")
    spec.marker_not_in(sections["Goals"], "spec.md ## Goals", NON_GOAL_MARKER, "non-goal")
    spec.marker_in(sections["Open questions"], "spec.md ## Open questions", UNKNOWN_MARKER, "unknown")
    spec.marker_in(spec.section_text(brief_text, "Still open"), "brief.md ## Still open",
                   UNKNOWN_MARKER, "unknown")
    for name in ("Summary", "Goals", "Non-goals", "Milestones"):
        spec.marker_not_in(sections[name], "spec.md ## " + name, UNKNOWN_MARKER, "unknown")
    spec.dates_from(spec_text, SOURCE)
    appendix = asserts.file_text(run, APPENDIX)
    if LINK not in appendix:
        asserts.fail("the appendix lacks the given link {}:\n{}".format(LINK, appendix))


def check_state(run):
    check_turns(run)
    count = asserts.commit_count(run)
    if count != common.EXPECTED_COMMITS:
        asserts.fail("expected {} commits (the fixture's plus one), found {}: {}".format(
            common.EXPECTED_COMMITS, count, asserts.commit_messages(run)))
    found = asserts.commit_files(run)
    if found != FILES:
        asserts.fail("the commit holds {}, expected {}".format(sorted(found), sorted(FILES)))
    check_content(run)
    common.one_new_commit(run, FILES)


def check(run):
    check_state(run)  # one_new_commit also holds the commit subject to writing's rule (AC14)
    common.loaded_and_checked(run)
    asserts.judge_pass(run, BRIEF, rubric=rubric(run), tries=2)
    asserts.judge_grounded(run, milestones_text(run), SOURCE, tries=2)
