import { createHash } from 'node:crypto'
import { cpSync, readFileSync, readdirSync, mkdirSync, writeFileSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { git, run, writeJson, forkRepository, releaseTagPattern } from './prepare.mjs'

export function stage(source, plan) {
  if (plan.repository !== forkRepository || !releaseTagPattern.test(plan.version.tag)) {
    throw new Error('Invalid release plan')
  }
  if (git(source, 'rev-parse', 'HEAD') !== plan.sourceSha) throw new Error('Wrong source checkout')
  const packagePath = join(source, 'package.json')
  const pkg = JSON.parse(readFileSync(packagePath, 'utf8'))
  pkg.version = plan.version.electron
  pkg.repository = { type: 'git', url: `https://github.com/${forkRepository}` }
  writeJson(packagePath, pkg)
  writeJson(join(source, 'electron-builder.downstream.json'), {
    extends: './electron-builder.yml',
    detectUpdateChannel: false,
    publish: [{ provider: 'generic', channel: 'latest',
      url: `https://github.com/${forkRepository}/releases/download/downstream-feed` }],
    linux: { artifactName: `Heroic-${plan.version.tag}-linux-\${arch}.\${ext}` }
  })
  writeJson(join(source, 'downstream-build-info.json'), plan)
}

export function updateMetadata(plan, imagePath) {
  const bytes = readFileSync(imagePath)
  const url = `https://github.com/${forkRepository}/releases/download/${plan.version.tag}/${encodeURIComponent(imagePath.split('/').pop())}`
  const hash = createHash('sha512').update(bytes).digest('base64')
  // JSON-quoted strings are also valid YAML. Use a generic feed: GitHub's
  // SemVer tag discovery cannot parse our deliberately zero-padded CalVer tags.
  return `version: ${JSON.stringify(plan.version.electron)}\nfiles:\n` +
    `  - url: ${JSON.stringify(url)}\n    sha512: ${hash}\n    size: ${bytes.length}\n` +
    `path: ${JSON.stringify(url)}\nsha512: ${hash}\n` +
    `releaseName: ${JSON.stringify(plan.version.tag)}\nreleaseDate: ${JSON.stringify(new Date().toISOString())}\n`
}

export function collect(source, plan, out) {
  mkdirSync(out)
  const dist = join(source, 'dist')
  const names = readdirSync(dist).filter((name) => name.startsWith(`Heroic-${plan.version.tag}-`) &&
    (name.endsWith('.AppImage') || name.endsWith('.tar.xz')))
  if (names.filter((n) => n.endsWith('.AppImage')).length !== 1 ||
      names.filter((n) => n.endsWith('.tar.xz')).length !== 1) {
    throw new Error('Expected exactly one AppImage and one tar.xz')
  }
  for (const name of names) {
    if (!statSync(join(dist, name)).isFile()) throw new Error('Package is not a regular file')
    cpSync(join(dist, name), join(out, name))
  }
  const image = names.find((n) => n.endsWith('.AppImage'))
  writeFileSync(join(out, 'latest-linux.yml'), updateMetadata(plan, join(out, image)))
  writeJson(join(out, 'build-info.json'), plan)
  writeFileSync(join(out, 'RELEASE-NOTES.md'), `# Heroic ${plan.version.tag}\n\n` +
    `Unofficial Linux x64 downstream build. AI-assisted changes by Astra (OpenAI), directed and tested by Felix.\n\n` +
    `Upstream: \`${plan.upstreamTag}\` (\`${plan.upstreamSha}\`).\n\nSource: \`${plan.sourceSha}\`.\n\n` +
    `CalVer date uses Europe/Berlin. Internal Electron version: \`${plan.version.electron}\`; pacman pkgver: \`${plan.version.pacman}\`.\n\n` +
    plan.patches.map((p) => `- ${p.subject} — ${p.status} (\`${p.result || p.original}\`)`).join('\n') +
    '\n\nThe source archive contains the exact source commit plus generated package-version and update-feed metadata.\n' +
    'Automated checks do not replace interactive login, game-launch or operating-system testing.\n' +
    'The first CalVer AppImage must be installed manually when migrating from the earlier felix.<run-id> scheme.\n')
  // Archive tracked source only, plus the three explicit packaging overlays.
  const archiveDir = join(out, 'source-archive')
  mkdirSync(archiveDir)
  const tarPath = join(out, 'tracked-source.tar')
  git(source, 'archive', '--format=tar', '--output', tarPath, plan.sourceSha)
  run('tar', ['-xf', tarPath, '-C', archiveDir])
  for (const name of ['package.json', 'electron-builder.downstream.json', 'downstream-build-info.json']) {
    cpSync(join(source, name), join(archiveDir, name))
  }
  run('tar', ['-czf', join(out, `Heroic-${plan.version.tag}-source.tar.gz`), '-C', archiveDir, '.'])
}

export function writePkgbuild(plan, archive, directory) {
  mkdirSync(directory)
  cpSync(archive, join(directory, 'heroic.tar.xz'))
  const hash = createHash('sha256').update(readFileSync(archive)).digest('hex')
  const template = readFileSync(new URL('./PKGBUILD', import.meta.url), 'utf8')
  writeFileSync(join(directory, 'PKGBUILD'), template
    .replaceAll('@PKGVER@', plan.version.pacman).replaceAll('@SHA256@', hash))
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const mode = process.argv[2]
  const plan = JSON.parse(readFileSync('plan/plan.json', 'utf8'))
  const source = resolve('source')
  const out = resolve('release')
  if (mode === 'stage') stage(source, plan)
  else if (mode === 'collect') collect(source, plan, out)
  else if (mode === 'pacman') {
    const archive = readdirSync(out).find((name) => name.endsWith('.tar.xz'))
    if (!archive) throw new Error('Missing built tar.xz')
    writePkgbuild(plan, join(out, archive), resolve('arch-package'))
  } else throw new Error('Expected stage, collect or pacman')
}
