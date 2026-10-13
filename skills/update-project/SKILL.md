---
name: update-project
description: Change a project in a DevOS state repo. It edits the priority, stakeholders or requirements in project.md, or renames the project and its folder, and commits the change. Use when the user asks to update a project, change its priority or stakeholders, add a requirement, change or remove a requirement, or rename a project.
---

# Update project

Change one project's `project.md` and commit it. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines `project.md` and slugs.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Find the project

Match the project the user names by its folder name under `projects/` or by the name in its `# <Project name>` title, ignoring case. With exactly one match, use it. With no project named, or a name that matches no folder or more than one, the project counts as missing. List the projects under `projects/` in your question.

## Get the change

The user asks for one or more of these changes:

| Change | Values you need |
|---|---|
| Priority | `P0`, `P1`, `P2` or `P3`. P0 is the most urgent |
| Stakeholders | the people or teams, or `none` |
| Add a requirement | its name, type, stakeholders (or `none`) and description |
| Change a requirement | the requirement and its new name, type, stakeholders or description |
| Delete a requirement | the requirement, and a request that says to delete or remove it |
| Rename the project | the new name |

The type is `need` when the project fails without the requirement, and `want` when it adds value but can be dropped. A priority given another way, such as "high", counts as missing.

Match a requirement by its `###` heading under `## Requirements`, ignoring case. With none or several matches, the requirement counts as missing. List the requirements in your question.

If the project, the change or a value it needs is missing, write nothing and run no command that changes a file. Ask for every missing value in one reply, one question per value, and end your turn. Never guess a value. When the user answers, continue from here with the answers.

## Make the change

Change only the lines you must, with targeted edits. Never rewrite or reformat the file. Leave every other line as it is.

- To change the priority or the stakeholders, edit that field under the title.
- To add a requirement, insert its block inside `## Requirements`, after the last requirement's block and right before the next `##` heading. When no heading follows, add the block at the end of the file. Never put it under another section, such as `## Notes`.
- To change a requirement, edit only its `###` heading or the fields that change.
- To delete a requirement, delete its `###` heading and every line up to the next `###` or `##` heading, or to the end of the file. Do this only when the user asked to delete or remove it.

A new requirement block has this shape. Keep one blank line before it and one blank line between it and the next heading:

```markdown
### <Requirement name>

- **Type:** <need or want>
- **Stakeholders:** <names, separated by commas, or none>
- **Description:** <what the requirement delivers>
```

Write names and stakeholders as the user gave them. Write each description by the `writing` rules and keep every fact the user gave.

When a deletion leaves two blank lines in a row, delete one. The file ends with one newline and no blank line after the last line.

## Rename the project

The folder name always matches the project name.

1. Make the new slug from the new name by the rules in FORMAT.md's Slugs section. For example, `Q4: Search & Latency!` becomes `q4-search-latency`. If the slug comes out empty, ask for a name with letters or digits.
2. If the new slug equals the old folder name, change only the `# <Project name>` title and commit as for any other change.
3. If `projects/<new-slug>/` already exists, change nothing. Say that the folder exists, ask for another name, and end your turn.
4. Run `git mv projects/<old-slug> projects/<new-slug>`.
5. Change the `# <Project name>` title in `projects/<new-slug>/project.md` to the new name.

## Check the file

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a line you wrote, then run the checker again. Leave every other problem as it is and name it in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the file you changed, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- projects/<slug>/project.md
git commit -m "<subject>" -- projects/<slug>/project.md
```

After `git mv`, skip `git add`. The old paths no longer exist, so `git add` fails on them. Name both folders in the commit, which then records the rename:

```sh
git commit -m "<subject>" -- projects/<old-slug> projects/<new-slug>
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Add the Saved cards requirement to Checkout Revamp`

## Push

Run `git remote`. If it prints nothing, don't push.

1. If the current branch has an upstream, run `git push`. The command `git rev-parse --abbrev-ref '@{u}'` prints the upstream, and fails when there is none.
2. Otherwise run `git push -u <remote> HEAD` with the remote that `git remote` printed. When it printed several, use `origin`.
3. If the push fails, keep the local commit. Quote the error in one line in your reply.

Never add a remote or create a remote repository.

## Reply

Follow the `writing` rules for replies about state. Say what changed in which project and file. Say whether you pushed, and whether the check ran and passed.
