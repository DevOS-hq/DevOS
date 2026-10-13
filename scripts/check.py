#!/usr/bin/env python3
"""Check a DevOS state repo against FORMAT.md.

Usage:
  python3 scripts/check.py [<state-repo>]   check a state repo (default: current folder)
  python3 scripts/check.py --rules          list every rule id

Prints one line per defect, `<path>:<line>: <rule id>: <detail>`, sorted by
path then line. Exits 0 when every known file is valid, 1 when any defect is
found, and 2 when the folder is not a DevOS state repo (no `.devos` holding
`format: 1`) or the path is not a folder.

Standard library only; runs on Python 3.9 and later.
"""

import argparse
import datetime
import os
import re
import sys

RULES = [
    "marker",
    "missing-file",
    "slug",
    "filename-date",
    "title",
    "heading",
    "missing-field",
    "priority",
    "date",
    "time-frame",
    "requirement-type",
    "action-line",
    "done-date",
    "impact-status",
    "references",
    "brief-link",
    "empty-section",
]

PRIORITIES = ("P0", "P1", "P2", "P3")
MARKER = "format: 1"
SEP = " · "

SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
REPORT_NAME_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})\.md")
TIME_FRAME_RE = re.compile(r"(\S+) to (\S+)")
HEADING_RE = re.compile(r"^(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*$")
LIST_RE = re.compile(r"^(?:[-*+]|[0-9]{1,9}[.)])(?:[ \t]+(.*))?$")
THEMATIC_RE = re.compile(r"^([-*_])(?:[ \t]*\1){2,}[ \t]*$")
FIELD_RE = re.compile(r"^\*\*([^*]+?):\*\*(.*)$")
LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^()\s]+)(?:\s+\"[^\"]*\")?\)")
ADDED_RE = re.compile(r"added\s+(\S+)")
DONE_RE = re.compile(r"done\s+(\S+)")


def short(text, limit=40):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_date(text):
    """A real calendar date in YYYY-MM-DD form, or None."""
    if not DATE_RE.fullmatch(text):
        return None
    try:
        return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:]))
    except ValueError:
        return None


