"""Tests for scripts/check.py, the DevOS state-file checker.

Every case runs the real checker as a subprocess against a copy of the
fixture state repo in tests/fixture/. A planted-defect case first proves the
clean copy passes, then applies one mutation and asserts the exit code and
the `<path>:<line>: <rule>:` output line. Standard library only; runs under
Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECK = os.path.join(ROOT, "scripts", "check.py")
FORMAT = os.path.join(ROOT, "FORMAT.md")
FIXTURE = os.path.join(HERE, "fixture")

P = "projects/checkout-revamp"
SPEC = P + "/specs/guest-checkout"
STATUS = P + "/status-reports/2026-10-09.md"
PROGRESS = "progress-reports/2026-10-01.md"


def run_check(args, cwd=None):
    return subprocess.run(
        [sys.executable, CHECK] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def describe(result):
    return "exit {}\nstdout:\n{}stderr:\n{}".format(
        result.returncode, result.stdout, result.stderr
    )


# --- mutations: each asserts its target exists, so fixture drift fails loudly ---


def _path(repo, rel):
    return os.path.join(repo, *rel.split("/"))


def _read(repo, rel):
    with open(_path(repo, rel), encoding="utf-8", newline="") as f:
        return f.read()


def _write(repo, rel, text):
    path = _path(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def replace(rel, *pairs):
    """Replace each `old` with `new` in one file; each `old` must occur once."""

    def apply(repo):
        text = _read(repo, rel)
        for old, new in zip(pairs[::2], pairs[1::2]):
            count = text.count(old)
            if count != 1:
                raise AssertionError(
                    "fixture drift: {!r} occurs {} times in {}".format(old, count, rel)
                )
            text = text.replace(old, new)
        _write(repo, rel, text)

    return apply


def append(rel, extra):
    def apply(repo):
        _write(repo, rel, _read(repo, rel) + extra)

    return apply


def write(rel, text):
    def apply(repo):
        _write(repo, rel, text)

    return apply


def delete(rel):
    def apply(repo):
        path = _path(repo, rel)
        if not os.path.isfile(path):
            raise AssertionError("fixture drift: {} is not a file".format(rel))
        os.remove(path)

    return apply


def rename(old, new):
    def apply(repo):
        src = _path(repo, old)
        if not os.path.exists(src):
            raise AssertionError("fixture drift: {} does not exist".format(old))
        os.rename(src, _path(repo, new))

    return apply


def chain(*steps):
    def apply(repo):
        for step in steps:
            step(repo)

    return apply


# Adds a `### Notes` heading under two spec sections, so their anchors are
# `notes` and `notes-1` (GitHub numbers repeated slugs).
DUPLICATE_NOTES = replace(
    SPEC + "/spec.md",
    "below today's level.\n",
    "below today's level.\n\n### Notes\n\nBaselines come from the September numbers.\n",
    "velocity limit.\n",
    "velocity limit.\n\n### Notes\n\nThe payments team owns the fraud checks.\n",
)


def case(cid, mutate, path, line, rule, exit=1):
    """`line` is an int, a string (first line containing it), or (string, n)."""
    return {"id": cid, "mutate": mutate, "path": path, "line": line, "rule": rule, "exit": exit}


DEFECTS = [
    # marker (exit 2)
    case("marker_missing", delete(".devos"), ".devos", 1, "marker", exit=2),
    case("marker_malformed", write(".devos", "format: 2\n"), ".devos", 1, "marker", exit=2),
    case("marker_remote_line_first",
         write(".devos", "remote: https://git.example.com/me/state.git\nformat: 1\n"),
         ".devos", 1, "marker", exit=2),
    # marker: lines after `format: 1` (exit 1; the rest of the repo is still checked)
    case("marker_remote_empty_url", write(".devos", "format: 1\nremote:   \n"),
         ".devos", 2, "marker"),
    case("marker_remote_duplicate",
         write(".devos", "format: 1\nremote: https://git.example.com/me/state.git\n"
                         "remote: https://git.example.com/me/state.git\n"),
         ".devos", 3, "marker"),
    case("marker_extra_line", write(".devos", "format: 1\nowner: me\n"), ".devos", 2, "marker"),
    case("marker_second_format_line", write(".devos", "format: 1\nformat: 1\n"),
         ".devos", 2, "marker"),
    # missing-file
    case("missing_project_md", delete(P + "/project.md"), P + "/project.md", 1, "missing-file"),
    case("missing_spec_md", delete(SPEC + "/spec.md"), SPEC + "/spec.md", 1, "missing-file"),
    case("missing_appendix_md", delete(SPEC + "/appendix.md"), SPEC + "/appendix.md", 1,
         "missing-file"),
    # slug
    case("slug_project_folder", rename(P, "projects/Checkout_Revamp"),
         "projects/Checkout_Revamp", 1, "slug"),
    case("slug_spec_folder", rename(SPEC, P + "/specs/Guest Checkout"),
         P + "/specs/Guest Checkout", 1, "slug"),
    # filename-date
    case("filename_not_a_date", rename(STATUS, P + "/status-reports/weekly.md"),
         P + "/status-reports/weekly.md", 1, "filename-date"),
    case("filename_not_a_real_date", rename(PROGRESS, "progress-reports/2026-10-32.md"),
         "progress-reports/2026-10-32.md", 1, "filename-date"),
    case("share_date_differs_from_filename",
         replace(STATUS, "- **Share date:** 2026-10-09", "- **Share date:** 2026-10-08"),
         STATUS, "**Share date:**", "filename-date"),
    case("unknown_md_in_status_reports",
         write(P + "/status-reports/notes.md", "Some notes.\n"),
         P + "/status-reports/notes.md", 1, "filename-date"),
    # title
    case("title_wrong", replace(P + "/evidence.md", "# Evidence\n", "# Wins\n"),
         P + "/evidence.md", 1, "title"),
    case("title_missing", replace(STATUS, "# Status report: Checkout Revamp\n\n", ""),
         STATUS, 1, "title"),
    case("title_wrong_brief_suffix",
         replace(SPEC + "/brief.md", "# Guest checkout: brief\n", "# Guest checkout\n"),
         SPEC + "/brief.md", 1, "title"),
    case("title_repeated", append(SPEC + "/appendix.md", "\n# More notes\n\nText.\n"),
         SPEC + "/appendix.md", "# More notes", "title"),
    # heading
    case("heading_missing", replace(SPEC + "/spec.md", "## Risks\n\n", ""),
         SPEC + "/spec.md", 1, "heading"),
    case("heading_out_of_order",
         replace(P + "/actions.md", "## In progress\n", "## TMP\n",
                 "## To do\n", "## In progress\n", "## TMP\n", "## To do\n"),
         P + "/actions.md", "## To do", "heading"),
    case("heading_duplicated", append(STATUS, "\n## Done\n\n- None\n"),
         STATUS, ("## Done", 2), "heading"),
    case("heading_progress_subsection_missing", replace(PROGRESS, "### Progress\n\n- None\n", ""),
         PROGRESS, "## Search Latency", "heading"),
    case("heading_progress_no_project_section",
         write(PROGRESS, "# Progress report\n\n- **Share date:** 2026-10-01\n"
                         "- **Time frame:** 2026-09-01 to 2026-09-30\n"),
         PROGRESS, 1, "heading"),
    # missing-field
    case("missing_priority", replace(P + "/project.md", "- **Priority:** P1\n", ""),
         P + "/project.md", 1, "missing-field"),
    case("missing_requirement_description",
         replace(P + "/project.md", "- **Description:** Returning shoppers can pay with a card"
                                    " saved on an earlier order.\n", ""),
         P + "/project.md", "### Saved cards", "missing-field"),
    case("empty_references",
         replace(P + "/evidence.md", "- **References:** [Checkout flow map]"
                                     "(https://example.com/docs/checkout-flow-map)",
                 "- **References:**"),
         P + "/evidence.md", "**References:**", "missing-field"),
    case("missing_impact_summary",
         replace(PROGRESS, "- **Impact summary:** No impact yet; the project starts in October.\n",
                 ""),
         PROGRESS, "## Search Latency", "missing-field"),
    # priority
    case("action_priority_p4",
         replace(P + "/actions.md", " · P2 · added 2026-10-05", " · P4 · added 2026-10-05"),
         P + "/actions.md", "Write the rollout plan", "priority"),
    case("project_priority_word",
         replace(P + "/project.md", "- **Priority:** P1", "- **Priority:** High"),
         P + "/project.md", "**Priority:**", "priority"),
    # date
    case("evidence_date_not_real", replace(P + "/evidence.md", "2026-10-08", "2026-02-30"),
         P + "/evidence.md", "2026-02-30", "date"),
    case("action_added_date_not_real",
         replace(P + "/actions.md", "added 2026-10-06", "added 2026-13-06"),
         P + "/actions.md", "saved-card storage", "date"),
    case("time_frame_date_not_real",
         replace(STATUS, "2026-09-25 to 2026-10-09", "2026-09-31 to 2026-10-09"),
         STATUS, "**Time frame:**", "date"),
    # time-frame
    case("time_frame_reversed",
         replace(STATUS, "2026-09-25 to 2026-10-09", "2026-10-09 to 2026-09-25"),
         STATUS, "**Time frame:**", "time-frame"),
    case("time_frame_not_a_range",
         replace(PROGRESS, "2026-09-01 to 2026-09-30", "September 2026"),
         PROGRESS, "**Time frame:**", "time-frame"),
    # requirement-type
    case("requirement_type_must",
         replace(P + "/project.md", "- **Type:** want", "- **Type:** must"),
         P + "/project.md", "**Type:** must", "requirement-type"),
    # action-line
    case("action_missing_added_date",
         replace(P + "/actions.md", "- Build the guest payment form · P0 · added 2026-09-28",
                 "- Build the guest payment form · P0"),
         P + "/actions.md", "Build the guest payment form", "action-line"),
    case("action_done_date_outside_done",
         replace(P + "/actions.md", "· P3 · added 2026-10-06",
                 "· P3 · added 2026-10-06 · done 2026-10-07"),
         P + "/actions.md", "saved-card storage", "action-line"),
    case("action_under_done_without_done_date",
         replace(P + "/actions.md", "· added 2026-09-15 · done 2026-10-02", "· added 2026-09-15"),
         P + "/actions.md", "Agree the guest checkout scope", "action-line"),
    case("non_action_item_in_action_section",
         replace(P + "/actions.md", "## To do\n\n", "## To do\n\n- Remember to ask about the vault\n"),
         P + "/actions.md", "Remember to ask", "action-line"),
    # done-date
    case("done_before_added",
         replace(P + "/actions.md", "· done 2026-09-21", "· done 2026-09-07"),
         P + "/actions.md", "Map the current checkout flow", "done-date"),
    # impact-status
    case("impact_status_shipped",
         replace(P + "/evidence.md", "outdated documents.\n- **Impact status:** delivered",
                 "outdated documents.\n- **Impact status:** shipped"),
         P + "/evidence.md", "**Impact status:** shipped", "impact-status"),
    # references
    case("references_inline_not_a_link",
         replace(P + "/evidence.md", "[Checkout flow map](https://example.com/docs/checkout-flow-map)",
                 "the flow map in the team wiki"),
         P + "/evidence.md", "**References:**", "references"),
    case("references_nested_item_not_a_link",
         replace(P + "/evidence.md", "  - [Prototype](https://example.com/prototypes/guest-checkout)",
                 "  - the prototype on the design board"),
         P + "/evidence.md", ("**References:**", 2), "references"),
    # brief-link
    case("brief_link_no_such_section",
         replace(SPEC + "/brief.md", "spec.md#non-goals", "spec.md#no-such-section"),
         SPEC + "/brief.md", "no-such-section", "brief-link"),
    case("brief_item_without_link",
         replace(SPEC + "/brief.md", "- [Whether guest orders need an email address]"
                                     "(spec.md#open-questions).",
                 "- Whether guest orders need an email address."),
         SPEC + "/brief.md", "Whether guest orders", "brief-link"),
    case("brief_link_only_inside_code_block",
         replace(SPEC + "/brief.md", "- [Whether guest orders need an email address]"
                                     "(spec.md#open-questions).",
                 "- Whether guest orders need an email address.\n\n  ```text\n"
                 "  [Open questions](spec.md#open-questions)\n  ```"),
         SPEC + "/brief.md", "Whether guest orders", "brief-link"),
    case("brief_link_past_repeated_anchors",
         chain(DUPLICATE_NOTES,
               replace(SPEC + "/brief.md", "spec.md#open-questions", "spec.md#notes-2")),
         SPEC + "/brief.md", "notes-2", "brief-link"),
    # empty-section
    case("spec_section_empty",
         replace(SPEC + "/spec.md", "- Fraud may rise without account history. Mitigation: keep the"
                                    " current fraud checks and add a per-card velocity limit.\n", ""),
         SPEC + "/spec.md", "## Risks", "empty-section"),
    case("brief_section_empty",
         replace(SPEC + "/brief.md", "- [No changes to the signed-in checkout](spec.md#non-goals).\n",
                 ""),
         SPEC + "/brief.md", "## Not doing", "empty-section"),
    case("status_section_empty",
         replace(STATUS, "- Build the guest payment form (in progress).\n- Write the rollout plan.\n",
                 ""),
         STATUS, "## Pending", "empty-section"),
    case("progress_list_empty", replace(PROGRESS, "- None\n", ""),
         PROGRESS, ("### Progress", 2), "empty-section"),
]

# Edits the format allows: each must keep the fixture valid (exit 0).
ALLOWED = [
    ("unknown_file_at_root", write("notes.md", "# My notes\n\nAnything goes here.\n")),
    ("unknown_file_in_project", write(P + "/notes.md", "Scratch notes, not a DevOS record.\n")),
    ("non_md_file_in_status_reports", write(P + "/status-reports/chart.csv", "week,orders\n")),
    ("marker_with_whitespace_and_crlf", write(".devos", "  format: 1  \r\n")),
    ("marker_without_trailing_newline", write(".devos", "format: 1")),
    ("marker_with_remote_lines",
     write(".devos", "format: 1\nremote: https://git.example.com/me/state.git\n"
                     "remote: git@git.example.com:me/state.git\n")),
    ("marker_with_remote_line_crlf_no_trailing_newline",
     write(".devos", "format: 1\r\nremote: https://git.example.com/me/state.git")),
    ("brief_item_none",
     replace(SPEC + "/brief.md", "- [No changes to the signed-in checkout](spec.md#non-goals).",
             "- None")),
    ("heading_inside_code_block_is_ignored",
     replace(SPEC + "/spec.md", "## Open questions\n",
             "```markdown\n## Goals\n# Not a title\n```\n\n## Open questions\n")),
    ("fenced_list_line_under_references_is_not_a_reference",
     replace(P + "/evidence.md", "  - [Prototype](https://example.com/prototypes/guest-checkout)\n",
             "  - [Prototype](https://example.com/prototypes/guest-checkout)\n\n"
             "  ```text\n  - not a reference\n  ```\n")),
    ("thematic_breaks_in_action_section_are_not_items",
     replace(P + "/actions.md", "## To do\n\n", "## To do\n\n* * *\n\n- - -\n\n")),
    ("brief_link_to_repeated_anchor",
     chain(DUPLICATE_NOTES,
           replace(SPEC + "/brief.md", "spec.md#open-questions", "spec.md#notes-1"))),
    ("extra_heading_and_field_in_evidence",
     chain(replace(P + "/evidence.md", "- **Impact status:** measured\n",
                   "- **Impact status:** measured\n- **Reviewer:** Design lead\n"),
           append(P + "/evidence.md", "\n### Method\n\nModerated sessions over video.\n"))),
    ("crlf_line_endings",
     lambda repo: _write(repo, P + "/actions.md",
                         _read(repo, P + "/actions.md").replace("\n", "\r\n"))),
    ("byte_order_mark_is_ignored",
     chain(lambda repo: _write(repo, P + "/actions.md", "﻿" + _read(repo, P + "/actions.md")),
           write(".devos", "﻿format: 1\n"))),
]


class FixtureCopy(unittest.TestCase):
    """Base: gives each test a fresh copy of the fixture state repo."""

    def fresh_copy(self):
        tmp = tempfile.mkdtemp(prefix="devos-check-")
        self.addCleanup(shutil.rmtree, tmp, True)
        repo = os.path.join(tmp, "repo")
        shutil.copytree(FIXTURE, repo)
        return repo

    def assert_clean(self, repo):
        result = run_check([repo])
        self.assertEqual(result.returncode, 0, "clean fixture copy must pass\n" + describe(result))
        self.assertEqual(result.stdout, "", "clean fixture copy must print nothing")


def expected_line(repo, path, line):
    if isinstance(line, int):
        return line
    needle, nth = (line, 1) if isinstance(line, str) else line
    seen = 0
    with open(_path(repo, path), encoding="utf-8") as f:
        for number, text in enumerate(f, 1):
            if needle in text:
                seen += 1
                if seen == nth:
                    return number
    raise AssertionError("locator {!r} not found in {}".format(line, path))


class PlantedDefects(FixtureCopy):
    """One test per DEFECTS row, generated below."""


def _make_defect_test(row):
    def test(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)
        row["mutate"](repo)
        result = run_check([repo])
        self.assertEqual(result.returncode, row["exit"], describe(result))
        prefix = "{}:{}: {}:".format(
            row["path"], expected_line(repo, row["path"], row["line"]), row["rule"]
        )
        lines = result.stdout.splitlines()
        self.assertTrue(
            any(out.startswith(prefix) for out in lines),
            "expected a line starting {!r}\n{}".format(prefix, describe(result)),
        )
        # One mutation, one defect: no cascade of unrelated lines.
        self.assertEqual(len(lines), 1, "expected exactly one defect line\n" + describe(result))

    return test


for _row in DEFECTS:
    setattr(PlantedDefects, "test_" + _row["id"], _make_defect_test(_row))


class AllowedEdits(FixtureCopy):
    """One test per ALLOWED row: the edit must not produce a defect."""


def _make_allowed_test(name, mutate):
    def test(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)
        mutate(repo)
        result = run_check([repo])
        self.assertEqual(result.returncode, 0, describe(result))
        self.assertEqual(result.stdout, "", describe(result))

    return test


for _name, _mutate in ALLOWED:
    setattr(AllowedEdits, "test_" + _name, _make_allowed_test(_name, _mutate))


class UnknownFiles(FixtureCopy):
    """Unknown files are ignored, except inside the dated-report folders."""

    def test_notes_at_root_and_in_project_folder_are_ignored(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)
        _write(repo, "notes.md", "Free notes.\n")
        _write(repo, P + "/notes.md", "Free notes.\n")
        result = run_check([repo])
        self.assertEqual(result.returncode, 0, describe(result))

    def test_notes_in_status_reports_is_a_filename_date_defect(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)
        _write(repo, P + "/status-reports/notes.md", "Free notes.\n")
        result = run_check([repo])
        self.assertEqual(result.returncode, 1, describe(result))
        self.assertIn(
            P + "/status-reports/notes.md:1: filename-date:", result.stdout, describe(result)
        )


class Fixture(unittest.TestCase):
    def test_fixture_passes(self):
        result = run_check([FIXTURE])
        self.assertEqual(result.returncode, 0, describe(result))
        self.assertEqual(result.stdout, "")

    def test_fixture_holds_every_record_type(self):
        for rel in [
            ".devos",
            "AGENTS.md",
            "CLAUDE.md",
            P + "/project.md",
            P + "/actions.md",
            P + "/evidence.md",
            STATUS,
            PROGRESS,
            SPEC + "/brief.md",
            SPEC + "/spec.md",
            SPEC + "/appendix.md",
        ]:
            self.assertTrue(os.path.isfile(_path(FIXTURE, rel)), rel)

    def test_fixture_carries_allowed_extras(self):
        project = _read(FIXTURE, P + "/project.md")
        evidence = _read(FIXTURE, P + "/evidence.md")
        actions = _read(FIXTURE, P + "/actions.md")
        self.assertIn("\n## Notes\n", project, "extra ## section")
        self.assertIn("\n- **Target quarter:** ", project, "extra field")
        self.assertRegex(project, r"\n- \*\*Description:\*\* [^\n]+\n  \S", "multi-line Description")
        self.assertRegex(evidence, r"\n- \*\*References:\*\*\n  - \[", "nested-list References")
        self.assertRegex(
            actions, r"(?m)^- [^\n]+ · [^\n]+ · P[0-3] · added [0-9-]+$", "action name with ' · '"
        )

    def test_agent_files_are_one_line_placeholders(self):
        for rel in ("AGENTS.md", "CLAUDE.md"):
            lines = _read(FIXTURE, rel).splitlines()
            self.assertEqual(len(lines), 1, rel)
            self.assertTrue(lines[0].startswith("Placeholder"), rel)


class Interface(FixtureCopy):
    def test_default_is_current_directory(self):
        repo = self.fresh_copy()
        self.assertEqual(run_check([], cwd=repo).returncode, 0)
        delete(P + "/project.md")(repo)
        result = run_check([], cwd=repo)
        self.assertEqual(result.returncode, 1, describe(result))
        self.assertIn(P + "/project.md:1: missing-file:", result.stdout)

    def test_not_a_directory_exits_2(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)  # a missing check.py also exits 2; rule that out
        self.assertEqual(run_check([_path(repo, ".devos")]).returncode, 2)
        self.assertEqual(run_check([os.path.join(repo, "no-such-folder")]).returncode, 2)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads mode-000 files")
    def test_unreadable_record_exits_2_without_a_traceback(self):
        repo = self.fresh_copy()
        self.assert_clean(repo)
        target = _path(repo, P + "/actions.md")
        os.chmod(target, 0)
        self.addCleanup(os.chmod, target, 0o644)
        result = run_check([repo])
        self.assertEqual(result.returncode, 2, describe(result))
        self.assertEqual(result.stdout, "", describe(result))
        self.assertIn(P + "/actions.md: cannot read", result.stderr, describe(result))
        self.assertNotIn("Traceback", result.stderr, describe(result))

    def test_output_is_sorted_by_path_then_line(self):
        repo = self.fresh_copy()
        replace(P + "/actions.md", "· P0 ·", "· P9 ·", "· P3 ·", "· P8 ·")(repo)
        replace(P + "/evidence.md", "- **Impact status:** measured",
                "- **Impact status:** guessed")(repo)
        delete(P + "/project.md")(repo)
        result = run_check([repo])
        self.assertEqual(result.returncode, 1, describe(result))
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 4, describe(result))
        keys = []
        for out in lines:
            match = re.match(r"^(.+?):([0-9]+): ([a-z-]+): \S", out)
            self.assertIsNotNone(match, out)
            keys.append((match.group(1), int(match.group(2))))
        self.assertEqual(keys, sorted(keys), describe(result))


def format_rule_ids():
    """Rule ids listed in FORMAT.md's `## Rule ids` section, in order."""
    with open(FORMAT, encoding="utf-8") as f:
        text = f.read()
    section = re.search(r"(?ms)^## Rule ids\n(.*?)(?=^## |\Z)", text)
    if not section:
        raise AssertionError("FORMAT.md has no `## Rule ids` section")
    return re.findall(r"(?m)^- `([a-z][a-z-]*)`: \S", section.group(1))


