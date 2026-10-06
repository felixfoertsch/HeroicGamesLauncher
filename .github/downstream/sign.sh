#!/usr/bin/env bash
# Runs only in the isolated publisher, never in the source/build job.
set -euo pipefail
umask 077
assets=$(realpath "${1:?release assets required}")
key=${PACMAN_SIGNING_KEY:-}
fingerprint=${PACMAN_SIGNING_FINGERPRINT:-}
passphrase=${PACMAN_SIGNING_PASSPHRASE:-}
if [[ -z "$key$fingerprint$passphrase" ]]; then
  # Retain unsigned packages in the build artifact, but never offer an unsigned feed.
  rm -f "$assets"/*.pkg.tar.zst
  printf '%s\n' 'Pacman publication awaits signing-key setup; no unsigned repository was published.' \
    > "$assets/SIGNING-STATUS.txt"
  echo 'signed=false' >> "$GITHUB_OUTPUT"
  exit 0
fi
[[ -n "$key" && "$fingerprint" =~ ^([A-Fa-f0-9]{40}|[A-Fa-f0-9]{64})$ ]] || {
  echo 'Signing configuration is incomplete; refusing publication.' >&2; exit 1;
}
fingerprint=${fingerprint^^}
export GNUPGHOME
GNUPGHOME=$(mktemp -d)
trap 'gpgconf --kill gpg-agent || true; rm -rf "$GNUPGHOME"' EXIT
printf '%s' "$key" | gpg --batch --import
actual=$(gpg --batch --with-colons --list-secret-keys | awk -F: '$1=="fpr" { print $10; exit }')
[[ "$actual" == "$fingerprint" ]] || { echo 'Signing fingerprint mismatch' >&2; exit 1; }
unset key PACMAN_SIGNING_KEY
sign_file() {
  printf '%s\n' "$passphrase" | gpg --batch --yes --pinentry-mode loopback \
    --passphrase-fd 0 --local-user "$fingerprint" --output "$1.sig" --detach-sign "$1"
  gpg --batch --verify "$1.sig" "$1"
}
shopt -s nullglob
packages=("$assets"/*.pkg.tar.zst)
((${#packages[@]} == 1)) || { echo 'Expected exactly one pacman package' >&2; exit 1; }
for package in "${packages[@]}"; do sign_file "$package"; done
image=$(cat "$assets/archlinux-image.txt")
[[ "$image" =~ ^archlinux@sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid Arch image digest' >&2; exit 1; }
# repo-add inspects package metadata. It does not execute the package or its install script.
# No signing key, passphrase or GitHub token is passed into this container.
docker run --rm --network=none --user "$(id -u):$(id -g)" -v "$assets:/repo" "$image" bash -euc '
  cd /repo
  repo-add heroic-felix.db.tar.gz ./*.pkg.tar.zst
  cp -L heroic-felix.db /tmp/heroic-felix.db
  cp -L heroic-felix.files /tmp/heroic-felix.files
  rm heroic-felix.db heroic-felix.files
  cp /tmp/heroic-felix.db /tmp/heroic-felix.files .
  rm -f heroic-felix.db.tar.gz heroic-felix.files.tar.gz
'
for db in "$assets/heroic-felix.db" "$assets/heroic-felix.files"; do sign_file "$db"; done
gpg --armor --export "$fingerprint" > "$assets/heroic-felix-key.asc"
printf '%s\n' "$fingerprint" > "$assets/heroic-felix-key.fingerprint"
echo 'signed=true' >> "$GITHUB_OUTPUT"
