# Felix downstream Heroic

This fork tracks stable upstream Heroic releases while carrying a linear series
of local changes. AI-assisted implementation by Astra (OpenAI), directed by Felix
Förtsch. Upstream review or acceptance of those changes does not control whether
the fork carries them.

## Branches and contributions

- `main`: upstream release plus the downstream commits, in order.
- `downstream-base`: the exact upstream commit below that local series. It is
  advanced atomically with a successfully validated update of `main`.
- `upstream-base`: a separate, deliberately unchanged review baseline for the
  existing draft PRs inside this fork.
- `feat/stack-game-copies` and `fix/nile-amazon-login`: the independent one-commit
  contributions. Automation never moves them, requests reviews, or opens an
  upstream PR. Their AI disclosures remain in place.

There is no feature-selection manifest. To include another change, apply its
commit to `main` without a merge commit. Future upstream updates replay every
commit after `downstream-base`, including the downstream build infrastructure.
A commit that is already upstream by ancestry or exact Git patch equivalence is
recorded as such. Conflicts and unexpectedly empty patches stop; a differently
implemented upstream fix is not automatically considered equivalent.

The bootstrap baseline is the previously tested development commit `e95e407a`.
The first production run replays the local changes onto the actual latest stable
release, not onto the current upstream development branch.

## Automation and publication

`Maintain downstream Heroic` runs on pushes to `main`, every six hours at minute
23 (UTC), and through Actions > Run workflow. `build/downstream` is a preview
branch: its candidate is checked and packaged, but never published or promoted.
A manual run defaults to a forced rebuild; scheduled unchanged-source checks do
not create another release.

The workflow resolves upstream's latest non-draft, non-prerelease version tag,
pins its commit, and replays the local series in a disposable worktree. It runs
real-Git automation tests, the full application type check, Jest, ESLint,
Prettier, Electron packaging, and pacman package/version inspection. Only then
can a separate publishing job sign packages and promote the candidate.

Promotion uses one atomic Git push with explicit expected-old-SHA leases for
both `main` and `downstream-base`. A concurrent edit prevents the entire push.
The former main is preserved under `downstream-history/<full-old-sha>`; release
tags are never force-updated. The workflow builds and publishes in the same run,
so it does not depend on a bot push triggering a second workflow.

An upstream compatibility failure leaves the previous main/release intact. A
publication failure may occur after source promotion; it does not replace the
last working update feed with an unbuilt or partly uploaded application. The
workflow retains diagnostics and creates/updates a single failure issue when
Issues is enabled. GitHub Actions failure notifications work independently.
A partial upload can leave a draft release or reserve a version number; rebuild
with Run workflow rather than overwriting that tag.

GitHub schedules are best-effort and public-repository schedules can be disabled
after 60 days of repository inactivity. Check the Actions page periodically;
re-enable the schedule there when necessary. This is not an instant upstream
webhook and does not promise maintenance-free compatibility with every release.

## CalVer

Application release tags are exactly:

```text
<heroic-release-tag>-YYYY.MM.DD.n
v2.22.1-2026.09.06.1
v2.22.1-2026.09.06.2
v2.22.2-2026.09.07.1
```

The date is Europe/Berlin. `n` starts at 1 for each upstream-tag/date pair and is
one greater than the largest already reserved Git tag in that pair. Failed
publication can leave a gap; existing versioned releases are never overwritten.
Concurrent runs are serialized.

Electron requires valid SemVer: its internal version is
`2.22.1-2026.9.6.1`, without a leading `v` or zero-padded numeric identifiers.
Pacman's version is `2.22.1_2026.09.06.1-1`: underscore instead of the forbidden
internal hyphen, followed by Arch's package-release suffix. The public release
tag and application archive names preserve the requested spelling. Generated
`build-info.json` records all three forms, source/upstream SHAs, and the replayed
commits. This is provenance, not a manually maintained patch manifest.

Tags point to the actual source on main. The matching source archive additionally
contains the generated package version and generic-update-feed configuration
used for packaging; dependencies and helper versions remain selected by that
source's frozen lockfile and helper definitions. Bit-identical reproducibility
across external toolchain changes is not claimed.

## Repository setup

No Amazon credentials or OpenAI API key are used by these workflows.

1. Keep Actions enabled. Enable **Issues** in Settings > General > Features for
   persistent conflict/failure reports.
