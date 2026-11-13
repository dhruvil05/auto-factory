<!-- Profile for internal admin/backoffice web apps. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Product name]: internal backoffice for [company] staff (never the public) to manage [customers, orders, invoices].

### Users and roles
- Admin: everything, including users, roles and settings.
- Manager: read and write within own [company/branch]; approves [refunds, invoices].
- Staff: read and write own records within own [company/branch]; no settings.
- Viewer: read only; no exports.

### Sensitive areas
Always goes to a human:
- Money: invoices, payments, refunds, prices, tax, rounding.
- Roles, permissions and who can grant them.
- Tenant/company scoping (any query that could cross companies).
- Deleting or bulk-changing records.
- Data exports and anything that leaves the system (email, files, webhooks).
- Audit log writes and retention.

### Authorization
- Permission checks: [policy classes in app/Policies] and [route middleware].
- Every list, detail, export and bulk action checks role AND company scope on the server; hiding a button is never the check.
- Verify by: [test that calls the endpoint as Viewer and as another company's user and expects 403/404].

### Data rules
- Every tenant table has [company_id]; every query filters by the signed-in user's company.
- Changes to money, roles and deletions write an audit row: who, what, before/after, when.
- Money: [integer cents / decimal(12,2)], currency stored per row, round [half-up] once at the end.
- Deletes are soft ([deleted_at]); hard deletes only by admin with audit.
- Migrations: [tool]; additive and reversible; backfill in a separate step.
- Bulk actions: confirm count first, run in a transaction or job, audited per record.

### UI conventions
- Components: [component library, path]; tables with sort, filter, pagination; theme: [tokens path].
- Destructive actions use a confirm dialog naming the record and count.

### Verify
- Run: [dev server command] at [http://localhost:{PORT}].
- Sign in as: seeded users per role from factory/seed-users.json.

### Terms
- [Company]: [the tenant; every record belongs to one]
- [Term]: [meaning]
