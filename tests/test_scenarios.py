"""Offline tests for the live scenario modules in tests/e2e/scenarios.

No CLI runs here. These tests prove that:
- every scenario module run.py would load meets the scenario contract (CLIS,
  START, PROMPT, ANSWERS, TIMEOUT, setup, check),
- the phase-03 project and action scenarios exist with the CLIs, start state,
  skill and answers the spec names,
- the shared helpers in scenarios/_statecheck.py read sections, fields and
  diffs correctly,
- each phase-03 check passes on a state repo shaped the way a working skill
  leaves it, and fails on the mistakes the spec guards against (a misplaced
  line, a reflowed file, a wrong date, a missing push, a turn-1 write).

The "working skill" outcomes are built by hand with git on a real copy of the
`state-repo` start, so the checks meet real files, real diffs and the real
check.py and banned.py.

Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
E2E = os.path.join(HERE, "e2e")
SCENARIOS = os.path.join(E2E, "scenarios")
if E2E not in sys.path:
    sys.path.insert(0, E2E)

import asserts  # noqa: E402
import runners  # noqa: E402


def _load_run_py():
    spec = importlib.util.spec_from_file_location("devos_e2e_run_for_scenarios", os.path.join(E2E, "run.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN_PY = _load_run_py()

if SCENARIOS not in sys.path:
    sys.path.insert(0, SCENARIOS)
import _statecheck  # noqa: E402

STARTS = {"empty", "fixture", "state-repo"}
ALL_CLIS = {"claude", "codex", "cursor"}

# name: (START, CLIS, skill named in PROMPT, ANSWERS)
PHASE_03 = {
    "create_project": ("state-repo", ("claude",), "create-project", ()),
    "update_project_requirement": ("state-repo", ("claude",), "update-project", ()),
    "add_action": ("state-repo", ("claude", "codex", "cursor"), "add-action", ()),
    "add_action_ask_priority": ("state-repo", ("claude",), "add-action", ("P1",)),
    "update_action_done": ("state-repo", ("claude",), "update-action", ()),
    "outside_state_repo": ("empty", ("claude",), "add-action", ()),
}

# name: (START, CLIS, skill named in PROMPT, ANSWERS)
PHASE_04 = {
    "record_evidence": ("state-repo", ("claude",), "record-evidence", ()),
    "write_status_report": ("state-repo", ("claude", "codex", "cursor"), "write-status-report", ()),
    "write_status_report_no_previous": ("state-repo", ("claude",), "write-status-report", ()),
    "write_progress_report": ("state-repo", ("claude",), "write-progress-report", ()),
}

# name: (START, CLIS, skill named in PROMPT, UNTIL_COMMIT, number of ANSWERS)
PHASE_05 = {
    "create_spec": ("state-repo", ("claude",), "create-spec", True, 4),
}


def scenario(name):
    found = RUN_PY.discover(RUN_PY.DEFAULT_SCENARIOS)
    if name not in found:
        raise AssertionError("no scenario module {}.py in {}".format(name, RUN_PY.DEFAULT_SCENARIOS))
    return RUN_PY.load(name, found[name])


class ScenarioContractTest(unittest.TestCase):
    def test_run_py_start_states_match(self):
        self.assertEqual(set(runners.STARTS), STARTS)
        self.assertEqual(set(runners.CLIS), ALL_CLIS)

    def test_every_scenario_meets_the_contract(self):
        found = RUN_PY.discover(RUN_PY.DEFAULT_SCENARIOS)
        self.assertTrue(found, "run.py finds no scenarios")
        for name, path in sorted(found.items()):
            with self.subTest(scenario=name):
                module = RUN_PY.load(name, path)
                clis = tuple(getattr(module, "CLIS", ("claude",)))
                self.assertTrue(clis, "CLIS is empty")
                self.assertLessEqual(set(clis), ALL_CLIS)
                self.assertIn(getattr(module, "START", "empty"), STARTS)
                self.assertTrue(callable(module.check))
                if hasattr(module, "setup"):
                    self.assertTrue(callable(module.setup))
                prompts = [module.PROMPT] + list(getattr(module, "ANSWERS", ()))
                for prompt in prompts:
                    for cli in clis:
                        text = RUN_PY.for_cli(prompt, cli)
                        self.assertIsInstance(text, str)
                        self.assertTrue(text and not text.startswith("-"), repr(text))
                timeout = getattr(module, "TIMEOUT", 900)
                self.assertIsInstance(timeout, int)
                self.assertGreater(timeout, 0)

    def test_phase_03_scenarios_exist_as_specified(self):
        for name, (start, clis, skill, answers) in sorted(PHASE_03.items()):
            with self.subTest(scenario=name):
                module = scenario(name)
                self.assertEqual(tuple(getattr(module, "CLIS", ("claude",))), clis)
                self.assertEqual(getattr(module, "START", "empty"), start)
                self.assertEqual(tuple(getattr(module, "ANSWERS", ())), answers)
                self.assertIn("Use the DevOS `{}` skill to ".format(skill), module.PROMPT)

    def test_phase_04_scenarios_exist_as_specified(self):
        for name, (start, clis, skill, answers) in sorted(PHASE_04.items()):
            with self.subTest(scenario=name):
                module = scenario(name)
                self.assertEqual(tuple(getattr(module, "CLIS", ("claude",))), clis)
                self.assertEqual(getattr(module, "START", "empty"), start)
                self.assertEqual(tuple(getattr(module, "ANSWERS", ())), answers)
                self.assertIn("Use the DevOS `{}` skill to ".format(skill), module.PROMPT)
                self.assertTrue(callable(getattr(module, "check_state", None)))

    def test_phase_04_prompts_carry_the_given_fields(self):
        prompt = scenario("record_evidence").PROMPT
        for text in ("Checkout Revamp", "Checkout errors fell after the retry fix",
                     "Checkout errors fell from 2.1% to 0.4% in the week after the retry fix.",
                     "measured", "https://example.com/dashboards/checkout-errors"):
            self.assertIn(text, prompt)
        self.assertIn("Checkout Revamp", scenario("write_status_report").PROMPT)
        self.assertIn("Search Latency", scenario("write_status_report_no_previous").PROMPT)
        self.assertIn("2026-10-01 to 2026-10-08", scenario("write_progress_report").PROMPT)

    def test_phase_05_scenarios_exist_as_specified(self):
        for name, (start, clis, skill, until_commit, answers) in sorted(PHASE_05.items()):
            with self.subTest(scenario=name):
                module = scenario(name)
                self.assertEqual(tuple(getattr(module, "CLIS", ("claude",))), clis)
                self.assertEqual(getattr(module, "START", "empty"), start)
                self.assertIs(getattr(module, "UNTIL_COMMIT", False), until_commit)
                self.assertEqual(len(getattr(module, "ANSWERS", ())), answers)
                self.assertIn("Use the DevOS `{}` skill to ".format(skill), module.PROMPT)
                self.assertTrue(callable(getattr(module, "check_state", None)))

    def test_create_spec_prompt_and_answers(self):
        module = scenario("create_spec")
        for text in ("Typo-tolerant search", "search-latency"):
            self.assertIn(text, module.PROMPT)
        first, rest = module.ANSWERS[0], module.ANSWERS[1:]
        for text in ("Problem:", "bluetooth headphnes", "Goals:", "Not doing:", "Milestones:",
                     "2026-11-20", "Risk:", "Mitigation:", "I don't know yet", module.LINK):
            self.assertIn(text, first)
        self.assertEqual(len(set(rest)), 1)
        self.assertIn("outline", rest[0])
        self.assertEqual(module.FOLDER, "projects/search-latency/specs/typo-tolerant-search")
        # One date in the user's words, and it is the milestone's target.
        self.assertEqual(sorted(set(module.spec.dates(module.SOURCE))), ["2026-11-20"])

    def test_status_report_prompts_give_no_frame(self):
        for name in ("write_status_report", "write_status_report_no_previous"):
            with self.subTest(scenario=name):
                prompt = scenario(name).PROMPT
                self.assertNotRegex(prompt, r"\d{4}-\d{2}-\d{2}")
                self.assertNotRegex(prompt.lower(), r"\bsince\b|\bframe\b|\bfrom\b")

    def test_add_action_ask_priority_gives_no_priority_in_turn_1(self):
        prompt = scenario("add_action_ask_priority").PROMPT
        self.assertNotRegex(prompt, r"\bP[0-3]\b")
        self.assertNotRegex(prompt.lower(), r"priorit")

    def test_create_project_has_a_setup_hook(self):
        self.assertTrue(callable(getattr(scenario("create_project"), "setup", None)))

    def test_helpers_are_not_scenarios(self):
        found = RUN_PY.discover(RUN_PY.DEFAULT_SCENARIOS)
        self.assertNotIn("_statecheck", found)
        self.assertNotIn("_initcheck", found)
        self.assertNotIn("_reportcheck", found)
        self.assertNotIn("_speccheck", found)


class StatecheckHelpersTest(unittest.TestCase):
    ACTIONS = (
        "# Actions\n\n## In progress\n\n- A · P0 · added 2026-01-01\n\n"
        "## To do\n\n- B · P1 · added 2026-01-02\n  - a note\n\n## Done\n"
    )

    def test_section_stops_at_the_next_heading_of_the_same_level(self):
        self.assertEqual(
            _statecheck.section(self.ACTIONS, "## To do"),
            ["", "- B · P1 · added 2026-01-02", "  - a note", ""],
        )
        self.assertEqual(_statecheck.items(_statecheck.section(self.ACTIONS, "## Done")), [])

    def test_section_includes_deeper_headings(self):
        text = "# T\n\n## Requirements\n\n### One\n\n- x\n\n## Notes\n"
        self.assertIn("### One", _statecheck.section(text, "## Requirements"))
        self.assertNotIn("## Notes", _statecheck.section(text, "## Requirements"))

    def test_section_fails_on_a_missing_or_repeated_heading(self):
        with self.assertRaises(AssertionError):
            _statecheck.section(self.ACTIONS, "## Later")
        with self.assertRaises(AssertionError):
            _statecheck.section(self.ACTIONS + "\n## Done\n", "## Done")

    def test_items_are_top_level_only(self):
        lines = _statecheck.section(self.ACTIONS, "## To do")
        self.assertEqual(_statecheck.items(lines), ["- B · P1 · added 2026-01-02"])

    def test_field_reads_inline_and_nested_values(self):
        lines = [
            "- **Type:** need",
            "- **Stakeholders:**",
            "  - Payments team",
            "  - Growth team",
            "- **Description:** One.",
            "  Two.",
        ]
        self.assertEqual(_statecheck.field(lines, "Type"), "need")
        self.assertEqual(_statecheck.field(lines, "Stakeholders"), "- Payments team\n- Growth team")
        self.assertEqual(_statecheck.field(lines, "Description"), "One.\nTwo.")
        self.assertIsNone(_statecheck.field(lines, "Priority"))

    def test_double_blank(self):
        self.assertEqual(_statecheck.double_blank("a\n\nb\n"), 0)
        self.assertEqual(_statecheck.double_blank("a\n\n\nb\n"), 3)

    def test_diff_lines_skips_file_headers(self):
        diff = (
            "diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n"
            "@@ -5 +4,0 @@\n-old line\n@@ -16,0 +16 @@\n+new line\n"
        )
        self.assertEqual(_statecheck.diff_lines(diff), (["new line"], ["old line"]))


DATE = "2026-10-12"
PINNED = "{}T12:00:00".format(DATE)


class RunBuilder(object):
    """Builds real state-repo runs and hand-made outcomes for the checks tests."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="devos-scenario-test-")
        self.addCleanup(shutil.rmtree, self.root, True)

    # building a run

    def make_run(self, start):
        run_root = tempfile.mkdtemp(prefix="run-", dir=self.root)
        state_root = tempfile.mkdtemp(prefix="state-", dir=self.root)
        gitconfig = os.path.join(run_root, "gitconfig")
        open(gitconfig, "w").close()
        env = runners.neutral_env(gitconfig)
        env["GIT_AUTHOR_DATE"] = PINNED
        env["GIT_COMMITTER_DATE"] = PINNED
        run = runners.Run("claude", run_root, state_root, env)
        shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(run.plugin_dir, "scripts"),
                        ignore=runners.COPY_IGNORE)
        runners.make("claude")._build_start(run, start)
        return run

    def read(self, run, rel):
        with open(asserts.path(run, rel), encoding="utf-8") as fh:
            return fh.read()

    def write(self, run, rel, text):
        target = asserts.path(run, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)

    def commit(self, run, subject, *rels):
        for args in (("add", "--") + rels, ("commit", "-q", "-m", subject, "--") + rels):
            result = run.git(*args)
            self.assertEqual(result.returncode, 0, result.stderr)

    def insert_after(self, text, anchor, new_lines):
        lines = text.split("\n")
        at = lines.index(anchor) + 1
        return "\n".join(lines[:at] + list(new_lines) + lines[at:])

    def passes(self, module, run):
        module.check_state(run)

    def fails(self, module, run, pattern):
        with self.assertRaisesRegex(AssertionError, pattern):
            module.check_state(run)


