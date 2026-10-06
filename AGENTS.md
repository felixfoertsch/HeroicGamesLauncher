**AI disclosure:** Prepared by Astra, an OpenAI AI assistant, at Felix Förtsch's direction.

# Downstream working agreement

These instructions record Felix's requirements for this fork. Preserve upstream contribution guidance and keep upstream-only submissions distinct from CI-enabled development branches.

## Commit policy

- Deliver one coherent commit per logical feature or fix. Include its implementation, tests, documentation, formatting corrections and related follow-up repairs in that commit.
- Temporary work-in-progress commits may be used on scratch branches for development and CI. Squash related iterations before integrating the finished change into `main` or presenting its contribution draft. Do not leave a trail of lint fixes, retry tweaks and partial implementation commits in the delivered patch series.
- Treat the downstream release pipeline as one logical infrastructure change while implementing or stabilizing it. Fold related repairs into that change instead of adding separate release-note entries for every iteration.
- Keep unrelated finished features and fixes separate. A sensible squash represents a complete change, not an arbitrary number of commits or every future change to the same subsystem.
- Use Heroic-style descriptive commit subjects, such as `feat: Stack duplicate cross-store games in the library`, `fix: Recover Amazon sessions and handle Nile login failures`, and `ci: Maintain validated downstream Heroic releases`.
- Disclose Astra's AI involvement at the beginning of PR and release descriptions, and in the opening paragraph of AI-assisted commit bodies. Distinguish automated checks from tests reported by Felix; never claim unperformed validation.

## Branches and releases

- `automation` owns workflows and ordered accepted patch files. Generated `main` tracks upstream main plus trusted downstream publisher tooling, with no workflow files. Stable and nightly are release channels, not source branches. Unfinished Nile and stacking work never enter accepted patch files or generated `main`.
- Existing feature branches and their preview workflows remain untouched. Preview publishers check out trusted generated `main`, never execute downloaded branch code with write credentials, receive no production signing secrets, and never update stable channels or Latest.
- Stable publishes immutable CalVer releases and only it may update Latest, `downstream-feed` and signed `pacman`. Nightly is isolated prerelease output and syncs generated `main` only under an expected-SHA lease. Preserve signing, full build validation and immutable-artifact guards.
- Use public release tags of the form `heroic-release-tag-YYYY.MM.DD.n`, with Europe/Berlin dates and the existing per-upstream-tag/date counter. Do not reintroduce workflow-run IDs as public versions.
- Never move or overwrite published release tags or binaries when cleaning branch history. Old releases describe the source they actually built; a release from the cleaned history gets a new CalVer revision.
- Before an authorized history rewrite, inspect the current remote head, preserve a recoverable reference to the old history, and verify that only the intended files change. Do not overwrite concurrent work. Use an explicit expected-SHA lease for Git pushes.

## Checks

Run the checks relevant to the change before considering it complete. The downstream pipeline includes Python/real-Git automation tests, TypeScript, Jest, ESLint, Prettier, Linux packaging, and a disposable-key pacman signature/download test. Report exactly which checks ran and any remaining limitations.
