---
name: record-evidence
description: Record evidence of impact for a project in a DevOS state repo. It appends one dated item with the impact, its status and links to the project's evidence.md, and commits the file. Use when the user asks to record evidence, log impact, note a win or a result for a brag doc or performance review, or save proof that work shipped or moved a number.
---

# Record evidence

Add one evidence item to a project's `evidence.md` and commit the file. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines `evidence.md` and its fields.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Get the fields

Run `date +%F` in the shell and use its output as today. Never take today's date from your own sense of time.

An evidence item has these fields:

| Field | Value |
|---|---|
| Project | a folder name under `projects/`, or the name in that folder's `# <Project name>` title |
| Name | what the evidence shows, such as `CI runs take half as long` |
| Impact | what changed and for whom, with the number when the user gave one |
| Impact status | `delivered` or `measured` |
| References | one or more links, or `none` |
| Date | the day of the evidence. Without one, use today |

Project, name, impact, impact status and references are required.

- Ask for the project when the user named none, even when the repo holds only one project.
- Match the project by folder name or title, ignoring case. When the user's project matches no folder, or more than one, it counts as missing. List the projects under `projects/` in your question. In the paths below, `<project>` is the matched folder's name, never the title.
- Set the impact status only from the user's words. A result the user observed, such as a number that moved, means `measured`. Work the user says shipped or launched, with no observed result, means `delivered`. When the user names the status, use it. In any other case the status counts as missing.
- When the user gave no link, References counts as missing. When the user answers `none`, or says there is no link, write `none`.
- When the user gives a date, use it as `YYYY-MM-DD`. Turn a relative date, such as "yesterday", into one from today. A date after today counts as missing. Ask about it, and never write it.

If a required field is missing, write nothing and run no command that changes a file. Ask for every missing field in one reply, one question per field, and end your turn. Never guess a value. When the user answers, continue from here with the answers.

## Write the item

Build the item in the shape FORMAT.md gives:

```markdown
## <name>

- **Date:** <date>
- **Impact:** <impact>
- **Impact status:** <delivered or measured>
- **References:** <links, separated by commas, or none>
```

- Keep the user's words for the name, on one line, in sentence case.
- Write the impact in one or two sentences from the user's facts. Keep every number the user gave and add none.
- For a `delivered` item, say what shipped. Claim no result that no one has observed.
- Write each link as `[text](url)`. The text names what the link shows, such as `[Error dashboard](https://example.com/errors)`. Keep the URL exactly as the user gave it.

If `projects/<project>/evidence.md` is missing, create it with this content, one blank line, and the item:

```markdown
# Evidence
```

## Place the item

Change only the lines you must. Add the item with a targeted edit. Never rewrite or reformat the file.

- Put the item at the end of the file, after its last line that is not blank. In a file with no items yet, that line is the `# Evidence` title.
- Leave one blank line between that line and the new `##` heading.
- Leave every other line as it is. The file ends with one newline.

## Check the file

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a line you wrote, then run the checker again. Leave every other problem as it is and name it in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the file you changed, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- projects/<project>/evidence.md
git commit -m "<subject>" -- projects/<project>/evidence.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages: under 72 characters, with no period at the end. An evidence name is often a full sentence, so name the evidence in three or four words instead of quoting it. For example: `Record faster CI runs in checkout-revamp evidence`

## Push

Run `git remote`. If it prints nothing, don't push.

1. If the current branch has an upstream, run `git push`. The command `git rev-parse --abbrev-ref '@{u}'` prints the upstream, and fails when there is none.
2. Otherwise run `git push -u <remote> HEAD` with the remote that `git remote` printed. When it printed several, use `origin`.
3. If the push fails, keep the local commit. Quote the error in one line in your reply.

Never add a remote or create a remote repository.

## Reply

Follow the `writing` rules for replies about state. Say which evidence you added to which file, with its impact status. Say whether you pushed, and whether the check ran and passed.
