import { execFileSync } from 'node:child_process'
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync
} from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'

const identity = [
  '-c',
  'user.name=Heroic custom build',
  '-c',
  'user.email=41898282+github-actions[bot]@users.noreply.github.com'
]

function git(repo, ...args) {
  return execFileSync('git', ['-C', repo, ...identity, ...args], {
    encoding: 'utf8',
    env: { ...process.env, GIT_TERMINAL_PROMPT: '0' },
    stdio: ['ignore', 'pipe', 'pipe'],
    maxBuffer: 32 * 1024 * 1024
  }).trim()
}

function normalizeRef(repo, value) {
  if (typeof value !== 'string' || !value || value.startsWith('-')) {
    throw new Error('Each source must specify a branch, tag, or full commit SHA')
  }
  if (/^[a-f0-9]{40}$/i.test(value)) return value.toLowerCase()
  const ref = value.startsWith('refs/') ? value : `refs/heads/${value}`
  if (!ref.startsWith('refs/heads/') && !ref.startsWith('refs/tags/')) {
    throw new Error(`Unsupported ref namespace: ${value}`)
  }
  git(repo, 'check-ref-format', ref)
  return ref
}

export function validateManifest(repo, value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Build manifest must be an object')
  }
  if (!Array.isArray(value.features) || value.features.length === 0) {
    throw new Error('Select at least one feature; refusing an unmodified build')
  }
  const base = normalizeRef(repo, value.base)
  const seen = new Set()
  const features = value.features.map((feature) => {
    if (
      !feature ||
      typeof feature.name !== 'string' ||
      !feature.name.trim() ||
      /[\r\n]/.test(feature.name)
    ) {
      throw new Error('Each feature needs a single-line name')
    }
    const ref = normalizeRef(repo, feature.ref)
    const mode = feature.mode ?? 'merge'
    if (!['merge', 'cherry-pick'].includes(mode)) {
      throw new Error(`Unsupported integration mode: ${mode}`)
    }
    if (seen.has(ref)) throw new Error(`Duplicate feature ref: ${ref}`)
    seen.add(ref)
    return { name: feature.name, ref, mode }
  })
  return { base, features }
}

function fetchCommit(repo, ref) {
  // Argument arrays, not shell interpolation: refs cannot execute commands.
  git(repo, 'fetch', '--no-tags', 'origin', ref)
  const sha = git(repo, 'rev-parse', '--verify', 'FETCH_HEAD^{commit}')
  if (/^[a-f0-9]{40}$/.test(ref) && sha !== ref) {
    throw new Error(`Resolved commit does not match pinned SHA: ${ref}`)
  }
  return sha
}

function writeJson(path, value) {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
}

