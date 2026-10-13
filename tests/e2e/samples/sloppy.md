# Checkout Revamp — Q4 Design Update

Let's dive into where the checkout revamp stands. In today's fast-paced e-commerce landscape, the checkout flow serves as the bedrock of our revenue, and this update is a testament to the team's meticulous work as we head toward the November 16 launch.

## Overview

This is not just a refactor, it's a paradigm shift. The new payment service boasts a vibrant retry model, highlighting our commitment to quality. We chose to leverage the existing job queue in order to facilitate retries, so a failed charge is now retried three times over ten minutes before the shopper sees an error, giving us a “single source of truth” for retries and/or fallbacks.

## Progress

- We delved into the intricate interplay between the cart, the tax engine, the address form, etc., and tax lookups will stay in the cart service for this release.
- Guest checkout went live for 5% of shoppers on October 6 and garnered strong results, underscoring the pivotal role of fewer form fields: completed orders rose from 61% to 66% of started checkouts in the first week.
- Dana Ruiz simply cut the address form from eleven fields to seven.
- Experts say that one-page checkouts convert better, and industry reports agree. Our own two-week test of a two-page layout produced fewer completed orders in both weeks, so we are keeping one page.

## Risks

It is important to note that, as of my last review, the fraud model has not been retrained since June, before guest checkout existed. If guest orders show a higher fraud rate, the risk team could potentially pause the rollout; Priya Shah owns this check and reports on it each Monday. Based on available information, the vendor may possibly fix duplicate webhooks someday, but it has no release date. Some critics argue the payment service is exposed – but it already ignores any webhook it has processed.

## Next steps

Priya will quickly bolster the fraud model by retraining it on October data by October 24, fostering a culture of quality. The payments team will add tests for the retry path by October 20. Reliability is our north star -- and the flywheel for our growth, so Dana will raise guest checkout to 25% of shoppers once the retrained model is live.

Exciting times ahead! The future looks bright, and this is a step in the right direction. 🚀

Great question, everyone. Of course! I hope this helps, and please let me know if you have any questions.
