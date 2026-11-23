import * as Y from 'yjs'
import type { HocuspocusProvider } from '@hocuspocus/provider'
import { yXmlFragmentToProsemirrorJSON } from 'y-prosemirror'
import { clauses, clauseText, jsonClauses } from '../document'
import { httpBase } from '../config'
import type { VersionPayload } from '../types'

export async function restoreVersion(provider: HocuspocusProvider, versionId: string): Promise<void> {
  const response = await fetch(`${httpBase()}/contracts/${encodeURIComponent(provider.configuration.name)}/versions/${encodeURIComponent(versionId)}`)
  if (!response.ok) throw new Error(`Version unavailable: ${response.status}`)
  const version: VersionPayload = await response.json()
  let json: any
  if (version.kind === 'snapshot') {
    const snapshot = Y.decodeSnapshot(Uint8Array.from(atob(version.snapshot), character => character.charCodeAt(0)))
    const historical = Y.createDocFromSnapshot(provider.document, snapshot)
    json = yXmlFragmentToProsemirrorJSON(historical.getXmlFragment('default'))
    historical.destroy()
  } else {
    json = version.json
  }
  const selected = jsonClauses(json)
  provider.document.transact(() => {
    for (const clause of clauses(provider.document)) {
      const target = selected.find(item => item.id === clause.getAttribute('clauseId'))
      if (!target) throw new Error('Clause missing from version')
      const text = clauseText(clause)
      text.delete(0, text.length)
      text.insert(0, target.text)
    }
  }, 'version-history')
}
