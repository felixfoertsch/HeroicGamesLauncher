const React = require('react')
const { render, screen, within, cleanup, waitFor } = require('@testing-library/react')
const userEvent = require('@testing-library/user-event').default
const { createInstance } = require('i18next')
const { I18nextProvider } = require('react-i18next')

jest.mock('frontend/components/UI/ActionIcons', () => ({ __esModule: true, default: () => null }))
jest.mock('frontend/screens/Library/components/AddGameButton', () => ({ __esModule: true, default: () => null }))

const LibraryHeader = require('frontend/screens/Library/components/LibraryHeader').default
let i18n
let user
const game = (runner, app_name, title = 'Example') => ({ runner, app_name, title, art_cover: '', art_square: '', install: {}, is_installed: false, canRunOffline: true })
const threeCopies = [game('legendary', 'e'), game('gog', 'g'), game('nile', 'a')]
const tree = (list) => React.createElement(I18nextProvider, { i18n }, React.createElement(LibraryHeader, { list }))
const value = (tooltip, label) => within(tooltip).getByText(label).nextElementSibling.textContent

beforeEach(async () => {
  i18n = createInstance()
  await i18n.init({ lng: 'en', fallbackLng: 'en', resources: { en: { translation: {} } }, interpolation: { escapeValue: false } })
  user = userEvent.setup()
  jest.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ x: 10, y: 10, top: 10, left: 10, bottom: 40, right: 60, height: 30, width: 50, toJSON: () => ({}) })
})
afterEach(() => { cleanup(); jest.restoreAllMocks() })

it('the actual LibraryHeader displays distinct games rather than store copies', () => {
  render(tree(threeCopies))
  expect(screen.getByRole('button', { name: '1 — show library overview' }).textContent).toBe('1')
  expect(screen.queryByRole('tooltip')).toBeNull()
})

it('opens on hover, reconciles all totals and lets the pointer enter the overview', async () => {
  render(tree(threeCopies))
  const button = screen.getByRole('button')
  await user.hover(button)
  const tooltip = await screen.findByRole('tooltip')
  expect(value(tooltip, 'Unique games')).toBe('1')
  expect(value(tooltip, 'Total copies')).toBe('3')
  expect(value(tooltip, 'Games on multiple stores')).toBe('1')
  expect(value(tooltip, 'Extra copies across stores')).toBe('2')
  for (const store of ['Epic Games', 'GOG', 'Amazon Games']) expect(value(tooltip, store)).toBe('1')
  expect(within(tooltip).queryByText('Zoom Platform')).toBeNull()
  expect(button.getAttribute('aria-describedby')).toBe(tooltip.id)
  await user.hover(tooltip)
  expect(screen.getByRole('tooltip')).toBe(tooltip)
  await user.unhover(tooltip)
  await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull())
})

it('opens for keyboard focus and dismisses with Escape', async () => {
  render(tree(threeCopies))
  await user.tab()
  expect(document.activeElement).toBe(screen.getByRole('button'))
  await screen.findByRole('tooltip')
  await user.keyboard('{Escape}')
  await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull())
})

it('opens on explicit activation and closes when focus leaves', async () => {
  render(React.createElement(I18nextProvider, { i18n }, React.createElement(React.Fragment, null, React.createElement(LibraryHeader, { list: threeCopies }), React.createElement('button', null, 'Outside'))))
  await user.click(screen.getByRole('button', { name: '1 — show library overview' }))
  await screen.findByRole('tooltip')
  await user.click(screen.getByRole('button', { name: 'Outside' }))
  await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull())
})

it('updates an open overview when the current list is filtered', async () => {
  const view = render(tree(threeCopies))
  await user.hover(screen.getByRole('button'))
  await screen.findByRole('tooltip')
  view.rerender(tree([threeCopies[1]]))
  const tooltip = screen.getByRole('tooltip')
  expect(value(tooltip, 'Total copies')).toBe('1')
  expect(value(tooltip, 'Extra copies across stores')).toBe('0')
  expect(value(tooltip, 'GOG')).toBe('1')
  expect(within(tooltip).queryByText('Epic Games')).toBeNull()
  expect(within(tooltip).queryByText('Amazon Games')).toBeNull()
  expect(within(tooltip).getByText('Current view, including search and filters.')).toBeTruthy()
})

it('supports empty views without showing misleading store totals', async () => {
  render(tree([]))
  await user.hover(screen.getByRole('button', { name: '0 — show library overview' }))
  const tooltip = await screen.findByRole('tooltip')
  expect(value(tooltip, 'Unique games')).toBe('0')
  expect(value(tooltip, 'Total copies')).toBe('0')
  expect(within(tooltip).getByText('No games match this view.')).toBeTruthy()
})

it('formats header and detail numbers using the active locale', async () => {
  i18n.addResourceBundle('de', 'translation', { libraryStats: { title: 'Bibliotheksübersicht' } })
  await i18n.changeLanguage('de')
  const list = Array.from({ length: 1234 }, (_, i) => game('gog', `${i}`, `Game ${i}`))
  render(tree(list))
  const button = screen.getByRole('button', { name: '1.234 — show library overview' })
  expect(button.textContent).toBe('1.234')
  await user.hover(button)
  const tooltip = await screen.findByRole('tooltip')
  expect(value(tooltip, 'GOG')).toBe('1.234')
})

it('shows Zoom and sideload counts without merging sideloads into store games', async () => {
  render(tree([game('zoom', 'z'), game('gog', 'g'), game('sideload', 's')]))
  await user.hover(screen.getByRole('button', { name: '2 — show library overview' }))
  const tooltip = await screen.findByRole('tooltip')
  expect(value(tooltip, 'Total copies')).toBe('3')
  expect(value(tooltip, 'Zoom Platform')).toBe('1')
  expect(value(tooltip, 'Sideloaded')).toBe('1')
})
