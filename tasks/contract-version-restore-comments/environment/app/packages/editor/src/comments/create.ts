import * as Y from 'yjs'
import type { HocuspocusProvider } from '@hocuspocus/provider'
import { clauses, clauseText } from '../document'
import { httpBase } from '../config'

export async function createComment(provider: HocuspocusProvider, clauseId: string, from: number, to: number) {
  const clause = clauses(provider.document).find(item => item.getAttribute('clauseId') === clauseId)
  if (!clause) throw new Error('Unknown clause')
  const text = clauseText(clause)
  const bytes = (value: Uint8Array) => btoa(Array.from(value, byte => String.fromCharCode(byte)).join(''))
  const response = await fetch(`${httpBase()}/contracts/${encodeURIComponent(provider.configuration.name)}/comments`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ clause_id: clauseId, quoted_text: text.toString().slice(from, to),
      start_pos: bytes(Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(text, from, 0))),
      end_pos: bytes(Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(text, to, -1))),
      context: { ydoc: bytes(Y.encodeStateAsUpdate(provider.document)),
        start_pos: bytes(Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(text, from, 0))),
        end_pos: bytes(Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(text, to, -1))) } }),
  })
  if (!response.ok) throw new Error(`Comment unavailable: ${response.status}`)
  return response.json()
}
