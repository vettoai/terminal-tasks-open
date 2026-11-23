import * as Y from 'yjs'
import type { CommentRow } from '../types'
import { clauses, clauseText } from '../document'

export function resolveCommentRange(ydoc: Y.Doc, comment: CommentRow): { from: number; to: number } {
  const detached = { from: 0, to: 0 }
  const start = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(new Uint8Array(comment.start_pos)), ydoc)
  const end = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(new Uint8Array(comment.end_pos)), ydoc)
  const clause = clauses(ydoc).find(clause => clause.getAttribute('clauseId') === comment.clause_id)
  if (!clause || !start || !end || start.type !== clauseText(clause) || end.type !== start.type || end.index <= start.index) return detached
  return { from: start.index, to: end.index }
}
