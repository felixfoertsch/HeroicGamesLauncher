#!/usr/bin/env bash
# Publish complete CalVer releases, then update AppImage and signed pacman feeds.
set -euo pipefail
assets=$(realpath "${1:?release assets required}")
repo=felixfoertsch/HeroicGamesLauncher
[[ "$GITHUB_REPOSITORY" == "$repo" ]] || exit 1
# Disclosure and public CalVer are derived from validated build provenance.
notes_flags=()
[[ "${SIGNED:-false}" != true ]] || notes_flags+=(--signed)
python3 .github/downstream/release_notes.py "$assets" "${notes_flags[@]}"
python3 .github/downstream/downstream.py checksums --output "$assets"
tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$assets/build-info.json")
source_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate"])' "$assets/build-info.json")
# A different signing key requires a deliberate client-trust migration.
previous=$(mktemp -d)
trap 'rm -rf "$previous"' EXIT
if [[ "${SIGNED:-false}" == true ]] && gh release view pacman --repo "$repo" >/dev/null 2>&1; then
  gh release download pacman --repo "$repo" --pattern heroic-felix-key.fingerprint --dir "$previous"
  cmp "$previous/heroic-felix-key.fingerprint" "$assets/heroic-felix-key.fingerprint"
fi
mapfile -d '' files < <(find "$assets" -maxdepth 1 -type f -print0)
python3 - "$assets" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, '.github/downstream')
from channel_build import publish_release
assets = Path(sys.argv[1])
plan = json.loads((assets / 'build-info.json').read_text())
if plan.get('schema') == 2:
    publish_release(assets, plan)
else:
    from downstream import command
    files = [str(p) for p in sorted(assets.iterdir())]
    command(['gh', 'release', 'create', plan['tag'], *files, '--repo', plan['repository'],
             '--verify-tag', '--draft', '--latest=false', '--title', 'Heroic ' + plan['tag'],
             '--notes-file', str(assets / 'RELEASE-NOTES.md')])
    command(['gh', 'release', 'edit', plan['tag'], '--repo', plan['repository'],
             '--draft=false', '--prerelease=false', '--latest'])
PY
python3 - "$previous" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.github/downstream').resolve()))
from release_notes import channel_notes
for channel in ('pacman', 'downstream-feed'):
    (Path(sys.argv[1]) / (channel + '.md')).write_text(channel_notes(channel))
PY
if [[ "${SIGNED:-false}" == true ]]; then
  if ! gh release view pacman --repo "$repo" >/dev/null 2>&1; then
    gh release create pacman --repo "$repo" --target "$source_sha" --prerelease --latest=false \
      --title 'Signed pacman repository (not an application release)' \
      --notes-file "$previous/pacman.md"
  else
    gh release edit pacman --repo "$repo" --notes-file "$previous/pacman.md"
  fi
  gh release upload pacman "$assets"/*.pkg.tar.zst "$assets"/*.pkg.tar.zst.sig --repo "$repo"
  gh release upload pacman "$assets/heroic-felix-key.asc" "$assets/heroic-felix-key.fingerprint" \
    --repo "$repo" --clobber
  gh release upload pacman "$assets/heroic-felix.db" "$assets/heroic-felix.db.sig" \
    "$assets/heroic-felix.files" "$assets/heroic-felix.files.sig" --repo "$repo" --clobber
fi
# Generic update metadata avoids interpreting padded CalVer tags as SemVer.
# The URL inside this feed names an immutable, already fully uploaded release.
if ! gh release view downstream-feed --repo "$repo" >/dev/null 2>&1; then
  gh release create downstream-feed --repo "$repo" --target "$source_sha" --prerelease --latest=false \
    --title 'AppImage update feed (not an application release)' \
    --notes-file "$previous/downstream-feed.md"
else
  gh release edit downstream-feed --repo "$repo" --notes-file "$previous/downstream-feed.md"
fi
gh release upload downstream-feed "$assets/latest-linux.yml" --repo "$repo" --clobber
