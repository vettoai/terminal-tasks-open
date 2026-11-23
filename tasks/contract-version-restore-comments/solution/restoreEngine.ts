import * as Y from 'yjs'
import { createHash } from 'node:crypto'
import * as decoding from 'lib0/decoding'
import { pool } from './database'
import { clauses, clauseText, jsonClauses } from '../../editor/src/document'

type Character = { id: string; char: string }
type Note = { text: string; boundary: number; ids: string[]; origins?: string[]; lineage?: string[][]; gap?: number; source?: Character[] }
type Plan = { source: Character[]; base: Character[]; notes: Note[]; aliases?: Character[]; views?: Character[][] }
type Plans = { versionId: string; requestKey: string; commentIds: string[]; clauses: Record<string, Plan> }
const running = new WeakSet<Y.Doc>()
const queues = new Map<string, Promise<any>>()

function characters(text: Y.XmlText, deleted = false): Character[] {
  const result: Character[] = []
  for (let item = (text as any)._start; item; item = item.right) {
    if ((!deleted && item.deleted) || typeof item.content.str !== 'string') continue
    for (let offset = 0; offset < item.content.str.length; offset++) result.push({ id: `${item.id.client}:${item.id.clock + offset}`, char: item.content.str[offset] })
  }
  return result
}
function lcsPairs(source: Character[], target: string) {
  const width = target.length + 1
  const lengths = new Uint32Array((source.length + 1) * width)
  for (let left = source.length - 1; left >= 0; left--) for (let right = target.length - 1; right >= 0; right--) lengths[left * width + right] = source[left].char === target[right] ? lengths[(left + 1) * width + right + 1] + 1 : Math.max(lengths[(left + 1) * width + right], lengths[left * width + right + 1])
  const result = new Map<number, string>()
  let left = 0, right = 0
  while (left < source.length && right < target.length) {
    if (source[left].char === target[right]) { result.set(right, source[left].id); left++; right++ }
    else if (lengths[(left + 1) * width + right] >= lengths[left * width + right + 1]) left++
    else right++
  }
  return result
}
function rewrite(text: Y.XmlText, desired: { char: string; id?: string }[]) {
  const keep = new Set(desired.flatMap(character => character.id ? [character.id] : []))
  const current = characters(text)
  for (let index = current.length - 1; index >= 0; index--) if (!keep.has(current[index].id)) text.delete(index, 1)
  let index = 0
  while (index < desired.length) {
    if (desired[index].id) { index++; continue }
    let end = index + 1
    while (end < desired.length && !desired[end].id) end++
    text.insert(index, desired.slice(index, end).map(character => character.char).join(''))
    index = end
  }
  return characters(text)
}
function discover(text: Y.XmlText, plan: Plan, normalizing = false) {
  const known = new Set([...plan.source, ...plan.base].map(character => character.id).concat(plan.notes.flatMap(note => note.ids)))
  const full = characters(text, true), live = new Set(characters(text).map(character => character.id))
  const sourceIndices = new Map(plan.source.map((character, index) => [character.id, index]))
  let changed = false
  let boundary = 0
  for (let index = 0; index < full.length; index++) {
    const character = full[index]
    if (sourceIndices.has(character.id)) boundary = sourceIndices.get(character.id)! + 1
    if (!live.has(character.id) || known.has(character.id)) continue
    const group = [character]
    while (index + 1 < full.length && live.has(full[index + 1].id) && !known.has(full[index + 1].id)) group.push(full[++index])
    changed = true
    let origin: string | undefined, rightOrigin: string | undefined
    for (let item = (text as any)._start; item; item = item.right) {
      if (typeof item.content.str !== 'string') continue
      const offset = group[0].id.startsWith(`${item.id.client}:`) ? Number(group[0].id.split(':')[1]) - item.id.clock : -1
      if (offset >= 0 && offset < item.length) {
        origin = offset ? `${item.id.client}:${item.id.clock + offset - 1}` : item.origin && `${item.origin.client}:${item.origin.clock}`
        rightOrigin = item.rightOrigin && `${item.rightOrigin.client}:${item.rightOrigin.clock}`
        break
      }
    }
    const continuation = origin && origin.split(':')[0] === group[0].id.split(':')[0] && plan.notes.find(note => (note.origins || note.ids).includes(origin!))
    if (continuation) {
      const lineage = continuation.lineage || continuation.ids.map(id => [id])
      const right = lineage.findIndex(ids => ids.includes(rightOrigin!)), left = lineage.findIndex(ids => ids.includes(origin!))
      const offset = right >= 0 ? right : left >= 0 ? left + 1 : continuation.text.length
      continuation.text = continuation.text.slice(0, offset) + group.map(character => character.char).join('') + continuation.text.slice(offset)
      continuation.origins = [...new Set([...(continuation.origins || continuation.ids), ...group.map(character => character.id)])]
      continuation.ids.splice(offset, 0, ...group.map(character => character.id))
      lineage.splice(offset, 0, ...group.map(character => [character.id]))
      continuation.lineage = lineage
      continue
    }
    let gap: number | undefined
    if (normalizing) {
      const originalIds = new Set(plan.source.map(character => character.id))
      const freshIds = new Set(plan.base.filter(character => !originalIds.has(character.id)).map(character => character.id).concat(plan.notes.flatMap(note => note.ids)))
      let fresh = false
      for (let item = (text as any)._start; item; item = item.right) {
        if (group.some(character => character.id === `${item.id.client}:${item.id.clock}`)) {
          for (const origin of [item.origin, item.rightOrigin]) if (origin && freshIds.has(`${origin.client}:${origin.clock}`)) fresh = true
        }
      }
      if (fresh) {
        const current = characters(text), start = current.findIndex(character => character.id === group[0].id)
        const before = new Set(current.slice(0, start).map(character => character.id))
        gap = plan.base.filter(character => before.has(character.id)).length
      }
    }
    let typingSource: Character[] | undefined, typingBoundary = boundary, score = 0
    for (const view of plan.views || []) {
      const left = view.findIndex(character => character.id === origin), right = view.findIndex(character => character.id === rightOrigin)
      const matched = Number(left >= 0) + Number(right >= 0)
      if (matched > score) {
        score = matched; typingSource = view; typingBoundary = right >= 0 ? right : left + 1
      }
    }
    plan.notes.push({ text: group.map(character => character.char).join(''), boundary: typingBoundary, ids: group.map(character => character.id), origins: group.map(character => character.id), ...(typingSource ? { source: typingSource } : {}), ...(gap === undefined ? {} : { gap }) })
  }
  return changed
}
function applyPlan(text: Y.XmlText, plan: Plan, retainBase = false) {
  const current = characters(text)
  const live = new Set(current.map(character => character.id))
  const positions = new Map(current.map((character, index) => [character.id, index]))
  if (retainBase) plan.base = plan.base.filter(character => live.has(character.id))
  const baseIndices = new Map(plan.base.map((character, index) => [character.id, index]))
  const gaps = new Map<number, Note[]>()
  for (const note of plan.notes) {
    const source = note.source || plan.source
    let gap = plan.base.length
    for (let index = note.boundary; index < source.length; index++) {
      const found = baseIndices.get(source[index].id)
      if (found !== undefined) { gap = found; break }
    }
    if (retainBase && note.gap !== undefined) {
      const start = positions.get(note.ids[0])!
      gap = plan.base.filter(character => positions.get(character.id)! < start).length
    } else if (retainBase && note.ids.length === note.text.length && note.ids.every((id, index) => positions.has(id) && positions.get(id) === positions.get(note.ids[0])! + index)) {
      let left = 0
      for (let index = note.boundary - 1; index >= 0; index--) {
        const found = baseIndices.get(source[index].id)
        if (found !== undefined) { left = found + 1; break }
      }
      const start = positions.get(note.ids[0])!
      const currentGap = plan.base.filter(character => positions.get(character.id)! < start).length
      if (currentGap >= left && currentGap <= gap) gap = currentGap
    }
    const values = gaps.get(gap) || []; values.push(note); gaps.set(gap, values)
  }
  if (retainBase) for (const notes of gaps.values()) notes.sort((left, right) => positions.get(left.ids[0])! - positions.get(right.ids[0])!)
  const desired: { char: string; id?: string; note?: Note; baseIndex?: number }[] = []
  for (let index = 0; index <= plan.base.length; index++) {
    for (const note of gaps.get(index) || []) {
      const preserve = note.ids.length === note.text.length && note.ids.every(id => live.has(id))
      for (let offset = 0; offset < note.text.length; offset++) desired.push({ char: note.text[offset], note, id: preserve ? note.ids[offset] : undefined })
    }
    if (index < plan.base.length) desired.push({ char: plan.base[index].char, id: live.has(plan.base[index].id) ? plan.base[index].id : undefined, baseIndex: index })
  }
  for (;;) {
    const retained = desired.filter(character => character.id)
    const conflict = retained.findIndex((character, index) => index > 0 && positions.get(character.id!)! < positions.get(retained[index - 1].id!)!)
    if (conflict < 0) break
    const candidates = [retained[conflict - 1].note, retained[conflict].note].filter((note): note is Note => !!note)
    candidates.sort((left, right) => Number(left.gap !== undefined) - Number(right.gap !== undefined))
    if (!candidates.length) throw new Error('Incompatible retained character order')
    for (const character of desired) if (character.note === candidates[0]) character.id = undefined
  }
  for (const note of plan.notes) {
    note.origins = [...new Set([...(note.origins || []), ...note.ids])]
    note.lineage ||= note.ids.map(id => [id])
  }
  const final = rewrite(text, desired)
  for (const note of plan.notes) note.ids = []
  for (let index = 0; index < desired.length; index++) {
    if (desired[index].note) desired[index].note!.ids.push(final[index].id)
    else plan.base[desired[index].baseIndex!] = final[index]
  }
  for (const note of plan.notes) {
    note.origins = [...new Set([...(note.origins || []), ...note.ids])]
    note.lineage = note.ids.map((id, index) => [...new Set([...(note.lineage?.[index] || []), id])])
  }
  if (!retainBase) plan.aliases = plan.base.map(character => ({ ...character }))
}
async function anchorComments(document: Y.Doc, contractId: string, versionId: string) {
  const version = (await pool.query('SELECT * FROM versions WHERE id=$1 AND contract_id=$2', [versionId, contractId])).rows[0]
  const rows = (await pool.query('SELECT c.*,o.ydoc AS origin_view,o.start_pos AS origin_start,o.end_pos AS origin_end FROM comments c JOIN comment_contexts o ON o.comment_id=c.id WHERE c.contract_id=$1', [contractId])).rows
  let historical: Y.Doc | undefined
  if (version.kind === 'snapshot') historical = Y.createDocFromSnapshot(document, Y.decodeSnapshot(version.snapshot), new Y.Doc({ gc: false }))
  const plans = document.getMap('version-history').get('plan') as Plans
  for (const row of rows) {
    if (!plans.commentIds.includes(row.id)) continue
    const currentClause = clauses(document).find(clause => clause.getAttribute('clauseId') === row.clause_id)!
    const currentText = clauseText(currentClause), plan = plans.clauses[row.clause_id]
    let from = -1, to = -1
    if (historical) {
      const clause = clauses(historical).find(clause => clause.getAttribute('clauseId') === row.clause_id)!, text = clauseText(clause)
      const context = new Y.Doc({ gc: false }); Y.applyUpdate(context, row.origin_view)
      const start = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(row.origin_start), context)
      const end = Y.createAbsolutePositionFromRelativePosition(Y.decodeRelativePosition(row.origin_end), context)
      const covered = start && end && start.type === end.type ? characters(start.type as Y.XmlText).slice(start.index, end.index).map(character => character.id) : []
      const chars = characters(text), indices = covered.map(id => chars.findIndex(character => character.id === id))
      if (indices.length && indices.every(index => index >= 0)) { from = indices[0]; to = indices.at(-1)! + 1 }
      context.destroy()
    } else {
      const chosen = jsonClauses(version.json).find(clause => clause.id === row.clause_id)!
      from = chosen.text.indexOf(row.quoted_text); to = from + row.quoted_text.length
    }
    let startOffset = 0, endOffset = 0
    const chars = characters(currentText)
    const aliases = plan.aliases || plan.base
    if (from >= 0 && to > from && aliases[from] && aliases[to - 1]) {
      startOffset = chars.findIndex(character => character.id === aliases[from].id)
      endOffset = chars.findIndex(character => character.id === aliases[to - 1].id) + 1
      if (startOffset < 0 || endOffset <= startOffset) startOffset = endOffset = 0
    }
    const start = Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(currentText, startOffset, 0))
    const end = Y.encodeRelativePosition(Y.createRelativePositionFromTypeIndex(currentText, endOffset, endOffset > startOffset ? -1 : 0))
    await pool.query('UPDATE comments SET start_pos=$2,end_pos=$3 WHERE id=$1', [row.id, Buffer.from(start), Buffer.from(end)])
  }
  historical?.destroy()
}
export function normalize(document: Y.Doc, contractId: string) {
  if (running.has(document)) return
  const saved = document.getMap('version-history').get('plan') as Plans | undefined
  if (!saved) return
  const plans: Plans = JSON.parse(JSON.stringify(saved))
  let changed = false
  for (const clause of clauses(document)) {
    const text = clauseText(clause), plan = plans.clauses[clause.getAttribute('clauseId')!]
    if (!plan) continue
    const live = new Map(characters(text).map(character => [character.id, character.char]))
    plan.notes = plan.notes.flatMap(note => {
      const retained = note.ids.flatMap((id, index) => live.has(id) ? [index] : [])
      if (retained.length !== note.ids.length) changed = true
      const ids = retained.map(index => note.ids[index])
      const lineage = retained.map(index => note.lineage?.[index] || [note.ids[index]])
      return ids.length ? [{ ...note, ids, lineage, text: ids.map(id => live.get(id)).join('') }] : []
    })
    if (discover(text, plan, true)) changed = true
  }
  if (!changed) return
  running.add(document)
  try {
    document.transact(() => {
      for (const clause of clauses(document)) applyPlan(clauseText(clause), plans.clauses[clause.getAttribute('clauseId')!], true)
      document.getMap('version-history').set('plan', plans)
    }, 'version-continuity')
  } finally { running.delete(document) }
}
export function receive(document: Y.Doc, contractId: string, frame: Uint8Array, origin: unknown) {
  const decoder = decoding.createDecoder(frame)
  decoding.readVarString(decoder)
  const type = decoding.readVarUint(decoder)
  if (type !== 0 && type !== 4) return
  const kind = decoding.readVarUint(decoder)
  if (kind !== 1 && kind !== 2) return
  const update = decoding.readVarUint8Array(decoder), deletion = Y.decodeUpdate(update).ds
  const saved = document.getMap('version-history').get('plan') as Plans | undefined
  const forwarded = new Map<string, Set<string>>()
  if (kind === 2 && saved) for (const [clauseId, plan] of Object.entries(saved.clauses)) {
    const ids = new Set<string>()
    for (const note of plan.notes) for (const [index, aliases] of (note.lineage || note.ids.map(id => [id])).entries()) {
      if (aliases.some(alias => {
        const [client, clock] = alias.split(':').map(Number)
        return deletion.clients.get(client)?.some(interval => clock >= interval.clock && clock < interval.clock + interval.len)
      })) ids.add(note.ids[index])
    }
    forwarded.set(clauseId, ids)
  }
  running.add(document)
  try {
    Y.applyUpdate(document, update, origin)
    document.transact(() => {
      for (const clause of clauses(document)) {
        const text = clauseText(clause), ids = forwarded.get(clause.getAttribute('clauseId')!)
        const current = characters(text)
        for (let index = current.length - 1; index >= 0; index--) if (ids?.has(current[index].id)) text.delete(index, 1)
      }
    }, origin)
  } finally { running.delete(document) }
  normalize(document, contractId)
}

