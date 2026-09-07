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

- Keep `main` linear above the stable `downstream-base`: upstream baseline, **one CI infrastructure commit first**, then only explicitly accepted, completed feature/fix commits. There is no feature-selection manifest. The CI commit carries the exact trailer `Downstream-CI: true`; its parent pins each development branch's upstream baseline.
- Develop features/fixes on separate branches based on the CI-enabled `main`. Keep one coherent application commit above that base; squash stacking cards, overview, preference, tests and related repairs into the stacking feature. Do not include Nile in stacking or stacking in Nile. Keep unfinished features/fixes out of `main`. Before an upstream submission, create a separate clean review branch without fork CI. Leave contribution PRs as drafts inside this fork unless Felix explicitly requests upstream submission or ready-for-review status. Do not open a PR for fork-only CI infrastructure.
- Every push to a CI-enabled development branch must build and publish its own immutable test prerelease. Test on the branch before rebasing/integrating into `main`; build the resulting revision again after rebasing. Main alone publishes CalVer releases and updates normal channels. Preview builds must never advance `main`, `downstream-base`, `downstream-feed`, `pacman` or Latest. Preserve build, test, signing and guarded promotion checks. Branch publishers use trusted main code and never receive production signing credentials. Release notes enumerate the actual commits above that build's upstream baseline, in order.
- Use public release tags of the form `heroic-release-tag-YYYY.MM.DD.n`, with Europe/Berlin dates and the existing per-upstream-tag/date counter. Do not reintroduce workflow-run IDs as public versions.
- Never move or overwrite published release tags or binaries when cleaning branch history. Old releases describe the source they actually built; a release from the cleaned history gets a new CalVer revision.
- Before an authorized history rewrite, inspect the current remote head, preserve a recoverable reference to the old history, and verify that only the intended files change. Do not overwrite concurrent work. Use an explicit expected-SHA lease for Git pushes.

## Checks

Run the checks relevant to the change before considering it complete. The downstream pipeline includes Python/real-Git automation tests, TypeScript, Jest, ESLint, Prettier, Linux packaging, and a disposable-key pacman signature/download test. Report exactly which checks ran and any remaining limitations.
