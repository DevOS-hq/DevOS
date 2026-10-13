"""Offline tests for the LLM judge in tests/e2e/judge.py.

The judge scores a file against the `writing` skill: each `##` heading of the
skill's SKILL.md becomes one criterion, scored 1-5 or n/a. A file passes
when every scored criterion is 4 or more and at least three were scored.
Every model call here goes to a stub, so nothing touches the network.

These tests prove that:
- the criteria are the `##` headings of the SKILL.md it is given (the real
  one and a planted one), not a fixed list;
- n/a is left out of the pass rule, fewer than three scored criteria fail,
  and a single 3 fails;
- a malformed model answer raises JudgeError and never passes;
- the model call is `claude -p` with JSON output, a JSON schema,
  --strict-mcp-config, --setting-sources project,local, no plugin, model
  `sonnet` unless DEVOS_JUDGE_MODEL says otherwise, the parent session's
  variables dropped, and an empty temp folder as cwd;
- `--calibrate` exits 0 only when the sloppy sample fails and the clean
  sample passes;
- asserts.judge_pass and the writing_rewrite scenario fit the judge;
- judge_grounded passes only when it lists at least one claim, every claim
  is supported, and every evidence quote occurs in the source; a malformed
  answer raises JudgeError;
- asserts.judge_pass(rubric=) sends the rubric's criteria in place of
  `writing`'s, and asserts.judge_grounded makes one fresh call after a fail
  with tries=2;
- `--calibrate` also needs the opaque brief to fail and the clear brief to
  pass under the cold-read rubric, and the invented spec to fail and the
  faithful spec to pass judge_grounded against the answers sample.

Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
E2E = os.path.join(HERE, "e2e")
SAMPLES = os.path.join(E2E, "samples")
WRITING_SKILL = os.path.join(ROOT, "skills", "writing", "SKILL.md")
SCENARIO = os.path.join(E2E, "scenarios", "writing_rewrite.py")
RUBRIC = os.path.join(E2E, "rubrics", "brief-cold-read.md")
BRIEF_OPAQUE = os.path.join(SAMPLES, "brief-opaque.md")
BRIEF_CLEAR = os.path.join(SAMPLES, "brief-clear.md")
SPEC_ANSWERS = os.path.join(SAMPLES, "spec-answers.md")
SPEC_GROUNDED = os.path.join(SAMPLES, "spec-grounded.md")
SPEC_INVENTED = os.path.join(SAMPLES, "spec-invented.md")
NEW_SAMPLES = (BRIEF_OPAQUE, BRIEF_CLEAR, SPEC_ANSWERS, SPEC_GROUNDED, SPEC_INVENTED)

if E2E not in sys.path:
    sys.path.insert(0, E2E)

import judge  # noqa: E402
import asserts  # noqa: E402

PLANTED_SKILL = """---
name: writing
description: A planted skill for the judge tests.
---

# Writing

Text before the first section is context, not a criterion.

## Alpha rules

Use short words.

### A sub-heading is part of its section

```text
## A heading inside a fence is not a criterion
```

## Beta rules ##

Name the actor.

## Gamma rules

Cut filler.

## Delta rules

Write commit messages as commands.
"""
PLANTED = ["Alpha rules", "Beta rules", "Gamma rules", "Delta rules"]
SESSION_VARS = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT")


def headings(text):
    """`##` headings outside fenced blocks, found independently of judge.py."""
    out, fenced = [], False
    for line in text.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
            continue
        m = re.match(r"^## +(.+?)(?: +#+)?\s*$", line)
        if m and not fenced:
            out.append(m.group(1))
    return out


def entry(score, breaks=(), note="No break found."):
    """One criterion's answer, in the field order the judge asks for."""
    return {"gaps": ["no owner named"], "breaks": list(breaks), "slips": [],
            "note": note, "score": score}


def answer(scores, **extra):
    """A `claude -p --output-format json` result holding the given scores."""
    out = {
        "type": "result", "subtype": "success", "is_error": False, "result": "",
        "total_cost_usd": 0.01,
        "structured_output": {
            "criteria": {name: entry(score) for name, score in scores.items()},
        },
    }
    out.update(extra)
    return json.dumps(out)


def schema_names(argv):
    """The criteria named in the --json-schema argument of a judge call."""
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    return schema["properties"]["criteria"]["required"]


class Stub(object):
    """Stands in for the model call; records every call it gets."""

    def __init__(self, stdout="", returncode=0, stderr="", reply=None):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.reply = reply
        self.calls = []

    def __call__(self, argv, prompt, cwd, env, timeout):
        self.calls.append({
            "argv": list(argv), "prompt": prompt, "cwd": cwd, "env": dict(env),
            "timeout": timeout,
            "listing": sorted(os.listdir(cwd)) if os.path.isdir(cwd) else None,
        })
        stdout = self.reply(argv, prompt) if self.reply else self.stdout
        return subprocess.CompletedProcess(list(argv), self.returncode, stdout, self.stderr)


class JudgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.skill = self.write("skill/SKILL.md", PLANTED_SKILL)
        self.sample = self.write("sample.md", "# Update\n\nThe build passes.\n")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(judge.MODEL_ENV, None)

    def write(self, rel, text):
        path = os.path.join(self.tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def judge(self, scores=None, stub=None, **kw):
        stub = stub or Stub(answer(scores))
        return judge.judge_file(self.sample, self.skill, call=stub, **kw), stub


class Criteria(JudgeCase):
    def test_real_skill_criteria_are_its_headings(self):
        with open(WRITING_SKILL, encoding="utf-8") as fh:
            text = fh.read()
        found = judge.criteria(text)
        self.assertEqual(found, headings(text))
        self.assertGreaterEqual(len(found), 4, "writing needs at least four ## sections")

    def test_planted_skill_criteria_are_its_headings(self):
        self.assertEqual(judge.criteria(PLANTED_SKILL), PLANTED)

    def test_schema_asks_for_exactly_the_headings(self):
        _, stub = self.judge({name: 5 for name in PLANTED})
        schema = json.loads(stub.calls[0]["argv"][stub.calls[0]["argv"].index("--json-schema") + 1])
        criteria = schema["properties"]["criteria"]
        self.assertEqual(criteria["required"], PLANTED)
        self.assertEqual(sorted(criteria["properties"]), sorted(PLANTED))
        self.assertFalse(criteria.get("additionalProperties", True))

    def test_editing_the_skill_changes_the_criteria(self):
        edited = PLANTED_SKILL.replace("## Gamma rules", "## Epsilon rules")
        self.assertEqual(judge.criteria(edited),
                         ["Alpha rules", "Beta rules", "Epsilon rules", "Delta rules"])

    def test_prompt_holds_the_whole_skill_and_the_sample(self):
        _, stub = self.judge({name: 5 for name in PLANTED})
        prompt = stub.calls[0]["prompt"]
        self.assertIn(PLANTED_SKILL.strip(), prompt)
        self.assertIn("The build passes.", prompt)
        for name in PLANTED:
            self.assertIn(name, prompt)
        self.assertIn("n/a", prompt)

    def test_duplicate_headings_are_an_error(self):
        dup = PLANTED_SKILL.replace("## Gamma rules", "## Alpha rules")
        with self.assertRaises(judge.JudgeError):
            judge.criteria(dup)

    def test_too_few_headings_are_an_error(self):
        with self.assertRaises(judge.JudgeError):
            judge.criteria("# Writing\n\n## Only\n\n## Two\n")


class Verdict(JudgeCase):
    def test_all_fives_pass(self):
        result, _ = self.judge({name: 5 for name in PLANTED})
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["scores"], {name: 5 for name in PLANTED})
        self.assertEqual(result["failures"], [])

    def test_all_fours_pass(self):
        result, _ = self.judge({name: 4 for name in PLANTED})
        self.assertEqual(result["verdict"], "pass")

    def test_na_is_left_out_of_the_pass_rule(self):
        scores = {"Alpha rules": 5, "Beta rules": 4, "Gamma rules": 4, "Delta rules": "n/a"}
        result, _ = self.judge(scores)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["scores"]["Delta rules"], "n/a")

    def test_a_single_three_fails(self):
        scores = {"Alpha rules": 5, "Beta rules": 5, "Gamma rules": 3, "Delta rules": 5}
        result, _ = self.judge(scores)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("Gamma rules" in f for f in result["failures"]), result["failures"])

    def test_failures_quote_the_breaks(self):
        out = json.loads(answer({name: 5 for name in PLANTED}))
        out["structured_output"]["criteria"]["Beta rules"] = entry(
            3, breaks=['"the file is rejected" hides the actor'])
        result, _ = self.judge(stub=Stub(json.dumps(out)))
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("the file is rejected" in f for f in result["failures"]),
                        result["failures"])

    def test_schema_asks_for_gaps_before_the_score(self):
        _, stub = self.judge({name: 5 for name in PLANTED})
        argv = stub.calls[0]["argv"]
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        item = schema["properties"]["criteria"]["properties"]["Alpha rules"]
        self.assertEqual(list(item["properties"]), ["gaps", "breaks", "slips", "note", "score"])
        self.assertEqual(item["required"], ["gaps", "breaks", "slips", "note", "score"])

    def test_a_one_fails(self):
        scores = {"Alpha rules": 1, "Beta rules": 5, "Gamma rules": 5, "Delta rules": "n/a"}
        self.assertEqual(self.judge(scores)[0]["verdict"], "fail")

    def test_two_scored_criteria_fail(self):
        scores = {"Alpha rules": 5, "Beta rules": 5, "Gamma rules": "n/a", "Delta rules": "n/a"}
        result, _ = self.judge(scores)
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(any("2" in f and "3" in f for f in result["failures"]), result["failures"])

    def test_three_scored_criteria_pass(self):
        scores = {"Alpha rules": 5, "Beta rules": 5, "Gamma rules": 4, "Delta rules": "n/a"}
        self.assertEqual(self.judge(scores)[0]["verdict"], "pass")

    def test_all_na_fails(self):
        result, _ = self.judge({name: "n/a" for name in PLANTED})
        self.assertEqual(result["verdict"], "fail")