export function restore(document: Y.Doc, contractId: string, versionId: string, update: Uint8Array) {
  const previous = queues.get(contractId) || Promise.resolve()
  const next = previous.then(async () => {
    const caller = new Y.Doc({ gc: false }); Y.applyUpdate(caller, update)
    const source = clauses(caller).map(clause => ({ id: clause.getAttribute('clauseId')!, chars: characters(clauseText(clause)) }))
    const key = createHash('sha256').update(JSON.stringify([versionId, source])).digest('hex')
    const version = (await pool.query('SELECT * FROM versions WHERE id=$1 AND contract_id=$2', [versionId, contractId])).rows[0]
    if (!version) throw new Error('Unknown version')
    let historical: Y.Doc | undefined
    const selected = version.kind === 'snapshot' ? (() => {
      historical = Y.createDocFromSnapshot(document, Y.decodeSnapshot(version.snapshot), new Y.Doc({ gc: false }))
      return clauses(historical).map(clause => ({ id: clause.getAttribute('clauseId')!, chars: characters(clauseText(clause)) }))
    })() : jsonClauses(version.json).map(clause => ({ id: clause.id, chars: [...clause.text].map(char => ({ char, id: '' })) }))
    const previousPlan = document.getMap('version-history').get('plan') as Plans | undefined
    const commentIds = (await pool.query('SELECT id FROM comments WHERE contract_id=$1', [contractId])).rows.map(row => row.id)
    const duplicate = previousPlan?.requestKey === key && previousPlan.versionId === versionId && selected.every(target => {
      const base = previousPlan.clauses[target.id]?.base
      const clause = clauses(document).find(clause => clause.getAttribute('clauseId') === target.id)!
      const live = new Set(characters(clauseText(clause)).map(character => character.id))
      return base?.length === target.chars.length && base.every((character, index) => character.char === target.chars[index].char && live.has(character.id))
    })
    if (duplicate) {
      running.add(document)
      try {
        const active = document.getMap('version-history').get('plan') as Plans
        document.getMap('version-history').set('plan', { ...active, commentIds })
      } finally { running.delete(document) }
      await anchorComments(document, contractId, versionId)
      caller.destroy(); historical?.destroy(); return
    }
    const plans: Plans = { versionId, requestKey: key, commentIds, clauses: {} }
    for (const target of selected) {
      const original = source.find(clause => clause.id === target.id)!.chars
      const live = new Set(original.map(character => character.id))
      const alignment = version.kind === 'json' ? lcsPairs(original, target.chars.map(character => character.char).join('')) : new Map(target.chars.flatMap((character, index) => live.has(character.id) ? [[index, character.id] as [number, string]] : []))
      const earlier = previousPlan?.clauses[target.id]
      const views = [...(earlier?.views || []), ...(earlier ? [earlier.source] : []), original]
      const uniqueViews = views.filter((view, index) => views.findIndex(other => other.length === view.length && other.every((character, offset) => character.id === view[offset].id)) === index)
      const plan: Plan = { source: original, views: uniqueViews, base: target.chars.map((character, index) => ({ char: character.char, id: alignment.get(index) || '' })), notes: [] }
      const text = clauseText(clauses(document).find(clause => clause.getAttribute('clauseId') === target.id)!)
      discover(text, plan)
      for (const note of plan.notes) {
        note.lineage = note.ids.map(id => {
          for (const prior of earlier?.notes || []) {
            const index = prior.ids.indexOf(id)
            if (index >= 0) return [...new Set([...(prior.lineage?.[index] || []), id])]
          }
          return [id]
        })
        note.origins = [...new Set(note.lineage.flat())]
      }
      plans.clauses[target.id] = plan
    }
    running.add(document)
    try {
      document.transact(() => {
        for (const clause of clauses(document)) applyPlan(clauseText(clause), plans.clauses[clause.getAttribute('clauseId')!])
        document.getMap('version-history').set('plan', plans)
      }, 'version-history')
    } finally { running.delete(document) }
    await anchorComments(document, contractId, versionId)
    await pool.query('UPDATE contracts SET ydoc=$2 WHERE id=$1', [contractId, Buffer.from(Y.encodeStateAsUpdate(document))])
    caller.destroy(); historical?.destroy()
  })
  queues.set(contractId, next.catch(() => {}))
  return next
}
