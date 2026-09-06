import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, writeFileSync, lstatSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { git, run, promotionArgs, forkRepository } from './prepare.mjs'

const repo = resolve('recipe')
const assets = resolve('release')
const plan = JSON.parse(readFileSync('plan/plan.json', 'utf8'))
if (process.env.GITHUB_REPOSITORY !== forkRepository || process.env.GITHUB_REF !== 'refs/heads/main') {
  throw new Error('Publication is restricted to this fork and main')
}
if (plan.sourceSha !== process.env.EXPECTED_SOURCE_SHA) throw new Error('Unexpected candidate source')

function gh(...args) { return run('gh', [...args, '--repo', forkRepository]) }
function api(path) { return JSON.parse(run('gh', ['api', path])) }
function currentMain() {
  return git(repo, 'ls-remote', 'origin', 'refs/heads/main').split(/\s/)[0]
}
function releaseFiles() {
  return readdirSync(assets).filter((name) => name !== 'RELEASE-NOTES.md').map((name) => {
    if (!/^[A-Za-z0-9_.-]+$/.test(name) || !lstatSync(join(assets, name)).isFile()) {
      throw new Error(`Unexpected release asset: ${name}`)
    }
    return join(assets, name)
  })
}

const mode = process.argv[2]
if (mode === 'promote') {
  git(repo, 'bundle', 'verify', resolve('plan/source.bundle'))
  git(repo, 'fetch', resolve('plan/source.bundle'),
    'refs/heads/downstream-candidate:refs/heads/downstream-candidate')
  if (git(repo, 'rev-parse', 'refs/heads/downstream-candidate') !== plan.sourceSha) {
    throw new Error('Source bundle does not match the tested commit')
  }
  if (currentMain() !== plan.previousMain) throw new Error('main changed while building; nothing will be published')
  run('gh', ['auth', 'setup-git'])
  git(repo, ...promotionArgs(plan))
} else if (mode === 'release') {
  if (currentMain() !== plan.sourceSha) throw new Error('main advanced after promotion; refusing to update the feed')
  const names = releaseFiles().filter((path) => !path.endsWith('/SHA256SUMS'))
  writeFileSync(join(assets, 'SHA256SUMS'), names.map((path) =>
    `${createHash('sha256').update(readFileSync(path)).digest('hex')}  ${path.split('/').pop()}\n`).join(''))
  // Release assets are uploaded while the release is a draft. The update feed
  // is changed only after the complete versioned release is made public.
  gh('release', 'create', plan.version.tag, '--verify-tag', '--draft',
    '--title', `Heroic ${plan.version.tag} (Felix downstream)`,
    '--notes-file', join(assets, 'RELEASE-NOTES.md'))
  gh('release', 'upload', plan.version.tag, ...releaseFiles())
  gh('release', 'edit', plan.version.tag, '--draft=false', '--latest')
  const releases = api(`repos/${forkRepository}/releases?per_page=100`)
  if (!releases.some((r) => r.tag_name === 'downstream-feed')) {
    gh('release', 'create', 'downstream-feed', '--target', plan.sourceSha,
      '--title', 'Downstream update feed (not an application version)',
      '--notes', 'Mutable AppImage and signed pacman repository metadata. Versioned application releases remain immutable.',
      '--prerelease', '--latest=false')
  }
  // Publish package files before the database that refers to them. Old package
  // files are deliberately retained for clients with cached database snapshots.
  if (existsSync(join(assets, 'heroic-felix.db'))) {
    const packages = releaseFiles().filter((p) => /\.pkg\.tar\.zst(?:\.sig)?$/.test(p))
    gh('release', 'upload', 'downstream-feed', ...packages)
    for (const name of ['heroic-felix.asc', 'heroic-felix.fingerprint',
      'heroic-felix.db', 'heroic-felix.db.sig', 'heroic-felix.files', 'heroic-felix.files.sig']) {
      gh('release', 'upload', 'downstream-feed', join(assets, name), '--clobber')
    }
  } else {
    console.log('Signed pacman feed not updated: configure PACMAN_SIGNING_KEY and PACMAN_SIGNING_FINGERPRINT.')
  }
  gh('release', 'upload', 'downstream-feed', join(assets, 'latest-linux.yml'), '--clobber')
  console.log(`Published https://github.com/${forkRepository}/releases/tag/${plan.version.tag}`)
} else throw new Error('Expected promote or release')