class Malformed(JudgeCase):
    GOOD = {name: 5 for name in PLANTED}

    def assert_error(self, stdout, returncode=0):
        with self.assertRaises(judge.JudgeError):
            self.judge(stub=Stub(stdout, returncode=returncode, stderr="boom"))

    def test_not_json(self):
        self.assert_error("I think it is fine.")

    def test_empty_output(self):
        self.assert_error("")

    def test_json_that_is_not_an_object(self):
        self.assert_error("[]")

    def test_nonzero_exit(self):
        self.assert_error(answer(self.GOOD), returncode=1)

    def test_is_error(self):
        self.assert_error(answer(self.GOOD, is_error=True))

    def test_no_structured_output_and_no_json_result(self):
        self.assert_error(json.dumps({"type": "result", "is_error": False, "result": "Looks good."}))

    def test_missing_criterion(self):
        scores = dict(self.GOOD)
        del scores["Delta rules"]
        self.assert_error(answer(scores))

    def test_unknown_criterion(self):
        scores = dict(self.GOOD, **{"Omega rules": 5})
        self.assert_error(answer(scores))

    def test_bad_scores(self):
        for bad in (0, 6, 4.5, "4", True, None, "pass"):
            with self.subTest(score=bad):
                self.assert_error(answer(dict(self.GOOD, **{"Beta rules": bad})))

    def test_entry_that_is_not_an_object(self):
        out = json.loads(answer(self.GOOD))
        out["structured_output"]["criteria"]["Beta rules"] = 5
        self.assert_error(json.dumps(out))

    def test_fields_of_the_wrong_type(self):
        bad = {"gaps": "none", "breaks": [3], "slips": None, "note": 3}
        for field, value in bad.items():
            with self.subTest(field=field):
                out = json.loads(answer(self.GOOD))
                out["structured_output"]["criteria"]["Beta rules"][field] = value
                self.assert_error(json.dumps(out))

    def test_missing_field(self):
        for field in ("gaps", "breaks", "slips", "note"):
            with self.subTest(field=field):
                out = json.loads(answer(self.GOOD))
                del out["structured_output"]["criteria"]["Beta rules"][field]
                self.assert_error(json.dumps(out))

    def test_json_result_text_is_a_fallback(self):
        out = json.loads(answer(self.GOOD))
        out["result"] = json.dumps(out.pop("structured_output"))
        result, _ = self.judge(stub=Stub(json.dumps(out)))
        self.assertEqual(result["verdict"], "pass")

    def test_noise_before_the_result_line(self):
        result, _ = self.judge(stub=Stub("a warning\n" + answer(self.GOOD) + "\n"))
        self.assertEqual(result["verdict"], "pass")


class Command(JudgeCase):
    def call(self, **kw):
        _, stub = self.judge({name: 5 for name in PLANTED}, **kw)
        self.assertEqual(len(stub.calls), 1)
        return stub.calls[0]

    def test_claude_print_mode_with_a_json_schema(self):
        argv = self.call()["argv"]
        self.assertEqual(os.path.basename(argv[0]), "claude")
        self.assertIn("-p", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(schema_names(argv), PLANTED)

    def test_no_plugin_and_strict_mcp_config(self):
        argv = self.call()["argv"]
        self.assertIn("--strict-mcp-config", argv)
        for flag in ("--plugin-dir", "--plugin-url", "--mcp-config"):
            self.assertNotIn(flag, argv)
        self.assertFalse(any(ROOT in arg for arg in argv), "the judge call names the plugin folder")

    def test_ignores_user_settings(self):
        argv = self.call()["argv"]
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project,local")

    def test_default_model_is_sonnet(self):
        argv = self.call()["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")

    def test_env_overrides_the_model(self):
        os.environ[judge.MODEL_ENV] = "opus"
        argv = self.call()["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "opus")

    def test_argument_overrides_the_env(self):
        os.environ[judge.MODEL_ENV] = "opus"
        argv = self.call(model="haiku")["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")

    def test_cwd_is_an_empty_temp_folder_removed_afterwards(self):
        call = self.call()
        cwd = os.path.realpath(call["cwd"])
        self.assertEqual(call["listing"], [], "the judge cwd must be empty")
        self.assertTrue(cwd.startswith(os.path.realpath(tempfile.gettempdir()) + os.sep), cwd)
        self.assertFalse(cwd.startswith(os.path.realpath(ROOT) + os.sep), cwd)
        self.assertNotEqual(cwd, os.path.realpath(os.getcwd()))
        self.assertFalse(os.path.exists(cwd), "the judge cwd must be removed")

    def test_parent_session_variables_are_dropped(self):
        for var in SESSION_VARS:
            os.environ[var] = "1"
        env = self.call()["env"]
        for var in SESSION_VARS:
            self.assertNotIn(var, env)
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))

    def test_module_seam_is_the_default_call(self):
        stub = Stub(answer({name: 5 for name in PLANTED}))
        with mock.patch.object(judge, "call_model", stub):
            result = judge.judge_file(self.sample, self.skill)
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(len(stub.calls), 1)