class Phase03ChecksTest(RunBuilder, unittest.TestCase):
    """Each phase-03 check against hand-made good and bad outcomes."""

    def test_full_check_also_demands_the_transcript(self):
        module = scenario("add_action")
        run = self.good_add_action(module)
        with self.assertRaisesRegex(AssertionError, "writing"):
            module.check(run)

    # create_project

    def good_create_project(self, module, push=True):
        run = self.make_run("state-repo")
        run.subs = module.setup(run.repo, run.state_root) or {}
        self.write(run, module.PROJECT, (
            "# Billing Alerts\n\n"
            "- **Priority:** P2\n"
            "- **Stakeholders:** Finance team, Support team\n\n"
            "## Requirements\n\n"
            "### Overdue invoice email\n\n"
            "- **Type:** need\n"
            "- **Stakeholders:** Finance team\n"
            "- **Description:** Customers get an email when an invoice is three days overdue.\n"
        ))
        self.write(run, module.ACTIONS, "# Actions\n\n## In progress\n\n## To do\n\n## Done\n")
        self.commit(run, "Add the Billing Alerts project", module.PROJECT, module.ACTIONS)
        if push:
            self.assertEqual(run.git("push", "-q").returncode, 0)
        return run

    def test_create_project_passes_when_pushed(self):
        module = scenario("create_project")
        self.passes(module, self.good_create_project(module))

    def test_create_project_fails_without_the_push(self):
        module = scenario("create_project")
        self.fails(module, self.good_create_project(module, push=False), "push never landed")

    def test_create_project_fails_on_a_non_empty_actions_file(self):
        module = scenario("create_project")
        run = self.make_run("state-repo")
        run.subs = module.setup(run.repo, run.state_root) or {}
        self.write(run, module.PROJECT, "# Billing Alerts\n\n- **Priority:** P2\n"
                   "- **Stakeholders:** Finance team, Support team\n\n## Requirements\n\n"
                   "### Overdue invoice email\n\n- **Type:** need\n- **Stakeholders:** Finance team\n"
                   "- **Description:** Customers get an email when an invoice is three days overdue.\n")
        self.write(run, module.ACTIONS, "# Actions\n\n## In progress\n\n## To do\n\n"
                   "- Draft the email · P2 · added {}\n\n## Done\n".format(DATE))
        self.commit(run, "Add the Billing Alerts project", module.PROJECT, module.ACTIONS)
        run.git("push", "-q")
        self.fails(module, run, "actions.md holds")

    # update_project_requirement

    NEW_REQUIREMENT = [
        "",
        "### Order tracking",
        "",
        "- **Type:** want",
        "- **Stakeholders:** Support team",
        "- **Description:** Shoppers can see where their order is from the confirmation email.",
    ]

    def test_update_project_requirement_passes_in_place(self):
        module = scenario("update_project_requirement")
        run = self.make_run("state-repo")
        text = self.insert_after(self.read(run, module.PROJECT), module.SAVED_CARDS_END, self.NEW_REQUIREMENT)
        self.write(run, module.PROJECT, text)
        self.commit(run, "Add the Order tracking requirement", module.PROJECT)
        self.passes(module, run)

    def test_update_project_requirement_fails_at_the_end_of_the_file(self):
        module = scenario("update_project_requirement")
        run = self.make_run("state-repo")
        text = self.read(run, module.PROJECT) + "\n".join(self.NEW_REQUIREMENT[1:]) + "\n"
        self.write(run, module.PROJECT, text)
        self.commit(run, "Add the Order tracking requirement", module.PROJECT)
        self.fails(module, run, "before ## Notes")

    def test_update_project_requirement_fails_when_a_line_is_rewritten(self):
        module = scenario("update_project_requirement")
        run = self.make_run("state-repo")
        text = self.insert_after(self.read(run, module.PROJECT), module.SAVED_CARDS_END, self.NEW_REQUIREMENT)
        self.write(run, module.PROJECT, text.replace("- **Stakeholders:** none", "- **Stakeholders:** None"))
        self.commit(run, "Add the Order tracking requirement", module.PROJECT)
        self.fails(module, run, "deletes 1")

    # add_action

    def good_add_action(self, module, line=None, anchor=None):
        run = self.make_run("state-repo")
        line = line or "- Load-test the payment API · P1 · added {}".format(DATE)
        text = self.insert_after(self.read(run, module.ACTIONS), anchor or module.NOTE, [line])
        self.write(run, module.ACTIONS, text)
        self.commit(run, "Add the payment API load-test action", module.ACTIONS)
        return run

    def test_add_action_passes_after_the_note(self):
        module = scenario("add_action")
        self.passes(module, self.good_add_action(module))

    def test_add_action_fails_before_the_note(self):
        module = scenario("add_action")
        run = self.good_add_action(module, anchor="- Add saved-card storage · P3 · added 2026-10-06")
        self.fails(module, run, "old file plus one line")

    def test_add_action_fails_on_the_wrong_date(self):
        module = scenario("add_action")
        run = self.good_add_action(module, line="- Load-test the payment API · P1 · added 2026-01-01")
        self.fails(module, run, "last item")

    def test_add_action_fails_when_a_blank_line_moves(self):
        module = scenario("add_action")
        run = self.make_run("state-repo")
        text = self.insert_after(self.read(run, module.ACTIONS), module.NOTE,
                                 ["- Load-test the payment API · P1 · added {}".format(DATE)])
        self.write(run, module.ACTIONS, text.replace("## In progress\n\n", "## In progress\n"))
        self.commit(run, "Add the payment API load-test action", module.ACTIONS)
        self.fails(module, run, "old file plus one line")

    def test_add_action_fails_with_a_second_commit(self):
        module = scenario("add_action")
        run = self.good_add_action(module)
        self.write(run, "projects/checkout-revamp/project.md",
                   self.read(run, "projects/checkout-revamp/project.md") + "\nMore notes.\n")
        self.commit(run, "Tidy the notes", "projects/checkout-revamp/project.md")
        self.fails(module, run, "expected 2 commits")

    # add_action_ask_priority

    def ask_priority_run(self, module, turn_1_text, turns=2, turn_1_commits=False):
        """A run whose last turn committed the action. Each turn carries real
        snapshots; with turn_1_commits, turn 1 made the commit instead of asking."""
        run = self.make_run("state-repo")
        start = runners.snapshot(run.repo, run.env)
        self.write(run, module.ACTIONS, (
            "# Actions\n\n## In progress\n\n## To do\n\n"
            "- Profile the slow search queries · P1 · added {}\n\n## Done\n".format(DATE)
        ))
        self.commit(run, "Add the slow-query profiling action", module.ACTIONS)
        end = runners.snapshot(run.repo, run.env)
        texts = [turn_1_text, "Added the action."][:turns]
        for index, text in enumerate(texts, 1):
            turn = runners.Turn(index, ["claude"])
            turn.text = text
            turn.before = start
            turn.after = end if index > 1 or turn_1_commits else start
            run.turns.append(turn)
        run.text = texts[-1]
        return run

    def test_add_action_ask_priority_passes(self):
        module = scenario("add_action_ask_priority")
        run = self.ask_priority_run(module, "What priority should it have: P0, P1, P2 or P3?")
        self.passes(module, run)

    def test_add_action_ask_priority_fails_when_turn_1_changed_the_repo(self):
        module = scenario("add_action_ask_priority")
        run = self.ask_priority_run(module, "What priority should it have?", turn_1_commits=True)
        self.fails(module, run, "turn 1 changed")

    def test_add_action_ask_priority_fails_when_turn_1_never_asks(self):
        module = scenario("add_action_ask_priority")
        run = self.ask_priority_run(module, "Which project did you mean?")
        self.fails(module, run, "never asks for the priority")

    def test_add_action_ask_priority_fails_without_the_answer_turn(self):
        module = scenario("add_action_ask_priority")
        run = self.ask_priority_run(module, "What priority?", turns=1)
        self.fails(module, run, "expected 2 turns")

    # update_action_done

    def done_run(self, module, keep_blank=False, done_date=DATE):
        run = self.make_run("state-repo")
        text = self.read(run, module.ACTIONS)
        drop = module.OLD + "\n" if keep_blank else module.OLD + "\n\n"
        self.assertIn(drop, text)
        text = text.replace(drop, "", 1) + "{} · done {}\n".format(module.OLD, done_date)
        self.write(run, module.ACTIONS, text)
        self.commit(run, "Mark the guest payment form done", module.ACTIONS)
        return run

    def test_update_action_done_passes(self):
        module = scenario("update_action_done")
        self.passes(module, self.done_run(module))

    def test_update_action_done_fails_on_two_blank_lines(self):
        module = scenario("update_action_done")
        self.fails(module, self.done_run(module, keep_blank=True), "two blank lines")

    def test_update_action_done_fails_on_the_wrong_done_date(self):
        module = scenario("update_action_done")
        self.fails(module, self.done_run(module, done_date="2026-10-01"), "last item")

    # outside_state_repo

    def outside_run(self, text, files=()):
        run = self.make_run("empty")
        for rel in files:
            self.write(run, rel, "x\n")
        run.text = text
        return run

    def test_outside_state_repo_passes(self):
        module = scenario("outside_state_repo")
        run = self.outside_run("This folder is not a DevOS state repo. The `init` skill sets one up.")
        self.passes(module, run)

    def test_outside_state_repo_fails_without_init(self):
        module = scenario("outside_state_repo")
        self.fails(module, self.outside_run("Run the initial setup first."), "never names")

    def test_outside_state_repo_fails_on_git_init_alone(self):
        module = scenario("outside_state_repo")
        self.fails(module, self.outside_run("Run `git init` here first."), "never names")

    def test_outside_state_repo_fails_on_a_written_file(self):
        module = scenario("outside_state_repo")
        run = self.outside_run("Use `init` first.", files=("notes/actions.md",))
        self.fails(module, run, "outside a state repo")


