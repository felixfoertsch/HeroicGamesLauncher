import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  berlinDate,
  nextVersion,
  replaySeries,
  promotionArgs,
  git,
  run
} from './prepare.mjs'
import { updateMetadata } from './package.mjs'

function fixture(t) {
  const directory = mkdtempSync(join(tmpdir(), 'heroic-downstream-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  const repo = join(directory, 'repo')
  run('git', ['init', '--initial-branch=main', repo])
  const commit = (file, value, message) => {
    writeFileSync(join(repo, file), value)
    git(repo, 'add', file)
    git(repo, 'commit', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')
  }
  const base = commit('base.txt', 'base\n', 'upstream U1')
  return { directory, repo, base, commit }
}

function version(tag = 'v2.22.1', date = '2026.09.06', tags = []) {
  return nextVersion(tag, date, tags)
}

test('CalVer preserves upstream tag and padded dates', () => {
  assert.deepEqual(version(), {
    tag: 'v2.22.1-2026.09.06.1',
    date: '2026.09.06',
    sequence: 1,
    electron: '2.22.1-2026.9.6.1',
    pacman: '2.22.1_2026.09.06.1'
  })
})

test('counter increases numerically, not lexicographically', () => {
  assert.equal(
    version('v2.22.1', '2026.09.06', [
      'v2.22.1-2026.09.06.9',
      'v2.22.1-2026.09.06.10',
      'v2.22.1-2026.09.06.2',
      'v2.22.1-2026.09.06.nonsense'
    ]).sequence,
    11
  )
})

test('counter resets per upstream tag and calendar date', () => {
  const tags = ['v2.22.1-2026.09.06.15']
  assert.equal(version('v2.22.1', '2026.09.07', tags).sequence, 1)
  assert.equal(version('v2.22.2', '2026.09.06', tags).sequence, 1)
  assert.equal(version('2.22.1').tag, '2.22.1-2026.09.06.1')
})

test('Berlin date handles midnight and winter/summer offsets', () => {
  assert.equal(berlinDate(new Date('2026-09-06T22:30:00Z')), '2026.09.07')
  assert.equal(berlinDate(new Date('2026-01-01T23:30:00Z')), '2026.01.02')
  assert.equal(berlinDate(new Date('2026-12-31T23:30:00Z')), '2027.01.01')
})

test('rejects invalid tags, dates, prereleases and counter overflow', () => {
  for (const tag of [
    '--help',
    'v2.22.1;exit',
    'v2.22.1-beta',
    'v02.2.1',
    'v2.22'
  ]) {
    assert.throws(() => version(tag))
  }
  for (const date of ['2026.2.06', '2026.02.30', '2026.13.01', '2026.00.01']) {
    assert.throws(() => version('v2.22.1', date))
  }
  assert.throws(() =>
    version('v2.22.1', '2026.09.06', ['v2.22.1-2026.09.06.9007199254740992'])
  )
  assert.equal(version('v2.22.1', '2028.02.29').sequence, 1)
})

test('replays A then B onto U2, preserving main and the original commits', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const a = commit('feature.txt', 'A\n', 'A')
  const b = commit('feature.txt', 'A\nB uses A\n', 'B')
  git(repo, 'checkout', '-b', 'upstream', base)
  const u2 = commit('upstream.txt', 'U2\n', 'upstream U2')
  git(repo, 'checkout', 'main')
  const result = replaySeries(repo, base, b, u2, join(directory, 'candidate'))
  assert.deepEqual(
    result.patches.map((p) => p.original),
    [a, b]
  )
  assert.equal(git(repo, 'rev-parse', 'main'), b)
  assert.equal(git(repo, 'rev-parse', `${result.sourceSha}~2`), u2)
  assert.equal(
    git(repo, 'show', `${result.sourceSha}:feature.txt`),
    'A\nB uses A'
  )
  assert.equal(git(repo, 'show', `${result.sourceSha}:upstream.txt`), 'U2')
})

test('unchanged upstream preserves commit identities', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const a = commit('a.txt', 'A\n', 'A')
  const result = replaySeries(repo, base, a, base, join(directory, 'candidate'))
  assert.equal(result.sourceSha, a)
  assert.equal(result.patches[0].status, 'unchanged')
})

test('exact equivalent upstream patch is recorded, not applied twice', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const a = commit('a.txt', 'A\n', 'A')
  const b = commit('b.txt', 'B\n', 'B')
  git(repo, 'checkout', '-b', 'upstream', base)
  commit('upstream.txt', 'U2\n', 'upstream U2')
  git(repo, 'cherry-pick', a)
  const target = git(repo, 'rev-parse', 'HEAD')
  const result = replaySeries(
    repo,
    base,
    b,
    target,
    join(directory, 'candidate')
  )
  assert.equal(result.patches[0].status, 'already-upstream')
  assert.equal(result.patches[1].status, 'replayed')
  assert.equal(git(repo, 'rev-parse', `${result.sourceSha}^`), target)
})

