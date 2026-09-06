import { test } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { prepareBuild, validateManifest } from './prepare.mjs'

function git(repo, ...args) {
  return execFileSync('git', ['-C', repo, ...args], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  }).trim()
}

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'heroic-stack-test-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const repo = join(root, 'repository')
  execFileSync('git', ['init', '-b', 'main', repo], { stdio: 'ignore' })
  git(repo, 'config', 'user.name', 'Test')
  git(repo, 'config', 'user.email', 'test@example.invalid')
  writeFileSync(
    join(repo, 'package.json'),
    JSON.stringify({ version: '2.22.1', packageManager: 'pnpm@10.28.0' })
  )
  writeFileSync(join(repo, 'electron-builder.yml'), 'productName: Heroic\n')
  writeFileSync(join(repo, 'shared.txt'), 'base\n')
  git(repo, 'add', '.')
  git(repo, 'commit', '-m', 'Base')
  const base = git(repo, 'rev-parse', 'HEAD')
  git(repo, 'remote', 'add', 'origin', repo)
  function branch(name, file, content) {
    git(repo, 'checkout', '-b', name, base)
    writeFileSync(join(repo, file), content)
    git(repo, 'add', file)
    git(repo, 'commit', '-m', name)
    const sha = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'checkout', 'main')
    return sha
  }
  const stacked = branch('feat/stack', 'stack.txt', 'stacked\n')
  const nile = branch('fix/nile', 'nile.txt', 'nile\n')
  return {
    repo,
    root,
    base,
    stacked,
    nile,
    branch,
    options: {
      repo,
      source: join(root, 'source'),
      artifacts: join(root, 'artifacts'),
      repository: 'test/heroic',
      buildId: '123.1',
      manifest: {
        base,
        features: [
          { name: 'Stack', ref: 'feat/stack' },
          { name: 'Nile', ref: 'fix/nile' }
        ]
      }
    }
  }
}

test('assembles both branches and preserves the original main branch', (t) => {
  const f = fixture(t)
  const result = prepareBuild(f.options)
  assert.equal(
    readFileSync(join(result.source, 'stack.txt'), 'utf8'),
    'stacked\n'
  )
  assert.equal(readFileSync(join(result.source, 'nile.txt'), 'utf8'), 'nile\n')
  assert.equal(git(f.repo, 'rev-parse', 'main'), f.base)
  assert.equal(git(f.repo, 'symbolic-ref', '--short', 'HEAD'), 'main')
  assert.equal(result.version, '2.22.1-felix.123.1')
  assert.equal(git(result.source, 'status', '--porcelain'), '')
  const info = JSON.parse(
    readFileSync(join(f.options.artifacts, 'build-manifest.json'))
  )
  assert.deepEqual(
    info.features.map(({ sha }) => sha),
    [f.stacked, f.nile]
  )
  assert.equal(info.sourceSha, git(result.source, 'rev-parse', 'HEAD'))
  const config = JSON.parse(
    readFileSync(join(result.source, 'electron-builder.custom.json'))
  )
  assert.equal(config.publish[0].owner, 'test')
  assert.equal(config.publish[0].repo, 'heroic')
})

test('accepts pinned full commit SHAs as merge inputs', (t) => {
  const f = fixture(t)
  f.options.manifest.features = [{ name: 'Pinned stack', ref: f.stacked }]
  const result = prepareBuild(f.options)
  assert(existsSync(join(result.source, 'stack.txt')))
  assert(!existsSync(join(result.source, 'nile.txt')))
})

test('cherry-picks one commit rather than bringing its whole branch', (t) => {
  const f = fixture(t)
  git(f.repo, 'checkout', 'feat/stack')
  writeFileSync(join(f.repo, 'single.txt'), 'only this change\n')
  git(f.repo, 'add', 'single.txt')
  git(f.repo, 'commit', '-m', 'Single independent change')
  const single = git(f.repo, 'rev-parse', 'HEAD')
  git(f.repo, 'checkout', 'main')
  f.options.manifest.features = [
    { name: 'Single', ref: single, mode: 'cherry-pick' }
  ]
  const result = prepareBuild(f.options)
  assert(existsSync(join(result.source, 'single.txt')))
  assert(!existsSync(join(result.source, 'stack.txt')))
})

