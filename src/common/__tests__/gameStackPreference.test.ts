import type { GameInfo } from '../types'
import { groupGameCopies } from '../gameStack'

function game(
  runner: GameInfo['runner'],
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
const epic = game('legendary', 'epic')
const gog = game('gog', 'gog')
const amazon = game('nile', 'amazon')

describe('optional game-copy stacking', () => {
  it('keeps stacking enabled for existing callers', () => {
    expect(groupGameCopies([epic, gog])).toEqual([[epic, gog]])
  })
  it('preserves original interleaved order when disabled', () => {
    const other = game('legendary', 'other', 'Other')
    expect(groupGameCopies([epic, other, gog, amazon], false, false)).toEqual([
      [epic],
      [other],
      [gog],
      [amazon]
    ])
  })
  it('still excludes DLC and repeated records', () => {
    const dlc = game('gog', 'dlc', 'Other', { install: { is_dlc: true } })
    expect(groupGameCopies([epic, dlc, gog, epic], false, false)).toEqual([
      [epic],
      [gog]
    ])
  })
  it('respects installed-only before displaying individual copies', () => {
    const installed = { ...gog, is_installed: true }
    expect(groupGameCopies([epic, installed], true, false)).toEqual([
      [installed]
    ])
  })
  it('preserves sideloads and store-scoped IDs', () => {
    const copies = [
      game('legendary', 'same'),
      game('gog', 'same'),
      game('sideload', 'same')
    ]
    expect(groupGameCopies(copies, false, false)).toEqual(
      copies.map((copy) => [copy])
    )
  })
  it('does not mutate the library when disabled and re-enabled', () => {
    const library = Object.freeze([
      Object.freeze({ ...epic }),
      Object.freeze({ ...gog })
    ])
    expect(groupGameCopies(library, false, false)).toEqual([[epic], [gog]])
    expect(groupGameCopies(library, false, true)).toEqual([[epic, gog]])
    expect(library).toEqual([epic, gog])
  })
  it('handles an empty or excluded library in either mode', () => {
    expect(groupGameCopies([], false, false)).toEqual([])
    expect(groupGameCopies([epic], true, false)).toEqual([])
  })
})