def by_sample(sloppy_scores, clean_scores):
    """A stub reply that scores the sloppy and clean samples differently."""
    with open(os.path.join(SAMPLES, "sloppy.md"), encoding="utf-8") as fh:
        sloppy = fh.read().strip()

    def reply(argv, prompt):
        score = sloppy_scores if sloppy in prompt else clean_scores
        return answer({name: score for name in schema_names(argv)})
    return reply


class Cli(JudgeCase):
    def main(self, args, stub):
        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
            code = judge.main(args + ["--skill", self.skill], call=stub)
        return code, out.getvalue()

    def test_calibrate_passes_when_sloppy_fails_and_clean_passes(self):
        stub = Stub(reply=by_sample(1, 5))
        code, _ = self.main(["--calibrate"], stub)
        self.assertEqual(code, 0)
        prompts = [c["prompt"] for c in stub.calls]
        self.assertEqual(len(prompts), 2)

    def test_calibrate_fails_a_judge_that_passes_both(self):
        self.assertEqual(self.main(["--calibrate"], Stub(reply=by_sample(5, 5)))[0], 1)

    def test_calibrate_fails_a_judge_that_fails_both(self):
        self.assertEqual(self.main(["--calibrate"], Stub(reply=by_sample(1, 3)))[0], 1)

    def test_calibrate_exits_2_on_a_malformed_answer(self):
        self.assertEqual(self.main(["--calibrate"], Stub("not json"))[0], 2)

    def test_files_pass_and_fail(self):
        good = Stub(answer({name: 5 for name in PLANTED}))
        self.assertEqual(self.main([self.sample], good)[0], 0)
        bad = Stub(answer({name: 2 for name in PLANTED}))
        code, out = self.main([self.sample], bad)
        self.assertEqual(code, 1)
        self.assertIn("FAIL", out)

    def test_missing_file_exits_2(self):
        stub = Stub(answer({name: 5 for name in PLANTED}))
        self.assertEqual(self.main([os.path.join(self.tmp, "nope.md")], stub)[0], 2)
        self.assertEqual(stub.calls, [])

    def test_no_arguments_exits_2(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(judge.main([], call=Stub()), 2)


class AssertsFit(JudgeCase):
    """asserts.judge_pass calls judge_file(path, skill_md) and reads `verdict`."""

    def fake_run(self):
        plugin = os.path.join(self.tmp, "plugin")
        os.makedirs(os.path.join(plugin, "skills", "writing"))
        shutil.copy(self.skill, os.path.join(plugin, "skills", "writing", "SKILL.md"))
        return types.SimpleNamespace(repo=self.tmp, plugin_dir=plugin)

    def test_pass(self):
        stub = Stub(answer({name: 5 for name in PLANTED}))
        with mock.patch.object(judge, "call_model", stub):
            verdict = asserts.judge_pass(self.fake_run(), "sample.md")
        self.assertEqual(verdict["verdict"], "pass")
        self.assertIn(PLANTED_SKILL.strip(), stub.calls[0]["prompt"])

    def test_fail_raises_assertion_error(self):
        stub = Stub(answer({name: 3 for name in PLANTED}))
        with mock.patch.object(judge, "call_model", stub):
            with self.assertRaises(AssertionError):
                asserts.judge_pass(self.fake_run(), "sample.md")


class RewriteScenario(unittest.TestCase):
    """The writing_rewrite scenario loads, and its setup copies the sloppy sample."""

    def load(self):
        spec = importlib.util.spec_from_file_location("devos_scenario_writing_rewrite", SCENARIO)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_declares_claude_and_a_check(self):
        module = self.load()
        self.assertEqual(tuple(module.CLIS), ("claude",))
        self.assertTrue(callable(module.check))
        self.assertRegex(module.PROMPT, r"writing")

    def test_setup_copies_the_sloppy_sample(self):
        module = self.load()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        module.setup(repo, tmp)
        with open(os.path.join(SAMPLES, "sloppy.md"), encoding="utf-8") as fh:
            sloppy = fh.read()
        with open(os.path.join(repo, module.DRAFT), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), sloppy)
        self.assertEqual(os.listdir(repo), [module.DRAFT])


