---
name: add-action
description: Add an action to a project in a DevOS state repo. It adds one line to the project's actions.md under To do, In progress or Done, and commits the file. Use when the user asks to add an action, a task or a to-do to a project, or to track new work on a project.
---

# Add action

Add one action to a project's `actions.md` and commit the file. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines `actions.md` and the action line.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Get the fields

An action has these fields:

| Field | Value |
|---|---|
| Name | the work to do, such as `Write the rollout plan` |
| Project | a folder name under `projects/`, or the name in that folder's `# <Project name>` title |
| Priority | `P0`, `P1`, `P2` or `P3`. P0 is the most urgent |
| Status | `To do`, `In progress` or `Done`. Without one, use `To do` |

Name, project and priority are required.

- Ask for the project when the user named none, even when the repo holds only one project.
- Match the project by folder name or title, ignoring case. When the user's project matches no folder, or more than one, it counts as missing. List the projects under `projects/` in your question. In the paths below, `<project>` is the matched folder's name, never the title.
- A priority given another way, such as "high", counts as missing.

If a required field is missing, write nothing and run no command that changes a file. Ask for every missing field in one reply, one question per field, and end your turn. Never guess a value. When the user answers, continue from here with the answers.

## Write the line

Run `date +%F` in the shell and use its output as today. Never take today's date from your own sense of time.

Build the line in the shape FORMAT.md gives:

```text
- <name> · <priority> · added <today>
```

For an action that goes straight to `## Done`, add ` · done <today>` at the end. Keep the user's words for the name, on one line. Drop quote marks that only wrap it.

If `projects/<project>/actions.md` is missing, create it with this content and the line in its section:

```markdown
# Actions

## In progress

## To do

## Done
```

## Place the line

Change only the lines you must. Insert the one new line with a targeted edit. Never rewrite or reformat the file.

- Put the line at the bottom of its section, after the last action there and after that action's indented notes. A note then stays with its own action.
- In an empty section, the line goes after the heading, with one blank line between them.
- Keep one blank line between the section's last line and the next heading.
- Leave every other line as it is. The file ends with one newline.

## Check the file

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a line you wrote, then run the checker again. Leave every other problem as it is and name it in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the file you changed, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- projects/<project>/actions.md
git commit -m "<subject>" -- projects/<project>/actions.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Add "Write the rollout plan" to checkout-revamp actions`

## Push

Run `git remote`. If it prints nothing, don't push.

1. If the current branch has an upstream, run `git push`. The command `git rev-parse --abbrev-ref '@{u}'` prints the upstream, and fails when there is none.
2. Otherwise run `git push -u <remote> HEAD` with the remote that `git remote` printed. When it printed several, use `origin`.
3. If the push fails, keep the local commit. Quote the error in one line in your reply.

Never add a remote or create a remote repository.

## Reply

Follow the `writing` rules for replies about state. Say which action you added to which file and section. Say whether you pushed, and whether the check ran and passed.
