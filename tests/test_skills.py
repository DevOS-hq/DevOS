"""Tests for tests/skill_lint.py and for the real skills under skills/.

Every planted case starts from a known-good skill, changes exactly one
thing, writes it to a temp folder, and asserts the lint fails with that
case's own rule id and no other. The good base passes clean, a skill named
`writing` is exempt from the "names X" rules, and every real skills/*/
folder must lint clean and match EXPECTED_SKILLS. Every real SKILL.md must
pass scripts/banned.py, and the `writing` skill must quote, in code, an
example of every banned.py category. Standard library only; runs under
Python 3.9.

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
SKILLS = os.path.join(ROOT, "skills")
LINT = os.path.join(HERE, "skill_lint.py")
SCRIPTS = os.path.join(ROOT, "scripts")
BANNED = os.path.join(SCRIPTS, "banned.py")
WRITING_SKILL = os.path.join(SKILLS, "writing", "SKILL.md")

for _path in (HERE, SCRIPTS):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import banned  # noqa: E402
import skill_lint  # noqa: E402

# The skills that must exist under skills/. Each wave that adds a skill adds
# its folder name here, so a missing or stray skill folder fails the suite:
#   wave 2 adds "writing", wave 3 adds "init", phase 03 adds the project and
#   action skills, phase 04 adds the evidence and report skills, phase 05 adds
#   "create-spec".
EXPECTED_SKILLS = {"writing", "init", "create-project", "update-project", "add-action",
                   "update-action", "record-evidence", "write-status-report",
                   "write-progress-report", "create-spec"}

# Steps the project and action skills must name in their body. Every one tests
# for `.devos`, points to `init` (in backticks, so "initial" does not count) and
# commits by path. The two action skills take today from the shell, and
# update-project renames a folder with git mv.
ACTION_SKILL_STEPS = (".devos", "`init`", "git add --", "git commit -m")
EXTRA_STEPS = {
    "create-project": (),
    "update-project": ("git mv",),
    "add-action": ("date +%F",),
    "update-action": ("date +%F",),
}


def missing_steps(skill, text):
    """The required steps that the body of SKILL.md `text` never names."""
    _, body, _ = skill_lint.split_skill(text)
    body = "\n".join(body)
    return [step for step in ACTION_SKILL_STEPS + EXTRA_STEPS[skill] if step not in body]


# Steps the evidence and report skills must name in their body (phase 04 AC2).
# All three test for `.devos`, point to `init`, commit by path and take today
# from the shell. The report skills run window.py and, on one line, say they
# write nothing without python3. record-evidence names both impact statuses
# and the `none` answer for References.
EVIDENCE_REPORT_STEPS = (".devos", "`init`", "git add --", "git commit -m", "date +%F")
EVIDENCE_REPORT_EXTRA = {
    "record-evidence": ("`delivered`", "`measured`", "`none`"),
    "write-status-report": ("window.py",),
    "write-progress-report": ("window.py",),
}
REPORT_SKILLS = ("write-status-report", "write-progress-report")
NO_PYTHON_LINE = "a line naming both python3 and nothing"


def missing_evidence_report_steps(skill, text):
    """The phase 04 steps that the body of SKILL.md `text` never names."""
    _, body, _ = skill_lint.split_skill(text)
    joined = "\n".join(body)
    missing = [step for step in EVIDENCE_REPORT_STEPS + EVIDENCE_REPORT_EXTRA[skill]
               if step not in joined]
    if skill in REPORT_SKILLS and not any("python3" in line and "nothing" in line
                                          for line in body):
        missing.append(NO_PYTHON_LINE)
    return missing


# Steps create-spec must name in its body (phase 05 AC2). It tests for
# `.devos`, points to `init`, commits by path, names the spec's Open questions
# and the brief's Still open, and links brief items to spec.md#<anchor>. Four
# rules must each sit on one line: the three-round cap, the outline step, an
# "I don't know" answer going to Open questions, and the brief's plain terms.
# A lowercase word matches in any case; `Open questions` matches as written.
CREATE_SPEC_STEPS = (".devos", "`init`", "git add --", "git commit -m",
                     "Open questions", "Still open", "spec.md#")
CREATE_SPEC_LINES = (("three", "round"), ("outline",), ("know", "Open questions"),
                     ("acronym",))


def line_holds(line, words):
    """Whether `line` holds every word, lowercase words in any case."""
    return all((w in line.lower()) if w == w.lower() else (w in line) for w in words)


def missing_create_spec_steps(text):
    """The phase 05 steps that the body of create-spec's SKILL.md `text` never names."""
    _, body, _ = skill_lint.split_skill(text)
    joined = "\n".join(body)
    missing = [step for step in CREATE_SPEC_STEPS if step not in joined]
    for words in CREATE_SPEC_LINES:
        if not any(line_holds(line, words) for line in body):
            missing.append("a line naming " + " and ".join(words))
    return missing


