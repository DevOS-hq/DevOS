"""Offline tests for the e2e runners, stub CLIs, asserts and run.py.

The runners in tests/e2e/runners.py drive the real `claude`, `codex` and
`cursor-agent` CLIs in live runs. Here every CLI is a stub from tests/stubs,
put first on PATH by this module, so nothing touches the network. Each stub
logs its cwd, argv and environment to $STUB_LOG and replays tool-call events
captured once from a live run (tests/stubs/fixtures/<cli>.jsonl), with the
plugin and repo paths filled in from the call.

For each of the three runners these tests prove that it:
- loads a temp copy of the plugin (Claude and Cursor: --plugin-dir; Codex:
  `plugin marketplace add` plus `plugin add devos@devos` under a temp
  CODEX_HOME),
- runs with cwd set to a temp copy of the start state, with no plugin source in
  any parent folder,
- resumes the turn-1 session id on turns 2..n and sends the answers in order,
- (Claude) ignores user settings and MCP servers on every turn, with
  DEVOS_E2E_CLAUDE_ARGS appended after those flags,
- raises a RunnerError naming the CLI on each failure signal,
- lists the loaded copy's FORMAT.md, writing skill and scripts/check.py in the
  normalized transcript,
- snapshots the state repo's HEAD and porcelain status before and after each
  turn, with None for what a folder outside git cannot give.
- with until_commit, sends no further answer once a turn has moved HEAD off
  turn 1's start (run.py passes a scenario's UNTIL_COMMIT, default False).

Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
E2E = os.path.join(HERE, "e2e")
STUBS = os.path.join(HERE, "stubs")
STUB_FIXTURES = os.path.join(STUBS, "fixtures")
FIXTURE = os.path.join(HERE, "fixture")
RUN_PY = os.path.join(E2E, "run.py")

if E2E not in sys.path:
    sys.path.insert(0, E2E)

CLIS = ("claude", "codex", "cursor")
BINARY = {"claude": "claude", "codex": "codex", "cursor": "cursor-agent"}
FAIL_MODES = {
    "claude": {"is_error": "is_error", "garbage": "unparseable", "garbage_line": "unparseable"},
    "cursor": {"is_error": "is_error", "garbage": "unparseable", "garbage_line": "unparseable"},
    "codex": {
        "exit": "exit",
        "error": "error",
        "turn_failed": "turn.failed",
        "no_turn_completed": "turn.completed",
        "garbage": "unparseable",
        "garbage_line": "unparseable",
    },
}
IDENTITY = {
    "GIT_AUTHOR_NAME": "DevOS Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "DevOS Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}
CURSOR_TRAILER = "Co-authored-by: Cursor <cursoragent@cursor.com>"


def load(name):
    """Import an e2e module by name (runners, asserts)."""
    return importlib.import_module(name)


def real(path):
    return os.path.realpath(path)


def tree(root):
    """Sorted relative file paths under root, dotfiles included."""
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            out.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(out)


def ancestors(path):
    path = real(path)
    parent = os.path.dirname(path)
    while True:
        yield parent
        up = os.path.dirname(parent)
        if up == parent:
            return
        parent = up


def opt(argv, flag):
    """Value after `flag` in argv, or None."""
    for i, arg in enumerate(argv[:-1]):
        if arg == flag:
            return argv[i + 1]
    return None


class StubEnv(object):
    """Per-test sandbox: stubs on PATH, a STUB_LOG, a temp base, a fake Codex auth."""

    def setUp(self):
        self.tmp = real(tempfile.mkdtemp(prefix="devos-runner-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = os.path.join(self.tmp, "stub.log")
        self.auth = os.path.join(self.tmp, "fake-auth.json")
        with open(self.auth, "w", encoding="utf-8") as fh:
            fh.write('{"stub": true}\n')
        path = STUBS + os.pathsep + os.environ.get("PATH", "")
        patcher = mock.patch.dict(
            os.environ,
            {"PATH": path, "STUB_LOG": self.log, "DEVOS_E2E_CODEX_AUTH": self.auth},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in ("STUB_FAIL", "STUB_FAIL_ON", "STUB_DO", "STUB_DO_ON"):
            os.environ.pop(var, None)
        # Never reach a real CLI: every binary must resolve to its stub.
        for binary in BINARY.values():
            found = shutil.which(binary, path=path)
            self.assertIsNotNone(found, "stub {} is missing".format(binary))
            self.assertEqual(
                real(found), real(os.path.join(STUBS, binary)),
                "{} resolves to {} instead of the stub".format(binary, found),
            )
        self.runners = load("runners")

    def calls(self, kind=None):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh if line.strip()]
        if kind:
            entries = [e for e in entries if e.get("call") == kind]
        return entries

    def runner(self, cli, **kw):
        kw.setdefault("tmp_base", self.tmp)
        return self.runners.make(cli, **kw)


class StubFilesTest(unittest.TestCase):
    """The stubs and their captured fixtures exist and leak no machine path."""

    def test_stubs_are_executable(self):
        for binary in BINARY.values():
            path = os.path.join(STUBS, binary)
            with self.subTest(binary=binary):
                self.assertTrue(os.path.isfile(path), "missing stub " + path)
                self.assertTrue(os.access(path, os.X_OK), "stub not executable: " + path)

    def test_fixtures_hold_placeholder_paths_only(self):
        for cli in CLIS:
            path = os.path.join(STUB_FIXTURES, cli + ".jsonl")
            with self.subTest(cli=cli):
                self.assertTrue(os.path.isfile(path), "missing fixture " + path)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                events = [json.loads(line) for line in text.splitlines() if line.strip()]
                self.assertGreater(len(events), 1)
                self.assertIn("{PLUGIN}/FORMAT.md", text)
                self.assertIn("{PLUGIN}/scripts/check.py", text)
                for bad in ("/Users/", "/home/", "/private/", "/var/folders", "/tmp/"):
                    self.assertNotIn(bad, text, "{} leaks a machine path ({})".format(path, bad))


class RunnerCases(StubEnv):
    """AC 1 bullets, run once per CLI by the subclasses below."""

    CLI = None

    # -- loads a temp copy of the plugin ------------------------------------

    def test_loads_a_temp_copy_of_the_plugin(self):
        run = self.runner(self.CLI).run("first prompt", answers=("an answer",))
        copy = real(run.plugin_dir)
        self.assertNotEqual(copy, real(ROOT))
        self.assertFalse(copy.startswith(real(ROOT) + os.sep))
        for rel in ("FORMAT.md", "scripts/check.py", ".claude-plugin/plugin.json"):
            self.assertTrue(os.path.isfile(os.path.join(copy, rel)), rel)
        model_calls = self.calls("model")
        self.assertEqual(len(model_calls), 2)
        if self.CLI == "codex":
            self.assert_codex_install(run, copy)
        else:
            for call in model_calls:
                argv = call["argv"]
                self.assertEqual(real(opt(argv, "--plugin-dir")), copy)
                self.assertIn("-p", argv)
                self.assertEqual(opt(argv, "--output-format"), "stream-json")
                if self.CLI == "claude":
                    self.assertEqual(opt(argv, "--permission-mode"), "bypassPermissions")
                    self.assertIn("--verbose", argv)
                else:
                    self.assertEqual(real(opt(argv, "--workspace")), real(run.repo))
                    self.assertIn("--trust", argv)
                    self.assertIn("--force", argv)
            self.assertEqual(real(run.plugin_root), copy)

    def assert_codex_install(self, run, copy):
        entries = self.calls()
        kinds = [(e["call"], e["argv"][:3]) for e in entries]
        self.assertEqual(
            kinds[:2],
            [("plugin", ["plugin", "marketplace", "add"]), ("plugin", ["plugin", "add", "devos@devos"])],
            "Codex must add the marketplace, then the plugin, before any exec",
        )
        self.assertEqual(real(entries[0]["argv"][3]), copy)
        home = real(entries[0]["env"]["CODEX_HOME"])
        self.assertNotEqual(home, real(os.path.expanduser("~/.codex")))
        self.assertFalse(real(run.repo).startswith(home + os.sep))
        for entry in entries:
            self.assertEqual(real(entry["env"]["CODEX_HOME"]), home)
            self.assertTrue(entry["codex_auth"], "auth.json was not copied into CODEX_HOME")
        root = real(run.plugin_root)
        self.assertTrue(root.startswith(os.path.join(home, "plugins", "cache") + os.sep), root)
        self.assertTrue(os.path.isfile(os.path.join(root, "FORMAT.md")))
        for call in self.calls("model"):
            argv = call["argv"]
            self.assertEqual(argv[0], "exec")
            for flag in ("--json", "--skip-git-repo-check", "--dangerously-bypass-approvals-and-sandbox"):
                self.assertIn(flag, argv)
            self.assertNotIn("-C", argv)
            self.assertNotIn("--cd", argv)

    # -- cwd is a temp copy of the start state, isolated from the plugin -----

    def test_cwd_is_an_isolated_temp_copy_of_the_fixture(self):
        run = self.runner(self.CLI).run("first prompt", answers=("an answer",), start="fixture")
        repo = real(run.repo)
        self.assertNotEqual(repo, real(FIXTURE))
        self.assertEqual(tree(repo), tree(FIXTURE))
        for call in self.calls("model"):
            self.assertEqual(real(call["cwd"]), repo)
        source = real(ROOT)
        self.assertFalse(repo.startswith(source + os.sep), "state repo sits inside the plugin source")
        for parent in ancestors(repo):
            self.assertNotEqual(os.path.basename(parent), "DevOS", parent)
            self.assertFalse(os.path.exists(os.path.join(parent, "DevOS")), parent)
            self.assertFalse(
                os.path.isfile(os.path.join(parent, ".claude-plugin", "plugin.json")),
                "a plugin root is a parent of the state repo: " + parent,
            )
            self.assertNotEqual(parent, real(os.path.dirname(run.plugin_dir)))
            try:
                children = sorted(os.listdir(parent))
            except OSError:  # an unlistable system folder holds no plugin we made
                continue
            for child in children:
                kid = os.path.join(parent, child)
                self.assertFalse(
                    os.path.isfile(os.path.join(kid, ".claude-plugin", "plugin.json")),
                    "plugin source sits next to a parent of the state repo: " + kid,
                )

    def test_every_call_has_closed_stdin_and_the_neutral_git_identity(self):
        # Put an open pipe on this process's stdin, so a call that inherits
        # stdin (instead of closing it) shows up as "other" in the stub log.
        read_end, write_end = os.pipe()
        saved = os.dup(0)
        os.dup2(read_end, 0)
        try:
            run = self.runner(self.CLI).run("first prompt", answers=("an answer",))
        finally:
            os.dup2(saved, 0)
            for fd in (saved, read_end, write_end):
                os.close(fd)
        entries = self.calls()
        self.assertGreaterEqual(len(entries), 2)
        for entry in entries:
            self.assertIn(entry["stdin"], ("devnull", "closed"), entry["argv"])
            env = entry["env"]
            for key, value in IDENTITY.items():
                self.assertEqual(env.get(key), value, key)
            gitconfig = env.get("GIT_CONFIG_GLOBAL")
            self.assertTrue(gitconfig, "GIT_CONFIG_GLOBAL is not set")
            self.assertNotEqual(real(gitconfig), real(os.path.expanduser("~/.gitconfig")))
            self.assertTrue(os.path.isfile(gitconfig), gitconfig)
            self.assertEqual(os.path.getsize(gitconfig), 0)
        self.assertEqual(run.env.get("GIT_AUTHOR_EMAIL"), "test@example.invalid")

    # -- turns 2..n resume the turn-1 session and send answers in order ------

    def test_resumed_turns_reuse_the_first_session_id_and_answers_in_order(self):
        answers = ("answer one", "answer two", "answer three")
        run = self.runner(self.CLI).run("the first prompt", answers=answers)
        calls = self.calls("model")
        self.assertEqual(len(calls), 4)
        first_id = calls[0]["session_id"]
        self.assertTrue(first_id)
        self.assertEqual(run.session_id, first_id)
        self.assertEqual(run.turns[0].session_id, first_id)
        self.assertEqual(len(run.turns), 4)
        first = calls[0]["argv"]
        self.assertEqual(first[-1], "the first prompt")
        if self.CLI == "codex":
            self.assertNotEqual(first[1], "resume")
        else:
            self.assertNotIn("--resume", first)
        for call, answer in zip(calls[1:], answers):
            argv = call["argv"]
            self.assertEqual(argv[-1], answer)
            if self.CLI == "codex":
                self.assertEqual(argv[:2], ["exec", "resume"])
                self.assertEqual(argv[-2], first_id)
            else:
                self.assertEqual(opt(argv, "--resume"), first_id)
            self.assertEqual(call["session_id"], first_id)
        self.assertIn("answer three", run.text)

    # -- until_commit stops sending answers after the first commit ----------

    ANSWERS = ("answer one", "answer two", "answer three")

    def test_until_commit_stops_after_the_turn_that_commits(self):
        os.environ["STUB_DO"] = "commit"
        os.environ["STUB_DO_ON"] = "resume"
        run = self.runner(self.CLI).run(
            "the first prompt", answers=self.ANSWERS, start="state-repo", until_commit=True,
        )
        calls = self.calls("model")
        self.assertEqual([c["argv"][-1] for c in calls], ["the first prompt", "answer one"])
        self.assertEqual(len(run.turns), 2)
        self.assertEqual(run.prompts, ["the first prompt"] + list(self.ANSWERS))
        first, second = run.turns
        self.assertEqual(first.after["head"], first.before["head"])
        self.assertNotEqual(second.after["head"], first.before["head"])
        self.assertIn("answer one", run.text)

    def test_until_commit_sends_every_answer_when_nothing_commits(self):
        run = self.runner(self.CLI).run(
            "the first prompt", answers=self.ANSWERS, start="state-repo", until_commit=True,
        )
        self.assertEqual(len(self.calls("model")), 4)
        self.assertEqual(len(run.turns), 4)
        self.assertEqual(run.turns[-1].after["head"], run.turns[0].before["head"])
        self.assertIn("answer three", run.text)

    def test_without_until_commit_every_answer_follows_a_commit(self):
        os.environ["STUB_DO"] = "commit"
        os.environ["STUB_DO_ON"] = "resume"
        run = self.runner(self.CLI).run("the first prompt", answers=self.ANSWERS, start="state-repo")
        self.assertEqual(len(self.calls("model")), 4)
        self.assertEqual(len(run.turns), 4)
        self.assertNotEqual(run.turns[1].after["head"], run.turns[0].before["head"])
        self.assertIn("answer three", run.text)

    def test_setup_hook_builds_the_start_state_and_fills_the_prompt(self):
        seen = {}

        def setup(repo, tmp):
            seen["repo"], seen["tmp"] = repo, tmp
            with open(os.path.join(repo, "user.txt"), "w", encoding="utf-8") as fh:
                fh.write("mine\n")
            return {"remote": os.path.join(tmp, "remote.git")}

        run = self.runner(self.CLI).run(
            "push to {remote}", answers=("again {remote}",), start="empty", setup=setup
        )
        self.assertEqual(real(seen["repo"]), real(run.repo))
        self.assertTrue(os.path.isfile(os.path.join(run.repo, "user.txt")))
        self.assertFalse(real(seen["tmp"]).startswith(real(os.path.dirname(run.plugin_dir)) + os.sep))
        remote = os.path.join(seen["tmp"], "remote.git")
        calls = self.calls("model")
        self.assertEqual(calls[0]["argv"][-1], "push to " + remote)
        self.assertEqual(calls[1]["argv"][-1], "again " + remote)

    # -- failure signals ------------------------------------------------------

    def test_each_failure_signal_raises_a_runner_error_naming_the_cli(self):
        for mode, word in sorted(FAIL_MODES[self.CLI].items()):
            with self.subTest(mode=mode):
                os.environ["STUB_FAIL"] = mode
                with self.assertRaises(self.runners.RunnerError) as cm:
                    self.runner(self.CLI).run("first prompt")
                err = cm.exception
                self.assertEqual(err.cli, self.CLI)
                self.assertIn(self.CLI, str(err))
                self.assertIn(word, str(err))
                self.assertIsNotNone(err.run, "the error must carry the run for its temp paths")
                self.assertTrue(os.path.isdir(err.run.repo), "temp dirs must be kept on failure")

    def test_a_failure_on_a_resumed_turn_raises_too(self):
        mode = sorted(FAIL_MODES[self.CLI])[0]
        os.environ["STUB_FAIL"] = mode
        os.environ["STUB_FAIL_ON"] = "resume"
        with self.assertRaises(self.runners.RunnerError) as cm:
            self.runner(self.CLI).run("first prompt", answers=("an answer",))
        self.assertEqual(cm.exception.cli, self.CLI)
        self.assertIn("turn 2", str(cm.exception))
        self.assertEqual(len(self.calls("model")), 2)

    def test_a_resumed_turn_on_a_new_session_raises(self):
        # Resuming must continue the turn-1 conversation; a fresh id means it did not.
        os.environ["STUB_FAIL"] = "new_session"
        os.environ["STUB_FAIL_ON"] = "resume"
        with self.assertRaises(self.runners.RunnerError) as cm:
            self.runner(self.CLI).run("first prompt", answers=("an answer",))
        self.assertEqual(cm.exception.cli, self.CLI)
        self.assertIn("session id", str(cm.exception))
        calls = self.calls("model")
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]["session_id"], calls[1]["session_id"])

    def test_a_success_raises_nothing_without_the_fail_switch(self):
        run = self.runner(self.CLI).run("first prompt")
        self.assertEqual(len(run.turns), 1)
        self.assertTrue(run.text)

    # -- normalized transcript ------------------------------------------------

    def test_transcript_lists_the_loaded_copy_paths(self):
        run = self.runner(self.CLI).run("first prompt")
        transcript = run.transcript
        fmt = run.plugin_path("FORMAT.md")
        check = run.plugin_path("scripts/check.py")
        self.assertEqual(real(fmt), real(os.path.join(run.plugin_root, "FORMAT.md")))
        paths = [real(p) for p in transcript.paths()]
        self.assertIn(real(fmt), paths)
        self.assertTrue(transcript.was_read(fmt))
        self.assertTrue(transcript.used_skill("writing", run.plugin_root))
        self.assertTrue(transcript.ran(check))
        if self.CLI == "claude":
            self.assertIn("devos:writing", [e.skill for e in transcript.events if e.kind == "skill"])
        else:
            self.assertIn(real(run.plugin_path("skills/writing/SKILL.md")), paths)
        # The source tree and, for Codex, the marketplace copy were never the loaded copy.
        self.assertFalse(transcript.was_read(os.path.join(ROOT, "FORMAT.md")))
        self.assertFalse(transcript.used_skill("writing", ROOT))
        self.assertFalse(transcript.used_skill("init", run.plugin_root))
        if self.CLI == "codex":
            self.assertNotEqual(real(run.plugin_root), real(run.plugin_dir))
            self.assertFalse(transcript.was_read(os.path.join(run.plugin_dir, "FORMAT.md")))
        for event in transcript.events:
            self.assertIn(event.kind, ("read", "skill", "shell", "write", "edit", "other"))
            self.assertGreaterEqual(event.turn, 1)

    def test_transcript_spans_every_turn(self):
        run = self.runner(self.CLI).run("first prompt", answers=("an answer",))
        turns = sorted(set(e.turn for e in run.transcript.events))
        self.assertEqual(turns, [1, 2])


class ClaudeRunnerTest(RunnerCases, unittest.TestCase):
    CLI = "claude"

    def test_every_turn_ignores_user_settings_and_mcp_servers(self):
        self.runner("claude").run("first prompt", answers=("one", "two"))
        calls = self.calls("model")
        self.assertEqual(len(calls), 3)
        for call in calls:
            argv = call["argv"]
            self.assertEqual(opt(argv, "--setting-sources"), "project,local", argv)
            self.assertIn("--strict-mcp-config", argv)

    def test_extra_args_follow_the_isolation_flags(self):
        os.environ["DEVOS_E2E_CLAUDE_ARGS"] = "--model haiku"
        self.runner("claude").run("first prompt", answers=("an answer",))
        calls = self.calls("model")
        self.assertEqual(len(calls), 2)
        for call in calls:
            argv = call["argv"]
            self.assertEqual(argv[-3:-1], ["--model", "haiku"], argv)
            self.assertIn("--strict-mcp-config", argv)
            self.assertIn("--setting-sources", argv)
            self.assertLess(argv.index("--strict-mcp-config"), argv.index("--model"))
            self.assertLess(argv.index("--setting-sources"), argv.index("--model"))


class CodexRunnerTest(RunnerCases, unittest.TestCase):
    CLI = "codex"

    def test_a_failed_plugin_add_raises_naming_codex(self):
        os.environ["STUB_FAIL"] = "plugin_add"
        with self.assertRaises(self.runners.RunnerError) as cm:
            self.runner("codex").run("first prompt")
        self.assertEqual(cm.exception.cli, "codex")
        self.assertIn("plugin add", str(cm.exception))
        self.assertEqual(self.calls("model"), [])

    def test_missing_auth_raises_naming_codex(self):
        missing = os.path.join(self.tmp, "no-such-auth.json")
        with self.assertRaises(self.runners.RunnerError) as cm:
            self.runner("codex", codex_auth=missing).run("first prompt")
        self.assertEqual(cm.exception.cli, "codex")
        self.assertIn("auth.json", str(cm.exception))


class CursorRunnerTest(RunnerCases, unittest.TestCase):
    CLI = "cursor"


class NeutralEnvTest(unittest.TestCase):
    """No git config outside the run's empty global file reaches a run."""

    def test_system_and_inherited_config_are_dropped(self):
        runners = load("runners")
        tmp = tempfile.mkdtemp(prefix="devos-neutral-env-")
        self.addCleanup(shutil.rmtree, tmp, True)
        gitconfig = os.path.join(tmp, "gitconfig")
        open(gitconfig, "w").close()
        base = dict(os.environ)
        base.update({
            "GIT_CONFIG_PARAMETERS": "'commit.gpgsign'='true'",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "user.name",
            "GIT_CONFIG_VALUE_0": "Leaked Name",
        })
        env = runners.neutral_env(gitconfig, base=base)
        self.assertEqual(env.get("GIT_CONFIG_NOSYSTEM"), "1")
        for key in ("commit.gpgsign", "user.name"):
            result = subprocess.run(
                ["git", "config", "--get", key], cwd=tmp, env=env,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
            )
            self.assertEqual(result.stdout.strip(), "", "{} leaked into the run".format(key))


