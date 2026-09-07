import type { GameInfo, Runner } from '../types'
import { getGameLibraryStats } from '../gameLibraryStats'
import { groupGameCopies } from '../gameStack'

function game(
  runner: Runner,
  app_name: string,
  title = 'Example',
  overrides: Partial<GameInfo> = {}
): GameInfo {
  return {
    runner,
    app_name,
    title,
    art_cover: '',
    art_square: '',
    install: {},
    is_installed: false,
    canRunOffline: true,
    ...overrides
  }
}

const emptySources = { legendary: 0, gog: 0, nile: 0, zoom: 0, sideload: 0 }

describe('getGameLibraryStats', () => {
  it('counts a game on three stores once, with two extra copies', () => {
    expect(getGameLibraryStats([
      game('legendary', 'epic'), game('gog', 'gog'), game('nile', 'amazon')
    ])).toEqual({
      games: 1, copies: 3, multiStoreGames: 1, extraCopies: 2,
      copiesByRunner: { ...emptySources, legendary: 1, gog: 1, nile: 1 }
    })
  })

  it('reconciles 400 Epic and 100 Amazon copies with 10 cross-store duplicates', () => {
    const epic = Array.from({ length: 400 }, (_, i) => game('legendary', `e${i}`, `Epic ${i}`))
    const amazon = Array.from({ length: 100 }, (_, i) => game('nile', `a${i}`, i < 10 ? `Epic ${i}` : `Amazon ${i}`))
    expect(getGameLibraryStats([...epic, ...amazon])).toEqual({
      games: 490, copies: 500, multiStoreGames: 10, extraCopies: 10,
      copiesByRunner: { ...emptySources, legendary: 400, nile: 100 }
    })
  })

  it('counts only copies supplied by the current store, search or visibility filters', () => {
    const library = [game('legendary', 'same-id'), game('gog', 'same-id'), game('gog', 'other', 'Other')]
    const selected = library.filter((item) => item.runner === 'gog' && item.title === 'Example')
    expect(getGameLibraryStats(selected)).toEqual({
      games: 1, copies: 1, multiStoreGames: 0, extraCopies: 0,
      copiesByRunner: { ...emptySources, gog: 1 }
    })
  })

  it('does not count an uninstalled copy excluded from the current view', () => {
    const library = [game('legendary', 'e'), game('gog', 'g', 'Example', { is_installed: true })]
    expect(getGameLibraryStats(library.filter((item) => item.is_installed))).toMatchObject({
      games: 1, copies: 1, extraCopies: 0, copiesByRunner: { ...emptySources, gog: 1 }
    })
  })

  it('excludes DLC and repeated records but preserves store-scoped IDs', () => {
    const epic = game('legendary', 'same')
    expect(getGameLibraryStats([
      epic, { ...epic }, game('gog', 'same'),
      game('nile', 'dlc', 'Example', { install: { is_dlc: true } })
    ])).toEqual({
      games: 1, copies: 2, multiStoreGames: 1, extraCopies: 1,
      copiesByRunner: { ...emptySources, legendary: 1, gog: 1 }
    })
  })

  it('keeps editions and ambiguous same-store matches separate', () => {
    const library = [game('legendary', 'e'), game('gog', 'g1'), game('gog', 'g2'), game('nile', 'remaster', 'Example Remastered')]
    expect(getGameLibraryStats(library)).toMatchObject({ games: 4, copies: 4, multiStoreGames: 0, extraCopies: 0 })
  })

  it('supports Zoom while treating sideloads as independent sources', () => {
    expect(getGameLibraryStats([
      game('gog', 'g'), game('zoom', 'z'), game('sideload', 's', 'Example', { install: { is_dlc: true } })
    ])).toEqual({
      games: 2, copies: 3, multiStoreGames: 1, extraCopies: 1,
      copiesByRunner: { ...emptySources, gog: 1, zoom: 1, sideload: 1 }
    })
  })

  it('uses the same normalized store titles as the rendered stacks', () => {
    const library = [game('legendary', 'e', '  GAME: Part-One™ '), game('gog', 'g', 'Game – Part One'), game('nile', 'other', 'Other', { overrides: { title: 'Game – Part One' } })]
    expect(getGameLibraryStats(library)).toMatchObject({ games: 2, copies: 3, extraCopies: 1 })
  })

  it('returns zeroes for an empty view', () => {
    expect(getGameLibraryStats([])).toEqual({ games: 0, copies: 0, multiStoreGames: 0, extraCopies: 0, copiesByRunner: emptySources })
  })

  it('does not mutate records and reconciles every total with the card groups', () => {
    const library = Object.freeze([
      Object.freeze(game('legendary', 'e')),
      Object.freeze(game('gog', 'g')),
      Object.freeze(game('nile', 'a', 'Other'))
    ])
    const before = JSON.stringify(library)
    const stats = getGameLibraryStats(library)
    expect(stats.games).toBe(groupGameCopies(library).length)
    expect(stats.copies).toBe(Object.values(stats.copiesByRunner).reduce((sum, value) => sum + value, 0))
    expect(stats.games + stats.extraCopies).toBe(stats.copies)
    expect(JSON.stringify(library)).toBe(before)
  })
})
