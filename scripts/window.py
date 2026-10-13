#!/usr/bin/env python3
"""Print the actions and evidence that fall inside a report's time frame.

Usage:
  python3 scripts/window.py <state-repo> --project <slug> --end <YYYY-MM-DD> [--start <YYYY-MM-DD>]
  python3 scripts/window.py <state-repo> --all --start <YYYY-MM-DD> --end <YYYY-MM-DD>

`--project` feeds a status report and `--all` a progress report. Without
`--start`, `--project` starts on the date of the newest `YYYY-MM-DD.md` in
`projects/<slug>/status-reports/` dated strictly before `--end`. A frame
includes both ends: start <= date <= end. Done actions are picked by their
done date, never their added date; evidence by its **Date**.

Output (stdout), one block per project, blank lines between blocks:

  Frame: 2026-10-09 to 2026-10-12

  Project: Checkout Revamp (checkout-revamp)

  Done actions in frame:
  - done 2026-10-10 · P1 · <action name>

  Evidence in frame:
  - 2026-10-11 · measured · <evidence name>
    Impact: <impact text>
    References: <inline references>      (or `References:` then the nested list)

  Open actions:
  - in progress · P0 · <action name>
    <the action's indented notes, kept as written>
  - to do · P2 · <action name>

The name always comes last, so a name holding ` · ` stays readable. An empty
list prints `- None`. `Open actions:` appears with `--project` only, and
lists every In progress action, then every To do action. `--project` always
prints its project; `--all` prints only projects with at least one done
action or evidence item in the frame, in folder-name order, so a quiet frame
under `--all` prints only the `Frame:` line.

Exit codes:
  0  success, including an empty frame
  1  a file in scope holds a line this script cannot read: an action line or
     date `check.py` reports as `action-line` or `date`, or an evidence item
     with no **Date** (listed at its `##` heading). Each is printed on stderr
     as `<path>:<line>: <rule>: <detail>` and stdout stays empty. In scope:
     the project's `actions.md` and `evidence.md` (`--project`), or every
     project's (`--all`).
  2  bad input: no `.devos` marker, not a folder, an unknown project, a date
     that is not a real YYYY-MM-DD, a start after the end, a bad flag
     combination, or a file that cannot be opened
  3  `--project` without `--start`, and no status report dated before `--end`

When more than one applies, 2 wins over 3, and 3 over 1.

Standard library only; runs on Python 3.9 and later. The line parsing comes
from `check.py` in this folder, so a line this script reads is exactly a
line the checker accepts.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check import (  # noqa: E402  (imported after the path is set)
    ADDED_RE,
    DONE_RE,
    REPORT_NAME_RE,
    SEP,
    SLUG_RE,
    Checker,
    Doc,
    Unreadable,
    _entries,
    check_marker,
    parse_date,
)

PROG = "window.py"
OPEN_SECTIONS = (("In progress", "in progress"), ("To do", "to do"))
ACTION_SECTIONS = ("In progress", "To do", "Done")
# The check.py rules that make a line unreadable here.
BLOCKING = ("action-line", "date")


class BadInput(Exception):
    """Exit 2 with this message."""


def real_date(text):
    """argparse type: a real YYYY-MM-DD date, kept as its text."""
    if parse_date(text) is None:
        raise argparse.ArgumentTypeError("`{}` is not a real YYYY-MM-DD date".format(text))
    return text


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog=PROG, description="Print the actions and evidence inside a report's time frame.")
    parser.add_argument("state_repo", help="state repo folder")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project", metavar="SLUG", help="one project, for a status report")
    scope.add_argument("--all", action="store_true", help="every project, for a progress report")
    parser.add_argument("--start", type=real_date, metavar="YYYY-MM-DD",
                        help="first day of the frame (default with --project: last status report)")
    parser.add_argument("--end", type=real_date, metavar="YYYY-MM-DD", required=True,
                        help="last day of the frame")
    args = parser.parse_args(argv)
    if args.all and args.start is None:
        parser.error("--all needs --start")  # exits 2
    if args.start is not None and parse_date(args.start) > parse_date(args.end):
        parser.error("start {} is after end {}".format(args.start, args.end))
    return args


def default_start(root, slug, end):
    """The newest status report date strictly before `end`, or None."""
    folder = os.path.join(root, "projects", slug, "status-reports")
    dates = []
    for name in _entries(folder, dirs=False):
        m = REPORT_NAME_RE.fullmatch(name)
        if m and parse_date(m.group(1)) is not None and m.group(1) < end:
            dates.append(m.group(1))
    return max(dates) if dates else None


class Action(object):
    def __init__(self, section, item, name, prio, added, done):
        self.section, self.item = section, item
        self.name, self.prio, self.added, self.done = name, prio, added, done


class Evidence(object):
    def __init__(self, name, date, fields):
        self.name, self.date, self.fields = name, date, fields


class Project(object):
    """One project's actions and evidence, read once; `problems` holds the
    unreadable lines as (path, line, rule, detail)."""

    def __init__(self, root, slug):
        self.slug, self.root = slug, root
        self.checker = Checker(root)
        self.actions, self.evidence, self.problems = [], [], []
        self.name = self._name()
        self._read_actions()
        self._read_evidence()

    def _doc(self, rel):
        if not os.path.isfile(self.checker.path(rel)):
            return None
        try:
            return self.checker.read(rel)
        except Unreadable as e:
            raise BadInput(str(e))

    def _name(self):
        doc = self._doc("projects/{}/project.md".format(self.slug))
        if doc:
            for h in doc.headings:
                if h.level == 1 and h.text:
                    return h.text
        return self.slug

    def _read_actions(self):
        rel = "projects/{}/actions.md".format(self.slug)
        doc = self._doc(rel)
        if doc is None:
            return
        for section in ACTION_SECTIONS:
            # The first `##` of that name counts, as in check.py.
            same = [h for h in doc.headings_in(2, 0, len(doc.lines)) if h.text == section]
            if not same:
                continue
            h = same[0]
            for item in doc.items(h.idx + 1, doc.end_of_section(h)):
                # Let check.py judge the line; keep only the defects that
                # stop us reading it.
                before = len(self.checker.defects)
                self.checker.action(rel, item, section == "Done")
                bad = [d for d in self.checker.defects[before:] if d[2] in BLOCKING]
                if bad:
                    self.problems.extend(bad)
                    continue
                self.actions.append(self._action(section, item))

    @staticmethod
    def _action(section, item):
        """Split a line check.py accepted, read from the right (FORMAT.md)."""
        parts = item.text.split(SEP)
        if section == "Done":
            done = DONE_RE.fullmatch(parts[-1].strip()).group(1)
            added = ADDED_RE.fullmatch(parts[-2].strip()).group(1)
            prio, name = parts[-3].strip(), SEP.join(parts[:-3]).strip()
        else:
            done = None
            added = ADDED_RE.fullmatch(parts[-1].strip()).group(1)
            prio, name = parts[-2].strip(), SEP.join(parts[:-2]).strip()
        return Action(section, item, name, prio, added, done)

    def _read_evidence(self):
        rel = "projects/{}/evidence.md".format(self.slug)
        doc = self._doc(rel)
        if doc is None:
            return
        for h in doc.headings_in(2, 0, len(doc.lines)):
            fields = doc.fields(*self.checker.body(doc, h))
            when = fields.get("Date")
            if when is None or not when.value:
                # check.py calls this `missing-field`; report it at the heading.
                self.problems.append((rel, h.num, "missing-field",
                                      "evidence `{}` has no `**Date:**`".format(h.text)))
                continue
            before = len(self.checker.defects)
            if self.checker.date(rel, when.num, when.value, "date") is None:
                self.problems.extend(self.checker.defects[before:])
                continue
            self.evidence.append(Evidence(h.text or "(no name)", when.value, fields))

    # --- selection -------------------------------------------------------------

    def done_in(self, start, end):
        return [a for a in self.actions if a.done is not None and start <= a.done <= end]

    def evidence_in(self, start, end):
        return [e for e in self.evidence if start <= e.date <= end]

    def open_actions(self):
        out = []
        for section, _ in OPEN_SECTIONS:
            out.extend(a for a in self.actions if a.section == section)
        return out


# --- output --------------------------------------------------------------------


def notes(lines):
    """The non-blank indented lines under an item, each kept as written."""
    return [line.rstrip() for line in lines if line.strip()]


def field_value(fields, label):
    f = fields.get(label)
    return f.value if f is not None and f.value else "(missing)"


def render_project(p, start, end, with_open):
    out = ["", "Project: {} ({})".format(p.name, p.slug), "", "Done actions in frame:"]
    done = p.done_in(start, end)
    out += ["- done {} · {} · {}".format(a.done, a.prio, a.name) for a in done] or ["- None"]

    out += ["", "Evidence in frame:"]
    items = p.evidence_in(start, end)
    if not items:
        out.append("- None")
    for e in items:
        out.append("- {} · {} · {}".format(e.date, field_value(e.fields, "Impact status"), e.name))
        out.append("  Impact: " + field_value(e.fields, "Impact"))
        refs = e.fields.get("References")
        if refs is None or not refs.value:
            out.append("  References: (missing)")
        else:
            out.append(("  References: " + refs.inline) if refs.inline else "  References:")
            out += ["  " + line for line in notes(refs.cont)]

    if with_open:
        out += ["", "Open actions:"]
        open_ = p.open_actions()
        if not open_:
            out.append("- None")
        labels = dict(OPEN_SECTIONS)
        for a in open_:
            out.append("- {} · {} · {}".format(labels[a.section], a.prio, a.name))
            out += ["  " + line for line in notes(a.item.cont)]
    return out


def run(args):
    root = args.state_repo
    if not os.path.isdir(root):
        raise BadInput("{}: not a folder".format(root))
    problem = check_marker(root)
    if problem:
        raise BadInput(problem)

    if args.project is not None:
        slug = args.project
        if not SLUG_RE.fullmatch(slug) or not os.path.isdir(os.path.join(root, "projects", slug)):
            raise BadInput("no project `{}` under projects/".format(slug))
        slugs = [slug]
    else:
        slugs = _entries(os.path.join(root, "projects"), dirs=True)

    # Read the files first, so a file that cannot be opened (exit 2) wins over
    # a missing start (exit 3), which wins over unreadable lines (exit 1).
    projects = [Project(root, s) for s in slugs]

    start, end = args.start, args.end
    if start is None:
        start = default_start(root, slugs[0], end)
        if start is None:
            print("{}: no start date: projects/{}/status-reports/ holds no report dated "
                  "before {}; pass --start".format(PROG, slugs[0], end), file=sys.stderr)
            return 3

    problems = sorted(set(d for p in projects for d in p.problems))
    if problems:
        for path, line, rule, detail in problems:
            print("{}:{}: {}: {}".format(path, line, rule, detail), file=sys.stderr)
        return 1

    lines = ["Frame: {} to {}".format(start, end)]
    for p in projects:
        if args.project is None and not (p.done_in(start, end) or p.evidence_in(start, end)):
            continue
        lines += render_project(p, start, end, with_open=args.project is not None)
    print("\n".join(lines))
    return 0


def main(argv=None):
    args = parse_args(argv)
    try:
        return run(args)
    except BadInput as e:
        print("{}: {}".format(PROG, e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
