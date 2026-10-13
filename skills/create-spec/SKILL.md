---
name: create-spec
description: Create a spec for a project in a DevOS state repo. It interviews the user for the problem, goals, non-goals, milestones, risks and open questions, shows an outline to confirm, then writes the spec's brief.md, spec.md and appendix.md and commits them. Use when the user asks to create a spec, write a spec, spec out a feature or a change, or write a design doc.
---

# Create spec

Interview the user, write one spec as three files under `projects/<project>/specs/<slug>/`, and commit them. Work only in the state repo in the current folder.

## Load the rules first

1. Load the DevOS `writing` skill by name. Follow it for every file you write, every question, the commit message and your reply. Its file is `../writing/SKILL.md`, relative to this SKILL.md. If another skill is also named `writing`, use this one.
2. Read `../../FORMAT.md`, relative to this SKILL.md, before you write anything. Its Spec section defines the three files. Its Slugs and Anchors sections define the folder name and the links.

Every plugin path in this skill is relative to this SKILL.md. The plugin root is two folders up from it. Turn each path into a full path before you use it, because your shell runs in the state repo.

## Stop outside a state repo

If the current folder has no `.devos` file, change nothing and run no git command. Reply that this folder is not a DevOS state repo and that the `init` skill sets one up. Then stop.

## Get the project and the name

The project and the spec name are required before you write anything.

- Ask for the project when the user named none, even when the repo holds only one project.
- Match the project by folder name or title, ignoring case. When the user's project matches no folder, or more than one, it counts as missing. List the projects under `projects/` in your question, and say that the `create-project` skill creates a new one. In the paths below, `<project>` is the matched folder's name, never the title.
- Make the slug from the spec name by the rules in FORMAT.md's Slugs section. For example, `Guest checkout: v2` becomes `guest-checkout-v2`. If the slug comes out empty, ask for a name with letters or digits.
- If `projects/<project>/specs/<slug>/` already exists, change nothing. Say that the spec exists and that the user can edit its files by hand. The name then counts as missing, so ask for another one.

## Know what the spec needs

Fill these slots from the user's words, starting with the first message:

| Slot | What fills it |
|---|---|
| Problem | who is affected, what goes wrong, and one concrete example |
| Goals | what the work must achieve |
| Non-goals | options the user rules out, or "none" |
| Milestones | what each milestone ships. A target date only when the user gives one |
| Risks | each risk, with its mitigation when the user gives one, or "none" |
| Open questions | the questions the user says are still open, or "none" |
| Supporting material | optional: links, data, alternatives considered or background, or "none" |

A slot is filled when the user answered it. A missing target date or mitigation leaves its slot filled. A slot is deferred when the user answers "I don't know yet", "TBD" or "undecided", or says to leave it open. Every other slot is empty.

## Interview, then confirm

Follow these steps in order. Ask in plain text. Each step that asks ends your turn, and the steps go on when the user answers.

1. **Round 1.** Create and edit no file, and run no git command that changes the repo. Reply with every empty slot as numbered questions, grouped by theme, plus the project and the name when they are missing. End your turn. When no slot is empty and you have the project and the name, go to step 4 instead.
2. **Later rounds.** After each answer, update the slots. Ask again only about the slots that are still empty, in one reply, and end your turn. Never ask again about a filled or deferred slot.
3. **The cap.** Ask at most three rounds of questions about the slots. Once the user has answered the third round, each slot still empty becomes an open question, such as "What are the risks?". Never ask a fourth round about the slots. Keep asking for the project and the name until the user gives them.
4. **The outline.** Once every slot is filled or deferred, or the cap is reached, reply with a short outline and end your turn. Write nothing yet, even when the user already said to go ahead. Open the outline with the spec name and its folder, written out in full with the real project and slug, such as `projects/checkout-revamp/specs/guest-checkout-v2/`. Give the parts in this shape:

   ```markdown
   <Spec name>, in projects/<project>/specs/<slug>/

   - Summary: <the problem, then the approach>
   - Goals: <each goal>
   - Non-goals: <each non-goal, or None>
   - Milestones: <each milestone, with its target date when given>
   - Risks: <each risk and its mitigation, or None>
   - Open questions: <each question, or None>
   - Appendix: <the supporting material, or none yet>
   ```

   End the outline by asking whether to write the spec as shown.
5. **Write.** When the user says yes, write the files. When the user sends corrections, apply them and write the files with no second outline. Ask again only when a correction is itself unclear, and only about that point.

## Never invent

- When the user says "I don't know yet", "TBD" or "undecided" about a slot or a point, write it under Open questions as a question in the user's words. For example, "I don't know yet whether refunds are in scope" becomes "Are refunds in scope?".
- Never ask about a deferred point again, and never answer it yourself. Never turn it into a goal, milestone, date, owner or number, and keep it out of every other section.
- Add no milestone, date, owner, number or decision the user did not give, and suggest none in your questions.
- "None" is an answer. Write it as `- None` and don't ask again.
- Write a target date as `YYYY-MM-DD`. If you can't turn the user's date into one, ask about it.

