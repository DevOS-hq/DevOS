"""Offline checks for the plugin manifests, LICENSE and README.

Run from the plugin root:  python3 -m unittest discover -s tests
Standard library only; Python 3.9 compatible.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CLAUDE_PLUGIN = ".claude-plugin/plugin.json"
CLAUDE_MARKET = ".claude-plugin/marketplace.json"
CODEX_PLUGIN = ".codex-plugin/plugin.json"
CODEX_MARKET = ".agents/plugins/marketplace.json"
CURSOR_PLUGIN = ".cursor-plugin/plugin.json"

MANIFESTS = (CLAUDE_PLUGIN, CODEX_PLUGIN, CURSOR_PLUGIN)
MARKETPLACES = (CLAUDE_MARKET, CODEX_MARKET)
ALL_JSON = MANIFESTS + MARKETPLACES

NAME = "devos"
HOLDER = "DevOS contributors"
# GitHub's canonical casing; a lowercase org makes a push print "moved".
PUBLIC_REPO = "DevOS-hq/DevOS"
PUBLIC_URL = "https://github.com/" + PUBLIC_REPO
IDENTITY_KEYS = ("author", "owner", "developerName")


def load(rel):
    with open(ROOT / rel, encoding="utf-8") as fh:
        return json.load(fh)


def identity_values(node, trail=""):
    """Yield (json path, value) for every author/owner/developerName key."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = "{}.{}".format(trail, key) if trail else key
            if key in IDENTITY_KEYS:
                yield here, value
            yield from identity_values(value, here)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from identity_values(item, "{}[{}]".format(trail, i))


def holder_of(value):
    """An identity is either a plain string or an object with a name."""
    if isinstance(value, dict):
        return value.get("name")
    return value


class ManifestTests(unittest.TestCase):
    def test_every_json_file_parses(self):
        for rel in ALL_JSON:
            with self.subTest(file=rel):
                self.assertIsInstance(load(rel), dict)

    def test_plugin_name_is_devos(self):
        for rel in MANIFESTS:
            with self.subTest(file=rel):
                self.assertEqual(load(rel).get("name"), NAME)

    def test_marketplaces_are_named_devos_with_one_devos_entry(self):
        for rel in MARKETPLACES:
            with self.subTest(file=rel):
                market = load(rel)
                self.assertEqual(market.get("name"), NAME)
                plugins = market.get("plugins")
                self.assertIsInstance(plugins, list)
                self.assertEqual(len(plugins), 1)
                self.assertEqual(plugins[0].get("name"), NAME)

    def test_one_version_everywhere(self):
        versions = {rel: load(rel).get("version") for rel in MANIFESTS}
        for rel in MARKETPLACES:
            versions[rel + " plugins[0]"] = load(rel)["plugins"][0].get("version")
        for where, version in versions.items():
            with self.subTest(where=where):
                self.assertIsInstance(version, str)
                self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_codex_and_cursor_point_at_skills(self):
        for rel in (CODEX_PLUGIN, CURSOR_PLUGIN):
            with self.subTest(file=rel):
                self.assertEqual(load(rel).get("skills"), "./skills/")

    def test_claude_marketplace_source_is_plugin_root(self):
        self.assertEqual(load(CLAUDE_MARKET)["plugins"][0].get("source"), "./")

    def test_codex_marketplace_source_is_local_plugin_root(self):
        self.assertEqual(
            load(CODEX_MARKET)["plugins"][0].get("source"),
            {"source": "local", "path": "./"},
        )

    def test_repo_links_point_at_the_public_repo(self):
        links = {}
        for rel in MANIFESTS:
            for key in ("homepage", "repository"):
                links["{}:{}".format(rel, key)] = load(rel).get(key)
        links[CODEX_PLUGIN + ":interface.websiteURL"] = (
            load(CODEX_PLUGIN)["interface"].get("websiteURL"))
        for where, url in links.items():
            with self.subTest(link=where):
                self.assertEqual(url, PUBLIC_URL)

    def test_skills_folder_exists(self):
        self.assertTrue((ROOT / "skills").is_dir())

    def test_every_identity_is_devos_contributors(self):
        found = {}
        for rel in ALL_JSON:
            for where, value in identity_values(load(rel)):
                found["{}:{}".format(rel, where)] = value
        # The places a listing shows a name must carry one; then every
        # identity anywhere must be the shared holder, never a person.
        required = (
            CLAUDE_PLUGIN + ":author",
            CLAUDE_MARKET + ":owner",
            CLAUDE_MARKET + ":plugins[0].author",
            CODEX_PLUGIN + ":author",
            CODEX_PLUGIN + ":interface.developerName",
            CURSOR_PLUGIN + ":author",
        )
        for where in required:
            with self.subTest(required=where):
                self.assertIn(where, found)
        for where, value in found.items():
            with self.subTest(identity=where):
                self.assertEqual(holder_of(value), HOLDER)


class PackagingFileTests(unittest.TestCase):
    def test_license_is_mit_held_by_devos_contributors(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 " + HOLDER, text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', text)

    def test_no_plugin_root_claude_md(self):
        # A plugin-root CLAUDE.md is never loaded and fails strict validation.
        self.assertFalse((ROOT / "CLAUDE.md").exists())

    def test_readme_install_lines_and_format_link(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for line in (
            "/plugin marketplace add " + PUBLIC_REPO,
            "/plugin install devos@devos",
            "codex plugin marketplace add " + PUBLIC_REPO,
            "codex plugin add devos@devos",
            "github.com/" + PUBLIC_REPO,
        ):
            with self.subTest(line=line):
                self.assertIn(line, text)
        self.assertRegex(text, r"\]\((\./)?FORMAT\.md\)")
        self.assertRegex(text, re.compile(r"state repo", re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
