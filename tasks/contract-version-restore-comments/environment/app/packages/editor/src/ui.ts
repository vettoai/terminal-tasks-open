import { Editor, Node } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import { HocuspocusProvider } from '@hocuspocus/provider'
import * as Y from 'yjs'
import { Clause } from './schema'
import { restoreVersion } from './versions/restoreVersion'
import { createComment } from '@contracts/editor'
import { resolveCommentRange } from './comments/resolve'
import { httpBase } from './config'

let editor: Editor
let provider: HocuspocusProvider
const plainDocument = Node.create({ name: 'doc', topNode: true, content: 'clause+' })
async function open() {
  editor?.destroy(); provider?.destroy(); provider?.configuration.websocketProvider.destroy()
  const name = (document.querySelector('#contract') as HTMLInputElement).value
  const ydoc = new Y.Doc({ gc: false })
  provider = new HocuspocusProvider({ url: 'ws://127.0.0.1:1234', name, document: ydoc })
  editor = new Editor({ element: document.querySelector('#editor')!, extensions: [StarterKit.configure({ history: false, document: false, heading: false, blockquote: false, bulletList: false, orderedList: false, listItem: false, codeBlock: false, hardBreak: false, horizontalRule: false, bold: false, italic: false, strike: false, code: false }), plainDocument, Clause, Collaboration.configure({ document: ydoc })] })
  const versions = await (await fetch(`${httpBase()}/contracts/${name}/versions`)).json()
  const history = document.querySelector('#history')!
  history.replaceChildren()
  for (const version of versions) {
    const button = document.createElement('button'); button.textContent = `Version ${version.number} · ${version.kind}`
    button.onclick = async () => { button.disabled = true; try { await restoreVersion(provider, version.id); await comments() } finally { button.disabled = false } }
    history.append(button)
  }
  ydoc.on('update', () => void comments())
  await comments()
}
async function comments() {
  const rows = await (await fetch(`${httpBase()}/contracts/${provider.configuration.name}/comments`)).json()
  const panel = document.querySelector('#comments')!; panel.replaceChildren()
  for (const row of rows) {
    row.start_pos = Uint8Array.from(atob(row.start_pos), character => character.charCodeAt(0))
    row.end_pos = Uint8Array.from(atob(row.end_pos), character => character.charCodeAt(0))
    const range = resolveCommentRange(provider.document, row)
    const line = document.createElement('p'); line.textContent = `${row.clause_id}: “${row.quoted_text}” — ${range.from === range.to ? 'detached' : `${range.from}–${range.to}`}`; panel.append(line)
  }
}
document.querySelector('#open')!.addEventListener('click', open)
document.querySelector('#comment')!.addEventListener('click', async () => {
  const selection = editor.state.selection
  const start = selection.$from
  if (start.depth < 2 || selection.$to.parent !== start.parent || selection.empty) return
  await createComment(provider, start.node(1).attrs.clauseId, start.parentOffset, selection.$to.parentOffset)
  await comments()
})
void open()
