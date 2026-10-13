---
name: create-project
description: Create a project in a DevOS state repo. It writes projects/<slug>/project.md with the priority, stakeholders and requirements, adds an empty actions.md, and commits both files. Use when the user asks to create a project, add a new project, start or set up a project, or track a new body of work.
---

# Create project

Create one project folder with its `project.md` and an empty `actions.md`, and commit both files. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every file you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines `project.md`, `actions.md` and slugs.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop when there is nothing to do

- If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.
- If `projects/<slug>/` already exists for the project's name, change nothing. Reply that the project exists and that the `update-project` skill changes it. Then stop.

Make the slug from the name by the rules in FORMAT.md's Slugs section. For example, `Q4: Search & Latency!` becomes `q4-search-latency`. If the slug comes out empty, ask for a name with letters or digits.

## Get the fields

A project has these fields:

| Field | Value |
|---|---|
| Name | the project's name, such as `Checkout Revamp` |
| Priority | `P0`, `P1`, `P2` or `P3`. P0 is the most urgent |
| Stakeholders | the people or teams with a stake in the project, or `none` |

All three are required. A priority given another way, such as "high", counts as missing.

Requirements are optional. Each requirement the user gives needs a name, a type, stakeholders (or `none`) and a description. The type is `need` when the project fails without the requirement, and `want` when it adds value but can be dropped.

If a required field is missing, write nothing and run no command that changes a file. Ask for every missing field in one reply, one question per field, and end your turn. Never guess a value. When the user answers, continue from here with the answers.

## Write the files

Create `projects/<slug>/project.md` in this shape, with the user's values:

```markdown
# <Project name>

- **Priority:** <priority>
- **Stakeholders:** <names, separated by commas, or none>

## Requirements

### <Requirement name>

- **Type:** <need or want>
- **Stakeholders:** <names, separated by commas, or none>
- **Description:** <what the requirement delivers>
```

Write one `###` block per requirement, in the order the user gave them, with one blank line between blocks. With no requirements, the file ends at the `## Requirements` line.

Create `projects/<slug>/actions.md` with this content:

```markdown
# Actions

## In progress

## To do

## Done
```

Write names and stakeholders as the user gave them. Write each description by the `writing` rules and keep every fact the user gave. End each file with one newline.

## Check the files

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a file you wrote, then run the checker again. If a problem sits in a file you did not write, leave that file alone and name the problem in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the two files you created, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- projects/<slug>/project.md projects/<slug>/actions.md
git commit -m "<subject>" -- projects/<slug>/project.md projects/<slug>/actions.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Create the Checkout Revamp project`

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

Follow the `writing` rules for replies about state. Say which project you created and which folder holds it. Say whether you pushed, and whether the check ran and passed.
