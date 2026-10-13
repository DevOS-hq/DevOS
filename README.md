# DevOS

DevOS is a plugin for Claude Code, Codex and Cursor that keeps a software engineer's project work in plain markdown: projects and their requirements, actions, evidence of impact, status reports, progress reports and specs. Each thing you do (create a project, add an action, write a status report) is one skill that reads and writes these files.

## Install

The plugin installs once per tool, for your user account. It never stores your work.

**Claude Code**

```
/plugin marketplace add DevOS-hq/DevOS
/plugin install devos@devos
```

**Codex**

```
codex plugin marketplace add DevOS-hq/DevOS
codex plugin add devos@devos
```

**Cursor**

Open Customize, choose From GitHub Repository, and enter `github.com/DevOS-hq/DevOS`.

## Your state repo

Your work lives in a separate git repository called a state repo. A folder is a state repo when its root holds a `.devos` file; the `init` skill creates one. To work in a state repo, open your agent in that folder. You can keep several on one machine, for example one per team, and plugin updates never change them.

Every record is a markdown file you can read and edit by hand:

```
.devos
projects/<project>/project.md
projects/<project>/actions.md
projects/<project>/evidence.md
projects/<project>/status-reports/<date>.md
projects/<project>/specs/<spec>/brief.md, spec.md, appendix.md
progress-reports/<date>.md
```

Keep a state repo on your machine, or in a private repository on your company's Git host, under your work account. DevOS does not push work records anywhere else.

Before any push, the skills run `scripts/remote.py`:

- A remote that is a path on your machine, or a `file://` URL, is always allowed.
- Any other remote must be confirmed. DevOS asks you once, word for word: "Is `<url>` a private repository on your company's Git host, under your work account?" A clear yes is recorded as a `remote: <url>` line in `.devos`, in its own commit. Every push checks again.
- The script also makes one anonymous, read-only `git ls-remote` against the remote, with credentials and your user and system git config turned off. If anyone can read the repo without signing in, the push is refused even when you confirmed it. Make the repo private first.
- A remote URL with credentials in it is refused.
- If `python3` or the script is missing or fails, nothing is pushed.

`init` checks the URL before it adds `origin`. If the check fails, it commits locally, adds no `origin` and pushes nothing. After it adds `origin`, it pushes only when git would push to that same URL, not one a git setting rewrites it to.

[FORMAT.md](FORMAT.md) defines each file. To check a state repo against it, run `python3 scripts/check.py <state-repo>` from the plugin folder; it prints one line per problem and needs only Python 3.9 or later.

## Skills

Ask your agent for the change you want, or name the skill. Each skill that changes a state repo asks for any required field you left out, commits only the files it touched, and pushes when the repo has a remote that passes the check described under "Your state repo".

- `init` sets up a state repo in the current folder.
- `create-project` creates a project with its priority, stakeholders and requirements.
- `update-project` changes a project's priority, stakeholders or requirements, or renames the project.
- `add-action` adds an action to a project.
- `update-action` moves an action between To do, In progress and Done, changes its priority or name, or deletes it.
- `record-evidence` records evidence of a project's impact, with its date, status and links.
- `write-status-report` writes one project's status report from its actions and evidence. The time frame starts at the project's last status report unless you give one.
- `write-progress-report` writes one report across all projects from their evidence and done actions, for a time frame you give.
- `create-spec` asks about the problem, goals, milestones, risks and open questions, shows an outline for you to confirm, then writes a project's spec as a brief, the full spec and an appendix.
- `writing` holds the plain-language rules the other skills follow for every file, commit message and reply.

The two report skills run `scripts/window.py`, which prints the actions and evidence in a time frame. A report holds only the items it prints, so the report skills need Python 3.9 or later. Apart from the one anonymous `git ls-remote` that `scripts/remote.py` makes before a push to a non-local remote, the scripts make no network calls.

## Testing

Run the offline suite from the plugin folder. It needs Python 3.9 or later and no internet access (one test talks to a git daemon on 127.0.0.1):

```
python3 -m unittest discover -s tests
```

It covers the checker, the banned-pattern check, the skill lint, the writing judge's rubric and the CLI runners. The runner tests drive stub CLIs from `tests/stubs`.

The live scenarios in `tests/e2e/scenarios` drive the real Claude Code, Codex and Cursor CLIs against temp state repos, so each run bills those accounts:

```
python3 tests/e2e/run.py --cli claude
python3 tests/e2e/run.py --cli codex --scenario init_empty
python3 tests/e2e/run.py --cli all --scenario agents_md_probe
```

Each scenario prints one PASS or FAIL line per CLI and runs once more before it reports FAIL. Add `--keep` to keep the temp folders. To check the writing judge, run `python3 tests/e2e/judge.py --calibrate`. It must fail `tests/e2e/samples/sloppy.md` and pass `tests/e2e/samples/clean.md`.

In headless runs, Claude Code, Codex and Cursor each followed a rule planted in a state repo's AGENTS.md without a tool call to read the file. Claude Code reads it through the `@AGENTS.md` line that `init` writes to CLAUDE.md.

## License

MIT. See [LICENSE](LICENSE). The `writing` skill condenses rules from MIT-licensed skills by other authors. [THIRD_PARTY.md](THIRD_PARTY.md) lists each source and its license.