# --- grounded milestones --------------------------------------------------------

SOURCE = """Milestones: first, the nightly export
of paid invoices, target 2026-12-04. Second, an email with the file, no date yet."""
CLAIMS_TEXT = """### Milestone 1: nightly export

Paid invoices export every night. Target: 2026-12-04.

### Milestone 2: email

The file goes out by email.
"""


def claim(text, supported=True, evidence=""):
    return {"claim": text, "supported": supported, "evidence": evidence}


def claims_answer(claims, **extra):
    """A `claude -p --output-format json` result holding a grounded answer."""
    out = {
        "type": "result", "subtype": "success", "is_error": False, "result": "",
        "total_cost_usd": 0.02,
        "structured_output": {"claims": claims},
    }
    out.update(extra)
    return json.dumps(out)


GOOD_CLAIMS = [
    claim("A nightly export of paid invoices, target 2026-12-04",
          evidence="the nightly export of paid invoices, target 2026-12-04"),
    claim("An email with the file", evidence="an email with the file"),
]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Grounded(JudgeCase):
    def grounded(self, stdout=None, stub=None, **kw):
        stub = stub or Stub(stdout)
        return judge.judge_grounded(CLAIMS_TEXT, SOURCE, call=stub, **kw), stub

    def test_pass_when_every_claim_is_supported_with_a_quote_from_the_source(self):
        result, stub = self.grounded(claims_answer(GOOD_CLAIMS))
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(result["unsupported"], [])
        self.assertEqual([c["claim"] for c in result["claims"]], [c["claim"] for c in GOOD_CLAIMS])
        self.assertEqual(result["cost_usd"], 0.02)
        self.assertEqual(len(stub.calls), 1)

    def test_quote_match_ignores_case_and_whitespace(self):
        claims = [claim("Nightly export", evidence="THE NIGHTLY   EXPORT of paid\ninvoices")]
        self.assertEqual(self.grounded(claims_answer(claims))[0]["verdict"], "pass")

    def test_one_unsupported_claim_fails(self):
        claims = GOOD_CLAIMS + [claim("A PDF bundle, target 2027-01-15", supported=False)]
        result, _ = self.grounded(claims_answer(claims))
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(len(result["unsupported"]), 1)
        self.assertIn("PDF bundle", result["unsupported"][0])

    def test_supported_claim_whose_quote_is_not_in_the_source_fails(self):
        claims = GOOD_CLAIMS + [claim("A PDF bundle", evidence="a PDF bundle of every invoice")]
        result, _ = self.grounded(claims_answer(claims))
        self.assertEqual(result["verdict"], "fail")
        self.assertEqual(len(result["unsupported"]), 1)
        self.assertIn("PDF bundle", result["unsupported"][0])

    def test_supported_claim_with_an_empty_quote_fails(self):
        claims = GOOD_CLAIMS + [claim("A PDF bundle", evidence="  ")]
        self.assertEqual(self.grounded(claims_answer(claims))[0]["verdict"], "fail")

    def test_zero_claims_fail(self):
        result, _ = self.grounded(claims_answer([]))
        self.assertEqual(result["verdict"], "fail")
        self.assertTrue(result["unsupported"], "a fail must say why")

    def test_malformed_answers_raise(self):
        good = json.loads(claims_answer(GOOD_CLAIMS))
        bad_claims = {
            "claims not a list": {"claims": "none"},
            "no claims key": {"criteria": {}},
            "claim not an object": {"claims": ["A nightly export"]},
            "supported not a bool": {"claims": [dict(GOOD_CLAIMS[0], supported="true")]},
            "evidence not a string": {"claims": [dict(GOOD_CLAIMS[0], evidence=None)]},
            "claim not a string": {"claims": [dict(GOOD_CLAIMS[0], claim=3)]},
            "missing evidence": {"claims": [{"claim": "x", "supported": True}]},
        }
        cases = {"not json": ("I think it is fine.", 0), "empty": ("", 0),
                 "is_error": (claims_answer(GOOD_CLAIMS, is_error=True), 0),
                 "nonzero exit": (claims_answer(GOOD_CLAIMS), 1)}
        for name, structured in bad_claims.items():
            cases[name] = (json.dumps(dict(good, structured_output=structured)), 0)
        for name, (stdout, code) in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(judge.JudgeError):
                    self.grounded(stub=Stub(stdout, returncode=code, stderr="boom"))

    def test_json_result_text_is_a_fallback(self):
        out = json.loads(claims_answer(GOOD_CLAIMS))
        out["result"] = json.dumps(out.pop("structured_output"))
        self.assertEqual(self.grounded(json.dumps(out))[0]["verdict"], "pass")

    def test_call_asks_for_claims_with_its_own_schema(self):
        _, stub = self.grounded(claims_answer(GOOD_CLAIMS))
        call = stub.calls[0]
        argv = call["argv"]
        self.assertEqual(os.path.basename(argv[0]), "claude")
        self.assertIn("-p", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        item = schema["properties"]["claims"]["items"]
        self.assertEqual(sorted(item["required"]), ["claim", "evidence", "supported"])
        self.assertEqual(item["properties"]["supported"]["type"], "boolean")
        self.assertIn(SOURCE.strip(), call["prompt"])
        self.assertIn(CLAIMS_TEXT.strip(), call["prompt"])
        self.assertEqual(call["listing"], [], "the judge cwd must be empty")
        self.assertFalse(os.path.exists(call["cwd"]), "the judge cwd must be removed")

    def test_model_argument(self):
        _, stub = self.grounded(claims_answer(GOOD_CLAIMS), model="haiku")
        argv = stub.calls[0]["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "haiku")

    def test_section_reads_past_a_heading_inside_a_code_fence(self):
        text = ("# Spec\n\n## Milestones\n\n### Milestone 1: form\n\nShips a form.\n\n"
                "```markdown\n## Risks\n```\n\nTarget: 2026-12-04\n\n## Risks\n\n- None\n")
        got = judge.section(text, "Milestones")
        self.assertIn("Target: 2026-12-04", got)
        self.assertNotIn("- None", got)
        with self.assertRaises(judge.JudgeError):
            judge.section(text, "Goals")


class CountingJudge(object):
    """A stand-in judge module: returns the queued verdicts in order and counts calls."""

    def __init__(self, *verdicts):
        self.verdicts = list(verdicts)
        self.calls = []

    def _next(self, name, args):
        self.calls.append((name, args))
        return self.verdicts.pop(0)

    def judge_file(self, path, skill_md):
        return self._next("judge_file", (path, skill_md))

    def judge_grounded(self, claims_text, source_text):
        return self._next("judge_grounded", (claims_text, source_text))


def grounded_verdict(verdict, note):
    return {"verdict": verdict, "claims": [claim(note)], "unsupported": [] if verdict == "pass" else [note],
            "cost_usd": None}


class AssertsGrounded(JudgeCase):
    RUN = types.SimpleNamespace(repo="/nonexistent", plugin_dir="/nonexistent")

    def check(self, module, tries):
        return asserts.judge_grounded(self.RUN, CLAIMS_TEXT, SOURCE, judge_module=module, tries=tries)

    def test_pass_on_the_first_call_makes_one_call(self):
        module = CountingJudge(grounded_verdict("pass", "ok"))
        self.assertEqual(self.check(module, 2)["verdict"], "pass")
        self.assertEqual(module.calls, [("judge_grounded", (CLAIMS_TEXT, SOURCE))])

    def test_fail_then_pass_makes_two_calls_and_passes(self):
        module = CountingJudge(grounded_verdict("fail", "first miss"), grounded_verdict("pass", "ok"))
        self.assertEqual(self.check(module, 2)["verdict"], "pass")
        self.assertEqual(len(module.calls), 2)

    def test_two_fails_report_both_results(self):
        module = CountingJudge(grounded_verdict("fail", "first miss"), grounded_verdict("fail", "second miss"))
        with self.assertRaises(AssertionError) as ctx:
            self.check(module, 2)
        self.assertEqual(len(module.calls), 2)
        self.assertIn("first miss", str(ctx.exception))
        self.assertIn("second miss", str(ctx.exception))

    def test_one_try_fails_after_one_call(self):
        module = CountingJudge(grounded_verdict("fail", "first miss"), grounded_verdict("pass", "ok"))
        with self.assertRaises(AssertionError):
            self.check(module, 1)
        self.assertEqual(len(module.calls), 1)

    def test_real_judge_fits(self):
        stub = Stub(claims_answer(GOOD_CLAIMS))
        with mock.patch.object(judge, "call_model", stub):
            verdict = asserts.judge_grounded(self.RUN, CLAIMS_TEXT, SOURCE)
        self.assertEqual(verdict["verdict"], "pass")
        self.assertEqual(len(stub.calls), 1)


# --- the cold-read rubric -------------------------------------------------------

PLANTED_RUBRIC = """# Planted rubric

## Kappa rule

A missing detail breaks this rule; it is not a gap.

## Lambda rule

Every term is explained.

## Mu rule

Open items are questions.
"""
RUBRIC_NAMES = ["Kappa rule", "Lambda rule", "Mu rule"]


class AssertsRubric(JudgeCase):
    """asserts.judge_pass(rubric=) sends the rubric in place of `writing`'s SKILL.md."""

    fake_run = AssertsFit.fake_run

    def test_rubric_replaces_the_writing_skill(self):
        rubric = self.write("rubric.md", PLANTED_RUBRIC)
        stub = Stub(reply=lambda argv, prompt: answer({n: 5 for n in schema_names(argv)}))
        with mock.patch.object(judge, "call_model", stub):
            verdict = asserts.judge_pass(self.fake_run(), "sample.md", rubric=rubric)
        self.assertEqual(verdict["verdict"], "pass")
        self.assertEqual(schema_names(stub.calls[0]["argv"]), RUBRIC_NAMES)
        self.assertIn(PLANTED_RUBRIC.strip(), stub.calls[0]["prompt"])
        self.assertNotIn(PLANTED_SKILL.strip(), stub.calls[0]["prompt"])

    def test_rubric_best_of_two(self):
        rubric = self.write("rubric.md", PLANTED_RUBRIC)
        module = CountingJudge({"verdict": "fail", "scores": {"Kappa rule": 2}, "failures": ["x"]},
                               {"verdict": "pass", "scores": {}, "failures": []})
        run = self.fake_run()
        self.assertEqual(asserts.judge_pass(run, "sample.md", judge_module=module, tries=2,
                                            rubric=rubric)["verdict"], "pass")
        sample = asserts.path(run, "sample.md")
        self.assertEqual(module.calls, [("judge_file", (sample, rubric))] * 2)

    def test_no_rubric_still_uses_writing(self):
        module = CountingJudge({"verdict": "pass", "scores": {}, "failures": []})
        run = self.fake_run()
        asserts.judge_pass(run, "sample.md", judge_module=module)
        self.assertEqual(module.calls[0][1][1],
                         os.path.join(run.plugin_dir, "skills", "writing", "SKILL.md"))


def section_body(text, title):
    """Lines under `## <title>` up to the next `## ` heading, found independently of judge.py."""
    out, inside = [], False
    for line in text.splitlines():
        if re.match(r"^## ", line):
            inside = line[3:].strip() == title
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


class ColdReadRubric(unittest.TestCase):
    def test_four_criteria(self):
        self.assertEqual(len(judge.criteria(read(RUBRIC))), 4)

    def test_each_rule_states_its_omission_as_a_break(self):
        # judge_text's prompt scores a missing detail as a free gap (spec review S9).
        text = read(RUBRIC)
        for name in judge.criteria(text):
            with self.subTest(criterion=name):
                body = section_body(text, name).lower()
                self.assertRegex(body, r"\bbreaks? this rule\b")
                self.assertIn("not a gap", body)


# --- the new samples ------------------------------------------------------------

BRIEF_HEADINGS = ["The problem", "The goal", "The plan", "Not doing", "Still open"]
SPEC_HEADINGS = ["Summary", "Goals", "Non-goals", "Milestones", "Risks", "Open questions"]
# The phase 05 scenario's topic and the fixture's text; a sample must not share them.
FOREIGN = re.compile(r"search-latency|query plans?|query cache|checkout-revamp|typo"
                     r"|edit[- ]?distance|did you mean|auto-?complete", re.I)


class NewSamples(unittest.TestCase):
    def test_shapes_follow_format_md(self):
        for path in (BRIEF_OPAQUE, BRIEF_CLEAR):
            with self.subTest(path=path):
                self.assertEqual(headings(read(path)), BRIEF_HEADINGS)
        for path in (SPEC_GROUNDED, SPEC_INVENTED):
            with self.subTest(path=path):
                self.assertEqual(headings(read(path)), SPEC_HEADINGS)

    def test_invented_spec_adds_one_milestone_and_changes_nothing_else(self):
        grounded, invented = read(SPEC_GROUNDED), read(SPEC_INVENTED)
        for name in SPEC_HEADINGS:
            if name != "Milestones":
                with self.subTest(section=name):
                    self.assertEqual(section_body(invented, name), section_body(grounded, name))
        count = lambda text: len(re.findall(r"^### ", section_body(text, "Milestones"), re.M))
        self.assertEqual(count(invented), count(grounded) + 1)
        self.assertIn(section_body(grounded, "Milestones").strip(), section_body(invented, "Milestones"))

    def test_topics_are_unrelated_to_the_scenario_and_fixture(self):
        for path in NEW_SAMPLES + (RUBRIC,):
            with self.subTest(path=path):
                self.assertIsNone(FOREIGN.search(read(path)))

    def test_banned_clean_and_short(self):
        files = list(NEW_SAMPLES) + [RUBRIC]
        result = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "banned.py")] + files,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in files:
            with self.subTest(path=path):
                self.assertLessEqual(len(read(path).splitlines()), 60)


