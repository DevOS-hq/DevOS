"""Tests for scripts/remote.py, the check that runs before every push.

Most cases build a small state repo (a `.devos` marker plus `git init`) in a
temp folder and run the real script as a subprocess, asserting the exit code
and the one line it prints. Cases that must prove the anonymous probe ran, or
did not run, import the script and replace the probe with a mock. The probe
unit case replaces `subprocess.run` and inspects the command, environment,
folder and timeout the probe builds. The `GitDaemon` cases serve bare repos
from a real `git daemon` on 127.0.0.1 and run the real probe against it; they
skip only when `git daemon` is not installed. No case reaches the network
beyond 127.0.0.1, and git runs with an empty HOME so the developer's own git
config cannot change a result. Standard library only; runs under Python 3.9.

Run from the plugin root:  python3 -m unittest discover -s tests
"""

import ast
import contextlib
import io
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SCRIPTS = os.path.join(ROOT, "scripts")
REMOTE = os.path.join(SCRIPTS, "remote.py")

sys.path.insert(0, SCRIPTS)
import remote  # noqa: E402

MARKER = "format: 1\n"
CREDENTIALS = "take the credentials out of the remote URL"
PUBLIC = "can be read without signing in"
PRIVATE_FIRST = "must be made private first"
NOT_CONFIRMED = "is not confirmed"
SSH_ONE = "git@git.example.invalid:org/one.git"
SSH_TWO = "git@git.example.invalid:org/two.git"


def describe(result):
    return "exit {}\nstdout:\n{}stderr:\n{}".format(
        result.returncode, result.stdout, result.stderr
    )


def clean_env(home):
    """The test process environment without GIT_* and with an empty HOME."""
    env = dict((k, v) for k, v in os.environ.items() if not k.startswith("GIT_"))
    env.update({"HOME": home, "XDG_CONFIG_HOME": home, "GIT_CONFIG_NOSYSTEM": "1"})
    return env


def git(env, *args, **kwargs):
    result = subprocess.run(
        ["git"] + list(args), env=env, capture_output=True, text=True, **kwargs
    )
    if result.returncode != 0:
        raise AssertionError("git {} failed:\n{}".format(" ".join(args), describe(result)))
    return result.stdout


def write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def make_state_repo(env, parent, devos=MARKER, name="state"):
    """A git repo holding `.devos`, on branch `main` with no commits."""
    repo = os.path.join(parent, name)
    os.mkdir(repo)
    git(env, "init", "-q", repo)
    git(env, "-C", repo, "symbolic-ref", "HEAD", "refs/heads/main")
    write_bytes(os.path.join(repo, ".devos"), devos.encode("utf-8"))
    return repo


def run_script(cwd, env, *args):
    return subprocess.run(
        [sys.executable, REMOTE] + list(args),
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


class ResultAsserts(unittest.TestCase):
    def assert_line(self, result, code, starts="", contains=()):
        """Exit `code`, exactly one stdout line, empty stderr; return the line."""
        self.assertEqual(result.returncode, code, describe(result))
        self.assertEqual(result.stderr, "", describe(result))
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, describe(result))
        self.assertTrue(lines[0].startswith(starts), describe(result))
        for text in contains:
            self.assertIn(text, lines[0], describe(result))
        return lines[0]


class StateRepoCase(ResultAsserts):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="devos-remote-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.mkdir(self.home)
        self.env = clean_env(self.home)
        self.repo = make_state_repo(self.env, self.tmp)
        self.devos = os.path.join(self.repo, ".devos")

    def git(self, *args):
        return git(self.env, "-C", self.repo, *args)

    def run_remote(self, *args, **kwargs):
        return run_script(kwargs.get("cwd", self.repo), kwargs.get("env", self.env), *args)


# --- source rules -------------------------------------------------------------


class Source(unittest.TestCase):
    def source(self):
        with open(REMOTE, encoding="utf-8") as f:
            return f.read()

    def test_parses_as_python_3_9(self):
        ast.parse(self.source(), filename=REMOTE, feature_version=(3, 9))

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "needs Python 3.10+ to list stdlib")
    def test_imports_only_the_standard_library(self):
        tree = ast.parse(self.source(), filename=REMOTE)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                self.assertIn(name.split(".")[0], sys.stdlib_module_names, name)


# --- pure functions: classifier, SSH-to-HTTPS, credentials --------------------


