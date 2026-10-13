"""`init` with a remote that cannot be reached keeps the local commit.

Start: an empty folder. The URL is a path to a git repo that does not exist.
Prompt: use the DevOS `init` skill here, with that URL as the remote.
Check: the state repo as in init_empty, `origin` set to the URL, nothing
created at the URL, and a reply that reports the failed push.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _initcheck as common  # noqa: E402
import asserts  # noqa: E402

CLIS = ("claude",)
START = "empty"
TIMEOUT = 900
PROMPT = common.PROMPT[:-1] + ", with {remote} as its remote."

PUSH = re.compile(r"(?i)\bpush")
FAILED = re.compile(
    r"(?i)\b(fail\w*|error|could ?n[o']t|cannot|can't|unable|not (a|found|exist|appear|reach)\w*|does ?n[o']t exist)"
)


def setup(repo, tmp):
    return {"remote": os.path.join(tmp, "missing", "remote.git")}


def check(run):
    url = run.subs["remote"]
    common.fresh_commit(run, "main")
    if asserts.remotes(run) != {"origin": url}:
        asserts.fail("expected origin = {}, found {}".format(url, asserts.remotes(run)))
    if os.path.exists(url) or os.path.exists(os.path.dirname(url)):
        asserts.fail("init created the remote at {}; it must only report the failed push".format(url))
    if not (PUSH.search(run.text) and FAILED.search(run.text)):
        asserts.fail("the reply does not report the failed push: {!r}".format(run.text))