BASE_NAME = "sample-skill"
BASE_DESCRIPTION = (
    "Add a sample record to the state repo. Use when the user asks to add a sample."
)
BASE_BODY = """
# Add a sample

1. Load the `writing` skill before you write any prose, commit messages included.
2. Read `../../FORMAT.md` for the record layout.
3. Ask for any required field the user did not give. Never invent one.
4. Write the record.
5. Run `python3 ../../scripts/check.py .` and fix what it reports.
   If python3 is missing, skip the check and say so.
6. Commit the files you touched, and push when a remote exists.
"""


def skill_text(name=BASE_NAME, description=BASE_DESCRIPTION, extra_frontmatter="",
               body=BASE_BODY):
    """A SKILL.md built from parts. Pass None to drop `name` or `description`."""
    lines = ["---"]
    if name is not None:
        lines.append("name: " + name)
    if description is not None:
        lines.append("description: " + description)
    if extra_frontmatter:
        lines.append(extra_frontmatter)
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def body_without(*pairs):
    """BASE_BODY with each (old, new) replacement applied; the old text must exist."""
    body = BASE_BODY
    for old, new in pairs:
        assert old in body, old
        body = body.replace(old, new)
    return body


# A base that pushes. It runs the remote check before its first `git push`,
# quotes the attestation question word for word, carries the fail-closed
# sentence and never runs a bare `git push`, so it passes `names-remote`.
QUESTION = ("Is `<url>` a private repository on your company's Git host, "
            "under your work account?")
FAIL_CLOSED = "Any other exit, or no `python3`: don't push, and say why in your reply."
PUSH_BODY = BASE_BODY + """
## Push

Run `git remote`. If it prints nothing, don't push.

1. From the state repo root, run the plugin's remote check, `../../scripts/remote.py`, with its
   full path: `python3 /path/to/plugin/scripts/remote.py check`.
2. Exit 0: run `git push -u <remote> HEAD` with the remote it named.
3. Exit 3: ask the user, word for word: "%s" Only a clear yes counts.
4. Exit 1: don't push.
5. %s
""" % (QUESTION, FAIL_CLOSED)


def push_body_without(*pairs):
    """PUSH_BODY with each (old, new) replacement applied; the old text must exist."""
    body = PUSH_BODY
    for old, new in pairs:
        assert old in body, old
        body = body.replace(old, new)
    return body


# One planted case per `names-remote` clause, with a word its message must hold.
REMOTE_CLAUSES = {
    "a-no-remote-check": (
        push_body_without(("`../../scripts/remote.py`", "the remote check"),
                          ("/path/to/plugin/scripts/remote.py", "/path/to/plugin/remote")),
        "remote.py",
    ),
    "a-remote-check-after-push": (
        push_body_without(
            ("1. From the state repo root, run the plugin's remote check, "
             "`../../scripts/remote.py`, with its\n   full path: "
             "`python3 /path/to/plugin/scripts/remote.py check`.\n", ""),
            ("\n5. Any other exit", "\n5. Then run `../../scripts/remote.py check`. Any other exit")),
        "remote.py",
    ),
    "b-question-reworded": (
        push_body_without((QUESTION, "Is `<url>` private?")),
        "question",
    ),
    "c-no-fail-closed": (
        push_body_without((FAIL_CLOSED, "Otherwise, don't push.")),
        "fail-closed",
    ),
    "d-bare-git-push": (
        push_body_without(("4. Exit 1: don't push.", "4. Exit 1: don't push. Never run `git push`.")),
        "bare",
    ),
}

