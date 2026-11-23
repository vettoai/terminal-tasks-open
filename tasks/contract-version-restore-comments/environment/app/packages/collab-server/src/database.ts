import pg from 'pg'

export const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL || 'postgres://contracts:contracts-local@127.0.0.1:5432/contracts' })
