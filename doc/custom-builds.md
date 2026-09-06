# Custom Heroic releases

The **Build custom Heroic** workflow builds a selected feature stack, not simply
whatever is on `main`. Its recipe lives on `build/custom-heroic` in
`.github/custom-build.json`. Feature branches stay independent; neither they
nor the recipe need to be merged into `main` to build a custom release.

The initial recipe is the base commit `e95e407a` plus, in order:

1. `feat/stack-game-copies` (including its optional-runner TypeScript fix).
2. `fix/nile-amazon-login`.

## Add, remove or pin features

Edit `.github/custom-build.json` on the **build/custom-heroic branch** and push.
The workflow automatically builds and publishes a new prerelease if checks pass.
To add a whole feature branch, append an entry to `features`:

```json
{
  "name": "Another feature",
  "ref": "feat/another-feature"
}
```

The default mode is `merge`: integrate the branch's history with a normal
three-way merge. A full commit SHA can replace `ref` to pin that exact branch
state. Explicit tags such as `refs/tags/v2.22.1` are also supported.

To apply only one ordinary commit, not all its ancestors, use:

```json
{
  "name": "One isolated fix",
  "ref": "0123456789abcdef0123456789abcdef01234567",
  "mode": "cherry-pick"
}
```

Use a real full 40-character commit SHA. Merge commits cannot be cherry-picked
without specifying a mainline; this recipe intentionally does not guess one.
Use merge mode for them. All refs must be in this fork; no external repository
URLs, shell commands, or automatic conflict resolutions are accepted.

Remove an entry to omit a feature from the next build. Update `base` to move to a
new upstream baseline. A conflict or invalid/missing ref fails the build rather
than dropping the feature or falling back to plain upstream Heroic.

Moving branch refs are resolved once at the beginning of each run. Re-run **all
jobs** to pick up new commits on existing feature branches, or push an empty
commit to the recipe branch to trigger a fresh run. Every release records the
exact SHAs, and its source includes `custom-build-locked.json` for pinned replay.
This pins the feature source, not every external service or a bit-identical binary.

## First run and manual triggering

GitHub normally disables Actions in a newly created fork. Enable them once in
this fork's **Actions** tab. The branch push trigger works without merging the
workflow into `main`. After enabling Actions, a fresh push is needed when the
original push did not create a run:

```sh
git fetch origin
git switch build/custom-heroic
git pull --ff-only
git commit --allow-empty -m "build: run selected Heroic feature stack"
git push origin build/custom-heroic
```

The **Run workflow** button (`workflow_dispatch`) requires the workflow file on
the repository's default branch. After merging this recipe PR, it can also be
run manually from the Actions tab, selecting the desired recipe branch. Keeping
recipe edits on `build/custom-heroic` retains automatic push-triggered builds.

## Outputs and checks

The workflow uses Ubuntu 24.04, Node 22, and the `packageManager` version from the
assembled source. It installs the frozen lockfile and Heroic's pinned helper
binaries, then runs full TypeScript checking, Jest, ESLint and Prettier **on the
combined source**, before building Linux x64 AppImage and tar.xz packages.

A successful run publishes an **unofficial prerelease in this fork**, never the
upstream repository. Version names look like `2.22.1-felix.<run-id>.<attempt>`.
Assets include both packages, the matching source archive, update metadata when
produced, `build-manifest.json` and `SHA256SUMS`. The release tag points at the
actual integrated source commit, not just the build recipe or unmodified `main`.

Packaging explicitly points the update feed at this fork. Builds use Heroic's
normal configuration location; back up that configuration before testing a new
build. Automated tests do not establish that live Amazon sign-in/MFA works.

The build job has read-only repository access. Only the separate publication
job has `contents: write`, and it does not execute source code from the feature
stack. Publishing never force-updates tags or changes a feature/main branch.
No personal access token or Amazon credentials are required by the workflow.

## Local recipe tests

The assembly script has no npm dependencies. Its tests use real temporary Git
repositories to cover ordered merges, pinned commits, cherry-picks, conflicts,
invalid inputs, source-bundle recovery, and replay after a branch advances:

```sh
node --test .github/scripts/custom-build/prepare.test.mjs
```
