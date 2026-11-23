export interface CommentRow {
  id: string
  contract_id: string
  clause_id: string
  quoted_text: string
  start_pos: Uint8Array
  end_pos: Uint8Array
  created_at: string | Date | null
}

export interface CommentContextPayload {
  ydoc: string
  start_pos: string
  end_pos: string
}

export interface CommentCreatePayload {
  clause_id: string
  quoted_text: string
  start_pos: string
  end_pos: string
  context: CommentContextPayload
}

export interface VersionRow {
  id: string
  contract_id: string
  number: number
  kind: 'snapshot' | 'json'
  snapshot: Uint8Array | null
  json: object | null
  created_at: string | Date | null
}

export type VersionPayload = { kind: 'snapshot'; snapshot: string } | { kind: 'json'; json: any }
