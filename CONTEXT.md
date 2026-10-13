# DevOS

An operating base for a software engineer's project work: projects, actions, evidence of impact, reports and specs, kept as markdown in a git repository the engineer owns.

## Language

### Where records live

**State repo**:
A git repository holding one person's DevOS records as markdown. A person may keep several, one per body of work.
_Avoid_: workspace, vault, state set

### Projects

**Project**:
A body of work with a priority, stakeholders and requirements. Every record except a progress report belongs to exactly one project.
_Avoid_: initiative, epic

**Requirement**:
A named outcome a project must deliver, marked need or want, with its own stakeholders and description.
_Avoid_: feature, story

**Need**:
A requirement the project fails without.
_Avoid_: must-have, P0 requirement

**Want**:
A requirement that adds value but can be dropped without failing the project.
_Avoid_: nice-to-have, stretch

**Stakeholder**:
A person or group with a say in, or a stake in, a project or requirement.
_Avoid_: owner, customer

**Priority**:
P0 to P3, where P0 is urgent. Applies to projects and actions.

### Work and impact

**Action**:
A unit of work on a project with a status (to do, in progress, done), a priority, the date it was added and, once done, the date it was done.
_Avoid_: task, todo, ticket

**Evidence**:
A dated record of impact on a project, with links where they exist, kept to support performance reviews. Its impact is either delivered or measured.
_Avoid_: win, accomplishment, brag

**Delivered**:
Evidence whose work has shipped but whose impact has not yet been observed.

**Measured**:
Evidence whose impact has been observed, usually with a number.

### Reports

**Status report**:
A dated update on one project covering a time frame: what got done and what is pending.
_Avoid_: update, weekly

**Progress report**:
A dated report across all projects covering a time frame, giving each project an impact summary and a progress list.
_Avoid_: performance review, self-review

**Share date**:
The date a report goes to its audience.

**Time frame**:
The date range a report covers.

### Specs

**Spec**:
A project's design document, made of a brief, a full spec and an appendix.
_Avoid_: PRD, design doc, RFC

**Brief**:
The short form of a spec for a reader with no context: the problem, the goal, the plan, what is not being done, and what is still open. Each point links to the full spec.
_Avoid_: summary, TL;DR

**Full spec**:
The complete spec: summary, goals, non-goals, milestones, risks and open questions.