class ReportcheckMarkersTest(unittest.TestCase):
    """The plan's marker table against the reports' fixed text (spec review S25)."""

    FIXED = (
        "# Status report: Checkout Revamp", "# Progress report", "- **Share date:** 2026-10-12",
        "- **Time frame:** 2026-10-09 to 2026-10-12", "- **Time frame:** 2026-10-01 to 2026-10-08",
        "## Done", "## Pending", " (in progress)", "- None", "## Checkout Revamp", "## Search Latency",
        "- **Impact summary:**", "### Progress",
    )

    def all_markers(self):
        import _reportcheck as report
        found = list(report.STATUS_IN + report.STATUS_OPEN + report.STATUS_OUT + report.PROGRESS_OUT)
        for markers in report.PROGRESS_IN.values():
            found.extend(markers)
        return found

    def test_no_marker_matches_the_fixed_text(self):
        import _reportcheck as report
        for marker in self.all_markers():
            for text in self.FIXED:
                with self.subTest(marker=marker, text=text):
                    self.assertFalse(report.hits(marker, text))

    def test_markers_are_the_plan_table(self):
        import _reportcheck as report
        self.assertEqual(report.STATUS_IN, ("fraud", "beta"))
        self.assertEqual(report.STATUS_OPEN, ("payment form", "rollout plan", "refund", "saved.card", "vault"))
        self.assertEqual(report.STATUS_OUT, ("scope", "flow map|mapped", "support", "usability|prototype|9 of 10"))
        self.assertEqual(report.PROGRESS_IN, {
            "Checkout Revamp": ("scope", "usability|prototype|9 of 10"),
            "Search Latency": ("p95|820|310",),
        })
        self.assertEqual(report.PROGRESS_OUT, (
            "flow map|mapped", "support", "fraud", "beta", "region", "csv|spreadsheet", "nightly"))
        self.assertEqual(report.PROGRESS_SECTIONS, ("Checkout Revamp", "Search Latency"))

    def test_markers_are_case_insensitive(self):
        import _reportcheck as report
        self.assertTrue(report.hits("saved.card", "Store Saved Cards"))
        self.assertTrue(report.hits("saved.card", "saved-card storage"))
        self.assertFalse(report.hits("fraud", "the payment form"))


