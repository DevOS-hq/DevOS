"""Headless runners for the DevOS live scenarios: Claude Code, Codex and Cursor.

A runner copies the plugin to a temp folder, builds the start state in a second
temp folder, sends the first prompt as turn 1, then resumes the turn-1 session
once per scripted answer. It returns a `Run`. Every failure signal raises
`RunnerError`, which names the CLI and carries the run, so the temp folders
(kept on failure) can be inspected. The scenario module contract and the
command line live in run.py; scenario checks use asserts.py.

    runner = make("claude")                  # or "codex", "cursor"
    run = runner.run(prompt, answers=(...), start="fixture", setup=None)
    run.transcript.was_read(run.plugin_path("FORMAT.md"))
    run.cleanup()

One run on disk (each root is a fresh mkdtemp folder):

    <run_root>/plugin/       the plugin copy handed to the CLI
    <run_root>/codex-home/   Codex only: CODEX_HOME with auth.json and the install cache
    <run_root>/gitconfig     empty file, used as GIT_CONFIG_GLOBAL
    <run_root>/logs/         argv, stdout and stderr of every call
    <state_root>/repo/       the state repo, the CLI's cwd
    <state_root>/...         anything a scenario's setup hook adds

The plugin copy is never in a parent folder of the state repo, nor next to one,
so a model cannot pass by finding skill files on disk.

How each CLI is driven (closed stdin on every call):

- claude: `claude -p --plugin-dir <copy> --permission-mode bypassPermissions
  --output-format stream-json --verbose --setting-sources project,local
  --strict-mcp-config [--resume <id>] <prompt>`. The last two flags drop the
  user's ~/.claude settings (hooks, global instructions, commit trailers) and
  MCP servers, so they cannot rewrite a run's commands or commits. The session
  id and final text come from the `result` event. Failure: `is_error: true`.
- cursor: `cursor-agent -p --plugin-dir <copy> --workspace <repo> --trust
  --force --output-format stream-json [--resume <id>] <prompt>`. Same result
  event and failure signal as Claude. Known limit: cursor-agent has no flag to
  ignore user-level config, so a run can still see the user's own skills; that
  is why `init` names the writing skill by its path relative to the plugin.
- codex: a temp CODEX_HOME holding a copy of ~/.codex/auth.json (or
  $DEVOS_E2E_CODEX_AUTH), then `codex plugin marketplace add <copy>` and
  `codex plugin add devos@devos`, which installs the plugin into
  <codex-home>/plugins/cache/. Turns run `codex exec --json
  --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox <prompt>`
  and `codex exec resume <same flags> <id> <answer>`. The session id is
  `thread_id` on `thread.started`. Failure: a non-zero exit, an `error` or
  `turn.failed` event, or no `turn.completed`.
- all three: output that is not one JSON object per line is a failure, and so
  is a resumed turn that reports a different session id.

`Run.plugin_root` is the copy the CLI loaded skills from: the plugin copy for
Claude and Cursor, the install cache copy for Codex. Transcript asserts check
paths under it. `Run.text` is the last turn's reply: Claude's final message,
Codex's last agent message, and for Cursor every assistant message of the turn
joined together (that is what its `result` holds).

Every call runs with GIT_AUTHOR_* and GIT_COMMITTER_* set to
`DevOS Test <test@example.invalid>`, GIT_CONFIG_GLOBAL set to an empty temp
file and GIT_CONFIG_NOSYSTEM=1, and with inherited `git -c` variables
(GIT_CONFIG_PARAMETERS, GIT_CONFIG_COUNT and its keys) dropped, so the user's
git config cannot leak in. Claude runs also ignore user
settings and MCP servers, and Codex runs use a temp CODEX_HOME (see above).
Variables an enclosing Claude Code session sets (SESSION_VARS) are dropped,
so a run started from inside an agent behaves like one started from a
terminal. Extra CLI flags (a cheaper
model, say) can be added with DEVOS_E2E_CLAUDE_ARGS, DEVOS_E2E_CODEX_ARGS or
DEVOS_E2E_CURSOR_ARGS, which are split like a shell line and go after the
built-in flags. DEVOS_E2E_TIMEOUT
sets the default seconds per turn.

Transcript: the tool calls of every turn, normalized into `Event`s:

    event.kind     "read" | "skill" | "shell" | "write" | "edit" | "other"
    event.tool     the CLI's own tool name ("Read", "command_execution", "readToolCall", ...)
    event.paths    absolute, symlink-resolved paths the call named
    event.runs     scripts a shell command executed (python3 <script>, ./script, sh <script>)
    event.command  shell command text, else ""
    event.skill    skill name of a skill-tool call ("devos:writing"), else ""
    event.turn     1-based turn number

    transcript.paths(kinds=None)       every path named, in order
    transcript.was_read(path)          a read, shell or skill call named the path
    transcript.ran(path)               a shell call executed the script
    transcript.used_skill(name, root)  <root>/skills/<name>/SKILL.md was loaded
    transcript.describe()              one line per event, for failure messages

A Claude `Skill` call for `devos:<name>` resolves to the SKILL.md under the
plugin path that Claude's `system/init` event reports, so it counts as a load
of that copy.

Standard library only; Python 3.9.
"""

