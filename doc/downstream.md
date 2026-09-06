# Felix's downstream Heroic builds

This fork carries a **linear Git patch series** on `main`. There is no maintained
feature-selection manifest. The **Downstream Heroic** workflow builds `main`, or
replays that same series onto a newer stable upstream release before building.
A rejected or closed upstream PR never removes a downstream patch.

## Branches and releases

- `main`: combined customized application. Initially stacking, Nile recovery,
  then downstream automation/packaging.
- `downstream-base`: upstream commit below the local patch series. The updater
  promotes this ref and `main` atomically, only after validation and packaging.
- `downstream-published`: source of the most recently completed publication.
  An unsuccessful publication leaves this marker unchanged for automatic retry.
- `upstream-base`: frozen review baseline for the existing independent draft
  PRs. It is intentionally not moved by the updater.
- `feat/stack-game-copies` and `fix/nile-amazon-login`: independent single-commit
  contribution branches. Automation neither edits these branches nor submits,
  merges, closes, or marks their PRs ready for review.
- `downstream-status`: metadata-only health snapshot, updated at least daily
  while checks run (also keeping repository activity separate from patch history).
- `build/downstream-preview`: non-publishing validation branch, not a package
  channel. Pushes here exercise the complete build without changing `main`.

The first CalVer run replays our local series from the initial development
baseline `e95e407a` onto the actual stable `v2.22.1` commit `2cc01fe4`. This
one-time, exactly pinned bootstrap removes seven unrelated development commits
and is fully validated before promotion. After that, only forward stable
upstream releases are adopted; arbitrary rewinds and divergent histories stop.

Checks run at 00:23, 06:23, 12:23 and 18:23 UTC, on pushes to `main`, and with
**Actions > Downstream Heroic > Run workflow** on `main`. A scheduled no-change
check skips packaging when the current source was already published. A manual
run rebuilds it, including after signing setup. GitHub may delay scheduled jobs;
check Actions and the health snapshot rather than assuming a hard deadline.

## Validation and failure behavior

A temporary detached checkout receives the commits after `downstream-base`, in
order. Only exact ancestry or Git patch-equivalence evidence permits a patch to
be skipped as already upstream; this is recorded in generated `build-info.json`.
Other empty patches, conflicts, merge commits in the local series, and failed
checks stop the pipeline. No automatic ours/theirs conflict overrides are used.

The pipeline runs real-Git regression tests, full Heroic TypeScript/Jest/ESLint/
Prettier checks, Linux x64 AppImage and tar.xz builds, native Arch packaging, and
a real signed-repository pacman download test using a disposable, unpublished key.
Passing these checks is not proof of all interactive behavior or live Amazon MFA.

The publisher verifies the complete artifact checksum list. It uses explicit
expected-SHA leases and one atomic push for `main`, `downstream-base`, the new
release tag and a backup tag. Work pushed during testing is not overwritten.
Build/signing failure leaves the previous working release and baseline intact.
Publication failure can leave a validated promoted `main` and/or an unpublished
draft release; the unchanged publication marker causes the next check to retry.
A failure issue is maintained when repository issues are enabled.

Each immutable release includes exact source, generated provenance, checksums,
AppImage/archive and the fork-specific updater configuration. Once signing is
configured, it also includes the signed pacman package and repository database.
Releases are marked as normal releases **of this unofficial fork**, never as
upstream Heroic releases. Existing release tags and assets are not overwritten.
The separate `pacman` prerelease is a rolling package index, not an app release.

## CalVer versions and AppImage updates

Public release tags preserve the upstream tag and use Europe/Berlin dates:

```text
v2.22.1-2026.09.06.1
v2.22.1-2026.09.06.2
v2.22.2-2026.09.07.1
```

`n` starts at 1 per upstream-tag/date pair and is one above the highest existing
remote tag in that pair. A failed publication may reserve a number; gaps are
allowed, but versioned tags and assets are never overwritten. Build runs remain
serialized. The date is determined when a candidate is prepared.

Electron requires valid SemVer, so its internal version is
`2.22.1-2026.9.6.1` (numeric prerelease identifiers cannot have leading zeros).
Pacman uses `2.22.1_2026.09.06.1-1` because pkgver cannot contain a hyphen; the
last `-1` is the Arch package release. Public release tags and archive filenames
retain the requested padded CalVer spelling. Generated `build-info.json` records
all forms; it is not a feature-selection manifest.

Install the first CalVer AppImage manually when switching from the earlier
`2.22.1-felix.<run-id>.<attempt>` scheme: those versions do not sort before the
new numeric prerelease under SemVer. New AppImages use a generic feed at
`https://github.com/felixfoertsch/HeroicGamesLauncher/releases/download/downstream-feed`.
Its `latest-linux.yml` names an exact versioned AppImage and its SHA512 hash. It
is updated only after the complete CalVer release is public. This avoids trying
to parse padded public tags as SemVer and never selects official unpatched
Heroic releases. Heroic still prompts before installing updates.

