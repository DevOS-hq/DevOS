"""Lint DevOS skill folders so every skill loads the same way on Claude Code,
Codex and Cursor.

Usage:  python3 tests/skill_lint.py <skill-dir>...

Prints one `<skill-dir>/SKILL.md: <rule-id>: <message>` line per problem.
Exits 0 when every skill is clean, 1 when any problem is found, and 2 on a
usage error (no arguments, or an argument that is not a folder). Import it
and call `lint_skill(skill_dir)` to get a list of `(rule_id, message)`.

Rules (ids are stable; tests and callers match on them):

  skill-file                the folder holds a readable SKILL.md
  frontmatter               line 1 is `---`, a closing `---` follows, and every
                            frontmatter line is a top-level `key: value`
  missing-name              the frontmatter has a non-blank `name`
  missing-description       the frontmatter has a `description` key
  name-pattern              `name` matches ^[a-z0-9]+(-[a-z0-9]+)*$
  name-length               `name` is at most 64 characters
  name-folder               `name` equals the folder name
  description-length        `description` is 1-1024 characters, with runs of
                            whitespace collapsed to one space (as Codex reads it)
  description-hash          a plain (unquoted, non-block) `description` holds no
                            ` #`, which YAML would read as the start of a comment
  description-colon         a plain `description` holds no `: ` (or a closing
                            `:`), which YAML rejects in an unquoted value
  body-length               the body after the closing `---` is at most 200 lines
  disable-model-invocation  the frontmatter never sets `disable-model-invocation`
  plugin-root-var           the file never uses ${CLAUDE_PLUGIN_ROOT} (Claude only)
  skill-dir-var             the file never uses ${CLAUDE_SKILL_DIR} (Claude only)
  names-writing             the body names the `writing` skill
  names-check               the body names `scripts/check.py`
  names-python3             the body contains `python3` (says what the skill does
                            when python3 is missing)
  names-format              the body names `../../FORMAT.md`
  names-remote              a body that holds `git push` (a) names
                            `scripts/remote.py` before its first `git push`,
                            (b) quotes the attestation question (QUESTION)
                            word for word, (c) holds the fail-closed sentence
                            (FAIL_CLOSED), and (d) never holds the bare command
                            `git push` in backticks. One problem per clause.

The five names-* rules skip the skill whose folder is `writing`. They read the
body only, because the body is what the model follows once the skill loads.
Clauses (b) and (c) match with runs of whitespace collapsed to one space, so a
sentence may wrap across lines.

What counts as naming the `writing` skill: the code span `writing` (in
backticks), `devos:writing`, or the phrase "writing skill" (any case, as whole
words). The bare word is not enough: "before writing a record" or "rewriting"
is ordinary prose and says nothing about loading the skill.

The frontmatter parser handles the flat YAML a SKILL.md uses: plain, single-
and double-quoted, and block (| or >) scalars, plus indented continuation
lines. Standard library only; runs under Python 3.9.
"""

import json
import os
import re
import sys

MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 200
WRITING = "writing"
QUESTION = ("Is `<url>` a private repository on your company's Git host, "
            "under your work account?")
FAIL_CLOSED = "Any other exit, or no `python3`: don't push, and say why in your reply."

RULES = {
    "skill-file": "the folder holds no readable SKILL.md",
    "frontmatter": "the frontmatter is missing or malformed",
    "missing-name": "the frontmatter has no `name`",
    "missing-description": "the frontmatter has no `description`",
    "name-pattern": "`name` must match ^[a-z0-9]+(-[a-z0-9]+)*$",
    "name-length": "`name` is longer than %d characters" % MAX_NAME,
    "name-folder": "`name` must equal the folder name",
    "description-length": "`description` must be 1-%d characters" % MAX_DESCRIPTION,
    "description-hash": "plain `description` holds ' #', which YAML reads as a comment; quote it",
    "description-colon": "plain `description` holds ': ', which YAML rejects unquoted; quote it",
    "body-length": "the body is longer than %d lines" % MAX_BODY_LINES,
    "disable-model-invocation": "the frontmatter sets `disable-model-invocation`",
    "plugin-root-var": "uses ${CLAUDE_PLUGIN_ROOT}, which only Claude Code expands",
    "skill-dir-var": "uses ${CLAUDE_SKILL_DIR}, which only Claude Code expands",
    "names-writing": "never names the `writing` skill",
    "names-check": "never names `scripts/check.py`",
    "names-python3": "never mentions `python3` (what to do when python3 is missing)",
    "names-format": "never names `../../FORMAT.md`",
    "names-remote": "pushes without the remote check",
}

NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KEY = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.*))?$")
DISABLE_KEY = re.compile(r"^\s*disable-model-invocation\s*:")
PLUGIN_ROOT_VAR = re.compile(r"\$\{?CLAUDE_PLUGIN_ROOT\b")
SKILL_DIR_VAR = re.compile(r"\$\{?CLAUDE_SKILL_DIR\b")
WRITING_REF = re.compile(r"`writing`|devos:writing|\bwriting skill\b", re.IGNORECASE)


