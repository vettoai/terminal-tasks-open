import { describe, it, expect, vi } from 'vitest'
import * as Y from 'yjs'
import { restoreVersion } from './restoreVersion'

describe('version history', () => {
  it('shows a saved text export', async () => {
    const document = new Y.Doc({ gc: false })
    const clause = new Y.XmlElement('clause'); clause.setAttribute('clauseId', 'c-1')
    const paragraph = new Y.XmlElement('paragraph'); const text = new Y.XmlText()
    paragraph.insert(0, [text]); clause.insert(0, [paragraph]); document.getXmlFragment('default').insert(0, [clause]); text.insert(0, 'Payment within 30 days.')
    vi.stubGlobal('fetch', async () => ({ ok: true, json: async () => ({ kind: 'json', json: { type: 'doc', content: [{ type: 'clause', attrs: { clauseId: 'c-1' }, content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Payment within 15 days.' }] }] }] } }) }))
    await restoreVersion({ document, configuration: { name: 'draft' } } as any, 'draft-terms')
    expect(text.toString()).toBe('Payment within 15 days.')
    vi.unstubAllGlobals()
  })
})
