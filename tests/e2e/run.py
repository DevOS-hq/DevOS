#!/usr/bin/env python3
"""Run the DevOS live scenarios on Claude Code, Codex and Cursor.

Usage (from the plugin root):

    python3 tests/e2e/run.py [--cli claude|codex|cursor|all] [--scenario NAME ...] [--keep]

Live runs call the real CLIs and bill their accounts. Each scenario runs on
each selected CLI it declares, and prints one line:

    PASS <scenario> [<cli>]
    FAIL <scenario> [<cli>]: <reason>
      try 1 kept: <run_root> <state_root>

A failing scenario is re-run once before it is reported FAIL. Temp folders of
failed tries are kept and printed; passing ones are removed unless --keep.
Exit status: 0 when everything passed, 1 on any FAIL, 2 on a usage error.
DEVOS_E2E_SCENARIOS points at another scenarios folder (the offline tests use it).

Scenario module contract
------------------------
One module per scenario: tests/e2e/scenarios/<name>.py. The file name is the
scenario name; files starting with "_" are skipped. A module may import
`asserts` and `runners` directly. Attributes:

    CLIS     CLIs that run it, from "claude", "codex", "cursor". Default ("claude",).
    START    "empty" (default): an empty folder.
             "fixture": a copy of tests/fixture.
             "state-repo": the fixture as a git repo on `main` with one commit.
    PROMPT   The turn-1 prompt: a str, or a dict {cli: str} for per-CLI wording.
    ANSWERS  Scripted answers, sent in order as turns 2..n on the resumed
             turn-1 session. Each a str or {cli: str}. Default ().
    TIMEOUT  Seconds per turn. Default 900.
    UNTIL_COMMIT
             True: send no further answer once a turn moves the state repo's
             HEAD off turn 1's starting HEAD, so run.turns may be shorter than
             run.prompts. Default False: every answer is sent.

    def setup(repo, tmp):            optional
        Runs after START is built and before turn 1. `repo` is the state repo
        (the CLI's cwd). `tmp` is the folder holding it, with no plugin source
        in it, for extra fixtures such as a bare remote. Use
        runners.git(repo, ...) for git commands, which applies the neutral
        identity. Return a dict to fill "{key}" in PROMPT and ANSWERS (say
        {"remote": url}), or None.

    def check(run):                  required
        Raise AssertionError on failure, normally through asserts.* helpers.
        `run` is a runners.Run: run.cli, run.repo, run.plugin_dir (the copy),
        run.plugin_root (the copy the CLI loaded; the install cache for
        Codex), run.plugin_path(rel), run.turns, run.text (last reply),
        run.session_id, run.transcript, run.subs, run.env.
        Each runners.Turn in run.turns has argv, returncode, stdout, stderr,
        events, session_id, text, seconds, and `before` / `after`: the state
        repo's {"head": sha, "status": porcelain} just before and after the
        CLI call, None for a part a non-repo or commitless folder lacks
        (asserts.turn_unchanged compares them).

Standard library only; Python 3.9.
"""

import argparse
import importlib.util
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import runners  # noqa: E402

DEFAULT_SCENARIOS = os.path.join(HERE, "scenarios")


def scenarios_dir():
    return os.environ.get("DEVOS_E2E_SCENARIOS") or DEFAULT_SCENARIOS


def discover(folder):
    """{name: path} for every scenario module in the folder."""
    found = {}
    if os.path.isdir(folder):
        for entry in sorted(os.listdir(folder)):
            if entry.endswith(".py") and not entry.startswith("_"):
                found[entry[:-3]] = os.path.join(folder, entry)
    return found


def load(name, path):
    spec = importlib.util.spec_from_file_location("devos_scenario_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "check", None)):
        raise AttributeError("scenario {} has no check(run)".format(name))
    return module


def for_cli(value, cli):
    if isinstance(value, dict):
        if cli not in value:
            raise KeyError("no {} entry in {!r}".format(cli, value))
        return value[cli]
    return value


def attempt(module, cli):
    """One try: (passed, reason, run or None)."""
    run = None
    try:
        runner = runners.make(cli)
        run = runner.run(
            for_cli(getattr(module, "PROMPT"), cli),
            answers=[for_cli(a, cli) for a in getattr(module, "ANSWERS", ())],
            start=getattr(module, "START", "empty"),
            setup=getattr(module, "setup", None),
            timeout=getattr(module, "TIMEOUT", None),
            until_commit=getattr(module, "UNTIL_COMMIT", False),
        )
    except runners.RunnerError as exc:
        return False, str(exc), exc.run
    except Exception as exc:
        return False, "{}: {}".format(type(exc).__name__, exc), getattr(exc, "run", None)
    try:
        module.check(run)
    except AssertionError as exc:
        return False, "check: {}".format(exc), run
    except Exception:
        return False, "check raised:\n" + traceback.format_exc().rstrip(), run
    return True, "", run


def report(status, name, cli, reason=""):
    head, _, rest = (reason or "").partition("\n")
    line = "{} {} [{}]".format(status, name, cli)
    if head:
        line += ": " + head
    print(line)
    for extra in rest.splitlines():
        print("    " + extra)
    sys.stdout.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Run the DevOS live scenarios. Each failing scenario is re-run once.",
    )
    parser.add_argument(
        "--cli", choices=runners.CLIS + ("all",), default="all",
        help="CLI to run the scenarios on (default: all)",
    )
    parser.add_argument(
        "--scenario", nargs="+", action="append", metavar="NAME",
        help="scenario to run, by module name; repeatable (default: every scenario)",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="keep the temp folders of passing runs too",
    )
    args = parser.parse_args(argv)

    folder = scenarios_dir()
    available = discover(folder)
    names = [n for group in (args.scenario or []) for n in group] or sorted(available)
    unknown = [n for n in names if n not in available]
    if unknown:
        parser.error("unknown scenario(s): {} (found in {}: {})".format(
            ", ".join(unknown), folder, ", ".join(sorted(available)) or "none"))
    if not names:
        print("no scenarios found in {}".format(folder), file=sys.stderr)
        return 2
    clis = runners.CLIS if args.cli == "all" else (args.cli,)

    passed = failed = 0
    for name in names:
        try:
            module = load(name, available[name])
        except Exception as exc:
            report("FAIL", name, "-", "cannot load: {}: {}".format(type(exc).__name__, exc))
            failed += 1
            continue
        declared = tuple(getattr(module, "CLIS", ("claude",)))
        for cli in clis:
            if cli not in declared:
                continue
            print("RUN {} [{}] ...".format(name, cli), file=sys.stderr)
            sys.stderr.flush()
            ok, reason, run = attempt(module, cli)
            kept = []
            if not ok:
                if run is not None:
                    kept.append(run)
                first_reason = reason
                ok, reason, run = attempt(module, cli)
                if ok:
                    reason = "passed on the re-run; first try: " + first_reason
            if ok:
                passed += 1
                report("PASS", name, cli, reason)
                if run is not None and not args.keep:
                    run.cleanup()
            else:
                failed += 1
                if run is not None:
                    kept.append(run)
                report("FAIL", name, cli, reason)
            for number, kept_run in enumerate(kept, 1):
                print("  try {} kept: {}".format(number, kept_run.kept()))
    if passed + failed == 0:
        print("no selected scenario runs on --cli {}".format(args.cli), file=sys.stderr)
        return 2
    print("{} passed, {} failed".format(passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