def checker_rule_ids():
    result = run_check(["--rules"])
    if result.returncode != 0:
        raise AssertionError("check.py --rules failed\n" + describe(result))
    return result.stdout.split()


class RuleIds(unittest.TestCase):
    def test_documented_tested_and_emittable_sets_agree(self):
        documented = format_rule_ids()
        emittable = checker_rule_ids()
        tested = [row["rule"] for row in DEFECTS]
        self.assertEqual(len(documented), len(set(documented)), "duplicate id in FORMAT.md")
        self.assertEqual(len(emittable), len(set(emittable)), "duplicate id in --rules")
        self.assertEqual(set(documented), set(emittable), "FORMAT.md vs check.py --rules")
        self.assertEqual(set(documented), set(tested), "FORMAT.md vs the planted-defect table")

    def test_table_covers_marker_twice_and_has_enough_cases(self):
        rules = [row["rule"] for row in DEFECTS]
        self.assertGreaterEqual(rules.count("marker"), 2)
        self.assertGreaterEqual(len(DEFECTS), 18)


def format_examples():
    """`Example: <path>` blocks from FORMAT.md, as {path: content}."""
    with open(FORMAT, encoding="utf-8") as f:
        text = f.read()
    pattern = r"(?m)^Example: `([^`]+)`\n\n```[a-z]*\n(.*?)^```$"
    return {path: body for path, body in re.findall(pattern, text, re.S)}


class FormatExamples(unittest.TestCase):
    def test_examples_form_a_valid_state_repo(self):
        examples = format_examples()
        kinds = {
            ".devos": r"^\.devos$",
            "project": r"^projects/[^/]+/project\.md$",
            "actions": r"^projects/[^/]+/actions\.md$",
            "evidence": r"^projects/[^/]+/evidence\.md$",
            "status report": r"^projects/[^/]+/status-reports/[^/]+\.md$",
            "progress report": r"^progress-reports/[^/]+\.md$",
            "brief": r"^projects/[^/]+/specs/[^/]+/brief\.md$",
            "spec": r"^projects/[^/]+/specs/[^/]+/spec\.md$",
            "appendix": r"^projects/[^/]+/specs/[^/]+/appendix\.md$",
        }
        for kind, pattern in kinds.items():
            self.assertTrue(
                any(re.match(pattern, path) for path in examples),
                "FORMAT.md has no example for " + kind,
            )
        tmp = tempfile.mkdtemp(prefix="devos-format-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for path, body in examples.items():
            _write(tmp, path, body)
        result = run_check([tmp])
        self.assertEqual(result.returncode, 0, describe(result))


if __name__ == "__main__":
    unittest.main()
