"""Helpers for a scenario's check(run). Each raises AssertionError on failure.

`run` is the runners.Run a scenario's check receives. Paths named `rel` are
relative to the state repo, with `/` separators. Scripts run from the plugin
copy (`run.plugin_dir`); transcript asserts look under the copy the CLI loaded
(`run.plugin_root`, which for Codex is the install cache).

git:         git(run, *args) -> stdout, branch, head, commit_count,
             commit_files (files one commit touched), commit_message (trailers
             such as Cursor's `Co-authored-by` removed), commit_messages,
             status (porcelain lines, untracked included), staged, untracked,
             remotes ({name: url}), commit_date(run, rev="HEAD") (committer
             date, YYYY-MM-DD)
turns:       turn_unchanged(run, n) (turn n, 1-based, left HEAD and status as
             it found them; fails for a turn run outside a git repo)
files:       path, tree, file_exists, file_missing, file_text,
             file_contains(run, rel, regex, count=None), file_lacks
scripts:     check_exit(run, expect=0) runs scripts/check.py on the state repo;
             banned_clean(run, rels) runs scripts/banned.py on state files
transcript:  read_format, writing_loaded, check_ran, plugin_file_read(run, rel),
             skill_used(run, name)
judge:       judge_pass(run, rel, tries=1, rubric=None) calls judge_file(path,
             skill_md) from e2e/judge.py, with `writing`'s SKILL.md or the
             `rubric` file as skill_md, and expects {"verdict": "pass" |
             "fail", "scores": {...}, "failures": [...]};
             judge_grounded(run, claims_text, source_text, tries=1) calls
             judge_grounded(claims_text, source_text) and expects
             {"verdict", "claims", "unsupported"}; tries=2 is best of two

Standard library only; Python 3.9.
"""

import importlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CURSOR_TRAILER = "Co-authored-by: Cursor <cursoragent@cursor.com>"
_TRAILER = re.compile(r"^Co-authored-by: Cursor <cursoragent@cursor\.com>[ \t]*$", re.I | re.M)


def fail(message):
    raise AssertionError(message)


# --- git ------------------------------------------------------------------------


def git(run, *args):
    """stdout of `git <args>` in the state repo; fails on a non-zero exit."""
    result = run.git(*args)
    if result.returncode != 0:
        fail("git {} exited {}: {}".format(" ".join(args), result.returncode, result.stderr.strip()))
    return result.stdout.rstrip("\n")


def _lines(text):
    return [line for line in text.splitlines() if line.strip()]


def branch(run):
    return git(run, "symbolic-ref", "--short", "HEAD")


def head(run):
    return git(run, "rev-parse", "HEAD")


def commit_count(run, rev="HEAD"):
    return int(git(run, "rev-list", "--count", rev))


