<!-- Profile for HTTP/JSON APIs and backend services. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Service name]: HTTP/JSON API that [does what] for [which clients].
- Consumers: [internal services, partner apps, public developers].

### Users and roles
- Client: calls the API with [API key / OAuth token]; sees only own [account] data.
- [Scope or role]: [what it allows, e.g. read:orders, write:orders].
- Admin: [internal endpoints only, under /admin].

### Sensitive areas
Always goes to a human:
- Authentication: tokens, keys, signing, expiry, revocation.
- Breaking changes to any published endpoint, field or error code.
- Money or irreversible side effects (charges, transfers, deletes).
- Rate limits and quotas.
- Data shared with or received from third parties (webhooks, callbacks).
- Secrets and config handling.

### Authorization
- Checks: [auth middleware path] for identity; [scope/policy check path] per endpoint.
- Every endpoint declares its required scope; default is deny.
- Verify by: [test calling the endpoint without a token, with a wrong scope and with another account's id].

### Data rules
- Versioning: [/v1 path prefix]; never remove or rename fields in a version, only add.
- Writes accept an [Idempotency-Key] header; replays return the first result.
- Errors: [JSON shape, e.g. {"error": {"code", "message"}}] with stable codes.
- Rate limits: [limit] per [key/minute]; 429 with Retry-After.
- Migrations: [tool]; additive, safe with old and new code running together.

### UI conventions
No UI

### Verify
- Run: [server command] on port {PORT}; [test command].
- Call: [curl/httpie example with a seeded test key from fixtures path].

### Terms
- [Account]: [who owns the data a key can see]
