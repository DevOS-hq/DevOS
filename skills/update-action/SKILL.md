---
name: update-action
description: Change an action in a DevOS state repo. It moves the action between To do, In progress and Done, changes its priority or name, or deletes it, and commits actions.md. Use when the user asks to mark an action done, start an action, move an action back to to do, change an action's priority, rename an action or delete an action.
---

# Update action

Change one action in a project's `actions.md` and commit the file. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every line you write, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. It defines `actions.md` and the action line.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Find the action

The user names the action and may name its project.

- With a project named, search that project's `actions.md`. Match the project by its folder name under `projects/` or by the name in its `# <Project name>` title, ignoring case.
- With no project named, search the `actions.md` of every project.
- In the paths below, `<project>` is the folder name of the matched action's project, never its title.

An action matches when its name holds the user's words, ignoring case. When one name equals the user's words exactly, that action is the only match.

With exactly one match, use it. With none or several, the action counts as missing. List the candidates in your question with their project and section. With no match, the candidates are every action you searched.

## Get the change

The user asks for one or more of these changes:

| Change | Value you need |
|---|---|
| Status | the target section: `To do`, `In progress` or `Done` |
| Priority | `P0`, `P1`, `P2` or `P3`. P0 is the most urgent |
| Name | the new name |
| Delete | a request that says to delete or remove the action |

A priority given another way, such as "high", counts as missing. Moving an action to another project is out of scope. Change nothing and say so.

If the action, the change or a value it needs is missing, write nothing and run no command that changes a file. Ask for every missing value in one reply, one question per value, and end your turn. Never guess a value. When the user answers, continue from here with the answers.

If the action already has the status, priority or name the user asked for, change nothing and say so.

## Make the change

Change only the lines you must, with targeted edits. Never rewrite or reformat the file. An action's block is its line plus the indented notes under it.

- To change the status, delete the block from its section. Add it at the bottom of the target section, after the last action there and that action's notes. Keep the notes under the line as they are.
- When the action moves into `## Done`, run `date +%F` in the shell and use its output as today. Add ` · done <today>` to the end of the line. Never take today's date from your own sense of time.
- When the action moves out of `## Done`, drop the ` · done <date>` part. A move between `## In progress` and `## To do` keeps the line as it is.
- To change the priority, edit only the priority part of the line.
- To rename the action, edit only the name part of the line.
- To delete the action, delete its block. Do this only when the user asked to delete or remove it. Marking an action done moves it to `## Done`.

FORMAT.md reads the line from the right, so the name is everything before the priority. Never change the added date.

Tidy only the blank lines your edit touched:

- When a removal leaves two blank lines in a row, delete one. An emptied section is then its heading, one blank line and the next heading.
- In a section that was empty, the moved line goes after the heading, with one blank line between them.
- Keep one blank line between a section's last line and the next heading.
- Leave every other line as it is. The file ends with one newline and no blank line after the last line.

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

Write the subject by the `writing` rules for commit messages. For example: `Mark "Map the current checkout flow" done in checkout-revamp`

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

Follow the `writing` rules for replies about state. Say which action changed, how, and in which file. Say whether you pushed, and whether the check ran and passed.
