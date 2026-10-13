"""Shared logic of the stub CLIs (claude, codex, cursor-agent) for offline tests.

Each stub call appends one JSON line to $STUB_LOG:

    {"cli", "call": "model" | "plugin", "cwd", "argv", "env": {CODEX_HOME,
     GIT_*}, "stdin": "devnull" | "closed" | "other", "codex_auth": bool,
     "session_id", "prompt"}

A model call replays fixtures/<cli>.jsonl, events captured once from a live
run, with these placeholders filled in:

    {PLUGIN}   the loaded plugin copy: --plugin-dir for claude and
               cursor-agent; for codex, the copy `plugin add` installed under
               $CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>
    {REPO}     the working folder (cursor-agent: --workspace)
    {SESSION}  a new id, or the --resume / `exec resume` id
    {TEXT}     "stub reply: <prompt>"

With no plugin loaded, events naming {PLUGIN} are left out, as a real CLI
would never touch those files.

STUB_FAIL drives one failure signal while every other signal stays healthy
(so each test proves the runner checks that one signal):

    claude, cursor-agent: is_error (result has is_error: true, exit 0)
    codex: exit (normal stream, exit 1), error (an `error` event),
           turn_failed (a `turn.failed` event), no_turn_completed,
           plugin_add (`plugin add` exits 1)
    all three: garbage (only non-JSON stdout), garbage_line (one non-JSON
           line inside a healthy stream), new_session (a resumed turn
           answers with a new session id; use with STUB_FAIL_ON=resume)

STUB_FAIL_ON=resume limits the failure to resumed turns (default: all turns).

STUB_DO makes a model call change its working folder, as a real turn that
edits the state repo would (STUB_DO_ON=resume limits it to resumed turns):

    write   write stub-write.txt, left untracked
    commit  write stub-commit.txt and commit it, leaving the status clean

The codex stub refuses to run without CODEX_HOME, so a test can never touch
the real ~/.codex. Python 3.9 standard library only.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
LOGGED_ENV = (
    "CODEX_HOME", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL", "GIT_CONFIG_GLOBAL",
)

# Options that take a value, per CLI. Anything else starting with '-' is a flag.
VALUE_OPTIONS = {
    "claude": {
        "--plugin-dir", "--resume", "-r", "--permission-mode", "--output-format",
        "--input-format", "--model", "--settings", "--setting-sources",
        "--append-system-prompt", "--system-prompt", "--allowedTools",
        "--disallowedTools", "--mcp-config", "--add-dir", "--max-turns",
        "--fallback-model", "--session-id", "--json-schema", "--agents",
    },
    "cursor": {
        "--plugin-dir", "--resume", "--workspace", "--output-format", "--model",
        "--add-dir", "--api-key",
    },
    "codex": {
        "-m", "--model", "-c", "--config", "-o", "--output-last-message", "-p",
        "--profile", "-s", "--sandbox", "-C", "--cd", "--output-schema",
        "--color", "-i", "--image", "--add-dir", "--local-provider",
    },
}
# `codex exec resume` has no -C, -s or --add-dir; the real CLI rejects them.
CODEX_RESUME_REJECTS = {"-C", "--cd", "-s", "--sandbox", "--add-dir"}


def stdin_state():
    try:
        info = os.fstat(0)
    except OSError:
        return "closed"
    try:
        null = os.stat(os.devnull)
    except OSError:
        return "other"
    if stat.S_ISCHR(info.st_mode) and info.st_rdev == null.st_rdev:
        return "devnull"
    return "other"


def log(entry):
    path = os.environ.get("STUB_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def parse(cli, argv):
    """(options {flag: value or True}, positionals)."""
    options, positionals = {}, []
    takes_value = VALUE_OPTIONS[cli]
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("-") and len(arg) > 1:
            if "=" in arg and arg.startswith("--"):
                key, value = arg.split("=", 1)
                options[key] = value
            elif arg in takes_value and i + 1 < len(argv):
                options[arg] = argv[i + 1]
                i += 1
            else:
                options[arg] = True
        else:
            positionals.append(arg)
        i += 1
    return options, positionals


def fill(node, values):
    if isinstance(node, str):
        for key, value in values.items():
            node = node.replace("{" + key + "}", value)
        return node
    if isinstance(node, list):
        return [fill(item, values) for item in node]
    if isinstance(node, dict):
        return {key: fill(item, values) for key, item in node.items()}
    return node


def fixture_events(name, values):
    with open(os.path.join(FIXTURES, name + ".jsonl"), encoding="utf-8") as fh:
        lines = [line for line in fh if line.strip()]
    events = []
    for line in lines:
        if values.get("PLUGIN") is None and "{PLUGIN}" in line:
            continue
        events.append(fill(json.loads(line), {k: v for k, v in values.items() if v is not None}))
    return events


def emit(events, mode=""):
    """Print the events as JSON lines; garbage_line slips one non-JSON line before the last."""
    lines = [json.dumps(event) for event in events]
    if mode == "garbage_line":
        lines.insert(max(len(lines) - 1, 0), "stub: a stray non-JSON line")
    sys.stdout.write("".join(line + "\n" for line in lines))
    sys.stdout.flush()


def garbage():
    sys.stdout.write("stub: this is not JSON\n")
    sys.stdout.flush()
    return 0


def base_entry(cli, argv):
    entry = {
        "cli": cli,
        "cwd": os.getcwd(),
        "argv": argv,
        "env": {key: os.environ[key] for key in LOGGED_ENV if key in os.environ},
        "stdin": stdin_state(),
    }
    home = os.environ.get("CODEX_HOME")
    entry["codex_auth"] = bool(home) and os.path.isfile(os.path.join(home, "auth.json"))
    return entry


def failing(resumed):
    mode = os.environ.get("STUB_FAIL", "")
    if not mode:
        return ""
    if os.environ.get("STUB_FAIL_ON", "all") == "resume" and not resumed:
        return ""
    return mode


def act(resumed, folder):
    """Carry out STUB_DO in `folder`; a failed commit exits the stub non-zero."""
    action = os.environ.get("STUB_DO", "")
    if not action or (os.environ.get("STUB_DO_ON", "all") == "resume" and not resumed):
        return
    name = "stub-commit.txt" if action == "commit" else "stub-write.txt"
    with open(os.path.join(folder, name), "a", encoding="utf-8") as fh:
        fh.write("stub turn\n")
    if action == "commit":
        for args in (["add", "--", name], ["commit", "-q", "-m", "Stub commit"]):
            subprocess.run(["git", "-C", folder] + args, stdin=subprocess.DEVNULL, check=True,
                           capture_output=True)


# --- claude and cursor-agent ----------------------------------------------------


def result_stream(cli, argv):
    entry = base_entry(cli, argv)
    options, positionals = parse(cli, argv)
    if "-p" not in options and "--print" not in options:
        sys.stderr.write("stub {}: only -p (print) mode is stubbed\n".format(cli))
        return 2
    if cli == "claude" and options.get("--output-format") == "stream-json" and "--verbose" not in options:
        sys.stderr.write("Error: When using --print, --output-format=stream-json requires --verbose\n")
        return 1
    if not positionals:
        sys.stderr.write("stub {}: no prompt\n".format(cli))
        return 2
    prompt = positionals[-1]
    resumed = options.get("--resume") or options.get("-r")
    mode = failing(bool(resumed))
    session = resumed if isinstance(resumed, str) and mode != "new_session" else str(uuid.uuid4())
    plugin = options.get("--plugin-dir")
    repo = options.get("--workspace") if cli == "cursor" else None
    values = {
        "PLUGIN": os.path.abspath(plugin) if isinstance(plugin, str) else None,
        "REPO": os.path.abspath(repo) if isinstance(repo, str) else os.getcwd(),
        "SESSION": session,
        "TEXT": "stub reply: " + prompt,
    }
    entry.update({"call": "model", "session_id": session, "prompt": prompt})
    log(entry)
    act(bool(resumed), values["REPO"])
    if mode == "garbage":
        return garbage()
    events = fixture_events(cli, values)
    for event in events:
        if event.get("type") == "result" and mode == "is_error":
            event["is_error"] = True
            event["result"] = "stub error"
    emit(events, mode)
    return 0


# --- codex ------------------------------------------------------------------------


def codex_home():
    home = os.environ.get("CODEX_HOME")
    if not home:
        sys.stderr.write("stub codex: CODEX_HOME is not set; refusing to touch ~/.codex\n")
        return None
    return home


def codex_plugin(argv):
    entry = base_entry("codex", argv)
    entry["call"] = "plugin"
    log(entry)
    home = codex_home()
    if home is None:
        return 2
    registry = os.path.join(home, "stub-marketplaces.json")
    known = {}
    if os.path.isfile(registry):
        with open(registry, encoding="utf-8") as fh:
            known = json.load(fh)
    if argv[1:3] == ["marketplace", "add"] and len(argv) == 4:
        source = os.path.abspath(argv[3])
        with open(os.path.join(source, ".agents", "plugins", "marketplace.json"), encoding="utf-8") as fh:
            market = json.load(fh)
        known[market["name"]] = source
        with open(registry, "w", encoding="utf-8") as fh:
            json.dump(known, fh)
        print("Added marketplace {}".format(market["name"]))
        return 0
    if argv[1:2] == ["add"] and len(argv) == 3:
        if os.environ.get("STUB_FAIL") == "plugin_add":
            sys.stderr.write("stub codex: plugin add failed\n")
            return 1
        plugin, _, market_name = argv[2].partition("@")
        if market_name not in known:
            sys.stderr.write("marketplace {} not found\n".format(market_name))
            return 1
        source = known[market_name]
        with open(os.path.join(source, ".codex-plugin", "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh).get("version", "0.0.0")
        target = os.path.join(home, "plugins", "cache", market_name, plugin, version)
        if os.path.exists(target):
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        print("Installed {}".format(argv[2]))
        return 0
    sys.stderr.write("stub codex: unsupported plugin command {}\n".format(argv))
    return 2


def codex_installed(home):
    cache = os.path.join(home, "plugins", "cache")
    if not os.path.isdir(cache):
        return None
    for market in sorted(os.listdir(cache)):
        folder = os.path.join(cache, market, "devos")
        if os.path.isdir(folder):
            versions = sorted(os.listdir(folder))
            if versions:
                return os.path.join(folder, versions[-1])
    return None


def codex_exec(argv):
    entry = base_entry("codex", argv)
    resumed = argv[1:2] == ["resume"]
    rest = argv[2:] if resumed else argv[1:]
    if resumed:
        bad = [a for a in rest if a in CODEX_RESUME_REJECTS]
        if bad:
            sys.stderr.write("error: unexpected argument '{}' found\n".format(bad[0]))
            return 2
    options, positionals = parse("codex", rest)
    if "--json" not in options:
        sys.stderr.write("stub codex: only --json output is stubbed\n")
        return 2
    if resumed:
        if len(positionals) != 2:
            sys.stderr.write("stub codex: exec resume needs <id> <prompt>\n")
            return 2
        session, prompt = positionals
    else:
        if len(positionals) != 1:
            sys.stderr.write("stub codex: exec needs one prompt\n")
            return 2
        session, prompt = str(uuid.uuid4()), positionals[0]
    home = codex_home()
    if home is None:
        return 2
    mode = failing(resumed)
    if mode == "new_session":
        session = str(uuid.uuid4())
    values = {
        "PLUGIN": codex_installed(home),
        "REPO": os.getcwd(),
        "SESSION": session,
        "TEXT": "stub reply: " + prompt,
    }
    entry.update({"call": "model", "session_id": session, "prompt": prompt})
    log(entry)
    act(resumed, values["REPO"])
    if mode == "garbage":
        return garbage()
    events = fixture_events("codex", values)
    if mode == "no_turn_completed":
        events = [e for e in events if e.get("type") != "turn.completed"]
    elif mode in ("error", "turn_failed"):
        extra = (
            {"type": "error", "message": "stub error"}
            if mode == "error"
            else {"type": "turn.failed", "error": {"message": "stub turn failed"}}
        )
        at = next((i for i, e in enumerate(events) if e.get("type") == "turn.completed"), len(events))
        events.insert(at, extra)
    emit(events, mode)
    return 1 if mode == "exit" else 0


def main(cli, argv):
    if cli in ("claude", "cursor"):
        return result_stream(cli, argv)
    if argv[:1] == ["plugin"]:
        return codex_plugin(argv)
    if argv[:1] == ["exec"]:
        return codex_exec(argv)
    sys.stderr.write("stub codex: unsupported command {}\n".format(argv))
    return 2