import glob
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.dirname(HERE)
PLUGIN_SRC = os.path.dirname(TESTS)

CLIS = ("claude", "codex", "cursor")
BINARIES = {"claude": "claude", "codex": "codex", "cursor": "cursor-agent"}
STARTS = ("empty", "fixture", "state-repo")
KINDS = ("read", "skill", "shell", "write", "edit", "other")
PLUGIN = "devos"
MARKETPLACE = "devos"
IDENTITY = {
    "GIT_AUTHOR_NAME": "DevOS Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "DevOS Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
# Inherited variables that would point git at another repository.
GIT_LOCATION_VARS = (
    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_PREFIX",
    "GIT_NAMESPACE", "GIT_CEILING_DIRECTORIES",
)
# Inherited variables that add git config on top of the files: `git -c` in an
# enclosing process, GIT_CONFIG_COUNT with its GIT_CONFIG_KEY_n and _VALUE_n.
GIT_CONFIG_VARS = ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG")
GIT_CONFIG_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
# Variables an enclosing Claude Code session sets for its own children. A run
# drops them so it behaves the same from a terminal or from inside an agent.
SESSION_VARS = (
    "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_SESSION_ATTENDED",
    "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
    "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_SSE_PORT", "CLAUDE_PID", "CLAUDE_EFFORT",
)
DEFAULT_TIMEOUT = 900
INSTALL_TIMEOUT = 180
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git")


class RunnerError(Exception):
    """A CLI run failed. `cli` names the CLI; `run` holds the kept temp folders."""

    def __init__(self, cli, message, run=None):
        Exception.__init__(self, "{}: {}".format(cli, message))
        self.cli = cli
        self.message = message
        self.run = run


# --- paths and shell commands -------------------------------------------------


def canon(path):
    """Absolute, symlink-resolved form of an absolute path."""
    return os.path.realpath(os.path.expanduser(path))


def _resolve(token, cwd):
    path = os.path.expanduser(token)
    if not os.path.isabs(path):
        if not cwd:
            return None
        path = os.path.join(cwd, path)
    return canon(path)


_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
_REDIRECTS = {">", ">>", "<", "<<", "<<<", ">&", "&>", "&>>", "<&", ">|"}
_PYTHON = re.compile(r"^python(\d+(\.\d+)?)?$")
_PYTHON_VALUE_OPTIONS = {"-X", "-W", "--check-hash-based-pycs"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_WRAPPERS = {"env", "command", "exec", "time", "nohup", "sudo"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _expand(word, env):
    """`$NAME` and `${NAME}` replaced for names in env; others left as they are."""
    def sub(match):
        name = match.group(1) or match.group(2)
        return env.get(name, match.group(0))
    return _VARIABLE.sub(sub, word) if "$" in word else word


def _assign(words, env):
    for word in words:
        if _ASSIGNMENT.match(word):
            name, value = word.split("=", 1)
            env[name] = value


_HEREDOC = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _lex(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    return list(lexer)


def _drop_heredoc_bodies(command):
    """The command with each heredoc's body and closing word removed."""
    lines, out, i = command.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        for match in _HEREDOC.finditer(lines[i]):
            strip_tabs, word = match.group(1) == "-", match.group(3)
            i += 1
            while i < len(lines) and (lines[i].lstrip("\t") if strip_tabs else lines[i]) != word:
                i += 1
        i += 1
    return "\n".join(out)


def _tokens(command):
    """Shell words; runs of `();<>|&` and unquoted newlines come out as their own tokens.

    When the whole command does not parse (an apostrophe in a heredoc body or
    a comment), heredoc bodies are dropped and each line is parsed alone, so
    the lines after the bad one still count.
    """
    try:
        return _lex(command)
    except ValueError:
        pass
    words = []
    for line in _drop_heredoc_bodies(command).split("\n"):
        try:
            words.extend(_lex(line))
        except ValueError:
            words.extend(line.split())
        words.append("\n")
    return words


def _pathish(token):
    if not token or token.startswith("-") or "$" in token or "://" in token:
        return False
    if "\n" in token or " " in token:
        return False
    return token.startswith(("/", "~", "./", "../")) or "/" in token


def command_paths(command, cwd, depth=0):
    """(paths, runs, cwd after) for a shell command.

    `paths` holds every path-like word, resolved against the working folder,
    which follows `cd`. `runs` holds the scripts the command executes: the
    script after python3, sh or bash, or a program named by its path. A
    `sh -c '<script>'` body is parsed the same way. A variable set earlier in
    the command (`P=/x;` or `export P=/x;`) is expanded in later words.
    """
    paths, runs = [], []
    words, env = [], {}
    for token in _tokens(command) + [";"]:
        if token in _SEPARATORS or (token and set(token) <= set("();&|\n")):
            if words:
                cwd = _segment(words, cwd, paths, runs, depth, env)
            words = []
        else:
            words.append(token)
    return paths, runs, cwd


def _add(target, path):
    if path and path not in target:
        target.append(path)


_BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")


def _braces(word, limit=64):
    """Shell brace expansion: a/{b,c}/d -> a/b/d, a/c/d."""
    match = _BRACE.search(word)
    if not match:
        return [word]
    out = []
    for part in match.group(1).split(","):
        out.extend(_braces(word[: match.start()] + part + word[match.end():], limit))
        if len(out) >= limit:
            break
    return out[:limit]


def _add_paths(target, word, cwd):
    if _pathish(word):
        for expanded in _braces(word):
            _add(target, _resolve(expanded, cwd))


def _segment(words, cwd, paths, runs, depth, env):
    args, redirect = [], False
    for word in (_expand(w, env) for w in words):
        if redirect:
            redirect = False
            _add_paths(paths, word, cwd)
            continue
        if word in _REDIRECTS:
            redirect = True
            continue
        args.append(word)
    for word in args:
        candidate = word.split("=", 1)[1] if word.startswith("--") and "=" in word else word
        _add_paths(paths, candidate, cwd)
    i, wrapped = 0, False
    while i < len(args):
        if _ASSIGNMENT.match(args[i]) or os.path.basename(args[i]) in _WRAPPERS:
            wrapped = wrapped or not _ASSIGNMENT.match(args[i])
        elif not (wrapped and args[i].startswith("-")):
            break
        i += 1
    rest = args[i:]
    if not rest:
        _assign(args, env)
        return cwd
    program = rest[0]
    base = os.path.basename(program)
    if base == "export":
        _assign(rest[1:], env)
        return cwd
    if base == "cd":
        target = rest[1] if len(rest) > 1 else "~"
        if "$" in target:
            return cwd
        return _resolve(target, cwd) or cwd
    if base in _SHELLS:
        for j in range(1, len(rest)):
            arg = rest[j]
            if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
                if j + 1 < len(rest) and depth < 4:
                    inner_paths, inner_runs, _ = command_paths(rest[j + 1], cwd, depth + 1)
                    for path in inner_paths:
                        _add(paths, path)
                    for path in inner_runs:
                        _add(runs, path)
                return cwd
            if not arg.startswith("-"):
                _add(runs, _resolve(arg, cwd))
                return cwd
        return cwd
    if _PYTHON.match(base):
        skip = False
        for arg in rest[1:]:
            if skip:
                skip = False
                continue
            if arg in ("-m", "-c", "-"):
                break
            if arg in _PYTHON_VALUE_OPTIONS:
                skip = True
                continue
            if arg.startswith("-"):
                continue
            _add(runs, _resolve(arg, cwd))
            break
        return cwd
    if "/" in program and "$" not in program:
        _add(runs, _resolve(program, cwd))
    return cwd


# --- transcript ----------------------------------------------------------------


class Event(object):
    """One normalized tool call. See the module docstring for the fields."""

    def __init__(self, kind, tool, paths=(), command="", skill="", runs=(), turn=1, raw=None):
        self.kind = kind
        self.tool = tool
        self.paths = tuple(p for p in paths if p)
        self.command = command or ""
        self.skill = skill or ""
        self.runs = tuple(p for p in runs if p)
        self.turn = turn
        self.raw = raw

    def describe(self):
        detail = self.command or self.skill or " ".join(self.paths)
        detail = detail.replace("\n", " ")
        if len(detail) > 200:
            detail = detail[:197] + "..."
        return "turn {} {} {}: {}".format(self.turn, self.kind, self.tool, detail)

    def __repr__(self):
        return "Event({})".format(self.describe())


class Transcript(object):
    """The tool calls of a run, in order, across every turn."""

    def __init__(self, events=()):
        self.events = list(events)

    def extend(self, events):
        self.events.extend(events)

    def paths(self, kinds=None):
        out = []
        for event in self.events:
            if kinds is None or event.kind in kinds:
                for path in event.paths:
                    _add(out, path)
        return out

    def was_read(self, path):
        target = canon(path)
        return any(
            target in event.paths
            for event in self.events
            if event.kind in ("read", "shell", "skill")
        )

    def ran(self, path):
        target = canon(path)
        return any(target in event.runs for event in self.events)

    def used_skill(self, name, root):
        return self.was_read(os.path.join(root, "skills", name, "SKILL.md"))

    def skills(self):
        return [event.skill for event in self.events if event.kind == "skill"]

    def describe(self, limit=80):
        lines = [event.describe() for event in self.events[:limit]]
        if len(self.events) > limit:
            lines.append("... {} more events".format(len(self.events) - limit))
        return "\n".join(lines) if lines else "(no tool calls)"


def normalize(cli, events, cwd=None, turn=1):
    """Turn one CLI turn's raw stream events into a list of `Event`s."""
    if cli == "claude":
        return _claude_events(events, cwd, turn)
    if cli == "codex":
        return _codex_events(events, cwd, turn)
    if cli == "cursor":
        return _cursor_events(events, cwd, turn)
    raise ValueError("unknown CLI: {}".format(cli))


def _file_event(kind, tool, path, cwd, turn, raw):
    resolved = _resolve(path, cwd) if isinstance(path, str) and path else None
    return Event(kind, tool, [resolved] if resolved else [], turn=turn, raw=raw)


def _claude_plugins(events):
    plugins = {}
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            for plugin in event.get("plugins") or []:
                if isinstance(plugin, dict) and plugin.get("name") and plugin.get("path"):
                    plugins[plugin["name"]] = plugin["path"]
    return plugins


def _skill_file(skill, plugins):
    name = skill.lstrip("/")
    if ":" in name:
        space, name = name.split(":", 1)
        roots = [plugins[space]] if space in plugins else []
    else:
        roots = list(plugins.values())
    for root in roots:
        path = os.path.join(root, "skills", name, "SKILL.md")
        if len(roots) == 1 or os.path.isfile(path):
            return canon(path)
    return None


_SKILL_BASE = "Base directory for this skill: "


def _claude_skill_base(event, pending, out, turn):
    """Attach the folder from Claude's skill-load text to its Skill call.

    After a skill loads, Claude adds a user text block that starts with
    "Base directory for this skill: <folder>". A skill invoked by a
    `/plugin:skill` prompt has no Skill call, so it becomes its own event.
    """
    for block in (event.get("message") or {}).get("content") or []:
        text = block.get("text") if isinstance(block, dict) else None
        if not isinstance(text, str) or not text.startswith(_SKILL_BASE):
            continue
        folder = text[len(_SKILL_BASE):].split("\n", 1)[0].strip()
        if not os.path.isabs(folder):
            continue
        path = canon(os.path.join(folder, "SKILL.md"))
        name = os.path.basename(folder)
        target = next((e for e in pending if e.skill.split(":")[-1] == name), None)
        if target is not None:
            pending.remove(target)
            if path not in target.paths:
                target.paths = target.paths + (path,)
        else:
            out.append(Event("skill", "prompt", [path], skill=name, turn=turn, raw=block))


def _claude_events(events, cwd, turn):
    plugins = _claude_plugins(events)
    out, shell_cwd, pending = [], cwd, []
    for event in events:
        if event.get("type") == "user":
            _claude_skill_base(event, pending, out, turn)
            continue
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            args = block.get("input") or {}
            if name == "Bash":
                command = args.get("command") or ""
                paths, runs, shell_cwd = command_paths(command, shell_cwd)
                out.append(Event("shell", name, paths, command, runs=runs, turn=turn, raw=block))
            elif name == "Skill":
                skill = args.get("skill") or args.get("command") or args.get("name") or ""
                path = _skill_file(skill, plugins) if skill else None
                out.append(Event("skill", name, [path] if path else [], skill=skill, turn=turn, raw=block))
                pending.append(out[-1])
            elif name == "Read":
                out.append(_file_event("read", name, args.get("file_path"), cwd, turn, block))
            elif name == "Write":
                out.append(_file_event("write", name, args.get("file_path"), cwd, turn, block))
            elif name in ("Edit", "MultiEdit", "NotebookEdit"):
                target = args.get("file_path") or args.get("notebook_path")
                out.append(_file_event("edit", name, target, cwd, turn, block))
            else:
                out.append(_file_event("other", name, args.get("path") or args.get("file_path"), cwd, turn, block))
    return out


def _codex_events(events, cwd, turn):
    items, order = {}, []
    for event in events:
        if event.get("type") not in ("item.started", "item.updated", "item.completed"):
            continue
        item = event.get("item") or {}
        key = item.get("id") or "anon-{}".format(len(order))
        if key not in items:
            order.append(key)
        items[key] = item
    out = []
    for key in order:
        item = items[key]
        kind = item.get("type") or ""
        if kind == "command_execution":
            command = item.get("command") or ""
            paths, runs, _ = command_paths(command, cwd)
            out.append(Event("shell", kind, paths, command, runs=runs, turn=turn, raw=item))
        elif kind == "file_change":
            paths = [_resolve(c.get("path"), cwd) for c in item.get("changes") or [] if c.get("path")]
            out.append(Event("write", kind, paths, turn=turn, raw=item))
        elif kind in ("mcp_tool_call", "web_search", "collab_tool_call"):
            out.append(Event("other", kind, turn=turn, raw=item))
    return out


_CURSOR_KINDS = {"read": "read", "edit": "edit", "write": "write", "shell": "shell"}


def _cursor_events(events, cwd, turn):
    calls, order = {}, []
    for event in events:
        if event.get("type") != "tool_call":
            continue
        key = event.get("call_id") or "anon-{}".format(len(order))
        if key not in calls:
            order.append(key)
            calls[key] = event
        elif event.get("subtype") == "completed":
            calls[key] = event
    out = []
    for key in order:
        body = calls[key].get("tool_call") or {}
        for name, call in body.items():
            # Siblings such as toolCallId and startedAtMs are metadata, not calls.
            if not name.endswith("ToolCall") or not isinstance(call, dict):
                continue
            tool = name[: -len("ToolCall")]
            args = call.get("args") or {}
            kind = _CURSOR_KINDS.get(tool, "other")
            if kind == "shell":
                command = args.get("command") or ""
                where = args.get("workingDirectory") or ""
                where = _resolve(where, cwd) if where else cwd
                paths, runs, _ = command_paths(command, where)
                out.append(Event("shell", name, paths, command, runs=runs, turn=turn, raw=call))
            else:
                out.append(_file_event(kind, name, args.get("path"), cwd, turn, call))
    return out


# --- git ------------------------------------------------------------------------


def neutral_env(gitconfig=os.devnull, base=None):
    """A copy of the environment with the neutral git identity and no user git config."""
    env = dict(os.environ if base is None else base)
    for var in list(env):
        if var in GIT_LOCATION_VARS or var in GIT_CONFIG_VARS or var.startswith(GIT_CONFIG_PREFIXES):
            env.pop(var)
    env.update(IDENTITY)
    env["GIT_CONFIG_GLOBAL"] = gitconfig
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def git(repo, *args, **kw):
    """Run git in `repo` with the neutral identity; return stdout. For setup hooks.

    Raises subprocess.CalledProcessError on a non-zero exit. Pass env=... to
    reuse a run's environment.
    """
    env = kw.pop("env", None) or neutral_env()
    result = subprocess.run(
        ["git", "-C", repo] + list(args),
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, ["git"] + list(args), result.stdout, result.stderr
        )
    return result.stdout


def snapshot(repo, env):
    """{"head": sha, "status": porcelain} of `repo`; None for a part git cannot give.

    A folder that is not a repo gives None for both, a repo with no commits
    None for head. GIT_CEILING_DIRECTORIES stops git at `repo`, so a folder
    inside some other repo never reports that repo. Never raises.
    """
    env = dict(env, GIT_CEILING_DIRECTORIES=os.path.dirname(repo))

    def out(*args):
        try:
            result = subprocess.run(
                ["git", "-C", repo] + list(args),
                env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            )
        except OSError:
            return None
        return result.stdout if result.returncode == 0 else None

    head = out("rev-parse", "--verify", "-q", "HEAD")
    return {
        "head": head.strip() if head else None,
        "status": out("status", "--porcelain=v1", "--untracked-files=all"),
    }


# --- runs -------------------------------------------------------------------------


class Turn(object):
    """One CLI call: argv, exit status, raw output, parsed events, session id, final text.

    `before` and `after` are the state repo's snapshot() taken just before and
    just after the call.
    """

    def __init__(self, index, argv):
        self.index = index
        self.argv = argv
        self.returncode = None
        self.stdout = ""
        self.stderr = ""
        self.events = []
        self.session_id = None
        self.text = ""
        self.seconds = 0.0
        self.before = None
        self.after = None


class Run(object):
    """The outcome of one runner.run(): paths, turns, transcript and environment."""

    def __init__(self, cli, run_root, state_root, env):
        self.cli = cli
        self.run_root = run_root
        self.state_root = state_root
        self.plugin_dir = os.path.join(run_root, "plugin")
        self.plugin_root = self.plugin_dir
        self.repo = os.path.join(state_root, "repo")
        self.gitconfig = os.path.join(run_root, "gitconfig")
        self.logs = os.path.join(run_root, "logs")
        self.env = env
        self.subs = {}
        self.prompts = []
        self.turns = []
        self.transcript = Transcript()
        self.session_id = None
        self.text = ""

    def plugin_path(self, rel):
        """Path of `rel` inside the copy the CLI loaded (the install cache for Codex)."""
        return os.path.join(self.plugin_root, *rel.split("/"))

    def git(self, *args):
        """Run git in the state repo with the run's environment; return the CompletedProcess."""
        return subprocess.run(
            ["git", "-C", self.repo] + list(args),
            env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        )

    def kept(self):
        return "{} {}".format(self.run_root, self.state_root)

    def cleanup(self):
        for path in (self.run_root, self.state_root):
            shutil.rmtree(path, ignore_errors=True)


def _fill(text, subs):
    for key, value in subs.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def _short(text, limit=400):
    text = (text or "").strip().replace("\n", " | ")
    return text if len(text) <= limit else text[: limit - 3] + "..."


class _Problem(Exception):
    pass


def _parse_lines(stdout):
    events = []
    for number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError:
            raise _Problem("unparseable output on line {}: {!r}".format(number, line[:160]))
        if not isinstance(event, dict):
            raise _Problem("unparseable output on line {}: not a JSON object".format(number))
        events.append(event)
    if not events:
        raise _Problem("unparseable output: no JSON events on stdout")
    return events


class Runner(object):
    """Shared driver. Subclasses set `cli` and build each turn's argv."""

    cli = None

    def __init__(self, plugin_src=PLUGIN_SRC, tmp_base=None, timeout=None,
                 extra_args=None, codex_auth=None):
        self.plugin_src = os.path.abspath(plugin_src)
        self.tmp_base = tmp_base
        self.timeout = timeout or int(os.environ.get("DEVOS_E2E_TIMEOUT") or DEFAULT_TIMEOUT)
        if extra_args is None:
            extra_args = shlex.split(os.environ.get("DEVOS_E2E_{}_ARGS".format(self.cli.upper()), ""))
        self.extra_args = list(extra_args)
        self.codex_auth = codex_auth
        self.binary = BINARIES[self.cli]

    # public

    def run(self, prompt, answers=(), start="empty", setup=None, timeout=None, until_commit=False):
        """Run turn 1 with `prompt`, then one resumed turn per answer. Return the Run.

        With `until_commit`, stop once a turn leaves HEAD off turn 1's starting
        HEAD: no further answer is sent. run.prompts keeps every prompt;
        run.turns holds only the turns that ran.
        """
        if start not in STARTS:
            raise ValueError("unknown start state {!r}; use one of {}".format(start, ", ".join(STARTS)))
        run = self._new_run()
        try:
            self._build_start(run, start)
            if setup is not None:
                try:
                    subs = setup(run.repo, run.state_root)
                except Exception as exc:  # a scenario bug, reported with the kept paths
                    raise RunnerError(self.cli, "setup hook failed: {!r}".format(exc), run)
                run.subs = dict(subs or {})
            run.prompts = [_fill(prompt, run.subs)] + [_fill(a, run.subs) for a in answers]
            for text in run.prompts:
                if not text or text.startswith("-"):
                    raise RunnerError(self.cli, "a prompt may not be empty or start with '-': {!r}".format(text), run)
            self._install(run)
            for index, text in enumerate(run.prompts, 1):
                self._turn(run, index, text, timeout or self.timeout)
                if until_commit and run.turns[-1].after["head"] != run.turns[0].before["head"]:
                    break
        except RunnerError:
            raise
        except OSError as exc:
            raise RunnerError(self.cli, "could not prepare the run: {}".format(exc), run)
        return run

    # setup

    def _new_run(self):
        run_root = canon(tempfile.mkdtemp(prefix="devos-e2e-", dir=self.tmp_base))
        state_root = canon(tempfile.mkdtemp(prefix="devos-state-", dir=self.tmp_base))
        gitconfig = os.path.join(run_root, "gitconfig")
        env = neutral_env(gitconfig)
        for var in SESSION_VARS:
            env.pop(var, None)
        run = Run(self.cli, run_root, state_root, env)
        open(gitconfig, "w").close()
        os.makedirs(run.logs)
        shutil.copytree(self.plugin_src, run.plugin_dir, ignore=COPY_IGNORE)
        return run

    def _build_start(self, run, start):
        if start == "empty":
            os.makedirs(run.repo)
            return
        fixture = os.path.join(self.plugin_src, "tests", "fixture")
        shutil.copytree(fixture, run.repo, ignore=COPY_IGNORE)
        if start == "state-repo":
            try:
                git(run.repo, "init", "-q", "-b", "main", env=run.env)
                git(run.repo, "add", "-A", env=run.env)
                git(run.repo, "commit", "-q", "-m", "Start state", env=run.env)
            except subprocess.CalledProcessError as exc:
                raise RunnerError(self.cli, "could not build the state-repo start: {}".format(_short(exc.stderr)), run)

    def _install(self, run):
        """Codex installs the plugin here; Claude and Cursor load --plugin-dir per call."""

    # turns

    def _argv(self, run, prompt, resume):
        raise NotImplementedError

    def _call(self, run, argv, cwd, timeout, label):
        name = label.replace(" ", "-")
        with open(os.path.join(run.logs, name + ".argv.json"), "w", encoding="utf-8") as fh:
            json.dump({"cwd": cwd, "argv": argv}, fh, indent=1)
        started = time.time()
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, env=run.env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
            )
        except OSError as exc:
            raise RunnerError(self.cli, "{}: cannot start {}: {}".format(label, argv[0], exc), run)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            out, err = proc.communicate()
            self._save(run, name, out, err)
            raise RunnerError(self.cli, "{}: timed out after {} s".format(label, timeout), run)
        out, err = self._save(run, name, out, err)
        return proc.returncode, out, err, time.time() - started

    @staticmethod
    def _save(run, name, out, err):
        out = (out or b"").decode("utf-8", "replace")
        err = (err or b"").decode("utf-8", "replace")
        for suffix, text in ((".stdout", out), (".stderr", err)):
            with open(os.path.join(run.logs, name + suffix), "w", encoding="utf-8") as fh:
                fh.write(text)
        return out, err

    def _turn(self, run, index, prompt, timeout):
        resume = run.session_id if index > 1 else None
        turn = Turn(index, self._argv(run, prompt, resume))
        run.turns.append(turn)
        label = "turn {}".format(index)
        turn.before = snapshot(run.repo, run.env)
        turn.returncode, turn.stdout, turn.stderr, turn.seconds = self._call(
            run, turn.argv, run.repo, timeout, label
        )
        turn.after = snapshot(run.repo, run.env)
        try:
            turn.events = _parse_lines(turn.stdout)
            problems = self._problems(turn)
        except _Problem as exc:
            problems = [str(exc)]
        if index > 1 and turn.session_id and turn.session_id != run.session_id:
            problems.append(
                "resumed session id {} differs from turn 1's {}".format(turn.session_id, run.session_id)
            )
        if index == 1 and not problems and not turn.session_id:
            problems.append("no session id in the output")
        if problems:
            message = "{}: {}".format(label, "; ".join(problems))
            if turn.stderr.strip():
                message += "; stderr: " + _short(turn.stderr)
            raise RunnerError(self.cli, message, run)
        if index == 1:
            run.session_id = turn.session_id
        run.text = turn.text
        run.transcript.extend(normalize(self.cli, turn.events, cwd=run.repo, turn=index))

    def _problems(self, turn):
        raise NotImplementedError


class _ResultStreamRunner(Runner):
    """Claude and Cursor: stream-json events ending in one `result` event."""

    def _problems(self, turn):
        problems = []
        results = [e for e in turn.events if e.get("type") == "result"]
        if not results:
            problems.append("no result event in the stream")
        else:
            result = results[-1]
            turn.session_id = result.get("session_id")
            turn.text = result.get("result") if isinstance(result.get("result"), str) else ""
            if result.get("is_error"):
                problems.append("result has is_error: true (subtype {}): {}".format(
                    result.get("subtype"), _short(turn.text, 200)))
        if not turn.session_id:
            turn.session_id = next((e.get("session_id") for e in turn.events if e.get("session_id")), None)
        if turn.returncode != 0:
            problems.append("exited with status {}".format(turn.returncode))
        return problems


class ClaudeRunner(_ResultStreamRunner):
    cli = "claude"

    def _argv(self, run, prompt, resume):
        argv = [
            self.binary, "-p", "--plugin-dir", run.plugin_dir,
            "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose",
            "--setting-sources", "project,local", "--strict-mcp-config",
        ]
        if resume:
            argv += ["--resume", resume]
        return argv + self.extra_args + [prompt]


class CursorRunner(_ResultStreamRunner):
    cli = "cursor"

    def _argv(self, run, prompt, resume):
        argv = [
            self.binary, "-p", "--plugin-dir", run.plugin_dir,
            "--workspace", run.repo, "--trust", "--force",
            "--output-format", "stream-json",
        ]
        if resume:
            argv += ["--resume", resume]
        return argv + self.extra_args + [prompt]


class CodexRunner(Runner):
    cli = "codex"
    FLAGS = ["--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"]

    def _auth_source(self):
        return (
            self.codex_auth
            or os.environ.get("DEVOS_E2E_CODEX_AUTH")
            or os.path.join(os.path.expanduser("~"), ".codex", "auth.json")
        )

    def _install(self, run):
        home = os.path.join(run.run_root, "codex-home")
        os.makedirs(home)
        run.env["CODEX_HOME"] = home
        auth = self._auth_source()
        if not os.path.isfile(auth):
            raise RunnerError(self.cli, "no auth.json at {}; log in to Codex first".format(auth), run)
        shutil.copyfile(auth, os.path.join(home, "auth.json"))
        os.chmod(os.path.join(home, "auth.json"), 0o600)
        steps = (
            ("plugin marketplace add", [self.binary, "plugin", "marketplace", "add", run.plugin_dir]),
            ("plugin add", [self.binary, "plugin", "add", "{}@{}".format(PLUGIN, MARKETPLACE)]),
        )
        for label, argv in steps:
            code, out, err, _ = self._call(run, argv, run.run_root, INSTALL_TIMEOUT, label)
            if code != 0:
                raise RunnerError(self.cli, "{} failed with status {}: {}".format(
                    label, code, _short(err or out)), run)
        pattern = os.path.join(home, "plugins", "cache", "*", PLUGIN, "*")
        roots = sorted(
            d for d in glob.glob(pattern)
            if os.path.isfile(os.path.join(d, ".codex-plugin", "plugin.json"))
        )
        if len(roots) != 1:
            raise RunnerError(self.cli, "plugin add left {} installed copies under {}".format(
                len(roots), os.path.dirname(pattern)), run)
        run.plugin_root = canon(roots[0])

    def _argv(self, run, prompt, resume):
        if resume:
            return [self.binary, "exec", "resume"] + self.FLAGS + self.extra_args + [resume, prompt]
        return [self.binary, "exec"] + self.FLAGS + self.extra_args + [prompt]

    def _problems(self, turn):
        problems = []
        types = [e.get("type") for e in turn.events]
        turn.session_id = next(
            (e.get("thread_id") for e in turn.events if e.get("type") == "thread.started"), None
        )
        for event in turn.events:
            if event.get("type") == "error":
                problems.append("error event: {}".format(_short(event.get("message"), 200)))
            elif event.get("type") == "turn.failed":
                detail = (event.get("error") or {}).get("message") if isinstance(event.get("error"), dict) else event.get("error")
                problems.append("turn.failed event: {}".format(_short(str(detail), 200)))
        if "turn.completed" not in types:
            problems.append("no turn.completed event")
        if turn.returncode != 0:
            problems.append("exited with status {}".format(turn.returncode))
        messages = [
            (e.get("item") or {}).get("text") or ""
            for e in turn.events
            if e.get("type") == "item.completed" and (e.get("item") or {}).get("type") == "agent_message"
        ]
        turn.text = messages[-1] if messages else ""
        return problems


RUNNERS = {"claude": ClaudeRunner, "codex": CodexRunner, "cursor": CursorRunner}


def make(cli, **kw):
    """A runner for `cli` ("claude", "codex" or "cursor")."""
    if cli not in RUNNERS:
        raise ValueError("unknown CLI {!r}; use one of {}".format(cli, ", ".join(CLIS)))
    return RUNNERS[cli](**kw)
