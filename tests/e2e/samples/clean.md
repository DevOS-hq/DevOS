# Checkout revamp: October design update

The checkout revamp is on track for the 2026-11-16 launch. The payment service now retries failed charges, and guest checkout is live for 5% of shoppers. One risk is open: the fraud model has not been retrained since June.

## What shipped

- The payments team moved charge retries onto the existing job queue. A failed charge now retries three times over ten minutes before the shopper sees an error.
- Guest checkout went live for 5% of shoppers on 2026-10-06. In that group, the share of started checkouts that end in an order rose from 61% to 66% in the first week.
- Dana Ruiz cut the address form from eleven fields to seven.

## Decisions

- We keep the one-page layout. The two-page version had fewer completed orders in both weeks of the test.
- Tax lookups stay in the cart service for this release. Moving them would double the migration work and would not change what the shopper sees.

## Risks

- The fraud model was last trained in June, before guest checkout existed. If guest orders show a higher fraud rate, the risk team pauses the rollout. Priya Shah owns this check and reports on it each Monday.
- The vendor has no release date for its fix to duplicate webhooks. Until the fix ships, the payment service ignores any webhook it has already processed.

## Next steps

1. Priya Shah retrains the fraud model on October data by 2026-10-24.
2. The payments team adds tests for the retry path by 2026-10-20.
3. Dana Ruiz raises guest checkout to 25% of shoppers after the retrained model is live.

Send questions to the checkout-revamp channel.
