# DevOS state format

A state repo is a git repository of markdown files that holds one person's DevOS records. This file defines every file DevOS reads and writes, so people and agents can edit state by hand and stay valid. `scripts/check.py` enforces these rules; each rule below names the checker rule id it maps to, in brackets.

## Marker

A folder is a state repo when its root holds a file named `.devos` whose first line is:

Example: `.devos`

```text
format: 1
```

A trailing newline is optional; surrounding whitespace, a trailing carriage return and blank lines are ignored. The number versions the format. Without a valid first line, skills treat the folder as not a state repo and point to `init` [`marker`].

Each later line is `remote: <url>`: a confirmed remote, one the user said is a private repository on their company's Git host, under their work account. The plugin's remote check, `scripts/remote.py`, writes a line when the user confirms a remote, and skills commit `.devos` alone after it. Skills push only to a remote the check allows. The URL is written exactly as `git remote get-url` prints it. A `remote:` line with no URL, a URL listed twice, or any other line is a defect [`marker`].

```text
format: 1
remote: git@git.example.com:me/devos-state.git
```

## Layout

```text
<state repo>/
  .devos
  AGENTS.md                    written by init
  CLAUDE.md                    written by init
  projects/
    <project>/
      project.md               required
      actions.md
      evidence.md
      status-reports/
        <YYYY-MM-DD>.md        one status report per share date
      specs/
        <spec>/
          brief.md             all three required
          spec.md
          appendix.md
  progress-reports/
    <YYYY-MM-DD>.md            one progress report per share date
```

- Every project folder needs `project.md` [`missing-file`]. Every spec folder needs `brief.md`, `spec.md` and `appendix.md` [`missing-file`].
- A record belongs to the project whose folder it sits in, so no record repeats the project as a field. Status report titles and progress report sections use the project name from the `# <Project name>` line of that project's `project.md`.
- A report file is named for its share date. Re-sharing a report on the same day replaces the file.
- Every other file is yours, and the checker ignores it, as it does any file or folder whose name starts with `.`. One exception: every `.md` file directly inside a `status-reports/` or `progress-reports/` folder must be a report named `<YYYY-MM-DD>.md` [`filename-date`].
- The checker does not read `AGENTS.md` or `CLAUDE.md`.
- State files are UTF-8 text. A byte-order mark at the start of a file is ignored, and so are Windows line endings.

## Common rules

### Lists and fields

- A list item starts at the beginning of a line with `- ` (`*`, `+` and `1.` also work). Indented lines under an item belong to it.
- A **field** is a list item `- **<Label>:** <value>`, with the colon inside the bold. Its value is the text after the label plus every indented line under it, nested list items included.
- Fields sit directly under their heading: after it and before the next heading of any level. If a label appears twice, the first one counts.
- A required field is missing when no item has its label, or when the label line and the lines under it are all empty [`missing-field`].
- **Stakeholders** and **References** take an inline comma-separated list or a nested list. **Stakeholders** may be `none`.
- Single-value fields (**Priority**, **Type**, **Date**, **Impact status**, **Share date**, **Time frame**) hold only their value.

### Dates and priorities

- A date is `YYYY-MM-DD` and must exist on the calendar: `2026-02-30` fails [`date`].
- A time frame is `<start date> to <end date>`, start on or before end [`time-frame`]. A time frame includes both its start and end dates. A well-formed time frame with an impossible date is a [`date`] defect.
- A priority is `P0`, `P1`, `P2` or `P3`; P0 is the most urgent [`priority`].

### Titles and headings

- Headings start at the beginning of a line with `#`.
- The **title** is the file's first heading and its only `#` heading. A missing, misplaced, wrongly worded or second `#` line is a [`title`] defect.
- Each required `##` or `###` heading appears once, in the order listed for its file. A missing, duplicated or out-of-order required heading is a [`heading`] defect.
- A **section** is a heading plus everything up to the next heading of the same or a higher level, so a `###` subsection belongs to the `##` section above it.
- Some headings name a record: in `evidence.md` every `##` is an evidence entry; in a progress report every `##` is a project section; under `## Requirements` every `###` is a requirement. These names must not be empty [`heading`]. Put headings of your own one level deeper there.

### Extra content

Extra headings (`## Notes`, `### Milestone 1`), extra fields (`- **Owner:** …`), prose and sub-bullets are allowed anywhere. The one exception is the three action sections of `actions.md`, where every list item must be an action line [`action-line`].

### Code blocks

