#!/usr/bin/env bash
# Run locally with an existing dedicated signing key. Private bytes go only to Actions secrets.
set -euo pipefail
umask 077
repo=felixfoertsch/HeroicGamesLauncher
fingerprint=${1:?Usage: bash .github/downstream/setup-signing.sh FULL_FINGERPRINT}
[[ "$fingerprint" =~ ^([A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})$ ]] || exit 1
fingerprint=${fingerprint^^}
command -v gh >/dev/null
command -v gpg >/dev/null
gh auth status
actual=$(gpg --batch --with-colons --list-secret-keys "$fingerprint" | awk -F: '$1=="fpr" { print $10; exit }')
[[ "$actual" == "$fingerprint" ]] || { echo 'Full primary-key fingerprint required' >&2; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
read -rsp 'Passphrase for the dedicated signing key: ' passphrase
printf '\n'
# Validate the passphrase and signing capability before updating any repository secret.
printf 'Heroic signing setup\n' > "$tmp/check"
printf '%s\n' "$passphrase" | gpg --batch --pinentry-mode loopback --passphrase-fd 0 \
  --local-user "$fingerprint" --detach-sign "$tmp/check"
printf '%s\n' "$passphrase" | gpg --batch --pinentry-mode loopback --passphrase-fd 0 \
  --armor --export-secret-keys "$fingerprint" > "$tmp/key.asc"
test -s "$tmp/key.asc"
gh secret set PACMAN_SIGNING_KEY --repo "$repo" < "$tmp/key.asc"
printf '%s' "$passphrase" | gh secret set PACMAN_SIGNING_PASSPHRASE --repo "$repo"
printf '%s' "$fingerprint" | gh variable set PACMAN_SIGNING_FINGERPRINT --repo "$repo"
unset passphrase
printf 'Configured signing identity: %s\n' "$fingerprint"
printf 'Now run the Downstream Heroic workflow manually on main to publish the signed feed.\n'
