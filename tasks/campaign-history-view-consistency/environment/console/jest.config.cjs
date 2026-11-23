module.exports = {
  preset: 'ts-jest', testEnvironment: 'jsdom', testMatch: ['**/__tests__/**/*.test.ts'],
  transform: { '^.+\\.tsx?$': ['ts-jest', { tsconfig: { module: 'commonjs', jsx: 'react-jsx' } }] }
};