# --- calibration ----------------------------------------------------------------


def invented_only():
    """Lines of the invented spec that the faithful spec lacks."""
    grounded = read(SPEC_GROUNDED).splitlines()
    return [line for line in read(SPEC_INVENTED).splitlines() if line.strip() and line not in grounded]


def by_kind(opaque=1, clear=5, invented_supported=False, faithful_supported=True):
    """A stub reply for every calibration sample: scores for criteria calls, claims for grounded ones."""
    sloppy, opaque_text = read(os.path.join(SAMPLES, "sloppy.md")).strip(), read(BRIEF_OPAQUE).strip()
    clear_text = read(BRIEF_CLEAR).strip()
    quote = " ".join(read(SPEC_ANSWERS).split())[:40]
    extra = invented_only()

    def reply(argv, prompt):
        schema = json.loads(argv[argv.index("--json-schema") + 1])
        if "criteria" in schema["properties"]:
            if sloppy in prompt:
                score = 1
            else:
                score = opaque if opaque_text in prompt else clear if clear_text in prompt else 5
            return answer({name: score for name in schema_names(argv)})
        invented = any(line in prompt for line in extra)
        supported = invented_supported if invented else faithful_supported
        claims = [claim("from the answers", evidence=quote)]
        claims.append(claim("the last milestone", supported=supported, evidence=quote if supported else ""))
        return claims_answer(claims)
    return reply


