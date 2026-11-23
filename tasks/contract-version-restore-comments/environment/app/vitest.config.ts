import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({ test: { pool: 'forks', maxWorkers: 2, minWorkers: 1, exclude: [...configDefaults.exclude, 'tests/browser/**'] } })