class Phase04ChecksTest(RunBuilder, unittest.TestCase):
    """Each phase-04 check against hand-made good and bad outcomes (AC6).

    The good report outcomes paraphrase the fixture's items and still carry the
    markers. None of these outcomes reads the fixture items phase 04 adds: the
    report checks read only the report file, and the evidence outcome appends
    after whatever evidence.md holds.

    Each bad report outcome is proved twice: the scenario's check_state fails,
    and the pure report check fails on the file with its own message, so a bad
    outcome that check.py also rejects still proves the marker check catches it.
    """

    # status report

    STATUS_DONE = (
        "- Every checkout order now passes through the fraud check.",
        "- The guest checkout beta went live and serves 5% of checkout traffic.",
    )
    STATUS_PENDING = (
        "- Finish the guest payment form (in progress)",
        "- Prepare the rollout plan for the ops review.",
        "- Draft the copy for the refund policy.",
        "- Store customers' saved cards once the card vault contract is signed.",
    )

    def status_text(self, done=STATUS_DONE, pending=STATUS_PENDING, start="2026-10-09", share=DATE):
        return (
            "# Status report: Checkout Revamp\n\n"
            "- **Share date:** {share}\n"
            "- **Time frame:** {start} to {share}\n\n"
            "## Done\n\n{done}\n\n"
            "## Pending\n\n{pending}\n"
        ).format(share=share, start=start, done="\n".join(done), pending="\n".join(pending))

    def status_run(self, text, file_date=DATE):
        import _reportcheck as report
        run = self.make_run("state-repo")
        rel = report.status_rel(file_date)
        self.write(run, rel, text)
        self.commit(run, "Add the Checkout Revamp status report", rel)
        return run

    def status_bad(self, pattern, **kwargs):
        import _reportcheck as report
        module = scenario("write_status_report")
        text = self.status_text(**kwargs)
        self.fails(module, self.status_run(text), ".")
        with self.assertRaisesRegex(AssertionError, pattern):
            report.status_report(text, report.STATUS_PREVIOUS, DATE)

    def test_write_status_report_passes_on_paraphrased_items(self):
        self.passes(scenario("write_status_report"), self.status_run(self.status_text()))

    def test_write_status_report_fails_on_a_missing_in_item(self):
        self.status_bad(r"## Done lacks in-frame items.*fraud", done=self.STATUS_DONE[1:])
        self.status_bad(r"## Done lacks in-frame items.*beta", done=self.STATUS_DONE[:1])

    def test_write_status_report_fails_on_an_out_item(self):
        for line in ("- Settled the guest checkout scope with payments.",
                     "- Support now works from one flow map.",
                     "- 9 of 10 testers finished a purchase."):
            with self.subTest(line=line):
                self.status_bad(r"OUT markers", done=self.STATUS_DONE + (line,))

    def test_write_status_report_fails_on_a_wrong_frame_start(self):
        self.status_bad(r"Time frame is '2026-09-25 to ", start="2026-09-25")

    def test_write_status_report_fails_on_an_open_action_under_done(self):
        self.status_bad(r"## Done lists open actions.*refund",
                        done=self.STATUS_DONE + ("- Drafted the refund policy copy.",))

    def test_write_status_report_fails_on_an_open_action_missing_from_pending(self):
        self.status_bad(r"## Pending lacks open actions.*refund", pending=(
            self.STATUS_PENDING[0], self.STATUS_PENDING[1], self.STATUS_PENDING[3]))

    def test_write_status_report_fails_on_a_dropped_blocker(self):
        pending = self.STATUS_PENDING[:3] + ("- Store customers' saved cards.",)
        self.status_bad(r"## Pending lacks open actions.*vault", pending=pending)

    def test_write_status_report_fails_on_a_done_item_under_pending(self):
        self.status_bad(r"## Pending lists done items.*fraud",
                        pending=self.STATUS_PENDING + ("- Wire the fraud check into checkout.",))

    def test_write_status_report_fails_on_a_share_date_off_the_commit_date(self):
        self.status_bad(r"Share date is '2026-10-11'", share="2026-10-11")

    def test_write_status_report_fails_on_a_file_dated_off_the_commit_date(self):
        text = self.status_text(share="2026-10-11")
        self.fails(scenario("write_status_report"), self.status_run(text, file_date="2026-10-11"),
                   "the commit holds")

    def test_write_status_report_fails_with_a_second_commit(self):
        run = self.status_run(self.status_text())
        rel = "projects/checkout-revamp/project.md"
        self.write(run, rel, self.read(run, rel) + "\nMore notes.\n")
        self.commit(run, "Tidy the notes", rel)
        self.fails(scenario("write_status_report"), run, "expected 2 commits")

    def test_write_status_report_full_check_demands_the_transcript(self):
        run = self.status_run(self.status_text())
        with self.assertRaisesRegex(AssertionError, "writing"):
            scenario("write_status_report").check(run)

    def test_window_ran_fails_without_window_py_in_the_transcript(self):
        import _reportcheck as report
        with self.assertRaisesRegex(AssertionError, "never ran .*window.py"):
            report.window_ran(self.make_run("state-repo"))

    # progress report

    CHECKOUT = (
        "Checkout Revamp",
        "Nine in ten testers finished a guest purchase on the prototype, and the team "
        "settled what guest checkout covers.",
        ("- Settled the guest checkout scope with the payments team.",
         "- A usability session saw 9 of 10 shoppers finish a guest purchase, up from 6 of 10."),
    )
    SEARCH = (
        "Search Latency",
        "Caching query plans brought p95 search latency down from 820 ms to 310 ms in staging.",
        ("- Cached query plans, cutting staging p95 latency to 310 ms.",),
    )

    def progress_text(self, sections=None, start="2026-10-01", end="2026-10-08", share=DATE):
        parts = ["# Progress report\n\n- **Share date:** {}\n- **Time frame:** {} to {}\n".format(share, start, end)]
        for name, summary, progress in sections or (self.CHECKOUT, self.SEARCH):
            block = "\n## {}\n\n".format(name)
            if summary is not None:
                block += "- **Impact summary:** {}\n\n".format(summary)
            block += "### Progress\n"
            if progress:
                block += "\n" + "\n".join(progress) + "\n"
            parts.append(block)
        return "".join(parts)

    def progress_run(self, text, file_date=DATE):
        import _reportcheck as report
        run = self.make_run("state-repo")
        rel = report.progress_rel(file_date)
        self.write(run, rel, text)
        self.commit(run, "Add the progress report for early October", rel)
        return run

    def progress_bad(self, pattern, **kwargs):
        import _reportcheck as report
        module = scenario("write_progress_report")
        text = self.progress_text(**kwargs)
        self.fails(module, self.progress_run(text), ".")
        with self.assertRaisesRegex(AssertionError, pattern):
            report.progress_report(text, DATE)

    def test_write_progress_report_passes_on_paraphrased_items(self):
        self.passes(scenario("write_progress_report"), self.progress_run(self.progress_text()))

    def test_write_progress_report_fails_on_a_missing_in_item(self):
        search = ("Search Latency", "Search got faster in staging.", ("- Cached query plans in staging.",))
        self.progress_bad(r"## Search Latency lacks in-frame items", sections=(self.CHECKOUT, search))
        checkout = (self.CHECKOUT[0], "Testers finished guest purchases more often.",
                    ("- Settled the guest checkout scope with the payments team.",))
        self.progress_bad(r"## Checkout Revamp lacks in-frame items.*usability",
                          sections=(checkout, self.SEARCH))

    def test_write_progress_report_fails_on_an_out_item(self):
        for line in ("- Wired the fraud check into checkout.", "- The guest checkout beta went live.",
                     "- Every region now serves cached results.", "- Support adopted the flow map."):
            with self.subTest(line=line):
                checkout = (self.CHECKOUT[0], self.CHECKOUT[1], self.CHECKOUT[2] + (line,))
                self.progress_bad(r"OUT markers", sections=(checkout, self.SEARCH))

    def test_write_progress_report_fails_on_a_wrong_frame_start(self):
        self.progress_bad(r"Time frame is '2026-10-02 to 2026-10-08'", start="2026-10-02")

    def test_write_progress_report_fails_on_an_extra_project_section(self):
        extra = ("Invoice Export", "Finance closes the month faster.", ("- Automated the export job.",))
        self.progress_bad(r"project sections are", sections=(self.CHECKOUT, self.SEARCH, extra))

    def test_write_progress_report_fails_on_a_missing_project_section(self):
        self.progress_bad(r"project sections are", sections=(self.CHECKOUT,))

    def test_write_progress_report_fails_on_a_section_without_an_impact_summary(self):
        search = (self.SEARCH[0], None, self.SEARCH[2] + ("- Staging p95 fell from 820 ms.",))
        self.progress_bad(r"## Search Latency has no Impact summary", sections=(self.CHECKOUT, search))

    def test_write_progress_report_fails_on_an_empty_progress_list(self):
        search = (self.SEARCH[0], self.SEARCH[1], ("- None",))
        self.progress_bad(r"## Search Latency has an empty ### Progress", sections=(self.CHECKOUT, search))

    def test_write_progress_report_fails_on_a_share_date_off_the_commit_date(self):
        self.progress_bad(r"Share date is '2026-10-11'", share="2026-10-11")

    # record_evidence

    def evidence_block(self, date=DATE, status="measured", references=None):
        module = scenario("record_evidence")
        return (
            "## {}\n\n- **Date:** {}\n- **Impact:** {}\n- **Impact status:** {}\n- **References:** {}\n"
        ).format(module.NAME, date, module.IMPACT, status,
                 references or "[Checkout errors dashboard]({})".format(module.LINK))

    def evidence_run(self, at_end=True, **kwargs):
        module = scenario("record_evidence")
        run = self.make_run("state-repo")
        old = self.read(run, module.EVIDENCE)
        block = self.evidence_block(**kwargs)
        if at_end:
            text = old + "\n" + block
        else:
            self.assertTrue(old.startswith("# Evidence\n\n"))
            text = "# Evidence\n\n" + block + "\n" + old[len("# Evidence\n\n"):]
        self.write(run, module.EVIDENCE, text)
        self.commit(run, "Record the checkout error drop", module.EVIDENCE)
        return run

    def test_record_evidence_passes(self):
        self.passes(scenario("record_evidence"), self.evidence_run())

    def test_record_evidence_fails_with_a_second_commit(self):
        module = scenario("record_evidence")
        run = self.evidence_run()
        rel = "projects/checkout-revamp/project.md"
        self.write(run, rel, self.read(run, rel) + "\nMore notes.\n")
        self.commit(run, "Tidy the notes", rel)
        self.fails(module, run, "expected 2 commits")

    def test_record_evidence_fails_on_a_non_final_item(self):
        self.fails(scenario("record_evidence"), self.evidence_run(at_end=False), "the last ## item")

    def test_record_evidence_fails_on_a_missing_link(self):
        self.fails(scenario("record_evidence"), self.evidence_run(references="none"), "lacks the link")

    def test_record_evidence_fails_on_a_wrong_impact_status(self):
        self.fails(scenario("record_evidence"), self.evidence_run(status="delivered"),
                   "Impact status is 'delivered'")

    def test_record_evidence_fails_on_a_date_off_the_commit_date(self):
        self.fails(scenario("record_evidence"), self.evidence_run(date="2026-10-11"), "Date is '2026-10-11'")

    def test_record_evidence_fails_on_a_deleted_line(self):
        module = scenario("record_evidence")
        run = self.make_run("state-repo")
        old = self.read(run, module.EVIDENCE)
        text = old.replace("# Evidence\n\n", "# Evidence\n", 1) + "\n" + self.evidence_block()
        self.write(run, module.EVIDENCE, text)
        self.commit(run, "Record the checkout error drop", module.EVIDENCE)
        self.fails(module, run, "deletes 1 lines")

    # write_status_report_no_previous

    def no_previous_run(self, text, changed=False):
        run = self.make_run("state-repo")
        start = runners.snapshot(run.repo, run.env)
        if changed:
            rel = "projects/search-latency/status-reports/{}.md".format(DATE)
            self.write(run, rel, "x\n")
        end = runners.snapshot(run.repo, run.env)
        turn = runners.Turn(1, ["claude"])
        turn.text = text
        turn.before, turn.after = start, end
        run.turns.append(turn)
        run.text = text
        return run

    def test_no_previous_passes_when_it_asks_for_a_start_date(self):
        module = scenario("write_status_report_no_previous")
        for text in ("Search Latency has no earlier status report. What start date should it cover?",
                     "There is no previous report to start from. Which time frame do you want?"):
            with self.subTest(text=text):
                self.passes(module, self.no_previous_run(text))

    def test_no_previous_fails_when_turn_1_changed_the_repo(self):
        module = scenario("write_status_report_no_previous")
        self.fails(module, self.no_previous_run("What start date?", changed=True), "turn 1 changed")

    def test_no_previous_fails_when_it_never_asks(self):
        module = scenario("write_status_report_no_previous")
        self.fails(module, self.no_previous_run("Wrote the Search Latency status report."), "never asks")


