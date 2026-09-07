#!/usr/bin/env bash
set -euo pipefail
CONTROL=$PWD
BASE=2cc01fe4c88703ed002eafa6eb0ca06bb43443fc
OLD_MAIN=86a81d655a01a8ff2b8e25ed300201cbeb014e6b
RESULT="$RUNNER_TEMP/reordered"
mkdir -p "$RESULT"
export RESULT BASE OLD_MAIN
export GIT_AUTHOR_NAME='Felix Förtsch' GIT_AUTHOR_EMAIL='mail@felixfoertsch.de'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
python3 - <<'PY'
import base64, gzip, hashlib
from pathlib import Path
parts = Path('.github/ci-reorder')
compressed = base64.b64decode(''.join((parts / f'part{i}.txt').read_text() for i in range(5)), validate=True)
assert hashlib.sha1(b'blob ' + str(len(compressed)).encode() + b'\0' + compressed).hexdigest() == '22fadfb46cd4c00ca03b7da1a14cd93cac3b6c42'
Path('/tmp/ci-reorder.patch').write_bytes(gzip.decompress(compressed))
PY
CI="$RUNNER_TEMP/ci-source"
git worktree add --detach "$CI" "$BASE"
git show --format= --binary 9004571a8cd1a726592d5ee1c29fceb4ba71f014 | git -C "$CI" apply --index
git -C "$CI" apply --index /tmp/ci-reorder.patch
cd "$CI"
pnpm install --frozen-lockfile
pnpm exec prettier --write --ignore-unknown .github/downstream .github/workflows/downstream.yml .github/workflows/build-main.yml AGENTS.md doc/downstream.md doc/custom-builds.md
# The delivered infrastructure commit must not change any application files.
git diff --exit-code "$BASE" -- src package.json pnpm-lock.yaml jest.config.js
git add .github/downstream .github/workflows/downstream.yml .github/workflows/build-main.yml AGENTS.md doc/downstream.md doc/custom-builds.md
git diff --cached --check
git commit --no-gpg-sign -m 'ci: Maintain validated downstream Heroic releases' -m "AI disclosure: Implemented by Astra, an OpenAI AI assistant, at Felix Förtsch's direction.

Build every CI-enabled branch on push, with exact-source test prereleases isolated from main's CalVer releases and signed update feeds. Preserve guarded stable upstream replay, provenance, checksums and signing tests. List actual downstream commits in release notes.

Downstream-CI: true"
CI_SHA=$(git rev-parse HEAD)
export CI_SHA
git update-ref refs/reorder/main "$CI_SHA"
STACK="$RUNNER_TEMP/stack-source"
NILE="$RUNNER_TEMP/nile-source"
git worktree add --detach "$STACK" "$CI_SHA"
git -C "$STACK" cherry-pick --no-commit 1271543d75e2f28d51ef9e7592d2160fac3af32c c0870e6aad84b516d3ffbcec44e20318b21547cb 86a81d655a01a8ff2b8e25ed300201cbeb014e6b
git -C "$STACK" commit --no-gpg-sign -m 'feat: Stack duplicate cross-store games in the library' -m "AI disclosure: Implemented by Astra, an OpenAI AI assistant, at Felix Förtsch's direction.

Group conservative cross-store title matches after filtering, with per-copy actions and a chooser. Preserve status-aware representatives and lazy-loading behavior. Include current-view unique-game statistics and a persistent Stack copies checkbox.

Consolidate the implementation, related corrections, tests and documentation into one independently testable feature. No Nile changes are included."
STACK_SHA=$(git -C "$STACK" rev-parse HEAD)
export STACK_SHA
git update-ref refs/reorder/stack "$STACK_SHA"
git worktree add --detach "$NILE" "$CI_SHA"
git -C "$NILE" cherry-pick --no-commit d52b755d40ce1c9e245e02911ce3846baaedafd8
git -C "$NILE" commit --no-gpg-sign -C d52b755d40ce1c9e245e02911ce3846baaedafd8
NILE_SHA=$(git -C "$NILE" rev-parse HEAD)
export NILE_SHA
git update-ref refs/reorder/nile "$NILE_SHA"
# Recombination must reproduce every old application file, not only a selected subset.
COMBINED="$RUNNER_TEMP/combined-source"
git worktree add --detach "$COMBINED" "$STACK_SHA"
git -C "$COMBINED" cherry-pick --no-commit "$NILE_SHA"
python3 - <<'PY'
import os, subprocess
from pathlib import Path
ci = os.environ['CI_SHA']; base = os.environ['BASE']; old = os.environ['OLD_MAIN']
git = lambda *args: subprocess.check_output(['git', *args], text=True).strip()
assert git('rev-list', '--count', f'{base}..{ci}') == '1'
for key in ('STACK_SHA', 'NILE_SHA'):
    sha = os.environ[key]
    assert git('rev-parse', f'{sha}^') == ci
    assert git('rev-list', '--count', f'{ci}..{sha}') == '1'
combined = str(Path(os.environ['RUNNER_TEMP']) / 'combined-source')
changed = subprocess.check_output(['git','-C',combined,'diff','--name-only',old], text=True).splitlines()
assert all(p.startswith('.github/') or p in ('AGENTS.md','doc/downstream.md','doc/custom-builds.md') for p in changed), changed
infra = git('diff','--name-only',base,ci).splitlines()
assert all(p.startswith('.github/') or p in ('AGENTS.md','doc/downstream.md','doc/custom-builds.md') for p in infra), infra
assert not any('__pycache__' in p or 'ci-reorder' in p for p in git('ls-tree','-r','--name-only',ci).splitlines())
import json
plan = {'base': base, 'main':ci, 'stack':os.environ['STACK_SHA'], 'nile':os.environ['NILE_SHA'], 'expected': {
 'main':old, 'feat/stack-game-copies':'dee93826a6dcd97c40eadffd988df3c2cf5f528b',
 'fix/nile-amazon-login':'7e3b75410111cc2af3f4750f542871fe9bea68da'}}
Path(os.environ['RESULT'],'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
print(json.dumps(plan, indent=2))
PY
git bundle create "$RESULT/candidates.bundle" refs/reorder/main refs/reorder/stack refs/reorder/nile "^$BASE"
sha256sum "$RESULT/candidates.bundle" | cut -d ' ' -f 1 > "$RESULT/bundle.sha256"
cp "$RESULT/plan.json" "$CONTROL/reorder-plan.json"
