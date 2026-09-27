# Hiring subscription catalog

Owner pricing lives inside the existing hiring owner-access screen. Only the verified owner account may read, draft, or publish prices. Workspace admins may choose a published subscription; they cannot set their own price or entitlement.

## Initial recommendation (USD)

| Plan | Monthly | Annual total | Seats | Open roles | API requests per calendar month |
| --- | ---: | ---: | ---: | ---: | ---: |
| Team | $99 | $990 | 5 | 5 | No new API entitlement |
| Integration | $299 | $2,990 | 15 | 25 | 1,000 |

These defaults are starting commercial recommendations, not validated willingness to pay or a capacity guarantee. The owner can edit price, billing interval, seats, roles, and API allowance before saving a draft. API usage is measured separately in the live and test environments; manual applications do not consume this API allowance. Existing included-access rights must be preserved explicitly before enabling billing.

Members and pending invitations count toward the seat allowance. Permission roles remain separate from seat limits. Reaching a limit blocks new capacity use; it does not delete existing company data. There are no automatic overage charges. Annual billing is paid for the full year; the API allowance still resets each calendar month.

## Price versions

Drafts do not grant access or charge anyone. Publishing creates a Stripe price and changes the version offered to new subscribers. Existing subscription prices and their limits remain readable after replacement. Checkout submits the displayed version ID; the server rejects a stale selection instead of silently charging a different amount. A published historical price cannot be edited or reactivated; create a new draft.

Provider calls have bounded timeouts and stable idempotency keys. Publication uses a per-plan, per-interval database lock after the provider operation and rejects competing stale drafts. Publishing does not enable billing. Existing server-verified Stripe webhook reconciliation remains the subscription authority.

## Rollout requirements

1. Apply migration 029 to staging first and verify repeated execution is safe.
2. Configure the existing staging Stripe test-key reference securely. Exercise draft publication, checkout, signed webhook replay, cancellation and renewal with test-mode objects.
3. Verify price/seat/API enforcement and preservation of historical subscriber limits.
4. Before changing included-access configuration, mark the existing authorized included workspaces for retained access and record the affected count privately. Do not grant it to future workspaces by default.
5. Configure production live-mode Stripe credentials and the existing billing webhook through secret references. Never commit keys. Keep BUSINESS_BILLING_ENABLED=0 until acceptance is complete.
6. Publish the reviewed owner prices and verify the exact displayed price, currency, interval and entitlement in a controlled checkout before opening public subscriptions.

No production readiness or latency guarantee follows from catalog implementation alone. Live applicant, invitation, download, embedding and webhook acceptance remain independent release requirements.

## Research basis

Reviewed September 26, 2026. TestGorilla separates assessment tiers and reserves API/ATS integrations for higher plans; Breezy offers collaborative hiring with unlimited users and an annual discount. These support simple bundled collaboration and a higher integration tier, but do not prove CookCredit demand or justify unlimited infrastructure consumption.

- https://www.testgorilla.com/pricing/
- https://marketing.breezy.hr/pricing
- https://docs.stripe.com/products-prices/manage-prices