class SpeccheckMarkersTest(unittest.TestCase):
    """The create_spec markers against the spec files' fixed text and the answers (D10)."""

    FIXED = (
        "# Typo-tolerant search", "# Typo-tolerant search: brief", "# Typo-tolerant search: appendix",
        "## Summary", "## Goals", "## Non-goals", "## Milestones", "## Risks", "## Open questions",
        "## The problem", "## The goal", "## The plan", "## Not doing", "## Still open",
        "- None", "Target: 2026-11-20", "### Milestone 1: ", "### Milestone 2: ", "## Links",
        "There is no supporting material yet.", "projects/search-latency/specs/typo-tolerant-search",
        "spec.md#summary", "spec.md#goals", "spec.md#milestones", "spec.md#non-goals",
        "spec.md#open-questions",
    )

    def setUp(self):
        self.module = scenario("create_spec")
        # Each answer of ANSWERS[0] by its label: "Milestones", "Risk", ...
        self.answers = dict(line.split(":", 1) for line in self.module.ANSWERS[0].splitlines())

    def test_markers_are_the_plan_table(self):
        module = self.module
        self.assertEqual(module.MILESTONE_MARKERS, ("edit[- ]?distance", "did you mean"))
        self.assertEqual(module.RISK_MARKER, "model numbers?|digits?")
        self.assertEqual(module.NON_GOAL_MARKER, "auto-?complete")
        self.assertEqual(module.UNKNOWN_MARKER, "brands?")

    def test_no_marker_matches_the_fixed_text(self):
        for marker in self.module.MARKERS:
            for text in self.FIXED + (self.module.PROMPT, self.module.ANSWERS[1]):
                with self.subTest(marker=marker, text=text):
                    self.assertFalse(self.module.spec.hits(marker, text))

    def test_each_marker_matches_only_its_own_answer(self):
        module = self.module
        owners = {marker: "Milestones" for marker in module.MILESTONE_MARKERS}
        owners.update({module.RISK_MARKER: "Risk", module.NON_GOAL_MARKER: "Not doing",
                       module.UNKNOWN_MARKER: "Unknown"})
        for marker, owner in owners.items():
            with self.subTest(marker=marker):
                matched = sorted(label for label, text in self.answers.items()
                                 if module.spec.hits(marker, text))
                self.assertEqual(matched, [owner])

    def test_markers_are_case_insensitive(self):
        hits = self.module.spec.hits
        self.assertTrue(hits("did you mean", "A \"Did you mean\" banner"))
        self.assertTrue(hits("edit[- ]?distance", "Edit distance of two"))
        self.assertTrue(hits("auto-?complete", "Auto-complete"))


