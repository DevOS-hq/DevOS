#!/usr/bin/env python3
"""Flag banned writing patterns in markdown or plain-text files.

Usage:
  python3 scripts/banned.py <file>...     check one or more files
  python3 scripts/banned.py --categories  list every category id

Prints one line per hit, `<path>:<line>: banned: <category>: <matched text>`,
in file order, then line, then column. Exits 0 when no file has a hit, 1 when
any file has one, and 2 on a usage error (no files given, unknown option) or
when any file cannot be read as UTF-8 text (missing, a folder, no
permission). Hits in the readable files still print when the exit is 2.

Skipped, so a document can quote a banned pattern as an example:
- fenced code blocks (``` or ~~~, any indent, closed by a fence of the same
  character at least as long);
- inline code spans on one line (`like this` or ``like `this` ``);
- URLs and markdown link targets.

The check is case-insensitive and catches only what a pattern can catch
reliably. Forced triads, synonym cycling, passive voice and tone are left to
a reader or an LLM judge.

Standard library only; runs on Python 3.9 and later.
"""

import argparse
import re
import sys

# Category id -> regex. The order is the order --categories prints.
PATTERNS = [
    ("dash", r"—|–|(?:^|(?<=\s))--(?=\s|$)"),
    ("contrast-framing",
     r"(?:\bnot|n['’]t)\s+(?:just|only|merely)\b"
     r"|\bit['’]?s not \w[^.]{0,30}, it['’]?s\b"),
    ("ai-vocabulary",
     r"\b(?:delv(?:e|es|ed|ing)|tapestr(?:y|ies)|testaments?|pivotal"
     r"|crucial(?:ly)?|showcas(?:e|es|ed|ing)|foster(?:s|ed|ing)?"
     r"|intricate(?:ly)?|intricac(?:y|ies)|vibrant(?:ly)?|enduring"
     r"|garner(?:s|ed|ing)?|interplay|meticulous(?:ly)?|bolster(?:s|ed|ing)?"
     r"|underscor(?:ed|ing)"
     r"|underscores?(?=\s+(?:the|that|how|why|what|its|their|our|a|an|this|these)\b))\b"),
    ("fancy-synonym",
     r"\b(?:utili[sz](?:e|es|ed|ing|ation)|leverag(?:e|es|ed|ing)"
     r"|facilitat(?:e|es|ed|ing|ion)|in order to|due to the fact"
     r"|it is important to note)\b"),
    ("fancy-is", r"\b(?:serves|stands|functions|operates) as\b|\bboast(?:s|ed|ing)?\b"),
    ("ing-rider",
     r",\s+(?:highlighting|underscoring|emphasizing|emphasising|ensuring"
     r"|reflecting|showcasing|fostering)\b"),
    ("staged-opener",
     r"\blet['’]?s\s+(?:dive|delve|explore|unpack|break\s+(?:\w+\s+)?down)\b"
     r"|\bhere['’]?s the thing\b|\bwithout further ado\b"
     r"|\bin today['’]?s\s+(?:fast|ever|rapidly|increasingly|modern|digital"
     r"|competitive|world|landscape|age|day and age)"),
    ("chatbot-residue",
     r"\bi hope this helps\b|\blet me know\b|\bgreat question\b|\bcertainly!"
     r"|\bof course!|\byou['’]?re absolutely right\b"),
    ("knowledge-hedge",
     r"\bas of my\b|\bmy (?:last|latest) (?:training|knowledge)\b"
     r"|\bbased on (?:the )?available information\b"),
    ("borrowed-authority",
     r"\bexperts (?:say|argue|believe|agree)\b|\bindustry reports\b|\bsome critics\b"),
    ("stacked-hedge", r"\b(?:could|might|may) (?:potentially|possibly|arguably)\b"),
    ("generic-closer",
     r"\bthe future looks bright\b|\bexciting times ahead\b"
     r"|\ba step in the right direction\b"),
    ("minimizer", r"\b(?:simply|easily|quickly|please)\b"),
    ("jargon-metaphor",
     r"\bnorth stars?\b|\bflywheels?\b|\bparadigms?\b|\bnexus\b|\bbedrock\b"),
    ("typography",
     u"[“”‘’]|\\band/or\\b|(?<![/\\w])etc\\b(?!/)\\.?"
     u"|[\U0001F000-\U0001FAFF☀-➿⭐⭕]"),
]

CATEGORIES = [cat for cat, _ in PATTERNS]
COMPILED = [(cat, re.compile(rx, re.IGNORECASE)) for cat, rx in PATTERNS]

FENCE_OPEN_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
FENCE_CLOSE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[ \t]*$")
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
URL_RE = re.compile(r"https?://\S+|\]\([^)\s]*\)")


def blank(match):
    """Replace a match with spaces so columns and the rest of the line keep their place."""
    return " " * len(match.group(0))


def prose_lines(text):
    """Yield (line number, text) for each line outside code, with code spans and URLs blanked."""
    fence = None
    for num, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        if fence:
            m = FENCE_CLOSE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]:
                fence = None
            continue
        m = FENCE_OPEN_RE.match(line)
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        yield num, URL_RE.sub(blank, CODE_SPAN_RE.sub(blank, line))


def scan(text):
    """Return (line, column, category, matched text) for every hit, sorted."""
    found = []
    for num, line in prose_lines(text):
        for cat, rx in COMPILED:
            for m in rx.finditer(line):
                found.append((num, m.start(), cat, m.group(0).strip()))
    return sorted(found)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="banned.py", description="Flag banned writing patterns in text files.")
    parser.add_argument("files", nargs="*", metavar="file", help="file to check")
    parser.add_argument("--categories", action="store_true",
                        help="list every category id and exit")
    args = parser.parse_args(argv)

    if args.categories:
        print("\n".join(CATEGORIES))
        return 0
    if not args.files:
        parser.print_usage(sys.stderr)
        print("banned.py: error: give at least one file", file=sys.stderr)
        return 2

    status = 0
    for path in args.files:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            reason = e.strerror if isinstance(e, OSError) and e.strerror else str(e)
            print("banned.py: {}: {}".format(path, reason), file=sys.stderr)
            status = 2
            continue
        for num, _col, cat, match in scan(text):
            print("{}:{}: banned: {}: {}".format(path, num, cat, match))
            status = status or 1
    return status


if __name__ == "__main__":
    sys.exit(main())
