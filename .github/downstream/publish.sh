#!/usr/bin/env bash
# Publish complete CalVer releases, then update AppImage and signed pacman feeds.
set -euo pipefail
assets=$(realpath "${1:?release assets required}")
repo=felixfoertsch/HeroicGamesLauncher
[[ "$GITHUB_REPOSITORY" == "$repo" ]] || exit 1
# Verify public/internal versions agree before using release names in any write.
python3 - "$assets/build-info.json" <<'PY'
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.github/downstream').resolve()))
from calver import validate_plan_version
validate_plan_version(json.loads(Path(sys.argv[1]).read_text()))
PY
tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$assets/build-info.json")
source_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate"])' "$assets/build-info.json")
# A different signing key requires a deliberate client-trust migration.
if [[ "${SIGNED:-false}" == true ]] && gh release view pacman --repo "$repo" >/dev/null 2>&1; then
  previous=$(mktemp -d)
  trap 'rm -rf "$previous"' EXIT
  gh release download pacman --repo "$repo" --pattern heroic-felix-key.fingerprint --dir "$previous"
  cmp "$previous/heroic-felix-key.fingerprint" "$assets/heroic-felix-key.fingerprint"
fi
mapfile -d '' files < <(find "$assets" -maxdepth 1 -type f ! -name RELEASE-NOTES.md -print0)
gh release create "$tag" "${files[@]}" --repo "$repo" --verify-tag --draft --latest=false \
  --title "Heroic $tag — unofficial downstream" --notes-file "$assets/RELEASE-NOTES.md"
gh release edit "$tag" --repo "$repo" --draft=false --prerelease=false --latest
if [[ "${SIGNED:-false}" == true ]]; then
  if ! gh release view pacman --repo "$repo" >/dev/null 2>&1; then
    gh release create pacman --repo "$repo" --target "$source_sha" --prerelease --latest=false \
      --title 'Signed pacman repository' \
      --notes 'Rolling signed package index. Versioned packages are retained. See doc/downstream.md for setup and trust verification.'
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
    --notes 'Mutable generic updater metadata. Application versions use CalVer; see doc/downstream.md.'
fi
gh release upload downstream-feed "$assets/latest-linux.yml" --repo "$repo" --clobber
