<!-- Profile for reusable packages/SDKs. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Package name]: [language] library that [does what] for [which developers].
- Published to [npm/PyPI/crates.io/Maven] as [package id].

### Users and roles
None

### Sensitive areas
Always goes to a human:
- Any change to the public API (exports, signatures, defaults, error types).
- Version bumps and release notes.
- New runtime dependencies or raised minimum [language/runtime] version.
- License or package metadata changes.
- Code that touches the network, filesystem, crypto or user secrets.

### Authorization
None

### Data rules
None

### UI conventions
No UI

### Verify
- Run: [test command]; [lint/type-check command].
- Public API lives in: [src/index or __init__ path]; anything else is internal.
- Semver: breaking change = major, new feature = minor, fix = patch.
- Every public change updates [README/docs path], [CHANGELOG.md] and an example in [examples/].
- Deprecate before removing: keep it working with a warning for [one minor release].

### Terms
- [Term]: [meaning in this library]