2. Automation needs permission to update `main` and `downstream-base`, including
   non-fast-forward updates. Restrictive rulesets/branch protection must permit
   that for the publishing identity. Never broadly disable protection on an
   unrelated repository.
3. The publisher first supports the normal `GITHUB_TOKEN`. When GitHub refuses
   a rebase that brings changed workflow files, configure repository secret
   `DOWNSTREAM_PUSH_TOKEN`: a fine-grained PAT restricted to this fork with
   **Contents: read/write** and **Workflows: read/write**. Only the isolated Git
   promotion step receives it. Do not paste the token into chat or commit it.
4. For a signed pacman feed, configure secret `PACMAN_SIGNING_KEY` with an
   ASCII-armored dedicated private signing key/subkey, optional secret
   `PACMAN_SIGNING_PASSPHRASE`, and repository variable
   `PACMAN_SIGNING_FINGERPRINT` containing the full 40-character primary-key
   fingerprint. Export/retain the primary key offline and use a dedicated
   signing subkey where practical. Never commit private keys. Both the supplied
   key and fingerprint are checked before signing.

AppImage/tar.xz releases work without signing secrets. In that case the pacman
binary is still built, but **no unsigned pacman repository is published**. Any
previously signed repository remains unchanged. After setting signing secrets,
run the workflow manually with Force enabled to publish the signed feed.

A signed pacman database is generated with embedded package signatures. The
package, database and file database also receive detached signatures. Signature
verification runs before publication. Key export contains only the public key.

## Install and update on CachyOS / Arch Linux

After the signed feed has been published, its stable source is:

```text
https://github.com/felixfoertsch/HeroicGamesLauncher/releases/download/downstream-feed
```

Download `heroic-felix.asc` from that source and compare its fingerprint with
**your independently recorded signing-key fingerprint**, not merely a value
retrieved from the same server. After verifying it:

```sh
sudo pacman-key --add heroic-felix.asc
sudo pacman-key --lsign-key YOUR_VERIFIED_FULL_FINGERPRINT
```

Add this to `/etc/pacman.conf`:

```ini
[heroic-felix]
SigLevel = Required DatabaseRequired
Server = https://github.com/felixfoertsch/HeroicGamesLauncher/releases/download/downstream-feed
```

Then install with a full system update:

```sh
sudo pacman -Syu heroic-felix
```

The package explicitly conflicts with other native Heroic packages and provides
`heroic` / `heroic-games-launcher`; review pacman's replacement prompt. It keeps
Heroic's normal configuration directory. Back up that directory before switching.
Flatpak is a separate installation and is not removed by pacman. No sandbox
bypass flag is added.

Normal `pacman -Syu` updates this package thereafter. New package assets are
uploaded before the signed repository index; old binaries are retained so a
cached database can still retrieve its package. GitHub cannot atomically swap a
database and its detached signature: during the brief update window a refresh
may fail signature verification. Retry later; do not disable signature checks.

## AppImage updates

Install the first CalVer AppImage manually. The earlier
`2.22.1-felix.<run-id>.<attempt>` versions do not sort before this scheme under
SemVer, and their GitHub-discovery feed cannot parse padded numeric tags.

New AppImages use a generic `latest-linux.yml` feed from `downstream-feed`.
It names exact versioned download URLs and uses the normalized internal SemVer
for update comparisons. It never falls back to official Heroic and loses our
patches. Heroic still asks before downloading/installing updates. The
`downstream-feed` release is mutable repository metadata, not an application
version; all application releases use CalVer.

## Working on the fork

Use a clean checkout; save local changes on a separate branch before following
rebased main. Do not force-push over someone else's work. To add a finished
independent contribution, cherry-pick it onto main and push normally. To propose
just that change upstream, retain or create a branch on clean upstream containing
only that change. Test it independently: clean patch application alone does not
prove it has no dependency on earlier changes.

When resolving an upstream conflict manually, replay the local series onto the
new release in a temporary branch, resolve and test, then update main and the
baseline together with explicit leases. Keep the backup/release tags. Do not
advance the baseline without the corresponding series, and do not remove the
Nile fix solely because its PR was rejected or closed.

Automation tests can be run without installing Heroic dependencies:

```sh
node --test .github/downstream/prepare.test.mjs
```
