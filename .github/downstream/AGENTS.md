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

- `patch-queue` automatically refreshes actual upstream default-branch source plus all accepted patches and an explicit trusted control overlay. Accepted patch files remain source-customization authority. Each rewrite requires a verified self-contained backup, permanent lightweight `archive/patch-queue/<full-old-control-SHA>` tag and atomic expected-SHA leases; never retag or delete archives. Identical intended trees with current upstream ancestry are no-ops. `patch-queue` owns workflows and ordered accepted patch files. Generated `main` tracks upstream main plus trusted downstream publisher tooling, with no workflow files. Edge is the sole release channel, not a source branch. The four accepted patches include stacking and Nile session recovery. Future unfinished work stays outside the accepted queue and generated `main`.
- Keep only `patch-queue` (default, workflows and accepted patches) and generated `main` as long-lived branches. Archive obsolete branch tips before removal. Publishers never execute downloaded branch code with write credentials; build jobs receive no production signing secrets or write credentials.
- Releases are cumulative. Current baseline contains four accepted patches; adding patch five triggers the release pipeline and publishes upstream plus all five patches for edge. Keep the previous upstream-plus-four releases alongside the new releases, and retain subsequent release history. Pushes adding accepted patches to `patch-queue` automatically trigger publication after validation. Old-release cleanup was a one-time operation, not an automatic retention policy. Pacman and AppImage feed records are delivery methods; retain their working endpoints.
- Edge updates Latest, `downstream-feed` and signed `pacman`, and syncs generated `main` only under an expected-SHA lease. Preserve signing, full build validation and safeguards against accidental artifact overwrite.
- Edge tags use `<upstream-tag>-edge-YYYY.MM.DD.N`, with Europe/Berlin dates and the per-upstream-tag/date counter. Preserve existing published identities.
- The first README paragraph links each accepted patch by its `NNNN` number on `patch-queue`; the ordered patch section repeats individual links before the unchanged upstream README.
- Skip complete, verified published source/control identities unless an explicit rebuild is requested. Run automation with Python ≥3.11.
- Do not automatically prune releases or hosted binaries. Delete release history only when explicitly requested. Keep existing Git tags unless explicitly asked to change them; never relabel old binaries as newly built source.
- Before an authorized history rewrite, inspect the current remote head, preserve a recoverable reference to the old history, and verify that only the intended files change. Do not overwrite concurrent work. Use an explicit expected-SHA lease for Git pushes.

## Checks

Run the checks relevant to the change before considering it complete. The downstream pipeline includes Python/real-Git automation tests, TypeScript, Jest, ESLint, Prettier, Linux packaging, and a disposable-key pacman signature/download test. Report exactly which checks ran and any remaining limitations.