## Write the spec

Create `projects/<project>/specs/<slug>/` with three files. Use the spec name as the user gave it in each title. End each file with one newline.

`spec.md` takes this shape:

```markdown
# <Spec name>

## Summary

<the problem, then the approach>

## Goals

- <goal>

## Non-goals

- <non-goal>

## Milestones

### Milestone 1: <short name>

<what ships>. Target: <YYYY-MM-DD>

## Risks

- <risk>. Mitigation: <mitigation>

## Open questions

- <question>
```

- **Summary:** two to four sentences. Say who is affected and what goes wrong, then the approach. Add the user's concrete example. When the user gave none, add the open question "What is a concrete example of the problem?" instead.
- **Goals:** one item per goal. When the goals are deferred, write `- None` and add an open question.
- **Non-goals:** one item per option the user ruled out, or `- None`.
- **Milestones:** one `### Milestone <n>: <short name>` per milestone, in the user's order, saying what it ships in the user's words. Add `Target: <date>` only when the user gave a date. When the milestones are deferred, write `- None` and add an open question.
- **Risks:** one item per risk, with `Mitigation:` and the mitigation when the user gave one, or `- None`.
- **Open questions:** every deferred point and every question the user raised, each as a question, or `- None`.

`brief.md` is for a reader with no context. It takes this shape:

```markdown
# <Spec name>: brief

## The problem

- [<who is affected and what goes wrong>](spec.md#summary)

## The goal

- [<what the work achieves>](spec.md#goals)

## The plan

- [<what milestone 1 ships>](spec.md#milestone-1-<short-name>)

## Not doing

- [<what the work leaves out>](spec.md#non-goals)

## Still open

- [<question>](spec.md#open-questions)
```

- Link each item to the `spec.md` section it summarizes: The problem to `spec.md#summary`, The goal to `spec.md#goals`, The plan to `spec.md#milestones` or a milestone's own anchor, Not doing to `spec.md#non-goals`, and Still open to `spec.md#open-questions`.
- Compute each anchor by FORMAT.md's Anchors section. For example, `### Milestone 1: Payment form` has the anchor `milestone-1-payment-form`.
- Make each item a full claim that a stranger can read without opening `spec.md` or the item above it. The link adds detail. Use no "then", "next" or "it" that points to another item. The first problem item says who is affected and what goes wrong.
- Explain or leave out every project name, folder name, codename, acronym and technical term. The brief's reader knows none of them. For example, write "the checkout redesign" instead of `checkout-revamp`, and "a copy kept on the phone" instead of "a local cache".
- Under The goal, say what a change is measured against, such as "half as many failed payments as today". Under The plan, say what each milestone changes for the people affected, beyond the feature's name.
- Under Not doing, name each option the user ruled out as the thing left out, such as "No changes to the sign-up form", never as a status such as "The sign-up form stays as it is". Under Still open, write each item as a question, never as a task.
- Write `- None` under The goal, The plan, Not doing or Still open when the matching `spec.md` section holds `- None`.

`appendix.md` holds only the supporting material the user gave, under the title `# <Spec name>: appendix`:

- Use the headings `## Links`, `## Alternatives considered`, `## Background` and `## Data`, in that order, and only those that have content.
- Write each link as a list item `- [text](url)`, with text that names what the link shows. Keep the URL exactly as the user gave it.
- When the user gave no supporting material, write the one line `No supporting material yet.` under the title.

## Check the files

Run the plugin's checker, `../../scripts/check.py`, on the state repo with its full path. For example: `python3 /path/to/plugin/scripts/check.py .`

The checker prints one line per problem and exits 0 when the folder is valid. Fix each problem in a file you wrote, then run the checker again. Leave every other problem as it is and name it in your reply.

If `python3` is missing, skip the check and say so in your reply.

## Commit

Commit only the three files, by path, in one commit. A change the user had already staged then stays staged and out of your commit. Here `<dir>` is `projects/<project>/specs/<slug>`:

```sh
git add -- <dir>/brief.md <dir>/spec.md <dir>/appendix.md
git commit -m "<subject>" -- <dir>/brief.md <dir>/spec.md <dir>/appendix.md
```

Never run `git add -A`, `git add .` or `git commit -a`.

Write the subject by the `writing` rules for commit messages: under 72 characters, with no period at the end. Name a long spec in a few words. For example: `Add the guest checkout v2 spec to checkout-revamp`

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

Follow the `writing` rules for replies about state. Say which spec you wrote and which folder holds its three files. Say whether you pushed, and whether the check ran and passed.