class NormalizeTest(unittest.TestCase):
    """The transcript tells running a script apart from reading it."""

    ROOT = "/opt/plug"
    CHECK = "/opt/plug/scripts/check.py"

    def setUp(self):
        self.runners = load("runners")

    def transcript(self, cli, events, cwd="/work/repo"):
        return self.runners.Transcript(self.runners.normalize(cli, events, cwd=cwd, turn=1))

    def claude_bash(self, command):
        return {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}]}}

    def test_claude_bash_run_versus_read(self):
        ran = self.transcript("claude", [self.claude_bash("python3 {} .".format(self.CHECK))])
        self.assertTrue(ran.ran(self.CHECK))
        read = self.transcript("claude", [self.claude_bash("cat {}".format(self.CHECK))])
        self.assertFalse(read.ran(self.CHECK))
        self.assertTrue(read.was_read(self.CHECK))

    def test_codex_wrapped_command_runs_the_script(self):
        event = {"type": "item.completed", "item": {
            "id": "item_1", "type": "command_execution",
            "command": "/bin/zsh -lc 'python3 {} \"$PWD\"'".format(self.CHECK),
            "aggregated_output": "", "exit_code": 0, "status": "completed"}}
        self.assertTrue(self.transcript("codex", [event]).ran(self.CHECK))

    def test_cursor_relative_script_resolves_against_the_working_directory(self):
        event = {"type": "tool_call", "subtype": "completed", "call_id": "c1", "tool_call": {
            "shellToolCall": {"args": {"command": "python3 scripts/check.py /work/repo",
                                       "workingDirectory": self.ROOT}}}}
        self.assertTrue(self.transcript("cursor", [event]).ran(self.CHECK))

    def test_cd_then_relative_script_resolves(self):
        command = "cd {} && python3 scripts/check.py /work/repo".format(self.ROOT)
        self.assertTrue(self.transcript("claude", [self.claude_bash(command)]).ran(self.CHECK))

    def test_a_variable_set_earlier_in_the_command_expands(self):
        # Seen live: Claude read FORMAT.md as `P=<plugin>; cat $P/FORMAT.md`.
        fmt = self.ROOT + "/FORMAT.md"
        for command in (
            "P={}; cat $P/FORMAT.md; echo ----".format(self.ROOT),
            "set -e\nP={}\ncat \"${{P}}/FORMAT.md\"".format(self.ROOT),
            "export P={} && cat $P/FORMAT.md".format(self.ROOT),
        ):
            with self.subTest(command=command):
                self.assertTrue(self.transcript("claude", [self.claude_bash(command)]).was_read(fmt))
        command = "export P={} && python3 $P/scripts/check.py .".format(self.ROOT)
        self.assertTrue(self.transcript("claude", [self.claude_bash(command)]).ran(self.CHECK))

    def test_an_unset_variable_names_no_path(self):
        transcript = self.transcript("claude", [self.claude_bash("cat $Q/FORMAT.md")])
        self.assertFalse(transcript.was_read(self.ROOT + "/FORMAT.md"))
        self.assertEqual(transcript.paths(), [])

    def test_an_unbalanced_quote_keeps_later_lines(self):
        # An apostrophe in a heredoc body or a comment stops shlex; the lines
        # after it must still be parsed, one command per line.
        for command in (
            "cat > AGENTS.md <<'EOF'\nDon't edit by hand.\nEOF\npython3 {} .".format(self.CHECK),
            "# don't skip the check\npython3 {} .".format(self.CHECK),
        ):
            with self.subTest(command=command):
                self.assertTrue(self.transcript("claude", [self.claude_bash(command)]).ran(self.CHECK))

    def test_env_by_path_and_its_options_run_the_script(self):
        for command in (
            "/usr/bin/env python3 {} .".format(self.CHECK),
            "env -i python3 {} .".format(self.CHECK),
        ):
            with self.subTest(command=command):
                transcript = self.transcript("claude", [self.claude_bash(command)])
                self.assertTrue(transcript.ran(self.CHECK))
                self.assertNotIn("/usr/bin/env", transcript.events[0].runs)

    def test_python_options_that_take_a_value_are_skipped(self):
        for option in ("-X utf8", "-W ignore", "-Xutf8"):
            command = "python3 {} {} .".format(option, self.CHECK)
            with self.subTest(command=command):
                transcript = self.transcript("claude", [self.claude_bash(command)])
                self.assertEqual(list(transcript.events[0].runs), [self.CHECK])

    def test_unrelated_python_is_not_the_check(self):
        command = "python3 /opt/other/scripts/check.py ."
        self.assertFalse(self.transcript("claude", [self.claude_bash(command)]).ran(self.CHECK))

    def test_codex_brace_expansion_reads_each_skill(self):
        # Seen live: Codex read two skills with one `cat .../skills/{a,b}/SKILL.md`.
        event = {"type": "item.completed", "item": {
            "id": "item_1", "type": "command_execution",
            "command": "/bin/zsh -lc 'cat /opt/plug/skills/{init,writing}/SKILL.md'",
            "aggregated_output": "", "exit_code": 0, "status": "completed"}}
        transcript = self.transcript("codex", [event])
        self.assertTrue(transcript.used_skill("writing", self.ROOT))
        self.assertTrue(transcript.used_skill("init", self.ROOT))
        self.assertFalse(transcript.used_skill("spec", self.ROOT))

    def test_cursor_tool_call_metadata_is_not_an_event(self):
        # Seen live: toolCallId, startedAtMs and friends sit next to readToolCall.
        event = {"type": "tool_call", "subtype": "started", "call_id": "c1", "tool_call": {
            "readToolCall": {"args": {"path": "/opt/plug/FORMAT.md"}},
            "hookAdditionalContexts": [], "toolCallId": "c1", "startedAtMs": "1"}}
        transcript = self.transcript("cursor", [event])
        self.assertEqual([e.kind for e in transcript.events], ["read"])

    def test_claude_skill_from_a_slash_prompt_counts_as_loaded(self):
        # Seen live: after a skill loads, Claude adds "Base directory for this skill: <dir>".
        base = {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "Base directory for this skill: /opt/plug/skills/init\n\n# Init\n"}]}}
        transcript = self.transcript("claude", [base])
        self.assertTrue(transcript.used_skill("init", self.ROOT))
        self.assertFalse(transcript.used_skill("init", "/opt/other"))

    def test_claude_skill_call_resolves_through_the_init_plugin_path(self):
        init = {"type": "system", "subtype": "init", "plugins": [{"name": "devos", "path": self.ROOT}]}
        call = {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "devos:writing"}}]}}
        transcript = self.transcript("claude", [init, call])
        self.assertTrue(transcript.used_skill("writing", self.ROOT))
        self.assertFalse(transcript.used_skill("writing", "/opt/other"))
        self.assertEqual(transcript.skills(), ["devos:writing"])


