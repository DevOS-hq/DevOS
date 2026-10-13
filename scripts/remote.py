#!/usr/bin/env python3
"""Check that a state repo may push to its remote, before every push.

Usage (run from the state repo root, the folder holding `.devos`):
  python3 scripts/remote.py check              check the remote a push would use
  python3 scripts/remote.py check --url <url>  check one URL (before it is a remote)
  python3 scripts/remote.py confirm <url>      record that the user confirmed <url>

A push may go to a path on this machine (a local path or a `file://` URL), or
to a URL the user confirmed is a private repository on their company's Git
host, under their work account. A confirmation is a `remote: <url>` line in
`.devos`, with the URL exactly as `git remote get-url` prints it.

`check` picks the remote a push would use: the current branch's upstream
remote, else the only remote, else `origin`. It checks every URL that
`git remote get-url --push --all <remote>` prints. Skills then push with
`git push -u <remote> HEAD` to the remote it named.

Before a URL is allowed or confirmed, one anonymous, read-only
`git ls-remote` probes it, with credential helpers, askpass, terminal prompts,
system and user git config all turned off (SSH URLs are probed over HTTPS).
If anyone can read the repo without signing in, it is refused even when
confirmed. Any other probe result leaves the decision to the confirmation.
Local paths and `file://` URLs are never probed.

Every run prints one line on stdout. In `check` mode it starts
`remote <name>: <url>`; otherwise it starts with the URL, or with `remote.py:`
for a usage or setup error.

Exit codes:
  0  allowed (for `confirm`: recorded, already recorded, or a local path)
  1  refused: the repo can be read without signing in; make it private first
  2  usage error, not a state repo, `.devos` not valid, no remote to pick,
     credentials in the URL, or any unexpected error
  3  not confirmed: `.devos` has no `remote:` line for the URL the line names

Standard library only; runs on Python 3.9 and later.
"""

import os
import shutil
import subprocess
import sys
import tempfile

PROG = "remote.py"
MARKER = "format: 1"
PROBE_TIMEOUT = 15
USAGE = "usage: remote.py check | remote.py check --url <url> | remote.py confirm <url>"

LOCAL, SSH, URL = "local", "ssh", "url"
SSH_SCHEMES = ("ssh", "git+ssh", "ssh+git")
PROBED_SCHEMES = ("http", "https", "git")
AZURE_SSH_HOSTS = ("ssh.dev.azure.com", "vs-ssh.visualstudio.com")
WINDOWS = os.name == "nt"

# Prepended to the probe's `git` call. Empty values clear what any config set;
# `http.emptyAuth=false` stops git signing in with a Kerberos ticket on its own;
# the protocol rules keep the probe on the transports it means to use.
PROBE_CONFIG = [
    "credential.helper=",
    "core.askPass=",
    "http.emptyAuth=false",
    "http.extraHeader=",
    "protocol.allow=never",
    "protocol.http.allow=always",
    "protocol.https.allow=always",
    "protocol.git.allow=always",
]

ALLOWED_LOCAL = "a path on this machine"
ALLOWED_CONFIRMED = "confirmed in .devos"


class Stop(Exception):
    """Ends the run with an exit code and its one output line."""

    def __init__(self, code, line):
        Exception.__init__(self, line)
        self.code = code
        self.line = line


# --- URLs ---------------------------------------------------------------------


def classify(url):
    """LOCAL, SSH or URL, by git's rule.

    A string holding `://` is a URL (`file://` is local); otherwise a colon
    before the first slash makes it an scp-like SSH address; otherwise it is a
    local path. On Windows a drive letter and colon (`C:/x`) is a local path.
    """
    if "://" in url:
        return LOCAL if url.startswith("file://") else URL
    if WINDOWS and len(url) >= 2 and url[1] == ":" and url[0].isascii() and url[0].isalpha():
        return LOCAL
    colon = url.find(":")
    slash = url.find("/")
    if colon != -1 and (slash == -1 or colon < slash):
        return SSH
    return LOCAL


def split_url(url):
    """(scheme, userinfo or None, host[:port], rest) of a `scheme://` URL.

    `rest` is everything after the host, starting with its `/` when present.
    """
    scheme, after = url.split("://", 1)
    slash = after.find("/")
    authority, rest = (after, "") if slash == -1 else (after[:slash], after[slash:])
    userinfo, at, hostport = authority.rpartition("@")
    if not at:
        return scheme, None, authority, rest
    return scheme, userinfo, hostport, rest