`downstream-feed` and `pacman` are rolling metadata releases, not application
versions. Neither replaces immutable CalVer releases. Source archives contain
the exact tagged source; the separate `packaging.json` and build information
record the generated version/feed settings used by electron-builder.

## One-time package signing setup

The build job has read-only access and receives no long-lived signing secret.
Only the isolated publisher receives the dedicated repository signing key.
Without a key, AppImage/archive publication works, but the pacman feed is **not**
published unsigned. The unsigned Arch package remains only in the CI artifact.

Create a dedicated signing-only key on your own computer (do not use a personal
mail/signing master key). Keep a secure backup and plan renewal before expiry:

```sh
gpg --quick-generate-key 'Heroic Felix repository signing' ed25519 sign 2y
gpg --list-secret-keys --with-fingerprint
bash .github/downstream/setup-signing.sh YOUR_FULL_PRIMARY_FINGERPRINT
```

The helper requires an authenticated GitHub CLI with permission to manage this
repository's Actions secrets and variables. It verifies signing first, then sets
`PACMAN_SIGNING_KEY`, `PACMAN_SIGNING_PASSPHRASE`, and the public variable
`PACMAN_SIGNING_FINGERPRINT`. Secret key bytes are never committed or published.
Run **Downstream Heroic** manually on `main` afterward. A fingerprint change stops
publication until you deliberately handle key rotation and client trust.

Normal operation uses the workflow's `GITHUB_TOKEN`. Branch protection and GitHub
workflow-file permissions may prevent automatic promotion. If GitHub rejects a
future update because upstream changed workflow files, configure a narrowly
scoped `DOWNSTREAM_PUSH_TOKEN` secret with Contents and Workflows write access
for **this fork only**. Do not weaken branch protections or grant upstream access.
Such a token can trigger other workflows on pushes; review/disable inherited
upstream release automation before enabling it. The pipeline itself does not
rely on a second push-triggered run: it builds and publishes in the same run.

## Add the signed source on CachyOS / Arch Linux

After the first **signed** publication, download the public key and compare its
full fingerprint with the one printed by your local signing setup:

```sh
curl --fail --location --output heroic-felix-key.asc \
  https://github.com/felixfoertsch/HeroicGamesLauncher/releases/download/pacman/heroic-felix-key.asc
gpg --show-keys --with-fingerprint heroic-felix-key.asc
# Only after verifying the fingerprint:
sudo pacman-key --add heroic-felix-key.asc
sudo pacman-key --lsign-key YOUR_FULL_PRIMARY_FINGERPRINT
```

Add to `/etc/pacman.conf`:

```ini
[heroic-felix]
SigLevel = Required DatabaseRequired
Server = https://github.com/felixfoertsch/HeroicGamesLauncher/releases/download/pacman
```

Then install with a complete system upgrade:

```sh
sudo pacman -Syu heroic-felix
```

The package conflicts with standard native Heroic packages because it installs
the same executable and uses the same configuration. Back up that configuration
before switching. It does not uninstall an existing Flatpak; avoid running both
copies simultaneously. Future `pacman -Syu` operations update the custom package.
This configures an update source, not unattended installation on your machines.

Old versioned packages remain on the rolling feed so an older database can still
fetch them. GitHub asset replacement is not transactional: during the short
index/signature switch a client may get a signature error. Retry later; **never**
disable signature checks. Storage grows as versions accumulate; prune old package
assets only deliberately, after clients have moved to newer database versions.

## Add or adapt a change

Create an independent contribution branch from a suitable clean upstream base,
then cherry-pick its completed commit into `main`. Alternatively develop linearly
on `main` and extract an independent contribution later. Changes to contribution
branches do not enter your builds until explicitly applied to `main`. A dependent
patch needs its prerequisites both downstream and in an upstream contribution.

When upstream changes conflict, reproduce the recorded baseline/target locally,
adapt the relevant patch, and run the checks before promoting the repaired series.
Moving `main` and `downstream-base` must use a single atomic, lease-guarded push;
never move only the baseline. The Python regression tests contain a minimal example.
No automated decision is based on whether a PR is accepted, rejected, or AI-assisted.

Because release updates rewrite the downstream commits, do not blindly pull into
a working checkout. First fetch, preserve local work on a branch, then reset only
a clean disposable checkout to `origin/main`. Published release tags and
`downstream-backup/<run-id>.<attempt>` retain recovery points.

The prior `.github/custom-build.json` / assembly workflow is superseded. Runtime
helpers and toolchain requirements can still change upstream; failures remain
visible and require maintenance rather than shipping an untested fallback.

Implementation and documentation: **Astra (OpenAI AI assistant)**, directed by
Felix Förtsch. Human smoke-test reports and automated checks are recorded separately.