def anchor_slug(text):
    """GitHub's heading anchor, before numbering repeats."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").replace("*", "")
    text = re.sub(r"[^\w\- ]", "", text.strip().lower())
    return text.replace(" ", "-")


def split_commas(text):
    """Split on commas that sit outside [] and ()."""
    parts, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


class Line(object):
    def __init__(self, num, text, fenced):
        self.num, self.text, self.fenced = num, text, fenced


class Heading(object):
    def __init__(self, idx, level, text):
        self.idx, self.num, self.level, self.text = idx, idx + 1, level, text


class Item(object):
    """A top-level list item: its line, its text after the marker, the
    indented lines under it, and those of them outside code fences (`read`)."""

    def __init__(self, num, text):
        self.num, self.text, self.cont, self.read = num, text, [], []


class Field(object):
    def __init__(self, num, inline, cont, read):
        self.num, self.inline, self.cont, self.read = num, inline, cont, read
        rest = [c.strip() for c in cont if c.strip()]
        self.value = " ".join([inline] + rest).strip()


class Doc(object):
    """A markdown file split into lines, with headings found outside code fences."""

    def __init__(self, text):
        raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.lines, self.headings = [], []
        fence = None
        for idx, text in enumerate(raw):
            fenced = False
            if fence:
                fenced = True
                m = FENCE_CLOSE_RE.match(text)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                    fence = None
            else:
                m = FENCE_OPEN_RE.match(text)
                if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                    fence = (m.group(1)[0], len(m.group(1)))
                    fenced = True
            self.lines.append(Line(idx + 1, text, fenced))
            if not fenced:
                h = HEADING_RE.match(text)
                if h:
                    words = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", h.group(2) or "").strip()
                    self.headings.append(Heading(idx, len(h.group(1)), words))

    def end_of_section(self, h):
        """Index after h's section: the next heading at h's level or higher."""
        for g in self.headings:
            if g.idx > h.idx and g.level <= h.level:
                return g.idx
        return len(self.lines)

    def next_heading(self, start):
        """Index of the first heading at or after `start`."""
        for g in self.headings:
            if g.idx >= start:
                return g.idx
        return len(self.lines)

    def headings_in(self, level, start, end):
        return [h for h in self.headings if h.level == level and start <= h.idx < end]

    def items(self, start, end):
        out, cur = [], None
        for line in self.lines[start:end]:
            text = line.text
            indented = text[:1] in (" ", "\t")
            if not text.strip():
                if cur is not None:
                    cur.cont.append("")
            elif indented:
                if cur is not None:
                    cur.cont.append(text)
                    if not line.fenced:
                        cur.read.append(text)
            elif line.fenced or THEMATIC_RE.match(text):
                cur = None
            else:
                m = LIST_RE.match(text)
                if m:
                    cur = Item(line.num, (m.group(1) or "").strip())
                    out.append(cur)
                else:
                    cur = None
        return out

    def fields(self, start, end):
        """Fields in lines[start:end]; the first one with a label wins."""
        out = {}
        for item in self.items(start, end):
            m = FIELD_RE.match(item.text)
            if m and m.group(1).strip() not in out:
                out[m.group(1).strip()] = Field(item.num, m.group(2).strip(), item.cont, item.read)
        return out

    def has_content(self, start, end):
        return any(line.text.strip() for line in self.lines[start:end])

    def anchors(self):
        seen, out = {}, set()
        for h in self.headings:
            base = anchor_slug(h.text)
            n = seen.get(base, 0)
            seen[base] = n + 1
            out.add(base if n == 0 else "{}-{}".format(base, n))
        return out


class Checker(object):
    def __init__(self, root):
        self.root = root
        self.defects = []

    def add(self, path, line, rule, detail):
        if rule not in RULES:
            raise ValueError("undocumented rule id: " + rule)
        self.defects.append((path, line, rule, detail))

    def read(self, rel):
        path = os.path.join(self.root, *rel.split("/"))
        try:
            with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
                return Doc(f.read())
        except OSError as e:
            raise Unreadable("{}: cannot read: {}".format(rel, e.strerror or e))

    # --- shared checks -------------------------------------------------------

    def title(self, rel, doc, ok, shape):
        """Check the `#` title line; return (title heading or None, its line)."""
        h1s = [h for h in doc.headings if h.level == 1]
        if not h1s:
            self.add(rel, 1, "title", "missing title line `{}`".format(shape))
            return None, 1
        title = h1s[0]
        if doc.headings[0] is not title:
            self.add(rel, title.num, "title", "the title must be the first heading")
        if not ok(title.text):
            self.add(rel, title.num, "title", "title must read `{}`".format(shape))
        for extra in h1s[1:]:
            self.add(rel, extra.num, "title", "only one `#` title line is allowed")
        return title, title.num

    def body(self, doc, heading):
        """(start, end) of the lines directly under a heading, or of the lines
        before the first heading when there is no title."""
        start = 0 if heading is None else heading.idx + 1
        return start, doc.next_heading(start)

    def required(self, rel, doc, level, names, start, end, parent_line):
        """Required headings of one level, in order, inside lines[start:end]."""
        marks = "#" * level
        present = doc.headings_in(level, start, end)
        found = {}
        for name in names:
            same = [h for h in present if h.text == name]
            if not same:
                self.add(rel, parent_line, "heading", "missing heading `{} {}`".format(marks, name))
                continue
            found[name] = same[0]
            for dup in same[1:]:
                self.add(rel, dup.num, "heading", "duplicate heading `{} {}`".format(marks, name))
        last = None
        for name in names:
            if name not in found:
                continue
            h = found[name]
            if last is not None and h.num < last.num:
                self.add(rel, h.num, "heading", "`{} {}` must come after `{} {}`".format(
                    marks, name, marks, last.text))
            else:
                last = h
        return found

    def field(self, rel, fields, label, parent_line):
        """The field's value, or None after reporting it missing or empty."""
        f = fields.get(label)
        if f is None:
            self.add(rel, parent_line, "missing-field", "missing field `**{}:**`".format(label))
            return None
        if not f.value:
            self.add(rel, f.num, "missing-field", "field `**{}:**` is empty".format(label))
            return None
        return f

    def named(self, rel, h, what):
        if not h.text:
            self.add(rel, h.num, "heading", "{} heading has no name".format(what))

    def priority(self, rel, line, value):
        if value not in PRIORITIES:
            self.add(rel, line, "priority", "priority must be P0, P1, P2 or P3, not `{}`".format(
                short(value)))

    def date(self, rel, line, value, label):
        if parse_date(value) is None:
            self.add(rel, line, "date", "{} `{}` is not a real YYYY-MM-DD date".format(
                label, short(value)))
            return None
        return parse_date(value)

    def time_frame(self, rel, f):
        m = TIME_FRAME_RE.fullmatch(f.value)
        if not m:
            self.add(rel, f.num, "time-frame", "time frame must read `YYYY-MM-DD to YYYY-MM-DD`")
            return
        start = self.date(rel, f.num, m.group(1), "time frame start")
        end = self.date(rel, f.num, m.group(2), "time frame end")
        if start and end and start > end:
            self.add(rel, f.num, "time-frame", "time frame starts after it ends")

    def section_items(self, rel, doc, h):
        items = doc.items(h.idx + 1, doc.end_of_section(h))
        if not items:
            self.add(rel, h.num, "empty-section", "`{} {}` needs at least one list item".format(
                "#" * h.level, h.text))
        return items

    def report_header(self, rel, doc, report_date, ok, shape):
        title, top = self.title(rel, doc, ok, shape)
        fields = doc.fields(*self.body(doc, title))
        share = self.field(rel, fields, "Share date", top)
        if share and self.date(rel, share.num, share.value, "share date"):
            if share.value != report_date:
                self.add(rel, share.num, "filename-date",
                         "share date {} differs from the file name {}.md".format(
                             short(share.value), report_date))
        frame = self.field(rel, fields, "Time frame", top)
        if frame:
            self.time_frame(rel, frame)
        return title, top

    # --- record types ------------------------------------------------------------

    def project(self, rel, doc):
        title, top = self.title(rel, doc, bool, "# <Project name>")
        fields = doc.fields(*self.body(doc, title))
        prio = self.field(rel, fields, "Priority", top)
        if prio:
            self.priority(rel, prio.num, prio.value)
        self.field(rel, fields, "Stakeholders", top)
        found = self.required(rel, doc, 2, ["Requirements"], 0, len(doc.lines), top)
        if "Requirements" not in found:
            return
        section = found["Requirements"]
        for req in doc.headings_in(3, section.idx + 1, doc.end_of_section(section)):
            self.named(rel, req, "requirement")
            rf = doc.fields(*self.body(doc, req))
            kind = self.field(rel, rf, "Type", req.num)
            if kind and kind.value not in ("need", "want"):
                self.add(rel, kind.num, "requirement-type",
                         "type must be `need` or `want`, not `{}`".format(short(kind.value)))
            self.field(rel, rf, "Stakeholders", req.num)
            self.field(rel, rf, "Description", req.num)

    def actions(self, rel, doc):
        _, top = self.title(rel, doc, lambda t: t == "Actions", "# Actions")
        names = ["In progress", "To do", "Done"]
        found = self.required(rel, doc, 2, names, 0, len(doc.lines), top)
        for name in names:
            if name in found:
                h = found[name]
                for item in doc.items(h.idx + 1, doc.end_of_section(h)):
                    self.action(rel, item, name == "Done")

    def action(self, rel, item, done_section):
        parts = item.text.split(SEP)
        last = parts[-1].strip()
        if done_section:
            shape = "`- <name> · P<n> · added <date> · done <date>`"
            if ADDED_RE.fullmatch(last):
                self.add(rel, item.num, "action-line",
                         "an action under `## Done` must end with ` · done <date>`")
                return
            if len(parts) < 4 or not DONE_RE.fullmatch(last) \
                    or not ADDED_RE.fullmatch(parts[-2].strip()):
                self.add(rel, item.num, "action-line", "expected " + shape)
                return
            name, prio = SEP.join(parts[:-3]).strip(), parts[-3].strip()
            added = ADDED_RE.fullmatch(parts[-2].strip()).group(1)
            done = DONE_RE.fullmatch(last).group(1)
        else:
            shape = "`- <name> · P<n> · added <date>`"
            if DONE_RE.fullmatch(last):
                self.add(rel, item.num, "action-line",
                         "only actions under `## Done` carry ` · done <date>`")
                return
            if len(parts) < 3 or not ADDED_RE.fullmatch(last):
                self.add(rel, item.num, "action-line", "expected " + shape)
                return
            name, prio = SEP.join(parts[:-2]).strip(), parts[-2].strip()
            added, done = ADDED_RE.fullmatch(last).group(1), None
        if not name:
            self.add(rel, item.num, "action-line", "action has no name")
            return
        self.priority(rel, item.num, prio)
        added_date = self.date(rel, item.num, added, "added date")
        if done is not None:
            done_date = self.date(rel, item.num, done, "done date")
            if added_date and done_date and done_date < added_date:
                self.add(rel, item.num, "done-date",
                         "done {} is before added {}".format(done, added))

    def evidence(self, rel, doc):
        self.title(rel, doc, lambda t: t == "Evidence", "# Evidence")
        for h in doc.headings_in(2, 0, len(doc.lines)):
            self.named(rel, h, "evidence")
            fields = doc.fields(*self.body(doc, h))
            when = self.field(rel, fields, "Date", h.num)
            if when:
                self.date(rel, when.num, when.value, "date")
            self.field(rel, fields, "Impact", h.num)
            status = self.field(rel, fields, "Impact status", h.num)
            if status and status.value not in ("delivered", "measured"):
                self.add(rel, status.num, "impact-status",
                         "impact status must be `delivered` or `measured`, not `{}`".format(
                             short(status.value)))
            refs = self.field(rel, fields, "References", h.num)
            if refs:
                self.references(rel, refs)

    def references(self, rel, f):
        if f.value == "none":
            return
        pieces = [p.strip() for p in split_commas(f.inline) if p.strip()]
        for line in f.read:
            m = LIST_RE.match(line.strip())
            if m:
                pieces.append((m.group(1) or "").strip())
        if not pieces:
            self.add(rel, f.num, "references", "references must be markdown links or `none`")
            return
        for piece in pieces:
            if not LINK_RE.search(piece):
                self.add(rel, f.num, "references",
                         "reference `{}` is not a markdown link `[text](url)`".format(short(piece)))
                return

    def status_report(self, rel, doc, report_date):
        _, top = self.report_header(
            rel, doc, report_date,
            lambda t: t.startswith("Status report: ") and bool(t[len("Status report: "):].strip()),
            "# Status report: <Project name>")
        found = self.required(rel, doc, 2, ["Done", "Pending"], 0, len(doc.lines), top)
        for name in ("Done", "Pending"):
            if name in found:
                self.section_items(rel, doc, found[name])

    def progress_report(self, rel, doc, report_date):
        _, top = self.report_header(rel, doc, report_date, lambda t: t == "Progress report",
                                    "# Progress report")
        sections = doc.headings_in(2, 0, len(doc.lines))
        if not sections:
            self.add(rel, top, "heading", "needs at least one `## <Project name>` section")
        for h in sections:
            self.named(rel, h, "project")
            self.field(rel, doc.fields(*self.body(doc, h)), "Impact summary", h.num)
            found = self.required(rel, doc, 3, ["Progress"], h.idx + 1, doc.end_of_section(h),
                                  h.num)
            if "Progress" in found:
                self.section_items(rel, doc, found["Progress"])

    def brief(self, rel, doc, anchors):
        _, top = self.title(rel, doc, lambda t: _named_suffix(t, ": brief"),
                            "# <Spec name>: brief")
        names = ["The problem", "The goal", "The plan", "Not doing", "Still open"]
        found = self.required(rel, doc, 2, names, 0, len(doc.lines), top)
        for name in names:
            if name not in found:
                continue
            for item in self.section_items(rel, doc, found[name]):
                rest = [c.strip() for c in item.cont if c.strip()]
                if item.text == "None" and not rest:
                    continue
                read = [c.strip() for c in item.read if c.strip()]
                targets = [t for _, t in LINK_RE.findall(" ".join([item.text] + read))]
                spec_targets = [t for t in targets if t.startswith("spec.md#")]
                if not spec_targets:
                    self.add(rel, item.num, "brief-link",
                             "item does not link to `spec.md#<section>`")
                    continue
                if anchors is None:
                    continue  # spec.md is missing, reported as missing-file
                for target in spec_targets:
                    if target[len("spec.md#"):] not in anchors:
                        self.add(rel, item.num, "brief-link",
                                 "`{}` matches no heading in spec.md".format(short(target)))
                        break

    def spec(self, rel, doc):
        _, top = self.title(rel, doc, bool, "# <Spec name>")
        names = ["Summary", "Goals", "Non-goals", "Milestones", "Risks", "Open questions"]
        found = self.required(rel, doc, 2, names, 0, len(doc.lines), top)
        for name in names:
            if name in found:
                h = found[name]
                if not doc.has_content(h.idx + 1, doc.end_of_section(h)):
                    self.add(rel, h.num, "empty-section", "`## {}` is empty".format(name))

    def appendix(self, rel, doc):
        self.title(rel, doc, lambda t: _named_suffix(t, ": appendix"), "# <Spec name>: appendix")

    # --- walking the state repo -----------------------------------------------------

    def run(self):
        projects = os.path.join(self.root, "projects")
        for name in _entries(projects, dirs=True):
            self.project_folder("projects/" + name)
        self.report_folder("progress-reports", self.progress_report)

    def project_folder(self, prel):
        name = prel.rsplit("/", 1)[1]
        if not SLUG_RE.fullmatch(name):
            self.add(prel, 1, "slug", "folder name `{}` is not a slug like `my-project`".format(
                short(name)))
        self.record(prel + "/project.md", self.project, required=True)
        self.record(prel + "/actions.md", self.actions)
        self.record(prel + "/evidence.md", self.evidence)
        self.report_folder(prel + "/status-reports", self.status_report)
        for spec_name in _entries(self.path(prel + "/specs"), dirs=True):
            self.spec_folder(prel + "/specs/" + spec_name)

    def spec_folder(self, srel):
        name = srel.rsplit("/", 1)[1]
        if not SLUG_RE.fullmatch(name):
            self.add(srel, 1, "slug", "folder name `{}` is not a slug like `my-spec`".format(
                short(name)))
        spec_doc = self.record(srel + "/spec.md", self.spec, required=True)
        anchors = spec_doc.anchors() if spec_doc else None
        self.record(srel + "/brief.md", lambda rel, doc: self.brief(rel, doc, anchors),
                    required=True)
        self.record(srel + "/appendix.md", self.appendix, required=True)

    def record(self, rel, check, required=False):
        if not os.path.isfile(self.path(rel)):
            if required:
                self.add(rel, 1, "missing-file", "required file is missing")
            return None
        doc = self.read(rel)
        check(rel, doc)
        return doc

    def report_folder(self, frel, check):
        for name in _entries(self.path(frel), dirs=False):
            if not name.endswith(".md"):
                continue
            rel = frel + "/" + name
            m = REPORT_NAME_RE.fullmatch(name)
            if not m or parse_date(m.group(1)) is None:
                self.add(rel, 1, "filename-date", "report file name must be `<YYYY-MM-DD>.md`")
                continue
            check(rel, self.read(rel), m.group(1))

    def path(self, rel):
        return os.path.join(self.root, *rel.split("/"))