/** Assemble a disposable worktree. Never push or modify an existing branch. */
export function prepareBuild({
  repo,
  source,
  artifacts,
  manifest,
  repository,
  buildId
}) {
  repo = resolve(repo)
  source = resolve(source)
  artifacts = resolve(artifacts)
  if (
    typeof repository !== 'string' ||
    !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository) ||
    repository.split('/').some((part) => part === '.' || part === '..')
  ) {
    throw new Error('Expected repository in owner/name form')
  }
  if (!/^[0-9]+\.[0-9]+$/.test(buildId)) {
    throw new Error('Build ID must be run-id.run-attempt')
  }
  if (existsSync(source) || existsSync(artifacts)) {
    throw new Error('Source and artifact destinations must not already exist')
  }
  const recipeSha = git(repo, 'rev-parse', 'HEAD')
  const recipe = validateManifest(repo, manifest)
  const baseSha = fetchCommit(repo, recipe.base)
  // Resolve all moving refs once, before merging or running any feature code.
  const features = recipe.features.map((feature) => ({
    ...feature,
    sha: fetchCommit(repo, feature.ref)
  }))

  git(repo, 'worktree', 'add', '--detach', source, baseSha)
  for (const feature of features) {
    try {
      if (feature.mode === 'cherry-pick') {
        git(source, 'cherry-pick', '-x', feature.sha)
      } else {
        git(
          source,
          'merge',
          '--no-ff',
          '--no-edit',
          '-m',
          `Integrate custom feature: ${feature.name}`,
          feature.sha
        )
      }
    } catch (error) {
      throw new Error(
        `Cannot integrate ${feature.name} (${feature.sha}); resolve the conflict in its branch.\n${error.stderr || error.message}`
      )
    }
  }
  if (git(source, 'status', '--porcelain')) {
    throw new Error('Integrated source is not clean')
  }
  const integratedSha = git(source, 'rev-parse', 'HEAD')
  const integratedTree = git(source, 'rev-parse', 'HEAD^{tree}')
  const packagePath = join(source, 'package.json')
  const pkg = JSON.parse(readFileSync(packagePath, 'utf8'))
  const coreVersion = /^([0-9]+\.[0-9]+\.[0-9]+)(?:[-+].*)?$/.exec(pkg.version)
  if (!coreVersion) throw new Error('Unsupported Heroic package version')
  const version = `${coreVersion[1]}-felix.${buildId}`
  pkg.version = version
  pkg.repository = { type: 'git', url: `https://github.com/${repository}` }
  writeJson(packagePath, pkg)

  const [owner, name] = repository.split('/')
  writeJson(join(source, 'electron-builder.custom.json'), {
    extends: './electron-builder.yml',
    publish: [
      { provider: 'github', owner, repo: name, releaseType: 'prerelease' }
    ],
    linux: {
      artifactName: 'Heroic-${version}-custom-${arch}.${ext}'
    }
  })
  const provenance = {
    repository,
    recipeSha,
    base: { ref: recipe.base, sha: baseSha },
    features,
    integratedSha,
    integratedTree,
    version,
    platform: 'linux',
    arch: 'x64',
    packageManager: pkg.packageManager
  }
  writeJson(join(source, 'custom-build-provenance.json'), provenance)
  writeJson(join(source, 'custom-build-locked.json'), {
    base: baseSha,
    features: features.map(({ name, sha, mode }) => ({ name, ref: sha, mode }))
  })
  writeFileSync(
    join(source, 'CUSTOM-BUILD.md'),
    '# Custom Heroic build\n\n' +
      'This source includes the selected features and packaging metadata.\n' +
      'See custom-build-provenance.json for the resolved commits.\n\n' +
      'Build on Linux with Node 22 and the packageManager version in package.json:\n\n' +
      '```sh\npnpm install --frozen-lockfile\npnpm exec install-electron\n' +
      'pnpm download-helper-binaries\npnpm codecheck\npnpm test --runInBand\n' +
      'pnpm exec electron-vite build\n' +
      'pnpm exec electron-builder --config electron-builder.custom.json --linux AppImage tar.xz --x64 --publish never\n```\n'
  )
  git(
    source,
    'add',
    'package.json',
    'electron-builder.custom.json',
    'custom-build-provenance.json',
    'custom-build-locked.json',
    'CUSTOM-BUILD.md'
  )
  git(source, 'commit', '-m', `Prepare custom Heroic ${version}`)
  const sourceSha = git(source, 'rev-parse', 'HEAD')
  const sourceTree = git(source, 'rev-parse', 'HEAD^{tree}')

  mkdirSync(artifacts, { recursive: true })
  writeJson(join(artifacts, 'build-manifest.json'), {
    ...provenance,
    sourceSha,
    sourceTree
  })
  // The bundle contains only commits above the base, not all upstream history.
  const bundleRef = `refs/custom-build/${buildId}`
  git(repo, 'update-ref', bundleRef, sourceSha, '0'.repeat(40))
  git(
    repo,
    'bundle',
    'create',
    join(artifacts, 'source.bundle'),
    bundleRef,
    `^${baseSha}`
  )
  git(
    source,
    'archive',
    '--format=tar.gz',
    '--prefix=heroic-custom/',
    `--output=${join(artifacts, `Heroic-${version}-source.tar.gz`)}`,
    'HEAD'
  )
  writeFileSync(
    join(artifacts, 'RELEASE-NOTES.md'),
    `# Heroic ${version}\n\nUnofficial Linux x64 custom build.\n\n` +
      `Base: \`${baseSha}\`\n\n` +
      features
        .map(({ name, ref, sha, mode }) => `- ${name}: \`${ref}\` → \`${sha}\` (${mode})`)
        .join('\n') +
      `\n\nSource commit: \`${sourceSha}\`\n\n` +
      'Published only after combined-source TypeScript, Jest, lint and formatting checks pass.\n' +
      'Automated checks do not verify live Amazon sign-in/MFA.\n\n' +
      'Includes AppImage, tar.xz, matching source and build-manifest.json.\n' +
      'Verify downloads with `sha256sum -c SHA256SUMS`.\n' +
      'The update feed is this fork, not the upstream Heroic repository.\n'
  )
  return { source, sourceSha, bundleRef, version, tag: `v${version}` }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values } = parseArgs({
    options: Object.fromEntries(
      ['repo', 'source', 'artifacts', 'manifest', 'repository', 'build-id'].map(
        (name) => [name, { type: 'string' }]
      )
    )
  })
  try {
    for (const name of ['repo', 'source', 'artifacts', 'manifest', 'repository', 'build-id']) {
      if (!values[name]) throw new Error(`Missing --${name}`)
    }
    const result = prepareBuild({
      ...values,
      manifest: JSON.parse(readFileSync(values.manifest, 'utf8')),
      buildId: values['build-id']
    })
    if (process.env.GITHUB_OUTPUT) {
      for (const [key, value] of Object.entries(result)) {
        appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`)
      }
    }
    console.log(JSON.stringify(result, null, 2))
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
