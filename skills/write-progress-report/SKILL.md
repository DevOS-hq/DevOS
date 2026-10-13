---
name: write-progress-report
description: Write a progress report across every project in a DevOS state repo for a time frame the user gives. It runs window.py to select the evidence and done actions in the frame, writes an impact summary and a progress list for each project under progress-reports, and commits it. Use when the user asks to write a progress report, a monthly or quarterly update, a brag doc, or a summary of impact for a performance review.
---

# Write progress report

Write one progress report from the evidence and done actions of every project, and commit it. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines the progress report and the time frame.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Get the frame

Run `date +%F` in the shell and use its output as today. Never take today's date from your own sense of time.

The time frame is required. It is a start date and an end date, each `YYYY-MM-DD`.

- Turn a relative frame into dates from today. `last month` is the previous calendar month. `Q3` is July 1 to September 30 of this year, or of last year if this year's Q3 has not started. State the dates in your reply.
- A frame that could mean more than one range, such as `the last sprint` or `recently`, counts as missing.

If the frame is missing, write nothing and run no command that changes a file. Ask for it in one reply and end your turn. Never guess a value. When the user answers, continue from here with the answer.

If `progress-reports/<today>.md` already exists, change nothing. Ask whether to replace it and end your turn. When the user says yes, continue and write the new report over that file.

## Select the items

If `python3` is missing, write nothing and say the report needs `python3` to select the items in the frame.

Never pick items by reading `actions.md` or `evidence.md` yourself. Run the plugin's `../../scripts/window.py` on the state repo with its full path, for this report, even when you ran it earlier in the conversation:

```sh
python3 /path/to/plugin/scripts/window.py . --all --start <start> --end <end>
```

Then act on the exit code:

- On exit 0, write the report from the output. It starts with a `Frame: <start> to <end>` line. Then comes one block for each project with evidence or done actions in the frame. A block starts with a `Project: <Project name> (<project>)` line, followed by the lists `Done actions in frame:` and `Evidence in frame:`. A list that prints `- None` is empty.
- When the output is only the `Frame:` line, no project has anything in the frame. Write nothing, and say so with the frame's dates.
- On exit 1, a line in some `actions.md` or `evidence.md` cannot be read. Write nothing. Quote the lines the script printed and ask the user to fix them.
- On exit 2, write nothing and quote the error.

If an item is not in the output, it is not in the report.

## Write the report

Write `progress-reports/<today>.md`. Create the `progress-reports` folder when it is missing.

```markdown
# Progress report

- **Share date:** <today>
- **Time frame:** <start> to <end>

## <Project name>

- **Impact summary:** <one or two sentences>

### Progress

- <item>
```

- Copy the time frame's two dates from the `Frame:` line.
- Write one `## <Project name>` section for each `Project:` block, in the order the output prints them. Take the name from the `Project:` line, without the folder name in parentheses.
- Write no section for a project the output leaves out.

The Impact summary says in one or two sentences what the project changed for its users or team in the frame.

- Draw it from the Impact text of the project's evidence in the output.
- When the output has no evidence for the project, draw it from the project's done actions.
- Keep a number when the source has one. Never invent one.
- Don't repeat the progress list in it.

`### Progress` lists what the project delivered in the frame:

- Write one item for each done action and each evidence item the output lists for the project.
- When an evidence item describes the same work as a done action, you may write one item that covers both. Never merge unrelated work, and never drop an item.
- Lead with the outcome. For a `delivered` evidence item, say the work shipped and claim no measured result.

The summary and the list do different jobs, so never write the same sentence in both. The summary states the result once. Each item names one piece of work and adds what the summary leaves out, taken from the output, such as the change behind the result and its links. This matters most when a project has one item. For example:

```markdown
- **Impact summary:** CI runs take 6 minutes instead of 14.

### Progress

- Moved the build cache to object storage. See the [CI dashboard](https://example.com/ci).
```

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
git add -- progress-reports/<today>.md
git commit -m "<subject>" -- progress-reports/<today>.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Add the <today> progress report`

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

Follow the `writing` rules for replies about state. Say which report you wrote, in which file, and its time frame with both dates. Say whether you pushed, and whether the check ran and passed.
