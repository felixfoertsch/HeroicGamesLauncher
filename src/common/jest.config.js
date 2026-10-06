module.exports = {
  displayName: 'Common',
  rootDir: '../..',
  roots: ['<rootDir>/src/common'],
  testEnvironment: 'node',
  testMatch: ['**/__tests__/**/*.test.ts'],
  transform: {
    '^.+\\.tsx?$': 'ts-jest'
  },
  modulePaths: ['<rootDir>/src']
}