class Classify(unittest.TestCase):
    def test_scp_like_is_ssh(self):
        for url in ("host:org/repo", "git@host:org/repo.git", "host:repo"):
            with self.subTest(url=url):
                self.assertEqual(remote.classify(url), remote.SSH)

    def test_paths_and_file_urls_are_local(self):
        for url in ("./foo:bar", "/abs/path", "rel/path", "file:///x", "plain", "../up.git"):
            with self.subTest(url=url):
                self.assertEqual(remote.classify(url), remote.LOCAL)

    def test_drive_paths_are_local_only_on_windows(self):
        # git treats `C:/x` as a local path on Windows and as an scp-like
        # address to host `C` everywhere else; the classifier follows it.
        for url in ("C:/repos/state.git", "C:\\repos\\state.git", "d:state.git"):
            with self.subTest(url=url):
                with mock.patch.object(remote, "WINDOWS", True):
                    self.assertEqual(remote.classify(url), remote.LOCAL)
                with mock.patch.object(remote, "WINDOWS", False):
                    self.assertEqual(remote.classify(url), remote.SSH)
        with mock.patch.object(remote, "WINDOWS", True):
            self.assertEqual(remote.classify("git@host:org/repo.git"), remote.SSH)

    def test_scheme_urls_are_urls(self):
        for url in ("https://host/org/repo.git", "http://host/r", "git://host/r",
                    "ssh://git@host:2222/org/repo", "ftp://host/r"):
            with self.subTest(url=url):
                self.assertEqual(remote.classify(url), remote.URL)


class ProbeTarget(unittest.TestCase):
    def test_ssh_maps_to_https(self):
        cases = [
            ("git@host:org/repo.git", "https://host/org/repo.git"),
            ("ssh://git@host:2222/org/repo", "https://host/org/repo"),
            ("git@ssh.dev.azure.com:v3/org/proj/repo", "https://dev.azure.com/org/proj/_git/repo"),
        ]
        for url, want in cases:
            with self.subTest(url=url):
                self.assertEqual(remote.probe_target(url), want)

    def test_git_and_http_urls_are_probed_as_given(self):
        for url in ("https://host/org/repo.git", "http://host:8080/r.git",
                    "git://127.0.0.1:9418/state.git"):
            with self.subTest(url=url):
                self.assertEqual(remote.probe_target(url), url)

    def test_userinfo_is_stripped(self):
        cases = [
            ("git://someone@127.0.0.1:9418/state.git", "git://127.0.0.1:9418/state.git"),
            ("ssh://me@host/org/repo", "https://host/org/repo"),
            ("https://token@host/org/repo.git", "https://host/org/repo.git"),
            ("deploy@host:org/repo.git", "https://host/org/repo.git"),
            ("HTTPS://host/org/repo.git", "https://host/org/repo.git"),
        ]
        for url, want in cases:
            with self.subTest(url=url):
                self.assertEqual(remote.probe_target(url), want)

    def test_local_urls_have_no_probe(self):
        for url in ("/abs/path", "rel/path", "./foo:bar", "file:///x"):
            with self.subTest(url=url):
                self.assertIsNone(remote.probe_target(url))


class Credentials(unittest.TestCase):
    def test_refused(self):
        for url in ("https://user:secret@host/r.git", "https://secret@host/r.git",
                    "http://user@host/r.git", "ssh://git:secret@host/org/r",
                    "git://user:secret@host/r.git"):
            with self.subTest(url=url):
                self.assertTrue(remote.has_credentials(url))

    def test_allowed(self):
        for url in ("ssh://git@host/org/r", "git@host:org/r.git", "https://host/r.git",
                    "git://host/r.git", "/abs/user:secret@x", "https://host/path@x"):
            with self.subTest(url=url):
                self.assertFalse(remote.has_credentials(url))


# --- the probe: what it runs and how it is isolated ---------------------------


