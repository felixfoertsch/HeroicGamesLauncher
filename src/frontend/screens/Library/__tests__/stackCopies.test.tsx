import { act, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import userEvent from '@testing-library/user-event'
import type { GameInfo } from 'common/types'
import type { ContextType } from 'frontend/types'
import ContextProvider from 'frontend/state/ContextProvider'
import Library from '..'

jest.mock('frontend/state/ContextProvider', () => ({
  __esModule: true,
  default: jest.requireActual<typeof import('react')>('react').createContext({})
}))
jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en', resolvedLanguage: 'en' },
    t: (key: string, fallback?: string | Record<string, unknown>) => {
      const text =
        typeof fallback === 'string'
          ? fallback
          : String(fallback?.defaultValue ?? key)
      return text.replace(/{{(\w+)}}/g, (_, name: string) =>
        String(typeof fallback === 'object' ? (fallback[name] ?? '') : '')
      )
    }
  })
}))
jest.mock('frontend/components/UI', () => ({
  Header: () => null,
  UpdateComponent: () => null
}))
jest.mock('frontend/components/UI/ErrorComponent', () => () => null)
jest.mock('frontend/hooks/hasHelp', () => ({ hasHelp: jest.fn() }))
jest.mock('frontend/state/InstallGameModal', () => ({
  openInstallGameModal: jest.fn()
}))
jest.mock('../components/RecentlyPlayed', () => () => null)
jest.mock('../components/CategoriesManager', () => () => null)
jest.mock('../components/LibraryTour', () => () => null)
jest.mock('../components/AlphabetFilter', () => () => null)
jest.mock('../components/EmptyLibrary', () => () => null)
jest.mock('../components/AddGameButton', () => () => null)
jest.mock('frontend/helpers/library', () => ({
  epicCategories: ['all', 'legendary'],
  gogCategories: ['all', 'gog'],
  amazonCategories: ['all', 'nile'],
  sideloadedCategories: ['all', 'sideload'],
  zoomCategories: ['all', 'zoom'],
  normalizeTitle: (title: string) => title.toLowerCase()
}))
jest.mock(
  '../components/GameCard',
  () =>
    function MockGameCard({
      gameInfo,
      copies
    }: {
      gameInfo: GameInfo
      copies: GameInfo[]
    }) {
      return (
        <div
          data-testid="game-card"
          data-store={gameInfo.runner}
          data-copies={copies.length}
          data-app-name={gameInfo.app_name}
          data-invisible="true"
        >
          {gameInfo.title}
        </div>
      )
    }
)
// Exercise actual Library context wiring, without unrelated toolbar controls.
jest.mock('frontend/components/UI/ActionIcons', () => {
  const { useContext } = jest.requireActual<typeof import('react')>('react')
  const { default: LibraryContext } =
    jest.requireActual<typeof import('../LibraryContext')>('../LibraryContext')
  return function Filters() {
    const context = useContext(LibraryContext)
    return (
      <>
        <button
          onClick={() =>
            context.setStoresFilters({
              legendary: true,
              gog: false,
              nile: false,
              sideload: false,
              zoom: false
            })
          }
        >
          Only Epic
        </button>
        <button onClick={() => context.setShowInstalledOnly(true)}>
          Installed only
        </button>
        <button onClick={() => context.handleLayout('list')}>
          List layout
        </button>
        <button onClick={() => context.handleSearch('Unique')}>
          Search unique
        </button>
        <button onClick={() => context.setShowFavourites(true)}>
          Favourites only
        </button>
      </>
    )
  }
})
function game(
  runner: GameInfo['runner'],
  app_name: string,
  title = 'Example',
  is_installed = false
): GameInfo {
  return {
    runner,
    app_name,
    title,
    is_installed,
    canRunOffline: true,
    install: {},
    art_cover: '',
    art_square: ''
  }
}
const epic = game('legendary', 'epic', 'Example', true)
const unique = game('legendary', 'unique', 'Unique')
const gog = game('gog', 'gog')
const amazon = game('nile', 'amazon')
const side = game('sideload', 'local')
function context(overrides: Partial<ContextType> = {}): ContextType {
  return {
    libraryStatus: [],
    refreshing: false,
    refreshingInTheBackground: false,
    epic: { library: [epic, unique], username: 'test' },
    gog: { library: [gog], username: 'test' },
    amazon: { library: [amazon], username: 'test', user_id: 'test' },
    zoom: { library: [], enabled: false },
    sideloadedLibrary: [side],
    favouriteGames: { list: [] },
    hiddenGames: { list: [] },
    libraryTopSection: 'disabled',
    platform: 'linux',
    currentCustomCategories: [],
    customCategories: { list: {} },
    gameUpdates: [],
    allTilesInColor: false,
    titlesAlwaysVisible: false,
    activeController: '',
    ...overrides
  } as ContextType
}
function mount(value = context()) {
  return render(
    <ContextProvider.Provider value={value}>
      <Library />
    </ContextProvider.Provider>
  )
}
function toggle() {
  return screen.getByRole('checkbox', { name: 'Stack copies' })
}
function cards() {
  return screen.getAllByTestId('game-card')
}

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem('showAlphabetFilter', 'false')
  Object.defineProperty(document.body, 'scrollTo', {
    configurable: true,
    value: jest.fn()
  })
  Object.defineProperty(window, 'IntersectionObserver', {
    configurable: true,
    writable: true,
    value: jest.fn(() => ({
      observe: jest.fn(),
      unobserve: jest.fn(),
      disconnect: jest.fn()
    }))
  })
})
afterEach(() => jest.restoreAllMocks())

