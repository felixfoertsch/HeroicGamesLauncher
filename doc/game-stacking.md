# Cross-store game stacks

The library groups matching store copies into one card (or one row in list
layout). A circular badge shows the number of copies in that stack. Clicking
or keyboard-activating the badge opens a chooser with each store, its title,
and whether that copy is installed. Selecting a copy opens that copy's existing
game page, with the usual install, play, settings and uninstall actions.

The normal card actions target the representative copy: an active operation
first, otherwise an installed copy, otherwise the first copy in library order.
The store logo identifies that representative. Running games and all active
operations, including importing, moving and extracting, therefore remain
accessible without treating different installations as one.

Title grouping is memoized independently of operation statuses. Status-only
updates reuse the existing lazy-loading observer while the displayed store-copy
identities are unchanged. Switching the representative, adding/removing cards or
changing their order refreshes observation so remounted cards still load.

## Matching and filtering

Matching uses store-provided titles, ignoring case, whitespace, trademark marks,
apostrophe style, and colon/hyphen separators. Unicode compatibility normalization
handles equivalent character representations. Edition names, sequel numbers,
accents and other substantive title differences are retained. Display-name
overrides do not change automatic matching.

Only unambiguous cross-store matches are grouped. Sideloaded games, blank titles
and multiple distinct same-title entries from a single store stay separate.
DLC entries are excluded as before. Repeated records with the same runner and
store ID do not inflate the count.

Grouping happens after the existing store, search, hidden-game, category and
other library filters; the installed-only restriction is applied before
counting. The badge counts copies in the current results, not copies excluded
by filters. Recent/favourite sections group the entries supplied to that section.
Library header totals continue to count the underlying store entries.

This is deliberately conservative title matching, not a global game-identity
database. Differently named store listings can remain separate, and unrelated
games with identical titles cannot always be distinguished. There are no new
network requests, metadata services, dependencies or configuration migrations.
No account records, game installations, saves or per-store settings are merged,
deleted or hidden by this feature.

## Tests

The Common Jest project contains regression tests for matching, ambiguous
editions, sideloads, DLC exclusion, filter semantics, stable ordering,
store-scoped IDs, non-mutation and representative selection.

```sh
pnpm test --selectProjects Common --runInBand
pnpm codecheck
pnpm lint
```

## Manual smoke test

Start the development build with `pnpm start` after installing dependencies and
running `pnpm download-helper-binaries`.

1. With the same game in Epic and GOG, verify one tile with a circular `2` badge.
   A game owned in only one store should have no badge.
2. Open the badge with mouse, Enter and Space. Verify both store entries and
   installation states, correct destination game pages, Escape/Close handling,
   and focus restoration to the badge.
3. Check grid and list layouts, recent/favourite sections, and controller mode.
   Ensure the badge does not cover the store icon, status or action buttons.
4. Filter to one store, hide one copy, and enable installed-only. The chooser
   must not reintroduce excluded entries. Clear the filters to restore the stack.
5. Install or launch the non-representative copy from its own page, then return
   to the library. Also check importing, moving and extracting that copy. Verify
   its status, available progress/cancel actions and lazy-loaded artwork, including
   after the operation completes and the representative changes.
6. Check a base game, sequel and remaster: they must remain separate. Check that
   each copy's settings, save location and uninstall actions remain independent.
