# Brief cold read

These rules grade a spec brief (`brief.md`) the way a reader with no context sees it: someone outside the project who reads only the brief and never opens `spec.md`. Each list item links to a section of `spec.md`. The link may add detail, but the item must make sense without it.

Under these rules, a missing actor, an unexplained term or an item that needs its link is a break of the rule it falls under. It is never a gap, and it costs points like any other break. List it under breaks and quote the item.

## The problem names who is affected and what goes wrong

The first item under `## The problem` names who is affected, as a group of people a stranger would recognize, and what goes wrong for them, in plain words. A first problem item that does not name who is affected breaks this rule; it is not a gap. So does a first item that gives a codename, a symptom or a metric in place of what goes wrong.

## Terms are explained or absent

Every project term, codename, internal team name and acronym in the brief is explained where it first appears, or left out. A reader outside the project must understand each item without asking what a word means. Each such term that the brief uses without explaining breaks this rule once; it is not a gap. Everyday abbreviations that most adults know, such as "PDF" or "FAQ", and product names introduced with what they are, such as "accounting software such as Xero", need no explaining.

## Each point stands without its link

Each item is a full claim that a stranger can understand from the brief alone. An item that only makes sense after opening its link breaks this rule; it is not a gap. Breaks include "as described in the spec", "hit the target" with no target named, "M1, then M2", "the sync work", and a "this" or "it" with nothing before it to point to.

## Open items are questions, and Not doing names real exclusions

Each item under `## Still open` reads as a question nobody has answered yet, such as "Should refunds appear as their own rows?". An item phrased as a task or a to-do, such as "Confirm X with Dana" or "Write up Y", breaks this rule; it is not a gap. Each item under `## Not doing` names a specific thing the team chose to leave out that a reader could have expected in scope. A vague item, such as "the sync work", or a negated goal, such as "the export will not crash", breaks this rule; it is not a gap. A bare `- None` under either heading follows the rule.
