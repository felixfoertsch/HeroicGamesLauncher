import { execFileSync } from 'node:child_process'
import { appendFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'
import { pathToFileURL } from 'node:url'

export const upstreamRepository = 'Heroic-Games-Launcher/HeroicGamesLauncher'
export const forkRepository = 'felixfoertsch/HeroicGamesLauncher'
export const stableTagPattern = /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/
export const releaseTagPattern =
  /^v?\d+\.\d+\.\d+-\d{4}\.\d{2}\.\d{2}\.[1-9]\d*$/
const shaPattern = /^[a-f0-9]{40}$/

export function run(command, args, options = {}) {
  return execFileSync(command, args, {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
    ...options
  }).trim()
}

export function git(repo, ...args) {
  return run('git', [
    '-C',
    repo,
    '-c',
    'user.name=Heroic downstream automation',
    '-c',
    'user.email=41898282+github-actions[bot]@users.noreply.github.com',
    ...args
  ])
}

function ancestor(repo, older, newer) {
  try {
    git(repo, 'merge-base', '--is-ancestor', older, newer)
    return true
  } catch (error) {
    if (error.status === 1) return false
    throw error
  }
}

export function writeJson(path, value) {
  writeFileSync(path, JSON.stringify(value, null, 2) + '\n')
}

export function berlinDate(now = new Date()) {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Berlin',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
    .format(now)
    .replaceAll('-', '.')
}

export function nextVersion(upstreamTag, date, tags) {
  if (!stableTagPattern.test(upstreamTag))
    throw new Error('Expected a stable upstream version tag')
  if (!/^\d{4}\.\d{2}\.\d{2}$/.test(date))
    throw new Error('Expected YYYY.MM.DD')
  const [year, month, day] = date.split('.').map(Number)
  const parsed = new Date(`${date.replaceAll('.', '-')}T12:00:00Z`)
  if (
    !Number.isFinite(parsed.getTime()) ||
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() + 1 !== month ||
    parsed.getUTCDate() !== day
  ) {
    throw new Error('Invalid calendar date')
  }
  const prefix = `${upstreamTag}-${date}.`
  const used = tags
    .filter((tag) => tag.startsWith(prefix))
    .map((tag) => tag.slice(prefix.length))
    .filter((n) => /^[1-9]\d*$/.test(n))
    .map(Number)
  if (used.some((n) => !Number.isSafeInteger(n)))
    throw new Error('Release counter overflow')
  const sequence = Math.max(0, ...used) + 1
  if (!Number.isSafeInteger(sequence))
    throw new Error('Release counter overflow')
  const core = upstreamTag.replace(/^v/, '')
  return {
    tag: `${prefix}${sequence}`,
    date,
    sequence,
    // Electron requires SemVer: numeric identifiers cannot have leading zeros.
    electron: `${core}-${year}.${month}.${day}.${sequence}`,
    // pacman does not allow a hyphen within pkgver.
    pacman: `${core}_${date}.${sequence}`
  }
}

/** Replay only the commits after the recorded baseline; never move a remote ref. */
export function replaySeries(repo, base, head, target, destination) {
  for (const sha of [base, head, target]) {
    if (!shaPattern.test(sha))
      throw new Error('Replay requires full commit SHAs')
  }
  if (!ancestor(repo, base, head))
    throw new Error('downstream-base is not an ancestor of the source')
  if (git(repo, 'rev-list', '--min-parents=2', `${base}..${head}`)) {
    throw new Error(
      'The downstream patch series must be linear: merge commits require manual cleanup'
    )
  }
  if (existsSync(destination))
    throw new Error('Refusing to overwrite the candidate directory')
  const commits = git(repo, 'rev-list', '--reverse', `${base}..${head}`)
    .split('\n')
    .filter(Boolean)
  const equivalent = new Set(
    git(repo, 'cherry', target, head, base)
      .split('\n')
      .filter((line) => line.startsWith('- '))
      .map((line) => line.slice(2))
  )
  git(
    repo,
    'worktree',
    'add',
    '--detach',
    destination,
    target === base ? head : target
  )
  const patches = []
  for (const sha of commits) {
    const subject = git(repo, 'show', '-s', '--format=%s', sha)
    if (target === base) {
      patches.push({ original: sha, result: sha, subject, status: 'unchanged' })
      continue
    }
    if (ancestor(repo, sha, target) || equivalent.has(sha)) {
      patches.push({ original: sha, subject, status: 'already-upstream' })
      continue
    }
    try {
      // --allow-empty preserves deliberately empty original commits, not patches
      // that unexpectedly become empty. Those still stop for human review.
      git(destination, 'cherry-pick', '--allow-empty', sha)
    } catch (error) {
      const conflicts = git(
        destination,
        'diff',
        '--name-only',
        '--diff-filter=U'
      )
      try {
        git(destination, 'cherry-pick', '--abort')
      } catch {
        /* retain diagnostics */
      }
      throw new Error(
        `Cannot replay ${sha} (${subject}). No patch was silently dropped.\n${conflicts || 'The patch may be partly present or empty; review it manually.'}\n${error.stderr || error.message}`
      )
    }
    patches.push({
      original: sha,
      result: git(destination, 'rev-parse', 'HEAD'),
      subject,
      status: 'replayed'
    })
  }
  return { sourceSha: git(destination, 'rev-parse', 'HEAD'), patches }
}

export function promotionArgs(plan) {
  for (const field of [
    'sourceSha',
    'previousMain',
    'previousBase',
    'upstreamSha'
  ]) {
    if (!shaPattern.test(plan[field] || '')) throw new Error(`Invalid ${field}`)
  }
  if (!releaseTagPattern.test(plan.version?.tag || ''))
    throw new Error('Invalid release tag')
  return [
    'push',
    '--atomic',
    `--force-with-lease=refs/heads/main:${plan.previousMain}`,
    `--force-with-lease=refs/heads/downstream-base:${plan.previousBase}`,
    'origin',
    `${plan.sourceSha}:refs/heads/main`,
    `${plan.upstreamSha}:refs/heads/downstream-base`,
    `${plan.sourceSha}:refs/tags/${plan.version.tag}`,
    `${plan.previousMain}:refs/tags/downstream-history/${plan.previousMain}`
  ]
}

function api(path) {
  return JSON.parse(run('gh', ['api', path]))
}

function outputs(values) {
  for (const [key, value] of Object.entries(values)) {
    if (/[\r\n]/.test(String(value)))
      throw new Error('Multiline workflow output')
    if (process.env.GITHUB_OUTPUT)
      appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`)
  }
}

export function prepare() {
  const repo = resolve('recipe')
  const destination = resolve('source')
  const out = resolve('plan')
  const recipeSha = git(repo, 'rev-parse', 'HEAD')
  const previousMain = git(repo, 'rev-parse', 'refs/remotes/origin/main')
  const previousBase = git(
    repo,
    'rev-parse',
    'refs/remotes/origin/downstream-base'
  )
  if (process.env.GITHUB_REPOSITORY !== forkRepository)
    throw new Error('This workflow is fork-only')
  if (
    process.env.GITHUB_REF === 'refs/heads/main' &&
    recipeSha !== previousMain
  ) {
    throw new Error(
      'main advanced before preparation; the newer push must be built instead'
    )
  }
  const latest = api(`repos/${upstreamRepository}/releases/latest`)
  if (
    latest.draft ||
    latest.prerelease ||
    !stableTagPattern.test(latest.tag_name)
  ) {
    throw new Error('Upstream latest is not a supported stable release')
  }
  const upstreamTag = latest.tag_name
  git(
    repo,
    'fetch',
    '--no-tags',
    `https://github.com/${upstreamRepository}.git`,
    `refs/tags/${upstreamTag}`
  )
  const upstreamSha = git(repo, 'rev-parse', 'FETCH_HEAD^{commit}')
  const baseVersion = JSON.parse(
    git(repo, 'show', `${previousBase}:package.json`)
  ).version
  const nextCore = upstreamTag.replace(/^v/, '')
  const targetVersion = JSON.parse(
    git(repo, 'show', `${upstreamSha}:package.json`)
  ).version
  if (targetVersion !== nextCore)
    throw new Error('Upstream release tag and package version disagree')
  const oldParts = baseVersion.split('.').map(Number)
  const newParts = nextCore.split('.').map(Number)
  for (let i = 0; i < 3; i++) {
    if (newParts[i] > oldParts[i]) break
    if (newParts[i] < oldParts[i])
      throw new Error('Refusing an upstream version downgrade')
  }
  const releases = JSON.parse(
    run('gh', [
      'api',
      '--paginate',
      '--slurp',
      `repos/${forkRepository}/releases?per_page=100`
    ])
  ).flat()
  const published = releases.filter(
    (r) => !r.draft && releaseTagPattern.test(r.tag_name)
  )
  if (
    baseVersion === nextCore &&
    previousBase !== upstreamSha &&
    published.some((r) => r.tag_name.startsWith(`${upstreamTag}-`))
  ) {
    throw new Error(
      'An already-used upstream release tag moved; review the baseline manually'
    )
  }
  const bootstrap =
    previousBase === 'e95e407a5340b4c3993fcc8fb8c4d3faeec9bcfb' &&
    published.length === 0
  if (
    previousBase !== upstreamSha &&
    !ancestor(repo, previousBase, upstreamSha) &&
    !(bootstrap && ancestor(repo, upstreamSha, previousBase))
  ) {
    throw new Error(
      'Upstream history rewound or diverged; manual review required'
    )
  }
  const alreadyBuilt = published.some((r) => {
    if (!r.tag_name.startsWith(`${upstreamTag}-`)) return false
    return (
      git(repo, 'rev-parse', `refs/tags/${r.tag_name}^{commit}`) === recipeSha
    )
  })
  const feed = releases.find(
    (r) => r.tag_name === 'downstream-feed' && !r.draft
  )
  const fullyPublished = feed?.body?.includes(`\nsource_sha=${recipeSha}\n`)
  if (
    previousBase === upstreamSha &&
    alreadyBuilt &&
    fullyPublished &&
    process.env.FORCE_BUILD !== 'true'
  ) {
    outputs({ needed: 'false' })
    if (process.env.GITHUB_STEP_SUMMARY)
      appendFileSync(
        process.env.GITHUB_STEP_SUMMARY,
        `Checked upstream at ${new Date().toISOString()}: ${upstreamTag}; current main already has a published build.\n`
      )
    return
  }
  mkdirSync(out)
  const { sourceSha, patches } = replaySeries(
    repo,
    previousBase,
    recipeSha,
    upstreamSha,
    destination
  )
  const version = nextVersion(
    upstreamTag,
    berlinDate(),
    git(repo, 'tag', '--list').split('\n')
  )
  const plan = {
    repository: forkRepository,
    recipeSha,
    previousMain,
    previousBase,
    upstreamTag,
    upstreamSha,
    sourceSha,
    version,
    patches,
    runId: process.env.GITHUB_RUN_ID,
    attempt: process.env.GITHUB_RUN_ATTEMPT
  }
  writeJson(join(out, 'plan.json'), plan)
  git(repo, 'update-ref', 'refs/heads/downstream-candidate', sourceSha)
  git(
    repo,
    'bundle',
    'create',
    join(out, 'source.bundle'),
    'refs/heads/downstream-candidate',
    `^${previousBase}`
  )
  outputs({ needed: 'true', source_sha: sourceSha, release_tag: version.tag })
  console.log(JSON.stringify(plan, null, 2))
  if (process.env.GITHUB_STEP_SUMMARY)
    appendFileSync(
      process.env.GITHUB_STEP_SUMMARY,
      `## Downstream candidate\n\nUpstream: ${upstreamTag} (${upstreamSha})\n\nRelease: ${version.tag}\n\nSource: ${sourceSha}\n\n` +
        patches.map((p) => `- ${p.subject}: ${p.status}`).join('\n') +
        '\n'
    )
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    prepare()
  } catch (error) {
    console.error(error.stack)
    process.exitCode = 1
  }
}
