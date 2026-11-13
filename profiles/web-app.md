<!-- Profile for customer-facing SaaS/web apps. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Product name]: [what it does] for [who pays for it].
- Public site plus a signed-in app; users sign up themselves.

### Users and roles
- Visitor: public pages, sign up, sign in.
- Member: own data inside own [workspace/account].
- Owner: members, plan and billing of own [workspace].
- [Support/Admin]: [internal tools; read-only on customer data unless stated].

### Sensitive areas
Always goes to a human:
- Billing: plans, prices, checkout, refunds, trials, [payment provider] webhooks.
- Sign-up, sign-in, password reset, sessions, OAuth.
- Access to another user's or workspace's data.
- Account or data deletion.
- Emails sent to customers.
- Privacy: tracking, cookies, consent, personal data.

### Authorization
- Checks: [middleware/guards path]; every request scoped to the signed-in user's [workspace].
- Plan limits enforced on the server in [path].
- Verify by: [test requesting another workspace's record and expecting 404].

### Data rules
- Every customer table has [workspace_id]; queries always filter by it.
- Money: [integer cents], amounts come from [payment provider]; never trust client prices.
- Migrations: [tool]; additive, zero-downtime, reversible.
- Personal data: [where it lives]; deletion requests via [process].

### UI conventions
- Components: [library, path]; theme/tokens: [path].
- Every new page: loading, empty and error states; works at phone width.
- Public pages: title and meta description; [SEO rules only if relevant].

### Verify
- Run: [dev server command] at [http://localhost:{PORT}].
- Sign in as: seeded users from factory/seed-users.json ([member, owner]).
- Payments: [provider] test mode only.

### Terms
- [Workspace]: [the account a customer pays for]