Lines inside fenced code blocks (```` ``` ```` or `~~~`) are never read as headings, fields or list items. They still count as content when a section must not be empty.

### Slugs

A project or spec folder name is a slug: lowercase letters and digits in words joined by single hyphens, such as `checkout-revamp` [`slug`]. To derive it from a name: lowercase it; drop every character other than ASCII letters, digits, spaces and hyphens; turn spaces into `-`; collapse repeated `-`; trim `-` from both ends. `Q4: Search & Latency!` becomes `q4-search-latency`.

### Anchors

A brief links to a heading in `spec.md` by its anchor, computed the way GitHub does: strip inline markup (backticks, `*`, link syntax); lowercase; drop every character other than letters, digits, `_`, `-` and spaces; turn each space into `-`. When a heading's anchor repeats in the same file, the second gets `-1`, the third `-2`, in document order. So `## Non-goals` is `non-goals`, `### Milestone 1: payment form` is `milestone-1-payment-form`, and a second `### Notes` is `notes-1`.

## Records

### Project: `projects/<project>/project.md`

Example: `projects/checkout-revamp/project.md`

```markdown
# Checkout Revamp

- **Priority:** P1
- **Stakeholders:** Payments team, Support team

## Requirements

### Guest checkout

- **Type:** need
- **Stakeholders:**
  - Payments team
  - Growth team
- **Description:** Shoppers can pay without creating an account.
  The confirmation page offers to create one afterwards.

### Saved cards

- **Type:** want
- **Stakeholders:** none
- **Description:** Returning shoppers can pay with a saved card.
```

- Title: `# <Project name>` [`title`].
- Fields under the title: **Priority** [`priority`] and **Stakeholders** [`missing-field`].
- Heading `## Requirements` [`heading`]. Each `###` under it is a requirement with fields **Type**, `need` or `want` [`requirement-type`], **Stakeholders** and **Description** [`missing-field`]. A project may have no requirements.
- A need is a requirement the project fails without; a want adds value but can be dropped.

### Actions: `projects/<project>/actions.md`

Example: `projects/checkout-revamp/actions.md`

```markdown
# Actions

## In progress

- Build the guest payment form · P0 · added 2026-09-28

## To do

- Write the rollout plan · ops review · P2 · added 2026-10-05

## Done

- Map the current checkout flow · P1 · added 2026-09-14 · done 2026-09-21
```

- Title: `# Actions` [`title`]. Headings `## In progress`, `## To do`, `## Done`, in that order [`heading`]. A section may be empty.
- Each action is one list item on one line: `- <name> · <priority> · added <date>`, plus ` · done <date>` exactly when it sits under `## Done` [`action-line`]. The separator is a space, a middle dot `·` and a space.
- The line is read from the right: the last two parts (three under `## Done`) are the priority, the added date and the done date, and everything before them is the name, so a name may contain ` · `.
- The priority must be valid [`priority`], both dates real [`date`], and the done date on or after the added date [`done-date`].
- Indented notes under an action and prose paragraphs are allowed. To change an action's status, move its line to the matching section.

### Evidence: `projects/<project>/evidence.md`

Example: `projects/checkout-revamp/evidence.md`

```markdown
# Evidence

## Guest checkout prototype raised completion

- **Date:** 2026-10-08
- **Impact:** In a usability test, 9 of 10 participants finished a guest purchase, up from 6 of 10.
- **Impact status:** measured
- **References:**
  - [Test notes](https://example.com/research/guest-checkout-test)
  - [Prototype](https://example.com/prototypes/guest-checkout)
```

- Title: `# Evidence` [`title`]. Each `##` heading is one piece of evidence, named for what it shows.
- Fields: **Date** [`date`], **Impact** [`missing-field`], **Impact status** [`impact-status`] and **References** [`references`].
- **Impact status** is `delivered` (the work shipped, its impact not yet observed) or `measured` (the impact was observed, usually as a number).
- **References** holds one or more markdown links `[text](url)`, inline and comma-separated or as a nested list, or the single word `none`. A short note may follow a link.

### Status report: `projects/<project>/status-reports/<YYYY-MM-DD>.md`

Example: `projects/checkout-revamp/status-reports/2026-10-09.md`

```markdown
# Status report: Checkout Revamp

- **Share date:** 2026-10-09
- **Time frame:** 2026-09-25 to 2026-10-09

## Done

- Ran a usability test on the guest checkout prototype: 9 of 10 participants finished a purchase.

## Pending

- Build the guest payment form (in progress).
```

- Title: `# Status report: <Project name>` [`title`].
- Fields under the title: **Share date**, equal to the file name's date [`date`, `filename-date`], and **Time frame** [`time-frame`].
- Headings `## Done` then `## Pending` [`heading`], each with at least one list item [`empty-section`]. Write `- None` when there is nothing to list.

### Progress report: `progress-reports/<YYYY-MM-DD>.md`

Example: `progress-reports/2026-10-01.md`

```markdown
# Progress report

- **Share date:** 2026-10-01
- **Time frame:** 2026-09-01 to 2026-09-30

## Checkout Revamp

- **Impact summary:** Support answers checkout questions from one flow map instead of three outdated documents.

### Progress

- Mapped the current checkout flow.
- Published the flow map to the support team.
```

- Title: `# Progress report` [`title`].
- Fields under the title: **Share date**, equal to the file name's date [`date`, `filename-date`], and **Time frame** [`time-frame`].
- One or more `## <Project name>` sections [`heading`]. Each has the field **Impact summary** [`missing-field`] and a `### Progress` heading [`heading`] with at least one list item [`empty-section`].

### Spec: `projects/<project>/specs/<spec>/`

A spec is three files: a brief for readers with no context, the full spec, and an appendix.

Example: `projects/checkout-revamp/specs/guest-checkout/brief.md`

```markdown
# Guest checkout: brief

## The problem

- [First-time shoppers must create an account before paying](spec.md#summary), and many leave at that step.

## The goal

- [More first-time shoppers finish checkout](spec.md#goals), with no rise in fraud.

## The plan

- [Ship a guest payment form, then ramp it to all traffic](spec.md#milestones).

## Not doing

- [No changes to the signed-in checkout](spec.md#non-goals).

## Still open

- [Whether guest orders need an email address](spec.md#open-questions).
```

- Title: `# <Spec name>: brief` [`title`].
- Headings `## The problem`, `## The goal`, `## The plan`, `## Not doing`, `## Still open`, in that order [`heading`], each with at least one list item [`empty-section`].
- Every list item links to the section of `spec.md` it summarizes, as `spec.md#<anchor>`, and the anchor must match a heading in the sibling `spec.md` [`brief-link`]. A bare `- None` item needs no link.

Example: `projects/checkout-revamp/specs/guest-checkout/spec.md`

```markdown
# Guest checkout

## Summary

Let shoppers pay without creating an account, then offer account creation on the confirmation page.

## Goals

- Raise checkout completion for first-time shoppers.
- Keep the fraud rate at or below today's level.

## Non-goals

- Changing the signed-in checkout.

## Milestones

### Milestone 1: payment form

The guest payment form ships behind a flag. Target: 2026-10-30.

### Milestone 2: rollout

Traffic ramps from 5% to 100% over two weeks.

## Risks

- Fraud may rise without account history. Mitigation: a per-card velocity limit.

## Open questions

- Do guest orders need an email address?
```

- Title: `# <Spec name>` [`title`].
- Headings `## Summary`, `## Goals`, `## Non-goals`, `## Milestones`, `## Risks`, `## Open questions`, in that order [`heading`], none of them empty [`empty-section`]. Write `- None` under a section with nothing to say.

Example: `projects/checkout-revamp/specs/guest-checkout/appendix.md`

```markdown
# Guest checkout: appendix

## Usability test script

1. Add any item to the cart.
2. Check out without signing in.
```

- Title: `# <Spec name>: appendix` [`title`]. The body is free-form.

## Checker

Run it from the plugin folder, pointing at a state repo (default: the current folder):

```text
python3 scripts/check.py [<state-repo>]
python3 scripts/check.py --rules
```

- It needs Python 3.9 or later and nothing else.
- It prints one line per defect, sorted by path then line: `<path>:<line>: <rule id>: <detail>`, for example ``projects/checkout-revamp/actions.md:5: priority: priority must be P0, P1, P2 or P3, not `P4` ``.
- A defect names the line it sits on. A missing field or heading names the line of the heading it belongs under (the title, for file-level items). A missing file, a bad file or folder name, and a missing title name line 1.
- Exit codes: `0` when every file it knows is valid, `1` when it finds a defect, `2` when the folder has no `.devos` or its first line is not `format: 1` (printed as a `.devos:1: marker:` line), the path is not a folder, or a file it knows cannot be read (a `<path>: cannot read: <reason>` message on stderr).
- `--rules` prints every rule id, one per line.

## Rule ids

- `marker`: `.devos` is missing or its first line is not `format: 1` (exit `2`), or a later line is not a `remote: <url>` line, has no URL, or repeats a URL (exit `1`).
- `missing-file`: a project folder has no `project.md`, or a spec folder lacks `brief.md`, `spec.md` or `appendix.md`.
- `slug`: a project or spec folder name is not a lowercase hyphenated slug.
- `filename-date`: a report file is not named `<YYYY-MM-DD>.md`, or its **Share date** differs from its name.
- `title`: the `#` title line is missing, misplaced, wrongly worded or repeated.
- `heading`: a required heading is missing, duplicated or out of order, or a record heading has no name.
- `missing-field`: a required field is absent or empty.
- `priority`: a priority is not `P0`, `P1`, `P2` or `P3`.
- `date`: a date is not a real `YYYY-MM-DD` date.
- `time-frame`: a time frame is not `<date> to <date>`, or it starts after it ends.
- `requirement-type`: a requirement's **Type** is not `need` or `want`.
- `action-line`: a list item in an action section is not a valid action line.
- `done-date`: an action's done date is before its added date.
- `impact-status`: **Impact status** is not `delivered` or `measured`.
- `references`: **References** is neither `none` nor markdown links.
- `brief-link`: a brief item does not link to `spec.md#<anchor>`, or the anchor matches no heading in `spec.md`.
- `empty-section`: a section that needs content has none.
