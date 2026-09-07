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

## Stacking preference

The **Stack copies** checkbox beside the library count changes presentation
only. It is enabled by default and saved locally across library navigation and
application restarts. Turn it off to show each eligible store copy separately,
with no multi-copy badge, in the original filtered and sorted library order.
The preference applies to grid and list layouts and the recent/favourite lanes.
It does not modify the collection, clear filters or alter the unique-game and
copy statistics. Statistics continue to use the same conservative matching.

Test the checkbox with mouse and keyboard (Space), navigate away and return,
then restart Heroic. Verify both layouts and auxiliary lanes, store/installed
filters, and that visible card placeholders are observed again when the display
changes. Committed Frontend tests exercise the real Library state and GamesList
with mocked card bodies and store data; they do not replace a desktop smoke test.

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
The library header counts unique game stacks, not their underlying store copies.

This is deliberately conservative title matching, not a global game-identity
database. Differently named store listings can remain separate, and unrelated
games with identical titles cannot always be distinguished. There are no new
network requests, metadata services, dependencies or configuration migrations.
No account records, game installations, saves or per-store settings are merged,
deleted or hidden by this feature.

## Library overview

Hover over, focus, or activate the header's number to show its overview. Escape
or moving away dismisses it; the pointer can move into the overview to read it.
The count and every overview statistic describe the **current main library view**,
including its store, search, alphabet, category, hidden and installed filters.
They do not add hidden or filtered-out copies or count the recent/favourite lane
again. Filtering to a single store naturally removes cross-store overlap.

- **Unique games:** number of stacks, using the same title/edition and ambiguity
  rules as the cards. This is the number displayed in the header.
- **Total copies:** distinct runner/app-ID records in those stacks, excluding DLC
  and repeated records.
- **Games on multiple stores:** number of stacks containing more than one copy.
- **Extra copies across stores:** total copies minus unique games. One game owned
  on three stores contributes one multi-store game and two extra copies.
- **Copies by source:** the per-store totals, plus sideloads when present. The
  rows sum to total copies; stores with no copies in this view are omitted.

For example, 400 Epic copies and 100 Amazon copies, with 10 matching games on
both, yield 490 unique games, 500 copies, 10 multi-store games and 10 extra copies.
Sideloads are independent entries, not matched to store titles. These statistics
use existing library metadata only and never fetch additional account data.

## Tests

The Common Jest project contains regression tests for matching, ambiguous
editions, sideloads, DLC exclusion, filter semantics, stable ordering,
store-scoped IDs, non-mutation, representative selection and overview totals.
`gameLibraryStats.test.ts` checks three-store overlaps, the 400/100-copy example,
per-source reconciliation, empty views and current-view filtering.

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
7. Compare the header count with main-list stacks, then open its overview using
   hover, keyboard focus, Enter/Space and touch. Check Escape, moving into and out
   of the overview, filtering while it is open, and a zero-result search. Confirm
   source counts sum to total copies and games plus extra copies equals copies.
