---
name: write-status-report
description: Write a status report for one project in a DevOS state repo. It runs window.py to select the done actions, evidence and open actions in the time frame, which starts at the project's last status report unless the user gives one, then writes the report under status-reports and commits it. Use when the user asks to write a status report, a project update or a weekly update, or to report what is done and pending on a project.
---

# Write status report

Write one project's status report from its actions and evidence, and commit it. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines the status report and the time frame.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Get the project and the frame

Run `date +%F` in the shell and use its output as today. Never take today's date from your own sense of time.

The project is required.

- Ask for the project when the user named none, even when the repo holds only one project.
- Match the project by folder name or title, ignoring case. When the user's project matches no folder, or more than one, it counts as missing. List the projects under `projects/` in your question. In the paths below, `<project>` is the matched folder's name, never the title.

The time frame is optional. Its end is the end date the user gives, or today. Its start is the start date the user gives. Without one, `window.py` starts the frame at the project's last status report. Turn a relative frame, such as "the last two weeks", into dates from today.

If the project is missing, write nothing and run no command that changes a file. Ask for it in one reply and end your turn. Never guess a value. When the user answers, continue from here with the answer.

If `projects/<project>/status-reports/<today>.md` already exists, change nothing. Ask whether to replace it and end your turn. When the user says yes, continue and write the new report over that file.

## Select the items

If `python3` is missing, write nothing and say the report needs `python3` to select the items in the frame.

Never pick items by reading `actions.md` or `evidence.md` yourself. Run the plugin's `../../scripts/window.py` on the state repo with its full path, for this report, even when you ran it earlier in the conversation:

```sh
python3 /path/to/plugin/scripts/window.py . --project <project> --end <end>
```

Add `--start <start>` when the user gave a start date. Then act on the exit code:

- On exit 0, write the report from the output. It starts with a `Frame: <start> to <end>` line and a `Project: <Project name> (<project>)` line. The lists `Done actions in frame:` and `Evidence in frame:` follow, then `Open actions:` with each action's notes, In progress first. A list that prints `- None` is empty.
- On exit 3, the project has no earlier status report, so the frame has no start. Write nothing. Ask for the frame's start date in one reply and end your turn. When the user answers, run `window.py` again with `--start`.
- On exit 1, a line in `actions.md` or `evidence.md` cannot be read. Write nothing. Quote the lines the script printed and ask the user to fix them.
- On exit 2, write nothing and quote the error.

If an item is not in the output, it is not in the report.

## Write the report

Write `projects/<project>/status-reports/<today>.md`. Create the `status-reports` folder when it is missing.

```markdown
# Status report: <Project name>

- **Share date:** <today>
- **Time frame:** <start> to <end>

## Done

- <item>

## Pending

- <item>
```

- Take the project name from the `Project:` line, without the folder name in parentheses.
- Copy the time frame's two dates from the `Frame:` line.

`## Done` lists what the frame delivered:

- Write one item for each done action in the output and one for each evidence item.
- When an evidence item describes the same work as a done action, you may write one item that covers both. Never merge unrelated work, and never drop an item.
- Lead with the outcome. Keep a number when the source has one. Never invent one.
- For a `delivered` evidence item, say the work shipped and claim no measured result.

`## Pending` lists every open action in the output:

- List every In progress action first, each followed by ` (in progress)`. Then list every To do action.
- When an action's note names a blocker, carry it into the item.
- Never list an open action under `## Done`, or a done action under `## Pending`.

For example:

```markdown
- Upgrade the CI runners (in progress).
- Move the build cache to object storage, waiting on the infra team's access grant.
```

Write `- None` under a section with nothing to list.

## Write for the reader

Lead each item with what changed for someone. Two pairs show the difference:

| Rule | Write | Instead of |
|---|---|---|
| Outcome over activity | `CI runs take 6 minutes instead of 14 since the build cache moved.` | `Worked on CI speed.` |
| A kept number over a slogan | `Failed sign-ins fell from 3.2% to 0.9% of attempts.` | `Greatly improved sign-in reliability.` |

- Cite only what `window.py` printed.
- Never repeat an item from an earlier report unless the output lists it.
- Never claim a measured result for a `delivered` item.

## Check the file

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in the report you wrote, then run the checker again. Leave every other problem as it is and name it in your reply.

## Commit

Commit only the report, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- projects/<project>/status-reports/<today>.md
git commit -m "<subject>" -- projects/<project>/status-reports/<today>.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Add the <today> status report for checkout-revamp`

## Push

Run `git remote`. If it prints nothing, don't push.

1. From the state repo root, run the plugin's remote check, `../../scripts/remote.py`, with its full path. For example: `python3 /path/to/plugin/scripts/remote.py check`. It picks the remote to push to and prints one line naming the remote and its URL.
2. Exit 0: run `git push -u <remote> HEAD` with the remote the check named.
3. Exit 3: the line names a URL nobody has confirmed. Ask the user, word for word: "Is `<url>` a private repository on your company's Git host, under your work account?" Only a clear yes counts. On yes, run `python3 /path/to/plugin/scripts/remote.py confirm <url>`. If it exits 0, commit `.devos` alone with `git commit -m "Confirm the push remote" -- .devos` and go back to step 1. On anything else, don't push.
4. Exit 1: the repo can be read without signing in. Don't push. Tell the user to make it private first.
5. Any other exit, or no `python3`: don't push, and say why in your reply.
6. If the push fails, keep the local commits. Quote the error in one line in your reply.

Never add a remote or create a remote repository.

## Reply

Follow the `writing` rules for replies about state. Say which report you wrote, in which file, and its time frame. Say whether you pushed, and whether the check ran and passed.
