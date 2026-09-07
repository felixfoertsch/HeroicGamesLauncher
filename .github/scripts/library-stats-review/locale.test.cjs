const React = require('react')
const { render, screen, cleanup } = require('@testing-library/react')
const { createInstance } = require('i18next')
const { I18nextProvider } = require('react-i18next')
const { supportedLanguages } = require('common/languages')
const LibraryStats = require('frontend/screens/Library/components/LibraryHeader/LibraryStats').default

afterEach(cleanup)

it.each(supportedLanguages)('renders valid localized numbers for Heroic locale %s', async (language) => {
  const i18n = createInstance()
  await i18n.init({ lng: language, fallbackLng: false, resources: { [language]: { translation: { libraryStats: { title: 'Statistics' } } } }, interpolation: { escapeValue: false } })
  const stats = { games: 1234, copies: 1234, multiStoreGames: 0, extraCopies: 0, copiesByRunner: { legendary: 0, gog: 1234, nile: 0, zoom: 0, sideload: 0 } }
  render(React.createElement(I18nextProvider, { i18n }, React.createElement(LibraryStats, { stats })))
  expect(screen.getByRole('button').textContent).toBe(new Intl.NumberFormat(language.replace(/_/g, '-')).format(1234))
})