describe('Stack copies preference', () => {
  it('defaults to enabled and shows one card per matched game', () => {
    mount()
    expect(toggle()).toBeChecked()
    expect(cards()).toHaveLength(3)
    expect(
      cards().filter((card) => card.getAttribute('data-copies') === '3')
    ).toHaveLength(1)
  })
  it('shows separate copies without changing the header total or saved filters', () => {
    mount()
    expect(document.querySelector('.numberOfgames')).toHaveTextContent('3')
    const count = document.querySelector('.numberOfgames')?.textContent
    fireEvent.click(toggle())
    expect(toggle()).not.toBeChecked()
    expect(cards()).toHaveLength(5)
    for (const card of cards()) expect(card).toHaveAttribute('data-copies', '1')
    expect(document.querySelector('.numberOfgames')).toHaveTextContent(count!)
    expect(localStorage.getItem('storesFilters')).toBeNull()
  })
  it('remembers the preference after the library unmounts and remounts', () => {
    const view = mount()
    fireEvent.click(toggle())
    expect(localStorage.getItem('stack_copies')).toBe('false')
    view.unmount()
    mount()
    expect(toggle()).not.toBeChecked()
    expect(cards()).toHaveLength(5)
    fireEvent.click(toggle())
    expect(localStorage.getItem('stack_copies')).toBe('true')
    expect(cards()).toHaveLength(3)
  })
  it('restores an explicitly saved off preference at startup', () => {
    localStorage.setItem('stack_copies', 'false')
    mount()
    expect(toggle()).not.toBeChecked()
    expect(cards()).toHaveLength(5)
  })
  it('can be switched using Space while keyboard-focused', async () => {
    const user = userEvent.setup()
    mount()
    act(() => toggle().focus())
    await user.keyboard(' ')
    expect(toggle()).not.toBeChecked()
    expect(cards()).toHaveLength(5)
  })
  it('applies equally to list layout', () => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: 'List layout' }))
    expect(document.querySelector('.gameListLayout')).not.toBeNull()
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(5)
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(3)
  })
  it.each([
    ['Only Epic', 2],
    ['Installed only', 1],
    ['Search unique', 1]
  ] as const)('preserves %s filtering', (button, count) => {
    mount()
    fireEvent.click(screen.getByRole('button', { name: button }))
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(count)
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(count)
  })
  it('toggles the favourites lane together with the main list', () => {
    mount(
      context({
        libraryTopSection: 'favourites',
        favouriteGames: {
          list: [
            { appName: 'epic', title: 'Example' },
            { appName: 'gog', title: 'Example' }
          ],
          add: jest.fn(),
          remove: jest.fn()
        }
      })
    )
    expect(cards()).toHaveLength(4)
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(7)
    fireEvent.click(screen.getByRole('button', { name: 'Favourites only' }))
    expect(cards()).toHaveLength(2)
    fireEvent.click(toggle())
    expect(cards()).toHaveLength(1)
  })
  it('observes newly displayed placeholders and disconnects on unmount', () => {
    const view = mount()
    const observer = jest.mocked(window.IntersectionObserver)
    expect(observer).toHaveBeenCalledTimes(1)
    fireEvent.click(toggle())
    expect(observer).toHaveBeenCalledTimes(2)
    fireEvent.click(toggle())
    expect(observer).toHaveBeenCalledTimes(3)
    view.unmount()
    for (const result of observer.mock.results) {
      const instance = result.value as { disconnect: jest.Mock }
      expect(instance.disconnect).toHaveBeenCalledTimes(1)
    }
  })
})
