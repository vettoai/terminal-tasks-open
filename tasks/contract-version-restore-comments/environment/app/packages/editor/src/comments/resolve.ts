import * as Y from 'yjs'
import type { CommentRow } from '../types'

export function resolveCommentRange(ydoc: Y.Doc, comment: CommentRow): { from: number; to: number } {
  const start = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(new Uint8Array(comment.start_pos)), ydoc)
  const end = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(new Uint8Array(comment.end_pos)), ydoc)
  if (!start || !end || start.type !== end.type || end.index <= start.index) return { from: 0, to: 0 }
  return { from: start.index, to: end.index }
}
