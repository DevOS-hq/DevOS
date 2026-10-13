---
name: init
description: Set up a DevOS state repo in the current folder. It writes the .devos marker, AGENTS.md, CLAUDE.md and the record folders, makes the first git commit, and connects a remote when the user gives a URL. Use when the user asks to init, set up, create or start a DevOS state repo, or to turn a folder into one.
---

# Init

Turn the current folder into a DevOS state repo and commit the files that make it one. Work only in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every file you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines the layout and the `.devos` marker.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop when there is nothing to do

- If the folder holds a `.devos` file, it is already a state repo. Change nothing, and tell the user it is already a state repo.
- If the user gave a remote URL and `git remote get-url origin` prints a different URL, change nothing. Reply with both URLs and ask which one to use.

Without a URL, set up a local repo and don't ask for one.

## Write the files

If the folder holds `.git`, it is already a git repo. Keep it and stay on its current branch. Otherwise run `git init -b main`.

Create each of these files that is missing:

| File | Content |
|---|---|
| `.devos` | the one line `format: 1` |
| `AGENTS.md` | the DevOS section below |
| `CLAUDE.md` | the one line `@AGENTS.md` |
| `projects/.gitkeep` | nothing |
| `progress-reports/.gitkeep` | nothing |

When `AGENTS.md` already exists, keep the user's text. Add a blank line and the DevOS section at the end, unless the file already has a `## DevOS` heading.

When `CLAUDE.md` already exists, keep the user's text. Add the line `@AGENTS.md` at the end, unless the file already has that line.

Leave every other file in the folder as it is.

The DevOS section, to copy as it stands:

```markdown
## DevOS

This folder is a DevOS state repo. It keeps project records as markdown files in git.

- Change records through the DevOS skills. Each skill writes its files in the format the plugin defines and commits them.
- Load the DevOS `writing` skill before you write any prose here, commit messages included.
- When you edit a record by hand, keep the format that FORMAT.md defines. FORMAT.md sits at the root of the DevOS plugin folder, next to `skills/`. Commit the change afterward.
```

## Check the files

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a file you wrote, then run the checker again. If a problem sits in a file you did not write, leave that file alone and name the problem in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the files you created or changed, by path. A change the user had already staged then stays staged and out of your commit:

```sh
git add -- <paths>
git commit -m "<subject>" -- <paths>
```

`<paths>` lists each file you created or changed, such as `.devos AGENTS.md CLAUDE.md projects/.gitkeep progress-reports/.gitkeep`. Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages. For example: `Set up the DevOS state repo`

## Push

Push only when the user gave a remote URL. Check the URL before you add it as `origin`.

1. From the state repo root, run the plugin's remote check, `../../scripts/remote.py`, with its full path. For example: `python3 /path/to/plugin/scripts/remote.py check --url <url>`. It prints one line about the URL.
2. Exit 0: if the repo has no `origin`, run `git remote add origin <url>`. If `origin` already has that URL, keep it. Then run `git remote get-url --push --all origin`. If it prints only `<url>`, run `git push -u origin HEAD`. If it prints any other URL, a git setting sends the push there and the check never saw it: don't push, keep `origin`, and name the URL in your reply. The next skill that pushes checks it.
3. Exit 3: nobody has confirmed the URL. Ask the user, word for word: "Is `<url>` a private repository on your company's Git host, under your work account?" Only a clear yes counts. On yes, run `python3 /path/to/plugin/scripts/remote.py confirm <url>`. If it exits 0, commit `.devos` alone with `git commit -m "Confirm the push remote" -- .devos` and go back to step 1. On anything else, don't push.
4. Exit 1: the repo can be read without signing in. Don't push. Tell the user to make it private first.
5. Any other exit, or no `python3`: don't push, and say why in your reply.
6. When the check stops the push, keep the local commits and add no `origin`.
7. If the push fails, keep the local commits and `origin`. Quote the error in one line in your reply.

Never create the remote repository, on GitHub or anywhere else. Without a URL, add no remote and don't push.

## Reply

Follow the `writing` rules for replies about state. Say which folder is now a state repo and what the commit holds. Say whether you pushed, and whether the check ran and passed.