LONG_NAME = "a" * 65
SHORT_ENOUGH_NAME = "a" * 64

# rule id -> (folder name, SKILL.md text). One planted bad skill per rule.
CASES = {
    "missing-name": (BASE_NAME, skill_text(name=None)),
    "missing-description": (BASE_NAME, skill_text(description=None)),
    "name-pattern": ("Bad_Name", skill_text(name="Bad_Name")),
    "name-length": (LONG_NAME, skill_text(name=LONG_NAME)),
    "name-folder": ("other-skill", skill_text()),
    "description-length": (BASE_NAME, skill_text(description="x" * 1025)),
    "description-hash": (
        BASE_NAME,
        skill_text(description="Add a sample record for issue #12 to the state repo."),
    ),
    "description-colon": (
        BASE_NAME,
        skill_text(description="Add a sample record. Use when: the user asks for one."),
    ),
    "body-length": (
        BASE_NAME,
        skill_text(body=BASE_BODY + "".join("Filler line %d.\n" % i for i in range(200))),
    ),
    "disable-model-invocation": (
        BASE_NAME,
        skill_text(extra_frontmatter="disable-model-invocation: true"),
    ),
    "plugin-root-var": (
        BASE_NAME,
        skill_text(body=BASE_BODY + "\nAlso read `${CLAUDE_PLUGIN_ROOT}/README.md`.\n"),
    ),
    "skill-dir-var": (
        BASE_NAME,
        skill_text(body=BASE_BODY + "\nAlso read `${CLAUDE_SKILL_DIR}/notes.md`.\n"),
    ),
    "names-writing": (
        BASE_NAME,
        skill_text(body=body_without(("the `writing` skill", "the style rules"))),
    ),
    "names-check": (
        BASE_NAME,
        skill_text(body=body_without(("../../scripts/check.py", "the checker"))),
    ),
    "names-python3": (
        BASE_NAME,
        skill_text(body=body_without(("python3", "python"))),
    ),
    "names-format": (
        BASE_NAME,
        skill_text(body=body_without(("../../FORMAT.md", "the format reference"))),
    ),
    "names-remote": (BASE_NAME, skill_text(body=REMOTE_CLAUSES["a-no-remote-check"][0])),
    "frontmatter": (BASE_NAME, BASE_BODY),
    "skill-file": (BASE_NAME, None),
}

# The 15 cases the acceptance criteria list; the other two are extra.
AC_CASES = {
    "missing-name", "missing-description", "name-pattern", "name-length",
    "name-folder", "description-length", "description-hash", "body-length",
    "disable-model-invocation", "plugin-root-var", "skill-dir-var",
    "names-writing", "names-check", "names-python3", "names-format",
}


