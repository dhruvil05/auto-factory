<!-- Blank profile for any kind of project. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Product in 1-3 lines: what it does and who uses it]

### Users and roles
- [Role]: [what it may see and do]
- [Role]: [what it may see and do]
- [Or write `None` if there are no users or roles]

### Sensitive areas
Always goes to a human:
- [Area that must never ship without a person approving, e.g. money, deletion]
- [Another area]

### Authorization
- Access checks live in: [middleware, policies, guards, with paths]
- Verify by: [how to prove a role is blocked, e.g. a test or a request as that role]
- [Or write `None` if there are no access rules]

### Data rules
- Scoping: [how records are scoped to a tenant/user, or none]
- Migrations: [tool and rules, e.g. additive only, no data loss]
- Audit: [what gets logged and where]
- [Or write `None` if the project stores no data]

### UI conventions
- Design system: [library or in-house components, with path]
- Theme/tokens: [where colors, spacing and fonts live]
- [Or write `No UI`]

### Verify
- Run: [command that starts the app or runs the checks]
- Sign in as: [seeded users per role, or none]
- Look at: [where the change shows up]

### Terms
- [Term]: [meaning in this project]