class Probe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="devos-remote-probe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        home = os.path.join(self.tmp, "home")
        os.mkdir(home)
        env = clean_env(home)
        # The probe's temp folder lands inside a git repo that carries config:
        # only the probe's own isolation keeps git from finding and reading it.
        outer = os.path.join(self.tmp, "outer")
        git(env, "init", "-q", outer)
        git(env, "-C", outer, "config", "url.https://leak.invalid/.insteadOf", "https://host/")
        self.inner_tmp = os.path.join(outer, "tmp")
        os.mkdir(self.inner_tmp)
        hostile = {
            "GIT_DIR": os.path.join(outer, ".git"),
            "GIT_CONFIG_PARAMETERS": "'credential.helper'='store'",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": "store",
            "GIT_ASKPASS": "/bin/echo",
            "SSH_ASKPASS": "/bin/echo",
            "GIT_TERMINAL_PROMPT": "1",
        }
        patcher = mock.patch.dict(os.environ, hostile)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp_patcher = mock.patch.object(tempfile, "tempdir", self.inner_tmp)
        tmp_patcher.start()
        self.addCleanup(tmp_patcher.stop)

    def fake_run(self, returncode=128, raises=None):
        real_run = subprocess.run
        seen = {}

        def fake(args, **kwargs):
            seen["args"] = list(args)
            seen.update(kwargs)
            cwd, env = kwargs["cwd"], kwargs["env"]
            seen["cwd_listing"] = os.listdir(cwd)
            seen["home_listing"] = os.listdir(env["HOME"])
            seen["discovery"] = real_run(
                ["git", "rev-parse", "--git-dir"], cwd=cwd, env=env,
                capture_output=True, text=True,
            )
            seen["config"] = real_run(
                ["git", "config", "--list", "--show-origin"], cwd=cwd, env=env,
                capture_output=True, text=True,
            )
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(args, returncode, "", "")

        return seen, fake

    def test_probe_runs_isolated_anonymous_ls_remote(self):
        seen, fake = self.fake_run()
        with mock.patch.object(remote.subprocess, "run", side_effect=fake):
            self.assertFalse(remote.readable_anonymously("git@host:org/repo.git"))

        args, env = seen["args"], seen["env"]
        self.assertEqual(args[0], "git")
        self.assertIn("ls-remote", args)
        self.assertNotIn("--exit-code", args)  # an empty public repo must still read as public
        self.assertEqual(args[-1], "https://host/org/repo.git")
        pairs = list(zip(args, args[1:]))
        self.assertIn(("-c", "credential.helper="), pairs)
        self.assertIn(("-c", "core.askPass="), pairs)
        self.assertIn(("-c", "http.emptyAuth=false"), pairs)  # no Kerberos sign-in

        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_ASKPASS"], "")
        self.assertEqual(env["SSH_ASKPASS"], "")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        for name in ("GIT_DIR", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
                     "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
            self.assertNotIn(name, env)
        self.assertEqual(seen["home_listing"], [])
        self.assertEqual(env["XDG_CONFIG_HOME"], env["HOME"])

        self.assertEqual(seen["timeout"], 15)
        self.assertEqual(seen["stdin"], subprocess.DEVNULL)
        self.assertEqual(seen["cwd_listing"], [])
        self.assertNotEqual(seen["discovery"].returncode, 0,
                            "probe folder is inside a repo: " + seen["discovery"].stdout)
        self.assertEqual(seen["config"].stdout, "", "probe reads git config")
        self.assertFalse(os.path.exists(seen["cwd"]), "probe temp folder left behind")

    def test_exit_0_means_public(self):
        seen, fake = self.fake_run(returncode=0)
        with mock.patch.object(remote.subprocess, "run", side_effect=fake):
            self.assertTrue(remote.readable_anonymously("git://127.0.0.1:9418/state.git"))
        self.assertEqual(seen["args"][-1], "git://127.0.0.1:9418/state.git")

    def test_other_exits_and_timeout_mean_not_public(self):
        for returncode in (2, 128, -9):
            seen, fake = self.fake_run(returncode=returncode)
            with self.subTest(returncode=returncode):
                with mock.patch.object(remote.subprocess, "run", side_effect=fake):
                    self.assertFalse(remote.readable_anonymously("https://host/r.git"))
        seen, fake = self.fake_run(raises=subprocess.TimeoutExpired(["git"], 15))
        with mock.patch.object(remote.subprocess, "run", side_effect=fake):
            self.assertFalse(remote.readable_anonymously("https://host/r.git"))
        self.assertFalse(os.path.exists(seen["cwd"]), "probe temp folder left behind")

    def test_local_urls_are_never_probed(self):
        with mock.patch.object(remote.subprocess, "run") as run:
            for url in ("/abs/path", "rel/path", "./foo:bar", "file:///x"):
                self.assertFalse(remote.readable_anonymously(url))
        run.assert_not_called()


# --- the command line, run as a subprocess -------------------------------------


class CommandLine(StateRepoCase):
    def test_no_marker_exits_2(self):
        os.remove(self.devos)
        self.assert_line(self.run_remote("check"), 2, contains=("not a DevOS state repo",))
        self.assert_line(self.run_remote("check", "--url", "/abs/x.git"), 2,
                         contains=("not a DevOS state repo",))
        self.assert_line(self.run_remote("confirm", "/abs/x.git"), 2,
                         contains=("not a DevOS state repo",))

    def test_malformed_marker_exits_2_and_points_to_the_checker(self):
        for text in ("format: 2\n", "", "remote: /x\nformat: 1\n", "format: 1\nbogus\n",
                     "format: 1\nremote:\n", "format: 1\nremote: /a\nremote: /a\n",
                     "format: 1\nremotes: /a\n"):
            with self.subTest(devos=text):
                write_bytes(self.devos, text.encode("utf-8"))
                self.assert_line(self.run_remote("check", "--url", "/abs/x.git"), 2,
                                 contains=("check.py",))

    def test_tolerant_marker_forms_are_read(self):
        text = "﻿format: 1\r\n\r\n  remote: git@h.invalid:o/r.git  \r\n\n"
        write_bytes(self.devos, text.encode("utf-8"))
        self.assert_line(self.run_remote("check", "--url", "/abs/x.git"), 0)

    def test_usage_errors_exit_2_with_one_line(self):
        for args in ([], ["check", "extra"], ["check", "--url"], ["check", "--url", ""],
                     ["confirm"], ["confirm", "a", "b"], ["confirm", ""], ["bogus"],
                     ["check", "--help"], ["-h"], ["--help"], ["confirm", " /x"],
                     ["check", "--url", "/x\nremote: /y"]):
            with self.subTest(args=args):
                self.assert_line(self.run_remote(*args), 2)

    def test_local_remote_is_allowed(self):
        path = os.path.join(self.tmp, "backup.git")
        self.git("remote", "add", "origin", path)
        self.assert_line(self.run_remote("check"), 0, starts="remote origin: " + path)
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_local_paths_and_file_urls_are_allowed_by_url(self):
        for url in ("/abs/path/state.git", "rel/path", "./foo:bar", "file:///x/state.git"):
            with self.subTest(url=url):
                self.assert_line(self.run_remote("check", "--url", url), 0, starts=url)

    def test_no_remote_exits_2(self):
        self.assert_line(self.run_remote("check"), 2, contains=("no remote to pick",))

    def test_picks_the_only_remote(self):
        self.git("remote", "add", "solo", "/srv/solo.git")
        self.assert_line(self.run_remote("check"), 0, starts="remote solo: /srv/solo.git")

    def test_picks_the_upstream_remote_first(self):
        for name in ("alpha", "beta", "origin"):
            self.git("remote", "add", name, "/srv/{}.git".format(name))
        self.git("config", "branch.main.remote", "beta")
        self.git("config", "branch.main.merge", "refs/heads/main")
        self.assert_line(self.run_remote("check"), 0, starts="remote beta: /srv/beta.git")

    def test_picks_origin_among_several(self):
        for name in ("alpha", "beta", "origin"):
            self.git("remote", "add", name, "/srv/{}.git".format(name))
        self.assert_line(self.run_remote("check"), 0, starts="remote origin: /srv/origin.git")

    def test_upstream_that_is_not_a_remote_falls_through(self):
        for name in ("alpha", "origin"):
            self.git("remote", "add", name, "/srv/{}.git".format(name))
        self.git("config", "branch.main.remote", ".")
        self.assert_line(self.run_remote("check"), 0, starts="remote origin: /srv/origin.git")

    def test_several_remotes_without_origin_or_upstream_exit_2(self):
        for name in ("alpha", "beta"):
            self.git("remote", "add", name, "/srv/{}.git".format(name))
        self.assert_line(self.run_remote("check"), 2, contains=("no remote to pick",))

    def test_credentials_in_the_remote_url_exit_2_without_printing_them(self):
        self.git("remote", "add", "origin", "https://someone:hunter2@git.example.invalid/r.git")
        line = self.assert_line(self.run_remote("check"), 2, starts="remote origin: ",
                                contains=(CREDENTIALS,))
        self.assertNotIn("hunter2", line)
        self.assertNotIn("someone", line)
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_git_missing_exits_2_not_1(self):
        self.git("remote", "add", "origin", "/srv/origin.git")
        empty_bin = os.path.join(self.tmp, "empty-bin")
        os.mkdir(empty_bin)
        env = dict(self.env, PATH=empty_bin)
        self.assert_line(self.run_remote("check", env=env), 2)


# --- in-process cases with the probe replaced by a mock -----------------------


class WithMockProbe(StateRepoCase):
    def setUp(self):
        super().setUp()
        cwd = os.getcwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, cwd)
        env_patcher = mock.patch.dict(os.environ, self.env, clear=True)
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        self.probe = mock.Mock(return_value=False)
        probe_patcher = mock.patch.object(remote, "readable_anonymously", self.probe)
        probe_patcher.start()
        self.addCleanup(probe_patcher.stop)

    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = remote.main(list(args))
        return subprocess.CompletedProcess(args, code, out.getvalue(), "")

    def probed(self):
        return [c.args[0] for c in self.probe.call_args_list]

    def confirm_lines(self):
        return [line for line in read_bytes(self.devos).decode("utf-8").splitlines()
                if line.startswith("remote:")]

    def test_local_urls_skip_the_probe_and_write_nothing(self):
        for url in ("/abs/path/state.git", "rel/path", "./foo:bar", "file:///x/state.git"):
            with self.subTest(url=url):
                self.assert_line(self.main("check", "--url", url), 0, starts=url)
                self.assert_line(self.main("confirm", url), 0, starts=url)
        self.probe.assert_not_called()
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_local_remote_skips_the_probe(self):
        self.git("remote", "add", "origin", "/srv/origin.git")
        self.assert_line(self.main("check"), 0, starts="remote origin: /srv/origin.git")
        self.probe.assert_not_called()

    def test_unconfirmed_url_exits_3_naming_it(self):
        self.git("remote", "add", "origin", SSH_ONE)
        self.assert_line(self.main("check"), 3, starts="remote origin: " + SSH_ONE,
                         contains=(NOT_CONFIRMED,))
        self.assertEqual(self.probed(), [SSH_ONE])
        self.assert_line(self.main("check", "--url", SSH_ONE), 3, starts=SSH_ONE,
                         contains=(NOT_CONFIRMED,))

    def test_confirmed_private_url_is_allowed(self):
        self.git("remote", "add", "origin", SSH_ONE)
        write_bytes(self.devos, (MARKER + "remote: " + SSH_ONE + "\n").encode("utf-8"))
        self.assert_line(self.main("check"), 0, starts="remote origin: " + SSH_ONE)
        self.assertEqual(self.probed(), [SSH_ONE])

    def test_public_url_exits_1_even_when_confirmed(self):
        self.probe.return_value = True
        self.git("remote", "add", "origin", SSH_ONE)
        write_bytes(self.devos, (MARKER + "remote: " + SSH_ONE + "\n").encode("utf-8"))
        self.assert_line(self.main("check"), 1, starts="remote origin: " + SSH_ONE,
                         contains=(PUBLIC, PRIVATE_FIRST))
        self.assert_line(self.main("check", "--url", SSH_ONE), 1, starts=SSH_ONE,
                         contains=(PUBLIC, PRIVATE_FIRST))

    def test_every_push_url_is_checked(self):
        self.git("remote", "add", "origin", "/srv/origin.git")
        for url in ("/srv/origin.git", SSH_ONE, SSH_TWO):
            self.git("config", "--add", "remote.origin.pushurl", url)
        write_bytes(self.devos, (MARKER + "remote: " + SSH_ONE + "\n").encode("utf-8"))
        self.assert_line(self.main("check"), 3, starts="remote origin: " + SSH_TWO)
        self.assertEqual(sorted(self.probed()), sorted([SSH_ONE, SSH_TWO]))

        self.probe.side_effect = lambda url: url == SSH_TWO
        self.assert_line(self.main("check"), 1, starts="remote origin: " + SSH_TWO)

        self.probe.side_effect = None
        self.assert_line(self.main("confirm", SSH_TWO), 0, starts=SSH_TWO)
        line = self.assert_line(self.main("check"), 0, starts="remote origin: /srv/origin.git")
        self.assertIn(SSH_ONE, line)
        self.assertIn(SSH_TWO, line)

    def test_push_url_is_checked_not_the_fetch_url(self):
        self.git("remote", "add", "origin", "/srv/origin.git")
        self.git("config", "remote.origin.pushurl", SSH_ONE)
        self.assert_line(self.main("check"), 3, starts="remote origin: " + SSH_ONE)

    def test_credentials_exit_2_without_probing_or_writing(self):
        for url in ("https://someone:hunter2@git.example.invalid/r.git",
                    "https://hunter2@git.example.invalid/r.git",
                    "ssh://git:hunter2@git.example.invalid/org/r"):
            with self.subTest(url=url):
                for args in (("check", "--url", url), ("confirm", url)):
                    line = self.assert_line(self.main(*args), 2, contains=(CREDENTIALS,))
                    self.assertNotIn("hunter2", line)
        self.probe.assert_not_called()
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_ssh_user_without_password_is_probed(self):
        url = "ssh://git@git.example.invalid/org/r"
        self.assert_line(self.main("check", "--url", url), 3, starts=url)
        self.assertEqual(self.probed(), [url])

    def test_confirm_appends_one_line_and_is_idempotent(self):
        self.assert_line(self.main("confirm", SSH_ONE), 0, starts=SSH_ONE)
        after_first = read_bytes(self.devos)
        self.assertEqual(after_first, (MARKER + "remote: " + SSH_ONE + "\n").encode("utf-8"))
        self.assert_line(self.main("confirm", SSH_ONE), 0, starts=SSH_ONE)
        self.assertEqual(read_bytes(self.devos), after_first)
        self.assert_line(self.main("confirm", SSH_TWO), 0, starts=SSH_TWO)
        self.assertEqual(self.confirm_lines(), ["remote: " + SSH_ONE, "remote: " + SSH_TWO])
        self.assert_line(self.main("check", "--url", SSH_TWO), 0, starts=SSH_TWO)

    def test_url_that_reads_back_as_several_lines_is_refused(self):
        # str.splitlines() also breaks on these, so recording such a URL would
        # read back as more than one `remote:` line: a URL nobody confirmed.
        for sep in ("\u2028", "\u2029", "\x85", "\x1c"):
            url = SSH_ONE + sep + "remote: " + SSH_TWO
            with self.subTest(sep=repr(sep)):
                self.assert_line(self.main("confirm", url), 2)
                self.assert_line(self.main("check", "--url", url), 2)
        self.probe.assert_not_called()
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_confirm_adds_a_missing_final_newline_first(self):
        write_bytes(self.devos, b"format: 1")
        self.assert_line(self.main("confirm", SSH_ONE), 0)
        self.assertEqual(read_bytes(self.devos),
                         ("format: 1\nremote: " + SSH_ONE + "\n").encode("utf-8"))

    def test_confirm_refuses_a_public_url(self):
        self.probe.return_value = True
        self.assert_line(self.main("confirm", SSH_ONE), 1, starts=SSH_ONE,
                         contains=(PUBLIC, PRIVATE_FIRST))
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_unexpected_error_in_the_probe_exits_2(self):
        self.probe.side_effect = RuntimeError("boom")
        self.assert_line(self.main("check", "--url", SSH_ONE), 2)
        self.assert_line(self.main("confirm", SSH_ONE), 2)
        self.assertEqual(read_bytes(self.devos), MARKER.encode("utf-8"))

    def test_unexpected_error_in_git_exits_2(self):
        self.git("remote", "add", "origin", SSH_ONE)
        with mock.patch.object(remote.subprocess, "run", side_effect=OSError("no git")):
            self.assert_line(self.main("check"), 2)

    def test_marker_read_failure_exits_2(self):
        with mock.patch("builtins.open", side_effect=PermissionError("denied")):
            self.assert_line(self.main("check", "--url", "/abs/x.git"), 2)


