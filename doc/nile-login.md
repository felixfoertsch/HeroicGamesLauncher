# Amazon / Nile login recovery

This change fixes specific failure paths in Heroic's account-login integration.
It does not change the Amazon storefront's cookies, bypass MFA, or modify Nile's
Amazon API implementation.

## Failure paths

- Nile refuses `auth --login` when it already has a session. Previously Heroic
  parsed the resulting empty stdout as JSON, and the UI never caught the failure.
- Heroic relied on its own cached profile to decide whether to load Nile's
  library. A valid CLI session could exist in Heroic's `NILE_CONFIG_PATH` while
  that cache was empty. Session checks now re-read the local profile first.
- Nile 1.2 uses `current_user.json`; older versions use nested customer data in
  `user.json`. Both formats are read, copying only the public name and user ID.
  An existing current-format file takes precedence over any legacy file.
- Amazon can redirect away from its authorization callback before `dom-ready`.
  Main-frame navigation/redirect events now supply the callback URL. Duplicate
  events cannot submit the same authorization code twice.
- Failed registration previously navigated to the account page as if successful.
  It now displays an error with a fresh-attempt retry. Preparation also has a
  30-second timeout, and results from abandoned attempts are ignored.

Existing local sessions are reused, not logged out or deleted. Recovery reloads
Heroic's renderer once to synchronize its cached account state. As with Nile's
own session check, finding a local profile does not prove a token is still valid
on Amazon's servers; library sync/launch remains responsible for token refresh.

## Validation

Regression tests are in `src/backend/storeManagers/nile/__tests__/` and use the
existing Backend Jest project. They cover account restoration, both profile
formats, damaged/missing profiles, preparation failures, helper arguments,
registration failure handling, public-data filtering and callback validation.

```sh
pnpm codecheck
pnpm test --runInBand
pnpm lint
pnpm prettier
```

A live Amazon sign-in cannot be verified by these mocked tests. On Linux, test:

1. With no Amazon session, use **Manage Accounts > Amazon > Login**, complete
   Amazon's password/MFA screens, and confirm the account and library appear.
2. Restart Heroic and confirm that the account remains available. A pre-existing
   CLI login must use Heroic's configured `NILE_CONFIG_PATH`, not a separate
   system-wide Nile directory.
3. Cancel/navigate away during preparation; no late response should redirect
   you back. A missing/broken helper should show an error instead of spinning
   indefinitely; Retry must start a fresh attempt.
4. After an unsuccessful registration, confirm no false-success navigation.
   Retry, log in, then verify Epic/GOG login and normal launch/install still work.

Do not post passwords, authorization callback URLs, authentication tokens or
raw Nile credential files in bug reports.
