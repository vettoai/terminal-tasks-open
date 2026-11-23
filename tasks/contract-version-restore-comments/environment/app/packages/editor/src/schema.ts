import { Node, mergeAttributes } from '@tiptap/core'
import { Schema } from '@tiptap/pm/model'

export const Clause = Node.create({
  name: 'clause', group: 'block', content: 'paragraph',
  addAttributes() { return { clauseId: { default: null } } },
  parseHTML() { return [{ tag: 'section[data-clause-id]', getAttrs: element => ({ clauseId: (element as HTMLElement).dataset.clauseId }) }] },
  renderHTML({ HTMLAttributes }) { return ['section', mergeAttributes({ 'data-clause-id': HTMLAttributes.clauseId }, HTMLAttributes), 0] },
})

export const clauseSchema = new Schema({ nodes: {
  doc: { content: 'clause+' },
  clause: { content: 'paragraph', attrs: { clauseId: { default: null } }, toDOM: node => ['section', { 'data-clause-id': node.attrs.clauseId }, 0] },
  paragraph: { content: 'text*', toDOM: () => ['p', 0] },
  text: {},
} })