def parse_frontmatter(lines):
    """Top-level scalars of a flat YAML mapping.

    Returns ({key: (style, value)}, [error]) where style is "plain",
    "quoted" or "block".
    """
    fields, errors, i = {}, [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = KEY.match(line)
        if not m:
            errors.append("frontmatter line %d is not a top-level `key: value`" % (i + 2))
            i += 1
            continue
        key, raw = m.group(1), (m.group(2) or "").rstrip()
        i += 1
        cont = []
        while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
            cont.append(lines[i].strip())
            i += 1
        rest = [c for c in cont if c]
        if re.fullmatch(r"[|>][-+]?", raw):
            fields[key] = ("block", ("\n" if raw[0] == "|" else " ").join(rest))
        elif raw.startswith('"'):
            text = " ".join([raw] + rest)
            try:
                value = json.loads(text)
            except ValueError:
                errors.append("`%s` is an unparseable double-quoted scalar" % key)
                value = text
            fields[key] = ("quoted", value)
        elif raw.startswith("'"):
            text = " ".join([raw] + rest)
            if not (len(text) >= 2 and text.endswith("'")):
                errors.append("`%s` is an unterminated single-quoted scalar" % key)
            fields[key] = ("quoted", text[1:-1].replace("''", "'"))
        else:
            fields[key] = ("plain", " ".join([raw] + rest))
    return fields, errors


def split_skill(text):
    """Return (frontmatter lines or None, body lines, [frontmatter error])."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, lines, ["line 1 is not `---`"]
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            return lines[1:end], lines[end + 1:], []
    return None, lines, ["no closing `---` after the frontmatter"]


def lint_skill(skill_dir):
    """Lint one skill folder. Returns a list of (rule_id, message)."""
    problems = []

    def report(rule, detail=""):
        problems.append((rule, RULES[rule] + (" (%s)" % detail if detail else "")))

    path = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        report("skill-file", e.__class__.__name__)
        return problems

    folder = os.path.basename(os.path.normpath(os.path.abspath(skill_dir)))
    fm_lines, body_lines, fm_errors = split_skill(text)

    if fm_lines is None:
        report("frontmatter", fm_errors[0])
    else:
        fields, parse_errors = parse_frontmatter(fm_lines)
        for err in parse_errors:
            report("frontmatter", err)

        name = " ".join(fields.get("name", ("", ""))[1].split())
        if not name:
            report("missing-name")
        else:
            if not NAME_PATTERN.match(name):
                report("name-pattern", repr(name))
            if len(name) > MAX_NAME:
                report("name-length", "%d characters" % len(name))
            if name != folder:
                report("name-folder", "%r in folder %r" % (name, folder))

        if "description" not in fields:
            report("missing-description")
        else:
            style, description = fields["description"]
            collapsed = " ".join(description.split())
            if not 1 <= len(collapsed) <= MAX_DESCRIPTION:
                report("description-length", "%d characters" % len(collapsed))
            if style == "plain" and re.search(r"\s#", " " + description):
                report("description-hash")
            if style == "plain" and re.search(r":(\s|$)", description):
                report("description-colon")

        if any(DISABLE_KEY.match(line) for line in fm_lines):
            report("disable-model-invocation")

    if len(body_lines) > MAX_BODY_LINES:
        report("body-length", "%d lines" % len(body_lines))
    if PLUGIN_ROOT_VAR.search(text):
        report("plugin-root-var")
    if SKILL_DIR_VAR.search(text):
        report("skill-dir-var")

    if folder != WRITING:
        body = "\n".join(body_lines)
        if not WRITING_REF.search(body):
            report("names-writing")
        if "scripts/check.py" not in body:
            report("names-check")
        if "python3" not in body:
            report("names-python3")
        if "../../FORMAT.md" not in body:
            report("names-format")
        if "git push" in body:
            flat = " ".join(body.split())
            if "scripts/remote.py" not in body[:body.index("git push")]:
                report("names-remote", "`scripts/remote.py` is not named before the first `git push`")
            if QUESTION not in flat:
                report("names-remote", "the attestation question is not quoted word for word")
            if FAIL_CLOSED not in flat:
                report("names-remote", "the fail-closed sentence is missing")
            if "`git push`" in body:
                report("names-remote", "holds the bare command `git push`")

    return problems


USAGE = "usage: skill_lint.py <skill-dir>..."


def main(argv):
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    for arg in argv:
        if not os.path.isdir(arg):
            print("skill_lint.py: not a folder: %s" % arg, file=sys.stderr)
            return 2
    found = False
    for arg in argv:
        path = os.path.join(arg, "SKILL.md")
        for rule, message in lint_skill(arg):
            print("%s: %s: %s" % (path, rule, message))
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
