"""Tests for scripts/window.py, the report time-frame filter.

Every case builds its own small state repo in a temp folder, runs the real
script as a subprocess and asserts the exit code, stdout and stderr. The
shared fixture is not used, so these tests do not move when it gains items.
Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WINDOW = os.path.join(ROOT, "scripts", "window.py")

ACTIONS_HEAD = "# Actions\n\n## In progress\n\n{progress}\n## To do\n\n{todo}\n## Done\n\n{done}"


def actions(progress=(), todo=(), done=()):
    """An actions.md body from lists of raw lines (notes included)."""
    def block(lines):
        return "".join(line + "\n" for line in lines)
    return ACTIONS_HEAD.format(progress=block(progress), todo=block(todo), done=block(done))


def evidence_item(name, date, impact, status="measured", refs="[Notes](https://example.com/n)"):
    lines = ["## " + name, ""]
    if date is not None:
        lines.append("- **Date:** " + date)
    lines += ["- **Impact:** " + impact, "- **Impact status:** " + status,
              "- **References:** " + refs, ""]
    return "\n".join(lines) + "\n"


def evidence(*items):
    return "# Evidence\n\n" + "".join(items)


def line_of(text, needle):
    """1-based line number of the only line holding `needle`."""
    hits = [i + 1 for i, line in enumerate(text.split("\n")) if needle in line]
    if len(hits) != 1:
        raise AssertionError("expected one line with {!r}, got {}".format(needle, hits))
    return hits[0]


class WindowTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="devos-window-")
        self.addCleanup(shutil.rmtree, self.repo)
        self.write(".devos", "format: 1\n")

    # --- helpers -------------------------------------------------------------

    def write(self, rel, text):
        path = os.path.join(self.repo, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def project(self, slug, name, actions_md=None, evidence_md=None, reports=()):
        p = "projects/" + slug
        self.write(p + "/project.md",
                   "# {}\n\n- **Priority:** P1\n- **Stakeholders:** none\n\n## Requirements\n"
                   .format(name))
        if actions_md is not None:
            self.write(p + "/actions.md", actions_md)
        if evidence_md is not None:
            self.write(p + "/evidence.md", evidence_md)
        for date in reports:
            self.write(p + "/status-reports/" + date, "# Status report: {}\n".format(name))

    def run_window(self, *args, repo=None):
        return subprocess.run(
            [sys.executable, WINDOW, self.repo if repo is None else repo] + list(args),
            capture_output=True, text=True)

    def ok(self, *args):
        r = self.run_window(*args)
        self.assertEqual(r.returncode, 0, self.describe(r))
        return r.stdout

    def exits(self, code, *args, repo=None):
        r = self.run_window(*args, repo=repo)
        self.assertEqual(r.returncode, code, self.describe(r))
        # Python itself exits 2 when the script is missing; demand the
        # script's own `window.py: ` message so that case cannot pass.
        self.assertIn("window.py: ", r.stderr, self.describe(r))
        return r

    @staticmethod
    def describe(r):
        return "exit {}\nstdout:\n{}stderr:\n{}".format(r.returncode, r.stdout, r.stderr)

    # --- frames --------------------------------------------------------------

    def test_frame_includes_both_ends(self):
        self.project("alpha", "Alpha", actions(done=[
            "- Day before start · P2 · added 2026-09-01 · done 2026-10-04",
            "- On start · P1 · added 2026-09-01 · done 2026-10-05",
            "- On end · P0 · added 2026-09-01 · done 2026-10-09",
            "- Day after end · P3 · added 2026-09-01 · done 2026-10-10",
        ]), evidence(
            evidence_item("Evidence before", "2026-10-04", "Before impact."),
            evidence_item("Evidence on start", "2026-10-05", "Start impact."),
            evidence_item("Evidence on end", "2026-10-09", "End impact.", status="delivered"),
            evidence_item("Evidence after", "2026-10-10", "After impact."),
        ))
        out = self.ok("--project", "alpha", "--start", "2026-10-05", "--end", "2026-10-09")
        self.assertIn("Frame: 2026-10-05 to 2026-10-09\n", out)
        self.assertIn("- done 2026-10-05 · P1 · On start\n", out)
        self.assertIn("- done 2026-10-09 · P0 · On end\n", out)
        self.assertNotIn("Day before start", out)
        self.assertNotIn("Day after end", out)
        self.assertIn("- 2026-10-05 · measured · Evidence on start\n", out)
        self.assertIn("- 2026-10-09 · delivered · Evidence on end\n", out)
        self.assertNotIn("Evidence before", out)
        self.assertNotIn("Evidence after", out)

    def test_done_actions_filter_by_done_date_not_added_date(self):
        self.project("alpha", "Alpha", actions(done=[
            "- Added before, done inside · P1 · added 2026-09-20 · done 2026-10-06",
            "- Added inside, done after · P2 · added 2026-10-06 · done 2026-10-20",
        ]))
        out = self.ok("--project", "alpha", "--start", "2026-10-05", "--end", "2026-10-09")
        self.assertIn("- done 2026-10-06 · P1 · Added before, done inside\n", out)
        self.assertNotIn("Added inside, done after", out)

    def test_evidence_filters_by_date_and_prints_its_fields(self):
        self.project("alpha", "Alpha", evidence_md=evidence(
            evidence_item("Inside the frame", "2026-10-07", "Errors fell from 2.1% to 0.4%.",
                          refs="[Dashboard](https://example.com/d), [Doc](https://example.com/x)"),
            evidence_item("Outside the frame", "2026-09-30", "Old impact."),
            "## Nested references\n\n- **Date:** 2026-10-08\n- **Impact:** Nested impact.\n"
            "- **Impact status:** delivered\n- **References:**\n"
            "  - [One](https://example.com/1)\n  - [Two](https://example.com/2)\n",
        ))
        out = self.ok("--project", "alpha", "--start", "2026-10-05", "--end", "2026-10-09")
        self.assertIn(
            "- 2026-10-07 · measured · Inside the frame\n"
            "  Impact: Errors fell from 2.1% to 0.4%.\n"
            "  References: [Dashboard](https://example.com/d), [Doc](https://example.com/x)\n",
            out)
        self.assertIn(
            "- 2026-10-08 · delivered · Nested references\n"
            "  Impact: Nested impact.\n"
            "  References:\n"
            "    - [One](https://example.com/1)\n"
            "    - [Two](https://example.com/2)\n",
            out)
        self.assertNotIn("Outside the frame", out)
        self.assertNotIn("Old impact", out)

    # --- open actions --------------------------------------------------------

    def test_project_prints_open_actions_with_notes_in_progress_first(self):
        self.project("alpha", "Alpha", actions(
            progress=["- Build the form · P0 · added 2026-09-28",
                      "  - Half the fields are done."],
            todo=["- Write the plan · ops review · P2 · added 2026-10-05",
                  "- Add saved cards · P1 · added 2026-10-06",
                  "  - Waiting on the vault contract."],
            done=["- Map the flow · P1 · added 2026-09-14 · done 2026-09-21"],
        ))
        out = self.ok("--project", "alpha", "--start", "2026-10-05", "--end", "2026-10-09")
        self.assertIn(
            "Open actions:\n"
            "- in progress · P0 · Build the form\n"
            "    - Half the fields are done.\n"
            "- to do · P2 · Write the plan · ops review\n"
            "- to do · P1 · Add saved cards\n"
            "    - Waiting on the vault contract.\n",
            out)
        # The out-of-frame done action is neither done-in-frame nor open.
        self.assertNotIn("Map the flow", out)

    # --- --all -----------------------------------------------------------------

    def test_all_omits_quiet_projects_and_keeps_folder_order(self):
        # Created out of order on disk; output must follow folder names.
        self.project("gamma", "Gamma", evidence_md=evidence(
            evidence_item("Gamma win", "2026-10-03", "Gamma impact.")))
        self.project("beta-quiet", "Beta Quiet", actions(
            todo=["- Beta open work · P1 · added 2026-10-02"],
            done=["- Beta old work · P1 · added 2026-09-01 · done 2026-09-10"],
        ), evidence(evidence_item("Beta old win", "2026-09-11", "Old.")))
        self.project("alpha", "Alpha", actions(
            todo=["- Alpha open work · P2 · added 2026-10-02"],
            done=["- Alpha shipped · P1 · added 2026-09-01 · done 2026-10-02"],
        ))
        out = self.ok("--all", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertIn("Project: Alpha (alpha)\n", out)
        self.assertIn("Project: Gamma (gamma)\n", out)
        self.assertLess(out.index("Project: Alpha (alpha)"), out.index("Project: Gamma (gamma)"))
        self.assertNotIn("Beta", out)
        self.assertNotIn("beta-quiet", out)
        # --all never lists open actions.
        self.assertNotIn("Open actions", out)
        self.assertNotIn("Alpha open work", out)
        self.assertIn("- done 2026-10-02 · P1 · Alpha shipped\n", out)
        self.assertIn("- 2026-10-03 · measured · Gamma win\n", out)

    def test_all_with_nothing_in_frame_prints_only_the_frame_line(self):
        self.project("alpha", "Alpha", actions(
            todo=["- Open work · P1 · added 2026-10-02"],
            done=["- Old work · P1 · added 2026-09-01 · done 2026-09-10"],
        ))
        out = self.ok("--all", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertEqual(out, "Frame: 2026-10-01 to 2026-10-08\n")

    def test_project_with_nothing_in_frame_still_prints_project_and_open_actions(self):
        self.project("alpha", "Alpha", actions(
            progress=["- Running work · P0 · added 2026-09-28"],
            todo=["- Open work · P1 · added 2026-10-02"],
            done=["- Old work · P1 · added 2026-09-01 · done 2026-09-10"],
        ))
        out = self.ok("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertIn("Frame: 2026-10-01 to 2026-10-08\n", out)
        self.assertIn("Project: Alpha (alpha)\n", out)
        self.assertIn("Done actions in frame:\n- None\n", out)
        self.assertIn("Evidence in frame:\n- None\n", out)
        self.assertIn("- in progress · P0 · Running work\n", out)
        self.assertIn("- to do · P1 · Open work\n", out)
        self.assertNotIn("Old work", out)

    def test_project_with_no_actions_file_prints_none_for_open_actions(self):
        self.project("alpha", "Alpha")
        out = self.ok("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertIn("Open actions:\n- None\n", out)

    # --- default start --------------------------------------------------------

    def test_default_start_is_newest_report_before_end(self):
        self.project("alpha", "Alpha", reports=(
            "2026-10-01.md", "2026-10-09.md", "2026-10-20.md", "notes.md", "chart.csv"))
        out = self.ok("--project", "alpha", "--end", "2026-10-12")
        self.assertIn("Frame: 2026-10-09 to 2026-10-12\n", out)

    def test_default_start_skips_a_report_dated_on_end(self):
        self.project("alpha", "Alpha", reports=("2026-10-01.md", "2026-10-09.md", "2026-10-12.md"))
        out = self.ok("--project", "alpha", "--end", "2026-10-12")
        self.assertIn("Frame: 2026-10-09 to 2026-10-12\n", out)

    def test_no_earlier_status_report_exits_3(self):
        self.project("alpha", "Alpha")
        r = self.exits(3, "--project", "alpha", "--end", "2026-10-12")
        self.assertEqual(r.stdout, "")
        self.assertIn("start date", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_only_a_report_dated_on_end_exits_3(self):
        self.project("alpha", "Alpha", reports=("2026-10-12.md", "notes.md"))
        self.exits(3, "--project", "alpha", "--end", "2026-10-12")

    def test_given_start_needs_no_status_report(self):
        self.project("alpha", "Alpha")
        out = self.ok("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-12")
        self.assertIn("Frame: 2026-10-01 to 2026-10-12\n", out)

    # --- exit 2 ----------------------------------------------------------------

    def test_bad_input_exits_2(self):
        self.project("alpha", "Alpha", reports=("2026-10-01.md",))
        cases = {
            "unknown slug": ["--project", "nope", "--end", "2026-10-12"],
            "path slug": ["--project", "../alpha", "--end", "2026-10-12"],
            "unreal end": ["--project", "alpha", "--end", "2026-02-30"],
            "unreal start": ["--all", "--start", "2026-13-01", "--end", "2026-10-12"],
            "malformed date": ["--project", "alpha", "--end", "12/10/2026"],
            "start after end": ["--all", "--start", "2026-10-12", "--end", "2026-10-01"],
            "project start after end": ["--project", "alpha", "--start", "2026-10-12",
                                        "--end", "2026-10-01"],
            "both": ["--project", "alpha", "--all", "--start", "2026-10-01",
                     "--end", "2026-10-12"],
            "neither": ["--start", "2026-10-01", "--end", "2026-10-12"],
            "all without start": ["--all", "--end", "2026-10-12"],
            "no end": ["--project", "alpha"],
        }
        for label, args in cases.items():
            with self.subTest(label):
                r = self.exits(2, *args)
                self.assertNotIn("Frame:", r.stdout)

    def test_no_devos_marker_exits_2(self):
        self.project("alpha", "Alpha")
        os.remove(os.path.join(self.repo, ".devos"))
        r = self.exits(2, "--all", "--start", "2026-10-01", "--end", "2026-10-12")
        self.assertIn(".devos", r.stderr)

    def test_missing_folder_exits_2(self):
        self.exits(2, "--all", "--start", "2026-10-01", "--end", "2026-10-12",
                   repo=os.path.join(self.repo, "missing"))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root opens any file")
    def test_unopenable_file_exits_2_before_a_missing_start(self):
        # Exit 2 outranks exit 3: a file that cannot be opened is reported
        # first, even when the project also has no earlier status report.
        self.project("alpha", "Alpha", actions_md=actions(todo=["- Task · P1 · added 2026-10-01"]))
        path = os.path.join(self.repo, "projects", "alpha", "actions.md")
        os.chmod(path, 0)
        self.addCleanup(os.chmod, path, 0o644)
        r = self.exits(2, "--project", "alpha", "--end", "2026-10-12")
        self.assertIn("actions.md", r.stderr)

    # --- exit 1 ----------------------------------------------------------------

    def assert_unreadable(self, r, rel, line, word):
        self.assertEqual(r.returncode, 1, self.describe(r))
        self.assertNotIn("Frame:", r.stdout)
        hits = [l for l in r.stderr.splitlines() if l.startswith("{}:{}: ".format(rel, line))]
        self.assertTrue(hits, self.describe(r))
        self.assertIn(word, hits[0])

    def test_unreadable_action_line_exits_1(self):
        text = actions(todo=["- No priority or date here"],
                       done=["- Fine · P1 · added 2026-09-01 · done 2026-10-02"])
        self.project("alpha", "Alpha", text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/actions.md",
                               line_of(text, "No priority"), "action-line")

    def test_done_line_without_done_date_exits_1(self):
        text = actions(done=["- Shipped it · P1 · added 2026-09-01"])
        self.project("alpha", "Alpha", text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/actions.md",
                               line_of(text, "Shipped it"), "action-line")

    def test_unreal_action_date_exits_1(self):
        text = actions(done=["- Shipped it · P1 · added 2026-09-01 · done 2026-10-32"])
        self.project("alpha", "Alpha", text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/actions.md",
                               line_of(text, "Shipped it"), "date")

    def test_unreal_evidence_date_exits_1(self):
        text = evidence(evidence_item("Good one", "2026-10-02", "Fine."),
                        evidence_item("Bad date", "2026-02-30", "Broken."))
        self.project("alpha", "Alpha", evidence_md=text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/evidence.md",
                               line_of(text, "2026-02-30"), "date")

    def test_evidence_item_without_date_exits_1_at_its_heading(self):
        text = evidence(evidence_item("Good one", "2026-10-02", "Fine."),
                        evidence_item("No date at all", None, "Undated."))
        self.project("alpha", "Alpha", evidence_md=text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/evidence.md",
                               line_of(text, "## No date at all"), "Date")

    def test_evidence_item_with_empty_date_exits_1_at_its_heading(self):
        text = evidence(evidence_item("Empty date", "", "Undated."))
        self.project("alpha", "Alpha", evidence_md=text)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/alpha/evidence.md",
                               line_of(text, "## Empty date"), "Date")

    def test_project_scope_ignores_other_projects_but_all_does_not(self):
        bad = actions(todo=["- Broken line"])
        self.project("alpha", "Alpha", actions(
            done=["- Alpha shipped · P1 · added 2026-09-01 · done 2026-10-02"]))
        self.project("zeta", "Zeta", bad)
        self.ok("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        r = self.run_window("--all", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assert_unreadable(r, "projects/zeta/actions.md",
                               line_of(bad, "Broken line"), "action-line")

    def test_defects_other_than_action_line_and_date_do_not_block(self):
        # check.py flags these as `priority` and `done-date`, not as unreadable.
        self.project("alpha", "Alpha", actions(done=[
            "- Odd priority · P9 · added 2026-09-01 · done 2026-10-02",
            "- Done before added · P1 · added 2026-10-05 · done 2026-10-03",
        ]))
        out = self.ok("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertIn("- done 2026-10-02 · P9 · Odd priority\n", out)
        self.assertIn("- done 2026-10-03 · P1 · Done before added\n", out)

    def test_all_problems_are_listed_together(self):
        acts = actions(todo=["- Broken one"], done=["- Broken two · P1 · added 2026-09-01"])
        evs = evidence(evidence_item("Bad date", "2026-02-30", "x"))
        self.project("alpha", "Alpha", acts, evs)
        r = self.run_window("--project", "alpha", "--start", "2026-10-01", "--end", "2026-10-08")
        self.assertEqual(r.returncode, 1, self.describe(r))
        lines = r.stderr.strip().splitlines()
        self.assertEqual(len(lines), 3, r.stderr)
        self.assertTrue(lines[0].startswith("projects/alpha/actions.md:"), r.stderr)
        self.assertTrue(lines[2].startswith("projects/alpha/evidence.md:"), r.stderr)


if __name__ == "__main__":
    unittest.main()
