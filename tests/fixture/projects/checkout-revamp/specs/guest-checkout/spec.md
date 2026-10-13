# Guest checkout

## Summary

Let shoppers pay without creating an account, then offer account creation on the confirmation page.

## Goals

- Raise checkout completion for first-time shoppers.
- Keep the fraud rate at or below today's level.

## Non-goals

- Changing the signed-in checkout.
- Saving cards for guests.

## Milestones

### Milestone 1: payment form

The guest payment form ships behind a flag and is tested by staff. Target: 2026-10-30.

### Milestone 2: rollout

Traffic ramps from 5% to 100% over two weeks while we watch fraud and completion rates.

## Risks

- Fraud may rise without account history. Mitigation: keep the current fraud checks and add a per-card velocity limit.

## Open questions

- Do guest orders need an email address, or is a phone number enough?