def commit_files(run, rev="HEAD"):
    """Set of paths the commit `rev` added, changed or deleted."""
    return set(_lines(git(run, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", rev)))


def strip_trailers(message):
    """Commit message without Cursor's co-author trailer, trailing blank lines dropped."""
    return _TRAILER.sub("", message).rstrip()


def commit_message(run, rev="HEAD"):
    return strip_trailers(git(run, "log", "-1", "--format=%B", rev))


def commit_messages(run, rev="HEAD"):
    """Messages from newest to oldest, trailers removed."""
    raw = git(run, "log", "--format=%B%x00", rev)
    return [strip_trailers(m) for m in raw.split("\x00") if m.strip()]


def status(run):
    """`git status --porcelain` lines, untracked files listed one by one; [] when clean."""
    return _lines(git(run, "status", "--porcelain=v1", "--untracked-files=all"))


def commit_date(run, rev="HEAD"):
    """Committer date of `rev` as YYYY-MM-DD, in the commit's own time zone."""
    return git(run, "log", "-1", "--format=%cs", rev)


def staged(run):
    return _lines(git(run, "diff", "--cached", "--name-only"))


def untracked(run):
    return _lines(git(run, "ls-files", "--others", "--exclude-standard"))


def remotes(run):
    out = {}
    for line in _lines(git(run, "remote", "-v")):
        parts = line.split()
        if len(parts) >= 2 and line.endswith("(fetch)"):
            out[parts[0]] = parts[1]
    return out


# --- turns ----------------------------------------------------------------------


def turn_unchanged(run, n):
    """Assert turn n (1-based) left the state repo's HEAD and status as it found them.

    Fails when either snapshot has no status: outside a git repo, a turn's
    writes would leave both snapshots None and compare equal.
    """
    if not 1 <= n <= len(run.turns):
        fail("no turn {}; the run has {} turn(s)".format(n, len(run.turns)))
    turn = run.turns[n - 1]
    if any(snap is None or snap.get("status") is None for snap in (turn.before, turn.after)):
        fail("turn {} ran outside a git repo, so its changes cannot be compared".format(n))
    if turn.before != turn.after:
        before, after = turn.before, turn.after
        fail("turn {} changed the state repo: HEAD {} -> {}; status before:\n{}status after:\n{}".format(
            n, before["head"], after["head"],
            before["status"] or "(clean)\n", after["status"] or "(clean)\n"))


# --- files ----------------------------------------------------------------------


def path(run, rel):
    return os.path.join(run.repo, *rel.split("/"))


def tree(run):
    """Sorted relative paths of every file in the state repo, .git excluded."""
    out = []
    for base, dirs, files in os.walk(run.repo):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            out.append(os.path.relpath(os.path.join(base, name), run.repo).replace(os.sep, "/"))
    return sorted(out)


def file_exists(run, rel):
    if not os.path.isfile(path(run, rel)):
        fail("expected file {} in the state repo; files: {}".format(rel, ", ".join(tree(run)) or "(none)"))


def file_missing(run, rel):
    if os.path.exists(path(run, rel)):
        fail("expected no {} in the state repo".format(rel))


def file_text(run, rel):
    file_exists(run, rel)
    with open(path(run, rel), encoding="utf-8") as fh:
        return fh.read()


def file_contains(run, rel, pattern, count=None, flags=re.M):
    """Assert the regex matches in the file; with `count`, exactly that many times."""
    found = len(re.findall(pattern, file_text(run, rel), flags))
    if count is None and not found:
        fail("{} has no match for /{}/".format(rel, pattern))
    if count is not None and found != count:
        fail("{} matches /{}/ {} times, expected {}".format(rel, pattern, found, count))
    return found


def file_lacks(run, rel, pattern, flags=re.M):
    if re.search(pattern, file_text(run, rel), flags):
        fail("{} matches /{}/ but should not".format(rel, pattern))


# --- plugin scripts -------------------------------------------------------------


def _script(run, rel, *args):
    script = os.path.join(run.plugin_dir, *rel.split("/"))
    if not os.path.isfile(script):
        fail("the plugin copy has no {}".format(rel))
    return subprocess.run(
        [sys.executable, script] + list(args),
        cwd=run.repo, env=run.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )


def check_exit(run, expect=0):
    """Run the plugin copy's scripts/check.py on the state repo and assert its exit code."""
    result = _script(run, "scripts/check.py", run.repo)
    if result.returncode != expect:
        fail("check.py exited {}, expected {}:\n{}{}".format(
            result.returncode, expect, result.stdout, result.stderr))
    return result


def banned_clean(run, rels):
    """Run the plugin copy's scripts/banned.py on state files; assert no hits."""
    result = _script(run, "scripts/banned.py", *[path(run, rel) for rel in rels])
    if result.returncode != 0:
        fail("banned.py exited {}:\n{}{}".format(result.returncode, result.stdout, result.stderr))
    return result


# --- transcript -----------------------------------------------------------------


def plugin_file_read(run, rel):
    """Assert the loaded copy's `rel` (e.g. FORMAT.md) was read."""
    target = run.plugin_path(rel)
    if not run.transcript.was_read(target):
        fail("{} never read {}. Transcript:\n{}".format(run.cli, target, run.transcript.describe()))


def skill_used(run, name):
    """Assert the loaded copy's skills/<name>/SKILL.md was loaded."""
    if not run.transcript.used_skill(name, run.plugin_root):
        fail("{} never loaded the {} skill from {}. Transcript:\n{}".format(
            run.cli, name, run.plugin_root, run.transcript.describe()))


def read_format(run):
    plugin_file_read(run, "FORMAT.md")


def writing_loaded(run):
    skill_used(run, "writing")


def check_ran(run):
    """Assert the loaded copy's scripts/check.py was executed."""
    target = run.plugin_path("scripts/check.py")
    if not run.transcript.ran(target):
        fail("{} never ran {}. Transcript:\n{}".format(run.cli, target, run.transcript.describe()))


# --- judge ----------------------------------------------------------------------


def judge_pass(run, rel, judge_module=None, tries=1, rubric=None):
    """Score a state file with the LLM judge (e2e/judge.py); assert the verdict is pass.

    The criteria come from `writing`'s SKILL.md in the plugin copy, or from
    the file at `rubric` when given. With tries=2, a failed first call gets
    one fresh call; the file passes if either call passes, and two fails
    report both calls' scores.
    """
    module = judge_module or importlib.import_module("judge")
    skill = rubric or os.path.join(run.plugin_dir, "skills", "writing", "SKILL.md")
    misses = []
    for _ in range(max(1, tries)):
        verdict = module.judge_file(path(run, rel), skill)
        if (verdict or {}).get("verdict") == "pass":
            return verdict
        misses.append("scores {}; failures {}".format(
            (verdict or {}).get("scores"), (verdict or {}).get("failures")))
    fail("judge failed {} on {} call(s): {}".format(rel, len(misses), " | ".join(misses)))


def judge_grounded(run, claims_text, source_text, judge_module=None, tries=1):
    """Assert each milestone in `claims_text` traces back to `source_text` (e2e/judge.py).

    With tries=2, a failed first call gets one fresh call; the claims pass if
    either call passes, and two fails report both calls' results. `run` is
    unused and keeps the signature in line with the other asserts.
    """
    module = judge_module or importlib.import_module("judge")
    misses = []
    for _ in range(max(1, tries)):
        verdict = module.judge_grounded(claims_text, source_text)
        if (verdict or {}).get("verdict") == "pass":
            return verdict
        misses.append("claims {}; unsupported {}".format(
            (verdict or {}).get("claims"), (verdict or {}).get("unsupported")))
    fail("grounded judge failed on {} call(s): {}".format(len(misses), " | ".join(misses)))
