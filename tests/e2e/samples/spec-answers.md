# Answers: Invoice export

A user's answers to the create-spec interview. judge.py --calibrate checks the milestones of spec-grounded.md and spec-invented.md against this text.

Problem: finance staff at our customers copy invoices out of the billing page by hand at month end. One customer's accountant told us it takes her two days every month, and copy mistakes end up in their ledger.

Goals: let an admin download a month of invoices as one CSV file, and cut month-end support tickets about invoices by half.

Not doing: no direct sync with accounting tools such as QuickBooks or Xero.

Milestones: first, a CSV download of one month's invoices from the billing page, target 2026-12-04. Second, a scheduled export that emails the file to an admin on the first of each month, no date yet.

Risk: large accounts have tens of thousands of invoices a month, so the download may time out. Mitigation: build the file in a background job and email a link when it is ready.

Unknown: I don't know yet whether refunds should appear as separate rows.

Supporting material: the support tag `invoice-export` collects the requests so far.
