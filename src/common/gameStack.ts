import type { GameInfo } from './types'

/** Store IDs are only unique within their runner. */
export function getGameIdentity(
  game: Pick<GameInfo, 'runner' | 'app_name'>
): string {
  return JSON.stringify([game.runner, game.app_name])
}

/** Keep edition names, sequel numbers and accents: this is not fuzzy matching. */
function normalizeStackTitle(title: string): string {
  return title
    .replace(/[™®©]/g, '')
    .normalize('NFKC')
    .toLowerCase()
    .replace(/['‘’]/g, '')
    .replace(/[:\-‐‑‒–—]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * Group an already filtered library without changing its order or game objects.
 * Sideloads, blank titles and ambiguous same-store matches stay separate.
 */
export function groupGameCopies(
  library: readonly GameInfo[],
  onlyInstalled = false
): GameInfo[][] {
  const seen = new Set<string>()
  const games = library.filter((game) => {
    if (game.runner !== 'sideload' && game.install.is_dlc) return false
    if (onlyInstalled && !game.is_installed) return false

    const identity = getGameIdentity(game)
    if (seen.has(identity)) return false
    seen.add(identity)
    return true
  })

  const candidates = new Map<string, GameInfo[]>()
  for (const game of games) {
    if (game.runner === 'sideload') continue
    // Use the store title, not a user-supplied display-name override.
    const title = normalizeStackTitle(game.title)
    if (!title) continue
    const copies = candidates.get(title)
    if (copies) copies.push(game)
    else candidates.set(title, [game])
  }

  const stackable = new Map<string, GameInfo[]>()
  for (const [title, copies] of candidates) {
    if (
      copies.length > 1 &&
      new Set(copies.map(({ runner }) => runner)).size === copies.length
    ) {
      stackable.set(title, copies)
    }
  }

  const result: GameInfo[][] = []
  const emitted = new Set<string>()
  for (const game of games) {
    const title = normalizeStackTitle(game.title)
    const copies = game.runner === 'sideload' ? undefined : stackable.get(title)
    if (!copies) {
      result.push([game])
    } else if (!emitted.has(title)) {
      result.push(copies)
      emitted.add(title)
    }
  }
  return result
}

/** Keep running/download operations visible, then prefer an installed copy. */
export function getGameStackRepresentative(
  copies: readonly GameInfo[],
  activeGames: ReadonlySet<string> = new Set()
): GameInfo | undefined {
  return (
    copies.find((game) => activeGames.has(getGameIdentity(game))) ??
    copies.find((game) => game.is_installed) ??
    copies[0]
  )
}
