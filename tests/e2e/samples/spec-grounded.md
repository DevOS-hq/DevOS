# Invoice export

## Summary

Finance staff at our customers copy invoices out of the billing page by hand at month end. One accountant spends two days on it every month, and copy mistakes reach the ledger. An admin will download a month of invoices as one CSV file, and later receive that file by email each month.

## Goals

- Let an admin download a month of invoices as one CSV file.
- Cut month-end support tickets about invoices by half.

## Non-goals

- A direct sync with accounting tools such as QuickBooks or Xero.

## Milestones

### Milestone 1: CSV download

The billing page offers a CSV download of one month's invoices. Target: 2026-12-04.

### Milestone 2: scheduled export

On the first of each month, an export emails the file to an admin.

## Risks

- Large accounts have tens of thousands of invoices a month, so the download may time out. Mitigation: build the file in a background job and email a link when it is ready.

## Open questions

- Should refunds appear as separate rows?