def has_credentials(url):
    """True for an http(s) URL with userinfo, or any URL with a password."""
    if "://" not in url:
        return False
    scheme, userinfo, _, _ = split_url(url)
    if userinfo is None:
        return False
    return scheme.lower() in ("http", "https") or ":" in userinfo


def redact(url):
    """`url` with any userinfo replaced by `***`, safe to print."""
    if "://" not in url:
        return url
    scheme, userinfo, hostport, rest = split_url(url)
    if userinfo is None:
        return url
    return "{}://***@{}{}".format(scheme, hostport, rest)


def strip_port(hostport):
    if hostport.startswith("["):
        return hostport[:hostport.find("]") + 1] if "]" in hostport else hostport
    return hostport.partition(":")[0]


def https_for_ssh(host, path):
    """Best-effort HTTPS URL for an SSH host and repo path."""
    path = path.lstrip("/")
    if host.lower() in AZURE_SSH_HOSTS:
        parts = path.split("/")
        if len(parts) == 4 and parts[0] == "v3":
            return "https://dev.azure.com/{}/{}/_git/{}".format(parts[1], parts[2], parts[3])
    return "https://{}/{}".format(host, path)


def probe_target(url):
    """The URL the anonymous probe reads for `url`, without userinfo, or None.

    SSH addresses map to HTTPS; `http(s)://` and `git://` URLs are read as
    given. Local paths, `file://` URLs and other schemes have no probe.
    """
    kind = classify(url)
    if kind == LOCAL:
        return None
    if kind == SSH:
        hostpart, _, path = url.partition(":")
        return https_for_ssh(hostpart.rpartition("@")[2], path)
    scheme, _, hostport, rest = split_url(url)
    if scheme.lower() in SSH_SCHEMES:
        return https_for_ssh(strip_port(hostport), rest)
    if scheme.lower() in PROBED_SCHEMES:
        return "{}://{}{}".format(scheme.lower(), hostport, rest)
    return None


# --- the anonymous probe ------------------------------------------------------


def probe_env(home):
    """The probe's environment: no GIT_* from the caller, no prompts, no config."""
    env = dict((k, v) for k, v in os.environ.items() if not k.startswith("GIT_"))
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CEILING_DIRECTORIES": os.path.dirname(home),
        "HOME": home,
        "XDG_CONFIG_HOME": home,
    })
    return env


def probe_args(target):
    args = ["git"]
    for setting in PROBE_CONFIG:
        args += ["-c", setting]
    return args + ["ls-remote", "--", target]