class Unreadable(Exception):
    """A known file exists but cannot be opened; the repo cannot be checked."""


def _named_suffix(title, suffix):
    return title.endswith(suffix) and bool(title[: -len(suffix)].strip())


def _entries(folder, dirs):
    """Sorted names of sub-folders (dirs=True) or files in a folder; dot-names skipped."""
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if name.startswith("."):
            continue
        full = os.path.join(folder, name)
        if (dirs and os.path.isdir(full)) or (not dirs and os.path.isfile(full)):
            out.append(name)
    return out


def check_marker(root):
    """None when `.devos` holds `format: 1`, else the detail of the defect."""
    path = os.path.join(root, ".devos")
    if not os.path.isfile(path):
        return "no `.devos` file: this folder is not a DevOS state repo"
    try:
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        content = None
    if content is None or content.strip() != MARKER:
        return "`.devos` must hold the single line `{}`".format(MARKER)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="check.py", description="Check a DevOS state repo against FORMAT.md.")
    parser.add_argument("state_repo", nargs="?", default=".",
                        help="state repo folder (default: current folder)")
    parser.add_argument("--rules", action="store_true", help="list every rule id and exit")
    args = parser.parse_args(argv)

    if args.rules:
        print("\n".join(RULES))
        return 0
    root = args.state_repo
    if not os.path.isdir(root):
        print("check.py: {}: not a folder".format(root), file=sys.stderr)
        return 2
    problem = check_marker(root)
    if problem:
        print(".devos:1: marker: " + problem)
        return 2

    checker = Checker(root)
    try:
        checker.run()
    except Unreadable as e:
        print("check.py: " + str(e), file=sys.stderr)
        return 2
    for path, line, rule, detail in sorted(set(checker.defects)):
        print("{}:{}: {}: {}".format(path, line, rule, detail))
    return 1 if checker.defects else 0


if __name__ == "__main__":
    sys.exit(main())