test('stops on conflicts without publishing artifacts or changing main', (t) => {
  const f = fixture(t)
  f.branch('conflict/one', 'shared.txt', 'one\n')
  f.branch('conflict/two', 'shared.txt', 'two\n')
  f.options.manifest.features = [
    { name: 'One', ref: 'conflict/one' },
    { name: 'Two', ref: 'conflict/two' }
  ]
  assert.throws(() => prepareBuild(f.options), /Cannot integrate Two/)
  assert(!existsSync(f.options.artifacts))
  assert.equal(git(f.repo, 'rev-parse', 'main'), f.base)
})

test('refuses an empty feature list and duplicate refs', (t) => {
  const f = fixture(t)
  assert.throws(
    () => validateManifest(f.repo, { base: f.base, features: [] }),
    /at least one/
  )
  assert.throws(
    () =>
      validateManifest(f.repo, {
        base: f.base,
        features: [
          { name: 'A', ref: f.stacked },
          { name: 'B', ref: f.stacked }
        ]
      }),
    /Duplicate/
  )
})

test('rejects invalid refs, modes and repository names before building', (t) => {
  const f = fixture(t)
  for (const ref of [
    '--upload-pack=bad',
    'https://evil.example/repo',
    'main\nmalicious',
    'refs/remotes/origin/main'
  ]) {
    assert.throws(() =>
      validateManifest(f.repo, { base: f.base, features: [{ name: 'Bad', ref }] })
    )
  }
  assert.throws(
    () =>
      validateManifest(f.repo, {
        base: f.base,
        features: [{ name: 'Bad', ref: f.stacked, mode: 'force' }]
      }),
    /Unsupported integration/
  )
  assert.throws(
    () => prepareBuild({ ...f.options, repository: '../other' }),
    /owner\/name/
  )
})

test('refuses to overwrite an existing source directory', (t) => {
  const f = fixture(t)
  assert.throws(
    () => prepareBuild({ ...f.options, source: f.repo }),
    /must not already exist/
  )
  assert.equal(git(f.repo, 'rev-parse', 'main'), f.base)
})

test('bundle restores the exact source commit into a separate checkout', (t) => {
  const f = fixture(t)
  const result = prepareBuild(f.options)
  const clone = join(f.root, 'publish-checkout')
  execFileSync('git', ['clone', '--no-local', f.repo, clone], { stdio: 'ignore' })
  const bundle = join(f.options.artifacts, 'source.bundle')
  git(clone, 'bundle', 'verify', bundle)
  git(clone, 'fetch', bundle, `${result.bundleRef}:refs/heads/publish-source`)
  assert.equal(git(clone, 'rev-parse', 'publish-source'), result.sourceSha)
  const archived = execFileSync(
    'tar',
    [
      '-tzf',
      join(f.options.artifacts, `Heroic-${result.version}-source.tar.gz`)
    ],
    { encoding: 'utf8' }
  )
  assert(archived.includes('heroic-custom/stack.txt'))
  assert(archived.includes('heroic-custom/nile.txt'))
  assert(archived.includes('heroic-custom/custom-build-locked.json'))
})

test('locked inputs reproduce the feature tree after a branch advances', (t) => {
  const f = fixture(t)
  const first = prepareBuild(f.options)
  const locked = JSON.parse(
    readFileSync(join(first.source, 'custom-build-locked.json'))
  )
  const firstInfo = JSON.parse(
    readFileSync(join(f.options.artifacts, 'build-manifest.json'))
  )
  git(f.repo, 'checkout', 'feat/stack')
  writeFileSync(join(f.repo, 'later.txt'), 'not in the pinned build\n')
  git(f.repo, 'add', 'later.txt')
  git(f.repo, 'commit', '-m', 'Advance branch')
  git(f.repo, 'checkout', 'main')
  const artifacts = join(f.root, 'artifacts-replay')
  const replay = prepareBuild({
    ...f.options,
    manifest: locked,
    source: join(f.root, 'source-replay'),
    artifacts,
    buildId: '123.2'
  })
  assert(!existsSync(join(replay.source, 'later.txt')))
  const replayInfo = JSON.parse(
    readFileSync(join(artifacts, 'build-manifest.json'))
  )
  assert.equal(replayInfo.integratedTree, firstInfo.integratedTree)
})
