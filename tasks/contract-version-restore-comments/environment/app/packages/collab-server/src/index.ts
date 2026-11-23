import { Server } from '@hocuspocus/server'
import { Database } from '@hocuspocus/extension-database'
import { randomUUID } from 'node:crypto'
import { pool } from './database'
import type { CommentCreatePayload } from '../../editor/src/types'

const server = Server.configure({
  port: Number(process.env.PORT || 1234),
  yDocOptions: { gc: false, gcFilter: () => false },
  debounce: 100,
  maxDebounce: 500,
  extensions: [new Database({
    fetch: async ({ documentName }) => (await pool.query('SELECT ydoc FROM contracts WHERE id=$1', [documentName])).rows[0]?.ydoc,
    store: async ({ documentName, state }) => {
      await pool.query('INSERT INTO contracts(id,ydoc) VALUES($1,$2) ON CONFLICT(id) DO UPDATE SET ydoc=EXCLUDED.ydoc', [documentName, Buffer.from(state)])
    },
  })],
  async onLoadDocument({ document }) { document.gc = false },
  async onRequest({ request, response }) {
    response.setHeader('Access-Control-Allow-Origin', '*')
    response.setHeader('Access-Control-Allow-Headers', 'content-type')
    response.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    if (request.method === 'OPTIONS') { response.writeHead(204).end(); throw null }
    const path = new URL(request.url || '/', 'http://127.0.0.1').pathname
    const match = path.match(/^\/contracts\/([^/]+)\/(versions|comments)(?:\/([^/]+))?$/)
    const send = (status: number, body: any) => { response.writeHead(status, { 'Content-Type': 'application/json' }); response.end(JSON.stringify(body)) }
    if (path === '/health') { send(200, { status: 'ok' }); throw null }
    if (!match) { send(404, { error: 'Not found' }); throw null }
    const contractId = decodeURIComponent(match[1])
    if (request.method === 'GET' && match[2] === 'versions' && match[3]) {
      const version = (await pool.query('SELECT * FROM versions WHERE id=$1 AND contract_id=$2', [decodeURIComponent(match[3]), contractId])).rows[0]
      if (!version) send(404, { error: 'Unknown version' })
      else send(200, version.kind === 'snapshot' ? { kind: 'snapshot', snapshot: version.snapshot.toString('base64') } : { kind: 'json', json: version.json })
    } else if (request.method === 'GET') {
      const table = match[2] === 'versions' ? 'versions' : 'comments'
      const rows = (await pool.query(`SELECT * FROM ${table} WHERE contract_id=$1 ORDER BY created_at,id`, [contractId])).rows
      send(200, rows.map(row => table === 'comments' ? { ...row, start_pos: row.start_pos.toString('base64'), end_pos: row.end_pos.toString('base64') } : { ...row, snapshot: row.snapshot?.toString('base64') }))
    } else if (request.method === 'POST' && match[2] === 'comments') {
      let body = ''
      for await (const chunk of request) { body += chunk; if (body.length > 16 * 1024 * 1024) throw new Error('Request too large') }
      const input = JSON.parse(body) as CommentCreatePayload
      const id = randomUUID()
      const connection = await pool.connect()
      let row
      try {
        await connection.query('BEGIN')
        row = (await connection.query('INSERT INTO comments VALUES($1,$2,$3,$4,$5,$6,CURRENT_TIMESTAMP) RETURNING *', [id, contractId, input.clause_id, input.quoted_text, Buffer.from(input.start_pos, 'base64'), Buffer.from(input.end_pos, 'base64')])).rows[0]
        await connection.query('INSERT INTO comment_contexts VALUES($1,$2,$3,$4)', [id, Buffer.from(input.context.ydoc, 'base64'), Buffer.from(input.context.start_pos, 'base64'), Buffer.from(input.context.end_pos, 'base64')])
        await connection.query('COMMIT')
      } catch (error) { await connection.query('ROLLBACK'); throw error }
      finally { connection.release() }
      send(201, { ...row, start_pos: row.start_pos.toString('base64'), end_pos: row.end_pos.toString('base64') })
    } else send(405, { error: 'Method not allowed' })
    throw null
  },
})

await server.listen()
async function shutdown() { await server.destroy(); await pool.end(); process.exit(0) }
process.on('SIGTERM', shutdown)
process.on('SIGINT', shutdown)
