#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${PACMAN_SIGNING_KEY:-}" && -z "${PACMAN_SIGNING_FINGERPRINT:-}" ]]; then
  echo '::warning::Signed pacman feed disabled until PACMAN_SIGNING_KEY and PACMAN_SIGNING_FINGERPRINT are configured.'
  exit 0
fi
[[ -n "${PACMAN_SIGNING_KEY:-}" && "${PACMAN_SIGNING_FINGERPRINT:-}" =~ ^[A-Fa-f0-9]{40}$ ]] || {
  echo '::error::Configure both the private signing key and its full primary fingerprint.'
  exit 1
}
export GNUPGHOME
GNUPGHOME=$(mktemp -d)
chmod 700 "$GNUPGHOME"
trap 'gpgconf --kill gpg-agent || true; rm -rf "$GNUPGHOME"' EXIT
printf '%s\n' "$PACMAN_SIGNING_KEY" | gpg --batch --import
fingerprint=${PACMAN_SIGNING_FINGERPRINT^^}
actual=$(gpg --batch --with-colons --list-secret-keys "$fingerprint" |
  awk -F: '$1 == "fpr" { print $10; exit }')
[[ "$actual" == "$fingerprint" ]] || { echo '::error::Signing key fingerprint mismatch'; exit 1; }
sign() {
  printf '%s' "${PACMAN_SIGNING_PASSPHRASE:-}" | gpg --batch --yes \
    --pinentry-mode loopback --passphrase-fd 0 --local-user "$fingerprint" \
    --output "$1.sig" --detach-sign "$1"
  gpg --batch --verify "$1.sig" "$1"
}
shopt -s nullglob
packages=(release/heroic-felix-*.pkg.tar.zst)
[[ ${#packages[@]} == 1 ]] || { echo '::error::Expected one pacman package'; exit 1; }
sign "${packages[0]}"
mkdir signed-repository
cp "${packages[0]}" "${packages[0]}.sig" signed-repository/
(cd signed-repository && repo-add heroic-felix.db.tar.gz ./*.pkg.tar.zst)
for name in db files; do
  cp -L "signed-repository/heroic-felix.$name" "release/heroic-felix.$name"
  sign "release/heroic-felix.$name"
done
gpg --batch --armor --export "$fingerprint" > release/heroic-felix.asc
printf '%s\n' "$fingerprint" > release/heroic-felix.fingerprint