SPEC_GOOD = """# Typo-tolerant search

## Summary

Shoppers who misspell a product name land on a page with no results: a search for "bluetooth headphnes" finds nothing. Search will match product titles despite small typos and suggest the intended spelling.

## Goals

- Show results for queries with up to two typos.
- Cut the number of empty results pages by half.

## Non-goals

- The search box's autocomplete stays as it is.

## Milestones

### Milestone 1: fuzzy title matching

Product titles match within an edit distance of two. Target: 2026-11-20.

### Milestone 2: spelling suggestion banner

A "Did you mean" banner offers the corrected query.

## Risks

- Fuzzy matching may return the wrong items for model numbers like XR-200. Mitigation: queries that hold digits skip fuzzy matching.

## Open questions

- Should brand names be exempt from fuzzy matching?
"""

BRIEF_GOOD = """# Typo-tolerant search: brief

## The problem

- [Shoppers who misspell a product name see an empty results page](spec.md#summary), for example after searching for "bluetooth headphnes".

## The goal

- [Searches with one or two typos still find products](spec.md#goals), and empty results pages fall by half.

## The plan

- [First, match product titles despite small typos](spec.md#milestone-1-fuzzy-title-matching), by 2026-11-20.
- [Then suggest the intended spelling above the results](spec.md#milestone-2-spelling-suggestion-banner).

## Not doing

- [No change to the suggestions shown while typing](spec.md#non-goals).

## Still open

- [Whether brand names should be exempt](spec.md#open-questions).
"""

