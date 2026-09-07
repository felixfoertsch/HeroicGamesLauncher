import type { GameInfo, Status } from '../types'
import {
  getActiveGameIdentities,
  getGameIdentity,
  getGameStackRepresentative,
  groupGameCopies
} from '../gameStack'

function game(
  runner: GameInfo['runner'],
  app_name: string,
  title = 'Example Game',
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

describe('groupGameCopies', () => {
  it('stacks Epic and GOG copies while preserving their store IDs', () => {
    const epic = game('legendary', 'epic-id')
    const gog = game('gog', 'gog-id')
    expect(groupGameCopies([epic, gog])).toEqual([[epic, gog]])
  })

  it('supports three or more stores, not just Epic and GOG', () => {
    const copies = [
      game('legendary', 'epic'),
      game('gog', 'gog'),
      game('nile', 'amazon'),
      game('zoom', 'zoom')
    ]
    expect(groupGameCopies(copies)).toEqual([copies])
  })

  it('normalizes case, whitespace, Unicode and trademark marks', () => {
    const epic = game('legendary', 'epic', '  EXAMPLE\u00a0 Game™  ')
    const gog = game('gog', 'gog', 'Example Game®')
    const amazon = game('nile', 'amazon', 'Ｅｘａｍｐｌｅ Game©')
    expect(groupGameCopies([epic, gog, amazon])).toEqual([[epic, gog, amazon]])
  })

  it('normalizes typographic apostrophes, colons and hyphens', () => {
    const epic = game('legendary', 'epic', 'Hero’s Quest: Part-One')
    const gog = game('gog', 'gog', "Hero's Quest – Part One")
    expect(groupGameCopies([epic, gog])).toEqual([[epic, gog]])
  })

  it('preserves accents and normalizes canonically equivalent Unicode', () => {
    const epic = game('legendary', 'epic', 'Café')
    const gog = game('gog', 'gog', 'Cafe\u0301')
    const other = game('nile', 'other', 'Cafe')
    expect(groupGameCopies([epic, gog, other])).toEqual([[epic, gog], [other]])
  })

  it('does not merge sequels, remasters, demos or different editions', () => {
    const copies = [
      game('legendary', 'base', 'Game'),
      game('gog', 'sequel', 'Game 2'),
      game('nile', 'remaster', 'Game Remastered'),
      game('gog', 'goty', 'Game Game of the Year Edition'),
      game('zoom', 'deluxe', 'Game Deluxe Edition'),
      game('nile', 'demo', 'Game Demo')
    ]
    expect(groupGameCopies(copies)).toEqual(copies.map((copy) => [copy]))
  })

  it('keeps sideloaded games independent of matching store titles', () => {
    const epic = game('legendary', 'epic')
    const sideload = game('sideload', 'custom')
    const gog = game('gog', 'gog')
    expect(groupGameCopies([epic, sideload, gog])).toEqual([
      [epic, gog],
      [sideload]
    ])
  })

  it('does not combine two distinct copies from the same store', () => {
    const first = game('gog', 'first')
    const second = game('gog', 'second')
    expect(groupGameCopies([first, second])).toEqual([[first], [second]])
  })

  it('leaves ambiguous same-store matches separate, in original order', () => {
    const first = game('gog', 'first')
    const other = game('nile', 'other', 'Other Game')
    const epic = game('legendary', 'epic')
    const second = game('gog', 'second')
    expect(groupGameCopies([first, other, epic, second])).toEqual([
      [first],
      [other],
      [epic],
      [second]
    ])
  })

  it('deduplicates repeated records before counting', () => {
    const epic = game('legendary', 'same-id')
    const gog = game('gog', 'same-id')
    expect(groupGameCopies([epic, { ...epic }, gog])).toEqual([[epic, gog]])
  })

  it('excludes DLC without suppressing the base game', () => {
    const epic = game('legendary', 'epic')
    const dlc = game('gog', 'dlc', 'Example Game', {
      install: { is_dlc: true }
    })
    const gog = game('gog', 'base')
    expect(groupGameCopies([dlc, epic, gog])).toEqual([[epic, gog]])
  })

  it('applies the installed-only filter before counting copies', () => {
    const epic = game('legendary', 'epic')
    const gog = game('gog', 'gog', 'Example Game', { is_installed: true })
    expect(groupGameCopies([epic, gog], true)).toEqual([[gog]])
    expect(groupGameCopies([epic], true)).toEqual([])
  })

  it('counts only copies supplied by the current library filters', () => {
    const epic = game('legendary', 'epic')
    const gog = game('gog', 'gog')
    const library = [epic, gog]
    expect(
      groupGameCopies(library.filter((copy) => copy.runner === 'gog'))
    ).toEqual([[gog]])
  })

  it('preserves first-occurrence order without mutating input', () => {
    const epic = Object.freeze(game('legendary', 'epic'))
    const other = Object.freeze(game('gog', 'other', 'Other Game'))
    const gog = Object.freeze(game('gog', 'gog'))
    const library = Object.freeze([epic, other, gog])
    expect(groupGameCopies(library)).toEqual([[epic, gog], [other]])
    expect(library).toEqual([epic, other, gog])
    expect(groupGameCopies(library)[0][0]).toBe(epic)
  })

  it('matches store titles rather than user display-name overrides', () => {
    const epic = game('legendary', 'epic', 'Example Game', {
      overrides: { title: 'My custom name' }
    })
    const gog = game('gog', 'gog')
    const other = game('nile', 'other', 'Other Game', {
      overrides: { title: 'Example Game' }
    })
    expect(groupGameCopies([epic, gog, other])).toEqual([[epic, gog], [other]])
  })

  it('leaves empty and punctuation-only titles separate', () => {
    const copies = [
      game('legendary', 'empty', ''),
      game('gog', 'empty', '  '),
      game('legendary', 'punctuation', '™:—'),
      game('gog', 'punctuation', '® -')
    ]
    expect(groupGameCopies(copies)).toEqual(copies.map((copy) => [copy]))
  })

  it('handles empty input', () => {
    expect(groupGameCopies([])).toEqual([])
  })
})

describe('getGameStackRepresentative', () => {
  it('prefers an installed copy', () => {
    const epic = game('legendary', 'epic')
    const gog = game('gog', 'gog', 'Example Game', { is_installed: true })
    expect(getGameStackRepresentative([epic, gog])).toBe(gog)
  })

  it('keeps an active copy visible ahead of an idle installed copy', () => {
    const epic = game('legendary', 'epic', 'Example Game', {
      is_installed: true
    })
    const gog = game('gog', 'gog')
    expect(
      getGameStackRepresentative([epic, gog], new Set([getGameIdentity(gog)]))
    ).toBe(gog)
  })

  it('uses both runner and app ID when selecting the active copy', () => {
    const epic = game('legendary', 'same-id')
    const gog = game('gog', 'same-id')
    expect(
      getGameStackRepresentative([epic, gog], new Set([getGameIdentity(gog)]))
    ).toBe(gog)
  })

  it('preserves input order when multiple copies have equal priority', () => {
    const epic = game('legendary', 'epic', 'Example Game', {
      is_installed: true
    })
    const gog = game('gog', 'gog', 'Example Game', { is_installed: true })
    expect(getGameStackRepresentative([epic, gog])).toBe(epic)
    expect(getGameStackRepresentative([gog, epic])).toBe(gog)
  })

  it('falls back to the first copy when none is installed', () => {
    const epic = game('legendary', 'epic')
    const gog = game('gog', 'gog')
    expect(getGameStackRepresentative([epic, gog])).toBe(epic)
  })

  it('returns undefined for an empty stack', () => {
    expect(getGameStackRepresentative([])).toBeUndefined()
  })
})

describe('active stack copies', () => {
  const epic = game('legendary', 'same-id', 'Example Game', {
    is_installed: true
  })
  const gog = game('gog', 'same-id')

  it.each<Status>([
    'installing',
    'importing',
    'updating',
    'launching',
    'playing',
    'uninstalling',
    'repairing',
    'moving',
    'queued',
    'syncing-saves',
    'redist',
    'extracting',
    'winetricks'
  ])('keeps the %s copy visible ahead of an idle installed copy', (status) => {
    const activeGames = getActiveGameIdentities([
      { appName: epic.app_name, runner: epic.runner, status: 'installed' },
      { appName: gog.app_name, runner: gog.runner, status }
    ])
    expect([...activeGames]).toEqual([getGameIdentity(gog)])
    expect(getGameStackRepresentative([epic, gog], activeGames)).toBe(gog)
  })

  it.each<Status>([
    'done',
    'canceled',
    'error',
    'notAvailable',
    'notSupportedGame',
    'notInstalled',
    'installed'
  ])('returns to the installed copy after status %s', (status) => {
    const activeGames = getActiveGameIdentities([
      { appName: gog.app_name, runner: gog.runner, status }
    ])
    expect(activeGames.size).toBe(0)
    expect(getGameStackRepresentative([epic, gog], activeGames)).toBe(epic)
  })

  it('ignores runner-less events and deduplicates repeated events', () => {
    const event = {
      appName: gog.app_name,
      runner: gog.runner,
      status: 'extracting' as const
    }
    expect([
      ...getActiveGameIdentities([
        { appName: epic.app_name, status: 'moving' },
        event,
        event
      ])
    ]).toEqual([getGameIdentity(gog)])
    expect(getActiveGameIdentities([]).size).toBe(0)
  })
})
