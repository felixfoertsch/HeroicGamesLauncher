module.exports = {
  displayName: 'Frontend',
  rootDir: '../..',
  roots: ['<rootDir>/src/frontend'],
  testEnvironment: 'jsdom',
  testMatch: ['**/__tests__/**/*.test.tsx'],
  transform: { '^.+\\.tsx?$': 'ts-jest' },
  modulePaths: ['<rootDir>/src'],
  moduleNameMapper: {
    '\\.(css|scss)$': '<rootDir>/src/frontend/__mocks__/style.js'
  }
}
