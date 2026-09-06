#!/usr/bin/env bash
# Publish fully uploaded releases; keep old packages on the rolling pacman channel.
set -euo pipefail
assets=$(realpath "${1:?release assets required}")
repo=felixfoertsch/HeroicGamesLauncher
[[ "$GITHUB_REPOSITORY" == "$repo" ]] || exit 1
tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$assets/build-info.json")
[[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-felix\.[0-9]+\.[0-9]+$ ]] || exit 1
# A different key is a manual rotation, not an automatic replacement of client trust.
if [[ "${SIGNED:-false}" == true ]] && gh release view pacman --repo "$repo" >/dev/null 2>&1; then
  previous=$(mktemp -d)
  trap 'rm -rf "$previous"' EXIT
  gh release download pacman --repo "$repo" --pattern heroic-felix-key.fingerprint --dir "$previous"
  cmp "$previous/heroic-felix-key.fingerprint" "$assets/heroic-felix-key.fingerprint"
fi
mapfile -d '' files < <(find "$assets" -maxdepth 1 -type f ! -name RELEASE-NOTES.md -print0)
gh release create "$tag" "${files[@]}" --repo "$repo" --verify-tag --draft --latest=false \
  --title "Heroic ${tag#v} — unofficial downstream" --notes-file "$assets/RELEASE-NOTES.md"
# Only make the release discoverable after every asset was uploaded successfully.
gh release edit "$tag" --repo "$repo" --draft=false --prerelease=false --latest
if [[ "${SIGNED:-false}" == true ]]; then
  source_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["candidate"])' "$assets/build-info.json")
  if ! gh release view pacman --repo "$repo" >/dev/null 2>&1; then
    gh release create pacman --repo "$repo" --target "$source_sha" --prerelease --latest=false \
      --title 'Signed pacman repository' \
      --notes 'Rolling signed package index. Versioned packages are retained. See doc/downstream.md for setup and trust verification.'
  fi
  # New immutable filenames first, then update the signed index. Never delete old packages.
  gh release upload pacman "$assets"/*.pkg.tar.zst "$assets"/*.pkg.tar.zst.sig --repo "$repo"
  gh release upload pacman "$assets/heroic-felix-key.asc" "$assets/heroic-felix-key.fingerprint" \
    --repo "$repo" --clobber
  gh release upload pacman "$assets/heroic-felix.db" "$assets/heroic-felix.db.sig" \
    "$assets/heroic-felix.files" "$assets/heroic-felix.files.sig" --repo "$repo" --clobber
fi