class AssertsTest(StubEnv, unittest.TestCase):
    """The scenario helpers in e2e/asserts.py, against stub runs."""

    def setUp(self):
        super(AssertsTest, self).setUp()
        self.asserts = load("asserts")

    def test_state_repo_start_is_one_neutral_commit_on_main(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="state-repo")
        self.assertEqual(a.branch(run), "main")
        self.assertEqual(a.commit_count(run), 1)
        self.assertEqual(a.status(run), [])
        self.assertEqual(a.git(run, "log", "-1", "--format=%an <%ae>"), "DevOS Test <test@example.invalid>")
        self.assertEqual(a.commit_files(run), set(tree(FIXTURE)))
        self.assertEqual(a.remotes(run), {})

    def test_check_exit(self):
        a = self.asserts
        good = self.runner("claude").run("first prompt", start="fixture")
        a.check_exit(good, 0)
        empty = self.runner("claude").run("first prompt", start="empty")
        with self.assertRaises(AssertionError):
            a.check_exit(empty, 0)
        a.check_exit(empty, 2)

    def test_transcript_asserts_pass_on_a_loaded_run_and_fail_on_an_empty_one(self):
        a = self.asserts
        for cli in CLIS:
            with self.subTest(cli=cli):
                run = self.runner(cli).run("first prompt")
                a.read_format(run)
                a.writing_loaded(run)
                a.check_ran(run)
                run.transcript = self.runners.Transcript([])
                for helper in (a.read_format, a.writing_loaded, a.check_ran):
                    with self.assertRaises(AssertionError):
                        helper(run)

    def test_files_and_greps(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        a.file_exists(run, "projects/checkout-revamp/project.md")
        with self.assertRaises(AssertionError):
            a.file_exists(run, "projects/nope.md")
        self.assertIn("format: 1", a.file_text(run, ".devos"))
        a.file_contains(run, ".devos", r"^format: 1$")
        with self.assertRaises(AssertionError):
            a.file_contains(run, ".devos", r"format: 2")
        a.file_contains(run, ".devos", r"format", count=1)
        with self.assertRaises(AssertionError):
            a.file_contains(run, ".devos", r"format", count=2)

    def test_banned_clean_calls_the_plugin_copy_script(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="empty")
        script = os.path.join(run.plugin_dir, "scripts", "banned.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(
                "import sys\n"
                "hits = [p for p in sys.argv[1:] if 'delve' in open(p).read()]\n"
                "for p in hits: print(p + ':1: banned: delve')\n"
                "sys.exit(1 if hits else 0)\n"
            )
        with open(os.path.join(run.repo, "good.md"), "w", encoding="utf-8") as fh:
            fh.write("Plain words.\n")
        with open(os.path.join(run.repo, "bad.md"), "w", encoding="utf-8") as fh:
            fh.write("Let us delve.\n")
        a.banned_clean(run, ["good.md"])
        with self.assertRaises(AssertionError) as cm:
            a.banned_clean(run, ["good.md", "bad.md"])
        self.assertIn("delve", str(cm.exception))

    def test_commit_message_drops_the_cursor_trailer(self):
        a = self.asserts
        self.assertEqual(a.strip_trailers("Add project\n\n" + CURSOR_TRAILER + "\n"), "Add project")
        self.assertEqual(a.strip_trailers("Add project\n\nBody line.\n"), "Add project\n\nBody line.")
        run = self.runner("cursor").run("first prompt", start="state-repo")
        a.git(run, "commit", "--allow-empty", "-q", "-m", "Second\n\n" + CURSOR_TRAILER)
        self.assertEqual(a.commit_message(run), "Second")

    def test_judge_hook_uses_the_given_module(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        seen = []

        def judge_file(path, skill):
            seen.append((path, skill))
            return {"verdict": "fail" if "bad" in path else "pass", "scores": {}, "failures": ["x"]}

        fake = types.SimpleNamespace(judge_file=judge_file)
        a.judge_pass(run, ".devos", judge_module=fake)
        self.assertEqual(real(seen[0][0]), real(os.path.join(run.repo, ".devos")))
        self.assertEqual(real(seen[0][1]), real(os.path.join(run.plugin_dir, "skills", "writing", "SKILL.md")))
        with open(os.path.join(run.repo, "bad.md"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        with self.assertRaises(AssertionError):
            a.judge_pass(run, "bad.md", judge_module=fake)

    def scripted_judge(self, verdicts):
        """A judge module that returns `verdicts` in order and counts its calls."""
        calls = []

        def judge_file(path, skill):
            verdict, score = verdicts[len(calls)]
            calls.append(path)
            return {"verdict": verdict, "scores": {"concision": score}, "failures": ["x"]}

        return types.SimpleNamespace(judge_file=judge_file), calls

    def test_judge_pass_first_call_passes(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        fake, calls = self.scripted_judge([("pass", 5), ("fail", 1)])
        verdict = a.judge_pass(run, ".devos", judge_module=fake, tries=2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(verdict["verdict"], "pass")

    def test_judge_pass_retries_once_after_a_fail(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        fake, calls = self.scripted_judge([("fail", 2), ("pass", 5), ("fail", 1)])
        verdict = a.judge_pass(run, ".devos", judge_module=fake, tries=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(verdict["verdict"], "pass")

    def test_judge_pass_fails_after_two_fails(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        fake, calls = self.scripted_judge([("fail", 2), ("fail", 3), ("pass", 5)])
        with self.assertRaises(AssertionError) as cm:
            a.judge_pass(run, ".devos", judge_module=fake, tries=2)
        self.assertEqual(len(calls), 2)
        message = str(cm.exception)
        self.assertIn("'concision': 2", message)
        self.assertIn("'concision': 3", message)

    def test_judge_pass_default_makes_one_call(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="fixture")
        fake, calls = self.scripted_judge([("fail", 2), ("pass", 5)])
        with self.assertRaises(AssertionError):
            a.judge_pass(run, ".devos", judge_module=fake)
        self.assertEqual(len(calls), 1)


class TurnSnapshotTest(StubEnv, unittest.TestCase):
    """Each Turn's before/after snapshot, and the asserts built on it."""

    def setUp(self):
        super(TurnSnapshotTest, self).setUp()
        self.asserts = load("asserts")

    def test_turn_records_snapshot_before_and_after(self):
        os.environ["STUB_DO"] = "write"
        os.environ["STUB_DO_ON"] = "resume"
        run = self.runner("claude").run("first prompt", answers=("go on",), start="state-repo")
        start = self.asserts.git(run, "rev-list", "--max-parents=0", "HEAD")
        clean = {"head": start, "status": ""}
        first, second = run.turns
        self.assertEqual(first.before, clean)
        self.assertEqual(first.after, clean)
        self.assertEqual(second.before, clean)
        self.assertEqual(second.after, {"head": start, "status": "?? stub-write.txt\n"})

    def test_snapshot_outside_git_repo_is_none(self):
        # The temp base sits inside a git repo, so a snapshot that walks up
        # from the state folder would report that repo instead of None.
        outer = os.path.join(self.tmp, "outer")
        os.makedirs(outer)
        self.runners.git(outer, "init", "-q")
        os.environ["STUB_DO"] = "write"
        run = self.runner("claude", tmp_base=outer).run("first prompt", start="empty")
        self.assertTrue(os.path.isfile(os.path.join(run.repo, "stub-write.txt")))
        self.assertEqual(run.turns[0].before, {"head": None, "status": None})
        self.assertEqual(run.turns[0].after, {"head": None, "status": None})

        def init(repo, tmp):
            self.runners.git(repo, "init", "-q", "-b", "main")

        fresh = self.runner("claude", tmp_base=outer).run("first prompt", start="empty", setup=init)
        self.assertEqual(fresh.turns[0].before, {"head": None, "status": ""})
        self.assertEqual(fresh.turns[0].after, {"head": None, "status": "?? stub-write.txt\n"})

    def test_turn_unchanged_passes_when_turn_writes_nothing(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", answers=("go on",), start="state-repo")
        a.turn_unchanged(run, 1)
        a.turn_unchanged(run, 2)
        self.assertEqual(run.turns[1].after["head"], a.head(run))

    def test_turn_unchanged_fails_when_turn_writes_a_file(self):
        a = self.asserts
        os.environ["STUB_DO"] = "write"
        os.environ["STUB_DO_ON"] = "resume"
        run = self.runner("claude").run("first prompt", answers=("go on",), start="state-repo")
        a.turn_unchanged(run, 1)
        with self.assertRaises(AssertionError) as cm:
            a.turn_unchanged(run, 2)
        self.assertIn("turn 2", str(cm.exception))
        self.assertIn("stub-write.txt", str(cm.exception))

    def test_turn_unchanged_fails_when_turn_commits(self):
        a = self.asserts
        os.environ["STUB_DO"] = "commit"
        os.environ["STUB_DO_ON"] = "resume"
        run = self.runner("claude").run("first prompt", answers=("go on",), start="state-repo")
        a.turn_unchanged(run, 1)
        second = run.turns[1]
        # A commit leaves the status clean, so only the HEAD comparison catches it.
        self.assertEqual(second.before["status"], second.after["status"])
        self.assertNotEqual(second.before["head"], second.after["head"])
        self.assertEqual(second.after["head"], a.head(run))
        self.assertEqual(a.commit_count(run), 2)
        with self.assertRaises(AssertionError) as cm:
            a.turn_unchanged(run, 2)
        self.assertIn(second.after["head"], str(cm.exception))
        with self.assertRaises(AssertionError):
            a.turn_unchanged(run, 3)

    def test_turn_unchanged_fails_outside_a_git_repo(self):
        # Outside git both snapshots are None, so a turn's writes would compare
        # equal; turn_unchanged must refuse rather than pass.
        os.environ["STUB_DO"] = "write"
        run = self.runner("claude").run("first prompt", start="empty")
        self.assertTrue(os.path.isfile(os.path.join(run.repo, "stub-write.txt")))
        with self.assertRaisesRegex(AssertionError, "outside a git repo"):
            self.asserts.turn_unchanged(run, 1)

    def test_commit_date_returns_committer_date(self):
        a = self.asserts
        run = self.runner("claude").run("first prompt", start="state-repo")
        env = dict(run.env, GIT_AUTHOR_DATE="2020-01-02 12:00:00 +0000",
                   GIT_COMMITTER_DATE="2024-03-05 12:00:00 +0000")
        subprocess.run(
            ["git", "-C", run.repo, "commit", "--allow-empty", "-q", "-m", "Dated"],
            env=env, stdin=subprocess.DEVNULL, check=True, capture_output=True,
        )
        self.assertEqual(a.commit_date(run), "2024-03-05")
        self.assertEqual(a.commit_date(run, "HEAD"), "2024-03-05")
        self.assertNotEqual(a.commit_date(run, "HEAD~1"), "2024-03-05")
        self.assertRegex(a.commit_date(run, "HEAD~1"), r"^\d{4}-\d{2}-\d{2}$")


SCENARIO_OK = '''
import asserts
CLIS = ("claude", "codex")
START = "fixture"
PROMPT = "run the probe"
ANSWERS = ("yes",)
def check(run):
    asserts.check_exit(run, 0)
    asserts.read_format(run)
    asserts.writing_loaded(run)
'''

SCENARIO_BAD = '''
import os
CLIS = ("claude",)
START = "empty"
PROMPT = "run the probe"
def check(run):
    with open(os.environ["COUNT_FILE"], "a") as fh:
        fh.write("bad\\n")
    raise AssertionError("planted failure")
'''

SCENARIO_FLAKY = '''
import os
CLIS = ("claude",)
START = "empty"
PROMPT = "run the probe"
def check(run):
    path = os.environ["COUNT_FILE"] + ".flaky"
    first = not os.path.exists(path)
    open(path, "a").close()
    if first:
        raise AssertionError("fails the first time only")
'''


class RunPyTest(StubEnv, unittest.TestCase):
    """run.py prints one PASS/FAIL line per scenario per CLI and re-runs a failure once."""

    def setUp(self):
        super(RunPyTest, self).setUp()
        self.scenarios = os.path.join(self.tmp, "scenarios")
        os.makedirs(self.scenarios)
        for name, body in (("ok", SCENARIO_OK), ("bad", SCENARIO_BAD), ("flaky", SCENARIO_FLAKY)):
            with open(os.path.join(self.scenarios, name + ".py"), "w", encoding="utf-8") as fh:
                fh.write(body)
        self.count = os.path.join(self.tmp, "count")
        os.environ["DEVOS_E2E_SCENARIOS"] = self.scenarios
        os.environ["COUNT_FILE"] = self.count
        os.environ["TMPDIR"] = self.tmp

    def run_py(self, *args):
        return subprocess.run(
            [sys.executable, RUN_PY] + list(args),
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300,
        )

    def test_help_lists_cli_and_scenario(self):
        result = subprocess.run([sys.executable, RUN_PY, "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--cli", result.stdout)
        self.assertIn("--scenario", result.stdout)

    def test_pass_fail_and_one_rerun(self):
        result = self.run_py("--cli", "claude")
        out = result.stdout
        self.assertEqual(result.returncode, 1, out + result.stderr)
        lines = [l for l in out.splitlines() if l.startswith(("PASS", "FAIL"))]
        self.assertEqual(len(lines), 3, out)
        self.assertIn("PASS ok [claude]", out)
        self.assertIn("PASS flaky [claude]", out)
        self.assertIn("FAIL bad [claude]", out)
        self.assertIn("planted failure", out)
        with open(self.count, encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("bad"), 2, "a failing scenario runs exactly twice")
        kept = [l.split("kept: ", 1)[1].split() for l in out.splitlines() if "kept: " in l]
        self.assertTrue(kept, "a failing run prints its kept temp dirs")
        for path in kept[-1]:
            self.assertTrue(os.path.isdir(path), path)

    def test_selects_scenarios_and_clis(self):
        result = self.run_py("--cli", "all", "--scenario", "ok")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = [l for l in result.stdout.splitlines() if l.startswith(("PASS", "FAIL"))]
        self.assertEqual(lines, ["PASS ok [claude]", "PASS ok [codex]"])

    def test_unknown_scenario_is_a_usage_error(self):
        result = self.run_py("--scenario", "no_such_scenario")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


SCENARIO_UNTIL_COMMIT = '''
CLIS = ("claude",)
START = "state-repo"
PROMPT = "run the probe"
ANSWERS = ("one", "two", "three")
UNTIL_COMMIT = True
def check(run):
    assert len(run.prompts) == 4, run.prompts
    assert len(run.turns) == 2, "{} turns ran".format(len(run.turns))
'''


class RunPyUntilCommitTest(StubEnv, unittest.TestCase):
    """run.py passes a scenario's UNTIL_COMMIT (default False) to Runner.run."""

    def load_run_py(self):
        spec = importlib.util.spec_from_file_location("devos_e2e_run", RUN_PY)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def forwarded(self, scenario):
        """The keyword arguments run.attempt() gives Runner.run for `scenario`."""
        run_py = self.load_run_py()
        seen = {}

        class FakeRunner(object):
            def run(self, prompt, **kw):
                seen.update(kw)
                return types.SimpleNamespace()

        with mock.patch.object(run_py.runners, "make", lambda cli: FakeRunner()):
            ok, reason, _ = run_py.attempt(scenario, "claude")
        self.assertTrue(ok, reason)
        return seen

    def test_until_commit_attribute_is_forwarded(self):
        scenario = types.SimpleNamespace(PROMPT="p", UNTIL_COMMIT=True, check=lambda run: None)
        self.assertIs(self.forwarded(scenario).get("until_commit"), True)

    def test_until_commit_defaults_to_false(self):
        scenario = types.SimpleNamespace(PROMPT="p", check=lambda run: None)
        kw = self.forwarded(scenario)
        self.assertIn("until_commit", kw)
        self.assertIs(kw["until_commit"], False)

    def test_scenario_with_until_commit_stops_at_the_committing_turn(self):
        scenarios = os.path.join(self.tmp, "scenarios")
        os.makedirs(scenarios)
        with open(os.path.join(scenarios, "until_commit.py"), "w", encoding="utf-8") as fh:
            fh.write(SCENARIO_UNTIL_COMMIT)
        os.environ.update({
            "DEVOS_E2E_SCENARIOS": scenarios, "TMPDIR": self.tmp,
            "STUB_DO": "commit", "STUB_DO_ON": "resume",
        })
        result = subprocess.run(
            [sys.executable, RUN_PY, "--cli", "claude"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS until_commit [claude]", result.stdout)
        self.assertNotIn("re-run", result.stdout)
        self.assertEqual(len(self.calls("model")), 2)


if __name__ == "__main__":
    unittest.main()