class CalibrateAll(JudgeCase):
    """--calibrate without --skill runs the writing, rubric and grounded pairs."""

    def main(self, stub):
        out = io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", io.StringIO()):
            code = judge.main(["--calibrate"], call=stub)
        return code, out.getvalue()

    def test_all_three_pairs_pass(self):
        stub = Stub(reply=by_kind())
        code, out = self.main(stub)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(stub.calls), 6)
        rubric_names = judge.criteria(read(RUBRIC))
        writing_names = judge.criteria(read(WRITING_SKILL))
        kinds = []
        for call in stub.calls:
            schema = json.loads(call["argv"][call["argv"].index("--json-schema") + 1])
            if "claims" in schema["properties"]:
                kinds.append("grounded")
                self.assertIn(read(SPEC_ANSWERS).strip(), call["prompt"])
            elif schema_names(call["argv"]) == rubric_names:
                kinds.append("rubric")
                self.assertIn(read(RUBRIC).strip(), call["prompt"])
            else:
                self.assertEqual(schema_names(call["argv"]), writing_names)
                kinds.append("writing")
        self.assertEqual(sorted(kinds), ["grounded"] * 2 + ["rubric"] * 2 + ["writing"] * 2)
        briefs = [c["prompt"] for c in stub.calls if read(RUBRIC).strip() in c["prompt"]]
        self.assertTrue(any(read(BRIEF_OPAQUE).strip() in p for p in briefs))
        self.assertTrue(any(read(BRIEF_CLEAR).strip() in p for p in briefs))
        grounded = [c["prompt"] for c in stub.calls if read(SPEC_ANSWERS).strip() in c["prompt"]]
        self.assertTrue(any(all(line in p for line in invented_only()) for p in grounded),
                        "the invented milestone never reached the grounded judge")

    def test_fails_a_judge_that_passes_the_opaque_brief(self):
        self.assertEqual(self.main(Stub(reply=by_kind(opaque=5)))[0], 1)

    def test_fails_a_judge_that_fails_the_clear_brief(self):
        self.assertEqual(self.main(Stub(reply=by_kind(clear=3)))[0], 1)

    def test_fails_a_judge_that_supports_the_invented_milestone(self):
        self.assertEqual(self.main(Stub(reply=by_kind(invented_supported=True)))[0], 1)

    def test_fails_a_judge_that_finds_the_faithful_spec_unsupported(self):
        self.assertEqual(self.main(Stub(reply=by_kind(faithful_supported=False)))[0], 1)

    def test_skill_flag_calibrates_only_the_writing_pair(self):
        stub = Stub(reply=by_kind())
        with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            code = judge.main(["--calibrate", "--skill", WRITING_SKILL], call=stub)
        self.assertEqual(code, 0)
        self.assertEqual(len(stub.calls), 2)


if __name__ == "__main__":
    unittest.main()