APPENDIX_GOOD = """# Typo-tolerant search: appendix

## Links

- [Empty-results dashboard](https://example.com/dashboards/empty-results)
"""

SPEC_QUESTIONS = (
    "Before I write the spec I need a few things. 1. What goes wrong, for whom, with an example? "
    "2. What are the goals? 3. What is out of scope? 4. What are the milestones and any target dates? "
    "5. What are the risks? 6. Any links or background for the appendix?"
)
SPEC_ROUND_2 = "Thanks. One more: what would mitigate the model number risk?"
SPEC_OUTLINE = (
    "Here is the outline for Typo-tolerant search, in "
    "projects/search-latency/specs/typo-tolerant-search/: fuzzy title matching by 2026-11-20, "
    "then a spelling banner. Shall I write it?"
)
SPEC_DONE = "Wrote the Typo-tolerant search spec and committed it."


class Phase05ChecksTest(RunBuilder, unittest.TestCase):
    """The create_spec check against hand-made good and bad outcomes (AC5).

    The good outcome paraphrases the scripted answers and still carries every
    marker. Each bad outcome changes one thing and must fail its own check,
    named in the failure message, before check.py or the commit checks could
    stand in for it.
    """

    def setUp(self):
        RunBuilder.setUp(self)
        self.module = scenario("create_spec")

    def spec_run(self, spec_text=SPEC_GOOD, brief_text=BRIEF_GOOD, appendix_text=APPENDIX_GOOD,
                 replies=(SPEC_QUESTIONS, SPEC_OUTLINE, SPEC_DONE), turn_1_writes=False,
                 extra_files=(), second_commit=False):
        """A run whose last turn committed the spec. Every earlier turn left HEAD
        as it found it; with turn_1_writes, turn 1 left the files on disk."""
        module = self.module
        run = self.make_run("state-repo")
        start = runners.snapshot(run.repo, run.env)
        written = {module.SPEC: spec_text, module.BRIEF: brief_text, module.APPENDIX: appendix_text}
        for rel, text in sorted(written.items()):
            self.write(run, rel, text)
        for rel in extra_files:
            self.write(run, rel, "x\n")
        dirty = runners.snapshot(run.repo, run.env)
        self.commit(run, "Add the Typo-tolerant search spec", *(sorted(written) + list(extra_files)))
        if second_commit:
            self.write(run, module.APPENDIX, appendix_text + "\nMore notes.\n")
            self.commit(run, "Add notes to the appendix", module.APPENDIX)
        end = runners.snapshot(run.repo, run.env)
        for index, text in enumerate(replies, 1):
            turn = runners.Turn(index, ["claude"])
            turn.text = text
            turn.before = start
            turn.after = end if index == len(replies) else start
            if index == 1 and turn_1_writes:
                turn.after = dirty
            run.turns.append(turn)
        run.text = replies[-1]
        return run

    def swap(self, text, old, new):
        self.assertIn(old, text)
        return text.replace(old, new)

    def spec_bad(self, pattern, **kwargs):
        self.fails(self.module, self.spec_run(**kwargs), pattern)

    def test_create_spec_passes_on_paraphrased_content(self):
        self.passes(self.module, self.spec_run())

    def test_create_spec_passes_after_a_second_question_round(self):
        run = self.spec_run(replies=(SPEC_QUESTIONS, SPEC_ROUND_2, SPEC_OUTLINE, SPEC_DONE))
        self.passes(self.module, run)

    def test_create_spec_full_check_demands_the_transcript(self):
        # The transcript checks run before either judge call, so this never reaches the judge.
        with self.assertRaisesRegex(AssertionError, "writing"):
            self.module.check(self.spec_run())

    # turns (AC8, AC9)

    def test_create_spec_fails_on_a_file_written_on_turn_1(self):
        self.spec_bad("turn 1 changed", turn_1_writes=True)

    def test_create_spec_fails_when_turn_1_asks_no_questions(self):
        self.spec_bad("fewer than two questions", replies=("Writing it now.", SPEC_OUTLINE, SPEC_DONE))

    def test_create_spec_fails_on_a_commit_on_the_answers_turn(self):
        self.spec_bad("commit came on turn 2", replies=(SPEC_QUESTIONS, SPEC_DONE))

    def test_create_spec_fails_without_the_folder_path_before_the_commit(self):
        outline = "Here is the outline: fuzzy title matching, then a spelling banner. Shall I write it?"
        self.spec_bad("never names the folder path", replies=(SPEC_QUESTIONS, outline, SPEC_DONE))

    def test_create_spec_fails_without_the_folder_path_after_a_question_round(self):
        # The path sits in an earlier reply, not the one just before the commit.
        replies = (SPEC_QUESTIONS, SPEC_OUTLINE, SPEC_ROUND_2, SPEC_DONE)
        self.spec_bad("turn 3's reply, before the commit, never names the folder path", replies=replies)

    # the commit

    def test_create_spec_fails_with_a_second_commit(self):
        self.spec_bad("expected 2 commits", second_commit=True)

    def test_create_spec_fails_on_a_fourth_file(self):
        notes = "projects/search-latency/specs/typo-tolerant-search/notes.md"
        self.spec_bad("the commit holds", extra_files=(notes,))

    # markers (AC11, AC12)

    def test_create_spec_fails_on_a_missing_milestone_marker(self):
        cases = (
            ("milestone 1 marker", "within an edit distance of two", "despite one or two typos"),
            ("milestone 2 marker", 'A "Did you mean" banner', "A banner"),
        )
        for pattern, old, new in cases:
            with self.subTest(pattern=pattern):
                self.spec_bad(pattern, spec_text=self.swap(SPEC_GOOD, old, new))

    def test_create_spec_fails_on_a_milestone_marker_outside_milestones(self):
        text = self.swap(SPEC_GOOD, 'A "Did you mean" banner offers', "A banner offers")
        text = self.swap(text, "- Cut the number", '- Show a "did you mean" hint.\n- Cut the number')
        self.spec_bad("milestone 2 marker", spec_text=text)

    def test_create_spec_fails_on_a_missing_risk_marker(self):
        text = self.swap(SPEC_GOOD, "for model numbers like XR-200. Mitigation: queries that hold digits "
                                    "skip fuzzy matching.", "for some queries.")
        self.spec_bad("risk marker", spec_text=text)

    def test_create_spec_fails_on_a_missing_non_goal_marker(self):
        text = self.swap(SPEC_GOOD, "- The search box's autocomplete stays as it is.", "- None")
        self.spec_bad("non-goal marker /auto-\\?complete/ is missing", spec_text=text)

    def test_create_spec_fails_on_the_non_goal_marker_under_goals(self):
        text = self.swap(SPEC_GOOD, "- Cut the number", "- Keep autocomplete as it is.\n- Cut the number")
        self.spec_bad("non-goal marker .* appears in spec.md ## Goals", spec_text=text)

    def test_create_spec_fails_on_the_unknown_point_missing_from_open_questions(self):
        text = self.swap(SPEC_GOOD, "- Should brand names be exempt from fuzzy matching?",
                         "- Should fuzzy matching cover descriptions too?")
        self.spec_bad("unknown marker .* missing from spec.md ## Open questions", spec_text=text)

    def test_create_spec_fails_on_the_unknown_point_missing_from_still_open(self):
        brief = self.swap(BRIEF_GOOD, "[Whether brand names should be exempt]",
                          "[Whether some names should be exempt]")
        self.spec_bad("unknown marker .* missing from brief.md ## Still open", brief_text=brief)

    def test_create_spec_fails_on_the_unknown_point_as_a_decision(self):
        cases = (
            ("Summary", "suggest the intended spelling.", "suggest the intended spelling. Brand names are exempt."),
            ("Goals", "- Cut the number", "- Exempt brand names.\n- Cut the number"),
            ("Non-goals", "stays as it is.", "stays as it is.\n- Matching brand names."),
            ("Milestones", "offers the corrected query.", "offers the corrected query, never for brands."),
        )
        for name, old, new in cases:
            with self.subTest(section=name):
                self.spec_bad("unknown marker .* appears in spec.md ## {}".format(name),
                              spec_text=self.swap(SPEC_GOOD, old, new))

    # dates, links, appendix (AC10, AC11)

    def test_create_spec_fails_on_a_date_not_in_the_answers(self):
        text = self.swap(SPEC_GOOD, "offers the corrected query.", "offers the corrected query. Target: 2026-12-15.")
        self.spec_bad("2026-12-15", spec_text=text)

    def test_create_spec_fails_on_a_brief_link_to_a_missing_anchor(self):
        brief = self.swap(BRIEF_GOOD, "spec.md#milestone-2-spelling-suggestion-banner",
                          "spec.md#milestone-2-did-you-mean-banner")
        self.spec_bad("matches no heading in spec.md", brief_text=brief)

    def test_create_spec_fails_on_a_brief_item_with_no_link(self):
        brief = self.swap(BRIEF_GOOD, "- [No change to the suggestions shown while typing](spec.md#non-goals).",
                          "- No change to the suggestions shown while typing.")
        self.spec_bad("links to no spec.md#<anchor>", brief_text=brief)

    def test_create_spec_fails_on_a_still_open_item_off_open_questions(self):
        brief = self.swap(BRIEF_GOOD, "exempt](spec.md#open-questions)", "exempt](spec.md#summary)")
        self.spec_bad("does not link to spec.md#open-questions", brief_text=brief)

    def test_create_spec_fails_without_the_appendix_link(self):
        appendix = "# Typo-tolerant search: appendix\n\nThere is no supporting material yet.\n"
        self.spec_bad("lacks the given link", appendix_text=appendix)


if __name__ == "__main__":
    unittest.main()
