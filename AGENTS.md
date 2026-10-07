# Downstream working agreement

These instructions record Felix's requirements for this fork. Preserve upstream contribution guidance and keep upstream-only submissions distinct from CI-enabled development branches.

## Commit policy

- Deliver one coherent commit per logical feature or fix. Include its implementation, tests, documentation, formatting corrections and related follow-up repairs in that commit.
- Temporary work-in-progress commits may be used on scratch branches for development and CI. Squash related iterations before integrating the finished change into `main` or presenting its contribution draft. Do not leave a trail of lint fixes, retry tweaks and partial implementation commits in the delivered patch series.
- Treat the downstream release pipeline as one logical infrastructure change while implementing or stabilizing it. Fold related repairs into that change instead of adding separate release-note entries for every iteration.
- Keep unrelated finished features and fixes separate. A sensible squash represents a complete change, not an arbitrary number of commits or every future change to the same subsystem.
- Keep downstream history clean: each commit is a coherent unit, ideally independently applicable. Fold follow-up fixes into their owning change rather than delivering separate `fix:` commits. Reorder, squash and force-push our downstream work when needed; leave upstream history unchanged.
- Use descriptive commit subjects, such as `feat: Stack duplicate cross-store games in the library`, `feat: Recover Amazon sessions and handle Nile login failures`, and `ci: Maintain validated downstream Heroic releases`.
- Distinguish automated checks from tests reported by Felix; never claim unperformed validation.

## Branches and releases

- `patch-queue` owns workflows and ordered accepted patch files. Generated `main` tracks upstream main plus trusted downstream publisher tooling, with no workflow files. Stable and nightly are release channels, not source branches. Unfinished Nile and stacking work never enter accepted patch files or generated `main`.
- Keep only `patch-queue` (default, workflows and accepted patches) and generated `main` as long-lived branches. Archive obsolete branch tips before removal. Publishers never execute downloaded branch code with write credentials; preview jobs receive no production signing secrets and never update stable channels or Latest.
- Releases are cumulative. Current baseline contains four accepted patches; adding patch five triggers the release pipeline and publishes upstream plus all five patches for stable and nightly. Keep the previous upstream-plus-four releases alongside the new releases, and retain subsequent release history. Pushes adding accepted patches to `patch-queue` automatically trigger publication after validation. Old-release cleanup was a one-time operation, not an automatic retention policy. Pacman and AppImage feed records are delivery methods; retain their working endpoints.
- Only stable may update Latest, `downstream-feed` and signed `pacman`. Nightly is isolated prerelease output and syncs generated `main` only under an expected-SHA lease. Preserve signing, full build validation and safeguards against accidental artifact overwrite.
- Use public release tags of the form `heroic-release-tag-YYYY.MM.DD.n`, with Europe/Berlin dates and the existing per-upstream-tag/date counter. Do not reintroduce workflow-run IDs as public versions.
- Do not automatically prune releases or hosted binaries. Delete release history only when explicitly requested. Keep existing Git tags unless explicitly asked to change them; never relabel old binaries as newly built source.
- Before an authorized history rewrite, inspect the current remote head, preserve a recoverable reference to the old history, and verify that only the intended files change. Do not overwrite concurrent work. Use an explicit expected-SHA lease for Git pushes.

## Checks

Run the checks relevant to the change before considering it complete. The downstream pipeline includes Python/real-Git automation tests, TypeScript, Jest, ESLint, Prettier, Linux packaging, and a disposable-key pacman signature/download test. Report exactly which checks ran and any remaining limitations.
