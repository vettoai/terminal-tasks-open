import * as Y from 'yjs'
import type { HocuspocusProvider } from '@hocuspocus/provider'
import { httpBase } from '../config'

export async function restoreVersion(provider: HocuspocusProvider, versionId: string): Promise<void> {
  const bytes = Y.encodeStateAsUpdate(provider.document)
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 8192) binary += String.fromCharCode(...bytes.subarray(offset, offset + 8192))
  const view = btoa(binary)
  const response = await fetch(`${httpBase()}/contracts/${encodeURIComponent(provider.configuration.name)}/restore`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ versionId, view }),
  })
  if (!response.ok) throw new Error(`Restore failed: ${response.status} ${await response.text()}`)
}
