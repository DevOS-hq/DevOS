"""Tests for scripts/banned.py, the banned-pattern check for prose.

Every case runs the real script as a subprocess. The sloppy sample in
tests/e2e/samples/ must hit every category, the clean sample must hit none,
and banned words inside fenced code blocks or inline code spans must be
skipped. Each skip case carries a control that puts the same words in plain
prose and expects a hit, so the skip test cannot pass on a script that finds
nothing. Standard library only; runs under Python 3.9.

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
BANNED = os.path.join(ROOT, "scripts", "banned.py")
SAMPLES = os.path.join(HERE, "e2e", "samples")
SLOPPY = os.path.join(SAMPLES, "sloppy.md")
CLEAN = os.path.join(SAMPLES, "clean.md")

CATEGORIES = [
    "dash",
    "contrast-framing",
    "ai-vocabulary",
    "fancy-synonym",
    "fancy-is",
    "ing-rider",
    "staged-opener",
    "chatbot-residue",
    "knowledge-hedge",
    "borrowed-authority",
    "stacked-hedge",
    "generic-closer",
    "minimizer",
    "jargon-metaphor",
    "typography",
]

HIT_RE = re.compile(r"^(.+):([0-9]+): banned: ([a-z-]+): (.+)$")


def run_banned(*args):
    return subprocess.run(
        [sys.executable, BANNED] + list(args),
        capture_output=True,
        text=True,
    )


def describe(result):
    return "exit {}\nstdout:\n{}\nstderr:\n{}".format(
        result.returncode, result.stdout, result.stderr)


def hits(result):
    """Parse stdout into (path, line, category, match) tuples; every line must parse."""
    out = []
    for text in result.stdout.splitlines():
        m = HIT_RE.match(text)
        if not m:
            raise AssertionError("unparseable output line: {!r}".format(text))
        out.append((m.group(1), int(m.group(2)), m.group(3), m.group(4)))
    return out


class TempFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="banned-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path


class Samples(unittest.TestCase):
    def test_sloppy_hits_every_category(self):
        result = run_banned(SLOPPY)
        self.assertEqual(result.returncode, 1, describe(result))
        found = {cat for _, _, cat, _ in hits(result)}
        for cat in CATEGORIES:
            with self.subTest(category=cat):
                self.assertIn(cat, found, describe(result))

    def test_sloppy_hits_point_at_the_right_line(self):
        result = run_banned(SLOPPY)
        with open(SLOPPY, encoding="utf-8") as f:
            lines = f.read().split("\n")
        for path, num, cat, match in hits(result):
            with self.subTest(line=num, category=cat):
                self.assertEqual(path, SLOPPY)
                self.assertIn(match.lower(), lines[num - 1].lower())

    def test_clean_sample_has_no_hits(self):
        result = run_banned(CLEAN)
        self.assertEqual(result.returncode, 0, describe(result))
        self.assertEqual(result.stdout, "")

    def test_samples_are_short(self):
        for path in (SLOPPY, CLEAN):
            with self.subTest(path=path):
                with open(path, encoding="utf-8") as f:
                    self.assertLessEqual(len(f.read().splitlines()), 60)

    def test_categories_flag_lists_every_category_in_order(self):
        result = run_banned("--categories")
        self.assertEqual(result.returncode, 0, describe(result))
        self.assertEqual(result.stdout.split(), CATEGORIES)


class Planted(TempFiles):
    """One planted line per category, so a regression names its category."""

    PLANTED = {
        "dash": "The build passed — then broke.",
        "contrast-framing": "This isn't just a refactor.",
        "ai-vocabulary": "We will delve into the logs.",
        "fancy-synonym": "We utilize the queue.",
        "fancy-is": "The queue serves as a buffer.",
        "ing-rider": "Retries dropped, highlighting the fix.",
        "staged-opener": "Let's dive in.",
        "chatbot-residue": "I hope this helps.",
        "knowledge-hedge": "As of my last update, it works.",
        "borrowed-authority": "Experts say it is fine.",
        "stacked-hedge": "It could potentially fail.",
        "generic-closer": "The future looks bright.",
        "minimizer": "Simply run the script.",
        "jargon-metaphor": "Speed is our north star.",
        "typography": "Pick one and/or the other.",
    }

    def test_planted_line_hits_its_own_category(self):
        self.assertEqual(sorted(self.PLANTED), sorted(CATEGORIES))
        for cat, text in self.PLANTED.items():
            with self.subTest(category=cat):
                path = self.write(cat + ".md", "# Note\n\n" + text + "\n")
                result = run_banned(path)
                self.assertEqual(result.returncode, 1, describe(result))
                self.assertIn((path, 3, cat), [h[:3] for h in hits(result)])

    def test_typography_catches_curly_quotes_etc_and_emoji(self):
        for text in ("He said “ship it”.", "It’s done.",
                     "Carts, taxes, etc. all moved.", "Shipped \U0001F680"):
            with self.subTest(text=text):
                result = run_banned(self.write("t.md", text + "\n"))
                self.assertEqual(result.returncode, 1, describe(result))
                self.assertEqual({h[2] for h in hits(result)}, {"typography"})


class CodeIsSkipped(TempFiles):
    BAD = "We delve into it — and utilize etc. and/or simply leverage it."

    def test_control_plain_prose_hits(self):
        result = run_banned(self.write("plain.md", self.BAD + "\n"))
        self.assertEqual(result.returncode, 1, describe(result))

    def test_backtick_fence_is_skipped(self):
        text = "# Note\n\n```text\n" + self.BAD + "\n```\n\nPlain words.\n"
        result = run_banned(self.write("fence.md", text))
        self.assertEqual(result.returncode, 0, describe(result))

    def test_tilde_fence_is_skipped(self):
        text = "# Note\n\n~~~\n" + self.BAD + "\n~~~\n\nPlain words.\n"
        result = run_banned(self.write("tilde.md", text))
        self.assertEqual(result.returncode, 0, describe(result))

    def test_indented_fence_and_longer_fence_are_skipped(self):
        text = "- Item:\n\n  ````md\n  ```\n  " + self.BAD + "\n  ```\n  ````\n"
        result = run_banned(self.write("nested.md", text))
        self.assertEqual(result.returncode, 0, describe(result))

    def test_prose_after_a_fence_closes_is_checked(self):
        text = "```\ndelve\n```\nWe delve here.\n"
        result = run_banned(self.write("after.md", text))
        self.assertEqual(result.returncode, 1, describe(result))
        self.assertEqual([h[1] for h in hits(result)], [4])

    def test_inline_code_span_is_skipped(self):
        text = ("Avoid `delve`, `utilize`, `—` and `etc.` in prose.\n"
                "Double ticks work too: ``a `simply` b``.\n")
        result = run_banned(self.write("inline.md", text))
        self.assertEqual(result.returncode, 0, describe(result))

    def test_prose_beside_an_inline_span_is_checked(self):
        result = run_banned(self.write("beside.md", "Run `check.py`, then delve.\n"))
        self.assertEqual(result.returncode, 1, describe(result))
        self.assertEqual({h[2] for h in hits(result)}, {"ai-vocabulary"})


class NoFalsePositives(TempFiles):
    """Ordinary technical prose that a loose pattern would wrongly flag."""

    def test_plain_prose_passes(self):
        text = "\n".join([
            "# Release notes",
            "",
            "In today's standup, Dana merged two fixes.",
            "Slugs use hyphens, never underscores in file names.",
            "Run `check.py --rules` to list rule ids, or pass --help.",
            "Dates look like 2026-10-12. Ranges look like pages 3-5.",
            "The checker is not run on fenced lines.",
            "It only reads files. It does not write them.",
            "See https://example.com/foster-care-delve--x for details.",
            "| Rule | Exit |",
            "|---|---|",
            "---",
            "",
        ])
        result = run_banned(self.write("plain.md", text))
        self.assertEqual(result.returncode, 0, describe(result))


class ExitCodes(TempFiles):
    def test_no_arguments_is_a_usage_error(self):
        result = run_banned()
        self.assertEqual(result.returncode, 2, describe(result))
        self.assertIn("usage", result.stderr.lower())

    def test_missing_file_exits_2(self):
        result = run_banned(os.path.join(self.tmp, "nope.md"))
        self.assertEqual(result.returncode, 2, describe(result))
        self.assertIn("nope.md", result.stderr)

    def test_directory_exits_2(self):
        result = run_banned(self.tmp)
        self.assertEqual(result.returncode, 2, describe(result))
        self.assertIn(self.tmp, result.stderr)

    def test_unreadable_wins_over_hits_and_hits_still_print(self):
        bad = self.write("bad.md", "We delve.\n")
        result = run_banned(bad, os.path.join(self.tmp, "nope.md"))
        self.assertEqual(result.returncode, 2, describe(result))
        self.assertEqual([h[2] for h in hits(result)], ["ai-vocabulary"])

    def test_clean_file_exits_0_and_bad_file_exits_1(self):
        good = self.write("good.md", "The build passed.\n")
        self.assertEqual(run_banned(good).returncode, 0)
        bad = self.write("bad.md", "The build passed, showcasing the fix.\n")
        self.assertEqual(run_banned(good, bad).returncode, 1)

    def test_script_is_executable(self):
        self.assertTrue(os.access(BANNED, os.X_OK), BANNED + " is not executable")


if __name__ == "__main__":
    unittest.main()
