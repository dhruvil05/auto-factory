<!-- Profile for iOS/Android/cross-platform mobile apps. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [App name]: [iOS/Android/both] app built with [Swift/Kotlin/React Native/Flutter] that [does what] for [who].
- Backend: [API name/URL]; this repo is [the app only / app and API].

### Users and roles
- Guest: [what works without an account].
- Member: own data, synced across devices.
- [Other role]: [what it may do].

### Sensitive areas
Always goes to a human:
- Permission prompts (camera, location, contacts, notifications, tracking).
- In-app purchases, subscriptions, prices.
- Sign-in, tokens and anything in the keychain/keystore.
- Offline sync and conflict handling (risk of losing user data).
- Local database migrations.
- Anything that could fail store review (privacy labels, required disclosures).

### Authorization
- Checks: enforced by the API at [path/service]; the app only hides what the API refuses.
- Tokens stored in: [Keychain/EncryptedSharedPreferences], never plain storage.
- Verify by: [test or request showing the API rejects another user's data].

### Data rules
- Local store: [SQLite/Realm/Core Data]; migrations in [path], never drop user data.
- Offline: writes queue locally and sync later; [last-write-wins / server-wins] on conflict.
- Every API change stays compatible with app versions still in use ([N] versions back).

### UI conventions
- Components: [design system path]; theme/tokens: [path].
- Platform patterns: [native navigation per platform / shared].
- Accessibility: labels on all controls, dynamic type, 44pt minimum touch targets.
- Every screen: loading, empty, error and offline states.

### Verify
- Run: [simulator/emulator command]; [test command].
- Sign in as: seeded users from factory/seed-users.json.

### Terms
- [Term]: [meaning in this app]
