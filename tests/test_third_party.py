"""Tests for THIRD_PARTY.md, the notice for the sources the `writing` skill
condenses.

The `writing` skill condenses three MIT-licensed skills. MIT asks that each
copy keep the copyright notice and the permission notice, so THIRD_PARTY.md
must hold, for each source: its URL, its copyright line exactly as the
source's LICENSE file has it, and the full MIT text. The README must link to
it. Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NOTICE = os.path.join(ROOT, "THIRD_PARTY.md")
README = os.path.join(ROOT, "README.md")

# Copyright lines exactly as each source's LICENSE file has them.
PSTACK_COPYRIGHT = "Copyright (c) 2026 Lauren Tan"
HUMANIZER_COPYRIGHT = "Copyright (c) 2025 Siqi Chen"

PSTACK_URLS = (
    "https://github.com/cursor/plugins/tree/main/pstack/skills/unslop",
    "https://github.com/cursor/plugins/tree/main/pstack/skills/technical-writing",
)
HUMANIZER_URLS = ("https://github.com/blader/humanizer",)

# The three paragraphs of the MIT License after the copyright line.
PERMISSION = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
"""
CONDITION = """
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
"""
WARRANTY = """
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def flat(text):
    """Text with every run of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", text).strip()


def full_license(copyright_line):
    """The full MIT text for one copyright holder, whitespace collapsed."""
    return flat("MIT License\n\n" + copyright_line + "\n" + PERMISSION + CONDITION + WARRANTY)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class ThirdPartyNotice(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(NOTICE), "DevOS/THIRD_PARTY.md is missing")
        self.text = read(NOTICE)
        self.flat = flat(self.text)

    def test_copyright_lines_are_verbatim(self):
        for line in (PSTACK_COPYRIGHT, HUMANIZER_COPYRIGHT):
            with self.subTest(line=line):
                self.assertIn(line, self.text.splitlines(),
                              "copyright line must sit on a line of its own, unchanged")

    def test_mit_permission_paragraph(self):
        self.assertIn(flat(PERMISSION), self.flat)

    def test_full_mit_text_follows_each_copyright_line(self):
        for line in (PSTACK_COPYRIGHT, HUMANIZER_COPYRIGHT):
            with self.subTest(line=line):
                self.assertIn(full_license(line), self.flat)

    def test_each_source_url(self):
        for url in PSTACK_URLS + HUMANIZER_URLS:
            with self.subTest(url=url):
                self.assertIn(url, self.text)

    def test_names_the_writing_skill(self):
        self.assertIn("skills/writing/SKILL.md", self.text)


class ReadmeLink(unittest.TestCase):
    def test_readme_links_third_party(self):
        self.assertRegex(read(README), r"\]\(THIRD_PARTY\.md\)")


if __name__ == "__main__":
    unittest.main()
