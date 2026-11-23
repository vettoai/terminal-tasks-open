import { Random, derive } from './generate.mjs'

export function focusedSchedule({ runs, fixtures }, reintroduced) {
  const serialSeed = derive(0x6954A2D3 ^ 0x31B9D74A)
  const offlineSeed = derive(0x6954A2D3 ^ 0xB2768E95)
  const serial = new Random(serialSeed), offline = new Random(offlineSeed)
  const selected = serial.shuffle(fixtures.map((_, index) => index)).slice(0, 12)
  const shapes = serial.shuffle(Array.from({ length: 12 }, (_, index) => index < 6))
  const restarts = new Set(serial.shuffle(Array.from({ length: 12 }, (_, index) => index)).slice(0, 6))
  const comparisons = selected.map((fixtureIndex, index) => {
    const rows = fixtures[fixtureIndex].versions
    const json = serial.pick(rows.filter(row => row.kind === 'json'))
    const snapshot = serial.pick(rows.filter(row => row.kind === 'snapshot'))
    const other = serial.pick(rows.filter(row => row.kind === 'snapshot' && row.id !== snapshot.id))
    const choices = shapes[index] ? [json, snapshot, other, json] : [snapshot, json, other, snapshot]
    return { fixtureIndex, versions: choices.map(row => row.id), restart: restarts.has(index) }
  })
  const candidates = runs.flatMap((run, index) => run.authoring ? [index] : [])
  const cells = offline.shuffle(['snapshot', 'json'].flatMap(kind => [false, true].flatMap(two => [false, true].flatMap(restart => [0, 1].map(() => ({ kind, two, restart }))))))
  const interruptions = cells.map(cell => {
    const eligible = candidates.filter(index => fixtures[index].versions.some(row => row.kind === cell.kind && reintroduced(fixtures[index], row).length))
    const fixtureIndex = offline.pick(eligible)
    candidates.splice(candidates.indexOf(fixtureIndex), 1)
    const version = offline.pick(fixtures[fixtureIndex].versions.filter(row => row.kind === cell.kind && reintroduced(fixtures[fixtureIndex], row).length))
    return { ...cell, fixtureIndex, version: version.id }
  })
  return { serial: { seed: serialSeed, rng: serial, cases: comparisons }, offline: { seed: offlineSeed, rng: offline, cases: interruptions } }
}

export function liveSelections(fixture, version) {
  const target = fixture.private.versions[version.id]
  return fixture.private.comments.flatMap(comment => {
    const clause = target.find(clause => clause.id === comment.clauseId)
    let from, to
    if (version.kind === 'snapshot') {
      const indices = comment.covered.map(id => clause.chars.findIndex(character => character.id === id))
      if (!indices.length || indices.some(index => index < 0)) return []
      from = indices[0]; to = indices.at(-1) + 1
    } else { from = clause.text.indexOf(comment.quote); to = from + comment.quote.length }
    return from > 0 && to - from >= 8 ? [{ comment: comment.id, clauseId: clause.id, from, to }] : []
  })
}

export function reviewLifetimeSchedule({ fixtures }) {
  const seed = derive(0x6954A2D3 ^ 0x5C27B8E1), rng = new Random(seed)
  const selections = (fixture, version) => liveSelections(fixture, version).filter(selection => {
    const review = fixture.private.comments.find(comment => comment.id === selection.comment)
    return !fixture.private.current.find(clause => clause.id === selection.clauseId).text.includes(review.quote)
  })
  const pool = fixtures.map((_, index) => index)
  const cells = rng.shuffle(['snapshot', 'json'].flatMap(kind => [false, true].map(restart => ({ kind, restart }))))
  const cases = cells.map(cell => {
    const fixtureIndex = rng.pick(pool.filter(index => fixtures[index].versions.some(row => row.kind === cell.kind && selections(fixtures[index], row).length)))
    pool.splice(pool.indexOf(fixtureIndex), 1)
    const fixture = fixtures[fixtureIndex]
    const version = rng.pick(fixture.versions.filter(row => row.kind === cell.kind && selections(fixture, row).length))
    return { ...cell, fixtureIndex, version: version.id, ...rng.pick(selections(fixture, version)) }
  })
  return { seed, rng, cases }
}

export function advanceLiveRange(span, from, to, insertedLength) {
  if (!span) return null
  const deleted = to - from
  const afterDelete = index => index <= from ? index : index >= to ? index - deleted : from
  const start = afterDelete(span.from), end = afterDelete(span.to)
  return end > start ? { from: start + (from <= start ? insertedLength : 0), to: end + (from < end ? insertedLength : 0) } : null
}

export function lifetimeSchedule({ runs, fixtures }, reintroduced) {
  const comparisonChoices = (fixture, row) => reintroduced(fixture, row).filter(candidate => fixture.private.current[candidate.clause].text.includes('.'))
  const comparisonSeed = derive(0x6954A2D3 ^ 0xD48C92B1)
  const liveSeed = derive(0x6954A2D3 ^ 0x7E139A64)
  const comparison = new Random(comparisonSeed), live = new Random(liveSeed)
  const comparisonPool = runs.flatMap((run, index) => run.authoring ? [index] : [])
  const comparisonCells = comparison.shuffle(['snapshot', 'json'].flatMap(kind => [false, true].flatMap(restart => [0, 1].map(() => ({ kind, restart })))))
  const comparisons = comparisonCells.map(cell => {
    const eligible = comparisonPool.filter(index => fixtures[index].versions.some(row => row.kind === cell.kind && comparisonChoices(fixtures[index], row).length))
    const fixtureIndex = comparison.pick(eligible), fixture = fixtures[fixtureIndex]
    comparisonPool.splice(comparisonPool.indexOf(fixtureIndex), 1)
    const version = comparison.pick(fixture.versions.filter(row => row.kind === cell.kind && comparisonChoices(fixture, row).length))
    const intermediate = comparison.pick(fixture.versions.filter(row => row.kind !== cell.kind))
    return { ...cell, fixtureIndex, version: version.id, intermediate: intermediate.id }
  })
  const livePool = fixtures.map((_, index) => index)
  const liveCells = live.shuffle(['snapshot', 'json'].flatMap(kind => [false, true].flatMap(restart => [0, 1, 2].map(() => ({ kind, restart })))))
  const comments = liveCells.map(cell => {
    const eligible = livePool.filter(index => fixtures[index].versions.some(row => row.kind === cell.kind && liveSelections(fixtures[index], row).length))
    const fixtureIndex = live.pick(eligible), fixture = fixtures[fixtureIndex]
    livePool.splice(livePool.indexOf(fixtureIndex), 1)
    const version = live.pick(fixture.versions.filter(row => row.kind === cell.kind && liveSelections(fixture, row).length))
    const selection = live.pick(liveSelections(fixture, version))
    return { ...cell, fixtureIndex, version: version.id, ...selection }
  })
  return { comparison: { seed: comparisonSeed, rng: comparison, cases: comparisons }, live: { seed: liveSeed, rng: live, cases: comments } }
}