test('conflict stops without dropping a fix or changing main', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const a = commit('base.txt', 'local\n', 'A')
  git(repo, 'checkout', '-b', 'upstream', base)
  const target = commit('base.txt', 'different upstream\n', 'U2')
  assert.throws(
    () => replaySeries(repo, base, a, target, join(directory, 'candidate')),
    /Cannot replay/
  )
  assert.equal(git(repo, 'rev-parse', 'main'), a)
})

test('semantic equivalence implemented differently is not silently skipped', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const a = commit('a.txt', 'A\n', 'A')
  git(repo, 'checkout', '-b', 'upstream', base)
  writeFileSync(join(repo, 'a.txt'), 'A\n')
  git(repo, 'add', 'a.txt')
  const target = commit(
    'unrelated.txt',
    'also changed\n',
    'combined upstream patch'
  )
  assert.throws(
    () => replaySeries(repo, base, a, target, join(directory, 'candidate')),
    /Cannot replay/
  )
  assert.equal(git(repo, 'rev-parse', 'main'), a)
})

test('nonlinear downstream histories are rejected', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  commit('a.txt', 'A\n', 'A')
  git(repo, 'checkout', '-b', 'side', base)
  commit('side.txt', 'side\n', 'side')
  git(repo, 'checkout', 'main')
  git(repo, 'merge', '--no-ff', '--no-edit', 'side')
  assert.throws(
    () =>
      replaySeries(
        repo,
        base,
        git(repo, 'rev-parse', 'HEAD'),
        base,
        join(directory, 'candidate')
      ),
    /must be linear/
  )
})

test('existing destination is not overwritten', (t) => {
  const { repo, base } = fixture(t)
  assert.throws(() => replaySeries(repo, base, base, base, repo), /overwrite/)
})

test('promotion uses atomic compare-and-swap leases and immutable release tags', () => {
  const plan = {
    previousMain: 'a'.repeat(40),
    previousBase: 'b'.repeat(40),
    sourceSha: 'c'.repeat(40),
    upstreamSha: 'd'.repeat(40),
    version: version()
  }
  const args = promotionArgs(plan)
  assert.ok(args.includes('--atomic'))
  assert.ok(
    args.includes(`--force-with-lease=refs/heads/main:${plan.previousMain}`)
  )
  assert.ok(
    args.includes(
      `--force-with-lease=refs/heads/downstream-base:${plan.previousBase}`
    )
  )
  assert.ok(args.includes(`${plan.sourceSha}:refs/tags/v2.22.1-2026.09.06.1`))
  assert.ok(!args.includes('--force'))
  assert.throws(() => promotionArgs({ ...plan, sourceSha: 'main' }))
  assert.throws(() =>
    promotionArgs({ ...plan, version: { tag: 'x\ncommands' } })
  )
})

test('stale main lease rejects the entire publication transaction', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const remote = join(directory, 'remote.git')
  run('git', ['init', '--bare', remote])
  git(repo, 'remote', 'add', 'origin', remote)
  git(
    repo,
    'push',
    'origin',
    `${base}:refs/heads/main`,
    `${base}:refs/heads/downstream-base`
  )
  const candidate = commit('a.txt', 'A\n', 'A')
  const concurrent = commit('concurrent.txt', 'concurrent\n', 'concurrent')
  git(repo, 'push', 'origin', `${concurrent}:refs/heads/main`)
  const plan = {
    previousMain: base,
    previousBase: base,
    sourceSha: candidate,
    upstreamSha: base,
    version: version()
  }
  assert.throws(() => git(repo, ...promotionArgs(plan)))
  assert.equal(git(remote, 'rev-parse', 'refs/heads/main'), concurrent)
  assert.equal(git(remote, 'tag', '--list'), '')
})

test('bundle transports the exact candidate commit', (t) => {
  const { directory, repo, base, commit } = fixture(t)
  const candidate = commit('a.txt', 'A\n', 'A')
  git(repo, 'update-ref', 'refs/heads/candidate', candidate)
  const bundle = join(directory, 'source.bundle')
  git(repo, 'bundle', 'create', bundle, 'refs/heads/candidate', `^${base}`)
  git(repo, 'bundle', 'verify', bundle)
  git(repo, 'fetch', bundle, 'refs/heads/candidate:refs/heads/restored')
  assert.equal(git(repo, 'rev-parse', 'restored'), candidate)
})

test('AppImage feed points at the exact padded CalVer release', (t) => {
  const { directory } = fixture(t)
  const image = join(
    directory,
    'Heroic-v2.22.1-2026.09.06.1-linux-x86_64.AppImage'
  )
  writeFileSync(image, 'image bytes')
  const metadata = updateMetadata({ version: version() }, image)
  assert.ok(metadata.includes('version: "2.22.1-2026.9.6.1"'))
  assert.ok(metadata.includes('/releases/download/v2.22.1-2026.09.06.1/'))
  assert.ok(metadata.includes('size: 11'))
  assert.ok(metadata.includes('sha512: '))
})