def readable_anonymously(url):
    """True when anyone can read `url` without signing in.

    Runs one `git ls-remote` with no credentials from an empty temp folder
    outside any repo. A timeout, a refusal or any other failure is False.
    """
    target = probe_target(url)
    if target is None:
        return False
    home = os.path.realpath(tempfile.mkdtemp(prefix="devos-probe-"))
    try:
        try:
            result = subprocess.run(
                probe_args(target), cwd=home, env=probe_env(home),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=PROBE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False
        return result.returncode == 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


# --- the state repo -----------------------------------------------------------


def read_marker(root):
    """The confirmed URLs in `.devos`, in file order; Stop(2) when it is not valid.

    Same reading as check.py: blank lines and surrounding whitespace are
    ignored, the first line is `format: 1`, every later line is a unique
    `remote: <url>`.
    """
    path = os.path.join(root, ".devos")
    if not os.path.isfile(path):
        raise Stop(2, "{}: no .devos here, so this is not a DevOS state repo; "
                      "run it from the state repo root".format(PROG))
    invalid = Stop(2, "{}: .devos is not valid; run the checker, scripts/check.py, "
                      "on the state repo to see the defect".format(PROG))
    try:
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        raise invalid
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines or lines[0] != MARKER:
        raise invalid
    urls = []
    for line in lines[1:]:
        key, colon, url = line.partition(":")
        url = url.strip()
        if key != "remote" or not colon or not url or url in urls:
            raise invalid
        urls.append(url)
    return urls


def append_remote(root, url):
    """Add `remote: <url>` as the last line of `.devos`, ending the file in a newline first."""
    path = os.path.join(root, ".devos")
    with open(path, "rb") as f:
        data = f.read()
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    addition = b""
    if data and not data.endswith((b"\n", b"\r")):
        addition += newline
    addition += ("remote: " + url).encode("utf-8") + newline
    with open(path, "ab") as f:
        f.write(addition)


def git(args):
    """Stdout lines of `git <args>` in the current folder; Stop(2) when it fails."""
    result = subprocess.run(
        ["git"] + args, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr.strip().splitlines() or ["exit {}".format(result.returncode)])[0]
        raise Stop(2, "{}: `git {}` failed: {}".format(PROG, " ".join(args), detail))
    return [line for line in result.stdout.split("\n") if line]


def upstream_remote():
    """The current branch's `branch.<name>.remote`, or None."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--quiet", "--short", "HEAD"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch:
        return None
    result = subprocess.run(
        ["git", "config", "--get", "branch.{}.remote".format(branch)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def pick_remote():
    """The remote a push uses: the upstream remote, else the only one, else `origin`."""
    names = git(["remote"])
    if not names:
        raise Stop(2, "{}: no remote to pick: `git remote` prints nothing".format(PROG))
    upstream = upstream_remote()
    if upstream in names:
        return upstream
    if len(names) == 1:
        return names[0]
    if "origin" in names:
        return "origin"
    raise Stop(2, "{}: no remote to pick: the branch has no upstream remote, and none of "
                  "the {} remotes is named origin".format(PROG, len(names)))


# --- the three modes ----------------------------------------------------------


def credentials_line(url):
    return "{} holds credentials; take the credentials out of the remote URL".format(redact(url))


def public_line(url):
    return "{} can be read without signing in; it must be made private first".format(url)


def check(urls, confirmed, prefix=""):
    """(exit code, line) for a push to every URL in `urls`."""
    for url in urls:
        if has_credentials(url):
            return 2, prefix + credentials_line(url)
    remote_urls = [url for url in urls if classify(url) != LOCAL]
    for url in remote_urls:
        if readable_anonymously(url):
            return 1, prefix + public_line(url)
    for url in remote_urls:
        if url not in confirmed:
            return 3, prefix + "{} is not confirmed: .devos has no remote: line for it".format(url)
    parts = ["{} is allowed ({})".format(
        url, ALLOWED_LOCAL if classify(url) == LOCAL else ALLOWED_CONFIRMED) for url in urls]
    return 0, prefix + "; ".join(parts)


def confirm(url, confirmed, root):
    """(exit code, line) after recording that the user confirmed `url`."""
    if has_credentials(url):
        return 2, credentials_line(url)
    if classify(url) == LOCAL:
        return 0, "{} is {}; nothing to confirm".format(url, ALLOWED_LOCAL)
    if readable_anonymously(url):
        return 1, public_line(url)
    if url in confirmed:
        return 0, "{} is already confirmed in .devos".format(url)
    append_remote(root, url)
    return 0, "{} is now confirmed: added a remote: line for it to .devos".format(url)


def usable(url):
    """True for a non-empty URL with no control characters and no space at either end.

    It must also read back as one line, so no character that `splitlines()`
    breaks on (U+0085, U+2028, U+2029) may appear in it.
    """
    return (bool(url) and url == url.strip() and url.splitlines() == [url]
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in url))


def parse_args(argv):
    """(mode, url or None); Stop(2) for anything else, including any help flag."""
    if argv == ["check"]:
        return "check", None
    if len(argv) == 3 and argv[:2] == ["check", "--url"]:
        mode, url = "check", argv[2]
    elif len(argv) == 2 and argv[0] == "confirm":
        mode, url = "confirm", argv[1]
    else:
        raise Stop(2, "{}: {}".format(PROG, USAGE))
    if not usable(url):
        raise Stop(2, "{}: not a usable remote URL: {!r}".format(PROG, url))
    return mode, url


def run(argv):
    mode, url = parse_args(argv)
    root = os.getcwd()
    confirmed = read_marker(root)
    if mode == "confirm":
        return confirm(url, confirmed, root)
    if url is not None:
        return check([url], confirmed)
    name = pick_remote()
    urls = git(["remote", "get-url", "--push", "--all", name])
    if not urls:
        raise Stop(2, "{}: remote {} has no URL".format(PROG, name))
    return check(urls, confirmed, prefix="remote {}: ".format(name))


def main(argv=None):
    # Exit 1 means "public", so no failure may fall through to Python's default 1.
    try:
        try:
            code, line = run(sys.argv[1:] if argv is None else list(argv))
        except Stop as e:
            code, line = e.code, e.line
        except (Exception, KeyboardInterrupt) as e:
            code, line = 2, "{}: unexpected error, so no push: {}: {}".format(
                PROG, type(e).__name__, e)
        print(" ".join(line.splitlines()))
        sys.stdout.flush()
        return code
    except Exception:
        return 2


if __name__ == "__main__":
    sys.exit(main())
