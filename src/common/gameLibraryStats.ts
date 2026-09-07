import type { GameInfo, Runner } from './types'
import { groupGameCopies } from './gameStack'

export interface GameLibraryStats {
  games: number
  copies: number
  multiStoreGames: number
  extraCopies: number
  copiesByRunner: Record<Runner, number>
}

/** Summarize the current view with exactly the same identity rules as its cards. */
export function getGameLibraryStats(
  library: readonly GameInfo[]
): GameLibraryStats {
  const stacks = groupGameCopies(library)
  const copiesByRunner: Record<Runner, number> = {
    legendary: 0,
    gog: 0,
    nile: 0,
    zoom: 0,
    sideload: 0
  }
  let copies = 0
  let multiStoreGames = 0

  for (const stack of stacks) {
    copies += stack.length
    if (stack.length > 1) multiStoreGames++
    for (const game of stack) copiesByRunner[game.runner]++
  }

  return {
    games: stacks.length,
    copies,
    multiStoreGames,
    extraCopies: copies - stacks.length,
    copiesByRunner
  }
}