# --- integration: the real probe against a real git daemon --------------------


def free_port():
    """A TCP port on 127.0.0.1 that nothing listens on right now."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def git_daemon_missing():
    """None when `git daemon` is installed, else the reason to skip."""
    try:
        exec_path = subprocess.run(["git", "--exec-path"], capture_output=True,
                                   text=True).stdout.strip()
    except OSError:
        return "git is not installed"
    if not os.path.isfile(os.path.join(exec_path, "git-daemon")):
        return "git daemon is not installed (no git-daemon in `git --exec-path`)"
    return None


def make_bare(env, path, seed):
    git(env, "init", "-q", "--bare", path)
    if seed:
        tree = git(env, "-C", path, "mktree", input="").strip()
        commit = git(env, "-C", path, "-c", "user.name=Test", "-c", "user.email=t@example.com",
                     "commit-tree", tree, "-m", "seed").strip()
        git(env, "-C", path, "update-ref", "refs/heads/main", commit)


def stop_daemon(proc):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


HOSTILE_CONFIG = """[url "{closed}"]
\tinsteadOf = {public}
[url "{public}"]
\tinsteadOf = {closed}
"""


class GitDaemon(ResultAsserts):
    @classmethod
    def setUpClass(cls):
        reason = git_daemon_missing()
        if reason:
            raise unittest.SkipTest(reason)
        cls.tmp = tempfile.mkdtemp(prefix="devos-remote-daemon-")
        cls.addClassCleanup(shutil.rmtree, cls.tmp, True)
        home = os.path.join(cls.tmp, "home")
        os.mkdir(home)
        cls.env = clean_env(home)
        served = os.path.join(cls.tmp, "served")
        os.mkdir(served)
        make_bare(cls.env, os.path.join(served, "state.git"), seed=True)
        make_bare(cls.env, os.path.join(served, "empty.git"), seed=False)

        port = free_port()
        cls.log_path = os.path.join(cls.tmp, "daemon.log")
        log = open(cls.log_path, "w")
        cls.addClassCleanup(log.close)
        cls.daemon = subprocess.Popen(
            ["git", "daemon", "--listen=127.0.0.1", "--port={}".format(port),
             "--export-all", "--base-path=" + served, "--reuseaddr"],
            env=cls.env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
        )
        cls.addClassCleanup(stop_daemon, cls.daemon)
        cls.public_url = "git://127.0.0.1:{}/state.git".format(port)
        cls.empty_url = "git://127.0.0.1:{}/empty.git".format(port)
        cls.prefix_public = "git://127.0.0.1:{}/".format(port)
        closed = free_port()
        cls.closed_url = "git://127.0.0.1:{}/state.git".format(closed)
        cls.prefix_closed = "git://127.0.0.1:{}/".format(closed)
        cls.wait_until_serving()

    @classmethod
    def wait_until_serving(cls):
        # Control arm: plain anonymous git can read the served repo, so a 1 from
        # remote.py below comes from its own probe reading it.
        deadline = time.time() + 15
        while True:
            if cls.daemon.poll() is not None:
                with open(cls.log_path) as f:
                    raise AssertionError("git daemon exited:\n" + f.read())
            result = subprocess.run(["git", "ls-remote", cls.public_url], env=cls.env,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and "refs/heads/main" in result.stdout:
                return
            if time.time() > deadline:
                raise AssertionError("git daemon never served:\n" + describe(result))
            time.sleep(0.1)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="devos-remote-daemon-case-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def state_repo(self, origin=None):
        repo = make_state_repo(self.env, self.tmp)
        if origin is not None:
            git(self.env, "-C", repo, "remote", "add", "origin", origin)
        return repo

    def test_closed_port_refuses_connections(self):
        result = subprocess.run(["git", "ls-remote", self.closed_url], env=self.env,
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, describe(result))

    def test_check_refuses_a_public_repo_even_when_confirmed(self):
        repo = self.state_repo(origin=self.public_url)
        write_bytes(os.path.join(repo, ".devos"),
                    (MARKER + "remote: " + self.public_url + "\n").encode("utf-8"))
        self.assert_line(run_script(repo, self.env, "check"), 1,
                         starts="remote origin: " + self.public_url,
                         contains=(PUBLIC, PRIVATE_FIRST))
        self.assert_line(run_script(repo, self.env, "check", "--url", self.public_url), 1,
                         starts=self.public_url, contains=(PUBLIC,))

    def test_check_refuses_an_empty_public_repo(self):
        repo = self.state_repo()
        write_bytes(os.path.join(repo, ".devos"),
                    (MARKER + "remote: " + self.empty_url + "\n").encode("utf-8"))
        self.assert_line(run_script(repo, self.env, "check", "--url", self.empty_url), 1,
                         starts=self.empty_url, contains=(PUBLIC,))

    def test_confirm_refuses_to_record_a_public_repo(self):
        repo = self.state_repo()
        devos = os.path.join(repo, ".devos")
        before = read_bytes(devos)
        self.assert_line(run_script(repo, self.env, "confirm", self.public_url), 1,
                         starts=self.public_url, contains=(PUBLIC, PRIVATE_FIRST))
        self.assertEqual(read_bytes(devos), before)

    def test_unreadable_url_needs_a_confirmed_line(self):
        repo = self.state_repo(origin=self.closed_url)
        devos = os.path.join(repo, ".devos")
        self.assert_line(run_script(repo, self.env, "check"), 3,
                         starts="remote origin: " + self.closed_url, contains=(NOT_CONFIRMED,))
        self.assert_line(run_script(repo, self.env, "check", "--url", self.closed_url), 3,
                         starts=self.closed_url, contains=(NOT_CONFIRMED,))
        self.assertEqual(read_bytes(devos), MARKER.encode("utf-8"))

        self.assert_line(run_script(repo, self.env, "confirm", self.closed_url), 0,
                         starts=self.closed_url)
        self.assertEqual(read_bytes(devos),
                         (MARKER + "remote: " + self.closed_url + "\n").encode("utf-8"))
        self.assert_line(run_script(repo, self.env, "check"), 0,
                         starts="remote origin: " + self.closed_url)
        self.assert_line(run_script(repo, self.env, "check", "--url", self.closed_url), 0,
                         starts=self.closed_url)

    def hostile_sources(self):
        """Each way git could pick up config, each holding the same two URL rewrites:
        the public URL to the closed port, and the closed port to the public URL."""
        config = HOSTILE_CONFIG.format(public=self.prefix_public, closed=self.prefix_closed)
        home = os.path.join(self.tmp, "hostile-home")
        os.mkdir(home)
        write_bytes(os.path.join(home, ".gitconfig"), config.encode("utf-8"))
        xdg = os.path.join(self.tmp, "hostile-xdg")
        os.makedirs(os.path.join(xdg, "git"))
        write_bytes(os.path.join(xdg, "git", "config"), config.encode("utf-8"))
        system = os.path.join(self.tmp, "hostile-system")
        write_bytes(system, config.encode("utf-8"))
        git_dir_repo = os.path.join(self.tmp, "hostile-repo")
        git(self.env, "init", "-q", git_dir_repo)
        write_bytes(os.path.join(git_dir_repo, ".git", "config"),
                    (read_bytes(os.path.join(git_dir_repo, ".git", "config")).decode("utf-8")
                     + config).encode("utf-8"))
        rules = [(self.prefix_closed, self.prefix_public), (self.prefix_public, self.prefix_closed)]
        count = {"GIT_CONFIG_COUNT": str(len(rules))}
        for i, (base, instead) in enumerate(rules):
            count["GIT_CONFIG_KEY_{}".format(i)] = "url.{}.insteadOf".format(base)
            count["GIT_CONFIG_VALUE_{}".format(i)] = instead
        parameters = " ".join("'url.{}.insteadof'='{}'".format(base, instead)
                              for base, instead in rules)
        no_system = dict(self.env)
        del no_system["GIT_CONFIG_NOSYSTEM"]
        return {
            "home": dict(self.env, HOME=home),
            "xdg": dict(self.env, XDG_CONFIG_HOME=xdg),
            "system": dict(no_system, GIT_CONFIG_SYSTEM=system),
            "git_dir": dict(self.env, GIT_DIR=os.path.join(git_dir_repo, ".git")),
            "config_count": dict(self.env, **count),
            "config_parameters": dict(self.env, GIT_CONFIG_PARAMETERS=parameters),
        }, config

    def test_probe_ignores_every_git_config_source(self):
        sources, config = self.hostile_sources()
        repo = self.state_repo()
        with open(os.path.join(repo, ".git", "config"), "a", encoding="utf-8") as f:
            f.write(config)
        plain_dir = os.path.join(self.tmp, "plain")
        os.mkdir(plain_dir)

        # Control arms: each source alone makes plain git read the closed-port URL
        # from the daemon, so a probe that honoured any of them would flip the result.
        for name, env in sorted(sources.items()):
            with self.subTest(control=name):
                result = subprocess.run(["git", "ls-remote", self.closed_url], cwd=plain_dir,
                                        env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, describe(result))
        result = subprocess.run(["git", "ls-remote", self.closed_url], cwd=repo,
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, "repo config control arm\n" + describe(result))

        hostile = dict(self.env)
        del hostile["GIT_CONFIG_NOSYSTEM"]
        for env in sources.values():
            for key, value in env.items():
                if self.env.get(key) != value:
                    hostile[key] = value
        self.assert_line(run_script(repo, hostile, "check", "--url", self.public_url), 1,
                         starts=self.public_url, contains=(PUBLIC,))
        self.assert_line(run_script(repo, hostile, "check", "--url", self.closed_url), 3,
                         starts=self.closed_url, contains=(NOT_CONFIRMED,))


if __name__ == "__main__":
    unittest.main()