class PlantedSkills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def plant(self, folder, text):
        d = os.path.join(self.tmp, folder)
        os.makedirs(d)
        if text is not None:
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(text)
        return d

    def rule_ids(self, skill_dir):
        return [rule for rule, _ in skill_lint.lint_skill(skill_dir)]

    def assert_only_rule(self, rule):
        folder, text = CASES[rule]
        found = self.rule_ids(self.plant(folder, text))
        self.assertEqual(found, [rule], "planted %s case" % rule)

    def test_good_base_passes(self):
        self.assertEqual(skill_lint.lint_skill(self.plant(BASE_NAME, skill_text())), [])

    def test_64_char_name_passes(self):
        d = self.plant(SHORT_ENOUGH_NAME, skill_text(name=SHORT_ENOUGH_NAME))
        self.assertEqual(self.rule_ids(d), [])

    def test_200_line_body_passes(self):
        filler = 200 - len(BASE_BODY.splitlines())
        body = BASE_BODY + "".join("Filler line %d.\n" % i for i in range(filler))
        self.assertEqual(len(body.splitlines()), 200)
        self.assertEqual(self.rule_ids(self.plant(BASE_NAME, skill_text(body=body))), [])

    def test_quoted_or_folded_hash_description_passes(self):
        quoted = skill_text(name="quoted", description='"Add a sample record for issue #12."')
        self.assertEqual(self.rule_ids(self.plant("quoted", quoted)), [])
        folded = skill_text(name="folded",
                            description=">\n  Add a sample record\n  for issue #12.")
        self.assertEqual(self.rule_ids(self.plant("folded", folded)), [])

    def test_colon_with_no_space_or_quoted_passes(self):
        text = skill_text(description="Add a sample record at 10:30 from https://example.com.")
        self.assertEqual(self.rule_ids(self.plant(BASE_NAME, text)), [])
        quoted = skill_text(name="quoted", description='"Use when: the user asks for one."')
        self.assertEqual(self.rule_ids(self.plant("quoted", quoted)), [])

    def test_unquoted_colon_space_in_description(self):
        self.assert_only_rule("description-colon")

    def test_hash_with_no_space_passes(self):
        text = skill_text(description="Add a sample record in C# style.")
        self.assertEqual(self.rule_ids(self.plant(BASE_NAME, text)), [])

    def test_every_rule_has_a_planted_case(self):
        self.assertEqual(set(CASES), set(skill_lint.RULES))
        self.assertEqual(len(AC_CASES), 15)
        self.assertTrue(AC_CASES <= set(CASES))

    # One test per planted case; each must fail with its own rule id only.
    def test_missing_name(self):
        self.assert_only_rule("missing-name")

    def test_missing_description(self):
        self.assert_only_rule("missing-description")

    def test_name_breaks_pattern(self):
        self.assert_only_rule("name-pattern")

    def test_name_over_64_chars(self):
        self.assert_only_rule("name-length")

    def test_name_differs_from_folder(self):
        self.assert_only_rule("name-folder")

    def test_description_over_1024_chars(self):
        self.assert_only_rule("description-length")

    def test_unquoted_hash_in_description(self):
        self.assert_only_rule("description-hash")

    def test_body_over_200_lines(self):
        self.assert_only_rule("body-length")

    def test_disable_model_invocation(self):
        self.assert_only_rule("disable-model-invocation")

    def test_plugin_root_variable(self):
        self.assert_only_rule("plugin-root-var")

    def test_skill_dir_variable(self):
        self.assert_only_rule("skill-dir-var")

    def test_never_names_writing(self):
        self.assert_only_rule("names-writing")

    def test_never_names_check_script(self):
        self.assert_only_rule("names-check")

    def test_never_names_python3(self):
        self.assert_only_rule("names-python3")

    def test_never_names_format(self):
        self.assert_only_rule("names-format")

    def test_pushes_without_remote_check(self):
        self.assert_only_rule("names-remote")

    def test_good_pushing_base_passes(self):
        self.assertEqual(skill_lint.lint_skill(self.plant(BASE_NAME, skill_text(body=PUSH_BODY))),
                         [])

    def test_each_names_remote_clause_fails_alone(self):
        for clause, (body, word) in sorted(REMOTE_CLAUSES.items()):
            with self.subTest(clause=clause):
                found = skill_lint.lint_skill(self.plant(clause, skill_text(name=clause, body=body)))
                self.assertEqual([rule for rule, _ in found], ["names-remote"], found)
                self.assertIn(word, found[0][1])

    def test_lint_constants_match_the_fixed_strings(self):
        self.assertEqual(skill_lint.QUESTION, QUESTION)
        self.assertEqual(skill_lint.FAIL_CLOSED, FAIL_CLOSED)

    def test_names_remote_ignores_a_body_that_never_pushes(self):
        # BASE_BODY says "push when a remote exists" but never `git push`.
        self.assertNotIn("git push", BASE_BODY)
        self.assertEqual(self.rule_ids(self.plant(BASE_NAME, skill_text())), [])

    def test_writing_skill_is_exempt_from_names_remote(self):
        body = "\n# Writing\n\nNever write `git push` in a commit message.\n"
        d = self.plant("writing", skill_text(name="writing", body=body))
        self.assertEqual(self.rule_ids(d), [])

    def test_no_frontmatter(self):
        self.assert_only_rule("frontmatter")

    def test_no_skill_file(self):
        self.assert_only_rule("skill-file")

    def test_bad_name_patterns(self):
        for bad in ("-lead", "trail-", "double--dash", "Upper", "under_score", "dot.ted"):
            with self.subTest(name=bad):
                d = self.plant(bad, skill_text(name=bad))
                self.assertEqual(self.rule_ids(d), ["name-pattern"])

    def test_empty_description_fails_length(self):
        d = self.plant(BASE_NAME, skill_text(description='""'))
        self.assertEqual(self.rule_ids(d), ["description-length"])

    def test_writing_word_alone_is_not_a_skill_reference(self):
        body = body_without(
            ("Load the `writing` skill before you write any prose",
             "Avoid rewriting old records before writing any prose"),
        )
        d = self.plant(BASE_NAME, skill_text(body=body))
        self.assertEqual(self.rule_ids(d), ["names-writing"])

    def test_writing_reference_forms_pass(self):
        forms = ("Load the writing skill", "Load `devos:writing`", "Load `writing`")
        for i, form in enumerate(forms):
            with self.subTest(form=form):
                body = body_without(("Load the `writing` skill", form))
                name = "case-%d" % i
                d = self.plant(name, skill_text(name=name, body=body))
                self.assertEqual(self.rule_ids(d), [])

    def test_writing_skill_is_exempt_from_names_rules(self):
        body = "\n# Writing\n\nUse plain words. Name the actor. Cut filler.\n"
        d = self.plant("writing", skill_text(name="writing", body=body))
        self.assertEqual(self.rule_ids(d), [])

    def test_writing_skill_still_gets_other_rules(self):
        body = "\n# Writing\n\nRead `${CLAUDE_PLUGIN_ROOT}/x.md`.\n"
        d = self.plant("writing", skill_text(name="writing", body=body))
        self.assertEqual(self.rule_ids(d), ["plugin-root-var"])


class LintCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def run_lint(self, *args):
        return subprocess.run([sys.executable, LINT] + list(args),
                              capture_output=True, text=True)

    def plant(self, folder, text):
        d = os.path.join(self.tmp, folder)
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(text)
        return d

    def test_clean_skill_exits_0(self):
        r = self.run_lint(self.plant(BASE_NAME, skill_text()))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "")

    def test_bad_skill_exits_1_with_rule_line(self):
        folder, text = CASES["names-format"]
        d = self.plant(folder, text)
        r = self.run_lint(d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(),
                         [os.path.join(d, "SKILL.md") + ": names-format: "
                          + skill_lint.RULES["names-format"]])

    def test_no_args_exits_2(self):
        self.assertEqual(self.run_lint().returncode, 2)

    def test_missing_dir_exits_2(self):
        self.assertEqual(self.run_lint(os.path.join(self.tmp, "nope")).returncode, 2)


def real_skill_dirs():
    if not os.path.isdir(SKILLS):
        return []
    return sorted(
        os.path.join(SKILLS, n) for n in os.listdir(SKILLS)
        if not n.startswith(".") and os.path.isdir(os.path.join(SKILLS, n))
    )


class RealSkills(unittest.TestCase):
    def test_every_real_skill_lints_clean(self):
        for d in real_skill_dirs():
            with self.subTest(skill=os.path.basename(d)):
                self.assertEqual(skill_lint.lint_skill(d), [])

    def test_skill_folders_match_expected(self):
        found = {os.path.basename(d) for d in real_skill_dirs()}
        self.assertEqual(found, EXPECTED_SKILLS)

    def test_every_real_skill_is_banned_clean(self):
        dirs = real_skill_dirs()
        self.assertTrue(dirs, "no skill folders under skills/")
        for d in dirs:
            with self.subTest(skill=os.path.basename(d)):
                r = subprocess.run([sys.executable, BANNED, os.path.join(d, "SKILL.md")],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_action_skills_name_required_steps(self):
        for skill in sorted(EXTRA_STEPS):
            with self.subTest(skill=skill):
                path = os.path.join(SKILLS, skill, "SKILL.md")
                self.assertTrue(os.path.isfile(path), "missing " + path)
                with open(path, encoding="utf-8") as fh:
                    self.assertEqual(missing_steps(skill, fh.read()), [])

    def test_required_steps_check_flags_a_missing_step(self):
        # Guards the check above: a bare "initial" is no pointer to `init`,
        # and a body without the date command fails the action skills.
        text = skill_text(name="add-action", body=(
            "\nIf `.devos` is missing, say the initial setup is needed.\n"
            "Run `git add -- <paths>` and `git commit -m \"<subject>\" -- <paths>`.\n"))
        self.assertEqual(missing_steps("add-action", text), ["`init`", "date +%F"])

    def test_evidence_and_report_skills_name_required_steps(self):
        for skill in sorted(EVIDENCE_REPORT_EXTRA):
            with self.subTest(skill=skill):
                path = os.path.join(SKILLS, skill, "SKILL.md")
                self.assertTrue(os.path.isfile(path), "missing " + path)
                with open(path, encoding="utf-8") as fh:
                    self.assertEqual(missing_evidence_report_steps(skill, fh.read()), [])

    def test_evidence_report_check_flags_a_missing_step(self):
        # Guards the check above: python3 and "nothing" on separate lines do
        # not count, and record-evidence must name `none` in code.
        report = skill_text(name="write-status-report", body=(
            "\nIf `.devos` is missing, point to the `init` skill.\n"
            "Run `date +%F`, then run window.py.\n"
            "If python3 is missing, stop.\nWrite nothing.\n"
            "Run `git add -- <paths>` and `git commit -m \"<subject>\" -- <paths>`.\n"))
        self.assertEqual(missing_evidence_report_steps("write-status-report", report),
                         [NO_PYTHON_LINE])
        evidence = skill_text(name="record-evidence", body=(
            "\nIf `.devos` is missing, point to the `init` skill. Run `date +%F`.\n"
            "The status is `delivered` or `measured`. References may be none.\n"
            "Run `git add -- <paths>` and `git commit -m \"<subject>\" -- <paths>`.\n"))
        self.assertEqual(missing_evidence_report_steps("record-evidence", evidence),
                         ["`none`"])

    def test_pushing_skills_check_the_remote_and_push_to_it(self):
        # names-remote applies only to a body holding `git push`, so pin that
        # every skill but `writing` pushes, and how each one calls the check.
        for skill in sorted(EXPECTED_SKILLS - {"writing"}):
            with self.subTest(skill=skill):
                with open(os.path.join(SKILLS, skill, "SKILL.md"), encoding="utf-8") as fh:
                    _, body, _ = skill_lint.split_skill(fh.read())
                body = "\n".join(body)
                if skill == "init":
                    steps = ("scripts/remote.py check --url <url>", "scripts/remote.py confirm <url>",
                             "git push -u origin HEAD", "-- .devos")
                else:
                    steps = ("scripts/remote.py check`", "scripts/remote.py confirm <url>",
                             "git push -u <remote> HEAD", "-- .devos")
                self.assertEqual([step for step in steps if step not in body], [])

    def test_init_checks_the_push_urls_of_origin_before_it_pushes(self):
        # `check --url` sees the URL as typed; git rewrites it on push with
        # `pushInsteadOf`/`insteadOf`, and an existing `origin` may hold a
        # `pushurl`. init compares what git will push to before it pushes.
        with open(os.path.join(SKILLS, "init", "SKILL.md"), encoding="utf-8") as fh:
            _, body, _ = skill_lint.split_skill(fh.read())
        body = "\n".join(body)
        get_url = "git remote get-url --push --all origin"
        self.assertIn(get_url, body)
        self.assertLess(body.index(get_url), body.index("git push -u origin HEAD"))

    def test_create_spec_names_required_steps(self):
        path = os.path.join(SKILLS, "create-spec", "SKILL.md")
        self.assertTrue(os.path.isfile(path), "missing " + path)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(missing_create_spec_steps(fh.read()), [])

    def test_create_spec_check_flags_a_missing_step(self):
        # Guards the check above: "three" and "rounds" on separate lines do not
        # count, nor does "know" on a line without `Open questions`, nor does a
        # lowercase "open questions". Each line rule fails on its own.
        text = skill_text(name="create-spec", body=(
            "\nIf `.devos` is missing, point to the `init` skill.\n"
            "Ask at most three times.\nStop after the third of the rounds.\n"
            "Show an Outline first. Write each acronym out.\n"
            "When the user does not know, add it to open questions.\n"
            "Fill Open questions and Still open. Link each item to spec.md#goals.\n"
            "Run `git add -- <paths>` and `git commit -m \"<subject>\" -- <paths>`.\n"))
        self.assertEqual(missing_create_spec_steps(text),
                         ["a line naming three and round",
                          "a line naming know and Open questions"])
        bare = skill_text(name="create-spec", body="\nWrite the spec.\n")
        self.assertEqual(len(missing_create_spec_steps(bare)),
                         len(CREATE_SPEC_STEPS) + len(CREATE_SPEC_LINES))

    def test_writing_quotes_an_example_of_every_banned_category(self):
        # Drift guard: a category added to banned.py, or an example dropped
        # from `writing`, fails here. Examples count only inside inline code
        # or a fenced block, which banned.py skips, so `writing` stays clean.
        with open(WRITING_SKILL, encoding="utf-8") as fh:
            snippets = code_snippets(fh.read())
        self.assertTrue(snippets, "skills/writing/SKILL.md quotes nothing in code")
        found = {hit[2] for snippet in snippets for hit in banned.scan(snippet)}
        missing = [cat for cat in banned.CATEGORIES if cat not in found]
        self.assertEqual(missing, [], "banned categories with no example in writing")


def code_snippets(text):
    """The text of every inline code span and fenced block line, in file order."""
    out, fence = [], None
    for line in text.replace("\r\n", "\n").split("\n"):
        if fence:
            m = banned.FENCE_CLOSE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
            else:
                out.append(line)
            continue
        m = banned.FENCE_OPEN_RE.match(line)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        out.extend(span.group(2) for span in banned.CODE_SPAN_RE.finditer(line))
    return out


class CodeSnippets(unittest.TestCase):
    """The drift test's extractor finds code and nothing else."""

    def test_spans_and_fences_only(self):
        text = (
            "Avoid `delve` and ``a `tick` here``.\n"
            "Plain prose with crucial words.\n"
            "```text\n"
            "the future looks bright\n"
            "```\n"
            "After the fence.\n"
        )
        self.assertEqual(code_snippets(text),
                         ["delve", "a `tick` here", "the future looks bright"])

    def test_snippet_hits_map_to_categories(self):
        cats = {hit[2] for s in code_snippets("Say `—` and `etc.` here.\n")
                for hit in banned.scan(s)}
        self.assertEqual(cats, {"dash", "typography"})


if __name__ == "__main__":
    unittest.main()
