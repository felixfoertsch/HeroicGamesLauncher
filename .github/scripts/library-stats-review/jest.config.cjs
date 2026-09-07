module.exports = {
  rootDir: '../../..',
  roots: ['<rootDir>/.github/scripts/library-stats-review'],
  testMatch: ['**/*.test.cjs'],
  testEnvironment: require.resolve('jest-environment-jsdom', {
    paths: [process.env.RUNNER_TEMP + '/library-stats-dom']
  }),
  transform: { '^.+\\.tsx?$': ['ts-jest', { diagnostics: false }] },
  modulePaths: ['<rootDir>/src'],
  moduleNameMapper: {
    '\\.css$': '<rootDir>/.github/scripts/library-stats-review/style.cjs'
  }
}
